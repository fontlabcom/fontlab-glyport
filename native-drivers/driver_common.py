# this_file: native-drivers/driver_common.py
"""Host-side Remopy driver support. No corpus files are opened or executed."""

import argparse
import json
import uuid
from pathlib import Path

from fontlab_remopy import FontLab


class Driver:
    def __init__(self, description):
        parser = argparse.ArgumentParser(description=description)
        parser.add_argument("--repo", type=Path, required=True)
        parser.add_argument("--output", type=Path)
        parser.add_argument("--manifest", type=Path)
        self.args = parser.parse_args()
        self.key = "_glyport_native_driver_" + uuid.uuid4().hex
        self.records = []
        self.fl = None

    def __enter__(self):
        self.fl = FontLab()
        self.fl.__enter__()
        try:
            self.fl.run(
                """
import sys, types, tempfile
from pathlib import Path
if any(name == "fontlab_glyport" or name.startswith("fontlab_glyport.") or name == "fly.gp" or name.startswith("fly.gp.") for name in sys.modules) or "gp" in vars(sys.modules.get("fly", types.ModuleType("fly"))):
    raise RuntimeError("Release existing Fly/Glyport sessions before native driver source selection")
state = types.ModuleType(driver_key)
state.paths = list(sys.path)
sys.path.insert(0, str(Path(repo) / "src"))
# Issue-104 sys.path guard: other agents' glyport copies must not be imported.
from fly import gp as _gp
assert _gp.__file__.startswith(str(Path(repo) / "src")), "imported " + _gp.__file__
state.temporary = tempfile.TemporaryDirectory(prefix="glyport-native-")
state.root = Path(state.temporary.name)
state.handles = []
state.contexts = []
sys.modules[driver_key] = state
result = {"python": sys.version, "fixture": str(state.root)}
""",
                repo=str(self.args.repo.resolve()),
                driver_key=self.key,
            )
        except BaseException:
            self.fl.close()
            raise
        return self

    def call(self, name, code, **variables):
        prelude = "import sys, time\nstate = sys.modules[driver_key]\n_native_start = time.monotonic()\n"
        suffix = "\nresult = {'checks': result, 'native_seconds': time.monotonic() - _native_start}\n"
        completed = self.fl.run(
            prelude + code + suffix, driver_key=self.key, **variables
        )
        record = {
            "name": name,
            **completed.value,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        assert record["native_seconds"] < 2.0, record
        self.records.append(record)
        return record["checks"]

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.fl:
                self.fl.run(
                    """
import sys
state = sys.modules[driver_key]
failures = []
for owned in reversed(state.handles + state.contexts):
    try:
        owned.close()
    except BaseException as error:
        failures.append(type(error).__name__ + ": " + str(error))
state.temporary.cleanup()
sys.path[:] = state.paths
sys.modules.pop(driver_key, None)
if failures:
    raise RuntimeError("; ".join(failures))
result = {"cleanup": "passed"}
""",
                    driver_key=self.key,
                )
        finally:
            if self.fl:
                self.fl.__exit__(exc_type, exc, tb)
        report = {
            "status": "failed" if exc else "passed",
            "checks": self.records,
            "scope": "owned synthetic fixtures; not corpus acceptance",
        }
        text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if self.args.output:
            with self.args.output.open("x", encoding="utf-8") as stream:
                stream.write(text)
        print(text, end="")
        return False
