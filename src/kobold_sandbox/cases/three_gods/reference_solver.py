from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import permutations

GODS = ("A", "B", "C")
ROLES = ("Truth", "Lie", "Random")


@dataclass(frozen=True)
class ThreeGodsWorld:
    roles: tuple[str, str, str]
    da_means_yes: bool

    def role_of(self, god: str) -> str:
        return self.roles[GODS.index(god)]

    def summary(self) -> str:
        mapping = "DA=yes" if self.da_means_yes else "JA=yes"
        pairs = ", ".join(f"{god}={role}" for god, role in zip(GODS, self.roles, strict=True))
        return f"{pairs}; {mapping}"


@dataclass(frozen=True)
class PredicateSpec:
    name: str

    def evaluate(self, world: ThreeGodsWorld) -> bool:
        if self.name == "DA means yes":
            return world.da_means_yes
        if self.name == "JA means yes":
            return not world.da_means_yes
        god, _, role = self.name.partition(" is ")
        return world.role_of(god) == role


@dataclass(frozen=True)
class StrategyNode:
    possible_worlds: tuple[int, ...]
    respondent: str | None = None
    predicate_name: str | None = None
    branches: dict[str, "StrategyNode"] | None = None

    @property
    def is_leaf(self) -> bool:
        return self.respondent is None

    def resolved_roles(self, worlds: tuple[ThreeGodsWorld, ...]) -> tuple[str, str, str]:
        first = worlds[self.possible_worlds[0]].roles
        return first


def generate_three_gods_worlds() -> tuple[ThreeGodsWorld, ...]:
    worlds: list[ThreeGodsWorld] = []
    for roles in permutations(ROLES):
        for da_means_yes in (True, False):
            worlds.append(ThreeGodsWorld(roles=tuple(roles), da_means_yes=da_means_yes))
    return tuple(worlds)


def build_default_predicates() -> tuple[PredicateSpec, ...]:
    predicates = [PredicateSpec("DA means yes"), PredicateSpec("JA means yes")]
    for god in GODS:
        for role in ROLES:
            predicates.append(PredicateSpec(f"{god} is {role}"))
    return tuple(predicates)


def _word_for_boolean(value: bool, da_means_yes: bool) -> str:
    if value == da_means_yes:
        return "DA"
    return "JA"


def _answer_word(world: ThreeGodsWorld, respondent: str, proposition_value: bool) -> str:
    role = world.role_of(respondent)
    if role == "Truth":
        return _word_for_boolean(proposition_value, world.da_means_yes)
    if role == "Lie":
        return _word_for_boolean(not proposition_value, world.da_means_yes)
    raise ValueError("Random is handled separately.")


def meta_answers(world: ThreeGodsWorld, respondent: str, predicate: PredicateSpec) -> tuple[str, ...]:
    role = world.role_of(respondent)
    if role == "Random":
        return ("DA", "JA")
    proposition_value = predicate.evaluate(world)
    return meta_answers_for_value(world, respondent, proposition_value)


def meta_answers_for_value(world: ThreeGodsWorld, respondent: str, proposition_value: bool) -> tuple[str, ...]:
    role = world.role_of(respondent)
    if role == "Random":
        return ("DA", "JA")
    inner_answer = _answer_word(world, respondent, proposition_value)
    meta_truth = inner_answer == "DA"
    return (_answer_word(world, respondent, meta_truth),)


def solve_three_gods_reference() -> StrategyNode:
    worlds = generate_three_gods_worlds()
    predicates = build_default_predicates()
    atomic_subsets = {
        predicate.name: frozenset(
            world_index
            for world_index, world in enumerate(worlds)
            if predicate.evaluate(world)
        )
        for predicate in predicates
    }

    def predicate_label(subset: frozenset[int]) -> str:
        for name, atomic_subset in atomic_subsets.items():
            if atomic_subset == subset:
                return name
        atomic_names = sorted(atomic_subsets)
        for left_index, left_name in enumerate(atomic_names):
            for right_name in atomic_names[left_index + 1 :]:
                if atomic_subsets[left_name] & atomic_subsets[right_name] == subset:
                    return f"{left_name} and {right_name}"
        if len(subset) == 1:
            world_index = next(iter(subset))
            return worlds[world_index].summary()
        return "world in {" + ", ".join(str(item) for item in sorted(subset)) + "}"

    @lru_cache(maxsize=None)
    def search(possible_worlds: tuple[int, ...], depth: int) -> StrategyNode | None:
        role_signatures = {worlds[index].roles for index in possible_worlds}
        if len(role_signatures) == 1:
            return StrategyNode(possible_worlds=possible_worlds)
        if depth == 0:
            return None

        ordered = tuple(sorted(possible_worlds))
        pivot = ordered[0]
        candidate_subsets: list[frozenset[int]] = []
        for mask in range(1, 1 << len(ordered)):
            subset = frozenset(
                world_index
                for bit_index, world_index in enumerate(ordered)
                if mask & (1 << bit_index)
            )
            if len(subset) == len(ordered):
                continue
            if pivot not in subset:
                continue
            candidate_subsets.append(subset)

        for respondent in GODS:
            for subset in candidate_subsets:
                branch_sets: dict[str, tuple[int, ...]] = {}
                for answer in ("DA", "JA"):
                    branch = tuple(
                        world_index
                        for world_index in possible_worlds
                        if answer in meta_answers_for_value(worlds[world_index], respondent, world_index in subset)
                    )
                    if branch:
                        branch_sets[answer] = branch

                if not branch_sets:
                    continue
                if all(branch == possible_worlds for branch in branch_sets.values()):
                    continue

                child_nodes: dict[str, StrategyNode] = {}
                failed = False
                for answer, branch in branch_sets.items():
                    child = search(branch, depth - 1)
                    if child is None:
                        failed = True
                        break
                    child_nodes[answer] = child
                if failed:
                    continue
                return StrategyNode(
                    possible_worlds=possible_worlds,
                    respondent=respondent,
                    predicate_name=predicate_label(subset),
                    branches=child_nodes,
                )
        return None

    strategy = search(tuple(range(len(worlds))), 3)
    if strategy is None:
        raise RuntimeError("No 3-question strategy found for the current predicate family.")
    return strategy


def render_three_gods_strategy_markdown(strategy: StrategyNode | None = None) -> str:
    worlds = generate_three_gods_worlds()
    root = strategy or solve_three_gods_reference()
    lines = [
        "# Three Gods Strategy",
        "",
        "Question form used throughout:",
        "> If I asked you whether `<predicate>`, would you say DA?",
        "",
    ]

    def walk(node: StrategyNode, prefix: str) -> None:
        if node.is_leaf:
            roles = node.resolved_roles(worlds)
            mapping_options = sorted({worlds[index].da_means_yes for index in node.possible_worlds})
            mapping_text = "DA/JA unresolved" if len(mapping_options) > 1 else ("DA=yes" if mapping_options[0] else "JA=yes")
            lines.append(
                f"{prefix}Resolved roles: `A={roles[0]}, B={roles[1]}, C={roles[2]}` ({mapping_text})"
            )
            return
        lines.append(
            f"{prefix}Ask `{node.respondent}` about `{node.predicate_name}`"
        )
        for answer, child in sorted((node.branches or {}).items()):
            lines.append(f"{prefix}- if answer is `{answer}`:")
            walk(child, prefix + "  ")

    walk(root, "")
    return "\n".join(lines)
