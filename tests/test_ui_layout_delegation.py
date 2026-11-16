# this_file: tests/test_ui_layout_delegation.py
"""Keep Vanilla policy around the shared binding-free layout solver."""

import fontlabapp.qt.layouts.linear as shared
import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.ui import vanilla_layout as adapter


def test_solver_delegates_original_inputs_and_tolerance_without_copying(monkeypatch):
    required, hints, result, calls = [], [], [17.5], []

    def solve(*args, **kwargs):
        calls.append((args, kwargs))
        return result

    monkeypatch.setattr(shared, "solve", solve)
    assert adapter._solve(required, hints, 1) is result
    args, keywords = calls[0]
    assert args[0] is required and args[1] is hints and args[2] == 1
    assert keywords == {"epsilon": adapter._EPSILON}


def test_inconsistent_rows_keep_the_original_foreign_capability_error():
    with pytest.raises(UnsupportedCapability) as failure:
        adapter._solve([([1], 1), ([1], 2)], [], 1)
    assert failure.value.capability == "vanilla.addAutoPosSizeRules.unsatisfiable"
    assert failure.value.__suppress_context__


def test_malformed_rows_keep_value_error_instead_of_foreign_conflict():
    with pytest.raises(ValueError):
        adapter._solve([([1, 0], 1), ([0], 0)], [], 2)


def test_unknown_solver_failure_is_not_hidden_by_the_adapter(monkeypatch):
    failure = RuntimeError("injected solver failure")
    monkeypatch.setattr(
        shared, "solve", lambda *args, **kwargs: (_ for _ in ()).throw(failure)
    )
    with pytest.raises(RuntimeError) as caught:
        adapter._solve([], [], 0)
    assert caught.value is failure


def test_cold_adapter_import_and_solver_never_request_native_modules():
    import os
    import subprocess
    import sys
    from pathlib import Path

    roots = [
        str(Path(shared.__file__).parents[1]),
        str(Path(adapter.__file__).parents[2]),
    ]
    command = [
        sys.executable,
        "-c",
        (
            "import sys; import fontlab_glyport.ui.vanilla_layout as adapter; "
            "assert adapter._solve([([1,1],10)],[([1,0],6)],2)==[6,4]; "
            "assert not {'fontlab','FL','PythonQt'} & sys.modules.keys(); "
            "print('cold import and arithmetic passed')"
        ),
    ]
    result = subprocess.run(
        command,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(roots)},
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "cold import and arithmetic passed"


@pytest.mark.parametrize(
    "rule",
    [
        {"view1": "item", "attribute1": "width", "constant": float("inf")},
        {"view1": "item", "attribute1": "width", "constant": "not-a-number"},
        {"view1": "missing", "attribute1": "width"},
        {"view1": "item", "attribute1": "baseline"},
        {"view1": "item", "attribute1": "width", "relation": ">="},
        17,
        "H:garbage",
    ],
)
def test_invalid_rules_preserve_the_previous_complete_layout(rule):
    from test_issue106_round4_ui import geometry
    from ui_doubles import make_qt

    from fontlab_glyport.ui.vanilla import make_vanilla_module

    module = make_vanilla_module(make_qt(), error_sink=print)
    window = module.Window((200, 100))
    window.item = module.TextBox("auto", "Item")
    window.addAutoPosSizeRules(["H:|[item]|", "V:|[item(20)]"])
    before = geometry(window.item), list(window._auto_rules)
    try:
        with pytest.raises((UnsupportedCapability, ValueError, TypeError)):
            window.addAutoPosSizeRules([rule])
        assert (geometry(window.item), window._auto_rules) == before
    finally:
        module.Window._env.close_windows()


def test_small_container_drops_weak_sizes_without_negative_native_extents():
    from test_issue106_round4_ui import geometry
    from ui_doubles import make_qt

    from fontlab_glyport.ui.vanilla import make_vanilla_module

    module = make_vanilla_module(make_qt(), error_sink=print)
    window = module.Window((20, 40))
    window.left = module.TextBox("auto", "Left")
    window.right = module.TextBox("auto", "Right")
    try:
        window.addAutoPosSizeRules(
            ["H:|[left][right]|", "V:|[left(20)]", "V:|[right(20)]"]
        )
        left, right = geometry(window.left), geometry(window.right)
        assert left[2] >= 0 and right[2] >= 0
        assert left[2] + right[2] == 20
    finally:
        module.Window._env.close_windows()
