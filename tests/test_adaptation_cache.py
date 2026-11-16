# this_file: tests/test_adaptation_cache.py
"""Owned fixtures for adaptation boundaries; never execute corpus code."""
# ruff: noqa: S102 -- executing owned fixtures verifies semantics.

import pytest
from test_adaptation import adapt

from fontlab_glyport import AdaptationError, adapt_source


def test_cache_hit_skips_pipeline(tmp_path, monkeypatch):
    result = adapt(tmp_path, "print 1\n")
    import fontlab_glyport.adaptation as module

    def forbidden(*args):
        pytest.fail("cache hit reran transformations")

    monkeypatch.setattr(module, "_pipeline", forbidden)
    assert adapt_source(
        result.original_path, profile="glyphs2", cache_dir=tmp_path / "cache"
    ).cache_hit


def test_publication_failure_cleans_staging(tmp_path, monkeypatch):
    import fontlab_glyport.adaptation as module

    def fail(*args):
        raise PermissionError("owned publication denied")

    monkeypatch.setattr(module.os, "rename", fail)
    with pytest.raises(AdaptationError, match="denied"):
        adapt(tmp_path, "print 1\n")
    assert not list((tmp_path / "cache" / "fontlab-glyport").glob(".staging-*"))
    assert (tmp_path / "original.py").read_bytes() == b"print 1\n"


def test_concurrent_publication(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "original.py"
    path.write_text("print 1\nvalue = 5 / 2\n")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                adapt_source, path, profile="glyphs2", cache_dir=tmp_path / "cache"
            )
            for _ in range(2)
        ]
        results = [f.result() for f in futures]
    assert results[0].path == results[1].path
    assert results[0].path.read_bytes() == results[1].path.read_bytes()
    assert not list((tmp_path / "cache" / "fontlab-glyport").glob(".staging-*"))


def test_combined_literals_and_raw_string(tmp_path):
    result = adapt(
        tmp_path, "print 0755L\nvalue = 0755L\nplain = '\\u1234'\nraw = ur'\\u1234'\n"
    )
    scope = {}
    exec(result.compile(), scope)
    assert scope["value"] == 493
    assert scope["plain"] == "\\u1234"
    assert any(d.code == "PY2_RAW_UNICODE_REVIEW" for d in result.diagnostics)
    assert (
        scope["raw"] == "\\u1234"
    )  # Python 2 raw-unicode escapes require manual review.


def test_future_print_and_except(tmp_path, capsys):
    result = adapt(
        tmp_path,
        "from __future__ import print_function\ntry:\n raise ValueError('bad')\nexcept ValueError, e:\n print(str(e))\n",
    )
    exec(result.compile(), {})
    assert capsys.readouterr().out == "bad\n"


def test_remaining_transformation_semantics(tmp_path, capsys):
    result = adapt(
        tmp_path, "print `0755L`, 1 <> 2, unicode(7), list(xrange(3)), u'café'\n"
    )
    exec(result.compile(), {})
    assert capsys.readouterr().out == "493 True 7 [0, 1, 2] café\n"


def _key_dir(tmp_path):
    (key_dir,) = (tmp_path / "cache" / "fontlab-glyport").iterdir()
    return key_dir


@pytest.mark.parametrize("survivors", [(), ("source.py",)])
def test_cache_when_key_dir_is_emptied_then_it_is_rebuilt_not_a_hit(tmp_path, survivors):
    result = adapt(tmp_path, "print 1\n")
    key_dir = _key_dir(tmp_path)
    for child in list(key_dir.iterdir()):
        if child.name not in survivors:
            child.unlink()
    rebuilt = adapt_source(
        result.original_path, profile="glyphs2", cache_dir=tmp_path / "cache"
    )
    assert not rebuilt.cache_hit
    assert rebuilt.path.read_bytes() == result.path.read_bytes()
    assert (key_dir / "manifest.json").is_file()


def test_cache_when_key_dir_is_complete_then_still_a_hit(tmp_path):
    result = adapt(tmp_path, "print 1\n")
    assert adapt_source(
        result.original_path, profile="glyphs2", cache_dir=tmp_path / "cache"
    ).cache_hit
    assert (_key_dir(tmp_path) / "source.py").is_file()
