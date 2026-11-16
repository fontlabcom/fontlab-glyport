# this_file: tests/test_issue106_round27.py
"""Python-bound guideline surface, rather than the broader C++ API."""

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_issue106_round9 import native as native_fixture

from fontlab_glyport.model.fontlab_backend import FontLabBackend


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


@pytest.mark.parametrize("role", ["center", "vector"])
def test_path_removal_with_python_bound_hint_links(native, monkeypatch, role):
    layer = native.font.glyphs[0].layers[0]
    node = native.layer.shapes[0].contours[0].nodes()[0]
    # flGuideLine inherits these links from flSnapLine. No extension property
    # is exported by pyflSnapLineImpl, even though the C++ model has one.
    hint = NS(id=900, isHint=True, center=None, vector=None)
    setattr(hint, role, node)
    native.layer.guidelines = [hint]
    monkeypatch.setattr(native.backend, "_guide_line", lambda value: value)
    layer.paths.remove(layer.paths[0])
    assert native.layer.guidelines == [], "remove hints linked through bound roles"


def test_backend_guideline_reads_are_in_python_stub():
    stub = (
        Path(__file__).resolve().parents[3]
        / "fontlab-echopy/src/fontlab_echopy/fontlab.pyi"
    )
    if not stub.exists():
        pytest.skip("Sibling fontlab-echopy checkout is required for API audit")
    tree = ast.parse(stub.read_text())
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "flGuideLine"
    )
    exposed = {
        n.target.id
        for n in cls.body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
    } | {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    backend = ast.parse(inspect.getsource(FontLabBackend))
    # Track only native wrapper locals, not GuideInfo recipe fields.
    locals_by_method = {
        "_node_hint_survivors": {"guide"},
        "_guide_line": {"guide"},
        "set_guide": {"guide"},
        "_new_guide": {"item"},
        "_read_layer_contents": {"g"},
        "master_guides": {"g"},
        "remove_guide": {"guide"},
    }
    reads = set()
    for method in backend.body[0].body:
        if (
            not isinstance(method, ast.FunctionDef)
            or method.name not in locals_by_method
        ):
            continue
        names = locals_by_method[method.name]
        for node in ast.walk(method):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in names
            ):
                reads.add(node.attr)
            # Include dynamic getattr/hasattr roles/fields: extension used to
            # hide in this tuple and evade direct attribute checks.
            if (
                isinstance(node, ast.comprehension)
                and isinstance(node.target, ast.Name)
                and node.target.id in {"role", "field"}
                and isinstance(node.iter, ast.Tuple)
            ):
                reads.update(
                    n.value for n in node.iter.elts if isinstance(n, ast.Constant)
                )
    assert reads, "Audit must find native guideline accesses"
    assert reads <= exposed, f"Unbound flGuideLine attributes: {reads - exposed}"
