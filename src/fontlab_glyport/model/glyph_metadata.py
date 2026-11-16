# this_file: src/fontlab_glyport/model/glyph_metadata.py
"""Owned metadata resolution from maintained data and audited scalar facts.

Native custom managers remain unqualified. ROS resource requests refuse when
their proprietary mapping data is required. The owned Arabic presentation stage
follows additional Unicode/ROS and precedes stored overlays. This resolver never
imports or queries a native application.
"""

from functools import lru_cache
from types import SimpleNamespace

PREFIX = "com.schriftgestaltung.Glyphs."
FIELDS = (
    ("case", "com.fontlab.glyport.case", "com.fontlab.glyport.storeCase"),
    ("group", PREFIX + "group", PREFIX + "storeGroup"),
    ("script", PREFIX + "script", PREFIX + "storeScript"),
    ("category", PREFIX + "category", PREFIX + "storeCategory"),
    ("subCategory", PREFIX + "subCategory", PREFIX + "storeSubCategory"),
    ("direction", PREFIX + "direction", PREFIX + "storeDirection"),
)
KEEP_NAME_CATEGORIES = {"Icon", "SF-Symbol"}
# Audited Glyphs4 scriptForUnicode synthesis ranges, not Unicode Script data.
HAN_RANGES = (
    (0x2E80, 0x1A),
    (0x2E9B, 0x59),
    (0x2F00, 0xD6),
    (0x3005, 1),
    (0x3007, 1),
    (0x3021, 9),
    (0x3038, 3),
    (0x303B, 1),
    (0x3400, 0x19B6),
    (0x4E00, 0x51CD),
    (0xF900, 0x16E),
    (0xFA70, 0x6A),
    (0x2F800, 0x21E),
    (0x20000, 0xA6D7),
    (0x2A700, 0x1035),
    (0x2B740, 0xDE),
    (0x2B820, 0x1682),
    (0x2CEB0, 0x1D31),
    (0x30000, 0x134B),
    (0x1F200, 0x100),
)
_UNKNOWN_PRODUCTION = object()


def private_use(value):
    return any(
        start <= value <= end
        for start, end in ((0xE000, 0xF8FF), (0xF0000, 0xFFFFD), (0x100000, 0x10FFFD))
    )


def _record(
    name,
    *,
    unicode=None,
    unicodeLegacy=None,
    category=None,
    subCategory=None,
    script=None,
    case=0,
    production=_UNKNOWN_PRODUCTION,
):
    from .info_records import add_unicode, new_record

    result = new_record(name)
    add_unicode(result, unicode)
    vars(result).update(
        unicodeLegacy=unicodeLegacy,
        category=category,
        subCategory=subCategory,
        script=script,
        case=case,
    )
    if production is _UNKNOWN_PRODUCTION:
        result._production_state = None
    else:
        result._production_state.value = production
    return result


def _data():
    from ..glyphsapp.glyph_info import glyph_categories

    glyph_categories("", [])  # Keep the documented dependency error at this boundary.
    from glyphsLib import glyphdata

    from .info_source import current_index

    index = current_index()
    if index is not None:
        from functools import partial

        data = getattr(index, "data", None)
        if data is None and index.shared is not None:
            data = getattr(index.shared, "data", None)
        if data is not None:
            return SimpleNamespace(
                GLYPHDATA=data, get_glyph=partial(glyphdata.get_glyph, data=data)
            )
    return glyphdata


def _direct(name):
    from .info_source import current_index

    index = current_index()
    if index is None:
        from ..glyphsapp.info_manager import GSGlyphsInfo

        index = GSGlyphsInfo.sharedManager()._index
    return index.raw_name(name)


