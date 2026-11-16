# this_file: src/fontlab_glyport/model/custom_info.py
"""Ordered custom-attribute mutation of one manager's owned record graph.

This core is separate from XML discovery/parsing and public manager dispatch.
It accepts parser-produced string attributes, not arbitrary bridged objects.
"""

from types import SimpleNamespace

from .info_records import GlyphInfoIndex, add_unicode, new_record
from .metadata_tokens import case_from_string, direction_from_string
from .production_metadata import _utf16_length


def _matching_record(index: GlyphInfoIndex, attributes: dict[str, str], codes):
    """Use local indexes only; index removal never clears stored encodings."""
    record = index.names.get(attributes["name"])
    if record is not None:
        for code in record.unicodes:
            index.unicodes.pop(code, None)
        record._locked = False
        return record
    candidates = codes if codes is not None else [attributes.get("unicode")]
    candidates = [*candidates, attributes.get("unicode2")]
    for code in candidates:
        if not code:
            continue
        record = index.unicodes.get(code)
        if record is not None:
            record._locked = False
            index.names.pop(record.name, None)
            index.unicodes.pop(code, None)
            return record
    return None


def _known(record: SimpleNamespace, *fields: str) -> None:
    record._unavailable_fields = frozenset(
        getattr(record, "_unavailable_fields", ())
    ) - set(fields)


def _update_fields(record: SimpleNamespace, attributes: dict[str, str]) -> None:
    for field in ("sortName", "sortNameKeep", "script", "mirror"):
        if field in attributes:
            setattr(record, field, attributes[field])
            _known(record, field)
    if "production" in attributes:
        record._production_state.value = attributes["production"]
    for field, decode in (
        ("direction", direction_from_string),
        ("case", case_from_string),
    ):
        if field in attributes:
            setattr(record, field, decode(attributes[field]))
            _known(record, field)
    if "category" in attributes:
        record.category = attributes["category"]
        if "subCategory" in attributes:
            record.subCategory = attributes["subCategory"]
    if "deprecated" in attributes:
        record.deprecated = True


def _update_arrays(record: SimpleNamespace, attributes: dict[str, str]) -> None:
    record.altNames = (
        attributes["altNames"].split(", ") if "altNames" in attributes else None
    )
    if "decompose" in attributes:
        # Both native setters store the same ivar: replace names/records together.
        _known(record, "components")
        record._component_records = None
        record._component_names = (
            attributes["decompose"].split(", ") if attributes["decompose"] else None
        )
    if "anchors" in attributes:
        _known(record, "anchors")
        record.anchors = (
            attributes["anchors"].split(", ") if attributes["anchors"] else None
        )
    marks = attributes.get("marks", attributes.get("accents"))
    if marks is not None:
        _known(record, "marks")
        record.marks = marks.split(", ") if marks else None


def merge_custom(
    index: GlyphInfoIndex,
    attributes: dict[str, str],
    *,
    seen: set[str] | None = None,
    duplicates: set[str] | None = None,
) -> SimpleNamespace | None:
    """Retain native merge ordering, stale aliases and primary-only final index.

    Duplicate production tracking belongs to the caller's file scope and does
    not roll back mutations. Description/group/legacy are not custom-merge fields.
    """
    if "name" not in attributes:
        return None
    value = attributes.get("unicode")
    codes = (
        value.split(", ") if value is not None and _utf16_length(value) >= 10 else None
    )
    record = _matching_record(index, attributes, codes)
    fresh = record is None
    if fresh:
        record = new_record()
    record.name = attributes["name"]
    for code in codes if codes is not None else [value]:
        add_unicode(record, code)
    add_unicode(record, attributes.get("unicode2"))
    _update_fields(record, attributes)
    if "production" in attributes and seen is not None:
        production = record._production_state.value
        if production in seen and duplicates is not None:
            duplicates.add(production)
        seen.add(production)
    _update_arrays(record, attributes)
    for alias in record.altNames or ():
        index.names[alias] = record
    record._locked = True
    if fresh:
        index.records.append(record)
    index.names[record.name] = record
    production = record._production_state.value
    if production is not None and not production.startswith("uni"):
        index.names.setdefault(production, record)
    if production is not None and production.startswith("afii") and record.unicode:
        record._production_state.value = "uni" + record.unicode
    if record.unicode is not None:
        index.unicodes[record.unicode] = record
    return record
