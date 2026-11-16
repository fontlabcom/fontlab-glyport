---
this_file: src_docs/md/development-and-limits.md
---

# Development and limits

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

## Complete compatibility and provenance

All nine maintained guides remain available, including the full [compatibility catalogue](guides/COMPATIBILITY.md). Historical source/native/corpus counts retain their original denominators and qualifiers. Native Qt5/arm64 Python 3.11 FontLab behavior is separate from standalone Qt6 or Python 3.13 documentation checks. No provider, private database, native driver or original plugin corpus is executed or rendered by this site build. Private Pages configuration and publication remain owner-held.
