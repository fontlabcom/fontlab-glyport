#!/usr/bin/env python3
# this_file: native-drivers/realuse/run_realuse.py
"""Run real-use targets from realuse/manifest.json inside FontLab (issue 106).

    verification/issue-104/fl-native.sh --mutating --lane G1 -- \
        uv run --quiet --project fontlab-remopy python native-drivers/realuse/run_realuse.py \
        --manifest realuse/manifest.json --out EVIDENCE_DIR ID [ID...]

Each target writes ``<id>-<stamp>.json`` (clauses, data, calls, an R018
receipt). Scripts run through the deployed launcher's ``run_script``; plugins
through ``install_plugin`` and are then exercised by protocol. See
realuse_common.py for isolation and the before/after VFJ diff.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import signal
import sys
import time
import traceback
from pathlib import Path
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))

import realuse_oracle
from realuse_common import (
    COMMON,
    CORPUS,
    Run,
    diff_samples,
    layer_of,
    require_workspace,
    vfj_diff,
)

SCRATCH = Path(
    "/private/tmp/claude-501/-Users-adam-Developer-vcs3-github-fontlabcom-fontlab-scripting/"
    "3552ca38-1012-44d4-a62f-de71226398d8/scratchpad/g1/runs"
)


def png_1x1() -> bytes:
    """A valid 1x1 opaque black PNG (owned fixture bytes for image-import scripts)."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    pixels = zlib.compress(b"\x00\x00\x00\x00\xff")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", pixels)
        + chunk(b"IEND", b"")
    )


ERROR_INFO = r"""
def error_info(error):
    import traceback
    from pathlib import Path
    frames = []
    for f in traceback.extract_tb(error.__traceback__):
        p = Path(f.filename)
        name = "/".join(p.parts[p.parts.index("fontlab_glyport"):]) if "fontlab_glyport" in p.parts else p.name
        frames.append(f"{name}:{f.lineno} in {f.name}")
    return dict(error=type(error).__name__, message=str(error)[:500],
                capability=getattr(error, "capability", None), frames=frames[-8:])
def profile_of(h):  # the Glyphs profile glyport resolved for this run (receipt)
    return getattr(getattr(h, "_assessment", None), "profile", None)
def outputs(h):
    ctx = getattr(h, "context", None)
    return list(ctx.output.strings) if ctx is not None and hasattr(ctx.output, "strings") else []
"""

RUN_SCRIPT = (
    COMMON
    + ERROR_INFO
    + r"""
L = sys.modules["_glyport_launcher"]
st.before_run = {id(w) for w in windows()}
st.run_out, st.handle = {}, None
def go():
    try:
        st.handle = L.run_script(path, dependency_paths=deps)
        st.run_out["state"] = st.handle.state
    except BaseException as error:
        st.handle = getattr(error, "handle", None)
        st.run_out.update(error_info(error))
deferred(go)
result = True
"""
)

RUN_COLLECT = (
    COMMON
    + ERROR_INFO
    + r"""
out = st.run_out  # read-only: never pump (queued corpus code runs only via deferred)
st.run_windows = [w for w in windows() if id(w) not in st.before_run]
texts = outputs(st.handle)
out.update(windows=describe(st.run_windows),
           output=[t.strip()[-300:] for t in texts if t.strip()][-10:],
           output_errors=errors_in(texts), dialogs=list(st.dialog_log),
           timed_out=st.deferred_timed_out, injections=st.deferred_injections,
           profile=profile_of(st.handle))
result = out
"""
)

