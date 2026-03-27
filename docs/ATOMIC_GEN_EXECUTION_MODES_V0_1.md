# Atomic GEN Execution Modes v0.1

## Purpose

This document defines how `GEN` should support different execution modes without changing the DSL itself.

The goal is:

- keep one stable assembly opcode
- avoid unnecessary live worker calls
- support local testing and benchmarks
- support replay and deterministic debugging

## Core rule

`GEN` should remain one opcode in Assembly DSL.

But its runtime backend may vary.

That means:

- the DSL does not change
- only execution mode changes

## Main execution modes

The first useful modes are:

- `live`
- `fixture`
- `replay`
- `mock`

## `live`

This is the normal runtime mode.

Behavior:

- call the actual LLM worker
- wait for the real response
- store real output

Use it for:

- production runs
- benchmark generation
- final route execution

## `fixture`

This mode uses predefined local example outputs instead of a live worker call.

Behavior:

- resolve the input key
- select a stored example response
- return it as if `GEN` produced it

Use it for:

- local testing
- pipeline development
- example-driven validation
- downstream parser/checker testing

This is especially useful when you already have:

- a set of sample good outputs
- a set of known bad outputs
- benchmark fixtures

## `replay`

This mode reuses an earlier recorded raw response.

Behavior:

- load a previously stored response artifact
- return it as the current `GEN` output

Use it for:

- exact debugging
- route replay
- deterministic issue reproduction

This is useful when you want:

- same input
- same raw response
- same downstream behavior

without another model call.

## `mock`

This mode returns a direct configured fake result.

Behavior:

- skip worker call
- return configured text or object

Use it for:

- unit tests
- early prototyping
- failure injection
- minimal harness tests

## Why this should not change the DSL

If `GEN` syntax changes per mode, the pipeline becomes harder to reason about.

It is better to keep:

- one opcode
- one graph shape
- one route structure

and swap only the execution backend.

## Suggested runtime control

Execution mode should be chosen via runtime config or state, not by changing source DSL.

Examples:

- config-driven
- per-run setting
- per-worker setting
- per-test harness setting

For example:

- `gen_mode = live`
- `gen_mode = fixture`
- `gen_mode = replay`
- `gen_mode = mock`

## Suggested fixture sources

Fixture mode may source data from:

- local JSON fixtures
- message containers
- benchmark datasets
- recorded example corpora

This fits well with the message-based architecture.

## Suggested replay sources

Replay mode may source data from:

- prior checkpoint carriers
- revision graph artifacts
- stored raw worker responses
- golden benchmark traces

## Suggested mock sources

Mock mode may source data from:

- inline configured text
- inline configured response object
- synthetic error case
- synthetic timeout case

## `GEN` output contract stays the same

Regardless of execution mode, the output contract should stay the same.

That means downstream steps should still receive:

- raw response or equivalent raw payload
- extracted raw text
- normal response bindings

So downstream logic does not need to know how the result was produced.

## Example

The same assembly line:

```asm
GEN  @generate.call.raw, @task.input.text, worker:generator, temp:0.2, max:256
```

may behave differently by mode:

- `live` -> call local worker
- `fixture` -> load a stored sample answer
- `replay` -> load a recorded raw response
- `mock` -> return configured fake output

The instruction stays the same.

## Why this is powerful

This gives:

- faster development
- less wasted generation
- local deterministic testing
- easier benchmark harnesses
- same pipeline under all modes

It also means you can test the whole downstream chain:

- parse
- split
- verify
- repair logic

without calling the model each time.

## Relation to Task A

Task A is a strong fit for this approach.

You can prepare fixture sets like:

- valid 4-block outputs
- duplicated-eye-color outputs
- duplicated-hair-color outputs
- broken-style outputs
- malformed block outputs

Then run downstream stages locally against them.

## Short summary

`GEN` should support multiple execution modes:

- `live`
- `fixture`
- `replay`
- `mock`

while keeping:

- the same DSL
- the same assembly
- the same downstream output contract

Only the backend source of the response changes.
