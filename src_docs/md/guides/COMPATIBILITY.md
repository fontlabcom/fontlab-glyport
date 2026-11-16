---
this_file: src_docs/md/guides/COMPATIBILITY.md
---
# Compatibility protocols and historical implementation notes

<a id="issue-205--direct-public-api-and-live-outlines"></a>

## Issue 205 — direct public API and live outlines

| Public member | Implementation and evidence |
| --- | --- |
| `fontlab_glyport.GlyphsApp` | Lazy public package forwarding every name in `make_glyphsapp_module().__all__`; the package's `__all__` is identical. `use_backend(backend, profile="glyphs4")` binds an explicit backend before access. Missing host raises `HostUnavailable`. `dir()` is host-free; `unbind()` closes and forgets an independent binding. |
| `GlyphsApp.plugins` | Seven SDK base classes: ReporterPlugin, GeneralPlugin, FilterWithDialog, FilterWithoutDialog, PalettePlugin, SelectTool, FileFormatPlugin. Active bootstrap identities are reused; the existing native session binds classes once; without a bound backend the original classes import without a plugin environment. |
| `GSLayer.removeOverlap(checkSelection=False)` | Both backends use existing skia-pathops winding-aware simplification in Python; the optional `boolean` extra is required. Closed selected contours are combined, open contours and components retained. Styled closed paths are refused by the existing boolean implementation. |
| `GSLayer.decomposeComponents()` | Both backends expand recursively after cycle/reference preflight. FakeBackend composes affine transforms in Python. Native decomposition reuses `flShape.ejectTo()` and `flLayer.removeShape()`/`insertShape()`, preserving explicit reference layers through the existing component route. |
| `GSLayer.correctPathDirection()` | Python fontTools analytic area, containment and contour reversal; outer contours counterclockwise, nested counters clockwise. Open paths and components retained. Containment is an informed guess for intersecting/touching contours; Glyphs' additional start-point/order normalization is not reproduced. |
| `GSLayer.addNodesAtExtremes(force=False, checkSelection=False)` | Python fontTools derivative roots and exact cubic/quadratic splitting; implied quadratic points supported. Selection limits processing to fully selected segments. No grid rounding or distortion is performed, so `force` has the same exact result. |
| `GSLayer.getPen()` / `getPointPen()` | One dual-protocol writing pen, using fontTools SegmentToPointPen. Each completed contour/component appends through the backend's existing collection API; node names and smoothness retained. A pen owns one nested Undo step across contours/components; finish with `doneDrawing()`/`close()` or a context manager. Caller-owned Undo groups still nest. |
| `GSLayer.draw(pen, contours=True, components=True)` | Backend snapshots emitted through fontTools PointToSegmentPen. No mutation; component transforms retained. FontTools outline protocol only: RoboFab-specific width/note/anchor/doneDrawing hooks are not emitted. |
| `GSLayer.drawPoints(pointPen, contours=True, components=True)` | Point protocol with node names, smoothness, cubic/quadratic types, open/closed contours and affine components. Pen identifiers have no native counterpart and are not retained. |
| `GSFont.save(path=None, formatVersion=None, makeCopy=False)` | Qualified `fontpr.call("save_font", font_id=package.fgId, path=absolute_path, overwrite=True)` for `.vfj`/`.vfc`, verified with `is_file()`. No current-font requirement; pending changes are refused. Copies restore the original recorded filepath; non-None formatVersion is unsupported. Export UFO/other formats separately. FakeBackend writes first-master UFO geometry/metrics/Unicode; it is an offline test serializer, not a complete multi-master or font-metadata exporter. |
| `GSFont.close(ignoreChanges=...)` | Native `flPackage.close(save=False)`. Omitted/false permission refuses unsaved or unknown dirty state (`flPackage.getProperty("__has_history_changes")`); explicitly pass `ignoreChanges=True` to discard edits. Pending Undo work is refused; descendants become stale. FakeBackend invalidates its document. |
| `GSFont.filepath` / `familyName` | Native `flPackage.fileName` reader and writable FontGate `fgFont.info.familyName`. No new `fontName` or localized `familyNames` facade. |

### Public API review additions — 2026-11-03

| Public member | Support and proving tests |
| --- | --- |
| SDK scalar constants and aliases | SDK names/values audited, including `GSRTL=RTL=2`, `GSBIDI=BIDI=1`, node types/numeric codes, metrics, hints, export formats, direction, annotation, style and property keys. `GSGuideLine is GSGuide`. Constants do not promise corresponding operations. `test_all_overlapping_sdk_constants_match` parses the authoritative SDK when present; `GLYPHS_SDK_PATH` accepts its root or wrapper file, otherwise its location is computed relative to the reference workspace/repository. |
| `GSFont()` | Explicit empty detached storage with no native binding; writable metadata, glyphs and masters. Saves first-master UFOs through the existing in-memory serializer. Registering it with `Glyphs.fonts` or saving it as a native document is unsupported; no FontLab package is created. `test_empty_font_and_master_can_be_filled_and_saved`. |
| `GSFontMaster()` / `font.masters.append()` | Detached name/basic metrics writable. In-memory backend accepts and binds the master; native append explicitly refuses because native master creation is not mapped. `test_native_master_append_and_duplicate_rename_refuse_before_notification`. |
| `layer.selection = [...]` / `= []` / `clearSelection()` | Nodes, anchors, components and guides in memory, including detached layers. Whole-input ownership/kind preflight. Native nodes and `flShape.selected` components are supported without Undo; anchors have no public bound pinpoint selection API and guides have no public selected field. Only explicitly selecting an unsupported kind refuses before mutation. Clearing/replacing supported selection skips those kinds, whose selection state cannot be observed or changed; reads omit them. `test_selection_replaces_and_clears_all_four_kinds_without_undo`, `test_selection_preflights_foreign_and_unsupported_kinds`, native selection contract test. |
| `GSComponent(glyph=None, offset=(0,0), scale=(1,1), transform=None)` | Explicit transform overrides offset/scale. Read/write affine transform, two-axis scale and CCW rotation; translation retained. Pure horizontal/vertical mirrors retain the negative X/Y scale respectively, with zero rotation. Reflected matrices use the equivalent representation with rotation nearest zero; matrix reads retain arbitrary affine shear. Live writes use existing copy-on-write/history guards; automatic layers refuse. Public/native transform regression tests check numeric matrices and original history ownership. |
| `GSNode.type`, `GSAnchor.name` | Writable detached and live. Node types are validated in the proxy before any backend access; only line/curve/qcurve/offcurve SDK string values are accepted. Native types use documented `flNode.NodeType` masks, preserving coordinates and other flags through copy-on-write. Native curve endpoints require existing controls (two for cubic); line conversion with incoming controls and mixed cubic/quadratic contours refuse before mutation. Native/public node and anchor tests verify expected values, lookup identity and notifications. |
| `font.familyName`, `unitsPerEm` / `upm` | Writable through package history; UPM must be a positive integer and native `setUpm(value, False)` does not scale outlines. Public/native metadata parameter tests. |
| `master.name`, `ascender`, `capHeight`, `xHeight`, `descender`, `italicAngle` | Writable through package history and matching Font-window guards; finite metrics only. Native rename retains proxy identity and prepares affected master/bracket layers
and masks; affected automatic layers refuse before mutation; another master's metric write restores the active master. Public/native master parameter tests and focus/duplicate-name refusal cases. |
| `GSPath.reverse()` | Reverse incoming segment types and node order for open/closed cubic/quadratic paths; retain positions, node metadata and closed flag. Live paths use existing guarded node replacement (retained old node handles become stale), one Undo group. `test_reverse_preserves_curve_geometry_flags_and_undo`. |
| `GlyphsApp.plugins` base imports | All seven bases import without a bound backend or native modules. Active/session-bound class identities remain reused. `test_plugin_bases_import_without_backend_or_host` and existing identity tests. |
| `GSInstance` interpolation | `interpolatedFont` (and unimplemented interpolation members) explicitly raise `UnsupportedCapability`; no interpolation or generated font is fabricated. |

All new live property writes nest in the existing Undo context. Offline native
contract tests prove calls/guards and notification counts, not real FontLab
Undo/Redo, editor selection or saved/reopened acceptance. No live environment
or canonical checkout was changed.

Extrema preserve closed-path rotation, and Boolean output omits duplicate closing
nodes. Unchanged extrema/overlap operations retain tokens, dirty state and Undo.
All four outline edits return `None`, nest inside existing layer/glyph Undo
groups, stage computed geometry before mutation and retain collection rollback.
The native backend publishes Python geometry using the existing guarded
`flNode`/`flContour` constructors and `flLayer` shape writes. The supplied echopy
stubs expose no matching **layer-scoped** boolean, winding or extrema operation;
glyph/shape boolean methods are not substituted for a layer edit.

The capitalized public package lives under an additional `_public` package
search root so it coexists with internal `glyphsapp/` on case-insensitive macOS
volumes. All existing internal module paths remain unchanged. An active
`activate()` is the source of truth; calling it after an independent public
session is bound is explicitly refused until `unbind()` releases it. `use_backend`
and `unbind` are not in the facade's star-import list. The scoped `run_script` session remains scoped to its handle.

