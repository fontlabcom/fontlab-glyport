# this_file: Scripts/Reports/Script Inspection Demo.py
# SPDX-License-Identifier: Apache-2.0
"""Script Inspection Demo.

What: Inspect this demo source without executing it or claiming native compatibility.
Use: Run from FontLab's Scripts menu to open a read-only snapshot report.
Safety: Reads only this script source; no font, history, selection, preferences,
Output or clipboard is changed. No open font is required.
"""


def build_report() -> dict:
    """Return real package results without importing a native host or opening UI."""
    from pathlib import Path

    from fly.gp import inspect_source

    assessment = inspect_source(Path(__file__))
    return {
        "profile": assessment.profile,
        "runtime_status": assessment.runtime_status,
        "required_capabilities": list(assessment.required_capabilities),
        "dependencies": [item.module for item in assessment.dependencies],
        "files": [
            {"name": item.path, "sha256": item.sha256, "bytes": item.bytes}
            for item in assessment.files
        ],
    }


def main() -> None:
    """Show the results using Fly and App's existing nonmodal report window."""
    from fly.ap.proof.reports.model import show_report

    show_report(
        build_report(),
        title="Script Inspection Demo",
        key="fontlab-glyport-script-inspection-demo",
    )


if __name__ == "__main__":
    main()
