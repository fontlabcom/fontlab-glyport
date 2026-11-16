---
this_file: src_docs/md/guides/unicode-lookup.md
---

# Global Unicode Glyph Info

The private candidate implements `Glyphs.glyphInfoForUnicode(String, font=None)`
and integer dispatch from `glyphInfoForName`. It returns the existing read-only
`GSGlyphInfo` snapshot or `None`. Lookup indexes maintained public GlyphData
records in file order, inserting each primary encoding and then its legacy
encoding. Later records overwrite earlier keys. The separate `unicode` and
`unicodeLegacy` fields retain their exact stored values; a legacy lookup does
not assign that key to the primary field.

The retained Glyphs4 base parser at `002152e4` inserts legacy encodings into the
same dictionary as primary encodings; loader `0022fffc` passes it to the global
manager. This corrects the earlier primary-only description. Public glyphsLib
6.16.2 data adds 730 legacy keys to 71,401 primary keys, for 72,131 combined keys.
The duplicate legacy key `0000` selects the later `NULL` record. This source
correction awaits fresh ordinary artifacts, consumer and native qualification;
previous artifact reports describe the earlier implementation.

The executable wrapper's keyword is `String`, with capital S. The documentation
label `Unicode` is not a keyword alias. These examples use an owned application
fixture outside FontLab; they do not activate a native application or synthetic
`GlyphsApp` module.

```python
from types import SimpleNamespace
from fly.gp.glyphsapp import GSApplication

app = GSApplication(SimpleNamespace(font=None), object(), {}, None, lambda *args: None)
assert app.glyphInfoForUnicode(65).name == "A"
assert app.glyphInfoForUnicode(String="004a").name == "J"
assert app.glyphInfoForUnicode("00C1").name == "Aacute"
assert [part.name for part in app.glyphInfoForUnicode("00C1").components] == [
    "A", "acutecomb"]
info = app.glyphInfoForUnicode("FE8D")
assert (info.name, info.unicode, info.unicodeLegacy) == ("alef-ar.isol", None, "FE8D")
assert app.glyphInfoForUnicode("FE80").name == "hamza-ar.isol"
assert app.glyphInfoForUnicode("0000").name == "NULL"
```

Global lookup never consults the active font, glyph state, ROS, presentation
parameters or stored metadata. An explicit non-None `font` on the Unicode method
refuses with `Glyphs.glyphInfoForUnicode.localData`: a font-local manager remains
unimplemented. The name method first dispatches integers to the Unicode method,
discarding its `font` argument exactly as the audited Python wrapper does.

```python
from types import SimpleNamespace
from fly.gp.errors import UnsupportedCapability
from fly.gp.glyphsapp import GSApplication

class UnreadableFont:
    def __getattribute__(self, name):
        raise AssertionError("Global lookup must not read the active font")

font = UnreadableFont()
app = GSApplication(SimpleNamespace(font=font), object(), {}, None, lambda *args: None)
assert app.glyphInfoForName(65, font=font).name == "A"
assert app.glyphInfoForUnicode("0041", font=None).name == "A"
try:
    app.glyphInfoForUnicode("0041", font=font)
except UnsupportedCapability as error:
    assert error.capability == "Glyphs.glyphInfoForUnicode.localData"
else:
    raise AssertionError("Explicit local Unicode lookup must refuse")
```

## Preserve lookup spelling and synthesis

Nil or input shorter than three UTF-16 code units returns `None` before lookup.
Otherwise the uppercased original text is used as the exact combined index key.
There is no trimming, zero-padding or scalar canonicalization. Integer inputs,
including bool and integer subclasses, first use the wrapper's exact `%04X`
formatting. Formatting width is a minimum, not a range check.

On an index miss, the retained manager synthesizes metadata using the uppercase
text for its name and encoding. The parsed 32-bit value selects the `uni` or `u`
prefix and classification; it does not reformat the text. A synthesized encoding
is retained only for uppercase text lengths1–7. Longer text may yield a record
whose `unicode` is `None`.

