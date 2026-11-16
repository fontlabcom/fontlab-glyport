# this_file: src/fontlab_glyport/model/fake_backend.py
"""Deterministic in-memory test helper; never used as a native fallback."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from itertools import count

from ..errors import StaleNativeObject, UnsupportedCapability
from .backend import (
    AnchorInfo,
    ClassInfo,
    ComponentInfo,
    EditViewInfo,
    FeatureInfo,
    FeaturesInfo,
    FontInfo,
    GlyphInfo,
    GuideInfo,
    HintInfo,
    InstanceInfo,
    KerningClassInfo,
    KerningPair,
    LayerIdentity,
    LayerInfo,
    MasterInfo,
    MasterMetrics,
    NodeInfo,
    PathInfo,
)
from .outline_ops import OutlineOperations


class FakeBackend(OutlineOperations):
    supports_anchor_selection = True
    supports_component_selection = True
    supports_guide_selection = True

    def __setattr__(self, key, value):
        from .revisions import RevisionDict

        if (
            not key.startswith("_")
            and isinstance(value, dict)
            and not isinstance(value, RevisionDict)
        ):
            value = RevisionDict(value, self._bump)
        object.__setattr__(self, key, value)
        if not key.startswith("_") and isinstance(value, RevisionDict):
            self._bump()

    def _bump(self):
        self._generation += 1

    def revision(self, font_id):
        self._require(font_id)
        return self._generation

    def __init__(self):
        self._generation = 0
        self._valid_generation = -1
        self._pending_backgrounds = {}
        self._copy_references = {}
        self._serial = count()
        self._selected_glyphs = set()
        self._font_selections = {}
        self.master_guides_data = {}
        self.master_zones_data = {}
        self.metrics: dict = {}  # master id -> MasterMetrics
        self.metric_reads: list = []
        self.notes: dict = {}  # glyph id -> note
        self.last_changes: dict = {}  # glyph id -> "YYYY-MM-DD HH:MM:SS"
        self.vertical_widths: dict = {}  # layer id -> advance height
        self.metrics_keys = {}
        self.marks: dict = {}  # glyph/layer id -> FontLab mark hue
        self.tags: dict = {}  # glyph id -> tuple of tags
        self.fonts = {
            "font": FontInfo(
                "font", "Example", 1000, (MasterInfo("master", "Regular"),)
            )
        }
        self.glyph_lists = {"font": (GlyphInfo("glyph", "A", ("0041",)),)}
        path = PathInfo("path", (NodeInfo("node", 0, 0),))
        self.layers = {
            ("glyph", "master"): LayerInfo(
                "layer",
                "master",
                500,
                (path,),
                (ComponentInfo("component", "A", (1, 0, 0, 1, 0, 0)),),
                (),
                ("path", "component"),
            )
        }
        self.current = "font"
        self.current_masters = {}
        self.font_paths: dict[str, str] = {}
        self.libs = {}
        self.feature_data = {}
        self.instance_data = {}
        self.kerning_data = {}
        self.hint_data = {}
        self.kerning_class_data = {}
        self.edit_views = {}
        self.class_data = {}
        self.bounds_data = {}
        self.transforms = []
        self.edit_texts = []
        self.current_layer_data = {}
        self.undo_events = []
        self._undo = False
        self._saved_revisions = {"font": self._generation}

    def _id(self):
        return f"new-{next(self._serial)}"

    def dark_mode(self):
        return False

    def list_fonts(self) -> tuple[str, ...]:
        return tuple(self.fonts)

    def current_font_id(self) -> str | None:
        return self.current

    def font_info(self, font_id: str) -> FontInfo:
        self._require(font_id)
        return self.fonts[font_id]

    def set_font_info(self, font_id, **changes):
        self.fonts[font_id] = replace(self.font_info(font_id), **changes)

    def append_master(self, font_id, master, metrics):
        info = self.font_info(font_id)
        if any(item.name == master.name for item in info.masters):
            raise ValueError("Duplicate master name")
        master = replace(master, id=self._id())
        self.fonts[font_id] = replace(info, masters=(*info.masters, master))
        self.metrics[master.id] = metrics
        for glyph in self.glyphs(font_id):
            self.layers[glyph.id, master.id] = LayerInfo(self._id(), master.id, 0)
        return master.id

    def set_master_info(self, master_id, **changes):
        self._require(master_id)
        if "name" in changes:
            for fid, info in self.fonts.items():
                if not any(m.id == master_id for m in info.masters):
                    continue
                if any(m.id != master_id and m.name == changes["name"] for m in info.masters):
                    raise ValueError("Duplicate master name")
                self.fonts[fid] = replace(info, masters=tuple(
                    replace(m, name=changes["name"]) if m.id == master_id else m
                    for m in info.masters))
        else:
            self.metrics[master_id] = replace(self.master_metrics(master_id), **changes)

    def font_path(self, font_id: str) -> str | None:
        self._require(font_id)
        return self.font_paths.get(font_id) or None

    def save_font(self, font_id: str, path: str | None = None, *, make_copy=False) -> None:
        """Write this fake font's first master as a real UFO for offline tests."""
        from pathlib import Path
        from types import SimpleNamespace

        from ..fonttools import fonttools_module

        self._require(font_id)
        if make_copy and path is None:
            raise ValueError("A path is required for makeCopy=True")
        path = path if path is not None else self.font_path(font_id)
        if not path:
            raise ValueError("No path set for this font")
        if Path(path).suffix.lower() != ".ufo":
            raise ValueError("FakeBackend.save supports .ufo paths")
        writer_cls = fonttools_module("ufoLib", "GSFont.save").UFOWriter
        font = self.font_info(font_id)
        if not font.masters:
            raise ValueError("Cannot save a font without a master")
        with writer_cls(path, formatVersion=3) as writer:
            writer.writeInfo(SimpleNamespace(familyName=font.familyName,
                                             unitsPerEm=font.unitsPerEm))
            glyph_set = writer.getGlyphSet()
            for glyph in self.glyphs(font_id):
                layer = self.layer(glyph.id, font.masters[0].id)
                data = SimpleNamespace(width=layer.width,
                                       unicodes=[int(u, 16) for u in glyph.unicodes])
                glyph_set.writeGlyph(glyph.name, data, lambda pen, lid=layer.id:
                                     self.draw_layer(lid, pen, points=True))
            glyph_set.writeContents()
            writer.writeLayerContents()
        if not make_copy:
            self.font_paths[font_id] = str(path)
            self._saved_revisions[font_id] = self._generation

    def outline_layer(self, layer_id: str) -> LayerInfo:
        """Return the live immutable outline snapshot."""
        self._require(layer_id)
        return self.layers[self._layer_key(layer_id)]

    def validate_component_expansion(self, layer_id, components) -> None:
        """Resolve the complete reference graph, refusing cycles before edits."""
        for component in components:
            self._component_reference(*self._layer_key(layer_id), component.componentName)

    def glyphs(self, font_id: str) -> tuple[GlyphInfo, ...]:
        self._require(font_id)
        return self.glyph_lists[font_id]

    def layer(self, glyph_id: str, master_id: str) -> LayerInfo:
        self._require(glyph_id)
        info = self.layers[glyph_id, master_id]
        self._require(info.masterId)
        return info

    def glyph_layers(self, glyph_id):
        self._require(glyph_id)
        font = next(
            self.fonts[fid]
            for fid, glyphs in self.glyph_lists.items()
            if any(g.id == glyph_id for g in glyphs)
        )
        if not font.masters:
            return ()
        result = [LayerIdentity(m.id, m.id, m.name) for m in font.masters]
        result.extend(
            LayerIdentity(key, layer.masterId, layer.name)
            for (glyph, key), layer in self.layers.items()
            if glyph == glyph_id
            and not key.endswith("#mask")
            and key not in {m.id for m in font.masters}
        )
        return tuple(result)

    def background_layer(self, layer_id):
        glyph, master = self._layer_key(layer_id)
        key = glyph, master + "#mask"
        if key in self.layers:
            return self.layers[key]
        if key not in self._pending_backgrounds:
            foreground = self.layers[glyph, master]
            self._pending_backgrounds[key] = LayerInfo(
                self._id(), foreground.masterId, 0, layerId=foreground.layerId
            )
            self._valid_generation = -1
        return self._pending_backgrounds[key]

    def snapshot_layer(self, layer_id):
        self._require(layer_id)
        key = self._layer_keys[layer_id]

        def capture(key):
            info = self.layers.get(key)
            if info is None:
                return None
            master_name = next(
                m.name
                for font in self.fonts.values()
                for m in font.masters
                if m.id == info.masterId
            )
            return deepcopy(
                (
                    info,
                    self.libs.get(info.id, {}),
                    self.hint_data.get(info.id, ()),
                    {
                        side: self.metrics_keys.get((info.id, side))
                        for side in ("left", "right", "width")
                    },
                    self._copy_references.get(
                        info.id,
                        tuple((c.componentName, master_name) for c in info.components),
                    ),
                )
            )

        return ("fake-layer-copy", capture(key), capture((key[0], key[1] + "#mask")))

    def append_layer(self, glyph_id, master_id, name, snapshot):
        from .layer_attachment import validate_name

        self._require(glyph_id)
        font = next(
            self.fonts[fid]
            for fid, glyphs in self.glyph_lists.items()
            if any(g.id == glyph_id for g in glyphs)
        )
        if master_id not in {m.id for m in font.masters}:
            raise ValueError("Master belongs to a different document")
        validate_name(
            name,
            [m.name for m in font.masters]
            + [info.name for (gid, _), info in self.layers.items() if gid == glyph_id],
        )
        if not isinstance(snapshot, tuple) or snapshot[0] != "fake-layer-copy":
            raise UnsupportedCapability("Incompatible layer-copy backend")
        _, foreground, background = deepcopy(snapshot)
        available = {g.name: g.id for g in self.glyph_lists[font.id]}
        masters_by_name = {m.name: m.id for m in font.masters}
        for payload in (foreground, background):
            if payload is None:
                continue
            for component, reference in payload[4]:
                if component not in available:
                    raise ValueError("Missing destination component glyph")
                if (
                    reference not in masters_by_name
                    or (available[component], masters_by_name[reference])
                    not in self.layers
                ):
                    raise ValueError("Missing destination component reference layer")
        token = self._id()

        def stage(payload, mask=False):
            info, lib, hints, metrics, references = payload
            ids = {
                item.id: self._id()
                for item in (*info.paths, *info.components, *info.anchors, *info.guides)
            }
            paths = tuple(
                replace(
                    p,
                    id=ids[p.id],
                    nodes=tuple(replace(n, id=self._id()) for n in p.nodes),
                )
                for p in info.paths
            )
            info = replace(
                info,
                id=self._id() if mask else token,
                masterId=master_id,
                layerId=token,
                name=("mask." if mask else "") + name,
                paths=paths,
                components=tuple(replace(c, id=ids[c.id]) for c in info.components),
                anchors=tuple(replace(a, id=ids[a.id]) for a in info.anchors),
                guides=tuple(replace(g, id=ids[g.id]) for g in info.guides),
                shape_ids=tuple(ids[i] for i in info.shape_ids),
            )
            return info, lib, hints, metrics, references

        staged = [(token, stage(foreground))]
        if background is not None:
            staged.insert(0, (token + "#mask", stage(background, True)))
        for key, (info, lib, hints, metrics, references) in staged:
            self.layers[glyph_id, key] = info
            self._copy_references[info.id] = references
            self.libs[info.id], self.hint_data[info.id] = lib, hints
            for side, value in metrics.items():
                self.metrics_keys[info.id, side] = value
        return token

    def clear_background_layer(self, layer_id):
        glyph, master = self._layer_key(layer_id)
        key = glyph, master + "#mask"
        if key not in self.layers:
            return
        self.layers.pop(key, None)
        self._pending_backgrounds.pop(key, None)
        self._bump()

    def validate_collection(self, layer_id, field, infos):
        from .bulk import validate_infos

        self._require(layer_id)
        names = {g.name for glyphs in self.glyph_lists.values() for g in glyphs}
        validate_infos(field, infos, names.__contains__)

    def prepare_collection(self, layer_id, field, *, state=None):
        # Immutable fake records already separate history from working geometry.
        pass

    def snapshot_collection(self, layer_id, *, stage=False):
        # Reading a pending mask must remain read-only.
        self._require(layer_id)
        if layer_id not in self._layer_keys:
            return None
        key = self._layer_keys[layer_id]
        return key, self.layers[key], self.hint_data.get(layer_id, ())

    def restore_collection(self, layer_id, state):
        if state is None:
            for key, layer in list(self.layers.items()):
                if layer.id == layer_id:
                    self._pending_backgrounds[key] = replace(
                        layer,
                        paths=(),
                        components=(),
                        anchors=(),
                        guides=(),
                        shape_ids=(),
                    )
                    del self.layers[key]
            return
        key, info, hints = state
        self.layers[key] = info
        self.hint_data[layer_id] = hints

    def layer_metrics_key(self, layer_id, side):
        self._require(layer_id)
        return self.metrics_keys.get((layer_id, side)) or None

    def set_layer_metrics_key(self, layer_id, side, value):
        self._require(layer_id)
        self.metrics_keys[layer_id, side] = value

    def append_master_guide(self, master_id, guide):
        self._require(master_id)
        guide = replace(guide, id=self._id())
        self.master_guides_data[master_id] = (*self.master_guides(master_id), guide)
        self._generation += 1
        return guide.id

    def update_layer_metrics(self, layer_id):
        self._require(layer_id)
        if any(
            self.layer_metrics_key(layer_id, side)
            for side in ("left", "right", "width")
        ):
            raise UnsupportedCapability(
                "Fake metric expression evaluation", capability="GSLayer.updateMetrics"
            )

    def master_guides(self, master_id):
        self._require(master_id)
        return self.master_guides_data.get(master_id, ())

    def master_zones(self, master_id):
        self._require(master_id)
        return self.master_zones_data.get(master_id, ())

    def set_master_zone(self, master_id, index, position, size):
        values = list(self.master_zones(master_id))
        values[index] = position, size
        self.master_zones_data[master_id] = tuple(values)

    def glyph_selected(self, font_id, glyph_id):
        self._require(glyph_id)
        return glyph_id in self._selected_glyphs

    def set_glyph_selected(self, font_id, glyph_id, value):
        self._require(glyph_id)
        (self._selected_glyphs.add if value else self._selected_glyphs.discard)(
            glyph_id
        )

    def path_attributes(self, path_id):
        self._require(path_id)
        return dict(self._member_infos[path_id].attributes)

    def set_path_attributes(self, path_id, values):
        self._require(path_id)
        for key, layer in list(self.layers.items()):
            if any(p.id == path_id for p in layer.paths):
                self.layers[key] = replace(
                    layer,
                    paths=tuple(
                        replace(p, attributes=dict(values)) if p.id == path_id else p
                        for p in layer.paths
                    ),
                )
                return

    def _set_member(self, token, field, **changes):
        self._require(token)
        key = self._member_layers[token]
        layer = self.layers[key]
        self.layers[key] = replace(layer, **{field: tuple(
            replace(item, **changes) if item.id == token else item
            for item in getattr(layer, field))})

    def component_selected(self, component_id):
        self._require(component_id)
        return self._member_infos[component_id].selected

    def set_component_selected(self, component_id, value):
        self._set_member(component_id, "components", selected=value)

    def guide_selected(self, guide_id):
        self._require(guide_id)
        return self._member_infos[guide_id].selected

    def set_guide_selected(self, guide_id, value):
        self._set_member(guide_id, "guides", selected=value)

    def set_anchor_name(self, anchor_id, name):
        self._set_member(anchor_id, "anchors", name=name)

    def set_component_transform(self, component_id, transform):
        self._set_member(component_id, "components", transform=transform)

    def set_node_type(self, node_id, kind):
        self._require(node_id)
        key = self._member_layers[node_id]
        layer = self.layers[key]
        self.layers[key] = replace(layer, paths=tuple(
            replace(path, nodes=tuple(
                replace(node, type=kind) if node.id == node_id else node
                for node in path.nodes)) for path in layer.paths))

    def anchor_selected(self, anchor_id):
        self._require(anchor_id)
        return self._member_infos[anchor_id].selected

    def set_anchor_selected(self, anchor_id, value):
        self._require(anchor_id)
        key = self._member_layers[anchor_id]
        layer = self.layers[key]
        self.layers[key] = replace(
            layer,
            anchors=tuple(
                replace(a, selected=value) if a.id == anchor_id else a
                for a in layer.anchors
            ),
        )

    def set_component_position(self, component_id, x, y):
        self._require(component_id)
        key = self._member_layers[component_id]
        layer = self.layers[key]
        self.layers[key] = replace(
            layer,
            components=tuple(
                replace(c, transform=(*c.transform[:4], float(x), float(y)))
                if c.id == component_id
                else c
                for c in layer.components
            ),
        )

    def component_bounds(self, component_id):
        from .detached_geometry import layer_bounds
        from .proxies import Model

        self._require(component_id)
        glyph_id, master = self._member_layers[component_id]
        font_id = next(
            fid
            for fid, glyphs in self.glyph_lists.items()
            if any(g.id == glyph_id for g in glyphs)
        )
        source = Model(self)._font(font_id).glyphs[glyph_id].layers[master]
        detached = source.copy()
        detached.shapes = [source.components[component_id].copy()]
        return layer_bounds(detached)

    def proxy_parent(self, token: str) -> str | None:
        self._require(token)
        if not isinstance(self._member_infos.get(token), ComponentInfo):
            return None
        return self.layers[self._member_layers[token]].id

    def layer_location(self, layer_id: str) -> tuple[str, str, bool]:
        glyph, master = self._layer_key(layer_id)
        return glyph, master.removesuffix("#mask"), master.endswith("#mask")

    def set_component_name(self, component_id: str, name: str) -> None:
        self._require(component_id)
        glyph, master = self._member_layers[component_id]
        layer = self.layers[glyph, master]
        current = next(c for c in layer.components if c.id == component_id)
        if current.componentName == name:
            return
        self._component_reference(glyph, master, name)
        self.layers[glyph, master] = replace(
            layer,
            components=tuple(
                replace(c, componentName=name) if c.id == component_id else c
                for c in layer.components
            ),
        )

    def _component_reference(self, glyph_id: str, master: str, name: str) -> LayerInfo:
        from .component_edits import _walk

        font_id = next(
            fid
            for fid, glyphs in self.glyph_lists.items()
            if any(g.id == glyph_id for g in glyphs)
        )
        names = {g.name: g.id for g in self.glyph_lists[font_id]}

        def resolve(reference: str) -> tuple[tuple[str, str], list[str], LayerInfo]:
            if reference not in names:
                raise ValueError(f"No glyph named {reference!r} in the containing font")
            key = names[reference]
            source = self.layers[key, master]
            return (
                (key, source.id),
                [c.componentName for c in source.components],
                source,
            )

        return _walk((glyph_id, self.layers[glyph_id, master].id), name, resolve)

    def _transformed_component_shape(
        self, info: PathInfo | ComponentInfo, matrix: tuple
    ) -> PathInfo | ComponentInfo:
        a, b, c, d, e, f = matrix
        if isinstance(info, ComponentInfo):
            x, y, z, w, tx, ty = info.transform
            return replace(
                info,
                id=self._id(),
                transform=(
                    a * x + c * y,
                    b * x + d * y,
                    a * z + c * w,
                    b * z + d * w,
                    a * tx + c * ty + e,
                    b * tx + d * ty + f,
                ),
            )
        return replace(
            info,
            id=self._id(),
            nodes=tuple(
                replace(
                    n, id=self._id(), x=a * n.x + c * n.y + e, y=b * n.x + d * n.y + f
                )
                for n in info.nodes
            ),
        )

    def decompose_component(
        self, layer_id: str, component_id: str, *, on_detach: Callable[[], None]
    ) -> None:
        key = self._layer_key(layer_id)
        layer = self.layers[key]
        target = next(c for c in layer.components if c.id == component_id)
        source = self._component_reference(*key, target.componentName)
        shapes = {s.id: s for s in (*source.paths, *source.components)}
        infos = [
            self._transformed_component_shape(shapes[i], target.transform)
            for i in source.shape_ids
        ]
        records = {s.id: s for s in (*layer.paths, *layer.components, *infos)}
        order = [
            i
            for old in layer.shape_ids
            for i in ([s.id for s in infos] if old == component_id else [old])
        ]
        self.layers[key] = replace(
            layer,
            shape_ids=tuple(order),
            paths=tuple(
                records[i] for i in order if not isinstance(records[i], ComponentInfo)
            ),
            components=tuple(
                records[i] for i in order if isinstance(records[i], ComponentInfo)
            ),
        )
        on_detach()

    def remove_component(self, layer_id, component_id):
        key = self._layer_key(layer_id)
        layer = self.layers[key]
        if component_id not in {c.id for c in layer.components}:
            raise ValueError("Component does not belong to layer")
        self.layers[key] = replace(
            layer,
            components=tuple(c for c in layer.components if c.id != component_id),
            shape_ids=tuple(i for i in layer.shape_ids if i != component_id),
        )

    def set_guide(self, guide_id, **changes):
        self._require(guide_id)
        for key, layer in self.layers.items():
            if any(guide.id == guide_id for guide in layer.guides):
                self.layers[key] = replace(
                    layer,
                    guides=tuple(
                        replace(guide, **changes) if guide.id == guide_id else guide
                        for guide in layer.guides
                    ),
                )
                return
        for master_id, guides in self.master_guides_data.items():
            if any(guide.id == guide_id for guide in guides):
                self.master_guides_data[master_id] = tuple(
                    replace(guide, **changes) if guide.id == guide_id else guide
                    for guide in guides
                )
                return

    def remove_guide(self, layer_id, guide_id):
        key = self._layer_key(layer_id)
        layer = self.layers[key]
        if guide_id not in {g.id for g in layer.guides}:
            raise ValueError("Guide does not belong to layer")
        self.layers[key] = replace(
            layer, guides=tuple(g for g in layer.guides if g.id != guide_id)
        )

    def _require(self, id):
        if not self.is_valid(id):
            raise StaleNativeObject(id)

    def is_valid(self, id: str) -> bool:
        if self._valid_generation != self._generation:
            ids = set(self.fonts)
            glyph_ids = set()
            for font in self.fonts.values():
                ids.update(master.id for master in font.masters)
                glyph_ids.update(g.id for g in self.glyph_lists.get(font.id, ()))
            ids.update(glyph_ids)
            self._layer_keys, self._member_infos, self._member_layers = {}, {}, {}
            for key, layer in self.layers.items():
                if key[0] not in glyph_ids:
                    continue
                self._layer_keys[layer.id] = key
                ids.add(layer.id)
                self._member_infos.update(
                    (v.id, v)
                    for v in (
                        *layer.paths,
                        *layer.components,
                        *layer.anchors,
                        *layer.guides,
                    )
                )
                self._member_infos.update(
                    (n.id, n) for path in layer.paths for n in path.nodes
                )
                for value in (
                    *layer.paths,
                    *layer.components,
                    *layer.anchors,
                    *layer.guides,
                ):
                    self._member_layers[value.id] = key
                for path in layer.paths:
                    self._member_layers.update((n.id, key) for n in path.nodes)
                ids.update(
                    v.id
                    for v in (
                        *layer.paths,
                        *layer.components,
                        *layer.anchors,
                        *layer.guides,
                    )
                )
                ids.update(n.id for path in layer.paths for n in path.nodes)
            ids.update(
                info.id
                for (glyph, _), info in self._pending_backgrounds.items()
                if glyph in glyph_ids
            )
            ids.update(
                guide.id
                for mid, guides in self.master_guides_data.items()
                if mid in ids
                for guide in guides
            )
            self._valid_ids, self._valid_generation = ids, self._generation
        return id in self._valid_ids

    def _layer_key(self, layer_id):
        self._require(layer_id)
        if layer_id in self._layer_keys:
            return self._layer_keys[layer_id]
        key = next(
            k for k, info in self._pending_backgrounds.items() if info.id == layer_id
        )
        self.layers[key] = self._pending_backgrounds.pop(key)
        return key

    def set_layer_width(self, layer_id: str, width: float) -> None:
        key = self._layer_key(layer_id)
        self.layers[key] = replace(self.layers[key], width=width)

    def node_name(self, node_id):
        self._require(node_id)
        return self._member_infos[node_id].name

    def set_node_name(self, node_id, name):
        self._require(node_id)
        key = self._member_layers[node_id]
        layer = self.layers[key]
        self.layers[key] = replace(
            layer,
            paths=tuple(
                replace(
                    path,
                    nodes=tuple(
                        replace(node, name=name) if node.id == node_id else node
                        for node in path.nodes
                    ),
                )
                for path in layer.paths
            ),
        )

    def set_node_position(self, node_id: str, x: float, y: float) -> None:
        self._require(node_id)
        for key, layer in self.layers.items():
            paths = tuple(
                replace(
                    p,
                    nodes=tuple(
                        replace(n, x=x, y=y) if n.id == node_id else n for n in p.nodes
                    ),
                )
                for p in layer.paths
            )
            self.layers[key] = replace(layer, paths=paths)

    def set_node_smooth(self, node_id: str, smooth: bool) -> None:
        self.set_node_connection(node_id, 100 if smooth else 0)

    def set_node_connection(self, node_id: str, connection: int) -> None:
        self._require(node_id)
        for key, layer in self.layers.items():
            paths = tuple(
                replace(
                    p,
                    nodes=tuple(
                        replace(n, smooth=connection == 100, connection=connection)
                        if n.id == node_id
                        else n
                        for n in p.nodes
                    ),
                )
                for p in layer.paths
            )
            self.layers[key] = replace(layer, paths=paths)

    def make_node_first(self, node_id: str) -> None:
        """Rotate the closed path so the node is last (Glyphs' start node)."""
        self._require(node_id)
        for key, layer in self.layers.items():
            paths = []
            for path in layer.paths:
                ids = [n.id for n in path.nodes]
                if node_id in ids:
                    cut = ids.index(node_id) + 1
                    path = replace(path, nodes=path.nodes[cut:] + path.nodes[:cut])
                paths.append(path)
            self.layers[key] = replace(layer, paths=tuple(paths))

    def layer_bounds(self, layer_id: str):
        self._require(layer_id)
        return self.bounds_data.get(layer_id)

    def transform_layer(self, layer_id: str, matrix) -> None:
        self._require(layer_id)
        self.transforms.append((layer_id, tuple(matrix)))
        from ..drawing.context import apply, concat

        key = self._layer_key(layer_id)
        layer = self.layers[key]
        self.layers[key] = replace(
            layer,
            paths=tuple(
                replace(
                    path,
                    nodes=tuple(
                        replace(
                            node,
                            x=apply(matrix, node.x, node.y)[0],
                            y=apply(matrix, node.x, node.y)[1],
                        )
                        for node in path.nodes
                    ),
                )
                for path in layer.paths
            ),
            anchors=tuple(
                replace(
                    anchor,
                    x=apply(matrix, anchor.x, anchor.y)[0],
                    y=apply(matrix, anchor.x, anchor.y)[1],
                )
                for anchor in layer.anchors
            ),
            components=tuple(
                replace(component, transform=concat(component.transform, matrix))
                for component in layer.components
            ),
        )

    def set_anchor_position(self, anchor_id: str, x: float, y: float) -> None:
        self._require(anchor_id)
        for key, layer in self.layers.items():
            anchors = tuple(
                replace(a, x=x, y=y) if a.id == anchor_id else a for a in layer.anchors
            )
            self.layers[key] = replace(layer, anchors=anchors)

    def current_master(self, font_id: str) -> str | None:
        self._require(font_id)
        return self.current_masters.get(font_id, self.fonts[font_id].masters[0].id)

    def set_current_master(self, font_id: str, master_id: str) -> None:
        self._require(font_id)
        if master_id not in {m.id for m in self.fonts[font_id].masters}:
            raise ValueError(master_id)
        self.current_masters[font_id] = master_id

    def glyph_note(self, glyph_id: str) -> str:
        self._require(glyph_id)
        return self.notes.get(glyph_id, "")

    def glyph_last_change(self, glyph_id: str) -> str | None:
        self._require(glyph_id)
        return self.last_changes.get(glyph_id)

    def layer_vertical_width(self, layer_id: str) -> float | None:
        self._require(layer_id)
        return self.vertical_widths.get(layer_id)

    def set_master_italic_angle(self, master_id, value):
        self.metrics[master_id] = replace(
            self.master_metrics(master_id), italicAngle=value
        )

    def set_glyph_unicodes(self, glyph_id, values):
        self._require(glyph_id)
        for font_id, glyphs in self.glyph_lists.items():
            self.glyph_lists[font_id] = tuple(
                replace(g, unicodes=tuple(values)) if g.id == glyph_id else g
                for g in glyphs
            )

    def master_metrics(self, master_id: str) -> MasterMetrics:
        self.metric_reads.append(master_id)
        return self.metrics.get(master_id, MasterMetrics(800, 700, -200, 500, 0))

    def node_selected(self, node_id):
        self._require(node_id)
        return self._member_infos[node_id].selected

    def remove_glyph(self, font_id, glyph_id):
        self._require(glyph_id)
        self.glyph_lists[font_id] = tuple(
            g for g in self.glyph_lists[font_id] if g.id != glyph_id
        )
        for key in list(self.layers):
            if key[0] == glyph_id:
                del self.layers[key]
        for key in tuple(self._pending_backgrounds):
            if key[0] == glyph_id:
                del self._pending_backgrounds[key]

    def rename_glyph(self, font_id, glyph_id, name):
        self._require(glyph_id)
        current = next(g for g in self.glyph_lists[font_id] if g.id == glyph_id)
        if current.name == name:
            return
        if not name or any(
            g.name == name and g.id != glyph_id for g in self.glyph_lists[font_id]
        ):
            raise ValueError("Duplicate or empty glyph name")
        self.glyph_lists[font_id] = tuple(
            replace(g, name=name) if g.id == glyph_id else g
            for g in self.glyph_lists[font_id]
        )

    def set_node_selected(self, node_id: str, selected: bool) -> None:
        self._require(node_id)
        for key, layer in self.layers.items():
            paths = tuple(
                replace(
                    p,
                    nodes=tuple(
                        replace(n, selected=selected) if n.id == node_id else n
                        for n in p.nodes
                    ),
                )
                for p in layer.paths
            )
            self.layers[key] = replace(layer, paths=paths)

    def append_path(self, layer_id: str, path: PathInfo) -> str:
        key = self._layer_key(layer_id)
        path = replace(
            path,
            id=self._id(),
            nodes=tuple(replace(n, id=self._id()) for n in path.nodes),
        )
        layer = self.layers[key]
        self.layers[key] = replace(
            layer, paths=(*layer.paths, path), shape_ids=(*layer.shape_ids, path.id)
        )
        return path.id

    def insert_path(self, layer_id: str, index: int, path: PathInfo) -> str:
        key = self._layer_key(layer_id)
        path = replace(
            path,
            id=self._id(),
            nodes=tuple(replace(n, id=self._id()) for n in path.nodes),
        )
        layer = self.layers[key]
        order = list(layer.shape_ids)
        index = min(max(index, 0), len(order))
        path_ids = {p.id for p in layer.paths}
        position = sum(1 for i in order[:index] if i in path_ids)
        paths = list(layer.paths)
        paths.insert(position, path)
        order.insert(index, path.id)
        self.layers[key] = replace(layer, paths=tuple(paths), shape_ids=tuple(order))
        return path.id

    def append_glyph(
        self, font_id: str, name: str, *, unicodes: tuple[str, ...] = ()
    ) -> str:
        self._require(font_id)
        if any(g.name == name for g in self.glyph_lists[font_id]):
            raise ValueError(f"Duplicate glyph name {name!r}")
        id = self._id()
        self.glyph_lists[font_id] = (
            *self.glyph_lists[font_id],
            GlyphInfo(id, name, unicodes),
        )
        for master in self.fonts[font_id].masters:
            self.layers[id, master.id] = LayerInfo(self._id(), master.id, 0)
        return id

    def append_component(self, layer_id: str, component: ComponentInfo) -> str:
        key = self._layer_key(layer_id)
        names = {g.name for glyphs in self.glyph_lists.values() for g in glyphs}
        if component.componentName not in names:
            raise ValueError(f"No glyph named {component.componentName!r}")
        component = replace(component, id=self._id())
        layer = self.layers[key]
        self.layers[key] = replace(
            layer,
            components=(*layer.components, component),
            shape_ids=(*layer.shape_ids, component.id),
        )
        return component.id

    def remove_path(self, layer_id: str, path_id: str) -> None:
        key = self._layer_key(layer_id)
        layer = self.layers[key]
        if path_id not in {p.id for p in layer.paths}:
            raise ValueError("Path does not belong to layer")
        self.layers[key] = replace(
            layer,
            paths=tuple(p for p in layer.paths if p.id != path_id),
            shape_ids=tuple(i for i in layer.shape_ids if i != path_id),
        )

    def add_anchor(self, layer_id: str, anchor: AnchorInfo) -> str:
        key = self._layer_key(layer_id)
        layer = self.layers[key]
        if any(a.name == anchor.name for a in layer.anchors):
            raise ValueError("Duplicate anchor name")
        anchor = replace(anchor, id=self._id())
        self.layers[key] = replace(layer, anchors=(*layer.anchors, anchor))
        return anchor.id

    def mark(self, id: str) -> int:
        self._require(id)
        return self.marks.get(id, 0)

    def set_mark(self, id: str, hue: int) -> None:
        self._require(id)
        self.marks[id] = hue

    def glyph_tags(self, glyph_id: str) -> tuple[str, ...]:
        self._require(glyph_id)
        return self.tags.get(glyph_id, ())

    def set_glyph_tags(self, glyph_id: str, tags: tuple[str, ...]) -> None:
        self._require(glyph_id)
        self.tags[glyph_id] = tuple(tags)

    def remove_anchor(self, layer_id: str, anchor_id: str) -> None:
        key = self._layer_key(layer_id)
        layer = self.layers[key]
        if anchor_id not in {a.id for a in layer.anchors}:
            raise ValueError("Anchor does not belong to layer")
        self.layers[key] = replace(
            layer, anchors=tuple(a for a in layer.anchors if a.id != anchor_id)
        )

    def insert_path_node(
        self,
        path_id: str,
        index: int,
        node: NodeInfo,
        *,
        on_attach: Callable[[str], None] | None = None,
    ) -> str:
        from .node_insert import insertion_index, insertion_node

        self._require(path_id)
        node = replace(insertion_node(node), id=self._id())
        key = self._member_layers[path_id]
        layer = self.layers[key]
        path = next(p for p in layer.paths if p.id == path_id)
        index = insertion_index(index, len(path.nodes))
        nodes = path.nodes[:index] + (node,) + path.nodes[index:]
        self.layers[key] = replace(
            layer,
            paths=tuple(
                replace(p, nodes=nodes) if p.id == path_id else p for p in layer.paths
            ),
        )
        if on_attach is not None:
            on_attach(node.id)
        return node.id

    def set_path_nodes(self, path_id: str, nodes, closed: bool) -> None:
        self._require(path_id)
        fresh = tuple(replace(n, id=self._id()) for n in nodes)
        for key, layer in self.layers.items():
            paths = tuple(
                replace(p, nodes=fresh, closed=closed) if p.id == path_id else p
                for p in layer.paths
            )
            self.layers[key] = replace(layer, paths=paths)

    def lib(self, id: str) -> dict:
        self._require(id)
        return deepcopy(self.libs.get(id, {}))

    def set_lib(self, id: str, data: dict) -> None:
        self._require(id)
        self.libs[id] = deepcopy(data)

    def features(self, font_id: str) -> FeaturesInfo:
        self._require(font_id)
        prefix, features = self.feature_data.get(font_id, ("", ()))
        return FeaturesInfo(prefix, tuple(FeatureInfo(*f) for f in features))

    def set_feature(self, font_id: str, name: str, code: str | None) -> None:
        self._require(font_id)
        prefix, features = self.feature_data.get(font_id, ("", ()))
        features = dict(features)
        if code is None:
            features.pop(name, None)
        else:
            features[name] = code
        self.feature_data[font_id] = (prefix, tuple(features.items()))

    def set_feature_prefix(self, font_id: str, code: str) -> None:
        self._require(font_id)
        _, features = self.feature_data.get(font_id, ("", ()))
        self.feature_data[font_id] = (code, features)

    def classes(self, font_id: str) -> tuple[ClassInfo, ...]:
        self._require(font_id)
        return self.class_data.get(font_id, ())

    def set_class(self, font_id, name, glyphs) -> None:
        self._require(font_id)
        classes = {c.name: c for c in self.class_data.get(font_id, ())}
        if glyphs is None:
            classes.pop(name, None)
        else:
            classes[name] = ClassInfo(name, tuple(glyphs))
        self.class_data[font_id] = tuple(classes.values())

    def rename_class(self, font_id, name, new_name) -> None:
        self._require(font_id)
        self.class_data[font_id] = tuple(
            ClassInfo(new_name, c.glyphs) if c.name == name else c
            for c in self.class_data.get(font_id, ())
        )

    def instances(self, font_id: str) -> tuple[InstanceInfo, ...]:
        self._require(font_id)
        return self.instance_data.get(font_id, ())

    def _replace_axes(self, font_id, axes, masters):
        self.fonts[font_id] = replace(
            self.fonts[font_id], axes=tuple(axes), masters=tuple(masters)
        )

    def add_axis(self, font_id, axis) -> str:
        info = self.font_info(font_id)
        axis = replace(axis, id=axis.tag)
        masters = [replace(m, axes=(*m.axes, 0.0)) for m in info.masters]
        self._replace_axes(font_id, (*info.axes, axis), masters)
        return axis.id

    def remove_axis(self, font_id, index) -> None:
        info = self.font_info(font_id)
        axes = [a for i, a in enumerate(info.axes) if i != index]
        masters = [
            replace(m, axes=tuple(v for i, v in enumerate(m.axes) if i != index))
            for m in info.masters
        ]
        self._replace_axes(font_id, axes, masters)

    def set_axis(self, font_id, index, axis) -> None:
        info = self.font_info(font_id)
        axes = list(info.axes)
        axes[index] = axis
        self._replace_axes(font_id, axes, info.masters)

    def set_master_axes(self, master_id, axes) -> None:
        self._require(master_id)
        for font_id, info in self.fonts.items():
            masters = [
                replace(m, axes=tuple(axes)) if m.id == master_id else m
                for m in info.masters
            ]
            self._replace_axes(font_id, info.axes, masters)

    def add_instance(self, font_id, instance) -> None:
        instances = self.instances(font_id)
        self.instance_data[font_id] = (*instances, replace(instance, id=self._id()))

    def set_instance(self, font_id, index, changes) -> None:
        instances = list(self.instances(font_id))
        instances[index] = replace(instances[index], **changes)
        self.instance_data[font_id] = tuple(instances)

    def remove_instance(self, font_id, index) -> None:
        instances = list(self.instances(font_id))
        del instances[index]
        self.instance_data[font_id] = tuple(instances)

    def kerning(self, font_id: str, master_id: str) -> tuple[KerningPair, ...]:
        self._require(master_id)
        pairs = self.kerning_data.get((font_id, master_id), {})
        return tuple(KerningPair(left, right, value) for (left, right), value in pairs.items())

    def set_kerning(self, font_id, master_id, left, right, value) -> None:
        self._require(master_id)
        pairs = self.kerning_data.setdefault((font_id, master_id), {})
        if value is None:
            pairs.pop((left, right), None)
        else:
            pairs[left, right] = value

    def kerning_classes(
        self, font_id: str, master_id: str | None = None
    ) -> tuple[KerningClassInfo, ...]:
        self._require(font_id)
        master_id = self.current_master(font_id) if master_id is None else master_id
        self._require(master_id)
        return self.kerning_class_data.get(
            (font_id, master_id), self.kerning_class_data.get(font_id, ())
        )

    def set_kerning_group(
        self, font_id: str, glyph_id: str, side: str, value: str | None
    ) -> None:
        from .kerning import available_group_name, group_name, membership_plan

        self._require(glyph_id)
        value = group_name(value)
        available_group_name(self, font_id, value)
        glyph = next((g for g in self.glyphs(font_id) if g.id == glyph_id), None)
        if glyph is None:
            raise ValueError("Glyph does not belong to this font")
        plans = {
            m.id: membership_plan(
                self.kerning_classes(font_id, m.id),
                self.kerning(font_id, m.id),
                glyph.name,
                side,
                value,
            )
            for m in self.font_info(font_id).masters
        }
        for master, groups in plans.items():
            if groups != self.kerning_classes(font_id, master):
                self.kerning_class_data[font_id, master] = groups

    def replace_kerning(
        self, font_id: str, master_id: str, pairs: tuple[KerningPair, ...]
    ) -> None:
        from .kerning import references

        self._require(master_id)
        if master_id not in {m.id for m in self.font_info(font_id).masters}:
            raise ValueError("Master does not belong to this font")
        wanted = {(p.left, p.right): p.value for p in pairs}
        if wanted != self.kerning_data.get((font_id, master_id), {}):
            self.kerning_data[font_id, master_id] = wanted
        groups = self.kerning_classes(font_id, master_id)
        kept = tuple(g for g in groups if g.glyphs or references(pairs, g.name))
        if kept != groups:
            self.kerning_class_data[font_id, master_id] = kept

    def append_guide(self, layer_id: str, guide: GuideInfo) -> str:
        key = self._layer_key(layer_id)
        guide = replace(guide, id=self._id())
        layer = self.layers[key]
        self.layers[key] = replace(layer, guides=(*layer.guides, guide))
        return guide.id

    def hints(self, layer_id: str) -> tuple[HintInfo, ...]:
        self._require(layer_id)
        return self.hint_data.get(layer_id, ())

    def add_hint(self, layer_id: str, hint) -> None:
        self._require(layer_id)
        self.hint_data[layer_id] = (*self.hint_data.get(layer_id, ()), hint)

    def set_hint(self, layer_id: str, index: int, changes) -> None:
        hints = list(self.hints(layer_id))
        hints[index] = replace(hints[index], **changes)
        self.hint_data[layer_id] = tuple(hints)

    def remove_hint(self, layer_id: str, index: int) -> None:
        hints = list(self.hints(layer_id))
        del hints[index]
        self.hint_data[layer_id] = tuple(hints)

    def edit_view(self, font_id: str) -> EditViewInfo | None:
        self._require(font_id)
        return self.edit_views.get(font_id)

    def open_edit_view(self, font_id: str) -> None:
        master = self.fonts[font_id].masters[0].name
        self.edit_views.setdefault(font_id, EditViewInfo((), None, master, "fake-tab"))

    def redraw_edit_view(self, font_id):
        self._require(font_id)

    def set_edit_cursor(self, font_id: str, index: int) -> None:
        self._require(font_id)
        self.edit_views[font_id] = replace(self.edit_views[font_id], cursor=index)

    def set_edit_glyphs(self, font_id: str, lines) -> None:
        self._require(font_id)
        self.edit_texts.append((font_id, lines))

    def current_layers(self, font_id: str) -> tuple[tuple[str, str], ...]:
        self._require(font_id)
        if font_id in self._font_selections and font_id not in self.edit_views:
            master = self.current_master(font_id)
            name = next(m.name for m in self.fonts[font_id].masters if m.id == master)
            glyphs = {g.id: g.name for g in self.glyph_lists[font_id]}
            return tuple(
                (glyphs[gid], name)
                for gid in self._font_selections[font_id]
                if gid in glyphs
            )
        return self.current_layer_data.get(font_id, ())

    def set_font_selection(self, font_id, glyph_ids):
        self._require(font_id)
        available = {g.id: g for g in self.glyph_lists[font_id]}
        if any(gid not in available for gid in glyph_ids):
            raise ValueError("Selected glyph belongs to a different font")
        self._selected_glyphs.difference_update(available)
        self._selected_glyphs.update(glyph_ids)
        self._font_selections[font_id] = tuple(glyph_ids)
        master = self.current_master(font_id)
        name = next(m.name for m in self.fonts[font_id].masters if m.id == master)
        self.current_layer_data[font_id] = tuple(
            (available[gid].name, name) for gid in glyph_ids
        )

    def begin_undo(self, name: str) -> None:
        if self._undo:
            raise RuntimeError("Undo group already active")
        self._undo = True
        self.undo_events.append(("begin", name))

    def end_undo(self) -> None:
        if not self._undo:
            raise RuntimeError("No undo group active")
        self._undo = False
        self.undo_events.append(("end", None))

    def can_publish_undo(self, font_id: str) -> bool:
        return self.is_valid(font_id)

    def discard_undo(self) -> None:
        self._undo = False
        self.undo_events.append(("discard", None))

    def close_font(self, font_id, *, ignore_changes=True):
        """Close the fake document and invalidate all descendant handles."""
        self._require(font_id)
        if not ignore_changes and self._saved_revisions.get(font_id) != self._generation:
            raise UnsupportedCapability(
                "Save the font first or pass ignoreChanges=True explicitly to discard edits",
                capability="GSFont.close.unsavedChanges")
        del self.fonts[font_id]
        if self.current == font_id:
            self.current = next(iter(self.fonts), None)
