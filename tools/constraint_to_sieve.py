"""
Bridge: LLM extracts constraints from text → converts to sieve DSL → solves.

Uses 9B to probe/extract, 27B to validate & convert to formal rules.
Then SmartSieveEngine solves it.
Routes through nothink proxy if configured.

Flow:
  1. Feed puzzle text to 9B → extract categories + values
  2. Feed puzzle text to 9B → extract rules as natural language
  3. Feed rules to 27B → convert to s.pos() DSL strings
  4. Validate rules (27B)
  5. Solve with SmartSieveEngine
"""

import json
import os
import re
import time
from datetime import datetime

from llm_client import LLM, GEN_JSON, GEN_RULES, chatml, extract_json
from sieve_engine import SmartSieveEngine, verify_logic

# ── LLM instance ────────────────────────────────────────────────────────────

llm = LLM()

# ── Stage 1: Extract categories ────────────────────────────────────────────

SYS_CATEGORIES = """You extract structured data from logic puzzles.
Given a puzzle text, identify ALL categories and their possible values.
Output JSON: {"categories": {"category_name": ["val1","val2",...], ...}}
Every category must have the same number of values. Use exact names from the text."""

def stage_extract_categories(text):
    print("\n  [1/5] Extracting categories (9B)...")
    raw = llm.ask_9b(SYS_CATEGORIES, f"Puzzle:\n{text}\n\nExtract categories as JSON:", GEN_JSON)
    print(f"    Raw: {raw[:200]}")
    data = extract_json(raw)
    if data and "categories" in data:
        cats = data["categories"]
    elif isinstance(data, dict):
        cats = data
    else:
        print("    FAILED to parse categories")
        return None
    print(f"    Found {len(cats)} categories: {list(cats.keys())}")
    for k, v in cats.items():
        print(f"      {k}: {v}")
    return cats


# ── Stage 2: Extract rules as natural language ─────────────────────────────

SYS_RULES_NL = """You extract constraints from logic puzzles.
List every rule/clue as a separate numbered line.
Include ALL clues, even positional ones (first, middle, last, next to, left of, etc).
Be precise: use exact names from the text."""

def stage_extract_rules_nl(text):
    print("\n  [2/5] Extracting rules in natural language (9B)...")
    raw = llm.ask_9b(SYS_RULES_NL, f"Puzzle:\n{text}\n\nList all clues:", GEN_JSON)
    rules = [l.strip() for l in raw.splitlines() if l.strip() and re.match(r'^\d', l.strip())]
    print(f"    Found {len(rules)} rules:")
    for r in rules:
        print(f"      {r}")
    return rules


# ── Stage 3: Convert to DSL (27B) ──────────────────────────────────────────

SYS_CONVERT = """You convert natural language puzzle constraints into Python DSL expressions.

Available DSL:
  s.pos("category", "value")  → returns position index (0-based)

Patterns:
  Same house:       s.pos("cat1", "A") == s.pos("cat2", "B")
  Next to:          abs(s.pos("cat1", "A") - s.pos("cat2", "B")) == 1
  Immediately left: s.pos("cat1", "A") == s.pos("cat2", "B") - 1
  Immediately right:s.pos("cat1", "A") == s.pos("cat2", "B") + 1
  Left of (any):    s.pos("cat1", "A") < s.pos("cat2", "B")
  First position:   s.pos("cat", "A") == 0
  Middle position:  s.pos("cat", "A") == 2  (for 5 houses)
  Last position:    s.pos("cat", "A") == 4  (for 5 houses)

CATEGORY NAMES and VALUES must match EXACTLY as provided.
Output one Python expression per line, nothing else. No comments, no numbering."""

def stage_convert_to_dsl(rules_nl, categories):
    print("\n  [3/5] Converting to DSL (27B)...")
    cats_str = json.dumps(categories, indent=2)
    rules_str = "\n".join(rules_nl)
    raw = llm.ask_27b(
        SYS_CONVERT,
        f"Categories:\n{cats_str}\n\nRules:\n{rules_str}\n\nConvert each rule to DSL:",
        GEN_RULES,
    )
    dsl_rules = []
    for line in raw.splitlines():
        line = line.strip().rstrip(',')
        line = re.sub(r'^[\d]+[\.\)]\s*', '', line)
        line = re.sub(r'^[-*]\s*', '', line)
        if 's.pos(' in line:
            match = re.search(r'((?:abs\()?s\.pos\(.+)', line)
            if match:
                expr = match.group(1).strip()
                expr = re.sub(r'\s*#.*$', '', expr)
                dsl_rules.append(expr)

    print(f"    Generated {len(dsl_rules)} DSL rules:")
    for r in dsl_rules:
        print(f"      {r}")
    return dsl_rules