def _suffix(record, name, suffix=None):
    values = _copy_production(vars(record).copy())
    from .production_metadata import StoredProduction, production_name

    if suffix is None:
        suffix = name.split(".")[len(record.name.split(".")) :]
    values.pop("_public_view", None)
    stored = values.get("_production_state")
    if stored is not None:
        base = production_name(record.name, stored.value, record.unicode, record.script)
        values["_production_state"] = StoredProduction(base + "." + ".".join(suffix))
    resolved_name = (
        name if name.startswith(record.name) else record.name + "." + ".".join(suffix)
    )
    values.update(name=resolved_name)
    values["unicodes"] = ()
    suffixes = set(suffix)
    if suffixes & {"case", "lf", "tf"}:
        values["case"] = 1
    elif suffixes & {"osf", "tosf"}:
        values["case"] = 2
    if suffixes & {"sc", "smcp", "c2sc", "pc", "pcap"}:
        from .smallcap_metadata import apply_smallcaps

        result = SimpleNamespace(**values)
        apply_smallcaps(result, name, ".".join(suffix), unicode_info)
        values = vars(result)
    elif values["category"] != "Number":
        if suffixes & {"subs", "sups", "sinf", "inferior"}:
            values["case"] = 4
        elif suffixes & {"dnom", "numr"}:
            values["subCategory"] = "Fraction"
    if values["script"] is None:
        from .compound_production import language_suffix
        from .compound_scripts import script_for_tag

        language = language_suffix(record.name)
        if language:
            values["script"] = script_for_tag(language) or language
    values.update(unicode=None, unicodeLegacy=None)
    return SimpleNamespace(**values)


def _copy_production(values: dict[str, object]) -> dict[str, object]:
    """Detach the stored field exactly when an owned native copy is required."""
    from .production_metadata import StoredProduction

    values.pop("_public_view", None)
    stored = values.get("_production_state")
    if stored is not None:
        values["_production_state"] = StoredProduction(stored.value)
    for field in ("anchors", "marks", "_component_records"):
        if values.get(field) is not None:
            values[field] = list(values[field])
    values["unicharString"] = None
    values["_locked"] = False
    return values


def _fill_production(record: SimpleNamespace) -> SimpleNamespace:
    from .production_metadata import production_name

    stored = getattr(record, "_production_state", None)
    if stored is not None and stored.value is None:
        stored.value = production_name(record.name, None, record.unicode, record.script)
    return record


def _unicode_records(name: str) -> list[SimpleNamespace] | None:
    from .unicode_name import decode_unicode_name

    def fallback(code):
        return _record(
            ("uni" if len(code) == 4 else "u") + code, unicode=code, production=None
        )

    return decode_unicode_name(name, unicode_info, fallback)


def _unicode_name(name: str, suffixes=None) -> SimpleNamespace | None:
    """Decode raw records, then copy one or compose their canonical names."""
    records = _unicode_records(name)
    if not records:
        return None
    if len(records) == 1:
        return SimpleNamespace(**_copy_production(vars(records[0]).copy()))
    from .compound_metadata import compose_names

    return compose_names([record.name for record in records], suffixes)


