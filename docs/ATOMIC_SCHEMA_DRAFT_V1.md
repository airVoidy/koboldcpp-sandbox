# Atomic Schema Draft V1

## Purpose

This draft defines the next canonical schema layer for Atomic.

It is shaped by three hard project constraints:

1. all data, including intermediate data, must remain visible as forum-like threads or card/chat objects
2. worker interaction must go through the same visible data system
3. the client must stay thin

This means hidden runtime state is not allowed as the primary representation.
Low-level stores may exist underneath, but they must link back to explicit `data_origin`.

## Core rule: no orphan data

Every meaningful artifact must be linked to a visible origin object.

Allowed visible origins:

- forum thread
- forum post
- card
- chat
- chat message
- attached block inside a card/message

Low-level artifacts may exist in:

- vector index
- sqlite tables
- sidecar files
- cache layers
- benchmark tables

But each such artifact must carry a `data_origin_ref`.

## Architecture stance

Atomic should be read as a stack:

- visible carrier layer
- sidecar metadata layer
- local transform/runtime layer
- gateway layer
- optional retrieval/index layer

The visible carrier layer is the human-auditable source of truth.

## Canonical object families

The minimum object families are:

1. `DataOrigin`
2. `CarrierBlock`
3. `Checkpoint`
4. `GatewayEvent`
5. `SidecarMeta`
6. `MatrixFrame`
7. `TextSpan`
8. `ProbeResult`
9. `RouteRecord`

## 1. DataOrigin

Represents the visible user-facing object that owns the data.

```json
{
  "origin_id": "msg_2026_03_27_0012",
  "origin_kind": "chat_message",
  "container_ref": "chat_session_main",
  "author_ref": "user_local",
  "created_at": "2026-03-27T18:10:00+03:00",
  "title": "Task A draft",
  "visibility": "local_private",
  "path_hint": "/threads/main/chat/12"
}
```

Rules:

- `origin_kind` must point to a visible carrier object
- this is the audit anchor for derived artifacts
- derived objects may point to the same origin or to a child block inside it

## 2. CarrierBlock

Represents a marked block inside a visible carrier.

Use this for:

- text sections
- table sections
- attached lists
- DSL snippets
- benchmark blocks

```json
{
  "block_id": "blk_0007",
  "data_origin_ref": "msg_2026_03_27_0012",
  "carrier_kind": "chat_message",
  "block_kind": "text_section",
  "label": "demoness_block_2",
  "char_start": 245,
  "char_end": 481,
  "char_len": 236,
  "token_start": null,
  "token_end": null,
  "format": "markdown"
}
```

Rules:

- `CarrierBlock` is the preferred anchor for partial text addressing
- blocks may overlap only if explicitly marked as alternate views
- blocks may also point to table or list regions

## 3. Checkpoint

Represents a durable, replayable runtime state boundary.

```json
{
  "checkpoint_id": "ckp_task_a_parse_03",
  "data_origin_ref": "msg_2026_03_27_0012",
  "carrier_block_refs": ["blk_0001", "blk_0002"],
  "checkpoint_kind": "parsed_structure",
  "stage": "parse_blocks",
  "lineage_ref": "lin_task_a_run_001",
  "parent_checkpoint_refs": ["ckp_task_a_raw_01"],
  "artifact_refs": ["mx_demoness_blocks_v1", "meta_parse_03"],
  "created_at": "2026-03-27T18:11:23+03:00",
  "status": "accepted"
}
```

Rules:

- checkpoints must be explicit
- checkpoints should be serializable in more than one form when practical
- checkpoints are the unit of repair/replay
- `continue` should typically create a new checkpoint, not mutate history invisibly

## 4. GatewayEvent

Represents one crossing into a worker endpoint.

```json
{
  "event_id": "gwe_0042",
  "gen_id": "gen_local_0042",
  "data_origin_ref": "msg_2026_03_27_0012",
  "lineage_ref": "lin_task_a_run_001",
  "worker_role": "generator",
  "endpoint_ref": "worker_local_5001",
  "transform_type": "generate_4_demoness_blocks",
  "checkpoint_from": "ckp_task_a_prompt_01",
  "checkpoint_to": "ckp_task_a_draft_02",
  "input_refs": ["msg_2026_03_27_0012", "blk_prompt_01"],
  "output_refs": ["msg_2026_03_27_0013", "blk_draft_4x"],
  "latency_ms": 842,
  "accepted": true,
  "fingerprint_ref": "fp_0042",
  "embedding_status": "deferred"
}
```

Rules:

- every worker interaction creates a `GatewayEvent`
- worker output must return into visible carriers or visible child blocks
- no gateway result should exist only in hidden temp memory

## 5. SidecarMeta

Represents machine-friendly metadata attached to a visible origin or block.

```json
{
  "meta_id": "meta_parse_03",
  "data_origin_ref": "msg_2026_03_27_0012",
  "carrier_block_ref": "blk_0002",
  "meta_kind": "parse_annotation",
  "transform_type": "block_split",
  "lineage_ref": "lin_task_a_run_001",
  "source_ref": "ckp_task_a_draft_02",
  "target_ref": "ckp_task_a_parse_03",
  "payload_ref": "mx_demoness_blocks_v1",
  "created_at": "2026-03-27T18:11:24+03:00"
}
```

Rules:

- sidecar metadata is allowed to be denser than the visible carrier
- it must still be traceable to a visible origin
- sidecar metadata is not the source of truth by itself

