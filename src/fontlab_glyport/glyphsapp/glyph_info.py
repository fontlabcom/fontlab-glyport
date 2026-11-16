# this_file: src/fontlab_glyport/glyphsapp/glyph_info.py
"""Raw snapshots, selected-manager views and the public GlyphData adapter.

Public metadata is source-qualified. Missing proprietary physical recipes are
explicit gaps; Unicode decomposition is not published as their replacement.
"""

import unicodedata
from functools import lru_cache
from types import SimpleNamespace
from typing import TYPE_CHECKING

from ..errors import UnsupportedCapability
from ..fonttools import fonttools_module
from ..model.proxies import _Explicit
from ..ui.cocoa import unsupported

if TYPE_CHECKING:
    from glyphsLib.glyphdata import GlyphData

_UNKNOWN_DESCRIPTION = object()


def glyph_categories(name: str, unicodes: list[str]) -> tuple[str | None, str | None]:
    """Read maintained GlyphData lazily; known names take priority over encoding."""
    try:
        from glyphsLib import glyphdata
    except ImportError as error:
        raise UnsupportedCapability(
            f"GSGlyph category metadata requires the glyphsLib dependency: {error}",
            capability="GSGlyph.categories.dependency",
            recovery_action="Install fontlab-glyport with its declared dependencies.",
        ) from error
    record = glyphdata.get_glyph(name)
    if record.category is None and unicodes:
        record = glyphdata.get_glyph(name, unicodes=unicodes)
    return record.category, record.subCategory


class GSGlyphInfo(_Explicit):
    """Read-only metadata; raw production shares fills while copies freeze it."""

    def __init__(self, glyph):
        from ..model.proxies import GSGlyph

        self._name, self._unicode = glyph.name, glyph.unicode
        self._category, self._sub_category = glyph.category, glyph.subCategory
        self._script = glyph.script
        self._case = glyph.case
        if isinstance(glyph, GSGlyph):
            from ..model.glyph_metadata import resolve

            record = resolve(glyph)
            self._unicode_legacy = record.unicodeLegacy if record is not None else None
        else:
            record = glyph
            self._unicode_legacy = getattr(glyph, "unicodeLegacy", None)
        self._production_state = getattr(record, "_production_state", None)
        self._description = getattr(record, "desc", _UNKNOWN_DESCRIPTION)
        self._components = []
        raw = glyph if isinstance(glyph, GSGlyph) else record
        self._group = getattr(raw, "group", _UNKNOWN_DESCRIPTION)
        self._group_idx = getattr(raw, "groupIdx", _UNKNOWN_DESCRIPTION)
        self._direction = getattr(raw, "direction", _UNKNOWN_DESCRIPTION)
        self._snapshot_unavailable = frozenset(
            getattr(record, "_unavailable_fields", ())
        )
        if isinstance(glyph, GSGlyph):
            self._snapshot_unavailable -= {"group", "groupIdx", "direction"}

    @classmethod
    def from_record(cls, record):
        """Bridge a selected record without re-resolving or consulting outlines."""
        if "_public_view" not in vars(record):
            result = cls.__new__(cls)
            result._resolved_record = record
            result._production_state = getattr(record, "_production_state", None)
            result._components = []
            record._public_view = result
        return record._public_view

    def _value(self, field, private):
        record = self.__dict__.get("_resolved_record")
        if record is None:
            result = self.__dict__.get(private, _UNKNOWN_DESCRIPTION)
            if field in self.__dict__.get("_snapshot_unavailable", ()):
                result = _UNKNOWN_DESCRIPTION
        else:
            result = getattr(record, field, _UNKNOWN_DESCRIPTION)
            if field in getattr(record, "_unavailable_fields", ()):
                result = _UNKNOWN_DESCRIPTION
        if result is _UNKNOWN_DESCRIPTION:
            raise UnsupportedCapability(
                f"This metadata source does not establish {field}",
                capability=f"GSGlyphInfo.{field}.source",
            )
        return result

    @property
    def desc(self) -> str | None:
        """Stored nullable description from the selected record, without synthesis."""
        return self._value("desc", "_description")

    @property
    def productionName(self) -> str | None:
        """Stored production; raw shared records can observe a later name fill."""
        record = self.__dict__.get("_resolved_record")
        state = (
            self._production_state
            if record is None
            else getattr(record, "_production_state", None)
        )
        if state is None:
            raise UnsupportedCapability(
                "This metadata source does not establish stored production",
                capability="GSGlyphInfo.productionName.source",
            )
        return state.value

    def __copy__(self) -> "GSGlyphInfo":
        from ..model.production_metadata import StoredProduction

        record = self.__dict__.get("_resolved_record")
        if record is not None:
            from ..model.info_records import copy_record

            return type(self).from_record(copy_record(record))
        result = type(self).__new__(type(self))
        result.__dict__.update(self.__dict__)
        result._components = list(self._components)
        if self._production_state is not None:
            result._production_state = StoredProduction(self._production_state.value)
        return result

    def __deepcopy__(self, memo: dict[int, object]) -> "GSGlyphInfo":
        result = self.__copy__()
        memo[id(self)] = result
        return result

    name = property(lambda self: self._value("name", "_name"))
    unicode = property(lambda self: self._value("unicode", "_unicode"))
    unicodeLegacy = property(
        lambda self: self._value("unicodeLegacy", "_unicode_legacy")
    )
    category = property(lambda self: self._value("category", "_category"))
    subCategory = property(lambda self: self._value("subCategory", "_sub_category"))
    script = property(lambda self: self._value("script", "_script"))
    case = property(lambda self: self._value("case", "_case"))
    group = property(lambda self: self._value("group", "_group"))
    groupIdx = property(lambda self: self._value("groupIdx", "_group_idx"))
    direction = property(lambda self: self._value("direction", "_direction"))

    @property
    def components(self):
        record = self.__dict__.get("_resolved_record")
        if record is None:
            return list(self._components)
        if "components" in getattr(record, "_unavailable_fields", ()):
            raise UnsupportedCapability(
                "The source does not establish metadata recipes",
                capability="GSGlyphInfo.components.source",
            )
        records = getattr(record, "_component_records", None)
        if records is None:
            names = getattr(record, "_component_names", None)
            return None if names is None else list(names)
        return [type(self).from_record(child) for child in records]


