from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class Expr:
    def to_python(self) -> str:
        raise NotImplementedError

    def variables(self) -> tuple[str, ...]:
        raise NotImplementedError


class Pred:
    def to_python(self) -> str:
        raise NotImplementedError

    def variables(self) -> tuple[str, ...]:
        raise NotImplementedError


@dataclass(frozen=True)
class ExactlyOne(Pred):
    items: tuple[Expr, ...]

    def to_python(self) -> str:
        rendered = ", ".join(item.to_python() for item in self.items)
        return f"(sum(1 for value in ({rendered}) if value) == 1)"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(*(item.variables() for item in self.items))


@dataclass(frozen=True)
class AllDifferent(Pred):
    items: tuple[Expr, ...]

    def to_python(self) -> str:
        rendered = ", ".join(item.to_python() for item in self.items)
        values = f"({rendered})"
        return f"(len(set({values})) == len({values}))"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(*(item.variables() for item in self.items))


@dataclass(frozen=True)
class Add(Expr):
    left: Expr
    right: Expr

    def to_python(self) -> str:
        return f"({self.left.to_python()} + {self.right.to_python()})"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(self.left.variables(), self.right.variables())


@dataclass(frozen=True)
class Sub(Expr):
    left: Expr
    right: Expr

    def to_python(self) -> str:
        return f"({self.left.to_python()} - {self.right.to_python()})"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(self.left.variables(), self.right.variables())


@dataclass(frozen=True)
class Abs(Expr):
    item: Expr

    def to_python(self) -> str:
        return f"abs({self.item.to_python()})"

    def variables(self) -> tuple[str, ...]:
        return self.item.variables()


@dataclass(frozen=True)
class Var(Expr):
    name: str

    def to_python(self) -> str:
        return self.name

    def variables(self) -> tuple[str, ...]:
        return (self.name,)


@dataclass(frozen=True)
class Const(Expr):
    value: object

    def to_python(self) -> str:
        return repr(self.value)

    def variables(self) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True)
class Item(Expr):
    container: str
    key: str

    def to_python(self) -> str:
        return f"{self.container}[{self.key!r}]"

    def variables(self) -> tuple[str, ...]:
        return (self.container,)


@dataclass(frozen=True)
class Eq(Pred):
    left: Expr
    right: Expr

    def to_python(self) -> str:
        return f"({self.left.to_python()} == {self.right.to_python()})"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(self.left.variables(), self.right.variables())


@dataclass(frozen=True)
class Ne(Pred):
    left: Expr
    right: Expr

    def to_python(self) -> str:
        return f"({self.left.to_python()} != {self.right.to_python()})"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(self.left.variables(), self.right.variables())


@dataclass(frozen=True)
class Lt(Pred):
    left: Expr
    right: Expr

    def to_python(self) -> str:
        return f"({self.left.to_python()} < {self.right.to_python()})"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(self.left.variables(), self.right.variables())


@dataclass(frozen=True)
class Le(Pred):
    left: Expr
    right: Expr

    def to_python(self) -> str:
        return f"({self.left.to_python()} <= {self.right.to_python()})"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(self.left.variables(), self.right.variables())


@dataclass(frozen=True)
class Gt(Pred):
    left: Expr
    right: Expr

    def to_python(self) -> str:
        return f"({self.left.to_python()} > {self.right.to_python()})"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(self.left.variables(), self.right.variables())


@dataclass(frozen=True)
class Ge(Pred):
    left: Expr
    right: Expr

    def to_python(self) -> str:
        return f"({self.left.to_python()} >= {self.right.to_python()})"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(self.left.variables(), self.right.variables())


@dataclass(frozen=True)
class InSet(Pred):
    left: Expr
    options: tuple[Expr, ...]

    def to_python(self) -> str:
        rendered = ", ".join(item.to_python() for item in self.options)
        return f"({self.left.to_python()} in ({rendered}))"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(self.left.variables(), *(item.variables() for item in self.options))


@dataclass(frozen=True)
class And(Pred):
    items: tuple[Pred, ...]

    def to_python(self) -> str:
        return "(" + " and ".join(item.to_python() for item in self.items) + ")"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(*(item.variables() for item in self.items))


@dataclass(frozen=True)
class Or(Pred):
    items: tuple[Pred, ...]

    def to_python(self) -> str:
        return "(" + " or ".join(item.to_python() for item in self.items) + ")"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(*(item.variables() for item in self.items))


@dataclass(frozen=True)
class Not(Pred):
    item: Pred

    def to_python(self) -> str:
        return f"(not {self.item.to_python()})"

    def variables(self) -> tuple[str, ...]:
        return self.item.variables()


@dataclass(frozen=True)
class Implies(Pred):
    left: Pred
    right: Pred

    def to_python(self) -> str:
        return f"((not {self.left.to_python()}) or {self.right.to_python()})"

    def variables(self) -> tuple[str, ...]:
        return _merge_vars(self.left.variables(), self.right.variables())


@dataclass(frozen=True)
class ConstraintSpec:
    predicate: Pred
    description: str = ""

    def to_python_expr(self) -> str:
        return self.predicate.to_python()

    def to_assertion(self) -> str:
        return f"assert {self.to_python_expr()}"

    def variables(self) -> tuple[str, ...]:
        return self.predicate.variables()


def _merge_vars(*groups: Iterable[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    for group in groups:
        for item in group:
            if item not in ordered:
                ordered.append(item)
    return tuple(ordered)
