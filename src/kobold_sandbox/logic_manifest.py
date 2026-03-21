from __future__ import annotations

import itertools
import re
import warnings
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .cases.einstein.schema_data import build_einstein_schema
from .core import build_schema_backends

_EINSTEIN_ALIAS_CACHE: dict[str, str] | None = None


LOGIC_MANIFEST_PROMPT = """Ты — аналитик логических структур. Твоя задача: прочитать текст рассуждений и извлечь из него формальную модель задачи.

Инструкции:

Выпиши список всех имен (entities).

Переведи условия задачи в краткие формулы (axioms), используя pos('Имя') для обозначения порядка (0-6).

Найди в тексте рассуждений <think> разные варианты (гипотезы). Выдели их в отдельные ветки (hypotheses).

Если в гипотезе предполагается, кто именно "Автор записки", запиши это как author == 'Имя'.

Формат вывода:
Используй простую структуру:
ENTITIES: [имена через запятую]
AXIOMS:
- формула 1
- формула 2
HYPOTHESES:
Branch Name: [формула, формула]

Текст для анализа:
{analysis_text}
"""


class LogicManifest(BaseModel):
    entities: list[str] = Field(default_factory=list)
    axioms: list[str] = Field(default_factory=list)
    hypotheses: dict[str, list[str]] = Field(default_factory=dict)


class ClaimResult(BaseModel):
    """Result of checking a single atomic claim against the world pool."""
    rule: str
    source: str  # "axiom" (from task) | "hypothesis" (from model)
    status: str  # "accepted" | "confirmed" | "hypothesis" | "declined"
    worlds_before: int
    worlds_after: int


class BranchVerificationResult(BaseModel):
    branch: str
    solutions: int
    sample_order: list[str] = Field(default_factory=list)


class LogicVerificationResult(BaseModel):
    stable_worlds: int
    branches: list[BranchVerificationResult] = Field(default_factory=list)
    claims: list[ClaimResult] = Field(default_factory=list)
    sample_order: list[str] = Field(default_factory=list)
    mode: str = "linear"


class LogicExamplePayload(BaseModel):
    source_text: str
    reasoning_text: str


class LogicExtractionResult(BaseModel):
    prompt: str
    raw_output: str
    manifest: LogicManifest
    verification: LogicVerificationResult


LINEAR_SCHEMA_PROMPT = """You convert linear-order reasoning into a compact schema.

Return only this format:
ENTITIES: [name, name]
RULES:
- same(A, B)
- next_to(A, B)
- directly_right(A, B)
- before(A, B)
- immediate_after(A, B)
- adjacent(A, B)
- one_of(name, [0, 6])
- at(name, 2)
- not_at(name, 0)
- before($author, Name)
- before(Name, $author)
BRANCHES:
Branch Name:
- author(Name)
- at(Name, 0)

Use 0-based positions.
Use $author only for the hidden author position.

Analysis text:
{analysis_text}
"""


class LinearLogicSchema(BaseModel):
    entities: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    branches: dict[str, list[str]] = Field(default_factory=dict)


class LinearSchemaExtractionResult(BaseModel):
    prompt: str
    raw_output: str
    linear_schema: LinearLogicSchema
    puzzle_schema: dict[str, Any] | None = None
    sieve_state: list[dict[str, list[str]]] | None = None
    stage_counts: str | None = None
    manifest: LogicManifest
    verification: LogicVerificationResult


class AtomicRuleSet(BaseModel):
    rules: list[str] = Field(default_factory=list)


def build_logic_manifest_prompt(analysis_text: str) -> str:
    return LOGIC_MANIFEST_PROMPT.format(analysis_text=analysis_text.strip())


def build_linear_schema_prompt(analysis_text: str) -> str:
    return LINEAR_SCHEMA_PROMPT.format(analysis_text=analysis_text.strip())


