# this_file: src/fontlab_glyport/model/public_info_index.py
"""Lazy manager-owned public records, with source gaps kept explicit."""

from .info_records import GlyphInfoIndex


class PublicInfoIndex(GlyphInfoIndex):
    """Keep this dataset's canonical raw objects through other-manager lookups."""

    def __init__(self, data):
        super().__init__()
        from ..glyphsapp.glyph_info import _name_index
        from .glyph_metadata import _unicode_index

        self.data = data
        self._name_attributes = _name_index(data)
        self._code_attributes = _unicode_index(data)
        self._by_attributes = {}

    def _record_for(self, attributes):
        if attributes is None:
            return None
        key = id(attributes)
        if key not in self._by_attributes:
            from ..glyphsapp.glyph_info import _database_glyph

            record = _database_glyph(
                attributes["name"],
                attributes=attributes,
                _data_override=self.data,
                _owned=True,
            )[0]
            # Public NFD decomposition is not the proprietary metadata recipe.
            record.unicodes = (record.unicode,) if record.unicode else ()
            record._component_names = None
            record._component_records = None
            record._unavailable_fields |= {"components"}
            self._by_attributes[key] = record
            self.records.append(record)
        return self._by_attributes[key]

    def prepare_custom_merge(self) -> None:
        """Materialize source indexes once so removals cannot resurrect lazy keys."""
        for name, attributes in self._name_attributes.items():
            self.names[name] = self._record_for(attributes)
        for code, attributes in self._code_attributes.items():
            self.unicodes[code] = self._record_for(attributes)
        if self._name_attributes or self._code_attributes:
            self.records[:] = [
                self._record_for(row) for row in self.data.names.values()
            ]
        # Replace these adapter maps; never clear cached/dependency dictionaries.
        self._name_attributes = {}
        self._code_attributes = {}

    def _own_name(self, name):
        return self.names.get(name) or self._record_for(self._name_attributes.get(name))

    def _own_unicode(self, code):
        return self.unicodes.get(code) or self._record_for(
            self._code_attributes.get(code)
        )