DRIVE_STEP = (
    COMMON
    + ERROR_INFO
    + r"""
import time
if not hasattr(st, "drive_out"):
    st.drive_out = {"steps": []}
out = st.drive_out
wins = [w for w in st.run_windows if live(w)]
def buttons():
    return [b for w in wins for b in qtlist(w.findChildren, QtGui.QPushButton) if b.isVisible()]
def find(kind, title):
    for w in wins:
        for b in qtlist(w.findChildren, kind):
            if b.isVisible() and b.text.replace("&", "") == title:
                return b
    return None
deferred_reset(done=True)
step = drive_step
out["buttons"] = [b.text for b in buttons()][:20]  # before deferred(): it must come last (M3)
if "click" in step:
    title = step["click"]
    if title is None:
        candidates = [b for b in buttons() if b.isDefault()] or [b for b in buttons()
                      if b.text.replace("&", "") not in ("Cancel", "Close", "Help", "?", "")]
        b = candidates[-1] if candidates else None
    else:
        b = find(QtGui.QPushButton, title)
    out["steps"].append(["click", title, None if b is None else b.text])
    if b is not None:
        deferred(b.click)  # the button's callback may run longer than run_python allows
elif "check" in step:
    b = find(QtGui.QCheckBox, step["check"])
    out["steps"].append(["check", step["check"], None if b is None else b.isChecked()])
    if b is not None and b.isChecked() != step.get("on", True):
        deferred(b.click)  # its callback runs under the in-FontLab deadline (M5)
elif "edit" in step:  # type into a text field: the n-th visible one, or the one after a label
    fields = [e for w in wins for e in qtlist(w.findChildren, QtGui.QLineEdit) if e.isVisible()]
    e = None
    if isinstance(step["edit"], int):
        e = fields[step["edit"]] if step["edit"] < len(fields) else None
    else:
        for w in wins:
            for label in qtlist(w.findChildren, QtGui.QLabel):
                if label.isVisible() and label.text.strip() == step["edit"]:
                    kids = qtlist(label.parent().children)
                    after = kids[kids.index(label) + 1:] if label in kids else []
                    e = next((k for k in after if isinstance(k, QtGui.QLineEdit) and k.isVisible()), None)
                    break
            if e is not None:
                break
    out["steps"].append(["edit", step["text"], None if e is None else e.text])
    if e is not None:
        deferred(lambda: e.setText(step["text"]))  # textChanged callbacks: deadline (M5)
elif "popup" in step:  # choose an item (by text) in the n-th visible pop-up button
    combos = [c for w in wins for c in qtlist(w.findChildren, QtGui.QComboBox) if c.isVisible()]
    c = combos[step["popup"]] if step["popup"] < len(combos) else None
    items = [c.itemText(i) for i in range(c.count)] if c is not None else []
    index = next((i for i, t in enumerate(items) if step["item"] in t), None)
    out["steps"].append(["popup", step["item"], items[index] if index is not None else None])
    if index is not None:
        deferred(lambda: c.setCurrentIndex(index))  # the callback runs from the event loop
elif "wait" in step:  # let the UI run, under the deferred watchdog
    def idle(seconds=float(step["wait"])):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            pump(); time.sleep(0.05)
    deferred(idle)
result = True
"""
)

DRIVE_COLLECT = (
    COMMON
    + ERROR_INFO
    + r"""
out = st.drive_out  # read-only
texts = outputs(st.handle)
out.update(output=[t.strip()[-300:] for t in texts if t.strip()][-10:],
           output_errors=errors_in(texts), dialogs=list(st.dialog_log),
           timed_out=st.deferred_timed_out, injections=st.deferred_injections)
result = out
"""
)


def drive(run: Run, steps: list, prefix: str = "") -> dict:
    for index, step in enumerate(steps):
        # the prefix may use COMMON's helpers (windows()): it goes after COMMON
        code = COMMON + prefix + DRIVE_STEP[len(COMMON) :]
        run.call_deferred(f"drive-{index}", code, drive_step=step)
    time.sleep(SETTLE_PAUSE)  # let FontLab's own event loop show the result
    return run.call("drive-collect", DRIVE_COLLECT)


SETTLE = (
    COMMON
    + ERROR_INFO
    + r"""
# read-only: the client waited `wait` seconds before this call (no pumping here)
from fly.gp.model import Model
from fly.gp.model.fontlab_backend import FontLabBackend
pkg = fontlab.flWorkspace.instance().findPackageId(font_id)
font = Model(FontLabBackend(packages=[pkg])).fonts[0]
try:
    tab = font.currentTab.text if font.currentTab is not None else None
except Exception as error:
    tab = "unreadable: " + repr(error)[:200]
texts = outputs(st.handle)
result = dict(tab=tab, output=[t.strip()[-300:] for t in texts if t.strip()][-10:], output_errors=errors_in(texts),
              text="".join(texts)[-20000:],  # whole Output for result oracles
              windows=describe([w for w in windows() if id(w) not in st.windows_before]),
              dialogs=list(st.dialog_log))
"""
)

SETTLE_PAUSE = 0.3  # client-side pause: FontLab's own event loop shows results


