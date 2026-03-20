from __future__ import annotations

import json
from dataclasses import dataclass, field

from .artifacts import DomainRef, EffectArtifact, EffectKind, JustificationRef, StateTransformation, SubjectRef
from .assertions import AtomicClaim, ClaimStatus, HypothesisTree, TabularAssertionBoard, ValueRange
from .constraints import Abs, Add, AllDifferent, Const, ConstraintSpec, Eq, ExactlyOne, Item, Sub
from .core.checklist import HypothesisEntry, HypothesisResult
from .core.decision_tree import (
    auto_reconcile_single_survivor,
    DecisionNode,
    DecisionTree,
    expand_decision_spec,
    reconcile_decision_branch,
    render_decision_tree_markdown,
)
from .core.hypothesis_runner import run_hypothesis_entry
from .core.node_specs import AdjacentPair, HypothesisLink, NodeSpec, OffsetPair, SameHousePair, TickPlanner, node_instance_to_entry
from .core.problem_case import ProblemCase
from .core.entity_slots import (
    EntityRef,
    EntityValue,
    SlotCell,
    SlotRef,
    attach_entity_to_slot,
    exclude_entity_from_slot,
    attach_rule_to_slot,
)
from .core.domain_rules import CellBinding, DomainRuleLambda, PossibleArgumentMatrix, RuleRegistry, RuleStage, apply_atomic_rule, apply_same_container_rule, bind_rule_to_slot
from .core.schema_engine import LogicGenerator, RuleSpec
from .core.state_graph import (
    StateGraph,
    StateSnapshot,
    branch_on_best_unresolved,
    choose_best_search_spec,
    expand_state_node,
    expand_state_sequence,
    propagate_until_fixpoint,
    search_n,
    search_step,
    search_until_blocked,
    tick_n,
    tick_once,
    tick_until_blocked,
)
from .core.worker_cells import (
    ArgumentEnvelope,
    ArgumentRef,
    RuleBinding,
    WorkerCell,
    WorkerRef,
    attach_argument_to_worker,
    attach_operation_to_worker,
    connect_worker_neighbors,
)
from .hypothesis_runtime import HypothesisReaction, HypothesisRuntime
from .ir import Axis, CanonicalIR, ConstraintRecord, StateGrid, Universe
from .outcomes import BranchOutcome, StepSnapshot, render_llm_step_output, render_outcome_table
from .reactive import ReactiveAtom
from .rule_dsl import Rule, eq as rule_eq, next_to, ref
from .storage import Sandbox


HOUSES = ("house-1", "house-2", "house-3", "house-4", "house-5")
EINSTEIN_MAX_BRANCH_CANDIDATES = 3

CATEGORY_VALUES: dict[str, tuple[str, ...]] = {
    "color": ("red", "green", "white", "yellow", "blue"),
    "nationality": ("englishman", "spaniard", "ukrainian", "norwegian", "japanese"),
    "drink": ("coffee", "tea", "milk", "orange-juice", "water"),
    "pet": ("dog", "snails", "fox", "horse", "zebra"),
    "smoke": ("old-gold", "kool", "chesterfield", "lucky-strike", "parliament"),
}

EINSTEIN_NAMESPACE_UNIVERSES: dict[str, tuple[str, ...]] = {
    f"{category}_by_house": values
    for category, values in CATEGORY_VALUES.items()
}


@dataclass(frozen=True)
class EinsteinDirectGiven:
    claim_id: str
    category: str
    row: str
    column: str
    container: str
    key: str
    value: str
    title: str
    description: str
    consequences: tuple[str, ...] = ()
    first_step: bool = True

    def to_rule(self) -> Rule:
        return Rule(
            rule_id=f"{self.claim_id}-rule",
            op=rule_eq(ref(self.container, self.key), self.value),
            description=self.description,
        )


@dataclass(frozen=True)
class EinsteinRelationClue:
    claim_id: str
    title: str
    spec: ConstraintSpec


@dataclass(frozen=True)
class EinsteinFirstStepNodeSpec:
    hypothesis_id: str
    title: str
    status: ClaimStatus
    rule: Rule
    related_cells: tuple[str, ...]
    consequences: tuple[str, ...]
    parent_hypothesis_id: str | None = None


@dataclass(frozen=True)
class EinsteinRelationOperand:
    namespace: str
    value: str
    label: str
    cell_prefix: str


@dataclass(frozen=True)
class EinsteinRelationCandidateSpec:
    relation_id: str
    relation_kind: str
    statement: str
    left: EinsteinRelationOperand
    right: EinsteinRelationOperand


@dataclass(frozen=True)
class EinsteinPositionalRelationSpec:
    relation_id: str
    relation_kind: str
    statement: str
    left: EinsteinRelationOperand
    right: EinsteinRelationOperand
    distance: int = 1


@dataclass(frozen=True)
class EinsteinRelationRegistry:
    same_house_pairs: tuple[EinsteinRelationCandidateSpec, ...]
    positional_pairs: tuple[EinsteinPositionalRelationSpec, ...]

    def get(self, relation_id: str) -> EinsteinRelationCandidateSpec | EinsteinPositionalRelationSpec:
        for item in [*self.same_house_pairs, *self.positional_pairs]:
            if item.relation_id == relation_id:
                return item
        raise KeyError(relation_id)


@dataclass(frozen=True)
class LoopEvent:
    kind: str
    spec_id: str
    node_id: str
    created_node_ids: tuple[str, ...] = ()
    accepted_branch_id: str | None = None
    decision_id: str | None = None
    status: str = ""


@dataclass(frozen=True)
class LoopPolicy:
    max_depth: int = 20
    max_branch_depth: int = 20
    max_parallel_branches: int = 2


@dataclass(frozen=True)
class PositionalFilterLayer:
    z_index: int
    rule_id: str
    trigger: EntityRef
    matrix: PossibleArgumentMatrix


@dataclass(frozen=True)
class EntityLinkLayer:
    z_index: int
    rule_id: str
    trigger: EntityRef
    matrix: PossibleArgumentMatrix


RELATION_CLUES: tuple[EinsteinRelationClue, ...] = (
    EinsteinRelationClue("clue-01-englishman-red", "Englishman lives in red house", ConstraintSpec(Eq(Item("nationality_house", "englishman"), Item("color_house", "red")))),
    EinsteinRelationClue("clue-02-spaniard-dog", "Spaniard owns dog", ConstraintSpec(Eq(Item("nationality_house", "spaniard"), Item("pet_house", "dog")))),
    EinsteinRelationClue("clue-03-green-coffee", "Green house drinks coffee", ConstraintSpec(Eq(Item("color_house", "green"), Item("drink_house", "coffee")))),
    EinsteinRelationClue("clue-04-ukrainian-tea", "Ukrainian drinks tea", ConstraintSpec(Eq(Item("nationality_house", "ukrainian"), Item("drink_house", "tea")))),
    EinsteinRelationClue("clue-05-green-right-of-white", "Green house is immediately right of white house", ConstraintSpec(Eq(Item("color_house", "green"), Add(Item("color_house", "white"), Const(1))))),
    EinsteinRelationClue("clue-06-old-gold-snails", "Old Gold smoker keeps snails", ConstraintSpec(Eq(Item("smoke_house", "old-gold"), Item("pet_house", "snails")))),
    EinsteinRelationClue("clue-07-yellow-kool", "Yellow house smokes Kool", ConstraintSpec(Eq(Item("color_house", "yellow"), Item("smoke_house", "kool")))),
    EinsteinRelationClue("clue-08-chesterfield-next-to-fox", "Chesterfield smoker next to fox owner", ConstraintSpec(Eq(Abs(Sub(Item("smoke_house", "chesterfield"), Item("pet_house", "fox"))), Const(1)))),
    EinsteinRelationClue("clue-09-kool-next-to-horse", "Kool smoker next to horse owner", ConstraintSpec(Eq(Abs(Sub(Item("smoke_house", "kool"), Item("pet_house", "horse"))), Const(1)))),
    EinsteinRelationClue("clue-10-lucky-strike-orange-juice", "Lucky Strike smoker drinks orange juice", ConstraintSpec(Eq(Item("smoke_house", "lucky-strike"), Item("drink_house", "orange-juice")))),
    EinsteinRelationClue("clue-11-japanese-parliament", "Japanese smokes Parliament", ConstraintSpec(Eq(Item("nationality_house", "japanese"), Item("smoke_house", "parliament")))),
    EinsteinRelationClue("clue-12-norwegian-next-to-blue", "Norwegian lives next to blue house", ConstraintSpec(Eq(Abs(Sub(Item("nationality_house", "norwegian"), Item("color_house", "blue"))), Const(1)))),
)

def load_einstein_direct_givens() -> tuple[EinsteinDirectGiven, ...]:
    from .cases.einstein.schema_data import build_einstein_schema

    givens = [
        EinsteinDirectGiven(
            claim_id=str(rule.metadata["claim_id"]),
            category=str(rule.metadata["category"]),
            row=str(rule.metadata["row"]),
            column=str(rule.metadata["column"]),
            container=str(rule.metadata["container"]),
            key=str(rule.metadata["key"]),
            value=str(rule.metadata["value"]),
            title=str(rule.metadata["title"]),
            description=str(rule.metadata["description"]),
            consequences=tuple(rule.metadata.get("consequences", [])),
            first_step=bool(rule.metadata.get("first_step", True)),
        )
        for rule in build_einstein_schema().rules
        if rule.type == "position" and rule.metadata and "claim_id" in rule.metadata
    ]
    order = {"house-1__norwegian__yes": 0, "house-3__milk__yes": 1}
    return tuple(sorted(givens, key=lambda item: order.get(item.claim_id, 99)))


def load_einstein_relation_candidates() -> tuple[EinsteinRelationCandidateSpec, ...]:
    from .cases.einstein.schema_data import build_einstein_schema

    category_aliases = {"nation": "nationality"}
    cell_prefixes = {
        "color": "einstein-color",
        "nation": "einstein-nationality",
        "pet": "einstein-pet",
        "drink": "einstein-drink",
        "smoke": "einstein-smoke",
    }

    value_aliases = {
        "nation": {
            "English": "englishman",
            "Spanish": "spaniard",
            "Ukrainian": "ukrainian",
            "Norwegian": "norwegian",
            "Japanese": "japanese",
        },
        "drink": {
            "Coffee": "coffee",
            "Tea": "tea",
            "Milk": "milk",
            "Juice": "orange-juice",
            "Water": "water",
        },
        "smoke": {
            "Old Gold": "old-gold",
            "Kool": "kool",
            "Chesterfield": "chesterfield",
            "Lucky Strike": "lucky-strike",
            "Parliament": "parliament",
        },
        "pet": {
            "Dog": "dog",
            "Snails": "snails",
            "Fox": "fox",
            "Horse": "horse",
            "Zebra": "zebra",
        },
        "color": {
            "Red": "red",
            "Green": "green",
            "White": "white",
            "Yellow": "yellow",
            "Blue": "blue",
        },
    }
    expected_order = (
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
        "ukrainian-tea",
        "old-gold-snails",
        "yellow-kool",
        "lucky-strike-orange-juice",
        "japanese-parliament",
    )

    def _canonical_value(category: str, value: str) -> str:
        return value_aliases[category][value]

    specs = [
        EinsteinRelationCandidateSpec(
            relation_id=str(rule.metadata["relation_id"]),
            relation_kind="same_house_pair",
            statement=str(rule.metadata["statement"]),
            left=EinsteinRelationOperand(
                namespace=f"{category_aliases.get(str(rule.fact[0]).split(':', 1)[0], str(rule.fact[0]).split(':', 1)[0])}_by_house",
                value=_canonical_value(str(rule.fact[0]).split(":", 1)[0], str(rule.fact[0]).split(":", 1)[1]),
                label=_canonical_value(str(rule.fact[0]).split(":", 1)[0], str(rule.fact[0]).split(":", 1)[1]),
                cell_prefix=cell_prefixes[str(rule.fact[0]).split(":", 1)[0]],
            ),
            right=EinsteinRelationOperand(
                namespace=f"{category_aliases.get(str(rule.fact[1]).split(':', 1)[0], str(rule.fact[1]).split(':', 1)[0])}_by_house",
                value=_canonical_value(str(rule.fact[1]).split(":", 1)[0], str(rule.fact[1]).split(":", 1)[1]),
                label=_canonical_value(str(rule.fact[1]).split(":", 1)[0], str(rule.fact[1]).split(":", 1)[1]),
                cell_prefix=cell_prefixes[str(rule.fact[1]).split(":", 1)[0]],
            ),
        )
        for rule in build_einstein_schema().rules
        if rule.type == "same"
    ]
    by_id = {spec.relation_id: spec for spec in specs}
    return tuple(by_id[relation_id] for relation_id in expected_order)


