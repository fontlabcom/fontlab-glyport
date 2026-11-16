# this_file: tests/test_realuse_oracles.py
"""Result oracles (realuse/oracles/): each must accept the expected result and
reject an unchanged font and its counterexamples, on the real GetGo fixture."""

import copy
import json
from pathlib import Path

import pytest
from test_realuse_harness import load

REPO = Path(__file__).resolve().parents[1]
MANIFEST = json.loads(
    (REPO / "realuse/manifest-portable.json").read_text(encoding="utf-8")
)
TARGETS = {t["id"]: t for t in MANIFEST["targets"]}
ORACLES = sorted(p.stem for p in (REPO / "realuse/oracles").glob("*.py"))
_FIXTURES: dict = {}


def fixture(target):
    common = load("realuse_common")
    name = target.get("fixture", "plum-var")
    if name not in _FIXTURES:
        path = common.fixture_path(name)
        _FIXTURES[name] = json.loads(path.read_text(encoding="utf-8"))
    return _FIXTURES[name]


def oracle_for(target_id):
    R = load("realuse_oracle")
    load("reporter_oracle")  # shared by the reporter oracles
    target = TARGETS[target_id]
    module = R.load(target_id)
    context = {"current": [["A", "Regular"]], "tab": target.get("tab", "A")}
    if target.get("prepare"):
        context["prepared"] = "prepared"  # the harness setup ran
    context.update(getattr(module, "CONTEXT", {}))
    return R, module, R.fresh(target, fixture(target), **copy.deepcopy(context))


def verdict(R, o):
    o.clauses.clear()
    return all(c["asserted"] for c in R.evaluate(o)), o.clauses


def test_parse_contour_when_closing_curve_then_both_points_off_curve():
    R = load("realuse_oracle")
    circle = ["69 5 s", "69 -9  80 -20  94 -20 s", "108 -20  119 -9  119 5 s"]
    circle += ["119 19  108 30  94 30 s", "80 30  69 19 c"]
    pts = R.parse_contour(circle)
    assert [(p.x, p.y) for p in pts if p.on] == [(69, 5), (94, -20), (119, 5), (94, 30)]
    assert len(pts) == 12 and pts[0].smooth


def test_parse_contour_when_truetype_off_curve_flag_then_off_curve():
    R = load("realuse_oracle")
    pts = R.parse_contour(["280 0", "2600 0 s", "2710 0 o", "2873 39 o", "2950 120"])
    assert [p.on for p in pts] == [True, True, False, False, True]


def test_set_contours_when_round_tripped_then_same_points():
    R = load("realuse_oracle")
    circle = ["69 5 s", "69 -9  80 -20  94 -20 s", "80 30  69 19 c"]
    layer = {"elements": [{"elementData": {"contours": [{"nodes": circle}]}}]}
    pts = R.contours(layer)
    R.set_contours(layer, pts)
    assert R.contours(layer) == pts


def test_evaluate_when_no_oracle_file_then_fails_closed():
    R = load("realuse_oracle")
    o = R.Oracle({"id": "no-such-target"}, {"font": {}}, {"font": {}})
    clauses = R.evaluate(o)
    assert clauses and not any(c["asserted"] for c in clauses)


def test_every_oracle_file_names_a_manifest_target():
    assert set(ORACLES) <= set(TARGETS), set(ORACLES) - set(TARGETS)


@pytest.mark.parametrize("target_id", ORACLES)
def test_oracle_when_expected_result_then_holds(target_id):
    R, module, o = oracle_for(target_id)
    module.example(o)
    ok, clauses = verdict(R, o)
    assert ok, [c for c in clauses if not c["asserted"]]


@pytest.mark.parametrize("target_id", ORACLES)
def test_oracle_when_counterexample_then_rejected(target_id):
    R, module, _ = oracle_for(target_id)
    wrong = list(getattr(module, "COUNTEREXAMPLES", []))
    assert wrong, "every oracle needs at least one counterexample"
    for make in wrong:
        _, _, o = oracle_for(target_id)
        make(o)
        ok, clauses = verdict(R, o)
        assert not ok, f"{make.__name__} passed: {clauses}"


