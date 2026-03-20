from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from .constraints import ConstraintSpec
from .storage import slugify


class ClaimStatus(str, Enum):
    GIVEN = "given"
    DERIVED = "derived"
    HYPOTHESIS = "hypothesis"
    REJECTED = "rejected"
    CONFIRMED = "confirmed"


class CellPhase(str, Enum):
    RAW = "raw"
    FORMAL = "formal"
    ATOMIC = "atomic"


@dataclass(frozen=True)
class ValueRange:
    values: tuple[str, ...] = ()
    lower: int | float | None = None
    upper: int | float | None = None

    @classmethod
    def from_values(cls, values: Iterable[str]) -> "ValueRange":
        return cls(values=tuple(values))

    def is_uncertain(self) -> bool:
        if self.values:
            return len(self.values) != 1
        return self.lower is None or self.upper is None or self.lower != self.upper


@dataclass
class AtomicClaim:
    claim_id: str
    title: str
    formal_text: str = ""
    python_code: str = ""
    formal_constraint: ConstraintSpec | None = None
    variables: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    status: ClaimStatus = ClaimStatus.GIVEN
    phase: CellPhase = CellPhase.RAW
    value_range: ValueRange | None = None
    consequences: list[str] = field(default_factory=list)

    def formalize(self, formal_text: str, variables: Iterable[str]) -> None:
        self.formal_text = formal_text
        self.variables = tuple(variables)
        self.phase = CellPhase.FORMAL

    def formalize_constraint(self, constraint: ConstraintSpec) -> None:
        self.formal_constraint = constraint
        self.formal_text = constraint.to_python_expr()
        self.variables = constraint.variables()
        self.phase = CellPhase.FORMAL

    def attach_python(self, python_code: str) -> None:
        self.python_code = python_code
        self.phase = CellPhase.ATOMIC

    def attach_atomic_constraint(self, constraint: ConstraintSpec) -> None:
        self.formalize_constraint(constraint)
        self.attach_python(constraint.to_assertion())

    def branch_slug(self) -> str:
        return slugify(self.claim_id.replace("__", "-"))


@dataclass(frozen=True)
class CellKey:
    row: str
    column: str

    @property
    def claim_id(self) -> str:
        return f"{slugify(self.row)}__{slugify(self.column)}"


@dataclass
class GridCell:
    key: CellKey
    claim: AtomicClaim
    raw_value: str = "?"

    def set_known(self, raw_value: str, status: ClaimStatus = ClaimStatus.GIVEN) -> None:
        self.raw_value = raw_value
        self.claim.status = status


@dataclass
class TabularAssertionBoard:
    name: str
    rows: tuple[str, ...]
    columns: tuple[str, ...]
    cells: dict[CellKey, GridCell] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for row in self.rows:
            for column in self.columns:
                key = CellKey(row=row, column=column)
                self.cells.setdefault(
                    key,
                    GridCell(
                        key=key,
                        claim=AtomicClaim(
                            claim_id=key.claim_id,
                            title=f"{row} x {column}",
                        ),
                    ),
                )

    def cell(self, row: str, column: str) -> GridCell:
        return self.cells[CellKey(row=row, column=column)]

    def seed_claim(
        self,
        row: str,
        column: str,
        raw_value: str,
        *,
        formal_text: str = "",
        python_code: str = "",
        formal_constraint: ConstraintSpec | None = None,
        variables: Iterable[str] = (),
        status: ClaimStatus = ClaimStatus.GIVEN,
        value_range: ValueRange | None = None,
    ) -> AtomicClaim:
        cell = self.cell(row, column)
        cell.set_known(raw_value, status=status)
        cell.claim.value_range = value_range
        if formal_constraint is not None:
            cell.claim.formalize_constraint(formal_constraint)
        elif formal_text:
            cell.claim.formalize(formal_text, variables)
        if python_code:
            cell.claim.attach_python(python_code)
        return cell.claim

    def formalize_cell(self, row: str, column: str, formal_text: str, variables: Iterable[str]) -> AtomicClaim:
        cell = self.cell(row, column)
        cell.claim.formalize(formal_text, variables)
        return cell.claim

    def formalize_cell_constraint(self, row: str, column: str, constraint: ConstraintSpec) -> AtomicClaim:
        cell = self.cell(row, column)
        cell.claim.formalize_constraint(constraint)
        return cell.claim

    def attach_atomic_code(self, row: str, column: str, python_code: str) -> AtomicClaim:
        cell = self.cell(row, column)
        cell.claim.attach_python(python_code)
        return cell.claim

    def attach_atomic_constraint(self, row: str, column: str, constraint: ConstraintSpec) -> AtomicClaim:
        cell = self.cell(row, column)
        cell.claim.attach_atomic_constraint(constraint)
        return cell.claim

    def unresolved_claims(self) -> list[AtomicClaim]:
        unresolved: list[AtomicClaim] = []
        for cell in self.cells.values():
            if cell.raw_value == "?":
                unresolved.append(cell.claim)
                continue
            if cell.claim.value_range and cell.claim.value_range.is_uncertain():
                unresolved.append(cell.claim)
        return unresolved

    def to_atomic_claims(self) -> list[AtomicClaim]:
        return [cell.claim for cell in self.cells.values()]

    def to_markdown(self) -> str:
        header = "| row | " + " | ".join(self.columns) + " |"
        separator = "|" + "---|" * (len(self.columns) + 1)
        lines = [header, separator]
        for row in self.rows:
            values = [self.cell(row, column).raw_value for column in self.columns]
            lines.append("| " + row + " | " + " | ".join(values) + " |")
        return "\n".join(lines)


