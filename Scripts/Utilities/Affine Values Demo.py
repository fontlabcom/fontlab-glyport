# this_file: Scripts/Utilities/Affine Values Demo.py
# SPDX-License-Identifier: Apache-2.0
"""Affine Values Demo.

What: Copy and change Cocoa-compatible affine values without changing the source.
Use: Run from FontLab's Scripts menu to open a read-only snapshot report.
Safety: Uses detached sample data only; no font, history, selection, preferences,
Output or clipboard is changed. No open font is required.
"""


def build_report() -> dict:
    """Return real package results without importing a native host or opening UI."""
    from fly.gp.affine import NSAffineTransformStruct

    original = NSAffineTransformStruct(1, 0, 0, 1, 0, 0)
    translated = original.copy()
    translated[4:6] = (50, -20)
    return {
        "original": tuple(original),
        "translated": tuple(translated),
        "named_translation": [translated.tX, translated.tY],
    }


def main() -> None:
    """Show the results using Fly and App's existing nonmodal report window."""
    from fly.ap.proof.reports.model import show_report

    show_report(
        build_report(),
        title="Affine Values Demo",
        key="fontlab-glyport-affine-values-demo",
    )


if __name__ == "__main__":
    main()
