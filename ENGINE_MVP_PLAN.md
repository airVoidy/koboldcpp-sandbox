# Engine MVP Plan

## Goal

Собрать один MVP-каркас, который покрывает несколько разных типов задач:

1. наш текущий текстовый case с извлечением метадаты из вопроса
2. Einstein-style logic puzzles
3. простое 2D sudoku
4. interactive constraints engine с диапазонами, последствиями и breakpoint-объяснениями

Ключевая идея:

- не делать четыре отдельных движка
- сделать одно общее constraint/provenance ядро
- а сверху дать разные frontends / adapters / problem loaders

## Core thesis

Общее ядро должно знать только про:

- variables
- domains
- constraints
- provenance
- dependency index
- solver queries
- explained projections

Оно не должно знать ничего специфичного про:

- текст вопроса
- “кто вошел раньше”
- “кто держит рыбку”
- клетки судоку
- UI диапазонов

Все это должно сидеть в domain adapters.

## MVP layers

### Layer 1. Extraction / Input adapters

Разные входы приводятся к общей форме `Rule` / `Variable` / `Domain`.

Нужны четыре адаптера:

1. `text_case_adapter`
2. `einstein_adapter`
3. `sudoku_adapter`
4. `interactive_constraints_adapter`

### Layer 2. Constraint core

Минимальное общее ядро:

- `Variable`
- `Domain`
- `Rule`
- `Expr` / `Pred`
- `ConstraintStore`
- `DependencyIndex`
- `ProvenanceGraph`
- `SolverAdapter`

### Layer 3. Analysis

Поверх solver:

- satisfiable / unsatisfiable
- candidate assignments
- derived exclusions
- projection to 1D
- boundary detection
- support explanation
- blocking explanation

### Layer 4. Summaries / Outputs

Разные выходные форматы:

- order candidates
- entity-table states
- sudoku candidate grid
- explained 1D ranges with breakpoints

## Shared truth model

Source of truth:

- variables
- domains
- rules
- derived constraints
- provenance graph
- solver state

Derived summaries:

- JSON for rendering
- anomalies
- candidate tables
- range segments
- user explanations

Это важно не смешивать.

## Minimal domain model

### Variables

MVP sorts:

- `bool`
- `int`
- `enum`

Этого достаточно для всех первых задач.

### Domains

Нужны:

- finite enum sets
- finite integer intervals
- finite coordinate products via multiple vars

Примеры:

- `pos(Anna) in {1..7}`
- `house_color[3] in Color`
- `cell[r,c] in {1..4}` для маленького sudoku
- `X in [0, 100]` для interactive constraints engine

### Predicate AST

MVP-предикаты:

- `Eq`
- `Ne`
- `Lt`
- `Le`
- `Gt`
- `Ge`
- `And`
- `Or`
- `Not`
- `Implies`
- `AllDifferent`
- `MemberOf`

`AllDifferent` важен, потому что без него Sudoku и Einstein будут неудобны.

## Solver strategy

Не надо начинать с “идеального общего solver”.

Нужно сделать двухслойный путь:

1. internal AST как source of truth
2. узкий backend adapter для первого solver

Для MVP достаточно одного backend:

- Z3

Почему:

- покрывает int/bool/enum
- умеет SAT/UNSAT
- умеет модели
- есть шанс на unsat core
- хорошо подходит под puzzle-задачи и range queries

## Provenance MVP

Каждое исходное правило должно иметь:

- `rule_id`
- `origin`
- `source_ref` или equivalent source handle
- `label`

Каждый derived node должен иметь:

- `node_id`
- `parent_node_ids`
- `source_rule_ids`
- `explanation_kind`

Нам не нужен сразу идеальный theorem prover.
Но нужен стабильный provenance skeleton.

## Dependency index MVP

Нужен обязательно.

Хранить:

- `var -> rule_ids`
- `rule -> vars`
- опционально `connected component`

Это даст:

- локальный пересчет
- быстрый `range_of(X)`
- быстрый `why X changed`
- хорошую базу для branch candidates

## Four problem classes

## 1. Text case pipeline

Current role:

- parser + atomic QA + deterministic assembly

Output adapter должен строить:

- variables: `pos(person)`, `author`
- domains
- rules from atoms

Примеры:

- `before(Anna, Maxim)` -> `pos(Anna) < pos(Maxim)`
- `immediately_after(Lera, Sofia)` -> `pos(Lera) = pos(Sofia) + 1`
- `not_first(Diana)` -> `pos(Diana) != 1`
- `either_first_or_last(Elisey)` -> `pos(Elisey)=1 OR pos(Elisey)=7`

Это должен быть первый vertical slice.

## 2. Einstein puzzle adapter

Представление:

- ось домов / слотов
- сущности по категориям
- bijection / all-different constraints
- relative position constraints
- adjacency constraints
- membership constraints

Почему это важно:

- это проверяет, что движок умеет работать с табличными логическими задачами
- это почти идеальная стресс-проверка provenance и explanation

