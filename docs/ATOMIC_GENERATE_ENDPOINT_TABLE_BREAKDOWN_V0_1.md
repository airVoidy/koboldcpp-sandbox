# Atomic Generate Endpoint Table Breakdown v0.1

## Purpose

This document shows how to take the current `generate` endpoint payload and treat it as an Atomic table object without calling the worker.

The goal is:

- inspect the request shape
- project it into a dense table checkpoint
- edit it safely
- resolve it back into endpoint JSON

## Current repo contract

In the current codebase, the native generate endpoint is wrapped by `NativeGenerateRequest` with these fields:

- `prompt`
- `temperature`
- `max_length`
- `model`

Endpoint:

- `/api/v1/generate`

This is intentionally smaller than the larger raw Kobold payload examples.

## Table object mapping

The current request shape maps to:

- schema: `native_generate_request`
- object path: `generate.request`

Example payload:

```json
{
  "prompt": "Write 4 demoness descriptions.",
  "temperature": 0.35,
  "max_length": 256,
  "model": "local-model"
}
```

Table projection:

| field | group | type | value | aliases | path |
|---|---|---|---|---|---|
| prompt | content | str | "Write 4 demoness descriptions." | [generate.prompt, request.prompt] | generate.request.prompt |
| temperature | sampling | float | 0.35 | [generate.temperature, request.temperature, gen.temp] | generate.request.temperature |
| max_length | limits | int | 256 | [generate.max_length, request.max_length] | generate.request.max_length |
| model | routing | str | "local-model" | [generate.model, request.model] | generate.request.model |

## Why this is useful

This already gives a clean non-LLM batch step:

1. read request payload
2. normalize into table object
3. inspect or patch table rows
4. resolve back into endpoint JSON

That means request assembly becomes its own checkpoint before any worker call.

## Example envelope

```json
{
  "table_data": {
    "schema_name": "native_generate_request",
    "object_path": "generate.request",
    "rows": [
      {
        "field": "prompt",
        "group": "content",
        "type": "str",
        "value": "Write 4 demoness descriptions.",
        "default": "",
        "aliases": ["generate.prompt", "request.prompt"],
        "path": "generate.request.prompt",
        "required": true,
        "description": ""
      }
    ]
  },
  "meta_data": {
    "endpoint": "/api/v1/generate"
  }
}
```

## Processing flow without worker

The first useful pass is:

1. take raw request JSON
2. build `NativeGenerateRequestSchema`
3. export `table_data`
4. inspect rows or patch aliases
5. export resolved JSON again

This already tests:

- aliasing
- defaults
- required fields
- path addressing
- table checkpoint readability

## Relation to larger generate payloads

The larger Kobold-style payload example with fields like:

- `max_context_length`
- `rep_pen`
- `rep_pen_range`
- `top_k`
- `top_p`
- `typical`

should be treated as a separate expanded schema, not mixed into the current repo contract.

So the layering is:

1. actual repo contract: `native_generate_request`
2. expanded future contract: `kobold_generate`

That keeps the current implementation honest while still leaving room for a richer worker-facing object later.

## Short summary

The generate endpoint can already be treated as a table-driven Atomic object.

Even without calling the worker, this gives:

- a useful checkpoint
- explicit data inspection
- safe patching
- deterministic resolve back to JSON
