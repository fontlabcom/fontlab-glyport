# this_file: src/fontlab_glyport/model/smallcap_metadata.py
"""Owned small-cap metadata stage; native/custom recipe qualification is separate."""

from .unicode_casing import lowercase_text, uppercase_scalar


def _utf16(values):
    encoded = "".join(map(chr, values)).encode("utf-16-be", "surrogatepass")
    return tuple(
        int.from_bytes(encoded[index : index + 2], "big")
        for index in range(0, len(encoded), 2)
    )


def _components(record):
    if "components" in getattr(record, "_unavailable_fields", ()):
        return None  # Unknown recipe differs from a known empty component list.
    explicit = getattr(record, "_component_records", None)
    if explicit is not None:
        return explicit
    from .glyph_metadata import _direct

    return [_direct(name) for name in (getattr(record, "_component_names", None) or ())]


def _copy_component(record, suffix, lowercase):
    from types import SimpleNamespace

    from ..errors import UnsupportedCapability
    from .glyph_metadata import _copy_production

    if record is None:
        raise UnsupportedCapability(
            "Small-cap expansion has a missing Unicode/component lookup",
            capability="GSGlyphInfo.smallCaps.expansion",
        )
    result = SimpleNamespace(**_copy_production(vars(record).copy()))
    result.name = lowercase(record.name)
    if record.category == "Letter":
        result.name += "." + suffix
    result.case = 3
    return result


def _remap(record, suffix, units, lookup, lowercase):
    donor = lookup(f"{units[0]:04X}")
    components = []
    if donor is not None:
        originals = _components(donor)
        if originals is None:
            record._component_records = record._component_names = None
            record._unavailable_fields = frozenset(
                getattr(record, "_unavailable_fields", ())
            ) | {"components", "anchors", "marks"}
            return
        if originals:
            components = [
                _copy_component(part, suffix, lowercase) for part in originals
            ]
        elif len(units) > 1:
            for unit in units:
                part = lookup(f"{unit:04X}")
                components.append(_copy_component(part, suffix, lowercase))
                if part.category == "Letter":
                    donor = part
    record._component_records = components
    record._unavailable_fields = frozenset(
        getattr(record, "_unavailable_fields", ())
    ) - {"components"}
    record._component_names = tuple(part.name for part in components)
    if donor is not None:
        for field in ("anchors", "marks"):
            value = getattr(donor, field, None)
            if value:
                setattr(record, field, value)


def apply_smallcaps(
    record,
    requested_name,
    suffix,
    lookup,
    *,
    uppercase=uppercase_scalar,
    lowercase=lowercase_text,
):
    """Set the small-cap case before the caller clears primary/legacy encodings."""
    if record.unicode and not requested_name.startswith("germandbls"):
        value = int(record.unicode, 16)
        units = _utf16(uppercase(value))
        if units[0] != value:
            _remap(record, suffix, units, lookup, lowercase)
    record.case = 3
