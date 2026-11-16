# this_file: tests/test_realuse_harness.py
"""Host-side pieces of the issue-106 real-use harness (no FontLab, no corpus).

Pure helpers and packaged GetGo fixtures work outside the native workspace.
"""

import importlib
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _no_outer_tracer():
    """These tests arm and assert sys.settrace deadline guards, and a thread has
    one trace function: a coverage tracer would be replaced by (and would itself
    trace) the guards under test. Suspend it, for new threads too, per test. The
    guarded code lives in native-drivers/, outside the measured src/."""
    import threading

    outer, outer_threads = sys.gettrace(), threading.gettrace()
    sys.settrace(None)
    threading.settrace(None)
    try:
        yield
    finally:
        threading.settrace(outer_threads)
        sys.settrace(outer)


DRIVERS = Path(__file__).resolve().parents[1] / "native-drivers/realuse"
HARNESS = DRIVERS


def load(name):
    sys.path.insert(0, str(DRIVERS))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(DRIVERS))


def vfj(*glyphs, kerning=None):
    master = {"fontMaster": {"name": "Regular", "kerning": kerning or {}}}
    return {"font": {"glyphs": list(glyphs), "masters": [master]}}


def glyph(name, width=500, anchors=None, elements=None):
    layer = {"name": "Regular", "advanceWidth": width}
    if anchors is not None:
        layer["anchors"] = anchors
    if elements is not None:
        layer["elements"] = elements
    return {"name": name, "layers": [layer]}


def test_vfj_diff_when_layer_keys_change_then_reports_glyph_and_keys():
    common = load("realuse_common")
    before = vfj(glyph("A"), glyph("B", anchors=[{"name": "top", "point": "1 2"}]))
    after = vfj(glyph("A", width=510), glyph("B", anchors=[]), glyph("C"))
    diff = common.vfj_diff(before, after)
    assert diff["changed"] == {"A": ["advanceWidth"], "B": ["anchors"]}, diff
    assert diff["added"] == ["C"] and diff["removed"] == [] and diff["font"] == []


def test_vfj_diff_when_only_kerning_changes_then_font_key_reported():
    common = load("realuse_common")
    diff = common.vfj_diff(vfj(glyph("A")), vfj(glyph("A"), kerning={"A": {"A": -10}}))
    assert diff == {
        "added": [],
        "removed": [],
        "changed": {},
        "font": ["masters"],
        "auto_rebuilt": [],
    }


def test_vfj_diff_when_identical_then_empty():
    common = load("realuse_common")
    font = vfj(glyph("A", elements=[{"component": {"glyphName": "B"}}]))
    assert common.vfj_diff(font, font) == {
        "added": [],
        "removed": [],
        "changed": {},
        "font": [],
        "auto_rebuilt": [],
    }


def auto_glyph(flags, locked, anchors):
    element = {"component": {"glyphName": "A"}, **({"locked": True} if locked else {})}
    layer = {
        "name": "Regular",
        "flags": flags,
        "elements": [element],
        "anchors": anchors,
    }
    return {"name": "Aacute", "layers": [layer]}


def test_vfj_diff_when_auto_layer_rebuilt_by_fontlab_then_not_a_change():
    common = load("realuse_common")
    top, stale = {"name": "top", "point": "1 2"}, {"name": "acute", "point": "3 4"}
    before = vfj(auto_glyph(16, True, [stale, top]))
    diff = common.vfj_diff(before, vfj(auto_glyph(16, False, [top])))
    assert diff["changed"] == {} and diff["auto_rebuilt"] == ["Aacute"], diff
    moved = vfj(auto_glyph(16, False, [{"name": "top", "point": "9 9"}]))
    assert common.vfj_diff(before, moved)["changed"] == {
        "Aacute": ["anchors", "elements"]
    }, "a moved anchor is an edit"
    plain = common.vfj_diff(
        vfj(auto_glyph(0, True, [top])), vfj(auto_glyph(0, False, [top]))
    )
    assert plain["changed"] == {"Aacute": ["elements"]}, "only auto layers are exempt"


def test_diff_samples_when_changed_then_before_after_of_changed_keys_only():
    common = load("realuse_common")
    before, after = vfj(glyph("A", width=500)), vfj(glyph("A", width=520))
    samples = common.diff_samples(before, after, common.vfj_diff(before, after))
    assert samples == {"A": {"Regular": {"advanceWidth": ["500", "520"]}}}


def test_scrub_when_traceback_has_source_lines_then_only_locations_kept():
    common = load("realuse_common")
    text = 'File "x.py", line 3, in main\n    secret_corpus_code()\n    ^^^^^^\nValueError: x'
    scrubbed = common.scrub(text)
    assert "secret_corpus_code" not in scrubbed and "line 3, in main" in scrubbed


def row(path, score, api=(), kind="script", protocol=None):
    return {
        "path": path,
        "repository": path.split("/")[0],
        "score": score,
        "api": list(api),
        "kind": kind,
        "protocol": protocol,
        "excluded": [],
    }


def test_round_robin_when_authors_repeat_then_best_of_each_author_first_and_capped():
    select = load("select_targets")
    rows = [
        row("a--x/1.py", 9),
        row("a--y/2.py", 8),
        row("a--x/3.py", 7),
        row("b--z/4.py", 1),
    ]
    ordered = select.round_robin(rows, per_author=2)
    assert [r["path"] for r in ordered] == ["a--x/1.py", "b--z/4.py", "a--y/2.py"]


def test_pick_when_curated_exclusion_then_next_candidate_fills_in():
    select = load("select_targets")
    rows = [row("a--x/1.py", 9), row("b--x/2.py", 8), row("c--x/3.py", 7)]
    assert [r["path"] for r in select.pick(rows, 2, {"b--x/2.py": "reason"})] == [
        "a--x/1.py",
        "c--x/3.py",
    ]


def test_coverage_when_selection_misses_a_frequent_name_then_listed():
    select = load("select_targets")
    eligible = [row("a--x/1.py", 1, ["width", "name"]), row("b--x/2.py", 1, ["width"])]
    cover = select.coverage([eligible[1]], eligible, top=2)
    assert cover == {"top": 2, "covered": 1, "missing": ["name"]}


@pytest.mark.parametrize(
    ("source", "protocol"),
    [
        ("class A(ReporterPlugin):\n", "ReporterPlugin"),
        ("class A(FilterWithDialog, Mixin):\n", "FilterWithDialog"),
        ("class A(object):\n", None),
    ],
)
def test_protocol_of_when_class_bases_vary_then_sdk_base_found(source, protocol):
    assert load("select_targets").protocol_of(source) == protocol


