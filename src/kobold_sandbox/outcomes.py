from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .artifacts import EffectArtifact

if TYPE_CHECKING:
    from .hypothesis_runtime import HypothesisReaction


@dataclass(frozen=True)
class BranchOutcome:
    outcome_id: str
    branch_status: str
    root_hypothesis_id: str
    checked_hypothesis_ids: tuple[str, ...]
    affected_hypothesis_ids: tuple[str, ...]
    affected_cells: tuple[str, ...]
    consequences: tuple[str, ...]
    effect_refs: tuple[str, ...] = ()
    notes: str = ""

    @classmethod
    def from_reaction(
        cls,
        reaction: "HypothesisReaction",
        *,
        outcome_id: str,
        branch_status: str = "saturated",
        effect_refs: tuple[str, ...] = (),
        notes: str = "",
    ) -> "BranchOutcome":
        return cls(
            outcome_id=outcome_id,
            branch_status=branch_status,
            root_hypothesis_id=reaction.root_hypothesis_id,
            checked_hypothesis_ids=reaction.checked_hypothesis_ids,
            affected_hypothesis_ids=reaction.affected_hypothesis_ids,
            affected_cells=reaction.affected_cells,
            consequences=reaction.consequences,
            effect_refs=effect_refs,
            notes=notes,
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StepSnapshot:
    step_id: str
    source_outcome_refs: tuple[str, ...]
    new_fixed_cells: tuple[str, ...]
    consequences: tuple[str, ...]
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class OutcomeWriter:
    def __init__(self, node_dir: Path):
        self.node_dir = node_dir
        self.analysis_dir = node_dir / "analysis"
        self.effects_dir = self.analysis_dir / "effects"

    def ensure_dirs(self) -> None:
        self.effects_dir.mkdir(parents=True, exist_ok=True)

    def write_effect_artifact(self, artifact: EffectArtifact) -> Path:
        self.ensure_dirs()
        path = self.effects_dir / f"{artifact.artifact_id}.json"
        path.write_text(json.dumps(artifact.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_branch_outcome(self, outcome: BranchOutcome) -> Path:
        self.ensure_dirs()
        path = self.analysis_dir / "outcome.json"
        path.write_text(json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_step_snapshot(self, snapshot: StepSnapshot) -> Path:
        self.ensure_dirs()
        path = self.analysis_dir / f"{snapshot.step_id}.json"
        path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def render_outcome_table(outcome: BranchOutcome) -> str:
    lines = [
        "| hypothesis_id | checked | affected |",
        "| --- | --- | --- |",
    ]
    affected = set(outcome.affected_hypothesis_ids)
    for hypothesis_id in outcome.checked_hypothesis_ids:
        lines.append(
            f"| {hypothesis_id} | yes | {'yes' if hypothesis_id in affected else 'no'} |"
        )
    return "\n".join(lines)


def render_llm_step_output(
    outcome: BranchOutcome,
    effects: list[EffectArtifact],
    *,
    include_python_block: bool = True,
) -> str:
    lines: list[str] = []
    if include_python_block:
        lines.extend(
            [
                "```python",
                f"outcome_id = {outcome.outcome_id!r}",
                f"branch_status = {outcome.branch_status!r}",
                f"affected_cells = {list(outcome.affected_cells)!r}",
                f"consequences = {list(outcome.consequences)!r}",
                "```",
                "",
            ]
        )
    lines.append("Result:")
    lines.append(f"- root_hypothesis: {outcome.root_hypothesis_id}")
    lines.append(f"- checked: {', '.join(outcome.checked_hypothesis_ids) or '-'}")
    lines.append(f"- affected: {', '.join(outcome.affected_hypothesis_ids) or '-'}")
    lines.append(f"- cells: {', '.join(outcome.affected_cells) or '-'}")
    lines.append(f"- consequences: {', '.join(outcome.consequences) or '-'}")
    if outcome.checked_hypothesis_ids:
        lines.append("")
        lines.append("Hypotheses:")
        lines.append(render_outcome_table(outcome))
    if effects:
        lines.append("- effects:")
        for artifact in effects:
            lines.append(f"  - {artifact.artifact_id}: {len(artifact.transformations)} transformation(s)")
    if outcome.notes:
        lines.append(f"- notes: {outcome.notes}")
    return "\n".join(lines)
