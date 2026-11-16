# this_file: tests/test_info_manager_singleton_class.py
"""Fixed-class shared allocation differs from direct plain-init ownership."""

import pytest

from fontlab_glyport.glyphsapp.info_manager import GSGlyphsInfo


@pytest.mark.parametrize("entry", ["shared", "constructor", "allocated_init", "new"])
def test_singleton_when_subclass_has_own_storage_then_process_global_is_used(
    monkeypatch, entry
):
    monkeypatch.setattr(GSGlyphsInfo, "_shared", None)
    marker = object()

    class Child(GSGlyphsInfo):
        _shared = marker

    receiver = Child.alloc()
    actual = {
        "shared": Child.sharedManager,
        "constructor": Child,
        "allocated_init": receiver.init,
        "new": Child.new,
    }[entry]()
    expected = GSGlyphsInfo.sharedManager()
    assert actual is expected, "All entrypoints use the same process-global pointer"
    assert type(actual) is (GSGlyphsInfo if entry == "shared" else Child), (
        "Shared allocation is fixed, but direct init retains its allocated receiver"
    )
    if entry == "allocated_init":
        assert actual is receiver, "The first NSObject init returns that same receiver"
    assert Child._shared is marker, "Do not write a subtype singleton slot"
    assert expected._fixed_index is None and expected._public_indexes == {}


@pytest.mark.parametrize("entry", ["constructor", "allocated_init", "new"])
def test_plain_init_when_subtype_overrides_shared_selector_then_does_not_dispatch_it(
    monkeypatch, entry
):
    monkeypatch.setattr(GSGlyphsInfo, "_shared", None)

    class Child(GSGlyphsInfo):
        @classmethod
        def sharedManager(cls):
            raise AssertionError(
                "Plain init does not send a subtype sharedManager selector"
            )

    actual = {
        "constructor": Child,
        "allocated_init": lambda: Child.alloc().init(),
        "new": Child.new,
    }[entry]()
    assert actual is GSGlyphsInfo.sharedManager()
    assert type(actual) is Child


def test_new_when_init_overridden_then_preserves_allocated_receiver_dispatch(
    monkeypatch,
):
    monkeypatch.setattr(GSGlyphsInfo, "_shared", None)
    calls = []
    result = object()

    class Child(GSGlyphsInfo):
        def init(self):
            calls.append(self)
            return result

    assert Child.new() is result
    assert len(calls) == 1 and type(calls[0]) is Child
    assert "_fixed_index" not in vars(calls[0]), "alloc does not initialize the graph"
    assert GSGlyphsInfo._shared is None, (
        "Overridden init never enters the base once path"
    )


def test_shared_manager_when_first_allocation_inflight_then_once_identity_is_preserved(
    monkeypatch,
):
    import threading
    from types import SimpleNamespace

    from fontlab_glyport.glyphsapp import info_manager, info_shared

    monkeypatch.setattr(GSGlyphsInfo, "_shared", None)
    entered, release, progress = threading.Event(), threading.Event(), threading.Event()
    original_new = object.__new__
    allocations, results, errors = [], [], []

    class ObservedLock:
        def __init__(self):
            self.lock = threading.Lock()

        def __enter__(self):
            if entered.is_set():
                progress.set()
            self.lock.acquire()

        def __exit__(self, *exc):
            self.lock.release()

    def allocate(cls):
        allocations.append(cls)
        if len(allocations) == 1:
            entered.set()
            assert release.wait(3), "The owned first allocator must be released"
        else:
            progress.set()
        return original_new(cls)

    def request():
        try:
            results.append(GSGlyphsInfo.sharedManager())
        except BaseException as error:  # noqa: BLE001 - collect every worker-thread failure for assertion in the parent thread
            errors.append(error)

    monkeypatch.setattr(
        info_manager, "object", SimpleNamespace(__new__=allocate), raising=False
    )
    monkeypatch.setattr(info_shared, "_shared_monitor", ObservedLock())
    first, second = threading.Thread(target=request), threading.Thread(target=request)
    first.start()
    try:
        assert entered.wait(3), "The first initializer must have entered allocation"
        second.start()
        assert progress.wait(3), "The second request must reach the lock or allocator"
        assert allocations == [GSGlyphsInfo], (
            "A second request must not allocate before once completes"
        )
    finally:
        release.set()
        first.join(3)
        if second.ident is not None:
            second.join(3)
    assert not first.is_alive() and not second.is_alive(), (
        "No owned worker may outlive the test"
    )
    assert not errors, errors
    assert len(results) == 2 and results[0] is results[1] is GSGlyphsInfo._shared


def test_plain_init_when_base_allocated_first_then_retains_exact_receiver(monkeypatch):
    monkeypatch.setattr(GSGlyphsInfo, "_shared", None)
    receiver = GSGlyphsInfo.alloc()
    assert receiver.init() is receiver, "The once block uses its captured receiver"
    assert GSGlyphsInfo.sharedManager() is receiver


def test_plain_init_when_global_exists_then_does_not_initialize_other_receiver(
    monkeypatch,
):
    monkeypatch.setattr(GSGlyphsInfo, "_shared", None)
    existing = GSGlyphsInfo.sharedManager()

    class Child(GSGlyphsInfo):
        _shared = object()

    receiver = Child.alloc()
    receiver._owned = "retained"
    assert receiver.init() is existing
    assert vars(receiver) == {"_owned": "retained"}, (
        "An existing global skips the once block"
    )


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("receiver", [None, object()])
def test_unbound_init_when_receiver_is_not_a_manager_then_preserves_shared_pointer(
    monkeypatch, cached, receiver
):
    monkeypatch.setattr(GSGlyphsInfo, "_shared", None)
    previous = GSGlyphsInfo.sharedManager() if cached else None
    with pytest.raises(TypeError, match="GSGlyphsInfo"):
        GSGlyphsInfo.init(receiver)
    assert GSGlyphsInfo._shared is previous, (
        "A bad receiver must not poison process-wide state"
    )
