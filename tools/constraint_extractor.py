"""
Constraint Extractor: 9B probes, 27B validates.

Pipeline:
  1. Word-level entity scan (9B) → validate (27B)
  2. Sentence-level axiom/hypothesis detection (9B) → validate (27B)
  3. Reformulation & discovery (9B) → validate (27B)

ChatML Instruct for Qwen 3.5, routed through nothink proxy if configured.
"""

import json
import os
import re
import sys
import time
from datetime import datetime

from llm_client import LLM, GEN_YES_NO, GEN_SHORT, GEN_MEDIUM, GEN_VALIDATE, is_yes

# ── LLM instance ────────────────────────────────────────────────────────────

llm = LLM()

# ── System prompts ──────────────────────────────────────────────────────────

SYS_ENTITY_PROBE = (
    "You are a precise linguistic analyzer. "
    "Given a source text and a word/phrase, decide if it is a named entity, "
    "domain concept, or key object in the text. Answer only Yes or No."
)

SYS_AXIOM_PROBE = (
    "You are a constraint analyzer. "
    "Given a source text and a sentence, decide if this sentence states "
    "a rule, law, constraint, or axiom (something assumed to always be true). "
    "Answer only Yes or No."
)

SYS_HYPOTHESIS_PROBE = (
    "You are a constraint analyzer. "
    "Given a source text and a sentence, decide if this sentence states "
    "a hypothesis, assumption, or uncertain claim that needs verification. "
    "Answer only Yes or No."
)

SYS_REFORMULATE = (
    "You are a concise writer. "
    "Reformulate the given constraint/axiom into a single short sentence. "
    "Keep the meaning, remove filler words."
)

SYS_DISCOVER = (
    "You are a constraint analyst. "
    "Given a source text, list any additional implicit axioms, rules, or constraints "
    "that are not stated directly but are implied. "
    "Return each on a new line, prefixed with '- '. If none, say 'None'."
)

SYS_VALIDATE = (
    "You are a senior analyst validating constraint extraction results. "
    "Given the source text and a proposed extraction (entities, axioms, hypotheses), "
    "review each item. For each, say KEEP or REJECT with a brief reason. "
    "Then add any MISSING items."
)

# ── Helpers ─────────────────────────────────────────────────────────────────

def extract_words(text: str) -> list[str]:
    """Extract candidate words (3+ chars, deduplicated)."""
    words = re.findall(r"\b[A-ZА-Яa-zа-яё]{2,}\b", text)
    seen = set()
    result = []
    for w in words:
        wl = w.lower()
        if wl not in seen and len(w) > 2:
            seen.add(wl)
            result.append(w)
    return result


def extract_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sents if len(s.strip()) > 10]


# ── Pipeline stages ─────────────────────────────────────────────────────────

def stage_entity_scan(source_text: str) -> list[dict]:
    """Probe 9B for each word: is it an entity?"""
    words = extract_words(source_text)
    print(f"\n  [Entity Scan] {len(words)} candidate words")

    entities = []
    for word in words:
        answer = llm.ask_9b(
            SYS_ENTITY_PROBE,
            f'Source text: "{source_text}"\n\nIs "{word}" an entity or key concept?',
            GEN_YES_NO,
        )
        verdict = is_yes(answer)
        marker = "+" if verdict else "·"
        print(f"    {marker} {word:<25} -> {answer}")
        entities.append({"word": word, "answer": answer, "is_entity": verdict})

    found = [e for e in entities if e["is_entity"]]
    print(f"  [Entity Scan] Found {len(found)} entities")
    return entities


def stage_axiom_hypothesis_scan(source_text: str) -> dict:
    """Probe 9B sentence by sentence: axiom? hypothesis?"""
    sentences = extract_sentences(source_text)
    print(f"\n  [Axiom/Hypothesis Scan] {len(sentences)} sentences")

    axioms = []
    hypotheses = []

    for sent in sentences:
        ans_ax = llm.ask_9b(
            SYS_AXIOM_PROBE,
            f'Source text: "{source_text}"\n\nSentence: "{sent}"\n\nIs this an axiom or rule?',
            GEN_YES_NO,
        )
        ans_hyp = llm.ask_9b(
            SYS_HYPOTHESIS_PROBE,
            f'Source text: "{source_text}"\n\nSentence: "{sent}"\n\nIs this a hypothesis?',
            GEN_YES_NO,
        )

        is_ax = is_yes(ans_ax)
        is_hyp = is_yes(ans_hyp)

        tag = ""
        if is_ax:
            tag += " [AXIOM]"
            axioms.append({"sentence": sent, "answer": ans_ax})
        if is_hyp:
            tag += " [HYPOTHESIS]"
            hypotheses.append({"sentence": sent, "answer": ans_hyp})
        if not tag:
            tag = " [-]"

        print(f"    {tag} {sent[:70]}...")

    print(f"  [Scan] Axioms: {len(axioms)}, Hypotheses: {len(hypotheses)}")
    return {"axioms": axioms, "hypotheses": hypotheses}