def test_note_when_output_holds_a_printed_traceback_then_source_lines_dropped(tmp_path):
    common = load("realuse_common")
    run = common.Run.__new__(common.Run)
    run.data, run.evidence = {}, []
    printed = 'File "x.py", line 23, in erase\n    keys = secret_corpus_call()\n    ^^^^\nTypeError: boom'
    run.note("run", {"output": [printed]})
    assert (
        "secret_corpus_call" not in json.dumps(run.data)
        and "line 23, in erase" in run.data["run"]["output"][0]
    )


def deferred_scope(common, **settings):
    """The in-host ``deferred``/``deferred_reset`` helpers with an immediate timer."""
    import sys as _sys
    import threading as _threading
    from types import SimpleNamespace

    source = common.COMMON
    helpers = source[
        source.index("def deferred_reset(") : source.index("def errors_in")
    ]
    defaults = {"deadline": 0.05, "deadline_grace": 0.05, "deadline_interval": 0.05}
    st = SimpleNamespace(**{**defaults, **settings})
    timer = SimpleNamespace(
        singleShot=lambda ms, fn: fn()
    )  # the event loop runs it at once
    scope = {"st": st, "sys": _sys, "QtCore": SimpleNamespace(QTimer=timer)}
    exec(common.GUARD_SETUP, {})  # noqa: S102 - the shared deadline module
    guard = _sys.modules["_realuse_guard"]
    guard.escalate_seconds = settings.get("escalate_seconds", 0.5)
    guard.escalate_interval = 0.05
    exec(helpers, scope)  # noqa: S102 - the harness's own in-host helpers
    alive = lambda: [t for t in _threading.enumerate() if t.name == "realuse-deadline"]
    return st, scope, alive


def spin():
    return True


def runaway():
    # A corpus-style bare except in a loop whose condition makes a call: the
    # injection lands there (outside the try) once. A loop whose every check
    # point is inside the try cannot be ended this way; the stuck path covers it.
    while spin():
        try:
            sum(range(50))
        except BaseException:  # noqa: BLE001, S110
            pass


def test_deferred_when_corpus_code_runs_past_deadline_then_stopped_even_if_swallowed():
    common = load("realuse_common")
    # Each injection escapes a bare-except loop only when it lands outside the
    # try (e.g. at the loop's jump), so the test allows many attempts.
    st, scope, alive = deferred_scope(common, deadline_max_injections=500)
    scope["deferred"](runaway)
    assert st.deferred_done and st.deferred_timed_out and not st.deferred_stuck
    assert isinstance(st.deferred_error, TimeoutError)
    assert st.deferred_injections[0] == 1, (
        "PyThreadState_SetAsyncExc must find the GUI thread"
    )
    assert not alive(), "the watchdog stops once the guarded code returned"
    scope["deferred"](lambda: None)
    assert st.deferred_done and not st.deferred_timed_out and st.deferred_error is None


def test_deferred_when_injection_lands_in_event_set_then_still_done_and_watchdog_stops(
    monkeypatch,
):
    import threading

    common = load("realuse_common")
    st, scope, alive = deferred_scope(common)
    original, raised = threading.Event.set, []

    def flaky_set(self):
        import sys

        # Only the wrapper's own finished.set(); Thread.start() also sets an Event.
        if not raised and sys._getframe(1).f_code.co_name == "wrapper":
            raised.append(True)
            raise TimeoutError("injected during Event.set")  # the C1 window
        original(self)

    monkeypatch.setattr(threading.Event, "set", flaky_set)
    scope["deferred"](lambda: None)
    assert raised and st.deferred_done, "the finally retries Event.set"
    assert not alive(), "the watchdog was stopped"


def test_deferred_when_injections_cannot_end_the_code_then_stuck_after_escalation():
    import _thread
    import threading
    import time

    common = load("realuse_common")
    st, scope, alive = deferred_scope(common, deadline_max_injections=3)
    gate = _thread.allocate_lock()
    gate.acquire()

    def native_wait():  # a native call: no injection or trace can interrupt it
        gate.acquire()

    runner = threading.Thread(target=lambda: scope["deferred"](native_wait))
    runner.start()
    deadline = time.monotonic() + 5
    while not st.deferred_stuck and time.monotonic() < deadline:
        time.sleep(0.01)
    assert st.deferred_stuck and st.deferred_timed_out, "reported stuck"
    assert st.deferred_escalations, "escalated before giving up"
    counts = len(st.deferred_injections), len(st.deferred_escalations)
    time.sleep(0.3)
    assert (len(st.deferred_injections), len(st.deferred_escalations)) == counts
    assert counts[0] == 3, "no injections after giving up"
    gate.release()
    runner.join(5)
    assert st.deferred_done and not alive()


def test_deferred_when_code_swallows_every_exception_then_escalation_ends_it():
    import _thread
    import threading
    import time

    common = load("realuse_common")
    st, scope, alive = deferred_scope(common, deadline_max_injections=3)
    swallowed = []

    def swallowing_loop():  # corpus hazard: bare except around a polling call
        lock = _thread.allocate_lock()
        lock.acquire()
        while True:
            try:
                lock.acquire(timeout=0.02)
            except:  # noqa: E722 - the pattern under test
                swallowed.append(1)

    t0 = time.monotonic()
    runner = threading.Thread(target=lambda: scope["deferred"](swallowing_loop))
    runner.start()
    runner.join(5)
    assert not runner.is_alive() and st.deferred_done and not st.deferred_stuck
    assert type(st.deferred_error).__name__ == "RealuseHalt", st.deferred_error
    assert len(swallowed) >= 3 and st.deferred_escalations
    assert time.monotonic() - t0 < 3 and not alive()
    assert sys.gettrace() is None


def test_deferred_cadence_when_late_then_grace_before_repeats():
    common = load("realuse_common")
    st, scope, alive = deferred_scope(
        common, deadline_grace=0.3, deadline_interval=0.05, deadline_max_injections=500
    )
    import time

    times = []

    def slow_cleanup():
        try:
            while spin():  # ends at the first injection (no bare except here)
                pass
        finally:
            t0 = time.monotonic()
            while (
                time.monotonic() - t0 < 0.25
            ):  # cleanup needing 250 ms after the first injection
                pass
            times.append(time.monotonic() - t0)

    scope["deferred"](slow_cleanup)
    assert times and times[0] >= 0.25, "cleanup finished inside the grace period"
    assert st.deferred_done and not alive()


