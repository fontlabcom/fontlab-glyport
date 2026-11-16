# this_file: native-drivers/native_02_adaptation_callbacks.py
"""Run via a Python 3.11 environment with fontlab-remopy installed."""

from driver_common import Driver

with Driver("Glyphs 3/4 adaptation and retained scoped imports") as driver:
    driver.call(
        "modern source and identity maps",
        """
from fly.gp import ExecutionContext
from fly.gp.adaptation_modern import adapt_modern
source = state.root / "modern.py"
source.write_text("from AppKit import NSMakePoint\\nimport objc\\n@objc.python_method\\ndef callback():\\n from Cocoa import NSMakeRect\\n return NSMakeRect(1,2,3,4).origin.x + NSMakePoint(5,6).y\\n")
state.original = source.read_bytes()
state.contexts = []
state.callbacks = []
for profile in ("glyphs3", "glyphs4"):
    adapted = adapt_modern(source, profile=profile, cache_dir=state.root / "cache")
    assert adapted.path.read_bytes() == state.original
    assert adapted.translate(2, 1).line == 2
    assert adapt_modern(source, profile=profile, cache_dir=state.root / "cache").cache_hit
    context = ExecutionContext(state.root, profile, cache_dir=state.root / "cache")
    state.contexts.append(context)
    assert context.run(source).status == "passed"
    state.callbacks.append(context.wrap(context.globals["callback"]))
state.host_appkit = sys.modules.get("AppKit")
result = {"profiles": ["glyphs3", "glyphs4"], "source_unchanged": True}
""",
    )
    driver.call(
        "callbacks in a later Remopy call",
        """
assert [callback() for callback in state.callbacks] == [7, 7]
assert sys.modules.get("AppKit") is state.host_appkit
assert not any(name.startswith(context.namespace) for context in state.contexts for name in sys.modules)
for context in state.contexts:
    context.close()
for callback in state.callbacks:
    try:
        callback()
    except RuntimeError:
        pass
    else:
        raise AssertionError("closed callback remained usable")
result = {"callback_values": [7, 7], "closed_callbacks_rejected": True}
""",
    )