@lru_cache(maxsize=1)
def _name_index(data: "GlyphData") -> dict[str, dict[str, str]]:
    """Retained parser: primary, non-uni production, then aliases; later wins."""
    index = {}
    for attributes in data.names.values():
        index[attributes["name"]] = attributes
        production = attributes.get("production")
        if production is not None and not production.startswith("uni"):
            index[production] = attributes
        if "altNames" in attributes:
            for alias in attributes["altNames"].replace(" ", "").split(","):
                index[alias] = attributes
    return index


def _database_glyph(
    name, *, missing_ok=False, attributes=None, _data_override=None, _owned=False
):
    try:
        from glyphsLib import glyphdata

        glyphdata.get_glyph(name)  # initializes the lazily loaded XML data
    except ImportError as error:
        raise UnsupportedCapability(
            f"Glyphs.glyphInfoForName.{name} requires the glyphsLib dependency: {error}",
            capability=f"Glyphs.glyphInfoForName.{name}",
        ) from error
    data = glyphdata.GLYPHDATA if _data_override is None else _data_override
    if attributes is None:
        attributes = _name_index(data).get(name) if name else None
    if not attributes:
        if missing_ok:
            return None, []
        raise unsupported(f"Glyphs.glyphInfoForName.{name}")
    case_values = {
        None: 0,
        "noCase": 0,
        "upper": 1,
        "lower": 2,
        "smallCaps": 3,
        "minor": 4,
        "other": 5,
    }
    case_name = attributes.get("case")
    if case_name not in case_values:
        raise unsupported("GSGlyphInfo.case")
    canonical = attributes["name"]
    from ..model.metadata_tokens import direction_from_string
    from ..model.production_metadata import StoredProduction, slot_for

    record = glyphdata.get_glyph(canonical, data=data)
    components = []
    if record.unicode:
        char = chr(int(record.unicode, 16))
        decomposed = unicodedata.normalize("NFD", char)
        if decomposed != char:
            for char in decomposed:
                component = data.unicodes.get(f"{ord(char):04X}")
                if component is None:
                    # A partial construction would be misleading.
                    components = []
                    break
                components.append(component["name"])
    return SimpleNamespace(
        name=canonical,
        unicode=record.unicode,
        unicodeLegacy=attributes.get("unicodeLegacy"),
        category=record.category,
        subCategory=record.subCategory,
        script=record.script,
        case=case_values[case_name],
        desc=attributes.get("description"),
        group=attributes.get("group"),
        groupIdx=0,
        direction=direction_from_string(attributes.get("direction")),
        _locked=True,
        anchors=attributes["anchors"].split(", ")
        if attributes.get("anchors") is not None
        else None,
        marks=attributes["marks"].split(", ")
        if attributes.get("marks") is not None
        else None,
        sortName=attributes.get("sortName"),
        sortNameKeep=attributes.get("sortNameKeep"),
        unicharString=None,
        baseString=None,
        _unavailable_fields=frozenset({"group", "groupIdx"})
        | frozenset(
            field
            for field in ("anchors", "marks", "sortName", "sortNameKeep")
            if field not in attributes
        ),
        _production_state=(
            StoredProduction(attributes.get("production"))
            if _owned
            else slot_for(data, attributes)
        ),
        _component_names=tuple(components),
    ), components