def settle(run: Run, wait: float, code: str = SETTLE) -> dict:
    """Let FontLab run its own event loop for ``wait`` s, then read state. The
    request never pumps: queued corpus code runs only through deferred()."""
    time.sleep(max(wait, SETTLE_PAUSE))
    return run.call("settle", code, font_id=run.font_id, wait=wait)


INSTALL_START = (
    COMMON
    + ERROR_INFO
    + r"""
L = sys.modules["_glyport_launcher"]
st.menus_before = menu_titles()
st.install_before = {id(w) for w in windows()}
st.install_out, st.handle = {}, None
def install():  # plugin settings()/start() are corpus code: deferred, under the watchdog
    try:
        st.handle = L.install_plugin(bundle)
        st.install_out["state"] = st.handle.state
    except BaseException as error:
        st.handle = getattr(error, "handle", None)
        st.install_out.update(error_info(error))
deferred(install)
result = True
"""
)

INSTALL_COLLECT = (
    COMMON
    + ERROR_INFO
    + r"""
out, h = st.install_out, st.handle  # read-only
after = menu_titles()
st.new_items = {m: [t for t in items if t not in st.menus_before.get(m, [])] for m, items in after.items()}
st.new_items = {m: t for m, t in st.new_items.items() if t}
texts = outputs(h)
plugin = getattr(h, "plugin", None)
out.update(menu_items=st.new_items, windows=describe([w for w in windows() if id(w) not in st.install_before]),
           plugin=type(plugin).__name__ if plugin is not None else None,
           output_errors=errors_in(texts), dialogs=list(st.dialog_log),
           timed_out=st.deferred_timed_out, injections=st.deferred_injections,
           profile=profile_of(h),
           registration=[e for s in getattr(h, "_stages", ()) if s.name == "registration" for e in s.evidence])
result = out
"""
)


def install(run: Run, bundle: str) -> dict:
    run.call_deferred("install", INSTALL_START, bundle=bundle)
    time.sleep(SETTLE_PAUSE)
    out = run.call("install-collect", INSTALL_COLLECT)
    run.profile = out.get("profile")
    return out


TRIGGER_START = (
    COMMON
    + r"""
st.before_trigger = {id(w) for w in windows()}
action = menu_action(menu, title)
st.trigger_found = action is not None
deferred_reset(done=True)
if action is not None:
    deferred(action.trigger)  # filters on whole layers may outlast run_python's 5 s
result = True
"""
)

TRIGGER_COLLECT = (
    COMMON
    + ERROR_INFO
    + r"""
out = dict(found=st.trigger_found)  # read-only
st.trigger_windows = [w for w in windows() if id(w) not in st.before_trigger]
texts = outputs(st.handle)
out.update(windows=describe(st.trigger_windows), output_errors=errors_in(texts),
           output=[t.strip()[-300:] for t in texts if t.strip()][-6:], dialogs=list(st.dialog_log),
           timed_out=st.deferred_timed_out, injections=st.deferred_injections)
result = out
"""
)


def trigger(run: Run, step: str, title: str | None) -> dict:
    if not title:
        return {}
    run.call_deferred(step, TRIGGER_START, menu=None, title=title)
    time.sleep(SETTLE_PAUSE)
    return run.call(step + "-collect", TRIGGER_COLLECT)


APPLY_START = (
    COMMON
    + ERROR_INFO
    + r"""
wins = [w for w in st.trigger_windows if live(w)]
buttons = [b for w in wins for b in qtlist(w.findChildren, QtGui.QPushButton) if b.isVisible()]
apply = [b for b in buttons if b.text.replace("&", "") not in ("Cancel", "")]
st.apply_out = dict(buttons=[b.text for b in buttons], applied=apply[-1].text if apply else None)
# Only the filter's own dialog counts as "still open": FontLab may raise or create a
# document frame window ("FontLab: ...") during the trigger (p-dottype, round 19).
st.apply_wins = [w for w in wins if not (w.windowTitle or "").startswith("FontLab:")]
deferred_reset(done=True)
if apply:
    deferred(apply[-1].click)  # the filter runs under the watchdog
result = True
"""
)

APPLY_COLLECT = (
    COMMON
    + ERROR_INFO
    + r"""
out = st.apply_out  # read-only
texts = outputs(st.handle)
out.update(open_after=[w.windowTitle for w in st.apply_wins if live(w)], output_errors=errors_in(texts))
result = out
"""
)


