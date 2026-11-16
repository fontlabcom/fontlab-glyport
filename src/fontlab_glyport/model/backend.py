# this_file: src/fontlab_glyport/model/backend.py
"""Host boundary: immutable snapshots, opaque lifetime IDs, explicit mutations.

IDs must never be recycled during a backend lifetime. Child IDs become invalid
when removed or when their document closes. Sequence order is native order.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

NodeType = Literal["line", "curve", "offcurve", "qcurve"]
Transform = tuple[float, float, float, float, float, float]


@dataclass(frozen=True)
class AxisInfo:
    id: str
    name: str
    tag: str
    hidden: bool = False


@dataclass(frozen=True)
class MasterInfo:
    id: str
    name: str
    # One coordinate per font axis, in font axis order.
    axes: tuple[float, ...] = ()


@dataclass(frozen=True)
class MasterMetrics:
    """A master's vertical metrics and italic angle (read on access)."""

    ascender: float
    capHeight: float
    descender: float
    xHeight: float
    italicAngle: float

    def __iter__(self):
        return iter(
            (
                self.ascender,
                self.capHeight,
                self.descender,
                self.xHeight,
                self.italicAngle,
            )
        )


@dataclass(frozen=True)
class FontInfo:
    id: str
    familyName: str
    unitsPerEm: int
    masters: tuple[MasterInfo, ...]
    axes: tuple[AxisInfo, ...] = ()


@dataclass(frozen=True)
class InstanceInfo:
    id: str
    name: str
    axes: tuple[float, ...] = ()
    exports: bool = True
    weight: str = "Regular"
    weightValue: float = 100.0
    width: str = "Normal"


@dataclass(frozen=True)
class KerningPair:
    """Glyph names, or Glyphs group keys ``@MMK_L_<group>``/``@MMK_R_<group>``."""

    left: str
    right: str
    value: float


@dataclass(frozen=True)
class EditViewInfo:
    """FontLab's active glyph tab of a font: glyph names per text line."""

    lines: tuple[tuple[str, ...], ...]
    active: str | None = None
    master: str = ""
    # Native text block id: a tab proxy addresses only the tab it was made for.
    id: str = ""
    # Index of the active glyph in the tab's text, one slot per glyph and per
    # line break (Glyphs' textCursor); None when no glyph is active.
    cursor: int | None = None


@dataclass(frozen=True)
class KerningClassInfo:
    """A FontLab kerning class; left = used on the pair's left side (VFJ "1st")."""

    name: str
    glyphs: tuple[str, ...]
    left: bool = False
    right: bool = False


@dataclass(frozen=True)
class GuideInfo:
    id: str
    x: float
    y: float
    angle: float = 0.0
    name: str = ""
    selected: bool = False


@dataclass(frozen=True)
class HintInfo:
    """A PostScript hint record; ghost widths are -20 (top) and 21 (bottom)."""

    horizontal: bool
    position: float
    width: float
    name: str = ""
    ghost: bool = False


@dataclass(frozen=True)
class GlyphInfo:
    id: str
    name: str
    unicodes: tuple[str, ...]


@dataclass(frozen=True)
class NodeInfo:
    id: str
    x: float
    y: float
    type: NodeType = "line"
    smooth: bool = False
    selected: bool = False
    connection: int | None = None
    name: str | None = None

    def __post_init__(self):
        if self.type not in {"line", "curve", "offcurve", "qcurve"}:
            raise ValueError(f"Invalid node type: {self.type}")


@dataclass(frozen=True)
class PathInfo:
    id: str
    nodes: tuple[NodeInfo, ...]
    closed: bool = True
    attributes: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ComponentInfo:
    id: str
    componentName: str
    transform: Transform
    selected: bool = False

    def __post_init__(self):
        if len(self.transform) != 6:
            raise ValueError("A component transform requires six values")


@dataclass(frozen=True)
class AnchorInfo:
    id: str
    name: str
    x: float
    y: float
    selected: bool = False


@dataclass(frozen=True)
class LayerIdentity:
    """Foreground catalog entry; ordinary layer IDs differ from master IDs."""

    id: str
    masterId: str
    name: str | None


