from kobold_sandbox.core import ready_hypotheses, run_hypothesis_entry
from kobold_sandbox.einstein_example import (
    EinsteinEnglishmanRedCase,
    EinsteinFirstStepCase,
    build_einstein_first_step_checklist,
    build_englishman_red_checklist,
    build_positional_relation_checklist,
    build_relation_candidate_checklist,
)


def test_ready_hypotheses_filters_by_dependencies() -> None:
    checklist = build_einstein_first_step_checklist()

    ready = ready_hypotheses(checklist, completed_ids={"house-1-norwegian-yes"})

    assert [entry.hypothesis_id for entry in ready] == [
        "house-1-norwegian-yes",
        "norwegian-next-to-blue",
        "house-3-milk-yes",
    ]


def test_einstein_checklist_uses_python_entrypoints() -> None:
    checklist = build_einstein_first_step_checklist()
    dependent = next(entry for entry in checklist if entry.hypothesis_id == "norwegian-next-to-blue")

    assert dependent.entrypoint == "kobold_sandbox.cases.einstein.entrypoints:run_first_step_hypothesis"
    assert dependent.depends_on == ("house-1-norwegian-yes",)
    assert "einstein-color:house-2:blue" in dependent.related_cells


def test_run_hypothesis_entry_executes_einstein_first_step_item() -> None:
    case = EinsteinFirstStepCase()
    entry = next(item for item in case.build_checklist() if item.hypothesis_id == "norwegian-next-to-blue")

    result = run_hypothesis_entry(entry, case.build_initial_context())

    assert result.hypothesis_id == "norwegian-next-to-blue"
    assert result.status == "saturated"
    assert result.passed is True
    assert result.branch_outcome is not None
    assert set(result.branch_outcome.checked_hypothesis_ids) == {"house-1-norwegian-yes", "norwegian-next-to-blue"}
    assert "house-2 is a blue candidate" in result.branch_outcome.consequences


def test_einstein_case_reconciles_passed_results_into_step_snapshot() -> None:
    case = EinsteinFirstStepCase()
    results = [run_hypothesis_entry(entry, case.build_initial_context()) for entry in case.build_checklist()]

    snapshot = case.reconcile(results)

    assert snapshot.step_id == "step-0001"
    assert "analysis/house-1-norwegian-yes/outcome.json" in snapshot.source_outcome_refs
    assert "einstein-color:house-2:blue" in snapshot.new_fixed_cells
    assert "house-2 is a blue candidate" in snapshot.consequences


def test_englishman_red_checklist_builds_five_house_candidates() -> None:
    checklist = build_englishman_red_checklist()

    assert [entry.hypothesis_id for entry in checklist] == [
        "englishman-red-house-1",
        "englishman-red-house-2",
        "englishman-red-house-3",
        "englishman-red-house-4",
        "englishman-red-house-5",
    ]
    assert all(entry.entrypoint == "kobold_sandbox.cases.einstein.entrypoints:run_binary_relation_candidate" for entry in checklist)
    assert checklist[0].metadata["relation_id"] == "englishman-red"
    assert checklist[0].metadata["relation_kind"] == "same_house_pair"
    assert checklist[0].metadata["left"]["namespace"] == "nationality_by_house"
    assert checklist[0].metadata["right"]["namespace"] == "color_by_house"


def test_same_house_pair_builder_expands_all_relation_specs() -> None:
    checklist = build_relation_candidate_checklist()

    assert len(checklist) == 40
    relation_ids = {entry.metadata["relation_id"] for entry in checklist}
    assert relation_ids == {
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
        "ukrainian-tea",
        "old-gold-snails",
        "yellow-kool",
        "lucky-strike-orange-juice",
        "japanese-parliament",
    }
    assert all(entry.metadata["relation_kind"] == "same_house_pair" for entry in checklist)


def test_positional_relation_builder_returns_manual_specs() -> None:
    checklist = build_positional_relation_checklist()

    assert [entry.hypothesis_id for entry in checklist] == [
        "norwegian-next-to-blue",
        "chesterfield-next-to-fox",
        "kool-next-to-horse",
        "green-right-of-white",
    ]
    assert checklist[0].metadata["relation_kind"] == "adjacent_pair"
    assert checklist[1].metadata["relation_kind"] == "adjacent_pair"
    assert checklist[2].metadata["relation_kind"] == "adjacent_pair"
    assert checklist[3].metadata["relation_kind"] == "offset_pair"


