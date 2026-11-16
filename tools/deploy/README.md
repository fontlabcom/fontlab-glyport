---
this_file: tools/deploy/README.md
---

# Deploy glyport into FontLab 9

The launcher requires `fontlab-fly>=1.3.0` in the chosen FontLab interpreter, alongside Glyport and its declared dependencies. Fly is not installed automatically.

FontLab runs any `.py` in its Scripts folder from the Scripts menu. This tool writes one
such file, `Glyport Launcher.py`, that loads glyport from this checkout:

```bash
uv pip install --python cpython-3.11-macos-aarch64-none --target .local/site311 "fissix>=24.4.24"
python3 tools/deploy/deploy_launcher.py --site .local/site311
```

The default target is `~/Library/Application Support/FontLab/FontLab 9/Scripts/`. The
tool refuses a same-named file it did not write (use `--force`), links, directories and
paths through the workspace's `fontlab-user-folder` link. Use an arm64 Python 3.11 for
the site directory (FontLab's interpreter); check compiled wheels with `lipo -archs`.

If glyport is already importable in FontLab (an editable install into
`~/Library/Application Support/FontLab/FontLab 9/python/3.11/site-packages`, e.g.
`uv pip install --link-mode=copy -e <checkout>` with fissix pulled in as its dependency),
`from fly import gp` works directly and the launcher is optional; deploy it with
`--installed` to get the menu entry without any path handling. Without `--installed`
the launcher always prefers its embedded `src` over an installed copy (used to test a
worktree while a different checkout is installed).

With the workspace packages installed that way, Fly's `gp` alias is the same module
object as `fontlab_glyport` (fontlab-fly README), so FontLab Python code can also call
glyport directly, without the launcher:

```python
from fly import gp  # == import fontlab_glyport (the installed copy)
handle = gp.run_script("/path/Script.py")  # auto: glyport decides (Glyphs 4 by default); "glyphs2" for Python 2
plugin = gp.install_plugin("/path/Plugin.glyphsReporter")
plugin.unload()
```

The launcher adds the Scripts-menu UI, picks the Glyphs 2 profile for Python 2 sources
automatically, keeps handles registered, and (without `--installed`) selects its
embedded checkout through Fly. Switching sources refuses while a launcher handle
is live or failed. Cleanup that leaves a handle active may be retried; a
terminal failed handle remains registered and reports unresolved cleanup on every
call, because a later no-op close does not prove its resources were released.
After all handles close successfully, reload clears only Glyport and its Fly
alias caches together.

In FontLab: Scripts > Glyport Launcher, then "Run a Glyphs script…", "Install a Glyphs
plugin bundle…" (choose the `.glyphsReporter`/`.glyphsFilter`/… folder) or "Unload all
glyport plugins". Python 2 sources run with the Glyphs 2 profile automatically.

From FontLab Python (what the native real-use harness does):

```python
exec(open(launcher_path).read(), {"GLYPORT_LAUNCHER_NO_UI": True})
launcher = sys.modules["_glyport_launcher"]
handle = launcher.run_script(
    "/path/Script.py", dependency_paths=["/path/with/helper/packages"]
)
plugin = launcher.install_plugin("/path/Plugin.glyphsReporter")
launcher.close_all()
```

`activate(reload=True)` re-imports glyport from `src` when no handle uses it (after
editing glyport). Tests: `tests/test_realuse_deploy.py`.
