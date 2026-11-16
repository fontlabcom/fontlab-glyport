# this_file: Scripts/Contours/Detached Path Demo.py
# SPDX-License-Identifier: Apache-2.0
"""Detached Path Demo.

What: Build a detached Glyphs-style path and measure its bounds and signed area.
Use: Run from FontLab's Scripts menu to open a read-only snapshot report.
Safety: Uses detached sample data only; no font, history, selection, preferences,
Output or clipboard is changed. No open font is required.
"""


def build_report() -> dict:
    """Return real package results without importing a native host or opening UI."""
    from fly.gp.model import GSLayer, GSNode, GSPath

    path = GSPath([GSNode(point) for point in [(0, 0), (200, 0), (200, 100), (0, 100)]])
    layer = GSLayer()
    layer.paths = [path]
    return {
        "bounds": path.bounds,
        "signed_area": path.area(),
        "closed": path.closed,
        "node_count": len(layer.paths[0].nodes),
    }


def main() -> None:
    """Show the results using Fly and App's existing nonmodal report window."""
    from fly.ap.proof.reports.model import show_report

    show_report(
        build_report(),
        title="Detached Path Demo",
        key="fontlab-glyport-detached-path-demo",
    )


if __name__ == "__main__":
    main()