def prepare_reasoning_excerpt(text: str, max_chars: int = 9000) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^<think>\s*</think>\s*", "", cleaned, flags=re.DOTALL)
    cleaned = cleaned.split("### Финальный вывод", 1)[0]
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars]
    return cleaned.strip()


def load_first_thoughts_example(path: Path) -> LogicExamplePayload:
    text = path.read_text(encoding="utf-8")
    matches = re.findall(r"\{\{\[INPUT\]\}\}(.*?)\{\{\[OUTPUT\]\}\}(.*?)(?=\{\{\[INPUT\]\}\}|\Z)", text, flags=re.DOTALL)
    if not matches:
        raise ValueError(f"Could not parse thoughts example file: {path}")
    source_text, reasoning_text = matches[0]
    return LogicExamplePayload(
        source_text=_clean_example_chunk(source_text),
        reasoning_text=_clean_example_chunk(reasoning_text),
    )


def parse_logic_manifest(text: str) -> LogicManifest:
    entities_match = re.search(r"ENTITIES:\s*\[(.*?)\]", text, flags=re.DOTALL | re.IGNORECASE)
    entities = []
    if entities_match:
        entities = [item.strip() for item in entities_match.group(1).split(",") if item.strip()]
    else:
        entities_line = re.search(r"ENTITIES:\s*(.+)", text, flags=re.IGNORECASE)
        if entities_line:
            entities = [item.strip() for item in entities_line.group(1).split(",") if item.strip()]

    axioms_block = _section_block(text, "AXIOMS", "HYPOTHESES")
    hypotheses_block = _section_block(text, "HYPOTHESES", None)
    global_zero_based = bool(
        re.search(
            r"(?:pos\('[^']+'\)|\bauthor_pos\b|\b[a-z_][a-z0-9_]*\b)\s*(?:==|!=|<=|>=|<|>)\s*0\b",
            f"{axioms_block}\n{hypotheses_block}",
            flags=re.IGNORECASE,
        )
    )

    alias_map = _build_entity_alias_map(entities)
    axioms = [
        normalized
        for line in axioms_block.splitlines()
        if (normalized := _normalize_formula(line, alias_map=alias_map, zero_based=global_zero_based))
    ]

    hypotheses: dict[str, list[str]] = {}
    current_branch: str | None = None
    for line in hypotheses_block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if ":" in stripped and not stripped.startswith("-"):
            branch_name, raw_rules = stripped.split(":", 1)
            branch_name = branch_name.strip()
            rule_match = re.search(r"\[(.*)\]", raw_rules)
            if rule_match:
                rules = [_normalize_formula(part, alias_map=alias_map, zero_based=global_zero_based) for part in rule_match.group(1).split(",")]
            else:
                rules = [_normalize_formula(raw_rules, alias_map=alias_map, zero_based=global_zero_based)]
            cleaned = [rule for rule in rules if rule]
            hypotheses.setdefault(branch_name, []).extend(cleaned)
            current_branch = branch_name
            continue
        if stripped.startswith("-") and current_branch:
            normalized = _normalize_formula(stripped, alias_map=alias_map, zero_based=global_zero_based)
            if normalized:
                hypotheses.setdefault(current_branch, []).append(normalized)

    return LogicManifest(entities=entities, axioms=axioms, hypotheses=hypotheses)


def parse_atomic_rule_set(text: str) -> AtomicRuleSet:
    rules: list[str] = []
    collecting = False
    section_header = re.compile(r"^\s*(ATOMIC_RULES|RULES)\s*:\s*$", flags=re.IGNORECASE)
    stop_header = re.compile(
        r"^\s*(ENTITIES|AXIOMS|HYPOTHESES|BRANCHES)\s*:\s*$",
        flags=re.IGNORECASE,
    )

    for raw_line in text.replace("\r\n", "\n").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if section_header.match(line):
            collecting = True
            continue
        if collecting and stop_header.match(line):
            break
        if not collecting:
            continue

        stripped = re.sub(r"^[\-\*\d\.\)\s]+", "", line)
        stripped = stripped.split("#", 1)[0].strip().strip(",;")
        stripped = stripped.replace("s.pos(", "pos(")
        if not stripped:
            continue
        if stripped.upper() in {"ATOMIC_RULES:", "RULES:"}:
            continue
        if stripped in {"-", "*"}:
            continue
        rules.append(stripped)
    return AtomicRuleSet(rules=rules)


