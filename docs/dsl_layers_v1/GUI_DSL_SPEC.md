# GUI DSL Spec — 4-Layer Client Display Architecture

## Overview

GUI DSL describes how data is displayed and interacted with on the client.
Server is a data source only. All display logic is client-side.

The universal invariant: **everything is a Message container**.
A single message, a batch of 50, a server response — all wrapped as Message with meta + data.

## Architecture

```
Server (matrices, storage)
    │
    │  Messages (serialized containers: meta + data)
    ▼
Mid-layer (card type registry, field refs, batch protocol)
    │
    │  raw data + template ref
    ▼
Client (4 DSL layers → rendered UI)

  L1  Layout DSL        — slot structure inside a card
  L2a Visual DSL        — screen skeleton, AABB zones, panels, CSS
  L2b Data Mapping DSL  — field refs, card types, batch protocol
  L3  Interaction DSL   — triggers, listeners, events, client logic
```

Server-client contract: **field paths only**.
Server stores however it wants. Client renders however it wants.
Mid-layer translates between the two via card types and field declarations.

L2a and L2b are parallel, not sequential:
- L2a says WHERE on screen things go (zones, panels, grid)
- L2b says WHAT data fills those zones (field refs, card types)
- Both feed into L1 card templates that define internal slot structure

---

## Layer 1: Layout DSL

**What:** slot structure, grouping, order.
**Where:** Card Builder, stored as serialized DSL / JSON templates.
**Already exists:** `card_template()`, `add_slot()`, slot types.

```
card_template(message)
  add_slot(@message, title, label:"Author")
  add_slot(@message, text_area, label:"Content")
  add_slot(@message, reactions)
  add_slot(@message, thread, label:"Replies", mode:"flat")
```

Defines WHAT is shown and in what structure. No data knowledge, no behavior.

### Slot Types (current)

```
title, tags, text_area, image, buttons, thread,
data_table, reactions, list, form, group, children
```

### Rules
- Layout is a tree of slots
- `group` nests children slots
- `children` renders sub-cards (with optional template ref)
- No data refs at this layer — pure structure

---

## Layer 2a: Visual DSL

**What:** screen skeleton — zones, panels, grid/flex layout, CSS properties.
**Where:** client-side. Defines the spatial structure BEFORE any data arrives.

L2a answers: "what does the screen look like as empty boxes?"

### Zone Model

A zone is an AABB (axis-aligned bounding box) — a rectangular region on screen.

```yaml
screen: slack_layout
  zone: sidebar
    width: 240px
    height: fill
    position: left
    scroll: vertical
    style:
      background: var(--bg-secondary)
      border-right: 1px solid var(--border)

  zone: main
    width: fill
    height: fill
    position: right-of(sidebar)
    layout: column

    zone: header
      height: 48px
      style:
        border-bottom: 1px solid var(--border)

    zone: messages
      height: fill
      scroll: vertical
      tag: message_list

    zone: input
      height: auto
      min-height: 40px
      max-height: 200px
      style:
        border-top: 1px solid var(--border)

  zone: thread_panel
    width: 360px
    height: fill
    position: right-of(main)
    visible: false          # shown on trigger
    style:
      border-left: 1px solid var(--border)
```

### Zone Properties

| Property | Values | Description |
|----------|--------|-------------|
| `width` / `height` | `Npx`, `N%`, `fill`, `auto` | sizing |
| `min-*` / `max-*` | `Npx` | constraints |
| `position` | `left`, `right-of(id)`, `below(id)`, `stack` | placement relative to siblings |
| `layout` | `row`, `column`, `stack`, `grid(cols)` | children arrangement |
| `scroll` | `none`, `vertical`, `horizontal`, `both` | overflow behavior |
| `visible` | `true`, `false` | initial visibility (toggled by L3) |
| `tag` | string | semantic tag for L2b to bind card types into |
| `style` | CSS-like properties | visual appearance |

### Nesting

Zones nest. A zone inside a zone creates a layout tree:

```
screen
  └─ sidebar          (left, 240px)
  └─ main             (fill, column layout)
       └─ header      (48px)
       └─ messages    (fill, scroll)
       └─ input       (auto height)
  └─ thread_panel     (right, hidden)
```

### Tags

Tags connect L2a zones to L2b card types:

```yaml
zone: messages
  tag: message_list       # L2b knows: "message_list" zone holds card_type "message"

zone: sidebar
  tag: channel_list       # L2b knows: "channel_list" zone holds card_type "channel_item"
```

Tags are the bridge. L2a doesn't know about data. L2b doesn't know about pixels.

### 3 Reference Skeletons

