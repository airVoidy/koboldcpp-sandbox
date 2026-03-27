# Atomic Worker Call Spec v0.1

## Purpose

This document defines the Atomic-side wrapper contract around a worker endpoint call.

The worker endpoint is treated as fixed or mostly fixed.
So Atomic should build upward from that contract rather than inventing a higher-level abstraction first.

The intended layering is:

1. worker endpoint spec
2. Atomic worker call spec
3. generate wrapper
4. prompt factory
5. message bindings

## Design rule

`generate` should not be a magical primitive.

It should be a concise wrapper over a fully explicit worker call description.

That description should preserve:

- what went into the worker
- what parameters were used
- what heuristics were applied
- where the result should land
- what event/checkpoint links should be emitted

## Main object

The central object is:

- `WorkerCallSpec`

It is the Atomic-side normalized description of one worker call.

## Minimal example

```json
{
  "call_id": "wcall_0001",
  "worker_ref": "generator",
  "endpoint": "http://localhost:5001",
  "request": {
    "messages": [
      {
        "role": "user",
        "content": "Написать 4 описания внешности демониц..."
      }
    ],
    "temperature": 0.6,
    "max_tokens": 2048,
    "grammar": null,
    "stop": [],
    "continue_assistant_turn": false
  },
  "response_target": {
    "message_ref": "msg_task_a_001",
    "slot": "generated.draft_4"
  }
}
```

## 1. Heuristics

Heuristics are not the same as hard parameters.

They describe wrapper-side decisions about how to call the worker or how to continue around the worker.

Typical heuristics:

- prompt mode inference
- no-think prefill behavior
- continue-on-length behavior
- repair-loop eligibility
- auto-capture behavior
- context injection policy
- stop selection policy

Example:

```json
{
  "heuristics": {
    "prompt_mode": "auto",
    "inject_context": true,
    "continue_on_length": true,
    "max_continue": 4,
    "prefill_assistant": false,
    "repair_loop_allowed": false
  }
}
```

Rule:

- heuristics should be explicit if they materially affect behavior
- hidden heuristics should be avoided

## 2. Parameters

Parameters are the actual worker-facing or wrapper-driving execution controls.

Typical parameters:

- `temperature`
- `max_tokens`
- `grammar`
- `stop`
- `continue_assistant_turn`
- `capture`
- `coerce`
- `think`
- `top_p`
- `seed`

Not every worker supports all of them.
Atomic should keep the normalized shape anyway.

Example:

```json
{
  "params": {
    "temperature": 0.6,
    "max_tokens": 2048,
    "grammar": null,
    "stop": [],
    "capture": null,
    "coerce": null,
    "think": false
  }
}
```

Rule:

- if a value is materially in play, it should be serializable
- avoid silently relying on implicit defaults

## 3. Additional fields

These are not always strictly required for the worker call itself,
but are strongly useful for Atomic runtime transparency.

Useful additional fields:

- `source_message_ref`
- `source_block_refs`
- `factory_ref`
- `factory_revision_ref`
- `checkpoint_from`
- `checkpoint_to`
- `gateway_event_ref`
- `lineage_ref`
- `response_target`
- `probe_after`
- `revision_policy`
- `timeout_ms`
- `tags`

Example:

```json
{
  "source_message_ref": "msg_task_a_001",
  "source_block_refs": [],
  "factory_ref": "factory.generate.task_a.v1",
  "checkpoint_from": "ckp_task_a_prompt_01",
  "checkpoint_to": "ckp_task_a_draft_02",
  "lineage_ref": "lin_task_a_run_001",
  "tags": ["task_a", "generate", "baseline"]
}
```

Rule:

- these fields should be easy to omit in the shortest path
- but easy to preserve in any durable/replayable path

## 4. Necessary fields

The actual minimum necessary fields for a valid worker call are:

- `worker_ref`
- `endpoint`
- `request.messages`

And in most practical Atomic usage, also:

- `response_target`

Recommended minimum durable Atomic call:

- `call_id`
- `worker_ref`
- `endpoint`
- `request.messages`
- `params`
- `response_target`

## Worker endpoint view

The underlying endpoint usually only needs something like:

```json
{
  "messages": [...],
  "temperature": 0.6,
  "max_tokens": 2048,
  "grammar": null,
  "stop": []
}
```