def parse_linear_logic_schema(text: str) -> LinearLogicSchema:
    schema_text = _extract_schema_body(text)
    entities_match = re.search(r"ENTITIES:\s*\[(.*?)\]", schema_text, flags=re.DOTALL | re.IGNORECASE)
    entities: list[str] = []
    if entities_match:
        entities = [item.strip() for item in entities_match.group(1).split(",") if item.strip()]
    else:
        entities_line = re.search(r"ENTITIES:\s*(.+)", schema_text, flags=re.IGNORECASE)
        if entities_line:
            entities = [item.strip() for item in entities_line.group(1).split(",") if item.strip()]

    rules_block = _section_block(schema_text, "RULES", "BRANCHES")
    branches_block = _section_block(schema_text, "BRANCHES", None)
    rules: list[str] = []
    for line in rules_block.splitlines():
        for rule in _split_schema_rules(line):
            if rule:
                rules.append(rule)

    branches: dict[str, list[str]] = {}
    current_branch: str | None = None
    anonymous_branch_index = 1
    for line in branches_block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        branch_name, inline_rules = _parse_branch_line(stripped)
        if branch_name is not None:
            current_branch = branch_name
            branch_rules = branches.setdefault(current_branch, [])
            branch_rules.extend(inline_rules)
            continue
        standalone_rules = _split_schema_rules(stripped)
        if standalone_rules:
            if current_branch is None:
                current_branch = f"Claim {anonymous_branch_index}"
                anonymous_branch_index += 1
                branches.setdefault(current_branch, [])
            branches[current_branch].extend(standalone_rules)
            if stripped.startswith("-"):
                current_branch = None
            continue
        if current_branch:
            branches[current_branch].extend(_split_schema_rules(stripped))
    if not entities:
        entities = _infer_entities_from_schema_rules(rules, branches)
    return LinearLogicSchema(entities=entities, rules=rules, branches=branches)


def linear_schema_to_manifest(schema: LinearLogicSchema) -> LogicManifest:
    axioms = [_schema_rule_to_formula(rule) for rule in schema.rules]
    hypotheses = {
        branch: [_schema_rule_to_formula(rule) for rule in rules]
        for branch, rules in schema.branches.items()
    }
    return LogicManifest(entities=schema.entities, axioms=axioms, hypotheses=hypotheses)


