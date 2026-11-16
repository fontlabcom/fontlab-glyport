---
this_file: Scripts/README.md
---
# Package demos

- [Detached Path Demo](Contours/Detached%20Path%20Demo.py)
- [Script Inspection Demo](Reports/Script%20Inspection%20Demo.py)
- [Affine Values Demo](Utilities/Affine%20Values%20Demo.py)

Run a demo from FontLab's Scripts menu. Each opens an App read-only, nonmodal snapshot report; no open font is needed. Install this package and its declared dependencies, plus `fontlab-fly>=1.3.0` and `fontlab-fontlabapp` providing `proof.reports.model.show_report` for the menu UI. Copy the functional subfolders from this `Scripts` directory into FontLab’s Scripts folder (or use `install.vfpy` where provided); the demos are also included in the source distribution.

The data belongs to the demo and is detached from open documents. Script Inspection reads its own Python source without executing it; it reports requirements, not proven native compatibility. No script edits font data, history, selection, preferences, Output or clipboard. API and UI errors propagate rather than reporting false success.

Outside FontLab, load a script with `runpy.run_path(path)` and call the returned `build_report` function to obtain its JSON-ready results through Fly without importing Qt or native FontLab modules. Calling `main` requires the FontLab report UI.
