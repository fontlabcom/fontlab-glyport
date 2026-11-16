# this_file: native-drivers/realuse/realuse_common.py
"""Host-side harness for the issue-106 real-use matrix (lane G1).

Each target is a real Glyphs corpus script or plugin bundle, run inside FontLab
through the *deployed* launcher (``Glyport Launcher.py`` in FontLab's Scripts
folder) against an owned scratch copy of a GetGo VFJ. One ``Run`` = one target:

- setup: HOME, GLYPORT_DEFAULTS and cwd point at scratch; the launcher file is
  executed with GLYPORT_LAUNCHER_NO_UI; glyport must load from the launcher's
  src; GlyphsApp dialogs answer from the manifest (never modal);
- the owned font copy is opened, a glyph tab shows the manifest's glyphs, and
  FontLab saves a "before" VFJ copy; after the target ran, an "after" copy;
  the two are diffed here (glyph set, layers, anchors, metrics, kerning);
- every Remopy call is short (FontLab's run_python has a 5 s deadline);
- teardown closes the launcher's handles, restores the host import path, HOME,
  cwd and dialog classes, and closes the owned font unsaved.

Corpus files are executed only inside FontLab through glyport (D11), never read
into evidence: tracebacks keep ``file, line N, in func`` and drop source lines.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORKSPACE = next(
    (p for p in HERE.parents if (p / "verification/issue-104/fl-native.sh").is_file()),
    None,
)
CORPUS = (
    Path(os.environ["GLYPORT_ORIGINAL_CORPUS"])
    if "GLYPORT_ORIGINAL_CORPUS" in os.environ
    else (WORKSPACE / "reference-glyphs-plugins" if WORKSPACE else None)
)
GETGO = WORKSPACE / "fontlab-python-examples/testdata/getgo" if WORKSPACE else None
PACKAGED_GETGO = REPO / "realuse/fixtures/getgo"


def require_workspace() -> Path:
    """Native execution requires the real workspace and its safety runner."""
    if WORKSPACE is None:
        raise RuntimeError(
            "Native realuse execution requires the FontLab scripting workspace"
        )
    return WORKSPACE


def fixture_path(name: str) -> Path:
    """Offline oracles use exact packaged bytes; native fixture roots stay unchanged."""
    return PACKAGED_GETGO / FIXTURES[name]


LAUNCHER = (
    Path.home()
    / "Library/Application Support/FontLab/FontLab 9/Scripts/Glyport Launcher.py"
)
STATE = "_glyport_realuse"
STAMP = os.environ.get("REALUSE_STAMP") or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
FIXTURES = {
    "cafe": "apache/cafe/cafe.vfj",
    "medi": "cc0/medi/medi.vfj",
    "plum-var": "cc0/plum/plum-var.vfj",
    "cosm-italic-var": "cc0/cosm/cosm-italic-var.vfj",
    "hebrew": "apache/zotosans/zotosans-hebrew.vfj",
    "kufi": "apache/zotosans/zoto-kufiarabic.vfj",
    "armenian": "apache/zotosans/zotosans-armenian.vfj",
    "gurmukhi": "apache/zotosans/zotosans-gurmukhi.vfj",
}

if WORKSPACE is not None:
    sys.path.insert(0, str(REPO / "src"))
from fly.gp.receipt import (
    Capability,
    Receipt,
    ReceiptAdapter,
    ReceiptDiagnostic,
    ReceiptEnvironment,
    ReceiptSource,
    Stage,
    validate_receipt,
)

# In-FontLab deadline for SYNCHRONOUS steps (controller incident 2026-10-16:
# FontLab's 5 s run_python deadline does not stop abandoned code). Every
# run_python step except WAIT runs its snippet under a watchdog thread that
# injects RealuseSyncDeadline (a BaseException: `except Exception` cannot
# swallow it) into the GUI thread after `guard_seconds`, every 0.5 s, at most
# 10 times. faulthandler dumps every thread's Python stack to the scratch
# folder if a snippet runs 30 s; it is cancelled on every exit path of the
# snippet. Code that swallows the 10 injections (bare except) is escalated
# (RealuseEscalation, below).
#
# Hang incidents 2026-10-16 (p-disguiser, hoi-dekinker): FontLab spun for 36 min
# in the first frame of the next run_python request. Root cause: "clearing" a
# pending injection with PyThreadState_SetAsyncExc(id, NULL) (see drain() below).
# Scope (review M6 of 36295b7: per-shooter anchors), as defence in depth: nothing may be injected or traced outside the guarded
# code. G.in_region(frame, anchor) is true only while `frame` runs inside the
# shooter's own guarded snippet or deferred wrapper (`anchor`, by code-object
# identity), reached before any other anchor (a nested guarded request, WAIT
# included) and before any run_python request frame (FontLab's wrapper globals
# hold __mcp_code). Every injection checks it under G.lock first, the escalation
# trace raises and arms only in region frames, and _guard_stop retires the
# guard under the same lock before anything else, then delivers a pending
# injection (drain), retried until it completes: once it returns, no injection
# is pending or can follow, so remopy's helper and FontLab's wrapper never see one.
GUARD_SETUP = r"""
import sys, types
G = sys.modules.get("_realuse_guard")
if G is None or getattr(G, "version", 0) != 5:
    import threading
    G = types.ModuleType("_realuse_guard")
    G.version, G.lock = 5, threading.Lock()
    class RealuseSyncDeadline(BaseException):
        "Raised into FontLab's GUI thread when a synchronous harness step overruns."
    G.RealuseSyncDeadline, G.token, G.events, G.fault_file = RealuseSyncDeadline, None, [], None
    G.anchors, G.escalation_anchor = {}, None  # id(code) -> code: identity, not equality
    def in_region(frame, anchor):
        # True when walking out from `frame` reaches `anchor` before any other
        # anchor (a nested guarded request or deferred call) or any frame of a
        # run_python request (FontLab's wrapper globals hold __mcp_code).
        while frame is not None:
            code = frame.f_code
            if code is anchor:
                return True
            if id(code) in G.anchors or "__mcp_code" in frame.f_globals:
                return False
            frame = frame.f_back
        return False
    # Escalation for code that swallows injected exceptions (bare except):
    # RealuseEscalation is injected like the others, but constructing it (which
    # happens in the target thread as soon as an `except` clause catches it)
    # arms a trace function on that thread that raises RealuseHalt at the next
    # line of a guarded (region) frame, i.e. inside the swallowing handler
    # itself, so the exception leaves that try. CPython unsets a trace function
    # that raises, so each escalation climbs out of one handler; code that
    # swallows at two nested levels in a loop can still hold on, and then the
    # client fails fast (stuck -> exit 3; a synchronous request hits the client
    # timeout).
    class RealuseHalt(BaseException):
        "Raised by the escalation trace function."
    # CPython 3.12+ instantiates the injected exception (so arms) at once, inside
    # the try; its "exception" event is still there, where a raise would be
    # swallowed and the trace unset. Wait for the handler's next line instead.
    # (3.11, FontLab's, instantiates it when the except clause matches.)
    def _tracer(frame, event, arg):
        if frame.f_code in G.safe_codes or not G.in_region(frame, G.escalation_anchor):
            return None
        if event == "exception":
            return G.tracer
        raise G.RealuseHalt("realuse deadline: code ignored the deadline")
    def arm():
        frame, anchor = sys._getframe(1), G.escalation_anchor
        if not G.in_region(frame, anchor):
            return  # never trace harness, transport, host or other guards' frames
        sys.settrace(G.tracer)  # replaces FontLab's 5 s __mcp_trace for this request (L14)
        while frame is not None and G.in_region(frame, anchor):
            if frame.f_code not in G.safe_codes:
                frame.f_trace = G.tracer
            frame = frame.f_back
    class RealuseEscalation(BaseException):
        "Injected after the plain deadline injections; arms the trace on creation."
        def __init__(self, *args):
            BaseException.__init__(self, *args)
            G.arm()
    G.RealuseHalt, G.tracer, G.arm, G.RealuseEscalation = RealuseHalt, _tracer, arm, RealuseEscalation
    # Never "clear" a pending injection with PyThreadState_SetAsyncExc(id, NULL):
    # on CPython 3.11 that leaves the async-exception eval-breaker flag set, and
    # the next Python call made while a trace function is set (FontLab's
    # run_python wrapper always sets one) spins forever in the eval loop: the
    # 2026-10-16 p-disguiser and hoi-dekinker hangs (reproducer in
    # verification/issue-106/evidence/glyport/hang-20261016-root-cause/).
    # A pending injection is delivered instead: calling drain() (any Python call
    # checks the eval breaker) raises it where the caller retries.
    def drain():
        return None
    G.in_region, G.drain = in_region, drain
    G.safe_codes = {_tracer.__code__, arm.__code__, in_region.__code__, drain.__code__, RealuseEscalation.__init__.__code__}
    G.escalate_seconds, G.escalate_interval, G.fault_seconds = 5.0, 0.2, 30
    sys.modules["_realuse_guard"] = G
