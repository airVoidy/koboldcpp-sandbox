"""NL-to-DSL: incremental behavior tree generation from natural language.

Pipeline:
1. plan_items() — NL task → list of item dicts (id, style, hair_color, etc.)
2. generate_element_do() — NL element description → DSL "do" array
3. build_tree_from_plan() — assemble full BehaviorTree from plan + generated elements
4. edit_element_via_chat() — modify element DSL via chat with model
"""

from __future__ import annotations

import json
import re
from typing import Any

from .behavior_orchestrator import LLMBackend


# ── JSON parsing helpers ─────────────────────────────────────────

def _strip_think(text: str) -> str:
    text = re.sub(r"<think>[\s\S]*?</think>\s*", "", text).strip()
    if "<think>" in text:
        text = re.sub(r"<think>[\s\S]*", "", text).strip()
    return text


def _loose_json_array(text: str) -> list[dict] | None:
    text = re.sub(r",\s*([}\]])", r"\1", text.strip())
    text = re.sub(r"//[^\n]*", "", text)
    # Fix common LLM JSON errors
    text = re.sub(r'\},\s*\{\s*\{', '},{', text)  # },{{ → },{ (extra opening brace)
    text = re.sub(r'\}\s*\{', '},{', text)  # missing comma between objects
    text = re.sub(r'"\s*\{', '",{', text)   # missing comma after string before object
    text = re.sub(r'\}\s*"', '},"', text)   # missing comma after object before string
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for i in range(len(text) - 1, 0, -1):
        if text[i] == "]":
            try:
                return json.loads(text[:i + 1])
            except json.JSONDecodeError:
                continue
    return None


