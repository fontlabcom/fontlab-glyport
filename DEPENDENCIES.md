---
this_file: DEPENDENCIES.md
---

## Conditional installer requirements

Only conditional installer requirements use `packaging==26.3` in an external uv-managed Python environment. FontLab itself imports only the standard library; no permanent project dependency was added. An unavailable helper fails before sibling execution.



Issue 235 adds `fontlab-python-pens` (import name `fontlab_pens`): a
zero-dependency, fontTools-compatible pen protocol for FontLab layers and
elements. `GSLayer.draw`/`getPen` and `correctPathDirection` take
`PointToSegmentPen`, `SegmentToPointPen`, `ReverseContourPointPen`, `AreaPen`
and `PointInsidePen` from it, so they no longer need fontTools. Other geometry
(`bezierTools`, bounds, segment area) still uses the fontTools resolver. The
package is unpublished: `[tool.uv.sources]` resolves the sibling checkout,
unpinned because its untagged hatch-vcs version is a dev release.

Issue 205 adds no dependency. Public import stays host-free. Pens, winding and
extrema reuse the existing public/private fontTools resolver; live overlap
removal reuses the existing optional `boolean` extra (`skia-pathops`). The base
gate skips its boolean-success case when that extra is absent; a second focused
run with `--with skia-pathops` verifies the actual combined contour and bounds.
# Dependencies

User-facing Scripts, launchers, authored native-driver payloads and current examples require `fontlab-fly>=1.3.0`. Supply reviewed Fly source on `PYTHONPATH` for source checks; isolated routing tests explicitly bootstrap that sibling and assert its origin. For extracted-archive checks without siblings, set `FONTLAB_FLY_SOURCE` to the reviewed `fontlab-fly/src` directory. Glyport runtime imports and package dependencies remain direct to avoid a Fly/Glyport dependency cycle. External Remopy transport continues to import its own client directly.

## Source-suite environment (Issue 250)

The workspace `.metaswarm/repos.sh` Glyport recipe requires arm64 Python 3.11,
pytest, pytest-cov, fontTools, fissix and glyphsLib, plus editable Glyport and
reviewed sibling `fontlab-fontlabapp` and `fontlab-python-pens` sources. Migration
tests read App's sibling alias oracle; an installed App alone does not supply
that source path. Use a fresh run-owned `TMPDIR` and writable uv cache. Incomplete
shared runtime-cache entries intentionally fail integrity checks: preserve the
old cache and select fresh temporary storage, without deleting or repairing it.
Set `QT_QPA_PLATFORM=offscreen`; standalone Qt does not qualify FontLab PythonQt.
Five HTTP/service tests require localhost TCP bind/connect permission. Sandbox
`EPERM` is an environment failure, not an absent optional dependency: rerun where
loopback is allowed without skipping these tests. Uncached dependencies also
require package-index network access.

No runtime dependency is needed for source-only inspection. Python stdlib
`ast`, `tokenize`, `plistlib`, `pathlib`, `hashlib` and `dataclasses` provide
parsing, encoded source reading, bundle metadata and immutable source facts.
Inspection neither executes corpus code nor imports native bindings.