def test_deferred_reset_clears_flags_for_steps_without_deferred_work():
    common = load("realuse_common")
    st, scope, _ = deferred_scope(common)
    st.deferred_timed_out, st.deferred_stuck, st.deferred_done = True, True, False
    scope["deferred_reset"](done=True)
    assert (
        st.deferred_done,
        st.deferred_timed_out,
        st.deferred_stuck,
        st.deferred_error,
    ) == (
        True,
        False,
        False,
        None,
    )
    for snippet in ("DRIVE_STEP", "TRIGGER_START"):
        code = getattr(load("run_realuse"), snippet).replace(
            common.COMMON, ""
        )  # the step's own code
        assert (
            "st.deferred_done = True" not in code
            and "deferred_reset(done=True)" in code
        ), snippet
    setup = common.SETUP
    assert "deferred_reset(done=True)" in setup, "SETUP initialises the flags (I1)"


class NativeExecutionError(RuntimeError):
    """Stand-in with remopy's class name: the host answered with an error."""


@pytest.mark.parametrize(
    ("error", "transport"),
    [
        (ConnectionError("x"), True),
        (RuntimeError("Connect FontLab with a fresh context before calling"), True),
        (RuntimeError("Connect FontLab using a with context before calling"), True),
        (
            NativeExecutionError(
                "FontLab execution failed: Cannot connect to FontLab 9."
            ),
            True,
        ),
        (
            NativeExecutionError(
                "FontLab execution failed: FontLab MCP authentication failed."
            ),
            True,
        ),
        (type("ClosedResourceError", (Exception,), {})(), True),  # anyio: no message
        (type("EndOfStream", (Exception,), {})(), True),
        (
            NativeExecutionError("FontLab execution failed: {'type': 'TimeoutError'}"),
            False,
        ),
        (
            NativeExecutionError("FontLab execution failed: {'type': 'NameError'}"),
            False,
        ),
    ],
)
def test_is_transport_error_when_classifying_then_only_host_answers_are_in_host(
    error, transport
):
    """Only a NativeExecutionError carrying an in-host Python error proves the host
    answered (review L4: message-less anyio errors are transport)."""
    assert load("realuse_common").is_transport_error(error) is transport


def bare_run(common, answers, deadline=0.0):
    run = common.Run.__new__(common.Run)
    run.target, run.calls, run.host_busy = {"deadline": deadline}, [], False
    run.deadline_events = []
    replies = iter(answers)

    def call(step, code, **variables):
        if not step.endswith("-wait"):
            return True
        reply = next(replies)
        if isinstance(reply, BaseException):
            raise reply
        return {"done": reply, "stuck": False, "timed_out": False, "injections": []}

    run.call = call
    run._reconnect = lambda: run.calls.append({"name": "reconnected"})
    return run


def test_call_deferred_when_session_drops_then_reconnects_and_waits_for_confirmation(
    monkeypatch,
):
    common = load("realuse_common")
    monkeypatch.setattr(common.time, "sleep", lambda s: None)
    run = bare_run(
        common, [False, ConnectionError("bridge dropped"), False, True], deadline=40
    )
    run.call_deferred("run", "code")
    assert {"name": "reconnected"} in run.calls and not run.host_busy, run.calls


def test_call_deferred_when_never_confirmed_then_host_still_busy_and_no_teardown(
    monkeypatch,
):
    common = load("realuse_common")
    monkeypatch.setattr(common.time, "sleep", lambda s: None)
    monkeypatch.setattr(common, "CONFIRM_GRACE", 0.0)
    run = bare_run(common, [False] * 1000)
    with pytest.raises(common.HostStillBusy):
        run.call_deferred("run", "code")
    assert run.host_busy, "teardown/close calls must be skipped for a busy host"


def test_call_deferred_when_interrupted_before_confirmation_then_host_still_busy():
    common = load("realuse_common")
    run = bare_run(common, [KeyboardInterrupt()], deadline=40)
    with pytest.raises(common.HostStillBusy):
        run.call_deferred("run", "code")
    assert run.host_busy, "(b) an interrupt while polling fences and skips teardown"


def test_call_deferred_when_scheduling_call_loses_the_session_then_host_still_busy():
    common = load("realuse_common")
    run = bare_run(common, [])

    def call(step, code, **variables):
        raise ConnectionError("bridge dropped while scheduling")

    run.call = call
    with pytest.raises(common.HostStillBusy):
        run.call_deferred("run", "code")
    assert run.host_busy, "(c) the code may already be queued: fence"


def test_call_deferred_when_scheduling_snippet_fails_in_host_then_confirms_then_plain_error():
    common = load("realuse_common")
    run = bare_run(common, [True])  # review M3: one WAIT confirms nothing is running
    waits = run.call

    def call(step, code, **variables):
        if step.endswith("-wait"):
            return waits(step, code)
        raise NativeExecutionError("FontLab execution failed: {'type': 'NameError'}")

    run.call = call
    with pytest.raises(NativeExecutionError):
        run.call_deferred("run", "code")
    assert not run.host_busy, "confirmed idle after the in-host error"
    assert [c for c in run.calls if c.get("name") == "reconnected"] == []


def test_reconnect_when_new_session_fails_then_fl_none_and_next_poll_reconnects(
    monkeypatch,
):
    import sys
    import types

    common = load("realuse_common")
    run = common.Run.__new__(common.Run)
    run.calls, run._client, run.fl = [], None, object()
    attempts = []

    class FailingFontLab:
        def __init__(self, timeout):
            attempts.append(timeout)

        def __enter__(self):
            raise ConnectionError("FontLab not reachable")

    monkeypatch.setitem(
        sys.modules, "fontlab_remopy", types.SimpleNamespace(FontLab=FailingFontLab)
    )
    run._reconnect()
    assert run.fl is None and len(attempts) == 1
    with pytest.raises(ConnectionError):  # a transport error: the next poll reconnects
        run.call("x-wait", "code")