def glyph_info(font, name):
    """Use one manager protocol for global and explicit-font metadata."""
    from .info_manager import GSGlyphsInfo

    manager = GSGlyphsInfo.sharedManager() if font is None else font.glyphsInfo()
    return manager.glyphInfoForName_(name)


def checked_unicode_code(value):
    """Validate the audited wrapper string boundary without performing a lookup."""
    if value is None:
        return None
    if type(value) is not str:
        raise UnsupportedCapability(
            "This Unicode lookup input requires unqualified bridge conversion",
            capability="Glyphs.glyphInfoForUnicode.inputType",
        )
    raw = value.encode("utf-16-le", errors="surrogatepass")
    if len(raw) < 6:
        return None
    try:
        raw.decode("utf-16-le")
    except UnicodeDecodeError as error:
        raise UnsupportedCapability(
            "Malformed UTF16 can yield a NULL native UTF8 pointer",
            capability="Glyphs.glyphInfoForUnicode.UTF16",
        ) from error
    return value.upper()


def unicode_glyph_info(value):
    """Global helpers share the same raw graph, views and production cells."""
    from .info_manager import GSGlyphsInfo

    return GSGlyphsInfo.sharedManager().glyphInfoForUnicode_(value)


def creation_unicodes(name):
    """Default encoding from Glyph Info; suffixed/unknown glyphs stay unencoded.

    Glyphs 3 GSGlyph(name) calls setName_, which initializes Glyph Info. Resolve
    on draft name assignment so append can preserve that exact encoding and
    a later updateGlyphInfo need not write fontgate.
    Optional database/tool absence must not prevent custom glyph creation.
    """
    if "." in name:
        return ()
    try:
        record, _ = _database_glyph(name)
        return (record.unicode,) if record.unicode else ()
    except UnsupportedCapability:
        pass
    try:
        agl = fonttools_module("agl", "GSGlyph.creation.unicodes")
    except UnsupportedCapability:
        return ()
    value = agl.toUnicode(name)
    if not value and name.endswith("comb"):
        value = agl.toUnicode(name[:-4] + "cmb")
    return (f"{ord(value):04X}",) if len(value) == 1 else ()
