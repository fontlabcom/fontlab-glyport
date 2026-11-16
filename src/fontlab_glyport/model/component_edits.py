# this_file: src/fontlab_glyport/model/component_edits.py
"""One-level component edits; native geometry never passes through path recipes."""

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ..errors import NativeOperationError, PartialFailure, UnsupportedCapability

if TYPE_CHECKING:
    from .fontlab_backend import FontLabBackend
    from .proxies import GSComponent, GSLayer

# CompositeShapesBuilderImpl::_build_shape refuses a hierarchy at this depth.
_MAX_COMPONENT_DEPTH = 64


def _walk(owner: object, name: object, resolve: Callable) -> Any:
    active, done = {owner}, set()

    def visit(reference: object) -> Any:
        key, children, source = resolve(reference)
        if key in active:
            raise ValueError(f"Component cycle through {reference!r}")
        if key in done:
            return source
        if len(active) >= _MAX_COMPONENT_DEPTH:
            raise UnsupportedCapability(
                "Component hierarchy exceeds the native depth limit"
            )
        active.add(key)
        for child in children:
            visit(child)
        active.remove(key)
        done.add(key)
        return source

    return visit(name)


def native_reference(
    backend: "FontLabBackend", layer_id: str, name: str, component_layer: str = ""
) -> Any:
    layer = backend._require_editable_layer(layer_id)
    glyph_id = backend._parents[layer_id]
    package = backend._object(backend._parents[glyph_id])
    master_name = backend._master_names[backend._layer_masters[layer_id]]

    def resolve(reference: tuple[str, str]) -> tuple[object, list, Any]:
        glyph_name, layer_name = reference
        glyph = package.findName(glyph_name)
        if glyph is None or not glyph.isValid:
            raise ValueError(f"No glyph named {glyph_name!r} in the containing font")
        source = glyph.findLayer(layer_name or master_name)
        if source is None or not source.isValid or source.autoLayer:
            raise UnsupportedCapability(
                "Component base needs a concrete, non-auto layer"
            )
        children = []
        for shape in source.shapes:
            if (
                not shape.transform.isAffine()
                or shape.isComposite
                and not shape.isComponent
            ):
                raise UnsupportedCapability(
                    "Unsupported component base shape or transform"
                )
            if shape.isComponent:
                children.append(
                    (shape.shapeData.componentGlyph, shape.shapeData.componentLayer)
                )
        return (glyph.id, source.id), children, source

    owner = backend._object(glyph_id).id, layer.id
    return _walk(owner, (name, component_layer), resolve)


def rename_native(backend: "FontLabBackend", component_id: str, name: str) -> None:
    shape = backend._object(component_id)
    layer_id = backend._parents[component_id]
    if shape.shapeData.componentGlyph == name:
        return
    native_reference(backend, layer_id, name, shape.shapeData.componentLayer)
    state = backend.snapshot_collection(layer_id)
    try:
        shape = backend._own_shape(layer_id, shape)
        shape.shapeData.componentGlyph = name
    except BaseException as error:
        try:
            backend.restore_collection(layer_id, state)
        except BaseException as recovery:
            failure = PartialFailure(
                f"Could not restore component reference: {recovery}",
                capability="GSComponent.componentName",
            )
            failure.errors = error, recovery
            raise failure from recovery
        raise
    backend._touch_layer(layer_id)


def _retire_component(backend: "FontLabBackend", component_id: str) -> None:
    from .fontlab_backend import _LIVE_BACKENDS

    document, _, native_id = backend._object_keys[component_id]
    package_id = backend._object_keys[document][2]
    for peer in tuple(_LIVE_BACKENDS):
        peer_document = peer._keys.get((package_id, "font", package_id))
        token = peer._keys.get((peer_document, "component", native_id))
        if token is not None:
            peer._invalidate(token)
            # Decomposition destroys this identity. History's ordinal fallback
            # and moved-handle recovery must not reuse it for a replacement.
            for mapping in (peer._history_aliases, peer._history_slots):
                for key, previous in tuple(mapping.items()):
                    if previous == token:
                        del mapping[key]
            peer._revision += 1


def decompose_native(
    backend: "FontLabBackend",
    layer_id: str,
    component_id: str,
    on_detach: Callable[[], None],
) -> None:
    backend._update_pending_layers()
    layer, shape = backend._object(layer_id), backend._object(component_id)
    if backend._parents[component_id] != layer_id:
        raise ValueError("Component does not belong to layer")
    native_reference(
        backend,
        layer_id,
        shape.shapeData.componentGlyph,
        shape.shapeData.componentLayer,
    )
    # Includes are cached even after layer updates; refresh the exact builder
    # before staging. Nonempty includes can still describe an earlier base.
    if shape.shapeData.builder.update() is False:
        raise NativeOperationError(
            "FontLab refused to refresh the component before decomposition",
            capability="GSComponent.decompose",
        )
    index = next(i for i, item in enumerate(layer.shapes) if item.id == shape.id)
    originals = tuple(shape.includesList)
    replacements = tuple(shape.ejectTo())  # default clone=True, apply_tx=True
    for source, clone in zip(originals, replacements, strict=True):
        backend._copy_clone_connections(source, clone)
    state = backend.snapshot_collection(layer_id)
    backend._prepare_layer(layer_id)
    backend._retain_component_history(layer_id, shape)
    try:
        layer.removeShape(shape)
        for offset, replacement in enumerate(replacements):
            layer.insertShape(index + offset, replacement)
    except BaseException as error:
        try:
            backend.restore_collection(layer_id, state)
        except BaseException as recovery:
            failure = PartialFailure(
                f"Could not restore component: {recovery}",
                capability="GSComponent.decompose",
            )
            failure.errors = error, recovery
            raise failure from recovery
        raise
    _retire_component(backend, component_id)
    try:
        on_detach()
    finally:
        backend._touch_layer(layer_id)


def decompose_proxy(layer: "GSLayer", component: "GSComponent") -> None:
    from .proxies import GSComponent

    if not isinstance(component, GSComponent) or component.parent is not layer:
        raise ValueError("Component does not belong to this layer")
    if "_font" not in layer.__dict__:
        raise UnsupportedCapability(
            "Detached one-level component decomposition is not mapped"
        )
    component._check()
    snapshot = replace(component._data(), id="")
    font, token = component._font, component._id

    def detached() -> None:
        font._cache.pop((GSComponent, token), None)
        component.__dict__.clear()
        component._draft = snapshot

    font._model._backend.decompose_component(layer._id, token, on_detach=detached)
