# Task A: Four Demonesses Benchmark

## Core benchmark idea

This benchmark defines two symmetric task directions:

### Direction A: prompt -> 4 demonesses

From one prompt, produce one structured text artifact containing **4 demoness blocks**.

Each block should describe one demoness.

### Direction B: unique property groups -> 1 demoness

From one unique atomic property group, produce **1 demoness block**.

This is the inverse direction:

- small -> big
- atomic -> grouped
- constrained properties -> one coherent block

## Why this benchmark matters

This task is intentionally small in formal space, but rich in semantic structure.

It covers:

- parsing
- annotation
- block splitting
- grouping
- assembly
- verification
- constraint coverage
- multimodal text/image alignment

## Minimal uniqueness axes

Every 4-block artifact should maintain uniqueness across blocks for at least:

- eye color
- hair color
- pose / action type
- name

Optional additional uniqueness axes:

- demon features
- style descriptors
- emotional tone
- environment details

## Why demonesses

The domain is useful because it is:

- visually recognizable
- culturally popular
- semantically constrained
- surprisingly small in stable distinguishing features

Typical demoness-defining visual markers are limited:

- horns
- wings
- tail
- unusual eyes
- claws / symbols / marks

That makes the benchmark good for testing where models and pipelines begin to fail under uniqueness pressure.

## Stored benchmark forms

The benchmark should be stored in multiple forms:

1. Prompt form
2. 4-block text artifact
3. Parsed block table
4. Atomic property tables
5. Reconstructed 1-block outputs
6. Optional generated images
7. Optional image-side descriptions

## Recommended checkpoint shapes

### Checkpoint 1

Raw prompt asking for 4 unique demoness descriptions.

### Checkpoint 2

One text file with 4 clearly separable blocks.

### Checkpoint 3

Per-block parsed structure:

- name
- eye color
- hair color
- pose / action
- demon features
- style

### Checkpoint 4

Atomic property groups extracted from each block.

### Checkpoint 5

Reconstruction:

- one property group -> one demoness block

## Benchmark philosophy

This benchmark is intentionally redundant and bidirectional.

It should be possible to test:

- big -> small
- small -> big
- parse stability
- uniqueness under pressure
- route quality
- model failure points
- prompt / DSL / probe duel scenarios

## Sports mode

The benchmark is also intentionally funny and visual.

Suggested competitive framing:

- whose agent runs out of unique demoness descriptions first
- whose DSL preserves uniqueness longest
- which route fails first on eye colors / hair colors / poses / demon features

This is both:

- a serious architecture benchmark
- and a meme-friendly public-facing challenge

## Long-term observation

If the benchmark becomes popular enough, language-level uniqueness may eventually saturate:

- many combinations will be reused
- semantic construction tricks will become the real differentiator
- image-space uniqueness may remain larger than text-space uniqueness

That makes this benchmark especially useful for studying:

- language saturation
- semantic clustering
- text-vs-image divergence
- route robustness

