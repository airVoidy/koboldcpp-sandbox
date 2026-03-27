# Task A Atomic Solutions Map

## Purpose

This document maps `Task A` into several Atomic solution routes.

Reference task:

```text
написать 4 описания внешности демониц в разных образах
[проверить, что разные образы, разный цвет глаз,
разный цвет волос, разные позы,
в описании должны быть элементы, по которым даже без указания расы понятно, что перед тобой демоница,
стиль: аниме, должен быть явно указан в описании]
```

The goal is to cover routes from:

- one prompt -> 4 blocks -> split -> verify

to:

- generate unique constraints first
- assemble a larger prompt from those constraints
- generate 4 blocks
- verify and repair

## Core benchmark contract

The final artifact should satisfy at minimum:

- 4 demoness appearance blocks
- different looks
- different eye colors
- different hair colors
- different poses
- each block contains demoness-signaling elements even without explicit race label
- anime style is explicitly stated in the description

## Constraint families

For `Task A`, the most useful explicit constraints are:

- block count = 4
- unique eye color per block
- unique hair color per block
- unique pose per block
- unique name per block
- each block must signal demoness traits
- each block must explicitly mention anime style

Optional stronger constraints:

- unique horn shape
- unique wing/tail emphasis
- unique emotional tone
- unique environment accent

## Canonical checkpoints

Recommended checkpoints:

1. raw task message
2. prompt factory output
3. generated 4-block artifact
4. split block table
5. extracted property matrix
6. verification/probe result
7. repaired or accepted final route

## Route A

## A1. Monolithic generation then local split

Shape:

- one prompt
- one generator call
- one 4-block text artifact
- local split
- local parse
- analyzer/verifier check

Best use:

- simplest baseline
- lowest orchestration complexity
- strongest first benchmark baseline

Main steps:

1. create task message
2. build direct prompt factory output
3. `generate` one text containing 4 blocks
4. split into 4 blocks
5. parse attributes into matrix
6. run uniqueness and demoness/anime probes
7. accept or repair

Atomic shape:

```pipeline
@task = $config.task_a_prompt
@draft4 = generate($factory.task_a_direct_4, worker:generator, input:@task)
@blocks = split_demoness_blocks(@draft4)
@matrix = parse_demoness_matrix(@blocks)
@probe = verify_task_a(@matrix)
```

Strengths:

- minimal route
- good benchmark baseline
- easy to compare workers

Weaknesses:

- uniqueness pressure is deferred until after generation
- more likely to need repair

## A2. Monolithic generation with immediate probe-repair loop

Shape:

- same as A1
- but `continue` is treated as repair loop, not open-ended continuation

Main steps:

1. generate 4 blocks
2. parse matrix
3. probe uniqueness and style constraints
4. if failed, create repair checkpoint
5. send targeted repair prompt
6. re-parse and re-probe

Atomic shape:

```pipeline
@draft4 = generate($factory.task_a_direct_4, worker:generator, input:@task)
@blocks = split_demoness_blocks(@draft4)
@matrix = parse_demoness_matrix(@blocks)
@probe = verify_task_a(@matrix)
@need_repair = probe_failed(@probe)

loop(while:@need_repair, max_iters:2) {
  @repair_prompt = build_repair_prompt(@draft4, @probe)
  @draft4 = generate(@repair_prompt, worker:generator)
  @blocks = split_demoness_blocks(@draft4)
  @matrix = parse_demoness_matrix(@blocks)
  @probe = verify_task_a(@matrix)
  @need_repair = probe_failed(@probe)
}
```

Best use:

- still simple
- more realistic fail-safe route

## Route B

## B1. Generate 4 blocks, then split into 4 block-specific prompts

Shape:

- one prompt -> 4 blocks
- split blocks
- derive one prompt per block
- verify each block independently
- verify global uniqueness across all 4

Best use:

- comparing block-local stability
- preparing image prompts later
- text-image alignment

Main steps:

1. generate 4-block artifact
2. split to block carriers
3. convert each block to a normalized one-block prompt/spec
4. run block-local verifier
5. run global uniqueness verifier

Core idea:

This route lets the system move from:

- large coherent generation

to:

- atomic block-level work units

without losing lineage.

## B2. Generate 4 answers independently from one higher-level task

Shape:

- first derive 4 unique property groups
- then generate 1 block from each
- assemble final 4-block artifact

This is already halfway toward constraint-first generation.

## Route C

## C1. Constraint-first generation

Shape:

- generate unique constraints first
- verify constraints first
- then assemble one larger prompt with those constraints embedded directly into instruction body
- generate 4 blocks
- verify result

This is one of the most important target routes.

Main steps:

