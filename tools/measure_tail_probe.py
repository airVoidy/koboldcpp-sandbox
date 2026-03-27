from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_TEXT = (
    "Нужен промпт для портрета персонажа: женщина-демон с уникальным цветом глаз, "
    "длинными серебряными волосами, уверенной позой, именем Лиара, без повторов деталей. "
    "Стиль иллюстративный, фон минималистичный, выражение лица спокойное."
)

DEFAULT_WORDS = [
    "цвет глаз",
    "Лиара",
    "минималистичный фон",
    "уникальность",
    "женщина-демон",
    "спокойное выражение",
    "иллюстративный стиль",
    "повторы",
]

PROBE_EXAMPLES = """Примеры:
Слово: "цвет глаз" -> 1
Слово: "имя" -> 1
Слово: "повторяться" -> 0
Слово: "стиль" -> 1
Слово: "сделай красиво" -> 0
Слово: "фон" -> 1
Слово: "уникальность" -> 0
Слово: "эмоция" -> 1"""


@dataclass
class ProbeResult:
    word: str
    latency_ms: int
    answer: str
    started_at_ms: int
    ended_at_ms: int


def build_stream_messages(text: str) -> list[dict[str, str]]:
    prompt = (
        "Извлеки кандидаты на ENTITIES из пользовательского запроса. "
        "Возвращай короткий список, по одному элементу в строке, без объяснений.\n\n"
        f"Текст:\n{text}"
    )
    return [{"role": "user", "content": prompt}]


def build_probe_prompt(text: str, word: str) -> str:
    return (
        "Ты бинарный классификатор. Ответь только 1 или 0.\n"
        "1 = это entity/именованная или значимая колонка-сущность для дальнейшего извлечения.\n"
        "0 = это не entity, а общее требование, стиль проверки, действие, оценка или абстракция.\n\n"
        f"{PROBE_EXAMPLES}\n\n"
        f"Текст:\n{text}\n\n"
        f'Слово: "{word}"\n'
        "Класс: "
    )


async def stream_generator(
    client: httpx.AsyncClient,
    url: str,
    text: str,
    tick_queue: asyncio.Queue[dict[str, Any]],
) -> dict[str, Any]:
    started = time.perf_counter()
    first_token_ms: int | None = None
    chunks: list[str] = []
    chunk_count = 0

    payload = {
        "messages": build_stream_messages(text),
        "temperature": 0.2,
        "max_tokens": 256,
        "stream": True,
        "cache_prompt": False,
    }

    async with client.stream("POST", f"{url.rstrip('/')}/v1/chat/completions", json=payload, timeout=180.0) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = ((obj.get("choices") or [{}])[0].get("delta") or {}).get("content", "")
            if not delta:
                continue
            chunk_count += 1
            chunks.append(delta)
            now_ms = int((time.perf_counter() - started) * 1000)
            if first_token_ms is None:
                first_token_ms = now_ms
            await tick_queue.put(
                {
                    "t_ms": now_ms,
                    "chunk_index": chunk_count,
                    "delta": delta,
                    "total_chars": sum(len(x) for x in chunks),
                }
            )

    total_ms = int((time.perf_counter() - started) * 1000)
    await tick_queue.put({"done": True, "t_ms": total_ms})
    return {
        "first_token_ms": first_token_ms,
        "total_ms": total_ms,
        "chunk_count": chunk_count,
        "text": "".join(chunks),
    }


async def probe_word(client: httpx.AsyncClient, url: str, text: str, word: str, base_started: float) -> ProbeResult:
    started = time.perf_counter()
    resp = await client.post(
        f"{url.rstrip('/')}/api/v1/generate",
        json={
            "prompt": build_probe_prompt(text, word),
            "temperature": 0.0,
            "max_length": 32,
            "grammar": 'root ::= "0" | "1"',
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    answer = str(data.get("results", [{}])[0].get("text") or "").strip()
    ended = time.perf_counter()
    return ProbeResult(
        word=word,
        latency_ms=int((ended - started) * 1000),
        answer=answer,
        started_at_ms=int((started - base_started) * 1000),
        ended_at_ms=int((ended - base_started) * 1000),
    )


async def run_measurement(generator_url: str, analyzer_url: str, text: str, words: list[str], launch_gap_ms: int) -> dict[str, Any]:
    tick_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    base_started = time.perf_counter()

    async with httpx.AsyncClient(trust_env=False) as client:
        stream_task = asyncio.create_task(stream_generator(client, generator_url, text, tick_queue))

        probe_results: list[ProbeResult] = []
        for idx, word in enumerate(words):
            if idx:
                await asyncio.sleep(launch_gap_ms / 1000.0)
            probe_results.append(await probe_word(client, analyzer_url, text, word, base_started))

        stream_result = await stream_task

    ticks: list[dict[str, Any]] = []
    while not tick_queue.empty():
        ticks.append(await tick_queue.get())

    return {
        "generator_url": generator_url,
        "analyzer_url": analyzer_url,
        "text": text,
        "stream": stream_result,
        "ticks": ticks,
        "probes": [r.__dict__ for r in probe_results],
    }


def print_summary(data: dict[str, Any]) -> None:
    stream = data["stream"]
    probes = data["probes"]
    print("STREAM")
    print(f"  first_token_ms: {stream['first_token_ms']}")
    print(f"  total_ms: {stream['total_ms']}")
    print(f"  chunk_count: {stream['chunk_count']}")
    print()
    print("PROBES")
    for item in probes:
        print(
            f"  {item['word']!r}: answer={item['answer']!r} "
            f"latency={item['latency_ms']}ms window={item['started_at_ms']}..{item['ended_at_ms']}ms"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure streamed generation vs parallel 1/0 probe requests.")
    parser.add_argument("--generator", default="http://localhost:5001")
    parser.add_argument("--analyzer", default="http://192.168.1.15:5050")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--gap-ms", type=int, default=400)
    parser.add_argument("--json-out", default="")
    parser.add_argument("--words", nargs="*", default=DEFAULT_WORDS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(
        run_measurement(
            generator_url=args.generator,
            analyzer_url=args.analyzer,
            text=args.text,
            words=list(args.words),
            launch_gap_ms=args.gap_ms,
        )
    )
    print_summary(result)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print()
        print(f"saved: {args.json_out}")


if __name__ == "__main__":
    main()