@dataclass
class HypothesisNode:
    node_id: str
    title: str
    assumptions: list[str] = field(default_factory=list)
    consequences: list[str] = field(default_factory=list)
    branch_name: str = ""
    status: ClaimStatus = ClaimStatus.HYPOTHESIS
    related_hypothesis_ids: list[str] = field(default_factory=list)
    related_cells: list[str] = field(default_factory=list)
    atom_ids: list[str] = field(default_factory=list)
    parent: "HypothesisNode | None" = field(default=None, repr=False)
    children: list["HypothesisNode"] = field(default_factory=list)

    def add_child(self, child: "HypothesisNode") -> None:
        child.parent = self
        self.children.append(child)

    def link_hypothesis(self, other_id: str) -> None:
        if other_id not in self.related_hypothesis_ids:
            self.related_hypothesis_ids.append(other_id)

    def link_cell(self, cell_ref: str) -> None:
        if cell_ref not in self.related_cells:
            self.related_cells.append(cell_ref)

    def add_atom(self, atom_id: str) -> None:
        if atom_id not in self.atom_ids:
            self.atom_ids.append(atom_id)

    @property
    def is_active(self) -> bool:
        return self.status in {ClaimStatus.HYPOTHESIS, ClaimStatus.CONFIRMED, ClaimStatus.DERIVED}

    def lineage(self) -> list[str]:
        cursor: HypothesisNode | None = self
        result: list[str] = []
        while cursor:
            result.append(cursor.node_id)
            cursor = cursor.parent
        return list(reversed(result))


@dataclass
class HypothesisTree:
    root: HypothesisNode

    @classmethod
    def from_problem(cls, problem_id: str, title: str = "Root hypothesis") -> "HypothesisTree":
        root_id = slugify(problem_id) or "root"
        return cls(root=HypothesisNode(node_id=root_id, title=title, branch_name="main", status=ClaimStatus.CONFIRMED))

    def create_child(
        self,
        parent: HypothesisNode,
        claim: AtomicClaim,
        *,
        title: str | None = None,
        consequences: Iterable[str] = (),
        related_cells: Iterable[str] = (),
    ) -> HypothesisNode:
        node_id = claim.branch_slug()
        branch_name = f"hyp/{node_id}"
        child = HypothesisNode(
            node_id=node_id,
            title=title or claim.title,
            assumptions=[claim.claim_id],
            consequences=list(consequences) or list(claim.consequences),
            branch_name=branch_name,
            status=claim.status,
            related_cells=list(related_cells),
        )
        parent.add_child(child)
        return child

    def get_node(self, node_id: str) -> HypothesisNode:
        for node in self.iter_nodes():
            if node.node_id == node_id:
                return node
        raise KeyError(node_id)

    def connected_component(self, node_id: str, *, active_only: bool = True) -> list[HypothesisNode]:
        nodes = {node.node_id: node for node in self.iter_nodes()}
        start = nodes[node_id]
        queue = [start.node_id]
        visited: set[str] = set()
        component: list[HypothesisNode] = []
        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)
            node = nodes[current_id]
            if not active_only or node.is_active:
                component.append(node)
            neighbors: set[str] = set(node.related_hypothesis_ids)
            if node.parent and node.parent.node_id != self.root.node_id:
                neighbors.add(node.parent.node_id)
            neighbors.update(child.node_id for child in node.children if child.node_id != self.root.node_id)
            for other in nodes.values():
                if other.node_id == node.node_id:
                    continue
                if other.node_id == self.root.node_id:
                    continue
                if set(node.related_cells) & set(other.related_cells):
                    neighbors.add(other.node_id)
            for neighbor_id in neighbors:
                if neighbor_id in nodes and neighbor_id not in visited:
                    if not active_only or nodes[neighbor_id].is_active:
                        queue.append(neighbor_id)
        return component

    def iter_nodes(self) -> Iterable[HypothesisNode]:
        stack = [self.root]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

    def pending_nodes(self) -> list[HypothesisNode]:
        return [node for node in self.iter_nodes() if node.status == ClaimStatus.HYPOTHESIS]
