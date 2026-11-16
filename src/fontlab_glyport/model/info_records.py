# this_file: src/fontlab_glyport/model/info_records.py
"""Manager-owned raw records and indexes, independent of global cache eviction.

These internal objects implement retained Glyphs4 raw index/copy contracts. They
are not a public manager, loader, or substitute for unavailable resource data.
"""

from types import SimpleNamespace

from .production_metadata import StoredProduction, _utf16_length


def new_record(name: str | None = None) -> SimpleNamespace:
    """Allocate known fresh defaults; never use these for unknown source fields."""
    return SimpleNamespace(
        name=name,
        unicode=None,
        unicodes=(),
        unicodeLegacy=None,
        category=None,
        subCategory=None,
        script=None,
        case=0,
        group=None,
        groupIdx=0,
        direction=0,
        desc=None,
        anchors=None,
        marks=None,
        sortName=None,
        sortNameKeep=None,
        altNames=None,
        mirror=None,
        deprecated=False,
        unicharString=None,
        baseString=None,
        _locked=False,
        _component_names=None,
        _component_records=None,
        _unavailable_fields=frozenset(),
        _production_state=StoredProduction(),
    )


def add_unicode(record: SimpleNamespace, code: str | None) -> None:
    """Retain the ordered set and first code; mirror addUnicode's UTF16 bound."""
    if code is None or not 0 < _utf16_length(code) < 8:
        return
    if code not in record.unicodes:
        record.unicodes += (code,)
        record.unicode = record.unicodes[0]


def copy_record(record: SimpleNamespace) -> SimpleNamespace:
    """Copy containers and stored production, retaining shallow component objects."""
    values = vars(record).copy()
    values.pop("_public_view", None)
    for field in (
        "anchors",
        "marks",
        "altNames",
        "_component_names",
        "_component_records",
    ):
        if values.get(field) is not None:
            values[field] = list(values[field])
    stored = values.get("_production_state")
    if stored is not None:
        values["_production_state"] = StoredProduction(stored.value)
    values.update(_locked=False, unicharString=None)
    return SimpleNamespace(**values)


class GlyphInfoIndex:
    """One generation of raw indexes and strongly retained canonical records."""

    def __init__(self, *, shared: "GlyphInfoIndex | None" = None) -> None:
        self.shared = shared
        self.records: list[SimpleNamespace] = []
        self.names: dict[str, SimpleNamespace] = {}
        self.unicodes: dict[str, SimpleNamespace] = {}

    def prepare_custom_merge(self) -> None:
        """Owned indexes are already concrete; lazy base indexes override this."""

    def append(self, record: SimpleNamespace) -> None:
        """Bundled parser order: name, non-uni production, aliases, codes, legacy."""
        self.records.append(record)
        self.names[record.name] = record
        production = record._production_state.value
        if production is not None and not production.startswith("uni"):
            self.names[production] = record
        for alias in record.altNames or ():
            self.names[alias] = record
        for code in record.unicodes:
            self.unicodes[code] = record
        if record.unicodeLegacy is not None:
            self.unicodes[record.unicodeLegacy] = record

    def _own_name(self, name):
        return self.names.get(name)

    def _own_unicode(self, code):
        return self.unicodes.get(code)

    def raw_name(self, name: str | None) -> SimpleNamespace | None:
        """Return the exact local object; only a local miss consults shared."""
        result = self._own_name(name)
        if result is None and self.shared is not None:
            return self.shared._own_name(name)
        return result

    def raw_unicode(self, code: str | None) -> SimpleNamespace | None:
        """Return raw indexed data without synthesis, fill, normalization or copy."""
        result = self._own_unicode(code)
        if result is None and self.shared is not None:
            return self.shared._own_unicode(code)
        return result

    def raw_unicodes(self, codes: list[str]) -> SimpleNamespace | None:
        """Skip unrepresented tokens; resolved plural lookup is a separate route."""
        for code in codes:
            record = self.raw_unicode(code)
            if record is not None:
                return record
        return None