def apply_dialog(run: Run) -> dict:
    run.call_deferred("apply", APPLY_START)
    time.sleep(SETTLE_PAUSE)
    return run.call("apply-collect", APPLY_COLLECT)


PAINT_START = (
    COMMON
    + ERROR_INFO
    + r"""
import time
def capture():  # painting calls the reporter's drawing code: deferred, under the watchdog
    session = st.handle.context.fontlab_session
    painters = session.painters
    for overlay, viewport, canvas, _ in list(painters.overlays.values()):
        overlay.update()
    end = time.monotonic() + 0.6
    while time.monotonic() < end:
        pump(); time.sleep(0.05)
    ink = []
    for overlay, viewport, canvas, _ in list(painters.overlays.values()):
        image = overlay.grab().toImage()
        w, h = image.width(), image.height()
        stride = max(3, int((w * h / 40000) ** 0.5) + 1)  # at most ~40,000 samples (L12)
        n = 0
        for y in range(0, h, stride):
            for x in range(0, w, stride):
                if QtGui.QColor(image.pixel(x, y)).alpha() > 0:
                    n += 1
        ink.append(n)
    st.paint_out = dict(painters=len(painters.painters), overlays=len(painters.overlays), ink=ink)
st.paint_out = {}
deferred(capture)
result = True
"""
)

PAINT_COLLECT = (
    COMMON
    + ERROR_INFO
    + r"""
texts = outputs(st.handle)  # read-only
result = dict(st.paint_out, output_errors=errors_in(texts),
              output=[t.strip()[-300:] for t in texts if t.strip()][-6:])
"""
)


def paint(run: Run, step: str) -> dict:
    run.call_deferred(step, PAINT_START)
    return run.call(step + "-collect", PAINT_COLLECT)


def _diff(run: Run, before: dict, after: dict) -> dict:
    diff = vfj_diff(before, after)
    run.note(
        "diff",
        {
            **diff,
            "changed": dict(list(diff["changed"].items())[:40]),
            "changed_count": len(diff["changed"]),
        },
    )
    if diff["changed"]:
        run.note("diff_samples", diff_samples(before, after, diff))
    return diff


def _expectations(
    run: Run, diff: dict, settled: dict, before: dict, after: dict
) -> None:
    expect = run.target.get("expect") or {}
    change = expect.get("change")
    touched = set(diff["changed"]) | set(diff["added"]) | set(diff["removed"])
    if change == "none":
        run.clause(
            "font unchanged (read-only or reporting target)",
            not touched and not diff["font"],
            diff,
        )
    elif change == "any":
        run.clause("the owned font changed", bool(touched or diff["font"]), diff)
    elif isinstance(change, dict):
        glyphs = set(change.get("glyphs", []))
        kinds = set(change.get("kinds", []))
        hit = {g: k for g, k in diff["changed"].items() if g in glyphs}
        ok = glyphs <= touched and all(kinds <= set(k) for k in hit.values())
        if change.get("added"):
            ok = ok and set(change["added"]) <= set(diff["added"])
        if change.get("font"):
            ok = ok and set(change["font"]) <= set(diff["font"])
        if change.get("only"):
            ok = ok and touched <= glyphs | set(change.get("added", []))
        run.clause(
            f"before/after: {json.dumps(change)}",
            ok,
            {
                "changed": hit,
                "added": diff["added"][:20],
                "font": diff["font"],
                "touched": len(touched),
            },
        )
    for check in expect.get("values", []):  # [glyph, layer, key, expected]
        glyph, layer, key, wanted = check
        got = (layer_of(after, glyph, layer) or {}).get(key)
        was = (layer_of(before, glyph, layer) or {}).get(key)
        run.clause(
            f"value {glyph}/{layer}/{key} == {wanted!r}",
            got == wanted,
            {"before": was, "after": got},
        )
    if run.target.get("dialog_expect"):
        shown = " ".join(settled.get("dialogs", []))
        run.clause(
            f"dialog shown: {run.target['dialog_expect']!r}",
            run.target["dialog_expect"] in shown,
            settled.get("dialogs"),
        )
    if "output" in expect:
        text = "\n".join(settled.get("output", []))
        run.clause(
            f"Output matches /{expect['output']}/",
            bool(re.search(expect["output"], text)),
            settled["output"],
        )
    if "tab" in expect:
        tab = settled.get("tab") or ""
        run.clause(
            f"a tab shows {expect['tab']!r}",
            all(t in tab for t in expect["tab"]),
            tab[:300],
        )
    if "window" in expect:
        run.clause(
            f"window opened: {expect['window']!r}",
            any(
                expect["window"] in w
                for w in settled["windows"] + run.data.get("run", {}).get("windows", [])
            ),
            settled["windows"],
        )
    if "file" in expect:
        files = [
            str(p.relative_to(run.scratch))
            for p in run.scratch.rglob("*")
            if p.is_file()
        ]
        hits = [f for f in files if fnmatch.fnmatch(f, expect["file"])]
        run.clause(
            f"file written: {expect['file']}",
            bool(hits) and all((run.scratch / h).stat().st_size for h in hits),
            hits[:10],
        )


