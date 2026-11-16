---
this_file: native-drivers/realuse/README.md
---

# Real-use matrix (issue 106)

Real Glyphs scripts and plugins from the read-only glyphs-plugins corpus, run inside
FontLab through the deployed launcher (`tools/deploy/`) on owned copies of GetGo VFJs.

- `select_targets.py --curation realuse/curation.json --output realuse/manifest.json`:
  static, read-only selection (rule in its docstring and in the manifest); records the
  coverage of the 50 most used Glyphs API names.
- `run_all.sh OUT_DIR [ID...]`: one `verification/issue-104/fl-native.sh --mutating`
  session per target; writes `<id>-<stamp>.json` and a log per attempt.
- `run_realuse.py`: one target. Scripts run through `run_script`, are driven through their
  own controls (`drive`), plugins through `install_plugin` and their protocol entry point
  (filter menu item and dialog Apply, reporter toggle and overlay paint, palette panel,
  general menu item, file-format export). Corpus code runs from FontLab's event loop, not
  inside run_python's 5 s deadline.
- Deadline and cancellation (review of 587db48): corpus code deferred to FontLab's event
  loop runs under a deadline (`deadline`, default 40 s). A watchdog thread then injects
  `TimeoutError` into the GUI thread, waits a 2 s grace period so cleanup (signal
  disconnects, closing widgets) can finish, and repeats every 0.75 s, at most 20 times
  (about 16 s; review M1 measured up to 33 injections to end a bare-except loop, so a few
  such loops are still reported stuck). If that does not end the code (it is in a nested event loop, a modal `exec()` or a long
  native call, so injections land elsewhere or nowhere), injection stops and the run is
  reported **stuck** (the last injection stays pending: clearing one is the CPython 3.11 hang below): the client raises HostStillBusy, skips every call into FontLab and
  exits 3; fl-native then writes `verification/issue-104/.host-busy` and refuses every lane
  (exit 79) until the controller checks or relaunches FontLab. A long native call, a modal
  dialog or a C++ loop cannot be interrupted by this at all; a stuck run needs a controller
  relaunch. The client waits for confirmed completion/cancellation (reconnecting only after
  transport errors, closing the failed session first, abandoned after 5 s) before it releases the host. Only
  remopy's `NativeExecutionError` counts as an in-host answer; every other error is
  transport. The client is marked busy before every scheduling call and cleared only after a
  confirmed finish; the exit code comes from that state (3 whenever busy, even if teardown or
  writing the receipt fails; scratch is then kept). An in-host error from a scheduling snippet
  is confirmed before it is raised, and `deferred(...)` is the last statement of every
  scheduling snippet. rc 4 means interrupted while FontLab was confirmed idle. Deadline and
  injection results are recorded per deferred step and asserted for every target kind.
- Hangs of 2026-10-16 (root cause, `verification/issue-106/evidence/glyport/hang-20261016-root-cause/`):
  `PyThreadState_SetAsyncExc(id, NULL)` on CPython 3.11 leaves the eval breaker set, and the
  next Python call under a trace function (FontLab's `run_python` wrapper always sets one)
  spins forever. The harness never clears an injection; a pending one is delivered by a
  Python call in a retried stop path. Injections and the escalation trace reach only the
  guarded snippet's frames (`in_region`). `run_realuse.py` exits with `os._exit` after
  flushing, so a deliberately unclosed busy session cannot hold the process in finalization.
- `realuse_common.py`: isolation (scratch HOME/defaults/cwd, dialogs answered from the
  manifest, never modal), FontLab-saved before/after VFJ diff (`auto_rebuilt` = FontLab's own
  auto-layer rebuild on display), Output traceback detection, R018 receipts, scrubbing of
  corpus source from evidence.

Curation keys per target: `fixture` (cafe, medi, plum-var, cosm-italic-var, hebrew, kufi,
armenian, gurmukhi), `tab`, `prepare` (lines of harness Python run on the owned copy before the "before" save; `font`, `layer` = glyport objects, `package` = the flPackage), `select_nodes`, `select_anchor`, `other_fonts`, `drive`
(`{"click": title|null}`, `{"check": title, "on": bool}`, `{"popup": n, "item": text}`,
`{"edit": n|label, "text": text}` (n-th visible field, or the field after a label), `{"wait": s}`), `expect`
(`change`: `"none"`/`"any"`/`{"glyphs", "kinds", "added", "font", "only"}`, `values`,
`output`, `tab`, `window`, `file`), `dialog_expect`, `answers`, `menu_item`, `classify_if`
(a controller-ruled classification for one exact failure), `purpose`.

Result oracles: `realuse/oracles/<id>.py` (see `realuse_oracle.py`); a target without one cannot
pass. Each run archives its oracle inputs to `<scratch root>/../artifacts/<id>-<stamp>.tar.gz`;
`reevaluate.py ARCHIVE` re-checks them with the current oracle code, host-side. Receipts carry
`oracle.verdict` (held/failed/missing); `report_table.py` shows it.

Evidence and tickets: parent workspace `verification/issue-106/evidence/glyport/`
(`realuse/`, `FIXES.md`), report `verification/issue-106/reports/G1-glyport-realuse.md`.
Tests: `tests/test_realuse_harness.py`.

Privacy (controller ruling, 2026-10-16): evidence never contains screen-level images. Don't use
`QScreen.grabWindow` or OS screenshots, even cropped to FontLab's window, because they can capture
the owner's desktop. Use only widget-level grabs (`widget.grab()`). Where those can't show the
natively painted canvas, record the step as skipped. Text that didn't come from the fixture or
the script (for example foreign text found in an owned tab) is redacted from receipts and kept
out of evidence and issues.