DIRECT_GIVENS = load_einstein_direct_givens()
RELATION_CANDIDATE_SPECS = load_einstein_relation_candidates()
ENGLISHMAN_RED_RELATION = next(item for item in RELATION_CANDIDATE_SPECS if item.relation_id == "englishman-red")
POSITIONAL_RELATION_SPECS: tuple[EinsteinPositionalRelationSpec, ...] = (
    EinsteinPositionalRelationSpec(
        relation_id="norwegian-next-to-blue",
        relation_kind="adjacent_pair",
        statement="Норвежец живёт рядом с синим домом.",
        left=EinsteinRelationOperand(
            namespace="nationality_house",
            value="norwegian",
            label="norwegian",
            cell_prefix="einstein-nationality",
        ),
        right=EinsteinRelationOperand(
            namespace="color_house",
            value="blue",
            label="blue",
            cell_prefix="einstein-color",
        ),
    ),
    EinsteinPositionalRelationSpec(
        relation_id="chesterfield-next-to-fox",
        relation_kind="adjacent_pair",
        statement="Chesterfield smoker lives next to fox owner.",
        left=EinsteinRelationOperand(
            namespace="smoke_house",
            value="chesterfield",
            label="chesterfield",
            cell_prefix="einstein-smoke",
        ),
        right=EinsteinRelationOperand(
            namespace="pet_house",
            value="fox",
            label="fox",
            cell_prefix="einstein-pet",
        ),
    ),
    EinsteinPositionalRelationSpec(
        relation_id="kool-next-to-horse",
        relation_kind="adjacent_pair",
        statement="Kool smoker lives next to horse owner.",
        left=EinsteinRelationOperand(
            namespace="smoke_house",
            value="kool",
            label="kool",
            cell_prefix="einstein-smoke",
        ),
        right=EinsteinRelationOperand(
            namespace="pet_house",
            value="horse",
            label="horse",
            cell_prefix="einstein-pet",
        ),
    ),
    EinsteinPositionalRelationSpec(
        relation_id="green-right-of-white",
        relation_kind="offset_pair",
        statement="Зелёный дом стоит сразу справа от белого дома.",
        left=EinsteinRelationOperand(
            namespace="color_house",
            value="green",
            label="green",
            cell_prefix="einstein-color",
        ),
        right=EinsteinRelationOperand(
            namespace="color_house",
            value="white",
            label="white",
            cell_prefix="einstein-color",
        ),
        distance=1,
    ),
)
def load_einstein_positional_relation_specs() -> tuple[EinsteinPositionalRelationSpec, ...]:
    from .cases.einstein.schema_data import build_einstein_schema

    category_aliases = {"nation": "nationality"}
    cell_prefixes = {
        "color": "einstein-color",
        "nation": "einstein-nationality",
        "pet": "einstein-pet",
        "drink": "einstein-drink",
        "smoke": "einstein-smoke",
    }

    value_aliases = {
        "nation": {
            "English": "englishman",
            "Spanish": "spaniard",
            "Ukrainian": "ukrainian",
            "Norwegian": "norwegian",
            "Japanese": "japanese",
        },
        "drink": {
            "Coffee": "coffee",
            "Tea": "tea",
            "Milk": "milk",
            "Juice": "orange-juice",
            "Water": "water",
        },
        "smoke": {
            "Old Gold": "old-gold",
            "Kool": "kool",
            "Chesterfield": "chesterfield",
            "Lucky Strike": "lucky-strike",
            "Parliament": "parliament",
        },
        "pet": {
            "Dog": "dog",
            "Snails": "snails",
            "Fox": "fox",
            "Horse": "horse",
            "Zebra": "zebra",
        },
        "color": {
            "Red": "red",
            "Green": "green",
            "White": "white",
            "Yellow": "yellow",
            "Blue": "blue",
        },
    }
    expected_order = (
        "norwegian-next-to-blue",
        "chesterfield-next-to-fox",
        "kool-next-to-horse",
        "green-right-of-white",
    )

    def _canonical_value(category: str, value: str) -> str:
        return value_aliases[category][value]

    specs: list[EinsteinPositionalRelationSpec] = []
    for rule in build_einstein_schema().rules:
        if rule.type not in {"next_to", "directly_right"}:
            continue
        left_cat, left_value = str(rule.fact[0]).split(":", 1)
        right_cat, right_value = str(rule.fact[1]).split(":", 1)
        if rule.type == "directly_right":
            left_cat, left_value, right_cat, right_value = right_cat, right_value, left_cat, left_value
            relation_kind = "offset_pair"
        else:
            relation_kind = "adjacent_pair"
        specs.append(
            EinsteinPositionalRelationSpec(
                relation_id=str(rule.metadata["relation_id"]),
                relation_kind=relation_kind,
                statement=str(rule.metadata["statement"]),
                left=EinsteinRelationOperand(
                    namespace=f"{category_aliases.get(left_cat, left_cat)}_house",
                    value=_canonical_value(left_cat, left_value),
                    label=_canonical_value(left_cat, left_value),
                    cell_prefix=cell_prefixes[left_cat],
                ),
                right=EinsteinRelationOperand(
                    namespace=f"{category_aliases.get(right_cat, right_cat)}_house",
                    value=_canonical_value(right_cat, right_value),
                    label=_canonical_value(right_cat, right_value),
                    cell_prefix=cell_prefixes[right_cat],
                ),
                distance=1,
            )
        )
    by_id = {spec.relation_id: spec for spec in specs}
    return tuple(by_id[relation_id] for relation_id in expected_order)


POSITIONAL_RELATION_SPECS = load_einstein_positional_relation_specs()
EINSTEIN_RELATION_REGISTRY = EinsteinRelationRegistry(
    same_house_pairs=RELATION_CANDIDATE_SPECS,
    positional_pairs=POSITIONAL_RELATION_SPECS,
)
FIRST_TEXT_RELATION_ORDER: tuple[str, ...] = (
    "englishman-red",
    "spaniard-dog",
    "green-coffee",
    "ukrainian-tea",
    "green-right-of-white",
    "old-gold-snails",
    "yellow-kool",
)

EINSTEIN_SOLVER_ORDER: tuple[str, ...] = (
    "norwegian-next-to-blue",
    "green-right-of-white",
    "ukrainian-tea",
    "englishman-red",
    "spaniard-dog",
    "green-coffee",
    "yellow-kool",
    "old-gold-snails",
    "lucky-strike-orange-juice",
    "japanese-parliament",
    "chesterfield-next-to-fox",
    "kool-next-to-horse",
)

ACTIVATION_GROUPS: dict[str, tuple[str, ...]] = {
    "englishman-red": ("spaniard-dog", "green-coffee"),
    "green-coffee": ("ukrainian-tea", "green-right-of-white"),
    "green-right-of-white": ("old-gold-snails",),
    "old-gold-snails": ("yellow-kool",),
}

BRANCH_GROUPS: dict[str, str] = {
    "ukrainian-tea": "ukrainian-tea-candidates",
    "norwegian-next-to-blue": "norwegian-next-to-blue-candidates",
}


def _build_sequential_links(relation_id: str) -> tuple[HypothesisLink, ...]:
    targets = ACTIVATION_GROUPS.get(relation_id)
    if targets is not None:
        return tuple(
            HypothesisLink(
                kind="activates",
                target_spec_id=target_id,
                metadata={"activation": "group"},
            )
            for target_id in targets
        )
    try:
        index = FIRST_TEXT_RELATION_ORDER.index(relation_id)
    except ValueError:
        return ()
    if index + 1 >= len(FIRST_TEXT_RELATION_ORDER):
        return ()
    return (
        HypothesisLink(
            kind="activates",
            target_spec_id=FIRST_TEXT_RELATION_ORDER[index + 1],
            metadata={"activation": "text_order"},
        ),
    )


def _build_branching_links(relation_id: str) -> tuple[HypothesisLink, ...]:
    branch_group = BRANCH_GROUPS.get(relation_id)
    if branch_group is None:
        return ()
    return (
        HypothesisLink(
            kind="branches_to",
            target_spec_id=branch_group,
            metadata={"branch_group": branch_group},
        ),
        HypothesisLink(
            kind="excludes",
            target_spec_id=branch_group,
            metadata={"exclusion_group": branch_group},
        ),
    )


EINSTEIN_NODE_SPECS: tuple[NodeSpec, ...] = tuple(
    [
        NodeSpec(
            node_id=relation.relation_id,
            kind="relation",
            entrypoint="kobold_sandbox.cases.einstein.entrypoints:run_binary_relation_candidate",
            payload=SameHousePair(
                left_ns=relation.left.namespace,
                left_value=relation.left.value,
                right_ns=relation.right.namespace,
                right_value=relation.right.value,
                universe_keys=HOUSES,
                left_label=relation.left.label,
                right_label=relation.right.label,
                left_cell_prefix=relation.left.cell_prefix,
                right_cell_prefix=relation.right.cell_prefix,
                statement=relation.statement,
            ),
            priority=20,
            links=_build_sequential_links(relation.relation_id) + _build_branching_links(relation.relation_id),
            tags=("einstein", "same-house"),
        )
        for relation in RELATION_CANDIDATE_SPECS
    ]
    + [
        NodeSpec(
            node_id=relation.relation_id,
            kind="relation",
            entrypoint="kobold_sandbox.cases.einstein.entrypoints:run_positional_relation_candidate",
            payload=(
                AdjacentPair(
                    left_ns=relation.left.namespace,
                    left_value=relation.left.value,
                    right_ns=relation.right.namespace,
                    right_value=relation.right.value,
                    left_label=relation.left.label,
                    right_label=relation.right.label,
                    left_cell_prefix=relation.left.cell_prefix,
                    right_cell_prefix=relation.right.cell_prefix,
                    statement=relation.statement,
                )
                if relation.relation_kind == "adjacent_pair"
                else OffsetPair(
                    left_ns=relation.left.namespace,
                    left_value=relation.left.value,
                    right_ns=relation.right.namespace,
                    right_value=relation.right.value,
                    distance=relation.distance,
                    left_label=relation.left.label,
                    right_label=relation.right.label,
                    left_cell_prefix=relation.left.cell_prefix,
                    right_cell_prefix=relation.right.cell_prefix,
                    statement=relation.statement,
                )
            ),
            priority=30,
            links=_build_sequential_links(relation.relation_id) + _build_branching_links(relation.relation_id),
            tags=("einstein", relation.relation_kind),
        )
        for relation in POSITIONAL_RELATION_SPECS
    ]
)
ALL_RELATION_ORDER: tuple[str, ...] = tuple(spec.node_id for spec in EINSTEIN_NODE_SPECS)


FIRST_STEP_NODE_SPECS: tuple[EinsteinFirstStepNodeSpec, ...] = (
    EinsteinFirstStepNodeSpec(
        hypothesis_id="house-1__norwegian__yes",
        title="House 1 is Norwegian",
        status=ClaimStatus.CONFIRMED,
        rule=DIRECT_GIVENS[0].to_rule(),
        related_cells=("einstein-nationality:house-1:norwegian",),
        consequences=DIRECT_GIVENS[0].consequences,
        parent_hypothesis_id=None,
    ),
    EinsteinFirstStepNodeSpec(
        hypothesis_id="norwegian-next-to-blue",
        title="Norwegian is next to blue house",
        status=ClaimStatus.HYPOTHESIS,
        rule=Rule(
            rule_id="norwegian-next-to-blue-rule",
            op=next_to(ref("nationality_house", "norwegian"), ref("color_house", "blue")),
            description="Relative rule: Norwegian is next to blue house",
        ),
        related_cells=("einstein-nationality:house-1:norwegian", "einstein-color:house-2:blue"),
        consequences=("blue house must be adjacent to house-1", "house-2 is a blue candidate"),
        parent_hypothesis_id="house-1__norwegian__yes",
    ),
    EinsteinFirstStepNodeSpec(
        hypothesis_id="house-3__milk__yes",
        title="House 3 drinks milk",
        status=ClaimStatus.CONFIRMED,
        rule=DIRECT_GIVENS[1].to_rule(),
        related_cells=("einstein-drink:house-3:milk",),
        consequences=DIRECT_GIVENS[1].consequences,
        parent_hypothesis_id=None,
    ),
)


@dataclass
class EinsteinCase:
    boards: dict[str, TabularAssertionBoard]
    clue_claims: list[AtomicClaim]
    structural_claims: list[AtomicClaim]

    def all_claims(self) -> list[AtomicClaim]:
        claims: list[AtomicClaim] = []
        for board in self.boards.values():
            claims.extend(board.to_atomic_claims())
        claims.extend(self.clue_claims)
        claims.extend(self.structural_claims)
        return claims

    def to_ir(self) -> CanonicalIR:
        grids = {
            category: StateGrid.from_board(board, row_axis="house", column_axis=category)
            for category, board in self.boards.items()
        }
        constraints: list[ConstraintRecord] = []
        constraints.extend(_constraint_records_from_claims(self.clue_claims, kind="clue"))
        constraints.extend(_constraint_records_from_claims(self.structural_claims, kind="structural"))
        return CanonicalIR(
            universe=Universe(
                problem_id="einstein-puzzle",
                axes=(
                    Axis(name="house", labels=HOUSES, value_kind="position"),
                    Axis(name="color", labels=CATEGORY_VALUES["color"]),
                    Axis(name="nationality", labels=CATEGORY_VALUES["nationality"]),
                    Axis(name="drink", labels=CATEGORY_VALUES["drink"]),
                    Axis(name="pet", labels=CATEGORY_VALUES["pet"]),
                    Axis(name="smoke", labels=CATEGORY_VALUES["smoke"]),
                ),
                object_types=("house", "person", "attribute"),
            ),
            grids=grids,
            constraints=constraints,
            claims=self.all_claims(),
        )

    def first_step_effects(self) -> EffectArtifact:
        return build_einstein_first_step_effects()