def _loose_json_object(text: str) -> dict | None:
    text = re.sub(r",\s*([}\]])", r"\1", text.strip())
    text = re.sub(r"//[^\n]*", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for i in range(len(text) - 1, 0, -1):
        if text[i] == "}":
            try:
                return json.loads(text[:i + 1])
            except json.JSONDecodeError:
                continue
    return None


def _extract_json_array(text: str) -> list[dict] | None:
    text = _strip_think(text)
    match = re.search(r"\[[\s\S]*", text)
    if match:
        return _loose_json_array(match.group(0))
    return None


def _extract_json_object(text: str) -> dict | None:
    text = _strip_think(text)
    match = re.search(r"\{[\s\S]*", text)
    if match:
        return _loose_json_object(match.group(0))
    return None


# ── System prompts ───────────────────────────────────────────────

PLAN_SYSTEM = (
    "Ты — планировщик задач. Разбей задачу на пункты.\n"
    "Верни ТОЛЬКО валидный JSON массив объектов.\n"
    "Пример с двумя объектами:\n"
    '[{"id":"item-01","prompt":"описание в готическом стиле","style":"gothic","key_detail":"чёрные волосы"},\n'
    '{"id":"item-02","prompt":"описание в стиле киберпанк","style":"cyberpunk","key_detail":"неоновые волосы"}]\n'
    "ВАЖНО: между объектами ставь ТОЛЬКО запятую, без лишних скобок: }, {\"id\"...\n"
    "ОБЯЗАТЕЛЬНЫЕ поля: id, prompt (инструкция агенту), style (уникальный стиль).\n"
    "ОПЦИОНАЛЬНО: key_detail (одна ключевая деталь для проверки).\n"
    "НЕ добавляй лишние поля — это определит агент.\n"
    "Будь краток: prompt 1-2 предложения.\n"
    "Без прозы, без markdown. Только JSON массив.\n"
    "Отвечай на том же языке, что и задача."
)

ELEMENT_SYSTEM = (
    'Сгенерируй DSL-команды "do" для элемента behavior tree.\n\n'
    "Namespace: $x = локальная переменная, @x = node.data.x, @@x = global_meta.x\n\n"
    "Доступные команды:\n"
    '  {"render": {"to": "$prompt", "template": "Текст {$@style}. Деталь: {$@key_detail}."}}\n'
    '  {"call": {"fn": "call_agent", "args": {"agent": "@@creative_agent", "prompt": "$prompt"}, "to": "$text"}}\n'
    '  {"save": {"@draft_text": "$text", "@llm_generated": true}}\n'
    '  {"set": {"@repair_count": {"inc": "@repair_count"}}}\n'
    '  {"outcome": "pass"}\n'
    '  {"claims": "$failures"}\n'
    '  {"if": {"test": {"empty": "$failures"}, "then": [...], "else": [...]}}\n'
    '  {"copy": {"from": "@draft_text", "to": "@final_text"}}\n'
    '  {"return": "@final_text"}\n\n'
    "Пример repair элемента:\n"
    '[{"set": {"@repair_count": {"inc": "@repair_count"}}},\n'
    '{"render": {"to": "$prompt", "template": "Исправь: {$@local_failures}\\nТекст: {$@draft_text}"}},\n'
    '{"call": {"fn": "call_agent", "args": {"prompt": "$prompt"}, "to": "$fixed"}},\n'
    '{"save": {"@draft_text": "$fixed"}},\n'
    '{"outcome": "pass"}]\n\n'
    "Верни ТОЛЬКО JSON массив. Без прозы, без markdown."
)

EDIT_ELEMENT_SYSTEM = (
    "Ты редактируешь DSL-элемент behavior tree.\n"
    "Тебе дан текущий JSON элемента и инструкция по изменению.\n"
    "Верни ТОЛЬКО обновлённый JSON объект элемента целиком.\n"
    "Namespace: $x = локальная переменная, @x = node.data.x, @@x = global_meta.x\n"
    "Без прозы, без markdown. Только JSON."
)

EDIT_NODE_SYSTEM = (
    "Ты редактируешь ноду behavior tree.\n"
    "Тебе дан текущий JSON ноды (data, elements, claims) и инструкция.\n"
    "Верни ТОЛЬКО обновлённый JSON объект ноды целиком.\n"
    "Без прозы, без markdown. Только JSON."
)


# ── Core functions ───────────────────────────────────────────────

def plan_items(
    llm: LLMBackend,
    task: str,
    agent_name: str = "small_context_worker",
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> list[dict[str, Any]]:
    """NL task → list of item dicts."""
    text = llm.call(
        agent_name, task,
        system_prompt=PLAN_SYSTEM,
        temperature=temperature,
        max_tokens=max_tokens,
        max_continue=5,
    )
    items = _extract_json_array(text)
    if items is None:
        raise ValueError(f"Could not parse plan from LLM output: {text[:300]}")
    return items


def generate_element_do(
    llm: LLMBackend,
    element_description: str,
    agent_name: str = "small_context_worker",
    *,
    context: dict[str, Any] | None = None,
    temperature: float = 0.15,
    max_tokens: int = 1024,
) -> list[dict[str, Any]]:
    """NL element description → DSL "do" array."""
    prompt = f"Сгенерируй массив do для элемента: {element_description}"
    if context:
        prompt += f"\nКонтекст: {json.dumps(context, ensure_ascii=False)}"

    text = llm.call(
        agent_name, prompt,
        system_prompt=ELEMENT_SYSTEM,
        temperature=temperature,
        max_tokens=max_tokens,
        max_continue=3,
    )
    do = _extract_json_array(text)
    if do is None:
        raise ValueError(f"Could not parse element DO from LLM output: {text[:300]}")
    return do


def edit_element_via_chat(
    llm: LLMBackend,
    current_element: dict[str, Any],
    instruction: str,
    agent_name: str = "small_context_worker",
    *,
    temperature: float = 0.15,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """Modify element DSL via chat instruction."""
    prompt = (
        f"Текущий элемент:\n```json\n{json.dumps(current_element, ensure_ascii=False, indent=2)}\n```\n\n"
        f"Инструкция: {instruction}"
    )
    text = llm.call(
        agent_name, prompt,
        system_prompt=EDIT_ELEMENT_SYSTEM,
        temperature=temperature,
        max_tokens=max_tokens,
        max_continue=1,
    )
    result = _extract_json_object(text)
    if result is None:
        raise ValueError(f"Could not parse edited element: {text[:300]}")
    return result


def edit_node_via_chat(
    llm: LLMBackend,
    current_node: dict[str, Any],
    instruction: str,
    agent_name: str = "small_context_worker",
    *,
    temperature: float = 0.15,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    """Modify node via chat instruction. Returns updated node dict."""
    # Compact node representation — skip large text fields
    compact = {
        "node_id": current_node.get("node_id"),
        "kind": current_node.get("kind"),
        "data": current_node.get("data", {}),
        "elements": [
            {
                "element_id": e.get("element_id"),
                "handler": e.get("handler"),
                "transitions": e.get("transitions", {}),
                "meta": e.get("meta", {}),
            }
            for e in current_node.get("elements", [])
        ],
        "claims": current_node.get("claims", []),
    }
    prompt = (
        f"Текущая нода:\n```json\n{json.dumps(compact, ensure_ascii=False, indent=2)}\n```\n\n"
        f"Инструкция: {instruction}"
    )
    text = llm.call(
        agent_name, prompt,
        system_prompt=EDIT_NODE_SYSTEM,
        temperature=temperature,
        max_tokens=max_tokens,
        max_continue=2,
    )
    result = _extract_json_object(text)
    if result is None:
        raise ValueError(f"Could not parse edited node: {text[:300]}")
    return result


PIPELINE_SYSTEM = (
    "Сгенерируй pipeline (список элементов) для behavior tree.\n"
    "Каждый элемент — это шаг обработки ПОСЛЕ генерации текста (draft уже есть).\n\n"
    "Формат: JSON массив объектов, каждый содержит:\n"
    '  {"element_id": "check", "transitions": {"pass": "finalize", "fail": "repair"}, "do": [...]}\n\n'
    "Namespace: $x=локальная, @x=node.data, @@x=global_meta\n"
    "Команды: claims, save, set, if, render, call, copy, outcome, return\n\n"
    "Пример pipeline из 3 элементов:\n"
    '[{"element_id":"check","transitions":{"pass":"finalize","fail":"repair"},"do":[\n'
    '  {"claims":"$failures"},{"save":{"@failures":"$failures"}},\n'
    '  {"if":{"test":{"empty":"$failures"},"then":[{"outcome":"pass"}],"else":[{"outcome":"fail"}]}}]},\n'
    '{"element_id":"repair","transitions":{},"do":[\n'
    '  {"set":{"@repair_count":{"inc":"@repair_count"}}},\n'
    '  {"render":{"to":"$prompt","template":"Исправь: {$@failures}\\nТекст: {$@draft_text}"}},\n'
    '  {"call":{"fn":"call_agent","args":{"prompt":"$prompt"},"to":"$fixed"}},\n'
    '  {"save":{"@draft_text":"$fixed"}},{"outcome":"pass"}]},\n'
    '{"element_id":"finalize","transitions":{},"do":[\n'
    '  {"copy":{"from":"@draft_text","to":"@final_text"}},\n'
    '  {"set":{"@audit_status":"pass"}},{"return":"@final_text"},{"outcome":"done"}]}]\n\n'
    "Верни ТОЛЬКО JSON массив. Без прозы."
)


def _generate_pipeline(
    llm: LLMBackend,
    task: str,
    agent_name: str,
    global_meta: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Generate shared pipeline elements (post-draft) via one LLM call."""
    prompt = f"Задача: {task}\nСгенерируй pipeline элементов для обработки после draft."
    if global_meta:
        prompt += f"\nНастройки: {json.dumps(global_meta, ensure_ascii=False)}"

    text = llm.call(
        agent_name, prompt,
        system_prompt=PIPELINE_SYSTEM,
        temperature=0.15,
        max_tokens=2048,
        max_continue=3,
    )
    elements_raw = _extract_json_array(text)
    if elements_raw is None:
        # Fallback: minimal pipeline
        return [
            {"element_id": "check", "handler": "__dsl__",
             "transitions": {"pass": "finalize", "fail": "repair"},
             "meta": {"do": [
                 {"claims": "$failures"}, {"save": {"@failures": "$failures"}},
                 {"if": {"test": {"empty": "$failures"},
                         "then": [{"outcome": "pass"}], "else": [{"outcome": "fail"}]}}]}},
            {"element_id": "repair", "handler": "__dsl__", "transitions": {},
             "meta": {"do": [
                 {"set": {"@repair_count": {"inc": "@repair_count"}}},
                 {"render": {"to": "$prompt", "template": "Исправь: {$@failures}\nТекст: {$@draft_text}"}},
                 {"call": {"fn": "call_agent", "args": {"prompt": "$prompt"}, "to": "$fixed"}},
                 {"save": {"@draft_text": "$fixed"}}, {"outcome": "pass"}]}},
            {"element_id": "finalize", "handler": "__dsl__", "transitions": {},
             "meta": {"do": [
                 {"copy": {"from": "@draft_text", "to": "@final_text"}},
                 {"set": {"@audit_status": "pass"}}, {"return": "@final_text"}, {"outcome": "done"}]}},
        ]

    # Normalize: ensure handler=__dsl__ and do is in meta
    result = []
    for el in elements_raw:
        do = el.get("do", [])
        result.append({
            "element_id": el.get("element_id", f"step-{len(result)+1}"),
            "handler": "__dsl__",
            "transitions": el.get("transitions", {}),
            "meta": {"do": do},
        })
    return result


def build_tree_from_plan(
    llm: LLMBackend,
    task: str,
    items: list[dict[str, Any]],
    agent_name: str = "small_context_worker",
    *,
    global_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a full BehaviorTree JSON from plan items + generated elements.

    Returns a tree dict ready for POST /api/behavior/tree.
    """
    if global_meta is None:
        global_meta = {}

    tree_id = f"auto-{task[:30].replace(' ', '-').lower()}"

    # Generate shared pipeline (element flow) via one LLM call
    # Worker decides what elements are needed and generates DSL for each
    shared_pipeline = _generate_pipeline(llm, task, agent_name, global_meta)

    nodes: dict[str, Any] = {}

    for item in items:
        item_id = item.get("id", f"item-{len(nodes)+1:02d}")

        # Per-item draft element — unique prompt per item
        try:
            draft_do = generate_element_do(
                llm,
                f"генерация текста по заданию. Используй call_agent. Сохрани в @draft_text.\nItem: {json.dumps(item, ensure_ascii=False)}",
                agent_name,
                context={"item": item, "global_meta": global_meta},
                max_tokens=1024,
            )
        except ValueError:
            draft_do = [
                {"render": {"to": "$prompt", "template": "{$@prompt}"}},
                {"call": {"fn": "call_agent", "args": {"prompt": "$prompt"}, "to": "$text"}},
                {"save": {"@draft_text": "$text"}},
                {"outcome": "pass"},
            ]

        elements = [
            {
                "element_id": "draft",
                "handler": "__dsl__",
                "transitions": {},
                "meta": {"do": draft_do},
            },
            *shared_pipeline,
        ]

        # Claims for this item
        claims = [
            {
                "claim_id": f"{item_id}-sentence-range",
                "scope": "node",
                "evaluator": "__dsl__",
                "status": "pending",
                "meta": {
                    "dsl": {
                        "test": {"in_range": [
                            {"call": {"fn": "len", "args": {"value": {"call": {"fn": "split_sentences", "args": {"text": {"coalesce": ["@final_text", "@draft_text"]}}}}}}},
                            global_meta.get("sentence_range", [5, 8]),
                        ]},
                        "pass": "sentence count in range",
                        "fail": "sentence count out of range",
                    }
                },
            },
            {
                "claim_id": f"{item_id}-key-detail",
                "scope": "node",
                "evaluator": "__dsl__",
                "status": "pending",
                "meta": {
                    "dsl": {
                        "test": {"not_empty": {"coalesce": ["@final_text", "@draft_text"]}},
                        "pass": "text present",
                        "fail": "text missing",
                    }
                },
            },
        ]

        nodes[item_id] = {
            "node_id": item_id,
            "kind": "description_item",
            "entry_element": "draft",
            "data": {**item, "repair_count": 0},
            "elements": elements,
            "claims": claims,
            "child_ids": [],
            "meta": {},
        }

    # Root node
    nodes["root"] = {
        "node_id": "root",
        "kind": "auto_root",
        "entry_element": "run_children",
        "data": {"task": task},
        "elements": [
            {
                "element_id": "run_children",
                "handler": "__dsl__",
                "transitions": {},
                "meta": {
                    "do": [
                        {"for_each": {
                            "in": "@child_ids",
                            "as": "$child_id",
                            "do": [{"run_node": {"node_id": "$child_id"}}],
                        }},
                        {"outcome": "done"},
                    ]
                },
            },
        ],
        "claims": [],
        "child_ids": [item.get("id", f"item-{i+1:02d}") for i, item in enumerate(items)],
        "meta": {},
    }

    return {
        "format_version": "behavior-tree/v1",
        "tree_id": tree_id,
        "root_node_id": "root",
        "global_meta": global_meta,
        "global_claims": [],
        "nodes": nodes,
    }


def plan_and_build(
    llm: LLMBackend,
    task: str,
    agent_name: str = "small_context_worker",
    *,
    global_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full pipeline: NL task → plan → build tree."""
    items = plan_items(llm, task, agent_name)
    return build_tree_from_plan(llm, task, items, agent_name, global_meta=global_meta)
