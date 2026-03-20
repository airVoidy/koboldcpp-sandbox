from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from .checklist import HypothesisEntry, HypothesisResult
from ..outcomes import StepSnapshot


class ProblemCase(Protocol):
    case_id: str

    def build_initial_context(self) -> Mapping[str, Any]: ...

    def build_checklist(self) -> list[HypothesisEntry]: ...

    def reconcile(self, results: list[HypothesisResult]) -> StepSnapshot: ...
