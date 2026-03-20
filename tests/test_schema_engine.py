from kobold_sandbox.cases.einstein import EINSTEIN_CATEGORY_ORDER, EINSTEIN_SCHEMA_DATA, build_einstein_schema
from kobold_sandbox.core import (
    build_schema_backends,
    build_schema_backends_from_linear,
    EntityRef,
    LogicGenerator,
    PuzzleSchema,
    UniversalPermutationEngine,
    UniversalSieveEngine,
    UniversalValidatorEngine,
    linear_schema_to_puzzle_schema,
    puzzle_schema_to_linear_schema,
)


def test_puzzle_schema_roundtrips_einstein_data() -> None:
    schema = PuzzleSchema.from_dict(EINSTEIN_SCHEMA_DATA)

    assert schema.name == "Einstein's Riddle"
    assert schema.size == 5
    assert schema.categories["color"][0] == "Red"
    assert schema.rules[0].type == "same"
    assert schema.rules[4].type == "directly_right"


def test_logic_generator_builds_working_validator_and_sieve() -> None:
    schema = build_einstein_schema()
    logic = LogicGenerator(schema)
    same_rule = schema.rules[0]
    position_rule = schema.rules[7]

    validator = logic.build_validator(same_rule)
    solved_like_state = [
        {"color": "Yellow", "nation": "Norwegian", "pet": "Fox", "drink": "Water", "smoke": "Kool"},
        {"color": "Blue", "nation": "Ukrainian", "pet": "Horse", "drink": "Tea", "smoke": "Chesterfield"},
        {"color": "Red", "nation": "English", "pet": "Snails", "drink": "Milk", "smoke": "Old Gold"},
        {"color": "White", "nation": "Spanish", "pet": "Dog", "drink": "Juice", "smoke": "Lucky Strike"},
        {"color": "Green", "nation": "Japanese", "pet": "Zebra", "drink": "Coffee", "smoke": "Parliament"},
    ]
    assert validator(solved_like_state) is True

    sieve = logic.build_sieve(position_rule)
    sieve_state = UniversalSieveEngine(schema).initial_state()
    changed = sieve(sieve_state)
    assert changed is True
    assert sieve_state[2]["drink"] == {"Milk"}


def test_logic_generator_builds_atomic_lambdas_from_schema_rules() -> None:
    schema = build_einstein_schema()
    logic = LogicGenerator(schema)

    same_atomic = logic.build_atomic_lambda(schema.rules[0])
    positional_atomic = logic.build_atomic_lambda(schema.rules[4])
    fixed_atomic = logic.build_atomic_lambda(schema.rules[7])

    assert same_atomic.relation_kind == "same_house_pair"
    assert same_atomic.left_entity == EntityRef("nation", "English")
    assert same_atomic.right_entity == EntityRef("color", "Red")
    assert positional_atomic.relation_kind == "offset_pair"
    assert positional_atomic.distance == 1
    assert fixed_atomic.relation_kind == "position_fixed"
    assert fixed_atomic.right_entity.entity_type == "position"
    assert fixed_atomic.right_entity.entity_id == "2"


def test_universal_permutation_engine_solves_einstein_schema() -> None:
    engine = UniversalPermutationEngine(build_einstein_schema(), category_order=EINSTEIN_CATEGORY_ORDER)
    solution = engine.solve()

    assert solution[0]["nation"] == "Norwegian"
    assert solution[0]["color"] == "Yellow"
    assert solution[0]["drink"] == "Water"
    assert solution[4]["nation"] == "Japanese"
    assert solution[4]["pet"] == "Zebra"
    assert solution[4]["smoke"] == "Parliament"


def test_universal_permutation_engine_renders_stage_counts() -> None:
    engine = UniversalPermutationEngine(build_einstein_schema(), category_order=EINSTEIN_CATEGORY_ORDER)
    markdown = engine.render_stage_counts()

    assert "# Einstein's Riddle Stage Counts" in markdown
    assert "| color | 24 |" in markdown
    assert "| nation | 12 |" in markdown
    assert "| drink | 12 |" in markdown
    assert "| smoke | 8 |" in markdown
    assert "| pet | 1 |" in markdown


def test_universal_sieve_engine_derives_partial_einstein_state() -> None:
    engine = UniversalSieveEngine(build_einstein_schema())
    state = engine.run_until_fixpoint()

    assert state[0]["nation"] == {"Norwegian"}
    assert state[1]["color"] == {"Blue"}
    assert state[2]["drink"] == {"Milk"}
    assert "Green" not in state[0]["color"]
    assert "White" not in state[4]["color"]


