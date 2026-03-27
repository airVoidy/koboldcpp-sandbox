# Atomic Memory Spec v0.1

## Purpose

`Atomic` needs a memory model that is:

- local-first
- chat-native
- matrix-first in day-to-day processing
- marked-concat-first in canonical text storage
- directly addressable
- compatible with secure sandbox boundaries
- suitable for benchmark-heavy route exploration

This spec defines the first practical version of that model.

---

## 1. Core Principles

### 1.1 Memory-first

`Atomic` is not centered around prompts or workers.
It is centered around:

- data
- metadata
- checkpoints
- transformations
- lineage
- addressability

LLM calls are only one class of transformation over memory.

### 1.2 Worker as gateway

Inside `Atomic`, a worker should be treated primarily as:

- a gateway
- an endpoint
- a queue boundary
- a transformation crossing

not as a rich user-facing object model.

Every crossing through such a gateway is a natural point to:

- capture lineage
- benchmark latency and stability
- attach route metadata
- attach `gen_id`
- compute or defer lightweight embeddings and fingerprints

### 1.3 Matrix-first

Everything that can reasonably be normalized should be represented as a 2D matrix:

- lists
- constraints
- checkpoints
- probe logs
- accepted/rejected items
- semantic groups

Even simple lists should be projected into tables early.

### 1.4 Sparse-addressable text

Text remains the richest natural carrier.
So text is retained in open, readable form, but with explicit addressability.

That addressability is modeled as a sparse virtual address space.

### 1.5 Marked readable concat

For text-heavy tasks, especially parse-and-annotate tasks, `Atomic` should assume a canonical virtual form:

- one readable concat carrier
- split into chunks
- explicitly marked
- directly addressable
- easy to project into tables

This is not the only physical storage layout.
It is the most useful canonical virtual layout for moving:

- from big text to small semantic groups
- from small semantic groups back to larger artifacts

### 1.6 Source of truth

Source of truth is:

- user-local messages
- message sidecar metadata

Everything else is derived, cached, normalized, or indexed.

### 1.6.1 Canonical L1 envelope

Even if lower server-side storage uses somewhat different internal layouts,
`L1` should remain canonically message-based.

That means:

- meaningful data should be representable as a message container
- meaningful data changes should be wrappable into message containers
- checkpoints should be representable in message form
- gateway-produced outputs should attach to message-level containers

This is both:

- a compatibility rule for other modules
- and a practical user-facing way of working with data

### 1.7 Redundant metadata is allowed

For this system, redundant metadata is a feature, not a bug.
If it helps with:

- replay
- slicing
- route mining
- debugging
- safe automation

it is acceptable to store it.

---

## 2. Layer Model

### L1: Message Layer

Human-readable containers.

Each message contains:

- open text or structured readable content
- sidecar metadata

This is the most natural user-facing and chat-facing storage layer.

This layer should remain canonical even if lower layers are implemented differently internally.

In practice, this layer should often look like:

- readable marked concat
- chunked text
- explicit block ids
- explicit local addresses

### L2: Matrix Layer

Primary working layer for agents and transformations.

This layer contains:

- tables
- projections
- lists as matrices
- checkpoints as row sets
- probe and acceptance logs

This is the default operational layer.
If something survives longer than one step, it should usually appear here.

### L3: Sparse Virtual File Layer

Addressable backing space for text chunks and long-lived block placement.

This layer provides:

- fixed virtual offsets
- block references
- cluster-local placement
- cache window projections

### L4: Retrieval / Optimization Layer

Optional secondary layer:

- embeddings
- route indexing
- cluster discovery
- ChromaDB or similar

This layer is not the source of truth.

---

## 3. Core Storage Decision

The selected direction is:

- `Matrix-First`
- plus `Sparse Virtual File`

This gives:

- readable user-local messages
- safe structured working state
- stable addressing
- future-friendly cache and embedding behavior

This is intentionally a hybrid:

- tables for working state
- sparse address space for canonical text placement
- sidecar metadata to bridge both

---

## 4. Core Types

### 4.1 MessageRecord

Message container with sidecar metadata.

