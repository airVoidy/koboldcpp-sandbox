from kobold_sandbox.einstein_example import (
    build_einstein_first_step_outcome,
    build_first_text_frontier,
    build_relation_state_sequence_graph,
    render_atomic_rule_uix_html,
    render_atomic_rule_uix_markdown,
    render_einstein_state_table,
    render_relation_check_table,
)
from kobold_sandbox.outcomes import BranchOutcome, OutcomeWriter, render_llm_step_output, render_outcome_table
from kobold_sandbox.storage import Sandbox


def test_outcome_writer_persists_outcome_effect_and_snapshot(tmp_path) -> None:
    sandbox = Sandbox(tmp_path)
    sandbox.init(sandbox_name="outcome-test", kobold_url="http://127.0.0.1:5001")
    node = sandbox.create_node("root", "step-branch", kind="generic")

    outcome, effect, snapshot, llm_text = build_einstein_first_step_outcome(
        {
            "nationality_by_house": {"house-1": "norwegian"},
            "drink_by_house": {"house-3": "milk"},
            "nationality_house": {"norwegian": 1},
            "color_house": {"blue": 2},
        }
    )

    writer = sandbox.outcome_writer(node.id)
    effect_path = writer.write_effect_artifact(effect)
    outcome_path = sandbox.write_branch_outcome(node.id, outcome)
    snapshot_path = sandbox.write_step_snapshot(node.id, snapshot)

    assert effect_path.exists()
    assert outcome_path.exists()
    assert snapshot_path.exists()
    assert "```python" in llm_text
    assert "affected_cells" in llm_text
    assert "Result:" in llm_text


def test_render_llm_step_output_contains_python_and_effect_summary() -> None:
    outcome = BranchOutcome(
        outcome_id="o-1",
        branch_status="saturated",
        root_hypothesis_id="h-1",
        checked_hypothesis_ids=("h-1",),
        affected_hypothesis_ids=("h-1",),
        affected_cells=("grid:a",),
        consequences=("a-fixed",),
        effect_refs=("effects/e-1.json",),
        notes="Example note",
    )

    text = render_llm_step_output(outcome, [])

    assert "```python" in text
    assert "outcome_id = 'o-1'" in text
    assert "- root_hypothesis: h-1" in text
    assert "| hypothesis_id | checked | affected |" in text
    assert "| h-1 | yes | yes |" in text
    assert "- notes: Example note" in text


def test_render_outcome_table_marks_checked_and_affected_rows() -> None:
    outcome = BranchOutcome(
        outcome_id="o-2",
        branch_status="contradicted",
        root_hypothesis_id="h-1",
        checked_hypothesis_ids=("h-1", "h-2"),
        affected_hypothesis_ids=("h-1",),
        affected_cells=(),
        consequences=(),
    )

    table = render_outcome_table(outcome)

    assert "| hypothesis_id | checked | affected |" in table
    assert "| h-1 | yes | yes |" in table
    assert "| h-2 | yes | no |" in table


def test_render_relation_check_table_uses_live_relation_outcome() -> None:
    table = render_relation_check_table(
        "englishman-red",
        {
            "nationality_by_house": {"house-2": "englishman"},
            "color_by_house": {"house-2": "red"},
        },
        house="house-2",
    )

    assert "| hypothesis_id | checked | affected |" in table
    assert "| englishman-house-2 | yes | yes |" in table
    assert "| house-2-red-yes | yes | yes |" in table


def test_render_einstein_state_table_shows_filled_cells_after_sequence() -> None:
    entries, context = build_first_text_frontier()
    graph = build_relation_state_sequence_graph(entries, context, max_depth=7)

    deepest = max(graph.nodes.values(), key=lambda node: (node.depth, node.node_id))
    assert deepest.depth == 3
    table = render_einstein_state_table(deepest.snapshot.values)

    assert "| house | nationality | color | drink | pet | smoke |" in table
    assert "| house-1 | englishman | red | - | snails | old-gold |" in table
    assert "| house-2 | spaniard | yellow | - | dog | kool |" in table
    assert "| house-3 | ukrainian | - | tea | - | - |" in table
    assert "| house-4 | - | white | - | - | - |" in table
    assert "| house-5 | - | green | coffee | - | - |" in table


def test_render_atomic_rule_uix_markdown_shows_rules_field_and_stages() -> None:
    markdown = render_atomic_rule_uix_markdown()

    assert "# Einstein Atomic Rule UIX" in markdown
    assert "## Atomic Rules" in markdown
    assert "| rule_id | stage | relation_kind | left | right |" in markdown
    assert "| englishman-red | entity-link | same_house_pair | englishman | red |" in markdown
    assert "## Base Field" in markdown
    assert "| slot | candidates | rules | z_exclusions |" in markdown
    assert "## Stage `entity-link`" in markdown
    assert "## Stage `positional-filter`" in markdown


def test_render_atomic_rule_uix_html_contains_interactive_sections() -> None:
    html = render_atomic_rule_uix_html()

    assert "<title>Einstein Atomic Rule UIX</title>" in html
    assert 'id="stage-list"' in html
    assert 'id="rule-list"' in html
    assert 'id="field-view"' in html
    assert 'id="rule-signature"' in html
    assert "const payload =" in html
    assert "trigger-row" in html
