# this_file: tests/test_lazy_import.py
"""The package must import in hosts that lack optional adaptation dependencies."""

import subprocess
import sys


def test_package_import_when_fissix_missing_then_succeeds_and_adaptation_is_lazy():
    code = (
        "import sys; sys.modules['fissix'] = None\n"
        "import fontlab_glyport, fontlab_glyport.model\n"
        "assert 'fontlab_glyport.adaptation' not in sys.modules\n"
        "try:\n    fontlab_glyport.adapt_source\nexcept ImportError:\n    print('lazy-ok')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    assert "lazy-ok" in out.stdout
