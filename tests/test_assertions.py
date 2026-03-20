from kobold_sandbox.assertions import (
    CellPhase,
    ClaimStatus,
    HypothesisTree,
    TabularAssertionBoard,
    ValueRange,
)
from kobold_sandbox.constraints import AllDifferent, And, Const, ConstraintSpec, Eq, ExactlyOne, InSet, Item, Ne
from kobold_sandbox.storage import Sandbox


def test_tabular_assertion_board_tracks_known_formal_and_atomic_steps() -> None:
    board = TabularAssertionBoard(
        name="einstein-colors",
        rows=("house-1", "house-2"),
        columns=("color", "owner"),
    )

    claim = board.seed_claim(
        "house-1",
        "color",
        "red",
        formal_text="house_color['house-1'] == 'red'",
        python_code="assert house_color['house-1'] == 'red'",
        variables=("house_color",),
        status=ClaimStatus.GIVEN,
    )

    assert claim.claim_id == "house-1__color"
    assert claim.phase == CellPhase.ATOMIC
    assert board.cell("house-1", "color").raw_value == "red"
    assert board.unresolved_claims()
    assert "house-2" in board.to_markdown()


def test_unresolved_claims_include_uncertain_ranges() -> None:
    board = TabularAssertionBoard(
        name="sudoku-row",
        rows=("r1c1",),
        columns=("digit",),
    )

    board.seed_claim(
        "r1c1",
        "digit",
        "candidate",
        status=ClaimStatus.HYPOTHESIS,
        value_range=ValueRange.from_values(["1", "3", "7"]),
    )

    unresolved = board.unresolved_claims()
    assert len(unresolved) == 1
    assert unresolved[0].value_range is not None
    assert unresolved[0].value_range.values == ("1", "3", "7")


def test_hypothesis_tree_creates_git_friendly_children() -> None:
    board = TabularAssertionBoard(
        name="einstein-owner",
        rows=("house-1",),
        columns=("owner",),
    )
    claim = board.seed_claim(
        "house-1",
        "owner",
        "norwegian",
        formal_text="owner['house-1'] == 'norwegian'",
        variables=("owner",),
        status=ClaimStatus.HYPOTHESIS,
    )
    claim.consequences.extend(
        [
            "house_index['norwegian'] == 1",
            "owner['house-1'] != 'german'",
        ]
    )

    tree = HypothesisTree.from_problem("Einstein Puzzle")
    child = tree.create_child(tree.root, claim)

    assert child.branch_name == "hyp/house-1-owner"
    assert child.assumptions == ["house-1__owner"]
    assert child.consequences == claim.consequences
    assert child.lineage() == ["einstein-puzzle", "house-1-owner"]
    assert tree.pending_nodes() == [child]


def test_sandbox_can_create_real_node_from_claim(tmp_path) -> None:
    sandbox = Sandbox(tmp_path)
    sandbox.init(sandbox_name="test-sandbox", kobold_url="http://127.0.0.1:5001")

    board = TabularAssertionBoard(
        name="einstein-owner",
        rows=("house-1",),
        columns=("owner",),
    )
    claim = board.seed_claim(
        "house-1",
        "owner",
        "norwegian",
        formal_text="owner['house-1'] == 'norwegian'",
        python_code="assert owner['house-1'] == 'norwegian'",
        variables=("owner",),
        status=ClaimStatus.HYPOTHESIS,
    )
    claim.consequences.append("owner['house-1'] != 'german'")

    node = sandbox.create_claim_node("root", claim, tags=["einstein", "owner"])
    state = sandbox.load_state()

    assert node.id == "house-1-owner"
    assert node.branch == "hyp/house-1-owner"
    assert node.kind == "claim"
    assert node.claim_id == "house-1__owner"
    assert node.assumptions == ["house-1__owner"]
    assert node.consequences == ["owner['house-1'] != 'german'"]
    assert state.active_node_id == node.id
    assert state.nodes[node.id].branch == node.branch
    assert sandbox.workspace_for(node.id).exists()
    assert "owner['house-1'] == 'norwegian'" in sandbox.notes_path(node.id).read_text(encoding="utf-8")


def test_constraint_spec_renders_to_python_and_updates_claim() -> None:
    board = TabularAssertionBoard(
        name="einstein-constraint",
        rows=("house-1",),
        columns=("owner",),
    )
    spec = ConstraintSpec(
        predicate=And(
            (
                Eq(Item("owner", "house-1"), Const("norwegian")),
                Ne(Item("owner", "house-1"), Const("german")),
                InSet(Item("house_index", "norwegian"), (Const(1), Const(2))),
            )
        ),
        description="Hypothesis for the first house owner",
    )

    claim = board.seed_claim(
        "house-1",
        "owner",
        "norwegian?",
        formal_constraint=spec,
        status=ClaimStatus.HYPOTHESIS,
    )
    board.attach_atomic_constraint("house-1", "owner", spec)

    assert claim.phase == CellPhase.ATOMIC
    assert claim.formal_constraint is spec
    assert claim.variables == ("owner", "house_index")
    assert claim.formal_text == "((owner['house-1'] == 'norwegian') and (owner['house-1'] != 'german') and (house_index['norwegian'] in (1, 2)))"
    assert claim.python_code == "assert ((owner['house-1'] == 'norwegian') and (owner['house-1'] != 'german') and (house_index['norwegian'] in (1, 2)))"


def test_sandbox_notes_include_constraint_spec(tmp_path) -> None:
    sandbox = Sandbox(tmp_path)
    sandbox.init(sandbox_name="test-sandbox", kobold_url="http://127.0.0.1:5001")

    board = TabularAssertionBoard(
        name="sudoku-constraint",
        rows=("r1c1",),
        columns=("digit",),
    )
    spec = ConstraintSpec(
        predicate=Eq(Item("grid", "r1c1"), Const(7)),
        description="Resolved sudoku digit",
    )
    claim = board.seed_claim(
        "r1c1",
        "digit",
        "7",
        formal_constraint=spec,
        status=ClaimStatus.CONFIRMED,
    )
    board.attach_atomic_constraint("r1c1", "digit", spec)

    node = sandbox.create_claim_node("root", claim)
    notes = sandbox.notes_path(node.id).read_text(encoding="utf-8")

    assert "## Constraint Spec" in notes
    assert "(grid['r1c1'] == 7)" in notes
    assert "assert (grid['r1c1'] == 7)" in notes


def test_collection_constraints_render_to_python() -> None:
    exactly_one = ConstraintSpec(
        ExactlyOne(
            (
                Item("board", "r1c1:1"),
                Item("board", "r1c1:2"),
                Item("board", "r1c1:3"),
            )
        )
    )
    all_different = ConstraintSpec(
        AllDifferent(
            (
                Item("color_house", "red"),
                Item("color_house", "green"),
                Item("color_house", "white"),
            )
        )
    )

    assert exactly_one.to_python_expr() == "(sum(1 for value in (board['r1c1:1'], board['r1c1:2'], board['r1c1:3']) if value) == 1)"
    assert all_different.to_python_expr() == "(len(set((color_house['red'], color_house['green'], color_house['white']))) == len((color_house['red'], color_house['green'], color_house['white'])))"
