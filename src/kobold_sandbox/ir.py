from __future__ import annotations

from dataclasses import dataclass, field

from .assertions import AtomicClaim, ClaimStatus, TabularAssertionBoard
from .constraints import ConstraintSpec


@dataclass(frozen=True)
class Axis:
    name: str
    labels: tuple[str, ...]
    value_kind: str = "symbol"


@dataclass(frozen=True)
class Universe:
    problem_id: str
    axes: tuple[Axis, ...]
    object_types: tuple[str, ...] = ()

    def axis(self, name: str) -> Axis:
        for axis in self.axes:
            if axis.name == name:
                return axis
        raise KeyError(name)


@dataclass(frozen=True)
class CellRef:
    grid_id: str
    row: str
    column: str

    @property
    def key(self) -> str:
        return f"{self.grid_id}:{self.row}:{self.column}"


@dataclass
class CellValue:
    ref: CellRef
    raw_value: str
    status: ClaimStatus
    claim_id: str
    domain: tuple[str, ...] = ()


@dataclass
class StateGrid:
    grid_id: str
    row_axis: str
    column_axis: str
    boards: list[TabularAssertionBoard] = field(default_factory=list)
    cells: dict[str, CellValue] = field(default_factory=dict)

    @classmethod
    def from_board(cls, board: TabularAssertionBoard, *, row_axis: str, column_axis: str) -> "StateGrid":
        grid = cls(
            grid_id=board.name,
            row_axis=row_axis,
            column_axis=column_axis,
            boards=[board],
        )
        for row in board.rows:
            for column in board.columns:
                cell = board.cell(row, column)
                value_range = cell.claim.value_range.values if cell.claim.value_range else ()
                ref = CellRef(grid_id=board.name, row=row, column=column)
                grid.cells[ref.key] = CellValue(
                    ref=ref,
                    raw_value=cell.raw_value,
                    status=cell.claim.status,
                    claim_id=cell.claim.claim_id,
                    domain=value_range,
                )
        return grid


@dataclass(frozen=True)
class ConstraintRecord:
    constraint_id: str
    kind: str
    spec: ConstraintSpec
    claim_id: str | None = None
    source: str = ""


@dataclass
class CanonicalIR:
    universe: Universe
    grids: dict[str, StateGrid]
    constraints: list[ConstraintRecord]
    claims: list[AtomicClaim]

    def claim(self, claim_id: str) -> AtomicClaim:
        for claim in self.claims:
            if claim.claim_id == claim_id:
                return claim
        raise KeyError(claim_id)
