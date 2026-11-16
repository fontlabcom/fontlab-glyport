---
this_file: src_docs/md/index.md
---

# Glyport


Run supported Glyphs scripts and plugins in FontLab with the `fontlab_glyport` Python package. Glyport adapts imports, selected Glyphs APIs, Python 2 source, plugin lifecycle and Cocoa/Vanilla UI routes. Unsupported capabilities raise explicit errors; complete Glyphs conformance remains open. User-facing examples require `fontlab-fly>=1.3.0` alongside Glyport and its declared dependencies. Fly shares the canonical provider modules; Glyport library code keeps direct imports to avoid a dependency cycle.

## Install

Host code targets Python 3.11 arm64; metadata permits Python 3.11+ externally. A terminal environment is not visible in FontLab.

Install the Glyport distribution and its matching reviewed App wheel with uv into the selected interpreter. Editable installation into FontLab is owner-managed.

Do not change FontLab's live environment without the owner's instruction; choose that interpreter explicitly. Installation includes `fissix>=24.4.24` `glyphslib>=6.16.1` and `fontlab-fontlabapp>=1.2.10`. Supply the genuine reviewed App release alongside Glyport. This does not imply registry availability or native acceptance. See DEPENDENCIES.md. GlyphData supplies named-glyph categories; imports and data loading stay lazy. A sys.path launcher does not install dependencies. Glyport never installs packages automatically. Optional extras, retained for existing installers:

| Extra | Purpose |
| --- | --- |
| `cocoa` | PyObjC Cocoa frameworks on macOS; install in the chosen host environment for the native route. |
| `geometry` | Public fontTools for exact bounds; FontLab's bundled private fontTools can also supply supported operations. |
| `boolean` | skia-pathops for detached-layer overlap removal. |
| `glyphdata` | Legacy installer name; retains the same glyphsLib minimum as the base package. |
| `native` | Host-side `verify --native` driver; requires the workspace's fontlab-remopy wheel, which is not on PyPI. |
| `test` | pytest and fontTools for source tests. |

