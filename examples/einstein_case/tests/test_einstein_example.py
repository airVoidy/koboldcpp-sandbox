from kobold_sandbox import CellPhase, ClaimStatus
from kobold_sandbox.einstein_example import (
    build_cell_hypothesis_claims,
    build_einstein_case,
    evaluate_einstein_first_step,
    load_einstein_direct_givens,
    load_einstein_relation_candidates,
    materialize_cell_hypothesis_branches,
)
from kobold_sandbox.storage import Sandbox


def test_build_einstein_case_seeds_expected_givens() -> None:
    case = build_einstein_case()

    norwegian_cell = case.boards["nationality"].cell("house-1", "norwegian")
    milk_cell = case.boards["drink"].cell("house-3", "milk")

    assert norwegian_cell.raw_value == "yes"
    assert norwegian_cell.claim.phase == CellPhase.ATOMIC
    assert milk_cell.raw_value == "yes"
    assert milk_cell.claim.phase == CellPhase.ATOMIC
    assert len(case.clue_claims) == 12
    assert len(case.structural_claims) == 55


def test_einstein_relation_clue_is_structured_constraint() -> None:
    case = build_einstein_case()
    right_of = next(claim for claim in case.clue_claims if claim.claim_id == "clue-05-green-right-of-white")

    assert right_of.phase == CellPhase.ATOMIC
    assert right_of.formal_text == "(color_house['green'] == (color_house['white'] + 1))"
    assert right_of.python_code == "assert (color_house['green'] == (color_house['white'] + 1))"
    assert right_of.variables == ("color_house",)


def test_einstein_direct_givens_load_from_formalization_json() -> None:
    givens = load_einstein_direct_givens()

    assert [item.claim_id for item in givens] == ["house-1__norwegian__yes", "house-3__milk__yes"]
    assert givens[0].container == "nationality_by_house"
    assert givens[1].value == "milk"


def test_einstein_relation_candidates_load_from_formalization_json() -> None:
    relations = load_einstein_relation_candidates()

    assert [item.relation_id for item in relations] == [
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
        "ukrainian-tea",
        "old-gold-snails",
        "yellow-kool",
        "lucky-strike-orange-juice",
        "japanese-parliament",
    ]
    assert all(item.relation_kind == "same_house_pair" for item in relations)
    assert relations[0].left.namespace == "nationality_by_house"
    assert relations[0].right.value == "red"


def test_build_cell_hypothesis_claims_returns_yes_no_pair() -> None:
    case = build_einstein_case()
    board = case.boards["color"]

    claims = build_cell_hypothesis_claims(board, "house-1", "red")

    assert [claim.claim_id for claim in claims] == ["house-1__red__yes", "house-1__red__no"]
    assert all(claim.status == ClaimStatus.HYPOTHESIS for claim in claims)
    assert claims[0].python_code == "assert (einstein_color_cell['house-1:red'] == 'yes')"
    assert claims[1].python_code == "assert (einstein_color_cell['house-1:red'] == 'no')"


def test_einstein_case_can_build_canonical_ir() -> None:
    case = build_einstein_case()
    ir = case.to_ir()

    assert ir.universe.problem_id == "einstein-puzzle"
    assert tuple(axis.name for axis in ir.universe.axes) == ("house", "color", "nationality", "drink", "pet", "smoke")
    assert set(ir.grids) == {"color", "nationality", "drink", "pet", "smoke"}
    assert ir.grids["color"].grid_id == "einstein-color"
    assert ir.grids["color"].cells["einstein-color:house-1:red"].domain == ("yes", "no")
    assert any(record.constraint_id == "clue-05-green-right-of-white" for record in ir.constraints)
    assert any(record.constraint_id == "struct-color-house-1" for record in ir.constraints)
    assert any(record.constraint_id == "struct-color-all-different" for record in ir.constraints)


def test_materialize_cell_hypothesis_branches_creates_git_nodes(tmp_path) -> None:
    sandbox = Sandbox(tmp_path)
    sandbox.init(sandbox_name="einstein-sandbox", kobold_url="http://127.0.0.1:5001")
    case = build_einstein_case()

    node_ids = materialize_cell_hypothesis_branches(
        sandbox,
        "root",
        case.boards["color"],
        "house-1",
        "red",
    )
    state = sandbox.load_state()

    assert node_ids == ["house-1-red-yes", "house-1-red-no"]
    assert state.nodes["house-1-red-yes"].branch == "hyp/house-1-red-yes"
    assert state.nodes["house-1-red-no"].branch == "hyp/house-1-red-no"
    assert "einstein-color: house-1 -> red = yes" in sandbox.notes_path("house-1-red-yes").read_text(encoding="utf-8")


def test_einstein_first_step_runs_through_hypothesis_runtime() -> None:
    reaction = evaluate_einstein_first_step(
        {
            "nationality_by_house": {"house-1": "norwegian"},
            "drink_by_house": {"house-3": "milk"},
            "nationality_house": {"norwegian": 1},
            "color_house": {"blue": 2},
        }
    )

    assert reaction.root_hypothesis_id == "house-1-norwegian-yes"
    assert reaction.checked_hypothesis_ids == ("house-1-norwegian-yes", "norwegian-next-to-blue")
    assert reaction.affected_hypothesis_ids == ("house-1-norwegian-yes", "norwegian-next-to-blue")
    assert reaction.affected_cells == (
        "einstein-nationality:house-1:norwegian",
        "einstein-color:house-2:blue",
    )
    assert "house-2 is a blue candidate" in reaction.consequences
