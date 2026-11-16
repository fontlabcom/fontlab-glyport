# this_file: tests/test_shared_deferred_batch.py
"""The foreign host retains its policy around the shared scheduling mechanic."""
from types import SimpleNamespace
from typing import Any, ClassVar

from fontlabapp.core.signals.deferred import DeferredBatch
from host_doubles import make_host_qt


class _Reaper(DeferredBatch):
    """Legacy view of one shared batch per backend (``hosts`` = the queue).

    Test-only (issue 122 T15): the plugin host uses App ``OwnedMenus`` and its
    own batch. This view keeps the historical shared-batch contract checked.
    """

    _instances: ClassVar[dict[int, "_Reaper"]] = {}

    def __init__(self, qt: Any):
        super().__init__(qt, lambda host: host._reap())

    def schedule(self, host: Any) -> None:
        """Retain the original keyword name while App owns scheduling."""
        super().schedule(host)

    @property
    def hosts(self) -> list[Any]:
        """Retain the historical private queue view, including assignments."""
        return self.pending

    @hosts.setter
    def hosts(self, value: list[Any]) -> None:
        self.pending = value

    @classmethod
    def for_qt(cls, qt: Any) -> "_Reaper":
        """Return the one view per Qt namespace (keyed by ``id(qt.QtCore)``)."""
        key = id(qt.QtCore)
        if key not in cls._instances:
            cls._instances[key] = cls(qt)
        return cls._instances[key]


def test_reaper_when_backend_namespace_reused_then_one_timer_and_legacy_queue_view():
    qt = make_host_qt()
    one = _Reaper.for_qt(qt)
    assert isinstance(one, DeferredBatch)
    assert _Reaper.for_qt(SimpleNamespace(QtCore=qt.QtCore)) is one
    assert _Reaper.for_qt(make_host_qt()) is not one
    calls = []
    host = SimpleNamespace(_reap=lambda: calls.append('reaped'))
    one.schedule(host=host); one.schedule(host)
    assert one.hosts is one.pending and one.hosts == [host]
    old = one.hosts
    one.timer.fire()
    assert calls == ['reaped'] and one.hosts == [] and old == [host]
    one.hosts = [host]
    assert one.pending == [host]
    one.timer.start()  # Direct legacy assignment alone does not arm the timer.
    one.timer.fire()
    assert calls == ['reaped', 'reaped']
