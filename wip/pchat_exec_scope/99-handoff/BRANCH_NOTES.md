# Branch Notes

Карта веток на 2026-04-16. Это не истина по архитектуре, а рабочие заметки: что где лежит и зачем к этому возвращаться.

## Основные

- `master`
  - `3bdb17a6`
  - `Fix merged runtime TS build breakages`
  - Текущая базовая ветка проекта. Не опорная для старого `pipeline-chat`, но это главный baseline.

- `codex/probe-7f-runtime-return`
  - `7f107e61`
  - `Add atomic projection containers and bind-based runtime views`
  - Пробная ветка для возврата к старой рабочей линии `pipeline-chat`.
  - Полезна как reference для:
    - старого HTML/runtime flow,
    - `Edit` через `atomicPatchValue(...)`,
    - projection containers.
  - Ветка смешанная: уже есть `cselect/creact`, поэтому это не финальная чистая опора.

- `codex/explicit-runtime-containers`
  - `629ffe23`
  - `Add modular projection tables and child-log paging`
  - Линия с explicit runtime containers, table/paging и child-log.
  - Исторически полезна как reference, но именно здесь обратно протащен legacy-слой вроде `current_channel_messages`.

- `codex/runtime-unify-view`
  - `da25554b`
  - `Unify runtime object flow and add replay debug tools`
  - Жирная runtime/view линия:
    - runtime object flow,
    - replay/debug tools,
    - template views,
    - edit/reactions в более позднем виде.
  - Полезна как донор отдельных кусков, но не как чистая база.

## Ветки с точечными восстановлением/срезами

- `codex/runtime-jsonata-slice`
  - `06d2ffef`
  - `Add message projection checkpoint and JSONata runtime eval`
  - Эксперименты с message projection, checkpoint и JSONata runtime eval.
  - Полезна как reference для `mjsonata`, projection slice и runtime eval.

- `codex/restore-materialize-endpoint`
  - `117b60c1`
  - `Add modular projection tables and child-log paging`
  - Ветка, где поверх мастера возвращался `materialize` и куски modular projection/tables.
  - Не воспринимать как каноничную архитектуру.

- `codex/restore-opora-line`
  - `6cb56228`
  - `Record session start in root log`
  - Review-срез для сравнения опорной линии и поиска лишнего по diff.
  - Ветка служебная, полезна именно для просмотра различий.

- `codex/master-pull-merge-d5f8434f`
  - `d5f8434f`
  - `Merge branch 'master' of https://github.com/airVoidy/koboldcpp-sandbox`
  - Сохранённый accidental merge. Нужна только как страховка/история, не как рабочая база.

## Старые/соседние линии

- `claude/priceless-burnell`
  - `184fc4c2`
  - `Pipeline Chat: batch/view endpoints, localStorage cache, architecture plan`
  - Ранняя линия `pipeline-chat`, полезна как маркер начала batch/view/localStorage слоя.

- `priceless-burnell`
  - `184fc4c2`
  - То же состояние, альтернативная ветка.

- `claude/focused-wozniak`
  - `01f33c1c`
  - `Template commands (.py), inheritance, hot-reload, git graph, wiki export`
  - Полезна как reference по template-command/inheritance линии до позднего runtime нагромождения.

- `claude/tender-archimedes`
  - `d8020e2d`
  - `Remove Projection endpoint legacy: runtime-only projections`
  - Линия по runtime-only projections. Смотреть как reference для вырезания legacy projection endpoint.

- `add-claude-github-actions-1775872393374`
  - `29e12617`
  - `Restore projection command layer from runtime slice`
  - Служебная/соседняя ветка. Смотреть только как донор projection command layer, если потребуется.

- `runtime-refactor-exec-capability`
  - `57c3307d`
  - `Restore projection command layer from runtime slice`
  - Соседняя рабочая ветка про `exec`/projection capability.

- `runtime-jsonata-slice`
  - `fb3d8d75`
  - `TSX cleanup: exec-only, remove Projection/Materialize legacy`
  - Отдельная линия со схожим названием; не путать с `codex/runtime-jsonata-slice`.

- `wiki-and-toolcalling`
  - `6cb56228`
  - `Record session start in root log`
  - Служебная ветка, не использовать как архитектурную опору.

## Практический вывод

- Для новой чистой реализации опора сейчас не в старых ветках, а в документации:
  - `wip/pchat_exec_scope/README.md`
  - `wip/pchat_exec_scope/01-foundation/ARCHITECTURE.md`
  - `wip/pchat_exec_scope/02-model/DATA_MODEL.md`
  - `wip/pchat_exec_scope/03-runtime/COMMAND_MODEL.md`
  - `wip/pchat_exec_scope/99-handoff/IMPLEMENTATION_PLAN.md`
  - `wip/pchat_exec_scope/99-handoff/HANDOFF.md`

- Старые ветки нужны как reference по отдельным кускам:
  - `7f107e61` — старый projection/runtime HTML flow,
  - `629ffe23` — table/paging/runtime containers,
  - `da25554b` — runtime object/replay/template views,
  - `01f33c1c` — template commands / inheritance.
