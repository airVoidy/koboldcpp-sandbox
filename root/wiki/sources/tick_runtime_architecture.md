# Tick Runtime Architecture

## Source

- Path: `TICK_RUNTIME_ARCHITECTURE.md`
- Ingested at: 2026-04-11T00:40:28.749229+00:00
- Ingested by: claude

## Summary

Общий у нас не “один solver на всё”. Общее у нас: - `Pine-AST` как mediator IR

## Excerpt

```
# Tick Runtime Architecture

## Core position

Общий у нас не “один solver на всё”.

Общее у нас:

- `Pine-AST` как mediator IR
- tick-based runtime
- общий provenance / source refs
- общий artifact protocol
- общий scheduler

А вычислительные модули специально разведены в стороны.

Это нужно, чтобы:

- параллелить вычисления
- держать module-local state и индексы
```