def test_evaluate_when_prepare_failed_then_its_own_failing_clause():
    R, module, o = oracle_for("s-papyrify")
    module.example(o)
    o.prepared = {"prepare_error": "AttributeError: removeMaster"}
    ok, clauses = verdict(R, o)
    assert not ok and clauses[0]["clause"].startswith("oracle: harness prepare")


def test_restore_when_context_saved_then_same_verdict(tmp_path):
    R, module, o = oracle_for("s-node-nudger")
    module.example(o)
    (tmp_path / "before.vfj").write_text(json.dumps(o.before))
    (tmp_path / "after.vfj").write_text(json.dumps(o.after))
    R.save_context(o, tmp_path / "oracle-context.json")
    again = R.restore(tmp_path)
    assert verdict(R, again)[0] and verdict(R, o)[0]


def test_oracle_verdict_when_clauses_then_held_failed_or_missing():
    common = load("realuse_common")
    held = [{"clause": "oracle: x", "asserted": True}]
    failed = held + [{"clause": "oracle: y", "asserted": False}]
    missing = [{"clause": "oracle: result oracle defined", "asserted": False}]
    assert common.oracle_verdict(held)["verdict"] == "held"
    assert common.oracle_verdict(failed) == {"verdict": "failed", "failed": ["y"]}
    assert common.oracle_verdict(missing)["verdict"] == "missing"
    assert common.oracle_verdict([])["verdict"] == "missing"


def test_gposreport_when_stopped_like_glyphs_then_ruled_outcome_holds():
    R, module, o = oracle_for("s-gposreport")
    module.stopped_like_glyphs(o)
    ok, clauses = verdict(R, o)
    assert ok, [c for c in clauses if not c["asserted"]]


def test_extrudetool_when_refused_precisely_on_9783_then_oracle_holds():
    R, _, o = oracle_for("p-extrudetool")
    o.extra = {
        "install": {
            "state": "active",
            "registration": [
                "SelectTool ExtrudeTool loaded: 0 host registrations",
                "tool: Unsupported capability: FontLab.register_tool (no Python tool API)",
            ],
        }
    }
    ok, clauses = verdict(R, o)
    assert ok, [c for c in clauses if not c["asserted"]]


def test_host_unlock_8512_tolerates_exactly_the_unlock_and_attaching_anchor():
    R = load("realuse_oracle")
    before = {
        "name": "Regular",
        "anchors": [
            {"name": "acute", "point": "216 478"},
            {"name": "top", "point": "236 478"},
        ],
        "elements": [
            {"component": {"glyphName": "a"}, "locked": True},
            {
                "component": {"glyphName": "acute"},
                "locked": True,
                "transform": {"xOffset": 26},
            },
        ],
    }
    after = {
        "name": "Regular",
        "anchors": [{"name": "top", "point": "236 478"}],
        "elements": [
            {"component": {"glyphName": "a"}},
            {"component": {"glyphName": "acute"}, "transform": {"xOffset": 26}},
        ],
    }
    assert R.host_unlock_8512(before, after)
    moved = json.loads(json.dumps(after))
    moved["elements"][1]["transform"]["xOffset"] = (
        40  # an offset change is not tolerated
    )
    assert not R.host_unlock_8512(before, moved)
    lost = json.loads(json.dumps(after))
    lost["anchors"] = []  # losing a non-attaching anchor is not tolerated
    assert not R.host_unlock_8512(before, lost)


def _italic_composite(locked=True, base_offset=None, mark_offset=-139):
    base = {"component": {"glyphName": "dotlessi"}}
    mark = {"component": {"glyphName": "acute"}, "transform": {"xOffset": mark_offset}}
    if base_offset is not None:
        base["transform"] = {"xOffset": base_offset}
    if locked:
        base["locked"] = mark["locked"] = True
    return {"name": "Italic", "elements": [base, mark]}


def _unlocked(layer):
    return {
        **layer,
        "elements": [
            {k: v for k, v in e.items() if k != "locked"} for e in layer["elements"]
        ],
    }


def test_host_unlock_8512_when_italic_master_then_mark_xoffset_change_tolerated():
    R = load("realuse_oracle")
    before = _italic_composite()
    after = _unlocked(_italic_composite(mark_offset=-12))
    assert R.host_unlock_8512(before, after, italic=True), (
        "italic re-offset of the attached mark"
    )