#### Forum
```yaml
screen: forum_layout
  zone: topic_list
    width: 300px
    scroll: vertical
    tag: topic_list

  zone: topic_view
    width: fill
    layout: column

    zone: topic_header
      height: auto
      tag: topic_header

    zone: topic_body
      height: auto
      tag: topic_body

    zone: replies
      height: fill
      scroll: vertical
      tag: reply_list
```

#### mIRC
```yaml
screen: mirc_layout
  zone: channel_bar
    height: 32px
    layout: row
    tag: channel_tabs

  zone: chat
    width: fill
    height: fill
    layout: column

    zone: messages
      height: fill
      scroll: vertical
      tag: message_list

    zone: input
      height: 32px
      tag: chat_input

  zone: userlist
    width: 160px
    position: right-of(chat)
    scroll: vertical
    tag: user_list
```

#### Slack
```yaml
screen: slack_layout
  zone: sidebar
    width: 240px
    scroll: vertical
    tag: channel_list

  zone: main
    width: fill
    layout: column

    zone: header
      height: 48px
      tag: channel_header

    zone: messages
      height: fill
      scroll: vertical
      tag: message_list

    zone: input
      height: auto
      tag: chat_input

  zone: thread_panel
    width: 360px
    position: right-of(main)
    visible: false
    tag: thread_view
```

---

## Layer 2b: Data Mapping DSL

**What:** connects data fields to layout slots, defines card types, batch shapes.
**Where:** mid-layer between server and client.

### Card Type Registry

Each card type = one template + one field declaration + one batch shape.

```yaml
card_type: message
  template: "message"
  fields:
    - author        # → title slot
    - text           # → text_area slot
    - reactions      # → reactions slot
    - replies        # → thread slot
    - time           # → meta display
    - status         # → status badge
```

### Field Refs

Slots bind to data via `bind` option:

```
add_slot(@message, title, bind:"author")
add_slot(@message, text_area, bind:"text")
add_slot(@message, thread, bind:"replies")
```

Resolve is dot-path: `bind:"author.name"` → `data.author.name`

### Batch Protocol

Request:
```yaml
batch_request:
  card_type: "message"
  scope: "room_17"
  range: [current, last:50]
  fields: [author, text, reactions, time]
```

Response = one Message container:
```yaml
message:
  type: "batch"
  card_type: "message"
  meta: { scope: "room_17", count: 50, has_more: true }
  rows: [ {raw}, {raw}, ... ]    # serialized, as-is
```

### Message Handlers (small fixed set)

| Handler | Trigger | Action |
|---------|---------|--------|
| `hydrate_batch` | batch response arrives | render N cards from rows |
| `append_one` | new single message | add card to end |
| `update_field` | field change on existing | rerender affected slot |
| `remove` | delete event | remove card |
| `prepend_batch` | "load more" response | insert cards at top |

---

## Layer 3: Interaction DSL

**What:** client-side display logic, interactivity, read requests.
**Where:** entirely on client. Server is read-only source for this layer.

This is the thickest layer. Every UI behavior lives here.

### Node Model

Each rendered UI element is an autonomous node with 3 explicit lists:

```yaml
node:
  id: "n_1"
  type: "thread"
  path: "room_17.replies"

  triggers:           # actions this node can initiate
    - scroll_to_bottom
    - collapse
    - request_more
    - select_item

  listeners:          # what this node reacts to
    - data:append     # new item in data path
    - data:bulk       # batch load
    - sibling:collapse  # adjacent node collapsed
    - viewport:enter  # scrolled into view

  events:             # what this node emits
    - item_clicked
    - overflow        # content exceeds viewport
    - empty           # no data
    - scrolled_to_end # trigger load-more
```

### Why 3 Explicit Lists

- **triggers**: what user/system can ask this node to do → policy can allow/deny
- **listeners**: what data/events this node consumes → lifecycle can auto-sub/unsub
- **events**: what this node produces → other nodes or policy can subscribe

Declared per **Card Type**, not per instance. 50 chat rooms share one trigger/listener/event declaration.

### Interaction Primitives

```yaml
# Collapse/expand
collapse:
  trigger: click_header
  affects: body
  state: open | collapsed
  persist: per_node     # remember state

# Lazy load / pagination
load_more:
  trigger: scrolled_to_end | button_click
  action: request_batch(card_type, scope, range:[next:50])
  handler: prepend_batch

# Filter
filter:
  trigger: input_change
  source: local_data    # client-side, no server call
  predicate: "text contains $query"
  affects: visible_items

# Sort
sort:
  trigger: header_click
  source: local_data
  key: "time" | "author" | "reactions.count"
  direction: asc | desc

# Selection
select:
  trigger: click_item
  mode: single | multi | range
  events: [selection_changed]

# Virtual scroll
virtual_scroll:
  trigger: scroll
  window: 50            # render only N visible items
  buffer: 10            # pre-render N above/below

# Derived values (cross-cutting)
derived:
  path: "room_17.unread_count"
  compute: count(room_17.messages, where: "read == false")
  listeners: [data:append, data:update_field]
  events: [value_changed]

# Read request to server
read_request:
  trigger: viewport:enter | explicit
  action: batch_request(card_type, scope, fields)
  debounce: 100ms
```

