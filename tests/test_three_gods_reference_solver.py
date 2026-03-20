from kobold_sandbox.cases.three_gods import (
    build_default_predicates,
    generate_three_gods_worlds,
    meta_answers,
    render_three_gods_strategy_markdown,
    solve_three_gods_reference,
)


def test_three_gods_world_space_has_12_worlds() -> None:
    worlds = generate_three_gods_worlds()

    assert len(worlds) == 12
    assert {world.da_means_yes for world in worlds} == {False, True}


def test_random_god_can_answer_both_words() -> None:
    worlds = generate_three_gods_worlds()
    random_world = next(world for world in worlds if world.role_of("A") == "Random")
    predicate = next(predicate for predicate in build_default_predicates() if predicate.name == "B is Truth")

    assert meta_answers(random_world, "A", predicate) == ("DA", "JA")


def test_three_gods_strategy_solves_world_in_3_questions() -> None:
    strategy = solve_three_gods_reference()
    worlds = generate_three_gods_worlds()

    assert strategy.respondent is not None
    assert strategy.branches is not None
    assert set(strategy.branches) <= {"DA", "JA"}
    assert all(child.possible_worlds for child in strategy.branches.values())

    def assert_leaves(node) -> None:
        if node.is_leaf:
            assert len({worlds[index].roles for index in node.possible_worlds}) == 1
            return
        for child in (node.branches or {}).values():
            assert_leaves(child)

    assert_leaves(strategy)


def test_three_gods_strategy_markdown_renders_question_tree() -> None:
    markdown = render_three_gods_strategy_markdown()

    assert "# Three Gods Strategy" in markdown
    assert "If I asked you whether" in markdown
    assert "Resolved roles:" in markdown
