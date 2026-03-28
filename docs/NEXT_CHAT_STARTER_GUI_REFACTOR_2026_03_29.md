# Next Chat Starter — GUI Builder Refactor

Скопируй это как первое сообщение в новом чате.

---

Прочитай для контекста:

- Всю memory из MEMORY.md (особенно session F summary)
- `tools/gui_builder.html` — текущий код (3400 строк)
- `tools/reactive_chat.html` — reference (11600 строк, не трогаем, только как пример)
- `tools/dsl_pipeline_chat.html` — новый Pipeline Chat (пример чистой архитектуры)
- `docs/WORKFLOW_V3_SPEC_DRAFT.md` — направление развития

## Задача

Рефактор `gui_builder.html` — убрать hardcoded структуры, перейти на registry/config подход.

## Что захардкожено сейчас

1. **Slot types** — 11 типов hardcoded в palette HTML + VALID_SLOT_TYPES Set + DSL commands
2. **DSL commands** — 8 switch-case в execDSL
3. **Component template system** — hardcoded property serialization
4. **Settings panel** — дублируется с reactive_chat
5. **Worker management** — дублируется
6. **LLM fetch** — дублируется

## Направление рефактора

### Phase 1: Slot Type Registry
```js
// Вместо hardcoded Set + palette HTML:
const SLOT_REGISTRY = {
  title: { label: 'Title', icon: '#', defaults: {}, render: renderTitle },
  tags: { label: 'Tags', icon: '●', defaults: {separator: ', '} },
  text_area: { label: 'Text', icon: '¶', defaults: {collapsed: false} },
  // ... extensible
};
// Palette generated: Object.entries(SLOT_REGISTRY).map(...)
// Validation: key in SLOT_REGISTRY
```

### Phase 2: DSL Command Registry
```js
// Вместо switch-case:
const DSL_COMMANDS = {
  card_template: {handler: dslCardTemplate, params: ['name']},
  add_slot: {handler: dslAddSlot, params: ['@template', 'type', '...options']},
  // ... extensible
};
function execDSL(line) {
  const cmd = DSL_COMMANDS[name];
  if (cmd) cmd.handler(args);
}
```

### Phase 3: Shared Components
Вынести в общий модуль (или inline shared functions):
- Settings panel (temperature, max_tokens)
- Worker list + probe
- LLM fetch wrapper
- Theme CSS variables

### Phase 4: Config-Driven Pages
```js
const PAGES = [
  {id: 'cards', label: 'L1 Slots', render: renderCardsPage},
  {id: 'components', label: 'L1.5 Components', render: renderComponentsPage},
  // ...
];
// Tab bar generated from PAGES array
```

## Ограничения

- Не ломать существующую функциональность
- reactive_chat.html НЕ трогать (только как reference)
- Инкрементально: один phase за раз, тестируем после каждого
- gui_builder.html остаётся single-file (no build system)
