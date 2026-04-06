from __future__ import annotations

from dataclasses import dataclass

from typing import Any

from .schema import Rect


@dataclass(slots=True)
class PatchOp:
    op: str


@dataclass(slots=True)
class AddNodeOp(PatchOp):
    id: str
    parent: str | None
    kind: str
    rect: Rect

    def __init__(self, id: str, parent: str | None, kind: str, rect: Rect) -> None:
        super().__init__(op='add_node')
        self.id = id
        self.parent = parent
        self.kind = kind
        self.rect = rect


@dataclass(slots=True)
class RemoveNodeOp(PatchOp):
    id: str
    delete_subtree: bool = False

    def __init__(self, id: str, delete_subtree: bool = False) -> None:
        super().__init__(op='remove_node')
        self.id = id
        self.delete_subtree = delete_subtree


@dataclass(slots=True)
class MoveNodeOp(PatchOp):
    id: str
    dx: int
    dy: int

    def __init__(self, id: str, dx: int, dy: int) -> None:
        super().__init__(op='move_node')
        self.id = id
        self.dx = dx
        self.dy = dy


@dataclass(slots=True)
class ResizeNodeOp(PatchOp):
    id: str
    dw: int
    dh: int

    def __init__(self, id: str, dw: int, dh: int) -> None:
        super().__init__(op='resize_node')
        self.id = id
        self.dw = dw
        self.dh = dh


@dataclass(slots=True)
class SetNodeRectOp(PatchOp):
    id: str
    rect: Rect

    def __init__(self, id: str, rect: Rect) -> None:
        super().__init__(op='set_node_rect')
        self.id = id
        self.rect = rect


@dataclass(slots=True)
class RenameNodeOp(PatchOp):
    old_id: str
    new_id: str

    def __init__(self, old_id: str, new_id: str) -> None:
        super().__init__(op='rename_node')
        self.old_id = old_id
        self.new_id = new_id


@dataclass(slots=True)
class UpdateNodeMetaOp(PatchOp):
    id: str
    patch: dict[str, Any]

    def __init__(self, id: str, patch: dict[str, Any]) -> None:
        super().__init__(op='update_node_meta')
        self.id = id
        self.patch = patch
