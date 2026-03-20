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
- выжимать максимум перформанса из каждого типа анализа
- не заставлять каждый модуль знать внутренности других

## Main principle

Архитектура должна быть:

- shared mediator
- specialized workers
- minimal cross-talk
- artifact-driven exchange
- lazy pull when blocked

То есть не:

- “модули плотно вызывают друг друга”

а:

- “модули публикуют артефакты и узкие запросы”

## Shared mediator

`Pine-AST` хранит:

- execution logic
- scheduling logic
- lag semantics
- worker bindings
- projection bindings
- serialization rules

Именно mediator отвечает за:

- порядок тиков
- запуск worker groups
- replay lagged layers
- merge patch bundles
- commit artifacts
- log tick history

Mediator не должен знать доменную внутреннюю математику каждого worker.

## Worker classes

Под каждый тип задачи и под каждый тип анализа запускается свой worker.

Крупно это выглядит так:

### Layer A. Metadata workers

Задача:

- разметить вход
- вытащить метадату
- привести к общему формализованному виду

Примеры:

- entity extraction
- relation marker extraction
- role extraction
- sentence/fragment normalization
- source provenance attachment

### Layer B. Structure workers

Задача:

- собрать структурные формы
- построить matrix/table/tree seeds
- выявить базовые domain constraints

Примеры:

- position-variable builder
- group/member mapper
- matrix-domain initializer
- candidate slot/domain builder

### Layer C. Constraint workers

Задача:

- проверять связи
- распространять ограничения
- искать shortcut-выводы
- локально сужать области допустимых состояний

Примеры:

- ordering solver
- adjacency propagator
- all-different propagator
- range projector
- contradiction detector

### Layer D. Tail workers

Задача:

- доедать unresolved tails
- забирать хвосты после фронтраннеров
- добирать дорогие или узкие случаи

Примеры:

- branch refiner
- crosscheck verifier
- late semantic replay
- local exhaustive checker

### Layer E. Regroup / planner workers

Задача:

- смотреть на все unresolved outputs
- группировать следующую волну задач максимально эффективно
- определять, кого запускать на следующем тике

Это отдельный важный класс workers, не просто utility.

## Frontrunner -> tail model

Главный рабочий ритм:

1. быстрые фронтраннеры дают первый полезный output
2. нижние слои ждут этот первый output
3. каждый следующий слой выжимает максимум из уже доступных данных
4. хвостовые workers добирают сложные куски
5. regroup/planner собирает новый оптимальный batch
6. следующий tick повторяет цикл

Это важно:

- каждый слой не стартует из пустоты
- каждый слой работает на уже нормализованном артефактном входе
- дорогие шаги откладываются до тех пор, пока они реально нужны

## Tick contract

На каждом тике runtime делает одно и то же:

1. читает committed artifacts предыдущих тиков
2. запускает активные frontrunner workers
3. собирает их patch/artifact outputs
4. запускает lagged/follower workers на новых артефактах
5. запускает tail workers на unresolved tails
6. запускает regroup/planner
7. коммитит:
   - новые факты
   - ограничения
   - матричные патчи
   - projection patches
   - unresolved requests
8. пишет tick log

## Communication rule

Модули должны общаться как можно меньше.

Правильный контракт такой:

- worker читает snapshot
- worker локально считает максимум
- worker публикует только:
  - новые facts
  - derived constraints
  - patches
  - explanations
  - requests for missing data

Worker не должен:

- читать произвольное внутреннее состояние другого worker
- напрямую дергать его функции
- зависеть от его временных структур

Это нужно и для перформанса, и для стабильности.

## Shared artifact types

Минимально нужны такие типы:

- `MetadataArtifact`
- `FactArtifact`
- `ConstraintArtifact`
- `ProjectionPatch`
- `MatrixPatch`
- `TreePatch`
- `HeatmapPatch`
- `HypothesisArtifact`
- `UnresolvedRequest`
- `TickLogArtifact`

