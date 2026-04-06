from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Rect:

    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def contains_rect(self, other: Rect) -> bool:
        return (
            self.x <= other.x
            and self.y <= other.y
            and self.right >= other.right
            and self.bottom >= other.bottom
        )

    def within_bounds(self, cols: int, rows: int) -> bool:
        return self.x >= 0 and self.y >= 0 and self.right <= cols and self.bottom <= rows

    def to_list(self) -> list[int]:
        return [self.x, self.y, self.w, self.h]


@dataclass(slots=True)
class LayoutNode:

    id: str
    kind: str
    rect: Rect
    parent: str | None = None
    children: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScreenSpec:

    cols: int
    rows: int
    root: str


@dataclass(slots=True)
class LayoutDocument:

    screen: ScreenSpec
    nodes: dict[str, LayoutNode]


@dataclass(slots=True)
class NlpMeta:

    synonyms: list[str] = field(default_factory=list)
    description: str = ''
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NodeMeta:

    title: str = ''
    role: str = 'node.unknown'
    kind: str = 'panel'
    renderer: str = 'utf_panel'
    data: dict[str, Any] = field(default_factory=dict)
    bind: dict[str, Any] = field(default_factory=dict)
    actions: dict[str, Any] = field(default_factory=dict)
    view: dict[str, Any] = field(default_factory=dict)
    binding: dict[str, Any] = field(default_factory=dict)
    events: dict[str, Any] = field(default_factory=dict)
    nlp: NlpMeta = field(default_factory=NlpMeta)
    props: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SnapLink:

    side: str
    target_id: str
    target_side: str
    strength: str = 'exact'


@dataclass(slots=True)
class UiNode:

    id: str
    kind: str
    rect: Rect
    parent: str | None
    children: list[str]
    title: str
    role: str
    renderer: str
    data: dict[str, Any]
    bind: dict[str, Any]
    actions: dict[str, Any]
    view: dict[str, Any]
    binding: dict[str, Any]
    events: dict[str, Any]
    nlp: NlpMeta
    props: dict[str, Any]
    resolved: dict[str, Any] = field(default_factory=dict)
    snap: list[SnapLink] = field(default_factory=list)


@dataclass(slots=True)
class UiRuntime:

    cols: int
    rows: int
    root_id: str
    nodes: dict[str, UiNode]