Evidence: FakeBackend geometry, pen recording/round-trips, actual UFO writes,
missing-host/lazy imports, public export equality and bootstrap identity tests;
native save/close are call-contract doubles only. This adds no FontLab runtime,
native Undo/Redo or saved/reopened acceptance claim.
Reference contracts: supplied Glyphs SDK wrapper docstrings and the official
[path-direction handbook](https://handbook.glyphsapp.com/editing-paths/) and
[fontTools point-pen protocols](https://fonttools.readthedocs.io/en/latest/pens/pointPen.html).

## Glyph Info lookup limitations — 2026-11-01

`Glyphs.glyphInfoForName(name, font=None)` queries the shared manager
(glyphsLib's global fallback data) when `font` is None. With a font it queries
`font.glyphsInfo()`: that document's local Glyph Info manager when one is loaded,
else the shared manager. A `font` that is not a GSFont raises `TypeError`. The
document-local lifecycle needs an info provider (see GLYPH_INFO_MANAGER.md).
A font glyph's metadata and outlines are not substituted for a Glyph Info database.
Custom global GlyphData overlays remain unimplemented; this fallback is not full
Glyphs database equivalence. Earlier candidate artifacts still use active-font
lookup and do not contain this source repair.

The newer [global Unicode lookup](unicode-lookup.md) implements
`glyphInfoForUnicode(String, font=None)` with exact combined-index lookup and
source-backed synthesis. Integer name lookup dispatches there and keeps the
supplied font, so both lookups use the same manager. The index inserts each public record's primary
then legacy encoding in record order, with last-write precedence. The retained
base parser proves legacy inclusion; this corrects earlier primary-only claims.
Legacy lookup retains separate primary/legacy fields: `FE8D` returns
`alef-ar.isol` with primary None and legacy `FE8D`. Public glyphsLib 6.16.2 gives
72,131 combined keys, including 730 legacy keys; `0000` selects the later `NULL`.
Private wheel/sdist and exact consumer checks pass for the retained parent Unicode snapshot; the new production candidate awaits its own installed and consumer checks; native workflow gates remain open;
older immutable reports retain their historical primary-only behavior.
Noncanonical spellings, signed32bit parsing and safe malformed-UTF16 refusal
are covered separately from proprietary database equivalence and native workflows.

An offline comparison with eleven retained Glyphs 4 native-manager cases matched
four represented fields (name, first Unicode, category and subcategory) in six
cases. Glyport refused `A.ss01`, `_corner.test`, `_part.test`, the empty name and
an unknown ordinary name. The retained upstream manager synthesized the first
three and returned nil for the last two. These observations do not establish
Python-wrapper behavior in every supported Glyphs version.

`GSGlyphInfo.script` now snapshots the supplied metadata script, including None
when no script is assigned. Global lookups use glyphsLib records rather than
guessing from the current glyph encoding; aliases resolve to canonical records.
The field is read-only. This does not qualify custom database overrides or native
workflows. Earlier artifacts do not contain the script-field addition.

`GSGlyphInfo.case` snapshots the supplied case enum. Global database lookups
map explicit case metadata to no-case/upper/lower/small-caps/minor/other (0–5),
and missing case metadata to no-case. Unknown labels raise `GSGlyphInfo.case`
rather than becoming no-case. Punctuation, combining marks and ligatures can
have case values that differ from Unicode general categories. This does not
add synthesized-name and custom-database support. Earlier artifacts lack this field.

### Glyph case lifecycle candidate

`GSGlyph.case` uses case metadata for supported names, including ligatures,
punctuation and combining marks. Explicit assignment changes the current case;
it does not enable `storeCase`. Setting an already-false `storeCase` does not
refresh metadata. Enabling it preserves the current case across name/metadata
refreshes. An attached true-to-false transition restores the supported database
default. Copy and unique attachment preserve the current value and flag.

This follows the pinned public wrapper and retained Glyphs 4 source analysis;
it is not new native verification. The public
[case](https://docu.glyphsapp.com/Core/GlyphsCore/GSGlyph/case/) and
[storeCase](https://docu.glyphsapp.com/Core/GlyphsCore/GSGlyph/storeCase/)
documentation describe the database/storage relationship.

Detached true-to-false reset is explicitly unsupported pending qualification.
Custom font/global databases and synthesized-name metadata remain unsupported.
The existing `updateGlyphInfo` missing-record refusal and Unicode/name behavior
remain separate limits; this change does not establish whole-method fidelity.
Case persistence uses the existing glyph-lib route. Native history, save/reopen,
fresh artifacts and original scripts' full workflows still require verification.

Owned offline example (requires the candidate source, not the preceding wheel):

```python
from fly.gp.model import GSGlyph

glyph = GSGlyph("ordfeminine")
assert glyph.case == 4  # Glyph Info classifies it as a minor figure.
glyph.case = 3
assert glyph.storeCase is False  # Assignment alone is temporary.
glyph.storeCase = True
glyph.name = "f_f_i"
assert glyph.case == 3  # Stored override survives a known-name change.
```

### Glyph script lifecycle candidate

`GSGlyph.script` uses named-glyph metadata without requiring a Unicode value.
Explicit `None`, empty strings and script names remain distinct. Assignment does
not enable `storeScript`; assigning false to an already-false flag is a no-op.
Enabling the flag preserves the current script through supported rename/refresh
operations. Disabling it on an attached glyph restores a known database record's
script, including a record whose script is None. Copies and unique attachment
preserve both script and flag, alongside case and unrelated lib values.

Changing Unicode alone does not change script. Known-name changes refresh an
unstored script; missing-name records preserve the previous value. Detached
true-to-false reset and attached reset without a metadata record refuse before
mutation. Custom managers, synthesized names and full `updateGlyphInfo` fidelity
remain open. This contract follows retained upstream source analysis; native
history and save/reopen still require verification with installed artifacts.

Owned offline example:

```python
from fly.gp.model import GSGlyph

glyph = GSGlyph("A")
assert glyph.script == "latin"
glyph.script = None
assert glyph.script is None
glyph.storeScript = True
glyph.name = "Alpha"
assert glyph.script is None  # Stored None survives the known-name change.
```

### Classification and shared resolver

The source candidate now supports independent `category`, `subCategory`,
`storeCategory` and `storeSubCategory` values. Classification accepts strings,
including the empty string, or `None`. Assigning Unicode alone does not refresh
classification. Turning an enabled storage flag off refreshes only that field;
a flag already off is a no-op. Detached resets remain explicitly unsupported.

Case, script and classification resets share Unicode-first resolution. For an
`A` encoded as `0061`, case resets to lowercase; for `0A15`, script resets to
Gurmukhi. The first resolvable encoding wins, including synthesized metadata:
an unassigned `0378` prevents a later `0A15` from supplying Gurmukhi metadata,
while `10FFFF`, which yields no record, allows the next encoding to be tried.
The `Icon` and `SF-Symbol` categories use the audited keep-name path.

These are owned offline checks against retained upstream analysis, not native
measurements. Custom data, full ROS mapping, complex small-cap mapping
and language suffixes remain unqualified. Arabic presentation settings and
additional encodings now follow the
audited helper gates; native workflow acceptance remains open. Earlier artifact hashes and examples above identify their
historical, narrower candidates; they do not identify this source revision.

Additional-Unicode refresh uses a bundled public Unicode17 scalar map, matching
macOS27.2 NSString.lowercaseString across all1,112,064 valid scalars. The helper
uses pre-apply case/script and staged name/codes; opposite-case ownership, Greek
sentinels, U+0130, dotless I, keep-name and detached Arabic paths remain distinct.
It does not promote legacy-only .isol data. This pins the measured casing version;
older/future Foundation equivalence and full custom-manager/ROS routes
and native history/persistence remain unqualified. Unicode licence/provenance
ship with the package; no Objective-C bridge is introduced at runtime.

`GSGlyphInfo` has a source-qualified [stored production field](production-metadata.md)
and [selected-record description](glyph-descriptions.md). Descriptions preserve
nullable stored text without Unicode-name synthesis. Anchors, direction and other
native metadata remain incomplete; matching subsets do not establish complete records.
The public unicodeLegacy property now preserves separate maintained legacy
encodings in owned read-only snapshots. Requested shipped ROS maps explicitly
refuse when their proprietary mapping data is required; no substitute map ships.
See [legacy encodings and ROS](legacy-and-ros.md) for examples and exact boundaries.
Custom global/document-local data overrides and synthesis need a coherent lookup
contract; a direct glyphsLib production-name call does not supply that contract.
Missing dependencies must remain distinguishable from genuine database misses.
The audit itself changed no runtime behavior; the subsequent default-lookup
repair above changes only the public application method.


Return to the [current installation and compatibility overview](../index.md).

This reference preserves the pre-cleanup README from revision `161efe3`.
First-slice status statements, native acceptance counts and revision references
below describe historical checkpoints; they do not establish current or complete
Glyphs conformance. The current README governs installation, backend selection
and overall limits. Detailed implementation notes and retained evidence remain
useful when interpreting older reports. `WORK.md` and workspace issue/evidence
paths mentioned below are checkout records, not additional distributed files.


Glyphs script and plugin compatibility for FontLab, developed in
[fontlabcom/fontlab-glyport](https://github.com/fontlabcom/fontlab-glyport).
The Python namespace is `fontlab_glyport`.

This repository owns the Glyphs model adapters, automatic source/import
adaptation, plugin lifecycle, and dynamic Cocoa/Vanilla-to-Qt translation.
Shared FontLab controls belong to Fontlabapp; PySide2 behavior belongs to
Pythonqtside. The expanded ecosystem specification is `issues/101.md` in the
parent workspace.

Current implementation: read-only script/bundle inspection, execution receipt
records, typed errors, cached Python 2 source adaptation and owned Python execution
scopes, plus the first R019–R022 live model slice. Native verification is pending.
An assessment records requirements; it does
not establish runtime compatibility. Source originals are never executed or
modified during inspection. Relative imports and computed runtime imports need
later dependency resolution; the inspector reports that limitation.

```python
from fly.gp import inspect_source

assessment = inspect_source("OriginalScript.py")
print(assessment.required_capabilities)
print(assessment.to_dict())
```

Use the genuine reviewed App checkout and clear inherited SCM pretend-version
variables first (DEPENDENCIES.md). The tracked lock is stale.

```bash
uv run --no-config --python cpython-3.11-macos-aarch64-none --no-project \
  --with pytest --with-editable ../fontlab-fontlabapp --with-editable . pytest -q
uv run --no-config --python cpython-3.11-macos-aarch64-none --no-project \
  --with-editable ../fontlab-fontlabapp --with-editable . \
  python -m fontlab_glyport inspect OriginalScript.py --json assessment.json
uv build --no-config
```

Profiles are `auto`, `glyphs2`, `glyphs3`, and `glyphs4`. Inspection records
declarations, API minima and simple version rejection guards. Unresolved `auto`
executes as `glyphs4`; conflicting evidence requires an explicit profile.
Compatibility version values describe that profile, not FontLab's version or
a claim of complete Glyphs conformance.
The `glyphs4` reference profile reports `versionNumber=4.1`,
`versionString="4.1.1"` and `buildNumber=4108` from shared version metadata.

The assessment includes original SHA-256 file identities, import locations,
SDK protocol declarations, bundle principal class, Python entry points and
resource requirements. Symlinks retain their link identity and are not followed
by inspection. Bundles without Python remain visible and require native support.
The CLI creates a new report file and refuses to overwrite an existing output.

## Ordinary Glyphs imports in FontLab

At the start of a Python 3 script running on FontLab's GUI thread, add:

```python
from fly import gp; gp.activate()
from GlyphsApp import *
import AppKit, Foundation, vanilla
```

Place activation after any `from __future__` statements, as Python requires.
The remaining script uses ordinary Python imports in its own namespace. This
uses the existing native adapters and supplies GlyphsApp exports (including bare
`Glyphs`) in the caller script globals. Legacy menu scripts also receive
`Font`, a snapshot of `Glyphs.font` when that caller activates (or `None`). `activate(namespace=globals())` makes the
target explicit. Existing conflicting globals are refused; cleanup removes only
names added by activation that the script has not since replaced. It does not
rewrite source. Use `run_script` for source adaptation/dependency routing.

Activation defaults to `glyphs4`; `activate(profile="glyphs3")` selects another
explicit profile. Repeated activation returns the same retained handle. Call
`gp.deactivate()` (or `handle.close()`) when finished with callbacks
and windows. Cleanup is idempotent. Activate/deactivate outside a running scoped
execution or callback. Scoped runs can execute while activation is retained.
Existing foreign GlyphsApp/Cocoa/Vanilla compatibility modules are refused to
protect another host; recognised native PyObjC modules can be preserved or
temporarily masked by the selected backend; unrelated imports and caller-installed replacements survive cleanup.
No global builtins patch or persistent execution lock is installed. Unit tests
cover import/lifecycle contracts; native acceptance is a separate required gate.

Glyph category/subCategory reads use the maintained GlyphData included with the
declared `glyphsLib` dependency. This covers spacing marks and unencoded named
alternates. Glyph case uses the separate Glyph Info case classification.
An incomplete dependency installation raises an explicit error.

## Python 2 source adaptation (R016/R017)

```python
from fly.gp import adapt_source

adapted = adapt_source("OriginalScript.py", profile="glyphs2", cache_dir=".glyport-cache")
code = adapted.compile()  # original filename; compilation does not execute
location = adapted.translate(1, 1)  # generated to original, one-based characters
```

Original bytes are read and never changed. Artifacts live under the owned
`cache_dir/fontlab-glyport` namespace, keyed by original SHA-256, profile and
`PIPELINE_VERSION` (including the installed fissix version). Completed entries
are published from staging directories; hits verify artifact hashes and skip
transformation. Corrupt entries fail explicitly. Keep originals outside this
owned namespace. Profiles select cache identities; all use the same syntax rules.
Source accepted by Python 3.11's AST parser passes through byte-for-byte with
zero adaptations, including Python 2 builtin names that are also valid syntax.

Ordered `Adaptation` receipt records cover `py2.print_statement`, `except_comma`,
`exec_statement`, `backticks`, `ne_diamond`, `raise_tuple`, `dict_iter`, `xrange`,
`long_literal`, `octal_literal`, `unicode_literals`, `unicode_builtin` and
`integer_division` (each has the `py2.` prefix). Each records its reason, input
and output byte hashes, and an external JSON `SourceMap`. Maps cover every
generated character using one-based Unicode columns and exclusive span ends;
unchanged characters preserve positions and replacements conservatively map
to the original edited span. Stage maps and the final map point directly to
the original, rather than the previous stage. EOF has no character span.
Absolute map paths are private receipt facts; alias/copy them before publishing
a public receipt. `AdaptationError.location` uses original path/line/column.

Classic `/` becomes `_glyport_div(left, right)`: integer operands floor (including
negative integers and bool), mixed/float operands use true division. Evaluation
order and associativity are preserved. Future `division` bypasses rewriting.
The helper import respects encoding cookies, docstrings and future imports;
bindings of its reserved name fail explicitly. Python 2 `/=` needs manual
adaptation and fails, unless future division applies. No host/UI imports occur.

Strings stay text; `PY2_STRING_AMBIGUITY` requests byte-operation review.
Fissix preserves ordinary trailing-comma/redirection prints, exception binding,
explicit-namespace exec, dict key-list snapshots and iterator APIs. It does not
emulate Python 2 hash-table iteration order, print softspace edge cases,
function-local implicit exec, exception-variable survival after handlers,
custom `__div__` coercion, or all shadowed builtin/method names. Diagnostics
request semantic review. Raw-unicode `ur` escapes require review and receive
`PY2_RAW_UNICODE_REVIEW`; conversion to raw text does not reproduce their
Unicode escape interpretation. This pipeline is source adaptation, not a
complete Python 2 interpreter or proof of host compatibility.

## Execution receipts and errors

`Receipt` and its frozen sub-records describe schema version 1 independently of
FontLab. `receipt.to_dict()` returns fresh JSON objects/arrays;
`validate_receipt(data)` returns structural errors (an empty list means valid).
`write_receipt(receipt, path)` validates and writes UTF-8 JSON, refuses existing
files (including links), and cleans up staging files on failure. It uses a
temporary file and replace, then an exclusive hard link for atomic publication
without overwrites, including concurrent writers. The destination filesystem
must support hard links. Validation does not establish native behavior.

Version-one choices where R018 leaves representation open:

- `schema_version` is integer `1`; other versions and identifiers are strings.
  Unknown record keys are errors. Evidence is an array of nonempty strings.
- Artifacts and source maps use `sha256` for their hash key. `source_map` is
  `{path, sha256}`, identifying an external generated-to-original span map;
  this validator does not read that file or prescribe its internal format.
- `not_applicable` requires `reason={role, reason}` and explicit
  `requested=False`. Requested capabilities/stages default to `True`; unsupported
  requested behavior belongs under `blocked` or `failed`.
- Nullable facts include repository/revision/source hash, environment values,
  adapter profile, source map, artifact hash and stage times. Each null needs a
  diagnostic whose `field` names it, e.g. `environment.qt` or
  `stages[0].started_at`. Missing diagnostic context and unused role reasons
  may be null without recursive diagnostics.
- Diagnostics use uppercase codes, `info|warning|error` severity, `location`
  (`path`, one-based integer `line`/`column`), `capability`, `message` and
  `recovery_action`. `ReceiptDiagnostic` is separate from assessment `Diagnostic`.
- Public validation/writing is the default: supply public aliases for private
  identifiers and retain source-relative paths. Absolute/home paths in fields
  or prose are rejected, not silently shortened. Arbitrary private identifiers
  cannot be detected automatically. `public=False` permits private reports;
  source `relative_path` and dirty-file keys must still be relative.

`GlyportError` subclasses are `HostUnavailable`, `UnsupportedCapability`,
`AdaptationError`, `DependencyUnavailable`, `StaleNativeObject`,
`NativeOperationError`, `Cancelled` and `PartialFailure`. `UnsupportedAttribute`
subclasses both `UnsupportedCapability` and `AttributeError` for attribute reads. Each accepts a message
and optional `location=SourceLocation(...)`, `capability` and `recovery_action`;
`error.to_diagnostic()` returns a `ReceiptDiagnostic`. All are exported from
`fontlab_glyport` without importing host/UI modules. `SystemExit` and
`KeyboardInterrupt` propagate unchanged.

## Owned execution scopes (R017)

```python
from fly.gp import ExecutionContext

context = ExecutionContext("scripts", "glyphs3", sink=print)
stage = context.run("scripts/main.py")
callback = context.wrap(context.globals["callback"])
callback()  # restores the import scope and output route for this invocation
context.close()  # idempotent; later activation is rejected
```

`context.on_close(hook)` registers a zero-argument hook. `close()` runs each
hook once, newest first, while the context is still usable, then unloads. A
failing hook, even one raising `SystemExit`, does not stop later hooks or the
unload. Afterwards `close()` re-raises the first process exit or interrupt as
is; otherwise it raises `PartialFailure`, whose message names each failure and
whose `errors` tuple holds every hook exception in run order.
Registering on a closed context raises `RuntimeError`. With no hooks, `close()`
behaves as before.

`run` activates the context itself; use `with context:` for direct scoped imports
through `context.import_module`. Nested activations and any second active context
are rejected before registration, even for matching profiles. Contexts may be
reused sequentially until closed. Sibling modules and packages, relative imports,
and bundle `Contents/Resources` use a unique private namespace. Package metadata
and original `__file__` paths support resource access. Each script runs with its
folder as cwd; the caller's cwd is restored on success, error or process exit.
Context-owned builtins and an `importlib` facade route ordinary imports and
`import_module`; unrelated host code retains its own imports. Modules are retained
outside `sys.modules` between activations, including for wrapped callbacks.

The optional third argument maps module names to zero-argument module providers;
additional names support optional dependency adapters. Defaults for GlyphsApp,
its plugins/UI, vanilla, AppKit, Foundation, Cocoa and objc raise
`UnsupportedCapability` on requested attributes with the original call location.
They provide no native functionality. Supply `cache_dir` to adapt scripts and
imported source using the existing pipeline. Execution infrastructure uses only
the standard library; optional adaptation uses the existing fissix dependency.

Fresh script globals are the default; `shared_globals=True` explicitly retains
one context's dictionary across runs for a profile needing Macro-style sharing.
`context.globals` exposes the latest dictionary. Host script globals are never
used. `Output` sends stdout/stderr writes to the injected callable, or collects
strings in `context.output.strings`; wrapped callbacks use the same route.
A host must inject its actual Macro/Output destination; no native routing is
claimed. `run` returns a receipt `Stage`, and records `SystemExit` in
`exit_status` (nonzero exits fail the stage). Other exceptions propagate with
`last_stage` retained; `KeyboardInterrupt` also propagates. Streams are restored.

The active finder and private module entries are removed after success or error;
pre-existing module-table values are restored and unrelated newly loaded host
modules are retained. Failed scopes do not retain newly imported private modules.
This is cooperative in-process scoping, not a security sandbox: mutations of
existing module objects, external side effects and concurrent host threads are
not rolled back or isolated. The lock serializes Glyport scopes only. Importing
through host-held importer references can bypass the owned facade. Native/Qt
profile coexistence is unimplemented; no Python subinterpreter safety is claimed.

## Live model (R019–R022, first slice)

Import `Model` from `fontlab_glyport.model`; backend/helper imports are from `fontlab_glyport.model.fontlab_backend`.
Native tests must use `pkg = owned_test_package(["A", "B"])` (retains `.package` and source `.fg_font`), then
`model = Model(FontLabBackend(packages=[pkg]))`. Explicit scope never reads workspace fonts;
its current font is the first valid supplied package. An empty scope stays empty.
Omitting `packages` exposes workspace fonts. Reads fetch package facts, glyph metadata, or one layer.
`model.fonts`/`model.font` expose the [Glyphs 3 subset](https://docu.glyphsapp.com/): fonts, masters, glyphs, layers and geometry.
Width/node-position edits, path append/remove and anchor append use the backend.
A master layer FontLab has not created yet (the `.notdef` of a new FontLab font has
none) reads as empty with width 0; the first width, path or anchor write creates it
natively (`findLayerCreate`) in the same change notification, and FontLab assigns
its default width (250 observed) unless the write sets one. Reads never create layers.
`glyph.layers` keeps masters first in font-master order, followed by ordinary
native auxiliary layers in native order. Masks and service/interpolating layers
are excluded from that foreground catalog. Master layer IDs equal master IDs;
auxiliaries have their own stable session IDs and native names. FontLab has no
associated-master metadata for ordinary auxiliaries, so Glyport maps them to the
first existing master, following the [Glyphs default](https://docu.glyphsapp.com/#GSLayer.associatedMasterId),
without changing native metadata. Their `isMasterLayer` remains false.
Clearing a missing background is a read-only no-op, including on auto layers;
clearing an existing auto-layer mask still refuses before any edit.
Edits are published so that one Edit > Undo reverts a whole `font.undo_group(name)`
(or a single edit outside a group): before the first change to each layer FontLab
is told its pre-change state, then the changed layers followed by their glyphs are
notified once (a layer alone is skipped by Undo). This leaves one extra Undo step
named like the group that restores the same state. What Undo restores is FontLab's
choice: advance width, anchors and added/removed paths are restored, but node
coordinates moved from Python (`node.position`, `layer.applyTransform`, `LSB`
writes) are not, whatever is notified (`crash/R054-node-coordinates-not-undone.md`
in the parent evidence). Known FontLab limitation: after
Undo then Redo, undoing the next step also reverts the redone glyphs, and their
redone state is lost (`crash/R054-redo-then-new-step-loses-redone-state.md` in the
parent evidence).

`font.userData`, `glyph.userData` and `layer.userData` are dict-like views of the
native libs (font: `packageLib["com.schriftgestaltung.Glyphs.fontUserData"]`;
glyph/layer: their whole `lib`). Master userData excludes reserved parameter keys
and preserves them when writing ordinary userData entries.

`font.customParameters` and `master.customParameters` preserve insertion order,
duplicate names and active flags. Indexed reads return live parameter objects;
name reads return the first active value, while name membership includes inactive
objects. Name assignment updates the first matching object, retaining its active
flag. Assigning `None` or deleting a name removes only the first match; deleting a
missing/empty name is a no-op. Integer bounds are strict, including `insert`.
`remove(parameter)` removes that object itself (by identity, as Glyphs'
`removeObject_`), not the first parameter with its name; a parameter that is
not in the collection raises `ValueError`.
Iteration uses the initial count; shrinking during iteration can raise IndexError.

An ordered lib sidecar holds persistent identities and values. Existing flat
`com.schriftgestaltung.customParameter.GSFont.<name>` values migrate on the first
write in their former sorted order; their original insertion order was never
recorded. Flat keys mirror first-active values for glyphsLib readers. New external
flat keys are imported. When an existing mirrored value is changed or removed
outside glyport, the flat keys win: reads never fail, a changed value updates
the effective (first active) parameter in place, a removed key drops that
name's active parameters, and the next write persists the result. One
`CUSTOM_PARAMETERS_REBUILT` warning goes to the execution receipt. The sidecar
key `com.fontlab.glyport.orderedParameters.<prefix>` is stored in the font's
lib and is saved and exported with it.
Unrelated lib entries are preserved. The sidecar and mirrors remain separate from
font/master userData. VFJ save/reopen and native history are still unqualified;
lib integers have previously reopened as floats.

Parameter name/value/active setters are supported. Names normalize only four
curly quotes; nil names become empty strings. Empty-name objects remain available
by index but are absent from keyed lookup/membership. Copies duplicate nested
values and retain the parent pointer; inserted objects become live and removed
objects detach. Nested mutation of an attached value container, same-object
multiple insertion, cross-owner reparenting and complete native identity remain
unqualified. The exact spaced Arabic presentation setting now has typed bool-schema
conversion and resolver processing on the audited path. macOS strings use real
Foundation parsing; non-macOS strings and arbitrary object conversion remain
explicitly unsupported. Numeric values preserve their precision. Full ROS
replacement, custom managers, native collision handling and complete original
workflows remain open.
See [Arabic presentation examples](arabic-presentation.md).

The [ordered parameter example](custom-parameters.md) runs against an owned offline
model. `font.features` and `font.featurePrefixes` remain read-only snapshots
(FontLab has one prefix, named "Prefix", and stores code with a trailing newline).

`font.axes` (name, axisTag, id = tag, hidden), `master.axes`/`internalAxesValues`
and `font.instances` (name, axes, exports) are read-only snapshots; coordinates come
from `axis.valueWeight(location)`. Unregistered owned packages expose no axes.

`font.kerning` is a live `{masterId: {left: {right: value}}}` mapping. Assign
`font.kerning[master.id] = pairs` to replace a master's pairs, or `{}` to clear
them; empty masters are omitted from reads. Pair keys are glyph ids or
`@MMK_L_<class>`/`@MMK_R_<class>`. Nested mappings are read-only snapshots;
assign the whole master mapping or use `setKerningForPair`/`removeKerningForPair`
to edit. `kerningForPair` returns `None` for a missing explicit pair. Kerning is
LTR only.

`glyph.rightKerningGroup`/`leftKerningGroup` read the currently selected master's
FontLab class used on the pair's left (VFJ "1st") or right side, respectively.
Assigning a group name updates membership across all independent-class masters;
`None` or `""` clears membership. Shared class changes are refused before edits,
including class cleanup during pair replacement; shared pair-only writes remain
supported. Kerning writes use FontLab's own tools (`fontpr`): each native command
has its own Undo step, outside any `undo_group`, with no aggregate atomic group.
Independent-class commands can clear opaque native main-glyph references that
the current host cannot expose; complete native metadata preservation is not
established (FontLab issue 8519).

`layer.guides` reads guidelines (not hints, which FontLab
also stores as guidelines) and accepts `GSGuide(position, angle, name)`;
`layer.hints` are read-only PostScript stem/ghost records (FontLab hints are not
node-linked, so `originNode` and friends raise).
`font.classes` lists FontLab's OpenType classes (`fgFont.groups` entries with
`isFeaGroup()`) as read-only `GSClass(name, code)` snapshots.

Without explicit `packages`, `model.font` (and `Glyphs.font`) is FontLab's active
font as FontLab's own tools report it (`flWorkspace.currentPackage` lags behind
switches). Right after the active font closes FontLab may report no active font
(then `model.font` is `None` until a font is activated) or already the remaining
one; glyport reports what FontLab reports. Proxies of a closed font
raise `StaleNativeObject`; other fonts' proxies stay valid. `node.selected` reads
and writes the native selection flag (UI state: no undo step); `layer.selection`
lists observable selected nodes/components (and anchors/guides where supported),
as detailed in the public API review matrix.

`layer.name` is the master name for master layers. Ordinary foreground auxiliaries
retain their backend name, including an empty string or `None`, without a fallback
to the associated master. Copies preserve that value. This does not establish
whether native Glyphs import preserves the distinction between absent and empty
names; backgrounds retain their existing naming behavior. The nullable/custom
name contract is described in the [Glyphs 2 native API](https://docu.glyphsapp.com/glyphs2/Core/Classes/GSLayer.html).
`layer.bounds` (`origin`, `size`) comes from
FontLab's `boundingBox` (an empty layer gives a zero rect); `LSB`/`RSB` derive from
bounds and width. Writing `LSB` translates the outline natively (anchors move with
it) and keeps RSB; writing `RSB` changes the width; both raise on an empty layer.
`layer.applyTransform([a, b, c, d, tx, ty])` uses `flLayer.applyTransform`.
Live/detached layer and path transforms, including the selection-aware layer
selector, reject NaN/infinite coefficients before backend calls, history or
geometry changes. Finite zero and negative scales keep their existing behavior.
Python-managed path, detached-layer and selection-aware transforms calculate
all point/component results before writes or history, so arithmetic overflow
leaves earlier geometry untouched. Repeated draft objects are calculated once
per occurrence, using the previous virtual result. Native whole-layer transforms and failures
inside setters are not covered by that guarantee. This does not establish native
transform/payload equivalence with Glyphs.
Stored anchors accept `position`/`x`/`y` writes. `font.selectedFontMaster` is
FontLab's current master; `disableUpdateInterface`/`enableUpdateInterface` are
no-ops.

With `fontlab_glyphsapp_provider`, `Glyphs.addCallback(fn, DOCUMENTOPENED)` and
`DOCUMENTCLOSED` connect to FontLab's own document signals (`packageReaded`,
`signalPackageClosed`); the callback's `notification.object()` is the event's
`GSDocument` (None for a font outside the model's scope). FontLab emitted no signal
for activation or saving through its MCP tools, so `DOCUMENTACTIVATED` and
`DOCUMENTWASSAVED` stay unsupported. `ctx.close()` disconnects every slot.

`font.currentTab` is FontLab's active glyph tab when it shows this font (else
`None`); `tab.text` reads and writes Glyphs text (characters, `/name ` for
unencoded glyphs, `\n` line breaks; unknown names or characters raise
`ValueError` before anything is sent), `tab.layers` are the tab's glyphs in the
tab's master. `font.newTab(text)` makes the font active and runs FontLab's "New
Glyph Tab". `font.selectedLayers` are FontLab's current glyphs of this font.
Empty lines in a tab are not reported back.
`with font.undo_group("Edit"):` balances groups on exceptions; proxies retain identity.
Imports are host-free; unsupported operations fail explicitly. See WORK.md for native verification.

## GlyphsApp host services (R026 first slice)

`fontlab_glyport.glyphsapp.make_glyphsapp_module(model, bridge, error_sink=...)`
returns a `GlyphsApp` module. Opt in per context with
`ctx.adapters["GlyphsApp"] = glyphsapp_provider(model, bridge, wrap=ctx.wrap, error_sink=sink, on_close=ctx.on_close)`;
without it the default placeholder still raises, and `GlyphsApp.plugins`/`GlyphsApp.UI`
stay placeholders either way. `model` is a `fontlab_glyport.model.Model`. Every host
effect goes through `bridge`, a `GlyphsBridge` protocol (`glyphsapp/bridge.py`).
`FontLabGlyphsBridge` (below) is the FontLab 9 bridge; it is not natively
verified yet. Tests use doubles, so nothing here is native evidence.

Exports: `Glyphs`, the model classes (`GSFont`, `GSFontMaster`, `GSGlyph`,
`GSLayer`, `GSPath`, `GSNode`, `GSAnchor`, `GSComponent`), the dialogs and these
event constants with their Glyphs SDK values: `UPDATEINTERFACE`, `DRAWBACKGROUND`,
`DRAWFOREGROUND`, `DRAWINACTIVE`, `MOUSEMOVED`, `MOUSEDOWN`, `MOUSEUP`,
`DOCUMENTOPENED`, `DOCUMENTACTIVATED`, `DOCUMENTWASSAVED`, `DOCUMENTCLOSED`
(`"GSDocumentWillCloseNotification"`, as in the SDK), `TABDIDOPEN` and `TABWILLCLOSE`.
Any other module name or `Glyphs.<member>` (read or write) raises
`UnsupportedCapability` located at the script line. Unknown reads on `Glyphs`
and `currentDocument` raise its subclass `UnsupportedAttribute`, which is also
an `AttributeError`, so `hasattr(Glyphs, "x")` is False and
`getattr(Glyphs, "x", default)` returns the default. Unknown module names stay
plain `UnsupportedCapability`, so `from GlyphsApp import X` keeps its
capability and location instead of becoming an `ImportError`.

Model proxies (`GSFont`, `GSGlyph`, `GSLayer` and the rest) follow the same
rule: an unknown read such as `layer.syncMetrics` raises `UnsupportedAttribute`
with its capability (`"GSLayer.syncMetrics"`) and script line, so corpus probes
like `hasattr(layer, "smartComponentPoleMapping")` and
`getattr(glyph, "color", None)` take their fallback. Unknown writes stay plain
`UnsupportedCapability`. Property bodies on these classes are guarded: an
`AttributeError` inside one surfaces as `UnsupportedCapability` naming the inner
capability, not as a miss of the property, so `hasattr` on a supported member
never silently returns False. Reading `.id` on an unattached draft (`GSNode()`)
raises `UnsupportedCapability("GSNode.id")`.

- `Glyphs.font`/`fonts` come from the model; `currentDocument` is `None` without
  a current font, otherwise an object with only `.font`.
- `versionNumber`/`buildNumber` are compatibility values the bridge reports.
  They are not FontLab's version.
- `showMacroWindow()`, `clearLog()`, `showNotification(title, message)` and
  `redraw()` call the bridge, never `sys.stdout`.
- `localize(value)` returns a string unchanged. For a dict it tries the
  bridge's `ui_language()`, then its primary subtag (`de-CH` -> `de`), then
  `"en"`, then the first value; `{}` gives `""`.
- `Message(message, title="Alert", OKButton=None)`, `AskString(message,
  value=None, title="Glyphs", OKButton=None, placeholder=None)`,
  `GetFolder(message=None, allowsMultipleSelection=False, path=None)`,
  `GetOpenFile(message=None, title=None, allowsMultipleSelection=False,
  filetypes=None, path=None)`, `GetFile` (SDK alias of `GetOpenFile` without
  `path`) and `GetSaveFile(message=None, ProposedFileName=None, filetypes=None,
  filetype=None)` return what the bridge answers. `GetSaveFile` also accepts the
  current SDK spelling `proposedFileName=` (not both). A single `filetype` or a
  string `filetypes` reaches the bridge as a one-item list.

Defaults live in the `defaults=` mapping (default: one process-wide in-memory
dict, like Glyphs' application-wide user defaults); nothing touches FontLab
preferences or files. Keys must be `str` (`TypeError` otherwise).

To persist defaults across sessions, pass
`defaults=JsonFileStore(path)` (`fontlab_glyport.glyphsapp.defaults`): one JSON
object in a file you choose, written atomically on every change. Values must be
JSON; tuples are stored as lists and anything else raises `TypeError` before
writing. A missing file reads as empty; a corrupt one raises `ValueError`. `fontlab_glyphsapp_provider`
uses it by default at `~/Library/Application Support/FontLab/Glyport/defaults.json`
(owner ruling; outside the FontLab 9 user folder), or at `$GLYPORT_DEFAULTS`; the
file is created on the first write.

- `Glyphs.defaults[key]` reads `None` when absent; assigning `None` or `del`
  removes the key, and removing an absent key is harmless. `.get(key, default)`
  works.
- `registerDefault(key, value)` stores the value only when the key is absent.
  A `None` key or value, or a key of two characters or fewer, raises `KeyError`
  (as the SDK does). This is simpler than NSUserDefaults, which keeps registered
  values in a separate domain: here a registered value is stored, so deleting it
  does not bring it back.
- `boolDefaults` reads `False` for a missing key, the value for a bool, nonzero
  for a number, and, for a string, `True` when (after whitespace, a sign and
  leading zeros) it starts with `Y`, `y`, `T`, `t` or `1`-`9`. Anything else is
  `False`. It accepts only `bool` or `None` on write.
- `intDefaults` reads `0` for a missing key. A bool gives 0 or 1, a finite
  float is truncated toward zero, and a non-finite float gives 0. A string gives
  its leading signed ASCII digits (`"3.7"` -> 3, `"x1"` -> 0). It accepts `int`,
  `float` (stored truncated) or `None` on write.

`Glyphs.addCallback(fn, EVENT)` returns `None`. It accepts a constant or its
raw string (`"GSUpdateInterface"`) and registers through `bridge.subscribe`,
retaining one token per `(fn, event)`. Bound methods match by equality, so
`removeCallback(self.update)` works. Adding the same pair again replaces the
old registration, so there are no duplicates. An unknown event raises
`UnsupportedCapability`, and a non-callable target raises `TypeError`.
`removeCallback(fn[, event])` removes every matching registration through
`bridge.remove` exactly once. Unknown or repeated removals do nothing. A token
whose `bridge.remove` raises is kept, so a later removal can retry it.
Callbacks run through `wrap` when given and receive the bridge's arguments.
Exceptions, including a closed context's `RuntimeError`, go to
`error_sink(exc, event)`. An exception raised by `error_sink` itself
propagates into the host's dispatch. `localize` returns `str(value)` for
anything that is neither a string nor a dict, as the SDK does. With
`on_close=ctx.on_close`, the first `addCallback` registers
`Glyphs._remove_all_callbacks` as a close hook, so `ctx.close()` removes every
callback once, including those of a module re-imported after a failed run.
Without `on_close`, a host tears down with `module.Glyphs._remove_all_callbacks()`.
It attempts every token, keeps any whose `bridge.remove` raised and re-raises
the first process exit, otherwise the first failure. The hook is consumed when
it runs, so an `addCallback` after `ctx.close()` is rejected by the closed
context and subscribes nothing. DRAW* events are only subscription contracts here: R026 routes painting
through `register_painter`, and nothing draws yet.

### FontLab bridge (`glyphsapp/fontlab_bridge.py`)

```python
from fly.gp.glyphsapp.fontlab_bridge import fontlab_glyphsapp_provider

ctx.adapters["GlyphsApp"] = fontlab_glyphsapp_provider(ctx, version=(3.2, 3234.0))
```

This builds `Model(FontLabBackend(packages))`, a `FontLabGlyphsBridge` and the
module provider in one call. Bridge diagnostics and callback errors go to
`ctx.output`. `ctx.close()` removes every callback first and then closes the
bridge. `version` is the compatibility `(versionNumber, buildNumber)` that
scripts see; no value is pinned yet, so the caller must choose it. Extra
keywords go to the bridge. Native modules load on first use only. Use the
bridge on the GUI thread.

- **Output.** `print` already goes to the context sink.
  `showMacroWindow()`/`clearLog()` do nothing by default, because FontLab's
  Output panel is user content. With `output_panel=True` they call
  `MainWindow.doShowOutputPanel()`/`doClearOutput()`, and raise
  `HostUnavailable` when there is no main window.
- **Notifications.** `showNotification` posts a 5 s status-bar message, never a
  dialog. Without a main window it writes to the log.
- **Redraw.** `redraw()` calls `fontlab.UpdateActiveCanvas()`, a view refresh
  without model change notifications.
- **Callbacks.** Only `UPDATEINTERFACE` is supported. One owned `QTimer`
  (250 ms) polls `(current package id, current glyph id)` and calls each
  callback once per change, with one argument: a `Notification` that has
  `name()` and `object()` (always `None`). The stubs show no native signal for
  other events, `DOCUMENTACTIVATED` included, so they raise
  `UnsupportedCapability` named `Glyphs.addCallback.<event>`. Removing the last
  callback disconnects the slot, then stops the timer and calls `deleteLater`;
  if the disconnect fails, the timer keeps running and the token is kept.
  A removal or `ctx.close()` made inside a callback only drops tokens; the
  timer is torn down after the callback round returns, never inside the
  emitting slot. Removing an issued token again does nothing (R026). A failure
  stays inside the timer slot and is logged, process exits included. The first
  subscription logs one `[GlyphsApp bridge]` line stating the narrower trigger.
- **Dialogs.** `Message` shows a non-modal `QMessageBox` and returns at once.
  Unlike Glyphs, where `Message` blocks until dismissed, script code after it
  keeps running. Boxes the user has closed are released on the next `Message`;
  the rest are closed by `bridge.close()`. `AskString`, `GetFolder`, `GetOpenFile`/`GetFile` and
  `GetSaveFile` return injected `answers={"ask_string": ...}` first. A `None`
  answer means cancel. Without an answer they run a modal `exec()` on an owned
  Qt dialog, but only with `interactive=True`; otherwise they raise
  `UnsupportedCapability` at the script line. `AskString` ignores `placeholder`.

## Vanilla UI (first slice)

`fontlab_glyport.ui.vanilla.make_vanilla_module(qt, error_sink=...)` returns a
`vanilla` module that builds real Qt widgets. `qt` is an injected namespace
exposing `QtCore` and `QtGui`; FontLab's PythonQt keeps widgets in `QtGui`, and
nothing here imports a Qt binding. To opt in, call
`ExecutionContext(root, "glyphs3", {"vanilla": vanilla_provider(qt, sink)})`.
Without this mapping, the default placeholder still raises.

The module exports exactly `Window`, `FloatingWindow` (tool window), `Group`,
`TextBox`, `EditText`, `Button`, `CheckBox`, `PopUpButton`, `Slider`,
`HorizontalLine` and `VerticalLine`, plus the slice 2 controls listed below.
Any other name, unsupported keyword or
`bind` event raises `UnsupportedCapability`. `sizeStyle` is accepted and only
recorded. Assigning a control to a window or group attribute parents its widget.
It also records a node in the window's versioned `UIGraph` (`window.graph`).
Every callback records a `Connection`. Layout follows `resolve_frame` and is
recomputed when the window is resized.

Callbacks receive the vanilla control as sender. Their exceptions go to
`error_sink(exc, sender)`, and programmatic `set()` does not fire them. Sliders
map floats onto an integer Qt slider with `SLIDER_STEPS` (1,000,000) steps.
`close()` and the title-bar close button take the same path. Close binds fire
once, every tracked signal connection is disconnected, and then the window
closes and `deleteLater()` runs. Open windows stay referenced until they are
closed. `getNSView()` returns the Qt widget as a compatibility handle.

To make callbacks follow the context's Output and imports, including callbacks
that fire after `run()` returns, register
`ctx.adapters["vanilla"] = vanilla_provider(qt, sink, wrap=ctx.wrap)`. A
callback that fires after the context has closed reports its error to the sink.
Add `on_close=ctx.on_close` and `ctx.close()` closes every window the module
still has open (close binds run inside the context first). Hooks run newest
first: vanilla registers at import, `GlyphsApp` at the first `addCallback`, so
Glyphs callbacks are removed before windows close when imports come first
(R027). A script that adds callbacks before importing vanilla reverses this.

Reassigning an attribute or running `del w.ok` retires the old control: its
connections are disconnected, its widget is unparented and `deleteLater` runs.
Its graph nodes (including a group's subtree) are kept but marked
`"detached": True`. See WORK.md for the native acceptance checklist.

Slice 2 adds the most frequent keywords and methods on these objects:

- Every control has `setToolTip(text)`.
- `TextBox` and `EditText` take `alignment="left"|"center"|"right"|"natural"|"justified"`
  (`natural` means left). Each value maps to the matching horizontal Qt flag
  combined with `AlignVCenter`, which is the Qt default for both widgets. Any
  other value raises `UnsupportedCapability` (`vanilla.TextBox.alignment.<value>`).
  `TextBox(selectable=True)` lets the user select the text with the mouse and
  the keyboard.
- `Window` and `FloatingWindow` gain `makeKey()` (raise and activate), `center()`
  (centre on the available geometry of the screen showing the window; it centres
  the client geometry, as `getPosSize` does, so the window deliberately sits about
  half a title bar low) and
  `getNSWindow()`, which returns the top-level Qt widget as a compatibility handle.
- `setDefaultButton(button)` accepts a push `Button`: Return or Enter clicks it
  while it is enabled, visible and still attached to that window. A button that
  is not attached to this open window (detached, retired, inside a deleted group,
  or in another window) raises `ValueError`, and its widget is never touched.
  Plain Qt widgets have
  no dialog default-button handling, so the window widget routes the key itself.
  Setting a new default clears the previous one.
- `autosaveName="name"` restores the window's last `[x, y, w, h]` frame for that
  name on construction. The frame is saved again whenever the window is
  resized, centred or closed. Frames are stored under `"window:<name>"` in the
  `settings` mapping passed to `make_vanilla_module(..., settings=...)` or
  `vanilla_provider(..., settings=...)`. By default this is an in-memory dict
  shared by every module in the process. Nothing is written to FontLab
  preferences or files. A malformed stored value is ignored, including
  non-finite numbers and a zero or negative width or height.

Slice 2 also adds the next nine controls by corpus frequency (they live in
`ui/vanilla_controls.py` and are exported from the same module). Programmatic
`set()` stays silent unless noted.

- `RadioGroup(posSize, titles, isVertical=True, callback=None)`: QRadioButtons
  in an exclusive QButtonGroup. `get()`/`set()` use the index, and `-1` means
  none. As with AppKit's radio-mode NSMatrix, the first title starts selected.
  Rows are 18/15/12 px (`regular`/`small`/`mini`), 2 px apart. A horizontal
  group splits the width equally.
- `RadioButton(posSize, title, value=False, callback=None)`: a standalone radio.
  It is not auto-exclusive, and clicking it always leaves it on, as in AppKit.
  It is not a push button, so `setDefaultButton` rejects it.
- `ComboBox(posSize, items, callback=None, continuous=False, completes=True)`:
  an editable QComboBox. `get()`/`set()` use the text, and it starts empty.
  `setItems()` replaces the choices and keeps the text. Typed text is never
  added to the list. The callback fires only for the user: a popup pick
  (`activated`) always fires it. With `continuous=True`, each keystroke fires it
  too (`textEdited`). Otherwise typed text fires it once per commit, on Return
  or on focus loss after an edit. Qt 5.15 emits `editingFinished` on every
  focus loss, so the line edit's `isModified()` flag gates the commit and is
  then cleared. Return on text that matches an item fires once, through Qt's
  own `activated`. `set()`, `setItems()` and a direct `setCurrentIndex()` never
  fire it.
- `TextEditor(posSize, text="", callback=None, readOnly=False, checksSpelling=False)`:
  a QPlainTextEdit. Every user edit fires the callback. `checksSpelling` is only
  recorded, because Qt has no spell checker here.
- `SquareButton` is a push `Button`. `HelpButton(posSize, callback=None)` is a
  push button titled `?`; `page`/`anchor` are unsupported.
- `ProgressBar(posSize, minValue=0, maxValue=100, isIndeterminate=False)`: the
  float value is clamped to the range and shown on a 0..`SLIDER_STEPS` Qt range.
  `set`, `increment(value=1)` and `get` work, and each update repaints so loops
  show progress. `start()`/`stop()` switch an indeterminate bar to Qt's busy
  indicator and back; on a determinate bar they do nothing.
- `Box(posSize, title=None)`: a QGroupBox that takes child controls like
  `Group`. Children are laid out inside a content widget placed on the box's
  `contentsRect()`, below the title. The content is refitted when the box is
  first shown (the style polish moves `contentsRect` below the title), on
  resize, and on `setTitle`. `setTitle`/`getTitle` work. `fillColor`, `margins` and similar raise.
- `List(posSize, items, columnDescriptions=None, ...)`: a QTableWidget with
  whole-row selection and no row numbers. Items are strings, or dicts keyed by
  each column's `key` (default: its `title`). Dicts are copied, so edits change
  the List's own dict, and `get()` returns those dicts. Column descriptions
  accept `title`, `key`, `editable` and `width`; `cell` and anything else raise,
  and so does `vanilla.CheckBoxListCell`. A column is editable when
  `editable=True`, or when `editCallback` is given and `editable` is unset.
  Editing a cell stores the text and fires `editCallback`. A double click fires
  `doubleClickCallback` only on a non-editable cell, because AppKit edits the
  cell instead. `selectionCallback` fires on user selection and on
  `setSelection()`, which vanilla also reports. `list[i]` and slices
  (`list[1:3]`) return items. `set`, `append`, `extend` and
  `remove` are silent. `enableDelete=True` lets Delete or Backspace remove the
  selected rows. `allowsEmptySelection=False` only selects row 0 at
  construction. `drawFocusRing=False` turns off the macOS focus rect. The graph
  records the columns and the item count, never the items.

## Runtime entry points (R006, R015, R033, R048)

`fontlab_glyport.run_script(path, profile="auto", font=None, options=None, host=None)`
and `install_plugin(bundle, ...)` return handles (`id`, `state`, `windows`,
`context`, snapshot `receipt`, `wrap`, `close`, `invalidate_document`; plugins add
`unload`). Profiles `glyphs2`/`glyphs3`/`glyphs4` are chosen from source/bundle
metadata unless given. The default FontLab host dispatches on the GUI thread, wires
the Vanilla provider and `fontlab_glyphsapp_provider`, and accepts an explicit
`OwnedPackage` font. Document invalidation is explicit: a host that binds a
workspace font can subscribe `DOCUMENTCLOSED` and call `handle.invalidate_document()`
(the default host binds only unregistered owned packages, which FontLab never
closes). Owned scripts get a scoped `subprocess.run` (explicit timeout, captured
text) and HTTP helpers with an overall deadline and cancellation; pyc files must
match the host's magic; ZIP entry points need `__main__.py[c]`.
`python -m fontlab_glyport verify --manifest MATRIX --native --output DIR` writes a
report and one private R018 receipt per row (`initial-regression` scope; corpus
targets stay blocked). Native drivers and details: `native-drivers/README.md`.

## Cocoa, Vanilla remainder and NIB/XIB (R029–R031)

- `vanilla.dialogs` (`ui/dialogs.py`): `message` (non-modal), `askYesNo`,
  `askYesNoCancel`, `getFile`, `getFolder`, `putFile`; results come from injected
  answers or, with `interactive=True`, a modal `exec()`; otherwise the call raises
  `UnsupportedCapability("vanilla.dialogs.<name>")` at the script line.
- `vanilla.Tabs` (QTabWidget pages) and `vanilla.Sheet` (window-modal child; the
  parent closes its sheets first). Native handles: `_nsObject`, `getNSTextField`,
  `getNSButton`, `getNSSlider`, `getNSPopUpButton` return Cocoa wrappers over the
  same widget; `EditText.nsTextFieldClass = objc.lookUpClass("GSSteppingTextField")`.
- `objc` (`ui/objc_bridge.py`): `python_method`, `IBOutlet`, `IBAction`, `super`,
  `selector`, `lookUpClass` (Qt-backed classes only), `error`,
  `nosuchclass_error`, `nil`, `YES`, `NO`. AppKit layer (`ui/cocoa*.py`): NSView
  (bottom-left frames, autoresizing), NSControl target/action, bindings `value`/
  `enabled`/`hidden`/`selectedIndex`, NSTextField, GSSteppingTextField, NSButton,
  NSSlider, NSPopUpButton, NSProgressIndicator, GSPaletteView, NSMenu/NSMenuItem.
- NIB/XIB (`ui/nib_archive.py`, `nib_graph.py`, `nib_loader.py`): both compiled
  NIB containers and XIB decode into the UI graph and instantiate with File's Owner,
  outlets, actions and bindings. Corpus: 78/78 XIBs and 103/103 NIBs decode;
  55/78 and 61/103 load with the current classes (NSImageView, NSStackView, NSBox,
  window templates and resources are not done).
- Widget lists from Qt (`findChildren`, `children`) go through App's
  `fontlabapp.qt.safe.qt_list` on the GUI thread (a garbage-collection race in
  list conversion crashed FontLab).

## Plugins and editor drawing (R025–R027, R032)

`GlyphsApp.plugins` has the seven SDK classes (`GeneralPlugin`,
`FilterWithoutDialog`, `FilterWithDialog`, `ReporterPlugin`, `PalettePlugin`,
`SelectTool`, `FileFormatPlugin`) bound to one plugin environment per execution
context; `plugins.loader.load_plugin` registers a class with FontLab
(`plugins/fontlab_host.py`: real menu QActions, tool windows for palettes and
dialogs, file-format export items, editor painters) and `unload()` removes every
registration deterministically. On FontLab builds with native canvas hooks
(`flCanvas.appendPythonPainter`, `flWorkspace.registerPythonTool`), backgrounds
paint under the outlines and `SelectTool` plugins become FontLab tools (see
"Native canvas painters and tools" below); older builds keep the R054 fallbacks
(background as overlay, no tools). `Glyphs.menu[EDIT_MENU].append(item)` registers through the same
host; the `*_MENU` constants are exported. Drawing (`drawing/`): NSColor,
NSBezierPath, NSAffineTransform, NSGraphicsContext, NSFont/NSAttributedString on
QPainter inside a paint scope; NSView `drawRect_` and mouse events; in the glyph
editor a transparent overlay paints after FontLab's own layer, mapped with the
native glyph and text-block transforms (< 1 px from the native outline).

`glyphsapp/fontlab_session.py` joins everything per execution context:
`FontLabPluginHost` gets a model adapter (selected layers, current font, layer
snapshot/restore, undo groups) and the editor painters a layer resolver, so
reporters and `Glyphs.addCallback(fn, DRAWFOREGROUND)` receive the model `GSLayer`
shown. `DRAWBACKGROUND` paints under the outlines through the native
`UnderOwner` painter; builds without `flCanvas.appendPythonPainter` fall back
to an overlay above them (R054). `install_plugin(bundle)` runs the
bundle and loads its principal class through `plugins.register_plugin` ->
`load_plugin`; `handle.unload()` removes it. `AppKit`/`Foundation`/`Cocoa` export
the Qt-backed classes, NS constants, menus, drawing and event names next to the
value types; unknown names still raise at the script line.

Host notes (issue 122). The generic parts of this host are App code:
`FontLabPluginHost` subclasses `fontlabapp.qt.menus.OwnedMenus`, and
`drawing.editor.EditorPainters` subclasses
`fontlabapp.qt.painting.editor.EditorPainters`. Glyport keeps only the Glyphs rules:

- Menus: only the `*_MENU` keys reach a FontLab menu (`PATH_MENU` is
  "Contour"). Every other name, including `FILTER_MENU`, `APP_MENU` and a
  literal title such as "Edit", goes to this host's own "Glyphs Plugins"
  menu. Each host keeps its own menu, even when two hosts are open at once.
  Registration is atomic: if the first NSMenuItem sync fails, the QAction and
  its token are removed before the error re-raises.
- Teardown waits for App's zero-delay timer; nothing is disconnected or
  deleted while one of the host's own signals dispatches. A filter dialog
  disconnects its Cancel/Apply buttons first (`_defer(first=True)`), before
  App closes and deletes the window. An error from `on_close(applied)` goes
  to the error sink with the plugin view as owner.
- A missing main window is App's `qtsafe.MainWindowNotFound`; the host raises
  `HostUnavailable`. The off-GUI-thread refusal stays a plain `RuntimeError`.
- Painters (overlay fallback): only the after-native-layer phase is supported;
  `before_native_layer` raises `UnsupportedCapability`
  (`FontLab.painter.before_native_layer`, R054). App wraps each paint body and
  ends the painter, so a painter exception goes to the sink, not to Qt.

Native canvas painters and tools (issue 201). `drawing.native_painters` keeps
App's registry, poll and per-glyph maths, and attaches two native painters per
glyph canvas: `UnderOwner` (Reporter `background`/`inactiveLayerBackground`,
`DRAWBACKGROUND`) and `OverOwner` (foregrounds). FontLab owns the painter; a
callback error goes to the sink. A `SelectTool` is registered with
`registerPythonTool`; `plugins.tool_bridge` maps press/move/release/double-click
to `mouseDown_`/`mouseDragged_` (button down) or `mouseMoved_`/`mouseUp_`/
`mouseDoubleDown_`, sets `Glyphs.currentEvent()`, and gives
`editViewController().graphicView()` with `activeLayer`, `scale`,
`getActiveLocation_` and `convertPoint_fromView_`. Differences: a mouse event is
claimed only when the plugin overrides the method; Glyphs' native select-tool
behaviour (`objc.super(...).mouseDown_`) is a no-op; keys reach `keyDown_`/
`keyUp_` but are never claimed, so FontLab shortcuts keep working; tools have
no toolbar icon yet; the tool's foreground/background paint only while it is
active. No bridge callback raises into FontLab: an error goes to the host sink
and the callback returns False (events) or None (activation). A refused
background falls back to an overlay with the R054 note, as for reporters.
During the tool's own paint `editViewController()` is built from the paint
context. `getActiveLocation_(None)` or a foreign event reads the live cursor;
`convertPoint_fromView_` returns viewport points, y up. Native check (FontLab
9.0.9802, HiDPI): event `localPos`, the painter device and the paint maths all
use logical viewport pixels (device height 428 = viewport height, device pixel
ratio 2, identity world transform).

Triage gap fixes (issue 201). `GlyphsApp.plugins` re-exports the SDK's
Foundation/AppKit/GlyphsApp names (`NSClassFromString`, `NSColor`, `Glyphs`,
`objc`, ...) that glyport provides; names glyport lacks stay absent, so `import *`
plugins fail at their first use. `ReporterPlugin.drawTextAtPoint` follows the SDK
(screen-point size at any zoom, nine alignment names, errors logged; refusals
still raise). `Foundation` adds `NSOffsetRect`/`NSPointInRect`; `GlyphsApp`
adds `NSStr`. `tab.view().window().windowController().toolDrawDelegate()` and
`.document()` resolve; FontLab's active tool is not readable, so the delegate
always reports the select tool (`isKindOfClass_(GlyphsToolSelect)` is true,
`dragging()` false). Anything beyond that chain (for example `view().frame()`)
still refuses. A reporter's `graphicView().getActiveLocation_(event)` uses a tool
event's point, else the live cursor mapped into the painted viewport;
`Glyphs.currentEvent()` is the tool event being handled, else a synthetic event
with the live `modifierFlags()` and the cursor in the active window's points,
y up (no active window: screen points; FontLab has no Cocoa event). `NSClassFromString("GlyphsToolSelect")` resolves to a marker
class, and `drawTextAtPoint` logs an unknown `align`. `NSContainsRect` is added; `NSScreen` reads QScreen geometry
through the PythonQt property. Text field cells report `isScrollable` and accept
`setScrollable_(True)` (a Qt line edit always scrolls; `False` on an edit field
refuses). vanilla `Window._window` gives only `contentMinSize`/`contentMaxSize`.

## Status

Implemented and verified (unreleased; details in CHANGELOG.md, evidence in the
workspace `verification/issue-101-ecosystem/evidence/`):

- Read-only `inspect_source`/CLI assessment over all 253 corpus bundles; receipt
  schema v1 and the typed error hierarchy (R015, R018).
- Glyphs 2 source adaptation into an owned cache with transformation IDs, hashes
  and line/column source maps (R016/R017).
- Scoped execution contexts: import scoping, module restore, output routing,
  callbacks and close hooks (R017).
- Live model first slice: probe-safe proxies, fake backend and the lazy FontLab
  backend; native reads and native mutation (width, paths, anchors, nodes) pass in
  an agent-owned FontLab session (R019–R022, partial).
- GlyphsApp host-services facade and FontLab GlyphsBridge: Output routing,
  UPDATEINTERFACE timer, status notifications, AskString/Message; native timer,
  redraw and close behaviour verified (R026, partial).
- Vanilla on Qt, slices 1–2: Window, FloatingWindow, Group, TextBox, EditText,
  Button, CheckBox, PopUpButton, Slider, lines, RadioGroup, ComboBox, TextEditor,
  Box, List and more, natively accepted on owned widgets (R028/R029, partial).

Implemented facilities include `run_script`/`install_plugin`, the `verify` CLI,
owned-font undo/redo and save/reopen, supported plugin protocols and Qt editor
drawing hooks. Acceptance is specific to the retained tests and native receipts,
not every source or protocol. Native Cocoa identity, scoped script/plugin imports
and four distinct original script pilots through both Cocoa backends passed in
FontLab 9.0.9783 at the preceding reviewed revision (76206df). The expanded script
matrix, final integrated regression, installed-artifact acceptance and release
checks remain outstanding. XIB/NIB translation remains incomplete.

### Cocoa backend selection

`activate(cocoa_backend="auto")` prefers real PyObjC on macOS and Qt elsewhere.
Use `activate(cocoa_backend="qt")` to force translation or `"native"` to require
macOS/PyObjC (missing dependencies raise). Scoped `run_script` and
`install_plugin` use `ExecutionOptions(cocoa_backend="native")` via `options=`.
Handles and their contexts expose `cocoa_backend` and `cocoa_fallback_reason`;
auto fallback reports why native imports were unavailable. All retained activation,
script and plugin handles must use the same backend request (`auto`, `native` or
`qt`). Close every retained handle and deactivate before changing that request,
even when an `auto` fallback happened to select Qt. Matching requests share the retained selection, including an `auto` fallback;
callbacks and unload hooks retain their chosen route until close. Conflicting
requests fail before publishing aliases or caller globals. Existing foreign
compatibility modules are refused.

The optional `cocoa` extra supplies `pyobjc-framework-Cocoa` on macOS only.
Install into your chosen Python environment yourself; Glyport never installs
packages into FontLab. Native imports use the original `objc`, `Foundation`,
`AppKit` and `Cocoa` modules, including lazy attributes and native class identity.
Forced Qt temporarily masks preloaded PyObjC modules and restores them on close
(or scope exit). Native modules are never given Qt names or loader metadata.

GlyphsApp models remain FontLab-backed; vanilla, menus, plugin hooks and drawing
bridges remain Qt-backed. Native NSView/NSColor objects are not automatically
converted to PythonQt widgets/colors: mixing them at those UI boundaries is
unsupported. Choose Qt for scripts requiring those bridges. Glyport starts no
NSApplication, QApplication or application-wide event loop. Close script-owned
native windows explicitly; Qt resource tracking does not own Cocoa windows.


## Issue120 P2: parseable legacy APIs

For a selected Glyphs2 route, otherwise Python3-parseable `.iteritems`,
`.iterkeys`, `.itervalues` and `.has_key` attribute loads now receive a tracked
source wrapper. Existing attributes are returned first, preserving native/custom
methods and descriptor failures. Only missing operations on a real dictionary
or dictionary class receive fallback behavior. Iteration is live; inherited
dictionary operations do not dispatch through an overridden modern items/keys/
values method. Receivers evaluate once and original arguments/errors propagate.

The execution scope adds Python2 aliases to its own builtins copy. It preserves
normal module/local/closure lookup, explicit user bindings, existing import/open
routing and Python's global builtins. Imported owned helpers receive that same
legacy scope. `adapt_source(...).compile()` is a compiler API; plain external
exec needs appropriate builtins, as before. Prefer the public run_script API.

Explicit Glyphs3/4 and unresolved auto profile behavior remains unchanged. A
real declared/selected Glyphs2 auto route receives the new behavior; no generation
is guessed from an arbitrary attribute name. Existing Python2-syntax conversion
remains on its prior fissix path and retains its semantic-review diagnostics.
This change does not claim a complete Python2 interpreter or new model/GUI APIs.

Generated helpers use a reserved name, diagnosed before cache publication on
source reference/binding conflicts. Original bytes/comments, encodings, f-string
syntax and source-map provenance remain retained. The pipeline version changes
the cache identity; old cached sources are not reused. Four real priority sources
were transformed/parsed only; none was compiled into executable code or run.
Their whole FontLab selection/UI/metrics/geometry workflows still require native
installed-artifact qualification through the dedicated owned-fixture runner.
