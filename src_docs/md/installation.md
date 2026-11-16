---
this_file: src_docs/md/installation.md
---

# Installation

User-facing examples require `fontlab-fly>=1.3.0` alongside Glyport and its declared dependencies. Fly shares the canonical provider modules; Glyport library code keeps direct imports to avoid a dependency cycle.

## Install

Host code targets Python 3.11 arm64; metadata permits Python 3.11+ externally. A terminal environment is not visible in FontLab.

Install the Glyport distribution and its matching reviewed App wheel with uv into the selected interpreter. Editable installation into FontLab is owner-managed.

Do not change FontLab's live environment without the owner's instruction; choose that interpreter explicitly. Installation includes `fissix>=24.4.24` `glyphslib>=6.16.1` and `fontlab-fontlabapp>=1.2.10`. Supply the genuine reviewed App release alongside Glyport. This does not imply registry availability or native acceptance. See DEPENDENCIES.md. GlyphData supplies named-glyph categories; imports and data loading stay lazy. A sys.path launcher does not install dependencies. Glyport never installs packages automatically. Optional extras, retained for existing installers:

| Extra | Purpose |
| --- | --- |
| `cocoa` | PyObjC Cocoa frameworks on macOS; install in the chosen host environment for the native route. |
| `geometry` | Public fontTools for exact bounds; FontLab's bundled private fontTools can also supply supported operations. |
| `boolean` | skia-pathops for detached-layer overlap removal. |
| `glyphdata` | Legacy installer name; retains the same glyphsLib minimum as the base package. |
| `native` | Host-side `verify --native` driver; requires the workspace's fontlab-remopy wheel, which is not on PyPI. |
| `test` | pytest and fontTools for source tests. |

See [DEPENDENCIES.md](https://github.com/fontlabcom/fontlab-glyport/blob/1f978bebc144754a369da0c684000479823c9276/DEPENDENCIES.md) for environment boundaries. Remopy runs externally.