def test_englishman_red_candidate_passes_for_single_combination() -> None:
    case = EinsteinEnglishmanRedCase()
    entry = next(item for item in case.build_checklist() if item.hypothesis_id == "englishman-red-house-2")

    result = run_hypothesis_entry(
        entry,
        {
            "nationality_by_house": {"house-2": "englishman"},
            "color_by_house": {"house-2": "red"},
        },
    )

    assert result.passed is True
    assert result.status == "saturated"
    assert result.branch_outcome is not None
    assert set(result.branch_outcome.checked_hypothesis_ids) == {"englishman-house-2", "house-2-red-yes"}
    assert "relation-link:englishman-red:house-2" in result.branch_outcome.affected_cells


def test_englishman_red_candidate_reports_link_collision() -> None:
    case = EinsteinEnglishmanRedCase()
    entry = next(item for item in case.build_checklist() if item.hypothesis_id == "englishman-red-house-2")

    result = run_hypothesis_entry(
        entry,
        {
            "nationality_by_house": {"house-2": "englishman"},
            "color_by_house": {"house-2": "blue"},
        },
    )

    assert result.passed is False
    assert result.status == "contradicted"
    assert result.branch_outcome is not None
    assert result.branch_outcome.affected_hypothesis_ids == ("englishman-house-2",)
    assert "Collision detected for house-2: relation englishman-red is not aligned." == result.notes


def test_englishman_red_candidate_fails_on_base_uniqueness_collision() -> None:
    case = EinsteinEnglishmanRedCase()
    entry = next(item for item in case.build_checklist() if item.hypothesis_id == "englishman-red-house-2")

    result = run_hypothesis_entry(
        entry,
        {
            "nationality_by_house": {"house-2": "englishman", "house-4": "englishman"},
            "color_by_house": {"house-2": "red"},
        },
    )

    assert result.passed is False
    assert result.status == "contradicted"
    assert result.branch_outcome is not None
    assert result.branch_outcome.affected_hypothesis_ids == ("house-2-red-yes",)


def test_adjacent_pair_candidate_passes_for_neighbor_positions() -> None:
    entry = next(item for item in build_positional_relation_checklist() if item.hypothesis_id == "norwegian-next-to-blue")

    result = run_hypothesis_entry(
        entry,
        {
            "nationality_house": {"norwegian": 1},
            "color_house": {"blue": 2},
        },
    )

    assert result.passed is True
    assert result.status == "saturated"
    assert result.branch_outcome is not None
    assert result.branch_outcome.checked_hypothesis_ids == ("norwegian-next-to-blue",)
    assert "relation-link:norwegian-next-to-blue" in result.branch_outcome.affected_cells


def test_adjacent_pair_candidate_reports_collision() -> None:
    entry = next(item for item in build_positional_relation_checklist() if item.hypothesis_id == "norwegian-next-to-blue")

    result = run_hypothesis_entry(
        entry,
        {
            "nationality_house": {"norwegian": 1},
            "color_house": {"blue": 4},
        },
    )

    assert result.passed is False
    assert result.status == "contradicted"
    assert result.notes == "Collision detected for positional relation norwegian-next-to-blue."


def test_adjacent_pair_candidate_fails_on_position_uniqueness_collision() -> None:
    entry = next(item for item in build_positional_relation_checklist() if item.hypothesis_id == "norwegian-next-to-blue")

    result = run_hypothesis_entry(
        entry,
        {
            "nationality_house": {"norwegian": 1},
            "color_house": {"blue": 2, "green": 2},
        },
    )

    assert result.passed is False
    assert result.status == "contradicted"
    assert result.notes == "Collision detected for positional relation norwegian-next-to-blue."


def test_offset_pair_candidate_passes_for_immediate_right_relation() -> None:
    entry = next(item for item in build_positional_relation_checklist() if item.hypothesis_id == "green-right-of-white")

    result = run_hypothesis_entry(
        entry,
        {
            "color_house": {"white": 2, "green": 3},
        },
    )

    assert result.passed is True
    assert result.status == "saturated"
    assert result.branch_outcome is not None
    assert result.branch_outcome.checked_hypothesis_ids == ("green-right-of-white",)


def test_offset_pair_candidate_reports_collision() -> None:
    entry = next(item for item in build_positional_relation_checklist() if item.hypothesis_id == "green-right-of-white")

    result = run_hypothesis_entry(
        entry,
        {
            "color_house": {"white": 2, "green": 5},
        },
    )

    assert result.passed is False
    assert result.status == "contradicted"
    assert result.notes == "Collision detected for positional relation green-right-of-white."


def test_offset_pair_candidate_fails_on_position_bounds_collision() -> None:
    entry = next(item for item in build_positional_relation_checklist() if item.hypothesis_id == "green-right-of-white")

    result = run_hypothesis_entry(
        entry,
        {
            "color_house": {"white": 5, "green": 6},
        },
    )

    assert result.passed is False
    assert result.status == "contradicted"
    assert result.notes == "Collision detected for positional relation green-right-of-white."