```json
{
  "message_id": "msg_00017",
  "thread_id": "thread_local_01",
  "role": "assistant",
  "kind": "checkpoint",
  "body": {
    "text": "ENTITIES:\n- eye color\n- hair color\n\nAXIOMS:\n- unique eye color",
    "format": "plain_text"
  },
  "meta": {
    "schema": "constraints_manifest.v1",
    "checkpoint": "constraints",
    "aliases": {
      "entities": "body.text.sections.entities",
      "axioms": "body.text.sections.axioms"
    },
    "positions": {
      "char_total": 78,
      "token_total": null,
      "used_blocks": ["blk_0012", "blk_0013"]
    },
    "tables": ["tbl_constraints_01"],
    "block_refs": ["blk_0012", "blk_0013"],
    "derived_from": ["msg_00012"],
    "transform_type": "parse_sections",
    "gateway_refs": ["gw_evt_0008"],
    "route_signature": "constraints.parse.v1",
    "status": {
      "accepted": true,
      "complete": true,
      "confidence": 0.82
    }
  }
}
```

Required fields:

- `message_id`
- `thread_id`
- `role`
- `kind`
- `body`
- `meta`

Recommended `meta` fields:

- `schema`
- `checkpoint`
- `aliases`
- `positions`
- `tables`
- `block_refs`
- `derived_from`
- `transform_type`
- `gateway_refs`
- `route_signature`
- `status`

### 4.2 TableFrame

Primary working datatype.

```json
{
  "frame_id": "tbl_constraints_01",
  "schema": "constraint_rows.v1",
  "headers": [
    "row_id",
    "kind",
    "value",
    "source_message_id",
    "block_ref",
    "char_start",
    "char_end",
    "char_len",
    "accepted",
    "confidence"
  ],
  "rows": [
    ["r1", "entity", "eye color", "msg_00017", "blk_0012", 10, 19, 9, true, 0.93],
    ["r2", "entity", "hair color", "msg_00017", "blk_0012", 23, 33, 10, true, 0.91],
    ["r3", "axiom", "unique eye color", "msg_00017", "blk_0013", 46, 62, 16, true, 0.88]
  ],
  "row_meta": {
    "r1": {
      "aliases": ["entity.eye_color"],
      "scope_tags": ["constraints", "entity"]
    },
    "r3": {
      "aliases": ["axiom.unique_eye_color"],
      "scope_tags": ["constraints", "axiom"]
    }
  },
  "frame_meta": {
    "message_refs": ["msg_00017"],
    "derived_from": ["blk_0012", "blk_0013"],
    "transform_type": "normalize_constraints",
    "route_signature": "constraints.normalize.v1"
  }
}
```

Required fields:

- `frame_id`
- `schema`
- `headers`
- `rows`
- `frame_meta`

Recommended fields:

- `row_meta`
- `aliases`
- `source_refs`

Rule:

If an artifact survives longer than one step, it should have a `TableFrame` projection.

This applies even to:

- lists
- checklists
- extracted tags
- candidate groups
- probe outputs

### 4.3 SparseBlock

Addressable chunk of text in virtual sparse space.

```json
{
  "block_id": "blk_0012",
  "space_id": "vfile_main_01",
  "offset": 1048576,
  "length": 128,
  "encoding": "utf-8",
  "content_ref": {
    "message_id": "msg_00017",
    "char_start_in_message": 0,
    "char_end_in_message": 35
  },
  "tags": [
    "constraints",
    "entities"
  ],
  "aliases": [
    "msg_00017.entities_block"
  ],
  "neighbors": {
    "prev": null,
    "next": "blk_0013"
  },
  "meta": {
    "cluster_id": "cluster_constraints_a",
    "scope_tags": ["manifest", "entity_list"],
    "derived_from": ["msg_00017"]
  }
}
```

Required fields:

- `block_id`
- `space_id`
- `offset`
- `length`
- `content_ref`
- `tags`

Why this exists:

This allows text to remain readable and locally stored while still supporting:

- fixed addressing
- sparse layouts
- cache windows
- cluster-local packing

It also makes it possible to remap the same textual chunks into:

- RAM windows
- VRAM-oriented working windows
- cluster-local overlays

without losing the usefulness of local address markers.

### 4.4 VirtualFileRegistry

Registry for sparse virtual address space.

```json
{
  "space_id": "vfile_main_01",
  "layout": "sparse",
  "block_size_hint": 128,
  "address_unit": "char",
  "blocks": [
    {"block_id": "blk_0012", "offset": 1048576, "length": 128},
    {"block_id": "blk_0013", "offset": 1048704, "length": 128}
  ],
  "meta": {
    "ram_profile": "med",
    "cache_policy": "cluster_local",
    "compression": "lz4"
  }
}
```

Required fields:

- `space_id`
- `layout`
- `blocks`

Notes:

This is a virtual layout.
It does not require a literal contiguous file on disk.

---

## 5. Position Convention

For any addressable text artifact, store redundant position info.

Required:

