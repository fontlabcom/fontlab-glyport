# this_file: src/fontlab_glyport/model/metrics_keys.py
"""Translate the shared, documented subset of Glyphs and FontLab metric links."""

import re

from ..ui.cocoa import unsupported

_LINK = re.compile(r"(={0,2})(\|?)([A-Za-z_][A-Za-z0-9_.]*)([+-]\d+(?:\.\d+)?)?\Z")


def to_native(value, side):
    if value is None or value == "":
        return ""
    match = _LINK.fullmatch(value)
    if match is None or side == "width" and match[2]:
        raise unsupported(f"GSLayer.{side}MetricsKey.syntax")
    return "".join(part or "" for part in match.groups()[1:])


def from_native(value, side):
    if not value:
        return None
    # Canonical Glyphs spelling when no original source spelling is retained.
    to_native(value, side)
    return "=" + value


def update(layer):
    """Evaluate supported Glyphs links against the same master, then write once.

    Resolve both sides before moving the outline: native sidebearing evaluation
    does not reliably apply the right-hand link on the tested FontLab build.
    """
    values = {}
    for side, attribute in (("left", "LSB"), ("right", "RSB"), ("width", "width")):
        key = getattr(layer, side + "MetricsKey") or getattr(
            layer.parent, side + "MetricsKey"
        )
        if not key:
            continue
        to_native(key, side)  # refuse unknown syntax before any geometry writes
        match = _LINK.fullmatch(key)
        glyph = layer._font.glyphs[match[3]]
        reference = None if glyph is None else glyph.layers[layer.associatedMasterId]
        if reference is None:
            raise unsupported(f"GSLayer.{side}MetricsKey.reference")
        if match[2]:
            attribute = "RSB" if side == "left" else "LSB"
        values[side] = float(getattr(reference, attribute)) + float(match[4] or 0)
    if values:
        with layer._font.undo_group("Update metrics"):
            for side, attribute in (
                ("left", "LSB"),
                ("right", "RSB"),
                ("width", "width"),
            ):
                if side in values:
                    setattr(layer, attribute, values[side])

    return bool(values)
