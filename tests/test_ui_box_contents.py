# this_file: tests/test_ui_box_contents.py
"""Compare complete reviewed prior functions to actual current entry points."""

from types import SimpleNamespace

import pytest

from fontlab_glyport.ui.vanilla_controls import Box, _group_box_class

# Exact complete definitions from reviewed b40ceb7 vanilla_controls.py.
PRIOR_SOURCE = 'def _fit_content(self) -> None:\n        """Put the content widget on contentsRect and lay the children out in it."""\n        rect = self._view.contentsRect()\n        frame = (rect.x(), rect.y(), rect.width(), rect.height())\n        self._content.setGeometry(*frame)\n        self._size = frame[2:]\n        self._relayout()\ndef _group_box_class(base: type) -> type:\n    """QGroupBox subclass that refits the Box content on show and resize.\n\n    The style polish before the first show moves contentsRect below the title,\n    so a fit made earlier would overlap it (observed natively in FontLab 9).\n    """\n\n    class GroupBox(base):\n        _owner = None\n\n        def showEvent(self, event):\n            base.showEvent(self, event)\n            if self._owner is not None:\n                self._owner._fit_content()\n\n        def resizeEvent(self, event):\n            base.resizeEvent(self, event)\n            if self._owner is not None:\n                self._owner._fit_content()\n\n    return GroupBox'
PRIOR = {}
exec(PRIOR_SOURCE, PRIOR)  # noqa: S102 -- complete frozen first-party definitions


def fit_trace(fit, failing=None, missing=None):
    trace = []
    error = RuntimeError("owned failure")
    frame = (1, 21, -2, 0)

    def step(name, value=None):
        trace.append(name)
        if name == failing:
            raise error
        return value

    rect = SimpleNamespace(
        **{
            name: lambda name=name, value=value: step(name, value)
            for name, value in zip(("x", "y", "width", "height"), frame)
        }
    )
    owner = SimpleNamespace(
        _view=SimpleNamespace(contentsRect=lambda: step("rect", rect)),
        _content=SimpleNamespace(setGeometry=lambda *args: step(("geometry", args))),
        _size=(99, 88),
    )
    owner._relayout = lambda: step(("relayout", owner._size))
    if missing is not None:
        target = (
            owner._view
            if missing == "contentsRect"
            else owner._content
            if missing == "setGeometry"
            else rect
        )
        delattr(target, missing)
    caught = None
    try:
        fit(owner)
    except (RuntimeError, AttributeError) as exc:
        caught = exc
    return trace, owner._size, caught, error


@pytest.mark.parametrize(
    "stage",
    [
        None,
        "rect",
        "x",
        "y",
        "width",
        "height",
        ("geometry", (1, 21, -2, 0)),
        ("relayout", (-2, 0)),
    ],
)
def test_complete_old_new_fit_has_identical_order_failure_identity_and_state(stage):
    old = fit_trace(PRIOR["_fit_content"], stage)
    new = fit_trace(Box._fit_content, stage)
    assert old[:2] == new[:2]
    assert old[2] is old[3] if stage is not None else old[2] is None
    assert new[2] is new[3] if stage is not None else new[2] is None
    if stage is None:
        assert new[:2] == (
            [
                "rect",
                "x",
                "y",
                "width",
                "height",
                ("geometry", (1, 21, -2, 0)),
                ("relayout", (-2, 0)),
            ],
            (-2, 0),
        )


@pytest.mark.parametrize(
    "missing", ["contentsRect", "x", "y", "width", "height", "setGeometry"]
)
def test_complete_old_new_missing_accessors_have_identical_trace_and_error(missing):
    old = fit_trace(PRIOR["_fit_content"], missing=missing)
    new = fit_trace(Box._fit_content, missing=missing)
    assert old[:2] == new[:2]
    assert type(old[2]) is type(new[2]) is AttributeError
    assert str(old[2]) == str(new[2])


@pytest.mark.parametrize("event", ["showEvent", "resizeEvent"])
@pytest.mark.parametrize(
    "mode", ["absent", "present", "replace", "remove", "base-error", "callback-error"]
)
def test_complete_old_new_events_use_live_owner_after_base_and_same_errors(event, mode):
    results = []
    for factory in [PRIOR["_group_box_class"], _group_box_class]:
        trace = []
        error = RuntimeError("owned event failure")
        token = object()  # has no size accessor

        def fit(trace=trace, error=error):
            trace.append("fit")
            if mode == "callback-error":
                raise error

        def native(widget, incoming, token=token, trace=trace, error=error):
            assert incoming is token
            trace.append("base")
            if mode == "replace":
                widget._owner = SimpleNamespace(
                    _fit_content=lambda trace=trace: trace.append("replacement")
                )
            if mode == "remove":
                widget._owner = None
            if mode == "base-error":
                raise error

        widget = factory(type("Base", (), {event: native}))()
        widget._owner = None if mode == "absent" else SimpleNamespace(_fit_content=fit)
        caught = None
        try:
            getattr(widget, event)(token)
        except RuntimeError as exc:
            caught = exc
        assert caught is error if mode.endswith("error") else caught is None
        results.append(trace)
    assert results[0] == results[1]
    assert results[1] == ["base"] + (
        []
        if mode in {"absent", "remove", "base-error"}
        else ["replacement" if mode == "replace" else "fit"]
    )


def test_fit_entry_point_keeps_signature_and_uses_shared_callable(monkeypatch):
    import inspect

    from fontlabapp.qt.layouts.content import fit_contents

    from fontlab_glyport.ui import vanilla_controls

    assert str(inspect.signature(Box._fit_content)) == "(self) -> None"
    assert vanilla_controls.fit_contents is fit_contents
    view, content = object(), object()
    size = (object(), object())
    trace = []

    def shared(container, child):
        assert container is view and child is content
        trace.append("geometry")
        return size

    monkeypatch.setattr(vanilla_controls, "fit_contents", shared)
    owner = SimpleNamespace(
        _view=view, _content=content, _relayout=lambda: trace.append(owner._size)
    )
    Box._fit_content(owner)
    assert owner._size is size and trace == ["geometry", size]