"""

GUARD = (
    GUARD_SETUP
    + r"""
def _guard_start(limit, name, code):
    import ctypes, threading, time, faulthandler
    inject = ctypes.pythonapi["PyThreadState_SetAsyncExc"]
    inject.argtypes, inject.restype = [ctypes.c_ulong, ctypes.py_object], ctypes.c_int
    token, target = object(), threading.get_ident()
    G.token = token
    G.anchors[id(code)] = code
    if G.fault_file is not None:
        faulthandler.dump_traceback_later(G.fault_seconds, repeat=True, file=G.fault_file)
    def shoot(kind, exc):  # under G.lock: only while this guard is live and the snippet runs
        if G.token is not token:
            return False
        if G.in_region(sys._current_frames().get(target), code):
            if exc is G.RealuseEscalation:
                G.escalation_anchor = code
            G.events.append({"step": name, kind: inject(target, exc)})
        else:
            G.events.append({"step": name, kind: "skipped: outside the snippet"})
        return True
    def watch():
        if limit is None:
            return
        end = time.monotonic() + limit
        while G.token is token and time.monotonic() < end:
            time.sleep(0.05)
        for _ in range(10):
            with G.lock:
                if not shoot("injection", G.RealuseSyncDeadline):
                    return
            time.sleep(0.5)
        end = time.monotonic() + G.escalate_seconds  # swallowed 10 times: escalate
        while time.monotonic() < end:
            with G.lock:
                if not shoot("escalation", G.RealuseEscalation):
                    return
            time.sleep(G.escalate_interval)
    threading.Thread(target=watch, name="realuse-sync-deadline", daemon=True).start()
    return token, target, code
def _guard_stop(guard):
    with G.lock:  # first: retire the guard, so the watcher cannot inject any more
        if G.token is guard[0]:
            G.token = None
        G.anchors.pop(id(guard[2]), None)
    G.drain()  # an injection still pending is delivered here (retried by the caller)
    sys.settrace(None)  # an escalation may have armed tracing on this thread
    import faulthandler
    faulthandler.cancel_dump_traceback_later()  # never left running in FontLab (review a)
G.safe_codes.add(sys._getframe().f_code)  # this request frame must run its finally
_code = compile(step_code, "<realuse " + guard_step + ">", "exec")
_attempts = range(100)  # built before the snippet: no call (eval-breaker point) in the finally
_guard = _guard_start(guard_seconds, guard_step, _code)
try:
    exec(_code, globals())
finally:
    # An injection made while the snippet ran but delivered after it ended lands
    # in _guard_stop (at most one: the watcher only injects into the snippet), as
    # can FontLab's own 5 s trace: stop again until it completes.
    for _attempt in _attempts:
        try:
            _guard_stop(_guard)
        except BaseException:
            if _attempt == _attempts[-1]:
                raise
        else:
            break
"""
)

SYNC_GUARD_SECONDS = 4.5  # below FontLab's 5 s run_python deadline

COMMON = r"""
import sys
from fly import fl as fontlab
from fly.qt import QtGui, QtCore
App = QtGui.QApplication
def pump(n=3):
    for _ in range(n):
        App.processEvents()
def qtlist(getter, *args):
    from fly.ap.qt.safe import qt_list
    return qt_list(getter, *args)
def menu_titles():
    out = {}
    for top in qtlist(fontlab.MainWindow().menuBar().actions):
        menu = top.menu()
        if menu is not None:
            out[top.text.replace("&", "")] = [a.text for a in qtlist(menu.actions) if a.text]
    return out
def menu_action(menu_name, text):
    for top in qtlist(fontlab.MainWindow().menuBar().actions):
        if menu_name in (None, top.text.replace("&", "")) and top.menu() is not None:
            for action in qtlist(top.menu().actions):
                if action.text == text:
                    return action
    return None
def windows():
    return [w for w in qtlist(App.topLevelWidgets) if w.isVisible()]
def live(w):  # a widget kept from an earlier step may have been destroyed since
    try:
        return w.isVisible()
    except ValueError:  # "Trying to call 'isVisible' on a destroyed QWidget object"
        return False
def describe(ws):
    return [w.className() + ":" + (w.windowTitle or "") for w in ws]
def click(button):
    button.click(); pump()