@dataclass(frozen=True)
class LayerInfo:
    id: str
    masterId: str
    width: float
    paths: tuple[PathInfo, ...] = ()
    components: tuple[ComponentInfo, ...] = ()
    anchors: tuple[AnchorInfo, ...] = ()
    # Interleaved path/component IDs, preserving Glyphs 3 shape order.
    shape_ids: tuple[str, ...] = ()
    guides: tuple[GuideInfo, ...] = ()
    layerId: str = ""
    name: str | None = ""


@dataclass(frozen=True)
class FeatureInfo:
    name: str
    code: str


@dataclass(frozen=True)
class ClassInfo:
    """An OpenType glyph class (VFJ font "classes")."""

    name: str
    glyphs: tuple[str, ...]


@dataclass(frozen=True)
class FeaturesInfo:
    """OpenType feature code; FontLab keeps one common prefix per font."""

    prefix: str = ""
    features: tuple[FeatureInfo, ...] = ()


@runtime_checkable
class ModelBackend(Protocol):
    """All data/mutation is explicit; no native objects cross this boundary."""

    supports_anchor_selection: bool
    supports_component_selection: bool
    supports_guide_selection: bool

    def revision(self, font_id: str) -> object: ...
    def validate_collection(self, layer_id: str, field: str, infos: tuple) -> None: ...
    def prepare_collection(self, layer_id: str, field: str, *, state=None) -> None: ...

    def snapshot_collection(self, layer_id: str, *, stage=False) -> object: ...
    def restore_collection(self, layer_id: str, state: object) -> None: ...

    def dark_mode(self) -> bool: ...
    def list_fonts(self) -> tuple[str, ...]: ...
    def current_font_id(self) -> str | None: ...
    def font_info(self, font_id: str) -> FontInfo: ...
    def set_font_info(self, font_id: str, **changes) -> None: ...
    def set_master_info(self, master_id: str, **changes) -> None: ...
    def font_path(self, font_id: str) -> str | None: ...
    def save_font(
        self, font_id: str, path: str | None = None, *, make_copy=False
    ) -> None: ...
    def close_font(self, font_id: str, *, ignore_changes=False) -> None: ...
    def outline_layer(self, layer_id: str) -> LayerInfo: ...
    def validate_component_expansion(
        self, layer_id: str, components: tuple[ComponentInfo, ...]
    ) -> None: ...
    def remove_layer_overlap(
        self, layer_id: str, *, check_selection=False, undo_group=...
    ) -> None: ...
    def decompose_layer_components(self, layer_id: str) -> None: ...
    def correct_layer_direction(self, layer_id: str) -> None: ...
    def add_layer_extrema(
        self, layer_id: str, *, force=False, check_selection=False, undo_group=...
    ) -> None: ...
    def draw_layer(
        self, layer_id: str, pen, *, points=False, contours=True, components=True
    ) -> None: ...
    def glyphs(self, font_id: str) -> tuple[GlyphInfo, ...]: ...
    def layer(self, glyph_id: str, master_id: str) -> LayerInfo: ...
    def glyph_layers(self, glyph_id: str) -> tuple[LayerIdentity, ...]: ...
    def background_layer(self, layer_id: str) -> LayerInfo: ...
    def clear_background_layer(self, layer_id: str) -> None: ...
    def layer_metrics_key(self, layer_id: str, side: str) -> str | None: ...
    def set_layer_metrics_key(
        self, layer_id: str, side: str, value: str | None
    ) -> None: ...
    def anchor_selected(self, anchor_id: str) -> bool: ...
    def set_anchor_selected(self, anchor_id: str, value: bool) -> None: ...
    def set_anchor_name(self, anchor_id: str, name: str) -> None: ...
    def component_selected(self, component_id: str) -> bool: ...
    def set_component_selected(self, component_id: str, value: bool) -> None: ...
    def guide_selected(self, guide_id: str) -> bool: ...
    def set_guide_selected(self, guide_id: str, value: bool) -> None: ...
    def set_component_transform(self, component_id: str, transform: Transform) -> None: ...
    def set_component_name(self, component_id: str, name: str) -> None: ...
    def decompose_component(
        self, layer_id: str, component_id: str, *, on_detach: Callable[[], None]
    ) -> None: ...
    def remove_component(self, layer_id: str, component_id: str) -> None: ...
    def set_guide(self, guide_id: str, **changes) -> None: ...
    def remove_guide(self, layer_id: str, guide_id: str) -> None: ...
    def set_layer_width(self, layer_id: str, width: float) -> None: ...
    def node_name(self, node_id: str) -> str | None: ...
    def set_node_name(self, node_id: str, name: str) -> None: ...
    def set_node_type(self, node_id: str, kind: NodeType) -> None: ...
    def set_node_position(self, node_id: str, x: float, y: float) -> None: ...

    def set_node_smooth(self, node_id: str, smooth: bool) -> None: ...
    def set_node_connection(self, node_id: str, connection: int) -> None: ...
    # Selection is UI state: no undo step and no change notification.
    def node_selected(self, node_id: str) -> bool: ...
    def append_master_guide(self, master_id: str, guide: GuideInfo) -> str: ...

    def update_layer_metrics(self, layer_id: str) -> None: ...

    def master_guides(self, master_id: str) -> tuple[GuideInfo, ...]: ...
    def master_zones(self, master_id: str) -> tuple[tuple[float, float], ...]: ...
    def set_master_zone(
        self, master_id: str, index: int, position: float, size: float
    ) -> None: ...
    def glyph_selected(self, font_id: str, glyph_id: str) -> bool: ...
    def set_glyph_selected(self, font_id: str, glyph_id: str, value: bool) -> None: ...
    def path_attributes(self, path_id: str) -> dict: ...
    def set_path_attributes(self, path_id: str, values: dict) -> None: ...
    def remove_glyph(self, font_id: str, glyph_id: str) -> None: ...
    def rename_glyph(self, font_id: str, glyph_id: str, name: str) -> None: ...
    def set_node_selected(self, node_id: str, selected: bool) -> None: ...
    # Layer outline bounds (x, y, width, height), or None for an empty layer.
    def layer_bounds(
        self, layer_id: str
    ) -> tuple[float, float, float, float] | None: ...
    def component_bounds(
        self, component_id: str
    ) -> tuple[float, float, float, float] | None: ...
    def set_component_position(self, component_id: str, x: float, y: float) -> None: ...
    def transform_layer(self, layer_id: str, matrix: Transform) -> None: ...
    def set_anchor_position(self, anchor_id: str, x: float, y: float) -> None: ...
    def current_master(self, font_id: str) -> str | None: ...
    def set_current_master(self, font_id: str, master_id: str) -> None: ...
    def set_master_italic_angle(self, master_id: str, value: float) -> None: ...
    def set_glyph_unicodes(self, glyph_id: str, values: tuple[str, ...]) -> None: ...
    def master_metrics(self, master_id: str) -> MasterMetrics: ...
    def glyph_note(self, glyph_id: str) -> str: ...
    def make_node_first(self, node_id: str) -> None: ...
    def glyph_last_change(self, glyph_id: str) -> str | None: ...
    def layer_vertical_width(self, layer_id: str) -> float | None: ...
    def append_path(self, layer_id: str, path: PathInfo) -> str: ...
    # Insert a path at an index of the layer's shape order (shape_ids).
    def insert_path(self, layer_id: str, index: int, path: PathInfo) -> str: ...
    def remove_path(self, layer_id: str, path_id: str) -> None: ...
    def add_anchor(self, layer_id: str, anchor: AnchorInfo) -> str: ...
    # A new glyph with an empty layer per master (layers are created on write).
    def append_glyph(
        self, font_id: str, name: str, *, unicodes: tuple[str, ...] = ()
    ) -> str: ...
    # A component of an existing glyph appended to the layer's shapes.
    def append_component(self, layer_id: str, component: ComponentInfo) -> str: ...
    def remove_anchor(self, layer_id: str, anchor_id: str) -> None: ...
    # FontLab mark of a glyph or layer: a hue, 0 = no mark.
    def mark(self, id: str) -> int: ...
    def set_mark(self, id: str, hue: int) -> None: ...
    # Glyph tags (FontLab flGlyph.tags), in their stored order.
    def glyph_tags(self, glyph_id: str) -> tuple[str, ...]: ...
    def set_glyph_tags(self, glyph_id: str, tags: tuple[str, ...]) -> None: ...
    # Insert preserves existing node tokens; on_attach runs before publication.
    def insert_path_node(
        self,
        path_id: str,
        index: int,
        node: NodeInfo,
        *,
        on_attach: Callable[[str], None] | None = None,
    ) -> str: ...

    # Replace nodes in place; old node tokens become invalid.
    def set_path_nodes(
        self, path_id: str, nodes: tuple[NodeInfo, ...], closed: bool
    ) -> None: ...
    def begin_undo(self, name: str) -> None: ...
    def end_undo(self) -> None: ...
    def can_publish_undo(self, font_id: str) -> bool: ...
    def discard_undo(self) -> None: ...
    def is_valid(self, id: str) -> bool: ...
    # Native libs of a font, glyph or layer as plain dict/list/scalar copies.
    def lib(self, id: str) -> dict: ...
    def set_lib(self, id: str, data: dict) -> None: ...
    def features(self, font_id: str) -> FeaturesInfo: ...
    # FontLab feature text ("feature tag { ... } tag;"); None removes the feature.
    def set_feature(self, font_id: str, name: str, code: str | None) -> None: ...
    def set_feature_prefix(self, font_id: str, code: str) -> None: ...
    def classes(self, font_id: str) -> tuple[ClassInfo, ...]: ...
    # OpenType class members by glyph name; None removes the class.
    def set_class(
        self, font_id: str, name: str, glyphs: tuple[str, ...] | None
    ) -> None: ...
    def rename_class(self, font_id: str, name: str, new_name: str) -> None: ...
    def instances(self, font_id: str) -> tuple[InstanceInfo, ...]: ...
    # Axes: add returns the new axis id; masters get FontLab's default coordinate.
    def add_axis(self, font_id: str, axis: AxisInfo) -> str: ...
    # Axes by native index; set_axis writes name, tag and hidden from ``axis``.
    def remove_axis(self, font_id: str, index: int) -> None: ...
    def set_axis(self, font_id: str, index: int, axis: AxisInfo) -> None: ...
    # One coordinate per font axis, in font axis order.
    def set_master_axes(self, master_id: str, axes: tuple[float, ...]) -> None: ...
    # Instances by native index; set_instance changes only the given fields
    # ("name", "exports", "axes") and keeps all other native data.
    def add_instance(self, font_id: str, instance: InstanceInfo) -> None: ...
    def set_instance(self, font_id: str, index: int, changes: dict) -> None: ...
    def remove_instance(self, font_id: str, index: int) -> None: ...
    def kerning(self, font_id: str, master_id: str) -> tuple[KerningPair, ...]: ...
    # value None removes the pair.
    def set_kerning(
        self, font_id: str, master_id: str, left: str, right: str, value: float | None
    ) -> None: ...
    def kerning_classes(
        self, font_id: str, master_id: str | None = None
    ) -> tuple[KerningClassInfo, ...]: ...
    def set_kerning_group(
        self, font_id: str, glyph_id: str, side: str, value: str | None
    ) -> None: ...
    def replace_kerning(
        self, font_id: str, master_id: str, pairs: tuple[KerningPair, ...]
    ) -> None: ...
    def append_guide(self, layer_id: str, guide: GuideInfo) -> str: ...
    def hints(self, layer_id: str) -> tuple[HintInfo, ...]: ...
    # Hint edits by native index (FontLab's edit_layer_hints order).
    def add_hint(self, layer_id: str, hint: HintInfo) -> None: ...
    # Only the given fields ("horizontal", "position", "width", "name").
    def set_hint(self, layer_id: str, index: int, changes: dict) -> None: ...
    def remove_hint(self, layer_id: str, index: int) -> None: ...
    # The font's active glyph tab, or None; opening and text go through FontLab UI.
    def edit_view(self, font_id: str) -> EditViewInfo | None: ...
    def open_edit_view(self, font_id: str) -> None: ...
    # Make the glyph at this text index (glyph and line-break slots) active.
    def redraw_edit_view(self, font_id: str) -> None: ...

    def set_edit_cursor(self, font_id: str, index: int) -> None: ...
    def set_edit_glyphs(
        self, font_id: str, lines: tuple[tuple[str, ...], ...]
    ) -> None: ...
    # FontLab's current glyphs of this font as (glyph name, layer name).
    def current_layers(self, font_id: str) -> tuple[tuple[str, str], ...]: ...

    def set_font_selection(self, font_id: str, glyph_ids: tuple[str, ...]) -> None: ...
