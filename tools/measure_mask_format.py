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
    return f"""Сделай маску той же длины, что и оригинальный текст.

Правила:
- выводи только строку-маску
- длина вывода должна быть ровно такой же, как длина оригинала
- для каждого НЕ-пробельного символа ставь одну цифру
- если в оригинале пробел, в выводе тоже должен быть пробел
- не копируй оригинальный текст
- не добавляй пояснений

Категории:
1 = поза
2 = цвет глаз
3 = цвет волос
4 = действие/жест
5 = отличительные особенности демоницы
6 = аниме
0 = другое

Оригинал:
<<<
{text}
>>>

Маска:
"""


def summarize_output(src: str, out: str) -> dict:
    same_len = len(src) == len(out)
    compared = min(len(src), len(out))
    space_matches = 0
    nonspace_digit_matches = 0
    bad_nonspace = 0
    for i in range(compared):
        s = src[i]
        o = out[i]
        if s == " ":
            if o == " ":
                space_matches += 1
        else:
            if o in "0123456":
                nonspace_digit_matches += 1
            else:
                bad_nonspace += 1
    return {
        "same_len": same_len,
        "input_len": len(src),
        "output_len": len(out),
        "space_matches": space_matches,
        "nonspace_digit_matches": nonspace_digit_matches,
        "bad_nonspace": bad_nonspace,
        "prefix": out[:160],
    }


def run_one(label: str, url: str, prompt: str, source_text: str) -> dict:
    started = time.perf_counter()
    with httpx.Client(trust_env=False, timeout=180.0) as client:
        resp = client.post(
            url,
            json={
                "prompt": prompt,
                "temperature": 0.0,
                "max_length": len(source_text) + 256,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    latency_ms = int((time.perf_counter() - started) * 1000)
    out = str(data.get("results", [{}])[0].get("text") or "")
    summary = summarize_output(source_text, out)
    summary["latency_ms"] = latency_ms
    summary["label"] = label
    return summary


def main() -> None:
    text = TEXT_PATH.read_text(encoding="utf-8")[:900]
    prompt = build_prompt(text)
    results = {label: run_one(label, url, prompt, text) for label, url in MODELS.items()}
    out_path = Path(r"C:\llm\KoboldCPP agentic sandbox\tools\measure_mask_format.last.json")
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()