See [DEPENDENCIES.md](https://github.com/fontlabcom/fontlab-glyport/blob/1f978bebc144754a369da0c684000479823c9276/DEPENDENCIES.md) for environment boundaries. Remopy runs externally.

## Ordinary Glyphs imports

Direct public imports expose the same 111 facade exports. Importing the package is lazy; first access builds one FontLab GUI-thread session (`glyphs4`). If using both entry points, call `activate()` first to share its exact objects; activation after an independent public binding is refused until `gp.GlyphsApp.unbind()` releases it. `dir(gp.GlyphsApp)` lists exports without binding a host. Through Fly, use `from fly import gp; gp.GlyphsApp.Glyphs`.

```python
from fly.gp.GlyphsApp import Glyphs, GSPath, GSNode
from fly.gp.GlyphsApp.plugins import GeneralPlugin
layer = Glyphs.font.selectedLayers[0]
layer.beginChanges()
try:
    layer.decomposeComponents()
    layer.correctPathDirection()
    layer.addNodesAtExtremes()
finally:
    layer.endChanges()
```

Outside FontLab, call `import fly.gp.GlyphsApp as gs; gs.use_backend(backend, profile="glyphs4")` before accessing exports (tests use `FakeBackend` from `fontlab_glyport.model.fake_backend`). Otherwise access raises `HostUnavailable`. Binding cannot replace a live session. Offline plugin exports are base classes; install via `install_plugin()` to supply their environment. `gs.unbind()` closes and forgets an independent default session/backend; activation handles retain their own cleanup.

Live layers also support `removeOverlap(checkSelection=False)` (existing `boolean` extra), `getPen()`, `getPointPen()`, `draw(pen)` and `drawPoints(pointPen)`. The pens use existing public/private fontTools; use `with layer.getPen() as pen:` or call `pen.doneDrawing()` to finish one Undo step spanning its contours. `font.save(path=None, formatVersion=None, makeCopy=False)` saves its native document by font ID to `.vfj`/`.vfc`; an unsaved font needs a path. Copies retain the original filepath; non-None `formatVersion` is refused. `font.close()` refuses unsaved edits unless `ignoreChanges=True` is explicit. Finish pending Undo groups first. FakeBackend saves first-master UFOs. See [public API contracts and limits](guides/COMPATIBILITY.md#issue-205--direct-public-api-and-live-outlines), including separate native verification requirements.

On FontLab's GUI thread, put activation after any `from __future__` statements:

```python
from fly import gp; gp.activate()
from GlyphsApp import *
import AppKit, Foundation, vanilla
```

Activation supplies supported globals, including `Glyphs` and a snapshot `Font`, to the caller. Use `activate(namespace=globals())` to select that namespace. Conflicting globals or foreign compatibility modules are refused. The default profile is `glyphs4`; select `profile="glyphs3"` or `"glyphs2"` as needed. These describe compatibility behavior, not full Glyphs support. Retain callbacks/windows while needed, then call `gp.deactivate()` or `handle.close()`. Cleanup is idempotent; close every handle before changing the Cocoa backend.

## Public model additions

The facade exports SDK constants (including `GSRTL=RTL=2`, `GSBIDI=BIDI=1`,
`MOVE` and `GSGuideLine`). Constants name SDK vocabulary; unsupported operations
still refuse explicitly. Plugin base classes import outside FontLab without
binding a backend. See the [support matrix](guides/COMPATIBILITY.md).

`GSFont()` creates an empty detached in-memory font; fill its masters and glyphs
and save a first-master UFO. It is never silently registered in FontLab.
`GSFontMaster()` creates a detached master accepted by in-memory font storage;
native master append explicitly refuses creation. Live font/master metadata,
node types, anchor names and component transforms use guarded writes and one
nested Undo group. `GSPath.reverse()` supports live and detached paths.
`layer.selection = [...]` and `clearSelection()` cover nodes, anchors, components
and guides in memory. Native selection supports nodes/components. Selecting an
unsupported anchor/guide refuses; clearing or replacing supported selection
skips those kinds, whose selection state cannot be observed or changed.
`GSInstance.interpolatedFont` remains an explicit refusal. The optional SDK audit
uses `GLYPHS_SDK_PATH` (SDK root or wrapper file) and skips when it is unset.

## Cocoa backend selection

`activate(cocoa_backend="auto")` prefers native PyObjC on macOS and Qt on Windows and other platforms. `"native"` requires macOS and available PyObjC; `"qt"` forces translation. Handles and execution contexts expose `cocoa_backend` and `cocoa_fallback_reason`, including an auto-fallback reason. Scoped `run_script` and `install_plugin` accept the same request through `ExecutionOptions(cocoa_backend="qt")` via `options=`. Concurrent retained handles must use the same request, even when auto selected Qt. Forced Qt masks preloaded PyObjC modules only for the owned scope and restores them on close. Glyphs models remain FontLab-backed. Vanilla, menu/plugin hooks and drawing bridges remain Qt-backed. Native NSView/NSColor objects are not automatically converted into PythonQt widgets/colors; choose Qt for scripts needing those bridges. Glyport starts no application-wide event loop. Close script-owned native Cocoa windows yourself.

## Vanilla session
`fontlab_glyport.ui.session.VanillaSession` owns the Qt Vanilla and dialogs namespaces and their windows (context manager; `close()` is idempotent). Importing it loads no PythonQt, Cocoa or Vanilla chain (5 s `run_python` deadline); the constructor does. Native steps: `native-drivers/vanilla_steps.py`.

## Inspect and run
```python
from fly.gp import run_script
with run_script("OriginalScript.py", profile="glyphs3") as handle:
    receipt = handle.receipt
```

Run on FontLab's GUI thread; retain a handle for modeless UI, then close it. Inspection reads source/bundles without execution or modification. It records hashes, imports, entrypoints, capabilities and unresolved dependencies. An assessment is not an execution pass.

```python
from fly.gp import inspect_source
assessment = inspect_source("OriginalScript.py")
print(assessment.required_capabilities)
```

The `glyport inspect` CLI accepts a source path and an optional JSON report path.

The CLI refuses to overwrite an existing report. `adapt_source` preserves original bytes and writes Python 2 transformations/source maps to an owned cache. It is source adaptation with explicit semantic limits. `run_script(path, ...)` and `install_plugin(bundle, ...)` return owned handles with context, receipt and close/unload methods. Execution scopes restore owned imports and output routes; they are cooperative scopes, not security sandboxes. The [compatibility guide](guides/COMPATIBILITY.md) describes model operations, receipts, callbacks, Vanilla controls, NIB/XIB loading and plugin protocols. [Native drivers](https://github.com/fontlabcom/fontlab-glyport/blob/1f978bebc144754a369da0c684000479823c9276/native-drivers/README.md) document owned-fixture verification.

## Compatibility limits and evidence

Support is specific to tests, native builds and retained receipts. Native checks exist for selected model, script, Cocoa/Qt and UI workflows; the expanded script/plugin matrix and final release acceptance remain open. Offline tests do not prove native compatibility. Unknown APIs raise typed errors such as `UnsupportedCapability`; closed-font handles raise `StaleNativeObject`. Known limits include incomplete NIB/XIB translation, unsupported SelectTool/background painting paths, Qt/native UI mixing, and host-specific Undo/Redo or save/reopen behavior. Direct native writes recheck App history ownership before mutation and publication. Use the matching current Font window for font metadata, master writes, creation, deletion and rename; Undo there. Existing glyph edits keep App's shown-owner and single-current-glyph fallback. A focus refusal retains earlier pending work: return to the matching Font window and retry `endChanges()`/`endUndo()`. Earlier edits are not rolled back automatically. Kerning tool history remains separate, with additional metadata/history limits. Read the [model and protocol notes](guides/COMPATIBILITY.md) before editing fonts; complete native Undo/Redo and saved/reopened acceptance remains open. Historical counts in that guide are not a current corpus-wide pass rate.

## Shared App mechanics

Glyport needs `fontlab-fontlabapp>=1.2.10` (one floor; see DEPENDENCIES.md). App owns the generic Qt and FontLab mechanics below; Glyport keeps every Cocoa, Vanilla and Glyphs policy. Native qualification of each row remains separate.

| App module | Purpose | What stays in Glyport |
| --- | --- | --- |
| `contours.affine` | Six-number affine helpers | Glyphs drawing context |
| `qt.painting.editor` | Glyph-editor painter registry, `PaintContext` | Glyphs phases and the `before_native_layer` refusal |
| `qt.menus` | Owned menu actions, tool windows, deferred teardown | Glyphs menu names, NSMenuItem sync, Apply/Cancel dialog |
| `qt.colors` | Shared Qt colour conversion | Cocoa and Vanilla colour adapters |
| `qt.safe` | GC-safe widget lists; `main_window`, `MainWindowNotFound` | `HostUnavailable` mapping, NSApp proxies |
| `core.edit_guards` | History ownership, matching Font window and queue disclosure | Prospective Glyphs owners, retained batches and retry/recovery policy |
| `qt.dialogs` | Owned dialog execution, message boxes, file filters | Answer injection, Glyphs dialog values and errors |
| `core.native_tabs` | Native tab sender and activation | Empty-tab text, source font, capability errors |
| `core.signals.callbacks` | Nested callback suppression | Cocoa/Vanilla callback policy |
| `core.signals.connections` | Exact signal/slot tracking and reverse teardown | Callbacks and owner cleanup |
| `qt.events.key` | Handled-key routing | Foreign keys, values and callbacks |
| `qt.events.resize` | Resize forwarding | Window and view frames |
| `qt.layouts.content` | Contents-rectangle fitting | Box title, style and child relayout |
| `qt.layouts.linear` | Required/weak linear layout equations | Vanilla auto-layout parsing and errors |
| `qt.layouts.stack` | Stack distribution arithmetic | NSStackView orientation, insets, hidden views |
| `qt.images.resources` | Image lookup, retina selection, rendering | NSImage/NSCursor APIs |
| `qt.images.view` | Image fitting and QLabel presentation | NSImage enums, Vanilla image policy |
| `qt.numeric` | Integer ranges and proportional setters | Clamping, ticks, exact values, busy/repaint |
| `qt.properties` | Known Qt property reads | Known property names |
| `qt.choices` | Editable-choice setup, commit once | Callbacks, conversion, lifetime |
| `qt.tables.items` | Qt text/checkbox table rows | Columns, binding, callbacks, quiet scopes |
| `qt.tables.selection` | Model-row and table-range selection | Cocoa/Vanilla bounds, bindings, dispatch |
| `qt.ui_graph` | UI node graph and serialization | Frame parsing and adapters |

## Module map

| Path in `src/fontlab_glyport/` | Responsibility |
| --- | --- |
| `bootstrap.py`, `entrypoints.py`, `execution.py` | Activation, script/plugin handles, owned execution |
| `inspection.py`, `assessment.py`, `bundles.py`, `cli.py` | Source/bundle facts and command-line reports |
| `adaptation*.py`, `_py2.py` | Source adaptation, cache identity and source maps |
| `glyphsapp/`, `model/` | Glyphs globals, font proxies, FontLab backend and offline fake backend |
| `ui/`, `cocoa_backend.py`, `foundation*.py` | Cocoa/Vanilla adapters, NIB/XIB loading, session lifetime |
| `plugins/`, `drawing/`, `notifications.py` | Plugin registration, menu hooks, painter adapters, callbacks |
| `receipt*.py`, `_receipt*.py` | Execution evidence, validation and native verification |

General UI belongs in `fontlabapp`; fontParts/UFO code belongs in Fontport. Glyport keeps Glyphs compatibility, including Cocoa/Vanilla emulation. New FontLab scripts use App through Fly (`from fly import ap`).

## Development

Tests run outside FontLab and include doubles. Native acceptance separately requires owned fonts/widgets and saved/reopened artifacts. `uv.lock` refers to a removed local registry; `test.sh` follows that lock. Use explicit sources.

Set `FONTLAB_SCRATCH` to a writable external-drive folder first. The recipe creates TMP/cache directories there. Use a separate cache for this dependency set; if App metadata is stale, select a fresh cache. The arm64 CPython 3.11 interpreter must be installed. Reviewed App and Fly sources must be at `../fontlab-fontlabapp` and `../fontlab-fly`. Network is needed for uncached dependencies. Clear every inherited `SETUPTOOLS_SCM_PRETEND_VERSION*` variable using the loop in DEPENDENCIES.md. Both packages install editable externally with normal resolution of genuine Git versions. FontLab's live environment is not changed.

```bash
: "${FONTLAB_SCRATCH:?Set FONTLAB_SCRATCH to a writable external-drive folder}"
export TMPDIR="$FONTLAB_SCRATCH/tmp" UV_CACHE_DIR="$FONTLAB_SCRATCH/glyport-cache"
mkdir -p "$TMPDIR" "$UV_CACHE_DIR" || exit 1
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="src:../fontlab-fly/src" uv run --no-config --python cpython-3.11-macos-aarch64-none --no-project --with pytest --with fonttools --with fissix --with glyphslib --with-editable ../fontlab-fontlabapp --with-editable . python -B -m pytest -q -p no:cacheprovider
```
Docs checks:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="src:../fontlab-fly/src" uv run --no-config --python cpython-3.11-macos-aarch64-none --no-project --with pytest --with fonttools --with fissix --with glyphslib --with-editable ../fontlab-fontlabapp --with-editable . python -B -m pytest -q -p no:cacheprovider tests/test_*docs.py tests/test_*distribution.py
```

Lint requires Ruff on PATH:

```bash
ruff check --no-cache --output-format concise src tests native-drivers
```

The cold-import child uses `python -I`; a PYTHONPATH entry alone cannot supply App. Without GLYPORT_DISTRIBUTION_DIR, three archive checks skip. For archive checks, first build one fresh wheel and sdist in an external directory with uv's build command; set GLYPORT_DISTRIBUTION_DIR to that directory and repeat the docs checks. Do not reuse archives after changing source or packaged documentation. Ruff currently reports 26 findings; fixes remain open.

The wheel retains runtime APIs and the test backend. The sdist includes tests, native drivers, licenses and the compatibility guide. No original plugin corpus ships. Glyport is Apache-2.0; NOTICE records bundled data and upstream licences. Selected `glyphs2` execution supplies isolated Python 2 builtin aliases (xrange/unichr/unicode/basestring/long). Parseable legacy dictionary attribute loads use a runtime fallback that preserves existing custom/native methods; other profiles are unchanged. Use `run_script(..., profile="glyphs2")`; compiling adapted text alone does not install execution builtins.

[Scripts demos](https://github.com/fontlabcom/fontlab-glyport/blob/768e0f8ddb345b310664cee415157060337772a1/Scripts/README.md) use detached sample data, with host-free `build_report()` results and optional FontLab report windows through Fly/App. No open font is required.
