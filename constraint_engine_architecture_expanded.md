# Constraint Projection Engine — Expanded Design Notes
*(длинное саммари обсуждения + архитектура классов + примерный кодовый каркас)*

## 1. Краткая постановка задачи

Есть пользовательская система правил над переменными.

Пользователь может постепенно добавлять:

- переменные;
- правила/ограничения;
- новые связи между переменными.

Нужно уметь:

1. определить, существует ли вообще хотя бы одно допустимое состояние системы;
2. вычислять возможные диапазоны / множества значений переменных как **проекции множества решений**;
3. для каждой итоговой области на 1D-оси переменной хранить **список влияющих исходных правил**;
4. пересчитывать это инкрементально при добавлении новых правил.

Ключевая мысль:

> правила задают не “отдельные домены переменных”, а **общее многомерное множество допустимых состояний**.

Диапазон одной переменной — это просто **тень** этого множества на одну ось.

---

## 2. Самая важная модель

### Не так

> у каждой переменной есть свой диапазон, и правила его постепенно сужают

### А так

> есть множество допустимых совместных состояний всей системы;  
> диапазон переменной — это проекция этого множества на ось переменной.

Это важно, потому что можно иметь сильную зависимость без полезного унарного диапазона.

Пример:

```text
A == B
```

Тогда по отдельности:

- `A`: почти всё
- `B`: почти всё

Но совместно:

- только точки, где `A == B`

То есть нельзя хранить только “диапазоны по одной переменной” как источник истины.  
Источник истины — **сами ограничения**.

---

## 3. Что должно быть ответом системы

### Минимальный ответ

- `SAT` / `UNSAT`
- по каждой переменной:
  - допустимые интервалы / множества / точки;
  - пометка, если диапазон условный или сильно зависит от других переменных;
  - список влияющих исходных правил на каждый сегмент диапазона

### Более честный ответ

```text
SAT

B:
  (-∞, 4)  allowed
     influenced_by = [r1, r7]
  [4, +∞)  conditionally allowed
     influenced_by = [r1]
     note = allowed when A <= 5
```

То есть результат не просто “range”, а **explained projection**.

---

## 4. Главная архитектурная идея

Разделить систему на независимые слои:

1. **AST выражений и предикатов**
2. **Хранилище ограничений**
3. **Граф происхождения (provenance DAG)**
4. **Индекс зависимостей / hypergraph**
5. **Solver adapter**
6. **Projection analyzer**
7. **User-facing summary layer**

Это позволяет не смешивать:

- исходные правила;
- выводимые следствия;
- SAT-семантику;
- объяснения для пользователя.

---

# 5. Базовые сущности

## 5.1 Variable

```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Variable:
    name: str
    sort: str   # "int", "real", "bool", "enum:Color"
```

Даже если исходных доменов нет, у переменной должен быть хотя бы **тип**.

---

## 5.2 AST выражений

```python
from dataclasses import dataclass
from typing import Tuple

class Expr:
    pass

class Pred:
    pass


@dataclass(frozen=True)
class Var(Expr):
    name: str


@dataclass(frozen=True)
class Const(Expr):
    value: Any


@dataclass(frozen=True)
class Add(Expr):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Sub(Expr):
    left: Expr
    right: Expr
```

---

## 5.3 Предикаты

```python
@dataclass(frozen=True)
class Eq(Pred):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Ne(Pred):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Lt(Pred):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Le(Pred):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Gt(Pred):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Ge(Pred):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class And(Pred):
    items: Tuple[Pred, ...]


@dataclass(frozen=True)
class Or(Pred):
    items: Tuple[Pred, ...]


@dataclass(frozen=True)
class Not(Pred):
    item: Pred


@dataclass(frozen=True)
class Implies(Pred):
    cond: Pred
    cons: Pred
```

---

## 5.4 Rule

Исходное пользовательское правило лучше хранить отдельно от производных ограничений.

```python
@dataclass(frozen=True)
class Rule:
    rule_id: str
    label: str
    pred: Pred
    origin: str = "user"
    meta: dict | None = None
```

