---
this_file: src_docs/md/guides/production-metadata.md
---

# Stored production metadata

`GSGlyphInfo.productionName` preserves a known stored value: None, empty text,
or explicit text, including a value equal to the nice name. The retained
Glyphs4 getter reads that field directly. The adjacent public API prose is not
an authority for changing a measured equal-name result to None.

Global exact names and aliases fill a nil stored field through the audited
manager helper. Empty text is present and bypasses that fill. Direct Unicode
queries do not fill it. A returned raw handle can observe later name access;
a copy keeps the value at copy time. For a reviewed Glyport session with
`Glyphs` imported from `GlyphsApp`:

```python
from copy import copy
raw = Glyphs.glyphInfoForUnicode("0041")
before = copy(raw)
old_value = before.productionName
named = Glyphs.glyphInfoForName("A")
assert named.productionName == "A"
assert raw.productionName == "A"
assert before.productionName == old_value
```

The initial value can already be filled by earlier lookups. A uni/u-style
single-record name is a copy of raw Unicode metadata; a bare character uses
raw Unicode access. Synthesized direct Unicode metadata explicitly stores its
constructed name. The helper's export-name normalization is separate from the
stored getter: it does not rewrite an existing raw production field.

The maintained data adapter reconstructs the retained parser's single name
index in record order: name, production unless it starts with lowercase `uni`,
then alternate names normalized by the maintained public loader. Later entries win, including collisions
with earlier primary names. Exact stored uni-looking names still preempt
Unicode decoding; an excluded production alias alone does not.

Model results share the field until a native copy branch applies: private-use
rename, additional Unicode, Arabic presentation or an enabled stored metadata
flag. An equal stored overlay still copies. Arabic additional-Unicode lookup
can fill the isolated record; presentation lookup stays raw. Generic suffix
production appends the original suffix tokens to helper output; global base
lookup and font-base resolution keep different fill behavior.

This qualifies represented public records and owned source controls. Public
XML is a versioned subset, not proprietary GlyphData completeness. Complex
uni/suffix/ligature and special synthesis, custom/global/font-local managers,
remaining resource/version branches and complete original workflows remain
open. Library-constructed classification alone cannot establish production;
that getter refuses with `GSGlyphInfo.productionName.source` rather than invent
None or a sanitized export name. Glyph production setters/storage flags and
`Glyphs.productionGlyphName` are separate contracts and are not added here.
Source tests do not establish FontLab history, persistence or native acceptance.
