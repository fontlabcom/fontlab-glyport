# this_file: src/fontlab_glyport/model/native_layer_copy.py
"""Owned native snapshots and rollback for auxiliary copy attachment."""

from dataclasses import dataclass

from ..errors import NativeOperationError, PartialFailure, UnsupportedCapability
from .layer_attachment import validate_name


@dataclass(frozen=True)
class NativeLayerCopy:
    """Opaque owned wrappers; never a source backend, proxy, Model or font."""

    foreground: object
    mask: object | None


def clone_layer(backend, source):
    clone = source.clone()
    for old, new in zip(source.shapes, clone.shapes, strict=True):
        new.active = old.active
        new.shapeData.name = old.shapeData.name
        backend._copy_clone_connections(old, new)
    return clone


def capture(backend, source):
    mask = source.getMaskLayer(False)
    return NativeLayerCopy(
        clone_layer(backend, source),
        clone_layer(backend, mask) if mask is not None and mask.isValid else None,
    )


def validate(backend, glyph_id, master_id, name, snapshot):
    if not isinstance(snapshot, NativeLayerCopy):
        raise UnsupportedCapability("Incompatible layer-copy backend")
    glyph = backend._object(glyph_id)
    document = backend._parents[glyph_id]
    masters = backend.font_info(document).masters
    if master_id not in {m.id for m in masters}:
        raise ValueError("Master belongs to a different document")
    validate_name(name, [m.name for m in masters] + [l.name for l in glyph.layers])
    package = backend._object(document)
    for layer in (snapshot.foreground, snapshot.mask):
        if layer is None:
            continue
        if layer.autoLayer:
            raise UnsupportedCapability("Cannot append an auto layer copy")
        for shape in layer.shapes:
            if not shape.isComponent:
                continue
            data = shape.shapeData
            target = package.findName(data.componentGlyph)
            if target is None or not target.isValid:
                raise ValueError("Missing destination component glyph")
            reference = data.componentLayer
            if not reference:
                raise UnsupportedCapability(
                    "Copied component requires an explicit reference layer"
                )
            target_layer = target.findLayer(reference)
            if target_layer is None or not target_layer.isValid:
                raise ValueError("Missing destination component reference layer")
    return glyph, document


def stage(backend, glyph, name, snapshot):
    any_shape = next(
        v for k, v in backend._native().ShapeType.items() if k.strip() == "AnyShape"
    )
    layers = []
    for source, label in ((snapshot.mask, "mask." + name), (snapshot.foreground, name)):
        if source is None:
            continue
        layer = clone_layer(backend, source)
        layer.name = label
        layer.glyph = glyph
        if source is snapshot.foreground and (
            layer.isService or layer.isMaskLayer or layer.isMasterLayer
        ):
            raise UnsupportedCapability(
                "Copied layer name denotes a service, mask or master layer"
            )
        shapes = list(layer.takeShapes(any_shape))
        for shape in shapes:
            layer.addShape(shape)
        layers.append(layer)
    return layers


def update_components(layer):
    for shape in layer.shapes:
        if shape.isComponent:
            builder = shape.shapeData.builder
            builder.changed()
            if builder.update() is False:
                raise NativeOperationError(
                    "Copied component update failed", capability="GSLayer.update"
                )
            shape.resetInkBox()


def append(backend, glyph_id, master_id, name, snapshot):
    glyph, document = validate(backend, glyph_id, master_id, name, snapshot)
    layers = stage(backend, glyph, name, snapshot)
    active = glyph.activeLayer
    colors = [layer.wireframeColor for layer in layers]
    prepared, changed = dict(backend._prepared), dict(backend._changed)
    pending = set(backend._pending_layer_updates)
    owned = set(backend._owned_shapes)
    tokens = []
    foreground = layers[-1]
    association_key = (backend._object(document).id, glyph.id, foreground.id)
    backend._prepare(("glyph", glyph))
    try:
        for layer, color in zip(layers, colors, strict=True):
            glyph.addLayer(layer, False)
            layer.wireframeColor = color
        glyph.activeLayer = active
        token = backend._layer_token(
            document, foreground, master_id, glyph_id, ("auxiliary", foreground.id)
        )
        tokens.append(token)
        if snapshot.mask is not None:
            tokens.append(
                backend._layer_token(
                    document,
                    layers[0],
                    master_id,
                    glyph_id,
                    ("auxiliary", foreground.id),
                    True,
                )
            )
        for layer in layers:
            update_components(layer)
        backend._auxiliary_associations[association_key] = backend._master_names[
            master_id
        ]
        backend._pending_layer_updates.update(tokens)
        backend._touch(*[("layer", layer) for layer in layers], ("glyph", glyph))
    except BaseException as error:
        try:
            present = {layer.id for layer in glyph.layers}
            for layer in reversed(layers):
                if layer.id in present:
                    glyph.removeLayer(layer)
            glyph.activeLayer = active
            glyph.changed()
            if glyph.update() is False:
                raise NativeOperationError(
                    "Rollback glyph update failed", capability="GSLayer.append.rollback"
                )
        except BaseException as recovery:
            failure = PartialFailure(
                f"Layer append rollback failed: {recovery}",
                capability="GSLayer.append.rollback",
            )
            failure.errors = (error, recovery)
            raise failure from recovery
        finally:
            for token in tokens:
                backend._invalidate(token)
            backend._prepared, backend._changed = prepared, changed
            backend._pending_layer_updates = pending
            backend._owned_shapes = owned
            backend._auxiliary_associations.pop(association_key, None)
            backend._revision += 1
        raise
    return token