def stage_reformulate(items: list[dict], label: str) -> list[dict]:
    """Ask 9B to reformulate each axiom/hypothesis shorter."""
    print(f"\n  [Reformulate {label}] {len(items)} items")

    for item in items:
        short = llm.ask_9b(
            SYS_REFORMULATE,
            f'Reformulate concisely:\n"{item["sentence"]}"',
            GEN_SHORT,
        )
        item["short"] = short
        print(f"    {item['sentence'][:50]}...\n      -> {short}")

    return items


def stage_discover(source_text: str) -> list[str]:
    """Ask 9B: are there more implicit axioms?"""
    print(f"\n  [Discover] Looking for implicit axioms...")
    answer = llm.ask_9b(
        SYS_DISCOVER,
        f'Source text:\n"{source_text}"\n\nList any implicit axioms or constraints:',
        GEN_MEDIUM,
    )

    lines = [
        l.strip().lstrip("- ")
        for l in answer.splitlines()
        if l.strip().startswith("-")
    ]
    print(f"  [Discover] Found {len(lines)} implicit constraints:")
    for l in lines:
        print(f"    + {l}")

    return lines


def stage_validate(source_text: str, extraction: dict) -> str:
    """Send full extraction to 27B for validation."""
    print(f"\n  [Validate] Sending to 27B...")

    entities_str = ", ".join(
        e["word"] for e in extraction["entities"] if e["is_entity"]
    )
    axioms_str = "\n".join(f"  - {a['sentence']}" for a in extraction["axioms"])
    hyps_str = "\n".join(f"  - {h['sentence']}" for h in extraction["hypotheses"])
    implicit_str = "\n".join(f"  - {d}" for d in extraction.get("discovered", []))

    user_msg = (
        f'Source text:\n"{source_text}"\n\n'
        f"Extracted entities: {entities_str}\n\n"
        f"Extracted axioms:\n{axioms_str}\n\n"
        f"Extracted hypotheses:\n{hyps_str}\n\n"
        f"Discovered implicit constraints:\n{implicit_str}\n\n"
        f"Review each item: KEEP or REJECT (with reason). Then list any MISSING items."
    )

    validation = llm.ask_27b(SYS_VALIDATE, user_msg, GEN_VALIDATE)

    print(f"  [27B Validation]:\n")
    for line in validation.splitlines():
        print(f"    {line}")

    return validation


# ── Main ────────────────────────────────────────────────────────────────────

EXAMPLE_TEXT = """\
Every customer must have a unique email address. \
Orders cannot exceed the customer's credit limit. \
Products with zero stock should not appear in search results. \
It is assumed that all prices are in USD unless otherwise specified. \
Premium customers might receive a 15% discount on bulk orders, \
but this has not been confirmed by the finance team. \
Shipping costs are calculated based on weight and destination zone. \
Returns are accepted within 30 days of purchase.\
"""


def run_pipeline(source_text: str):
    print("=" * 70)
    print("  CONSTRAINT EXTRACTOR")
    print(llm.status())
    print("=" * 70)
    print(f"\n  Source text:\n  {source_text[:200]}...\n")

    t0 = time.perf_counter()

    # Stage 1: Entity scan
    entities = stage_entity_scan(source_text)

    # Stage 2: Axiom / Hypothesis scan
    ah = stage_axiom_hypothesis_scan(source_text)

    # Stage 3: Reformulate
    if ah["axioms"]:
        ah["axioms"] = stage_reformulate(ah["axioms"], "Axioms")
    if ah["hypotheses"]:
        ah["hypotheses"] = stage_reformulate(ah["hypotheses"], "Hypotheses")

    # Stage 4: Discover implicit
    discovered = stage_discover(source_text)

    # Stage 5: Validate with 27B
    extraction = {
        "entities": entities,
        "axioms": ah["axioms"],
        "hypotheses": ah["hypotheses"],
        "discovered": discovered,
    }
    validation = stage_validate(source_text, extraction)

    elapsed = time.perf_counter() - t0

    # Summary
    ent_count = sum(1 for e in entities if e["is_entity"])
    print(f"\n{'=' * 70}")
    print(f"  SUMMARY")
    print(
        f"  Entities: {ent_count}  |  Axioms: {len(ah['axioms'])}  "
        f"|  Hypotheses: {len(ah['hypotheses'])}  |  Discovered: {len(discovered)}"
    )
    print(f"  Total time: {elapsed:.1f}s")
    print(f"{'=' * 70}")

    # Save log
    log_dir = os.path.join(os.path.dirname(__file__), "compare_logs")
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"constraints_{ts}.json")

    log = {
        "timestamp": ts,
        "source_text": source_text,
        "entities": entities,
        "axioms": ah["axioms"],
        "hypotheses": ah["hypotheses"],
        "discovered": discovered,
        "validation_27b": validation,
        "elapsed_s": round(elapsed, 1),
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    print(f"  Log: {log_path}\n")
    return log


if __name__ == "__main__":
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        text = EXAMPLE_TEXT

    run_pipeline(text)
