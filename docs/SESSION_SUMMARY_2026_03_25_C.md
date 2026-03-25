# Session Summary — 2026-03-25 Session C

## Card Builder + DSL Fixes

### What was done

#### DSL v2 Fixes
- **All DSL tools server-side**: tag, remove_tag, set_text, append_text, table_header, reshape_grid, join — all route through `/api/atomic/run`
- **`$config.*` normalization**: UI, export, docs all use `$config.name` (parser converts to internal `@config.`)
- **Multiline trigger parsing**: regex fix `[\s\S]+` for triggers spanning multiple lines
- **Pipeline import fix**: `fromPipeline` flag prevents recursive pipeline detection
- **Import popup fix**: single-field `showNamePopup` returns string, not object
- **`await` fix**: all async server-side tools now awaited in `applyAtomicTool` dispatch
- **Restart Pipeline** button in context menu
- **Global Params aliases**: `{type: 'alias', name, ref}` — multiple names for same data, resolveRef follows chain

#### Server-side
- `until_contains`, `until_regex`, `min_chars` continue conditions in generate
- `continue_assistant_turn` fix for prefill/continue modes
- Server handlers for tag, remove_tag, set_text, append_text, table_header, reshape_grid, join

#### Card Builder (Phase 1-3)
- **Data model**: `cardTemplates` in localStorage, `CardSlot` with id/type/label/binding/options/children
- **11 component types**: title, tags, text_area, image, buttons, thread (tree/flat), data_table, reactions, list, form, group
- **DSL commands**: card_template, add_slot, remove_slot, move_slot, bind_slot, slot_option, apply_template, delete_template, clone_template
- **Card Builder tab**: 3-panel layout (palette + canvas + properties)
- **Canvas**: slot tree rendering with indent for group children
- **Properties panel**: label, binding, type-specific options (buttons items, thread mode, etc.)
- **Drag reorder**: HTML5 DnD on canvas slots → move_slot DSL
- **All visual actions → DSL**: palette click, prop edit, delete all emit DSL commands

#### Pipeline E2E test
- Full pipeline tested: `@input` → `generate` → `parse_sections` → `join` — all through server
- `$config.prompt_constraints` + `$config.hypothesis_cols` created in Global Params

### What's Next (Phase 4-5)
- **Phase 4**: Slot component renderers — extract renderSlot* functions, renderTemplatedCard, config-aware branch in renderEntityCard
- **Phase 5**: Live preview in canvas using sample entity data
- **Workflow migration**: convert renderNode() hardcoded layout to card template config

### Key Files Modified
- `tools/reactive_chat.html` — Card Builder UI, DSL tools, fixes
- `src/kobold_sandbox/server.py` — server-side tool handlers, continue conditions
- `docs/PIPELINE_DSL_SPEC.md` — v2 spec updates
- `docs/ATOMIC_DSL_RECIPES.md` — example pipelines

### Card Template Example (demo_card)
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
