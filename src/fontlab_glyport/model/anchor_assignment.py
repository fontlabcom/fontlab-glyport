# this_file: src/fontlab_glyport/model/anchor_assignment.py
"""Glyphs keyed anchor assignment over atomic layer collection replacement."""


def assign_anchor(layer, key, value):
    from .proxies import GSAnchor

    if not isinstance(key, (str, int)) or isinstance(key, bool):
        raise TypeError("Anchor assignment requires a name or index")
    if not isinstance(value, GSAnchor):
        raise TypeError("Expected GSAnchor")
    if "_draft" not in value.__dict__:
        value = value.copy()
    original_name = value.name
    try:
        values = list(layer.anchors)
        if isinstance(key, str):
            value.name = key
            position = next(
                (i for i, anchor in enumerate(values) if anchor.name == key), None
            )
            if position is None:
                values.append(value)
            else:
                values[position] = value
        else:
            values[key] = value
        layer.anchors = values
    except BaseException:
        if value.name != original_name:
            value.name = original_name
        raise
