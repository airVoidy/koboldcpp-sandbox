# Architecture Next: CMD-обёртки, Console Scopes, Message-based L0

## Source

- Path: `ARCHITECTURE_NEXT.md`
- Ingested at: 2026-04-11T00:40:28.744783+00:00
- Ingested by: claude

## Summary

Pipeline Chat переписан с последовательных HTTP (5-12 запросов на действие) на batch + view (2 запроса). Следующий шаг: generic console scopes, CMD как универсальная обёртка, message-based L0. CMD — н

## Excerpt

```
# Architecture Next: CMD-обёртки, Console Scopes, Message-based L0

## Контекст

Pipeline Chat переписан с последовательных HTTP (5-12 запросов на действие) на batch + view (2 запроса). Следующий шаг: generic console scopes, CMD как универсальная обёртка, message-based L0.

## 1. CMD как универсальная обёртка

CMD — не просто консольная команда, а **контейнер-обёртка** на всех уровнях:

- **Валидатор** — проверяет данные до патча, не пропускает мусор
- **Контекст** — несёт автора, selected объект, любые кастомные поля через точечную нотацию (`.cmd`, `.name`, `.emoji` — any)
- **Логика** — toggle, increment, slot allocation — внутри обёртки
- **Composable** — cmd передаёт в следующую cmd, pipeline из одноатомных шагов
- **Лямбда** — `cmd x -> applyCommand(x)`, разворачивается при вызове

### cmd объект

```javascript
{ cmd: 'react', target: 'msg_1', emoji: '👍', user: 'alice', _ts: Date.now() }
```