@dataclass
class EinsteinFirstStepCase(ProblemCase):
    case_id: str = "einstein-first-step"

    def build_initial_context(self) -> dict[str, object]:
        return {
            "nationality_by_house": {"house-1": "norwegian"},
            "drink_by_house": {"house-3": "milk"},
            "nationality_house": {"norwegian": 1},
            "color_house": {"blue": 2},
        }

    def build_checklist(self) -> list[HypothesisEntry]:
        return build_einstein_first_step_checklist()

    def reconcile(self, results: list[HypothesisResult]) -> StepSnapshot:
        passed_results = [result for result in results if result.passed and result.branch_outcome is not None]
        consequences: list[str] = []
        fixed_cells: list[str] = []
        for result in passed_results:
            for item in result.branch_outcome.consequences:
                if item not in consequences:
                    consequences.append(item)
            for cell in result.branch_outcome.affected_cells:
                if cell not in fixed_cells:
                    fixed_cells.append(cell)
        return StepSnapshot(
            step_id="step-0001",
            source_outcome_refs=tuple(f"analysis/{result.hypothesis_id}/outcome.json" for result in passed_results),
            new_fixed_cells=tuple(fixed_cells),
            consequences=tuple(consequences),
            notes="Checklist reconciliation for Einstein first-step hypotheses.",
        )


@dataclass
class EinsteinEnglishmanRedCase(ProblemCase):
    case_id: str = "einstein-englishman-red"

    def build_initial_context(self) -> dict[str, object]:
        return {
            "nationality_by_house": {},
            "color_by_house": {},
        }

    def build_checklist(self) -> list[HypothesisEntry]:
        return build_relation_candidate_checklist(relation_id="englishman-red")

    def reconcile(self, results: list[HypothesisResult]) -> StepSnapshot:
        passed_results = [result for result in results if result.passed and result.branch_outcome is not None]
        fixed_cells: list[str] = []
        consequences: list[str] = []
        for result in passed_results:
            for cell in result.branch_outcome.affected_cells:
                if cell not in fixed_cells:
                    fixed_cells.append(cell)
            for consequence in result.branch_outcome.consequences:
                if consequence not in consequences:
                    consequences.append(consequence)
        return StepSnapshot(
            step_id="step-englishman-red-0001",
            source_outcome_refs=tuple(f"analysis/{result.hypothesis_id}/outcome.json" for result in passed_results),
            new_fixed_cells=tuple(fixed_cells),
            consequences=tuple(consequences),
            notes="Sequential coverage snapshot for the Englishman/red clue.",
        )


def make_category_board(category: str) -> TabularAssertionBoard:
    board = TabularAssertionBoard(
        name=f"einstein-{category}",
        rows=HOUSES,
        columns=CATEGORY_VALUES[category],
    )
    for row in HOUSES:
        for value in CATEGORY_VALUES[category]:
            board.cell(row, value).claim.value_range = ValueRange.from_values(["yes", "no"])
    return board


def build_einstein_case() -> EinsteinCase:
    boards = {category: make_category_board(category) for category in CATEGORY_VALUES}
    clue_claims: list[AtomicClaim] = []
    structural_claims: list[AtomicClaim] = []

    _seed_direct_givens(boards)
    clue_claims.extend(_build_relation_clues())
    structural_claims.extend(_build_structural_claims())

    return EinsteinCase(
        boards=boards,
        clue_claims=clue_claims,
        structural_claims=structural_claims,
    )


def _seed_direct_givens(boards: dict[str, TabularAssertionBoard]) -> None:
    for given in DIRECT_GIVENS:
        spec = ConstraintSpec(Eq(Item(given.container, given.key), Const(given.value)), given.description)
        board = boards[given.category]
        board.seed_claim(
            given.row,
            given.column,
            "yes",
            formal_constraint=spec,
            status=ClaimStatus.GIVEN,
        )
        board.attach_atomic_constraint(given.row, given.column, spec)


def _relation_claim(
    claim_id: str,
    title: str,
    spec: ConstraintSpec,
    *,
    status: ClaimStatus = ClaimStatus.GIVEN,
) -> AtomicClaim:
    claim = AtomicClaim(
        claim_id=claim_id,
        title=title,
        status=status,
    )
    claim.attach_atomic_constraint(spec)
    return claim


def _build_relation_clues() -> list[AtomicClaim]:
    return [_relation_claim(item.claim_id, item.title, item.spec) for item in RELATION_CLUES]


def _build_structural_claims() -> list[AtomicClaim]:
    claims: list[AtomicClaim] = []
    for category, values in CATEGORY_VALUES.items():
        for house in HOUSES:
            items = tuple(Item(f"einstein_{category}_cell", f"{house}:{value}") for value in values)
            spec = ConstraintSpec(ExactlyOne(items))
            claims.append(
                _structured_claim(
                    claim_id=f"struct-{category}-{house}",
                    title=f"{house} has exactly one {category}",
                    spec=spec,
                )
            )
        for value in values:
            items = tuple(Item(f"einstein_{category}_cell", f"{house}:{value}") for house in HOUSES)
            spec = ConstraintSpec(ExactlyOne(items))
            claims.append(
                _structured_claim(
                    claim_id=f"struct-{category}-{value}",
                    title=f"{value} appears in exactly one house",
                    spec=spec,
                )
            )
        inverse_items = tuple(Item(f"{category}_house", value) for value in values)
        claims.append(
            _structured_claim(
                claim_id=f"struct-{category}-all-different",
                title=f"{category} house assignments are all different",
                spec=ConstraintSpec(AllDifferent(inverse_items)),
            )
        )
    return claims


def _structured_claim(claim_id: str, title: str, spec: ConstraintSpec) -> AtomicClaim:
    claim = AtomicClaim(
        claim_id=claim_id,
        title=title,
        status=ClaimStatus.GIVEN,
    )
    claim.attach_atomic_constraint(spec)
    return claim


def _claim_from_rule_spec(spec: EinsteinFirstStepNodeSpec) -> AtomicClaim:
    return AtomicClaim(
        claim_id=spec.hypothesis_id,
        title=spec.title,
        python_code=spec.rule.to_assertion(),
        variables=spec.rule.variables(),
        status=spec.status,
        consequences=list(spec.consequences),
    )


def _effect_from_direct_given(given: EinsteinDirectGiven) -> StateTransformation:
    subject_id = f"einstein-{given.category}:{given.row}:{given.column}"
    return StateTransformation(
        transformation_id=f"einstein-t-{given.row}-{given.column}",
        kind=EffectKind.FIXED_ASSIGNMENT,
        subject_ref=SubjectRef(
            subject_id=subject_id,
            kind="grid-cell",
            path=f"grids/einstein-{given.category}/{given.row}/{given.column}.json",
        ),
        previous_domain_ref=DomainRef(
            domain_id=f"einstein-{given.category}-yes-no",
            kind="enum",
            payload={"values": ["yes", "no"]},
        ),
        next_domain_ref=DomainRef(
            domain_id=f"einstein-{given.category}-fixed-yes",
            kind="singleton",
            payload={"values": ["yes"]},
        ),
        justification_refs=(JustificationRef(given.claim_id, "claim"),),
        metadata={"summary": given.description},
    )


def _constraint_records_from_claims(claims: list[AtomicClaim], *, kind: str) -> list[ConstraintRecord]:
    records: list[ConstraintRecord] = []
    for claim in claims:
        if claim.formal_constraint is None:
            continue
        records.append(
            ConstraintRecord(
                constraint_id=claim.claim_id,
                kind=kind,
                spec=claim.formal_constraint,
                claim_id=claim.claim_id,
                source=claim.title,
            )
        )
    return records


def build_cell_hypothesis_claims(board: TabularAssertionBoard, row: str, column: str) -> list[AtomicClaim]:
    base = board.cell(row, column)
    positive = AtomicClaim(
        claim_id=f"{base.claim.claim_id}__yes",
        title=f"{board.name}: {row} -> {column} = yes",
        status=ClaimStatus.HYPOTHESIS,
        value_range=ValueRange.from_values(["yes"]),
    )
    positive.attach_atomic_constraint(
        ConstraintSpec(Eq(Item(f"{board.name.replace('-', '_')}_cell", f"{row}:{column}"), Const("yes")))
    )
    negative = AtomicClaim(
        claim_id=f"{base.claim.claim_id}__no",
        title=f"{board.name}: {row} -> {column} = no",
        status=ClaimStatus.HYPOTHESIS,
        value_range=ValueRange.from_values(["no"]),
    )
    negative.attach_atomic_constraint(
        ConstraintSpec(Eq(Item(f"{board.name.replace('-', '_')}_cell", f"{row}:{column}"), Const("no")))
    )
    return [positive, negative]


def materialize_cell_hypothesis_branches(
    sandbox: Sandbox,
    parent_id: str,
    board: TabularAssertionBoard,
    row: str,
    column: str,
    *,
    tags: list[str] | None = None,
) -> list[str]:
    node_ids: list[str] = []
    for claim in build_cell_hypothesis_claims(board, row, column):
        node = sandbox.create_claim_node(
            parent_id,
            claim,
            tags=(tags or []) + ["einstein", board.name, row, column, claim.value_range.values[0]],
        )
        node_ids.append(node.id)
    return node_ids


def build_einstein_first_step_effects() -> EffectArtifact:
    transformations = tuple(_effect_from_direct_given(item) for item in DIRECT_GIVENS if item.first_step)
    return EffectArtifact(
        artifact_id="einstein-step-0001",
        format="constraint-engine-output",
        producer_constraint_id="einstein-direct-givens",
        transformations=transformations,
        metadata={"step": "initial givens"},
    )


def build_einstein_first_step_tree() -> tuple[HypothesisTree, HypothesisRuntime]:
    tree = HypothesisTree.from_problem("Einstein First Step")
    runtime = HypothesisRuntime()
    built: dict[str, object] = {tree.root.node_id: tree.root}
    for spec in FIRST_STEP_NODE_SPECS:
        parent = tree.root if spec.parent_hypothesis_id is None else built[spec.parent_hypothesis_id]
        claim = _claim_from_rule_spec(spec)
        node = tree.create_child(
            parent,
            claim,
            related_cells=spec.related_cells,
        )
        node.node_id = claim.branch_slug()
        node.branch_name = f"hyp/{node.node_id}"
        built[spec.hypothesis_id] = node
        runtime.attach_atom(node, ReactiveAtom.from_rule(spec.rule, source_claim_id=claim.claim_id))
    return tree, runtime


def build_einstein_first_step_checklist() -> list[HypothesisEntry]:
    entrypoint = "kobold_sandbox.cases.einstein.entrypoints:run_first_step_hypothesis"
    return [
        HypothesisEntry(
            hypothesis_id=_claim_from_rule_spec(spec).branch_slug(),
            title=spec.title,
            entrypoint=entrypoint,
            context_refs=("examples/einstein_case/context/initial_state.json",),
            depends_on=(
                (_claim_from_rule_spec_by_id(spec.parent_hypothesis_id).branch_slug(),)
                if spec.parent_hypothesis_id is not None
                else ()
            ),
            related_cells=spec.related_cells,
            tags=("einstein", "first-step", spec.status.value),
            metadata={
                "spec_id": spec.hypothesis_id,
                "description": spec.rule.description,
            },
        )
        for spec in FIRST_STEP_NODE_SPECS
    ]


def build_relation_candidate_checklist(
    *,
    relation_kind: str = "same_house_pair",
    relation_id: str | None = None,
) -> list[HypothesisEntry]:
    relations = [
        item
        for item in RELATION_CANDIDATE_SPECS
        if item.relation_kind == relation_kind and (relation_id is None or item.relation_id == relation_id)
    ]
    entrypoint = "kobold_sandbox.cases.einstein.entrypoints:run_binary_relation_candidate"
    checklist: list[HypothesisEntry] = []
    for relation in relations:
        checklist.extend(
            [
                HypothesisEntry(
                    hypothesis_id=f"{relation.relation_id}-{house}",
                    title=f"{relation.relation_id} candidate at {house}",
                    entrypoint=entrypoint,
                    context_refs=("examples/einstein_case/context/initial_state.json",),
                    related_cells=(
                        f"{relation.left.cell_prefix}:{house}:{relation.left.value}",
                        f"{relation.right.cell_prefix}:{house}:{relation.right.value}",
                        f"relation-link:{relation.relation_id}:{house}",
                    ),
                    tags=("einstein", "sequential", relation_kind, relation.relation_id, house),
                    metadata={
                        "house": house,
                        "universe_keys": HOUSES,
                        "relation_id": relation.relation_id,
                        "relation_kind": relation.relation_kind,
                        "left": {
                            "namespace": relation.left.namespace,
                            "value": relation.left.value,
                            "label": relation.left.label,
                            "cell_prefix": relation.left.cell_prefix,
                        },
                        "right": {
                            "namespace": relation.right.namespace,
                            "value": relation.right.value,
                            "label": relation.right.label,
                            "cell_prefix": relation.right.cell_prefix,
                        },
                        "statement": relation.statement,
                    },
                )
                for house in HOUSES
            ]
        )
    return checklist