R016/R017 source adaptation uses `fissix>=24.4.24` (R046 decision, 2026-10-14).
Evaluated its lib2to3-style concrete-syntax fixers against the owned print,
exception, exec, literal, dict and division fixtures. Selected fissix because
it preserves concrete syntax and supplies the established Python 2 grammar
without building a custom parser. The stdlib lib2to3 approach ties availability
to old interpreter releases; fissix is independently distributed and supports
the package's Python 3.11+ boundary. Its latest published release is 24.4.24;
release cadence is slow, so dependency updates need semantic regression tests.
See [official documentation](https://fissix.readthedocs.io/en/latest/) and
[release metadata](https://pypi.org/project/fissix/). Inspected the installed
`refactor.py`, `fix_dict.py`, `fix_unicode.py` and `fix_numliterals.py` before use.
Fissix's `appdirs` dependency locates its default grammar cache; Glyport instead
places grammar artifacts under the caller's owned cache. Fissix grammar/fixers
are loaded lazily for legacy syntax, with no host/UI bindings. The installed version is
part of `PIPELINE_VERSION`; changing the library invalidates adaptation caches.
Only integer dispatch, separated literal stages, cache publication and composed
provenance are custom code. No custom grammar or all-fixer sweep is used.

Hatchling and hatch-vcs provide wheel/sdist builds and Git-derived versions.
Pytest provides core, malformed-input, CLI and source-preservation tests.

Optional extra `native` (R046): `fontlab-remopy>=0.2`, the host-side MCP client
that `glyport verify --native` uses (`receipt_native._fontlab_client` imports it
lazily; without it the command fails with an install hint naming this extra).
fontlab-remopy is a workspace package and **not on PyPI**: install its wheel
(`uv pip install <workspace>/fontlab-remopy/dist/fontlab_remopy-*.whl`, or an
editable install of the checkout) before or together with
`fontlab-glyport[native]`. pyproject's `[tool.uv] override-dependencies` gives it
an always-false marker so uv's lock and `uv run`/`uv sync` never try to fetch it;
the wheel metadata still declares the extra. Remopy runs on the host side only,
never inside FontLab.

Planned native services are Echopy and Pythonqtside, with Remopy for
external acceptance orchestration. Add dependencies only when the implemented
runtime consumes them; avoid eager native imports at package import time.

Runtime dependency `glyphsLib>=6.16.1` supplies its maintained GlyphData database
for glyph category/subCategory, including live glyphs, suffixes and names absent
from the font. Direct named metadata and the shared glyph resolver have separate precedence:
explicit glyph refresh/reset resolves ordered encodings before name fallback.
The XML ships with the dependency;
glyport does not copy plugin-corpus files or maintain a guessed naming table.
Canonical Unicode decompositions give base/combining-mark component infos;
custom non-Unicode Glyphs construction recipes are not supplied by this data.
An incomplete installation raises `UnsupportedCapability` with
`GSGlyph.categories.dependency` or `Glyphs.glyphInfoForName.<name>` rather than
returning a plausible Unicode category (acute/grave are Glyphs Marks).
The older `glyphdata` extra name is retained for installer compatibility with
the same `glyphslib>=6.16.1` bound as the mandatory dependency. This aligns its
metadata; it adds no dependency and changes no runtime import route.
Imports and XML parsing remain lazy; no extra is required for normal package
installation. FontLab's sys.path launcher does not install dependencies. No automatic package
installation or public alias for private FontLab modules is performed.
See the [glyphsLib implementation](https://github.com/googlefonts/glyphsLib/blob/main/Lib/glyphsLib/glyphdata.py).

Optional extra `geometry` supplies public `fonttools>=4.38` for exact extrema via
[`BoundsPen`](https://fonttools.readthedocs.io/en/latest/pens/boundsPen.html).
Resolution prefers an importable `fontTools` module, then the bundled
`fontlab_private.fontTools` provided by FontLab 9 (4.39.4.FL_PRIVATE). The same
resolver handles Adobe glyph-name lookup when optional GlyphData needs it.
If neither route is available, nonempty detached bounds and sidebearing operations
raise `DetachedLayer.bounds.dependency`. Empty bounds and geometric component
decomposition need neither package. Boolean overlap removal remains a precise
refusal on nonempty detached geometry.

Round 8: optional `boolean` extra adds `skia-pathops` for detached-layer overlap removal. No compiled geometry dependency is required for base imports or model access; missing boolean support raises `DetachedLayer.removeOverlap.dependency`.

Round 19 also includes fontTools in the `test` extra so geometry regressions run
in a clean test installation. Runtime fontTools stays optional. The shared
resolver supplies Unicode Scripts data, exact italic spacing extrema, and
`PointInsidePen` for Cocoa nonzero/even-odd containment (including cubic curves).
Plugin-corpus code is not copied into Glyport. Audited scalar synthesis and
public Unicode data have their own documented provenance.

Optional `cocoa`: `pyobjc-framework-Cocoa>=11; sys_platform == "darwin"` supplies
AppKit/Foundation/Cocoa and depends on pyobjc-core (`objc`). Real module imports
preserve lazy framework resolution and native identity. Windows installs no
PyObjC dependency. No automatic installation or event-loop startup occurs.
Official bridge semantics: https://pyobjc.readthedocs.io/en/latest/core/intro.html
and https://pyobjc.readthedocs.io/en/latest/notes/framework-wrappers.html .
Controller owns real FontLab acceptance using an isolated scratch environment.

## App dependency: fontlab-fontlabapp

`pyproject.toml` `[tool.uv.sources]` resolves App as an editable install of the
sibling checkout `../fontlab-fontlabapp`, and `uv.lock` records that path. The
lock therefore works only inside the fontlab-scripting workspace (or a tree
with that sibling); a standalone clone must install a built App wheel instead.

Glyport requires `fontlab-fontlabapp>=1.2.10`. This one floor covers every
shared App module that Glyport imports; README.md "Shared App mechanics" lists
them with the policy that stays in Glyport. App imports no Glyport code, and
Glyport adds no optional import or duplicated fallback for App code. The App
modules use the standard library and injected Qt/FontLab handles only.

The 1.2.10 minimum declares the required App contract. The local sibling can
still have a genuine 1.1.x hatch-vcs version until its release is tagged; keep
the floor and report resolution failures. Never fabricate versions with SCM
pretend-version variables. Source tests do not establish registry availability,
native qualification or release acceptance.

`ui/session.py` (`VanillaSession`) is Apache-2.0 code that moved from App in
issue 122. NOTICE records its provenance; the Apache-2.0 LICENSE holds the licence
text. Both ship in the wheel and sdist.

## Lock and test commands

`uv.lock` is not refreshed. It resolves App from a removed local registry
under `.local/`, and a refreshed lock would point at another local path, so a
relock needs the owner's agreement. Explicit `--no-project` source checks and
ordinary artifact installation are the development routes; `sh test.sh` and frozen
sync do not establish the current closure. From this checkout, with reviewed App
source beside it, clear every inherited version fabrication:

```bash
for scm_name in $(env | sed -n 's/^\(SETUPTOOLS_SCM_PRETEND_VERSION[^=]*\)=.*/\1/p'); do
  unset "$scm_name"
done
PYTHONPATH=src uv run --no-config --python cpython-3.11-macos-aarch64-none --no-project \
  --with pytest --with fonttools --with fissix --with glyphslib \
  --with-editable ../fontlab-fontlabapp --with-editable . python -m pytest -q
```

Both packages are installed in uv's external test environment, so normal dependency
resolution enforces the App floor. `PYTHONPATH=src` also reaches test subprocesses.
For an ordinary install into a disposable external Python 3.11 arm64 environment,
provide the reviewed App and Glyport wheels together:

```bash
uv pip install --no-config --python "$CHECK_ENV/bin/python" "$APP_WHEEL" "$GLYPORT_WHEEL"
```

Set those paths to the external environment and reviewed artifacts. Do not bypass
dependencies or use overrides. The owner-managed FontLab environment is unchanged.
Use the writable external TMP/cache described in README.

The explicit `--no-config` routes ignore local/user uv configuration, including
legacy project overrides; normal dependency metadata still governs resolution.


## Shared Qt-list conversion — unreleased prerequisite

`fontlab-fontlabapp>=1.2.10` is required by the existing Glyport
`ui.qtsafe` import path. App supplies stdlib-only `fontlabapp.qt.safe.qt_list`;
Glyport retains its GUI-thread refusal before delegating. No optional import or
duplicated fallback is used. App restores the original GC state even when a
callback enables GC while the caller originally had it disabled; this is an
intentional strengthening of Glyport's former restoration behavior.

Use the genuine Git-derived App artifact described above. Supply it alongside
Glyport during ordinary dependency resolution; do not fabricate its version or
bypass dependencies. The historical local review lock is not a release lock.

## Unicode scalar lowercase data

The additional-Unicode resolver uses the bundled Unicode 17.0.0 single-scalar
lowercase map, rather than Python's interpreter-dependent `str.lower` data.
The 1,488 changed mappings combine UnicodeData field13 with unconditional
SpecialCasing lowercase entries, omitting identity mappings. Conditional and
localized string casing is outside this operation. The upstream operation reads
a single input scalar and the first scalar of its lowercase result.

Public inputs (Unicode License V3, included as LICENSE-UNICODE-3.0):

- [UnicodeData.txt](https://www.unicode.org/Public/17.0.0/ucd/UnicodeData.txt), SHA256 `2e1efc1dcb59c575eedf5ccae60f95229f706ee6d031835247d843c11d96470c`.
- [SpecialCasing.txt](https://www.unicode.org/Public/17.0.0/ucd/SpecialCasing.txt), SHA256 `efc25faf19de21b92c1194c111c932e03d2a5eaf18194e33f1156e96de4c9588`.

External calibration compares every 1,112,064 valid scalar against macOS27.2
NSString.lowercaseString and independently CFStringLowercase: all map entries
and identity results match. Python3.11/Unicode14 differs on55scalars. This pins
the measured casing contract; it does not establish equivalence to every older
or future Foundation version, or native FontLab/Glyphs workflow acceptance.
No Foundation/Objective-C bridge or new runtime package is introduced for casing.
The existing glyphsLib/fontTools metadata APIs do not expose this full mapping;
adding ICU solely for this operation would introduce a compiled dependency.


## Compound-name casing

`data/unicode17_casing.json.gz` packs1580full-uppercase mappings from those same
public Unicode17inputs and the category ranges used by the retained nonlocalized
Foundation name scan: Lu/Ll/Lt are cased; Mn/Me/Cf/Lm/Sk plus0027/2019 are
ignorable. This differs from modern Unicode Final_Sigma and is not locale casing.
Standard-library gzip/JSON/bisect load the pinned public resource lazily; no new
package or runtime native bridge is added. Surrogate pairs normalize through UTF16;
unpaired units and NUL survive. Current product functions match standalone
NSString in2228224whole-name probes and1114112uppercase probes, including2048
unpaired units, on Foundation5027.1.8/macOS27.2. Older/future Foundation versions
and native FontLab/Glyphs workflows need separate qualification.


## Public compound metadata resources

No new runtime package is added. Existing glyphsLib6.16.2public GlyphData.xml/
GlyphData_Ideographs.xml supply uniquely identified tag/script facts and public
glyph names; derived payloads pin both XML hashes. The glyphsLib distribution's
Apache-2.0 licence is retained by LICENSE and credited in NOTICE.
Unicode17ArabicShaping.txt supplies joining facts under LICENSE-UNICODE-3.0;
the unchanged source/notice is retained in tests/data for reproducible checks.
Only the independently checked retained R-versus-other predicate is supplied;
private resource completeness, arbitrary connection types and native/version
qualification remain separate. Runtime modules load only the pinned public JSON
resources, never a native Glyphs database. Fresh archive licence/payload checks
remain required when packaging is possible.

### Discovery source candidate

No package dependency added. The qualified macOS provider uses standard-library
ctypes/os/pathlib for SDK sys/xattr.h getxattr and Finder.h flags. CDLL(None) uses
the current process's OS symbols; no Foundation/objc library is imported. This
is OS-only metadata qualification, not native alias or Foundation-order parity.

Issue 201 archive successor: the sdist includes the owned deploy helper/template,
67 behavior-only oracles, the portable 67-target manifest and three unmodified
GetGo fixtures with upstream licenses and byte provenance. The frozen original
manifest remains source-only; only its two private provenance locations differ
in the portable successor. Offline helpers require no workspace; native execution
requires the real workspace and its safety runner. Wheel runtime is unchanged.
Verification results are retained separately; native/original-corpus acceptance remains open.

The complete Plum fixture adds CC0-1.0 to the project SPDX expression. Its
unmodified upstream CC0 license is at realuse/fixtures/getgo/cc0/LICENSE.txt;
Cafe and Gurmukhi retain their upstream Apache license and copyright metadata.

## Documentation build

The separate Python 3.13 docs environment uses `src_docs/requirements.txt`, with 31 exact hash-locked packages: ProperDocs 1.6.7, MkDocs 1.6.1, MaterialX 10.1.8 and PyMdown 11.0.1. Search is the only plugin. Light fltheme26 supplies one shared menu/footer. Runtime dependencies and uv.lock are unchanged. Host and ordinary artifact checks explicitly select arm64 CPython 3.11 and assert the actual architecture.
