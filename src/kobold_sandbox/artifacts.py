from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class EffectKind(str, Enum):
    DOMAIN_NARROWING = "domain_narrowing"
    FIXED_ASSIGNMENT = "fixed_assignment"
    REJECTION = "rejection"
    DERIVED_CONSTRAINT = "derived_constraint"
    CONTRADICTION = "contradiction"
    BRANCH_SPLIT = "branch_split"
    CANDIDATE_CLOUD = "candidate_cloud"
    STATE_PATCH = "state_patch"


@dataclass(frozen=True)
class RuntimeRef:
    module: str
    callable: str
    code_hash: str = ""


@dataclass(frozen=True)
class SubjectRef:
    subject_id: str
    kind: str
    path: str


@dataclass(frozen=True)
class DomainRef:
    domain_id: str
    kind: str
    payload: dict


@dataclass(frozen=True)
class JustificationRef:
    ref_id: str
    kind: str
    path: str = ""


@dataclass(frozen=True)
class StateTransformation:
    transformation_id: str
    kind: EffectKind
    subject_ref: SubjectRef
    next_domain_ref: DomainRef
    previous_domain_ref: DomainRef | None = None
    justification_refs: tuple[JustificationRef, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EffectArtifact:
    artifact_id: str
    format: str
    producer_constraint_id: str
    transformations: tuple[StateTransformation, ...] = ()
    runtime_output_ref: RuntimeRef | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
