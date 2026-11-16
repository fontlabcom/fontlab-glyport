#!/usr/bin/env python3
# this_file: native-drivers/realuse/reevaluate.py
"""Re-run a target's result oracle on a kept run artifact, host-side.

    python native-drivers/realuse/reevaluate.py ARTIFACT.tar.gz [...]

Each native run archives its oracle inputs (realuse_common.Run.keep_artifacts);
this rebuilds the Oracle from one and prints the clauses with the current
oracle code, so an oracle fixed after a native run is checked without FontLab.
"""

import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import realuse_oracle


def reevaluate(archive: Path) -> bool:
    with tempfile.TemporaryDirectory(prefix="reevaluate-") as tmp:
        with tarfile.open(archive) as tar:
            tar.extractall(tmp, filter="data")
        oracle = realuse_oracle.restore(Path(tmp))
        clauses = realuse_oracle.evaluate(oracle)
    held = all(c["asserted"] for c in clauses)
    print(f"{archive.name}: {'held' if held else 'failed'}")
    for c in clauses:
        print(
            ("  ok   " if c["asserted"] else "  MISS ")
            + c["clause"]
            + ("" if c["asserted"] else " :: " + c["detail"][:300])
        )
    return held


def main(argv: list[str]) -> int:
    results = [reevaluate(Path(a)) for a in argv]
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
