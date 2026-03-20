from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class Ref:
    namespace: str
    key: str

    def to_python(self) -> str:
        return f"{self.namespace}[{self.key!r}]"

    def variable(self) -> str:
        return self.namespace


@dataclass(frozen=True)
class RelRef:
    anchor: Ref
    relation: str
    params: tuple[object, ...] = ()


@dataclass(frozen=True)
class RuleOp:
    name: str
    args: tuple[object, ...]

    def variables(self) -> tuple[str, ...]:
        ordered: list[str] = []
        for arg in self.args:
            for item in _collect_variables(arg):
                if item not in ordered:
                    ordered.append(item)
        return tuple(ordered)

    def to_python(self) -> str:
        rendered = ", ".join(_render_arg(arg) for arg in self.args)
        return f"{self.name}({rendered})"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    op: RuleOp
    description: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    def variables(self) -> tuple[str, ...]:
        return self.op.variables()

    def to_python(self) -> str:
        return self.op.to_python()

    def to_assertion(self) -> str:
        return f"assert {self.to_python()}"


def ref(namespace: str, key: str) -> Ref:
    return Ref(namespace=namespace, key=key)


def rel(anchor: Ref, relation: str, *params: object) -> RelRef:
    return RelRef(anchor=anchor, relation=relation, params=tuple(params))


def eq(left: object, right: object) -> RuleOp:
    return RuleOp("rule_eq", (left, right))


def ne(left: object, right: object) -> RuleOp:
    return RuleOp("rule_ne", (left, right))


def next_to(left: object, right: object) -> RuleOp:
    return RuleOp("rule_next_to", (left, right))


def right_of(left: object, right: object, distance: int = 1) -> RuleOp:
    return RuleOp("rule_right_of", (left, right, distance))


def all_different(*items: object) -> RuleOp:
    return RuleOp("rule_all_different", tuple(items))


def exactly_one(*items: object) -> RuleOp:
    return RuleOp("rule_exactly_one", tuple(items))


def _render_arg(arg: object) -> str:
    if isinstance(arg, Ref):
        return arg.to_python()
    if isinstance(arg, RelRef):
        params = ", ".join(repr(item) for item in arg.params)
        return f"rel({arg.anchor.to_python()}, {arg.relation!r}{', ' if params else ''}{params})"
    return repr(arg)


def _collect_variables(arg: object) -> Iterable[str]:
    if isinstance(arg, Ref):
        yield arg.variable()
        return
    if isinstance(arg, RelRef):
        yield arg.anchor.variable()
        return
    if isinstance(arg, (tuple, list)):
        for item in arg:
            yield from _collect_variables(item)