---

# 6. Provenance layer — ключевой кусок

Тут и живёт недостающая часть твоей системы.

Тебе нужен отдельный уровень, который хранит:

- исходные правила;
- промежуточные выводы;
- связи “из чего что получилось”;
- возможность подняться от итогового сегмента диапазона к стартовым правилам.

## 6.1 ConstraintNode

```python
@dataclass
class ConstraintNode:
    node_id: str
    pred: Pred
    kind: str                 # "rule", "derived", "fact", "query"
    source_rule_ids: set[str]
    parent_node_ids: list[str]
    explanation: str | None = None
```

### Смысл полей

- `rule` — исходное правило пользователя;
- `derived` — следствие, полученное из других узлов;
- `fact` — временное ограничение запроса;
- `query` — вспомогательное ограничение во время range-analysis.

Самое важное поле:

- `source_rule_ids`

Это множество **исходных пользовательских правил**, от которых в конечном счёте зависит данный узел.

---

## 6.2 ProvenanceGraph

```python
class ProvenanceGraph:
    def __init__(self):
        self.nodes: dict[str, ConstraintNode] = {}
        self.parents: dict[str, set[str]] = {}
        self.children: dict[str, set[str]] = {}

    def add_rule_node(self, node: ConstraintNode) -> None:
        self.nodes[node.node_id] = node
        self.parents.setdefault(node.node_id, set())
        self.children.setdefault(node.node_id, set())

    def add_derived_node(self, node: ConstraintNode) -> None:
        self.nodes[node.node_id] = node
        self.parents.setdefault(node.node_id, set())
        self.children.setdefault(node.node_id, set())

        for parent_id in node.parent_node_ids:
            self.parents[node.node_id].add(parent_id)
            self.children.setdefault(parent_id, set()).add(node.node_id)

    def ancestry_rule_ids(self, node_id: str) -> set[str]:
        stack = [node_id]
        seen = set()
        result = set()

        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)

            node = self.nodes[cur]
            result |= set(node.source_rule_ids)

            for p in self.parents.get(cur, ()):
                stack.append(p)

        return result

    def ancestry_nodes(self, node_id: str) -> list[str]:
        stack = [node_id]
        seen = set()
        out = []

        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            out.append(cur)
            for p in self.parents.get(cur, ()):
                stack.append(p)

        return out
```

### Зачем DAG

Потому что объяснение сегмента почти никогда не будет “напрямую это правило”.

Чаще:

- `r1: A > 5 => B < 4`
- `r2: B < 4 => C = 1`
- derived: `A > 5 => C = 1`

А потом уже этот derived-узел участвует в итоговом диапазоне `C`.

Без provenance DAG всё это превратится в липкий туман.

---

# 7. Constraint store

Это source of truth по правилам и переменным.

```python
class ConstraintStore:
    def __init__(self):
        self.variables: dict[str, Variable] = {}
        self.rule_ids: list[str] = []
        self.prov = ProvenanceGraph()

    def add_variable(self, var: Variable) -> None:
        self.variables[var.name] = var

    def add_rule(self, rule: Rule) -> None:
        node = ConstraintNode(
            node_id=rule.rule_id,
            pred=rule.pred,
            kind="rule",
            source_rule_ids={rule.rule_id},
            parent_node_ids=[],
            explanation=rule.label or None,
        )
        self.rule_ids.append(rule.rule_id)
        self.prov.add_rule_node(node)

    def all_rule_preds(self) -> list[Pred]:
        return [self.prov.nodes[rid].pred for rid in self.rule_ids]
```

---

# 8. Dependency index / hypergraph

Нужен отдельный слой, чтобы быстро понимать:

- какие правила вообще связаны с переменной;
- какой компонент нужно пересчитывать;
- какие правила имеют смысл для конкретной проекции.