def _oracle(run: Run, before: dict, after: dict, settled: dict, extra: dict) -> None:
    """The target's result oracle (realuse/oracles/<id>.py); none means no pass."""
    selection = run.data.get("selection", {})
    windows = settled.get("windows", []) + extra.get("run", {}).get("windows", [])
    oracle = realuse_oracle.Oracle(
        run.target,
        before,
        after,
        output=[settled.get("text", "")],
        dialogs=settled.get("dialogs", []),
        windows=windows,
        tab=settled.get("tab") or "",
        files={
            str(p.relative_to(run.scratch)): p.stat().st_size
            for p in run.scratch.rglob("*")
            if p.is_file() and p.suffix != ".vfj"
        },
        current=[
            c for c in selection.get("selected_layers", []) if isinstance(c, list)
        ],
        selected_nodes=selection.get("selected_nodes", 0),
        extra=extra,
        scratch=run.scratch,
        prepared=selection.get("prepared"),
    )
    realuse_oracle.save_context(oracle, run.scratch / "oracle-context.json")
    for clause in realuse_oracle.evaluate(oracle):
        run.clause(clause["clause"], clause["asserted"], clause["detail"])
    if getattr(oracle, "note_host_8512", None):  # tolerated host defect, recorded
        run.note(
            "tolerated R054 fontlab/fl#8512 (component unlock on save)",
            oracle.note_host_8512,
        )


QUIESCE = (
    COMMON
    + r"""
# Close the windows the script opened (their close handlers remove callbacks), then let
# FontLab's event loop run idle passes before any save (F57: writer/paint race).
def quiesce():
    st.quiesce_closed = []
    for w in [w for w in windows() if id(w) not in st.windows_before]:
        if (w.windowTitle or "").startswith("FontLab:"):
            continue
        st.quiesce_closed.append(w.windowTitle)
        w.close()
    for _ in range(10):
        App.processEvents()
deferred(quiesce)
result = True
"""
)

QUIESCE_COLLECT = (
    COMMON
    + r"""
result = dict(closed=list(getattr(st, "quiesce_closed", [])),
              left=describe([w for w in windows() if id(w) not in st.windows_before]),
              timed_out=st.deferred_timed_out, error=repr(st.deferred_error) if st.deferred_error else None)
"""
)


