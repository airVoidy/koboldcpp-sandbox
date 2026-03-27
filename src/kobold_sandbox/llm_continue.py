"""Centralised LLM call with automatic continue-on-length."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class LLMResult:
    raw: str = ""
    answer: str = ""
    think: str = ""
    continues: int = 0
    finish_reason: str = "stop"
    prompt_mode: str = "chat"
    raw_responses: list[dict] = field(default_factory=list)
    latency_ms: int = 0


_THINK_RE = re.compile(r"<think\b[^>]*>([\s\S]*?)</think>", re.IGNORECASE)
_THINK_STRIP_RE = re.compile(r"<think\b[^>]*>[\s\S]*?</think>\s*", re.DOTALL | re.IGNORECASE)


def _is_length_finish(reason: str | None) -> bool:
    return str(reason or "").strip().lower() in {"length", "max_tokens"}


def _choose_prompt_mode(messages: list[dict], prompt_mode: str) -> str:
    mode = str(prompt_mode or "auto").strip().lower()
    if mode in {"chat", "instruct"}:
        return mode
    if len(messages) == 1 and str(messages[0].get("role", "")).lower() == "user":
        return "instruct"
    return "chat"


def _messages_to_instruct_prompt(messages: list[dict]) -> str:
    if not messages:
        return ""
    if len(messages) == 1 and str(messages[0].get("role", "")).lower() == "user":
        return str(messages[0].get("content") or "")
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "user").strip().lower()
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            parts.append(f"System:\n{content}")
        elif role == "assistant":
            parts.append(f"Assistant:\n{content}")
        else:
            parts.append(f"User:\n{content}")
    return "\n\n".join(parts).strip()


def _native_generate(
    http: httpx.Client,
    base_url: str,
    prompt: str,
    *,
    temperature: float,
    max_tokens: int,
) -> dict:
    resp = http.post(
        f"{base_url.rstrip('/')}/api/v1/generate",
        json={
            "prompt": prompt,
            "temperature": temperature,
            "max_length": max_tokens,
        },
    )
    resp.raise_for_status()
    return resp.json()


def strip_think(text: str) -> tuple[str, str]:
    m = _THINK_RE.search(text)
    if m:
        think = m.group(1).strip()
        answer = _THINK_STRIP_RE.sub("", text).strip()
        return answer, think

    if "<think>" in text:
        idx = text.find("<think>")
        end_idx = text.rfind("</think>")
        if end_idx > idx:
            think = text[idx + 7:end_idx].strip()
            answer = text[end_idx + 8:].strip()
            return answer, think
        answer = text[:idx].strip()
        return answer, text[idx + 7:].strip()

    return text, ""


def llm_call_with_continue(
    base_url: str,
    messages: list[dict],
    *,
    temperature: float = 0.6,
    max_tokens: int = 2048,
    no_think: bool = True,
    max_continue: int = 20,
    continue_on_length: bool = True,
    stop: list[str] | None = None,
    grammar: str | None = None,
    extra_payload: dict[str, Any] | None = None,
    prompt_mode: str = "auto",
    http: httpx.Client | None = None,
    timeout: float = 180.0,
) -> LLMResult:
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    own_http = http is None
    if own_http:
        http = httpx.Client(timeout=timeout, trust_env=False)

    selected_mode = _choose_prompt_mode(messages, prompt_mode)
    msgs = list(messages)
    if selected_mode == "chat" and no_think and (not msgs or msgs[-1].get("role") != "assistant"):
        msgs.append({"role": "assistant", "content": "<think>\n\n</think>\n\n"})

    has_prefill = bool(selected_mode == "chat" and msgs and msgs[-1].get("role") == "assistant")
    is_continue_turn = bool(selected_mode == "chat" and (no_think or has_prefill))

    result = ""
    raw_responses: list[dict] = []
    last_finish = "stop"
    started_at = time.perf_counter()

    try:
        for i in range(max_continue + 1):
            payload: dict[str, Any] | None = None
            try:
                if selected_mode == "instruct":
                    prompt = _messages_to_instruct_prompt(msgs)
                    if i > 0:
                        prompt = f"{prompt}{result}"
                    data = _native_generate(
                        http,
                        base_url,
                        prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                else:
                    if i == 0:
                        cur_messages = msgs
                    elif has_prefill:
                        prefix = "<think>\n\n</think>\n\n" if no_think else ""
                        cur_messages = [*msgs[:-1], {"role": "assistant", "content": prefix + result}]
                    else:
                        cur_messages = [*msgs, {"role": "assistant", "content": result}]

                    payload = {
                        "messages": cur_messages,
                        "continue_assistant_turn": i > 0 or is_continue_turn,
                        "cache_prompt": False,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "stream": False,
                    }
                    if stop:
                        payload["stop"] = stop
                    if grammar:
                        payload["grammar"] = grammar
                        payload["grammar_string"] = grammar
                    if extra_payload:
                        payload.update(extra_payload)
                    resp = http.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError):
                if own_http:
                    http.close()
                    http = httpx.Client(timeout=timeout, trust_env=False)
                try:
                    if selected_mode == "instruct":
                        prompt = _messages_to_instruct_prompt(msgs)
                        if i > 0:
                            prompt = f"{prompt}{result}"
                        data = _native_generate(
                            http,
                            base_url,
                            prompt,
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )
                    else:
                        resp = http.post(url, json=payload)
                        resp.raise_for_status()
                        data = resp.json()
                except Exception:
                    break
            except httpx.HTTPStatusError:
                break

            raw_responses.append(data)
            if selected_mode == "instruct":
                item = (data.get("results") or [{}])[0]
                chunk = str(item.get("text") or "")
                last_finish = str(item.get("finish_reason") or "stop")
            else:
                choice = (data.get("choices") or [{}])[0]
                chunk = choice.get("message", {}).get("content", "")
                last_finish = choice.get("finish_reason", "stop")
            result += chunk

            if not continue_on_length:
                break
            if not _is_length_finish(last_finish):
                break
    finally:
        if own_http:
            http.close()

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    answer, think = strip_think(result)

    return LLMResult(
        raw=result,
        answer=answer,
        think=think,
        continues=max(0, len(raw_responses) - 1),
        finish_reason=last_finish,
        prompt_mode=selected_mode,
        raw_responses=raw_responses,
        latency_ms=latency_ms,
    )
