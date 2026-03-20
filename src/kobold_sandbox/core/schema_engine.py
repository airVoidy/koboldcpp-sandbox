from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import permutations
from typing import Any, Literal

from .domain_rules import DomainRuleLambda
from .entity_slots import EntityRef

RuleType = Literal["same", "position", "next_to", "directly_right", "all_different_group"]


@dataclass(frozen=True)
class RuleSpec:
    type: RuleType
    fact: tuple[Any, ...]
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class PuzzleSchema:
    name: str
    size: int
    categories: dict[str, tuple[str, ...]]
    rules: tuple[RuleSpec, ...]
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PuzzleSchema":
        metadata = data["metadata"]
        return cls(
            name=str(metadata["name"]),
            size=int(metadata["size"]),
            categories={key: tuple(values) for key, values in data["categories"].items()},
            rules=tuple(
                RuleSpec(
                    type=rule["type"],
                    fact=tuple(rule["fact"]),
                    metadata={key: value for key, value in rule.items() if key not in {"type", "fact"}},
                )
                for rule in data["rules"]
            ),
            metadata=dict(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": dict(self.metadata or {}) | {"name": self.name, "size": self.size},
            "categories": {key: list(values) for key, values in self.categories.items()},
            "rules": [
                {
                    "type": rule.type,
                    "fact": list(rule.fact),
                    **dict(rule.metadata or {}),
                }
                for rule in self.rules
            ],
        }


@dataclass(frozen=True)
class SchemaBackendBundle:
    puzzle_schema: PuzzleSchema
    linear_schema: Any | None
    logic: "LogicGenerator"
    sieve: "UniversalSieveEngine"
    permutation: "UniversalPermutationEngine"
    validator: "UniversalValidatorEngine"


class LogicGenerator:
    def __init__(self, schema: PuzzleSchema) -> None:
        self.schema = schema

    def _parse_fact(self, fact: str) -> tuple[str, str]:
        category, value = fact.split(":", 1)
        return category, value

    def build_validator(self, rule: RuleSpec):
        def get_position(state: list[dict[str, str]], fact: str | int) -> int:
            if isinstance(fact, int):
                return fact
            category, value = fact.split(":", 1)
            for house_index, house in enumerate(state):
                if house[category] == value:
                    return house_index
            raise ValueError(f"Value {fact!r} not found in solved state.")

        if rule.type in {"same", "position"}:
            return lambda state: get_position(state, rule.fact[0]) == get_position(state, rule.fact[1])
        if rule.type == "next_to":
            return lambda state: abs(get_position(state, rule.fact[0]) - get_position(state, rule.fact[1])) == 1
        if rule.type == "directly_right":
            return lambda state: get_position(state, rule.fact[1]) == get_position(state, rule.fact[0]) + 1
        if rule.type == "all_different_group":
            category = str(rule.fact[0])
            positions = tuple(int(item) for item in rule.fact[1:])
            return lambda state: len({state[position][category] for position in positions}) == len(positions)
        raise ValueError(f"Unsupported rule type: {rule.type}")

    def build_sieve(self, rule: RuleSpec):
        if rule.type == "same":
            left_cat, left_val = self._parse_fact(rule.fact[0])
            right_cat, right_val = self._parse_fact(rule.fact[1])

            def same_sieve(state: list[dict[str, set[str]]]) -> bool:
                changed = False
                for house in state:
                    if house[left_cat] == {left_val}:
                        new_values = house[right_cat] & {right_val}
                        if new_values != house[right_cat]:
                            house[right_cat] = new_values
                            changed = True
                    if left_val not in house[left_cat] and right_val in house[right_cat]:
                        house[right_cat].discard(right_val)
                        changed = True
                    if house[right_cat] == {right_val}:
                        new_values = house[left_cat] & {left_val}
                        if new_values != house[left_cat]:
                            house[left_cat] = new_values
                            changed = True
                    if right_val not in house[right_cat] and left_val in house[left_cat]:
                        house[left_cat].discard(left_val)
                        changed = True
                return changed

            return same_sieve

        if rule.type == "position":
            category, value = self._parse_fact(rule.fact[0])
            target_index = int(rule.fact[1])
            repeated_categories = set((self.schema.metadata or {}).get("repeated_categories", ()))

            def position_sieve(state: list[dict[str, set[str]]]) -> bool:
                changed = False
                for house_index, house in enumerate(state):
                    if house_index == target_index:
                        new_values = house[category] & {value}
                        if new_values != house[category]:
                            house[category] = new_values
                            changed = True
                    elif category not in repeated_categories and value in house[category]:
                        house[category].discard(value)
                        changed = True
                return changed

            return position_sieve

        if rule.type == "next_to":
            left_cat, left_val = self._parse_fact(rule.fact[0])
            right_cat, right_val = self._parse_fact(rule.fact[1])

            def next_to_sieve(state: list[dict[str, set[str]]]) -> bool:
                changed = False
                for house_index, house in enumerate(state):
                    if left_val in house[left_cat]:
                        neighbors = []
                        if house_index > 0:
                            neighbors.append(state[house_index - 1][right_cat])
                        if house_index + 1 < len(state):
                            neighbors.append(state[house_index + 1][right_cat])
                        if not any(right_val in values for values in neighbors):
                            house[left_cat].discard(left_val)
                            changed = True
                    if right_val in house[right_cat]:
                        neighbors = []
                        if house_index > 0:
                            neighbors.append(state[house_index - 1][left_cat])
                        if house_index + 1 < len(state):
                            neighbors.append(state[house_index + 1][left_cat])
                        if not any(left_val in values for values in neighbors):
                            house[right_cat].discard(right_val)
                            changed = True
                return changed

            return next_to_sieve

        if rule.type == "directly_right":
            left_cat, left_val = self._parse_fact(rule.fact[0])
            right_cat, right_val = self._parse_fact(rule.fact[1])

            def directly_right_sieve(state: list[dict[str, set[str]]]) -> bool:
                changed = False
                if left_val in state[len(state) - 1][left_cat]:
                    state[len(state) - 1][left_cat].discard(left_val)
                    changed = True
                if right_val in state[0][right_cat]:
                    state[0][right_cat].discard(right_val)
                    changed = True
                for house_index, house in enumerate(state):
                    if left_val in house[left_cat]:
                        if house_index + 1 >= len(state) or right_val not in state[house_index + 1][right_cat]:
                            house[left_cat].discard(left_val)
                            changed = True
                    if right_val in house[right_cat]:
                        if house_index == 0 or left_val not in state[house_index - 1][left_cat]:
                            house[right_cat].discard(right_val)
                            changed = True
                    if house[left_cat] == {left_val} and house_index + 1 < len(state):
                        new_values = state[house_index + 1][right_cat] & {right_val}
                        if new_values != state[house_index + 1][right_cat]:
                            state[house_index + 1][right_cat] = new_values
                            changed = True
                    if house[right_cat] == {right_val} and house_index > 0:
                        new_values = state[house_index - 1][left_cat] & {left_val}
                        if new_values != state[house_index - 1][left_cat]:
                            state[house_index - 1][left_cat] = new_values
                            changed = True
                return changed

            return directly_right_sieve

        if rule.type == "all_different_group":
            category = str(rule.fact[0])
            positions = tuple(int(item) for item in rule.fact[1:])

            def all_different_group_sieve(state: list[dict[str, set[str]]]) -> bool:
                changed = False
                fixed_values = {
                    next(iter(state[position][category]))
                    for position in positions
                    if len(state[position][category]) == 1
                }
                for position in positions:
                    if len(state[position][category]) > 1:
                        new_values = state[position][category] - fixed_values
                        if new_values != state[position][category]:
                            state[position][category] = new_values
                            changed = True
                candidate_pool: dict[str, list[int]] = {}
                for position in positions:
                    for value in state[position][category]:
                        candidate_pool.setdefault(value, []).append(position)
                for value, candidate_positions in candidate_pool.items():
                    if len(candidate_positions) == 1:
                        target = candidate_positions[0]
                        new_values = state[target][category] & {value}
                        if new_values != state[target][category]:
                            state[target][category] = new_values
                            changed = True
                return changed

            return all_different_group_sieve

        raise ValueError(f"Unsupported rule type: {rule.type}")

    def build_validators(self) -> tuple:
        return tuple(self.build_validator(rule) for rule in self.schema.rules)

    def build_sieves(self) -> tuple:
        return tuple(self.build_sieve(rule) for rule in self.schema.rules)

    def build_atomic_lambda(self, rule: RuleSpec, *, container_type: str = "house_slot") -> DomainRuleLambda:
        if rule.type == "same":
            left_cat, left_val = self._parse_fact(rule.fact[0])
            right_cat, right_val = self._parse_fact(rule.fact[1])
            relation_kind = "same_house_pair"
            distance = 0
        elif rule.type == "next_to":
            left_cat, left_val = self._parse_fact(rule.fact[0])
            right_cat, right_val = self._parse_fact(rule.fact[1])
            relation_kind = "adjacent_pair"
            distance = 1
        elif rule.type == "directly_right":
            right_cat, right_val = self._parse_fact(rule.fact[0])
            left_cat, left_val = self._parse_fact(rule.fact[1])
            relation_kind = "offset_pair"
            distance = 1
        elif rule.type == "position":
            category, value = self._parse_fact(rule.fact[0])
            relation_kind = "position_fixed"
            return DomainRuleLambda(
                rule_id=f"{rule.type}:{category}:{value}:{int(rule.fact[1])}",
                container_type=container_type,
                relation_kind=relation_kind,
                left_type_ref=category,
                right_type_ref="position",
                left_entity=EntityRef(category, value),
                right_entity=EntityRef("position", str(int(rule.fact[1]))),
                distance=0,
                metadata={"rule_type": rule.type, "fact": rule.fact},
            )
        else:
            raise ValueError(f"Unsupported rule type: {rule.type}")

        return DomainRuleLambda(
            rule_id=f"{rule.type}:{left_cat}:{left_val}:{right_cat}:{right_val}",
            container_type=container_type,
            relation_kind=relation_kind,
            left_type_ref=left_cat,
            right_type_ref=right_cat,
            left_entity=EntityRef(left_cat, left_val),
            right_entity=EntityRef(right_cat, right_val),
            distance=distance,
            metadata={"rule_type": rule.type, "fact": rule.fact},
        )

    def build_atomic_lambdas(self, *, container_type: str = "house_slot") -> tuple[DomainRuleLambda, ...]:
        return tuple(self.build_atomic_lambda(rule, container_type=container_type) for rule in self.schema.rules)


class UniversalPermutationEngine:
    def __init__(self, schema: PuzzleSchema, *, category_order: tuple[str, ...] | None = None) -> None:
        self.schema = schema
        self.cat_names = list(category_order or tuple(schema.categories.keys()))
        self.size = schema.size
        self.perms = tuple(permutations(range(self.size)))

    def _get_val_idx(self, fact_str: str) -> tuple[int, int]:
        category, value = fact_str.split(":", 1)
        category_idx = self.cat_names.index(category)
        value_idx = self.schema.categories[category].index(value)
        return category_idx, value_idx

    def _get_position(self, state: tuple[tuple[int, ...], ...], fact: str | int) -> int:
        if isinstance(fact, int):
            return fact
        category_idx, value_idx = self._get_val_idx(fact)
        return state[category_idx].index(value_idx)

    def _check(self, state: tuple[tuple[int, ...], ...], rule: RuleSpec) -> bool:
        try:
            left = self._get_position(state, rule.fact[0])
            right = self._get_position(state, rule.fact[1])
        except (ValueError, IndexError):
            return True

        if rule.type in {"same", "position"}:
            return left == right
        if rule.type == "next_to":
            return abs(left - right) == 1
        if rule.type == "directly_right":
            return right == left + 1
        raise ValueError(f"Unsupported rule type: {rule.type}")

    def _is_ready(self, rule: RuleSpec, current_idx: int) -> bool:
        for fact in rule.fact:
            if isinstance(fact, str):
                category = fact.split(":", 1)[0]
                if self.cat_names.index(category) > current_idx:
                    return False
        return True

    def _permutations_for_category(
        self,
        category_name: str,
        sieve_state: list[dict[str, set[str]]] | None,
    ) -> tuple[tuple[int, ...], ...]:
        if sieve_state is None:
            return self.perms
        allowed_by_house = [
            {self.schema.categories[category_name].index(value) for value in house[category_name]}
            for house in sieve_state
        ]
        return tuple(
            permutation
            for permutation in self.perms
            if all(value_idx in allowed_by_house[house_index] for house_index, value_idx in enumerate(permutation))
        )

    def solve_raw(self, *, sieve_state: list[dict[str, set[str]]] | None = None) -> tuple[tuple[int, ...], ...]:
        stream: list[tuple[tuple[int, ...], ...]] = [()]
        for current_idx in range(len(self.cat_names)):
            new_stream: list[tuple[tuple[int, ...], ...]] = []
            rules_to_check = [rule for rule in self.schema.rules if self._is_ready(rule, current_idx)]
            category_name = self.cat_names[current_idx]
            category_perms = self._permutations_for_category(category_name, sieve_state)
            for state in stream:
                for permutation in category_perms:
                    candidate = state + (permutation,)
                    if all(self._check(candidate, rule) for rule in rules_to_check):
                        new_stream.append(candidate)
            stream = new_stream
        if not stream:
            raise RuntimeError("No solution found for schema.")
        return stream[0]

    def solve(self, *, sieve_state: list[dict[str, set[str]]] | None = None) -> list[dict[str, str]]:
        result = self.solve_raw(sieve_state=sieve_state)
        output: list[dict[str, str]] = []
        for house_index in range(self.size):
            house: dict[str, str] = {}
            for category_idx, category_name in enumerate(self.cat_names):
                value_idx = result[category_idx][house_index]
                house[category_name] = self.schema.categories[category_name][value_idx]
            output.append(house)
        return output

    def render_stage_counts(self, *, sieve_state: list[dict[str, set[str]]] | None = None) -> str:
        stream: list[tuple[tuple[int, ...], ...]] = [()]
        lines = [
            f"# {self.schema.name} Stage Counts",
            "",
            "| step | surviving_states |",
            "| --- | ---: |",
        ]
        for current_idx, category_name in enumerate(self.cat_names):
            new_stream: list[tuple[tuple[int, ...], ...]] = []
            rules_to_check = [rule for rule in self.schema.rules if self._is_ready(rule, current_idx)]
            category_perms = self._permutations_for_category(category_name, sieve_state)
            for state in stream:
                for permutation in category_perms:
                    candidate = state + (permutation,)
                    if all(self._check(candidate, rule) for rule in rules_to_check):
                        new_stream.append(candidate)
            stream = new_stream
            lines.append(f"| {category_name} | {len(stream)} |")
        return "\n".join(lines)


class UniversalSieveEngine:
    def __init__(self, schema: PuzzleSchema) -> None:
        self.schema = schema
        self.cat_names = list(schema.categories.keys())
        self.size = schema.size
        self.logic = LogicGenerator(schema)

    def initial_state(self) -> list[dict[str, set[str]]]:
        return [
            {category: set(values) for category, values in self.schema.categories.items()}
            for _ in range(self.size)
        ]

    def apply_uniqueness(self, state: list[dict[str, set[str]]]) -> bool:
        changed = False
        repeated_categories = set((self.schema.metadata or {}).get("repeated_categories", ()))
        for category, values in self.schema.categories.items():
            if category not in repeated_categories:
                for value in values:
                    carrier_indexes = [index for index, house in enumerate(state) if value in house[category]]
                    if len(carrier_indexes) == 1:
                        house = state[carrier_indexes[0]]
                        new_values = house[category] & {value}
                        if new_values != house[category]:
                            house[category] = new_values
                            changed = True
                for house_index, house in enumerate(state):
                    if len(house[category]) == 1:
                        (fixed_value,) = tuple(house[category])
                        for other_index, other_house in enumerate(state):
                            if other_index != house_index and fixed_value in other_house[category]:
                                other_house[category].discard(fixed_value)
                                changed = True
        return changed

    def _has_contradiction(self, state: list[dict[str, set[str]]]) -> bool:
        return any(not values for house in state for values in house.values())

    def run_until_fixpoint(self, state: list[dict[str, set[str]]] | None = None) -> list[dict[str, set[str]]]:
        current = deepcopy(state if state is not None else self.initial_state())
        sieves = self.logic.build_sieves()
        while True:
            changed = False
            for sieve in sieves:
                changed = sieve(current) or changed
                if self._has_contradiction(current):
                    raise RuntimeError("Sieve engine reached contradiction.")
            changed = self.apply_uniqueness(current) or changed
            if self._has_contradiction(current):
                raise RuntimeError("Sieve engine reached contradiction.")
            if not changed:
                return current

    def render_state(self, state: list[dict[str, set[str]]] | None = None) -> str:
        current = state if state is not None else self.run_until_fixpoint()
        lines = [
            f"# {self.schema.name} Sieve State",
            "",
            "| house | " + " | ".join(self.cat_names) + " |",
            "| --- | " + " | ".join(["---"] * len(self.cat_names)) + " |",
        ]
        for index, house in enumerate(current):
            cells = []
            for category in self.cat_names:
                cells.append(", ".join(sorted(house[category])) or "-")
            lines.append(f"| house-{index + 1} | " + " | ".join(cells) + " |")
        return "\n".join(lines)


class UniversalValidatorEngine:
    def __init__(self, schema: PuzzleSchema) -> None:
        self.schema = schema
        self.logic = LogicGenerator(schema)
        self.validators = tuple((rule, self.logic.build_validator(rule)) for rule in schema.rules)

    def check_rule(self, state: list[dict[str, str]], rule: RuleSpec) -> bool:
        validator = self.logic.build_validator(rule)
        try:
            return bool(validator(state))
        except ValueError:
            return False

    def is_valid(self, state: list[dict[str, str]]) -> bool:
        for _rule, validator in self.validators:
            try:
                if not validator(state):
                    return False
            except ValueError:
                return False
        return True


def puzzle_schema_to_linear_schema(schema: PuzzleSchema):
    from ..logic_manifest import LinearLogicSchema

    repeated_categories = set((schema.metadata or {}).get("repeated_categories", ()))
    if repeated_categories:
        raise ValueError("Repeated-category schemas are not compatible with LinearLogicSchema.")

    rules: list[str] = []
    for rule in schema.rules:
        if rule.type == "same":
            rules.append(f"same({rule.fact[0]}, {rule.fact[1]})")
            continue
        if rule.type == "next_to":
            rules.append(f"next_to({rule.fact[0]}, {rule.fact[1]})")
            continue
        if rule.type == "directly_right":
            rules.append(f"directly_right({rule.fact[0]}, {rule.fact[1]})")
            continue
        if rule.type == "position":
            rules.append(f"at({rule.fact[0]}, {int(rule.fact[1])})")
            continue
        raise ValueError(f"Rule type {rule.type!r} is not compatible with LinearLogicSchema.")

    entities: list[str] = []
    for category, values in schema.categories.items():
        entities.extend(f"{category}:{value}" for value in values)
    return LinearLogicSchema(entities=entities, rules=rules, branches={})


def linear_schema_to_puzzle_schema(
    schema,
    *,
    name: str = "Structured Puzzle",
    size: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> PuzzleSchema:
    categories: dict[str, list[str]] = {}

    def parse_entity(term: str) -> tuple[str, str]:
        cleaned = term.strip().strip("'\"")
        if ":" not in cleaned:
            raise ValueError(f"Entity {cleaned!r} is not in category:value format.")
        category, value = cleaned.split(":", 1)
        return category, value

    position_hints: list[int] = []
    rules: list[RuleSpec] = []
    for entity in schema.entities:
        category, value = parse_entity(entity)
        categories.setdefault(category, [])
        if value not in categories[category]:
            categories[category].append(value)

    for raw_rule in schema.rules:
        if raw_rule.startswith("same(") and raw_rule.endswith(")"):
            inner = raw_rule[5:-1]
            left, right = [part.strip() for part in inner.split(",", 1)]
            rules.append(RuleSpec(type="same", fact=(left, right), metadata={"source_rule": raw_rule}))
            continue
        if raw_rule.startswith("next_to(") and raw_rule.endswith(")"):
            inner = raw_rule[8:-1]
            left, right = [part.strip() for part in inner.split(",", 1)]
            rules.append(RuleSpec(type="next_to", fact=(left, right), metadata={"source_rule": raw_rule}))
            continue
        if raw_rule.startswith("directly_right(") and raw_rule.endswith(")"):
            inner = raw_rule[15:-1]
            left, right = [part.strip() for part in inner.split(",", 1)]
            rules.append(RuleSpec(type="directly_right", fact=(left, right), metadata={"source_rule": raw_rule}))
            continue
        if raw_rule.startswith("at(") and raw_rule.endswith(")"):
            inner = raw_rule[3:-1]
            left, right = [part.strip() for part in inner.split(",", 1)]
            position = int(right)
            position_hints.append(position)
            rules.append(RuleSpec(type="position", fact=(left, position), metadata={"source_rule": raw_rule}))
            continue
        raise ValueError(f"Rule {raw_rule!r} is not compatible with PuzzleSchema.")

    inferred_size = max(
        [len(values) for values in categories.values()] + [max(position_hints) + 1 if position_hints else 0]
    )
    schema_metadata = dict(metadata or {})
    schema_metadata.setdefault("source_format", "linear_schema")
    return PuzzleSchema(
        name=name,
        size=size or inferred_size,
        categories={category: tuple(values) for category, values in categories.items()},
        rules=tuple(rules),
        metadata=schema_metadata,
    )


def build_schema_backends(
    schema: PuzzleSchema,
    *,
    category_order: tuple[str, ...] | None = None,
    linear_schema: Any | None = None,
) -> SchemaBackendBundle:
    logic = LogicGenerator(schema)
    return SchemaBackendBundle(
        puzzle_schema=schema,
        linear_schema=linear_schema,
        logic=logic,
        sieve=UniversalSieveEngine(schema),
        permutation=UniversalPermutationEngine(schema, category_order=category_order),
        validator=UniversalValidatorEngine(schema),
    )


def build_schema_backends_from_linear(
    linear_schema,
    *,
    name: str = "Structured Puzzle",
    size: int | None = None,
    metadata: dict[str, Any] | None = None,
    category_order: tuple[str, ...] | None = None,
) -> SchemaBackendBundle:
    puzzle_schema = linear_schema_to_puzzle_schema(
        linear_schema,
        name=name,
        size=size,
        metadata=metadata,
    )
    return build_schema_backends(
        puzzle_schema,
        category_order=category_order,
        linear_schema=linear_schema,
    )
