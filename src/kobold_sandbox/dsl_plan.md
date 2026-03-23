Context
Сейчас generic handlers (llm_generate, llm_repair, evaluate_claims, truncate_sentences, finalize_from_claims) в Python читают конфигурацию из element.meta. Нужно обобщить: любой handler описывается декларативно в JSON как последовательность ops, чтобы мелкие LLM могли добавлять новые handlers без изменения Python кода.
DSL Design
Element с DSL handler
json{
  "element_id": "draft",
  "handler": "__dsl__",
  "meta": {
    "ops": [
      {"op": "llm_call", "prompt_template": "...", "output_field": "draft_text"},
      {"op": "set", "field": "llm_generated", "value": true},
      {"op": "set_outcome", "outcome": "pass"}
    ]
  }
}
Named Templates & Variables
Templates — именованные шаблоны, определяются на уровне element.meta или tree.global_meta. Позволяют переиспользовать промпты:
json{
  "meta": {
    "templates": {
      "base_prompt": "Опиши внешность персонажа.\nСтиль: {$data.style}.\nЦвет волос: {$data.hair_color}.",
      "quality_check": "Проверь текст:\n- не менее {$var.min_sent} предложений\n- упомянут {$data.key_detail}",
      "repair_instruction": "Перепиши текст, исправив:\n{$var.failures}\n\nСтарый текст:\n{$var.old_text}"
    },
    "ops": [...]
  }
}
Использование в ops через {$tpl.base_prompt}:
json{"op": "llm_call", "prompt_template": "{$tpl.base_prompt}\nДополнительно: {$var.extra_detail}", "output_field": "draft_text"}
Variables — пользовательские переменные внутри DSL. Scope = текущий element run (не сохраняются в data):
json{"op": "var", "name": "min_sent", "value": 5}
{"op": "var", "name": "failures", "value": "{$data.local_failures}"}
{"op": "var", "name": "prompt", "template": "{$tpl.base_prompt}\nЯзык: {$global.language}"}
Доступ через {$var.name}. Variables удобны для:

Промежуточных вычислений без засорения node.data
Параметризации шаблонов (один шаблон + разные переменные)
Передачи контекста между ops без side effects

Global templates (tree-level, для всех нод):
json{
  "global_meta": {
    "templates": {
      "language_instruction": "Отвечай на {$global.language}. Начинай сразу с текста.",
      "style_prefix": "Стиль: {$data.style}."
    }
  }
}
Template resolution order: element.meta.templates → tree.global_meta.templates → not found = literal
Op vocabulary
Data ops: set, copy, increment, append, delete
Variable ops: var (set named variable, accessible via {$var.name})
Template ops: expand (expand template → field or variable)
LLM ops: llm_call, llm_call_or_fallback (with nested fallback_ops) — каждый поддерживает inline temperature, max_tokens, no_think, agent_name
Claim ops: evaluate_claims, check_claims_pass
Text ops: truncate_sentences, regex_replace, strip, join
Control flow: branch (condition → then_ops/else_ops), set_outcome, set_return, halt, loop (max_iterations cap)
Diagnostic: log (message to meta for UI)
Парсинг результата LLM → переменные
llm_call может парсить ответ и извлекать переменные:
json{
  "op": "llm_call",
  "prompt_template": "Оцени формальность текста от 1 до 10. Ответь только числом.\n\nТекст:\n{$data.draft_text}",
  "output_field": "_raw_score",
  "parse": {
    "mode": "number",
    "var": "formality_score"
  }
}
Parse modes:

"number" — извлечь первое число из ответа → {$var.name} как int/float
"word" — первое слово ответа → {$var.name} как строка
"line" — первая строка (trim) → {$var.name}
"json" — парсить весь ответ как JSON → {$var.name} как dict/list
"regex" — {"mode": "regex", "pattern": "Score:\\s*(\\d+)", "group": 1, "var": "score"} → capture group
"enum" — {"mode": "enum", "values": ["YES","NO","PARTIAL"], "var": "verdict"} — найти первое совпадение из списка
"lines" — split по строкам → {$var.name} как list
"key_value" — парсить key: value строки → {$var.name} как dict

Примеры:
LLM call с per-op параметрами:
json{"op": "llm_call",
 "prompt_template": "Есть ли в тексте описание цвета волос? Ответь YES или NO.",
 "output_field": "_check",
 "agent_name": "small_context_worker",
 "temperature": 0.1,
 "max_tokens": 30,
 "no_think": true,
 "parse": {"mode": "enum", "values": ["YES","NO"], "var": "has_hair"}}
