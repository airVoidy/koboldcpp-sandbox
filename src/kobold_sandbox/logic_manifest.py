from __future__ import annotations

import itertools
import re
import warnings
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


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


class BranchVerificationResult(BaseModel):
    branch: str
    solutions: int
    sample_order: list[str] = Field(default_factory=list)


class LogicVerificationResult(BaseModel):
    stable_worlds: int
    branches: list[BranchVerificationResult] = Field(default_factory=list)


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

    alias_map = _build_entity_alias_map(entities)
    axioms = [
        normalized
        for line in axioms_block.splitlines()
        if (normalized := _normalize_formula(line, alias_map=alias_map))
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
                rules = [_normalize_formula(part, alias_map=alias_map) for part in rule_match.group(1).split(",")]
            else:
                rules = [_normalize_formula(raw_rules, alias_map=alias_map)]
            cleaned = [rule for rule in rules if rule]
            hypotheses.setdefault(branch_name, []).extend(cleaned)
            current_branch = branch_name
            continue
        if stripped.startswith("-") and current_branch:
            normalized = _normalize_formula(stripped, alias_map=alias_map)
            if normalized:
                hypotheses.setdefault(current_branch, []).append(normalized)

    return LogicManifest(entities=entities, axioms=axioms, hypotheses=hypotheses)


def parse_linear_logic_schema(text: str) -> LinearLogicSchema:
    entities_match = re.search(r"ENTITIES:\s*\[(.*?)\]", text, flags=re.DOTALL | re.IGNORECASE)
    entities: list[str] = []
    if entities_match:
        entities = [item.strip() for item in entities_match.group(1).split(",") if item.strip()]
    else:
        entities_line = re.search(r"ENTITIES:\s*(.+)", text, flags=re.IGNORECASE)
        if entities_line:
            entities = [item.strip() for item in entities_line.group(1).split(",") if item.strip()]

    rules_block = _section_block(text, "RULES", "BRANCHES")
    branches_block = _section_block(text, "BRANCHES", None)
    rules = [rule for line in rules_block.splitlines() if (rule := _normalize_schema_rule(line))]

    branches: dict[str, list[str]] = {}
    current_branch: str | None = None
    for line in branches_block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith(":") and not stripped.startswith("-"):
            current_branch = stripped[:-1].strip()
            branches.setdefault(current_branch, [])
            continue
        if stripped.startswith("-") and current_branch:
            rule = _normalize_schema_rule(stripped)
            if rule:
                branches[current_branch].append(rule)
    return LinearLogicSchema(entities=entities, rules=rules, branches=branches)


def linear_schema_to_manifest(schema: LinearLogicSchema) -> LogicManifest:
    axioms = [_schema_rule_to_formula(rule) for rule in schema.rules]
    hypotheses = {
        branch: [_schema_rule_to_formula(rule) for rule in rules]
        for branch, rules in schema.branches.items()
    }
    return LogicManifest(entities=schema.entities, axioms=axioms, hypotheses=hypotheses)


def verify_logic(manifest: LogicManifest) -> LogicVerificationResult:
    entities = manifest.entities
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

    stable_worlds = [world for world in worlds if all(check(world, axiom) for axiom in manifest.axioms)]
    branch_results: list[BranchVerificationResult] = []
    for branch, rules in manifest.hypotheses.items():
        author_rule = next((rule for rule in rules if "author ==" in rule), None)
        author_name = _author_name(author_rule) if author_rule else None
        valid_worlds = [world for world in stable_worlds if all(check(world, rule, author_name) for rule in rules)]
        sample_order = []
        if valid_worlds:
            sample = valid_worlds[0]
            sample_order = sorted(entities, key=lambda name: sample[entities.index(name)])
        branch_results.append(
            BranchVerificationResult(branch=branch, solutions=len(valid_worlds), sample_order=sample_order)
        )
    return LogicVerificationResult(stable_worlds=len(stable_worlds), branches=branch_results)


def _section_block(text: str, start: str, end: str | None) -> str:
    if end:
        pattern = rf"{start}:\s*(.*?){end}:"
    else:
        pattern = rf"{start}:\s*(.*)$"
    match = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _normalize_formula(text: str, alias_map: dict[str, str] | None = None) -> str:
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
    stripped = re.sub(r"^[\-\*\d\.\)\s]+", "", text.strip())
    stripped = stripped.split("#", 1)[0].strip()
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped


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
