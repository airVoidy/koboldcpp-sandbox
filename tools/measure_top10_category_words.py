from __future__ import annotations

import json
import time
from pathlib import Path

import httpx


TEXT_PATH = Path(r"C:\llm\KoboldCPP agentic sandbox\tools\probe_wordlist_case.txt")
MODELS = {
    "5001_9b": "http://localhost:5001/api/v1/generate",
    "5050_27b": "http://192.168.1.15:5050/api/v1/generate",
}


def build_prompt(text: str) -> str:
    return f"""Из текста выпиши top 10 слов или коротких фрагментов для каждой категории.

Категории:
1 поза
2 цвет глаз
3 цвет волос
4 действие/жест
5 отличительные особенности демоницы
6 аниме
8 другое
9 ничего из вышеперечисленного

Формат ответа строго такой:
1: item, item, item
2: item, item, item
3: item, item, item
4: item, item, item
5: item, item, item
6: item, item, item
8: item, item, item
9: item, item, item

Правила:
- без пояснений
- только слова или короткие фрагменты из текста
- можно меньше 10, если в тексте мало примеров
- не повторяй один и тот же элемент в нескольких категориях без необходимости

Текст:
<<<
{text}
>>>
"""


def run_one(label: str, url: str, prompt: str) -> dict:
    started = time.perf_counter()
    with httpx.Client(trust_env=False, timeout=180.0) as client:
        resp = client.post(
            url,
            json={
                "prompt": prompt,
                "temperature": 0.0,
                "max_length": 1200,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    latency_ms = int((time.perf_counter() - started) * 1000)
    out = str(data.get("results", [{}])[0].get("text") or "")
    return {
        "label": label,
        "latency_ms": latency_ms,
        "output_len": len(out),
        "text": out,
    }


def main() -> None:
    text = TEXT_PATH.read_text(encoding="utf-8")
    prompt = build_prompt(text)
    results = {label: run_one(label, url, prompt) for label, url in MODELS.items()}
    out_path = Path(r"C:\llm\KoboldCPP agentic sandbox\tools\measure_top10_category_words.last.json")
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        key: {
            "latency_ms": value["latency_ms"],
            "output_len": value["output_len"],
            "preview": value["text"][:500],
        }
        for key, value in results.items()
    }, ensure_ascii=False, indent=2))
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()