def test_deferred_when_stuck_with_default_cap_then_ten_injections_then_escalation():
    import _thread
    import threading
    import time

    common = load("realuse_common")
    st, scope, _ = deferred_scope(common, deadline_interval=0.01, deadline_grace=0.01)
    gate = _thread.allocate_lock()
    gate.acquire()
    runner = threading.Thread(target=lambda: scope["deferred"](gate.acquire))
    runner.start()
    deadline = time.monotonic() + 10
    while not st.deferred_stuck and time.monotonic() < deadline:
        time.sleep(0.01)
    gate.release()
    runner.join(5)
    assert st.deferred_stuck and len(st.deferred_injections) == 10, (
        "default cap (review b)"
    )
    assert st.deferred_escalations


def test_deferred_when_giving_up_as_stuck_then_pending_injection_fires_in_the_call():
    import _thread
    import threading
    import time

    common = load("realuse_common")
    st, scope, alive = deferred_scope(common, deadline_max_injections=2)
    gate = _thread.allocate_lock()
    gate.acquire()
    runner = threading.Thread(target=lambda: scope["deferred"](gate.acquire))
    runner.start()
    deadline = time.monotonic() + 5
    while not st.deferred_stuck and time.monotonic() < deadline:
        time.sleep(0.01)
    assert st.deferred_stuck
    gate.release()
    runner.join(5)
    assert st.deferred_done and not alive()
    # Not cleared (SetAsyncExc(id, NULL) is the CPython 3.11 hang): the pending
    # injection is delivered inside the guarded call once it returns to Python.
    assert type(st.deferred_error).__name__ in {"TimeoutError", "RealuseEscalation"}


def test_collect_snippets_report_injection_results():
    run_realuse = load("run_realuse")
    for name in ("RUN_COLLECT", "DRIVE_COLLECT", "TRIGGER_COLLECT"):
        assert "injections=st.deferred_injections" in getattr(run_realuse, name), name


def test_sigterm_handler_when_signalled_then_raises_into_call_deferred():
    run_realuse = load("run_realuse")
    with pytest.raises(KeyboardInterrupt):
        run_realuse.interrupted(15, None)


def test_main_when_started_then_installs_the_sigterm_handler(monkeypatch, tmp_path):
    run_realuse = load("run_realuse")
    monkeypatch.setattr(run_realuse, "require_workspace", lambda: tmp_path)  # fake native boundary
    installed = []
    monkeypatch.setattr(run_realuse.signal, "signal", lambda *a: installed.append(a))
    monkeypatch.setattr(
        run_realuse, "Run", lambda *a: (_ for _ in ()).throw(SystemExit(9))
    )
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps({"targets": [{"id": "a", "kind": "script", "path": "a"}]})
    )
    with pytest.raises(SystemExit):
        run_realuse.main(["--manifest", str(manifest), "--out", str(tmp_path), "a"])
    assert (run_realuse.signal.SIGTERM, run_realuse.interrupted) in installed, (
        "review I5 (a)"
    )


def test_main_when_interrupted_outside_deferred_work_then_stops_the_batch(
    monkeypatch, tmp_path
):
    run_realuse = load("run_realuse")
    monkeypatch.setattr(run_realuse, "require_workspace", lambda: tmp_path)  # fake native boundary
    started = []

    class FakeRun:
        def __init__(self, target, out, scratch):
            self.target = target
            self.host_busy = False
            started.append(target["id"])

        def finish(self, error=None):
            return 1  # an ordinary failed receipt

    def interrupted_script(run):
        raise KeyboardInterrupt("signal 15")  # e.g. during save_copy or collect

    monkeypatch.setattr(run_realuse, "Run", FakeRun)
    monkeypatch.setattr(run_realuse, "run_script_target", interrupted_script)
    monkeypatch.setattr(run_realuse.signal, "signal", lambda *a: None)
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps(
            {"targets": [{"id": i, "kind": "script", "path": i} for i in ("a", "b")]}
        )
    )
    code = run_realuse.main(
        ["--manifest", str(manifest), "--out", str(tmp_path), "a", "b"]
    )
    assert code not in (0, 1) and started == ["a"], (code, started)


def test_call_deferred_when_scheduling_error_and_code_never_confirms_then_host_still_busy(
    monkeypatch,
):
    common = load("realuse_common")
    monkeypatch.setattr(common.time, "sleep", lambda s: None)
    monkeypatch.setattr(common, "CONFIRM_GRACE", 0.0)
    run = bare_run(common, [False] * 1000)

    def call(step, code, **variables):
        if step.endswith("-wait"):
            return {"done": False, "stuck": False}
        raise NativeExecutionError("FontLab execution failed: {'type': 'RuntimeError'}")

    run.call = call
    with pytest.raises(common.HostStillBusy):
        run.call_deferred("drive-0", "code")
    assert run.host_busy, "M3: work queued before the error is fenced"


def test_call_deferred_when_confirmed_then_records_deadline_event():
    common = load("realuse_common")
    run = bare_run(common, [True])
    run.call_deferred("run", "code")
    assert not run.host_busy and run.deadline_events == [
        {"step": "run", "timed_out": False, "injections": []}
    ]


def test_call_deferred_when_reading_the_answer_fails_then_fences_at_once():
    common = load("realuse_common")
    run = bare_run(common, [])
    run.call = lambda step, code, **v: (
        True if not step.endswith("-wait") else {"oops": 1}
    )
    with pytest.raises(common.HostStillBusy):
        run.call_deferred("run", "code")
    assert run.host_busy and not run.calls, "L8: no reconnect churn on a client bug"


def real_run(common, tmp_path, **target):
    target = {"id": "t-x", "kind": "script", "path": "x.py", **target}
    return common.Run(target, tmp_path / "out", tmp_path / "scratch")


def test_finish_when_busy_and_plain_error_then_3_and_scratch_kept(tmp_path):
    common = load("realuse_common")
    run = real_run(common, tmp_path)
    run.host_busy = True
    assert run.finish(RuntimeError("cleanup failed")) == 3
    assert run.scratch.exists(), "L6: FontLab's HOME/cwd still point into scratch"


def test_finish_when_busy_and_writing_the_receipt_fails_then_3(tmp_path, monkeypatch):
    common = load("realuse_common")
    run = real_run(common, tmp_path)
    run.host_busy = True

    def broken(error, busy):
        raise OSError("disk full")

    monkeypatch.setattr(run, "_finish", broken)
    assert run.finish(None) == 3


