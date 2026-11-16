# this_file: src/fontlab_glyport/model/fontlab_backend.py
"""FontLab 9 adapter based on echopy stubs; native verification is outstanding.

Imports are deferred until a backend operation. Reads are limited to the requested
package metadata, glyph metadata list, or single layer. Cached native handles use
isValid and parent lifetimes; snapshots are rebuilt within each public read call.
"""

import re
import weakref
from collections import deque
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, replace
from itertools import count

from .._strict import caller_location
from ..errors import (
    HostUnavailable,
    NativeOperationError,
    PartialFailure,
    StaleNativeObject,
    UnsupportedCapability,
)
from .backend import (
    AnchorInfo,
    AxisInfo,
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

# Native node flags are interpreted, never guessed numeric enum values.
NODE_TYPE_MAPPING = {
    "off": "offcurve",
    "on_line": "line",
    "on_cubic": "curve",
    "on_quadratic": "qcurve",
}


def _control(node) -> bool:
    """Native fact (glyport-matrix probe_nodes): a quadratic off-curve point
    has type "off" (``isOff()``), a cubic control point type "curve"
    (``isCurve()``); on-curve points are "on"."""
    return node.isOff() or node.isCurve()


def node_type(node, quadratic, previous=None):
    """Glyphs' type of a native node. Control points are "offcurve"; an
    on-curve point ends a curve when the point before it (``previous``) is a
    control point: "qcurve" after a quadratic one, "curve" after a cubic one."""
    if _control(node):
        return NODE_TYPE_MAPPING["off"]
    if previous is not None and _control(previous):
        cubic = previous.isCurve() and not quadratic
        return NODE_TYPE_MAPPING["on_cubic" if cubic else "on_quadratic"]
    return NODE_TYPE_MAPPING["on_line"]


def glyphs_order(items: list, closed: bool) -> list:
    """FontLab lists a closed contour from its start node; Glyphs lists the
    start node last."""
    return items[1:] + items[:1] if closed and items else items


def fontlab_order(items: list, closed: bool) -> list:
    return items[-1:] + items[:-1] if closed and items else items


def _import_qtgui():
    try:
        from PythonQt import QtGui
    except ImportError as error:
        raise HostUnavailable("PythonQt.QtGui is unavailable") from error
    return QtGui


def _glyphs_key(key, side):
    """FontLab "@T" on the left is Glyphs "@MMK_L_T"; glyph names pass through."""
    if key.startswith(FONTLAB_GROUP):
        return GLYPHS_GROUPS[side] + key[len(FONTLAB_GROUP) :]
    return key


def _fontlab_key(key, side):
    prefix = GLYPHS_GROUPS[side]
    return FONTLAB_GROUP + key[len(prefix) :] if key.startswith(prefix) else key


def _plain(value, _active=None):
    """Materialize lib values; native handles must never cross a font boundary."""
    if value is None:
        return None
    for kind in (bool, str, bytes, int, float):
        if isinstance(value, kind):
            return kind(value)
    active = set() if _active is None else _active
    if id(value) in active:
        raise UnsupportedCapability("Cyclic lib value", capability="lib.value")
    active.add(id(value))
    try:
        if hasattr(value, "items"):
            result = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise UnsupportedCapability(
                        "Lib keys must be strings", capability="lib.value"
                    )
                result[str(key)] = _plain(item, active)
            return result
        if isinstance(value, (list, tuple)):
            return [_plain(item, active) for item in value]
        raise UnsupportedCapability(
            f"Unsupported lib value type: {type(value).__name__}",
            capability="lib.value",
        )
    finally:
        active.remove(id(value))


# Native fact (R023, evidence glyport-model/probe_undo_forms.json): one Edit > Undo
# step needs the changed layers followed by their glyph in one notifyChangesApplied
# list. A layer alone only advances the layer history, so Undo skips that edit; a
# single object (not a list) adds no step at all.
_LOCATION_REPR = re.compile(r"<flLocation ?(.*)>", re.DOTALL)
_LOCATION_ENTRY = re.compile(r"([^=,<>\s]+)=(\([^)]*\)|[^,>]*)")


def _location_keys(location):
    """The keys of a native flLocation as its repr lists them (lowercased), or
    None when the repr does not account for every entry."""
    match = _LOCATION_REPR.fullmatch(repr(location))
    if match is None:
        return None
    keys = [key for key, _ in _LOCATION_ENTRY.findall(match.group(1))]
    return keys if len(keys) == len(location) else None


def _location_spellings(location, keys):
    """Exact stored key -> value for repr keys, or None when not recoverable.

    Native fact (glyport-r020/probe-location-keys-run1): lookups are
    case-sensitive while repr lowercases keys, and flLocation has no other way
    to list its keys. Each lowercased repr key stands for one stored key; the
    usual spellings (as listed, upper, capitalized, title) are tried. A group
    of n equal lowercased keys must resolve to exactly n distinct spellings,
    otherwise the stored keys are ambiguous or unusual and None is returned.
    """
    groups = {}
    for key in keys:
        groups[key] = groups.get(key, 0) + 1
    found = {}
    for key, size in groups.items():
        spellings = dict.fromkeys((key, key.upper(), key.capitalize(), key.title()))
        hits = {k: location[k] for k in spellings if location[k] is not None}
        if len(hits) != size:
            return None
        found.update(hits)
    return found


NOTIFY_ORDER = {"layer": 0, "glyph": 1}

# FontLab short names of registered axes (FontLab's own: "wt", "wd"); others use the tag.
AXIS_SHORT_NAMES = {
    "wght": "wt",
    "wdth": "wd",
    "ital": "it",
    "slnt": "sl",
    "opsz": "op",
}

# In-process MCP tools (`fontpr`) page kerning pairs; FontLab names classes "@name".
KERNING_PAGE = 200
FONTLAB_GROUP = "@"
GLYPHS_GROUPS = {"left": "@MMK_L_", "right": "@MMK_R_"}

# Native lib attribute per registered object kind (fontlab.pyi: dict(name, QVariant)).
LIB_ATTRIBUTES = {"font": "packageLib", "glyph": "lib", "layer": "lib"}


class _PendingLayer:
    """A master layer FontLab has not created yet (R021).

    Native fact: glyphs of a FontLab-created font (the .notdef of an MCP
    new_font font) have no layers at all. Reads see an empty layer with width 0;
    the first write creates it with findLayerCreate, and FontLab then assigns its
    default width. Reads never create layers, since they run in owner sessions.
    """

    isValid = True

    def __init__(self, master_name):
        self.master_name = master_name


class _PendingBackground(_PendingLayer):
    """An absent mask: reads do not create native layers."""

    def __init__(self, foreground_id):
        self.foreground_id = foreground_id


# Live backends (weak): a copy-on-write clone rebinds tokens in all of them.
_LIVE_BACKENDS = weakref.WeakSet()


@dataclass(frozen=True)
class OwnedPackage:
    """Retain both native objects; unregistered package.fgPackage is unsafe."""

    package: object
    fg_font: object


def _qpoint(x: float, y: float):
    """flNode takes a QPointF (fontlab.pyi: flNode(QPointF position[, nodeType]))."""
    from PythonQt.QtCore import QPointF

    return QPointF(float(x), float(y))


def owned_test_package(glyph_names: Iterable[str]) -> OwnedPackage:
    """Build an unregistered package for native acceptance, never a user font.

    Single-character names use that character's Unicode. Other names receive
    deterministic Plane 15 private-use values. No outlines or workspace operations
    are added; the native package constructor supplies the default empty layers.
    """
    names = tuple(glyph_names)
    if any(not isinstance(name, str) or not name for name in names):
        raise ValueError("Glyph names must be nonempty strings")
    if len(set(names)) != len(names) or len(names) > 0xFFFE:
        raise ValueError("Glyph names must be unique and fit the private-use range")
    native = FontLabBackend._native()
    try:
        import fontgate
    except ImportError as error:
        raise HostUnavailable("FontLab fontgate API is unavailable") from error
    font = fontgate.fgFont()
    for index, name in enumerate(names):
        glyph = fontgate.fgGlyph(name)
        glyph.addUnicode(ord(name) if len(name) == 1 else 0xF0000 + index)
        # Native fact: a new fgGlyph has no layers; add the default master's.
        glyph.layers.append(fontgate.fgLayer("Regular"))
        font.addGlyph(glyph)
    return OwnedPackage(native.flPackage(font), font)


class FontLabBackend(OutlineOperations):
    supports_anchor_selection = False
    supports_component_selection = True
    supports_guide_selection = False
    volatile_collections = frozenset({"axes", "instances"})

    """Use on the UI thread; raw packages must be workspace-registered.

    Unregistered packages must be supplied as OwnedPackage, retaining their source
    fgFont so accessing metadata never invokes the unsafe fgPackage getter.
    """

    def __init__(self, packages: Iterable[object] | None = None):
        _LIVE_BACKENDS.add(self)  # every session's tokens follow copy-on-write
        self._packages = None if packages is None else tuple(packages)
        self._owned_fonts = {
            item.package.id: item.fg_font
            for item in self._packages or ()
            if isinstance(item, OwnedPackage)
        }
        self._serial = count()
        self._keys = {}
        self._object_keys = {}
        self._objects = {}
        self._parents = {}
        self._glyph_native_ids = {}
        self._glyph_names = {}
        self._glyph_tokens = {}
        self._master_names = {}
        self._layer_masters = {}
        self._auxiliary_associations = {}
        self._glyph_layer_tokens = {}
        self._layer_members = {}
        self._listed_font_ids = set()
        self._node_shapes = {}
        self._selection_flags = {}
        self._metric_sources = {}
        self._history_markers = {}
        self._history_aliases = {}
        self._history_slots = {}
        self._reading_slots = None
        self._reconciling = False
        self._validating = False
        self._revision = 0
        self._undo_name = None
        self._changed = {}
        self._pending_layer_updates = set()
        self._prepared = {}
        self._owned_shapes = set()  # shape ids cloned for this notification cycle
        self._history_disclosure = None

    def revision(self, font_id):
        package = self._object(font_id)
        history = getattr(package, "currentHistoryState", None)
        return (
            self._revision,
            history() if history is not None else None,
            getattr(package, "glyphsCount", None),
        )

    def kerning_revision(self, font_id):
        """Observe native kerning Undo without invalidating geometry snapshots.

        MCP kerning commands attach history to the current kerning container,
        independently of package history. Its identity also tracks master changes.
        Never request this native container from an unregistered owned package.
        """
        package = self._object(font_id)
        revision = self.revision(font_id)
        if package.id in self._owned_fonts:
            return revision, None
        return revision, self._kerning_history_marker(self._kerning_container(package))

    @staticmethod
    def _kerning_container(package):
        if not callable(getattr(type(package), "kerningContainer", None)):
            raise UnsupportedCapability(
                "Native kerning history is unavailable", capability="kerning.history"
            )
        return package.kerningContainer()

    @staticmethod
    def _kerning_history_marker(container):
        if not getattr(container, "isValid", False):
            raise StaleNativeObject("Native kerning history container is stale")
        if not callable(getattr(type(container), "currentHistoryState", None)):
            raise UnsupportedCapability(
                "Native kerning history is unavailable", capability="kerning.history"
            )
        return container.id, container.currentHistoryState()

    def kerning_write_revision(self, font_id, master_ids, containers=None):
        """Validate every master in a writer snapshot using retained live handles.

        Native PackageImpl retains each container by master name until package
        release. Capture handles with bounded master scopes once; warm checks do
        not switch masters or enumerate classes. Check the live current identity
        too, so a replaced container cannot authorize the previous snapshot.
        """
        package = self._object(font_id)
        revision = self.revision(font_id)
        if package.id in self._owned_fonts:
            return (revision, None), {}
        names = {m: self._kerning_master(font_id, m) for m in master_ids}
        current = self._kerning_container(package)
        current_marker = self._kerning_history_marker(current)
        current_name = package.master
        current_master = next(
            (m for m, name in names.items() if name == current_name), None
        )
        if (
            containers is None
            or tuple(containers) != tuple(master_ids)
            or current_master not in containers
            or self._kerning_history_marker(containers[current_master])[0]
            != current_marker[0]
        ):
            containers = {
                m: self._master_read(m, self._kerning_container) for m in master_ids
            }
        markers = tuple(
            (m, self._kerning_history_marker(container))
            for m, container in containers.items()
        )
        return (revision, markers), containers

    def cache_revision(self, font_id, key):
        """Validate glyph-owned snapshots against notified native edits and Undo.

        Parent traversal is bounded by object depth, independent of font size.
        Native writes without history notification have no observable marker.
        """
        if isinstance(key, tuple) and key and key[0] == "kerning-groups":
            return self.kerning_revision(font_id)
        revision = self.revision(font_id)
        for token in (key,) if isinstance(key, str) else key:
            if not isinstance(token, str):
                continue
            while token in self._object_keys:
                if self._object_keys[token][1] == "glyph":
                    glyph = self._object(token)
                    history = getattr(glyph, "currentHistoryState", None)
                    return revision, history() if history else None
                token = self._parents.get(token)
        return revision

    @staticmethod
    def _fontpr():
        """FontLab's MCP tools for embedded Python (native, with undo history)."""
        try:
            import fontpr
        except ImportError as error:
            raise HostUnavailable("FontLab fontpr tools are unavailable") from error
        return fontpr

    @staticmethod
    def _fontgate():
        try:
            import fontgate
        except ImportError as error:
            raise HostUnavailable("FontLab fontgate API is unavailable") from error
        return fontgate

    @staticmethod
    def _native():
        try:
            import fontlab
        except ImportError as error:
            raise HostUnavailable(
                "FontLab 9 native Python API is unavailable"
            ) from error
        return fontlab

    def _invalidate(self, token):
        # A stale failed updater remains a publication barrier until explicit
        # recovery/discard; removing a handle must not authorize its old batch.
        key = self._object_keys[token]
        if self._keys.get(key) == token:
            del self._keys[key]
        self._objects.pop(token, None)

    def _register(self, key, obj, parent=None):
        token = self._keys.get(key)
        if token is None and key[1] in {"node", "path", "component", "anchor", "guide"}:
            previous = self._history_aliases.get(key)
            if previous is not None and previous not in self._objects:
                # A new destination may first be read after the source retired
                # the handle. Its native id still identifies the same object.
                token = self._keys[key] = previous
        slot = None
        if self._reading_slots is not None and key[1] in {
            "path",
            "node",
            "component",
            "anchor",
            "guide",
        }:
            counts, _ = self._reading_slots
            ordinal = counts.get((parent, key[1]), 0)
            counts[parent, key[1]] = ordinal + 1
            label = obj.name if key[1] == "anchor" else ordinal
            slot = (parent, key[1], label)
            if self._reconciling:
                token = self._history_aliases.get(
                    key, self._history_slots.get(slot, token)
                )
                if token is not None:
                    old = self._object_keys[token]
                    if self._keys.get(old) == token:
                        self._keys.pop(old)
                    self._keys[key] = token
        # Unresolved glyphs deliberately have no editing wrapper yet.
        if (
            token is not None
            and self._objects.get(token) is not None
            and not self._reconciling
            and key[1] != "layer"
            and not self.is_valid(token)
        ):
            self._invalidate(token)
        if key not in self._keys:
            self._keys[key] = f"fl-{next(self._serial)}"
        token = self._keys[key]
        self._object_keys[token] = key
        self._history_aliases[key] = token
        if slot is not None:
            self._reading_slots[1][slot] = token
        self._parents[token] = parent
        if obj is not None or token not in self._objects:
            self._objects[token] = obj
        return token

    def _font_id(self, package):
        return self._register((package.id, "font", package.id), package)

    def _package_handles(self):
        if self._packages is not None:
            return tuple(
                item.package if isinstance(item, OwnedPackage) else item
                for item in self._packages
            )
        native = self._native()
        return tuple(
            native.flPackage(p) for p in native.flWorkspace.instance().packages()
        )

    def _fontgate_font(self, package):
        # Do not use dict.get(key, package.fgPackage): defaults evaluate eagerly.
        if package.id in self._owned_fonts:
            return self._owned_fonts[package.id]
        return package.fgPackage

    def _layer_token(
        self, document, layer, master_id, glyph_id, layer_key, background=False
    ):
        # Master layers are keyed by glyph and master (Glyphs: layerId ==
        # masterId), so a pending layer keeps its token when it is created.
        # Auxiliaries use ("auxiliary", native id), never a name or master id.
        key = (document, "layer", glyph_id, layer_key)
        if background:
            key += ("background",)
        lid = self._register(key, layer, glyph_id)
        self._layer_masters[lid] = master_id
        self._glyph_layer_tokens.setdefault(glyph_id, set()).add(lid)
        # Capture the epoch when a handle is exposed, before an external Undo can
        # replace its wrapper. A first later read must not adopt that new epoch
        # as the baseline and retire the still-rebindable identity.
        if glyph_id not in self._history_markers:
            history = getattr(self._objects.get(glyph_id), "currentHistoryState", None)
            if history is not None:
                self._history_markers[glyph_id] = history()
        return lid

    def _read_layer(
        self, document, layer, master_id, glyph_id, background=False, *, layer_key=None
    ):
        layer_key = master_id if layer_key is None else layer_key
        lid = self._layer_token(
            document, layer, master_id, glyph_id, layer_key, background
        )
        if isinstance(layer, _PendingLayer):
            for token in self._layer_members.get(lid, ()):
                self._invalidate(token)
            self._layer_members[lid] = set()
            identity = (
                self._keys[(document, "layer", glyph_id, layer_key)]
                if isinstance(layer_key, tuple)
                else ""
            )
            return LayerInfo(lid, master_id, 0.0, layerId=identity)
        previous = self._reading_slots
        self._reading_slots = ({}, {})
        try:
            info = self._read_layer_contents(document, layer, master_id, lid)
            if isinstance(layer_key, tuple):
                foreground = self._keys[(document, "layer", glyph_id, layer_key)]
                info = replace(info, layerId=foreground, name=layer.name)
            return info
        finally:
            self._reading_slots = previous

    def _read_layer_contents(self, document, layer, master_id, lid):
        paths, components, shape_ids = [], [], []
        for shape in layer.shapes:
            # Native fact (probe_components.json): a glyph component is both
            # isComponent and isComposite; only other composites are unmapped.
            if shape.isComposite and not shape.isComponent:
                raise UnsupportedCapability(
                    "Nested composite shapes need a separate mapping"
                )
            if shape.isComponent:
                cid = self._register((document, "component", shape.id), shape, lid)
                tx = shape.transform
                if not tx.isAffine():
                    raise UnsupportedCapability(
                        "Projective component transforms are not affine"
                    )
                components.append(
                    ComponentInfo(
                        cid,
                        shape.shapeData.componentGlyph,
                        (tx.m11(), tx.m12(), tx.m21(), tx.m22(), tx.dx(), tx.dy()),
                    )
                )
                shape_ids.append(cid)
                continue
            for contour in shape.contours:
                pid = self._register((document, "path", contour.id), contour, lid)
                nodes = []
                native_nodes = list(contour.nodes())
                for index, node in enumerate(native_nodes):
                    nid = self._register((document, "node", node.id), node, pid)
                    point = shape.transform.map(node.position)
                    previous = (
                        native_nodes[index - 1] if index or contour.closed else None
                    )
                    selected = bool(node.selected)
                    self._selection_flags[nid] = selected
                    nodes.append(
                        NodeInfo(
                            nid,
                            point.x(),
                            point.y(),
                            node_type(node, contour.isTT, previous),
                            self._node_smooth(node),
                            selected,
                            name=getattr(node, "name", "") or None,
                        )
                    )
                    self._node_shapes[nid] = (shape, lid)
                nodes = glyphs_order(nodes, contour.closed)
                paths.append(PathInfo(pid, tuple(nodes), contour.closed))
                shape_ids.append(pid)
        anchors = tuple(
            AnchorInfo(
                self._register((document, "anchor", a.id), a, lid),
                a.name,
                a.point.x(),
                a.point.y(),
            )
            for a in layer.anchors
        )
        guides = tuple(
            GuideInfo(
                self._register((document, "guide", g.id), g, lid),
                g.centerPoint.x(),
                g.centerPoint.y(),
                g.angle,
                g.name,
            )
            for raw in layer.guidelines
            for g in (self._guide_line(raw),)
            # Native fact (r020-model run 1): PostScript hints are flGuideLines too.
            if not g.isHint
        )
        info = LayerInfo(
            lid,
            master_id,
            layer.advanceWidth,
            tuple(paths),
            tuple(components),
            anchors,
            tuple(shape_ids),
            guides,
        )
        members = {item.id for item in (*paths, *components, *anchors, *guides)}
        members.update(node.id for path in paths for node in path.nodes)
        for token in self._layer_members.get(lid, set()) - members:
            parent = self._parents.get(token)
            if self._object_keys[token][1] == "node":
                parent = self._parents.get(parent)
            # A destination visited earlier may already own this native token.
            if parent == lid:
                self._invalidate(token)
        self._layer_members[lid] = members
        self._history_slots.update(self._reading_slots[1])
        return info

    def dark_mode(self):
        return bool(self._native().flPreferences().isDark)

    def list_fonts(self) -> tuple[str, ...]:
        ids = tuple(self._font_id(p) for p in self._package_handles() if p.isValid)
        for token in self._listed_font_ids - set(ids):
            self._invalidate(token)
        self._listed_font_ids = set(ids)
        return ids

    def font_id_for(self, package) -> str | None:
        """Font id of a native package (e.g. a signal argument) in this scope."""
        if not package.isValid:
            return None
        if self._packages is not None and package.id not in {
            p.id for p in self._package_handles()
        }:
            return None
        return self._font_id(package)

    def current_font_id(self) -> str | None:
        if self._packages is not None:
            return next(iter(self.list_fonts()), None)
        # Native fact (probe_app_state.json): flWorkspace.currentPackage lags behind
        # the active font after a switch; FontLab's own get_active_font follows it.
        # After the active font closes, FontLab has no active font until another is
        # activated (r019-document run 2); that is reported as None, not guessed.
        tools = self._fontpr()
        try:
            active = tools.get_active_font()
        except tools.Error:
            return None
        current = self._native().flWorkspace.instance().findPackageId(active["id"])
        if current is None or not current.isValid:
            return None
        return self._font_id(current)

    def _validate_history(self, token, *, force=False):
        """Reconcile one glyph's retained handles only when native history moves."""
        if self._validating or self._reconciling or self._reading_slots is not None:
            return
        key = self._object_keys.get(token)
        if key is None or key[1] in {"font", "master", "glyph"}:
            return
        glyph_id = token
        while (
            glyph_id in self._object_keys and self._object_keys[glyph_id][1] != "glyph"
        ):
            glyph_id = self._parents.get(glyph_id)
        if glyph_id not in self._object_keys:
            return
        self._validating = True
        try:
            if not self.is_valid(glyph_id):
                return
            glyph = self._objects[glyph_id]
            history = getattr(glyph, "currentHistoryState", None)
            marker = history() if history else None
            previous = self._history_markers.setdefault(glyph_id, marker)
            if previous == marker and not force:
                return
            self._reconciling = True
            try:
                layers = sorted(
                    self._glyph_layer_tokens.get(glyph_id, ()),
                    key=lambda token: len(self._object_keys[token]),
                )
                for lid in layers:
                    layer_key = self._object_keys[lid]
                    if len(layer_key) == 4:
                        if isinstance(layer_key[3], tuple):
                            layer = self._auxiliary_layer(glyph_id, lid)
                            if layer is not None:
                                self._read_layer(
                                    layer_key[0],
                                    layer,
                                    self._layer_masters[lid],
                                    glyph_id,
                                    layer_key=layer_key[3],
                                )
                        else:
                            self.layer(glyph_id, self._layer_masters[lid])
                    else:
                        foreground = self._keys.get(layer_key[:4])
                        if foreground is not None:
                            self.background_layer(foreground)
                self._revision += 1
                self._history_markers[glyph_id] = marker
            finally:
                self._reconciling = False
        finally:
            self._validating = False

    def _recover_moved_handle(self, token):
        """On an orphan only, inspect other already-modeled glyph histories.

        No font listing or normal-hit scan: an external cross-glyph move can
        leave the source's token temporarily orphaned until its destination
        glyph's changed history is reconciled.
        """
        if self._validating or self._reconciling or self._reading_slots is not None:
            return
        key = self._object_keys.get(token)
        if key is None or key[1] not in {
            "node",
            "path",
            "component",
            "anchor",
            "guide",
        }:
            return
        for glyph, layers in tuple(self._glyph_layer_tokens.items()):
            if self._object_keys[glyph][0] != key[0] or not layers:
                continue
            self._validate_history(
                next(iter(layers)), force=glyph not in self._history_markers
            )
            if token in self._objects:
                return

    def is_valid(self, id: str) -> bool:
        self._validate_history(id)
        if id not in self._objects:
            self._recover_moved_handle(id)
        if id not in self._objects:
            return False
        parent = self._parents[id]
        if parent is not None and not self.is_valid(parent):
            return False
        obj = self._objects[id]
        if obj is None:
            package = self._objects[parent]
            if package.id in self._owned_fonts:
                obj = package.findName(self._glyph_names[id])
            else:
                obj = package.findFgId(self._glyph_native_ids[id])
            self._objects[id] = obj
        if obj is None or not obj.isValid:
            self._invalidate(id)
            return False
        if id in self._master_names and self._master_names[id] not in obj.masters:
            self._invalidate(id)
            return False
        master = self._layer_masters.get(id)
        return master is None or self.is_valid(master)

    def proxy_parent(self, token):
        """Current logical parent, already reconciled by proxy validation."""
        key = self._object_keys.get(token)
        if key is None or key[1] not in {
            "node",
            "path",
            "component",
            "anchor",
            "guide",
        }:
            return None
        parent = self._parents[token]
        if key[1] == "guide" and self._object_keys[parent][1] != "layer":
            return None
        return parent

    def layer_location(self, layer_id):
        key = self._object_keys[layer_id]
        identity = self._keys[key[:4]] if isinstance(key[3], tuple) else key[3]
        return key[2], identity, len(key) > 4

    def _object(self, id):
        if not self.is_valid(id):
            raise StaleNativeObject(id)
        key = self._object_keys[id]
        if key[1] == "layer" and len(key) == 4 and isinstance(key[3], tuple):
            layer = self._auxiliary_layer(key[2], id)
            if layer is None:
                raise StaleNativeObject(id)
            return layer
        return self._objects[id]

    def _axes(self, package):
        # Unregistered owned packages expose no axes: their native getters may
        # reach the unsafe fgPackage.
        return () if package.id in self._owned_fonts else tuple(package.axes)

    @staticmethod
    def _coordinates(axes, location):
        """One coordinate per axis, 0.0 where the location stores none.

        Native facts: flLocation keys vary (FontLab's own setLocation uses the
        short name; probe_locations.json), and flAxis.valueWeight returns the
        location's weight value for every axis, so it cannot read a second axis
        (glyport-r020/probe-location-read-run1). Items are read by key instead.
        """

        def value(axis):
            for key in (axis.shortName, axis.name, axis.tag):
                try:
                    stored = location[key]
                except (KeyError, IndexError, TypeError):
                    continue
                if isinstance(stored, tuple):  # anisotropic: (x, y)
                    return tuple(float(v) for v in stored)
                if stored is not None:
                    return float(stored)
            return 0.0

        return tuple(value(a) for a in axes)

    def font_path(self, font_id: str) -> str | None:
        """flPackage.fileName (echopy fontlab.pyi); unsaved fonts have no path."""
        path = self._object(font_id).fileName
        return str(path) if path else None

    def save_font(self, font_id: str, path: str | None = None, *, make_copy=False) -> None:
        """Save a registered document by native font ID, verifying the output file."""
        from pathlib import Path

        package = self._font_write(font_id, "GSFont.save")
        if self._undo_name is not None or self._changed:
            raise UnsupportedCapability("End pending changes before saving", capability="GSFont.save")
        if make_copy and path is None:
            raise ValueError("A path is required for makeCopy=True")
        target = path if path is not None else self.font_path(font_id)
        if not target:
            raise ValueError("No path set for this font")
        destination = Path(target).expanduser().resolve()
        if destination.suffix.lower() not in {".vfj", ".vfc"}:
            raise UnsupportedCapability(
                "Native save requires .vfj or .vfc; export UFO or other formats instead",
                capability="GSFont.save.format",
            )
        # echopy fontpr.call(name, **kwargs), fontpr.save_font; same qualified
        # save_font(font_id, path, overwrite) route as fontport.host.save.
        save = self._resolve_tool("call", "GSFont.save")
        original = package.fileName
        try:
            save("save_font", font_id=package.fgId, path=str(destination), overwrite=True)
            if not destination.is_file():
                raise NativeOperationError(
                    f"FontLab did not create {destination}", capability="GSFont.save")
        finally:
            if make_copy:
                package.fileName = original

    def close_font(self, font_id: str, *, ignore_changes=False) -> None:
        """Close a document, requiring deliberate permission to discard edits."""
        package = self._font_write(font_id, "GSFont.close")
        if self._undo_name is not None or self._changed:
            raise UnsupportedCapability("End pending changes before closing", capability="GSFont.close")
        # echopy: fontlab.flPackage.getProperty(key). The repository's
        # native dirty-state contract is __has_history_changes, not window flags.
        if not ignore_changes and package.getProperty("__has_history_changes") not in (False, 0):
            raise UnsupportedCapability(
                "Save the font first or pass ignoreChanges=True explicitly to discard edits",
                capability="GSFont.close.unsavedChanges",
            )
        # echopy: fontlab.flPackage.close(save=False).
        if package.close(False) is False:
            raise NativeOperationError("FontLab refused to close the font", capability="GSFont.close")
        self._invalidate(font_id)

    def outline_layer(self, layer_id: str) -> LayerInfo:
        """Snapshot a master, auxiliary or background layer using existing readers."""
        self._object(layer_id)
        glyph, identity, background = self.layer_location(layer_id)
        info = self.layer(glyph, identity)
        return self.background_layer(info.id) if background else info

    def validate_component_expansion(self, layer_id, components) -> None:
        """Check native reference layers before the first component is detached."""
        from .component_edits import native_reference

        for component in components:
            shape = self._object(component.id)
            native_reference(self, layer_id, component.componentName,
                             shape.shapeData.componentLayer)
        # Decomposition reuses component_edits.decompose_native:
        # echopy fontlab.flShape.ejectTo, flLayer.removeShape/insertShape.
        # Boolean, direction and extrema algorithms run in Python: echopy has
        # no corresponding layer-scoped calls. Publication reuses guarded
        # flContour/flNode construction and flLayer.addShape/removeShape.

    def set_font_info(self, font_id, **changes):
        package = self._font_write(font_id, "GSFont.metadata")
        info = self._fontgate_font(package).info
        self._prepare(("font", package))
        if "familyName" in changes:
            info.familyName = changes["familyName"]
        if "unitsPerEm" in changes:
            # Metadata only: changing UPM must not rescale outlines.
            package.setUpm(changes["unitsPerEm"], False)
        self._touch(("font", package))

    def set_master_info(self, master_id, **changes):
        font_id = self._parents[master_id]
        package = self._font_write(font_id, "GSFontMaster.metadata")
        old = self._master_names[master_id]
        entries = [("font", package)]
        if "name" in changes:
            name = changes["name"]
            if name != old and name in package.masters:
                raise ValueError("Duplicate master name")
            # Native rename also changes master/bracket layers and their masks.
            self._require_history_scope(("font", package))
            for info in self.glyphs(font_id):
                glyph = self._object(info.id)
                layers = [layer for layer in glyph.layers
                          if layer.name == old or layer.name.startswith((old + ":", old + " ["))]
                if not layers:
                    continue
                entries.append(("glyph", glyph))
                for layer in layers:
                    if layer.autoLayer:
                        raise UnsupportedCapability("Rename refuses automatic master layers", capability="GSFontMaster.name.autoLayer")
                    key = master_id if layer.name == old else ("auxiliary", layer.id)
                    self._layer_token(font_id, layer, master_id, info.id, key)
                    entries.append(("layer", layer))
                    mask = layer.getMaskLayer(False)
                    if mask is not None and mask.isValid:
                        self._layer_token(font_id, mask, master_id, info.id, key, background=True)
                        entries.append(("layer", mask))
            self._prepare(*entries)
            package.renameMaster(old, name)
            if name not in package.masters:
                raise NativeOperationError("Native master rename refused")
            for peer in tuple(_LIVE_BACKENDS):
                for token, previous in tuple(peer._master_names.items()):
                    owner = peer._objects.get(token)
                    if previous != old or owner is None or owner.id != package.id:
                        continue
                    key = peer._object_keys[token]
                    new_key = (*key[:2], name)
                    peer._keys.pop(key, None)
                    peer._keys[new_key] = token
                    peer._object_keys[token] = new_key
                    peer._history_aliases[new_key] = token
                    peer._master_names[token] = name
        else:
            fields = {"ascender": "ascender_value", "capHeight": "capsHeight_value",
                      "xHeight": "xHeight_value", "descender": "descender_value",
                      "italicAngle": "italicAngle_value"}
            self._prepare(("font", package))
            def mutate(target):
                for field, value in changes.items():
                    setattr(target, fields[field], value)
            self._master_read(master_id, mutate)
        self._touch(*entries)

    def font_info(self, font_id: str) -> FontInfo:
        package = self._object(font_id)
        axes = self._axes(package)
        masters = []
        for name in package.masters:
            token = self._register((font_id, "master", name), package, font_id)
            self._master_names[token] = name
            coordinates = (
                self._coordinates(axes, package.location(name)) if axes else ()
            )
            masters.append(MasterInfo(token, name, coordinates))
        return FontInfo(
            font_id,
            self._fontgate_font(package).info.familyName,
            package.upm,
            tuple(masters),
            tuple(
                AxisInfo(a.tag or a.name, a.name, a.tag, bool(a.hidden)) for a in axes
            ),
        )

    def classes(self, font_id: str) -> tuple[ClassInfo, ...]:
        # Native fact (probe_ot_classes.json): fgFont.groups maps names to fgGroup;
        # OpenType classes answer isFeaGroup() and index as glyph names.
        groups = self._fontgate_font(self._object(font_id)).groups
        return tuple(
            ClassInfo(name, tuple(group))
            for name, group in groups.items()
            if group.isFeaGroup()
        )

    def instances(self, font_id: str) -> tuple[InstanceInfo, ...]:
        package = self._object(font_id)
        # flPackage.instances and axes are owned native value lists, unlike
        # the unsafe fgPackage getter on unregistered packages.
        axes = tuple(package.axes)
        return tuple(
            InstanceInfo(
                f"{font_id}-instance-{index}",
                item.name,
                self._coordinates(axes, item.location),
                bool(item.exportable),
                str(item.weight),
                float(item.weightValue),
                str(item.width),
            )
            for index, item in enumerate(package.instances)
        )

    def _tool_font(self, font_id, capability):
        """MCP font id of a registered package (native fact: package.fgId)."""
        package = self._object(font_id)
        if package.id in self._owned_fonts:
            raise UnsupportedCapability(
                "FontLab tools need a workspace-registered font", capability=capability
            )
        return package.fgId

    def _resolve_tool(self, name, capability):
        """Resolve the host dependency before any history or document writes."""
        tools = self._fontpr()
        function = getattr(tools, name, None)
        if not callable(function):
            raise UnsupportedCapability(
                f"FontLab tool {name!r} is unavailable", capability=capability
            )

        def invoke(*args, **arguments):
            try:
                return function(*args, **arguments)
            except tools.Error as error:
                raise NativeOperationError(str(error), capability=capability) from error

        return invoke

    def _tool(self, name, capability, **arguments):
        return self._resolve_tool(name, capability)(**arguments)

    def kerning(self, font_id: str, master_id: str) -> tuple[KerningPair, ...]:
        fid = self._tool_font(font_id, "GSFont.kerning")
        master, pairs = self._kerning_master(font_id, master_id), []
        while True:
            page = self._tool(
                "list_kerning_pairs",
                "GSFont.kerning",
                font_id=fid,
                master_name=master,
                offset=len(pairs),
                limit=KERNING_PAGE,
            )
            rows = page["pairs"]
            pairs.extend(
                KerningPair(
                    _glyphs_key(row["left"], "left"),
                    _glyphs_key(row["right"], "right"),
                    float(row["value"]),
                )
                for row in rows
            )
            if not rows or len(pairs) >= page["total_pairs"]:
                return tuple(pairs)

    def set_kerning(self, font_id, master_id, left, right, value) -> None:
        """Through FontLab's own kerning tools, which record their own Undo step."""
        fid = self._tool_font(font_id, "GSFont.setKerningForPair")
        master = self._kerning_master(font_id, master_id)
        pair = {
            "font_id": fid,
            "master_name": master,
            "left": _fontlab_key(left, "left"),
            "right": _fontlab_key(right, "right"),
        }
        if value is None:
            if not self._tool(
                "get_kerning_pair", "GSFont.removeKerningForPair", **pair
            )["has_value"]:
                return
            name, capability = "delete_kerning_pair", "GSFont.removeKerningForPair"
        else:
            pair["value"] = value
            name, capability = "set_kerning_pair", "GSFont.setKerningForPair"
        write = self._resolve_tool(name, capability)
        try:
            write(**pair)
        finally:
            self._kerning_changed()

    def kerning_classes(
        self, font_id: str, master_id: str | None = None
    ) -> tuple[KerningClassInfo, ...]:
        fid = self._tool_font(font_id, "GSGlyph.kerningGroups")
        arguments = (
            {}
            if master_id is None
            else {"master_name": self._kerning_master(font_id, master_id)}
        )
        reply = self._tool(
            "list_kerning_classes", "GSGlyph.kerningGroups", font_id=fid, **arguments
        )
        return tuple(
            KerningClassInfo(
                c["name"], tuple(c["glyph_names"]), bool(c["left"]), bool(c["right"])
            )
            for c in reply["classes"]
        )

    def _kerning_master(self, font_id, master_id):
        self._object(master_id)
        if (
            self._parents.get(master_id) != font_id
            or master_id not in self._master_names
        ):
            raise ValueError("Master does not belong to this font")
        return self._master_names[master_id]

    def _kerning_changed(self):
        """Invalidate peer readers without adding history to native-tool writes."""
        for peer in tuple(_LIVE_BACKENDS):
            peer._revision += 1

    def set_kerning_group(
        self, font_id: str, glyph_id: str, side: str, value: str | None
    ) -> None:
        from .fontlab_kerning import set_group

        set_group(self, font_id, glyph_id, side, value)

    def replace_kerning(
        self, font_id: str, master_id: str, pairs: tuple[KerningPair, ...]
    ) -> None:
        from .fontlab_kerning import replace_pairs

        replace_pairs(self, font_id, master_id, pairs)

    def _text_block(self, font_id):
        """FontLab's active glyph-tab text block if it shows this font."""
        package = self._object(font_id)
        workspace = self._native().flWorkspace.instance()
        block = workspace.getActiveTextBlock()
        if block is None:
            # Native fact (r019-tab run 2): a fresh glyph tab has no active text
            # block; its text is the active canvas's first block.
            canvas = workspace.getActiveCanvas()
            blocks = [] if canvas is None else list(canvas.textBlocks())
            block = blocks[0] if blocks else None
        if block is None or block.package.fgId != package.fgId:
            return None
        return block

    def edit_view(self, font_id: str) -> EditViewInfo | None:
        self._tool_font(font_id, "GSFont.currentTab")
        block = self._text_block(font_id)
        if block is None:
            return None
        lines: dict[int, list[str]] = {}
        for info in block.getAllGlyphs() or ():
            lines.setdefault(block.getLineIndex(info), []).append(info.glyph.name)
        # Empty lines have no glyph infos, including leading/trailing breaks.
        breaks = sum(bool(symbol.cr) for symbol in block.symbolList().symbols())
        line_count = max(max(lines, default=-1) + 1, breaks + 1 if breaks else 0)
        active = block.getActiveGlyph()
        slots = self._text_slots(block)
        cursor = None
        if active is not None:
            cursor = next(
                (i for i, info in enumerate(slots) if info and info.id == active.id),
                None,
            )
        return EditViewInfo(
            tuple(tuple(lines.get(index, ())) for index in range(line_count)),
            None if active is None else active.glyph.name,
            self._object(font_id).master,
            str(block.id),
            cursor,
        )

    @staticmethod
    def _text_slots(block):
        """The tab's glyph infos in text order, None for each line break."""
        slots, line = [], None
        for info in block.getAllGlyphs() or ():
            index = block.getLineIndex(info)
            if line is not None and index != line:
                slots.extend([None] * (index - line))
            line = index
            slots.append(info)
        return slots

    def redraw_edit_view(self, font_id):
        self._object(font_id)
        self._native().UpdateActiveCanvas()

    def set_edit_cursor(self, font_id: str, index: int) -> None:
        """flTextBlock.setActiveGlyph(flGlyphInfo) (probe_text_cursor.json):
        the glyph at ``index``, else the nearest glyph before it."""
        block = self._text_block(font_id)
        if block is None:
            raise UnsupportedCapability(
                "No glyph tab of this font is active",
                capability="GSEditViewController.textCursor",
            )
        slots = self._text_slots(block)
        target = next((s for s in reversed(slots[: index + 1]) if s), None)
        if target is not None:
            block.setActiveGlyph(target)

    def open_edit_view(self, font_id: str) -> None:
        """Open a literal empty tab, as Glyphs' addTabWithDisplayString_("") does."""
        fid = self._tool_font(font_id, "GSFont.newTab")
        from .navigation import empty_tab_emitter, preserve_rendered_activation

        qtgui = _import_qtgui()
        main = self._native().MainWindow()
        if main is None:
            raise UnsupportedCapability(
                "FontLab's main window is unavailable", capability="GSFont.newTab"
            )
        workspace = self._native().flWorkspace.instance()
        with (
            preserve_rendered_activation(workspace),
            empty_tab_emitter(qtgui, main) as emitter,
        ):
            self._tool("set_active_font", "GSFont.newTab", font_id=fid)
            emitter.setText("")

    def set_edit_glyphs(self, font_id: str, lines) -> None:
        """Replace the active glyph tab's text (requestContent, probe_glyph_tab.json).

        Native facts (probe_tab_text.json): FontLab's string parser drops
        unencoded "/name" tokens, so names go in as fgSymbol objects; only the
        string form "\n" makes a line break; fgSymbolList() without an argument
        cannot be built.
        """
        if self._text_block(font_id) is None:
            raise UnsupportedCapability(
                "No glyph tab of this font is active",
                capability="GSEditViewController.text",
            )
        native, symbols = self._native(), None
        for index, names in enumerate(lines):
            parts = [native.fgSymbolList("\n")] if index else []
            if names:
                parts.append(native.fgSymbolList([native.fgSymbol(n) for n in names]))
            for part in parts:
                if symbols is None:
                    symbols = part
                else:
                    symbols.append(part)
        if symbols is None:
            symbols = native.fgSymbolList("")
        from .navigation import preserve_shape_activation

        package = self._object(font_id)
        with preserve_shape_activation(
            package, (name for line in lines for name in line)
        ):
            native.flItems().requestContent(symbols, 0)

    def current_layers(self, font_id: str) -> tuple[tuple[str, str], ...]:
        fid = self._tool_font(font_id, "GSFont.selectedLayers")
        tools = self._fontpr()
        try:
            reply = tools.get_current_glyphs()
        except tools.Error:  # "No current glyphs."
            return ()
        workspace = self._native().flWorkspace.instance()
        master = (
            self._object(font_id).master
            if getattr(workspace, "activeFontPanel", None) is not None
            else None
        )
        return tuple(
            (g["name"], master if master is not None else g["active_layer_name"])
            for g in reply["glyphs"]
            if g["package_id"] == fid
        )

    def set_font_selection(self, font_id, glyph_ids):
        """Select through the documented existing TypeRig scalar API.

        Restrict to this font's Font Window so legacy selection never changes
        an unrelated font or an editor tab. Empty input clears selection.
        """
        capability = "GSFont.selection"
        fid = self._tool_font(font_id, capability)
        active = self._tool("get_active_font", capability)["id"]
        native = self._native()
        if active != fid or native.flWorkspace.instance().activeFontPanel is None:
            raise UnsupportedCapability(
                "Font selection requires this font's active Font Window",
                capability=capability,
            )
        indices = []
        for glyph_id in glyph_ids:
            glyph = self._object(glyph_id)
            if self._parents[glyph_id] != font_id:
                raise ValueError("Selected glyph belongs to a different font")
            record = self._fontgate_font(self._object(font_id))[glyph.name]
            indices.append(int(record.index))
        try:
            from FL import fl
        except ImportError as error:
            raise UnsupportedCapability(
                "The scalar Font Window selection API (FL.fl.Select) is unavailable",
                capability=capability,
            ) from error
        # TypeRig's working FontLab caller uses legacy scalar indices. Avoid
        # PythonQt's unsupported Python-list -> QList<ulong> conversion.
        fl.Unselect()
        for index in indices:
            fl.Select(index)
        self._revision += 1  # UI selection is not an Undo edit

    def _layer_name(self, layer_id):
        layer = self._object(layer_id)
        if isinstance(layer, _PendingBackground):
            raise UnsupportedCapability(
                "No native mask exists", capability="GSLayer.background.hints"
            )
        if isinstance(layer, _PendingLayer):
            return layer.master_name
        # Old doubles may model unnamed master layers, but masks must have their own name.
        if self._object_keys[layer_id][-1] == "background":
            name = getattr(layer, "name", None)
            if not name or name == self._master_names[self._layer_masters[layer_id]]:
                raise UnsupportedCapability(
                    "Mask has no distinct addressable layer name",
                    capability="GSLayer.background.hints",
                )
            return name
        return getattr(layer, "name", self._master_names[self._layer_masters[layer_id]])

    def hints(self, layer_id: str) -> tuple[HintInfo, ...]:
        layer = self._object(layer_id)
        if isinstance(layer, _PendingLayer):
            return ()
        glyph_id = self._parents[layer_id]
        fid = self._tool_font(self._parents[glyph_id], "GSLayer.hints")
        where = {
            "font_id": fid,
            "glyph_name": self._object(glyph_id).name,
            "layer_name": self._layer_name(layer_id),
        }
        hints, offset = [], 0
        while True:
            page = self._tool(
                "get_layer_hints", "GSLayer.hints", offset=offset, **where
            )
            hints.extend(
                HintInfo(
                    row["orientation"] == "horizontal",
                    row["position"],
                    row["width"],
                    row.get("name", ""),
                    bool(row.get("ghost")),
                )
                for row in page["hints"]
            )
            if not page.get("truncated"):
                return tuple(hints)
            offset = page["next_offset"]

    def _edit_hints(self, layer_id, operation, capability):
        """One FontLab edit_layer_hints operation, notified like other layer edits.

        Native fact (glyport-r020/hints-run1-FAILED): called from Python the tool
        records no Undo step of its own, so an unnotified hint edit is lost to
        Undo; with the layer and glyph notified around it, it is one step, or
        part of the enclosing glyport undo group.
        """
        self._require_editable_layer(layer_id)
        layer_name = self._layer_name(
            layer_id
        )  # refuse an unnamed mask before any mutation
        glyph_id = self._parents[layer_id]
        tool_font = self._tool_font(self._parents[glyph_id], capability)
        edit = self._resolve_tool("edit_layer_hints", capability)
        glyph_name = self._object(glyph_id).name
        self._writable_layer(layer_id)
        self._prepare_layer(layer_id)
        self._commit_layer_edits(layer_id)
        edit(
            font_id=tool_font,
            glyph_name=glyph_name,
            layer_name=layer_name,
            operations=[operation],
        )
        self._touch_layer(layer_id)

    @staticmethod
    def _hint_fields(hint):
        if not isinstance(hint, HintInfo):
            raise TypeError("Expected HintInfo")
        return {
            "orientation": "horizontal" if hint.horizontal else "vertical",
            "position": hint.position,
            "width": hint.width,
            "name": hint.name,
        }

    def add_hint(self, layer_id: str, hint: HintInfo) -> None:
        fields = self._hint_fields(hint)
        self._edit_hints(
            layer_id,
            {"op": "add", **fields, "ghost": hint.ghost},
            "GSLayer.hints.append",
        )

    def set_hint(self, layer_id: str, index: int, changes: dict) -> None:
        """Patch only the given fields: FontLab rejects geometry on linked or
        expression-driven hints, while a name-only edit is accepted."""
        unknown = set(changes) - {"horizontal", "position", "width", "name"}
        if unknown:
            raise ValueError(f"Unknown hint fields: {sorted(unknown)}")
        fields = {k: v for k, v in changes.items() if k != "horizontal"}
        if "horizontal" in changes:
            fields["orientation"] = (
                "horizontal" if changes["horizontal"] else "vertical"
            )
        self._edit_hints(
            layer_id, {"op": "set", "hint_index": index, **fields}, "GSHint"
        )

    def remove_hint(self, layer_id: str, index: int) -> None:
        self._edit_hints(
            layer_id, {"op": "delete", "hint_index": index}, "GSLayer.hints.remove"
        )

    def glyphs(self, font_id: str) -> tuple[GlyphInfo, ...]:
        package = self._object(font_id)
        result = []
        for glyph in self._fontgate_font(package).glyphs:
            token = self._register((font_id, "glyph", glyph.id), None, font_id)
            self._glyph_native_ids[token] = glyph.id
            self._glyph_names[token] = glyph.name
            result.append(
                GlyphInfo(
                    token,
                    self._glyph_names[token],
                    tuple(f"{u:04X}" for u in glyph.unicodes),
                )
            )
        tokens = {glyph.id for glyph in result}
        for token in self._glyph_tokens.get(font_id, set()) - tokens:
            self._invalidate(token)
        self._glyph_tokens[font_id] = tokens
        return tuple(result)

    def glyph_lookup(self, font_id, key, *, unicode=False):
        """Consult FontGate's authoritative name/Unicode hash maps.

        flPackage delegates both finders to fg::Font (font.cpp:2384/2435).
        This observes other glyphs' renames without scanning their markers.
        Older/incomplete hosts without a finder use the bounded index fallback.
        """
        package = self._object(font_id)
        glyph = None
        if not unicode:
            finder = getattr(package, "findName", None)
            if not callable(finder):
                return NotImplemented
            glyph = finder(key)
        if glyph is None or not glyph.isValid:
            finder = getattr(package, "findUnicode", None)
            if not callable(finder):
                return NotImplemented
            try:
                code = int(key, 16) if unicode or len(key) != 1 else ord(key)
            except ValueError:
                return NotImplemented  # opaque glyport ID, or unknown name
            if not 0 <= code <= 0x10FFFF:
                return NotImplemented
            glyph = finder(code)
        if glyph is None or not glyph.isValid:
            return None
        identity = getattr(glyph, "fgGlyphId", None)
        if identity is None:
            return NotImplemented
        token = self._register((font_id, "glyph", identity), glyph, font_id)
        self._glyph_native_ids[token], self._glyph_names[token] = identity, glyph.name
        return token

    def glyph_info(self, glyph_id):
        """Read one glyph's metadata without listing the font."""
        glyph = self._object(glyph_id)
        self._glyph_names[glyph_id] = glyph.name
        package = self._object(self._parents[glyph_id])
        record = self._fontgate_font(package)[glyph.name]
        return GlyphInfo(
            glyph_id, glyph.name, tuple(f"{u:04X}" for u in record.unicodes)
        )

    @staticmethod
    def _master_layer_ids(glyph, names):
        """Resolve declared slots through the native finder, never name-derived roles.

        FontLab's case-sensitive finder selects the last equal-name stored layer.
        isMasterLayer also accepts interpolation/bracket names and cannot identify
        which concrete record supplies a declared slot. Missing slots stay pending.
        """
        result = set()
        for name in names:
            layer = glyph.findLayer(name)
            if layer is not None and layer.isValid:
                result.add(layer.id)
        return result

    def glyph_layers(self, glyph_id):
        """Master order first, followed by ordinary auxiliaries in native order.

        Keep explicit copied associations across live peers/history. Imported
        auxiliaries without session metadata use the first-master fallback;
        no persistent native lib keys are invented for this mapping.
        """
        glyph = self._object(glyph_id)
        font_id = self._parents[glyph_id]
        masters = self.font_info(font_id).masters
        if not masters:
            return ()
        result = [LayerIdentity(m.id, m.id, m.name) for m in masters]
        master_layers = self._master_layer_ids(glyph, (m.name for m in masters))
        package = self._object(font_id)
        for layer in glyph.layers:
            if (
                not layer.isValid
                or layer.id in master_layers
                or layer.isService
                or layer.isMaskLayer
            ):
                continue
            association = self._auxiliary_associations.get(
                (package.id, glyph.id, layer.id)
            )
            if association is None:
                association = next(
                    (
                        peer._auxiliary_associations[package.id, glyph.id, layer.id]
                        for peer in tuple(_LIVE_BACKENDS)
                        if (package.id, glyph.id, layer.id)
                        in peer._auxiliary_associations
                    ),
                    None,
                )
            if association is not None:
                self._auxiliary_associations[package.id, glyph.id, layer.id] = (
                    association
                )
            master = next(
                (m.id for m in masters if m.name == association), masters[0].id
            )
            token = self._layer_token(
                font_id, layer, master, glyph_id, ("auxiliary", layer.id)
            )
            result.append(LayerIdentity(token, master, layer.name))
        return tuple(result)

    def snapshot_layer(self, layer_id):
        from .native_layer_copy import capture

        layer = self._object(layer_id)
        if isinstance(layer, (_PendingLayer, _PendingBackground)):
            return None
        if layer.isService or layer.isMaskLayer or layer.autoLayer:
            return None
        return capture(self, layer)

    def append_layer(self, glyph_id, master_id, name, snapshot):
        from .native_layer_copy import append

        return append(self, glyph_id, master_id, name, snapshot)

    def _auxiliary_layer(self, glyph_id, token):
        key = self._object_keys.get(token)
        if (
            key is None
            or key[1:3] != ("layer", glyph_id)
            or not isinstance(key[3], tuple)
            or len(key) != 4
        ):
            raise StaleNativeObject(token)
        if self._keys.get(key) != token:
            return None
        glyph = self._object(glyph_id)
        package = self._object(self._parents[glyph_id])
        master_layers = self._master_layer_ids(glyph, package.masters)
        for layer in glyph.layers:
            if (
                layer.id == key[3][1]
                and layer.isValid
                and not layer.isService
                and not layer.isMaskLayer
                and layer.id not in master_layers
            ):
                self._objects[token] = layer
                return layer
        self._invalidate(token)
        background = self._keys.get(key + ("background",))
        if background is not None:
            self._invalidate(background)
        return None

    def layer(self, glyph_id: str, master_id: str) -> LayerInfo:
        glyph = self._object(glyph_id)
        if master_id not in self._master_names:
            layer = self._auxiliary_layer(glyph_id, master_id)
            if layer is None:
                raise StaleNativeObject(master_id)
            return self._read_layer(
                self._parents[glyph_id],
                layer,
                self._layer_masters[master_id],
                glyph_id,
                layer_key=self._object_keys[master_id][3],
            )
        self._object(master_id)
        font_id = self._parents[glyph_id]
        if self._parents[master_id] != font_id:
            raise UnsupportedCapability("Master belongs to a different document")
        name = self._master_names[master_id]
        layer = glyph.findLayer(name)
        if layer is None or not layer.isValid:
            layer = _PendingLayer(name)
        return self._read_layer(font_id, layer, master_id, glyph_id)

    def background_layer(self, layer_id):
        foreground = self._object(layer_id)
        layer = (
            None
            if isinstance(foreground, _PendingLayer)
            else foreground.getMaskLayer(False)
        )
        if layer is None or not layer.isValid:
            layer = _PendingBackground(layer_id)
        glyph_id = self._parents[layer_id]
        return self._read_layer(
            self._parents[glyph_id],
            layer,
            self._layer_masters[layer_id],
            glyph_id,
            background=True,
            layer_key=self._object_keys[layer_id][3],
        )

    def clear_background_layer(self, layer_id):
        foreground = self._object(layer_id)
        if isinstance(foreground, _PendingLayer):
            return
        mask = foreground.getMaskLayer(False)
        if mask is None or not mask.isValid:
            return
        self._require_editable_layer(layer_id)
        glyph_id = self._parents[layer_id]
        glyph = self._object(glyph_id)
        self._prepare_layer(layer_id)
        mask_id = mask.id
        glyph.removeLayer(mask)
        # The glyph/foreground batch now owns removal; never publish a deleted
        # mask wrapper from edits earlier in the same group.
        self._changed.pop(("layer", mask_id), None)
        self._prepared.pop(("layer", mask_id), None)
        key = self._object_keys[layer_id] + ("background",)
        token = self._keys.get(key)
        if token is not None:
            self._invalidate(token)
        self._touch_layer(layer_id)

    def validate_collection(self, layer_id, field, infos):
        self._require_editable_layer(layer_id)
        from .bulk import validate_infos

        glyph_id = self._parents[layer_id]
        package = self._object(self._parents[glyph_id])
        validate_infos(field, infos, lambda name: package.findName(name) is not None)
        if field in ("paths", "shapes"):
            self._node_hint_survivors(layer_id)
        for info in infos:
            if isinstance(info, ComponentInfo):
                self._tool_font(self._parents[glyph_id], "GSLayer.components.append")
                self._resolve_tool("set_glyph", "GSLayer.components.append")
                if self._object_keys[layer_id][-1] == "background":
                    raise UnsupportedCapability(
                        "Mask component creation is not mapped",
                        capability="GSLayer.background.components",
                    )
                if info.transform[:4] != (1, 0, 0, 1):
                    raise UnsupportedCapability(
                        "Scaled/rotated component creation is not mapped",
                        capability="GSComponent.transform",
                    )
            if isinstance(info, PathInfo):
                for node in info.nodes:
                    self._check_connection(node.connection)
                if any(n.type == "qcurve" for n in info.nodes) and any(
                    n.type == "curve" for n in info.nodes
                ):
                    raise UnsupportedCapability(
                        "Mixed quadratic/cubic contours", capability="GSPath.nodes"
                    )

    def path_grouping(self, layer_id):
        """Remember contour counts, without retaining history-owned shapes."""
        layer = self._object(layer_id)
        if isinstance(layer, _PendingLayer):
            return ()
        return tuple(len(s.contours) for s in layer.shapes if not s.isComponent)

    def restore_path_grouping(self, layer_id, groups):
        """Combine newly constructed identity-transform paths into old groups.

        Components and baseline shapes are never mutated. If the replacement
        has fewer paths, preserve the groups that still fit; surplus paths form
        one new group.
        """
        self._require_editable_layer(layer_id)
        self._require_history_scope(tokens=(layer_id,))
        layer = self._object(layer_id)
        self._native()
        paths = [s for s in layer.shapes if not s.isComponent]
        offset = 0
        for size in (*groups, len(paths)):
            batch = paths[offset : offset + size]
            if not batch:
                break
            first = batch[0]
            for shape in batch[1:]:
                for contour in shape.contours:
                    first.addContour(contour, True)
                layer.removeShape(shape)
            offset += len(batch)
        self._touch_layer(layer_id)

    def _node_hint_survivors(self, layer_id, contour=None):
        """Resolve hint wrappers and links before checkpointing any mutation.

        Only center/vector are Python-bound (pyflSnapLineImpl / fontlab.pyi).
        The C++ extension link is inaccessible: extension-only links cannot
        be cleaned up here. Unlinked coordinate hints and guides survive.
        """
        ids = set() if contour is None else {node.id for node in contour.nodes()}
        document = self._object_keys[layer_id][0]
        tokens = {self._keys.get((document, "node", identity)) for identity in ids} - {
            None
        }

        def removed(node):
            identity = getattr(node, "id", None)
            return identity in ids or (
                self._history_aliases.get((document, "node", identity)) in tokens
            )

        layer = self._object(layer_id)
        if isinstance(layer, _PendingLayer):
            return []
        wanted = []
        for item in layer.guidelines:
            guide = self._guide_line(item)
            if guide.isHint and any(
                removed(getattr(guide, role)) for role in ("center", "vector")
            ):
                continue
            wanted.append(item)
        return wanted

    def _drop_node_hints(self, layer_id, wanted):
        layer = self._object(layer_id)
        if len(wanted) != len(layer.guidelines):
            layer.guidelines = wanted

    @contextmanager
    def stage_collection(self, layer_id, field, infos):
        """Construct detached input values before removing any live members."""
        self._require_editable_layer(layer_id)
        factories = {
            PathInfo: self._build_path,
            AnchorInfo: self._build_anchor,
            GuideInfo: self._new_guide,
            ComponentInfo: lambda info: self._build_component(layer_id, info),
        }
        staged = {}
        for info in infos:
            factory = factories.get(type(info))
            if factory is not None:
                staged.setdefault((layer_id, type(info)), deque()).append(
                    (info, factory(info))
                )
        previous = getattr(self, "_staged_native_values", None)
        self._staged_native_values = staged
        try:
            yield
        finally:
            self._staged_native_values = previous

    def _staged_native(self, layer_id, info, factory):
        self._require_editable_layer(layer_id)
        staged = getattr(self, "_staged_native_values", None)
        values = None if staged is None else staged.get((layer_id, type(info)))
        if values and values[0][0] == info:
            return values.popleft()[1]
        return factory(info)

    def _stage_shapes(self, layer_id, *, force=False):
        layer = self._object(layer_id)
        if isinstance(layer, _PendingLayer):
            return ()
        return tuple(
            (
                shape,
                shape.clone() if force or shape.id not in self._owned_shapes else None,
            )
            for shape in layer.shapes
        )

    def prepare_collection(self, layer_id, field, *, state=None):
        """Stage detached geometry, checkpoint originals, then attach clones."""
        self._require_editable_layer(layer_id)
        if field not in ("paths", "components", "shapes"):
            return
        layer = self._object(layer_id)
        if isinstance(layer, _PendingLayer):
            return
        self._require_history_scope(tokens=(layer_id,))
        if field in ("paths", "shapes"):
            self._node_hint_survivors(layer_id)
        glyph_id = self._parents[layer_id]
        package = self._object(self._parents[glyph_id])
        self._native()
        staged = (
            self._stage_shapes(layer_id, force=True)
            if state is None
            else tuple(
                (shape, shape.clone() if clone is None else clone)
                for shape, clone in state[5]
            )
        )
        if tuple(s.id for s, _ in staged) != tuple(s.id for s in layer.shapes):
            raise UnsupportedCapability(
                "Layer shapes changed after collection staging",
                capability="GSLayer.shapes",
            )
        package.checkInitHistoryState(0)
        self._prepare_layer(layer_id)
        for shape, clone in staged:
            self._own_shape(layer_id, shape, force=True, clone=clone)

    def snapshot_collection(self, layer_id, *, stage=False):
        """Capture rollback bindings and stage clones without touching the layer.

        Collection preparation attaches fresh working clones before mutation,
        including shapes already owned by an enclosing Undo group. Originals
        stay attached until preparation records the history baseline.
        """
        layer = self._object(layer_id)
        from .collection_state import snapshot_bindings

        bindings = snapshot_bindings(self, layer_id, tuple(_LIVE_BACKENDS))
        return (
            layer,
            () if isinstance(layer, _PendingLayer) else tuple(layer.shapes),
            () if isinstance(layer, _PendingLayer) else tuple(layer.anchors),
            () if isinstance(layer, _PendingLayer) else tuple(layer.guidelines),
            bindings,
            tuple(
                (
                    shape,
                    shape.clone() if stage or shape.id in self._owned_shapes else None,
                )
                for shape in (() if isinstance(layer, _PendingLayer) else layer.shapes)
            ),
            self._revision,
        )

    def restore_collection(self, layer_id, state):
        self._require_editable_layer(layer_id)
        from .collection_state import restore_bindings, snapshot_bindings

        original, shapes, anchors, guides, bindings = state[:5]
        layer = self._objects[layer_id]
        if (
            len(state) > 6
            and self._revision == state[6]
            and layer is original
            and (
                isinstance(layer, _PendingLayer)
                or (
                    tuple(s.id for s in layer.shapes) == tuple(s.id for s in shapes)
                    and tuple(a.id for a in layer.anchors)
                    == tuple(a.id for a in anchors)
                    and tuple(g.id for g in layer.guidelines)
                    == tuple(g.id for g in guides)
                )
            )
            and snapshot_bindings(self, layer_id, tuple(_LIVE_BACKENDS)) == bindings
        ):
            return  # pure staging/eligibility refusal: nothing to restore or publish
        self._native()  # refuse a missing host before changing recovery state
        if isinstance(original, _PendingLayer):
            if not isinstance(layer, _PendingLayer):
                native_id = layer.id
                self._object(self._parents[layer_id]).removeLayer(layer)
                self._changed.pop(("layer", native_id), None)
                self._prepared.pop(("layer", native_id), None)
            self._objects[layer_id] = original
            self._pending_layer_updates.discard(layer_id)
        else:
            layer.removeAllShapes()
            layer.addShapes(list(shapes))
            layer.clearAnchors()
            for anchor in anchors:
                layer.addAnchor(anchor)
            if tuple(g.id for g in layer.guidelines) != tuple(g.id for g in guides):
                layer.guidelines = list(guides)
        restore_bindings(bindings)
        if isinstance(original, _PendingLayer):
            self._touch(("glyph", self._object(self._parents[layer_id])))
        else:
            self._touch_layer(layer_id)

    def layer_metrics_key(self, layer_id, side):
        from .metrics_keys import from_native

        attr = {
            "left": "metricsLeft",
            "right": "metricsRight",
            "width": "metricsWidth",
        }[side]
        layer = self._object(layer_id)
        native = "" if isinstance(layer, _PendingLayer) else getattr(layer, attr) or ""
        source = self._metric_sources.get((layer_id, side))
        if source is not None and source[0] == native:
            return source[1] or None
        return from_native(native, side)

    def set_layer_metrics_key(self, layer_id, side, value):
        from .metrics_keys import to_native

        wanted = to_native(value, side)
        attr = {
            "left": "metricsLeft",
            "right": "metricsRight",
            "width": "metricsWidth",
        }[side]
        layer = self._writable_layer(layer_id)
        self._prepare_layer(layer_id)
        setattr(layer, attr, wanted)
        self._metric_sources[layer_id, side] = wanted, value
        self._touch_layer(layer_id)

    def _master_read(self, master_id, read):
        package, name = self._object(master_id), self._master_names[master_id]
        current = package.master
        if name != current:
            package.setMaster(name)
        try:
            return read(package)
        finally:
            if name != current:
                package.setMaster(current)

    def _guide_line(self, guide):
        # Some builds return a generic wrapper which already exposes the
        # underlying guide's properties. Reconstructing it can fail overload
        # conversion, and is unnecessary for reads or edits.
        if type(guide).__name__ != "flObject" or all(
            hasattr(guide, field) for field in ("centerPoint", "angle", "isHint")
        ):
            return guide
        try:
            return self._native().flGuideLine(guide)
        except (TypeError, ValueError) as error:
            raise UnsupportedCapability(
                "FontLab cannot recover this generic guideline wrapper",
                capability="GSGuide.nativeWrapper",
            ) from error

    def set_guide(self, guide_id, **changes):
        guide = self._guide_line(self._object(guide_id))
        parent_id = self._parents[guide_id]
        layer = self._object_keys[parent_id][1] == "layer"
        package = None if layer else self._object(parent_id)
        transform = None
        if "x" in changes or "y" in changes:
            point = guide.centerPoint
            dx = changes.get("x", point.x()) - point.x()
            dy = changes.get("y", point.y()) - point.y()
            transform = _import_qtgui().QTransform(1.0, 0.0, 0.0, 1.0, dx, dy)
        if layer:
            self._prepare_layer(parent_id)
        else:
            self._prepare(("font", package))

        def mutate(_package=None):
            if transform is not None:
                guide.applyTransform(transform)
            if "angle" in changes:
                guide.angle = changes["angle"]
            if "name" in changes:
                guide.name = changes["name"]

        if layer:
            mutate()
        else:
            self._master_read(parent_id, mutate)
        if layer:
            self._touch_layer(parent_id)
        else:
            self._touch(("font", package))

    def _new_guide(self, guide):
        # Avoid overloaded positional constructor conversion in PythonQt.
        item = self._native().flGuideLine()
        item.angle, item.name = float(guide.angle), guide.name
        item.applyTransform(
            _import_qtgui().QTransform(1.0, 0.0, 0.0, 1.0, guide.x, guide.y)
        )
        return item

    def append_master_guide(self, master_id, guide):
        self._object(master_id)
        # flPackage.guidelines is read-only. Its guidelinesHost pointer
        # conversion does not retain the native pointer in the available
        # pygate source; dereferencing it is unsafe. flLayer.appendGuidelines
        # cannot append a font-level guide.
        raise UnsupportedCapability(
            "No safe native master-guideline insertion binding is available",
            capability="GSFontMaster.guides.append",
        )

    def update_layer_metrics(self, layer_id):
        layer = self._writable_layer(layer_id)
        if not any(
            self.layer_metrics_key(layer_id, side)
            for side in ("left", "right", "width")
        ):
            return
        glyph = self._object(self._parents[layer_id])
        self.prepare_collection(layer_id, "shapes")
        with self._metrics_layer_scope(glyph, layer):
            try:
                glyph.updateSidebearings(False)
            finally:
                self._touch_layer(layer_id)

    @staticmethod
    def _metrics_layer_scope(glyph, layer):
        from contextlib import contextmanager

        @contextmanager
        def enter():
            previous = glyph.activeLayer
            try:
                glyph.activeLayer = layer
                yield
            finally:
                glyph.activeLayer = previous

        return enter()

    def master_guides(self, master_id):
        def read(package):
            document = self._parents[master_id]
            return tuple(
                GuideInfo(
                    self._register((document, "guide", g.id), g, master_id),
                    g.centerPoint.x(),
                    g.centerPoint.y(),
                    g.angle,
                    g.name,
                )
                for raw in package.guidelines
                for g in (self._guide_line(raw),)
                if not g.isHint
            )

        return self._master_read(master_id, read)

    def master_zones(self, master_id):
        return self._master_read(
            master_id,
            lambda p: tuple(
                (float(zone.position), abs(float(zone.width)) * sign)
                for zones, sign in ((p.ps_zonesT, 1), (p.ps_zonesB, -1))
                for zone in zones
            ),
        )

    def set_master_zone(self, master_id, index, position, size):
        raise UnsupportedCapability(
            "Native master zone mutation is not mapped",
            capability="GSFontMaster.alignmentZones",
        )

    def glyph_selected(self, font_id, glyph_id):
        raise UnsupportedCapability(
            "Font View selection has no mapped accessor; flGlyphInfo.isSelected is a text-item flag",
            capability="GSGlyph.selected",
        )

    def set_glyph_selected(self, font_id, glyph_id, value):
        self.glyph_selected(font_id, glyph_id)

    def path_attributes(self, path_id):
        raise UnsupportedCapability(
            "Glyphs path styling attributes are not mapped to native shape styles",
            capability="GSPath.attributes",
        )

    def set_path_attributes(self, path_id, values):
        self.path_attributes(path_id)

    def anchor_selected(self, anchor_id):
        self._object(anchor_id)
        raise UnsupportedCapability(
            "R054: flPinPoint stores selection in private _selected; its Python "
            "binding exposes neither isSelected nor setSelected. Object flags "
            "and fgAnchor data/mark are not editor selection; flCanvas.selection "
            "exposes visual items without a pinpoint identity accessor",
            capability="GSAnchor.selected",
            location=caller_location(),
        )

    def set_anchor_selected(self, anchor_id, value):
        self.anchor_selected(anchor_id)  # same precise native limitation on writes

    def component_selected(self, component_id):
        return bool(self._object(component_id).selected)

    def set_component_selected(self, component_id, value):
        self._object(component_id).selected = bool(value)
        self._revision += 1

    def guide_selected(self, guide_id):
        self._object(guide_id)
        raise UnsupportedCapability(
            "GSGuide selection has no public native selected field",
            capability="GSGuide.selected",
        )

    def set_guide_selected(self, guide_id, value):
        self.guide_selected(guide_id)

    def set_component_transform(self, component_id, transform):
        shape = self._object(component_id)
        layer_id = self._parents[component_id]
        self._require_editable_layer(layer_id)
        matrix = _import_qtgui().QTransform(*transform)
        shape = self._own_shape(layer_id, shape)
        shape.transform = matrix
        self._touch_layer(layer_id)

    def set_anchor_name(self, anchor_id, name):
        anchor = self._object(anchor_id)
        layer_id = self._parents[anchor_id]
        self._prepare_layer(layer_id)
        anchor.name = name
        self._touch_layer(layer_id)

    def component_bounds(self, component_id):
        shape = self._object(component_id)
        rect = shape.inkBox(_import_qtgui().QTransform())
        if rect is None or rect.isNull():
            return None
        return rect.x(), rect.y(), rect.width(), rect.height()

    def set_component_position(self, component_id, x, y):
        shape = self._object(component_id)
        layer_id = self._parents[component_id]
        if self._object(layer_id).autoLayer:
            raise UnsupportedCapability(
                "Moving components in native auto layers needs a mapped glyph-only edit",
                capability="GSComponent.position.autoLayer",
            )
        t = shape.transform
        matrix = _import_qtgui().QTransform(
            t.m11(), t.m12(), t.m21(), t.m22(), float(x), float(y)
        )
        shape = self._own_shape(layer_id, shape)
        shape.transform = matrix
        self._touch_layer(layer_id)

    def set_component_name(self, component_id: str, name: str) -> None:
        from .component_edits import rename_native

        rename_native(self, component_id, name)

    def decompose_component(
        self, layer_id: str, component_id: str, *, on_detach: Callable[[], None]
    ) -> None:
        from .component_edits import decompose_native

        decompose_native(self, layer_id, component_id, on_detach)

    def remove_component(self, layer_id, component_id):
        layer, shape = self._object(layer_id), self._object(component_id)
        if self._parents[component_id] != layer_id:
            raise ValueError("Component does not belong to layer")
        self._prepare_layer(layer_id)
        layer.removeShape(shape)
        self._invalidate(component_id)
        self._touch_layer(layer_id)

    def remove_guide(self, layer_id, guide_id):
        layer, guide = self._object(layer_id), self._object(guide_id)
        if self._parents[guide_id] != layer_id:
            raise ValueError("Guide does not belong to layer")
        # Resolve the native value list before checkpointing, then reassign it
        # whole, retaining diagonal guides and PostScript hints.
        wanted = [item for item in layer.guidelines if item.id != guide.id]
        self._prepare_layer(layer_id)
        try:
            layer.guidelines = wanted
        except (AttributeError, TypeError) as error:
            self._touch_layer(layer_id)
            raise UnsupportedCapability(
                "FontLab cannot assign this layer's guidelines",
                capability="GSLayer.guides",
                location=caller_location(),
            ) from error
        self._touch_layer(layer_id)
        if [item.id for item in layer.guidelines] != [item.id for item in wanted]:
            raise UnsupportedCapability(
                "FontLab did not store the requested guidelines",
                capability="GSLayer.guides",
                location=caller_location(),
            )
        self._invalidate(guide_id)

    def _writable_layer(self, layer_id):
        """Return the native layer, creating a pending master layer first."""
        self._require_editable_layer(layer_id)
        self._require_history_scope(tokens=(layer_id,))
        layer = self._object(layer_id)
        if isinstance(layer, _PendingBackground):
            foreground_id = layer.foreground_id
            foreground = self._writable_layer(foreground_id)
            self._prepare_layer(foreground_id)
            layer = foreground.getMaskLayer(True)
            if layer is None or not layer.isValid:
                raise UnsupportedCapability(
                    "FontLab could not create the mask layer",
                    capability="GSLayer.background",
                )
            self._objects[layer_id] = layer
            self._touch_layer(foreground_id)
        elif isinstance(layer, _PendingLayer):
            glyph = self._object(self._parents[layer_id])
            self._prepare(("glyph", glyph))
            layer = glyph.findLayerCreate(layer.master_name)
            self._objects[layer_id] = layer
            self._touch_layer(layer_id)
        return layer

    def _lib_owner(self, id, create=False):
        kind = self._object_keys.get(id, (None, None))[1]
        if kind not in LIB_ATTRIBUTES:
            raise UnsupportedCapability(
                "Only fonts, glyphs and layers have native libs", capability="lib"
            )
        obj = (
            self._writable_layer(id) if create and kind == "layer" else self._object(id)
        )
        if kind == "font" and obj.id in self._owned_fonts:
            # packageLib may reach the unsafe fgPackage getter of an unregistered package.
            raise UnsupportedCapability(
                "Font lib of an unregistered owned package", capability="font.lib"
            )
        return kind, obj

    def lib(self, id: str) -> dict:
        if id in self._master_names:
            return self._master_read(id, lambda package: _plain(package.masterLib))
        kind, obj = self._lib_owner(id)
        if isinstance(obj, _PendingLayer):
            return {}
        return _plain(getattr(obj, LIB_ATTRIBUTES[kind]))

    def set_lib(self, id: str, data: dict) -> None:
        """Assign the whole lib, read it back, and revert if anything was lost."""
        if id in self._master_names:
            self._require_history_scope(("font", self._object(id)))

            def write(package):
                before = _plain(package.masterLib)
                wanted = _plain(data)
                if before == wanted:
                    return
                self._prepare(("font", package))
                try:
                    package.masterLib = wanted
                    if _plain(package.masterLib) != wanted:
                        raise UnsupportedCapability(
                            "Master lib did not retain values",
                            capability="GSFontMaster.userData",
                        )
                except BaseException as error:
                    try:
                        package.masterLib = before
                        if _plain(package.masterLib) != before:
                            raise RuntimeError(
                                "Master lib recovery verification failed"
                            )
                    except BaseException as recovery:
                        failure = PartialFailure(
                            f"Master lib write failed and recovery failed: {recovery}",
                            capability="GSFontMaster.userData.rollback",
                        )
                        failure.errors = (error, recovery)
                        raise failure from recovery
                    raise
                self._touch(("font", package))

            return self._master_read(id, write)
        wanted = _plain(data)
        kind, obj = self._lib_owner(id)
        attr = LIB_ATTRIBUTES[kind]
        before = {} if isinstance(obj, _PendingLayer) else _plain(getattr(obj, attr))
        if kind == "layer":
            obj = self._writable_layer(id)
            self._prepare_layer(id)
        else:
            self._prepare((kind, obj))
        setattr(obj, attr, wanted)
        stored = _plain(getattr(obj, attr))
        if stored != wanted:
            setattr(obj, attr, before)
            lost = sorted(k for k in wanted if stored.get(k) != wanted[k])
            raise UnsupportedCapability(
                f"FontLab {kind} lib did not store these keys faithfully: {lost}",
                capability=f"{kind}.lib",
            )
        if kind == "layer":
            self._touch_layer(id)
        else:
            self._touch((kind, obj))

    def features(self, font_id: str) -> FeaturesInfo:
        layout = self._fontgate_font(self._object(font_id)).features
        return FeaturesInfo(
            layout.get_prefix() or "",
            # fgOTLayout documents keys(), not iteration.
            tuple(FeatureInfo(t, layout.get_feature(t)) for t in layout.keys()),  # noqa: SIM118
        )

    def _font_write(self, font_id, capability):
        """The package of a font-level write (features, classes, axes, instances).

        Undo (native fact, glyport-r020/probe-font-writes-run3 and
        probe-axes-instances-run1): notifying the package before and after the
        change gives one Edit > Undo step that restores it, and Redo reapplies it.
        Owned unregistered packages are refused: notifying them is unsafe and
        their fgPackage getter crashes FontLab.
        """
        package = self._object(font_id)
        if package.id in self._owned_fonts:
            raise UnsupportedCapability(
                "Font-level writes need a workspace-registered font",
                capability=capability,
            )
        return package

    def set_feature(self, font_id: str, name: str, code: str | None) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("A feature needs a tag name")
        if code is not None and not isinstance(code, str):
            raise TypeError("Feature code must be a string")
        package = self._font_write(font_id, "GSFont.features")
        layout = package.fgPackage.features
        self._prepare(("font", package))
        if code is None:
            layout.remove(name)
        else:
            layout.set_feature(name, code)
        self._touch(("font", package))

    def set_feature_prefix(self, font_id: str, code: str) -> None:
        if not isinstance(code, str):
            raise TypeError("Prefix code must be a string")
        package = self._font_write(font_id, "GSFont.featurePrefixes")
        self._prepare(("font", package))
        package.fgPackage.features.set_prefix(code)
        self._touch(("font", package))

    @staticmethod
    def _native_index(items, index, what):
        if not 0 <= index < len(items):
            raise StaleNativeObject(f"{what} {index}")
        return index

    def add_axis(self, font_id: str, axis: AxisInfo) -> str:
        """Native fact (glyport-r020/probe-axes-instances-run1): flAxis(name, tag,
        short name) and addAxis; masters read the default coordinate until set."""
        package = self._font_write(font_id, "GSFont.axes.append")
        self._check_axis_unique(package.axes, None, axis, "GSFont.axes.append")
        short = AXIS_SHORT_NAMES.get(axis.tag, axis.tag)
        native = self._native().flAxis(axis.name, axis.tag, short)
        native.hidden = axis.hidden
        self._prepare(("font", package))
        package.addAxis(native)
        self._touch(("font", package))
        return axis.tag or axis.name

    @staticmethod
    def _check_axis_unique(axes, index, axis, capability):
        for i, other in enumerate(axes):
            if i != index and (other.name == axis.name or other.tag == axis.tag):
                raise UnsupportedCapability(
                    f"Another axis is named {other.name} or tagged {other.tag}",
                    capability=capability,
                )

    def remove_axis(self, font_id: str, index: int) -> None:
        """Native fact (probe-axes-instances-run1): flPackage has no removeAxis;
        assigning the axes list without the axis removes it."""
        package = self._font_write(font_id, "GSFont.axes.remove")
        axes = list(package.axes)
        del axes[self._native_index(axes, index, "axis")]
        self._prepare(("font", package))
        package.axes = axes
        self._touch(("font", package))

    def set_axis(self, font_id: str, index: int, axis: AxisInfo) -> None:
        package = self._font_write(font_id, "GSAxis")
        axes = list(package.axes)
        native = axes[self._native_index(axes, index, "axis")]
        self._check_axis_unique(axes, index, axis, "GSAxis")
        self._prepare(("font", package))
        native.name, native.tag, native.hidden = axis.name, axis.tag, axis.hidden
        package.axes = axes
        self._touch(("font", package))

    def _location(self, package, old, coordinates, capability):
        """A new flLocation: ``coordinates`` by axis short name, plus every entry
        of ``old`` that belongs to no current axis (a removed axis, extra data).

        Native facts (glyport-r020/probe-review-fixes-run1,
        probe-location-keys-run1): flLocation is not iterable; its repr lists
        its keys lowercased with rounded values, lookups are case-sensitive and
        values may be (x, y) tuples; flLocation() without arguments raises
        (review-run1-FAILED). An entry whose stored key cannot be found is
        refused rather than dropped.
        """
        axes = list(self._axes(package))
        if len(coordinates) != len(axes):
            raise ValueError(f"Expected {len(axes)} axis coordinates")
        keys = [] if old is None else _location_keys(old)
        if keys is None:
            raise UnsupportedCapability(
                "This location's entries cannot be listed", capability=capability
            )
        own = {k.lower() for a in axes for k in (a.shortName, a.name, a.tag) if k}
        other = [key for key in keys if key not in own]
        kept = _location_spellings(old, other) if other else {}
        if kept is None:
            raise UnsupportedCapability(
                "This location has entries whose exact keys cannot be recovered "
                "(an unusual or ambiguous capitalisation)",
                capability=capability,
            )
        new = {a.shortName: float(v) for a, v in zip(axes, coordinates, strict=True)}
        return self._native().flLocation({**kept, **new})

    def set_master_axes(self, master_id: str, axes) -> None:
        """Native fact (glyport-r020/probe-locations-run1): flLocation(dict) takes
        axis names or short names; FontLab's own setLocation uses short names."""
        font_id = self._parents[master_id]
        package = self._font_write(font_id, "GSFontMaster.axes")
        name = self._master_names[master_id]
        location = self._location(
            package, package.location(name), tuple(axes), "GSFontMaster.axes"
        )
        self._prepare(("font", package))
        package.setLocation(location, name)
        self._touch(("font", package))

    def _store_instances(self, font_id, capability, change):
        """Apply ``change(package, copies)`` and assign the list back in one call.

        Native facts (glyport-r020/probe-axes-instances-run1,
        probe-review-fixes-run1): flPackage.instances hands out copies, so
        attribute edits on them do not stick, and assigning a list stores it.
        On a failed assignment the original list is assigned again; the change
        notification is sent either way.
        """
        package = self._font_write(font_id, capability)
        original = list(package.instances)
        copies = list(package.instances)
        change(package, copies)
        self._prepare(("font", package))
        try:
            package.instances = copies
        except Exception:
            package.instances = original
            raise
        finally:
            self._touch(("font", package))

    def add_instance(self, font_id: str, instance: InstanceInfo) -> None:
        def change(package, copies):
            location = self._location(package, None, instance.axes, "GSInstance")
            native = self._native().flInstance(instance.name, instance.name, location)
            native.exportable = instance.exports
            copies.append(native)

        self._store_instances(font_id, "GSFont.instances.append", change)

    def set_instance(self, font_id: str, index: int, changes: dict) -> None:
        unknown = set(changes) - {"name", "exports", "axes"}
        if unknown:
            raise ValueError(f"Unknown instance fields: {sorted(unknown)}")

        def change(package, copies):
            native = copies[self._native_index(copies, index, "instance")]
            if "axes" in changes:
                native.location = self._location(
                    package, native.location, tuple(changes["axes"]), "GSInstance.axes"
                )
            if "name" in changes:
                if native.tsn == native.name:  # a style name that followed the name
                    native.tsn = changes["name"]
                native.name = changes["name"]
            if "exports" in changes:
                native.exportable = bool(changes["exports"])

        self._store_instances(font_id, "GSInstance", change)

    def remove_instance(self, font_id: str, index: int) -> None:
        def change(package, copies):
            del copies[self._native_index(copies, index, "instance")]

        self._store_instances(font_id, "GSFont.instances.remove", change)

    def _ot_groups(self, font_id, name, capability):
        """The fgGroups of a writable font, refusing a non-OpenType group ``name``."""
        package = self._font_write(font_id, capability)
        groups = package.fgPackage.groups
        if groups.has_key(name) and not groups[name].isFeaGroup():  # noqa: W601 - native API
            raise UnsupportedCapability(
                f"{name} is a FontLab kerning or metrics group, not an OpenType class",
                capability=capability,
            )
        return package, groups

    def set_class(self, font_id: str, name: str, glyphs) -> None:
        """Native fact (glyport-r020/probe-font-writes-run3): fgGroups has no item
        assignment; fromDict(all groups plus the new one) adds a class and leaves
        FontLab's per-master kerning classes untouched; remove(name) deletes it."""
        if not isinstance(name, str) or not name:
            raise ValueError("A class needs a name")
        if glyphs is not None and not all(isinstance(g, str) and g for g in glyphs):
            raise TypeError("Class members must be glyph names")
        package, groups = self._ot_groups(font_id, name, "GSFont.classes")
        current = None
        if glyphs is not None:
            members = list(glyphs)
            current = dict(groups.asDict())
            current[name] = self._fontgate().fgGroup(
                name, members, "FeaClassGroupMode", members[0] if members else ""
            )
        self._prepare(("font", package))
        if glyphs is None:
            groups.remove(name)
        else:
            groups.fromDict(current)
        self._touch(("font", package))

    def rename_class(self, font_id: str, name: str, new_name: str) -> None:
        if not isinstance(new_name, str) or not new_name:
            raise ValueError("A class needs a name")
        package, groups = self._ot_groups(font_id, name, "GSClass.name")
        if groups.has_key(new_name):  # noqa: W601 - native API
            raise UnsupportedCapability(
                f"A group named {new_name} exists", capability="GSClass.name"
            )
        self._prepare(("font", package))
        groups.rename(name, new_name)
        self._touch(("font", package))

    def _require_history_scope(
        self, *entries: tuple[str, object], tokens: Iterable[str] = (),
        creates: bool = False,
    ) -> None:
        """Check prospective and retained Glyport owners with public App guards."""
        from .history_scope import disclose_pending, require_scope

        require_scope(self, entries, tokens=tokens, creates=creates)
        disclose_pending(self)

    def _prepare(self, *entries):
        """Notify the pre-change state of the first entry's object once per group.

        Native fact (glyport-model/probe_undo_first_edit.json): FontLab stores an
        object's state at each notification and Undo restores the previous
        stored one, so without this a script's first edit of a glyph cannot be
        undone. The extra Undo step it adds restores the same state.
        The entries go out together whenever the first one is not yet prepared
        (a second layer of a glyph is prepared as [layer, glyph] too), and are
        recorded only after the notification succeeded, so a retry resends.
        """
        self._require_history_scope(*entries)
        kind, first = entries[0]
        if (kind, first.id) in self._prepared:
            return
        batch = {(k, o.id): o for k, o in entries}
        self._notify(self._undo_name or "Glyport edit", batch)
        self._prepared.update(batch)
        # A synchronous notification callback can change focus. Keep its valid
        # checkpoint, but recheck before returning to a forward writer.
        self._require_history_scope(*entries)

    def _own_shape(self, layer_id, shape, *, force=False, clone=None):
        """Copy-on-write for in-place edits: FontLab's history keeps references
        to shapes, so a node or contour changed in place is changed in the stored
        undo state too and Undo cannot restore it (native probe
        glyport-matrix/probe_undo_cloned_shape.json). Construct the detached clone
        before notification, then record the still-attached original and swap
        the clone in at the same index. Tokens follow only after attachment.
        Once per shape and notification cycle, except when a collection
        checkpoint forces a fresh working clone to protect saved geometry."""
        self._require_editable_layer(layer_id)
        self._require_history_scope(tokens=(layer_id,))
        if not force and shape.id in self._owned_shapes:
            self._prepare_layer(layer_id)
            return shape
        layer = self._object(layer_id)
        index = next(i for i, s in enumerate(layer.shapes) if s.id == shape.id)
        clone = shape.clone() if clone is None else clone
        self._copy_clone_connections(shape, clone)
        self._prepare_layer(layer_id)
        self._retain_component_history(layer_id, shape)
        layer.removeShape(shape)
        inserted = layer.insertShape(index, clone)
        clone = inserted if inserted is not None else clone
        document = self._object_keys[layer_id][0]
        package_id = self._object_keys[document][2]
        for backend in list(
            _LIVE_BACKENDS
        ):  # scripts and plugins hold their own tokens
            peer_document = backend._keys.get((package_id, "font", package_id))
            if peer_document is not None:
                backend._follow_clone(peer_document, shape, clone)
        self._owned_shapes.add(clone.id)
        return clone

    def _retain_component_history(self, layer_id, shape):
        """Keep detached component dependencies in the existing prepared batch.

        FontLab 9784 needs the ORIGINAL shape/data/builder before layer/glyph
        in the final notification to restore a component on Undo (fl#7641).
        Reading the builder after detachment/publication can already be too late.
        These are native history objects, never public proxy bindings.
        """
        if shape.isComponent:
            key = ("component_history", layer_id, shape.id)
            if key not in self._prepared:
                data = shape.shapeData
                self._prepared[key] = shape, data, data.builder

    def _copy_clone_connections(self, shape, clone):
        # ShapeDataImpl::cloneCustom calls contour.checkSmooth(), which derives
        # Smooth/G2 from geometry and discards intentional flag-only state.
        # Restore only connection bits on the detached clone, in native order,
        # before checkpoint/attachment. Never alter the history-owned source.
        if shape.isComponent:
            return
        mask = self._native().flNode.NodeKind["SmoothMask"]
        for source, target in zip(shape.contours, clone.contours, strict=True):
            for old, new in zip(source.nodes(), target.nodes(), strict=True):
                new.nodeState = (new.nodeState & ~mask) | (old.nodeState & mask)

    def _follow_clone(self, document, shape, clone):
        """Rebind component, path and node tokens from ``shape`` to ``clone``."""
        if shape.isComponent:
            self._rebind(
                (document, "component", shape.id),
                (document, "component", clone.id),
                clone,
            )
            return
        for old_contour, new_contour in zip(
            shape.contours, clone.contours, strict=True
        ):
            path_id = self._rebind(
                (document, "path", old_contour.id),
                (document, "path", new_contour.id),
                new_contour,
            )
            layer_id = self._parents.get(path_id)
            for old_node, new_node in zip(
                old_contour.nodes(), new_contour.nodes(), strict=True
            ):
                node_id = self._rebind(
                    (document, "node", old_node.id),
                    (document, "node", new_node.id),
                    new_node,
                )
                if node_id is not None and layer_id is not None:
                    self._node_shapes[node_id] = (clone, layer_id)

    def _rebind(self, old_key, new_key, obj):
        """Point an existing token at a replacement native object."""
        token = self._keys.pop(old_key, None)
        if token is None:
            return None
        self._history_aliases[old_key] = token
        self._history_aliases[new_key] = token
        self._keys[new_key] = token
        self._object_keys[token] = new_key
        self._objects[token] = obj
        self._revision += 1  # peer proxies must not keep pre-clone record snapshots
        return token

    def _retire_path_nodes(self, path_id):
        """Retire replaced nodes in every peer before fallible cache updates.

        Explicit collection rollback restores these bindings from its snapshot.
        """
        document, _, native_id = self._object_keys[path_id]
        package_id = self._object_keys[document][2]
        for backend in tuple(_LIVE_BACKENDS):
            peer_document = backend._keys.get((package_id, "font", package_id))
            peer_path = backend._keys.get((peer_document, "path", native_id))
            if peer_path is not None:
                for token in [
                    t for t, parent in backend._parents.items() if parent == peer_path
                ]:
                    backend._invalidate(token)

    def _shape_of(self, layer_id, contour):
        layer = self._object(layer_id)
        return next(
            s for s in layer.shapes if any(c.id == contour.id for c in s.contours)
        )

    def _require_editable_layer(self, layer_id):
        """Refuse auto layers before edits: notifying them rebuilds recipes (fl#8512).

        A mask also belongs to its foreground's edit scope. Neither an existing
        mask nor a pending mask permits bypassing an auto foreground's refusal.
        """
        layer = self._object(layer_id)
        if self._object_keys[layer_id][-1] == "background":
            glyph = self._object(self._parents[layer_id])
            foreground_key = self._object_keys[layer_id][:-1]
            foreground_id = self._keys.get(foreground_key)
            foreground = (
                self._object(layer.foreground_id)
                if isinstance(layer, _PendingBackground)
                else self._object(foreground_id)
                if foreground_id is not None
                else glyph.findLayer(self._master_names[self._layer_masters[layer_id]])
            )
            if foreground is not None and getattr(foreground, "autoLayer", False):
                layer = foreground
        if getattr(layer, "autoLayer", False):
            raise UnsupportedCapability(
                "Editing a native auto layer needs a verified glyph-only edit route",
                capability="GSLayer.autoLayer.edit",
            )
        return layer

    def _prepare_layer(self, layer_id):
        self._require_editable_layer(layer_id)
        glyph = self._objects[self._parents[layer_id]]
        self._prepare(("layer", self._objects[layer_id]), ("glyph", glyph))

    def _touch(self, *entries):
        """Record (kind, native object) changes; publish now outside an undo group."""
        # Revision counters cover a session's full record cache. Invalidate
        # every live session on metadata as well as geometry changes, even
        # before the enclosing native Undo group publishes its notification.
        for peer in tuple(_LIVE_BACKENDS):
            peer._revision += 1
        for kind, item in entries:
            self._changed[kind, item.id] = item
        self._require_history_scope(*entries)
        self._update_pending_layers()
        if self._undo_name is None:
            self._notify("Glyport edit", self._changed, post=True)
            # Keep the batch and its copy-on-write baseline if update/publication
            # fails. A subsequent write retries it instead of losing the edit.
            self._changed, self._prepared = {}, {}
            self._owned_shapes = set()
            self._history_disclosure = None

    def _commit_layer_edits(self, layer_id):
        """Refresh native layer/glyph caches at a completed layer write boundary.

        Native tools mark the layer/glyph changed before notifyGlyphUpdate.
        update() runs their model updaters without pumping UI events or exporting
        a bare fgGlyph wrapper. Node setters do not invalidate owner bounds;
        readers and hint tools must observe completed edits even inside Undo.
        """
        self._require_editable_layer(layer_id)
        self._require_history_scope(tokens=(layer_id,))
        layer = self._object(layer_id)
        glyph = self._object(self._parents[layer_id])
        for item in (layer, glyph):
            item.changed()
            if item.update() is False:
                raise NativeOperationError(
                    f"FontLab refused to update {type(item).__name__} after a layer edit",
                    capability="GSLayer.update",
                    location=caller_location(),
                )

    def _update_pending_layers(self):
        """Retry failed updates before publication; never discard a failed layer."""
        for layer_id in tuple(self._pending_layer_updates):
            self._commit_layer_edits(layer_id)
            self._pending_layer_updates.remove(layer_id)

    def _touch_layer(self, layer_id):
        self._require_editable_layer(layer_id)
        glyph = self._objects[self._parents[layer_id]]
        self._pending_layer_updates.add(layer_id)
        self._touch(("layer", self._objects[layer_id]), ("glyph", glyph))

    def _notify(self, name, changed, *, post=False):
        self._require_history_scope(*((key[0], obj) for key, obj in changed.items()))
        self._update_pending_layers()
        keys = sorted(
            changed, key=lambda key: NOTIFY_ORDER.get(key[0], len(NOTIFY_ORDER))
        )
        # Older FontLab builds default to shallow history (9784 changed it).
        # Save nested outline data explicitly on every supported build.
        originals = []
        if post:
            for key, objects in self._prepared.items():
                if key[0] == "component_history":
                    owner = self._objects.get(key[1])
                    kind = self._object_keys[key[1]][1]
                    if owner is not None and (kind, owner.id) in changed:
                        originals.extend(objects)
        # Native cache callbacks may change focus after the first fence.
        self._require_history_scope(*((key[0], obj) for key, obj in changed.items()))
        self._native().flItems().notifyChangesApplied(
            name, originals + [changed[k] for k in keys], True
        )

    def set_layer_width(self, layer_id: str, width: float) -> None:
        layer = self._writable_layer(layer_id)
        self._prepare_layer(layer_id)
        layer.advanceWidth = width
        self._touch_layer(layer_id)

    def node_name(self, node_id):
        return self._object(node_id).name or None

    def set_node_name(self, node_id, name):
        self._object(node_id)
        shape, layer_id = self._node_shapes[node_id]
        self._own_shape(layer_id, shape)
        self._object(node_id).name = name
        self._touch_layer(layer_id)

    def set_node_position(self, node_id: str, x: float, y: float) -> None:
        node = self._object(node_id)
        shape, lid = self._node_shapes[node_id]
        # Native fact: PythonQt's QTransform.inverted() returns only the transform.
        if not shape.transform.isInvertible():
            raise UnsupportedCapability(
                "Cannot edit a node under a singular shape transform"
            )
        point = _qpoint(x, y)
        local = shape.transform.inverted().map(point)
        self._own_shape(lid, shape)
        node = self._object(node_id)  # the clone's node
        node.x, node.y = local.x(), local.y()
        self._touch_layer(lid)

    def _node_smooth(self, node):
        # Raw state also exposes control-node flags that native isSmooth masks.
        # Project host G2/Hobby onto the supported plain Glyphs smooth contract;
        # their advanced modes cannot round-trip through connection=0/100.
        return bool(node.nodeState & self._native().flNode.NodeKind["SmoothMask"])

    def _set_node_smooth(self, node, smooth):
        # setSmooth aligns handles. Public nodeState only assigns flags
        # (Proteus/common/model/flnode.cpp); use the exported named masks.
        # Explicit plain writes replace G2/Hobby as well as Smooth, retaining
        # type, first, selection and every unrelated bit without moving points.
        flags = self._native().flNode.NodeKind
        node.nodeState = (node.nodeState & ~flags["SmoothMask"]) | (
            flags["Smooth"] if smooth else 0
        )

    def set_node_type(self, node_id, kind):
        node = self._object(node_id)
        contour = self._object(self._parents[node_id])
        nodes = list(contour.nodes())
        index = next(i for i, item in enumerate(nodes) if item.id == node.id)
        incoming = []
        for offset in range(1, len(nodes)):
            if not contour.closed and offset > index:
                break
            before = nodes[(index - offset) % len(nodes)]
            if not _control(before):
                break
            incoming.append(before)
        if kind in ("curve", "qcurve") and (
            not incoming or kind == "curve" and len(incoming) != 2
        ):
            raise UnsupportedCapability(
                "GSNode.type: curve endpoints need existing incoming controls",
                capability="GSNode.type",
            )
        if kind == "line" and incoming:
            raise UnsupportedCapability(
                "GSNode.type: remove incoming controls before making a line",
                capability="GSNode.type",
            )
        control = "Off" if kind == "qcurve" or kind == "offcurve" and contour.isTT else "Curve"
        if kind in ("curve", "qcurve"):
            incoming_ids = {n.id for n in incoming}
            others = [n for n in nodes if _control(n) and n.id not in incoming_ids]
            if any(n.isOff() != (kind == "qcurve") for n in others):
                raise UnsupportedCapability("GSNode.type: mixed cubic/quadratic contour", capability="GSNode.type")
        flags = self._native().flNode.NodeType
        shape, layer_id = self._node_shapes[node_id]
        tokens = [self._keys[(self._object_keys[node_id][0], "node", n.id)] for n in incoming]
        self._own_shape(layer_id, shape)
        for token in tokens if kind in ("curve", "qcurve") else ():
            target = self._object(token)
            target.nodeState = (target.nodeState & ~flags["AnyNodeMask"]) | flags[control]
        target = self._object(node_id)
        target.nodeState = (target.nodeState & ~flags["AnyNodeMask"]) | flags[control if kind == "offcurve" else "On"]
        self._touch_layer(layer_id)

    def set_node_smooth(self, node_id: str, smooth: bool) -> None:
        self._object(node_id)
        shape, lid = self._node_shapes[node_id]
        self._own_shape(lid, shape)
        self._set_node_smooth(self._object(node_id), smooth)
        self._touch_layer(lid)

    def set_node_connection(self, node_id: str, connection: int) -> None:
        self._object(node_id)
        self._check_connection(connection)
        self.set_node_smooth(node_id, connection == 100)

    @staticmethod
    def _check_connection(connection):
        if connection not in (None, 0, 100):
            raise UnsupportedCapability(
                f"FontLab cannot store Glyphs node connection {connection!r}",
                capability="GSNode.connection",
                location=caller_location(),
            )

    def layer_bounds(self, layer_id: str):
        layer = self._object(layer_id)
        if isinstance(layer, _PendingLayer):
            return None
        rect = layer.boundingBox
        if rect is None or rect.isNull():
            return None
        return (rect.x(), rect.y(), rect.width(), rect.height())

    def transform_layer(self, layer_id: str, matrix) -> None:
        # Native fact (r020-metrics run 1): QTransform is in PythonQt.QtGui.
        transform = _import_qtgui().QTransform(*(float(v) for v in matrix))
        layer = self._writable_layer(layer_id)
        staged = self._stage_shapes(layer_id)
        self._prepare_layer(layer_id)
        for shape, clone in staged:
            self._own_shape(layer_id, shape, clone=clone)
        layer.applyTransform(transform)
        self._touch_layer(layer_id)

    def set_anchor_position(self, anchor_id: str, x: float, y: float) -> None:
        anchor = self._object(anchor_id)
        layer_id = self._parents[anchor_id]
        point = _qpoint(x, y)
        self._prepare_layer(layer_id)
        anchor.point = point
        self._touch_layer(layer_id)

    def glyph_note(self, glyph_id: str) -> str:
        return str(self._object(glyph_id).note or "")

    def glyph_last_change(self, glyph_id: str) -> str | None:
        """flGlyph.lastModified (QDateTime) as local ``YYYY-MM-DD HH:MM:SS``."""
        stamp = self._object(glyph_id).lastModified
        if stamp is None or not stamp.isValid():
            return None
        return stamp.toString("yyyy-MM-dd HH:mm:ss")

    def layer_vertical_width(self, layer_id: str) -> float | None:
        layer = self._object(layer_id)
        if isinstance(layer, _PendingLayer) or not layer.hasAdvanceHeight:
            return None
        return float(layer.advanceHeight)

    def set_master_italic_angle(self, master_id, value):
        value = float(value)
        package, name = self._object(master_id), self._master_names[master_id]
        current = package.master
        self._prepare(("font", package))
        try:
            if name != current:
                package.setMaster(name)
            package.italicAngle_value = value
            self._touch(("font", package))
        finally:
            if name != current:
                package.setMaster(current)

    def set_glyph_unicodes(self, glyph_id, values):
        glyph = self._object(glyph_id)
        package = self._object(self._parents[glyph_id])
        # Keep the target-font-owned wrapper; flGlyph.fgGlyph exports a bare one.
        record = self._fontgate_font(package)[glyph.name]
        unicodes = [int(value, 16) for value in values]
        if list(record.unicodes) == unicodes:
            return  # no write, notification, or Undo entry for an unchanged value
        from .creation import guard_pending

        if any(layer.autoLayer for layer in glyph.layers):
            raise UnsupportedCapability(
                "Unicode edits on native auto layers need a verified edit route",
                capability="GSGlyph.unicodes.autoLayer",
            )
        guard_pending(package, glyph, capability="GSGlyph.unicodes")
        # FontLab fl#8514: with a glyph tab open this setter may rewrite OTHER
        # laid-out glyphs on save. Retain the metadata-only route: MCP set_glyph
        # destroys unrelated state and fails native Unicode lookup/Undo (r34).
        self._prepare(("glyph", glyph))
        record.unicodes = unicodes
        self._touch(("glyph", glyph))

    def master_metrics(self, master_id: str) -> MasterMetrics:
        """``fontlab.FontMetrics(package, master)`` gives the vertical metrics of
        any master. FontLab has no per-master italic angle accessor: the
        current master's ``italicAngle_value`` is read, another master made
        current for the read and then restored (no undo step: native check
        in glyport-matrix legacy-syntax)."""
        package, name = self._object(master_id), self._master_names[master_id]
        metrics = self._native().FontMetrics(package, name)
        current = package.master
        if name != current:
            package.setMaster(name)
        try:
            angle = float(package.italicAngle_value)
        finally:
            if name != current:
                package.setMaster(current)
        return MasterMetrics(
            float(metrics.ascender),
            float(metrics.capsHeight),
            float(metrics.descender),
            float(metrics.xHeight),
            angle,
        )

    def current_master(self, font_id: str) -> str | None:
        package = self._object(font_id)
        name = package.master
        masters = {m.name: m.id for m in self.font_info(font_id).masters}
        return masters.get(name)

    def set_current_master(self, font_id: str, master_id: str) -> None:
        package = self._object(font_id)
        master = next(
            (m for m in self.font_info(font_id).masters if m.id == master_id), None
        )
        if master is None:
            raise ValueError("Master does not belong to this font")
        package.setMaster(master.name)

    def make_node_first(self, node_id: str) -> None:
        """Glyphs' ``makeNodeFirst``: the node becomes the contour's start node."""
        node = self._object(node_id)
        path_id = self._parents[node_id]
        contour = self._object(path_id)
        index = next(i for i, n in enumerate(contour.nodes()) if n.id == node.id)
        layer_id = self._parents[path_id]
        shape = self._shape_of(layer_id, contour)
        self._own_shape(layer_id, shape)
        self._object(path_id).setStartPoint(index)
        self._touch_layer(layer_id)

    def node_selected(self, node_id):
        selected = bool(self._object(node_id).selected)
        if self._selection_flags.get(node_id, selected) != selected:
            self._revision += 1  # editor selection is not part of Undo history
        self._selection_flags[node_id] = selected
        return selected

    def remove_glyph(self, font_id, glyph_id):
        package, glyph = self._object(font_id), self._object(glyph_id)
        prepared = dict(self._prepared)
        removed = {("glyph", glyph.id)}
        layer_tokens = set(self._glyph_layer_tokens.get(glyph_id, ()))
        for token in layer_tokens:
            layer = self._objects.get(token)
            if layer is not None and not isinstance(layer, _PendingLayer):
                removed.add(("layer", layer.id))
        glyph_name = str(glyph.name)
        self._prepare(("font", package))
        result = package.deleteGlyph(glyph)
        # Older pygate wrappers discard the native bool and return None.
        # Verify that void result rather than declaring an actual deletion failed.
        remaining = package.findName(glyph_name) if result is None else None
        if result is False or (remaining is not None and remaining.isValid):
            self._prepared = prepared
            raise NativeOperationError(
                f"FontLab refused to remove glyph {glyph_name!r}",
                capability="GSFont.glyphs.remove",
                location=caller_location(),
            )
        self._invalidate(glyph_id)
        self._glyph_layer_tokens.pop(glyph_id, None)
        for key in removed:
            self._prepared.pop(key, None)
            self._changed.pop(key, None)
        # Successful deletion retires these layer owners, but package history
        # still needs the retained component originals before publication.
        for key in tuple(self._prepared):
            if key[0] == "component_history" and key[1] in layer_tokens:
                self._prepared[(key[0], font_id, key[2])] = self._prepared.pop(key)
        self._pending_layer_updates.difference_update(layer_tokens)
        self._touch(("font", package))

    def rename_glyph(self, font_id, glyph_id, name):
        package, glyph = self._object(font_id), self._object(glyph_id)
        if name == glyph.name:
            return
        existing = package.findName(name) if name else None
        if not name or existing is not None and existing.id != glyph.id:
            raise ValueError("Duplicate or empty glyph name")
        self._require_history_scope(("font", package), ("glyph", glyph))
        record = self._fontgate_font(package)[glyph.name]
        unicodes = list(record.unicodes)
        native_glyph = glyph.fgGlyph
        self._prepare(("font", package), ("glyph", glyph))
        if not package.renameGlyph(native_glyph, name, True):
            raise UnsupportedCapability(
                "Native glyph rename refused", capability="GSGlyph.name"
            )
        # FontLab re-derives the encoding from the new name; Glyphs keeps it.
        # Retain the package-owned record and restore before the closing batch.
        if list(record.unicodes) != unicodes:
            record.unicodes = unicodes
        self._touch(("font", package), ("glyph", glyph))

    def set_node_selected(self, node_id: str, selected: bool) -> None:
        # Observe before/after: script and editor changes invalidate snapshots
        # without publishing an Undo notification or scanning sibling nodes.
        self.node_selected(node_id)
        self._object(node_id).selected = bool(selected)
        self.node_selected(node_id)

    def append_path(self, layer_id: str, path: PathInfo) -> str:
        return self.insert_path(layer_id, -1, path)

    def insert_path(self, layer_id: str, index: int, path: PathInfo) -> str:
        """A new one-contour shape before the shape that holds the entry at
        ``index`` of the layer's shape order (path and component ids); a
        negative or past-the-end index appends."""
        shape = self._staged_native(layer_id, path, self._build_path)
        layer = self._writable_layer(layer_id)
        before = self._shape_at(layer_id, index)
        self._prepare_layer(layer_id)
        if before is None:
            added = layer.addShape(shape)
        else:
            position = next(i for i, s in enumerate(layer.shapes) if s.id == before.id)
            inserted = layer.insertShape(position, shape)
            added = inserted if inserted is not None else shape
        self._touch_layer(layer_id)
        document = self._object_keys[layer_id][0]
        inserted = added.contours[0]
        token = self._register((document, "path", inserted.id), inserted, layer_id)
        self._layer_members[layer_id].add(token)
        return token

    def _build_path(self, path):
        """Build a detached native shape; no layer/history access."""
        for node in path.nodes:
            self._check_connection(node.connection)
        quadratic = any(n.type == "qcurve" for n in path.nodes)
        if quadratic and any(n.type == "curve" for n in path.nodes):
            raise UnsupportedCapability("Mixed quadratic and cubic contour")
        native = self._native()
        control = "off" if quadratic else "curve"  # see _control
        nodes = []
        for node in fontlab_order(list(path.nodes), path.closed):
            # Native fact: nodeType is accepted only as a keyword argument.
            item = native.flNode(
                _qpoint(node.x, node.y),
                nodeType=control if node.type == "offcurve" else "on",
            )
            if node.name is not None:
                item.name = node.name
            self._set_node_smooth(item, node.smooth)
            item.selected = node.selected
            nodes.append(item)
        contour = native.flContour(nodes, closed=path.closed)  # keyword only (native)
        if quadratic:
            # A single contour has one native quadratic/cubic representation.
            contour.isTT = True
        shape = native.flShape()
        # Native fact: addContour(contour) raises IndexError; the second bool is required.
        shape.addContour(contour, True)
        return shape

    def _shape_at(self, layer_id, index):
        """The native shape holding entry ``index`` of the shape order, or None."""
        if index < 0:
            return None
        glyph_id = self._parents[layer_id]
        order = self._read_layer(
            self._parents[glyph_id],
            self._object(layer_id),
            self._layer_masters[layer_id],
            glyph_id,
            background=self._object_keys[layer_id][-1] == "background",
            layer_key=self._object_keys[layer_id][3],
        ).shape_ids
        if index >= len(order):
            return None
        obj = self._object(order[index])
        if self._object_keys[order[index]][1] == "component":
            return obj
        return self._shape_of(layer_id, obj)

    def append_glyph(
        self, font_id: str, name: str, *, unicodes: tuple[str, ...] = ()
    ) -> str:
        """Construct inside the target package from a value-only VFJ recipe.

        flPackage.addGlyph(flGlyph) transfers an FG pointer rather than copying
        it. Use the same target-owned builder as fontport, including for replace.
        """
        package = self._object(font_id)
        if not name or package.findName(name) is not None:
            raise ValueError(f"Duplicate or empty glyph name {name!r}")
        target_id = self._tool_font(font_id, "GSFont.glyphs.append")
        create = self._resolve_tool("set_glyph", "GSFont.glyphs.append")
        data = {
            "name": str(name),
            "layers": [
                {"name": str(master), "advanceWidth": 0} for master in package.masters
            ],
        }
        if unicodes:
            data["unicodes"] = [int(code, 16) for code in unicodes]
        from .creation import create_preserving

        create_preserving(
            self,
            package,
            name,
            create,
            font_id=target_id,
            glyph_name=data["name"],
            create=True,
            glyph_data=data,
        )
        added = package.findName(name)
        fg_id = added.fgGlyphId
        # Keep the target-native wrapper alive; never substitute a source or
        # detached fontgate glyph for the package-owned flGlyph.
        token = self._register((font_id, "glyph", fg_id), added, font_id)
        self._glyph_native_ids[token], self._glyph_names[token] = fg_id, name
        self._touch(("font", package), ("glyph", added))
        return token

    def append_component(self, layer_id: str, component: ComponentInfo) -> str:
        """FontLab 9.0.9780 offers no working component constructor from Python
        (flLayer.setGlyphComponents rejects every argument form; addComponent
        only records a recipe entry). A component is built by fontpr set_glyph
        in a scratch glyph, cloned into the layer, and the scratch glyph is
        deleted (probe_create_glyph.json). Translation transforms only."""
        shape = self._staged_native(
            layer_id, component, lambda info: self._build_component(layer_id, info)
        )
        layer = self._writable_layer(layer_id)
        self._prepare_layer(layer_id)
        shape = layer.addShape(shape)
        self._touch_layer(layer_id)
        document = self._object_keys[layer_id][0]
        token = self._register((document, "component", shape.id), shape, layer_id)
        self._layer_members[layer_id].add(token)
        return token

    def _build_component(self, layer_id, component):
        """Build and detach the temporary tool-produced shape before attachment."""
        if self._object_keys[layer_id][-1] == "background":
            raise UnsupportedCapability(
                "Native mask component construction is not mapped",
                capability="GSLayer.background.components",
            )
        a, b, c, d, x, y = component.transform
        if (a, b, c, d) != (1, 0, 0, 1):
            raise UnsupportedCapability(
                "Scaled or rotated new components", capability="GSComponent.transform"
            )
        font_id = self._parents[self._parents[layer_id]]
        self._tool_font(font_id, "GSLayer.components.append")
        create = self._resolve_tool("set_glyph", "GSLayer.components.append")
        package = self._object(font_id)
        if package.findName(component.componentName) is None:
            raise ValueError(f"No glyph named {component.componentName!r}")
        layer_name = self._layer_name(layer_id)
        scratch_name = package.findNewName("_glyport.component")
        element = {
            "component": {"glyphName": component.componentName},
            "transform": {"xOffset": x, "yOffset": y},
        }
        data = {
            "name": scratch_name,
            "layers": [{"name": layer_name, "elements": [element]}],
        }
        from .creation import create_preserving

        create_preserving(
            self,
            package,
            scratch_name,
            create,
            font_id=package.fgId,
            glyph_name=scratch_name,
            glyph_data=data,
            create=True,
        )
        scratch = package.findName(scratch_name)
        try:
            source = scratch.findLayer(layer_name).shapes[0]
            return source.clone()
        finally:
            package.deleteGlyph(scratch)

    def remove_path(self, layer_id: str, path_id: str) -> None:
        layer = self._object(layer_id)
        contour = self._object(path_id)
        # Checked first: a pending layer has no paths and no native shapes.
        if self._parents[path_id] != layer_id:
            raise ValueError("Path does not belong to layer")
        shape = next(
            (s for s in layer.shapes if any(c.id == contour.id for c in s.contours)),
            None,
        )
        if shape is None:
            raise ValueError("Path does not belong to layer")
        wanted = self._node_hint_survivors(layer_id, contour)
        if len(shape.contours) == 1:  # remove the whole shape: no in-place edit
            self._prepare_layer(layer_id)
            self._drop_node_hints(layer_id, wanted)
            layer.removeShape(shape)
        else:
            self._own_shape(layer_id, shape)
            self._drop_node_hints(layer_id, wanted)
            contour = self._object(path_id)
            self._shape_of(layer_id, contour).removeContour(contour)
        self._invalidate(path_id)
        self._touch_layer(layer_id)

    def add_anchor(self, layer_id: str, anchor: AnchorInfo) -> str:
        layer = self._object(layer_id)
        if not isinstance(layer, _PendingLayer) and any(
            a.name == anchor.name for a in layer.anchors
        ):
            raise ValueError("Duplicate anchor name")
        item = self._staged_native(layer_id, anchor, self._build_anchor)
        layer = self._writable_layer(layer_id)
        self._prepare_layer(layer_id)
        layer.addAnchor(item)
        self._touch_layer(layer_id)
        document = self._object_keys[layer_id][0]
        token = self._register((document, "anchor", item.id), item, layer_id)
        self._layer_members[layer_id].add(token)
        return token

    def _build_anchor(self, anchor):
        native = self._native()
        point = _qpoint(anchor.x, anchor.y)
        item = native.flPinPoint(point)
        item.name = anchor.name
        return item

    def mark(self, id: str) -> int:
        obj = self._object(id)
        return 0 if isinstance(obj, _PendingLayer) else int(obj.mark)

    def glyph_tags(self, glyph_id: str) -> tuple[str, ...]:
        return tuple(str(t) for t in self._object(glyph_id).tags or ())

    def set_glyph_tags(self, glyph_id: str, tags: tuple[str, ...]) -> None:
        """flGlyph.tags is assigned as a whole list; setTag raises
        (native probe glyport-matrix/probe_glyph_tags.json)."""
        glyph = self._object(glyph_id)
        values = [str(t) for t in tags]
        self._native()
        self._require_history_scope(("glyph", glyph))
        glyph.tags = values
        self._touch(("glyph", glyph))

    def set_mark(self, id: str, hue: int) -> None:
        """flGlyph.mark / flLayer.mark: a hue, 0 = no mark (TypeRig's
        fontMarkColors use the same scale)."""
        hue = int(hue)
        self._native()
        kind = self._object_keys[id][1]
        obj = self._writable_layer(id) if kind == "layer" else self._object(id)
        layer_id = id if kind == "layer" else None
        if layer_id is not None:
            self._prepare_layer(layer_id)
        else:
            self._require_history_scope(("glyph", obj))
        obj.mark = hue
        if layer_id is not None:
            self._touch_layer(layer_id)
        else:
            self._touch(("glyph", obj))

    def remove_anchor(self, layer_id: str, anchor_id: str) -> None:
        layer = self._object(layer_id)
        if self._parents.get(anchor_id) != layer_id:
            raise ValueError("Anchor does not belong to layer")
        anchor = self._object(anchor_id)
        self._prepare_layer(layer_id)
        layer.removeAnchor(anchor)
        self._touch_layer(layer_id)
        self._layer_members[layer_id].discard(anchor_id)
        self._invalidate(anchor_id)

    def insert_path_node(
        self,
        path_id: str,
        index: int,
        node: NodeInfo,
        *,
        on_attach: Callable[[str], None] | None = None,
    ) -> str:
        """Insert one native node without retiring retained handles.

        Register and attach before fallible cache updates: a failed publication
        still leaves the caller bound to the node that really entered the path.
        Closed append inserts after the old native start, then moves that same
        start object to the end. Unlike setStartPoint, this admits controls as
        temporary first nodes, without smoothing or replacing any old node.
        """
        from .node_insert import insertion_index, insertion_node

        contour = self._object(path_id)
        index = insertion_index(index, len(contour.nodes()))
        node = insertion_node(node)
        append_closed = (
            contour.closed and bool(contour.nodes()) and index == len(contour.nodes())
        )
        layer_id = self._parents[path_id]
        shape = self._shape_of(layer_id, contour)
        self._require_editable_layer(layer_id)
        if not shape.transform.isInvertible():
            raise UnsupportedCapability(
                "Cannot edit a path under a singular shape transform"
            )
        local = shape.transform.inverted().map(_qpoint(node.x, node.y))
        insertion_node(NodeInfo("", local.x(), local.y()))
        control = "off" if contour.isTT else "curve"
        item = self._native().flNode(
            local, nodeType=control if node.type == "offcurve" else "on"
        )
        if node.name is not None:
            item.name = node.name
        self._set_node_smooth(item, node.smooth)
        item.selected = node.selected
        native_index = (
            1
            if append_closed
            else (index + 1 if contour.closed and contour.nodes() else index)
        )
        owned = self._own_shape(layer_id, shape)
        contour = self._object(path_id)
        contour.insert(native_index, item)
        if append_closed:
            # Source: removeOne only detaches the object; removeAt smooths its
            # neighbours. Retain the same old start for native ID/hint identity.
            start = contour.nodes()[0]
            contour.removeOne(start)
            contour.insert(len(contour.nodes()), start)
        document = self._object_keys[layer_id][0]
        token = self._register((document, "node", item.id), item, path_id)
        self._node_shapes[token] = (owned, layer_id)
        try:
            if on_attach is not None:
                on_attach(token)
        finally:
            # Even a caller attachment error cannot bypass failed-publication state.
            self._touch_layer(layer_id)
        return token

    def set_path_nodes(self, path_id: str, nodes, closed: bool) -> None:
        """``flContour.assign(list(flNode))`` keeps the contour (and its shape
        position); points are mapped into the shape's local coordinates."""
        for node in nodes:
            self._check_connection(node.connection)
        contour = self._object(path_id)
        layer_id = self._parents[path_id]
        layer = self._object(layer_id)
        shape = next(
            s for s in layer.shapes if any(c.id == contour.id for c in s.contours)
        )
        if not shape.transform.isInvertible():
            raise UnsupportedCapability(
                "Cannot edit a path under a singular shape transform"
            )
        inverse = shape.transform.inverted()
        native = self._native()
        quadratic = any(n.type == "qcurve" for n in nodes)
        control = "off" if quadratic else "curve"  # see _control
        items = []
        for node in fontlab_order(list(nodes), closed):
            item = native.flNode(
                inverse.map(_qpoint(node.x, node.y)),
                nodeType=control if node.type == "offcurve" else "on",
            )
            if node.name is not None:
                item.name = node.name
            self._set_node_smooth(item, node.smooth)
            item.selected = node.selected
            items.append(item)
        wanted = self._node_hint_survivors(layer_id, contour)
        self._own_shape(layer_id, shape)
        self._drop_node_hints(layer_id, wanted)
        contour = self._object(path_id)
        contour.assign(items)
        self._retire_path_nodes(path_id)
        contour.closed = closed
        self._touch_layer(layer_id)

    def append_guide(self, layer_id: str, guide: GuideInfo) -> str:
        # Native fact (probe_breadth2.json): flGuideLine(angle, QPointF) plus
        # appendGuidelines([guide]) keeps the name.
        item = self._staged_native(layer_id, guide, self._new_guide)
        layer = self._writable_layer(layer_id)
        self._prepare_layer(layer_id)
        layer.appendGuidelines([item])
        self._touch_layer(layer_id)
        document = self._object_keys[layer_id][0]
        token = self._register((document, "guide", item.id), item, layer_id)
        self._layer_members[layer_id].add(token)
        return token

    def begin_undo(self, name: str) -> None:
        if self._undo_name is not None:
            raise RuntimeError("Undo group already active")
        if self._changed:
            raise RuntimeError(
                "Unpublished edits must be retried before a new Undo group"
            )
        self._native()
        self._undo_name, self._changed, self._prepared = name, {}, {}
        self._owned_shapes = set()
        self._history_disclosure = None

    def end_undo(self) -> None:
        if self._undo_name is None:
            raise RuntimeError("No undo group active")
        # Publish first: if it fails the group stays open with its changes, so
        # end_undo() can be retried.
        if self._changed:
            self._notify(self._undo_name, self._changed, post=True)
        self._undo_name, self._changed, self._prepared = None, {}, {}
        self._owned_shapes = set()
        self._history_disclosure = None

    def can_publish_undo(self, font_id: str) -> bool:
        """Check package registration before dereferencing any stored children.

        An explicitly scoped package can remain isValid after leaving the
        workspace. Closed/unregistered packages must never reach flItems.
        """
        if not self.is_valid(font_id):
            return False
        native = self._native()
        workspace = native.flWorkspace.instance()
        if workspace is None:
            return False
        registered = {native.flPackage(p).id for p in workspace.packages()}
        if self._objects[font_id].id not in registered:
            return False
        # PythonQt may produce a fresh wrapper at each read. Match the native
        # identity, resolving newly appended glyph tokens only after checking
        # the owning package. Replace stored wrappers with the validated ones.
        available = {}
        kinds = {kind for kind, _ in self._changed}
        candidates = list(self._object_keys.items())
        # Resolved objects first: a normal edit must not materialize every
        # unresolved glyph just to validate a handful of changed identities.
        candidates.sort(key=lambda item: self._objects.get(item[0]) is None)
        for token, key in candidates:
            if self._changed.keys() <= available.keys():
                break
            if key[1] not in kinds:
                continue
            owner = token
            while self._parents.get(owner) is not None:
                owner = self._parents[owner]
            owner_key = self._object_keys.get(owner)
            if (
                owner_key is None
                or owner_key[1] != "font"
                or owner_key[2] not in registered
            ):
                continue
            if self.is_valid(token):
                obj = self._objects[token]
                if not isinstance(obj, _PendingLayer):
                    available[key[1], obj.id] = obj
        if not self._changed.keys() <= available.keys():
            return False
        self._changed = {key: available[key] for key in self._changed}
        return True

    def discard_undo(self) -> None:
        """Drop pending wrappers locally; do not call any native API."""
        self._undo_name, self._changed, self._prepared = None, {}, {}
        self._pending_layer_updates.clear()
        self._owned_shapes = set()
        self._history_disclosure = None
