from kobold_sandbox.reactive import ReactiveAtom, evaluate_atom
from kobold_sandbox.rule_dsl import Rule, all_different, eq, exactly_one, next_to, ref, right_of


def test_rule_dsl_renders_python_for_relative_and_absolute_rules() -> None:
    norwegian = Rule(
        rule_id="norwegian-first",
        op=eq(ref("nationality_by_house", "house-1"), "norwegian"),
    )
    blue = Rule(
        rule_id="norwegian-next-to-blue",
        op=next_to(ref("nationality_house", "norwegian"), ref("color_house", "blue")),
    )
    green = Rule(
        rule_id="green-right-of-white",
        op=right_of(ref("color_house", "green"), ref("color_house", "white")),
    )

    assert norwegian.to_assertion() == "assert rule_eq(nationality_by_house['house-1'], 'norwegian')"
    assert blue.to_assertion() == "assert rule_next_to(nationality_house['norwegian'], color_house['blue'])"
    assert green.to_assertion() == "assert rule_right_of(color_house['green'], color_house['white'], 1)"


def test_reactive_atom_from_rule_evaluates_correctly() -> None:
    rule = Rule(
        rule_id="norwegian-next-to-blue",
        op=next_to(ref("nationality_house", "norwegian"), ref("color_house", "blue")),
    )
    atom = ReactiveAtom.from_rule(rule)

    passed = evaluate_atom(atom, {"nationality_house": {"norwegian": 1}, "color_house": {"blue": 2}})
    failed = evaluate_atom(atom, {"nationality_house": {"norwegian": 1}, "color_house": {"blue": 4}})

    assert passed.passed is True
    assert failed.passed is False
    assert atom.variables == ("nationality_house", "color_house")


def test_rule_dsl_supports_collection_ops() -> None:
    all_diff = Rule(
        rule_id="all-diff",
        op=all_different(
            ref("color_house", "red"),
            ref("color_house", "green"),
            ref("color_house", "white"),
        ),
    )
    ex_one = Rule(
        rule_id="exactly-one",
        op=exactly_one(
            ref("einstein_color_cell", "house-1:red"),
            ref("einstein_color_cell", "house-1:green"),
            ref("einstein_color_cell", "house-1:blue"),
        ),
    )

    assert all_diff.to_assertion().startswith("assert rule_all_different(")
    assert ex_one.to_assertion().startswith("assert rule_exactly_one(")