def test_main_when_busy_and_finish_interrupted_then_3(monkeypatch, tmp_path):
    run_realuse = load("run_realuse")
    monkeypatch.setattr(run_realuse, "require_workspace", lambda: tmp_path)  # fake native boundary

    class BusyRun:
        def __init__(self, target, out, scratch):
            self.target, self.host_busy = target, False

        def finish(self, error=None):
            raise KeyboardInterrupt("second signal while writing the receipt")

    def scheduled_then_killed(run):
        run.host_busy = True
        raise KeyboardInterrupt("signal 15")

    monkeypatch.setattr(run_realuse, "Run", BusyRun)
    monkeypatch.setattr(run_realuse, "run_script_target", scheduled_then_killed)
    monkeypatch.setattr(run_realuse.signal, "signal", lambda *a: None)
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps({"targets": [{"id": "a", "kind": "script", "path": "a"}]})
    )
    assert (
        run_realuse.main(["--manifest", str(manifest), "--out", str(tmp_path), "a"])
        == 3
    )


def test_fontlab_exit_when_busy_and_close_interrupted_then_host_still_busy_kept(
    monkeypatch, tmp_path
):
    import types

    common = load("realuse_common")
    monkeypatch.setattr(common, "require_workspace", lambda: tmp_path)  # fake native boundary
    src = str(common.REPO / "src")
    info = {
        "python": "3.11",
        "os": "Darwin",
        "arch": "arm64",
        "qt": "5.15",
        "glyport": src + "/fontlab_glyport/__init__.py",
        "site": "",
        "src": src,
    }

    class Session:
        def run(self, code, **variables):
            return types.SimpleNamespace(value=info, stderr="")

    class FakeFontLab:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return Session()

        def __exit__(self, *exc):
            raise KeyboardInterrupt("second signal while the portal waits")

    monkeypatch.setitem(
        sys.modules, "fontlab_remopy", types.SimpleNamespace(FontLab=FakeFontLab)
    )
    run = real_run(common, tmp_path)
    with pytest.raises(common.HostStillBusy), run.fontlab():
        run.host_busy = True
        raise common.HostStillBusy("deferred code unconfirmed")
    assert any(c.get("name") == "close-busy-session" for c in run.calls)


def test_status_when_classified_but_oracle_failed_then_failed(tmp_path):
    common = load("realuse_common")
    run = real_run(common, tmp_path)
    run.classification = "corpus-defect"
    run.clause("oracle: drawn before the defect", False)
    assert run.status() == "failed"
    run.clauses = [
        {"clause": "oracle: drawn before the defect", "asserted": True, "detail": ""}
    ]
    assert run.status() == "classified"


def test_synchronous_call_when_session_lost_then_busy_no_teardown_and_exit_3(
    monkeypatch, tmp_path
):
    import types

    common = load("realuse_common")
    monkeypatch.setattr(common, "require_workspace", lambda: tmp_path)  # fake native boundary
    run_realuse = load("run_realuse")
    src = str(common.REPO / "src")
    info = {
        "python": "3.11",
        "os": "Darwin",
        "arch": "arm64",
        "qt": "5.15",
        "glyport": src + "/fontlab_glyport/__init__.py",
        "site": "",
        "src": src,
    }
    sent = []

    class Session:
        def run(self, code, **variables):
            sent.append(code)
            if len(sent) == 1:
                return types.SimpleNamespace(value=info, stderr="")
            raise TimeoutError("run_python: no answer within 900 s")  # GUI thread hung

    class FakeFontLab:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return Session()

        def __exit__(self, *exc):
            raise AssertionError("a busy session must not be closed (L10)")

    monkeypatch.setitem(
        sys.modules, "fontlab_remopy", types.SimpleNamespace(FontLab=FakeFontLab)
    )
    run = real_run(common, tmp_path)
    with pytest.raises(TimeoutError) as caught, run.fontlab():
        run.call("paint-off", "pump()")  # a reporter painting corpus code hangs
    assert run.host_busy, "review H2"
    assert len(sent) == 2, "no TEARDOWN sent into the hung host"
    assert run_realuse.finish_or_busy(run, caught.value) == 3


def guarded(common, step_code, seconds, tail=""):
    """Run GUARD like one run_python request: in its own thread, so the request's
    outermost frame disappears when it ends (as in FontLab)."""
    import threading

    namespace = {
        "state": "_t",
        "step_code": step_code,
        "guard_seconds": seconds,
        "guard_step": "t",
    }
    caught = []

    def request():
        try:
            exec(common.GUARD + tail, namespace)  # noqa: S102 - the harness's own in-host guard
        except BaseException as error:  # noqa: BLE001 - inspected by the test
            caught.append(error)

    thread = threading.Thread(target=request, daemon=True)
    thread.start()
    thread.join(20)
    assert not thread.is_alive(), "the guard did not stop the request"
    if caught:
        raise caught[0]
    return namespace


def test_sync_guard_when_snippet_loops_forever_then_deadline_raised_and_cleared():
    import time

    common = load("realuse_common")
    t0 = time.monotonic()
    with pytest.raises(BaseException) as caught:
        guarded(common, "while True:\n    pass\n", 0.2)  # pure Python, no C calls
    assert type(caught.value).__name__ == "RealuseSyncDeadline"
    assert not isinstance(caught.value, Exception), (
        "corpus `except Exception` cannot swallow it"
    )
    assert time.monotonic() - t0 < 3
    guard = sys.modules["_realuse_guard"]
    assert guard.token is None and guard.events[-1]["injection"] == 1
    time.sleep(0.7)  # no stray injection lands after the guard stopped
    guard.events.clear()


def test_sync_guard_when_snippet_returns_then_result_kept_and_no_injection():
    import time

    common = load("realuse_common")
    namespace = guarded(
        common, "import sys\nst = sys.modules.get(state)\nresult = 41 + 1\n", 0.3
    )
    assert namespace["result"] == 42
    time.sleep(0.5)
    assert sys.modules["_realuse_guard"].events == []


def test_call_when_step_then_guarded_except_wait(tmp_path):
    import types

    common = load("realuse_common")
    run = real_run(common, tmp_path)
    sent = []

    class Session:
        def run(self, code, **variables):
            sent.append((code, variables))
            return types.SimpleNamespace(value=True, stderr="")

    run.fl = Session()
    run.call("settle", "result = 1")
    run.call("x-wait", common.WAIT, guard=None)
    (first, v1), (second, v2) = sent
    assert first == common.GUARD and v1["guard_seconds"] == common.SYNC_GUARD_SECONDS
    assert v1["step_code"].endswith("result = 1") and v1["guard_step"] == "settle"
    assert second == common.GUARD and v2["guard_seconds"] is None
    assert v2["step_code"].endswith(common.WAIT)


