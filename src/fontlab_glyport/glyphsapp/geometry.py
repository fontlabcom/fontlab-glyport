# this_file: src/fontlab_glyport/glyphsapp/geometry.py
"""Glyphs module point helpers; no host geometry or optional dependencies."""

from itertools import pairwise
from math import hypot

from ..ui.cocoa import NSMakePoint

__all__ = [
    "addPoints",
    "distance",
    "divideCurve",
    "pointOnLine",
    "pointOnQuadratic",
    "scalePoint",
    "subtractPoints",
]


def _xy(point):
    x, y = getattr(point, "position", point)
    return x, y


def distance(P1, P2):
    """Euclidean distance, accepting points, coordinate pairs or nodes."""
    x, y = _xy(P1)
    other_x, other_y = _xy(P2)
    return hypot(x - other_x, y - other_y)


def addPoints(P1, P2):
    x, y = _xy(P1)
    other_x, other_y = _xy(P2)
    return NSMakePoint(x + other_x, y + other_y)


def subtractPoints(P1, P2):
    x, y = _xy(P1)
    other_x, other_y = _xy(P2)
    return NSMakePoint(x - other_x, y - other_y)


def scalePoint(P, scalar):
    x, y = _xy(P)
    return NSMakePoint(x * scalar, y * scalar)


def pointOnLine(P0, P1, t):
    x, y = _xy(P0)
    end_x, end_y = _xy(P1)
    return NSMakePoint((1 - t) * x + t * end_x, (1 - t) * y + t * end_y)


def pointOnQuadratic(P0, P1, P2, t):
    return pointOnLine(pointOnLine(P0, P1, t), pointOnLine(P1, P2, t), t)


def divideCurve(P0, P1, P2, P3, t):
    """Split a cubic by De Casteljau; share its middle point in a 7-tuple.

    Like the Glyphs 4 wrapper, retain the original endpoints and allow t
    outside [0, 1] (extrapolation rather than clamping).
    """
    controls = [pointOnLine(a, b, t) for a, b in pairwise((P0, P1, P2, P3))]
    handles = [pointOnLine(a, b, t) for a, b in pairwise(controls)]
    middle = pointOnLine(*handles, t)
    return P0, controls[0], handles[0], middle, handles[1], controls[2], P3