def run_script_target(run: Run) -> None:
    target = run.target
    path = CORPUS / target["path"]
    deps = []
    for name, rel in (
        target.get("deps") or {}
    ).items():  # Glyphs' Scripts folder layout: name -> repo dir
        link = run.scratch / "deps" / name
        link.parent.mkdir(exist_ok=True)
        link.symlink_to(CORPUS / rel, target_is_directory=True)
        deps.append(str(link.parent))
    for rel, kind in (target.get("make_files") or {}).items():  # owned input files
        made = run.scratch / rel
        made.parent.mkdir(parents=True, exist_ok=True)
        made.write_bytes(png_1x1() if kind == "png" else b"")
    with run.fontlab(), run.owned_font():
        selection = run.show_glyphs()
        before = run.save_copy("before")
        run.call_deferred("run", RUN_SCRIPT, path=str(path), deps=sorted(set(deps)))
        time.sleep(SETTLE_PAUSE)
        ran = run.call("run-collect", RUN_COLLECT)
        run.profile = ran.get("profile")
        run.note("run", ran)
        driven = {}
        if target.get("drive"):
            driven = drive(run, target["drive"])
            run.note("drive", driven)
        settled = settle(run, float(target.get("settle", 0.3)))
        run.note("settled", settled)
        if target.get(
            "quiesce_before_save"
        ):  # F57 bisect: close the script's windows, idle
            run.call_deferred("quiesce", QUIESCE)
            time.sleep(1.0)
            run.note("quiesce", run.call("quiesce-collect", QUIESCE_COLLECT))
        if target.get(
            "no_save"
        ):  # calibration probes that must not write (F57 read-back)
            after, others = before, []
        elif (
            target.get("save_order") == "others-first"
        ):  # F57 bisect: which package write hangs
            others = run.save_others("after")
            after = run.save_copy("after")
        else:
            after = run.save_copy("after")
            others = run.save_others("after")
    diff = _diff(run, before, after)
    if target.get("tab"):
        run.clause(
            "selection: the tab's glyphs are FontLab's current glyphs",
            bool(selection),
            selection,
        )
    run.clause(
        "ran through the deployed launcher's run_script without exception",
        "error" not in ran,
        {k: ran.get(k) for k in ("error", "message", "capability", "frames")},
    )
    errors = (
        ran.get("output_errors", [])
        + driven.get("output_errors", [])
        + settled.get("output_errors", [])
    )
    run.clause("no traceback or error in the script's Output", not errors, errors[:3])
    if target.get("drive"):
        missing = [
            s
            for s in driven.get("steps", [])
            if s[0] in ("click", "popup", "edit") and s[2] is None
        ]
        run.clause(
            "UI driven through its own controls",
            bool(ran.get("windows")) and not missing,
            driven.get("steps"),
        )
    _expectations(run, diff, settled, before, after)
    _oracle(
        run, before, after, settled, {"run": ran, "drive": driven, "others": others}
    )
    # a precise, ruled classification for a known failure
    reason = ruled_classification(target.get("classify_if"), ran, settled, errors)
    if reason:
        run.classification = reason


def ruled_classification(rule, ran, settled, output_errors) -> str | None:
    """The ruled reason when this run shows exactly the ruled failure, else None."""
    if not rule:
        return None
    if rule.get("fixture_unavailable"):  # ruled: no GetGo font can exercise it
        # still must run cleanly (its oracle checks the no-op)
        return rule["reason"] if "error" not in ran else None
    if "dialog" in rule:  # the script itself reports the ruled condition
        hit = rule["dialog"] in " ".join(settled.get("dialogs", []))
        return rule["reason"] if hit else None
    if "output_error" in rule:  # a traceback the script's own callback printed
        text = "\n".join(output_errors)
        hit = rule["output_error"] in text and rule.get("frame", "") in text
        return rule["reason"] if hit else None
    hit = ran.get("error") == rule["error"] and rule.get("frame", "") in " ".join(
        ran.get("frames") or []
    )
    return rule["reason"] if hit else None


def run_control_target(run: Run) -> None:
    """No corpus code: the same open/tab/save/save sequence, to show which VFJ
    differences FontLab itself produces between two saves."""
    with run.fontlab(), run.owned_font():
        run.show_glyphs()
        before = run.save_copy("before")
        settled = settle(run, 0.3, SETTLE.replace("outputs(st.handle)", "[]"))
        after = run.save_copy("after")
    _expectations(run, _diff(run, before, after), settled, before, after)


