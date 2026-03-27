from __future__ import annotations

import json
import statistics
import time
from collections import Counter
from pathlib import Path

import httpx


TEXT_PATH = Path(r"C:\llm\KoboldCPP agentic sandbox\tools\probe_wordlist_case.txt")
MODELS = {
    "5001_9b": "http://localhost:5001/api/v1/generate",
    "5050_27b": "http://192.168.1.15:5050/api/v1/generate",
}
WINDOW = 50
STRIDE = 10


def make_windows(text: str, size: int, stride: int) -> list[dict]:
    out = []
    for start in range(0, max(1, len(text) - size + 1), stride):
        chunk = text[start:start + size]
        if len(chunk) < size:
            break
        out.append({"start": start, "end": start + len(chunk), "text": chunk})
    return out


def build_prompt(chunk: str) -> str:
    return f"""поставь цифру от 1 до 9, если текст относится к категории
1 поза
2 цвет глаз
3 цвету волос
4 позе
5 отличительным особенностям демоницы
6 аниме
8 другое
9 ничего из вышеперечисленного

ответь только одной цифрой

Примеры:
глаза янтарные и с вертикальным зрачком=2
белые длинные волосы=3
сидит на краю балкона=1
она лежит на снегу, обхватив колени=4
крылья, рога и хвост=5
стиль аниме=6
связующий текст и служебные слова=8
обрывок без понятного признака=9

Текст:
{chunk}

Ответ:
"""


def ask_window(url: str, chunk: str) -> tuple[str, int]:
    prompt = build_prompt(chunk)
    started = time.perf_counter()
    with httpx.Client(trust_env=False, timeout=60.0) as client:
        resp = client.post(
            url,
            json={
                "prompt": prompt,
                "temperature": 0.0,
                "max_length": 16,
                "grammar": 'root ::= "1" | "2" | "3" | "4" | "5" | "6" | "8" | "9"',
            },
        )
        resp.raise_for_status()
        data = resp.json()
    latency_ms = int((time.perf_counter() - started) * 1000)
    answer = str(data.get("results", [{}])[0].get("text") or "").strip()
    return answer, latency_ms


def run_model(label: str, url: str, windows: list[dict]) -> dict:
    rows = []
    latencies = []
    labels = Counter()
    for item in windows:
        answer, latency_ms = ask_window(url, item["text"])
        rows.append({
            "start": item["start"],
            "end": item["end"],
            "label": answer,
            "latency_ms": latency_ms,
            "text": item["text"],
        })
        latencies.append(latency_ms)
        labels[answer] += 1
    return {
        "windows": len(rows),
        "avg_ms": round(statistics.mean(latencies), 1),
        "median_ms": round(statistics.median(latencies), 1),
        "min_ms": min(latencies),
        "max_ms": max(latencies),
        "labels": dict(labels),
        "sample": rows[:20],
    }


def main() -> None:
    text = TEXT_PATH.read_text(encoding="utf-8")
    windows = make_windows(text, WINDOW, STRIDE)
    results = {label: run_model(label, url, windows) for label, url in MODELS.items()}
    out_path = Path(r"C:\llm\KoboldCPP agentic sandbox\tools\measure_window_categories.last.json")
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        k: {
            "windows": v["windows"],
            "avg_ms": v["avg_ms"],
            "median_ms": v["median_ms"],
            "labels": v["labels"],
        }
        for k, v in results.items()
    }, ensure_ascii=False, indent=2))
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()
