# this_file: src/fontlab_glyport/model/attachment.py
"""Populate an inserted glyph before binding the caller's detached copy."""

from ..errors import PartialFailure


def target_master(font, source):
    """Proxy tokens are session-local; cross-font copies match master names."""
    from .proxies import _unsupported

    masters = list(font.masters)
    owner = source.__dict__.get("_master_owner")
    if (
        owner is not None
        and owner == font._copy_owner
        and source.associatedMasterId in {master.id for master in masters}
    ):
        return source.associatedMasterId
    matches = [
        master.id
        for master in masters
        if master.name == source.__dict__.get("_master_name", source.name)
    ]
    if len(matches) != 1:
        _unsupported("font.glyphs.append: unmatched layer master")
    return matches[0]


def require_supported_attributes(layer):
    """The backend cannot persist Glyphs brace/bracket layer attributes."""
    from .._strict import caller_location
    from ..errors import UnsupportedCapability

    if layer.__dict__.get("_attributes"):
        raise UnsupportedCapability(
            "The model backend cannot attach Glyphs layer attributes",
            capability="GSLayer.attributes.attach",
            location=caller_location(),
        )
    background = layer.__dict__.get("_background")
    if background is not None:
        require_supported_attributes(background)


def populate_layer(destination, source):
    from .fontlab_backend import _plain

    require_supported_attributes(source)
    destination.width = source.width
    destination.shapes = source.shapes
    destination.anchors = source.anchors
    destination.guides = source.guides
    destination.hints = source.hints
    destination.userData.update(_plain(dict(source.userData)))
    for side in ("left", "right", "width"):
        name = side + "MetricsKey"
        setattr(destination, name, getattr(source, name))
    # Copies snapshot backgrounds without creating a native mask on read.
    background = source.__dict__.get("_background")
    if background is not None:
        destination.background = background


def attach(font, glyph, data, layers, user_data):
    from .fontlab_backend import _plain
    from .glyph_metadata import FIELDS
    from .proxies import GSGlyph, _Proxy

    # Validate the entire graph before insertion, not only when a lib is written.
    user_data = _plain(user_data)

    def validate_layer(layer):
        require_supported_attributes(layer)
        _plain(dict(layer.userData))
        background = layer.__dict__.get("_background")
        if background is not None:
            validate_layer(background)

    for layer in layers:
        validate_layer(layer)
        target_master(font, layer)
    backend = font._model._backend
    case_state = {
        key: value
        for key, value in glyph._case_state().items()
        if key in {item for _, key, flag in FIELDS for item in (key, flag)}
    }
    codes = data.unicodes
    token = (
        backend.append_glyph(font._id, data.name, unicodes=codes)
        if codes
        else backend.append_glyph(font._id, data.name)
    )
    staged = object.__new__(GSGlyph)
    _Proxy.__init__(staged, font, token, lambda: font.glyphs.info(token))
    font._cache[GSGlyph, token] = staged
    destinations = []
    try:
        staged.userData.update(user_data)
        if case_state:
            state = staged._case_state()
            state.update(case_state)
            staged._set_case_state(state)
        for side, value in glyph.__dict__.get("_glyph_metrics_keys", {}).items():
            setattr(staged, side + "MetricsKey", value)
        for source in layers:
            destination = staged.layers[target_master(font, source)]
            populate_layer(destination, source)
            destinations.append(destination)
    except BaseException as error:
        try:
            backend.remove_glyph(font._id, token)
        except BaseException as recovery:
            failure = PartialFailure(
                f"Glyph attachment failed and insertion could not be removed: {recovery}",
                capability="GSFont.glyphs.append.rollback",
            )
            failure.errors = (error, recovery)
            raise failure from recovery
        finally:
            font._cache.pop((GSGlyph, token), None)
        raise
    glyph.__class__ = GSGlyph
    glyph.__dict__.clear()
    glyph.__dict__.update(staged.__dict__)
    font._cache[GSGlyph, token] = glyph
    # Its first layer-index closure captured the temporary owner. Rebuild it
    # so later reads cannot overwrite layer.parent with that staging proxy.
    font._indexes.pop((token, "layers"), None)
    for destination in destinations:
        destination._glyph = glyph
    return glyph
