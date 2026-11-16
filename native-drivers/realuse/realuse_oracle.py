# this_file: native-drivers/realuse/realuse_oracle.py
"""Result oracles for real-use targets (issue 106, owner goal item 2).

A target passes only when its oracle holds: ``realuse/oracles/<target-id>.py``
states what must differ between the owned GetGo copy before and after the run
(or what a reporting target must show), derived from the script source and the
Glyphs 4 behaviour notes. Oracles describe behaviour in their own words and
never quote corpus code.

Oracle module contract::

    def check(o: Oracle) -> None        # o.clause(...) for every property
    def example(o: Oracle) -> None      # apply the expected result by hand (tests)
    COUNTEREXAMPLES = [fn, ...]          # wrong results; check() must reject each

Host-side only: reads the FontLab-saved VFJ copies the harness already captures.
VFJ node grammar follows vfjLib (vfjLib/Lib/vfjLib/const.py, proxy.py): a contour
is a list of segments; points in a segment are separated by two spaces; the last
point of a segment is on-curve except in a ``c`` segment (off-curves that close
back to the contour's first point); flags after ``x y``: ``s`` smooth, ``o``
TrueType off-curve, ``g2``, ``sx``/``sy``, ``{n:'name'}``.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

ORACLES = Path(__file__).resolve().parents[2] / "realuse" / "oracles"


@dataclass(frozen=True)
class Pt:
    x: float
    y: float
    on: bool = True
    smooth: bool = False


def parse_contour(nodes: list[str]) -> list[Pt]:
    points: list[Pt] = []
    for segment in nodes:
        parts = [p.split() for p in segment.split("  ") if p.strip()]
        closing = any("c" in p[2:] for p in parts)
        for index, p in enumerate(parts):
            last = index == len(parts) - 1
            on = last and not closing and "o" not in p[2:]
            points.append(Pt(float(p[0]), float(p[1]), on, "s" in p[2:]))
    return points


def layers(vfj: dict, glyph: str) -> dict[str, dict]:
    for g in vfj["font"].get("glyphs", []):
        if g["name"] == glyph:
            return {
                layer.get("name", str(i)): layer
                for i, layer in enumerate(g.get("layers", []))
            }
    return {}


def glyph_record(vfj: dict, glyph: str) -> dict | None:
    return next((g for g in vfj["font"].get("glyphs", []) if g["name"] == glyph), None)


# FontLab's own differences between two saves of an edited font (control target and
# round-3 receipts): composites get a new ``lastModified`` when a base glyph changes,
# and displayed auto layers are rebuilt (realuse_common.auto_rebuild).
GLYPH_NOISE = frozenset({"lastModified"})


def host_unlock_8512(lb: dict, la: dict, italic: bool = False) -> bool:
    """R054 fontlab/fl#8512 (FontLab 9.0.9783): after any notifyChangesApplied, the
    next save unlocks every locked component of composites on the notified master
    and drops the base's attaching anchor (named like an attached mark component).
    On a master with a non-zero italic angle (``italic``) the same save also re-lays
    out the attached marks: their xOffset changes (probes/f62-italic: -139 -> -12).
    True when ``la`` is ``lb`` with exactly that difference and nothing else."""
    elements = lb.get("elements") or []
    if not any(e.get("locked") for e in elements):
        return False
    unlocked = [{k: v for k, v in e.items() if k != "locked"} for e in elements]
    marks = {e["component"]["glyphName"] for e in elements if "component" in e}
    kept = [a for a in lb.get("anchors") or [] if a.get("name") not in marks]
    expected = dict(lb, elements=unlocked)
    if "anchors" in lb:
        expected["anchors"] = kept
        if not kept and "anchors" not in la:
            expected.pop("anchors")
    if la == lb:
        return False
    if expected == la:
        return True
    return italic and expected == _italic_marks_restored(elements, la)


def _italic_marks_restored(elements: list, la: dict) -> dict:
    """``la`` with the xOffset of each locked attached mark (a component after the
    first element) put back to its value before the save; only xOffset, and only
    where the rest of the component is unchanged."""
    after = la.get("elements") or []
    if len(after) != len(elements):
        return la
    restored = []
    for index, (e, a) in enumerate(zip(elements, after)):
        mark = index > 0 and e.get("locked") and "component" in e
        tb, ta = e.get("transform") or {}, a.get("transform") or {}
        rest_same = {k: v for k, v in tb.items() if k != "xOffset"} == {
            k: v for k, v in ta.items() if k != "xOffset"
        }
        same_part = a.get("component") == e.get("component") and set(a) - {
            "transform"
        } == set(e) - {"locked", "transform"}
        if mark and rest_same and same_part and tb != ta:
            a = dict(a)
            if tb:
                a["transform"] = tb
            else:
                a.pop("transform", None)
        restored.append(a)
    return dict(la, elements=restored)


def italic_masters(*vfjs: dict) -> frozenset[str]:
    """Names of masters with a non-zero italic angle in any of the given VFJ files."""
    return frozenset(
        m["fontMaster"].get("name")
        for vfj in vfjs
        for m in vfj.get("font", {}).get("masters", [])
        if (m.get("fontMaster") or {}).get("italic_angle")
    )


ITALIC: set[str] = set()  # master (layer) names with an italic angle; set by evaluate


HOST_8512: list[str] = []  # layers tolerated under R054 fl#8512 (reported by evaluate)


# Layer keys that record UI state, not font data. Controller ruling 2026-10-16: the
# layer-level "active" flag (which layer is current) is UI state; FontLab's get_glyph /
# set_glyph restore (glyport 1.0.1 creation preservation) drops it.
LAYER_UI_STATE = frozenset({"active"})


def without_ui_state(layer: dict | None) -> dict | None:
    if layer is None:
        return None
    return {k: v for k, v in layer.items() if k not in LAYER_UI_STATE}


def same_layer(lb: dict | None, la: dict | None) -> bool:
    if lb == la:
        return True
    if lb is None or la is None:
        return False
    lb, la = without_ui_state(lb), without_ui_state(la)
    if lb == la:
        return True
    if host_unlock_8512(lb, la, italic=lb.get("name") in ITALIC):
        HOST_8512.append(str(lb.get("name")))
        return True
    from realuse_common import auto_rebuild  # heavy module: lazy

    return auto_rebuild(lb, la)


def same_glyph(gb: dict | None, ga: dict | None) -> bool:
    if gb is None or ga is None:
        return gb is ga
    keys = (gb.keys() | ga.keys()) - GLYPH_NOISE - {"layers"}
    if any(gb.get(k) != ga.get(k) for k in keys):
        return False
    lb = {
        layer.get("name", str(i)): layer for i, layer in enumerate(gb.get("layers", []))
    }
    la = {
        layer.get("name", str(i)): layer for i, layer in enumerate(ga.get("layers", []))
    }
    mark = len(HOST_8512)
    same = lb.keys() == la.keys() and all(same_layer(lb[n], la[n]) for n in lb)
    HOST_8512[mark:] = [f"{gb.get('name')}/{layer}" for layer in HOST_8512[mark:]]
    return same


def same_cycle(a: list, b: list) -> bool:
    """Equal closed contours, whatever their start node."""
    if len(a) != len(b):
        return False
    return not a or any(a == b[i:] + b[:i] for i in range(len(b)))


def contours(layer: dict | None) -> list[list[Pt]]:
    found = []
    for element in (layer or {}).get("elements", []):
        data = element.get("elementData")
        if isinstance(data, dict):
            found += [
                parse_contour(c.get("nodes", [])) for c in data.get("contours", [])
            ]
    return found


def points(layer: dict | None) -> list[Pt]:
    return [p for c in contours(layer) for p in c]


def oncurves(layer: dict | None) -> list[Pt]:
    return [p for p in points(layer) if p.on]


def anchors(layer: dict | None) -> dict[str, tuple[float, float]]:
    out = {}
    for a in (layer or {}).get("anchors", []):
        x, y = (float(v) for v in a.get("point", "0 0").split()[:2])
        out[a.get("name", "")] = (x, y)
    return out


def components(layer: dict | None) -> list[str]:
    names = []
    for element in (layer or {}).get("elements", []):
        component = element.get("component") or (element.get("elementData") or {}).get(
            "component"
        )
        if isinstance(component, dict):
            names.append(component.get("glyphName", ""))
    return names


def placed(layer: dict | None) -> list[tuple[str, float, float]]:
    """Components of a layer with their offsets: (glyph name, x, y)."""
    found = []
    for element in (layer or {}).get("elements", []):
        component = element.get("component")
        if isinstance(component, dict):
            t = element.get("transform", {})
            found.append(
                (
                    component.get("glyphName", ""),
                    float(t.get("xOffset", 0)),
                    float(t.get("yOffset", 0)),
                )
            )
    return found


def on_outline(
    x: float, y: float, polygons: list[list[Pt]], tolerance: float = 1.5
) -> bool:
    """Is (x, y) on one of the straight-sided outlines (within tolerance)?"""
    for poly in polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            dx, dy = b.x - a.x, b.y - a.y
            t = 0.0
            if dx or dy:
                t = max(
                    0.0,
                    min(1.0, ((x - a.x) * dx + (y - a.y) * dy) / (dx * dx + dy * dy)),
                )
            if math.hypot(a.x + t * dx - x, a.y + t * dy - y) <= tolerance:
                return True
    return False


def perimeter(polygon: list[Pt]) -> float:
    return sum(
        math.dist((a.x, a.y), (b.x, b.y))
        for a, b in zip(polygon, polygon[1:] + polygon[:1])
    )


def has_shapes(layer: dict | None) -> bool:
    return bool(layer) and bool(contours(layer) or components(layer))


def bounds(pts: list[Pt]) -> tuple[float, float, float, float] | None:
    if not pts:
        return None
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def close(a: float, b: float, tolerance: float = 0.51) -> bool:
    return math.isclose(a, b, abs_tol=tolerance)


def sidebearings(layer: dict | None) -> tuple[float, float] | None:
    """(LSB, RSB) from node bounds: exact for straight-sided glyphs such as A;
    oracles that need curve extrema use glyphs without curves."""
    box = bounds(points(layer))
    if box is None:
        return None
    return box[0], float(layer.get("advanceWidth", 0)) - box[2]


def location(vfj: dict, master: str) -> dict[str, float]:
    for m in vfj["font"].get("masters", []):
        if m["fontMaster"]["name"] == master:
            return {k: float(v) for k, v in m["fontMaster"].get("location", {}).items()}
    return {}


def tab_glyphs(vfj: dict, text: str) -> list[str]:
    """Glyph names shown by a tab text: characters via the font's cmap, ``/name``
    tokens by name (FontLab's tab text uses characters where a glyph has one)."""
    cmap = {}
    for g in vfj["font"].get("glyphs", []):
        for code in str(g.get("unicode", "")).split(","):
            if code.strip():
                cmap.setdefault(chr(int(code, 16)), g["name"])
    names, i = [], 0
    while i < len(text):
        if text[i] == "/":
            j = i + 1
            while j < len(text) and text[j] not in "/ \n":
                j += 1
            names.append(text[i + 1 : j])
            i = j + (1 if j < len(text) and text[j] == " " else 0)
        elif text[i] in " \n":
            i += 1
        else:
            names.append(cmap.get(text[i], "?" + text[i]))
            i += 1
    return names


def instances(vfj: dict) -> list[tuple[str, dict[str, float]]]:
    """FontLab axis instances of a single-axis font: (name, {axis short name: value})."""
    axes = vfj["font"].get("axes", [])
    if len(axes) != 1:
        return []
    axis = axes[0]
    return [
        (i["name"].strip("()"), {axis["shortName"]: float(i["value"])})
        for i in axis.get("axisInstances", [])
    ]


def master_at(vfj: dict, where: dict[str, float]) -> str | None:
    return next((m for m in masters(vfj) if location(vfj, m) == where), None)


def tab_text(vfj: dict, names: list[str]) -> str:
    """The text FontLab shows for a tab of ``names`` (inverse of tab_glyphs)."""
    records = {g["name"]: g for g in vfj["font"].get("glyphs", [])}
    out = ""
    for name in names:
        code = str(records.get(name, {}).get("unicode", "")).split(",")[0].strip()
        out += chr(int(code, 16)) if code else f"/{name} "
    return out


def sfnt_glyph_count(data: bytes) -> int | None:
    """numGlyphs from an OpenType file's maxp table (None if not an sfnt)."""
    import struct

    if len(data) < 12 or data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        return None
    (count,) = struct.unpack(">H", data[4:6])
    for i in range(count):
        tag, _, offset, _ = struct.unpack(">4sIII", data[12 + 16 * i : 28 + 16 * i])
        if tag == b"maxp":
            return struct.unpack(">H", data[offset + 4 : offset + 6])[0]
    return None


def kerning_classes(vfj: dict, master: str) -> dict[str, tuple[bool, list[str]]]:
    """FontLab kerning classes of a master: "@name" -> (first side, glyph names)."""
    for m in vfj["font"].get("masters", []):
        if m["fontMaster"]["name"] == master:
            return {
                "@" + c["name"]: (bool(c.get("1st")), list(c.get("names", [])))
                for c in m["fontMaster"].get("kerning", {}).get("kerningClasses", [])
            }
    return {}


def kern_value(vfj: dict, master: str, left: str, right: str) -> float:
    """Effective kerning of a glyph pair: exceptions before classes, as FontLab."""
    pairs, classes = kerning(vfj, master), kerning_classes(vfj, master)
    lefts = [left] + [
        k for k, (first, names) in classes.items() if first and left in names
    ]
    rights = [right] + [
        k for k, (first, names) in classes.items() if not first and right in names
    ]
    for lk in lefts:
        for rk in rights:
            if rk in pairs.get(lk, {}):
                return float(pairs[lk][rk])
    return 0.0


def fixture(name: str) -> dict:
    """A GetGo fixture as shipped (read-only source of an owned copy or other font)."""
    from realuse_common import fixture_path  # heavy module: lazy

    return json.loads(fixture_path(name).read_text(encoding="utf-8"))


def masters(vfj: dict) -> list[str]:
    return [m["fontMaster"]["name"] for m in vfj["font"].get("masters", [])]


def kerning(vfj: dict, master: str) -> dict:
    for m in vfj["font"].get("masters", []):
        if m["fontMaster"]["name"] == master:
            return m["fontMaster"].get("kerning", {}).get("pairs", {}) or {}
    return {}


@dataclass
class Oracle:
    """What an oracle sees: both saved copies and what the run showed."""

    target: dict
    before: dict
    after: dict
    output: list[str] = field(default_factory=list)
    dialogs: list[str] = field(default_factory=list)
    windows: list[str] = field(default_factory=list)
    tab: str = ""
    files: dict[str, int] = field(default_factory=dict)  # scratch path -> size
    current: list[list[str]] = field(default_factory=list)  # [[glyph, layer]]
    selected_nodes: int | str = 0
    extra: dict = field(default_factory=dict)  # protocol results (paint, export)
    scratch: Path | None = None  # the run's scratch folder (exported files)
    prepared: object = None  # the harness prepare step's result (None: no prepare)
    clauses: list[dict] = field(default_factory=list)

    def clause(self, name: str, ok: bool, detail: object = "") -> bool:
        text = detail if isinstance(detail, str) else json.dumps(detail, default=repr)
        self.clauses.append(
            {"clause": "oracle: " + name, "asserted": bool(ok), "detail": text[:2000]}
        )
        return bool(ok)

    # --- views ----------------------------------------------------------------
    def before_glyph(self, name: str) -> dict | None:
        return glyph_record(self.before, name)

    def after_glyph(self, name: str) -> dict | None:
        return glyph_record(self.after, name)

    def lb(self, glyph: str, layer: str | None = None) -> dict | None:
        found = layers(self.before, glyph)
        return found.get(layer or self.layer) if found else None

    def la(self, glyph: str, layer: str | None = None) -> dict | None:
        found = layers(self.after, glyph)
        return found.get(layer or self.layer) if found else None

    @property
    def layer(self) -> str:
        """The layer FontLab showed (the current master) when the script ran."""
        return self.current[0][1] if self.current and len(self.current[0]) > 1 else ""

    def read(self, name: str) -> str:
        """A file the target wrote into the scratch folder (``files`` keys)."""
        return (self.scratch / name).read_text(encoding="utf-8", errors="replace")

    @property
    def text(self) -> str:
        return "\n".join(self.output)

    def changed_layers(self, glyph: str) -> set[str]:
        lb, la = layers(self.before, glyph), layers(self.after, glyph)
        return {
            n for n in lb.keys() | la.keys() if not same_layer(lb.get(n), la.get(n))
        }

    def touched(self) -> set[str]:
        """Glyphs whose data changed, ignoring FontLab's own save noise."""
        gb = {g["name"]: g for g in self.before["font"].get("glyphs", [])}
        ga = {g["name"]: g for g in self.after["font"].get("glyphs", [])}
        return {
            n for n in gb.keys() | ga.keys() if not same_glyph(gb.get(n), ga.get(n))
        }

    def font_keys_changed(self) -> set[str]:
        fb, fa = self.before["font"], self.after["font"]
        return {
            k for k in fb.keys() | fa.keys() if k != "glyphs" and fb.get(k) != fa.get(k)
        }

    # --- common properties ----------------------------------------------------
    def only_layer_changed(self, glyph: str, layer: str | None = None) -> bool:
        layer = layer or self.layer
        changed = self.changed_layers(glyph)
        return self.clause(
            f"{glyph}: only the shown layer {layer!r} changed",
            changed == {layer},
            sorted(changed),
        )

    def nothing_else_changed(
        self, glyphs: set[str], font: set[str] = frozenset()
    ) -> bool:
        others = sorted(self.touched() - set(glyphs))
        keys = sorted(self.font_keys_changed() - set(font))
        return self.clause(
            "no other glyph or font data changed",
            not others and not keys,
            {"glyphs": others[:20], "font": keys},
        )

    def composites_follow(self, base: str, layer: str = "Regular") -> set[str]:
        """Glyphs built on ``base`` that changed: the host re-lays them out when
        the base's metrics or anchors change, as Glyphs' automatic composites do
        (calibrated 2026-10-16). Asserts each changed only on ``layer`` and only
        in the fields that follow the base (components, width, anchors, and
        FontLab's TrueType hinting data, which it drops on such a change);
        returns them so the caller can exclude them from nothing_else_changed."""
        following = {
            "elements",
            "advanceWidth",
            "anchors",
            "TTData",
        }  # FontLab drops TT hinting data with the change
        found = {
            g
            for g in self.touched() - {base}
            if base in components(layers(self.before, g).get(layer))
        }

        def follows(glyph: str) -> bool:
            before, after = layers(self.before, glyph), layers(self.after, glyph)
            for name in set(before) | set(after):
                lb, la = before.get(name), after.get(name)
                if lb == la:
                    continue
                if name != layer or lb is None or la is None:
                    return False
                changed = {k for k in set(lb) | set(la) if lb.get(k) != la.get(k)}
                if not changed <= following or components(lb) != components(la):
                    return False
            return True

        self.clause(
            f"composites of {base} changed only where they follow it"
            f" ({layer}: components, width, anchors)",
            all(follows(g) for g in found),
            sorted(found)[:20],
        )
        return found

    def unchanged(self) -> bool:
        return self.clause(
            "the owned font is unchanged",
            not self.touched() and not self.font_keys_changed(),
            {
                "glyphs": sorted(self.touched())[:20],
                "font": sorted(self.font_keys_changed()),
            },
        )

    # --- mutation helpers for examples/counterexamples -----------------------------
    def edit_layer(self, glyph: str, layer: str | None = None) -> dict:
        return layers(self.after, glyph)[layer or self.layer]


def set_contours(layer: dict, new: list[list[Pt]]) -> None:
    """Replace the contours of a layer's first path element (examples only)."""

    def fmt(v: float) -> str:
        return str(int(v)) if float(v).is_integer() else repr(round(v, 3))

    segments = []
    for contour in new:
        out, pending = [], []
        for p in contour:
            text = fmt(p.x) + " " + fmt(p.y) + (" s" if p.smooth else "")
            if p.on:
                out.append("  ".join([*pending, text]))
                pending = []
            else:
                pending.append(text)
        if pending:
            out.append("  ".join(pending) + " c")
        segments.append({"nodes": out})
    for element in layer.get("elements", []):
        if (
            isinstance(element.get("elementData"), dict)
            and "contours" in element["elementData"]
        ):
            element["elementData"]["contours"] = segments
            return
    layer.setdefault("elements", []).append({"elementData": {"contours": segments}})


def load(target_id: str):
    path = ORACLES / f"{target_id}.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(
        f"oracle_{target_id.replace('-', '_')}", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(oracle: Oracle) -> list[dict]:
    """Run the target's oracle; a target without one cannot pass (fail closed)."""
    if oracle.target.get("prepare"):  # the harness setup, not the target, failed
        ok = not (
            isinstance(oracle.prepared, dict) and "prepare_error" in oracle.prepared
        )
        oracle.clause(
            "harness prepare took effect (ran without error)",
            ok and oracle.prepared is not None,
            oracle.prepared,
        )
    module = load(oracle.target["id"])
    if module is None:
        oracle.clause(
            "result oracle defined",
            False,
            f"missing realuse/oracles/{oracle.target['id']}.py",
        )
        return oracle.clauses
    HOST_8512.clear()
    ITALIC.clear()
    if isinstance(oracle.before, dict) and isinstance(oracle.after, dict):
        ITALIC.update(italic_masters(oracle.before, oracle.after))
    try:
        module.check(oracle)
    except Exception as error:  # noqa: BLE001 - an oracle crash is a failed oracle
        oracle.clause(
            "oracle evaluated without error", False, f"{type(error).__name__}: {error}"
        )
    if HOST_8512:  # recorded, not hidden: the host defect touched these layers
        oracle.note_host_8512 = sorted(set(HOST_8512))
    if not oracle.clauses:
        oracle.clause("oracle asserted something", False, "check() added no clause")
    return oracle.clauses


CONTEXT_FIELDS = (
    "output",
    "dialogs",
    "windows",
    "tab",
    "files",
    "current",
    "selected_nodes",
    "extra",
    "prepared",
)


def save_context(oracle: Oracle, path: Path) -> None:
    """Everything but the VFJ copies (saved next to it as before/after*.vfj)."""
    data = {name: getattr(oracle, name) for name in CONTEXT_FIELDS}
    data["extra"] = {
        k: v for k, v in oracle.extra.items() if k != "others"
    }  # saved as VFJ
    data["target"] = oracle.target
    path.write_text(json.dumps(data, default=repr), encoding="utf-8")


def restore(folder: Path) -> Oracle:
    """An Oracle rebuilt from an extracted run artifact (reevaluate.py)."""
    data = json.loads((folder / "oracle-context.json").read_text(encoding="utf-8"))
    others = sorted(folder.glob("after-other-*.vfj"))
    extra = dict(data["extra"])
    if others:
        extra["others"] = [json.loads(p.read_text(encoding="utf-8")) for p in others]
    return Oracle(
        data["target"],
        json.loads((folder / "before.vfj").read_text(encoding="utf-8")),
        json.loads((folder / "after.vfj").read_text(encoding="utf-8")),
        **{k: data[k] for k in CONTEXT_FIELDS if k != "extra"},
        extra=extra,
        scratch=folder,
    )


def fresh(target: dict, vfj: dict, **context) -> Oracle:
    """Before = after = a deep copy of ``vfj`` (tests mutate ``after``)."""
    return Oracle(target, copy.deepcopy(vfj), copy.deepcopy(vfj), **context)