```python
class DependencyIndex:
    def __init__(self):
        self.var_to_node_ids: dict[str, set[str]] = {}
        self.node_to_var_names: dict[str, set[str]] = {}

    def register(self, node_id: str, var_names: set[str]) -> None:
        self.node_to_var_names[node_id] = set(var_names)
        for v in var_names:
            self.var_to_node_ids.setdefault(v, set()).add(node_id)

    def nodes_for_var(self, var_name: str) -> set[str]:
        return set(self.var_to_node_ids.get(var_name, set()))
```

### extract_vars

Нужен helper, который умеет вытащить имена переменных из AST.

```python
def extract_vars_expr(expr: Expr) -> set[str]:
    if isinstance(expr, Var):
        return {expr.name}
    if isinstance(expr, Const):
        return set()
    if isinstance(expr, (Add, Sub)):
        return extract_vars_expr(expr.left) | extract_vars_expr(expr.right)
    return set()


def extract_vars_pred(pred: Pred) -> set[str]:
    if isinstance(pred, (Eq, Ne, Lt, Le, Gt, Ge)):
        return extract_vars_expr(pred.left) | extract_vars_expr(pred.right)
    if isinstance(pred, And):
        out = set()
        for item in pred.items:
            out |= extract_vars_pred(item)
        return out
    if isinstance(pred, Or):
        out = set()
        for item in pred.items:
            out |= extract_vars_pred(item)
        return out
    if isinstance(pred, Not):
        return extract_vars_pred(pred.item)
    if isinstance(pred, Implies):
        return extract_vars_pred(pred.cond) | extract_vars_pred(pred.cons)
    return set()
```

---

# 9. Solver adapter

Этот слой должен быть максимально тупым и честным.  
Никакой бизнес-логики, только семантика.

```python
class SolverAdapter:
    def __init__(self, store: ConstraintStore):
        self.store = store

    def is_sat(self, extra: list[Pred] | None = None) -> bool:
        # тут реальная интеграция с SMT/CSP solver
        return True

    def model(self, extra: list[Pred] | None = None) -> dict[str, Any]:
        return {}

    def entails(self, pred: Pred) -> bool:
        # store.rules => pred ?
        return False

    def min_value(self, var_name: str, extra: list[Pred] | None = None):
        return None

    def max_value(self, var_name: str, extra: list[Pred] | None = None):
        return None

    def unsat_core_rule_ids(self, extra: list[Pred] | None = None) -> set[str]:
        # если solver поддерживает unsat core — отлично
        return set()
```

### Практически

Для первой рабочей версии это обычно:

- свой AST
- перевод в Z3
- `push/pop`
- запросы на SAT
- опционально `unsat_core`

---

# 10. User-facing result objects

Вот здесь собирается объяснимый диапазон.

## 10.1 RangeSegment

```python
@dataclass
class RangeSegment:
    left: Any | None
    right: Any | None
    left_closed: bool
    right_closed: bool
    allowed: bool

    support_rule_ids: set[str]
    support_node_ids: set[str]

    note: str | None = None
```

Это одна часть оси:

- разрешённая
- или запрещённая

И к ней привязаны:

- исходные влияющие правила;
- внутренние узлы provenance graph.

---

## 10.2 BoundaryPoint

```python
@dataclass
class BoundaryPoint:
    value: Any
    kind: str           # "lower", "upper", "fixed", "excluded", "conditional"
    rule_ids: set[str]
    node_ids: set[str]
    note: str | None = None
```

### Зачем отдельно границы

Потому что очень часто пользователь хочет не “какой диапазон в целом”, а:

> откуда взялась именно эта точка / эта граница / эта дырка

---

## 10.3 ExplainedRange

```python
@dataclass
class ExplainedRange:
    var_name: str
    segments: list[RangeSegment]
    boundaries: list[BoundaryPoint]
    relational_notes: list[str]
```

### Зачем relational_notes

Потому что бывают ситуации:

- унарный диапазон выглядит широким;
- но есть жёсткая зависимость от других переменных.

Например:

```text
A == B
```

Поэтому полезно писать:

```text
B: individually wide, but constrained by relation A == B
```

---

# 11. Projection analyzer — сердце explained projection

Это слой, который строит разрез оси переменной на meaningful segments.