def name_info(name, font=None, *, fill_production=False):
    """Resolve known names and preserve the existing suffix-category route."""
    direct = _direct(name)
    if direct is not None:
        return _fill_production(direct) if fill_production else direct
    data = _data()
    if len(name) == 1:
        return unicode_info(f"{ord(name):04X}")
    if (
        len(name) == 2
        and 0xD800 <= ord(name[0]) <= 0xDBFF
        and 0xDC00 <= ord(name[1]) <= 0xDFFF
    ):
        scalar = 0x10000 + ((ord(name[0]) - 0xD800) << 10) + ord(name[1]) - 0xDC00
        return unicode_info(f"{scalar:04X}")
    decoded = _unicode_name(name)
    if decoded is not None:
        return decoded
    if "." in name:
        parts = name.split(".")
        if font is not None and not fill_production:
            for end in range(len(parts) - 1, 0, -1):
                source = font.glyphs[".".join(parts[:end])]
                if source is not None and source.unicode:
                    record = resolve(source)
                    if record is not None:
                        return _suffix(record, name, parts[end:])
        # The name algorithm chooses a represented longest prefix. It does not
        # synthesize intermediate prefixes before passing remaining suffixes.
        for end in range(len(parts) - 1, 0, -1):
            record = _direct(".".join(parts[:end]))
            if record is not None:
                remaining = parts[end:]
                candidate = _direct(record.name + "." + remaining[0])
                if candidate is not None:
                    # This canonical re-entry keeps a nonnil empty array after
                    # consuming its last token; the decoded-single route below
                    # instead chooses nil. Their trailing-dot results differ.
                    return _suffix(candidate, name, remaining[1:])
                record = _direct(record.name) or record
                if parts[-1] in {"case", "cap"}:
                    record = SimpleNamespace(**_copy_production(vars(record).copy()))
                    record.case = 1
                return _suffix(_fill_production(record), name, remaining)
        decoded_records = _unicode_records(parts[0]) if len(parts[0]) > 1 else None
        if decoded_records and len(decoded_records) > 1:
            from .compound_metadata import compose_names

            record = compose_names(
                [record.name for record in decoded_records], parts[1:]
            )
            if record is not None:
                record.unicode = record.unicodeLegacy = None
                return record
        record = name_info(parts[0], fill_production=True)
        if record is not None:
            if decoded_records and len(decoded_records) == 1:
                candidate = _direct(record.name + "." + parts[1])
                if candidate is not None:
                    remaining = parts[2:]
                    if remaining:
                        return _suffix(candidate, name, remaining)
                    # A consumed last token produces a nil list, not an empty
                    # array: native suffix handling stores no helper result.
                    values = _copy_production(vars(candidate).copy())
                    values.update(unicode=None, unicodeLegacy=None)
                    return SimpleNamespace(**values)
            return _suffix(record, name, parts[1:])
    constructed = data.get_glyph(name)
    if constructed.category is not None:
        return _record(
            name,
            category=constructed.category,
            subCategory=constructed.subCategory,
            script=constructed.script,
        )
    return None


def _hex_value(code):
    """Audited NSString helper: additive uint32 nibbles, spaces and minus signs."""
    if not code:
        return 0x7FFFFFFF
    value, shift, negative = 0, 0, False
    for character in reversed(code):
        if character in "- ":
            negative = negative or character == "-"
            continue
        if character not in "0123456789ABCDEFabcdef":
            return 0x7FFFFFFF
        value = (value + (int(character, 16) << shift)) & 0xFFFFFFFF
        shift = (shift + 4) & 31
    return (-value if negative else value) & 0xFFFFFFFF


@lru_cache(maxsize=1)
def _unicode_index(data):
    """Index immutable public records in parser order, primary then legacy.

    glyphsLib's own Unicode dictionary omits legacy keys. Keep it unchanged;
    cache this adapter by the actual static GlyphData identity instead.
    """
    index = {}
    for attributes in data.names.values():
        for field in ("unicode", "unicodeLegacy"):
            code = attributes.get(field)
            if code is not None:
                index[code] = attributes
    return index


def unicode_info(code):
    """Direct Unicode data wins; a synthesized result also stops iteration."""
    from .info_source import current_index

    index = current_index()
    if index is None:
        from ..glyphsapp.info_manager import GSGlyphsInfo

        index = GSGlyphsInfo.sharedManager()._index
    record = index.raw_unicode(code)
    if record is not None:
        return record
    value = _hex_value(code)
    bmp = value < 0x10000 or value >= 0x80000000
    if not bmp and value > 0x10FFFE:
        return None
    script = (
        "han"
        if any(start <= value < start + count for start, count in HAN_RANGES)
        else None
    )
    category = "Private Use" if private_use(value) else "Letter" if script else "Other"
    name = ("uni" if bmp else "u") + code
    record = _record(
        name,
        production=name,
        unicode=code if len(code) < 8 else None,
        category=category,
        script=None if private_use(value) else script,
    )
    record.sortName = ("uni0" if bmp else "unj") + code
    return record


