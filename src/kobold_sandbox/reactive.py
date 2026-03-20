from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .assertions import AtomicClaim
from .rule_dsl import Rule
from .rule_runtime import rule_all_different, rule_eq, rule_exactly_one, rule_ne, rule_next_to, rule_right_of


SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "len": len,
    "set": set,
    "sum": sum,
    "min": min,
    "max": max,
    "tuple": tuple,
    "list": list,
    "rule_eq": rule_eq,
    "rule_ne": rule_ne,
    "rule_next_to": rule_next_to,
    "rule_right_of": rule_right_of,
    "rule_all_different": rule_all_different,
    "rule_exactly_one": rule_exactly_one,
}


@dataclass(frozen=True)
class ReactiveAtom:
    atom_id: str
    expression: str
    variables: tuple[str, ...] = ()
    source_claim_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_claim(cls, claim: AtomicClaim) -> "ReactiveAtom":
        expression = claim.python_code or (f"assert {claim.formal_text}" if claim.formal_text else "assert False")
        return cls(
            atom_id=claim.branch_slug(),
            expression=expression,
            variables=claim.variables,
            source_claim_id=claim.claim_id,
            metadata={
                "title": claim.title,
                "status": claim.status.value,
                "phase": claim.phase.value,
            },
        )

    @classmethod
    def from_rule(
        cls,
        rule: Rule,
        *,
        atom_id: str | None = None,
        source_claim_id: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> "ReactiveAtom":
        return cls(
            atom_id=atom_id or rule.rule_id,
            expression=rule.to_assertion(),
            variables=rule.variables(),
            source_claim_id=source_claim_id,
            metadata={"rule_id": rule.rule_id, "description": rule.description, **(metadata or {})},
        )


@dataclass(frozen=True)
class AtomEvaluation:
    atom_id: str
    passed: bool
    variables: tuple[str, ...]
    source_claim_id: str | None = None
    error: str | None = None


class AtomRuntime:
    def __init__(self) -> None:
        self._atoms: dict[str, ReactiveAtom] = {}

    def register(self, atom: ReactiveAtom) -> ReactiveAtom:
        self._atoms[atom.atom_id] = atom
        return atom

    def register_claim(self, claim: AtomicClaim) -> ReactiveAtom:
        return self.register(ReactiveAtom.from_claim(claim))

    def get(self, atom_id: str) -> ReactiveAtom:
        return self._atoms[atom_id]

    def evaluate(self, atom_id: str, context: dict[str, Any]) -> AtomEvaluation:
        return evaluate_atom(self.get(atom_id), context)

    def evaluate_many(self, atom_ids: list[str], context: dict[str, Any]) -> list[AtomEvaluation]:
        return [self.evaluate(atom_id, context) for atom_id in atom_ids]


def evaluate_atom(atom: ReactiveAtom, context: dict[str, Any]) -> AtomEvaluation:
    globals_dict = {"__builtins__": SAFE_BUILTINS}
    locals_dict = dict(context)
    try:
        expression = atom.expression.strip()
        if expression.startswith("assert "):
            exec(expression, globals_dict, locals_dict)
        else:
            result = eval(expression, globals_dict, locals_dict)
            if not result:
                raise AssertionError(f"Expression returned falsy value: {result!r}")
        return AtomEvaluation(
            atom_id=atom.atom_id,
            passed=True,
            variables=atom.variables,
            source_claim_id=atom.source_claim_id,
        )
    except AssertionError as exc:
        return AtomEvaluation(
            atom_id=atom.atom_id,
            passed=False,
            variables=atom.variables,
            source_claim_id=atom.source_claim_id,
            error=str(exc) or "assertion failed",
        )
    except Exception as exc:  # pragma: no cover - kept for API/runtime diagnostics
        return AtomEvaluation(
            atom_id=atom.atom_id,
            passed=False,
            variables=atom.variables,
            source_claim_id=atom.source_claim_id,
            error=f"{type(exc).__name__}: {exc}",
        )