def deferred_reset(done=False):
    # One place for the per-step flags (review I1): steps without deferred work
    # reset them too, so a stale timeout is never reported against them.
    st.deferred_done, st.deferred_error = done, None
    st.deferred_timed_out, st.deferred_stuck, st.deferred_injections = False, False, []
    st.deferred_escalations = []
def deferred(function):
    # Run from the event loop, outside this run_python call (FontLab's 5 s
    # run_python deadline): long corpus code then runs as from the Scripts menu.
    # Deadline st.deadline s (default 40, below the MCP bridge's 60 s): a
    # watchdog thread injects TimeoutError into the GUI thread
    # (PyThreadState_SetAsyncExc). The first injection is followed by a grace
    # period (st.deadline_grace, 2 s) so cleanup (signal disconnects, closing
    # widgets) can finish, then repeats every st.deadline_interval (0.75 s).
    # After st.deadline_max_injections (20, about 16 s; a bare-except loop needed up
    # to 33 in review M1's measurements, most below 20) that do not end the guarded code
    # (it is inside a nested loop, modal exec or a long native call, so the
    # injections land elsewhere), injection stops and st.deferred_stuck tells
    # the client, which fences the host (exit 3). The last pending injection is not
    # cleared (that is the CPython 3.11 hang, see drain()): it fires when the stuck
    # code returns to Python, in a host that is fenced and relaunched. A long native call is
    # interrupted only when it returns to Python. Injections go only into the wrapped call
    # (G.in_region, see GUARD_SETUP); one that would land in a nested run_python request is
    # skipped and recorded as such.
    import ctypes, threading, time
    limit = float(getattr(st, "deadline", 40.0))
    grace = float(getattr(st, "deadline_grace", 2.0))
    interval = float(getattr(st, "deadline_interval", 0.75))
    most = int(getattr(st, "deadline_max_injections", 10))
    G = sys.modules["_realuse_guard"]
    inject = ctypes.pythonapi["PyThreadState_SetAsyncExc"]
    inject.argtypes, inject.restype = [ctypes.c_ulong, ctypes.py_object], ctypes.c_int
    deferred_reset()
    def wrapper():
        target = threading.get_ident()
        finished = threading.Event()
        def shoot(exc):  # only into the wrapped call, never into a nested request
            with G.lock:  # never between a nested guard's retirement and its drain
                if G.in_region(sys._current_frames().get(target), wrapper.__code__):
                    if exc is G.RealuseEscalation:
                        G.escalation_anchor = wrapper.__code__
                    return inject(target, exc)
            return "skipped: outside the deferred call"
        def watchdog():
            if finished.wait(limit):
                return
            st.deferred_timed_out = True
            pause = grace
            while len(st.deferred_injections) < most:
                st.deferred_injections.append(shoot(TimeoutError))
                if finished.wait(pause):
                    return
                pause = interval
            # Swallowed `most` times: escalate (cannot be swallowed by a handler).
            end = time.monotonic() + G.escalate_seconds
            while time.monotonic() < end:
                st.deferred_escalations.append(shoot(G.RealuseEscalation))
                if finished.wait(G.escalate_interval):
                    return
            st.deferred_stuck = True  # stop injecting; the client fences the host
        guard = threading.Thread(target=watchdog, name="realuse-deadline", daemon=True)
        guard.start()
        try:
            function()
        except BaseException as error:  # recorded; WAIT reports it
            st.deferred_error = error
        finally:
            while True:  # an injection racing the return may land anywhere in here
                try:
                    sys.settrace(None)  # an escalation may have armed tracing
                    finished.set()
                    guard.join()
                    G.drain()  # a pending injection is delivered here and retried
                    break
                except BaseException:  # noqa: deadline exceptions only, retried
                    continue
            st.deferred_done = True
    G.safe_codes.add(wrapper.__code__)
    G.anchors[id(wrapper.__code__)] = wrapper.__code__
    QtCore.QTimer.singleShot(0, wrapper)
def errors_in(texts):
    joined = "".join(texts)  # Output arrives line by line: keep each traceback whole
    found, start = [], joined.find("Traceback")
    while start != -1:
        end = joined.find("Traceback", start + 1)
        found.append(joined[start:end if end != -1 else None][-1500:])
        start = end
    return found + [t[-700:] for t in texts if "Traceback" not in joined and ("Error" in t or "failed" in t)]
"""

SETUP = (
    COMMON
    + r"""
import os, types, gc
paths = list(sys.path)
st = types.ModuleType(state)
st.paths, st.answers, st.dialog_log = paths, answers, []
st.env = {k: os.environ.get(k) for k in ("HOME", "GLYPORT_DEFAULTS")}
st.cwd = os.getcwd()
st.launcher_before = sys.modules.get("_glyport_launcher")
sys.modules[state] = st
os.environ["HOME"], os.environ["GLYPORT_DEFAULTS"] = home, defaults
os.chdir(home)
code = compile(open(launcher, encoding="utf-8").read(), launcher, "exec")
exec(code, {"__name__": "glyport_launcher", "__file__": launcher, "GLYPORT_LAUNCHER_NO_UI": True})
L = sys.modules["_glyport_launcher"]
glyport = L.activate(reload=True)
assert glyport.__file__.startswith(L.GLYPORT_SRC), glyport.__file__
from fly.gp.glyphsapp import fontlab_dialogs as D
st.dialogs = (D.Dialogs.__init__, D.Dialogs._answer, D.Dialogs.message)
def _init(self, qtgui, interactive, given, _o=st.dialogs[0]):
    _o(self, qtgui, False, dict(st.answers, **given))
def _answer(self, name, _o=st.dialogs[1]):
    st.dialog_log.append(name)
    return _o(self, name)
def _message(self, message, title, ok_button, _o=st.dialogs[2]):
    st.dialog_log.append("message: " + str(title)[:80] + ": " + str(message)[:300])
    return _o(self, message, title, ok_button)
D.Dialogs.__init__, D.Dialogs._answer, D.Dialogs.message = _init, _answer, _message
# Curation "stub_callbacks" (F57 bisect): Glyphs.addCallback for these events is a no-op.
from fly.gp.glyphsapp import application as A
st.add_callback = A.GSApplication.addCallback
if stub_callbacks:
    def _add_callback(self, target, operation, _o=st.add_callback):
        if operation in stub_callbacks:
            st.dialog_log.append("callback stubbed: " + str(operation))
            return None
        return _o(self, target, operation)
    A.GSApplication.addCallback = _add_callback
st.windows_before = {id(w) for w in windows()}
st.deadline = deadline
deferred_reset(done=True)
G = sys.modules.get("_realuse_guard")
if G is not None:  # faulthandler stacks for hung requests, kept with the scratch folder
    G.fault_file = open(fault_log, "a")
