# Atomic Batch Model v0.1

## Purpose

This document fixes one core architectural stance:

`Atomic DSL` should be treated primarily as a language for `Atomic Batches`.

It is not just a free-form command script layer.
It is a batch-oriented, replayable, message-to-message execution model.

## Core rule

An `Atomic Batch` takes:

- formatted `Message` input

and produces:

- formatted `Message` output

with replay capability.

This should remain true even when the batch internally uses:

- local transforms
- matrix projections
- gateway calls
- probes
- repair loops
- revision checkpoints

## Why this matters

This keeps Atomic aligned with the main system model:

- `L1` is message-based
- metadata is formalized
- execution remains transparent
- replay remains possible
- hardcoded one-off logic is reduced

## Main idea

Any meaningful Atomic sequence should, where practical, be decomposable into batches.

So instead of thinking:

- one giant DSL script

the preferred model is:

- one or more bounded `Atomic Batches`
- each with explicit input
- explicit logic
- explicit output
- explicit replay surface

## Batch contract

Each batch should have:

1. input message contract
2. separated data payload
3. separated task logic
4. output message contract
5. replay metadata

## Required batch properties

An `Atomic Batch` should ideally be:

- serializable
- replayable
- inspectable
- composable
- data/logic separated
- message-based at the boundary

## Message boundary rule

The batch boundary is message-based.

That means:

- batch input should be representable as message containers
- batch output should be representable as message containers
- internal artifacts may be richer
- but the stable boundary remains message-in / message-out

## Separation rule

Inside a batch, keep these explicitly separate:

1. `DATA`
2. `Atomic Task Logic`

This is important.

The batch must not collapse:

- concrete task data
- reusable execution logic

into one inseparable hardcoded blob.

## Data section

`DATA` means:

- input messages
- referenced blocks
- prompt text payloads
- grammar payloads
- config values
- tables
- refs
- runtime bindings

This section should contain task-specific content and inputs.

## Logic section

`Atomic Task Logic` means:

- transforms
- worker calls
- routing
- probes
- checkpoint behavior
- repair behavior
- output binding behavior

This section should contain reusable operational logic.

## Why data and logic must be separate

This prevents:

- hidden hardcoded prompts
- task-specific constants leaking into reusable logic
- copy-paste route growth
- brittle one-off pipelines

And it enables:

- reusing the same logic on different tasks
- growing a base of solutions over time
- comparing route behavior cleanly
- replaying old logic with new data

## Canonical batch shape

Suggested canonical shape:

```json
{
  "batch_id": "batch_task_a_generate_01",
  "kind": "atomic_batch",
  "input_message_refs": ["msg_task_a_001"],
  "data": {
    "task_text_ref": "msg_task_a_001",
    "config_refs": ["extract_constraints_instruction"],
    "grammar_refs": [],
    "bindings": {
      "task_text": "$message.msg_task_a_001.text"
    }
  },
  "logic": {
    "dsl": [
      "@draft4 = generate($factory.task_a_direct_4, worker:generator, input:@task)"
    ]
  },
  "output": {
    "target_message_ref": "msg_task_a_001",
    "target_slot": "generated.draft_4"
  },
  "replay": {
    "checkpoint_from": "ckp_task_a_prompt_01",
    "checkpoint_to": "ckp_task_a_draft_02"
  }
}
```

## DSL serialization rule

An `Atomic Batch` should be serializable into DSL convention.

But the serialization should preserve the distinction:

- `DATA` separately
- `Atomic Task Logic` separately

This is critical.

## Suggested serialization shape

One useful shape is:

```text
BATCH
name: task_a_generate_01

DATA
$task_text = @msg.task_a_001.text
$factory = task_a_direct_4
$worker = generator

LOGIC
@draft4 = generate($factory, worker:$worker, input:$task_text)

OUTPUT
-> @msg.task_a_001.generated.draft_4
```

The exact syntax can vary later.
The important rule is the separation.

## Replay rule

Each batch should be replayable as a bounded unit.

Replay should know:

- input message refs
- data payload refs
- logic version
- worker call refs
- output target
- checkpoint links

This makes batches a natural unit for:

- debugging
- route comparison
- benchmark tracking
- repair loops

## Relation to worker calls

Inside a batch, worker calls should appear as:

- explicit `WorkerCallSpec` instances
- or concise DSL that compiles into them

So the batch is the higher bounded execution unit.
The worker call is the lower gateway unit.

## Relation to prompt factories

Prompt factories should feed data into batches, not disappear inside logic.

That means:

- prompt-factory refs belong in batch data/config
- compiled prompt artifacts may be emitted during batch execution
- but reusable batch logic should not hardcode prompt bodies

## Relation to checkpoints

A batch should usually have:

- clear checkpoint entry
- clear checkpoint exit

This makes it easy to:

- replay one batch
- replace one batch with another
- compare route alternatives

## Relation to revision graph

Batches are good candidates for durable revision-visible units.

A batch run may produce:

- input snapshot
- worker call event
- output message
- checkpoint
- revision commit

## Route decomposition rule

Large tasks should be decomposable into multiple batches.

For example:

1. extract constraints
2. generate candidate artifact
3. split into blocks
4. verify constraints
5. repair if needed

Each of these may become its own batch.

## Task A example

For the demoness benchmark, the first simple path is:

### Batch 1

- input: task message
- data: task text
- logic: one generator call
- output: one 4-block draft message

### Batch 2

- input: 4-block draft message
- data: block text
- logic: split + parse
- output: parsed matrix message / sidecar

### Batch 3

- input: parsed matrix
- data: extracted properties
- logic: uniqueness probes
- output: verification message

This decomposition is already better than one monolithic hidden pipeline.

## Hardcode avoidance rule

No task-specific hardcoded content should be buried in reusable batch logic unless explicitly declared as batch data.

This is one of the main reasons for the batch model.

The solution base should grow through:

- reusable logic
- reusable factories
- reusable schemas
- reusable probes

not through accumulating hidden one-off prompt strings.

## Short form vs canonical form

Like worker calls, batches may have:

- short form for model generation
- canonical expanded form for runtime persistence

Short form is acceptable if it can be expanded without ambiguity.

## Minimal invariant set

The Atomic batch model should preserve:

1. message-in / message-out boundaries
2. replayability
3. data/logic separation
4. explicit output target
5. compatibility with worker call specs
6. compatibility with checkpoints and revision graph

## Short summary

The intended interpretation is:

- `Atomic DSL` is a DSL for `Atomic Batches`
- batches are bounded replayable execution units
- boundaries are message-based
- `DATA` and `Atomic Task Logic` are serialized separately

This is how Atomic avoids hardcoded route sprawl while growing a reusable base of solutions.
