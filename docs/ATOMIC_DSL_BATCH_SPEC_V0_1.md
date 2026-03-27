# Atomic DSL Batch Spec v0.1

## Purpose

This is the starting draft spec for `Atomic DSL` under the batch-oriented model.

The main idea is:

- `Atomic DSL` is a DSL for `Atomic Batches`
- generation is always a worker endpoint call
- but assembling the input for that call is itself an important batch
- that assembly step should be inspectable and statically analyzable before any LLM call happens

## Core stance

`generate` is not the first step.

The first step is:

- collect input
- resolve refs
- apply heuristics
- fill defaults
- bind outputs
- statically analyze the batch

Only after that should the system call the worker endpoint.

So for Atomic, `input assembly` is also a first-class batch.

## High-level shape

A typical generation route should look like:

1. input batch
2. static analysis batch
3. worker call batch
4. output capture batch

This is more useful than treating everything as one opaque `generate(...)`.

## Message-based rule

Every batch remains message-based at the boundary.

That means:

- input comes from message/container refs
- output lands in message/container refs
- internal projections may use matrices, spans, sidecars, etc.

## Separation rule

Each batch should separate:

- `DATA`
- `LOGIC`

And inside `DATA`, the top-level semantic groups should also be explicit.

## Top-level semantic groups

At the user-facing or author-facing level, the DSL should expose grouped semantic sections such as:

- `Parameters`
- `Instruction`
- `Context`
- `Target`
- `Heuristics`
- `Bindings`

These are easier to understand than flat low-level command soup.

## Main batch kinds

Suggested initial batch kinds:

1. `input_assembly`
2. `static_analysis`
3. `worker_call`
4. `output_capture`
5. `transform`
6. `probe`
7. `repair`

## 1. Input Assembly Batch

This is the first-class batch that prepares a worker call.

It does not require an LLM.

Typical responsibilities:

- resolve source message refs
- resolve block refs
- load defaults
- choose heuristic profile
- expand context
- render instruction
- collect parameters
- compute output target
- build canonical worker call object

This stage is diverse and tricky enough that it should not be hidden.

## 2. Static Analysis Batch

Before sending anything to the generator, Atomic should try to statically validate the assembled batch.

Typical checks:

- required inputs exist
- target refs exist or are creatable
- parameter values are valid
- grammar refs resolve
- no forbidden hardcoded content in logic
- output target is explicit
- heuristics are coherent

This gives an early failure point before expensive model calls.

## 3. Worker Call Batch

This batch performs the actual endpoint call.

Its core normalized object is:

- `WorkerCallSpec`

This stage should preserve:

- compiled request payload
- parameters
- heuristics
- endpoint ref
- response target

## 4. Output Capture Batch

After worker response:

- create output message/container
- attach sidecar metadata
- emit gateway event
- link checkpoint/revision refs

This should also be explicit.

## Why this structure is useful

It gives:

- more transparent execution
- preflight validation
- replayability
- cleaner route composition
- less hidden hardcode

## Draft DSL shape

The DSL should support a grouped form that is intuitive for users and agents.

One possible draft shape:

```text
BATCH generate_task_a

DATA
  input.message = @msg.task_a_001
  input.text = @msg.task_a_001.text

  parameters.max_tokens = 2048
  parameters.temperature = 0.6
  parameters.think = false

  context.main = ""
  instruction.main = @msg.task_a_001.text

  target.message = @msg.task_a_001
  target.slot = generated.draft_4

  heuristics.profile = default_generate
  heuristics.continue_on_length = true
  heuristics.max_continue = 2

LOGIC
  assemble_generate_input()
  static_check_generate_input()
  run_worker_call(worker:generator)
  capture_worker_output()
```

This is only a draft shape.
The key point is the grouping.

## Parameters group

`Parameters` should collect execution controls in one place.

Examples:

- `parameters.max_tokens`
- `parameters.temperature`
- `parameters.think`
- `parameters.top_p`
- `parameters.seed`
- `parameters.stop`
- `parameters.grammar_ref`

These should be easy to inspect and override.

## Instruction group

`Instruction` should hold the main task-bearing text or structured instruction body.

This is where the semantic request lives.

Examples:

- direct task text
- task text plus rewritten constraint framing
- assembled prompt body from constraint groups

## Context group

`Context` should hold auxiliary text or structured payloads that support the instruction.

Examples:

- retrieved notes
- prior accepted checkpoints
- known constraints
- previous output being repaired

## Target group

`Target` should explicitly say where the result goes.

Examples:

- `target.message`
- `target.slot`
- `target.block`
- `target.append_mode`

This prevents hidden write destinations.

## Heuristics group

`Heuristics` are wrapper-side decisions, not direct task data.

Examples:

- heuristic profile
- continue-on-length
- prompt mode
- context injection policy
- repair-loop eligibility

These should be explicit and statically analyzable.

## Bindings group

`Bindings` connect semantic groups to concrete message/container refs.

Examples:

- `bindings.input_text = @msg.task_a_001.text`
- `bindings.output_slot = @msg.task_a_001.generated.draft_4`
- `bindings.grammar = @msg.grammar_binary.text`

This keeps data refs explicit without mixing them into reusable logic.

## Static analysis targets

The DSL runtime should be able to analyze at least:

- missing inputs
- unresolved refs
- missing targets
- unsupported parameter combinations
- invalid grammar refs
- likely hardcoded logic leakage
- empty instruction with non-empty worker call

## Default parameter collection

If values are not explicitly set, the assembly batch should collect defaults from:

1. batch-local data
2. task-level config/message refs
3. heuristic profile
4. system defaults

But those resolved defaults should become visible in the assembled batch.

That is important.

The worker should receive resolved values, not mysterious implicit state.

## Endpoint call as lower layer

The worker endpoint remains the lower fixed layer.

Atomic should wrap it, not redefine it.

So the flow is:

- semantic groups
- batch assembly
- normalized worker call
- endpoint request

## Task A example

For the demoness task, the first batch should look conceptually like:

### Input

- source message text = user task

### Parameters

- temperature = 0.6
- max_tokens = 2048
- think = false

### Instruction

- direct task request text

### Context

- empty for the first baseline route

### Target

- output goes to `generated.draft_4`

### Heuristics

- prompt_mode = auto
- continue_on_length = true
- max_continue = 2

### Logic

- assemble
- static check
- call generator
- capture output

## Intended layering

The draft DSL should support at least three practical layers:

### Layer 1

Semantic grouped batch declaration.

This is the intuitive user-facing or model-facing form.

### Layer 2

Expanded normalized batch form.

This is the fully explicit runtime form after defaults and bindings resolve.

### Layer 3

Concrete worker call and output capture actions.

This is the execution layer.

## Why this stays flexible

This approach stays flexible because:

- different heuristic profiles can be swapped
- different workers can be targeted
- different prompt factories can feed instruction/context
- different output targets can be chosen

without changing the whole logic model.

## Why this stays intuitive

This approach stays intuitive because:

- users think in terms of instruction, context, parameters, output
- not in terms of raw payload assembly internals

So the DSL should let them work from these semantic groups first.

## Minimal invariant set

The starting Atomic DSL should preserve:

1. batch-oriented execution
2. message-based boundaries
3. `DATA` separate from `LOGIC`
4. `input assembly` as first-class batch work
5. static analysis before LLM call
6. resolved defaults visible before execution
7. endpoint call as lower wrapped layer

## Short summary

The starting Atomic DSL should be understood as:

- a grouped batch DSL
- where `generate` is not the start, but one step
- and where assembling and checking the worker input is itself a replayable batch

This gives a flexible but inspectable foundation for growing Atomic routes.
