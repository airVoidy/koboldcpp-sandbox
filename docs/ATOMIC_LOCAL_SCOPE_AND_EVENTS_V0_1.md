# Atomic Local Scope and Events v0.1

## Purpose

This document defines a simple local scope and event model for Atomic.

The goal is:

- avoid one giant global namespace
- keep references easy to generate
- allow different objects to expose different local aliases
- let event cascades stay simple and tree-friendly

## Core rule

Atomic semantic references should be local by default.

That means:

- aliases are defined inside the current scope
- `on` clauses resolve inside the same scope
- different scopes may reuse the same alias names safely

## Scope-bound resolution

`on` does not need a separate hard owner model.

It is enough to say:

- `on` resolves inside the scope where it is declared

That scope may be:

- a node
- a message container
- a checkpoint object
- a table object
- a template

## Why local scope is better

Local scope helps because:

- model generation is easier
- names stay short
- aliases do not collide globally
- each object can expose the refs that make sense for it

## Basic pattern

Inside a scope, declare some local refs:

```text
@self
@parent
@child_message
@carrier
@table
@span
```

Then attach events:

```text
[on new @child_message]
[on edit @child_message]
[on remove @child_message]
```

## Event model

An `on` block means:

- when event `X` happens
- on local ref `Y`
- run the declared reaction

At this level, the system does not need to overdefine execution details.

The main thing is:

- event type is explicit
- local target ref is explicit
- resolution is local to the current scope

## Event names

Useful starting event names:

- `new`
- `edit`
- `remove`
- `patch`
- `resolve`
- `attach`
- `detach`
- `split`
- `merge`
- `comment`

This set should stay extensible.

## Message-thread example

A thread-starting message may define:

```text
@child_message
@prior_messages
```

Then:

```text
[on new @child_message]
[on edit @child_message]
[on remove @child_message]
```

Here `@child_message` is meaningful because this scope is a thread-like message object.

## Table example

A table object may define:

```text
@row
@cell
@patch
```

Then:

```text
[on patch @cell]
[on add @row]
[on remove @row]
```

This is the same event form, but with different local aliases.

## Carrier example

A checkpoint carrier scope may define:

```text
@carrier
@span
@comment_thread
```

Then:

```text
[on add @span]
[on comment @span]
[on attach @comment_thread]
```

## Template example

A template or schema scope may define:

```text
@slot
@example
@constraint
```

Then:

```text
[on fill @slot]
[on edit @example]
[on attach @constraint]
```

## Cascades

Because scopes are local, event cascades can stay simple.

One scope may react and create new messages or containers.

Those new objects may define their own local aliases and their own `on` blocks.

So the system naturally becomes:

- tree-shaped
- scope-local
- composable

## No mandatory global alias map

There may still be some common convenience refs in practice.

But the model should not depend on one universal global alias dictionary.

The default should be:

- local aliases first
- global conventions optional

## Relation to code style

In a reactive-atomic approach, exact trigger ownership is less important than declaration context.

So this model intentionally avoids overformalizing:

- owner semantics
- one rigid inheritance model
- one fixed runtime binding rule

The important thing is simply:

- declare local refs
- use `on` against them
- resolve inside current scope

## Short summary

Atomic event handling should be:

- local-scope-first
- alias-based
- scope-bound
- tree-friendly

So different objects can expose different semantic refs, while still using the same simple event form:

- `[on new @child_message]`
- `[on patch @cell]`
- `[on add @span]`
