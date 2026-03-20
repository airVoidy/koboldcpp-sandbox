from kobold_sandbox.cases.einstein import (
    render_reference_solution_markdown,
    render_reference_stage_counts,
    solve_einstein_reference,
    solve_einstein_reference_staged,
)


def test_reference_solver_finds_classic_einstein_solution() -> None:
    solution = solve_einstein_reference()
    state = solution.as_state()

    assert state["nation"] == ["norwegian", "ukrainian", "englishman", "spaniard", "japanese"]
    assert state["color"] == ["yellow", "blue", "red", "white", "green"]
    assert state["drink"] == ["water", "tea", "milk", "orange-juice", "coffee"]
    assert state["smoke"] == ["kool", "chesterfield", "old-gold", "lucky-strike", "parliament"]
    assert state["pet"] == ["fox", "horse", "snails", "dog", "zebra"]


def test_reference_solution_markdown_renders_house_table() -> None:
    markdown = render_reference_solution_markdown()

    assert "# Einstein Reference Solution" in markdown
    assert "| house | nation | color | drink | smoke | pet |" in markdown
    assert "| house-5 | japanese | green | coffee | parliament | zebra |" in markdown


def test_staged_reference_solver_matches_nested_reference_solver() -> None:
    assert solve_einstein_reference_staged() == solve_einstein_reference()


def test_reference_stage_counts_render_expected_progression() -> None:
    markdown = render_reference_stage_counts()

    assert "| colors | 24 |" in markdown
    assert "| nations | 12 |" in markdown
    assert "| drinks | 12 |" in markdown
    assert "| smokes | 8 |" in markdown
    assert "| pets | 1 |" in markdown
