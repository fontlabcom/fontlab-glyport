# this_file: tests/test_migrate_app_paths.py
"""Migration boundaries and repeatability, independent of native FontLab."""

import importlib.util
import sys
from pathlib import Path

import pytest


def test_rewrite_when_paths_overlap_then_preserve_boundaries_and_bindings():
    path = Path(__file__).resolve().parents[1] / "tools/migrate_app_paths.py"
    spec = importlib.util.spec_from_file_location("migrate_app_paths", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    mapping = migration.load_mapping()
    source = '''from fly.ap import scripting as api
from fontlabapp import masters, draft_signals
from fontlabapp.masters.inspect import model
import fly.ap.glyph_catalog as catalog
monkeypatch.setattr("fontlabapp.scripting.capture", callback)
mock.patch('fly.ap.scripting.capture')
importlib.import_module("fontlab_remopy.control")
fly.fp.feature_blocks.read_feature_blocks(font)
fontlab_fontport.ui.fontinfo
fontlabapp.scripting_extra other.fontlabapp.scripting fly.ap.scripting_extra
fontlabapp.masters.inspect.model.capture
{"api_module": "glyph_tree", "unrelated": "glyph_tree"}
assert row["api_module"] == "glyph_tree"
'''
    expected = '''import fly.ap.core.scripting as api
import fontlabapp.masters.inspect.model as masters
import fontlabapp.core.signals.scope as draft_signals
from fontlabapp.masters.inspect import model
import fly.ap.glyphs.catalog.model as catalog
monkeypatch.setattr("fontlabapp.core.scripting.capture", callback)
mock.patch('fly.ap.core.scripting.capture')
importlib.import_module("fontlab_remopy.client")
fly.ap.fontui.feature_blocks.read_feature_blocks(font)
fontlabapp.fontui.fontinfo
fontlabapp.scripting_extra other.fontlabapp.scripting fly.ap.scripting_extra
fontlabapp.masters.inspect.model.capture
{"api_module": "glyphs.tree.model", "unrelated": "glyph_tree"}
assert row["api_module"] == "glyphs.tree.model"
'''
    rewritten = migration.rewrite(source, mapping)
    assert rewritten == expected, "Change only complete module paths; retain imported local names"
    assert migration.rewrite(rewritten, mapping) == rewritten, "Canonical paths must be stable"


def test_migrate_when_archive_present_then_leave_it_untouched(tmp_path):
    path = Path(__file__).resolve().parents[1] / "tools/migrate_app_paths.py"
    spec = importlib.util.spec_from_file_location("migrate_app_paths", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    for name in ("src/current.py", "src/_reference/archived.py"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("import fly.ap.scripting\n")
    assert migration.migrate(tmp_path, migration.load_mapping()) == ["src/current.py"]
    assert (tmp_path / "src/_reference/archived.py").read_text() == "import fly.ap.scripting\n"



def _load_migration():
    path = Path(__file__).resolve().parents[1] / "tools/migrate_app_paths.py"
    spec = importlib.util.spec_from_file_location("migrate_app_paths", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _fake_app(root, aliases):
    legacy = root / "src/fontlabapp/_legacy.py"
    legacy.parent.mkdir(parents=True)
    (legacy.parent / "__init__.py").write_text("raise ImportError('package must not run')\n")
    legacy.write_text(f"ALIASES = {aliases!r}\n")
    return legacy


def test_load_mapping_when_sibling_app_present_then_sibling_oracle_wins(
    tmp_path, monkeypatch
):
    migration = _load_migration()
    _fake_app(tmp_path / "fontlab-fontlabapp", {"fontlabapp.old": "fontlabapp.new"})
    monkeypatch.setattr(migration, "ROOT", tmp_path / "fontlab-glyport")
    mapping = migration.load_mapping()
    assert mapping["fontlabapp.old"] == "fontlabapp.new"
    assert mapping["fly.ap.old"] == "fly.ap.new"


def test_load_mapping_when_no_sibling_then_installed_app_oracle_without_import(
    tmp_path, monkeypatch
):
    """A lone sdist or wheel test run reads the installed App's _legacy.py."""
    migration = _load_migration()
    installed = tmp_path / "site"
    _fake_app(installed, {"fontlabapp.gone": "fontlabapp.here"})
    monkeypatch.syspath_prepend(str(installed / "src"))
    monkeypatch.delitem(sys.modules, "fontlabapp", raising=False)
    monkeypatch.setattr(migration, "ROOT", tmp_path / "lone" / "fontlab-glyport")
    mapping = migration.load_mapping()
    assert mapping["fontlabapp.gone"] == "fontlabapp.here"
    assert "fontlabapp" not in sys.modules, "Locate _legacy.py without importing App"


def test_load_mapping_when_no_app_anywhere_then_names_both_sources(
    tmp_path, monkeypatch
):
    migration = _load_migration()
    monkeypatch.setattr(migration, "ROOT", tmp_path / "fontlab-glyport")
    monkeypatch.setattr(migration.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(FileNotFoundError, match="installed fontlab-fontlabapp"):
        migration.load_mapping()