def build_englishman_red_checklist() -> list[HypothesisEntry]:
    return build_relation_candidate_checklist(relation_id="englishman-red")


def build_positional_relation_checklist(
    *,
    relation_kind: str | None = None,
    relation_id: str | None = None,
) -> list[HypothesisEntry]:
    specs = [
        item
        for item in POSITIONAL_RELATION_SPECS
        if (relation_kind is None or item.relation_kind == relation_kind)
        and (relation_id is None or item.relation_id == relation_id)
    ]
    entrypoint = "kobold_sandbox.cases.einstein.entrypoints:run_positional_relation_candidate"
    return [
        HypothesisEntry(
            hypothesis_id=spec.relation_id,
            title=f"{spec.relation_id} positional candidate",
            entrypoint=entrypoint,
            context_refs=("examples/einstein_case/context/initial_state.json",),
            related_cells=(
                f"{spec.left.cell_prefix}:{spec.left.value}",
                f"{spec.right.cell_prefix}:{spec.right.value}",
                f"relation-link:{spec.relation_id}",
            ),
            tags=("einstein", "positional", spec.relation_kind, spec.relation_id),
            metadata={
                "relation_id": spec.relation_id,
                "relation_kind": spec.relation_kind,
                "distance": spec.distance,
                "left": {
                    "namespace": spec.left.namespace,
                    "value": spec.left.value,
                    "label": spec.left.label,
                    "cell_prefix": spec.left.cell_prefix,
                },
                "right": {
                    "namespace": spec.right.namespace,
                    "value": spec.right.value,
                    "label": spec.right.label,
                    "cell_prefix": spec.right.cell_prefix,
                },
                "statement": spec.statement,
            },
        )
        for spec in specs
    ]


def render_relation_check_table(
    relation_id: str,
    context: dict[str, object],
    *,
    house: str | None = None,
) -> str:
    relation = EINSTEIN_RELATION_REGISTRY.get(relation_id)
    if isinstance(relation, EinsteinRelationCandidateSpec):
        target_house = house or "house-1"
        entry = next(
            item
            for item in build_relation_candidate_checklist(relation_id=relation_id)
            if item.metadata["house"] == target_house
        )
    else:
        entry = next(item for item in build_positional_relation_checklist(relation_id=relation_id))
    result = run_hypothesis_entry(entry, context)
    if result.branch_outcome is None:
        raise ValueError(f"No branch outcome produced for {relation_id}")
    return render_outcome_table(result.branch_outcome)


def build_relation_state_graph(
    relation_id: str,
    context: dict[str, object],
    *,
    house: str | None = None,
    max_depth: int = 1,
) -> StateGraph:
    relation = EINSTEIN_RELATION_REGISTRY.get(relation_id)
    snapshot = StateSnapshot.from_values({key: dict(value) for key, value in context.items()})
    graph = StateGraph.from_snapshot(snapshot)
    if isinstance(relation, EinsteinRelationCandidateSpec):
        entries = build_relation_candidate_checklist(relation_id=relation_id)
        if house is not None:
            entries = [entry for entry in entries if entry.metadata["house"] == house]
    else:
        entries = build_positional_relation_checklist(relation_id=relation_id)
    expand_state_node(graph, graph.root_node_id, entries, max_depth=max_depth)
    return graph


def build_relation_state_sequence_graph(
    entries: list[HypothesisEntry],
    context: dict[str, object],
    *,
    max_depth: int,
) -> StateGraph:
    snapshot = StateSnapshot.from_values({key: dict(value) for key, value in context.items()})
    graph = StateGraph.from_snapshot(snapshot)
    expand_state_sequence(graph, graph.root_node_id, entries, max_depth=max_depth)
    return graph




def choose_relation_search_frontier(
    graph: StateGraph,
    *,
    relation_ids: tuple[str, ...],
    node_id: str | None = None,
    consumed_spec_ids: set[str] | None = None,
) -> tuple[str | None, list[HypothesisEntry]]:
    spec_map = {spec.node_id: spec for spec in EINSTEIN_NODE_SPECS}
    specs = [spec_map[item] for item in relation_ids]
    planner = TickPlanner(max_branch_candidates=EINSTEIN_MAX_BRANCH_CANDIDATES)
    target_node = graph.nodes[node_id or graph.root_node_id]
    best_spec, entries = choose_best_search_spec(
        planner,
        specs,
        target_node.snapshot,
        consumed_spec_ids=consumed_spec_ids,
    )
    return (best_spec.node_id if best_spec else None), entries


def search_relation_graph_step(
    graph: StateGraph,
    *,
    relation_ids: tuple[str, ...],
    node_id: str | None = None,
    max_depth: int,
    consumed_spec_ids: set[str] | None = None,
) -> tuple[str | None, list[str]]:
    spec_map = {spec.node_id: spec for spec in EINSTEIN_NODE_SPECS}
    specs = [spec_map[item] for item in relation_ids]
    planner = TickPlanner(max_branch_candidates=EINSTEIN_MAX_BRANCH_CANDIDATES)
    return search_step(
        graph,
        node_id or graph.root_node_id,
        planner,
        specs,
        max_depth=max_depth,
        consumed_spec_ids=consumed_spec_ids,
    )


def search_relation_graph_n(
    graph: StateGraph,
    *,
    relation_ids: tuple[str, ...],
    steps: int,
    node_id: str | None = None,
    max_depth: int,
    consumed_spec_ids: set[str] | None = None,
) -> list[tuple[str, list[str]]]:
    spec_map = {spec.node_id: spec for spec in EINSTEIN_NODE_SPECS}
    specs = [spec_map[item] for item in relation_ids]
    planner = TickPlanner(max_branch_candidates=EINSTEIN_MAX_BRANCH_CANDIDATES)
    return search_n(
        graph,
        node_id or graph.root_node_id,
        planner,
        specs,
        max_depth=max_depth,
        steps=steps,
        consumed_spec_ids=consumed_spec_ids,
    )


def search_relation_graph_until_blocked(
    graph: StateGraph,
    *,
    relation_ids: tuple[str, ...],
    node_id: str | None = None,
    max_depth: int,
    consumed_spec_ids: set[str] | None = None,
) -> tuple[list[tuple[str, list[str]]], str]:
    spec_map = {spec.node_id: spec for spec in EINSTEIN_NODE_SPECS}
    specs = [spec_map[item] for item in relation_ids]
    planner = TickPlanner(max_branch_candidates=EINSTEIN_MAX_BRANCH_CANDIDATES)
    return search_until_blocked(
        graph,
        node_id or graph.root_node_id,
        planner,
        specs,
        max_depth=max_depth,
        consumed_spec_ids=consumed_spec_ids,
    )


def expand_relation_decision_branch(
    graph: StateGraph,
    *,
    relation_id: str,
    node_id: str | None = None,
    max_depth: int,
    tree: DecisionTree | None = None,
) -> tuple[DecisionTree, DecisionNode | None, list[str]]:
    spec_map = {spec.node_id: spec for spec in EINSTEIN_NODE_SPECS}
    planner = TickPlanner(max_branch_candidates=EINSTEIN_MAX_BRANCH_CANDIDATES)
    decision_tree = tree or DecisionTree.empty()
    branch_links = collect_relation_links(relation_id, link_kind="branches_to")
    exclude_links = collect_relation_links(relation_id, link_kind="excludes")
    decision, created = expand_decision_spec(
        decision_tree,
        graph,
        node_id or graph.root_node_id,
        planner,
        spec_map[relation_id],
        max_depth=max_depth,
        branch_group_id=(branch_links[0].target_spec_id if branch_links else None),
        exclusion_group_id=(exclude_links[0].target_spec_id if exclude_links else None),
    )
    return decision_tree, decision, created


def reconcile_relation_decision_branch(
    tree: DecisionTree,
    decision_id: str,
    accepted_branch_instance_id: str,
) -> DecisionNode:
    reconcile_decision_branch(tree, decision_id, accepted_branch_instance_id)
    return tree.decisions[decision_id]


def auto_reconcile_relation_decision_branch(
    tree: DecisionTree,
    decision_id: str,
) -> str | None:
    return auto_reconcile_single_survivor(tree, decision_id)


def expand_and_auto_reconcile_relation_decision_branch(
    graph: StateGraph,
    *,
    relation_id: str,
    node_id: str | None = None,
    max_depth: int,
    tree: DecisionTree | None = None,
) -> tuple[DecisionTree, DecisionNode | None, list[str], str | None]:
    decision_tree = tree or DecisionTree.empty()
    target_node_id = node_id or graph.root_node_id
    decision_id = f"{target_node_id}::{relation_id}"
    if decision_id in decision_tree.decisions:
        decision = decision_tree.decisions[decision_id]
        created: list[str] = []
    else:
        decision_tree, decision, created = expand_relation_decision_branch(
            graph,
            relation_id=relation_id,
            node_id=target_node_id,
            max_depth=max_depth,
            tree=decision_tree,
        )
    accepted = None
    if decision is not None:
        accepted = auto_reconcile_relation_decision_branch(decision_tree, decision.decision_id)
        decision = decision_tree.decisions[decision.decision_id]
    return decision_tree, decision, created, accepted


def tick_relation_graph_once(
    graph: StateGraph,
    *,
    relation_ids: tuple[str, ...],
    node_id: str | None = None,
    max_depth: int,
    consumed_spec_ids: set[str] | None = None,
) -> tuple[str | None, list[str]]:
    spec_map = {spec.node_id: spec for spec in EINSTEIN_NODE_SPECS}
    specs = [spec_map[item] for item in relation_ids]
    planner = TickPlanner(max_branch_candidates=EINSTEIN_MAX_BRANCH_CANDIDATES)
    target_node_id = node_id or graph.root_node_id
    return tick_once(
        graph,
        target_node_id,
        planner,
        specs,
        max_depth=max_depth,
        consumed_spec_ids=consumed_spec_ids,
    )


def tick_relation_graph_n(
    graph: StateGraph,
    *,
    relation_ids: tuple[str, ...],
    steps: int,
    node_id: str | None = None,
    max_depth: int,
    consumed_spec_ids: set[str] | None = None,
) -> list[tuple[str, list[str]]]:
    spec_map = {spec.node_id: spec for spec in EINSTEIN_NODE_SPECS}
    specs = [spec_map[item] for item in relation_ids]
    planner = TickPlanner(max_branch_candidates=EINSTEIN_MAX_BRANCH_CANDIDATES)
    target_node_id = node_id or graph.root_node_id
    return tick_n(
        graph,
        target_node_id,
        planner,
        specs,
        max_depth=max_depth,
        steps=steps,
        consumed_spec_ids=consumed_spec_ids,
    )


def tick_relation_graph_until_blocked(
    graph: StateGraph,
    *,
    relation_ids: tuple[str, ...],
    node_id: str | None = None,
    max_depth: int,
    consumed_spec_ids: set[str] | None = None,
) -> tuple[list[tuple[str, list[str]]], str]:
    spec_map = {spec.node_id: spec for spec in EINSTEIN_NODE_SPECS}
    specs = [spec_map[item] for item in relation_ids]
    planner = TickPlanner(max_branch_candidates=EINSTEIN_MAX_BRANCH_CANDIDATES)
    target_node_id = node_id or graph.root_node_id
    return tick_until_blocked(
        graph,
        target_node_id,
        planner,
        specs,
        max_depth=max_depth,
        consumed_spec_ids=consumed_spec_ids,
    )


def build_demo_relation_frontier(*, contradictory: bool = False) -> tuple[list[HypothesisEntry], dict[str, object]]:
    entries = [
        next(item for item in build_relation_candidate_checklist(relation_id="englishman-red") if item.metadata["house"] == "house-1"),
        next(item for item in build_relation_candidate_checklist(relation_id="spaniard-dog") if item.metadata["house"] == "house-2"),
        next(item for item in build_relation_candidate_checklist(relation_id="green-coffee") if item.metadata["house"] == "house-5"),
        next(item for item in build_positional_relation_checklist(relation_id="green-right-of-white")),
    ]
    context: dict[str, object] = {
        "nationality_by_house": {"house-1": "englishman", "house-2": "spaniard"},
        "color_by_house": {"house-1": "red", "house-4": "white", "house-5": "green"},
        "pet_by_house": {"house-2": "dog"},
        "drink_by_house": {"house-5": "coffee"},
        "color_house": {"red": 1, "white": 4, "green": 5},
    }
    if contradictory:
        context["color_house"] = {"red": 1, "white": 3, "green": 5}
        context["color_by_house"] = {"house-1": "red", "house-3": "white", "house-5": "green"}
    return entries, context