Что не нужно в MVP:

- сложные natural language parser flows

Лучше сразу давать puzzle в структурированном JSON/YAML.

## 3. Simple 2D Sudoku adapter

Представление:

- `cell_r_c`
- домен чисел
- row all-different
- col all-different
- block all-different
- givens

Почему это полезно:

- проверяет grid-like constraints
- проверяет сильную propagation-семантику
- заставляет строить candidate summaries по ячейкам

Для MVP достаточно:

- 4x4 или 6x6

Не нужен сразу 9x9.

## 4. Interactive constraints engine

Это не puzzle adapter, а отдельный режим работы поверх того же ядра.

Пользователь:

- задает переменные
- задает ограничения
- добавляет новые правила постепенно

Система:

- говорит SAT / UNSAT
- показывает range/projection по каждой переменной
- показывает breakpoints
- показывает какие правила влияют на каждый сегмент
- показывает relational notes, если проекция неполна

Это уже прямое применение explained projection layer.

## MVP order

Правильный порядок такой:

1. text case
2. interactive constraints engine
3. Einstein adapter
4. simple Sudoku

Почему так:

- text case уже у нас есть как источник атомов
- interactive engine заставит сделать честный core
- Einstein проверит relational logic
- Sudoku проверит grid/all-different/generalization

## Recommended repo structure

Новые модули:

- `src/kobold_sandbox/constraints/ast.py`
- `src/kobold_sandbox/constraints/core.py`
- `src/kobold_sandbox/constraints/provenance.py`
- `src/kobold_sandbox/constraints/index.py`
- `src/kobold_sandbox/constraints/z3_adapter.py`
- `src/kobold_sandbox/constraints/projection.py`
- `src/kobold_sandbox/constraints/engine.py`

Domain adapters:

- `src/kobold_sandbox/adapters/text_case.py`
- `src/kobold_sandbox/adapters/einstein.py`
- `src/kobold_sandbox/adapters/sudoku.py`
- `src/kobold_sandbox/adapters/interactive.py`

Examples:

- `examples/quest_order_case/`
- `examples/einstein_case/`
- `examples/sudoku_4x4_case/`
- `examples/interactive_ranges_case/`

## Concrete MVP milestone plan

### Milestone 1. Constraint core skeleton

Deliver:

- AST
- `Variable`
- `Rule`
- `ConstraintStore`
- `ProvenanceGraph`
- `DependencyIndex`
- no advanced projection yet

Done when:

- можно вручную завести 3-5 правил и проверить `SAT`

### Milestone 2. Narrow Z3 backend

Deliver:

- AST -> Z3 translation
- `is_sat`
- `model`
- simple entailment checks

Done when:

- `quest_order_case` minimal constraints отрабатывают

### Milestone 3. Text case adapter

Deliver:

- `atoms_v0.json -> Rule objects`
- variables and domains for order puzzle
- deterministic compilation from atoms to constraints

Done when:

- можно получить хотя бы один candidate solution
- можно объяснить rule provenance

### Milestone 4. Explained projection MVP

Deliver:

- `range_of(var)`
- breakpoints from direct rules
- allowed/blocked segments
- support/block explanation with rule ids

Done when:

- interactive constraints mode показывает 1D сегменты и влияющие правила

### Milestone 5. Einstein adapter

Deliver:

- structured puzzle schema
- category/slot encoding
- all-different + neighbor + left/right constraints

Done when:

- движок решает простой canonical Einstein-style example

### Milestone 6. Sudoku adapter

Deliver:

- 4x4 sudoku encoding
- candidate summaries per cell
- contradiction explanation for invalid givens

Done when:

- движок решает хотя бы один 4x4 example

## MVP output objects

Нужны общие result types:

- `SatResult`
- `UnsatResult`
- `CandidateModel`
- `ExplainedRange`
- `RangeSegment`
- `BoundaryPoint`
- `BlockingExplanation`
- `SupportExplanation`

И domain-specific summaries:

- `OrderSummary`
- `EinsteinGridSummary`
- `SudokuGridSummary`

## What to postpone

Не надо в первую волну:

- полный generic theorem proving
- оптимальные minimal support sets везде
- сложные nonlinear arithmetic constraints
- rich string constraints
- generalized N-dimensional projection engine
- full natural-language puzzle ingestion

## Sharp engineering rules

- LLM не строит constraints JSON целиком
- LLM только отвечает на атомарные вопросы
- source provenance обязателен
- все derived constraints имеют stable ids
- summary никогда не является source of truth
- adapters не знают solver internals
- solver layer не знает про текстовые фрагменты

## Best first vertical slice

Самый правильный следующий vertical slice:

1. взять `quest_order_case`
2. преобразовать `atoms_v0.json` в `Rule`
3. завести `pos(person)` и `author`
4. сделать узкий Z3 backend
5. получить SAT/model
6. вернуть explanation через `rule_id -> source_ref`

Если это заработает, остальное уже будет расширением, а не магией.
