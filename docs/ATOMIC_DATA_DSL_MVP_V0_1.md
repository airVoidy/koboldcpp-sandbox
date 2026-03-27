# Atomic Data DSL MVP v0.1

## Purpose

This document defines the smallest useful subset of the Atomic Data DSL.

The goal is not completeness.

The goal is to support one clear path:

1. read raw input
2. build a data object
3. project it into a table checkpoint
4. patch it if needed
5. resolve it back into JSON

## MVP rule

The MVP Data DSL should stay:

- explicit
- tiny
- AST-like
- replayable

## Minimal node set

The first usable node set is:

- `object`
- `raw_text`
- `raw_json`
- `table`
- `meta`
- `patch`
- `resolved_json`

This is enough for the first real workflows.

## Minimal object shape

Every object may be represented as:

```json
{
  "node": "object",
  "name": "...",
  "children": []
}
```

## Minimal workflow pattern

The main pattern is:

```text
raw input
-> object
-> table checkpoint
-> patch nodes
-> resolved json checkpoint
```

## Node meanings

### object

Defines a named data object.

Example:

```json
{
  "node": "object",
  "name": "generate.request",
  "children": []
}
```

### raw_text

Stores original text without changing it.

Example:

```json
{
  "node": "raw_text",
  "value": "написать 4 описания внешности демониц..."
}
```

### raw_json

Stores original JSON payload without changing it.

Example:

```json
{
  "node": "raw_json",
  "value": {
    "prompt": "Write 4 demoness descriptions.",
    "temperature": 0.35
  }
}
```

### table

Stores the working dense representation.

Example:

```json
{
  "node": "table",
  "value": {
    "rows": [
      {
        "field": "temperature",
        "type": "float",
        "value": 0.35,
        "path": "generate.request.temperature"
      }
    ]
  }
}
```

### meta

Stores refs and structured metadata.

Example:

```json
{
  "node": "meta",
  "value": {
    "message_ref": "msg_task_a_001",
    "schema_name": "native_generate_request"
  }
}
```

### patch

Describes one explicit change.

Example:

```json
{
  "node": "patch",
  "target": "generate.request.temperature",
  "value": 0.5,
  "meta": {
    "reason": "sampling_update"
  }
}
```

### resolved_json

Stores a resolved endpoint-compatible payload after table and patch steps.

Example:

```json
{
  "node": "resolved_json",
  "value": {
    "prompt": "Write 4 demoness descriptions.",
    "temperature": 0.5,
    "max_length": 256,
    "model": "local-model"
  }
}
```

## One full example

### Step 1: task input object

```json
{
  "node": "object",
  "name": "task.input",
  "children": [
    {
      "node": "raw_text",
      "value": "написать 4 описания внешности демониц в разных образах..."
    },
    {
      "node": "meta",
      "value": {
        "message_ref": "msg_task_a_001",
        "kind": "task_input"
      }
    }
  ]
}
```

### Step 2: generate request object

```json
{
  "node": "object",
  "name": "generate.request",
  "children": [
    {
      "node": "raw_json",
      "value": {
        "prompt": "написать 4 описания внешности демониц в разных образах...",
        "temperature": 0.35,
        "max_length": 256,
        "model": "local-model"
      }
    },
    {
      "node": "table",
      "value": {
        "rows": [
          {
            "field": "prompt",
            "type": "str",
            "value": "написать 4 описания внешности демониц в разных образах...",
            "path": "generate.request.prompt"
          },
          {
            "field": "temperature",
            "type": "float",
            "value": 0.35,
            "path": "generate.request.temperature"
          },
          {
            "field": "max_length",
            "type": "int",
            "value": 256,
            "path": "generate.request.max_length"
          },
          {
            "field": "model",
            "type": "str",
            "value": "local-model",
            "path": "generate.request.model"
          }
        ]
      }
    },
    {
      "node": "meta",
      "value": {
        "schema_name": "native_generate_request",
        "endpoint": "/api/v1/generate"
      }
    }
  ]
}
```

### Step 3: table checkpoint patch

```json
{
  "node": "patch",
  "target": "generate.request.temperature",
  "value": 0.5,
  "meta": {
    "reason": "task_a_sampling_adjustment"
  }
}
```

### Step 4: resolved JSON checkpoint

```json
{
  "node": "resolved_json",
  "value": {
    "prompt": "написать 4 описания внешности демониц в разных образах...",
    "temperature": 0.5,
    "max_length": 256,
    "model": "local-model"
  }
}
```

## Replay logic

Replay should be simple:

1. load object
2. load table
3. apply patch nodes in order
4. emit resolved JSON

No hidden runtime inference is needed for this layer.

## Why this is enough

This MVP already supports:

- raw text storage
- raw JSON storage
- table checkpoints
- safe explicit edits
- endpoint-ready payload reconstruction

That is enough to support the first `generate` preparation flow.

## Short summary

The smallest useful Atomic Data DSL is:

- `object`
- `raw_text`
- `raw_json`
- `table`
- `meta`
- `patch`
- `resolved_json`

And the first canonical path is:

- `task.input`
- `generate.request`
- `table checkpoint`
- `resolved_json_checkpoint`
