# this_file: src/fontlab_glyport/model/compatibility.py
"""Structural master comparison for the model's supported shape types."""

from .backend import PathInfo
from .proxies import CAP, CORNER, _unsupported


def signature(layer):
    if layer is None:
        return (), ()
    if "_draft" in layer.__dict__:
        _unsupported("GSGlyph.mastersCompatibleForLayerIds_.detached")
    data = layer._data()
    records = {item.id: item for item in (*data.paths, *data.components)}
    shapes = []
    for token in data.shape_ids or tuple(records):
        shape = records[token]
        if isinstance(shape, PathInfo):
            shapes.append(
                ("path", shape.closed, tuple(node.type for node in shape.nodes))
            )
        else:
            shapes.append(("component", shape.componentName))
    # Glyphs' default options compare anchor names, not their coordinates.
    for hint in layer.hints:
        if hint.type in (CAP, CORNER):
            _unsupported("GSGlyph.mastersCompatibleForLayerIds_.pathComponents")
    return tuple(shapes), tuple(sorted(anchor.name for anchor in data.anchors))


def compatible(glyph, layer_ids):
    if len(layer_ids) <= 1:
        return True
    initial = signature(glyph.layers[layer_ids[0]])
    for layer_id in layer_ids[1:]:
        layer = glyph.layers[layer_id]
        # The reference ignores missing/inactive subsequent layers.
        if layer is not None and signature(layer) != initial:
            return False
    return True


def compare_string(layer):
    """GlyphsCore path/ASCII-anchor signature; refuse unresolved encodings."""
    from .proxies import GSPath

    if any(hint.type in (CAP, CORNER) for hint in layer.hints):
        _unsupported("GSLayer.compareString.pathComponents")
    if layer.components:
        _unsupported("GSLayer.compareString.anchorOrComponentEncoding")
    anchor_names = [anchor.name for anchor in layer.anchors]
    if not all(name.isascii() for name in anchor_names):
        _unsupported(
            "GSLayer.compareString.nonASCIIAnchorNames (unverified NSString collation)"
        )
    codes = {"line": "l", "curve": "c", "offcurve": "o", "qcurve": "q"}
    parts = []
    for shape in layer.shapes:
        if isinstance(shape, GSPath):
            parts.append(
                "".join(codes[node.type] for node in shape.nodes)
                + ("_" if shape.closed else "|_")
            )
    # GSLayer.compareStringOptions: appends sorted anchor keys joined with **.
    parts.append("**".join(sorted(anchor_names)))
    return "".join(parts)
