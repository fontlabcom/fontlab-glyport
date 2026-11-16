---
this_file: src_docs/md/guides/legacy-and-ros.md
---

# Legacy encodings and ROS metadata

`GSGlyphInfo.unicodeLegacy` reads a separate legacy encoding from maintained
GlyphData. It never replaces `unicode`. The package exposes an owned read-only
snapshot; native Glyph Info has a setter which this facade does not emulate.

```python
from types import SimpleNamespace
from fly.gp.glyphsapp.application import GSApplication

app = GSApplication(SimpleNamespace(font=None), object(), {}, None, lambda *args: None)
info = app.glyphInfoForName("alef-ar.isol")
assert info.name == "alef-ar.isol"
assert info.unicode is None
assert info.unicodeLegacy == "FE8D"
alias = app.glyphInfoForName("aleffinalarabic")
assert alias.name == "alef-ar.fina" and alias.unicodeLegacy == "FE8E"
assert app.glyphInfoForName("alef-ar").unicodeLegacy is None
```

Global lookup ignores the active font, its parameters and stored overrides.
Explicit non-None `font` lookup remains unsupported for name strings. The new
[global Unicode lookup](unicode-lookup.md) indexes primary then legacy values
for each public record in file order, with last-write precedence. Legacy lookup
preserves the separate fields: `FE8D` selects `alef-ar.isol`, whose `unicode` is
None and `unicodeLegacy` is `FE8D`. Integer name lookup
dispatches to that method before dropping its font argument, as in the wrapper.

The retained base parser constructs this combined index. The earlier
primary-only description was incorrect; historical artifact evidence remains
unchanged and does not qualify this source correction. Public data is not proof
of proprietary database completeness, and font-local custom loaders remain open.

Direct construction from a package `GSGlyph` reads the new legacy field through
the owned metadata resolver. Existing name, primary encoding, script and case
snapshot behavior is preserved. A nil resolved record yields no legacy encoding;
it does not infer one from the glyph name or primary encoding. Generic derived
suffixes clear inherited legacy metadata.

```python
from fly.gp.model import GSGlyph
from fly.gp.glyphsapp.glyph_info import GSGlyphInfo

glyph = GSGlyph("alef-ar.isol")
info = GSGlyphInfo(glyph)
assert info.unicodeLegacy == "FE8D" and glyph.unicodes == []
glyph.name = "alef-ar.isol.owned"
assert info.unicodeLegacy == "FE8D"  # Existing snapshot stays unchanged.
assert GSGlyphInfo(glyph).unicodeLegacy is None
```

ROS processing in the audited upstream shared manager replaces the complete
ordered Unicode set by the resolved metadata name, after additional encodings
and before Arabic presentation processing. It depends on five proprietary
MapFiles. They are not bundled with Glyport, and Adobe CMaps or GlyphData are
not equivalent substitutes. Requests for Adobe-CNS1, Adobe-GB1, Adobe-Japan1,
Adobe-KR or Adobe-Korea1 therefore raise `GSGlyphInfo.ROS.mappingData` before
metadata writes, even if the requested glyph might be absent from that map.

```python
from fly.gp.errors import UnsupportedCapability
from fly.gp.model import Model
from fly.gp.model.fake_backend import FakeBackend

font = Model(FakeBackend()).font
glyph = font.glyphs["A"]
before = (glyph.name, glyph.unicodes)
font.customParameters["ROS"] = "Adobe-Japan1-7"
try:
    glyph.updateGlyphInfo(changeName=False)
except UnsupportedCapability as error:
    assert error.capability == "GSGlyphInfo.ROS.mappingData"
else:
    raise AssertionError("Missing ROS data must refuse")
assert (glyph.name, glyph.unicodes) == before
```

The guard recognizes the shared manager's exact strings: split on `-`; only if
the count differs from three, retry using comma plus one space. The first two
pieces identify the map; the supplement is ignored without numeric validation.
Case and whitespace are preserved. Nil, malformed strings and names absent from
the audited shipped resources leave the preceding metadata unchanged. This is
the shipped shared-manager boundary, not arbitrary custom-manager equivalence.
Nontext values require Objective-C description conversion and explicitly raise
`GSGlyphInfo.ROS.value` until that conversion is qualified. Normal first-active
parameter selection applies; inactive or shadowed ROS records are not selected.

No native applications are called by these examples. Full ROS mapping, custom
managers, native collision handling, Undo/Redo and saved/reopened workflows
remain unqualified. See [Arabic presentation](arabic-presentation.md) for the
following stage and its separate platform boundaries.
