# this_file: native-drivers/round19_owned_checks.py
"""G1-only checks: run solo with FL_RESTART=1, then restart FontLab.

Load this file in the host and call run(absolute_empty_scratch_directory).
Never run against owner documents. This module creates its own two fonts;
no native calls occur at import. F57 save/reopen is deliberately synchronous
and must use G1's isolated crash/hang-fenced driver, not a shared session.
"""

from pathlib import Path
from uuid import uuid4


def run(output_directory):
    from fly import fl as fontlab
    from fly import pr as fontpr
    from fly.gp.model import GSAnchor, Model
    from fly.gp.model.fontlab_backend import FontLabBackend

    root = Path(output_directory)
    assert root.is_absolute(), "FontLab resolves relative saves against its cwd"
    root.mkdir(parents=True, exist_ok=False)
    workspace = fontlab.flWorkspace.instance()
    assert not workspace.packages(), "FL_RESTART=1 with no owner documents required"
    owned_ids = []

    def create(label):
        response = fontpr.call(
            "new_font",
            family_name=f"GlyportR19-{label}-{uuid4().hex}",
            style_name="Regular",
        )
        font_id = response["font"]["id"]
        owned_ids.append(font_id)
        package = workspace.currentPackage
        assert package.fgId == font_id
        return package

    def geometry(glyph):
        return {
            "name": glyph.name,
            "unicodes": list(glyph.unicodes),
            "layers": [
                {
                    "name": layer.name,
                    "width": layer.width,
                    "paths": [
                        [
                            (tuple(node.position), node.type, node.smooth)
                            for node in path.nodes
                        ]
                        for path in layer.paths
                    ],
                    "anchors": [(a.name, tuple(a.position)) for a in layer.anchors],
                }
                for layer in glyph.layers
            ],
        }

    try:
        source_package, target_package = create("source"), create("target")
        backend = FontLabBackend(packages=[source_package, target_package])
        model = Model(backend)
        source = model._font(backend._font_id(source_package))
        target = model._font(backend._font_id(target_package))
        for package in (source_package, target_package):
            fontpr.call(
                "set_glyph",
                font_id=package.fgId,
                glyph_name="A",
                create=True,
                glyph_data={
                    "name": "A",
                    "unicode": "0041",
                    "layers": [
                        {
                            "name": str(package.masters[0]),
                            "advanceWidth": 500,
                            "elements": [
                                {
                                    "elementData": {
                                        "contours": [
                                            {
                                                "nodes": [
                                                    "10 0",
                                                    "110 0",
                                                    "110 200",
                                                    "10 200",
                                                ]
                                            }
                                        ]
                                    }
                                }
                            ],
                        }
                    ],
                },
            )
        source_layer = source.glyphs["A"].layers[0]
        source_layer.paths[0].nodes[0].x += 15
        source_layer.width += 30
        source_layer.anchors.append(GSAnchor("top", (60, 200)))
        expected = geometry(source.glyphs["A"])
        copied = source.glyphs["A"].copy()
        del target.glyphs["A"]
        target.glyphs.append(copied)
        assert geometry(target.glyphs["A"]) == expected
        destination = root / "round19-target.vfj"
        fontpr.call(
            "save_font",
            font_id=target_package.fgId,
            path=str(destination),
            overwrite=False,
        )
        target_id = target_package.fgId
        fontpr.call("close_font", font_id=target_id, save=False)
        owned_ids.remove(target_id)
        before = {p.id for p in workspace.packages()}
        fontpr.call("open_font", path=str(destination))
        reopened = [
            fontlab.flPackage(p) for p in workspace.packages() if p.id not in before
        ]
        assert len(reopened) == 1
        owned_ids.append(reopened[0].fgId)
        fresh = FontLabBackend(packages=reopened)
        reopened_font = Model(fresh)._font(fresh._font_id(reopened[0]))
        assert geometry(reopened_font.glyphs["A"]) == expected
        print("ROUND19_F57_SAVE_REOPEN_PASSED")
        # Complete native VFJ before/after a public-property audit, not just IDs.
        before_read = fontpr.call(
            "get_glyph", font_id=source_package.fgId, glyph_name="A"
        )
        from fly.gp.errors import UnsupportedCapability

        glyph = source.glyphs["A"]
        objects = [
            glyph,
            source_layer,
            *source_layer.paths,
            *(node for path in source_layer.paths for node in path.nodes),
            *source_layer.anchors,
        ]
        for obj in objects:
            for cls in type(obj).__mro__:
                for name, descriptor in vars(cls).items():
                    if name.startswith("_") or not isinstance(descriptor, property):
                        continue
                    try:
                        getattr(obj, name)
                    except UnsupportedCapability:
                        pass
        assert (
            fontpr.call("get_glyph", font_id=source_package.fgId, glyph_name="A")
            == before_read
        )
        assert source_layer.master.font is source
        assert source_layer.anchorForName_("top").position == (60, 200)
        assert source.kerningDict() == source.kerning
        assert source_layer.paths[0].bezierPath.containsPoint_((50, 100))
        source_layer.master.italicAngle = 9
        assert source_layer.master.italicAngle == 9
        # Cover actual metric evaluation, including restoration of active layer.
        from fly.gp.model import GSGlyph

        reference = source.glyphs.append(GSGlyph("reference"))
        from fly.gp.model import GSNode, GSPath

        reference.layers[0].paths = [
            GSPath(
                [
                    GSNode((30, 0)),
                    GSNode((130, 0)),
                    GSNode((130, 200)),
                    GSNode((30, 200)),
                ],
                closed=True,
            )
        ]
        reference.layers[0].width = 180
        source_layer.leftMetricsKey = "=reference"
        source_layer.rightMetricsKey = "=reference"
        native_glyph = source_package.findName("A")
        active = native_glyph.activeLayer
        source_layer.updateMetrics()
        assert native_glyph.activeLayer.id == active.id
        assert abs(source_layer.LSB - reference.layers[0].LSB) < 0.01
        assert abs(source_layer.RSB - reference.layers[0].RSB) < 0.01
        source_layer.leftMetricsKey = source_layer.rightMetricsKey = None
        return {
            "F57": "save/reopen passed",
            "updateMetrics": "evaluated; active layer restored",
            "italicAngle": source_layer.master.italicAngle,
        }
    finally:
        for font_id in reversed(owned_ids):
            fontpr.call("close_font", font_id=font_id, save=False)