import platform
result = dict(python=platform.python_version(), arch=platform.machine(), os=platform.system(),
              qt=QtCore.qVersion(), glyport=glyport.__file__, src=L.GLYPORT_SRC, site=L.GLYPORT_SITE,
              app_version=str(QtGui.QApplication.instance().applicationVersion))
"""
)

TEARDOWN = (
    COMMON
    + r"""
import os
failures = []
G = sys.modules.get("_realuse_guard")
if G is not None and G.fault_file is not None:
    import faulthandler
    faulthandler.cancel_dump_traceback_later()
    G.fault_file.close()
    G.fault_file = None
L = sys.modules.get("_glyport_launcher")
if L is not None:
    failures += L.close_all()
if st is not None:
    try:
        from fly.gp.glyphsapp import fontlab_dialogs as D
        D.Dialogs.__init__, D.Dialogs._answer, D.Dialogs.message = st.dialogs
        from fly.gp.glyphsapp import application as A
        A.GSApplication.addCallback = st.add_callback
    except Exception as error:
        failures.append("dialog restore: " + repr(error))
    # FontLab's own panels (YDock, ToolbarPanel, ...) appear lazily; owned
    # windows are Qt classes (PythonQt subclasses report their Qt base).
    left = describe([w for w in windows() if id(w) not in st.windows_before
                     and w.className().startswith("Q")])
    sys.path[:] = st.paths
    for key, value in st.env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    os.chdir(st.cwd)
    if st.launcher_before is None and not failures:
        sys.modules.pop("_glyport_launcher", None)
    sys.modules.pop(state, None)
if not failures:
    fly = sys.modules.get("fly")
    if fly is not None:
        vars(fly).pop("gp", None)
    for m in [m for m in sys.modules if m.split(".")[0] in ("fontlab_glyport", "GlyphsApp", "vanilla") or m == "fly.gp" or m.startswith("fly.gp.")]:
        del sys.modules[m]
result = dict(failures=failures, windows_left=left if st is not None else None,
              path_restored=st is not None and sys.path == st.paths,
              env_restored=st is not None and all(os.environ.get(k) == v for k, v in st.env.items()),
              cwd_restored=st is not None and os.getcwd() == st.cwd)
"""
)

TAB = (
    COMMON
    + r"""
from fly.gp.model import Model
from fly.gp.model.fontlab_backend import FontLabBackend
pkg = fontlab.flWorkspace.instance().findPackageId(font_id)
font = Model(FontLabBackend(packages=[pkg])).fonts[0]
if text:  # "" keeps the font window active (font-view selection scripts)
    font.newTab(text)
pump(6)
selected = 0
if select_nodes:  # Glyphs scripts often act on selected nodes: select every node of the shown layer
    layer = font.selectedLayers[0]
    for path in layer.paths:
        for node in path.nodes:
            node.selected = True
            selected += 1
    pump()
if select_anchor:  # scripts acting on a selected anchor
    try:
        for anchor in font.selectedLayers[0].anchors:
            if anchor.name == select_anchor:
                anchor.selected = True
                selected += 1
    except Exception as error:  # an unsupported selection is the target's result
        selected = "anchor selection failed: " + type(error).__name__ + ": " + str(error)[:200]
    pump()
result = selected
"""
)

PREPARE = (  # harness-owned setup of the owned copy before "before" is saved
    COMMON
    + r"""
from fly.gp.model import Model
from fly.gp.model.fontlab_backend import FontLabBackend
pkg = fontlab.flWorkspace.instance().findPackageId(font_id)
font = Model(FontLabBackend(packages=[pkg])).fonts[0]
scope = {"font": font, "package": pkg, "fontlab": fontlab, "layer": font.selectedLayers[0] if font.selectedLayers else None}
try:
    exec(compile(prepare, "<realuse prepare>", "exec"), scope)
    pump(4)
    result = scope.get("result", True)
except Exception as error:  # reported as its own clause, not as a target failure
    result = {"prepare_error": type(error).__name__ + ": " + str(error)[:300]}
"""
)

SELECTION = (
    COMMON
    + r"""
from fly import gp as fontlab_glyport
from fly.gp.model import Model
from fly.gp.model.fontlab_backend import FontLabBackend
pump(4)
pkg = fontlab.flWorkspace.instance().findPackageId(font_id)
font = Model(FontLabBackend(packages=[pkg])).fonts[0]
result = [[l.parent.name, l.name] for l in font.selectedLayers]  # glyph, shown layer (oracles)
st.windows_before = {id(w) for w in windows()}  # FontLab's own panels appear with the first glyph tab
"""
)

# A traceback frame's source line (and caret line) after "line N, in func":
# corpus source text never enters evidence.
_SOURCE_LINE = re.compile(
    r"(line \d+, in [^\n\\]+)(?:\\n|\n)[ \t]{2,}[^\n\\]*(?:(?:\\n|\n)[ \t]{2,}[\^~ ]+(?=\\n|\n|$))?"
)


WAIT = (
    COMMON
    + r"""
# Read-only (controller ruling 2026-10-16): never pump here, so queued corpus
# code can run only from FontLab's own event loop, under the deferred watchdog.
result = dict(done=st.deferred_done, stuck=st.deferred_stuck,
              timed_out=st.deferred_timed_out, injections=list(st.deferred_injections),
              escalations=len(st.deferred_escalations))
