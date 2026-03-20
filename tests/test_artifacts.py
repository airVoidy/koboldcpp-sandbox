from kobold_sandbox import EffectKind
from kobold_sandbox.einstein_example import build_einstein_case
from kobold_sandbox.quest_order_runtime import derive_corridor_effect_artifact


def test_quest_order_runtime_effect_artifact_uses_state_transformations() -> None:
    artifact = derive_corridor_effect_artifact()

    assert artifact.format == "constraint-engine-output"
    assert artifact.producer_constraint_id == "quest-corridor-derive-author-ilya"
    assert artifact.runtime_output_ref is not None
    assert len(artifact.transformations) == 3

    author = artifact.transformations[0]
    assert author.kind == EffectKind.DOMAIN_NARROWING
    assert author.subject_ref.subject_id == "author_position"
    assert author.next_domain_ref.payload == {"values": [4]}

    cloud = artifact.transformations[2]
    assert cloud.kind == EffectKind.CANDIDATE_CLOUD
    assert cloud.next_domain_ref.kind == "candidate-cloud"
    assert cloud.next_domain_ref.payload["fixed"]["4"] == ["author"]


def test_einstein_first_step_effects_are_expressed_as_artifact() -> None:
    case = build_einstein_case()
    artifact = case.first_step_effects()

    assert artifact.artifact_id == "einstein-step-0001"
    assert len(artifact.transformations) == 2
    assert all(item.kind == EffectKind.FIXED_ASSIGNMENT for item in artifact.transformations)
    assert artifact.transformations[0].subject_ref.subject_id == "einstein-nationality:house-1:norwegian"
    assert artifact.transformations[1].next_domain_ref.payload == {"values": ["yes"]}