```python
class ProjectionAnalyzer:
    def __init__(self, store: ConstraintStore, index: DependencyIndex, solver: SolverAdapter):
        self.store = store
        self.index = index
        self.solver = solver

    def range_of(self, var_name: str) -> ExplainedRange:
        # 1) собрать связанные правила
        # 2) собрать breakpoints
        # 3) построить candidate segments
        # 4) SAT-check по сегментам
        # 5) найти support/block explanations
        # 6) вернуть ExplainedRange
        return ExplainedRange(
            var_name=var_name,
            segments=[],
            boundaries=[],
            relational_notes=[],
        )
```

---

# 12. Как строить ось: breakpoints

Очень полезный приём.

Берёшь все ограничения, которые касаются переменной `X`, и вытаскиваешь из них “интересные значения”:

- `X < 4` → `4`
- `X <= 4` → `4`
- `X == 3` → `3`
- `X != 5` → `5`

Потом из точек `{3, 5, 7}` строишь сегменты:

- `(-∞, 3)`
- `{3}`
- `(3, 5)`
- `{5}`
- `(5, 7)`
- `{7}`
- `(7, +∞)`

Каждый такой сегмент можно проверять отдельно.

---

## 12.1 Упрощённая заготовка

```python
def collect_breakpoints(var_name: str, preds: list[Pred]) -> list[Any]:
    points = set()

    def visit(pred: Pred):
        if isinstance(pred, (Eq, Ne, Lt, Le, Gt, Ge)):
            if isinstance(pred.left, Var) and pred.left.name == var_name and isinstance(pred.right, Const):
                points.add(pred.right.value)
            if isinstance(pred.right, Var) and pred.right.name == var_name and isinstance(pred.left, Const):
                points.add(pred.left.value)
        elif isinstance(pred, And):
            for item in pred.items:
                visit(item)
        elif isinstance(pred, Or):
            for item in pred.items:
                visit(item)
        elif isinstance(pred, Not):
            visit(pred.item)
        elif isinstance(pred, Implies):
            visit(pred.cond)
            visit(pred.cons)

    for p in preds:
        visit(p)

    return sorted(points)
```

---

# 13. Segment explanation

Вот тут как раз и нужен provenance слой.

## 13.1 Для forbidden сегмента

Если:

```text
rules + (X in segment)
```

даёт `UNSAT`, то:

- этот сегмент невозможен;
- нужно объяснить, какие правила его блокируют.

Идеальный вариант:

- получить `unsat core`;
- поднять `unsat core` к исходным правилам.

## 13.2 Для allowed сегмента

Если сегмент допустим:

- можно взять witness model;
- можно собрать правила, которые определили его границы;
- можно собрать ancestry тех derived nodes, которые реально участвовали.

---

## 13.3 Отдельно: support vs block

Это разные вещи.

### blocking explanation
Почему кусок **нельзя**.

### support explanation
Почему кусок **можно** и откуда у него такие границы.

Если всё смешать в один список, получится каша.

---

# 14. API объяснений

### BlockingExplanation

```python
@dataclass
class BlockingExplanation:
    rule_ids: set[str]
    node_ids: set[str]
    text: str | None = None
```

### SupportExplanation

```python
@dataclass
class SupportExplanation:
    rule_ids: set[str]
    node_ids: set[str]
    witness_model: dict[str, Any] | None = None
    text: str | None = None
```

Их можно хранить внутри `RangeSegment`, если хочешь более явную модель.

---

# 15. Публичный движок

Вот оркестратор, который сводит всё вместе.

```python
class ConstraintEngine:
    def __init__(self):
        self.store = ConstraintStore()
        self.index = DependencyIndex()
        self.solver = SolverAdapter(self.store)
        self.projections = ProjectionAnalyzer(self.store, self.index, self.solver)

    def add_var(self, name: str, sort: str) -> None:
        self.store.add_variable(Variable(name=name, sort=sort))

    def add_rule(self, rule_id: str, pred: Pred, label: str = "") -> None:
        rule = Rule(rule_id=rule_id, label=label, pred=pred)
        self.store.add_rule(rule)

        var_names = extract_vars_pred(pred)
        self.index.register(rule_id, var_names)

    def is_sat(self) -> bool:
        return self.solver.is_sat()

    def range_of(self, var_name: str) -> ExplainedRange:
        return self.projections.range_of(var_name)
```