"""
)


def scrub(text: str) -> str:
    return _SOURCE_LINE.sub(r"\1", text)


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def revision() -> str:
    if not (REPO / ".git").exists():
        from email.parser import Parser

        metadata = Parser().parsestr((REPO / "PKG-INFO").read_text(encoding="utf-8"))
        return "archive:" + metadata["Version"]
    git = ["git", "-C", str(REPO)]
    head = subprocess.run(
        [*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = subprocess.run(
        [*git, "status", "--porcelain", "--", "src"],
        capture_output=True,
        text=True,
        check=True,
    )
    return head + ("+dirty" if dirty.stdout.strip() else "")


# --- VFJ diff ----------------------------------------------------------------------
def _layers(glyph: dict) -> dict:
    return {
        layer.get("name", str(i)): layer
        for i, layer in enumerate(glyph.get("layers", []))
    }


AUTO_LAYER = 16  # VFJ layer flag of a FontLab auto layer (autoRecipe composites)


def _unlocked(elements):
    return [{k: v for k, v in e.items() if k != "locked"} for e in elements or []]


def auto_rebuild(lb: dict, la: dict) -> bool:
    """FontLab's own rebuild of an auto layer when it is displayed: component
    ``locked`` flags dropped and stale anchors removed, nothing else
    (probes/probe_composite_native-render.json: no glyport involved)."""
    if not lb.get("flags", 0) & AUTO_LAYER:
        return False
    rest = {k for k in lb.keys() | la.keys() if lb.get(k) != la.get(k)} - {
        "elements",
        "anchors",
    }
    kept = [a for a in la.get("anchors", []) if a not in lb.get("anchors", [])]
    return (
        not rest
        and not kept
        and _unlocked(lb.get("elements")) == _unlocked(la.get("elements"))
    )


def vfj_diff(before: dict, after: dict) -> dict:
    """Glyph-level differences between two FontLab-saved VFJ copies.

    Glyphs whose only differences are FontLab auto-layer rebuilds go to
    ``auto_rebuilt``, not ``changed``."""
    fb, fa = before["font"], after["font"]
    gb = {g["name"]: g for g in fb.get("glyphs", [])}
    ga = {g["name"]: g for g in fa.get("glyphs", [])}
    changed: dict[str, list[str]] = {}
    rebuilt: list[str] = []
    for name in sorted(gb.keys() & ga.keys()):
        if gb[name] == ga[name]:
            continue
        kinds = {
            k
            for k in gb[name].keys() | ga[name].keys()
            if k != "layers" and gb[name].get(k) != ga[name].get(k)
        }
        lb, la = _layers(gb[name]), _layers(ga[name])
        if lb.keys() != la.keys():
            kinds.add("layer set")
        if (
            not kinds
            and lb.keys() == la.keys()
            and all(lb[n] == la[n] or auto_rebuild(lb[n], la[n]) for n in lb)
        ):
            rebuilt.append(name)
            continue
        for lname in lb.keys() & la.keys():
            for key in lb[lname].keys() | la[lname].keys():
                if lb[lname].get(key) != la[lname].get(key):
                    kinds.add(key)
        changed[name] = sorted(kinds)
    font_keys = sorted(
        k for k in fb.keys() | fa.keys() if k != "glyphs" and fb.get(k) != fa.get(k)
    )
    return {
        "added": sorted(ga.keys() - gb.keys()),
        "removed": sorted(gb.keys() - ga.keys()),
        "changed": changed,
        "font": font_keys,
        "auto_rebuilt": rebuilt,
    }


def diff_samples(before: dict, after: dict, diff: dict, limit: int = 3) -> dict:
    """Before/after of the changed keys for the first changed glyphs (GetGo
    fonts are open-source fixtures, so their data may enter evidence)."""
    samples = {}
    for name, kinds in list(diff["changed"].items())[:limit]:
        gb = {g["name"]: g for g in before["font"]["glyphs"]}[name]
        ga = {g["name"]: g for g in after["font"]["glyphs"]}[name]
        lb, la = _layers(gb), _layers(ga)
        samples[name] = {
            layer: {
                k: [
                    json.dumps(lb[layer].get(k))[:400],
                    json.dumps(la[layer].get(k))[:400],
                ]
                for k in kinds
                if lb[layer].get(k) != la[layer].get(k)
            }
            for layer in lb.keys() & la.keys()
            if lb[layer] != la[layer]
        }
    return samples


def layer_of(vfj: dict, glyph: str, layer: str | None = None) -> dict | None:
    for g in vfj["font"].get("glyphs", []):
        if g["name"] == glyph:
            layers = _layers(g)
            if layer is None:
                return next(iter(layers.values()), None)
            return layers.get(layer)
    return None


TRANSPORT_MARKERS = (
    "Cannot connect to FontLab",
    "MCP authentication failed",
    "fresh context",
    "Connection closed",
)


def is_transport_error(error: BaseException) -> bool:
    """True when the Remopy session itself failed (reconnect), False for an error
    raised by the code inside FontLab (retry on the same session; review I4).

    Only remopy's NativeExecutionError proves the host answered; anything else
    (OSError, anyio's message-less ClosedResourceError, a closed client's
    RuntimeError) is transport (review L4, M2). The bridge also wraps its own
    connection failures in NativeExecutionError: those carry a marker."""
    if type(error).__name__ != "NativeExecutionError":
        return True
    return any(marker in str(error) for marker in TRANSPORT_MARKERS)


# Seconds past a target's deadline before giving up confirmation: the watchdog
# needs grace 2 s + 9 x 0.75 s + 5 s of escalation; more means FontLab's GUI
# thread is not coming back, so the run fails fast (exit 3) instead of 160 s.
CONFIRM_GRACE = 25.0
# Client limit per request. Synchronous steps stop inside FontLab after 4.5 s
# (+ 5 s of injections + 5 s of escalation) and WAIT never blocks, so a request
# still unanswered after this means FontLab's GUI thread is lost: the transport
# error marks the host busy (H2) and the run exits 3 instead of waiting 900 s.
CALL_TIMEOUT = 45.0
WAIT_PAUSE = 0.5  # client pause between WAIT polls (WAIT itself never blocks)
# Closing a session whose call timed out waits for that call (and the relay
# process) to end: give up after this and abandon it (the process exits with
# os._exit, run_realuse.exit_now, so nothing waits for it at shutdown).
CLOSE_TIMEOUT = 5.0


def oracle_verdict(clauses: list[dict]) -> dict:
    """held / failed / missing, from the receipt's "oracle: ..." clauses."""
    mine = [c for c in clauses if c["clause"].startswith("oracle: ")]
    if not mine or any(c["clause"] == "oracle: result oracle defined" for c in mine):
        return {
            "verdict": "missing",
            "failed": [c["clause"] for c in mine if not c["asserted"]],
        }
    failed = [c["clause"][len("oracle: ") :] for c in mine if not c["asserted"]]
    return {"verdict": "failed" if failed else "held", "failed": failed}


class HostStillBusy(RuntimeError):
    """FontLab may still be running corpus code: stop, do not queue more runs."""