Atomic should not confuse this low-level payload with the full runtime call object.

The runtime call object must also know:

- where it came from
- where it goes
- what wrapper heuristics were applied

## Normalized WorkerCallSpec

Suggested normalized shape:

```json
{
  "call_id": "wcall_0001",
  "worker_ref": "generator",
  "endpoint": "http://localhost:5001",
  "source_message_ref": "msg_task_a_001",
  "source_block_refs": [],
  "factory_ref": "factory.generate.task_a.v1",
  "request": {
    "messages": [
      {
        "role": "user",
        "content": "..."
      }
    ]
  },
  "params": {
    "temperature": 0.6,
    "max_tokens": 2048,
    "grammar": null,
    "stop": [],
    "capture": null,
    "coerce": null,
    "think": false
  },
  "heuristics": {
    "prompt_mode": "auto",
    "continue_on_length": true,
    "max_continue": 4,
    "inject_context": false
  },
  "response_target": {
    "message_ref": "msg_task_a_001",
    "slot": "generated.draft_4"
  },
  "checkpoint_from": "ckp_task_a_prompt_01",
  "checkpoint_to": "ckp_task_a_draft_02",
  "lineage_ref": "lin_task_a_run_001",
  "tags": ["task_a"]
}
```

## Response target

`response_target` should be explicit whenever possible.

This prevents the vague pattern:

- call worker
- get text back
- figure out later where to store it

Preferred target fields:

- `message_ref`
- `slot`

Optional:

- `block_ref`
- `append_mode`
- `checkpoint_ref`

## Relation to message system

The worker call spec should connect directly to the message system.

At minimum:

- source text comes from message/container refs
- compiled request may itself be preserved as a message/container
- output must land in a message/container

This keeps `L1` transparent.

## Relation to gateway events

Each durable worker call should produce or link to:

- `GatewayEvent`

The `WorkerCallSpec` is the call description.
The `GatewayEvent` is the runtime event record.

These are related but not identical.

## Relation to generate wrapper

`generate(...)` should be understood as shorthand for:

1. resolve source message text
2. resolve prompt factory output
3. build `WorkerCallSpec`
4. perform call
5. write output to `response_target`
6. emit `GatewayEvent`

This is why `WorkerCallSpec` comes first.

## Task A example

For the benchmark task:

Input message:

```text
написать 4 описания внешности демониц в разных образах ...
```

Atomic-side call:

```json
{
  "call_id": "wcall_task_a_01",
  "worker_ref": "generator",
  "endpoint": "http://localhost:5001",
  "source_message_ref": "msg_task_a_001",
  "factory_ref": "factory.generate.task_a.direct_4",
  "request": {
    "messages": [
      {
        "role": "user",
        "content": "Напиши 4 отдельных блока с описаниями внешности демониц..."
      }
    ]
  },
  "params": {
    "temperature": 0.6,
    "max_tokens": 2048,
    "grammar": null,
    "stop": [],
    "capture": null,
    "coerce": null,
    "think": false
  },
  "heuristics": {
    "prompt_mode": "auto",
    "continue_on_length": true,
    "max_continue": 2,
    "inject_context": false
  },
  "response_target": {
    "message_ref": "msg_task_a_001",
    "slot": "generated.draft_4"
  }
}
```

## Complexity check

The main risk is making this object too large for easy generation by models.

To keep it practical:

- keep top-level sections stable
- use predictable field names
- let empty sections be omitted in short form
- preserve a canonical expanded form for durable storage

That gives two views:

- short form for generation
- expanded form for runtime persistence

## Suggested short form

Example concise form:

```json
{
  "worker_ref": "generator",
  "messages": [{"role": "user", "content": "..."}],
  "params": {"temperature": 0.6, "max_tokens": 2048},
  "target": {"message_ref": "msg_task_a_001", "slot": "generated.draft_4"}
}
```

The runtime can expand this into canonical full form.

## Short summary

The right starting point for Atomic `generate` is:

- a fixed worker endpoint contract
- wrapped by an explicit `WorkerCallSpec`

That spec should clearly separate:

1. heuristics
2. parameters
3. additional fields
4. necessary fields

Then everything above it stays simpler and more transparent.