def test_sync_guard_when_snippet_returns_then_request_tail_is_never_injected():
    import time

    common = load("realuse_common")
    t0 = time.monotonic()
    # the "request" keeps running 1 s after its snippet: no injection may land there
    guarded(common, "result = 1", 0.2, tail="\nimport time\ntime.sleep(1.0)\n")
    assert time.monotonic() - t0 >= 1.0
    assert sys.modules["_realuse_guard"].events == []


def test_sync_guard_when_snippet_swallows_the_deadline_then_escalation_ends_it():
    import time

    common = load("realuse_common")
    t0 = time.monotonic()
    with pytest.raises(BaseException) as caught:
        guarded(
            common,
            "import time\nwhile True:\n    try:\n        time.sleep(0.005)\n    except:\n        pass\n",
            0.1,
        )
    assert type(caught.value).__name__ in {"RealuseSyncDeadline", "RealuseHalt"}
    assert time.monotonic() - t0 < 15  # 10 plain injections x 0.5 s, then escalation
    assert sys.gettrace() is None
    sys.modules["_realuse_guard"].events.clear()


def test_deferred_when_code_swallows_at_two_nested_levels_then_stuck_quickly():
    import threading
    import time

    common = load("realuse_common")
    st, scope, _ = deferred_scope(common, deadline_max_injections=3)
    stop = threading.Event()

    def nested_swallower():
        while not stop.is_set():
            try:
                while not stop.is_set():
                    try:
                        time.sleep(0.005)
                    except:  # noqa: E722, S110 - the hazard under test
                        pass
            except:  # noqa: E722, S110
                pass

    t0 = time.monotonic()
    runner = threading.Thread(
        target=lambda: scope["deferred"](nested_swallower), daemon=True
    )
    runner.start()
    while not (st.deferred_stuck or st.deferred_done) and time.monotonic() - t0 < 10:
        time.sleep(0.01)
    stop.set()
    runner.join(5)
    assert st.deferred_stuck or type(st.deferred_error).__name__ == "RealuseHalt"
    assert time.monotonic() - t0 < 5, "fails fast instead of waiting"


def test_sync_guard_faulthandler_cancelled_on_success_and_failure(tmp_path):
    import time

    common = load("realuse_common")
    exec(common.GUARD_SETUP, {})  # noqa: S102
    guard = sys.modules["_realuse_guard"]
    log = tmp_path / "fault.log"
    guard.fault_file, guard.fault_seconds = log.open("w"), 0.3
    try:
        guarded(common, "result = 1", 2.0)
        with pytest.raises(ZeroDivisionError):
            guarded(common, "1 / 0", 2.0)
        time.sleep(0.8)  # a pending repeat=True dump would have written by now
        guard.fault_file.flush()
        assert log.read_text() == "", "review (a): no dump left running"
    finally:
        guard.fault_file.close()
        guard.fault_file, guard.fault_seconds = None, 30
        guard.events.clear()


def test_polls_and_collects_never_pump_the_event_loop():
    common = load("realuse_common")
    run_realuse = load("run_realuse")
    readers = [
        common.WAIT,
        run_realuse.RUN_COLLECT,
        run_realuse.DRIVE_COLLECT,
        run_realuse.TRIGGER_COLLECT,
        run_realuse.INSTALL_COLLECT,
        run_realuse.APPLY_COLLECT,
        run_realuse.PAINT_COLLECT,
        run_realuse.SETTLE,
    ]
    for code in readers:
        body = code[len(common.COMMON) :]
        assert "pump(" not in body and "processEvents" not in body, body[:120]
    # corpus-reaching actions are scheduled only through deferred()
    for code in (
        run_realuse.INSTALL_START,
        run_realuse.APPLY_START,
        run_realuse.PAINT_START,
    ):
        assert "deferred(" in code[len(common.COMMON) :]


def test_sync_guard_when_injection_lands_in_guard_stop_then_stop_retried(tmp_path):
    """An injection made while the snippet ran but delivered after it ended lands
    in _guard_stop: the stop is retried, so the guard is retired and the request
    goes on (hang incidents 2026-10-16: nothing may reach the transport frames)."""
    import time

    common = load("realuse_common")
    marker = "def _guard_stop(guard):\n"
    once = (
        marker
        + "    if not _once:\n        _once.append(1)\n"
        + "        raise G.RealuseSyncDeadline('delivered in the stop')\n"
    )
    patched = common.GUARD.replace(marker, once)
    assert patched != common.GUARD

    class Patched:
        GUARD = patched

    namespace = {"_once": []}
    namespace.update(guarded_namespace(Patched, "result = 7", 0.3))
    assert namespace["result"] == 7 and namespace["_once"] == [1]
    guard = sys.modules["_realuse_guard"]
    assert guard.token is None and not set(guard.anchors) - _deferred_anchors(guard)
    time.sleep(0.6)
    assert guard.events == [], "no injection after the guard stopped"
    assert sys.gettrace() is None


def guarded_namespace(common, step_code, seconds):
    import threading

    namespace = {
        "_once": [],
        "state": "_t",
        "step_code": step_code,
        "guard_seconds": seconds,
        "guard_step": "t",
    }
    caught = []

    def request():
        try:
            exec(common.GUARD, namespace)  # noqa: S102 - the harness's own in-host guard
        except BaseException as error:  # noqa: BLE001 - inspected by the test
            caught.append(error)

    thread = threading.Thread(target=request, daemon=True)
    thread.start()
    thread.join(20)
    assert not thread.is_alive() and not caught, caught
    return namespace


def _deferred_anchors(guard):
    return {key for key, code in guard.anchors.items() if code.co_name == "wrapper"}


REQUEST = """
import time
try:
    exec(GUARD, namespace)
except BaseException as error:  # the snippet's own outcome
    outcome.append(type(error).__name__)
t = time.monotonic()
while time.monotonic() - t < tail:  # remopy's helper / FontLab's wrapper after the snippet
    pass
outcome.append("tail done")
"""