# ── Stage 4: Validate rules (27B) ──────────────────────────────────────────

SYS_VALIDATE_RULES = """You validate Python DSL constraint expressions for a logic puzzle.
Check each rule for:
  1. Category names and values match the provided categories exactly
  2. The expression is syntactically valid Python
  3. The logic matches the original natural language constraint

For each rule output: OK or FIXME: <corrected expression>
If a rule is wrong, provide the corrected version."""

def stage_validate_rules(dsl_rules, rules_nl, categories):
    print("\n  [4/5] Validating rules (27B)...")
    cats_str = json.dumps(categories, indent=2)
    pairs = "\n".join(f"NL: {nl}\nDSL: {dsl}" for nl, dsl in zip(rules_nl, dsl_rules))
    raw = llm.ask_27b(
        SYS_VALIDATE_RULES,
        f"Categories:\n{cats_str}\n\nRules to validate:\n{pairs}\n\nValidate each:",
        GEN_RULES,
    )
    print(f"    Validation output:")
    for line in raw.splitlines():
        if line.strip():
            print(f"      {line.strip()}")

    fixed = list(dsl_rules)
    for line in raw.splitlines():
        if "FIXME:" in line:
            match = re.search(r'FIXME:\s*(s\.pos\(.+)', line)
            if match:
                fix = match.group(1).strip()
                for i, r in enumerate(fixed):
                    if fix != r and 's.pos(' in fix:
                        fixed[i] = fix
                        print(f"    Applied fix: {r} → {fix}")
                        break
    return fixed


# ── Stage 5: Solve ─────────────────────────────────────────────────────────

def stage_solve(categories, dsl_rules):
    print("\n  [5/5] Solving...")
    engine = SmartSieveEngine(categories, dsl_rules)
    solutions = engine.solve(verbose=True)

    if solutions:
        print("\n  Solution:")
        print(engine.format_solution(solutions[0]))
    else:
        print("\n  No solution found! Rules may be contradictory.")

    return solutions


# ── Full pipeline ───────────────────────────────────────────────────────────

EXAMPLE_PUZZLE = """\
There are five houses in a row, each with a different color. \
In each house lives a person of a different nationality. \
Each person drinks a different beverage, smokes a different brand, and keeps a different pet.

1. The Englishman lives in the red house.
2. The Swede keeps dogs.
3. The Dane drinks tea.
4. The green house is immediately to the left of the white house.
5. The green house owner drinks coffee.
6. The person who smokes Pall Mall keeps birds.
7. The owner of the yellow house smokes Dunhill.
8. The person living in the center house drinks milk.
9. The Norwegian lives in the first house.
10. The person who smokes Blend lives next to the one who keeps cats.
11. The person who keeps horses lives next to the Dunhill smoker.
12. The person who smokes Blue Master drinks beer.
13. The German smokes Prince.
14. The Norwegian lives next to the blue house.
15. The person who smokes Blend has a neighbor who drinks water.\
"""


def run_pipeline(text=None):
    text = text or EXAMPLE_PUZZLE

    print("=" * 70)
    print("  Constraint-to-Sieve Pipeline")
    print(llm.status())
    print("=" * 70)
    print(f"\n  Input:\n  {text[:150]}...\n")

    t0 = time.perf_counter()

    cats = stage_extract_categories(text)
    if not cats:
        return

    rules_nl = stage_extract_rules_nl(text)
    if not rules_nl:
        return

    dsl_rules = stage_convert_to_dsl(rules_nl, cats)
    if not dsl_rules:
        return

    dsl_rules = stage_validate_rules(dsl_rules, rules_nl, cats)
    solutions = stage_solve(cats, dsl_rules)

    elapsed = time.perf_counter() - t0

    # Save log
    log_dir = os.path.join(os.path.dirname(__file__), "compare_logs")
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"sieve_{ts}.json")

    log = {
        "timestamp": ts,
        "input_text": text,
        "categories": cats,
        "rules_nl": rules_nl,
        "dsl_rules": dsl_rules,
        "solutions_count": len(solutions),
        "solution": solutions[0] if solutions else None,
        "elapsed_s": round(elapsed, 1),
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n  Total: {elapsed:.1f}s | Log: {log_path}")
    return solutions


if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    run_pipeline(text)
