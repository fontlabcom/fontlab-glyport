# this_file: native-drivers/native_04_public_handles.py
"""Exercise real host dispatch with synthetic registration, no font mutations."""

from driver_common import Driver

with Driver("Public run/plugin handles and receipt snapshots") as driver:
    driver.call(
        "public run through default FontLab gateway",
        """
from fly.gp import run_script
from fly.gp.receipt import validate_receipt
source = state.root / "public.py"
source.write_text("# GLYPHS_VERSION: 3\\ndef callback():\\n from Foundation import NSMakeRange\\n return NSMakeRange(1,4).length\\n")
state.run = run_script(source)
state.handles.append(state.run)
assert state.run.state == "active"
assert validate_receipt(state.run.receipt.to_dict(), public=False) == []
state.callback = state.run.wrap(state.run.context.globals["callback"])
state.receipt = state.run.receipt
result = {"state": state.run.state, "host": state.run.receipt.environment.host, "receipt_valid": True}
""",
    )
    driver.call(
        "later callback and unload",
        """
assert state.callback() == 4
state.run.close()
state.run.close()
assert state.run.state == "closed"
assert state.receipt.stages[-1].name == "execution"
assert state.run.receipt.stages[-1].name == "close"
result = {"callback": 4, "idempotent_close": True, "snapshot_retained": True}
""",
    )
    driver.call(
        "plugin registrar contract and failure receipt",
        """
import plistlib
from fly.gp import install_plugin, run_script
from fly.gp.entrypoints import _native_host, PluginRegistration
from fly.gp.receipt import validate_receipt
from fly.gp.errors import UnsupportedCapability
bundle = state.root / "Fixture.glyphsPlugin"
(bundle / "Contents/Resources").mkdir(parents=True)
(bundle / "Contents/Info.plist").write_bytes(plistlib.dumps({"GlyphsVersion": "4", "PyMainFileNames": ["plugin.py"], "NSPrincipalClass": "Fixture"}))
(bundle / "Contents/Resources/plugin.py").write_text("class Fixture:\\n pass\\n")
try:
    install_plugin(bundle)
except UnsupportedCapability as error:
    assert error.handle.state == "failed"
else:
    raise AssertionError("a non-plugin principal class counted as installation")
state.unloads = []
host = _native_host()
host.plugin_installer = lambda context, assessment: PluginRegistration(lambda: state.unloads.append("unloaded"), evidence=("synthetic:registrar-hook",))
state.plugin = install_plugin(bundle, host=host)
state.handles.append(state.plugin)
assert state.plugin.state == "active"
state.plugin.unload()
state.plugin.unload()
assert state.unloads == ["unloaded"]
source = state.root / "failed.py"
source.write_text("raise ValueError('owned-fixture')\\n")
try:
    run_script(source, profile="glyphs3")
except ValueError as error:
    assert error.handle.state == "failed"
    assert validate_receipt(error.receipt.to_dict(), public=False) == []
else:
    raise AssertionError("failed script reported success")
result = {"registration_contract": "passed", "native_menus_protocols": "not covered", "failure_receipt": "valid"}
""",
    )
    driver.call(
        "default Vanilla creates an owned window",
        """
from fly.gp import run_script
source = state.root / "owned_window.py"
source.write_text("from vanilla import Window, Button\\nvalues=[]\\ndef clicked(sender):\\n from AppKit import NSMakePoint\\n values.append(NSMakePoint(4,5).x)\\nw=Window((200,100), 'Glyport owned check')\\nw.b=Button((10,10,80,20), 'Go', callback=clicked)\\nw.open()\\n")
state.vanilla = run_script(source, profile="glyphs3")
state.handles.append(state.vanilla)
assert len(state.vanilla.windows) == 1
result = {"owned_windows": 1}
""",
    )
    driver.call(
        "default Vanilla callback and window teardown",
        """
state.vanilla.context.globals["w"].b.getNSView().click()
assert state.vanilla.context.globals["values"] == [4]
state.vanilla.close()
state.vanilla.close()
assert state.vanilla.windows == []
assert state.vanilla.state == "closed"
result = {"scoped_callback": 4, "owned_windows_after_close": 0}
""",
    )
