# this_file: src/fontlab_glyport/model/node_insert.py
"""Shared insertion boundary checks, matching the pinned Glyphs 3 wrapper."""

from dataclasses import replace
from math import isfinite

from ..errors import UnsupportedCapability
from .backend import NodeInfo


def insertion_index(index: int, length: int) -> int:
    """Negative indices add length once; insertion never clamps."""
    if not isinstance(index, int):
        raise TypeError("Node insertion indices must be integers")
    if index < 0:
        index += length
    if not 0 <= index <= length:
        raise IndexError("Node insertion index out of range")
    return index


def insertion_node(node: NodeInfo) -> NodeInfo:
    """Stage finite coordinates and representable connection before any edit."""
    x, y = float(node.x), float(node.y)
    if not isfinite(x) or not isfinite(y):
        raise ValueError("Node coordinates must be finite")
    if node.connection not in (None, 0, 100):
        raise UnsupportedCapability(
            f"Unsupported node connection {node.connection}",
            capability="GSNode.connection",
        )
    smooth = node.smooth if node.connection is None else node.connection == 100
    return replace(node, x=x, y=y, smooth=smooth)
