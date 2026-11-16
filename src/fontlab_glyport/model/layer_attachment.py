# this_file: src/fontlab_glyport/model/layer_attachment.py
"""Bind a copied auxiliary only after its backend transaction succeeds."""

from dataclasses import fields, is_dataclass

from ..errors import UnsupportedCapability


def copy_state(layer):
    """Value fingerprint of the entire represented detached graph, without IDs.

    Only the root's name and master association may change before attachment.
    Referenced component layers and backgrounds participate, including cycles.
    This stores values, never source tokens, proxies or native handles.
    """
    from .copies import DetachedLayer
    from .proxies import GSHint, _Proxy

    seen = {}

    def freeze(value):
        if isinstance(value, (str, int, float, bool, bytes, type(None))):
            return value
        if is_dataclass(value):
            return (
                type(value).__name__,
                tuple(
                    (f.name, freeze(getattr(value, f.name)))
                    for f in fields(value)
                    if f.name != "id"
                ),
            )
        key = id(value)
        if key in seen:
            return ("reference", seen[key][0])
        seen[key] = (len(seen), value)
        if isinstance(value, DetachedLayer):
            return (
                "layer",
                freeze(
                    {
                        "name": None if value is layer else value.name,
                        "associationUnchanged": value is layer
                        or value.associatedMasterId == value._draft.masterId,
                        "width": value.width,
                        "italic": value.italicAngle,
                        "slant": value.slantHeight,
                        "attributes": value._attributes,
                        "lib": value._user_data,
                        "metrics": value._metrics_keys,
                        "shapes": value._shapes,
                        "anchors": value._anchors,
                        "guides": value._guides,
                        "hints": value._hints,
                        "background": value._background,
                        "references": value._component_layers,
                    }
                ),
            )
        if isinstance(value, dict):
            return tuple((freeze(k), freeze(v)) for k, v in value.items())
        if isinstance(value, (list, tuple)):
            return tuple(freeze(v) for v in value)
        if isinstance(value, _Proxy):
            return freeze(value._data())
        if isinstance(value, GSHint):
            return freeze(value._values)
        raise TypeError(f"Unsupported copied payload value: {type(value).__name__}")

    return freeze(layer)


def append_layer(glyph, layer):
    from .attachment import target_master
    from .background import GSBackgroundLayer
    from .copies import DetachedLayer
    from .proxies import GSLayer, _Proxy

    glyph._check()
    if not isinstance(layer, DetachedLayer) or isinstance(layer, GSBackgroundLayer):
        raise TypeError("layers.append requires a detached copied normal GSLayer")
    if layer.parent is not None:
        raise ValueError("The copied layer already has an owner")
    snapshot = layer.__dict__.get("_copy_snapshot")
    if snapshot is None:
        raise UnsupportedCapability(
            "layers.append requires a captured normal layer copy"
        )
    if copy_state(layer) != layer._copy_state:
        raise UnsupportedCapability(
            "Cannot attach a modified rich copy; only rename and master association are supported"
        )
    masters = {m.id for m in glyph._font.masters}
    same_owner = layer.__dict__.get("_master_owner") == glyph._font._copy_owner
    changed_association = layer.associatedMasterId != layer._copy_association
    if (same_owner or changed_association) and layer.associatedMasterId not in masters:
        raise ValueError("Copied layer has an invalid master association")
    master = (
        layer.associatedMasterId
        if changed_association
        else target_master(glyph._font, layer)
    )
    backend = glyph._font._model._backend
    token = backend.append_layer(glyph.id, master, layer.name, snapshot)
    # Child/background handles retained by the caller remain detached values.
    # They never acquire native identities or mutate the newly attached graph.
    font = glyph._font
    retain_detached_graph(layer)
    background = layer.__dict__.get("_background")
    if background is not None:
        background._foreground = None
        background._glyph = None
    layer.__class__ = GSLayer
    layer.__dict__.clear()
    _Proxy.__init__(
        layer,
        font,
        token,
        lambda: font._layer_info(
            (glyph.id, token), lambda: backend.layer(glyph.id, token)
        ),
    )
    layer._glyph = glyph
    font._cache[GSLayer, token] = layer


def retain_detached_graph(layer):
    """Redirect recursive component references before rebinding the root proxy.

    A retained background can refer to its own foreground through a component.
    Keep that edge pointed at a detached value twin, never the newly live root.
    """
    twin = object.__new__(type(layer))
    twin.__dict__.update(layer.__dict__)
    pending, seen = [twin], set()
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        for name, reference in item._component_layers.items():
            if reference is layer:
                reference = item._component_layers[name] = twin
            if reference is not None:
                pending.append(reference)
        if item._background is not None:
            pending.append(item._background)


def validate_name(name, existing):
    if (
        not isinstance(name, str)
        or not name.strip()
        or name.casefold().startswith("mask.")
    ):
        raise ValueError("A copied layer needs a nonempty normal auxiliary name")
    names = {n.casefold() for n in existing}
    if name.casefold() in names or ("mask." + name).casefold() in names:
        raise UnsupportedCapability(
            "Copied foreground or mask name collides with an existing layer"
        )
