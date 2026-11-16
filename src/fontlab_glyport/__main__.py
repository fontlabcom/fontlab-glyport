# this_file: src/fontlab_glyport/__main__.py
"""Enable ``python -m fontlab_glyport`` without native host imports."""

from .cli import main

raise SystemExit(main())
