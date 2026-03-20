from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..outcomes import BranchOutcome


@dataclass(frozen=True)
class HypothesisEntry:
    hypothesis_id: str
    title: str
    entrypoint: str
    context_refs: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    related_cells: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HypothesisResult:
    hypothesis_id: str
    title: str
    entrypoint: str
    status: str
    passed: bool
    effect_refs: tuple[str, ...] = ()
    affected_subject_refs: tuple[str, ...] = ()
    derived_hypothesis_ids: tuple[str, ...] = ()
    notes: str = ""
    worker_output: str = ""
    branch_outcome: BranchOutcome | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def ready_hypotheses(entries: list[HypothesisEntry], completed_ids: set[str]) -> list[HypothesisEntry]:
    return [entry for entry in entries if set(entry.depends_on).issubset(completed_ids)]
