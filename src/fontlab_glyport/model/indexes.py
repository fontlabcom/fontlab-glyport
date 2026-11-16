# this_file: src/fontlab_glyport/model/indexes.py
"""Revision-scoped record indexes; constructing a proxy never scans its peers."""

from ..errors import StaleNativeObject
from .proxies import ProxySequence


class IndexedSequence(ProxySequence):
    def __init__(self, revision, records, make, keys=lambda info: (info.id,), **kw):
        super().__init__(lambda: list(self), **kw)
        self._revision, self._records, self._make, self._record_keys = (
            revision,
            records,
            make,
            keys,
        )
        self._version = object()
        self._validator = None
        self._native_lookup = None
        self._markers = {}

    def _refresh(self, *, force=False):
        version = self._revision()
        if not force and version == self._version:
            return
        records = tuple(self._records())
        self._infos = {item.id: item for item in records}
        self._order = tuple(self._infos)
        self._positions = {key: i for i, key in enumerate(self._order)}
        self._markers = {
            key: value for key, value in self._markers.items() if key in self._infos
        }
        self._reindex()
        self._version = version

    def _reindex(self):
        self._primary, self._aliases, self._unicodes = {}, {}, {}
        for item in self._infos.values():
            for code in getattr(item, "unicodes", ()):
                self._unicodes.setdefault(code.upper(), item.id)
        for item in self._infos.values():
            keys = self._record_keys(item)
            if keys:
                self._primary.setdefault(keys[0], item.id)
                for key in keys:
                    self._aliases.setdefault(key, item.id)

    def _validate(self, tokens):
        if self._validator is None:
            return
        marker, read = self._validator
        changed = False
        for token in tokens:
            if token not in self._infos:
                raise StaleNativeObject(token)
            version = marker(token)
            if self._markers.get(token, object()) != version:
                record = read(token)
                changed |= self._infos[token] != record
                self._infos[token] = record
                self._markers[token] = version
        if changed:
            self._reindex()

    def _validate_catalog(self, tokens):
        try:
            self._validate(tokens)
        except StaleNativeObject:
            if self._validator is None:
                raise
            # Native replacement can keep glyphsCount and package history fixed.
            # Rebuild once, then let a persistently stale host report its error.
            self._refresh(force=True)
            self._validate(self._order)

    def token_for_key(self, key, *, unicode=False):
        self._refresh()
        if self._native_lookup is not None:
            token = self._native_lookup(key, unicode=unicode)
            if token is not NotImplemented:
                if token is None:
                    return None
                if token not in self._infos:
                    self._refresh(force=True)
                self._validate_catalog((token,))
                return token

        def lookup():
            if unicode:
                return self._unicodes.get(key)
            return self._primary.get(key, self._aliases.get(key))

        token = lookup()
        if token is not None:
            previous = self._record_keys(self._infos[token])
            marker = self._markers.get(token)
            self._validate_catalog((token,))
            record = self._infos.get(token)
            current = () if record is None else self._record_keys(record)
            # A changed candidate may still match its old character alias after
            # a native name swap. Recover once on mismatch; unchanged alias hits
            # must inspect only this glyph, independent of the catalog size.
            if (
                previous != current
                or key not in current
                or not unicode
                and key != current[0]
                and marker != self._markers.get(token)
            ):
                self._validate_catalog(self._order)
            token = lookup()
        if token is None:
            # No package-wide history marker exists: misses must inspect each
            # glyph marker. Hits inspect one glyph, independent of font size.
            self._validate_catalog(self._order)
            token = lookup()
        return token

    def records(self):
        self._refresh()
        self._validate_catalog(self._order)
        return self._infos.values()

    def info(self, key):
        self._refresh()
        self._validate_catalog((key,))
        try:
            return self._infos[key]
        except KeyError:
            raise StaleNativeObject(key) from None

    def ordinal(self, key):
        self._refresh()
        try:
            return self._positions[key]
        except KeyError:
            raise StaleNativeObject(key) from None

    def __len__(self):
        self._refresh()
        return len(self._order)

    def __iter__(self):
        self._refresh()
        self._validate_catalog(self._order)
        return (self._make(key) for key in self._order)

    def __getitem__(self, key):
        self._refresh()
        if isinstance(key, slice):
            self._validate_catalog(self._order[key])
            return [self._make(token) for token in self._order[key]]
        if isinstance(key, int):
            self._validate_catalog((self._order[key],))
            return self._make(self._order[key])
        if not isinstance(key, str):
            raise TypeError("Expected an index, slice or string key")
        token = self.token_for_key(key)
        return None if token is None else self._make(token)

    def __contains__(self, value):
        if isinstance(value, str):
            return self[value] is not None
        self._refresh()
        token = (
            value.__dict__.get("_id", value.__dict__.get("_token"))
            if hasattr(value, "__dict__")
            else None
        )
        if token in self._infos:
            self._validate_catalog((token,))
        return token in self._infos and value is self._make(token)


class LayerSequence(IndexedSequence):
    """Keep direct master lookups lazy; enumerate auxiliaries only when needed."""

    def __init__(self, *args, masters, **kwargs):
        self._masters = masters
        super().__init__(*args, **kwargs)

    def __getitem__(self, key):
        masters = self._masters()
        if isinstance(key, int) and 0 <= key < len(masters):
            return self._make(masters[key].id)
        if isinstance(key, str) and any(m.id == key for m in masters):
            return self._make(key)
        return super().__getitem__(key)
