"""Reactive Task Parser — dialog-based, no hardcoded prompts.

All parsing happens through visible dialog in the thread.
Server proxies messages between user and worker, extracts structure from responses.
No system_prompt, no hidden instructions — ChatML instruct style.

Flow:
  1. User sends task → root node created, message in thread
  2. Worker receives task, responds in thread (free form)
  3. Server tries to extract structure (JSON) from worker's response
  4. If structure found → build task + first entity
  5. If not → continue dialog, user/worker clarify
"""
from __future__ import annotations

import json
import re
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .behavior_orchestrator import LLMBackend


# ---------------------------------------------------------------------------
# JSON extraction from free-form text
# ---------------------------------------------------------------------------

def extract_json_object(text: str) -> dict | None:
    """Extract first JSON object from text, if any."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except (json.JSONDecodeError, ValueError):
                    return None
    return None


def extract_structure_from_response(response: str) -> dict | None:
    """Try to extract task structure from worker's response.

    Looks for JSON with count/unique_fields, or parses free-form text.
    Returns parsed dict or None if can't extract.
    """
    obj = extract_json_object(response)
    if obj and "count" in obj:
        return obj
    return None


# ---------------------------------------------------------------------------
# Dialog state
# ---------------------------------------------------------------------------

def new_dialog_state(message: str) -> dict[str, Any]:
    """Create fresh dialog state from user's first message."""
    return {
        "raw_message": message,
        "messages": [
            {"role": "user", "content": message},
        ],
        "parsed": None,       # extracted structure, once found
        "phase": "dialog",    # "dialog" | "ready"
        "entities_created": 0,
    }


def add_worker_response(state: dict, response: str, think: str = "") -> dict[str, Any]:
    """Add worker's response to dialog, try to extract structure."""
    state["messages"].append({
        "role": "assistant",
        "content": response,
        "think": think,
    })

    # Try to extract structure from response
    parsed = extract_structure_from_response(response)
    if parsed:
        state["parsed"] = parsed
        state["phase"] = "ready"

    return state


def add_user_message(state: dict, message: str) -> dict[str, Any]:
    """Add user's follow-up message to dialog."""
    state["messages"].append({
        "role": "user",
        "content": message,
    })
    return state


# ---------------------------------------------------------------------------
# Call worker (just proxy, no system prompt)
# ---------------------------------------------------------------------------