def verify_logic(manifest: LogicManifest) -> LogicVerificationResult:
    if _looks_like_einstein_manifest(manifest):
        return verify_einstein_logic(manifest)

    entities = manifest.entities
    if not entities:
        return LogicVerificationResult(stable_worlds=0, mode="atomic")

    worlds = list(itertools.permutations(range(len(entities))))
    alias_map = _build_entity_alias_map(entities)

    def check(world: tuple[int, ...], rule: str, author_name: str | None = None) -> bool:
        def pos(name: str) -> int:
            return world[entities.index(name)]

        alias_ctx = {
            alias: pos(entity_name)
            for alias, entity_name in alias_map.items()
            if entity_name in entities
        }
        ctx = {
            "pos": pos,
            "abs": abs,
            "author": author_name,
            "author_pos": pos(author_name) if author_name in entities else -1,
            "exists": lambda _item, cond=True: cond,
            **alias_ctx,
        }
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                return bool(eval(rule, {"__builtins__": {}}, ctx))
        except Exception:
            return True

    # Build tagged rules: (rule_str, source_label)
    tagged_rules: list[tuple[str, str]] = []
    for ax in manifest.axioms:
        tagged_rules.append((ax, "axiom"))
    for _branch, rules in manifest.hypotheses.items():
        for r in rules:
            tagged_rules.append((r, "hypothesis"))

    # Cascading sieve: check each rule against current world pool
    pool = list(worlds)
    claim_results: list[ClaimResult] = []

    for rule, source in tagged_rules:
        before = len(pool)
        has_author = "author" in rule.lower()

        if has_author:
            filtered = [w for w in pool if any(check(w, rule, c) for c in entities)]
        else:
            filtered = [w for w in pool if check(w, rule)]

        after = len(filtered)

        if after == 0:
            status = "declined"
            # Don't filter pool — skip contradicting rule
        elif source == "axiom":
            status = "accepted"
            pool = filtered  # axioms always accepted, filter pool
        elif after == before:
            status = "confirmed"  # follows from axioms — true in all remaining worlds
            # No filtering needed, pool unchanged
        else:
            status = "hypothesis"  # compatible but not proven, narrows space
            pool = filtered  # accept provisionally, filter pool

        claim_results.append(ClaimResult(
            rule=rule, source=source, status=status,
            worlds_before=before, worlds_after=after,
        ))

    sample_order = []
    if pool:
        s = pool[0]
        sample_order = sorted(entities, key=lambda n: s[entities.index(n)])

    return LogicVerificationResult(
        stable_worlds=len(pool),
        claims=claim_results,
        sample_order=sample_order,
        mode="atomic",
    )


def verify_einstein_logic(manifest: LogicManifest) -> LogicVerificationResult:
    bundle = build_schema_backends(build_einstein_schema())
    solved_state = bundle.permutation.solve()
    alias_map = _build_einstein_alias_map()

    def pos(name: str) -> int:
        canonical = _canonicalize_einstein_name(name, alias_map=alias_map)
        if canonical == "$author":
            return -1
        if ":" in canonical:
            category, value = canonical.split(":", 1)
            for house_index, house in enumerate(solved_state):
                if house.get(category) == value:
                    return house_index
            raise ValueError(name)
        raise ValueError(name)

    def check(rule: str, author_name: str | None = None) -> bool:
        ctx = {
            "pos": pos,
            "abs": abs,
            "author": author_name,
            "author_pos": pos(author_name) if author_name else -1,
            "exists": lambda _item, cond=True: cond,
        }
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                return bool(eval(rule, {"__builtins__": {}}, ctx))
        except Exception:
            return False

    branch_results: list[BranchVerificationResult] = []
    for branch, rules in manifest.hypotheses.items():
        author_rule = next((rule for rule in rules if "author ==" in rule), None)
        author_name = _author_name(author_rule) if author_rule else None
        is_valid = all(check(rule, author_name) for rule in rules)
        sample_order = [f"house-{index + 1}" for index in range(len(solved_state))]
        branch_results.append(
            BranchVerificationResult(
                branch=branch,
                solutions=1 if is_valid else 0,
                sample_order=sample_order if is_valid else [],
            )
        )
    return LogicVerificationResult(stable_worlds=1, branches=branch_results, mode="einstein")


def _section_block(text: str, start: str, end: str | None) -> str:
    if end:
        pattern = rf"^\s*{start}\s*:\s*(.*?)(?=^\s*{end}\s*:)"
    else:
        pattern = rf"^\s*{start}\s*:\s*(.*)$"
    match = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""