def run_request(common, step_code, seconds, tail):
    """One run_python request as FontLab nests it: the wrapper's globals hold
    __mcp_code; the GUARD runs inside; transport code runs after it."""
    import threading

    outcome, escaped = [], []
    namespace = {
        "state": "_t",
        "step_code": step_code,
        "guard_seconds": seconds,
        "guard_step": "t",
    }
    wrapper_globals = {
        "__mcp_code": "exec(helper, {})",
        "GUARD": common.GUARD,
        "namespace": namespace,
        "outcome": outcome,
        "tail": tail,
    }

    def request():
        try:
            exec(REQUEST, wrapper_globals)  # noqa: S102 - emulated FontLab request
        except BaseException as error:  # noqa: BLE001 - must stay empty
            escaped.append(error)

    thread = threading.Thread(target=request, daemon=True)
    thread.start()
    thread.join(30)
    assert not thread.is_alive(), "the request did not finish"
    return outcome, escaped


def test_sync_guard_when_snippet_ends_near_deadline_then_nothing_reaches_the_transport():
    import random

    common = load("realuse_common")
    guard_module = None
    for i in range(25):  # snippets ending just before, at and after the deadline
        busy = 0.08 + random.uniform(-0.03, 0.03)
        step = f"import time\nt = time.monotonic()\nwhile time.monotonic() - t < {busy}:\n    pass\n"
        outcome, escaped = run_request(common, step, 0.08, tail=0.6)
        assert not escaped, f"iteration {i}: {escaped!r} reached the transport frames"
        assert outcome[-1] == "tail done", outcome
        guard_module = sys.modules["_realuse_guard"]
        assert guard_module.token is None
    assert sys.gettrace() is None
    guard_module.events.clear()


def test_sync_guard_when_snippet_waits_in_nested_request_then_injections_skipped():
    """While the snippet pumps a nested run_python request (its frames hold
    __mcp_code), the watcher records skips instead of injecting into it."""
    common = load("realuse_common")
    nested = (
        "exec('import time\\nt = time.monotonic()\\nwhile time.monotonic() - t < 1.2:\\n    pass\\n',"
        " {'__mcp_code': 'nested request'})\nresult = 'nested done'\n"
    )
    namespace = guarded(common, nested, 0.1)
    guard = sys.modules["_realuse_guard"]
    assert namespace["result"] == "nested done"
    assert guard.events and all(
        str(e.get("injection")).startswith("skipped") for e in guard.events
    ), guard.events
    guard.events.clear()


def test_deferred_when_call_serves_a_guarded_nested_request_then_never_shot_into_it():
    """Review M6: deferred corpus code sitting in a modal loop while FontLab
    serves a WAIT (itself guarded): the deferred watchdog skips instead of
    injecting into that request."""
    import threading

    common = load("realuse_common")
    st, scope, alive = deferred_scope(common, deadline_max_injections=4)
    inner = "import time\nt = time.monotonic()\nwhile time.monotonic() - t < 0.8:\n    pass\nresult = 'inner'\n"
    served = {}

    def modal_loop():  # the corpus call; the nested request runs inside it
        inner_ns = {
            "state": "_t",
            "step_code": inner,
            "guard_seconds": None,
            "guard_step": "wait",
        }
        exec(  # noqa: S102 - emulated FontLab run_python request
            "exec(GUARD, inner_ns)",
            {"__mcp_code": "nested", "GUARD": common.GUARD, "inner_ns": inner_ns},
        )
        served["result"] = inner_ns["result"]

    runner = threading.Thread(target=lambda: scope["deferred"](modal_loop), daemon=True)
    runner.start()
    runner.join(20)
    assert served.get("result") == "inner", "the nested request was never injected"
    assert st.deferred_injections and all(
        str(r).startswith("skipped") for r in st.deferred_injections
    ), st.deferred_injections
    assert st.deferred_error is None and not alive()


def test_in_region_when_another_anchor_is_nearer_then_false():
    common = load("realuse_common")
    exec(common.GUARD_SETUP, {})  # noqa: S102
    guard = sys.modules["_realuse_guard"]
    seen = {}

    def inner():
        frame = sys._getframe()
        seen["outer"] = guard.in_region(frame, outer.__code__)
        seen["inner"] = guard.in_region(frame, inner.__code__)

    def outer():
        inner()

    for code in (outer.__code__, inner.__code__):
        guard.anchors[id(code)] = code
    try:
        outer()
    finally:
        for code in (outer.__code__, inner.__code__):
            guard.anchors.pop(id(code), None)
    assert seen == {"outer": False, "inner": True}


def test_deferred_shoot_takes_the_guard_lock():
    common = load("realuse_common")
    body = common.COMMON[common.COMMON.index("def shoot(exc)") :]
    assert body.index("with G.lock") < body.index("inject(target, exc)")


def guarded_with(common, step_code, seconds, **extra):
    import threading

    namespace = {
        "state": "_t",
        "step_code": step_code,
        "guard_seconds": seconds,
        "guard_step": "t",
        **extra,
    }
    caught = []

    def request():
        try:
            exec(common.GUARD, namespace)  # noqa: S102 - the harness's own in-host guard
        except BaseException as error:  # noqa: BLE001 - inspected by the test
            caught.append(error)

    thread = threading.Thread(target=request, daemon=True)
    thread.start()
    thread.join(20)
    assert not thread.is_alive() and not caught, caught
    return namespace


def test_main_guard_exits_through_exit_now_even_if_interrupted():
    run_realuse = load("run_realuse")
    import inspect

    source = inspect.getsource(run_realuse)
    tail = source[source.index('if __name__ == "__main__":') :]
    assert "code = 3" in tail and "finally:" in tail and "exit_now(code)" in tail
    body = inspect.getsource(run_realuse.exit_now)
    assert body.index("SIG_IGN") < body.rindex("os._exit(code)")


def test_escalation_when_armed_outside_a_guarded_snippet_then_no_trace():
    common = load("realuse_common")
    exec(common.GUARD_SETUP, {})  # noqa: S102
    guard = sys.modules["_realuse_guard"]
    guard.RealuseEscalation()  # e.g. an injection that reached transport code
    assert sys.gettrace() is None
    assert sys._getframe().f_trace is None


def test_escalation_when_armed_inside_snippet_then_traces_only_snippet_frames():
    common = load("realuse_common")
    exec(common.GUARD_SETUP, {})  # noqa: S102
    guard = sys.modules["_realuse_guard"]
    seen = {}

    def snippet():
        try:
            guard.RealuseEscalation()
            sum(range(3))  # next line of a region frame: RealuseHalt
        except BaseException as error:  # noqa: BLE001 - inspected below
            seen["error"] = type(error).__name__
            seen["outer"] = sys._getframe(1).f_trace

    guard.anchors[id(snippet.__code__)] = snippet.__code__
    guard.escalation_anchor = snippet.__code__
    try:
        snippet()
    finally:
        guard.anchors.pop(id(snippet.__code__), None)
        guard.escalation_anchor = None
        sys.settrace(None)
    assert seen["error"] == "RealuseHalt"
    assert seen["outer"] is None, "the caller frame is outside the region: never traced"