no_think: true добавляет prefill <think>\n\n</think>\n\n + continue_assistant_turn: true как в чате. Для коротких ответов: max_tokens: 30 + no_think: true = быстро и дёшево.
Параметры resolution order: op → element.meta → tree.global_meta → defaults:

temperature: op → meta → global → 0.6
max_tokens: op → meta → global → 2048
agent_name: op → meta → global.creative_agent → "small_context_worker"
no_think: op → meta → false

Числовая оценка:
json{"op": "llm_call", "prompt_template": "Rate 1-10: {$data.draft_text}", "output_field": "_raw",
 "parse": {"mode": "number", "var": "quality_score"}},
{"op": "branch", "condition": {"test": "lt", "field": "$var.quality_score", "value": 5},
 "then_ops": [{"op": "set_outcome", "outcome": "fail"}],
 "else_ops": [{"op": "set_outcome", "outcome": "pass"}]}
Enum вердикт:
json{"op": "llm_call", "prompt_template": "Есть ли в тексте описание цвета волос? Ответь YES или NO.\n{$data.draft_text}",
 "output_field": "_check",
 "parse": {"mode": "enum", "values": ["YES","NO"], "var": "has_hair_color"}},
{"op": "branch", "condition": {"test": "eq", "field": "$var.has_hair_color", "value": "YES"},
 "then_ops": [{"op": "set_outcome", "outcome": "pass"}],
 "else_ops": [{"op": "set_outcome", "outcome": "fail"}]}
JSON structured output:
json{"op": "llm_call", "prompt_template": "Верни JSON: {\"score\": число, \"reason\": \"строка\"}\n{$data.draft_text}",
 "output_field": "_analysis",
 "parse": {"mode": "json", "var": "analysis"}},
{"op": "set", "field": "quality_score", "value": "{$var.analysis.score}"},
{"op": "set", "field": "quality_reason", "value": "{$var.analysis.reason}"}
Prompt blocks как первоклассные параметры
System, prompt, think, answer, base_question — все блоки сохраняются и передаются как параметры. Можно ссылаться на них из ops, передавать между нодами, переиспользовать:
json{
  "meta": {
    "templates": {
      "base_question": "Создать 10 описаний внешности в разных стилях",
      "system_critic": "Ты — строгий критик описаний внешности.",
      "answer_format": "Ответь YES или NO. Без пояснений."
    },
    "ops": [
      {"op": "llm_call",
       "system_template": "{$tpl.system_critic}",
       "prompt_template": "Соответствует ли описание задаче: {$tpl.base_question}?\n\nОписание:\n{$data.draft_text}\n\n{$tpl.answer_format}",
       "output_field": "_verdict_raw",
       "temperature": 0.1, "max_tokens": 10, "no_think": true,
       "parse": {"mode": "enum", "values": ["YES","NO"], "var": "matches_task"}}
    ]
  }
}
Multi-parse — несколько parse rules на один LLM call:
json{"op": "llm_call",
 "prompt_template": "Оцени текст:\n1. Формальность (1-10):\n2. Есть цвет волос (YES/NO):\n3. Краткое резюме (одно предложение):\n\n{$data.draft_text}",
 "output_field": "_analysis",
 "parse": [
   {"mode": "regex", "pattern": "Формальность.*?(\\d+)", "group": 1, "var": "formality_score", "type": "int"},
   {"mode": "enum", "values": ["YES","NO"], "var": "has_hair_color"},
   {"mode": "regex", "pattern": "резюме.*?:\\s*(.+)", "group": 1, "var": "summary"}
 ]}
Передача между нодами — через node.data:
json{"op": "set", "field": "base_question", "value": "{$tpl.base_question}"}
Потом в другой ноде: {$data.base_question} содержит сохранённый вопрос.
Prompt block types — для structured LLM calls:
json{"op": "llm_call",
 "messages": [
   {"role": "system", "content": "{$tpl.system_critic}"},
   {"role": "user", "content": "{$tpl.base_question}"},
   {"role": "assistant", "content": "{$data.draft_text}"},
   {"role": "user", "content": "Оцени этот ответ. {$tpl.answer_format}"}
 ],
 "output_field": "evaluation"}