def build_ordered_frontier_from_context(
    relation_ids: tuple[str, ...],
    context: dict[str, object],
) -> list[HypothesisEntry]:
    planner = TickPlanner(max_branch_candidates=EINSTEIN_MAX_BRANCH_CANDIDATES)
    snapshot = StateSnapshot.from_values({key: dict(value) for key, value in context.items()})
    spec_map = {spec.node_id: spec for spec in EINSTEIN_NODE_SPECS}
    entries: list[HypothesisEntry] = []
    for relation_id in relation_ids:
        spec = spec_map[relation_id]
        instances = planner.materialize(spec, snapshot)
        if not instances:
            raise ValueError(f"Could not materialize spec {relation_id}")
        entries.append(node_instance_to_entry(spec, instances[0]))
    return entries


def build_first_text_frontier(*, contradictory: bool = False) -> tuple[list[HypothesisEntry], dict[str, object]]:
    context: dict[str, object] = {
        "nationality_by_house": {
            "house-1": "englishman",
            "house-2": "spaniard",
            "house-3": "ukrainian",
        },
        "color_by_house": {
            "house-1": "red",
            "house-2": "yellow",
            "house-4": "white",
            "house-5": "green",
        },
        "pet_by_house": {
            "house-2": "dog",
            "house-1": "snails",
        },
        "drink_by_house": {
            "house-5": "coffee",
            "house-3": "tea",
        },
        "smoke_by_house": {
            "house-1": "old-gold",
            "house-2": "kool",
        },
        "color_house": {"red": 1, "yellow": 2, "white": 4, "green": 5},
    }
    if contradictory:
        context["smoke_by_house"] = {
            "house-1": "old-gold",
            "house-2": "chesterfield",
        }
    entries = build_ordered_frontier_from_context(FIRST_TEXT_RELATION_ORDER, context)
    return entries, context


def build_direct_givens_context() -> dict[str, object]:
    context: dict[str, object] = {
        "__universes__": {key: list(value) for key, value in EINSTEIN_NAMESPACE_UNIVERSES.items()},
    }
    for given in DIRECT_GIVENS:
        bucket = context.setdefault(given.container, {})
        if isinstance(bucket, dict):
            bucket[given.key] = given.value
        if given.container.endswith("_by_house") and given.key.startswith("house-"):
            house_index = int(given.key.split("-", 1)[1])
            inverse_bucket = context.setdefault(f"{given.container[:-9]}_house", {})
            if isinstance(inverse_bucket, dict):
                inverse_bucket[given.value] = house_index
    return context


def build_einstein_entities() -> dict[EntityRef, EntityValue]:
    entities: dict[EntityRef, EntityValue] = {}
    for house in HOUSES:
        ref = EntityRef("house", house)
        entities[ref] = EntityValue(ref=ref, labels=(house,))
    for category, values in CATEGORY_VALUES.items():
        for value in values:
            ref = EntityRef(category, value)
            entities[ref] = EntityValue(ref=ref, labels=(value,))
    return entities


def build_einstein_house_slots() -> dict[SlotRef, SlotCell]:
    return {
        SlotRef("house_slot", house): SlotCell(ref=SlotRef("house_slot", house))
        for house in HOUSES
    }


def attach_first_relation_rule_to_house_slots(
    slots: dict[SlotRef, SlotCell],
) -> dict[SlotRef, SlotCell]:
    entities = build_einstein_entities()
    englishman = entities[EntityRef("nationality", "englishman")].ref
    red = entities[EntityRef("color", "red")].ref
    for house in HOUSES:
        slot = slots[SlotRef("house_slot", house)]
        attach_entity_to_slot(slot, englishman)
        attach_entity_to_slot(slot, red)
        attach_rule_to_slot(slot, "englishman-red")
    return slots


def build_atomic_rule_lambdas() -> tuple[DomainRuleLambda, ...]:
    from .cases.einstein.schema_data import build_einstein_schema

    logic = LogicGenerator(build_einstein_schema())
    rules: list[DomainRuleLambda] = []
    for relation in RELATION_CANDIDATE_SPECS:
        generated = logic.build_atomic_lambda(
            RuleSpec(
                type="same",
                fact=(
                    f"{relation.left.namespace.removesuffix('_by_house')}:{relation.left.value}",
                    f"{relation.right.namespace.removesuffix('_by_house')}:{relation.right.value}",
                ),
            ),
            container_type="house_slot",
        )
        rules.append(
            DomainRuleLambda(
                rule_id=relation.relation_id,
                container_type=generated.container_type,
                relation_kind=generated.relation_kind,
                left_type_ref=generated.left_type_ref,
                right_type_ref=generated.right_type_ref,
                left_entity=generated.left_entity,
                right_entity=generated.right_entity,
                distance=generated.distance,
                metadata={"statement": relation.statement, "relation_kind": relation.relation_kind},
            )
        )
    for relation in POSITIONAL_RELATION_SPECS:
        generated = logic.build_atomic_lambda(
            RuleSpec(
                type="next_to" if relation.relation_kind == "adjacent_pair" else "directly_right",
                fact=(
                    f"{relation.right.namespace.removesuffix('_house')}:{relation.right.value}",
                    f"{relation.left.namespace.removesuffix('_house')}:{relation.left.value}",
                )
                if relation.relation_kind == "offset_pair"
                else (
                    f"{relation.left.namespace.removesuffix('_house')}:{relation.left.value}",
                    f"{relation.right.namespace.removesuffix('_house')}:{relation.right.value}",
                ),
            ),
            container_type="house_slot",
        )
        rules.append(
            DomainRuleLambda(
                rule_id=relation.relation_id,
                container_type=generated.container_type,
                relation_kind=generated.relation_kind,
                left_type_ref=generated.left_type_ref,
                right_type_ref=generated.right_type_ref,
                left_entity=generated.left_entity,
                right_entity=generated.right_entity,
                distance=generated.distance,
                metadata={"statement": relation.statement, "relation_kind": relation.relation_kind},
            )
        )
    return tuple(rules)


def build_atomic_rule_pipeline() -> tuple[RuleStage, ...]:
    entity_link_ids = tuple(rule.rule_id for rule in build_atomic_rule_lambdas() if rule.relation_kind == "same_house_pair")
    positional_filter_ids = tuple(
        rule.rule_id for rule in build_atomic_rule_lambdas() if rule.relation_kind in {"adjacent_pair", "offset_pair"}
    )
    return (
        RuleStage(
            stage_id="entity-link",
            stage_kind="entity_link",
            rule_ids=entity_link_ids,
        ),
        RuleStage(
            stage_id="positional-filter",
            stage_kind="positional_filter",
            rule_ids=positional_filter_ids,
        ),
    )


def build_positional_filter_z_layers() -> tuple[RuleStage, ...]:
    positional_rules = tuple(
        rule for rule in build_atomic_rule_lambdas() if rule.relation_kind in {"adjacent_pair", "offset_pair"}
    )
    return tuple(
        RuleStage(
            stage_id=f"z-filter-{index + 1}",
            stage_kind="positional_filter",
            rule_ids=(rule.rule_id,),
        )
        for index, rule in enumerate(positional_rules)
    )


def build_entity_link_z_layers() -> tuple[RuleStage, ...]:
    entity_rules = tuple(rule for rule in build_atomic_rule_lambdas() if rule.relation_kind == "same_house_pair")
    return tuple(
        RuleStage(
            stage_id=f"z-link-{index + 1}",
            stage_kind="entity_link",
            rule_ids=(rule.rule_id,),
        )
        for index, rule in enumerate(entity_rules)
    )


def build_first_atomic_rule_lambdas() -> tuple[DomainRuleLambda, ...]:
    return tuple(rule for rule in build_atomic_rule_lambdas() if rule.relation_kind == "same_house_pair")


def build_atomic_rule_slot_grid() -> dict[SlotRef, SlotCell]:
    slots = build_einstein_house_slots()
    entities = build_einstein_entities()
    for relation in RELATION_CANDIDATE_SPECS:
        left = entities[EntityRef(relation.left.namespace.removesuffix("_by_house"), relation.left.value)].ref
        right = entities[EntityRef(relation.right.namespace.removesuffix("_by_house"), relation.right.value)].ref
        for house in HOUSES:
            slot = slots[SlotRef("house_slot", house)]
            attach_entity_to_slot(slot, left)
            attach_entity_to_slot(slot, right)
            attach_rule_to_slot(slot, relation.relation_id)
    for relation in POSITIONAL_RELATION_SPECS:
        left = entities[EntityRef(relation.left.namespace.removesuffix("_house"), relation.left.value)].ref
        right = entities[EntityRef(relation.right.namespace.removesuffix("_house"), relation.right.value)].ref
        for house in HOUSES:
            slot = slots[SlotRef("house_slot", house)]
            attach_entity_to_slot(slot, left)
            attach_entity_to_slot(slot, right)
            attach_rule_to_slot(slot, relation.relation_id)
    return slots


def build_first_atomic_rule_slot_grid() -> dict[SlotRef, SlotCell]:
    return build_atomic_rule_slot_grid()


def bind_first_atomic_rules_to_slots(
    slots: dict[SlotRef, SlotCell] | None = None,
) -> tuple[RuleRegistry, list[CellBinding], dict[SlotRef, SlotCell]]:
    slot_grid = slots or build_first_atomic_rule_slot_grid()
    registry = RuleRegistry()
    bindings: list[CellBinding] = []
    for rule in build_first_atomic_rule_lambdas():
        for slot in slot_grid.values():
            if slot.ref.slot_type != rule.container_type:
                continue
            bindings.append(bind_rule_to_slot(registry, slot, rule))
    return registry, bindings, slot_grid


def bind_atomic_rules_to_slots(
    slots: dict[SlotRef, SlotCell] | None = None,
) -> tuple[RuleRegistry, list[CellBinding], dict[SlotRef, SlotCell]]:
    slot_grid = slots or build_atomic_rule_slot_grid()
    registry = RuleRegistry()
    bindings: list[CellBinding] = []
    for rule in build_atomic_rule_lambdas():
        for slot in slot_grid.values():
            if slot.ref.slot_type != rule.container_type:
                continue
            bindings.append(bind_rule_to_slot(registry, slot, rule))
    return registry, bindings, slot_grid


def bind_atomic_rule_pipeline_to_slots(
    slots: dict[SlotRef, SlotCell] | None = None,
) -> tuple[RuleRegistry, dict[str, list[CellBinding]], dict[SlotRef, SlotCell]]:
    slot_grid = slots or build_atomic_rule_slot_grid()
    registry = RuleRegistry()
    rules_by_id = {rule.rule_id: rule for rule in build_atomic_rule_lambdas()}
    stage_bindings: dict[str, list[CellBinding]] = {}
    for stage in build_atomic_rule_pipeline():
        stage_bindings[stage.stage_id] = []
        for rule_id in stage.rule_ids:
            rule = rules_by_id[rule_id]
            for slot in slot_grid.values():
                if slot.ref.slot_type != rule.container_type:
                    continue
                stage_bindings[stage.stage_id].append(bind_rule_to_slot(registry, slot, rule))
    return registry, stage_bindings, slot_grid


def apply_first_atomic_rule_lambda(
    rule_id: str,
    trigger: EntityRef,
    *,
    slots: dict[SlotRef, SlotCell] | None = None,
) -> PossibleArgumentMatrix:
    rule = next(item for item in build_first_atomic_rule_lambdas() if item.rule_id == rule_id)
    return apply_same_container_rule(rule, trigger, slots or build_first_atomic_rule_slot_grid())


def apply_atomic_rule_lambda(
    rule_id: str,
    trigger: EntityRef,
    *,
    slots: dict[SlotRef, SlotCell] | None = None,
) -> PossibleArgumentMatrix:
    slot_grid = slots or build_atomic_rule_slot_grid()
    rule = next(item for item in build_atomic_rule_lambdas() if item.rule_id == rule_id)
    matrix = apply_atomic_rule(rule, trigger, slot_grid)
    z_key = f"{rule.rule_id}:{trigger.entity_type}:{trigger.entity_id}"
    for row in matrix.rows:
        slot = slot_grid[row.slot_ref]
        for entity in row.excluded_entities:
            exclude_entity_from_slot(slot, z_key, entity)
    return matrix


def throw_argument_across_positional_z(
    trigger: EntityRef,
    *,
    slots: dict[SlotRef, SlotCell] | None = None,
) -> tuple[list[PositionalFilterLayer], dict[SlotRef, SlotCell]]:
    slot_grid = slots or build_atomic_rule_slot_grid()
    rules_by_id = {rule.rule_id: rule for rule in build_atomic_rule_lambdas()}
    layers: list[PositionalFilterLayer] = []
    for z_index, stage in enumerate(build_positional_filter_z_layers(), start=1):
        rule_id = stage.rule_ids[0]
        rule = rules_by_id[rule_id]
        matrix = apply_atomic_rule(rule, trigger, slot_grid)
        z_key = f"{rule.rule_id}:{trigger.entity_type}:{trigger.entity_id}"
        for row in matrix.rows:
            slot = slot_grid[row.slot_ref]
            for entity in row.excluded_entities:
                exclude_entity_from_slot(slot, z_key, entity)
        layers.append(
            PositionalFilterLayer(
                z_index=z_index,
                rule_id=rule_id,
                trigger=trigger,
                matrix=matrix,
            )
        )
    return layers, slot_grid


