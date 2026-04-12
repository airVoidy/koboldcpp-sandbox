# Legacy Branch Notes

Короткая карта веток, которые уже просмотрены и не должны мержиться целиком без разбора.

## Safe Current Base

- `runtime-refactor-exec-capability`
  - базовый runtime/frontend слой
  - projection endpoints восстановлены
  - endpoint logs снова пишут сериализованный runtime object
  - public legacy `materialize` убран из основного потока

- `codex/runtime-unify-view`
  - текущая интеграционная ветка поверх `runtime-refactor-exec-capability`
  - добавлены capability rules в `koboldcpp-sandbox/src/lib/sandbox.ts`
  - возвращён приятный layout сообщений
  - восстановлены недостающие frontend entry files (`index.html`, `tsconfig.json`)

## Donor Branches

- `claude/tender-archimedes`
  - полезна как донор отдельных commit-ов
  - хорошие куски:
    - capability-based access
    - exec-first sandbox ideas
    - UI polish
  - опасно мержить целиком:
    - может откатывать projection/runtime слой
    - может утащить назад server interaction

- `codex/explicit-runtime-containers`
  - исторически важна:
    - projection/table containers
    - child-log paging
    - modular ops
  - нельзя мержить целиком в текущую ветку:
    - ветка сильно старее
    - удаляет текущий TS frontend
    - откатывает projection/jsonata/runtime notes
  - использовать только как reference

- `codex/runtime-jsonata-slice`
  - ранний слой JSONata/message projection
  - основные полезные идеи уже перенесены вручную
  - целиком не мержить

## Useful Concepts Already Preserved

- `message projection`
- `template aggregation projection`
- `flat_store`
- `views`
- `mjsonata`
- `mcheckpoint`
- runtime sandbox как exec-first слой

## Practical Rule

Если нужен код из старой ветки:

1. смотреть `git show <commit>:<path>`
2. переносить только конкретный файл или кусок
3. не делать merge/rebase старой ветки целиком

