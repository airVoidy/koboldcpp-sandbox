# Session E — 2026-03-27

## What was done

### 1. Worker component reference cleanup
- `_builderComponentRef()` simplified from verbose table+DSL spec to a flat 2-line reference
- Available slot types: `title, tags, text_area, image, buttons, thread, data_table, reactions, list, form, group, children`
- Rule: "DSL is layout only — no data fields in add_slot commands"
- Rationale: small LLMs with large context need direct lists, not abstract specs

### 2. Scrollbar styling
- Added global `::-webkit-scrollbar` styles (6px thin, dark theme colors)
- Firefox support via `scrollbar-width: thin; scrollbar-color`
- All panels (builder canvas, properties, live preview, code editor) now have consistent thin dark scrollbars

### 3. Worker DSL generation analysis
- Worker correctly identified slot types and nesting structure for demo_card template
- Worker incorrectly embedded `data:` fields in DSL commands (should be layout only)
- Root cause: worker needs explicit component list in context, not spec-level documentation

## Next steps — 3 base layout modes

The next session should implement 3 layout modes as card_template configs to validate the DSL/slot system's flexibility:

1. **Forum-alike** — threaded topic cards, nested replies, quote blocks
2. **mIRC-alike** — linear shared chat, messages append at bottom, simple feed
3. **Slack-alike** — channels, message threads, reactions, rich embeds

Goal: prove the same DSL + slot system handles diverse UI paradigms without code changes.

## Additional open items
- Atomic Tasks: debug info in user step cards (show @parsed, @claims, entities after tool runs)
- Atomic Tasks: worker prompts need detailed spec with examples (small models need verbose context)
- Properties panel hide button fix (Card Builder)
- Progress bar visual cleanup