### Lifecycle

```
node created (template applied)
  → subscribe to declared listeners
  → emit "mounted"

node destroyed (scrolled away / room closed)
  → unsubscribe all listeners
  → emit "unmounted"
  → no manual cleanup needed
```

### Event Flow (no central controller)

```
user scrolls to bottom
  → thread node: trigger "scrolled_to_end"
  → thread node: action "request_more"
  → mid-layer: batch_request → server
  → server: response Message (batch)
  → mid-layer: handler "prepend_batch"
  → thread node: listener "data:bulk" fires
  → thread node: rerenders with new items
  → thread node: emits "overflow" if too many
  → scrollbar node: listener "sibling:overflow" → adjusts
```

No manager, no store, no controller. Nodes talk via events.

---

## Client Storage

Everything stored close to wire format:

```
localStorage / memory:

templates: {
  "message":     { slots: [...], serialized_dsl: "..." },
  "chat_room":   { slots: [...], serialized_dsl: "..." },
  "forum_topic": { slots: [...], serialized_dsl: "..." }
}

card_types: {
  "message":     { template: "message", fields: [...], handlers: [...] },
  "chat_room":   { template: "chat_room", fields: [...], handlers: [...] }
}

data: {
  "room_17": {
    card_type: "message",
    rows: [ {raw}, {raw}, ... ]     # as received from server
  }
}
```

No intermediate models. Render = `template + raw data → HTML`.

---

## Rendering Pipeline

```
1. screen skeleton rendered from L2a (zones, layout, CSS — no data yet)
2. raw data arrives (Message container from server)
3. handler routes by message type (batch/single/update/remove)
4. card_type lookup (L2b) → get template (L1) + field declaration + target zone tag
5. for each data row:
     template.slots.forEach(slot →
       value = resolve(row, slot.bind)
       html += renderSlot(slot.type, value)
     )
6. rendered card inserted into matching L2a zone (by tag)
7. interaction layer (L3) attaches triggers/listeners per card_type declaration
8. node is live — reacts to events autonomously
```

---

## 3 Reference Templates

### Forum
```
card_type: forum_topic
  template: forum_topic
  fields: [title, category, body, reactions, replies]
  children_type: forum_reply

  interaction:
    replies: { collapse: true, load_more: true, sort: [time, votes] }
    body: { collapse: true, max_lines: 10 }

card_type: forum_reply
  template: forum_reply
  fields: [author, text, reactions, nested]
  interaction:
    nested: { collapse: true, indent: true, max_depth: 3 }
```

### mIRC
```
card_type: mirc_channel
  template: mirc_chat
  fields: [channel_name, users, messages]

  interaction:
    messages: { scroll_to_bottom: true, virtual_scroll: 200, reverse: true }
    users: { sort: [status, name], filter: true }
```

### Slack
```
card_type: slack_channel
  template: slack_channel
  fields: [channel_name, pinned, messages, reactions]

  interaction:
    messages: { scroll_to_bottom: true, virtual_scroll: 100, load_more: true }
    pinned: { collapse: true }
    thread_sidebar: { trigger: message_click, mode: slide_panel }
    reactions: { inline: true, picker: true }
```

---

## Summary

| Layer | Scope | Knows about | Doesn't know about |
|-------|-------|-------------|-------------------|
| L1 Layout | slot tree inside a card | types, order, groups | screen position, data, behavior |
| L2a Visual | screen skeleton | zones, AABB, CSS, tags | data fields, card types |
| L2b Data Mapping | data ↔ zones ↔ slots | field paths, card types, batch shapes | pixels, CSS, behavior |
| L3 Interaction | client display logic | triggers, listeners, events | server storage, layout structure |

```
Direction:

  L2a (skeleton)  ──┐
                    ├──►  Rendered UI
  L2b (data)  ─────┤
                    │
  L1 (card slots)  ─┘
                    │
  L3 (interaction)  ──►  live behavior on rendered nodes
```

L2a and L2b are parallel inputs — one provides WHERE, the other provides WHAT.
L1 provides HOW (internal card structure). L3 provides WHEN (reactions to events).

Server never knows about UI. Client never knows about storage format.
L2b is the only place where both sides meet — through field paths and card types.
L2a is pure client — server doesn't know about zones or layout.
