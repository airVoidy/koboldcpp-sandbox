# Next Chat Starter — Session D (Card Builder continued)

## Context
Reactive Task Builder — single-file HTML app (`tools/reactive_chat.html`) + Python server (`src/kobold_sandbox/server.py`).
KoboldCPP local LLM backend. All DSL commands server-side via `/api/atomic/run`.

## What's Done (Session C)
- **Card Builder Phase 1-3**: DSL commands + tab UI + palette + canvas + props panel + drag reorder + undo (Ctrl+Z) + console log
- **DSL commands**: card_template, add_slot, remove_slot, move_slot, bind_slot, slot_option, apply_template, delete_template, clone_template
- **11 component types**: title, tags, text_area, image, buttons, thread (tree/flat), data_table, reactions, list, form, group (container with children)
- **Template data**: `cardTemplates` in localStorage, `CardSlot {id, type, label, binding, options, children}`
- **Undo**: snapshot-based, builderPushUndo before each mutation, Ctrl+Z on builder tab
- **All GUI actions → DSL**: every visual change emits a DSL command to console

## What's Next

### Phase 4: Slot Component Renderers (~200 lines)
- Extract rendering functions from `renderNode()` (line ~1586) — the workflow etalon card
- Create `renderSlotTitle`, `renderSlotTags`, `renderSlotTextArea`, `renderSlotImage`, `renderSlotButtons`, `renderSlotThread`, `renderSlotDataTable`, `renderSlotReactions`, `renderSlotList`, `renderSlotForm`, `renderSlotGroup`
- `renderTemplatedCard(entity, template)` — iterates slots, calls renderSlot* for each
- Config-aware branch in `renderEntityCard()` (line ~3871): if entity has `tags.card_template` → use template rendering

### Phase 5: Live Preview (~80 lines)
- Preview pane in builder canvas using sample entity data
- Re-renders on every template change
- Sample data = first entity from atomicEntities or hardcoded defaults

### Then: Workflow Migration
- Convert `renderNode()` hardcoded layout into a card template config
- Reply/Thread rules, context etc → from hardcode to config
- Thread modes: tree (forum/slack with nested replies) vs flat (mIRC-like chat)

## Key References
- `renderNode()` at line ~1586 — etalon card layout to replicate
- `renderEntityCard()` at line ~3871 — where template rendering hooks in
- `cardTemplates` / `saveCardTemplates()` — data model
- `toolAddSlot()`, `toolBindSlot()` etc — DSL command handlers
- `renderBuilderPage()` — builder UI render
- `renderSlotTree()` — canvas slot tree renderer
- `builderPushUndo()` / `builderUndo()` — undo system
- Demo template: `examples/card_templates/demo_card.json`

## Demo Template (already built)
```
card_template(demo_card)
add_slot(@demo_card, title)
add_slot(@demo_card, tags)
add_slot(@demo_card, group, label:"Answer")
  add_slot(@demo_card, text_area, parent:"s_3", label:"RESULT")
  add_slot(@demo_card, image, parent:"s_3")
  add_slot(@demo_card, buttons, parent:"s_3")
add_slot(@demo_card, reactions)
add_slot(@demo_card, thread)
```

## Style Notes
- Warm casual tone, concise responses
- All LLM calls visible in UI, no hidden server logs
- Don't edit LLM prompts beyond what's explicitly requested
- Server-side framework, JS is display layer only
- $config.* for global params, @name for local entities