def throw_argument_across_entity_links_z(
    trigger: EntityRef,
    *,
    slots: dict[SlotRef, SlotCell] | None = None,
) -> tuple[list[EntityLinkLayer], dict[SlotRef, SlotCell]]:
    slot_grid = slots or build_atomic_rule_slot_grid()
    rules_by_id = {rule.rule_id: rule for rule in build_atomic_rule_lambdas()}
    layers: list[EntityLinkLayer] = []
    for z_index, stage in enumerate(build_entity_link_z_layers(), start=1):
        rule_id = stage.rule_ids[0]
        rule = rules_by_id[rule_id]
        matrix = apply_atomic_rule(rule, trigger, slot_grid)
        z_key = f"{rule.rule_id}:{trigger.entity_type}:{trigger.entity_id}"
        for row in matrix.rows:
            slot = slot_grid[row.slot_ref]
            for entity in row.excluded_entities:
                exclude_entity_from_slot(slot, z_key, entity)
        layers.append(
            EntityLinkLayer(
                z_index=z_index,
                rule_id=rule_id,
                trigger=trigger,
                matrix=matrix,
            )
        )
    return layers, slot_grid


def throw_argument_across_atomic_z(
    trigger: EntityRef,
    *,
    slots: dict[SlotRef, SlotCell] | None = None,
) -> tuple[list[EntityLinkLayer], list[PositionalFilterLayer], dict[SlotRef, SlotCell]]:
    slot_grid = slots or build_atomic_rule_slot_grid()
    entity_layers, slot_grid = throw_argument_across_entity_links_z(trigger, slots=slot_grid)
    positional_layers, slot_grid = throw_argument_across_positional_z(trigger, slots=slot_grid)
    return entity_layers, positional_layers, slot_grid


def render_atomic_rule_list() -> str:
    rules = build_atomic_rule_lambdas()
    lines = [
        "| rule_id | stage | relation_kind | left | right |",
        "| --- | --- | --- | --- | --- |",
    ]
    stage_by_rule = {
        rule_id: stage.stage_id
        for stage in build_atomic_rule_pipeline()
        for rule_id in stage.rule_ids
    }
    for rule in rules:
        lines.append(
            f"| {rule.rule_id} | {stage_by_rule.get(rule.rule_id, '-')} | {rule.relation_kind} | "
            f"{rule.left_entity.entity_id} | {rule.right_entity.entity_id} |"
        )
    return "\n".join(lines)


def _atomic_rule_signature(rule: DomainRuleLambda) -> str:
    if rule.relation_kind == "same_house_pair":
        return (
            f"lambda trigger in {{{rule.left_entity.entity_id}, {rule.right_entity.entity_id}}}: "
            f"same_slot({rule.left_entity.entity_id} <-> {rule.right_entity.entity_id})"
        )
    if rule.relation_kind == "adjacent_pair":
        return (
            f"lambda trigger in {{{rule.left_entity.entity_id}, {rule.right_entity.entity_id}}}: "
            f"adjacent_slot({rule.left_entity.entity_id} <-> {rule.right_entity.entity_id})"
        )
    if rule.relation_kind == "offset_pair":
        return (
            f"lambda trigger in {{{rule.left_entity.entity_id}, {rule.right_entity.entity_id}}}: "
            f"offset_slot({rule.left_entity.entity_id} -> {rule.right_entity.entity_id}, d={rule.distance})"
        )
    return f"lambda trigger: {rule.relation_kind}"


def render_atomic_slot_field(slots: dict[SlotRef, SlotCell]) -> str:
    lines = [
        "| slot | candidates | rules | z_exclusions |",
        "| --- | --- | --- | --- |",
    ]
    for slot_ref in sorted(slots, key=lambda item: int(item.slot_id.split("-", 1)[1])):
        slot = slots[slot_ref]
        candidates = ", ".join(
            f"{entity.entity_type}:{entity.entity_id}"
            for entity in sorted(slot.candidate_entities, key=lambda item: (item.entity_type, item.entity_id))
        ) or "-"
        rules = ", ".join(slot.rule_ids) or "-"
        exclusions = "; ".join(
            f"{z_key} -> {', '.join(sorted(f'{entity.entity_type}:{entity.entity_id}' for entity in entities))}"
            for z_key, entities in sorted(slot.z_exclusions.items())
        ) or "-"
        lines.append(f"| {slot_ref.slot_id} | {candidates} | {rules} | {exclusions} |")
    return "\n".join(lines)


def render_atomic_rule_stage_views() -> str:
    slots = build_atomic_rule_slot_grid()
    sections: list[str] = []
    for stage in build_atomic_rule_pipeline():
        stage_slots = build_atomic_rule_slot_grid()
        lines = [
            f"## Stage `{stage.stage_id}`",
            "",
            f"- kind: `{stage.stage_kind}`",
            f"- rules: `{', '.join(stage.rule_ids)}`",
            "",
        ]
        for rule_id in stage.rule_ids:
            rule = next(item for item in build_atomic_rule_lambdas() if item.rule_id == rule_id)
            trigger = rule.left_entity
            apply_atomic_rule_lambda(rule_id, trigger, slots=stage_slots)
        lines.append(render_atomic_slot_field(stage_slots))
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def render_atomic_rule_uix_markdown() -> str:
    slots = build_atomic_rule_slot_grid()
    return "\n".join(
        [
            "# Einstein Atomic Rule UIX",
            "",
            "## Atomic Rules",
            "",
            render_atomic_rule_list(),
            "",
            "## Base Field",
            "",
            render_atomic_slot_field(slots),
            "",
            render_atomic_rule_stage_views(),
        ]
    )


def _serialize_slot_field(slots: dict[SlotRef, SlotCell]) -> list[dict[str, object]]:
    return [
        {
            "slot_id": slot_ref.slot_id,
            "slot_type": slot_ref.slot_type,
            "candidates": [
                {"entity_type": entity.entity_type, "entity_id": entity.entity_id}
                for entity in sorted(slot.candidate_entities, key=lambda item: (item.entity_type, item.entity_id))
            ],
            "rules": list(slot.rule_ids),
            "z_exclusions": {
                z_key: [
                    {"entity_type": entity.entity_type, "entity_id": entity.entity_id}
                    for entity in sorted(entities, key=lambda item: (item.entity_type, item.entity_id))
                ]
                for z_key, entities in sorted(slot.z_exclusions.items())
            },
        }
        for slot_ref, slot in sorted(slots.items(), key=lambda item: int(item[0].slot_id.split("-", 1)[1]))
    ]


def build_atomic_rule_uix_payload() -> dict[str, object]:
    slots = build_atomic_rule_slot_grid()
    rules = build_atomic_rule_lambdas()
    stages = build_atomic_rule_pipeline()
    rule_views: dict[str, dict[str, object]] = {}
    for rule in rules:
        left_matrix = apply_atomic_rule_lambda(rule.rule_id, rule.left_entity, slots=build_atomic_rule_slot_grid())
        right_matrix = apply_atomic_rule_lambda(rule.rule_id, rule.right_entity, slots=build_atomic_rule_slot_grid())
        rule_views[rule.rule_id] = {
            "left_trigger": {
                "entity_type": rule.left_entity.entity_type,
                "entity_id": rule.left_entity.entity_id,
                "rows": [
                    {
                        "slot_id": row.slot_ref.slot_id,
                        "possible": [
                            {"entity_type": entity.entity_type, "entity_id": entity.entity_id}
                            for entity in row.possible_entities
                        ],
                        "excluded": [
                            {"entity_type": entity.entity_type, "entity_id": entity.entity_id}
                            for entity in row.excluded_entities
                        ],
                    }
                    for row in left_matrix.rows
                ],
                "field": _serialize_slot_field(build_atomic_rule_slot_grid() if rule.relation_kind == "same_house_pair" else (lambda s: (apply_atomic_rule_lambda(rule.rule_id, rule.left_entity, slots=s), s)[1])(build_atomic_rule_slot_grid())),
            },
            "right_trigger": {
                "entity_type": rule.right_entity.entity_type,
                "entity_id": rule.right_entity.entity_id,
                "rows": [
                    {
                        "slot_id": row.slot_ref.slot_id,
                        "possible": [
                            {"entity_type": entity.entity_type, "entity_id": entity.entity_id}
                            for entity in row.possible_entities
                        ],
                        "excluded": [
                            {"entity_type": entity.entity_type, "entity_id": entity.entity_id}
                            for entity in row.excluded_entities
                        ],
                    }
                    for row in right_matrix.rows
                ],
                "field": _serialize_slot_field(build_atomic_rule_slot_grid() if rule.relation_kind == "same_house_pair" else (lambda s: (apply_atomic_rule_lambda(rule.rule_id, rule.right_entity, slots=s), s)[1])(build_atomic_rule_slot_grid())),
            },
        }
    return {
        "rules": [
            {
                "rule_id": rule.rule_id,
                "relation_kind": rule.relation_kind,
                "signature": _atomic_rule_signature(rule),
                "left": {"entity_type": rule.left_entity.entity_type, "entity_id": rule.left_entity.entity_id},
                "right": {"entity_type": rule.right_entity.entity_type, "entity_id": rule.right_entity.entity_id},
            }
            for rule in rules
        ],
        "stages": [
            {
                "stage_id": stage.stage_id,
                "stage_kind": stage.stage_kind,
                "rule_ids": list(stage.rule_ids),
            }
            for stage in stages
        ],
        "base_field": _serialize_slot_field(slots),
        "rule_views": rule_views,
    }


