# Architecture Summary

## Source

- Path: `ARCHITECTURE_SUMMARY.md`
- Ingested at: 2026-04-11T00:40:28.740149+00:00
- Ingested by: claude

## Summary

Build a local agentic sandbox over `koboldcpp` where a reasoning model generates hypotheses, framework workers formalize and check them, and the system accumulates verified structure across multiple s

## Excerpt

```
# Architecture Summary

## Goal

Build a local agentic sandbox over `koboldcpp` where a reasoning model generates hypotheses, framework workers formalize and check them, and the system accumulates verified structure across multiple synchronized representations.

The target is not a single linear chain-of-thought store, but a reusable framework for:

- parsing task questions into answer schemas
- atomizing conditions into typed hypotheses
- expanding consequences to bounded depth
- tracking causal and semantic links between claims
- checking branch compatibility and intersections
- compiling verified facts into a fast execution layer

## Core Principle

`git` branches are runtime sandboxes for hypothesis execution, not the primary knowledge model.

Knowledge should live in a canonical fact/hypothesis layer, with multiple projections built on top of it:
```