def ros_unicode(glyph, record):
    """Recognize shipped ROS resources without substituting different mappings.

    The audited shared manager uses exact registry/ordering strings and ignores
    the supplement. Its five proprietary MapFiles are not redistributed here;
    refusing before writes avoids silently retaining the wrong Unicode set.
    """
    if record is None or glyph.parent is None:
        return record
    value = glyph.parent.customParameters["ROS"]
    if value is None:
        return record
    if type(value) is not str:
        from ..errors import UnsupportedCapability

        raise UnsupportedCapability(
            "ROS values require an audited native string description; use text.",
            capability="GSGlyphInfo.ROS.value",
        )
    parts = value.split("-")
    if len(parts) != 3:
        parts = value.split(", ")
    if len(parts) == 3 and "-".join(parts[:2]) in {
        "Adobe-CNS1",
        "Adobe-GB1",
        "Adobe-Japan1",
        "Adobe-KR",
        "Adobe-Korea1",
    }:
        from ..errors import UnsupportedCapability

        raise UnsupportedCapability(
            "ROS Unicode replacement requires Glyphs' proprietary mapping data; "
            "the requested metadata cannot be resolved with maintained GlyphData.",
            capability="GSGlyphInfo.ROS.mappingData",
        )
    return record


def _resolve(glyph, *, name=None, unicodes=None, state=None):
    """Resolve one glyph, then overlay independently stored metadata fields."""
    name = glyph.name if name is None else name
    codes = glyph.unicodes if unicodes is None else unicodes
    state = glyph._case_state() if state is None else state
    category_key = PREFIX + "category"
    category = state[category_key] if category_key in state else glyph.category  # noqa: SIM401 - fallback property must stay lazy when the key exists
    if category in KEEP_NAME_CATEGORIES:
        return _record(name, category=category, production=None)
    record = None
    for code in codes:
        record = unicode_info(code)
        if record is not None:
            break
    if record is None:
        record = name_info(name, glyph.parent)
    if record is None:
        return None
    if record.category == "Private Use":
        if getattr(record, "_locked", True):
            record = SimpleNamespace(**_copy_production(vars(record).copy()))
        record.name = name
        record.unicode = next(iter(codes), record.unicode)
        record.unicodes = tuple(codes)
    from .unicode_case import additional_unicode, presentation_unicode

    record = additional_unicode(glyph, record, name, codes)
    record = ros_unicode(glyph, record)
    record = presentation_unicode(glyph, record)
    if record is None:
        return None
    if any(state.get(flag, False) for _, _, flag in FIELDS):
        if getattr(record, "_locked", True):
            record = SimpleNamespace(**_copy_production(vars(record).copy()))
        for field, key, flag in FIELDS:
            if state.get(flag, False):
                setattr(
                    record, field, state[key] if key in state else getattr(glyph, field)
                )
                record._unavailable_fields = frozenset(
                    getattr(record, "_unavailable_fields", ())
                ) - {field}
    return record


def resolve(glyph, *, name=None, unicodes=None, state=None):
    """Bind actual attached glyphs to their selected manager for the whole call."""
    from .info_source import current_index
    from .proxies import GSGlyph

    if (
        current_index() is None
        and isinstance(glyph, GSGlyph)
        and glyph.parent is not None
    ):
        from ..glyphsapp.info_manager import GSGlyphsInfo

        manager = glyph.parent.glyphsInfo()
        if not isinstance(manager, GSGlyphsInfo):
            from ..errors import UnsupportedCapability

            raise UnsupportedCapability(
                "Staged metadata requires a qualified manager record protocol",
                capability="GSGlyphInfo.manager.stagedMetadata",
            )
        with manager._scope():
            return _resolve(glyph, name=name, unicodes=unicodes, state=state)
    return _resolve(glyph, name=name, unicodes=unicodes, state=state)


def raw_name_info(name):
    """Keep the legacy model's raw defaults independent of selected resolution."""
    from .info_source import selected_index

    with selected_index(None):
        return name_info(name)
