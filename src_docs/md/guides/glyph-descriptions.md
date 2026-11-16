---
this_file: src_docs/md/guides/glyph-descriptions.md
---
# Read stored glyph descriptions

`GSGlyphInfo.desc` returns the description stored on the selected metadata record.
It preserves `None`, empty text and Unicode text. It does not manufacture a
description from a glyph name or Python's Unicode database.

In FontLab, access the public facade on the GUI thread. To share an activated
session, call `gp.activate()` after `from fly import gp` and before the public
import below. Outside FontLab, first call `import fly.gp.GlyphsApp as gs;
gs.use_backend(backend, profile="glyphs4")` with an explicit backend, before
accessing `Glyphs`. See [ordinary imports and backend binding](https://github.com/fontlabcom/fontlab-glyport/blob/main/src_docs/md/glyphs-cocoa-and-vanilla.md#ordinary-glyphs-imports).

Query the global metadata explicitly:

```python
from fly.gp.GlyphsApp import Glyphs

info = Glyphs.glyphInfoForName("A")
by_unicode = Glyphs.glyphInfoForUnicode("0041")
assert by_unicode.desc == info.desc
if info.desc:
    print(info.desc)
```

A suffix or compound can retain its selected seed's description. Component
descriptions are not joined. Exact whole-name records can preempt composition,
and Indic seed replacement can select a different record. These rules follow the
existing lookup pipeline; a description read does not resolve another record.

```python
base = Glyphs.glyphInfoForName("A")
alternate = Glyphs.glyphInfoForName("A.alt")
assert alternate.desc == base.desc
```

The description is read-only:

```python
from fly.gp.errors import UnsupportedCapability

try:
    info.desc = "Replacement"
except UnsupportedCapability as error:
    assert error.capability == "GSGlyphInfo.desc"
else:
    raise AssertionError("The stored description must remain read-only")
```

The current provider is the versioned public GlyphData subset. A known parsed
record without a description has `None`; an external metadata object that does
not establish the field raises `GSGlyphInfo.desc.source`. Public subset results
do not establish proprietary database completeness or every Glyphs version.

The retained wrapper and native stored getter agree with the documented
[GSGlyphInfo property](https://docu.glyphsapp.com/Core/GlyphsCore/GSGlyphInfo/).
Current source checks cover selected-record behavior, including nullable text,
aliases, Unicode, suffixes, compounds, copies and model snapshots. Matching
committed artifacts, Echopy producer provenance and ordinary consumers need their
separate qualification.

`GSGlyph.glyphInfo` selects its font/document manager. An explicit font also
selects that manager for application lookup:

```python
font = Glyphs.font
if font is not None:
    selected = Glyphs.glyphInfoForName("A", font=font)
    if selected is not None:
        print(selected.desc)
```

Manager hits retain canonical record views. The explicit `GSGlyphInfo(glyph)`
constructor remains a frozen glyph snapshot; it is a different operation.
Complete local initialization/reload, private resources, original scripts and
native workflows remain open. Source checks do not qualify UI effects, FontLab
history or saved/reopened artifacts.