---

# 16. Минимальный пример использования

```python
engine = ConstraintEngine()

engine.add_var("A", "int")
engine.add_var("B", "int")
engine.add_var("C", "int")

engine.add_rule(
    "r1",
    Implies(
        Gt(Var("A"), Const(5)),
        Lt(Var("B"), Const(4)),
    ),
    label="If A > 5 then B < 4",
)

engine.add_rule(
    "r2",
    Implies(
        Lt(Var("B"), Const(4)),
        Eq(Var("C"), Const(1)),
    ),
    label="If B < 4 then C = 1",
)

sat = engine.is_sat()
rng_b = engine.range_of("B")
rng_c = engine.range_of("C")
```

---

# 17. Как выглядит user-facing summary

Пример желаемого результата:

```text
SAT

B:
  (-∞, 4) allowed
    influenced_by_rules = [r1]
  [4, +∞) conditionally allowed
    note = allowed when A <= 5

C:
  {1} conditionally implied
    influenced_by_rules = [r1, r2]
    reasoning = A > 5 => B < 4 => C = 1
```

---

# 18. Инкрементальный пересчёт

Поскольку пользователь может постоянно докидывать правила, нужно проектировать не “одноразовый batch-анализ”, а инкрементальный движок.

## База

Хранить:

- список переменных;
- список правил;
- dependency index / hypergraph;
- provenance graph;
- кэш проекций.

## При добавлении нового правила

1. зарегистрировать правило;
2. выделить его переменные;
3. найти затронутый компонент;
4. инвалидировать кэши проекций только в этом компоненте;
5. пересчитать только нужный кусок.

---

# 19. Кэширование

Полезно кэшировать:

- `range_of(var_name)`
- собранные breakpoints
- slice связанного компонента
- derived nodes, если делаешь lazy derivation

### Но

Никогда не делай derived summary источником истины.  
Истина — это всё ещё исходные constraints.

---

# 20. Lazy derivation вместо полного вывода

Очень хорошая инженерная идея.

Не пытайся заранее вывести все следствия мира.

Лучше:

- при запросе `range_of(X)` строить локальный slice;
- выводить только те промежуточные узлы, которые реально нужны;
- записывать их в provenance graph как derived nodes.

Так ты не строишь домашний theorem prover размером с галактику.

---

# 21. Что важно для первой версии

## Нужно обязательно

- стабильные ID у правил и derived nodes;
- AST вместо строк;
- отдельный provenance graph;
- отдельный dependency index;
- explained range как first-class result.

## Можно отложить

- полные минимальные support sets;
- совершенный unsat core;
- сложную арифметику;
- строки и произвольные пользовательские функции.

---

# 22. Разделение truth vs summary

Это одна из самых полезных границ в архитектуре.

## Source of truth

- переменные
- исходные правила
- derived nodes
- solver semantics

## Derived summary

- SAT/UNSAT
- диапазоны
- сегменты
- boundary points
- human-readable explanations

Если summary станет источником истины — всё постепенно поедет в логическую кашу.

---

# 23. Какой минимальный pipeline нужен для range_of(X)

```text
1. Взять правила, связанные с X
2. Собрать breakpoints
3. Построить candidate segments
4. Для каждого сегмента проверить SAT
5. Если SAT:
      собрать support explanation
   Если UNSAT:
      собрать blocking explanation
6. Собрать ExplainedRange
```

---

# 24. Модель “влияющих правил”

Есть несколько уровней полезности.

## Уровень 1. Graph slice
Какие правила вообще находятся в компоненте переменной `X`.

Быстро, но грубо.

## Уровень 2. Boundary rules
Какие правила реально породили конкретную границу.

Лучше.

## Уровень 3. Minimal support / unsat core
Какие правила минимально нужны для:

- разрешённости сегмента;
- или невозможности сегмента.

Это уже самое вкусное, но и самое трудное.

### Практический компромисс для MVP

- для forbidden сегментов: `minimal blocking rule set`
- для allowed сегментов: `boundary rule set + witness model`

Это даёт очень неплохую объяснимость уже в первой версии.

---

# 25. Итоговый список классов

Вот хороший, компактный, но достаточный набор:

```text
Variable
Expr / Pred subclasses
Rule
ConstraintNode
ProvenanceGraph
ConstraintStore
DependencyIndex
SolverAdapter
ProjectionAnalyzer
ConstraintEngine
ExplainedRange
RangeSegment
BoundaryPoint
BlockingExplanation
SupportExplanation
```

---

# 26. Полный пример каркаса кода

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple


# =========================
# AST
# =========================

class Expr:
    pass


class Pred:
    pass


@dataclass(frozen=True)
class Var(Expr):
    name: str


@dataclass(frozen=True)
class Const(Expr):
    value: Any


@dataclass(frozen=True)
class Add(Expr):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Sub(Expr):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Eq(Pred):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Ne(Pred):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Lt(Pred):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Le(Pred):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Gt(Pred):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Ge(Pred):
    left: Expr
    right: Expr


@dataclass(frozen=True)
class And(Pred):
    items: Tuple[Pred, ...]


@dataclass(frozen=True)
class Or(Pred):
    items: Tuple[Pred, ...]


@dataclass(frozen=True)
class Not(Pred):
    item: Pred


@dataclass(frozen=True)
class Implies(Pred):
    cond: Pred
    cons: Pred


# =========================
# Core entities
# =========================

@dataclass(frozen=True)
class Variable:
    name: str
    sort: str


@dataclass(frozen=True)
class Rule:
    rule_id: str
    label: str
    pred: Pred
    origin: str = "user"
    meta: dict | None = None


@dataclass
class ConstraintNode:
    node_id: str
    pred: Pred
    kind: str
    source_rule_ids: set[str]
    parent_node_ids: list[str]
    explanation: str | None = None


# =========================
# Explanations
# =========================

@dataclass
class BlockingExplanation:
    rule_ids: set[str]
    node_ids: set[str]
    text: str | None = None


@dataclass
class SupportExplanation:
    rule_ids: set[str]
    node_ids: set[str]
    witness_model: dict[str, Any] | None = None
    text: str | None = None


@dataclass
class RangeSegment:
    left: Any | None
    right: Any | None
    left_closed: bool
    right_closed: bool
    allowed: bool
    support_rule_ids: set[str]
    support_node_ids: set[str]
    note: str | None = None


@dataclass
class BoundaryPoint:
    value: Any
    kind: str
    rule_ids: set[str]
    node_ids: set[str]
    note: str | None = None


@dataclass
class ExplainedRange:
    var_name: str
    segments: list[RangeSegment]
    boundaries: list[BoundaryPoint]
    relational_notes: list[str]


# =========================
# Helper functions
# =========================

def extract_vars_expr(expr: Expr) -> set[str]:
    if isinstance(expr, Var):
        return {expr.name}
    if isinstance(expr, Const):
        return set()
    if isinstance(expr, (Add, Sub)):
        return extract_vars_expr(expr.left) | extract_vars_expr(expr.right)
    return set()


def extract_vars_pred(pred: Pred) -> set[str]:
    if isinstance(pred, (Eq, Ne, Lt, Le, Gt, Ge)):
        return extract_vars_expr(pred.left) | extract_vars_expr(pred.right)

    if isinstance(pred, And):
        out = set()
        for item in pred.items:
            out |= extract_vars_pred(item)
        return out

    if isinstance(pred, Or):
        out = set()
        for item in pred.items:
            out |= extract_vars_pred(item)
        return out

    if isinstance(pred, Not):
        return extract_vars_pred(pred.item)

    if isinstance(pred, Implies):
        return extract_vars_pred(pred.cond) | extract_vars_pred(pred.cons)

    return set()