def test_universal_sieve_engine_renders_state_table() -> None:
    engine = UniversalSieveEngine(build_einstein_schema())
    markdown = engine.render_state()

    assert "# Einstein's Riddle Sieve State" in markdown
    assert "| house | color | nation | pet | drink | smoke |" in markdown
    assert "| house-1 |" in markdown


def test_permutation_engine_accepts_sieve_state_as_pruning_input() -> None:
    schema = build_einstein_schema()
    sieve_engine = UniversalSieveEngine(schema)
    sieve_state = sieve_engine.run_until_fixpoint()
    permutation_engine = UniversalPermutationEngine(schema, category_order=EINSTEIN_CATEGORY_ORDER)

    solution = permutation_engine.solve(sieve_state=sieve_state)

    assert solution[0]["nation"] == "Norwegian"
    assert solution[1]["color"] == "Blue"
    assert solution[4]["pet"] == "Zebra"


def test_sieve_pruning_reduces_early_stage_counts() -> None:
    schema = build_einstein_schema()
    sieve_engine = UniversalSieveEngine(schema)
    sieve_state = sieve_engine.run_until_fixpoint()
    permutation_engine = UniversalPermutationEngine(schema, category_order=EINSTEIN_CATEGORY_ORDER)

    plain = permutation_engine.render_stage_counts()
    pruned = permutation_engine.render_stage_counts(sieve_state=sieve_state)

    assert "| color | 24 |" in plain
    assert "| color | 2 |" in pruned
    assert "| nation | 12 |" in plain
    assert "| nation | 7 |" in pruned
    assert "| drink | 5 |" in pruned
    assert "| smoke | 3 |" in pruned


def test_universal_validator_engine_accepts_reference_solution() -> None:
    schema = build_einstein_schema()
    permutation_engine = UniversalPermutationEngine(schema, category_order=EINSTEIN_CATEGORY_ORDER)
    validator = UniversalValidatorEngine(schema)

    solution = permutation_engine.solve()

    assert validator.is_valid(solution) is True


def test_universal_validator_engine_rejects_broken_solution() -> None:
    schema = build_einstein_schema()
    permutation_engine = UniversalPermutationEngine(schema, category_order=EINSTEIN_CATEGORY_ORDER)
    validator = UniversalValidatorEngine(schema)

    solution = permutation_engine.solve()
    broken = [dict(house) for house in solution]
    broken[0]["color"] = "Blue"

    assert validator.is_valid(broken) is False


def test_puzzle_schema_bridges_to_linear_schema_for_einstein() -> None:
    linear_schema = puzzle_schema_to_linear_schema(build_einstein_schema())

    assert "same(nation:English, color:Red)" in linear_schema.rules
    assert "directly_right(color:White, color:Green)" in linear_schema.rules
    assert "at(nation:Norwegian, 0)" in linear_schema.rules


def test_linear_schema_bridges_back_to_puzzle_schema() -> None:
    linear_schema = puzzle_schema_to_linear_schema(build_einstein_schema())
    rebuilt = linear_schema_to_puzzle_schema(linear_schema, name="Einstein Structured")

    assert rebuilt.name == "Einstein Structured"
    assert rebuilt.size == 5
    assert rebuilt.categories["nation"][0] == "English"
    assert any(rule.type == "same" and rule.fact == ("nation:English", "color:Red") for rule in rebuilt.rules)


def test_build_schema_backends_from_puzzle_schema_returns_ready_engines() -> None:
    bundle = build_schema_backends(build_einstein_schema(), category_order=EINSTEIN_CATEGORY_ORDER)

    assert bundle.puzzle_schema.name == "Einstein's Riddle"
    assert bundle.linear_schema is None
    assert bundle.permutation.solve()[4]["pet"] == "Zebra"
    assert bundle.validator.is_valid(bundle.permutation.solve()) is True


def test_build_schema_backends_from_linear_returns_ready_engines() -> None:
    linear_schema = puzzle_schema_to_linear_schema(build_einstein_schema())
    bundle = build_schema_backends_from_linear(
        linear_schema,
        name="Einstein Structured",
        category_order=EINSTEIN_CATEGORY_ORDER,
    )

    assert bundle.linear_schema is linear_schema
    assert bundle.puzzle_schema.name == "Einstein Structured"
    assert bundle.sieve.run_until_fixpoint()[0]["nation"] == {"Norwegian"}
