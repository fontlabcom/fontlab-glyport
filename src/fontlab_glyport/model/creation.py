# this_file: src/fontlab_glyport/model/creation.py
"""Measured MCP-only preservation of default-recipe auto layers on creation."""

from collections.abc import Mapping, Sequence
from copy import deepcopy

from ..errors import PartialFailure, UnsupportedCapability

CAPABILITY = "GSFont.glyphs.append.preserveComposites"
AUTO_LAYER_FLAG = 16


def normalize_json(value):
    """fontpr exposes JSON arrays as tuples; set_glyph needs plain lists."""
    if isinstance(value, Mapping):
        return {key: normalize_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [normalize_json(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise UnsupportedCapability(
        f"get_glyph returned non-JSON {type(value).__name__}", capability=CAPABILITY
    )


def glyph_json(reply):
    """Normalize bare or enveloped MCP glyphs to independent, list-only JSON."""
    data = normalize_json(reply)
    if isinstance(data, dict):
        data = data.get("glyph", data)
    if not isinstance(data, dict) or not isinstance(data.get("layers"), list):
        raise UnsupportedCapability(
            "get_glyph returned no layer JSON", capability=CAPABILITY
        )
    return data


def required(data, names):
    """Locks/attaching-anchor-only changes are the tolerated host fl#8512 defect.

    Component base, order, complete transform and width must survive. When a
    restore is needed the entire original JSON (including anchors) is submitted.
    """
    return {
        layer["name"]: (
            [
                (index, element["component"], element.get("transform"))
                for index, element in enumerate(layer.get("elements", []))
                if "component" in element
            ],
            layer.get("advanceWidth"),
        )
        for layer in data["layers"]
        if layer.get("name") in names
    }


def signatures(glyph, names):
    """Read only bound component values; no serialization or model writes."""
    result = {}
    for layer in glyph.layers:
        if layer.name not in names:
            continue
        components = []
        for index, shape in enumerate(layer.shapes):
            if shape.isComponent:
                t = shape.transform
                components.append(
                    (
                        index,
                        str(shape.shapeData.componentGlyph),
                        t.m11(),
                        t.m12(),
                        t.m21(),
                        t.m22(),
                        t.dx(),
                        t.dy(),
                    )
                )
        anchors = tuple((a.name, a.point.x(), a.point.y()) for a in layer.anchors)
        result[layer.name] = (components, layer.advanceWidth, anchors)
    return result


def component_data(values):
    # Anchor-only changes remain the tolerated host fl#8512 case.
    return {name: value[:2] for name, value in values.items()}


def guard_pending(package, glyph, *, capability=CAPABILITY):
    """Refuse edits incompatible with a pending glyph/layer batch in any session."""
    from .fontlab_backend import _LIVE_BACKENDS

    identities = {("glyph", glyph.id)} | {("layer", layer.id) for layer in glyph.layers}
    for peer in tuple(_LIVE_BACKENDS):
        if (package.id, "font", package.id) not in peer._keys:
            continue
        if identities.intersection(peer._changed):
            raise UnsupportedCapability(
                f"Cannot preserve {glyph.name} while glyph/layer notifications are pending",
                capability=capability,
            )


def capture(backend, package):
    states, read = [], None
    for record in backend._fontgate_font(package).glyphs:
        glyph = package.findName(record.name)
        if glyph is None:
            continue
        candidates = {
            layer.name for layer in glyph.layers if layer.autoLayer and not layer.recipe
        }
        if not candidates:
            continue
        guard_pending(package, glyph)
        if read is None:
            read = backend._resolve_tool("get_glyph", CAPABILITY)
        data = glyph_json(read(font_id=package.fgId, glyph_name=glyph.name))
        layers = {
            layer["name"]
            for layer in data["layers"]
            if layer.get("name") in candidates
            and int(layer.get("flags", 0)) & AUTO_LAYER_FLAG
            and not layer.get("autoRecipe")
        }
        if layers:
            states.append((glyph.name, data, layers, signatures(glyph, layers)))
    return states, read


def refresh(package, name):
    """MCP replaces layers: refresh retained handles without notifying them."""
    from .fontlab_backend import _LIVE_BACKENDS

    for peer in tuple(_LIVE_BACKENDS):
        peer._revision += 1
        for glyph, tokens in tuple(peer._glyph_layer_tokens.items()):
            document = peer._object_keys[glyph][0]
            if (
                peer._object_keys[document][2] != package.id
                or peer._glyph_names.get(glyph) != name
            ):
                continue
            if tokens:
                peer._validate_history(next(iter(tokens)), force=True)


def restore(package, states, read, builder):
    errors = []
    for name, data, layers, cheap_before in states:
        try:
            glyph = package.findName(name)
            if component_data(signatures(glyph, layers)) == component_data(
                cheap_before
            ):
                continue
            guard_pending(package, glyph)
            before = required(data, layers)
            current = glyph_json(read(font_id=package.fgId, glyph_name=name))
            if required(current, layers) == before:
                continue
            try:
                builder(
                    font_id=package.fgId,
                    glyph_name=name,
                    create=False,
                    glyph_data=deepcopy(data),
                )
            finally:
                refresh(package, name)
            restored = glyph_json(read(font_id=package.fgId, glyph_name=name))
            if required(restored, layers) != before:
                raise RuntimeError(
                    "MCP restore verification failed (auto layer rebuilt again)"
                )
        except Exception as error:  # noqa: BLE001 - attempt every affected glyph
            errors.append((name, error))
    if errors:
        detail = "; ".join(f"{name}: {error}" for name, error in errors)
        raise UnsupportedCapability(
            f"Cannot restore unrelated composites {detail}", capability=CAPABILITY
        ) from errors[0][1]


def create_preserving(backend, package, name, builder, **kwargs):
    backend._require_history_scope(("font", package), creates=True)
    states, read = capture(backend, package)
    try:
        builder(**kwargs)
        restore(package, states, read, builder)
    except Exception as error:
        recovery = []
        added = package.findName(name)
        if added is not None:
            try:
                if not package.deleteGlyph(added):
                    raise RuntimeError("Native deletion refused")
            except Exception as failure:  # noqa: BLE001 - attempt every rollback step
                recovery.append(failure)
        try:
            restore(package, states, read, builder)
        except Exception as failure:  # noqa: BLE001 - attempt every rollback step
            recovery.append(failure)
        if recovery:
            failure = PartialFailure(
                f"Creation rollback failed for {', '.join(s[0] for s in states)}: {recovery}",
                capability=CAPABILITY,
            )
            failure.errors = (error, *recovery)
            raise failure from error
        raise