# =========================
# Provenance graph
# =========================

class ProvenanceGraph:
    def __init__(self):
        self.nodes: dict[str, ConstraintNode] = {}
        self.parents: dict[str, set[str]] = {}
        self.children: dict[str, set[str]] = {}

    def add_rule_node(self, node: ConstraintNode) -> None:
        self.nodes[node.node_id] = node
        self.parents.setdefault(node.node_id, set())
        self.children.setdefault(node.node_id, set())

    def add_derived_node(self, node: ConstraintNode) -> None:
        self.nodes[node.node_id] = node
        self.parents.setdefault(node.node_id, set())
        self.children.setdefault(node.node_id, set())

        for parent_id in node.parent_node_ids:
            self.parents[node.node_id].add(parent_id)
            self.children.setdefault(parent_id, set()).add(node.node_id)

    def ancestry_rule_ids(self, node_id: str) -> set[str]:
        stack = [node_id]
        seen = set()
        result = set()

        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)

            node = self.nodes[cur]
            result |= set(node.source_rule_ids)

            for p in self.parents.get(cur, ()):
                stack.append(p)

        return result


# =========================
# Store / index
# =========================

class ConstraintStore:
    def __init__(self):
        self.variables: dict[str, Variable] = {}
        self.rule_ids: list[str] = []
        self.prov = ProvenanceGraph()

    def add_variable(self, var: Variable) -> None:
        self.variables[var.name] = var

    def add_rule(self, rule: Rule) -> None:
        node = ConstraintNode(
            node_id=rule.rule_id,
            pred=rule.pred,
            kind="rule",
            source_rule_ids={rule.rule_id},
            parent_node_ids=[],
            explanation=rule.label or None,
        )
        self.rule_ids.append(rule.rule_id)
        self.prov.add_rule_node(node)

    def all_rule_preds(self) -> list[Pred]:
        return [self.prov.nodes[rid].pred for rid in self.rule_ids]


class DependencyIndex:
    def __init__(self):
        self.var_to_node_ids: dict[str, set[str]] = {}
        self.node_to_var_names: dict[str, set[str]] = {}

    def register(self, node_id: str, var_names: set[str]) -> None:
        self.node_to_var_names[node_id] = set(var_names)
        for v in var_names:
            self.var_to_node_ids.setdefault(v, set()).add(node_id)

    def nodes_for_var(self, var_name: str) -> set[str]:
        return set(self.var_to_node_ids.get(var_name, set()))


# =========================
# Solver adapter
# =========================

class SolverAdapter:
    def __init__(self, store: ConstraintStore):
        self.store = store

    def is_sat(self, extra: list[Pred] | None = None) -> bool:
        # Placeholder. Real implementation should translate AST to solver calls.
        return True

    def model(self, extra: list[Pred] | None = None) -> dict[str, Any]:
        return {}

    def entails(self, pred: Pred) -> bool:
        return False

    def unsat_core_rule_ids(self, extra: list[Pred] | None = None) -> set[str]:
        return set()


# =========================
# Projection analysis
# =========================

def collect_breakpoints(var_name: str, preds: list[Pred]) -> list[Any]:
    points = set()

    def visit(pred: Pred):
        if isinstance(pred, (Eq, Ne, Lt, Le, Gt, Ge)):
            if isinstance(pred.left, Var) and pred.left.name == var_name and isinstance(pred.right, Const):
                points.add(pred.right.value)
            if isinstance(pred.right, Var) and pred.right.name == var_name and isinstance(pred.left, Const):
                points.add(pred.left.value)

        elif isinstance(pred, And):
            for item in pred.items:
                visit(item)

        elif isinstance(pred, Or):
            for item in pred.items:
                visit(item)

        elif isinstance(pred, Not):
            visit(pred.item)

        elif isinstance(pred, Implies):
            visit(pred.cond)
            visit(pred.cons)

    for p in preds:
        visit(p)

    return sorted(points)