```python
from types import SimpleNamespace
from fly.gp.glyphsapp import GSApplication

app = GSApplication(SimpleNamespace(font=None), object(), {}, None, lambda *args: None)
for text, name, code in [
    ("041", "uni041", "041"),
    ("000041", "uni000041", "000041"),
    ("00000041", "uni00000041", None),
    ("0FE8D", "uni0FE8D", "0FE8D"),
]:
    info = app.glyphInfoForUnicode(text)
    assert (info.name, info.unicode, info.unicodeLegacy) == (name, code, None)
assert app.glyphInfoForName("alef-ar.isol").unicodeLegacy == "FE8D"
```

The historical hex helper skips ASCII spaces and minus signs, treats any minus
as final negation, adds nibbles with shift counts modulo32 and wraps sums to32bits.
Invalid text returns its sentinel, which the manager rejects. Signed high-bit
values take the BMP naming route; `10FFFE` is accepted and `10FFFF` is rejected.
This reproduces source behavior rather than applying a strict Unicode-scalar
validator. Reading these snapshots does not assign malformed encodings to fonts.

```python
from types import SimpleNamespace
from fly.gp.glyphsapp import GSApplication

app = GSApplication(SimpleNamespace(font=None), object(), {}, None, lambda *args: None)
for text in ("--41", " 4 1 ", "   "):
    info = app.glyphInfoForUnicode(text)
    assert info.name == "uni" + text and info.unicode == text
for text in ("80000000", "100000000", "FFFFFFFFF"):
    info = app.glyphInfoForUnicode(text)
    assert info.name == "uni" + text and info.unicode is None
assert app.glyphInfoForUnicode("10FFFE").name == "u10FFFE"
assert app.glyphInfoForUnicode("10FFFF") is None
assert app.glyphInfoForUnicode("U+0041") is None
```

Synthesized case is0, subCategory and unicodeLegacy are None. PUA uses category
`Private Use` with no script. Otherwise the audited historical Han ranges yield
script `han` and category `Letter`; other synthesized records use `Other`.
These are specific source ranges, not current Unicode Script inference. Direct
maintained records retain their own metadata and supported NFD components.

```python
from types import SimpleNamespace
from fly.gp.glyphsapp import GSApplication

app = GSApplication(SimpleNamespace(font=None), object(), {}, None, lambda *args: None)
assert app.glyphInfoForUnicode("00ﬀ").name == "ydieresis"  # Uppercase expands to00FF.
assert app.glyphInfoForUnicode("0ﬀ") is None  # Minimum length checked before expansion.
info = app.glyphInfoForUnicode("0009FCC")  # Seven-digit spelling forces synthesis.
assert (info.script, info.category) == ("han", "Letter")
assert app.glyphInfoForUnicode("0009FCD").category == "Other"
assert app.glyphInfoForUnicode("00F8FF").category == "Private Use"
```

## Explicit boundaries

Only built-in strings, None and wrapper-dispatched integers are supported.
Other bridge types, including string subclasses, refuse explicitly without broad
string/integer coercion. Non-None font refusal precedes payload checks. An actual
malformed UTF-16 string can make Foundation's native UTF8String return NULL;
the retained helper dereferences that pointer unchecked. This package refuses
that unsafe domain. Hex text `D800` is a distinct, supported synthesis input.

```python
from types import SimpleNamespace
from fly.gp.errors import UnsupportedCapability
from fly.gp.glyphsapp import GSApplication

app = GSApplication(SimpleNamespace(font=None), object(), {}, None, lambda *args: None)
for value, capability in [([], "inputType"), ("\ud80000", "UTF16")]:
    try:
        app.glyphInfoForUnicode(value)
    except UnsupportedCapability as error:
        assert error.capability == "Glyphs.glyphInfoForUnicode." + capability
    else:
        raise AssertionError("Unqualified or unsafe bridge input must refuse")
assert app.glyphInfoForUnicode("D800").unicode == "D800"
```

Standalone macOS27.2 Foundation calibration covered all1,112,064valid scalars:
Python3.11 uppercase differs for55, but only non-ASCII `ﬀ` enters the accepted
parser alphabet, identically in both. This scopes the measured casing boundary;
it does not qualify other Foundation versions or arbitrary PyObjC conversion.
Maintained GlyphData is not proof of proprietary database identity/completeness.
Custom/global overlays, font-local managers, remaining Glyph Info fields and
native workflows remain open. See [legacy/ROS](legacy-and-ros.md) for the separate
font-local postprocessing boundary.