def _normalize_formula(text: str, alias_map: dict[str, str] | None = None, zero_based: bool = False) -> str:
    stripped = text.strip()
    stripped = re.sub(r"^[\-\*\d\.\)\s]+", "", stripped)
    stripped = re.sub(r"\s*\(invalid.*$", "", stripped, flags=re.IGNORECASE)
    stripped = stripped.replace("≤", "<=").replace("≥", ">=").replace("≠", "!=")
    stripped = stripped.replace(" = ", " == ")
    stripped = re.sub(r"\s=\s", " == ", stripped)
    stripped = re.sub(r"\bOR\b", "or", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\bAND\b", "and", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\bauthor\s*=\s*['\"](.*?)['\"]", r"author == '\1'", stripped, flags=re.IGNORECASE)
    stripped = re.sub(
        r"(?P<lhs>(?:pos\('[^']+'\)|[a-zA-Z_][a-zA-Z0-9_]*))\s*==\s*(?P<first>\d+)\s+or\s+(?P<second>\d+)\b",
        lambda match: f"({match.group('lhs')} == {match.group('first')} or {match.group('lhs')} == {match.group('second')})",
        stripped,
        flags=re.IGNORECASE,
    )
    if alias_map:
        stripped = _rewrite_alias_formula(stripped, alias_map)
    if not zero_based:
        stripped = re.sub(
            r"(pos\('[^']+'\)\s*(?:==|!=|<=|>=|<|>)\s*)(\d+)",
            lambda match: f"{match.group(1)}{int(match.group(2)) - 1}",
            stripped,
        )
        stripped = re.sub(
            r"\b([a-z_][a-z0-9_]*)\s*(==|!=|<=|>=|<|>)\s*(\d+)\b",
            lambda match: f"{match.group(1)} {match.group(2)} {int(match.group(3)) - 1}",
            stripped,
            flags=re.IGNORECASE,
        )
    stripped = stripped.replace("pos('Автор')", "author_pos")
    if "author" not in stripped.lower() and not _looks_like_expression(stripped):
        return ""
    return stripped.strip()


def _author_name(rule: str) -> str | None:
    match = re.search(r"author\s*==\s*['\"](.*?)['\"]", rule)
    return match.group(1).strip() if match else None


def _clean_example_chunk(text: str) -> str:
    cleaned = text.replace("\\n", "\n").strip().strip('",')
    cleaned = cleaned.split("[<|h|", 1)[0]
    return cleaned.strip()


def _looks_like_einstein_manifest(manifest: LogicManifest) -> bool:
    known_markers = {
        "Норвежец", "Англичанин", "Испанец", "Украинец", "Японец",
        "Norwegian", "English", "Spanish", "Ukrainian", "Japanese",
        "Красный", "Синий", "Зелёный", "Жёлтый", "Белый",
        "Red", "Blue", "Green", "Yellow", "White",
        "Зебра", "Вода", "Молоко", "Kool", "Parliament",
    }
    schema = build_einstein_schema()
    canonical_entities = {
        f"{category}:{value}"
        for category, values in schema.categories.items()
        for value in values
    }
    canonical_values = {
        value
        for values in schema.categories.values()
        for value in values
    }
    score = sum(
        1
        for entity in manifest.entities
        if entity in known_markers or entity in canonical_entities or entity in canonical_values
    )
    if score >= 4:
        return True
    joined = " ".join(manifest.axioms + [rule for rules in manifest.hypotheses.values() for rule in rules])
    return sum(1 for token in (known_markers | canonical_entities | canonical_values) if token in joined) >= 4


def _canonicalize_einstein_name(name: str | None, *, alias_map: dict[str, str] | None = None) -> str:
    if not name:
        return ""
    cleaned = str(name).strip().strip("'\"")
    if cleaned == "$author":
        return cleaned
    effective_alias_map = alias_map or _build_einstein_alias_map()
    normalized = _surface_key(cleaned)
    return effective_alias_map.get(normalized, cleaned)


