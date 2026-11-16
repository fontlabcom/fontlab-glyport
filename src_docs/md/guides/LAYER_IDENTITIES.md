---
this_file: src_docs/md/guides/LAYER_IDENTITIES.md
---

# Keep layer identity separate from its name

Two foreground layers can share a display name without sharing storage. Glyport
keeps the declared master slots first, in font-master order, then every other
valid stored foreground in native order. Mask and service records are excluded
from that latter group. A missing master retains its existing pending slot;
reading the collection creates no native layer or Undo entry.
Without declared masters, the existing empty-collection behavior remains.

FontLab's `isMasterLayer` is derived from names, including interpolation/bracket
names. It does not uniquely identify a declared master slot. The native
case-sensitive `findLayer(name)` selects the last matching stored identity. Glyport
uses that same finder for each declared slot and gives other same-name records
their own auxiliary tokens. It does not invent persistent native metadata.

The public Glyphs-compatible `isMasterLayer` describes a declared slot:
`layer.layerId == layer.associatedMasterId`. A native master-like record outside
those slots is represented as an auxiliary. Imported auxiliaries without an
explicit retained association keep the first-master fallback; association is
separate from the displayed name and native interpolation semantics.

## Inspect every identity

These read-only helpers take a glyph already resolved by the caller. They do not
choose a font, change selection, open a window or edit a document. The standalone
checks run the exact helpers against owned primitives through the actual
FontLabBackend/Model/proxy code; that is separate from native host acceptance.

```python
def layer_rows(glyph) -> list[dict[str, object]]:
    return [
        {"id": layer.layerId, "master": layer.associatedMasterId,
         "name": layer.name, "is_master": layer.isMasterLayer,
         "width": layer.width}
        for layer in glyph.layers
    ]
```

For example, distinct stored Regular/Bold duplicates can produce four rows
with names `Regular, Bold, Regular, Bold`. The first two are declared slots;
the last two have their own IDs. Never key a preservation snapshot by name alone.

## Select declared masters deliberately

```python
def master_layers(glyph) -> list:
    return [layer for layer in glyph.layers if layer.isMasterLayer]
```

This intentionally selects declared slots, including a pending missing master.
A zero-width pending slot is not proof that a real empty layer exists. The
collection is therefore not a literal stored-only iterator for an original
Transform workflow. That workflow needs its own qualified stored-layer projection,
occurrence order and complete shape/component/image/anchor/PS/TT payload contract.

## Find all layers with a display name

```python
def named_layers(glyph, name: str) -> list:
    return [layer for layer in glyph.layers if layer.name == name]
```

The result may contain several objects. `glyph.layers["Regular"]` is not an
existing name alias: general string lookup uses exact layer IDs. Integer master
ordinals and declared master IDs retain their lazy direct lookup. Other indices,
slices and auxiliary IDs use the complete catalogue.

## Resolve a retained session ID

```python
def layer_by_id(glyph, layer_id: str):
    return glyph.layers[layer_id]
```

Repeated lookup returns the same proxy while that identity remains live.
Reordering or renaming an auxiliary does not merge it with another same-name
record. If it becomes the finder-selected master identity, its old auxiliary
handle is retired instead of silently aliasing the master slot. Removal also
retires the old auxiliary/background handles. These are session tokens, not a
new persistent UUID format.

The backend captures the glyph history marker when a layer handle is exposed.
On a later notified history change it rebinds retained identities to replacement
wrappers before reading. Unnotified native changes have no general observable
history marker. Do not retry an edit blindly after a stale-handle error.

## Editing and native acceptance

Owned checks verify that each duplicate-layer width write changes only its exact
target and that automatic-layer writes still refuse before history. Enumeration
does not qualify every interpolating/generated layer for writing. Existing
automatic/dependant, shared-owner, pending-update and history-scope protections
remain applicable.

Actual imported layer roles/order, complete font/cache/date/lifetime preservation,
Apply/Undo/Redo/save/reopen and all four owner-font workflows still need the native
owned-fixture protocol. No API declaration or standalone model test supplies
that proof. See [Compatibility](COMPATIBILITY.md) and the workspace acceptance
ledger before treating a script as native-complete.