def render_atomic_rule_uix_html() -> str:
    payload = json.dumps(build_atomic_rule_uix_payload(), ensure_ascii=False)
    template = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Einstein Atomic Rule UIX</title>
  <style>
    :root {{
      --bg: #f4efe6;
      --paper: #fffaf1;
      --ink: #1f1a17;
      --muted: #76685d;
      --line: #d8c8b5;
      --accent: #aa4a1f;
      --accent-soft: #f3d6c8;
      --stage: #e7dfcf;
      --ok: #285943;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #f8e7d6, transparent 28%),
        radial-gradient(circle at top right, #e7efe2, transparent 24%),
        linear-gradient(180deg, #f2eadf, #f7f1e7 55%, #efe6da);
    }}
    .shell {{
      max-width: 1500px;
      margin: 0 auto;
      padding: 24px;
      display: grid;
      grid-template-columns: 320px 1fr 420px;
      gap: 18px;
    }}
    .panel {{
      background: color-mix(in srgb, var(--paper) 94%, white);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 12px 30px rgba(72, 45, 24, 0.08);
      min-height: 120px;
    }}
    h1, h2, h3 {{ margin: 0 0 12px; font-weight: 600; }}
    h1 {{ font-size: 28px; }}
    h2 {{ font-size: 18px; }}
    h3 {{ font-size: 15px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }}
    .hero {{
      grid-column: 1 / -1;
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: end;
    }}
    .hero p {{ margin: 6px 0 0; max-width: 780px; color: var(--muted); }}
    .stage-list, .rule-list {{ display: flex; flex-direction: column; gap: 10px; }}
    .stage-btn, .rule-btn, .trigger-btn {{
      width: 100%;
      text-align: left;
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      border-radius: 14px;
      padding: 12px 14px;
      cursor: pointer;
      transition: 140ms ease;
    }}
    .stage-btn:hover, .rule-btn:hover, .trigger-btn:hover {{
      border-color: var(--accent);
      transform: translateY(-1px);
    }}
    .stage-btn.active, .rule-btn.active, .trigger-btn.active {{
      background: var(--accent-soft);
      border-color: var(--accent);
    }}
    .badge {{
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      background: var(--stage);
      color: var(--muted);
      font-size: 12px;
      margin-right: 6px;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      vertical-align: top;
    }}
    th {{ text-align: left; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }}
    .chip {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 999px;
      margin: 2px 4px 2px 0;
      background: #f1ece3;
      border: 1px solid #e0d3c3;
      font-size: 12px;
    }}
    .chip.excluded {{ background: #f7d9d2; border-color: #e9ab9d; }}
    .chip.possible {{ background: #dceee3; border-color: #9ac6af; }}
    .grid-head {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      margin-bottom: 12px;
    }}
    .trigger-row {{
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
    }}
    .mini {{
      color: var(--muted);
      font-size: 12px;
    }}
    .sig {{
      display: block;
      margin-top: 6px;
      padding: 10px 12px;
      border-radius: 12px;
      background: #f6efe6;
      border: 1px solid #e8d7c4;
      font-family: "Cascadia Code", "Consolas", monospace;
      font-size: 12px;
      color: #5f3f2b;
      white-space: pre-wrap;
    }}
    @media (max-width: 1180px) {{
      .shell {{ grid-template-columns: 1fr; }}
      .hero {{ display: block; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="panel hero">
      <div>
        <h1>Einstein Atomic Rule Sandbox</h1>
        <p>Интерактивный UIX для атомарных лямбд: слева stages, по центру правило и trigger, справа поле со списками possible и вычёркиваниями по Z.</p>
      </div>
      <div class="meta">
        <span class="badge" id="rule-count"></span>
        <span class="badge" id="stage-count"></span>
      </div>
    </section>
    <aside class="panel">
      <h2>Stages</h2>
      <div id="stage-list" class="stage-list"></div>
    </aside>
    <main class="panel">
      <div class="grid-head">
        <div>
          <h2 id="rule-title">Rule</h2>
          <div class="mini" id="rule-meta"></div>
          <div id="rule-signature" class="sig"></div>
        </div>
      </div>
      <div id="rule-list" class="rule-list"></div>
    </main>
    <aside class="panel">
      <h2>Field</h2>
      <div class="trigger-row" id="trigger-row"></div>
      <div class="mini" id="trigger-meta"></div>
      <div id="field-view"></div>
    </aside>
  </div>
  <script id="payload-json" type="application/json">__PAYLOAD__</script>
  <script>
    const payload = JSON.parse(document.getElementById("payload-json").textContent);
    const state = {{
      stageId: payload.stages[0]?.stage_id ?? null,
      ruleId: payload.stages[0]?.rule_ids[0] ?? null,
      triggerSide: "left_trigger",
    }};

    const stageList = document.getElementById("stage-list");
    const ruleList = document.getElementById("rule-list");
    const fieldView = document.getElementById("field-view");
    const triggerRow = document.getElementById("trigger-row");
    const triggerMeta = document.getElementById("trigger-meta");
    const ruleTitle = document.getElementById("rule-title");
    const ruleMeta = document.getElementById("rule-meta");
    const ruleSignature = document.getElementById("rule-signature");
    document.getElementById("rule-count").textContent = `${payload.rules.length} rules`;
    document.getElementById("stage-count").textContent = `${payload.stages.length} stages`;

    function ruleById(ruleId) {{
      return payload.rules.find((rule) => rule.rule_id === ruleId);
    }}

    function stageById(stageId) {{
      return payload.stages.find((stage) => stage.stage_id === stageId);
    }}

    function renderStages() {{
      stageList.innerHTML = "";
      for (const stage of payload.stages) {{
        const button = document.createElement("button");
        button.className = "stage-btn" + (stage.stage_id === state.stageId ? " active" : "");
        button.innerHTML = `<strong>${{stage.stage_id}}</strong><div class="mini">${{stage.stage_kind}} · ${{stage.rule_ids.length}} rules</div>`;
        button.onclick = () => {{
          state.stageId = stage.stage_id;
          state.ruleId = stage.rule_ids[0];
          state.triggerSide = "left_trigger";
          render();
        }};
        stageList.appendChild(button);
      }}
    }}

    function renderRules() {{
      const stage = stageById(state.stageId);
      const selectedRule = ruleById(state.ruleId);
      ruleList.innerHTML = "";
      ruleTitle.textContent = stage ? `Rules / ${stage.stage_id}` : "Rules";
      ruleMeta.textContent = stage ? `${stage.stage_kind}` : "";
      ruleSignature.textContent = selectedRule ? selectedRule.signature : "";
      for (const ruleId of stage.rule_ids) {{
        const rule = ruleById(ruleId);
        const button = document.createElement("button");
        button.className = "rule-btn" + (rule.rule_id === state.ruleId ? " active" : "");
        button.innerHTML = `
          <strong>${rule.rule_id}</strong>
          <div class="mini">${rule.relation_kind} · ${rule.left.entity_id} ↔ ${rule.right.entity_id}</div>
        `;
        button.onclick = () => {{
          state.ruleId = rule.rule_id;
          state.triggerSide = "left_trigger";
          renderField();
          renderRules();
        }};
        ruleList.appendChild(button);
      }}
    }}

    function chips(items, cssClass="") {{
      if (!items.length) return '<span class="mini">-</span>';
      return items.map((item) => `<span class="chip ${cssClass}">${item.entity_type}:${item.entity_id}</span>`).join("");
    }}

    function renderField() {{
      const rule = ruleById(state.ruleId);
      const view = payload.rule_views[state.ruleId][state.triggerSide];
      triggerRow.innerHTML = "";
      [["left_trigger", rule.left], ["right_trigger", rule.right]].forEach(([key, entity]) => {{
        const button = document.createElement("button");
        button.className = "trigger-btn" + (key === state.triggerSide ? " active" : "");
        button.textContent = `${entity.entity_type}:${entity.entity_id}`;
        button.onclick = () => {{
          state.triggerSide = key;
          renderField();
        }};
        triggerRow.appendChild(button);
      }});
      triggerMeta.textContent = `trigger: ${view.entity_type}:${view.entity_id}`;
      const rows = view.rows.map((row) => {{
        const fieldSlot = view.field.find((item) => item.slot_id === row.slot_id);
        const zText = Object.entries(fieldSlot.z_exclusions || {{}})
          .map(([key, entities]) => `${key}: ${entities.map((entity) => `${entity.entity_type}:${entity.entity_id}`).join(", ")}`)
          .join("<br>") || '<span class="mini">-</span>';
        return `
          <tr>
            <td>${row.slot_id}</td>
            <td>${chips(fieldSlot.candidates)}</td>
            <td>${chips(row.possible, "possible")}</td>
            <td>${chips(row.excluded, "excluded")}</td>
            <td>${zText}</td>
          </tr>
        `;
      }}).join("");
      fieldView.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>slot</th>
              <th>base candidates</th>
              <th>possible</th>
              <th>excluded</th>
              <th>z-layer</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }}

    function render() {{
      renderStages();
      renderRules();
      renderField();
    }}

    render();
  </script>
</body>
</html>"""
    normalized = template.replace("{{", "{").replace("}}", "}")
    return normalized.replace("__PAYLOAD__", payload)


def build_einstein_worker_cells() -> dict[WorkerRef, WorkerCell]:
    workers: dict[WorkerRef, WorkerCell] = {}
    for namespace, values in EINSTEIN_NAMESPACE_UNIVERSES.items():
        for house in HOUSES:
            ref = WorkerRef(worker_type=namespace, worker_id=house)
            workers[ref] = WorkerCell(ref=ref, domain=set(values))
        connect_worker_neighbors(
            workers,
            tuple(WorkerRef(namespace, house) for house in HOUSES),
        )
    return workers


def build_einstein_argument_envelopes(
    *,
    relation_ids: tuple[str, ...] | None = None,
) -> tuple[dict[ArgumentRef, ArgumentEnvelope], list[RuleBinding]]:
    selected_ids = set(relation_ids or ALL_RELATION_ORDER)
    workers = build_einstein_worker_cells()
    envelopes: dict[ArgumentRef, ArgumentEnvelope] = {}
    bindings: list[RuleBinding] = []

    for spec in EINSTEIN_NODE_SPECS:
        if spec.node_id not in selected_ids:
            continue
        payload = spec.payload
        if isinstance(payload, SameHousePair):
            arg_ref = ArgumentRef("same_house_pair", spec.node_id)
            envelopes[arg_ref] = ArgumentEnvelope(
                ref=arg_ref,
                subtype="same_house_pair",
                values={payload.left_value, payload.right_value},
                metadata={
                    "rule_id": spec.node_id,
                    "left_ns": payload.left_ns,
                    "right_ns": payload.right_ns,
                },
            )
            for namespace in (payload.left_ns, payload.right_ns):
                for house in payload.universe_keys:
                    binding = attach_argument_to_worker(
                        workers[WorkerRef(namespace, house)],
                        envelopes[arg_ref],
                        rule_id=spec.node_id,
                    )
                    bindings.append(binding)
            continue
        if isinstance(payload, AdjacentPair):
            arg_ref = ArgumentRef("adjacent_pair", spec.node_id)
            envelopes[arg_ref] = ArgumentEnvelope(
                ref=arg_ref,
                subtype="adjacent_pair",
                values={payload.left_value, payload.right_value},
                metadata={
                    "rule_id": spec.node_id,
                    "left_ns": payload.left_ns,
                    "right_ns": payload.right_ns,
                },
            )
            for namespace in (payload.left_ns.replace("_house", "_by_house"), payload.right_ns.replace("_house", "_by_house")):
                for house in HOUSES:
                    binding = attach_argument_to_worker(
                        workers[WorkerRef(namespace, house)],
                        envelopes[arg_ref],
                        rule_id=spec.node_id,
                    )
                    attach_operation_to_worker(workers[WorkerRef(namespace, house)], "adjacent_pair")
                    bindings.append(binding)
            continue
        if isinstance(payload, OffsetPair):
            arg_ref = ArgumentRef("offset_pair", spec.node_id)
            envelopes[arg_ref] = ArgumentEnvelope(
                ref=arg_ref,
                subtype="offset_pair",
                values={payload.left_value, payload.right_value},
                metadata={
                    "rule_id": spec.node_id,
                    "left_ns": payload.left_ns,
                    "right_ns": payload.right_ns,
                    "distance": payload.distance,
                },
            )
            for namespace in (payload.left_ns.replace("_house", "_by_house"), payload.right_ns.replace("_house", "_by_house")):
                for house in HOUSES:
                    binding = attach_argument_to_worker(
                        workers[WorkerRef(namespace, house)],
                        envelopes[arg_ref],
                        rule_id=spec.node_id,
                    )
                    attach_operation_to_worker(workers[WorkerRef(namespace, house)], "offset_pair")
                    bindings.append(binding)
            continue
    return envelopes, bindings


def summarize_state_graph(graph: StateGraph) -> str:
    lines = [
        "| node_id | depth | status | derived_from |",
        "| --- | --- | --- | --- |",
    ]
    for node in sorted(graph.nodes.values(), key=lambda item: (item.depth, item.node_id)):
        lines.append(
            f"| {node.node_id} | {node.depth} | {node.status} | {node.derived_from_edge_id or '-'} |"
        )
    lines.append("")
    lines.append("| edge_id | hypothesis_id | status | to_node_id |")
    lines.append("| --- | --- | --- | --- |")
    for edge in sorted(graph.edges.values(), key=lambda item: item.edge_id):
        lines.append(f"| {edge.edge_id} | {edge.hypothesis_id} | {edge.status} | {edge.to_node_id} |")
    return "\n".join(lines)


def render_einstein_state_table(values: dict[str, object]) -> str:
    namespace_map = {
        "nationality": "nationality_by_house",
        "color": "color_by_house",
        "drink": "drink_by_house",
        "pet": "pet_by_house",
        "smoke": "smoke_by_house",
    }
    lines = [
        "| house | nationality | color | drink | pet | smoke |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for house in HOUSES:
        row_values = []
        for category in ("nationality", "color", "drink", "pet", "smoke"):
            namespace = namespace_map[category]
            bucket = values.get(namespace, {})
            row_values.append(bucket.get(house, "-") if isinstance(bucket, dict) else "-")
        lines.append(f"| {house} | " + " | ".join(row_values) + " |")
    return "\n".join(lines)


def render_tick_events_table(events: list[tuple[str, list[str]]]) -> str:
    lines = [
        "| spec_id | created_nodes |",
        "| --- | --- |",
    ]
    for spec_id, created in events:
        created_label = ", ".join(created) if created else "-"
        lines.append(f"| {spec_id} | {created_label} |")
    return "\n".join(lines)


def render_loop_events_table(events: list[LoopEvent]) -> str:
    lines = [
        "| kind | spec_id | node_id | created_nodes | accepted_branch | status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for event in events:
        created = ", ".join(event.created_node_ids) if event.created_node_ids else "-"
        accepted = event.accepted_branch_id or "-"
        status = event.status or "-"
        lines.append(
            f"| {event.kind} | {event.spec_id} | {event.node_id} | {created} | {accepted} | {status} |"
        )
    return "\n".join(lines)


def run_relation_graph_until_blocked(
    context: dict[str, object],
    *,
    relation_ids: tuple[str, ...] = ALL_RELATION_ORDER,
    max_depth: int = 20,
    consumed_spec_ids: set[str] | None = None,
) -> tuple[StateGraph, list[tuple[str, list[str]]], str]:
    graph = StateGraph.from_snapshot(StateSnapshot.from_values({key: dict(value) for key, value in context.items()}))
    events, status = tick_relation_graph_until_blocked(
        graph,
        relation_ids=relation_ids,
        max_depth=max_depth,
        consumed_spec_ids=consumed_spec_ids,
    )
    return graph, events, status


def run_relation_graph_two_phase_until_blocked(
    context: dict[str, object],
    *,
    relation_ids: tuple[str, ...] = ALL_RELATION_ORDER,
    max_depth: int = 20,
) -> tuple[StateGraph, list[tuple[str, list[str]]], str]:
    graph = StateGraph.from_snapshot(StateSnapshot.from_values({key: dict(value) for key, value in context.items()}))
    planner = TickPlanner(max_branch_candidates=EINSTEIN_MAX_BRANCH_CANDIDATES)
    spec_map = {spec.node_id: spec for spec in EINSTEIN_NODE_SPECS}
    specs = [spec_map[relation_id] for relation_id in relation_ids]
    current_node_id = graph.root_node_id
    attempted_state_specs: set[tuple[str, str]] = set()
    events: list[tuple[str, list[str]]] = []

    while True:
        current_node_id, propagated_events, propagate_status = propagate_until_fixpoint(
            graph,
            current_node_id,
            planner,
            specs,
            max_depth=max_depth,
            attempted_state_specs=attempted_state_specs,
        )
        events.extend(propagated_events)
        if propagate_status == "max_depth":
            return graph, events, "max_depth"
        spec_id, created = branch_on_best_unresolved(
            graph,
            current_node_id,
            planner,
            specs,
            max_depth=max_depth,
            attempted_state_specs=attempted_state_specs,
        )
        if spec_id is None:
            return graph, events, "blocked"
        events.append((spec_id, created))
        if not created:
            return graph, events, "blocked"
        current_node_id = min(
            created,
            key=lambda node_id: (
                graph.nodes[node_id].depth,
                graph.nodes[node_id].snapshot.state_id,
            ),
        )


def run_einstein_solver_until_blocked(
    *,
    max_depth: int = 50,
) -> tuple[StateGraph, list[tuple[str, list[str]]], str]:
    return run_relation_graph_two_phase_until_blocked(
        build_direct_givens_context(),
        relation_ids=EINSTEIN_SOLVER_ORDER,
        max_depth=max_depth,
    )


def render_solver_run_markdown(
    graph: StateGraph,
    events: list[tuple[str, list[str]]],
    status: str,
) -> str:
    deepest = max(graph.nodes.values(), key=lambda node: (node.depth, node.node_id))
    lines = [
        "# Einstein While-Blocked Run",
        "",
        f"- status: `{status}`",
        f"- executed_specs: `{len(events)}`",
        f"- deepest_depth: `{deepest.depth}`",
        "",
        "## Tick Events",
        "",
        render_tick_events_table(events),
        "",
        "## Deepest State",
        "",
        render_einstein_state_table(deepest.snapshot.values),
    ]
    return "\n".join(lines)


def build_decision_demo_graph() -> tuple[StateGraph, DecisionTree, DecisionNode | None, list[str]]:
    graph = StateGraph.from_snapshot(
        StateSnapshot.from_values(
            {
                "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
                "color_by_house": {"house-2": "red", "house-3": "green"},
                "pet_by_house": {"house-4": "dog"},
                "color_house": {"white": 2, "green": 3},
            }
        )
    )
    _, created_seed = search_relation_graph_step(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        max_depth=7,
        consumed_spec_ids={"englishman-red", "spaniard-dog"},
    )
    seed_node_id = created_seed[0]
    tree, decision, created = expand_relation_decision_branch(
        graph,
        relation_id="ukrainian-tea",
        node_id=seed_node_id,
        max_depth=7,
        tree=DecisionTree.empty(),
    )
    return graph, tree, decision, created


def collect_linked_relation_ids(
    start_relation_id: str,
    *,
    link_kind: str = "activates",
    max_hops: int = 8,
) -> tuple[str, ...]:
    spec_map = {spec.node_id: spec for spec in EINSTEIN_NODE_SPECS}
    if start_relation_id not in spec_map:
        raise KeyError(start_relation_id)
    collected = [start_relation_id]
    frontier = [start_relation_id]
    visited = {start_relation_id}
    for _ in range(max_hops):
        next_frontier: list[str] = []
        for current_id in frontier:
            current_spec = spec_map[current_id]
            next_links = [
                link
                for link in current_spec.links
                if link.kind == link_kind and link.target_spec_id not in visited
            ]
            for link in next_links:
                next_id = link.target_spec_id
                collected.append(next_id)
                visited.add(next_id)
                next_frontier.append(next_id)
        if not next_frontier:
            break
        frontier = next_frontier
    return tuple(collected)


def collect_relation_links(
    relation_id: str,
    *,
    link_kind: str | None = None,
) -> tuple[HypothesisLink, ...]:
    spec_map = {spec.node_id: spec for spec in EINSTEIN_NODE_SPECS}
    if relation_id not in spec_map:
        raise KeyError(relation_id)
    links = spec_map[relation_id].links
    if link_kind is None:
        return links
    return tuple(link for link in links if link.kind == link_kind)


def tick_linked_relation_graph_n(
    graph: StateGraph,
    *,
    start_relation_id: str,
    steps: int,
    node_id: str | None = None,
    max_depth: int,
    consumed_spec_ids: set[str] | None = None,
) -> list[tuple[str, list[str]]]:
    return tick_relation_graph_n(
        graph,
        relation_ids=collect_linked_relation_ids(start_relation_id),
        steps=steps,
        node_id=node_id,
        max_depth=max_depth,
        consumed_spec_ids=consumed_spec_ids,
    )


def tick_linked_relation_graph_until_blocked(
    graph: StateGraph,
    *,
    start_relation_id: str,
    node_id: str | None = None,
    max_depth: int,
    consumed_spec_ids: set[str] | None = None,
) -> tuple[list[tuple[str, list[str]]], str]:
    return tick_relation_graph_until_blocked(
        graph,
        relation_ids=collect_linked_relation_ids(start_relation_id),
        node_id=node_id,
        max_depth=max_depth,
        consumed_spec_ids=consumed_spec_ids,
    )


def search_linked_relation_graph_until_blocked(
    graph: StateGraph,
    *,
    start_relation_id: str,
    node_id: str | None = None,
    max_depth: int,
    consumed_spec_ids: set[str] | None = None,
) -> tuple[list[tuple[str, list[str]]], str]:
    return search_relation_graph_until_blocked(
        graph,
        relation_ids=collect_linked_relation_ids(start_relation_id),
        node_id=node_id,
        max_depth=max_depth,
        consumed_spec_ids=consumed_spec_ids,
    )


def run_linked_relation_loop(
    context: dict[str, object],
    *,
    start_relation_id: str,
    max_depth: int = 20,
) -> tuple[StateGraph, DecisionTree, list[tuple[str, list[str]]], list[tuple[str, str | None]], str]:
    graph = StateGraph.from_snapshot(StateSnapshot.from_values({key: dict(value) for key, value in context.items()}))
    tick_events, status = search_linked_relation_graph_until_blocked(
        graph,
        start_relation_id=start_relation_id,
        max_depth=max_depth,
        consumed_spec_ids=set(),
    )
    decision_tree = DecisionTree.empty()
    decision_events: list[tuple[str, str | None]] = []
    current_node_id = graph.root_node_id
    for spec_id, created in tick_events:
        if collect_relation_links(spec_id, link_kind="branches_to") and len(created) > 1:
            decision_tree, decision, _, accepted = expand_and_auto_reconcile_relation_decision_branch(
                graph,
                relation_id=spec_id,
                node_id=current_node_id,
                max_depth=max_depth,
                tree=decision_tree,
            )
            decision_events.append((decision.spec_id if decision is not None else spec_id, accepted))
        if created:
            current_node_id = created[0]
    return graph, decision_tree, tick_events, decision_events, status


def run_linked_relation_loop_trace(
    context: dict[str, object],
    *,
    start_relation_id: str,
    max_depth: int = 20,
    policy: LoopPolicy | None = None,
) -> tuple[StateGraph, DecisionTree, list[LoopEvent], str]:
    loop_policy = policy or LoopPolicy(max_depth=max_depth)
    graph = StateGraph.from_snapshot(StateSnapshot.from_values({key: dict(value) for key, value in context.items()}))
    tick_events, status = search_linked_relation_graph_until_blocked(
        graph,
        start_relation_id=start_relation_id,
        max_depth=loop_policy.max_depth,
        consumed_spec_ids=set(),
    )
    decision_tree = DecisionTree.empty()
    loop_events: list[LoopEvent] = []
    current_node_id = graph.root_node_id
    for spec_id, created in tick_events:
        current_depth = graph.nodes[current_node_id].depth
        loop_events.append(
            LoopEvent(
                kind="tick",
                spec_id=spec_id,
                node_id=current_node_id,
                created_node_ids=tuple(created),
                status="branched" if len(created) > 1 else ("advanced" if created else "stalled"),
            )
        )
        if (
            collect_relation_links(spec_id, link_kind="branches_to")
            and len(created) > 1
            and current_depth < loop_policy.max_branch_depth
        ):
            created = created[: loop_policy.max_parallel_branches]
            decision_tree, decision, _, accepted = expand_and_auto_reconcile_relation_decision_branch(
                graph,
                relation_id=spec_id,
                node_id=current_node_id,
                max_depth=loop_policy.max_depth,
                tree=decision_tree,
            )
            loop_events.append(
                LoopEvent(
                    kind="branch",
                    spec_id=spec_id,
                    node_id=current_node_id,
                    created_node_ids=tuple(created),
                    accepted_branch_id=accepted,
                    decision_id=(decision.decision_id if decision is not None else None),
                    status=(decision.status if decision is not None else "untraced"),
                )
            )
            if accepted is not None:
                loop_events.append(
                    LoopEvent(
                        kind="auto_reconcile",
                        spec_id=spec_id,
                        node_id=current_node_id,
                        accepted_branch_id=accepted,
                        decision_id=(decision.decision_id if decision is not None else None),
                        status="reconciled",
                    )
                )
        if created:
            current_node_id = created[0]
    loop_events.append(
        LoopEvent(
            kind="blocked" if status == "blocked" else "exhausted",
            spec_id="-",
            node_id=current_node_id,
            status=status,
        )
    )
    return graph, decision_tree, loop_events, status


def render_decision_demo_markdown(
    graph: StateGraph,
    tree: DecisionTree,
    decision: DecisionNode | None,
    created_node_ids: list[str],
) -> str:
    lines = [
        "# Einstein Decision Branch Demo",
        "",
        f"- decision: `{decision.spec_id if decision else '-'}`",
        f"- branch_count: `{len(decision.branch_instance_ids) if decision else 0}`",
        f"- created_states: `{len(created_node_ids)}`",
        "",
        "## Decision Tree",
        "",
        render_decision_tree_markdown(tree),
    ]
    for node_id in created_node_ids:
        node = graph.nodes[node_id]
        lines.extend(
            [
                "",
                f"## State {node.node_id}",
                "",
                render_einstein_state_table(node.snapshot.values),
            ]
        )
    return "\n".join(lines)


def _claim_from_rule_spec_by_id(hypothesis_id: str) -> AtomicClaim:
    spec = next(item for item in FIRST_STEP_NODE_SPECS if item.hypothesis_id == hypothesis_id)
    return _claim_from_rule_spec(spec)


def evaluate_einstein_first_step(context: dict[str, object]) -> HypothesisReaction:
    tree, runtime = build_einstein_first_step_tree()
    return runtime.evaluate_connected(tree, "house-1-norwegian-yes", context)


def build_einstein_first_step_outcome(context: dict[str, object]) -> tuple[BranchOutcome, EffectArtifact, StepSnapshot, str]:
    reaction = evaluate_einstein_first_step(context)
    effect = build_einstein_first_step_effects()
    outcome = BranchOutcome.from_reaction(
        reaction,
        outcome_id="einstein-first-step",
        effect_refs=(f"effects/{effect.artifact_id}.json",),
        notes="Initial direct givens and their first linked consequence.",
    )
    snapshot = StepSnapshot(
        step_id="step-0001",
        source_outcome_refs=("analysis/outcome.json",),
        new_fixed_cells=tuple(
            item.subject_ref.subject_id
            for item in effect.transformations
            if item.kind == EffectKind.FIXED_ASSIGNMENT
        ),
        consequences=outcome.consequences,
        notes="First saturated reactive step for Einstein direct givens.",
    )
    llm_text = render_llm_step_output(outcome, [effect])
    return outcome, effect, snapshot, llm_text


def write_einstein_prompt(case_dir: Path) -> Path:
    case_dir.mkdir(parents=True, exist_ok=True)
    question = """На улице стоят пять домов.
Англичанин живёт в красном доме.
У испанца есть собака.
В зелёном доме пьют кофе.
Украинец пьёт чай.
Зелёный дом стоит сразу справа от белого дома.
Тот, кто курит Old Gold, разводит улиток.
В жёлтом доме курят Kool.
В центральном доме пьют молоко.
Норвежец живёт в первом доме.
Сосед того, кто курит Chesterfield, держит лису.
В доме по соседству с тем, в котором держат лошадь, курят Kool.
Тот, кто курит Lucky Strike, пьёт апельсиновый сок.
Японец курит Parliament.
Норвежец живёт рядом с синим домом.
Кто пьёт воду? Кто держит зебру?

Каждый дом имеет уникальный цвет. Все жители разных национальностей, с разными животными, напитками и марками сигарет.
Под "справа" понимается справа относительно наблюдателя."""
    path = case_dir / "question.txt"
    path.write_text(question, encoding="utf-8")
    return path
