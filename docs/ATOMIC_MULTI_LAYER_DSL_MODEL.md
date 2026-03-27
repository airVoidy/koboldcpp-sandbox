# Atomic Multi-Layer DSL Model

## Purpose

This document defines the intended multi-layer shape of `Atomic DSL`.

The key idea is:

- `Atomic DSL` should likely be split into at least two DSL layers
- possibly three
- so the system can support both simple and powerful workflows
- while preserving transparency and deterministic expansion

This also fits the checkpoint-oriented design of Atomic.

## Core rule

One DSL composition should behave like one `Atomic function`.

That means:

- one semantic operation
- one stable contract
- one expandable implementation path
- one replayable checkpointed execution unit

So instead of writing only large flat scripts, Atomic should allow:

- compact semantic calls
- which expand into lower-level assembly
- which can expand further into raw runtime macros

## Why this matters

This gives the system both:

- simplicity at the top
- power and explicitness underneath

It also lets the solution base grow in a reusable way.

## Main layers

The most likely useful structure is:

1. `Semantic Atomic DSL`
2. `Assembly Atomic DSL`
3. optional `Runtime Macro Layer`

## 1. Semantic Atomic DSL

This is the user-facing or agent-facing layer.

It should expose compact semantic functions.

Examples:

- `generateInstructionAnswer(...)`
- `extractConstraints(...)`
- `verifyUniqueness(...)`
- `repairFromProbe(...)`

At this layer:

- intent matters more than wiring
- arguments are grouped semantically
- the user should not need to think about every low-level binding

## 2. Assembly Atomic DSL

This is the explicit batch assembly layer.

It expands semantic calls into:

- data bindings
- parameter bindings
- heuristic resolution
- static analysis
- worker call assembly
- output capture
- metadata emission

This layer is still DSL, but much closer to execution mechanics.

## 3. Runtime Macro Layer

This is optional but likely useful.

It is the low-level internal expansion layer.

It may include:

- worker payload construction
- raw endpoint call blocks
- low-level message writes
- event emission
- metadata attachment
- trigger/listener hooks

This layer is usually not what ordinary users should write directly.

But it should still be inspectable.

## Expansion rule

Any high-level Atomic function should have a deterministic expansion path downward.

That means:

- semantic call
- expands into assembly batch
- expands into lower runtime actions

This prevents hidden magic.

## Checkpoint rule

Because Atomic is checkpoint-oriented, every layer should be compatible with checkpoint splitting.

This means:

- semantic functions should be splittable into checkpoint-friendly substeps
- assembly batches should expose entry/exit checkpoints
- runtime macros should be linkable to checkpoint and gateway events

So the layering supports both:

- abstraction
- explicit replay

## High-level function idea

A semantic function may look like:

```text
generateInstructionAnswer(
  datalink,
  [prompt.question, prompt.params, prompt.context]
)
```

At this layer, the function contract is:

- read input from semantic refs
- generate one answer
- write raw answer to the provided `datalink`

Everything else is standardized expansion.

## What standardized expansion should provide

The lower layers should automatically provide:

- prompt assembly
- parameter resolution
- heuristic profile resolution
- static validation
- worker call construction
- output capture
- gateway event creation
- checkpoint hooks
- metadata attachment
- listener/trigger compatibility

So the semantic function stays compact while the runtime remains explicit.

## Datalink rule

The output target should be explicit even at the semantic layer.

This is why `datalink` is important.

The semantic call should know:

- where to read from
- where to write to

That keeps even high-level functions grounded in the message system.

## Layered example

### Semantic layer

```text
generateInstructionAnswer(
  @msg.task_a_001.generated.draft_4,
  [@msg.task_a_001.text, parameters.default_generate, context.empty]
)
```

### Assembly layer

Expands roughly into:

```text
BATCH generate_instruction_answer

DATA
  input.text = @msg.task_a_001.text
  parameters.temperature = 0.6
  parameters.max_tokens = 2048
  parameters.think = false
  context.main = ""
  target.link = @msg.task_a_001.generated.draft_4
  heuristics.profile = default_generate

LOGIC
  assemble_generate_input()
  static_check_generate_input()
  run_worker_call(worker:generator)
  capture_worker_output()
```

### Runtime macro layer

Expands further into:

- resolve source message text
- resolve default params
- build `WorkerCallSpec`
- call endpoint
- write raw answer to datalink
- emit `GatewayEvent`
- attach checkpoint metadata

## Why this is good for simple tasks

For simple tasks, the user can stay at semantic layer and call compact functions.

They still get:

- replayability
- message-based outputs
- standardized metadata

without writing low-level assembly by hand.

## Why this is good for powerful tasks

For more advanced work, the user can:

- inspect the assembly layer
- patch the assembly layer
- inspect runtime macro expansion
- override default heuristics
- replace parts of the logic

So the system remains powerful instead of becoming a black box.

## Checkpoint decomposition

Since Atomic tries to split work into checkpoints where possible,
the multi-layer model helps naturally:

- one semantic function
- many checkpointable assembly steps

Examples:

- assemble input
- validate
- call worker
- capture result
- verify
- repair

Each can become its own checkpoint if needed.

## Base of solutions

This model is also important for growing the solution base.

Without layers, the system tends to accumulate:

- flat scripts
- hidden prompt hardcodes
- duplicated logic

With layers, the system can accumulate:

- semantic functions
- reusable assembly templates
- reusable runtime macros
- reusable heuristic profiles

This is much healthier.

## Semantic groups at the upper layer

The upper layers should use grouped semantic inputs such as:

- `parameters`
- `instruction`
- `context`
- `target`
- `heuristics`

This keeps the surface intuitive.

## Transparency rule

The user or agent should always be able to:

1. call a compact semantic function
2. inspect the lower assembly expansion
3. inspect the lower runtime behavior

This is a core Atomic value.

## Minimal invariant set

The multi-layer DSL model should preserve:

1. one composition behaves like one Atomic function
2. high-level calls are expandable downward
3. message-based boundaries remain explicit
4. checkpoints remain compatible at every layer
5. output targets stay explicit
6. hidden hardcode is reduced

## Short summary

The intended future model is:

- top layer: compact semantic Atomic functions
- middle layer: explicit assembly batches
- low layer: raw runtime macros and worker calls

This gives Atomic a path to support:

- easy simple usage
- deep inspectability
- checkpoint-heavy execution
- a growing reusable base of solutions
