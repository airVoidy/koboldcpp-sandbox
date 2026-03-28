# ATOMIC Data Scope Lifecycle v0.1

## Purpose

Define the main lifecycle scopes for Atomic data artifacts.

The goal is to keep intermediate state explicit without forcing all of it to become durable clutter.


## Core Scope Set

Atomic should use three main scope layers:

- `@data.temp`
- `@data.local`
- `@data.global`


## `@data.temp`

Temporary pipeline scope.

Use for:

- intermediate request drafts
- temporary projections
- parse scratchpads
- probe scratch outputs
- transient comparison tables
- debug-visible but non-durable working artifacts

### Lifecycle

- visible during execution
- may be checkpointed for debug if needed
- expected to be cleaned after pipeline completion
- not preferred for durable storage

### Purpose

Make intermediate state explicit without polluting durable task/global memory.


## `@data.local`

Task-local or tree-local working scope.

Use for:

- current task input
- current task answer
- local summaries
- local extracted facts
- task-bound objects/tables/checkpoints

### Lifecycle

- survives the pipeline
- remains attached to the current task/tree/session scope
- can be reused by later local steps
- may later be promoted upward


## `@data.global`

Promoted shared scope.

Use for:

- consolidated lists
- reusable summaries
- shared presets
- promoted facts or indexes
- user-level durable artifacts

### Lifecycle

- long-lived
- explicitly promoted or merged into
- should stay cleaner and more curated than local/temp scopes


## Canonical Flow

Recommended direction:

1. create transient work in `@data.temp`
2. keep task-relevant retained results in `@data.local`
3. explicitly promote selected artifacts into `@data.global`


## Why This Is Better

- `temp` keeps debug visibility
- `local` keeps task memory explicit
- `global` keeps durable shared memory curated
- avoids hidden runtime buffers
- avoids dumping every scratch artifact into long-lived storage


## Artifact Examples

### Temp

```text
@data.temp.object.generate.request_draft
@data.temp.table.response.parse_scratch
@data.temp.wiki.probe.notes
```

### Local

```text
@data.local.wiki.task.input
@data.local.object.generate.request
@data.local.message.response.output
@data.local.table.response.annotations
```

### Global

```text
@data.global.wiki.colors.eyes
@data.global.wiki.colors.hair
@data.global.table.entity.index
```


## Important Rule

`temp`, `local`, and `global` are not different storage ontologies.

They are lifecycle scopes over the same general data-artifact model.


## Summary

Atomic should explicitly distinguish:

- `@data.temp` for transient visible working state
- `@data.local` for task-local retained state
- `@data.global` for promoted durable shared state