def call_worker(
    state: dict[str, Any],
    llm: LLMBackend,
    agent_name: str = "small_context_worker",
    settings: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Send full dialog history to worker via ChatML instruct format.

    Returns (answer, think) — both visible in thread.
    No system_prompt — just the conversation messages.
    """
    import httpx

    settings = settings or {}
    client = llm.get(agent_name)
    if client is None:
        raise ValueError(f"No worker registered as '{agent_name}'")

    # Build ChatML messages — full conversation history
    messages = [{"role": m["role"], "content": m["content"]} for m in state["messages"]]

    no_think = settings.get("no_think", True)
    if no_think:
        messages.append({"role": "assistant", "content": "<think>\n\n</think>\n\n"})

    temperature = settings.get("temperature", 0.3)
    max_tokens = settings.get("max_tokens", 2048)
    max_continue = settings.get("max_continue", 20)

    base_url = client.base_url.rstrip("/")
    http = httpx.Client(timeout=client.timeout, trust_env=False)

    try:
        # First request
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if no_think:
            payload["continue_assistant_turn"] = True

        resp = http.post(f"{base_url}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        raw_result = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        finish = data.get("choices", [{}])[0].get("finish_reason", "stop")

        if no_think:
            full_assistant = "<think>\n\n</think>\n\n" + raw_result
        else:
            full_assistant = raw_result

        # Continue loop until EoT
        for i in range(max_continue):
            if str(finish).strip().lower() not in {"length", "max_tokens"}:
                break
            cont_messages = list(messages[:-1]) if no_think else list(messages)
            cont_messages.append({"role": "assistant", "content": full_assistant})
            cont_payload = {
                "messages": cont_messages,
                "continue_assistant_turn": True,
                "cache_prompt": False,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }
            resp = http.post(f"{base_url}/v1/chat/completions", json=cont_payload)
            resp.raise_for_status()
            cont_data = resp.json()
            chunk = cont_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            raw_result += chunk
            full_assistant += chunk
            finish = cont_data.get("choices", [{}])[0].get("finish_reason", "stop")
    finally:
        http.close()

    # Separate think and answer
    think = ""
    answer = raw_result
    think_match = re.search(r"<think\b[^>]*>([\s\S]*?)</think>", raw_result, re.IGNORECASE)
    if think_match:
        think = think_match.group(1).strip()
        answer = re.sub(r"<think\b[^>]*>[\s\S]*?</think>\s*", "", raw_result, flags=re.DOTALL | re.IGNORECASE).strip()
    elif "<think>" in raw_result:
        idx = raw_result.find("<think>")
        end_idx = raw_result.rfind("</think>")
        if end_idx > idx:
            think = raw_result[idx + 7:end_idx].strip()
            answer = raw_result[end_idx + 8:].strip()

    return answer, think


# ---------------------------------------------------------------------------
# Build task from parsed structure
# ---------------------------------------------------------------------------

def build_task_from_parsed(state: dict[str, Any]) -> dict[str, Any] | None:
    """Build ReactiveTask dict from parsed dialog structure."""
    parsed = state.get("parsed")
    if not parsed:
        return None

    count = parsed.get("count")
    if not count or count < 1:
        return None

    base_task = parsed.get("base_task", state.get("raw_message", ""))
    unique_fields = parsed.get("unique_fields", [])
    generation_prompt = parsed.get("generation_prompt", base_task)

    # First entity only — rest iterative
    first_entity = {
        "entity-01": {
            "properties": {
                "text": "",
                "validated": False,
                **{f["field"]: "" for f in unique_fields},
            }
        }
    }
    state["entities_created"] = 1

    # Constraint injection for entities after first
    constraint_parts = []
    for f in unique_fields:
        label = f.get("label", f["field"])
        constraint_parts.append(f"- {label}: {{$@@used_{f['field']}s}}")
    constraint_suffix = ""
    if constraint_parts:
        constraint_suffix = (
            "\n\nЗАПРЕЩЕНО повторять (уже использованные):\n"
            + "\n".join(constraint_parts)
            + "\n\nСоздай ДРУГОЙ уникальный вариант."
        )

    pipeline = [
        {
            "layer_id": "generate",
            "ops": [
                {"render": {
                    "template": generation_prompt + constraint_suffix
                        + "\n\nОтвечай на русском. Начинай сразу с текста, без заголовков.",
                    "to": "$_prompt",
                }},
                {"call": {
                    "fn": "call_agent",
                    "args": {"prompt": "$_prompt"},
                    "to": "@text",
                }},
            ],
            "tags": ["generate"],
        },
    ]

    extractors = []
    for f in unique_fields:
        question = f.get("extraction_question", f"Какой {f.get('label', f['field'])} в тексте? Кратко.")
        extractors.append({
            "field": f["field"],
            "question": question,
            "constraint_list": f"used_{f['field']}s",
            "parse_mode": "word",
            "max_tokens": 30,
            "no_think": True,
        })

    constraints = []
    for f in unique_fields:
        constraints.append({
            "constraint_id": f"unique_{f['field']}",
            "watches": [f"*.{f['field']}.changed"],
            "check": {"not_empty": f"@@used_{f['field']}s"},
        })

    global_meta: dict[str, Any] = {
        "language": "ru",
        "base_task": base_task,
        "generation_prompt": generation_prompt,
        "raw_message": state.get("raw_message", ""),
        "entity_count": count,
    }
    for f in unique_fields:
        global_meta[f"used_{f['field']}s"] = []

    # Verify config from dialog context
    check_items = [f"- {f.get('label', f['field'])}" for f in unique_fields]
    verify_config = {
        "max_rounds": 3,
        "pass_keyword": "PASS",
        "verifier_prompt_template": (
            "Evaluate:\n" + "\n".join(check_items)
            + "\n\nPASS if good, FAIL + fix otherwise.\n\n{text}"
        ),
    }

    return {
        "task_id": _slugify(base_task) or "reactive-task",
        "global_meta": global_meta,
        "entities": first_entity,
        "pipeline": pipeline,
        "extractors": extractors,
        "constraints": constraints,
        "verify_config": verify_config,
    }


def create_next_entity(state: dict[str, Any]) -> dict[str, Any] | None:
    """Create next entity in iterative sequence."""
    parsed = state.get("parsed", {})
    count = parsed.get("count", state.get("entity_count", 0))
    created = state.get("entities_created", 0)

    if created >= count:
        return None

    idx = created + 1
    eid = f"entity-{idx:02d}"
    unique_fields = parsed.get("unique_fields", [])

    entity = {
        "entity_id": eid,
        "index": idx,
        "properties": {
            "text": "",
            "validated": False,
            **{f["field"]: "" for f in unique_fields},
        },
    }

    state["entities_created"] = idx
    return entity


def _slugify(text: str) -> str:
    tr = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    result = []
    for ch in text.lower():
        if ch in tr:
            result.append(tr[ch])
        elif ch.isascii() and (ch.isalnum() or ch in "-_"):
            result.append(ch)
        elif ch in " \t":
            result.append("-")
    slug = re.sub(r"-+", "-", "".join(result)).strip("-")
    return slug[:60] if slug else ""
