from kobold_sandbox.assertions import ClaimStatus, HypothesisTree
from kobold_sandbox.hypothesis_runtime import HypothesisRuntime
from kobold_sandbox.reactive import ReactiveAtom
from kobold_sandbox.assertions import AtomicClaim


def test_hypothesis_runtime_evaluates_active_connected_component() -> None:
    tree = HypothesisTree.from_problem("Einstein Puzzle")

    red_claim = AtomicClaim(
        claim_id="house-1__red__yes",
        title="house-1 is red",
        python_code="assert einstein_color_cell['house-1:red'] == 'yes'",
        variables=("einstein_color_cell",),
        status=ClaimStatus.HYPOTHESIS,
        consequences=["house-1-color-fixed", "reject house-1 blue"],
    )
    english_claim = AtomicClaim(
        claim_id="englishman__house-1",
        title="englishman in house-1",
        python_code="assert nationality_by_house['house-1'] == 'englishman'",
        variables=("nationality_by_house",),
        status=ClaimStatus.HYPOTHESIS,
        consequences=["englishman-red-link"],
    )
    blue_claim = AtomicClaim(
        claim_id="house-2__blue__yes",
        title="house-2 is blue",
        python_code="assert einstein_color_cell['house-2:blue'] == 'yes'",
        variables=("einstein_color_cell",),
        status=ClaimStatus.REJECTED,
        consequences=["should-not-appear"],
    )

    red = tree.create_child(tree.root, red_claim, related_cells=("einstein-color:house-1:red",))
    english = tree.create_child(tree.root, english_claim, related_cells=("einstein-color:house-1:red", "einstein-nationality:house-1:englishman"))
    blue = tree.create_child(tree.root, blue_claim, related_cells=("einstein-color:house-2:blue",))

    red.link_hypothesis(english.node_id)
    english.link_hypothesis(red.node_id)
    blue.link_hypothesis(red.node_id)

    runtime = HypothesisRuntime()
    runtime.attach_atom(red, ReactiveAtom.from_claim(red_claim))
    runtime.attach_atom(english, ReactiveAtom.from_claim(english_claim))
    runtime.attach_atom(blue, ReactiveAtom.from_claim(blue_claim))

    reaction = runtime.evaluate_connected(
        tree,
        red.node_id,
        {
            "einstein_color_cell": {"house-1:red": "yes", "house-2:blue": "no"},
            "nationality_by_house": {"house-1": "englishman"},
        },
    )

    assert reaction.root_hypothesis_id == "house-1-red-yes"
    assert reaction.checked_hypothesis_ids == ("house-1-red-yes", "englishman-house-1")
    assert reaction.affected_hypothesis_ids == ("house-1-red-yes", "englishman-house-1")
    assert reaction.affected_cells == (
        "einstein-color:house-1:red",
        "einstein-nationality:house-1:englishman",
    )
    assert reaction.consequences == (
        "house-1-color-fixed",
        "reject house-1 blue",
        "englishman-red-link",
    )
    assert all(result.passed for result in reaction.results)


def test_hypothesis_runtime_reports_failed_connected_hypothesis() -> None:
    tree = HypothesisTree.from_problem("Mini")
    first_claim = AtomicClaim(
        claim_id="a__yes",
        title="A yes",
        python_code="assert board['a'] == 'yes'",
        variables=("board",),
        status=ClaimStatus.HYPOTHESIS,
        consequences=["a-fixed"],
    )
    second_claim = AtomicClaim(
        claim_id="b__yes",
        title="B yes",
        python_code="assert board['b'] == 'yes'",
        variables=("board",),
        status=ClaimStatus.HYPOTHESIS,
        consequences=["b-fixed"],
    )
    first = tree.create_child(tree.root, first_claim, related_cells=("grid:a",))
    second = tree.create_child(tree.root, second_claim, related_cells=("grid:b",))
    first.link_hypothesis(second.node_id)
    second.link_hypothesis(first.node_id)

    runtime = HypothesisRuntime()
    runtime.attach_atom(first, ReactiveAtom.from_claim(first_claim))
    runtime.attach_atom(second, ReactiveAtom.from_claim(second_claim))

    reaction = runtime.evaluate_connected(
        tree,
        first.node_id,
        {"board": {"a": "yes", "b": "no"}},
    )

    assert reaction.checked_hypothesis_ids == ("a-yes", "b-yes")
    assert reaction.affected_hypothesis_ids == ("a-yes",)
    assert reaction.affected_cells == ("grid:a",)
    assert reaction.consequences == ("a-fixed",)
    assert reaction.results[1].passed is False


def test_hypothesis_runtime_builds_dependency_graph_automatically() -> None:
    tree = HypothesisTree.from_problem("Graph")
    runtime = HypothesisRuntime()

    left_claim = AtomicClaim(
        claim_id="left",
        title="Left",
        python_code="assert board['a'] == 'yes'",
        variables=("board",),
        status=ClaimStatus.HYPOTHESIS,
        consequences=["shared-semantic"],
    )
    middle_claim = AtomicClaim(
        claim_id="middle",
        title="Middle",
        python_code="assert board['b'] == 'yes'",
        variables=("board",),
        status=ClaimStatus.HYPOTHESIS,
    )
    right_claim = AtomicClaim(
        claim_id="right",
        title="Right",
        python_code="assert other['x'] == 1",
        variables=("other",),
        status=ClaimStatus.HYPOTHESIS,
    )

    left = tree.create_child(tree.root, left_claim, related_cells=("grid:a",))
    middle = tree.create_child(tree.root, middle_claim, related_cells=("grid:b",))
    right = tree.create_child(tree.root, right_claim, related_cells=("grid:z",))
    middle.assumptions.append("shared-semantic")
    runtime.attach_atom(left, ReactiveAtom.from_claim(left_claim))
    runtime.attach_atom(middle, ReactiveAtom.from_claim(middle_claim))
    runtime.attach_atom(right, ReactiveAtom.from_claim(right_claim))

    graph = runtime.build_dependency_graph(tree)

    assert graph.adjacency[left.node_id] == (middle.node_id,)
    assert graph.adjacency[middle.node_id] == (left.node_id,)
    assert graph.adjacency[right.node_id] == ()
    assert any("shared-variable" in reason or "semantic-overlap" in reason for reason in graph.reasons[f"{left.node_id}->{middle.node_id}"])
