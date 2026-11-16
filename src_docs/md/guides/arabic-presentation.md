---
this_file: src_docs/md/guides/arabic-presentation.md
---
# Arabic presentation-form encodings

These examples use owned offline models. They test source behaviour and do not
open or modify a FontLab document. The maintained GlyphData supplies legacy
presentation codes; native persistence/history and complete caller workflows
still require qualification.

## Enable and refresh

```python
from fly.gp.model import GSCustomParameter, GSGlyph, Model
from fly.gp.model.fake_backend import FakeBackend

KEY = "Use Arabic Presentation Form Unicodes"
font = Model(FakeBackend()).font
glyph = font.glyphs.append(GSGlyph("alef-ar"))
font.customParameters[KEY] = True
glyph.updateGlyphInfo(changeName=False)
assert glyph.name == "alef-ar"
assert glyph.unicodes == ["0627", "FE8D"]
```

The exact spaced key matters. The compact spelling is a different parameter.
The parent font supplies the setting; a master setting does not enable it.

## First active duplicate

```python
font.customParameters[KEY] = False
second = GSCustomParameter(KEY, True)
font.customParameters.append(second)
glyph.updateGlyphInfo(changeName=False)
assert glyph.unicodes == ["0627"]
font.customParameters[0].active = False
glyph.updateGlyphInfo(changeName=False)
assert glyph.unicodes == ["0627", "FE8D"]
```

Name assignment targets the first object, including an inactive one. Effective
lookup selects the first active value. Refresh rebuilds the encoding list; it
removes the earlier presentation addition when the setting becomes disabled.

## Typed values on macOS

```python
from fly.gp.model.parameter_numbers import normalize
assert normalize("YES", locale_name="en_US") == 0
assert normalize("true", locale_name="en_US") == 0
assert normalize("0,5", locale_name="de_DE") == 0.5
assert normalize("0.5junk", locale_name="en_US") == float(2**63)
assert normalize("1.0e-46", locale_name="en_US") == 0.0
assert normalize(1e-46) == 1e-46
```

String conversion uses real NSString/NSNumberFormatter behaviour, including the
current locale and float32 rounding. A failed decimal parse uses the upstream
nonzero sentinel. Raw Python truthiness would get YES/true and tiny values wrong.
The explicit locale above belongs to a temporary formatter; preferences remain
unchanged. Normal parameter writes use the process locale and cached formatter.
Numeric bool/int/float values retain precision, and typed object None becomes
False. Assigning None by parameter name instead removes the first matching object.

Non-macOS string conversion and arbitrary object/container conversion explicitly
raise UnsupportedCapability pending qualification. Numeric values remain usable.

## Canonical metadata and stored script

```python
font = Model(FakeBackend()).font
alias = font.glyphs.append(GSGlyph("ownedArabicAlias"))
alias.unicode = "0627"
alias.storeScript = True
alias.script = "latin"
font.customParameters[KEY] = True
alias.updateGlyphInfo(changeName=False)
assert alias.name == "ownedArabicAlias" and alias.script == "latin"
assert alias.unicodes == ["0627", "FE8D"]
```

The presentation stage tests the resolved record's script and canonical name,
then reads direct unicodeLegacy or the raw canonical .isol record. An empty
non-nil legacy blocks fallback. Additions preserve order and deduplicate; generic
constructed suffixes clear inherited legacy. Stored metadata overlays run later.
The preceding additional-Unicode stage retains its own gates and semantics.

ROS replacement, custom managers, complete suffix synthesis and native name
collision handling remain open; combined equivalence is not claimed. Requested
shipped ROS maps now refuse before presentation because their proprietary data
is unavailable. A native collision can clear encodings even with changeName=False.
The public unicodeLegacy snapshot and its distinct global/local metadata paths
are described in [Legacy encodings and ROS](legacy-and-ros.md).