def run_plugin_target(run: Run) -> None:
    target = run.target
    bundle = CORPUS / target["path"]
    protocol = target["protocol"]
    with run.fontlab(), run.owned_font():
        selection = run.show_glyphs()
        before = run.save_copy("before")
        installed = install(run, str(bundle))
        run.note("install", installed)
        exercised = {}
        if "error" not in installed:
            exercised = _exercise(run, protocol, installed)
        settled = settle(run, float(target.get("settle", 0.3)))
        run.note("settled", settled)
        after = run.save_copy("after")
    diff = _diff(run, before, after)
    refused_tool = [  # glyport records a refused tool hook and still reports "active"
        e
        for e in installed.get("registration", [])
        if e.startswith("tool:") and "FontLab.register_tool" in e
    ]
    if protocol == "SelectTool":
        run.clause(
            "tool registered with the host (no refused tool hook)",
            installed.get("state") == "active" and not refused_tool,
            installed.get("registration"),
        )
    if protocol == "SelectTool" and (
        installed.get("capability") == "FontLab.register_tool" or refused_tool
    ):
        run.classification = (
            "host-limitation-R054: FontLab 9 has no Python tool API "
            "(FontLabPluginHost.register_tool; existing ruling, select-tool matrix target)"
        )
    run.clause(
        "selection: the tab's glyphs are FontLab's current glyphs",
        bool(selection),
        selection,
    )
    run.clause(
        "installed through the deployed launcher's install_plugin",
        installed.get("state") == "active",
        {
            k: installed.get(k)
            for k in ("state", "error", "message", "capability", "frames")
        },
    )
    errors = (
        installed.get("output_errors", [])
        + exercised.get("output_errors", [])
        + settled.get("output_errors", [])
    )
    run.clause("no traceback or error in the plugin's Output", not errors, errors[:3])
    if exercised:
        _protocol_clauses(run, protocol, installed, exercised)
    _expectations(run, diff, settled, before, after)
    _oracle(run, before, after, settled, {"install": installed, **exercised})


def _item(run: Run, installed: dict, menu: str, prefix: str = "") -> str | None:
    """A menu item the plugin added: preferably in ``menu``, else in any menu
    (FontLab files the SDK's FILTER_MENU items under "Glyphs Plugins")."""
    wanted = run.target.get("menu_item")
    found = installed.get("menu_items", {})
    items = found.get(menu, []) + [
        t for m, ts in found.items() if m != menu for t in ts
    ]
    if wanted:
        return wanted if wanted in items else None
    return next((t for t in items if t.startswith(prefix)), None)


def _exercise(run: Run, protocol: str, installed: dict) -> dict:
    out: dict = {}
    title = None
    if protocol == "ReporterPlugin":
        title = _item(run, installed, "View", "Show ")
        out["toggle_on"] = trigger(run, "toggle-on", title)
        out["paint"] = paint(run, "paint") if title else {}
        out["toggle_off"] = trigger(run, "toggle-off", title)
        out["paint_off"] = paint(run, "paint-off") if title else {}
    elif protocol in ("FilterWithoutDialog", "FilterWithDialog"):
        title = _item(run, installed, "Filter")
        out["trigger"] = trigger(run, "trigger", title)
        if protocol == "FilterWithDialog" and out["trigger"].get("windows"):
            out["apply"] = apply_dialog(run)
    elif protocol == "GeneralPlugin":
        menu, title = run.target.get("menu", "Edit"), None
        title = _item(run, installed, menu)
        out["trigger"] = trigger(run, "trigger", title)
        if run.target.get("drive") and out["trigger"].get("windows"):
            out["drive"] = drive(
                run, run.target["drive"], "st.run_windows = st.trigger_windows\n"
            )
    elif protocol == "FileFormatPlugin":
        title = _item(run, installed, "File", "Export with ")
        out["trigger"] = trigger(run, "trigger", title)
    elif protocol == "PalettePlugin" and run.target.get("drive"):
        panel = run.target.get("window")  # the palette's own controls only (L9)
        if not panel:
            out["drive"] = {"refused": "palette drive needs the curation key 'window'"}
        else:
            out["drive"] = drive(
                run,
                run.target["drive"],
                f"st.run_windows = [w for w in windows() if id(w) not in st.windows_before"
                f" and {panel!r} in (w.windowTitle or '')]\n",
            )
    out["output_errors"] = [
        e
        for part in out.values()
        if isinstance(part, dict)
        for e in part.get("output_errors", [])
    ]
    out["title"] = title if protocol != "PalettePlugin" else None
    run.note("exercise", out)
    return out