## 6. MatrixFrame

Represents the canonical working table/matrix form.

```json
{
  "matrix_id": "mx_demoness_blocks_v1",
  "data_origin_ref": "msg_2026_03_27_0012",
  "frame_kind": "table",
  "shape": [4, 6],
  "columns": ["name", "eyes", "hair", "pose", "features", "style"],
  "row_origin_refs": ["blk_0002", "blk_0003", "blk_0004", "blk_0005"],
  "storage_ref": "sidecar://tables/mx_demoness_blocks_v1.json"
}
```

Rules:

- tables are the default working format
- lists should be liftable into matrix form when useful
- matrix rows and cells should remain linkable to visible origins

## 7. TextSpan

Represents positional text metadata for precise mapping.

```json
{
  "span_id": "span_0144",
  "data_origin_ref": "msg_2026_03_27_0013",
  "carrier_block_ref": "blk_draft_4x",
  "span_kind": "entity_value",
  "label": "hair_color",
  "char_start": 312,
  "char_end": 323,
  "char_len": 11,
  "token_start": null,
  "token_end": null,
  "value_text": "silver hair"
}
```

Rules:

- positional metadata should be redundant on purpose
- `char_start`, `char_end`, and `char_len` are preferred minimums
- token offsets are optional, not required

## 8. ProbeResult

Represents a central runtime probe output.

```json
{
  "probe_id": "probe_cov_08",
  "data_origin_ref": "msg_2026_03_27_0013",
  "lineage_ref": "lin_task_a_run_001",
  "probe_kind": "coverage",
  "target_ref": "ckp_task_a_parse_03",
  "input_refs": ["mx_demoness_blocks_v1"],
  "result": "warning",
  "score": 0.75,
  "summary": "Hair values are unique, pose values partially overlap.",
  "evidence_refs": ["row_2", "row_4"],
  "created_at": "2026-03-27T18:12:10+03:00"
}
```

Rules:

- probe logic belongs to runtime, not to ad hoc worker behavior
- probe outputs should be first-class artifacts
- probes may trigger repair loops by creating new checkpoints

## 9. RouteRecord

Represents the higher-level path through a pipeline/run.

```json
{
  "route_id": "route_task_a_001",
  "data_origin_ref": "msg_2026_03_27_0012",
  "lineage_ref": "lin_task_a_run_001",
  "dsl_family": "atomic",
  "dsl_ref": "blk_atomic_recipe_01",
  "checkpoint_refs": [
    "ckp_task_a_prompt_01",
    "ckp_task_a_draft_02",
    "ckp_task_a_parse_03",
    "ckp_task_a_verify_04"
  ],
  "gateway_event_refs": ["gwe_0042", "gwe_0043"],
  "probe_refs": ["probe_cov_08", "probe_contra_02"],
  "final_status": "accepted"
}
```

Rules:

- route records should stay simple and auditable
- the route is a visible replay spine, not hidden scheduler state

## Worker interaction rule

Workers must interact through the same visible system as users.

That means worker I/O should be represented as:

- messages
- cards
- child blocks within them
- sidecar metadata attached to those objects

Not as private opaque buffers with no user-auditable anchor.

## DSL position in the stack

Atomic is one DSL family among several.

Its role is to bridge:

- human-readable NLP-facing structures
- explicit visible carriers
- deterministic local transforms
- worker gateway calls
- machine-friendly sidecar schemas

So the DSL family is a translation membrane between language and code, not a hidden backend language.

## Prompt factory boundary

Prompt factories should be modeled as a separate layer from Atomic runtime orchestration.

Their job is to construct model-facing payloads with explicit slots such as:

- `context`
- `instruction`
- `think`
- `format`
- optional `examples`
- optional `policy`

Atomic runtime objects may reference prompt-factory outputs, but should not blur:

- prompt assembly
- visible data mutation
- checkpointing
- gateway event tracking

This separation matters because the DSL should remain easy for models to generate safely, even if that means a somewhat more redundant command surface.

## Thin client consequences

Because the client is thin:

- heavy indexing should remain local service/runtime side
- rendering should consume visible carriers plus summarized sidecar metadata
- the client should not need hidden runtime reconstruction logic to explain state
- replay and audit should be derivable from visible objects and linked sidecars

## Canonical invariants

These invariants should hold across the system:

1. every durable artifact has `data_origin_ref`
2. every worker crossing has `GatewayEvent`
3. every replay boundary has `Checkpoint`
4. every machine-only structure links back to visible carrier objects
5. source of truth remains visible user data plus sidecar metadata
6. retrieval/index layers are replaceable and non-canonical

## Immediate implementation order

Recommended order:

1. `DataOrigin` + `CarrierBlock`
2. `Checkpoint`
3. `GatewayEvent`
4. `SidecarMeta`
5. `MatrixFrame` + `TextSpan`
6. `ProbeResult`
7. `RouteRecord`

## Task A mapping

For `Task A`, the canonical chain should be:

1. prompt message as `DataOrigin`
2. 4-block draft as visible output message
3. each demoness block as `CarrierBlock`
4. parsed uniqueness table as `MatrixFrame`
5. parse/verify boundaries as `Checkpoint`
6. generator/analyzer calls as `GatewayEvent`
7. uniqueness and contradiction checks as `ProbeResult`

This gives a full benchmark path without hidden state.
