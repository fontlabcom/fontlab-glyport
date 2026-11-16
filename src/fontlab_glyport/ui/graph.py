# this_file: src/fontlab_glyport/ui/graph.py
"""Versioned, host-independent UI graph that vanilla translation populates."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import fontlabapp.qt.ui_graph as _shared

UI_GRAPH_VERSION = _shared.UI_GRAPH_VERSION
Connection = _shared.Connection
AUTO = "auto"

Number = int | float
Dimension = Number | str


def _check_number(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"Frame.{name} must be a number, got {value!r}")


def _check_dimension(name: str, value: Any) -> None:
    if value != AUTO:
        _check_number(name, value)


@dataclass(frozen=True)
class Frame:
    """Vanilla posSize values verbatim; width/height may be "auto"."""

    left: Number
    top: Number
    width: Dimension
    height: Dimension

    def __post_init__(self) -> None:
        _check_number("left", self.left)
        _check_number("top", self.top)
        _check_dimension("width", self.width)
        _check_dimension("height", self.height)

    @classmethod
    def from_pos_size(cls, pos_size: Sequence[Dimension]) -> "Frame":
        """Accept a vanilla posSize; a window's (w, h) means size only."""
        if pos_size == AUTO:
            return cls(0, 0, AUTO, AUTO)
        if len(pos_size) == 2:
            return cls(0, 0, pos_size[0], pos_size[1])
        if len(pos_size) == 4:
            return cls(*pos_size)
        raise ValueError(f"posSize needs 2 or 4 items, got {len(pos_size)}")

    def to_json(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class Node(_shared.Node):
    """One source UI object with the original Vanilla frame value type."""

    frame: Frame | None = None

    def _frame_json(self) -> dict[str, Any] | None:
        return self.frame.to_json() if self.frame else None

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "Node":
        frame = data["frame"]
        return cls(**{**data, "frame": Frame(**frame) if frame is not None else None})


class UIGraph(_shared.UIGraph):
    """Shared ordered graph, binding the original Vanilla frame adapter."""

    _node_type = Node

    def add_node(
        self,
        source_class: str,
        *,
        parent_id: str | None = None,
        frame: Frame | None = None,
        properties: Mapping[str, Any] | None = None,
        resources: Mapping[str, Any] | None = None,
        source_id: str | None = None,
        attribute_name: str | None = None,
    ) -> Node:
        return super().add_node(
            source_class,
            parent_id=parent_id,
            frame=frame,
            properties=properties,
            resources=resources,
            source_id=source_id,
            attribute_name=attribute_name,
        )

    def children(self, node_id: str) -> tuple[Node, ...]:
        return super().children(node_id)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "UIGraph":
        return super().from_json(data)


def _extent(value: Dimension, origin: float, parent: float, hint: float) -> Number:
    if value == AUTO:
        return hint
    return value if value > 0 else parent - origin + value


def resolve_frame(
    frame: Frame,
    parent_width: Number,
    parent_height: Number,
    *,
    size_hint: tuple[Number, Number] = (0, 0),
) -> tuple[Number, Number, Number, Number]:
    """Return (x, y, w, h) in parent coordinates using vanilla posSize rules."""
    x = parent_width + frame.left if frame.left < 0 else frame.left
    y = parent_height + frame.top if frame.top < 0 else frame.top
    w = _extent(frame.width, x, parent_width, size_hint[0])
    h = _extent(frame.height, y, parent_height, size_hint[1])
    return x, y, w, h