## Provenance rule

Все артефакты обязаны нести provenance.

Минимум:

- `artifact_id`
- `source_refs`
- `worker_id`
- `tick_id`
- `parent_artifact_ids`
- `interpretation_level`

Если вывод derived, он всё равно должен уметь подниматься к текстовой базе или к upstream artifacts.

## Module-local representations

Очень важно:

общий формат артефактов не означает общий внутренний state.

Наоборот, каждый worker может держать своё представление:

- semantic trees
- relation buckets
- matrix candidates
- domain intervals
- 2D candidate maps
- shortcut graphs
- local caches

Наружу он обязан отдавать только нормализованные artifacts/patches.

## Why this is good

Эта схема дает сразу несколько плюсов:

- дешёвый параллелизм
- selective recomputation
- module-level caching
- простую invalidation model
- возможность подключать новые workers без переписывания старых

## Constraint engine role

Constraint engine в этой архитектуре не “центр всего”.

Он один из ключевых worker families.

Его вход:

- уже формализованная metadata
- уже собранные rules/constraints
- domain seeds

Его выход:

- области допустимых состояний переменных
- derived exclusions
- breakpoint explanations
- local influence summaries
- heatmap-like effect maps

## 1D and 2D outputs

Mediator должен сериализовать результат не только в текст, но и в compact plot-like forms.

Для constraints engine это значит:

- 1D ranges по каждой переменной
- boundary points
- support/block explanations
- 2D effect maps

Для interaction view важен output формата:

- “области возможных состояний переменной”
- “что происходит при переходе через breakpoint”
- “как изменение здесь влияет на соседние переменные”

Твоя идея с `3x3` heatmap/matrix сюда ложится очень хорошо как compact local influence map.

## Final layer contract

Последний шаг пайплайна не должен просто dump-ить сырые derived facts.

Он должен собирать максимально краткий и ёмкий итог.

Нужны два главных результата:

### 1. Hypothesis summary

Список правил / гипотез.

Для каждой гипотезы:

- формализованная версия
- натуральная версия
- что нужно для подтверждения
- что нужно для опровержения
- каких данных сейчас не хватает
- от каких артефактов/фактов она зависит

### 2. Constraint state summary

Для каждой переменной:

- области допустимых состояний
- breakpoints
- почему сегмент allowed / blocked
- локальная карта влияния на другие переменные
- compact 2D/3x3 impact map, если применимо

## Data hunger rule

Каждый слой имеет право запрашивать дополнительные данные только когда уже выжал максимум из того, что есть.

То есть:

- сначала локальная пропагация
- потом derived shortcuts
- потом unresolved output
- только потом request upstream/downstream help

Это защищает от лишней болтовни между модулями.

## Best implementation split

Практически это лучше разделить так:

- `mediator runtime`
- `artifact store`
- `tick scheduler`
- `worker registry`
- `worker protocols`
- `projection serializers`
- `task regroup planner`

Отдельно:

- metadata worker family
- structure worker family
- constraint worker family
- tail worker family
- summary worker family

## Relation to current repo

Это хорошо продолжает уже существующие документы:

- [PINE_AST_DRAFT.md](C:/llm/KoboldCPP%20agentic%20sandbox/PINE_AST_DRAFT.md)
- [PYNECORE_INTEGRATION_PLAN.md](C:/llm/KoboldCPP%20agentic%20sandbox/PYNECORE_INTEGRATION_PLAN.md)

Но уточняет главное:

- общий у нас mediator runtime
- а не общая внутренняя логика workers

## Immediate engineering consequence

Следующий кодовый шаг лучше делать не как “общий solver module для всего подряд”, а как:

1. ввести artifact contract
2. ввести worker protocol
3. ввести tick scheduler skeleton
4. подключить первый worker family:
   - metadata/formalization
5. затем второй:
   - narrow constraint worker for `quest_order_case`

Уже после этого можно наращивать Einstein, Sudoku и range-engine workers без ломки общей модели.
