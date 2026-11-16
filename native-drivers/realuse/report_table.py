#!/usr/bin/env python3
# this_file: native-drivers/realuse/report_table.py
"""Markdown status table of the latest attempt per target in one or more round
directories (later directories win), for the G1 report.

    python native-drivers/realuse/report_table.py MANIFEST ROUND_DIR [ROUND_DIR...]
"""

import json
import sys
from pathlib import Path


def latest(dirs: list[Path]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for directory in dirs:
        for path in sorted(directory.glob("*.json")):
            record = json.loads(path.read_text())
            found[record["id"]] = {**record, "_file": f"{directory.name}/{path.name}"}
    return found


def reason(record: dict) -> str:
    if record["status"] == "classified":
        return record["classification"]
    missed = [c for c in record["clauses"] if not c["asserted"]]
    return missed[0]["clause"] + ": " + missed[0]["detail"][:120] if missed else ""


def main(argv: list[str]) -> int:
    manifest = json.loads(Path(argv[0]).read_text())
    records = latest([Path(a) for a in argv[1:]])
    rows = [
        "| Target | Kind | Status | Oracle | Evidence | First unmet clause / classification |",
        "|---|---|---|---|---|---|",
    ]
    counts: dict[str, int] = {}
    for target in manifest["targets"]:
        record = records.get(target["id"])
        status = record["status"] if record else "not run"
        counts[status] = counts.get(status, 0) + 1
        detail = reason(record).replace("|", "/").replace("\n", " ") if record else ""
        kind = target["protocol"] or "script"
        oracle = (record or {}).get("oracle", {}).get("verdict", "")
        rows.append(
            f"| {target['id']} | {kind} | {status} | {oracle} | {record['_file'] if record else ''} | {detail[:160]} |"
        )
    print(f"Counts: {counts}\n")
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