class Run:
    """One real-use target: calls, clauses, evidence, receipt."""

    def __init__(self, target: dict, out_dir: Path, scratch_root: Path):
        self.target = target
        self.out = out_dir
        self.out.mkdir(parents=True, exist_ok=True)
        scratch_root.mkdir(parents=True, exist_ok=True)
        self.scratch = Path(
            tempfile.mkdtemp(prefix=target["id"] + "-", dir=scratch_root)
        )
        (self.scratch / "home").mkdir()
        self.clauses: list[dict] = []
        self.evidence: list[str] = []
        self.calls: list[dict] = []
        self.environment = dict.fromkeys(
            ("host", "host_build", "python", "qt", "os", "arch")
        )
        self.classification: str | None = None
        self.fl = None
        self.font_id = None
        self.started = now()
        self.revision = revision()
        self.data: dict = {}
        self.host_busy = False
        self.profile: str | None = None  # glyport's resolved Glyphs profile (receipt)
        self.deadline_events: list[dict] = []  # one per confirmed deferred step (M4)

    # --- bookkeeping ---------------------------------------------------------------
    def clause(self, name: str, ok: bool, detail: object = "") -> bool:
        text = detail if isinstance(detail, str) else json.dumps(detail, default=repr)
        self.clauses.append(
            {"clause": name, "asserted": bool(ok), "detail": scrub(text)[:2000]}
        )
        return bool(ok)

    def note(self, label: str, value: object) -> None:
        # Scripts print their own tracebacks: scrub source lines from data too.
        value = json.loads(scrub(json.dumps(value, default=repr)))
        self.data[label] = value
        self.evidence.append(
            scrub(f"{label}: {json.dumps(value, default=repr)}")[:1500]
        )

    # --- FontLab -------------------------------------------------------------------
    def call(
        self,
        step: str,
        code: str,
        guard: float | None = SYNC_GUARD_SECONDS,
        **variables,
    ):
        """One run_python step. Unless ``guard`` is None (WAIT, which polls under
        the deferred watchdog), the snippet runs under the in-FontLab GUARD."""
        prelude = "import sys\nst = sys.modules.get(state)\n"
        t0 = time.monotonic()
        try:
            if self.fl is None:  # a reconnect failed: transport, retried by the caller
                raise ConnectionError("no FontLab session (the last reconnect failed)")
            completed = self.fl.run(
                GUARD,
                state=STATE,
                step_code=prelude + code,
                guard_seconds=None if guard is None else float(guard),
                guard_step=step,
                **variables,
            )
        except Exception as error:
            if is_transport_error(error):
                # A synchronous call can also pump corpus code (reporters, settle):
                # a lost session means FontLab may be hung in it (review H2).
                self.host_busy = True
            self.calls.append(
                {
                    "name": step,
                    "error": scrub(str(error))[-800:],
                    "seconds": time.monotonic() - t0,
                }
            )
            raise
        self.calls.append(
            {
                "name": step,
                "stderr": scrub(completed.stderr[-600:]),
                "seconds": round(time.monotonic() - t0, 2),
            }
        )
        return completed.value

    def call_deferred(self, step: str, code: str, **variables):
        """``code`` schedules work with ``deferred(...)``; wait until FontLab
        confirms it finished or was cancelled by its in-host deadline.

        The client never walks away from running corpus code: a dropped session
        is replaced and polling continues; if completion is still unconfirmed
        ``CONFIRM_GRACE`` seconds after the deadline, HostStillBusy stops this
        target and run_all.sh stops the batch (no further runs are queued).
        Any other exit before confirmation (a session lost while scheduling, an
        interrupt while polling) is HostStillBusy too (review I5 b, c)."""
        # Pessimistic: busy from before the scheduling call until FontLab
        # confirms the deferred work finished (review H1); any exit in between,
        # whatever its type, leaves host_busy set and ends in exit 3.
        self.host_busy = True
        try:
            self.call(step, code, **variables)
        except Exception as error:
            if is_transport_error(error):
                self._busy(
                    f"{step}: session lost while scheduling (code may be queued)", error
                )
            # An in-host error may still follow a queued deferred() (review M3):
            # confirm before re-raising it.
            try:
                self._confirm(step)
            except HostStillBusy:
                raise
            except BaseException as again:  # noqa: BLE001 - re-raised as HostStillBusy
                self._busy(f"{step}: interrupted while confirming", again)
            self.host_busy = False
            raise
        except BaseException as error:  # noqa: BLE001 - re-raised as HostStillBusy
            self._busy(f"{step}: interrupted while scheduling", error)
        try:
            t0 = self._confirm(step)
        except HostStillBusy:
            raise
        except BaseException as error:  # noqa: BLE001 - re-raised as HostStillBusy
            self._busy(
                f"{step}: interrupted before FontLab confirmed completion", error
            )
        self.host_busy = False
        return t0

    def _busy(self, message: str, error: BaseException) -> None:
        self.host_busy = True  # skip teardown/close calls into a busy host
        raise HostStillBusy(message) from error

    def _confirm(self, step: str) -> float:
        t0 = time.monotonic()
        cap = float(self.target.get("deadline", 40)) + CONFIRM_GRACE
        while True:
            try:
                state = self.call(step + "-wait", WAIT, guard=None)
            except Exception as error:  # noqa: BLE001 - classified below
                transport = is_transport_error(error)
                self.calls.append(
                    {
                        "name": step + ("-reconnect" if transport else "-poll-error"),
                        "error": scrub(str(error))[-300:],
                    }
                )
                time.sleep(2)
                if transport:
                    self._reconnect()
            else:
                # Reading the answer is client code: a bug here propagates and
                # fences at once instead of reconnecting until the cap (L8).
                if state["done"]:
                    self.deadline_events.append(
                        {
                            "step": step,
                            "timed_out": bool(state.get("timed_out")),
                            "injections": list(state.get("injections") or []),
                        }
                    )
                    return t0
                if state["stuck"]:
                    self.host_busy = True
                    raise HostStillBusy(
                        f"{step}: corpus code stuck past its deadline inside FontLab"
                    )
                time.sleep(WAIT_PAUSE)  # WAIT never blocks inside FontLab
            if time.monotonic() - t0 > cap:
                self.host_busy = True  # skip teardown/close calls into a busy host
                raise HostStillBusy(
                    f"{step}: FontLab did not confirm completion or cancellation within {cap:g} s"
                )

    def _reconnect(self) -> None:
        """Close the failed session, then open one new session (review I4)."""
        from fontlab_remopy import FontLab

        old, self._client = self._client, None
        if old is not None:  # closing waits for a hung call: bounded, else abandoned
            errors: list[str] = []

            def close() -> None:
                try:
                    old.__exit__(None, None, None)
                except Exception as error:  # noqa: BLE001 - it already failed
                    errors.append(scrub(str(error))[-200:])

            closer = threading.Thread(
                target=close, name="close-old-session", daemon=True
            )
            closer.start()
            closer.join(CLOSE_TIMEOUT)
            if closer.is_alive() or errors:
                self.calls.append(
                    {
                        "name": "close-old-session",
                        "abandoned": closer.is_alive(),
                        "error": errors[0] if errors else "",
                    }
                )
        try:
            client = FontLab(timeout=CALL_TIMEOUT)
            self.fl = client.__enter__()
            self._client = client
        except Exception as error:  # noqa: BLE001 - the next poll retries
            self.fl = None  # never poll a closed client (review M2)
            self.calls.append(
                {"name": "reconnect-failed", "error": scrub(str(error))[-300:]}
            )

    @contextlib.contextmanager
    def fontlab(self):
        require_workspace()
        from fontlab_remopy import FontLab

        (self.scratch / "out").mkdir(exist_ok=True)
        # Default dialog answers: outputs go to the run's scratch "out" folder.
        answers = {"get_folder": "@scratch/out", "get_save_file": "@scratch/out/export"}
        answers.update(self.target.get("answers") or {})
        for key, value in list(
            answers.items()
        ):  # "@scratch/x" -> an owned scratch path
            if isinstance(value, str) and value.startswith("@scratch/"):
                answers[key] = str(self.scratch / value[len("@scratch/") :])
        # Waiting calls block while deferred corpus code runs on the GUI thread:
        # allow long whole-font scripts (the 30 s default would abandon the session).
        self._client = FontLab(timeout=CALL_TIMEOUT)
        fl = self.fl = self._client.__enter__()
        try:
            info = self.call(
                "setup",
                SETUP,
                launcher=str(LAUNCHER),
                home=str(self.scratch / "home"),
                defaults=str(self.scratch / "glyphs-defaults.json"),
                fault_log=str(self.scratch / "faulthandler.log"),
                deadline=float(self.target.get("deadline", 40)),
                answers=answers,
                stub_callbacks=list(self.target.get("stub_callbacks") or []),
            )
            self.environment.update(
                host="FontLab",
                host_build=info.get("app_version"),  # applicationVersion, e.g. 9.0.9783
                python=info["python"],
                os=info["os"],
                arch=info["arch"],
                qt=info["qt"],
            )
            self.note(
                "launcher",
                {
                    "file": str(LAUNCHER),
                    "glyport": info["glyport"],
                    "site": info["site"],
                },
            )
            self.clause(
                "deployed launcher loaded glyport from this checkout's src",
                info["src"] == str(REPO / "src")
                and info["glyport"].startswith(info["src"]),
                info,
            )
            try:
                yield fl
            finally:
                if self.host_busy:
                    self.note("teardown", "skipped: FontLab did not confirm completion")
                else:
                    self._teardown()
                self.fl = None
        finally:
            if self._client is not None:
                client, self._client = self._client, None
                if not self.host_busy:
                    client.__exit__(None, None, None)
                else:  # the portal would wait up to 900 s for the hung call (L10);
                    # the process exits 3 right after, which closes the session
                    self.calls.append({"name": "close-busy-session", "skipped": True})

    def _teardown(self) -> None:
        teardown = self.call("teardown", TEARDOWN)
        self.note("teardown", teardown)
        self.clause(
            "cleanup: handles closed, no windows left, sys.path/HOME/cwd restored",
            not teardown["failures"]
            and not teardown["windows_left"]
            and teardown["path_restored"]
            and teardown["env_restored"]
            and teardown["cwd_restored"],
            teardown,
        )

    @contextlib.contextmanager
    def owned_font(self):
        extra = []
        try:
            for name in self.target.get("other_fonts", []):
                copy = self.scratch / ("other-" + Path(FIXTURES[name]).name)
                shutil.copyfile(GETGO / FIXTURES[name], copy)
                known = {f["id"] for f in self.fl.fonts()}
                self.fl.open_font(path=str(copy))
                extra += sorted({f["id"] for f in self.fl.fonts()} - known)
            self.other_ids = list(extra)
            with self._main_font() as font_id:
                yield font_id
        finally:
            if not self.host_busy:
                self._close_extra(extra)

    def _close_extra(self, extra: list) -> None:
        for font_id in extra:
            self._retry("close-other", self.fl.close_font, font_id=font_id, save=False)
        if extra:
            left = sorted(set(extra) & {f["id"] for f in self.fl.fonts()})
            self.clause(
                "cleanup: extra owned font copies closed unsaved", not left, left
            )

    @contextlib.contextmanager
    def _main_font(self):
        fixture = GETGO / FIXTURES[self.target.get("fixture", "cafe")]
        copy = self.scratch / fixture.name
        shutil.copyfile(fixture, copy)
        before = {f["id"] for f in self.fl.fonts()}
        self.fl.open_font(path=str(copy))
        self.font_id = next(iter({f["id"] for f in self.fl.fonts()} - before))
        self.note(
            "fixture",
            {
                "name": self.target.get("fixture", "cafe"),
                "file": fixture.name,
                "sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
            },
        )
        try:
            yield self.font_id
        finally:
            if not self.host_busy:
                self._close_main(before)

    def _close_main(self, before: set) -> None:
        self._retry("close", self.fl.close_font, font_id=self.font_id, save=False)
        left = {f["id"] for f in self.fl.fonts()} - before
        self.clause("cleanup: owned font copy closed unsaved", not left, sorted(left))

    def _retry(self, step: str, function, **arguments):
        """FontLab refuses save/close while a save is in progress (its own
        backup save after an edit, mcptools_file.cpp saveInProgress)."""
        for attempt in range(30):
            try:
                return function(**arguments)
            except Exception as error:
                if "save is already in progress" not in str(error) or attempt == 29:
                    raise
                self.calls.append({"name": step, "retry": attempt})
                time.sleep(0.5)
        return None

    def save_copy(self, label: str) -> dict:
        path = self.scratch / f"{label}.vfj"
        self._retry(
            "save-" + label, self.fl.save_font, font_id=self.font_id, path=str(path)
        )
        return json.loads(path.read_text(encoding="utf-8"))

    def save_others(self, label: str) -> list[dict]:
        """FontLab-saved copies of the other owned fonts (scripts that write
        into other open fonts are judged on these)."""
        found = []
        for index, font_id in enumerate(getattr(self, "other_ids", [])):
            path = self.scratch / f"{label}-other-{index}.vfj"
            self._retry(
                "save-other-" + label,
                self.fl.save_font,
                font_id=font_id,
                path=str(path),
            )
            found.append(json.loads(path.read_text(encoding="utf-8")))
        return found

    def show_glyphs(self) -> list[str]:
        text = self.target.get("tab", "A")
        nodes = self.call(
            "tab",
            TAB,
            font_id=self.font_id,
            text=text,
            select_nodes=bool(self.target.get("select_nodes")),
            select_anchor=self.target.get("select_anchor"),
        )
        prepared = None
        if self.target.get("prepare"):  # e.g. add a brace layer the script works on
            prepared = self.call(
                "prepare",
                PREPARE,
                font_id=self.font_id,
                prepare="\n".join(self.target["prepare"]),
            )
        selection = self.call("selection", SELECTION, font_id=self.font_id)
        self.note(
            "selection",
            {
                "tab": text,
                "selected_layers": selection,
                "selected_nodes": nodes,
                "prepared": prepared,
            },
        )
        return selection

    # --- result ----------------------------------------------------------------------
    def status(self) -> str:
        # A ruled classification still needs its oracle (the faithful Glyphs result
        # up to the ruled point) to hold; otherwise the target failed.
        if self.classification and oracle_verdict(self.clauses)["verdict"] != "failed":
            return "classified"
        if self.clauses and all(c["asserted"] for c in self.clauses):
            return "passed"
        return "failed"

    def receipt(self, status: str) -> dict:
        target = self.target
        repo, _, rel = target["path"].partition("/")
        if target.get("probe"):  # a G1 calibration script outside the corpus
            repo, rel = "g1-calibration-probe", Path(target["path"]).name
        receipt_status = {
            "passed": "passed",
            "failed": "failed",
            "classified": "blocked",
        }[status]
        issues = [
            ReceiptDiagnostic(
                "CLAUSE_NOT_ASSERTED", "warning", f"{c['clause']}: {c['detail']}"[:900]
            )
            for c in self.clauses
            if not c["asserted"]
        ]
        if self.classification:
            issues.append(
                ReceiptDiagnostic("CLASSIFIED", "info", self.classification[:900])
            )
        for name, value in self.environment.items():
            if value is None:
                issues.append(
                    ReceiptDiagnostic(
                        "FACT_UNAVAILABLE",
                        "info",
                        "Not observed by this driver.",
                        field="environment." + name,
                    )
                )
        receipt = Receipt(
            f"realuse-{target['id']}-{self.started}",
            ReceiptSource(repo, None, rel, target.get("sha256"), {}),
            ReceiptEnvironment(**self.environment),
            ReceiptAdapter(
                f"fontlab-glyport {self.revision}",
                self.profile or "unobserved",  # as resolved by glyport in the run
                "realuse-106",
            ),
            (),
            (
                Capability(
                    "realuse-target",
                    receipt_status,
                    tuple(
                        f"{'asserted' if c['asserted'] else 'NOT asserted'}: {c['clause']}"
                        for c in self.clauses
                    )
                    or ("no clauses",),
                ),
            ),
            (
                Stage(
                    "realuse",
                    receipt_status,
                    self.started,
                    now(),
                    tuple(self.evidence) or ("no evidence",),
                ),
            ),
            (),
            tuple(issues),
        ).to_dict()
        if target.get("sha256") is None:
            receipt["diagnostics"].append(
                ReceiptDiagnostic(
                    "FACT_UNAVAILABLE",
                    "info",
                    "No single source file identifies this target.",
                    field="source.sha256",
                ).to_dict()
            )
        receipt["diagnostics"].append(
            ReceiptDiagnostic(
                "FACT_UNAVAILABLE",
                "info",
                "Corpus checkout revision not pinned per file; sha256 identifies it.",
                field="source.revision",
            ).to_dict()
        )
        errors = validate_receipt(receipt, public=False)
        if errors:
            raise ValueError("invalid receipt: " + "; ".join(errors))
        return receipt

    def keep_artifacts(self) -> str | None:
        """Archive the run's oracle inputs (saved VFJ copies, exports, oracle
        context) next to the scratch root, so oracles can be re-evaluated
        host-side (reevaluate.py) without another native run."""
        if not (self.scratch / "oracle-context.json").is_file():
            return None
        folder = self.scratch.parent.parent / "artifacts"
        folder.mkdir(parents=True, exist_ok=True)
        base = folder / f"{self.target['id']}-{STAMP}"
        archive = shutil.make_archive(
            str(base), "gztar", root_dir=self.scratch, base_dir="."
        )
        return archive

    def finish(self, error: BaseException | None = None) -> int:
        """Write the receipt; 3 whenever FontLab may still run corpus code, even
        if writing the receipt fails (review H1)."""
        busy = self.host_busy or isinstance(error, HostStillBusy)
        try:
            return self._finish(error, busy)
        except BaseException as failure:
            if not busy:
                raise
            print(f"receipt not written ({type(failure).__name__}: {failure})")
            return 3

    def deadline_clauses(self) -> None:
        """Every confirmed deferred step, of every target kind (review M4)."""
        if not self.deadline_events:
            return
        late = [e["step"] for e in self.deadline_events if e["timed_out"]]
        self.clause(
            "corpus code finished within the in-FontLab deadline (every deferred step)",
            not late,
            {"timed_out": late, "deadline_s": self.target.get("deadline", 40)},
        )
        injections = [r for e in self.deadline_events for r in e["injections"]]
        if injections:  # 0 means the deadline never reached the GUI thread
            self.clause(
                "every deadline injection reached FontLab's GUI thread",
                all(r == 1 for r in injections),
                {"injections": injections},
            )

    def _finish(self, error: BaseException | None, busy: bool) -> int:
        if error is not None:
            self.clause(
                "driver completed without exception",
                False,
                "".join(traceback.format_exception(error))[-1500:],
            )
        self.deadline_clauses()
        status = self.status()
        record = {
            "id": self.target["id"],
            "kind": self.target["kind"],
            "protocol": self.target.get("protocol"),
            "path": self.target["path"],
            "glyport_revision": self.revision,
            "status": status,
            "classification": self.classification,
            "clauses": self.clauses,
            "data": self.data,
            "calls": self.calls,
            "deadline_events": self.deadline_events,
            "receipt": self.receipt(status),
            "oracle": oracle_verdict(self.clauses),
            "artifacts": None if busy else self.keep_artifacts(),
            "host_busy": busy,
        }
        with (self.out / f"{self.target['id']}-{STAMP}.json").open("x") as stream:
            stream.write(json.dumps(record, indent=1, default=repr) + "\n")
        if busy:  # FontLab's HOME/cwd and the open copy still live there (L6)
            print(f"scratch kept (host busy): {self.scratch}")
        else:
            shutil.rmtree(self.scratch, ignore_errors=True)
        asserted = sum(c["asserted"] for c in self.clauses)
        print(
            f"{self.target['id']}: {status} ({asserted}/{len(self.clauses)} clauses)"
            + (f" [{self.classification}]" if self.classification else "")
        )
        for c in self.clauses:
            print(
                ("  ok   " if c["asserted"] else "  MISS ")
                + c["clause"]
                + ("" if c["asserted"] else " :: " + c["detail"][:600])
            )
        if busy:
            print("HOST-STILL-BUSY: " + str(error))
            return 3
        return 0 if status in ("passed", "classified") else 1