- `char_start`
- `char_end`
- `char_len`

Optional but recommended:

- `token_start`
- `token_end`
- `token_len`
- `line_start`
- `line_end`

Mandatory references:

- `message_id`
- `block_ref`

The same text span should be reachable from:

- the original message
- the sparse block
- the matrix projection

---

## 6. Metadata Convention

Metadata should describe:

- what this artifact is
- where it lives
- how it was produced
- what it can become next

Required metadata:

- `schema`
- `checkpoint`
- `derived_from`
- `transform_type`
- `status`

Recommended metadata:

- `aliases`
- `positions`
- `tables`
- `block_refs`
- `probe_refs`
- `patch_refs`
- `gen_id`
- `cluster_id`
- `related_refs`
- `gateway_refs`
- `benchmark_refs`

Status object, at minimum:

- `accepted`
- `complete`
- `confidence`

---

## 7. Lineage Convention

Every artifact must know how it came to exist.

Required lineage fields:

- `derived_from`
- `transform_type`

Recommended lineage fields:

- `pipeline_step_id`
- `checkpoint_from`
- `checkpoint_to`
- `producer`
- `gen_id`
- `probe_id`
- `patch_id`
- `route_signature`

This is especially important because the system is chat-centered and benchmark-driven.

---

## 8. Gateway Linkage

Whenever data crosses a model gateway, metadata should be enriched.

At minimum, record:

- `gen_id`
- `worker_role`
- `endpoint`
- `input_refs`
- `output_refs`
- `checkpoint_from`
- `checkpoint_to`
- `transform_type`
- `latency_ms`
- `accepted`

This event is a useful semantic fingerprint even before any embedding is computed.

Even when gateway linkage is stored as metadata or sidecar structure,
the accepted output of the crossing should still remain attachable to message-layer containers.

If resources are free while the gateway is busy, the system may also:

- attach a lightweight embedding
- attach a route fingerprint
- attach constraint coverage notes
- attach verification traces

Verification crossings are especially valuable here, because they naturally expose:

- constraints
- verdicts
- reject reasons
- coverage gaps

---

## 9. Text Rule

Text should stay in readable open form locally.

This is realistic and compatible with user behavior.

Security is achieved through:

- local-first storage
- sandbox boundaries
- safe sharing rules
- selective metadata exposure

not through assuming that all user data will be encrypted at rest in perfect ways.

---

## 10. Safe Sharing Rule

Users may exchange:

- DSL
- presets
- schemas
- safe metadata summaries
- route signatures

Users should not exchange by default:

- raw local memory
- local LLM internals
- private checkpoint stores
- unrestricted internal object graphs

This aligns with the secure-sandbox interaction model.

Share the sandbox, not the core.

---

## 11. Route Exploration Rule

At the user-agentic layer, the system should begin with:

- what we have
- what we want to get

Then it should:

- define checkpoints
- serialize them redundantly
- explore candidate routes
- collect benchmark metadata
- preserve lineage

The final saved DSL route should be the most reliable route, not necessarily the fastest route.

The intended high-level interface is deliberately blunt and fail-safe:

- what we have
- what we want
- what constraints matter
- what checkpoints are expected
- what can go wrong

Then route exploration can stay systematic instead of relying on hidden prompt magic.

---

## 12. Checkpoint Serialization Rule

Checkpoints should be serialized redundantly and, where useful, in multiple forms:

- readable message form
- matrix form
- sparse-block form

This makes route comparison and replay easier.

Where useful, multiple checkpoint variants may coexist for the same stage:

- strict parse form
- loose human-readable form
- verification-oriented table form

This is intentional redundancy, not accidental duplication.

---

## 13. Initial Task Bias

The first practical focus for this memory model is:

- parse and annotate as is
- from big text to smaller tagged groups

This direction is a good first milestone because metadata built there is reusable in both directions:

- big -> small
- small -> big

---

## 14. Design Goal

The goal of `Atomic Memory Spec v0.1` is not perfect compression or elegance.

The goal is:

- stable addressability
- readable local storage
- structured working state
- benchmark-friendly lineage
- compatibility with local sandboxed agent systems

---

## 15. Practical First Milestone

The first milestone should implement:

1. `MessageRecord`
2. `TableFrame`
3. `SparseBlock`
4. `VirtualFileRegistry`
5. Position metadata
6. Gateway event metadata
7. Redundant checkpoint serialization

That is enough to begin solving the first benchmark tasks in a systematic way.

Operationally, meaningful state changes should still be able to surface through `MessageRecord` containers even if lower storage layers are more specialized.