def _build_einstein_alias_map() -> dict[str, str]:
    global _EINSTEIN_ALIAS_CACHE
    if _EINSTEIN_ALIAS_CACHE is not None:
        return _EINSTEIN_ALIAS_CACHE

    schema = build_einstein_schema()
    alias_map: dict[str, str] = {}
    mapped_facts: set[str] = set()

    for rule in schema.rules:
        statement = str((rule.metadata or {}).get("statement", "") or "")
        used_mentions: set[str] = set()
        for fact in rule.fact:
            if not isinstance(fact, str) or ":" not in fact:
                continue
            category, value = fact.split(":", 1)
            for candidate in _extract_einstein_mentions(statement, category):
                key = _surface_key(candidate)
                if key and key not in used_mentions:
                    alias_map[key] = fact
                    used_mentions.add(key)
                    mapped_facts.add(fact)
                    break

    reference_text = _load_einstein_reference_text()
    for category, values in schema.categories.items():
        remaining_facts = [f"{category}:{value}" for value in values if f"{category}:{value}" not in mapped_facts]
        if not remaining_facts:
            continue
        remaining_mentions: list[str] = []
        seen_keys: set[str] = set()
        for mention in _extract_einstein_mentions(reference_text, category):
            key = _surface_key(mention)
            if key and key not in alias_map and key not in seen_keys:
                remaining_mentions.append(mention)
                seen_keys.add(key)
        if len(remaining_mentions) == len(remaining_facts):
            for mention, fact in zip(remaining_mentions, remaining_facts):
                alias_map[_surface_key(mention)] = fact

    for category, values in schema.categories.items():
        for value in values:
            fact = f"{category}:{value}"
            alias_map[_surface_key(value)] = fact
            alias_map[_surface_key(fact)] = fact

    _EINSTEIN_ALIAS_CACHE = alias_map
    return alias_map


def _extract_einstein_mentions(text: str, category: str) -> list[str]:
    if not text:
        return []
    cleaned = text.replace("ё", "е").replace("Ё", "Е")
    patterns = {
        "nation": [
            r"\b[А-ЯЁ][а-яё]+(?:ец|анин)\b",
            r"\b[А-ЯЁ][а-яё]+ца\b",
        ],
        "color": [
            r"\b([А-ЯЁа-яё]+)\s+дом",
        ],
        "drink": [
            r"(?:пь[её]т|пьют)\s+([А-ЯЁа-яё]+(?:\s+[А-ЯЁа-яё]+)?)",
        ],
        "pet": [
            r"(?:есть|держит|держат|разводит)\s+([А-ЯЁа-яё]+(?:\s+[А-ЯЁа-яё]+)?)",
        ],
        "smoke": [
            r"(?:курит|курят)\s+([A-Za-z][A-Za-z ]*[A-Za-z]|[А-ЯЁа-яё]+)",
        ],
    }
    results: list[str] = []
    for pattern in patterns.get(category, []):
        for match in re.finditer(pattern, cleaned, flags=re.IGNORECASE):
            value = match.group(1) if match.groups() else match.group(0)
            value = re.sub(r"\b(дом|доме|дома)\b", "", value, flags=re.IGNORECASE).strip(" ,.")
            if value:
                results.append(value)
    return results


def _load_einstein_reference_text() -> str:
    path = Path(__file__).resolve().parents[2] / "examples" / "einstein_case" / "question.txt"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _surface_key(text: str) -> str:
    normalized = text.lower().replace("ё", "е")
    normalized = re.sub(r"[^a-zа-я0-9\s]+", " ", normalized, flags=re.IGNORECASE)
    words = [word for word in normalized.split() if word]
    stripped_words = [_strip_surface_suffixes(word) for word in words]
    return " ".join(word for word in stripped_words if word).strip()