def _protocol_clauses(run: Run, protocol: str, installed: dict, out: dict) -> None:
    if protocol == "ReporterPlugin":
        paint = out.get("paint", {})
        run.clause(
            "View-menu toggle registered and switched on: a painter is active",
            bool(out.get("title")) and paint.get("painters", 0) >= 1,
            {"title": out.get("title"), **paint},
        )
        run.clause(
            "the reporter drew into the glyph editor overlay (non-transparent pixels)",
            any(n > 0 for n in paint.get("ink", [])),
            paint.get("ink"),
        )
    elif protocol in ("FilterWithoutDialog", "FilterWithDialog"):
        run.clause(
            "Filter-menu item registered and triggered",
            bool(out.get("title")) and out["trigger"].get("found"),
            out.get("trigger"),
        )
        if protocol == "FilterWithDialog":
            apply = out.get("apply", {})
            run.clause(
                "filter dialog opened and applied with its own button",
                bool(apply.get("applied")) and not apply.get("open_after"),
                apply,
            )
    elif protocol == "PalettePlugin":
        title = run.target.get("window") or ""
        run.clause(
            "palette panel shown",
            any(title in w for w in installed.get("windows", [])),
            installed.get("windows"),
        )
    elif protocol == "GeneralPlugin":
        run.clause(
            "menu item registered and triggered",
            bool(out.get("title")) and out["trigger"].get("found"),
            {"items": installed.get("menu_items"), "trigger": out.get("trigger")},
        )
    elif protocol == "FileFormatPlugin":
        run.clause(
            "File-menu export item registered and triggered",
            bool(out.get("title")) and out["trigger"].get("found"),
            out.get("trigger"),
        )


INTERRUPTED = 4  # interrupted while FontLab was confirmed idle: run_all.sh stops (fl-native also fences rc 4)


def interrupted(signum, frame):
    """A killed tool or job sends SIGTERM: raise it so an unconfirmed deferred run
    becomes HostStillBusy (exit 3) instead of dying silently."""
    raise KeyboardInterrupt(f"signal {signum}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("ids", nargs="+")
    args = parser.parse_args(argv)
    targets = {t["id"]: t for t in json.loads(args.manifest.read_text())["targets"]}
    bad = [  # absolute paths only for harness calibration probes (curation key "probe")
        i
        for i in args.ids
        if i in targets
        and Path(targets[i]["path"]).is_absolute()
        and not targets[i].get("probe")
    ]
    if bad:  # checked before FontLab is touched: rc 2 is not fenced (a probe once was, 07:14)
        print(
            f"run_realuse: target paths must be 'repository/relative': {bad}",
            file=sys.stderr,
        )
        return 2
    require_workspace()
    signal.signal(signal.SIGTERM, interrupted)  # SIGTERM reaches call_deferred (I5 a)
    worst = 0
    for target_id in args.ids:
        run = Run(targets[target_id], args.out, SCRATCH)
        try:
            runner = {
                "script": run_script_target,
                "plugin": run_plugin_target,
                "control": run_control_target,
            }
            runner[run.target["kind"]](run)
        except BaseException as error:  # noqa: BLE001 - recorded in the result and receipt
            code = finish_or_busy(run, error)
            if code == 3:
                return 3  # host state unknown: do not run further targets
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                return INTERRUPTED  # killed/interrupted: never start the next target
            worst = max(worst, code)
            continue
        code = finish_or_busy(run, None)
        if code == 3:
            return 3
        worst = max(worst, code)
    return worst


def finish_or_busy(run, error: BaseException | None) -> int:
    """run.finish(), but 3 whenever the run left FontLab possibly busy, even if
    finishing raised or was interrupted (review H1)."""
    code = 3
    try:
        code = run.finish(error)
    finally:
        if run.host_busy:
            return 3  # noqa: B012 - deliberate: host state beats any exception
    return code


def exit_now(code: int) -> NoReturn:
    """End the process without interpreter finalization.

    A busy session is deliberately left open (L10) and an abandoned reconnect
    keeps its client: each owns an anyio portal whose generator, closed by the
    final garbage collection, waits for the hung call. In the 2026-10-16
    s-hoi-dekinker run that held the client 36 minutes in Py_FinalizeEx after
    the receipt was written (evidence hang-20261016-hoi-dekinker/client-sample.txt),
    so fl-native.sh never saw exit 3. Receipts are written and closed by then;
    flush the streams and leave at once. Signals are ignored from here on and a
    failing flush is ignored, so os._exit always runs (review L13)."""
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, signal.SIG_IGN)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except BaseException:  # noqa: BLE001, S110 - leaving regardless
            pass
    os._exit(code)


def entry(argv: list[str] | None = None) -> int:
    """main(), with argparse exits kept and anything unexpected failing closed (3)."""
    try:
        return main(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 1
    except BaseException:  # noqa: BLE001 - host state unknown: fence (fl-native, rc 3)
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    code = 3  # a signal before entry() returns still exits 3 (fail closed)
    try:
        code = entry()
    finally:
        exit_now(code)
