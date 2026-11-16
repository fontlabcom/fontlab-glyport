# this_file: src/fontlab_glyport/model/info_finalize.py
"""Glyph-info updater over explicitly qualified owned records.

``updateComponentsInfos`` updates the component infos; ``updateBaseString``
delegates to ``_stringForInfo``. The private default-mark array/fraction dictionary and
unknown physical recipes are deliberately unavailable, never empty defaults.
This host-only implementation is not native/high-level initialization proof.
"""

from collections.abc import Callable, Sequence
from types import SimpleNamespace

from ..errors import UnsupportedCapability
from .info_records import GlyphInfoIndex, add_unicode, new_record
from .production_metadata import _utf16_length
from .unicode_name import decode_unicode_name

UNKNOWN_ARABIC_MARKS = object()
_Lookup = Callable[[str], SimpleNamespace | None]


class _UnknownSource(Exception):
    """A dependency is unavailable; only its derived field is withheld."""


def _read(record: SimpleNamespace | None, field: str):
    if record is None:
        return None  # Objective-C nil messaging at an established missing lookup.
    if field in getattr(record, "_unavailable_fields", ()) or not hasattr(
        record, field
    ):
        raise _UnknownSource(field)
    return getattr(record, field)


def _unavailable(record: SimpleNamespace, field: str) -> None:
    record._unavailable_fields = frozenset(
        getattr(record, "_unavailable_fields", ())
    ) | {field}


def _components(record: SimpleNamespace):
    if "components" in getattr(record, "_unavailable_fields", ()):
        raise _UnknownSource("components")
    resolved = getattr(record, "_component_records", None)
    if resolved is not None:
        return resolved
    if not hasattr(record, "_component_names"):
        raise _UnknownSource("components")
    return record._component_names


def _reference(record: SimpleNamespace, field: str, lookup: _Lookup) -> None:
    values = _read(record, field)
    if not values or len(values) != 1:
        return
    token = values[0]
    if not isinstance(token, str):
        raise _UnknownSource(field)
    if _utf16_length(token) <= 1 or not token.startswith("="):
        return
    if token[1:] == _read(record, "name"):
        return
    target = lookup(token[1:])
    # Retained implementation tests TARGET MARKS even for the anchors branch.
    if _read(target, "marks"):
        setattr(record, field, _read(target, field))


def _marks(record: SimpleNamespace, lookup: _Lookup, defaults) -> None:
    if _read(record, "marks"):
        _reference(record, "marks", lookup)
    elif _read(record, "script") == "arabic" and _read(record, "category") == "Letter":
        if defaults is UNKNOWN_ARABIC_MARKS:
            raise _UnknownSource("marks")
        record.marks = defaults


def _resolve_components(
    record: SimpleNamespace, index: GlyphInfoIndex, lookup: _Lookup
):
    try:
        tokens = _components(record)
    except _UnknownSource:
        _unavailable(record, "components")
        return
    if not tokens:
        return  # Count zero leaves the nil/empty storage distinction intact.
    resolved = []
    for token in tokens:
        if not isinstance(token, str):
            raise UnsupportedCapability(
                "Component finalization requires source-qualified name tokens",
                capability="GSGlyphsInfo.updateComponentsInfos.componentTokens",
            )
        try:
            child = index.raw_name(token)
            if child is None:
                child = lookup(token)
        except UnsupportedCapability:
            _unavailable(record, "components")
            return
        if child is not None:
            resolved.append(child)
    record._component_records = resolved


def _unicode_text(record: SimpleNamespace) -> str | None:
    from .glyph_metadata import _hex_value

    cached = _read(record, "unicharString")
    if cached is not None:
        return cached
    codes = _read(record, "unicodes")
    text = None
    if codes:
        value = _hex_value(codes[0])
        if 0 < value <= 0x10FFFE:
            text = chr(value)
    legacy = _read(record, "unicodeLegacy")
    if legacy and _read(record, "script") == "arabic":
        value = _hex_value(legacy)
        if 0 < value <= 0x10FFFE:
            text = chr(value)
    record.unicharString = text
    return text


def _production(record: SimpleNamespace) -> str | None:
    state = _read(record, "_production_state")
    if state is None:
        raise _UnknownSource("production")
    return state.value


