"""
Compare two KoboldCPP models side-by-side.
Sends identical prompts in parallel, measures timing, logs everything.
Routes through nothink proxy if configured, otherwise strips think blocks locally.
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from llm_client import LLM, GEN_COMPARE, chatml

# ── Config ──────────────────────────────────────────────────────────────────

SYS = "You are a helpful assistant. Answer concisely."

TEST_PROMPTS = [
    {"name": "reasoning",   "user": "A farmer has 17 sheep. All but 9 run away. How many sheep does the farmer have left? Explain your reasoning step by step."},
    {"name": "creative",    "user": "Write a short 4-line poem about a cat who learned to code."},
    {"name": "extraction",  "user": 'Extract all colors mentioned in this text: "The azure sky met the crimson sunset, while emerald leaves rustled and a golden bird flew past the silver lake."\nReturn them as a JSON array.'},
    {"name": "translation", "user": 'Translate to Russian: "The quick brown fox jumps over the lazy dog."'},
    {"name": "code",        "user": "Write a Python function that checks if a string is a palindrome. Keep it short."},
]

LOG_DIR = os.path.join(os.path.dirname(__file__), "compare_logs")

# ── Core ────────────────────────────────────────────────────────────────────

def run_comparison(llm: LLM, prompt_entry: dict, params: dict) -> dict:
    """Run one prompt against both endpoints in parallel."""
    prompt_text = chatml(SYS, prompt_entry["user"])

    endpoints = {"9B": "9b", "27B": "27b"}
    results = {}

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(llm.generate_raw, which, prompt_text, params): label
            for label, which in endpoints.items()
        }
        for fut in as_completed(futures):
            label = futures[fut]
            results[label] = fut.result()

    return {
        "prompt_name": prompt_entry["name"],
        "prompt_user": prompt_entry["user"],
        "results": results,
    }


def print_comparison(comp: dict):
    print(f"\n{'='*70}")
    print(f"  TASK: {comp['prompt_name']}")
    print(f"{'='*70}")
    print(f"  Prompt: {comp['prompt_user'][:80]}...")
    print()

    for name, res in comp["results"].items():
        status = f"HTTP {res['status']}" if res["status"] != -1 else f"ERROR: {res.get('error','?')}"
        words = len(res["text"].split())
        print(f"  ┌─ {name}  [{status}]")
        print(f"  │  Time: {res['elapsed_s']}s  ~words: {words}")
        print(f"  │")
        for line in res["text"].strip().splitlines():
            print(f"  │  {line}")
        print(f"  └{'─'*50}")
        print()


def main():
    llm = LLM()
    print("Connecting...")
    print(llm.status())

    print(f"\nRunning {len(TEST_PROMPTS)} tasks...")
    print(f"Gen params: temp={GEN_COMPARE['temperature']} top_p={GEN_COMPARE['top_p']} max_len={GEN_COMPARE['max_length']}")

    all_comparisons = []
    for i, entry in enumerate(TEST_PROMPTS, 1):
        print(f"\n[{i}/{len(TEST_PROMPTS)}] {entry['name']}...")
        comp = run_comparison(llm, entry, GEN_COMPARE)
        all_comparisons.append(comp)
        print_comparison(comp)

    # Summary table
    endpoints = ["9B", "27B"]
    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    print(f"  {'Task':<15}  {'9B':>12}s  {'27B':>12}s")
    print(f"  {'-'*15}  {'-'*13}  {'-'*13}")

    totals = {n: 0.0 for n in endpoints}
    for comp in all_comparisons:
        print(f"  {comp['prompt_name']:<15}", end="")
        for name in endpoints:
            t = comp["results"][name]["elapsed_s"]
            totals[name] += t
            print(f"  {t:>12.3f}s", end="")
        print()

    print(f"  {'TOTAL':<15}", end="")
    for name in endpoints:
        print(f"  {totals[name]:>12.3f}s", end="")
    print()

    # Save log
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(LOG_DIR, f"compare_{ts}.json")
    log = {
        "timestamp": ts,
        "model_info": {n: llm.model_info(n.lower()) for n in endpoints},
        "gen_params": GEN_COMPARE,
        "comparisons": all_comparisons,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    print(f"\nLog saved: {path}")


if __name__ == "__main__":
    main()