LEFT_OPEN = """
import contextlib, sys, threading
sys.path.insert(0, {harness!r})
import run_realuse
hung = threading.Event()
@contextlib.contextmanager
def portal():  # like remopy's anyio portal: closing waits for the hung call to end
    try:
        yield
    finally:
        hung.wait()
class Client:  # held in a reference cycle, as remopy's portal is: shutdown's gc closes it
    pass
client = Client()
client.session, client.me = portal(), client
client.session.__enter__()  # a busy session is deliberately left open (L10)
del client
print("receipt written", flush=True)
{leave}
"""


@pytest.mark.parametrize(
    ("leave", "finishes"),
    [("run_realuse.exit_now(3)", True), ("sys.exit(3)", False)],
)
def test_exit_when_busy_session_left_open_then_exit_now_never_blocks(
    tmp_path, leave, finishes
):
    """Root cause of the 36-minute client hang (2026-10-16): interpreter shutdown
    closes the open session's generator, which waits for the hung call."""
    import subprocess

    script = tmp_path / "left_open.py"
    script.write_text(LEFT_OPEN.format(harness=str(HARNESS), leave=leave))
    try:
        done = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except subprocess.TimeoutExpired:
        assert not finishes, "exit_now must not wait for the open session"
        return
    assert finishes, "sys.exit is expected to hang in finalization (control)"
    assert done.returncode == 3 and "receipt written" in done.stdout, done.stderr


def test_never_clears_an_injection_with_a_null_async_exception():
    """CPython 3.11: PyThreadState_SetAsyncExc(id, NULL) leaves the eval breaker
    set; the next Python call under a trace function (FontLab's run_python
    wrapper sets one) spins forever (hangs of 2026-10-16)."""
    common = load("realuse_common")
    run_realuse = load("run_realuse")
    sources = [common.GUARD, common.COMMON, common.WAIT, common.TEARDOWN]
    sources += [v for v in vars(run_realuse).values() if isinstance(v, str)]
    for source in sources:
        assert "c_void_p" not in source, source[:200]  # the NULL-taking clear


CPYTHON_311_HANG = """
import ctypes, sys, threading
f = ctypes.pythonapi.PyThreadState_SetAsyncExc
f.argtypes, f.restype = [ctypes.c_ulong, ctypes.c_void_p], ctypes.c_int
f(threading.get_ident(), None)  # "clear": no exception pending
sys.settrace(lambda *a: None)
(lambda: None)()  # 3.11: spins here forever
print("returned")
"""


def test_root_cause_reproducer_null_async_exc_then_traced_call_spins():
    """The host-free reproducer of the FontLab hangs, recorded as a test: it
    documents the interpreter defect the harness must avoid."""
    import subprocess

    try:
        done = subprocess.run(
            [sys.executable, "-c", CPYTHON_311_HANG],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        assert sys.version_info[:2] == (3, 11), "only CPython 3.11 is known to spin"
        return
    assert done.stdout.strip() == "returned"
    assert sys.version_info[:2] != (3, 11), "CPython 3.11 was expected to spin"


def test_main_when_target_path_is_absolute_then_rc2_before_fontlab(tmp_path):
    """A receipt needs 'repository/relative' paths; an absolute probe path
    failed only after the run and fenced the host (2026-10-16 07:14)."""
    run_realuse = load("run_realuse")
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps(
            {"targets": [{"id": "p", "kind": "script", "path": "/abs/probe.py"}]}
        )
    )
    assert (
        run_realuse.main(["--manifest", str(manifest), "--out", str(tmp_path), "p"])
        == 2
    )


def test_owned_copies_are_closed_without_saving():
    """Cross-font targets (Deliver-style) leave a second owned copy: both closes
    pass save=False, so no agent autosave blocks the next launch (2026-10-16)."""
    import inspect

    common = load("realuse_common")
    source = inspect.getsource(common.Run)
    closes = [line for line in source.splitlines() if "close_font" in line]
    assert len(closes) == 2 and all("save=False" in line for line in closes), closes


KERNING_RULE = {
    "output_error": "TypeError: '>' not supported between instances of 'NoneType' and 'int'",
    "frame": 'kerning pairs unlocker.py", line 183, in unlockKerning',
    "reason": "Glyphs-incompatible",
}
KERNING_TRACE = (
    '  File "/c/kerning pairs unlocker.py", line 183, in unlockKerning\n'
    "TypeError: '>' not supported between instances of 'NoneType' and 'int'\n"
)


def test_ruled_classification_when_output_error_matches_then_reason():
    rule = load("run_realuse").ruled_classification
    assert rule(KERNING_RULE, {}, {}, [KERNING_TRACE]) == "Glyphs-incompatible"


def test_ruled_classification_when_output_error_differs_then_none():
    rule = load("run_realuse").ruled_classification
    other_frame = KERNING_TRACE.replace("line 183", "line 99")
    assert rule(KERNING_RULE, {}, {}, [other_frame]) is None, "frame must match"
    assert rule(KERNING_RULE, {}, {}, []) is None, "no traceback, no classification"


def test_ruled_classification_when_no_rule_or_other_kinds_then_unchanged():
    rule = load("run_realuse").ruled_classification
    assert rule(None, {"error": "TypeError"}, {}, []) is None
    raised = {"error": "TypeError", "frames": ["x.py:17"]}
    by_error = {"error": "TypeError", "frame": "x.py:17", "reason": "r"}
    assert rule(by_error, raised, {}, []) == "r"
    assert (
        rule(
            {"dialog": "not found", "reason": "d"}, {}, {"dialogs": ["X not found"]}, []
        )
        == "d"
    )
    assert (
        rule({"fixture_unavailable": True, "reason": "f"}, {"error": "E"}, {}, [])
        is None
    )


def test_manifest_when_kerning_unlocker_then_carries_the_output_error_rule():
    manifest = json.loads(
        (DRIVERS.parents[1] / "realuse/manifest-portable.json").read_text()
    )
    rows = manifest["targets"]
    row = next(r for r in rows if r["id"] == "s-kerning-pairs-unlocker")
    assert row["classify_if"]["output_error"].startswith("TypeError"), row.get(
        "classify_if"
    )