Параметризация промптов, контекста и вопросов
Всё — промпты, системные сообщения, вопросы, инструкции — параметризуется одинаково через шаблоны:
json{
  "meta": {
    "templates": {
      "system": "Ты — {$var.role}. {$tpl.language_instruction}",
      "question": "{$tpl.base_question}\nКонтекст: {$data.context}\nОграничения: {$var.constraints}",
      "base_question": "Ответь на вопрос кратко и точно.",
      "language_instruction": "Отвечай на {$global.language}."
    },
    "ops": [
      {"op": "var", "name": "role", "value": "критик текстов"},
      {"op": "var", "name": "constraints", "value": "максимум 2 предложения"},
      {"op": "llm_call",
       "system_template": "{$tpl.system}",
       "prompt_template": "{$tpl.question}",
       "output_field": "answer",
       "parse": {"mode": "word", "var": "verdict"}}
    ]
  }
}
```

Цепочка resolution: `{$tpl.system}` → "Ты — {$var.role}. {$tpl.language_instruction}" → "Ты — критик текстов. Отвечай на русском."

### Variable scopes
```
{$var.name}      — element-local (ephemeral, only during this element run)
{$node.name}     — node-scope (persistent in node.data._vars, survives across elements in same node)
{$tree.name}     — tree-scope (persistent in tree.global_meta._vars, shared across ALL nodes)
Ops для работы с scoped vars:
json{"op": "var", "name": "score", "value": 5}                           // element-local
{"op": "var", "name": "score", "value": 5, "scope": "node"}          // saved to node.data._vars.score
{"op": "var", "name": "total_passed", "value": 0, "scope": "tree"}   // saved to tree.global_meta._vars.total_passed
Пример: глобальный счётчик пройденных нод:
json// В каждой ноде после audit:
{"op": "branch", "condition": {"test": "eq", "field": "audit_status", "value": "pass"},
 "then_ops": [
   {"op": "increment", "field": "$tree.total_passed"},
   {"op": "log", "message": "Node {$node_id} passed. Total: {$tree.total_passed}"}
 ]}
Пример: передать base_question из root во все дочерние ноды:
json// В root:
{"op": "var", "name": "base_question", "value": "Создать 10 описаний внешности", "scope": "tree"}

// В child node:
{"op": "llm_call", "prompt_template": "Задача: {$tree.base_question}\nСтиль: {$data.style}...", ...}
Template namespaces (полный список)

{$data.field} — node.data (persistent, per-node)
{$global.field} — tree.global_meta (settings: temperature, language, etc.)
{$var.name} — element-local variable (ephemeral)
{$node.name} — node-scope variable (persistent in node.data._vars)
{$tree.name} — tree-scope variable (persistent in tree.global_meta._vars)
{$tpl.name} — named template (recursively expanded)
{$extra.field} — extra context passed to handler
{$node_id}, {$tree_id} — built-in

Conditions (for branch/loop)
json{"test": "truthy|eq|gt|lt|contains|empty|not|all_claims_pass|has_failures", "field": "...", "value": "..."}
```

### Custom Python scripts (op: `run_script`)

Для случаев когда DSL ops недостаточно — агенты могут писать простые Python скрипты в отдельную папку:
```
data/behavior_scripts/
  ├── check_rhyme.py
  ├── count_adjectives.py
  └── validate_json_schema.py
Каждый скрипт — одна функция run(ctx) с доступом к ограниченному API:
python# data/behavior_scripts/check_rhyme.py
def run(ctx):
    text = ctx.get("data.draft_text")
    lines = text.strip().split("\n")
    # простая проверка рифмы
    if len(lines) >= 2 and lines[-1][-3:] == lines[-2][-3:]:
        ctx.set_var("has_rhyme", True)
    else:
        ctx.set_var("has_rhyme", False)
DSL op:
json{"op": "run_script", "script": "check_rhyme", "timeout": 5}
ctx API (sandboxed):

ctx.get("data.field"), ctx.get("var.name"), ctx.get("global.field") — read
ctx.set_var("name", value) — set DSL variable
ctx.set_data("field", value) — write to node.data
ctx.log("message") — diagnostic
Нет: file I/O, network, imports (кроме whitelist: re, json, math, collections)

Загрузка: скрипты загружаются из data/behavior_scripts/ по имени. Hot-reload: файл перечитывается при каждом вызове (кешируется на 10с).
Безопасность:

timeout (default 5с, max 30с)
Restricted builtins (без open, exec, eval, __import__)
Import whitelist: re, json, math, collections, itertools
Скрипт выполняется в отдельном exec scope

Safety

DSL ops: фиксированный набор, нет произвольного кода
loop имеет max_iterations (default 5, cap 20)
{$tpl.name} — max recursion depth 5 (защита от circular refs)
run_script — sandboxed exec с timeout и restricted imports

Implementation
New file: src/kobold_sandbox/dsl_interpreter.py (~300 строк)

DslContext dataclass: tree/node/element/orchestrator + outcome/value/updated_paths/op_log/halted
_run_ops(ctx, ops) — рекурсивный интерпретатор
Per-op functions: _op_set, _op_llm_call, _op_branch, etc.
DSL_OPS: dict[str, Callable] — реестр ops
handle_dsl() — entry point, регистрируется как __dsl__ handler
Reuses _expand_template(), _strip_think(), _sentence_split() из behavior_orchestrator.py

Changes in behavior_orchestrator.py

Import + register: orchestrator.register_handler("__dsl__", handle_dsl) в create_reference_behavior_orchestrator()
Export _expand_template, _strip_think, _sentence_split для импорта из dsl_interpreter.py

UI: tools/behavior_tree.html

В element detail: если handler=__dsl__, показать ops pipeline вместо простого JSON
Каждый op: index, name, summary, status (из node.meta._dsl_log)
Вложенные ops (branch/fallback) — с отступом
Цвета: зелёный=done, оранжевый=running, красный=error

Tests: tests/test_dsl_interpreter.py

Unit tests для каждого op type
Integration: DSL-element в reference tree, run_node, verify outcome

Reference case update

Конвертировать 1-2 ноды в character_description_reference_tree.json на __dsl__

Examples
Generate (was llm_generate):
json{"ops": [
  {"op": "llm_call_or_fallback", "prompt_template": "...", "output_field": "draft_text",
   "fallback_ops": [{"op": "set", "field": "draft_text", "value": "[Stub]"}]},
  {"op": "set", "field": "llm_generated", "value": true},
  {"op": "set_outcome", "outcome": "pass"}
]}
Check + branch (was evaluate_claims):
json{"ops": [
  {"op": "evaluate_claims", "failure_field": "local_failures"},
  {"op": "branch", "condition": {"test": "empty", "field": "local_failures"},
   "then_ops": [{"op": "set_outcome", "outcome": "pass"}],
   "else_ops": [{"op": "set_outcome", "outcome": "fail"}]}
]}
Compress + finalize (was truncate + audit):
json{"ops": [
  {"op": "truncate_sentences", "source_field": "draft_text", "target_field": "final_text"},
  {"op": "evaluate_claims", "failure_field": "_final"},
  {"op": "branch", "condition": {"test": "all_claims_pass"},
   "then_ops": [{"op": "set", "field": "audit_status", "value": "pass"}],
   "else_ops": [{"op": "set", "field": "audit_status", "value": "fail"}]},
  {"op": "set_return", "field": "final_text"},
  {"op": "set_outcome", "outcome": "done"}
]}
```

## UI для DSL ops

В element detail panel для `__dsl__` handler:

### Op pipeline view
Каждый op показан как строка:
```
1. var         role = "критик"
2. llm_call    → draft_text  temp=0.6 max=2048          ✅ done
3. llm_call    → _check  temp=0.1 max=30 no_think       ✅ done
4. branch      has_hair == YES?
   ├ then: set_outcome pass                              ✅
   └ else: set_outcome fail
5. set         audit_status = "pass"                     ✅ done
LLM op detail (при клике на op)

Resolved prompt (подставленные переменные)
agent, temperature, max_tokens, no_think badge
Parse mode + extracted variable
Raw LLM response (если есть в log)

Template library (sidebar или секция)

Список всех templates из element.meta + global_meta
Preview с resolved variables
Click to edit

Variables panel

Текущие {$var.*} со значениями
Подсветка где используются

Verification

python -m pytest tests/test_dsl_interpreter.py -v — all ops work
python -m pytest tests/test_behavior_orchestrator.py -v -k "not live" — existing tests pass
В UI: открыть DSL element → видеть ops pipeline с resolved values
Run node с DSL element → результат идентичен native handler