def _unicode_components(name: str, index: GlyphInfoIndex):
    def fresh(code):
        # baseInfosForUniName's final owned fallback always has a Unicode and
        # nil legacy encoding; its unknown script/category cannot alter text.
        item = new_record(("uni" if len(code) == 4 else "u") + code)
        add_unicode(item, code)
        return item

    return decode_unicode_name(name, index.raw_unicode, fresh)


def _component_text(record, components, index, lookup, seen, active):
    result = ""
    fraction = _read(record, "subCategory") == "Fraction"
    name = _read(record, "name")
    for child in components or ():
        if isinstance(child, str):
            # The native helper resolves residual tokens through SHARED, not
            # THIS manager. No qualified shared synthesis callback is supplied.
            raise _UnknownSource("shared component synthesis")
        if child is None or name in seen:
            continue
        if fraction and not _read(child, "unicodes") and _read(child, "case") == 4:
            raise _UnknownSource("private fraction dictionary")
        seen.add(name)
        try:
            result += _string_for_info(child, index, lookup, seen, active)
        finally:
            seen.remove(name)
    return result


def _suffix_text(record, production, index, lookup, seen, active):
    name = _read(record, "name")
    if name is not None and "." in name:
        target = lookup(name.split(".", 1)[0])
        if target is not None:
            if name in seen:
                text = ""
            else:
                seen.add(name)
                try:
                    text = _string_for_info(target, index, lookup, seen, active)
                finally:
                    seen.remove(name)
            if _read(record, "script") == "arabic":
                if ".fina" in name:
                    return "\u200d" + text
                if ".medi" in name:
                    return "\u200d" + text + "\u200d"
                if ".init" in name:
                    return text + "\u200d"
            return text
    # The native unsigned range expression requires the first dot at >= 2.
    if production is not None and production.find(".") >= 2:
        target = lookup(production.split(".", 1)[0])
        if target is None or _read(target, "name") == name:
            return ""
        return _string_for_info(target, index, lookup, seen, active)
    return ""


def _string_for_info(record, index, lookup, seen, active):
    if id(record) in active:
        # Component/name cycles have explicit native name guards. Production
        # recursion has no such guard; refuse that unsupported unbounded case.
        if _read(record, "name") in seen:
            return _suffix_text(
                record, _production(record), index, lookup, seen, active
            )
        raise _UnknownSource("unguarded production recursion")
    active.add(id(record))
    try:
        text = _unicode_text(record)
        if text is not None:
            return text
        production = _production(record)
        if production and _utf16_length(production) >= 2 and production.startswith("u"):
            components = _unicode_components(production, index)
        else:
            components = _components(record)
        text = _component_text(record, components, index, lookup, seen, active)
        return text or _suffix_text(record, production, index, lookup, seen, active)
    finally:
        active.remove(id(record))


def finalize_info(
    index: GlyphInfoIndex,
    lookup: _Lookup,
    *,
    arabic_fallback_marks: Sequence[str] | object = UNKNOWN_ARABIC_MARKS,
) -> None:
    """Finalize THIS manager in source order; preserve unrelated known fields.

    ``lookup`` is this manager's resolved full-name route. Missing resources or
    fields withhold only the derived field. Repeated resolved-object tokens are
    refused at their original source-order mutation point, without rollback.
    Default marks are an explicitly supplied owned resource, never guessed.
    """
    try:
        defaults = _read(lookup("alef-ar"), "marks")
        if not defaults:
            defaults = arabic_fallback_marks
    except (_UnknownSource, UnsupportedCapability):
        defaults = UNKNOWN_ARABIC_MARKS
    for record in index.records:
        _resolve_components(record, index, lookup)
        for field in ("marks", "anchors"):
            try:
                if field == "marks":
                    _marks(record, lookup, defaults)
                else:
                    _reference(record, field, lookup)
            except (_UnknownSource, UnsupportedCapability):
                _unavailable(record, field)
    for record in index.records:
        try:
            if _read(record, "baseString") is None:
                record.baseString = _string_for_info(
                    record, index, lookup, set(), set()
                )
        except (_UnknownSource, UnsupportedCapability):
            _unavailable(record, "baseString")
