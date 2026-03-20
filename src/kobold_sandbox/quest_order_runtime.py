from __future__ import annotations

from .artifacts import (
    DomainRef,
    EffectArtifact,
    EffectKind,
    JustificationRef,
    RuntimeRef,
    StateTransformation,
    SubjectRef,
)


def derive_corridor_effect_artifact() -> EffectArtifact:
    return EffectArtifact(
        artifact_id="quest-corridor-effect-0001",
        format="constraint-engine-output",
        producer_constraint_id="quest-corridor-derive-author-ilya",
        runtime_output_ref=RuntimeRef(
            module="kobold_sandbox.quest_order_runtime",
            callable="derive_corridor_effect_artifact",
        ),
        transformations=(
            StateTransformation(
                transformation_id="quest-t-author-position",
                kind=EffectKind.DOMAIN_NARROWING,
                subject_ref=SubjectRef(
                    subject_id="author_position",
                    kind="scalar-variable",
                    path="vars/author_position.json",
                ),
                previous_domain_ref=DomainRef(
                    domain_id="author-position-before",
                    kind="interval",
                    payload={"lower": 3, "upper": 4},
                ),
                next_domain_ref=DomainRef(
                    domain_id="author-position-after",
                    kind="singleton",
                    payload={"values": [4]},
                ),
                justification_refs=(
                    JustificationRef("reasoning-r-0007", "reasoning", "reasoning/r-0007.md"),
                    JustificationRef("constraint-corridor", "constraint", "constraints/corridor.json"),
                ),
                metadata={"summary": "Author collapses to position 4"},
            ),
            StateTransformation(
                transformation_id="quest-t-ilya-position",
                kind=EffectKind.DOMAIN_NARROWING,
                subject_ref=SubjectRef(
                    subject_id="position_by_person.ilya",
                    kind="map-entry",
                    path="vars/position_by_person/ilya.json",
                ),
                previous_domain_ref=DomainRef(
                    domain_id="ilya-position-before",
                    kind="interval",
                    payload={"lower": 3, "upper": 3},
                ),
                next_domain_ref=DomainRef(
                    domain_id="ilya-position-after",
                    kind="singleton",
                    payload={"values": [3]},
                ),
                justification_refs=(
                    JustificationRef("reasoning-r-0007", "reasoning", "reasoning/r-0007.md"),
                    JustificationRef("constraint-corridor", "constraint", "constraints/corridor.json"),
                ),
                metadata={"summary": "Ilya collapses to position 3"},
            ),
            StateTransformation(
                transformation_id="quest-t-partial-order",
                kind=EffectKind.CANDIDATE_CLOUD,
                subject_ref=SubjectRef(
                    subject_id="quest-order-state",
                    kind="state-snapshot",
                    path="states/step-0001.json",
                ),
                next_domain_ref=DomainRef(
                    domain_id="quest-order-cloud-0001",
                    kind="candidate-cloud",
                    payload={
                        "fixed": {
                            "1": ["elisey"],
                            "2": ["diana"],
                            "3": ["ilya"],
                            "4": ["author"],
                        },
                        "remaining_positions": {
                            "5": ["anna", "maxim", "sofiya", "lera"],
                            "6": ["anna", "maxim", "sofiya", "lera"],
                            "7": ["anna", "maxim", "sofiya", "lera"],
                        },
                    },
                ),
                justification_refs=(JustificationRef("reasoning-r-0007", "reasoning", "reasoning/r-0007.md"),),
                metadata={"summary": "Remaining search cloud after corridor reduction"},
            ),
        ),
    )