def test_host_unlock_8512_when_upright_master_then_mark_xoffset_change_fails():
    R = load("realuse_oracle")
    before = _italic_composite()
    after = _unlocked(_italic_composite(mark_offset=-12))
    assert not R.host_unlock_8512(before, after), (
        "upright masters keep mark offsets (fl#8512)"
    )
    assert not R.host_unlock_8512(before, after, italic=False)


def test_host_unlock_8512_when_composite_was_not_unlocked_then_offset_change_fails():
    R = load("realuse_oracle")
    before = _italic_composite(locked=False)
    after = _italic_composite(locked=False, mark_offset=-12)
    assert not R.host_unlock_8512(before, after, italic=True), "no unlock, no tolerance"


def test_host_unlock_8512_when_base_component_moves_then_fails():
    R = load("realuse_oracle")
    before = _italic_composite(base_offset=0)
    after = _unlocked(_italic_composite(base_offset=20))
    assert not R.host_unlock_8512(before, after, italic=True), (
        "only the attached mark may move"
    )


def test_host_unlock_8512_when_italic_mark_yoffset_changes_then_fails():
    R = load("realuse_oracle")
    before = _italic_composite()
    after = _unlocked(_italic_composite(mark_offset=-12))
    after["elements"][1]["transform"]["yOffset"] = 30
    assert not R.host_unlock_8512(before, after, italic=True), (
        "yOffset change was never measured"
    )


def test_host_unlock_8512_when_italic_and_other_layer_data_changes_then_fails():
    R = load("realuse_oracle")
    before = _italic_composite()
    after = _unlocked(_italic_composite(mark_offset=-12))
    after["advanceWidth"] = 999
    assert not R.host_unlock_8512(before, after, italic=True), (
        "everything else must match"
    )


def test_italic_masters_when_angle_set_in_either_file_then_named():
    R = load("realuse_oracle")
    upright = {"font": {"masters": [{"fontMaster": {"name": "Regular"}}]}}
    slanted = {
        "font": {"masters": [{"fontMaster": {"name": "Regular", "italic_angle": -12}}]}
    }
    assert R.italic_masters(upright) == frozenset()
    assert R.italic_masters(upright, slanted) == {"Regular"}


def test_same_layer_when_only_layer_active_flag_differs_then_same():
    R = load("realuse_oracle")
    layer = {"name": "Regular", "advanceWidth": 596}
    assert R.same_layer({**layer, "active": True}, layer), (
        "layer 'active' is UI state (ruling)"
    )


def test_same_layer_when_element_active_or_data_differs_then_not_same():
    R = load("realuse_oracle")
    before = {"name": "Regular", "active": True, "elements": [{"active": True, "a": 1}]}
    after = {"name": "Regular", "elements": [{"a": 1}]}
    assert not R.same_layer(before, after), (
        "only the layer-level flag is ruled UI state"
    )
    assert not R.same_layer(
        {"name": "R", "active": True, "advanceWidth": 1},
        {"name": "R", "advanceWidth": 2},
    )


def test_same_layer_when_8512_unlock_with_active_dropped_then_tolerated():
    R = load("realuse_oracle")
    before = {
        "name": "Light",
        "active": True,
        "anchors": [
            {"name": "acute", "point": "257 688"},
            {"name": "top", "point": "277 688"},
        ],
        "elements": [
            {"component": {"glyphName": "A"}, "locked": True},
            {
                "component": {"glyphName": "acute"},
                "locked": True,
                "transform": {"xOffset": 67},
            },
        ],
    }
    after = {
        "name": "Light",
        "anchors": [{"name": "top", "point": "277 688"}],
        "elements": [
            {"component": {"glyphName": "A"}},
            {"component": {"glyphName": "acute"}, "transform": {"xOffset": 67}},
        ],
    }
    assert R.same_layer(before, after), "fl#8512 unlock plus the UI-state flag"


def test_kerning_unlocker_when_ruled_error_and_nothing_written_then_holds():
    R, module, o = oracle_for("s-kerning-pairs-unlocker")
    o.output = ["Traceback ...\n" + module.RULED_ERROR]
    ok, clauses = verdict(R, o)
    assert ok, [c for c in clauses if not c["asserted"]]