1. derive 4 unique property groups
2. verify property-group uniqueness
3. render one assembled prompt:
   `собери задачу, в которой: ...`
4. inject generated constraints text directly into instruction body
5. generate 4 demoness blocks
6. split/parse/verify

Prompt-factory split:

- `context`: original task + benchmark mode
- `instruction`: produce 4 coherent descriptions using these exact uniqueness groups
- `think`: explicit per worker policy
- `format`: 4 clearly separable blocks

Best use:

- strongest route for reliability
- best for fail-safe generation
- best for explicit checkpointing

## C2. Constraint-first with local constraint generator

Shape:

- local or analyzer-assisted generation of allowed value pools
- local selection of 4 unique bundles
- final generator call only assembles prose

Example bundle axes:

- eyes
- hair
- pose
- demon markers
- name

Example generated property table:

| block | name | eyes | hair | pose | demon markers | style |
|---|---|---|---|---|---|---|
| 1 | ... | amber | black | kneeling | curved horns, spaded tail | anime |
| 2 | ... | violet | silver | mid-leap | bat wings, glowing sigils | anime |

Then one final prompt factory renders:

```text
Собери задачу, в которой нужно написать 4 описания внешности демониц.
Используй следующие уникальные группы свойств.
Для каждого блока используй ровно одну группу.
Сохрани аниме-стилистику и явные демонические признаки.
...
```

Strengths:

- local runtime owns uniqueness
- generator only realizes prose
- high reliability

Weaknesses:

- more orchestration
- less spontaneous variety unless bundles are rich enough

## Route D

## D1. Full two-phase route

Phase 1:

- generate or derive unique constraints
- verify constraints
- checkpoint accepted property matrix

Phase 2:

- use accepted property matrix as source for prose generation
- generate 4 blocks
- parse back into matrix
- compare generated matrix against source matrix
- run contradiction/coverage probes

This is likely the strongest reference route.

Why it matters:

- explicit source matrix
- explicit output matrix
- clear compare step
- strong benchmark for route robustness

## Atomic building blocks needed

To support the routes above cleanly, Atomic should have reusable building blocks for:

- `split_demoness_blocks(@text)`
- `parse_demoness_matrix(@blocks)`
- `build_task_a_constraint_groups(@task)`
- `verify_task_a_constraints(@matrix)`
- `render_task_a_assembled_prompt(@matrix)`
- `verify_task_a(@matrix)`
- `build_repair_prompt(@artifact, @probe)`
- `compare_constraint_matrix(@source_matrix, @generated_matrix)`

Some can be Atomic macros.
Some are better treated as prompt factories plus local transforms.

## Prompt factories needed

Minimum prompt factories:

1. `task_a_direct_4`
2. `task_a_constraint_groups`
3. `task_a_assembled_from_constraints`
4. `task_a_repair_from_probe`
5. `task_a_block_verify`
6. `task_a_global_verify`

Each factory should explicitly separate:

- `context`
- `instruction`
- `think`
- `format`

## Probe suite for Task A

Recommended probes:

- `coverage`: all 4 blocks present and parseable
- `anti-repeat`: repeated descriptions or near-duplicates
- `uniqueness`: eyes/hair/pose/name all distinct
- `demoness_signal`: each block contains demoness markers
- `anime_style`: anime explicitly present
- `contradiction`: generated text contradicts source property matrix

## Recommended reference routes

If only three routes are kept as official references, use:

1. `A1` monolithic baseline
2. `C1` constraint-first assembled prompt
3. `D1` full two-phase matrix -> prose -> matrix compare route

These three together cover:

- simple baseline
- practical reliability route
- strongest benchmark route

## Revision graph view

Each important stage should become a revision-visible event:

- task message commit
- accepted constraint matrix commit
- generated 4-block artifact commit
- parsed output matrix commit
- verification result commit
- repair branch commit if needed
- accepted final route tag

## Suggested canonical benchmark comparison

For each route, compare:

- number of gateway crossings
- latency
- parse success rate
- uniqueness pass rate
- repair count
- final acceptance rate
- text-image readiness

## Practical recommendation

For the current Atomic direction, the best near-term target is:

- keep `A1` as baseline
- build `C1` as first serious fail-safe route
- treat `D1` as the canonical benchmark-quality route

That gives a clean progression:

- direct generation
- constraint-first generation
- two-phase verified generation

## Short summary

`Task A` is useful because it can be solved through several increasingly explicit Atomic routes:

- direct one-shot generation
- generation plus repair loop
- constraint-first assembly
- full source-matrix to output-matrix comparison

This makes it ideal for testing:

- prompt factories
- checkpoint design
- gateway event capture
- probe quality
- revision transparency
- route reliability