class ProjectionAnalyzer:
    def __init__(self, store: ConstraintStore, index: DependencyIndex, solver: SolverAdapter):
        self.store = store
        self.index = index
        self.solver = solver

    def range_of(self, var_name: str) -> ExplainedRange:
        rule_ids = self.index.nodes_for_var(var_name)
        preds = [self.store.prov.nodes[rid].pred for rid in rule_ids]

        points = collect_breakpoints(var_name, preds)

        segments: list[RangeSegment] = []
        boundaries: list[BoundaryPoint] = []

        # Placeholder: in a real implementation we would build segments around points
        # and query SAT/UNSAT for each of them.
        if points:
            boundaries.append(
                BoundaryPoint(
                    value=points[0],
                    kind="candidate",
                    rule_ids=set(rule_ids),
                    node_ids=set(rule_ids),
                    note="Collected from rules mentioning the variable",
                )
            )

        segments.append(
            RangeSegment(
                left=None,
                right=None,
                left_closed=False,
                right_closed=False,
                allowed=True,
                support_rule_ids=set(rule_ids),
                support_node_ids=set(rule_ids),
                note="Placeholder segment. Replace with SAT-based slicing.",
            )
        )

        return ExplainedRange(
            var_name=var_name,
            segments=segments,
            boundaries=boundaries,
            relational_notes=[],
        )


# =========================
# Public engine
# =========================

class ConstraintEngine:
    def __init__(self):
        self.store = ConstraintStore()
        self.index = DependencyIndex()
        self.solver = SolverAdapter(self.store)
        self.projections = ProjectionAnalyzer(self.store, self.index, self.solver)

    def add_var(self, name: str, sort: str) -> None:
        self.store.add_variable(Variable(name=name, sort=sort))

    def add_rule(self, rule_id: str, pred: Pred, label: str = "") -> None:
        rule = Rule(rule_id=rule_id, label=label, pred=pred)
        self.store.add_rule(rule)

        var_names = extract_vars_pred(pred)
        self.index.register(rule_id, var_names)

    def is_sat(self) -> bool:
        return self.solver.is_sat()

    def range_of(self, var_name: str) -> ExplainedRange:
        return self.projections.range_of(var_name)


# =========================
# Example usage
# =========================

if __name__ == "__main__":
    engine = ConstraintEngine()

    engine.add_var("A", "int")
    engine.add_var("B", "int")
    engine.add_var("C", "int")

    engine.add_rule(
        "r1",
        Implies(
            Gt(Var("A"), Const(5)),
            Lt(Var("B"), Const(4)),
        ),
        label="If A > 5 then B < 4",
    )

    engine.add_rule(
        "r2",
        Implies(
            Lt(Var("B"), Const(4)),
            Eq(Var("C"), Const(1)),
        ),
        label="If B < 4 then C = 1",
    )

    print("SAT:", engine.is_sat())
    print("Range(B):", engine.range_of("B"))
    print("Range(C):", engine.range_of("C"))
```

---

# 27. Совсем краткое саммари обсуждения

- без исходных доменов нельзя честно мыслить в терминах “локальный диапазон переменной как источник истины”;
- правила задают **общее пространство решений**;
- диапазоны — это **проекции**;
- одних диапазонов мало, потому что теряются реляционные зависимости;
- нужен **separate provenance layer**, чтобы каждая граница / сегмент диапазона могла ссылаться на исходные правила;
- missing piece в архитектуре — это именно **explained projection layer**:
  - slicing по переменной,
  - segmentation оси,
  - SAT/UNSAT по сегментам,
  - support/block explanation,
  - подъём к стартовым правилам через provenance DAG.

---

# 28. Самое короткое инженерное резюме

Если свести всё в одну фразу:

> Тебе нужен не просто движок ограничений, а движок **объяснимых проекций** над инкрементальной базой ограничений.

И лучший первый прочный каркас для этого:

- AST
- ConstraintStore
- ProvenanceGraph
- DependencyIndex
- SolverAdapter
- ProjectionAnalyzer
- ExplainedRange / RangeSegment / BoundaryPoint

Это уже нормальный скелет, а не абстрактная философская слизь.
