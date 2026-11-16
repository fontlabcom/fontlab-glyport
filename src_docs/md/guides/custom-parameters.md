---
this_file: src_docs/md/guides/custom-parameters.md
---
# Ordered custom parameters

This example exercises owned offline data. It demonstrates collection behaviour;
it does not qualify FontLab persistence or execute a filter.

```python
from fly.gp.model import GSCustomParameter, Model
from fly.gp.model.fake_backend import FakeBackend

font = Model(FakeBackend()).font
first = GSCustomParameter("Filter", "First filter")
second = GSCustomParameter("Filter", "Second filter")
font.customParameters.extend([first, second])
assert font.customParameters[0] is first
assert font.customParameters["Filter"] == "First filter"
first.active = False
assert "Filter" in font.customParameters
assert font.customParameters["Filter"] == "Second filter"
font.customParameters["Filter"] = "Changed inactive filter"
assert first.value == "Changed inactive filter" and not first.active
assert font.customParameters["Filter"] == "Second filter"
font.customParameters["Filter"] = None
assert list(font.customParameters) == [second]
assert first.parent is None
second.name = "Renamed filter"
assert font.customParameters["Filter"] is None
assert font.customParameters["Renamed filter"] == "Second filter"
```

A name read selects the first active duplicate. A name write, name deletion or
`remove(parameter)` acts on the first matching object, including an inactive one.
Use integer indices when the intended operation is positional. Removing an object
detaches it; subsequent detached edits do not change the stored collection.

Legacy lib values import without modifying unrelated data. After import, ordered
records preserve duplicate names and active flags across reconstructed Python
models. External additions through flat glyphsLib-compatible keys are retained.
Conflicting external edits of an existing mirror raise an error before a later
write can overwrite them. Full native save/reopen remains an acceptance gate.

The Arabic presentation setting requires typed numeric validation and resolver
postprocessing in addition to this collection. Those stages remain pending.

For the separately packaged read-only corpus-ranking driver, set
`GLYPORT_ORIGINAL_CORPUS` to the retained original corpus and
`GLYPORT_GLYPHS_WRAPPER` to its pinned upstream Python wrapper. The driver parses
files; it does not execute original scripts. Corpus configuration is unrelated
to the owned offline example above.