def _strip_surface_suffixes(word: str) -> str:
    suffixes = (
        "анин", "янин", "цами", "ями", "ами", "ями", "ого", "ему", "ому", "ыми", "ими",
        "ями", "ами", "ая", "яя", "ое", "ее", "ом", "ем", "ым", "им", "ой", "ый", "ий",
        "ую", "юю", "ов", "ев", "ец", "ца", "у", "ю", "а", "я", "ы", "и", "е", "о", "ь",
    )
    for suffix in suffixes:
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _build_entity_alias_map(entities: list[str]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for entity in entities:
        base = _slugify_entity(entity)
        variants = {
            base,
            base.replace("ya", "ia"),
            base.replace("fy", "fiy"),
            base.replace("ey", "ei"),
            base[:-1] if base.endswith("a") else base,
        }
        for variant in {item for item in variants if item}:
            for alias in (variant, f"{variant}_pos", f"pos_{variant}"):
                alias_map[alias] = entity
    return alias_map


def _slugify_entity(entity: str) -> str:
    translit = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
        "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
        "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
        "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    parts: list[str] = []
    for char in entity.lower().strip():
        if char in translit:
            parts.append(translit[char])
        elif char.isalnum():
            parts.append(char)
        else:
            parts.append("_")
    return re.sub(r"_+", "_", "".join(parts)).strip("_")


def _rewrite_alias_formula(text: str, alias_map: dict[str, str]) -> str:
    rewritten = text
    for alias, entity in sorted(alias_map.items(), key=lambda item: len(item[0]), reverse=True):
        rewritten = re.sub(rf"\b{re.escape(alias)}\b", f"pos('{entity}')", rewritten)
    return rewritten


def _looks_like_expression(text: str) -> bool:
    return any(token in text for token in ("pos(", "author", "==", "!=", "<=", ">=", "<", ">"))


def _normalize_schema_rule(text: str) -> str:
    stripped = text.strip()
    stripped = re.sub(r"^```[a-z0-9_-]*\s*$", "", stripped, flags=re.IGNORECASE)
    stripped = stripped.strip("`")
    stripped = re.sub(r"^[\-\*\u2022\d\.\)\]\s]+", "", stripped)
    stripped = stripped.split("#", 1)[0].strip()
    stripped = stripped.strip().strip(",;")
    stripped = stripped.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    stripped = stripped.replace("—", "-").replace("–", "-")
    stripped = re.sub(r"^(RULES|BRANCHES)\s*:\s*$", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\bimmediately_after\s*\(", "immediate_after(", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\badjacent_to\s*\(", "adjacent(", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\bnextto\s*\(", "next_to(", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\boneof\s*\(", "one_of(", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\bauthor\s*==\s*['\"](.*?)['\"]", r"author(\1)", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\bauthor\s*=\s*['\"](.*?)['\"]", r"author(\1)", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped


def _extract_schema_body(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").strip()
    fenced_blocks = re.findall(r"```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)```", cleaned)
    for block in fenced_blocks:
        if re.search(r"^\s*(?:ENTITIES|RULES)\s*:", block, flags=re.IGNORECASE | re.MULTILINE):
            cleaned = block.strip()
            break

    start_match = re.search(r"^\s*ENTITIES\s*:", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    if start_match:
        cleaned = cleaned[start_match.start():]
    else:
        start_match = re.search(r"^\s*RULES\s*:", cleaned, flags=re.IGNORECASE | re.MULTILINE)
        if start_match:
            cleaned = cleaned[start_match.start():]
    return cleaned


def _split_schema_rules(text: str) -> list[str]:
    stripped = _normalize_schema_rule(text)
    if not stripped:
        return []
    if stripped.startswith("[") and stripped.endswith("]"):
        return [item for item in (_normalize_schema_rule(part) for part in _split_top_level(stripped[1:-1])) if item]
    return [stripped]


def _parse_branch_line(text: str) -> tuple[str | None, list[str]]:
    stripped = _normalize_schema_rule(text)
    if not stripped or "(" in stripped.split(":", 1)[0]:
        return None, []
    if ":" not in stripped:
        return None, []

    branch_name, tail = stripped.split(":", 1)
    branch_name = branch_name.strip().strip("[]")
    if not branch_name:
        return None, []

    tail = tail.strip()
    if not tail:
        return branch_name, []
    return branch_name, _split_schema_rules(tail)


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _infer_entities_from_schema_rules(rules: list[str], branches: dict[str, list[str]]) -> list[str]:
    entities: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        for entity in _entities_from_rule(rule):
            if entity not in seen:
                seen.add(entity)
                entities.append(entity)
    for branch_rules in branches.values():
        for rule in branch_rules:
            for entity in _entities_from_rule(rule):
                if entity not in seen:
                    seen.add(entity)
                    entities.append(entity)
    return entities


def _entities_from_rule(rule: str) -> list[str]:
    match = re.match(r"^\s*([a-z_][a-z0-9_]*)\s*\((.*)\)\s*$", rule, flags=re.IGNORECASE)
    if not match:
        return []
    fn_name = match.group(1).lower()
    args = [item.strip() for item in _split_top_level(match.group(2))]
    if fn_name == "author" and args:
        return _entity_like_terms([args[0]])
    return _entity_like_terms(args)


def _entity_like_terms(args: list[str]) -> list[str]:
    entities: list[str] = []
    for arg in args:
        cleaned = arg.strip()
        if not cleaned or cleaned == "$author":
            continue
        if cleaned.startswith("[") and cleaned.endswith("]"):
            continue
        if re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
            continue
        if cleaned.lower() in {"true", "false", "null", "none"}:
            continue
        cleaned = cleaned.strip("'\"")
        if not cleaned or cleaned == "$author":
            continue
        entities.append(cleaned)
    return entities


def _schema_rule_to_formula(rule: str) -> str:
    match = re.fullmatch(r"same\((.+?),\s*(.+?)\)", rule)
    if match:
        return f"{_schema_term(match.group(1))} == {_schema_term(match.group(2))}"
    match = re.fullmatch(r"next_to\((.+?),\s*(.+?)\)", rule)
    if match:
        return f"abs({_schema_term(match.group(1))} - {_schema_term(match.group(2))}) == 1"
    match = re.fullmatch(r"directly_right\((.+?),\s*(.+?)\)", rule)
    if match:
        return f"{_schema_term(match.group(2))} == {_schema_term(match.group(1))} + 1"
    match = re.fullmatch(r"before\((.+?),\s*(.+?)\)", rule)
    if match:
        return f"{_schema_term(match.group(1))} < {_schema_term(match.group(2))}"
    match = re.fullmatch(r"immediate_after\((.+?),\s*(.+?)\)", rule)
    if match:
        return f"{_schema_term(match.group(1))} == {_schema_term(match.group(2))} + 1"
    match = re.fullmatch(r"adjacent\((.+?),\s*(.+?)\)", rule)
    if match:
        return f"abs({_schema_term(match.group(1))} - {_schema_term(match.group(2))}) == 1"
    match = re.fullmatch(r"one_of\((.+?),\s*\[(.*?)\]\)", rule)
    if match:
        name = _schema_term(match.group(1))
        values = [item.strip() for item in match.group(2).split(",") if item.strip()]
        return "(" + " or ".join(f"{name} == {value}" for value in values) + ")"
    match = re.fullmatch(r"at\((.+?),\s*(\d+)\)", rule)
    if match:
        return f"{_schema_term(match.group(1))} == {match.group(2)}"
    match = re.fullmatch(r"not_at\((.+?),\s*(\d+)\)", rule)
    if match:
        return f"{_schema_term(match.group(1))} != {match.group(2)}"
    match = re.fullmatch(r"author\((.+?)\)", rule)
    if match:
        name = match.group(1).strip().strip("'\"")
        return f"author == '{name}'"
    return rule


def _schema_term(term: str) -> str:
    cleaned = term.strip()
    if cleaned == "$author":
        return "author_pos"
    cleaned = cleaned.strip("'\"")
    return f"pos('{cleaned}')"
