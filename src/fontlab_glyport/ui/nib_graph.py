# this_file: src/fontlab_glyport/ui/nib_graph.py
"""XIB sources and compiled NIBs as one ``UIGraph`` (R028, R031).

Both readers emit the same node schema, so a NIB with no XIB source and the
XIB it came from produce equal graphs (the tests compare them):

- ``source_class`` is the AppKit class (``NSTextField``); a custom class is in
  ``properties["customClass"]`` (``GSSteppingTextField``, ``GSPaletteView``).
- Placeholders are ``NSCustomObject`` nodes with ``properties["role"]``:
  ``owner`` (File's Owner, with ``className``), ``firstResponder`` or
  ``application``; other custom objects have role ``object``.
- Views carry ``frame`` ``[x, y, w, h]`` in Cocoa's bottom-left coordinates,
  ``autoresizingMask`` (Interface Builder's default 12, top-left pinned) and
  ``hidden``. Controls add the keys their class uses: ``title``,
  ``editable``, ``bezeled``, ``buttonType``, ``state``, ``minValue``,
  ``maxValue``, ``value``, ``items``, ``selectedIndex``, ``continuous``,
  ``enabled``, ``toolTip``.
- Connections: ``outlet`` (owner node -> destination, selector = property;
  an outlet to a control's cell points at the control),
  ``action`` (control -> target, selector = action), ``binding`` (control ->
  controller, selector = binding name, argument = key path), ``constraint``
  (first item -> second item, or the first item again for a constant;
  selector ``"<attribute> <relation> <attribute>"``, argument
  ``"<multiplier> <constant> <priority>"``).
- A tab view's items are its child ``NSView`` pages with ``tabLabel`` and
  ``tabIdentifier``; text fields with a number formatter carry ``formatter``
  ``{"minimum", "maximum"}``, and a standalone formatter is an
  ``NSNumberFormatter`` node with the limits it sets; progress indicators carry ``minValue``,
  ``maxValue``, ``value`` and ``indeterminate``.
- A matrix carries ``rows``, ``columns``, ``mode``, ``cellSize``,
  ``intercellSpacing`` and ``cells``: row-major button cells, each with
  ``title``, ``buttonType``, ``state``, ``tag`` and ``enabled``.
- A box carries ``boxType``, ``titlePosition``, ``borderType``,
  ``transparent`` and ``title`` (``""`` when no title is shown); its only
  child is its content view, marked ``contentView``.
- A scroll view carries ``hasVerticalScroller``, ``hasHorizontalScroller``,
  ``autohidesScrollers`` and a custom ``clipViewClass``; its only child is
  its clip view's document view, marked ``documentView`` (the clip view and
  scrollers are not nodes).
- An array controller is an ``NSArrayController`` node; each table column
  is also an ``NSTableColumn`` child node (``index``) so bindings can name it.
- A table view carries ``columns`` (``identifier``, ``title``, ``width``,
  ``minWidth``, ``maxWidth``, ``editable``), ``headerVisible``,
  ``allowsMultipleSelection``, ``rowHeight`` and ``prototypes``: for a
  view-based table, each prototype cell view as its own graph JSON keyed by
  identifier (File's Owner = the ``makeViewWithIdentifier_owner_`` owner).
- Buttons also carry ``bordered`` and, with a named image, ``image`` and
  ``imagePosition``; a switch carries ``state``.
- A text view carries ``string`` (plain text), ``editable`` and
  ``selectable``.
- A split view carries ``vertical`` and ``dividerStyle`` (its subviews are
  the panes); a grid view carries ``rows``, ``columns``, ``rowSpacing`` and
  ``columnSpacing`` (its cells' content views are its children); a visual
  effect view is a plain container.
- A segmented control carries ``segments`` (``label``, ``width``,
  ``selected``, ``tag``, ``image``) and ``trackingMode``; a search field
  adds ``placeholder`` and ``sendsSearchStringImmediately`` to the text
  field properties.
- A combo box carries ``title`` (its text), ``editable``, ``items``,
  ``completes``, ``numberOfVisibleItems`` and ``usesDataSource``.
- A path control carries ``url`` (a URL string), ``editable`` and
  ``allowedTypes``.
- An image view carries ``image`` (a resource name) and ``imageScaling``.
- A stack view carries ``orientation`` (0 horizontal, 1 vertical),
  ``alignment`` (an NSLayoutAttribute), ``distribution``, ``spacing``,
  ``edgeInsets`` ``[top, left, bottom, right]`` and ``detachesHiddenViews``;
  its children (the arranged views) carry ``arranged``.
- A window (``NSWindow`` or ``NSPanel``; a custom subclass in ``customClass``)
  carries ``title``, ``styleMask`` and ``contentRect`` (screen coordinates,
  bottom-left); its content view is its only child, marked ``contentView``.

Nodes keep document order (XIB) or archive order of ``NSSubviews`` (NIB).
Elements the readers do not translate still become nodes (class
``xib:<element>`` or the archived class); the loader decides what is blocked.
"""

import re
import struct
import xml.etree.ElementTree as ET
import xml.parsers.expat
from pathlib import Path
from typing import Any

from .graph import UIGraph
from .nib_archive import MAX_BYTES, Archived, NibFormatError, read_nib, read_nib_data

DEFAULT_MASK = 12  # NSViewMaxXMargin | NSViewMinYMargin
# Resource bounds: Interface Builder files stay far below these.
MAX_DEPTH = 64  # nested views
MAX_NODES = 10_000
MAX_XML_DEPTH = 256  # XML elements of any kind
MAX_XML_ELEMENTS = 200_000
_MASK_BITS = {
    "flexibleMinX": 1,
    "widthSizable": 2,
    "flexibleMaxX": 4,
    "flexibleMinY": 8,
    "heightSizable": 16,
    "flexibleMaxY": 32,
}
_XIB_CLASSES = {
    "customView": "NSView",
    "view": "NSView",
    "textField": "NSTextField",
    "secureTextField": "NSSecureTextField",
    "button": "NSButton",
    "slider": "NSSlider",
    "popUpButton": "NSPopUpButton",
    "progressIndicator": "NSProgressIndicator",
    "tabView": "NSTabView",
    "imageView": "NSImageView",
    "box": "NSBox",
    "stackView": "NSStackView",
    "scrollView": "NSScrollView",
    "matrix": "NSMatrix",
    "pathControl": "NSPathControl",
    "tableView": "NSTableView",
    "comboBox": "NSComboBox",
    "textView": "NSTextView",
    "switch": "NSSwitch",
    "searchField": "NSSearchField",
    "segmentedControl": "NSSegmentedControl",
    "splitView": "NSSplitView",
    "gridView": "NSGridView",
    "visualEffectView": "NSVisualEffectView",
    "tableCellView": "NSTableCellView",
}
_BUTTON_TYPES = {"check": 3, "radio": 4, "push": 7, "square": 7}
# NSWindowStyleMask bits as XIB's windowStyleMask spells them.
_STYLE_BITS = {
    "titled": 1,
    "closable": 2,
    "miniaturizable": 4,
    "resizable": 8,
    "utility": 16,
    "docModal": 64,
    "nonactivatingPanel": 128,
    "texturedBackground": 256,
    "unifiedTitleAndToolbar": 4096,
    "HUD": 8192,
    "fullSizeContentView": 32768,
}
_WINDOW_CLASSES = ("NSWindow", "NSPanel")
# NSStackViewDistribution; a XIB without the attribute uses gravity areas (-1).
_DISTRIBUTIONS = {
    "gravityAreas": -1,
    "fill": 0,
    "fillEqually": 1,
    "fillProportionally": 2,
    "equalSpacing": 3,
    "equalCentering": 4,
}
_INSETS = ("top", "left", "bottom", "right")
# NSScrollView NSsFlags (as ibtool writes them)
_SCROLL_VERTICAL, _SCROLL_HORIZONTAL = 0x10, 0x20
_SCROLL_AUTOHIDES = 0x200
# NSBoxType, NSTitlePosition and NSBorderType as XIB spells them.
_BOX_TYPES = {"primary": 0, "secondary": 1, "separator": 2, "oldStyle": 3, "custom": 4}
_TITLE_POSITIONS = {
    "noTitle": 0,
    "aboveTop": 1,
    "atTop": 2,
    "belowTop": 3,
    "aboveBottom": 4,
    "atBottom": 5,
    "belowBottom": 6,
}
_BORDER_TYPES = {"none": 0, "line": 1, "bezel": 2, "groove": 3}
_BOX_SEPARATOR = 2
# NSMatrixMode; a XIB without the attribute is a radio matrix.
_MATRIX_MODES = {"radio": 0, "highlight": 1, "list": 2, "track": 3}
_MATRIX_FLAGS = ((0x40000000, 0), (0x80000000, 1), (0x20000000, 2))  # else track
# NSCellImagePosition: XIB names (leading/trailing as ibtool resolves them)
# and the NIB's NSButtonFlags byte (bits 0x78; 0x80 is "bordered").
_IMAGE_POSITIONS = {
    "noImage": 0,
    "only": 1,
    "left": 2,
    "right": 3,
    "below": 4,
    "above": 5,
    "overlaps": 6,
    "leading": 2,
    "trailing": 3,
}
_NIB_IMAGE_POSITIONS = {0x40: 1, 0x38: 2, 0x28: 3, 0x18: 4, 0x08: 5, 0x48: 6}
_BUTTON_BORDERED = 0x80
_DIVIDER_STYLES = {"thick": 1, "thin": 2, "paneSplitter": 3}
_SEARCH_IMMEDIATE = 0x08  # NSSearchFieldFlags, first byte
# NSSegmentSwitchTracking
_TRACKING_MODES = {"selectOne": 0, "selectAny": 1, "momentary": 2}
_DECIMAL_WORDS = 8
_TABLE_MULTIPLE = 0x08000000  # NSTvFlags: allowsMultipleSelection
_TEXT_SELECTABLE, _TEXT_EDITABLE = 0x1, 0x2  # NSTextViewSharedData NSFlags
_IMAGE_SCALING = {
    "proportionallyDown": 0,
    "axesIndependently": 1,
    "none": 2,
    "proportionallyUpOrDown": 3,
}
_STATES = {"on": 1, "off": 0, "mixed": -1}
_ROLES = {"-2": "owner", "-1": "firstResponder", "-3": "application"}
# NSCell flags (GNUstep's NSCell -initWithCoder: layout).
_CELL_ON, _CELL_DISABLED, _CELL_EDITABLE = 0x80000000, 0x20000000, 0x10000000
_CELL_BEZELED = 0x00400000
_HIDDEN = 0x80000000
_NUMBERS = re.compile(r"-?\d+(?:\.\d+)?")
# NSLayoutAttribute and NSLayoutRelation as XIB spells them.
_LAYOUT_ATTRIBUTES = (
    "notAnAttribute",
    "left",
    "right",
    "top",
    "bottom",
    "leading",
    "trailing",
    "width",
    "height",
    "centerX",
    "centerY",
    "lastBaseline",
    "firstBaseline",
)
_RELATIONS = {-1: "lessThanOrEqual", 0: "equal", 1: "greaterThanOrEqual"}
_PI_INDETERMINATE = 0x2  # NSpiFlags (GNUstep's NSProgressIndicator coder)


def _constraint(builder, first, second, attributes, relation, numbers) -> None:
    """Queue one constraint connection; ``numbers`` = multiplier, constant, priority."""
    selector = f"{attributes[0]} {relation} {attributes[1]}"
    # Interface Builder's standard spacing stays symbolic: "standard".
    argument = " ".join(n if isinstance(n, str) else f"{float(n):g}" for n in numbers)
    builder.pending.append(
        (
            first,
            second if second is not None else first,
            "constraint",
            selector,
            argument,
        )
    )


def _yes(value: str | None) -> bool:
    return value == "YES"


def _children(element, tag: str) -> list:
    found = element.find(tag)
    return [] if found is None else list(found)


class _Builder:
    """Adds nodes and connections; maps source ids to node ids."""

    def __init__(self, shared: dict | None = None) -> None:
        self.graph = UIGraph()
        self.ids: dict[Any, str] = {}
        self.pending: list[tuple] = []  # connections resolved after all nodes
        # One budget for a document and its nested prototype graphs: objects
        # (nodes plus widget-making properties, see charge) and nested bytes.
        self.shared = shared if shared is not None else {"objects": 0, "bytes": 0}

    def node(self, key, cls, parent=None, source_id=None, **props) -> str:
        if key in self.ids:
            raise NibFormatError(
                f"object {source_id or key} appears more than once in the view tree"
            )
        self.charge(1)
        parent_id = self.ids.get(parent) if parent is not None else None
        node = self.graph.add_node(
            cls,
            parent_id=parent_id,
            source_id=None if source_id is None else str(source_id),
            properties={k: v for k, v in props.items() if v is not None},
        )
        self.ids[key] = node.node_id
        return node.node_id

    def charge(self, count: int) -> None:
        """Count ``count`` objects (nodes, or matrix cells and segments that
        each become a widget) against ``MAX_NODES``."""
        self.shared["objects"] += count
        if self.shared["objects"] > MAX_NODES:
            raise NibFormatError(f"more than {MAX_NODES} nodes")

    def alias(self, key, node_key) -> None:
        """Connections to ``key`` (a control's cell) reach ``node_key``'s node."""
        if key is not None and key not in self.ids and node_key in self.ids:
            self.ids[key] = self.ids[node_key]

    def finish(self) -> UIGraph:
        for owner, target, event, selector, argument in self.pending:
            if owner in self.ids and target in self.ids:
                self.graph.connect(
                    self.ids[owner], self.ids[target], event, selector, argument
                )
        return self.graph


# --- XIB -----------------------------------------------------------------


def graph_from_xib(path: str | Path) -> UIGraph:
    """Translate an Interface Builder XIB document into a ``UIGraph``.

    A document type declaration (DTD, entities) is rejected before parsing,
    so entity expansion never runs; size, nesting and node counts are bounded.
    """
    data = Path(path).read_bytes()
    if len(data) > MAX_BYTES:
        raise NibFormatError(f"{path}: too large for a XIB")
    _check_xml(path, data)
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise NibFormatError(f"{path}: malformed XIB ({error})") from error
    if root.tag != "document" or "Cocoa" not in root.get("type", ""):
        raise ValueError(f"{path}: not a Cocoa XIB document")
    builder = _Builder()
    for element in _children(root, "objects"):
        _xib_object(builder, element, None)
    return builder.finish()


# XIB elements graph_from_xib reads; keyed ones only under these keys.
_TRANSLATED = {
    "document",
    "dependencies",
    "plugIn",
    "capability",
    "deployment",
    "objects",
    "customObject",
    "userDefaultsController",
    "subviews",
    "tabViewItems",
    "tabViewItem",
    "autoresizingMask",
    "textFieldCell",
    "secureTextFieldCell",
    "buttonCell",
    "sliderCell",
    "popUpButtonCell",
    "menu",
    "items",
    "menuItem",
    "numberFormatter",
    "window",
    "panel",
    "windowStyleMask",
    "edgeInsets",
    "clipView",
    "scroller",
    "cells",
    "column",
    "pathCell",
    "allowedTypes",
    "tableColumns",
    "tableColumn",
    "tableHeaderCell",
    "prototypeCellViews",
    "tableHeaderView",
    "comboBoxCell",
    "segmentedCell",
    "segments",
    "segment",
    "searchFieldCell",
    "holdingPriorities",
    "arrayController",
    "declaredKeys",
    "rows",
    "gridRow",
    "columns",
    "gridColumn",
    "gridCells",
    "gridCell",
    "textView",
    "attributedString",
    "fragment",
    "objectValues",
    "constraints",
    "constraint",
    "connections",
    "outlet",
    "action",
    "binding",
    *_XIB_CLASSES,
}
_TRANSLATED_KEYS = {
    "rect": {"frame", "contentRect"},
    "size": {"cellSize", "intercellSpacing"},
    "url": {"url"},
    "string": {"title"},
    "real": {"minimum", "maximum"},
}


def untranslated_xib(path: str | Path) -> dict[str, int]:
    """Elements of a XIB that ``graph_from_xib`` does not translate, with counts
    (fonts, colours, cell behaviours, ...): the unmapped-property report."""
    data = Path(path).read_bytes()
    _check_xml(path, data)
    counts: dict[str, int] = {}
    for element in ET.fromstring(data).iter():
        keys = _TRANSLATED_KEYS.get(element.tag)
        if element.tag in _TRANSLATED or (
            keys is not None and element.get("key") in keys
        ):
            continue
        counts[element.tag] = counts.get(element.tag, 0) + 1
    return dict(sorted(counts.items()))


def _check_xml(path, data: bytes) -> None:
    """Validate with expat before building a tree: any DTD (so no entity can
    be declared or expanded, whatever the encoding) is rejected, and the whole
    XML tree is bounded to ``MAX_XML_DEPTH`` levels and ``MAX_XML_ELEMENTS``."""
    parser = xml.parsers.expat.ParserCreate()
    state = {"depth": 0, "elements": 0}

    def doctype(*args):
        raise NibFormatError(f"{path}: XIB with a DTD or entities is not accepted")

    def start(name, attributes):
        state["depth"] += 1
        state["elements"] += 1
        if state["depth"] > MAX_XML_DEPTH:
            raise NibFormatError(f"{path}: XML nests deeper than {MAX_XML_DEPTH}")
        if state["elements"] > MAX_XML_ELEMENTS:
            raise NibFormatError(
                f"{path}: XML has more than {MAX_XML_ELEMENTS} elements"
            )

    def end(name):
        state["depth"] -= 1

    parser.StartDoctypeDeclHandler = doctype
    parser.EntityDeclHandler = doctype
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    try:
        parser.Parse(data, True)
    except xml.parsers.expat.ExpatError as error:
        raise NibFormatError(f"{path}: malformed XIB ({error})") from error


def _xib_object(
    builder: _Builder, element, parent, depth: int = 0, extra: dict | None = None
) -> None:
    if depth > MAX_DEPTH:
        raise NibFormatError(f"views nest too deep (over {MAX_DEPTH})")
    tag, source_id = element.tag, element.get("id")
    if tag == "customObject":
        role = _ROLES.get(source_id, "object")
        builder.node(
            source_id,
            "NSCustomObject",
            source_id=source_id,
            role=role,
            className=element.get("customClass") or "NSObject",
        )
    elif tag == "userDefaultsController":
        builder.node(source_id, "NSUserDefaultsController", source_id=source_id)
    elif tag == "arrayController":
        builder.node(source_id, "NSArrayController", source_id=source_id)
    elif tag in ("window", "panel"):
        _xib_window(builder, element, depth)
    elif tag == "numberFormatter":  # a standalone formatter object
        builder.node(
            source_id, "NSNumberFormatter", source_id=source_id, **_xib_limits(element)
        )
    else:
        cls = _XIB_CLASSES.get(tag, f"xib:{tag}")
        props = {"customClass": element.get("customClass")}
        props.update(_xib_view(element))
        props.update(_xib_control(tag, element))
        props.update(extra or {})
        if tag == "tableView":
            prototypes = _xib_prototypes(element, builder.shared, depth + 1)
            props["prototypes"] = prototypes or None
        builder.charge(_expansion(props))
        builder.node(source_id, cls, parent, source_id=source_id, **props)
        cell = element.find("*[@key='cell']")
        if cell is not None:  # an outlet to the cell gets the control
            builder.alias(cell.get("id"), source_id)
        arranged = {"arranged": True} if tag == "stackView" else None
        for child in _children(element, "subviews"):
            _xib_object(builder, child, source_id, depth + 1, arranged)
        for index, column in enumerate(
            _children(element, "tableColumns") if tag == "tableView" else ()
        ):  # columns are objects: bindings and outlets can name them
            column_id = column.get("id")
            builder.node(column_id, "NSTableColumn", source_id, column_id, index=index)
            _xib_connections(builder, column, column_id)
        for cell in _children(element, "gridCells") if tag == "gridView" else ():
            content = cell.find("*[@key='contentView']")
            if content is not None:
                _xib_object(builder, content, source_id, depth + 1)
        content = element.find("view[@key='contentView']") if tag == "box" else None
        if content is not None:
            _xib_object(builder, content, source_id, depth + 1, {"contentView": True})
        clip = (
            element.find("clipView[@key='contentView']")
            if tag == "scrollView"
            else None
        )
        for child in [] if clip is None else _children(clip, "subviews")[:1]:
            _xib_object(builder, child, source_id, depth + 1, {"documentView": True})
        for item in _children(element, "tabViewItems"):
            page = item.find("view[@key='view']")
            if page is not None:
                labels = {
                    "tabLabel": item.get("label", ""),
                    "tabIdentifier": item.get("identifier") or None,
                }
                _xib_object(builder, page, source_id, depth + 1, labels)
        _xib_constraints(builder, element, source_id)
    _xib_connections(builder, element, source_id)


def _xib_window(builder: _Builder, element, depth: int) -> None:
    source_id, custom = element.get("id"), element.get("customClass")
    rect = element.find("rect[@key='contentRect']")
    style = element.find("windowStyleMask[@key='styleMask']")
    builder.node(
        source_id,
        _window_class(element.tag == "panel", custom),
        source_id=source_id,
        customClass=None if custom in _WINDOW_CLASSES else custom,
        title=element.get("title", ""),
        styleMask=0
        if style is None
        else sum(bit for name, bit in _STYLE_BITS.items() if _yes(style.get(name))),
        contentRect=None
        if rect is None
        else [float(rect.get(k, 0)) for k in ("x", "y", "width", "height")],
    )
    content = element.find("view[@key='contentView']")
    if content is not None:
        _xib_object(builder, content, source_id, depth + 1, {"contentView": True})


def _window_class(panel: bool, custom: str | None) -> str:
    return "NSPanel" if panel or custom == "NSPanel" else "NSWindow"


def _expansion(props: dict) -> int:
    """Objects a node's properties will create: matrix cells and segments (a
    widget each); prototype graphs charge the shared budget themselves. A
    matrix whose cells do not fill its rows and columns is malformed."""
    cells = props.get("cells") or []
    if "cells" in props and props.get("rows", 0) * props.get("columns", 0) != len(
        cells
    ):
        raise NibFormatError("matrix cells do not match its rows and columns")
    return len(cells) + len(props.get("segments") or [])


def _xib_constraints(builder: _Builder, element, source_id) -> None:
    for item in _children(element, "constraints"):
        multiplier = item.get("multiplier", "1")
        if ":" in multiplier:  # Interface Builder writes ratios as "a:b"
            top, bottom = multiplier.split(":", 1)
            multiplier = float(top) / float(bottom)
        _constraint(
            builder,
            item.get("firstItem") or source_id,
            item.get("secondItem"),
            (item.get("firstAttribute"), item.get("secondAttribute", "notAnAttribute")),
            item.get("relation", "equal"),
            (
                multiplier,
                "standard" if _yes(item.get("symbolic")) else item.get("constant", 0),
                item.get("priority", 1000),
            ),
        )


def _xib_view(element) -> dict[str, Any]:
    rect = element.find("rect[@key='frame']")
    frame = None
    if rect is not None:
        frame = [float(rect.get(k, 0)) for k in ("x", "y", "width", "height")]
    mask_element = element.find("autoresizingMask[@key='autoresizingMask']")
    mask = DEFAULT_MASK
    if mask_element is not None:
        mask = sum(
            bit for name, bit in _MASK_BITS.items() if _yes(mask_element.get(name))
        )
    return {
        "frame": frame,
        "autoresizingMask": mask,
        "hidden": _yes(element.get("hidden")),
        "toolTip": element.get("toolTip"),
    }


def _xib_control(tag: str, element) -> dict[str, Any]:
    if tag == "splitView":
        return {
            "vertical": _yes(element.get("vertical")),
            "dividerStyle": _DIVIDER_STYLES.get(element.get("dividerStyle"), 1),
        }
    if tag == "gridView":
        return {
            "rows": len(_children(element, "rows")),
            "columns": len(_children(element, "columns")),
            "rowSpacing": float(element.get("rowSpacing", 6)),
            "columnSpacing": float(element.get("columnSpacing", 6)),
        }
    if tag == "switch":
        return {"state": _STATES.get(element.get("state"), 0)}
    if tag == "textView":
        storage = element.find("attributedString[@key='textStorage']")
        fragments = [] if storage is None else storage.findall("fragment")
        return {
            "string": "".join(
                f.get("content") or f.findtext("string[@key='content']") or ""
                for f in fragments
            ),
            "editable": element.get("editable") != "NO",
            "selectable": element.get("selectable") != "NO",
        }
    if tag == "tableView":
        return _xib_table(element)
    if tag == "matrix":
        return _xib_matrix(element)
    if tag == "box":
        return _box(
            _BOX_TYPES.get(element.get("boxType"), 0),
            _TITLE_POSITIONS.get(element.get("titlePosition"), 2),
            _BORDER_TYPES.get(element.get("borderType"), 3),
            _yes(element.get("transparent")),
            element.get("title", "Box"),
        )
    if tag == "scrollView":
        clip = element.find("clipView[@key='contentView']")
        return {
            "hasVerticalScroller": element.get("hasVerticalScroller") != "NO",
            "hasHorizontalScroller": element.get("hasHorizontalScroller") != "NO",
            "autohidesScrollers": _yes(element.get("autohidesScrollers")),
            "clipViewClass": None if clip is None else clip.get("customClass"),
        }
    if tag == "stackView":
        insets = element.find("edgeInsets[@key='edgeInsets']")
        return {
            "orientation": 1 if element.get("orientation") == "vertical" else 0,
            "alignment": _LAYOUT_ATTRIBUTES.index(element.get("alignment", "centerY")),
            "distribution": _DISTRIBUTIONS[element.get("distribution", "gravityAreas")],
            "spacing": float(element.get("spacing", 8)),
            "edgeInsets": [
                0.0 if insets is None else float(insets.get(side, 0))
                for side in _INSETS
            ],
            "detachesHiddenViews": _yes(element.get("detachesHiddenViews")),
        }
    if tag == "progressIndicator":
        return {
            "minValue": float(element.get("minValue", 0)),
            "maxValue": float(element.get("maxValue", 100)),
            "value": float(element.get("doubleValue", 0)),
            "indeterminate": _yes(element.get("indeterminate")),
        }
    cell = element.find("*[@key='cell']")
    if cell is None:
        return {}
    props: dict[str, Any] = {"enabled": cell.get("enabled") != "NO"}
    if tag in ("textField", "secureTextField", "searchField"):
        props.update(
            title=_xib_title(cell),
            editable=_yes(cell.get("editable")),
            bezeled=cell.get("borderStyle") == "bezel",
        )
        props["continuous"] = _yes(cell.get("continuous"))
        if tag == "searchField":
            props.update(
                placeholder=cell.get("placeholderString") or "",
                sendsSearchStringImmediately=_yes(
                    cell.get("sendsSearchStringImmediately")
                ),
            )
        formatter = cell.find("numberFormatter[@key='formatter']")
        if formatter is not None:
            props["formatter"] = {"minimum": None, "maximum": None}
            props["formatter"].update(_xib_limits(formatter))
    elif tag == "button":
        props.update(
            title=_xib_title(cell),
            buttonType=_BUTTON_TYPES.get(cell.get("type"), 0),
            state=_STATES.get(cell.get("state"), 0),
            bordered=cell.get("borderStyle") is not None,
        )
        if cell.get("image"):
            position = _IMAGE_POSITIONS.get(cell.get("imagePosition"), 0)
            props.update(image=cell.get("image"), imagePosition=position)
    elif tag == "slider":
        props.update(
            minValue=float(cell.get("minValue", 0)),
            maxValue=float(cell.get("maxValue", 1)),
            value=float(cell.get("doubleValue", 0)),
            continuous=_yes(cell.get("continuous")),
        )
    elif tag == "segmentedControl":
        segments = [
            _segment(
                item.get("label") or "",
                item.get("width", 0),
                _yes(item.get("selected")),
                item.get("tag", 0),
                item.get("image"),
            )
            for item in cell.findall("segments/segment")
        ]
        props.update(
            segments=segments,
            trackingMode=_TRACKING_MODES.get(cell.get("trackingMode"), 0),
        )
    elif tag == "comboBox":
        props.update(
            _combo(
                _xib_title(cell),
                _yes(cell.get("editable")),
                [item.text or "" for item in cell.findall("objectValues/string")],
                cell.get("completes") != "NO",
                cell.get("numberOfVisibleItems", 5),
                _yes(cell.get("usesDataSource")),
            )
        )
    elif tag == "pathControl":
        url = cell.find("url[@key='url']")
        allowed = [item.text for item in cell.findall("allowedTypes/string")]
        props.update(
            url=None if url is None else url.get("string"),
            editable=_yes(cell.get("editable")),
            allowedTypes=allowed or None,
        )
    elif tag == "imageView":
        props.update(
            image=cell.get("image"),
            imageScaling=_IMAGE_SCALING.get(cell.get("imageScaling"), 0),
        )
    elif tag == "popUpButton":
        items = cell.findall("menu/items/menuItem")
        ids = [item.get("id") for item in items]
        selected = cell.get("selectedItem")
        props.update(
            items=[item.get("title", "") for item in items],
            selectedIndex=ids.index(selected) if selected in ids else -1,
        )
    return props


def _xib_limits(formatter) -> dict[str, float]:
    """A number formatter's set ``minimum``/``maximum``."""
    limits = {}
    for key in ("minimum", "maximum"):
        real = formatter.find(f"real[@key='{key}']")
        if real is not None:
            limits[key] = float(real.get("value"))
    return limits


def _xib_table(element) -> dict[str, Any]:
    columns, prototypes = [], {}
    for index, column in enumerate(_children(element, "tableColumns")):
        header = column.find("tableHeaderCell[@key='headerCell']")
        # ibtool names an unnamed column as AppKit does
        identifier = (
            column.get("identifier") or f"AutomaticTableColumnIdentifier.{index}"
        )
        columns.append(
            _column(
                identifier,
                "" if header is None else header.get("title", ""),
                [column.get(k) for k in ("width", "minWidth", "maxWidth")],
                column.get("editable") != "NO",
            )
        )
    return _table(
        columns,
        prototypes,
        element.get("headerView") is not None,
        element.get("multipleSelection") != "NO",
        element.get("rowHeight", 17),
    )


def _xib_prototypes(element, shared: dict, depth: int) -> dict:
    """A view-based table's prototype cell views, keyed by identifier."""
    prototypes = {}
    for index, column in enumerate(_children(element, "tableColumns")):
        identifier = (
            column.get("identifier") or f"AutomaticTableColumnIdentifier.{index}"
        )
        for view in _children(column, "prototypeCellViews"):
            key = view.get("identifier") or identifier
            prototypes[key] = _xib_prototype(view, shared, depth)
    return prototypes


def _xib_prototype(view, shared: dict, depth: int) -> dict:
    """A prototype cell view as its own graph: File's Owner is whoever
    ``makeViewWithIdentifier_owner_`` names (as in the archived NIB). It shares
    the document's budget and continues its nesting depth."""
    builder = _Builder(shared)
    for source_id, role, name in (
        ("-2", "owner", "NSObject"),
        ("-1", "firstResponder", "FirstResponder"),
        ("-3", "application", "NSObject"),
    ):
        builder.node(
            source_id, "NSCustomObject", source_id=source_id, role=role, className=name
        )
    _xib_object(builder, view, None, depth)
    return builder.finish().to_json()


def _segment(label, width, selected, tag, image) -> dict[str, Any]:
    return {
        "label": label,
        "width": float(width),
        "selected": selected,
        "tag": int(tag),
        "image": image,
    }


def _combo(title, editable, items, completes, visible, data_source) -> dict[str, Any]:
    return {
        "title": title,
        "editable": editable,
        "items": items,
        "completes": completes,
        "numberOfVisibleItems": int(visible),
        "usesDataSource": data_source,
    }


def _column(identifier, title, widths, editable) -> dict[str, Any]:
    width, low, high = (None if w is None else float(w) for w in widths)
    return {
        "identifier": identifier,
        "title": title or "",
        "width": width,
        "minWidth": low,
        "maxWidth": high,
        "editable": bool(editable),
    }


def _table(columns, prototypes, header, multiple, row_height) -> dict[str, Any]:
    return {
        "columns": columns,
        "prototypes": prototypes or None,
        "headerVisible": header,
        "allowsMultipleSelection": multiple,
        "rowHeight": float(row_height),
    }


def _xib_matrix(element) -> dict[str, Any]:
    columns = [list(column) for column in _children(element, "cells")]
    rows = len(columns[0]) if columns else 0
    cells = [_xib_cell(column[row]) for row in range(rows) for column in columns]

    def size(key):
        found = element.find(f"size[@key='{key}']")
        return (
            None
            if found is None
            else [float(found.get(k, 0)) for k in ("width", "height")]
        )

    return {
        "rows": rows,
        "columns": len(columns),
        "mode": _MATRIX_MODES.get(element.get("mode", "radio"), 0),
        "cellSize": size("cellSize"),
        "intercellSpacing": size("intercellSpacing"),
        "cells": cells,
    }


def _xib_cell(cell) -> dict[str, Any]:
    return {
        "title": _xib_title(cell),
        "buttonType": _BUTTON_TYPES.get(cell.get("type"), 0),
        "state": _STATES.get(cell.get("state"), 0),
        "tag": int(cell.get("tag", 0)),
        "enabled": cell.get("enabled") != "NO",
    }


def _xib_title(cell) -> str:
    """A cell title: the attribute, or a ``<string key="title">`` (multi-line)."""
    if cell.get("title") is not None:
        return cell.get("title")
    return cell.findtext("string[@key='title']") or ""


def _xib_connections(builder: _Builder, element, source_id) -> None:
    for item in _children(element, "connections"):
        if item.tag == "outlet":
            event = (source_id, item.get("destination"), "outlet", item.get("property"))
        elif item.tag == "action":
            event = (source_id, item.get("target"), "action", item.get("selector"))
        elif item.tag == "binding":
            event = (source_id, item.get("destination"), "binding", item.get("name"))
            builder.pending.append((*event, item.get("keyPath")))
            continue
        else:
            continue
        builder.pending.append((*event, None))


# --- NIB -----------------------------------------------------------------


def graph_from_nib(path: str | Path) -> UIGraph:
    """Translate a compiled NIB (file or bundle directory) into a ``UIGraph``."""
    return _graph_from_root(read_nib(path))


def _graph_from_root(
    data: Archived, shared: dict | None = None, depth: int = 0
) -> UIGraph:
    """A NIB root's graph; a nested prototype passes the document's budget
    and its nesting depth."""
    builder = _Builder(shared)
    owner = data.get("NSRoot")
    keys, parents = data.get("NSObjectsKeys") or [], data.get("NSObjectsValues") or []
    tooltips = _nib_tooltips(data.get("NSConnections") or [])
    top = [obj for obj, parent in zip(keys, parents, strict=False) if parent is owner]
    _nib_placeholder(builder, owner, "owner")
    roles = {}
    for obj in keys:
        if isinstance(obj, Archived) and _nib_role(obj) in (
            "firstResponder",
            "application",
        ):
            roles[_nib_role(obj)] = obj
    if "firstResponder" not in roles:  # ibtool drops an unused First Responder
        roles["firstResponder"] = Archived(
            "NSCustomObject", {"NSClassName": "FirstResponder"}
        )
    for role, obj in sorted(roles.items()):
        _nib_placeholder(builder, obj, role)
    for obj in top:
        if obj is owner or id(obj) in builder.ids:
            continue
        _nib_object(builder, obj, None, tooltips, depth)
    _nib_connections(builder, data.get("NSConnections") or [])
    return builder.finish()


def _nib_role(obj: Archived) -> str | None:
    if obj.cls != "NSCustomObject":
        return None
    name = obj.get("NSClassName")
    return {"FirstResponder": "firstResponder", "NSApplication": "application"}.get(
        name, "object"
    )


def _nib_placeholder(builder: _Builder, obj: Archived, role: str) -> None:
    name = obj.get("NSClassName") or "NSObject"
    if role == "application":
        name = "NSObject"
    builder.node(id(obj), "NSCustomObject", role=role, className=name)


def _nib_object(
    builder: _Builder,
    obj: Any,
    parent,
    tooltips,
    depth: int = 0,
    extra: dict | None = None,
) -> None:
    if not isinstance(obj, Archived):
        return
    if depth > MAX_DEPTH:
        raise NibFormatError(f"views nest too deep (over {MAX_DEPTH})")
    if obj.cls == "NSCustomObject":
        builder.node(
            id(obj),
            "NSCustomObject",
            role="object",
            className=obj.get("NSClassName") or "NSObject",
        )
        return
    if obj.cls == "NSUserDefaultsController":
        builder.node(id(obj), "NSUserDefaultsController")
        return
    if obj.cls == "NSWindowTemplate":
        custom = obj.get("NSWindowClass")
        builder.node(
            id(obj),
            _window_class(False, custom),
            customClass=None if custom in _WINDOW_CLASSES else custom,
            title=obj.get("NSWindowTitle") or "",
            styleMask=obj.get("NSWindowStyleMask", 0),
            contentRect=_numbers(obj.get("NSWindowRect")) or None,
        )
        content = {"contentView": True}
        _nib_object(
            builder, obj.get("NSWindowView"), id(obj), tooltips, depth + 1, content
        )
        return
    if obj.cls == "NSArrayController":
        builder.node(id(obj), "NSArrayController")
        return
    if obj.cls == "NSNumberFormatter":  # a standalone formatter object
        builder.node(id(obj), "NSNumberFormatter", **_nib_limits(obj))
        return
    cls, custom = _nib_classes(obj)
    props = {"customClass": custom, **_nib_view(obj), **_nib_control(cls, obj)}
    props["toolTip"] = tooltips.get(id(obj))
    props.update(extra or {})
    if cls == "NSTableView":
        prototypes = _nib_prototypes(obj, builder.shared, depth + 1)
        props["prototypes"] = prototypes or None
    builder.charge(_expansion(props))
    builder.node(id(obj), cls, parent, **props)
    if isinstance(
        obj.get("NSCell"), Archived
    ):  # an outlet to the cell gets the control
        builder.alias(id(obj.get("NSCell")), id(obj))
    items = obj.get("NSTabViewItems") if cls == "NSTabView" else None
    if items is not None:  # NSSubviews repeats the selected page: use the items
        for item in items:
            labels = {
                "tabLabel": item.get("NSLabel") or "",
                "tabIdentifier": item.get("NSIdentifier") or None,
            }
            _nib_object(
                builder, item.get("NSView"), id(obj), tooltips, depth + 1, labels
            )
    elif cls == "NSTableView":  # columns are objects: bindings can name them
        for index, column in enumerate(obj.get("NSTableColumns") or []):
            builder.node(id(column), "NSTableColumn", id(obj), index=index)
    elif cls == "NSBox":  # its subviews are the content view
        content = {"contentView": True}
        _nib_object(
            builder, obj.get("NSContentView"), id(obj), tooltips, depth + 1, content
        )
    elif cls == "NSScrollView":  # the clip view's document view; scrollers skipped
        clip = obj.get("NSContentView")
        document = clip.get("NSDocView") if isinstance(clip, Archived) else None
        content = {"documentView": True}
        _nib_object(builder, document, id(obj), tooltips, depth + 1, content)
    else:  # a stack view's subviews are its arranged views (flat hierarchy)
        arranged = {"arranged": True} if cls == "NSStackView" else None
        for child in obj.get("NSSubviews") or ():
            _nib_object(builder, child, id(obj), tooltips, depth + 1, arranged)
    for item in obj.get("NSViewConstraints") or ():
        first, second = item.get("NSFirstItem") or obj, item.get("NSSecondItem")
        _constraint(
            builder,
            id(first),
            None if second is None else id(second),
            tuple(
                _LAYOUT_ATTRIBUTES[item.get(key, 0)]
                for key in ("NSFirstAttribute", "NSSecondAttribute")
            ),
            _RELATIONS.get(item.get("NSRelation", 0), "equal"),
            (
                item.get("NSMultiplier", 1.0),
                "standard"
                if item.get("NSSymbolicConstant") == "NSSpace"
                else item.get("NSConstant", 0.0),
                item.get("NSPriority", 1000),
            ),
        )


def _nib_classes(obj: Archived) -> tuple[str, str | None]:
    base, custom = obj.cls, None
    if obj.cls == "NSClassSwapper":
        base, custom = obj.get("NSOriginalClassName"), obj.get("NSClassName")
    elif obj.cls == "NSCustomView":
        base, custom = "NSView", obj.get("NSClassName")
    return base, None if custom == base else custom


def _numbers(text: str | None) -> list[float]:
    return [float(n) for n in _NUMBERS.findall(text or "")]


def _nib_view(obj: Archived) -> dict[str, Any]:
    frame = _numbers(obj.get("NSFrame"))
    if not frame:
        frame = [0.0, 0.0, *_numbers(obj.get("NSFrameSize"))]
    flags = obj.get("NSvFlags", DEFAULT_MASK) & 0xFFFFFFFF
    return {
        "frame": frame if len(frame) == 4 else None,
        "autoresizingMask": flags & 0x3F,
        "hidden": bool(flags & _HIDDEN),
    }


def _box(box_type, position, border, transparent, title) -> dict[str, Any]:
    """Box properties; a separator or an untitled box has the title ``""``."""
    shown = position != 0 and box_type != _BOX_SEPARATOR
    return {
        "boxType": box_type,
        "titlePosition": position,
        "borderType": border,
        "transparent": transparent,
        "title": (title or "") if shown else "",
    }


def _nib_matrix(obj: Archived) -> dict[str, Any]:
    flags = obj.get("NSMatrixFlags", 0) & 0xFFFFFFFF
    mode = next((mode for bit, mode in _MATRIX_FLAGS if flags & bit), 3)

    def size(key):
        numbers = _numbers(obj.get(key))
        return numbers if len(numbers) == 2 else None

    cells = []
    for cell in obj.get("NSCells") or []:
        cell_flags = cell.get("NSCellFlags", 0) & 0xFFFFFFFF
        cells.append(
            {
                "title": cell.get("NSContents") or "",
                "buttonType": _nib_button_type(cell),
                "state": 1 if cell_flags & _CELL_ON else 0,
                "tag": cell.get("NSTag", 0),
                "enabled": not cell_flags & _CELL_DISABLED,
            }
        )
    return {
        "rows": obj.get("NSNumRows", 0),
        "columns": obj.get("NSNumCols", 0),
        "mode": mode,
        "cellSize": size("NSCellSize"),
        "intercellSpacing": size("NSIntercellSpacing"),
        "cells": cells,
    }


def _nib_text(obj: Archived) -> dict[str, Any]:
    storage = obj
    for key in ("NSTextContainer", "NSLayoutManager", "NSTextStorage"):
        storage = storage.get(key) if isinstance(storage, Archived) else None
    shared = obj.get("NSSharedData")
    flags = shared.get("NSFlags", 3) if isinstance(shared, Archived) else 3
    text = storage.get("NSString") if isinstance(storage, Archived) else ""
    return {
        "string": text if isinstance(text, str) else "",
        "editable": bool(flags & _TEXT_EDITABLE),
        "selectable": bool(flags & _TEXT_SELECTABLE),
    }


def _nib_table(obj: Archived) -> dict[str, Any]:
    columns = []
    for column in obj.get("NSTableColumns") or []:
        header = column.get("NSHeaderCell")
        columns.append(
            _column(
                column.get("NSIdentifier"),
                header.get("NSContents") if isinstance(header, Archived) else "",
                [column.get(k) for k in ("NSWidth", "NSMinWidth", "NSMaxWidth")],
                column.get("NSIsEditable", False),
            )
        )
    return _table(
        columns,
        {},
        obj.get("NSHeaderView") is not None,
        bool(obj.get("NSTvFlags", 0) & _TABLE_MULTIPLE),
        obj.get("NSRowHeight", 17.0),
    )


def _nib_prototypes(obj: Archived, shared: dict, depth: int) -> dict:
    """A view-based table's archived prototype cell views (nested NIB data),
    each its own graph within the document's depth, object and byte budget."""
    prototypes = {}
    for identifier, nib in _pairs(obj.get("NSTableViewArchivedReusableViewsKey")):
        data = nib.get("NSNibFileData") if isinstance(nib, Archived) else None
        data = data.get("NS.bytes") if isinstance(data, Archived) else data
        if not isinstance(data, bytes):
            continue
        shared["bytes"] += len(data)
        if shared["bytes"] > MAX_BYTES:
            raise NibFormatError(f"nested prototype data over {MAX_BYTES} bytes")
        if depth > MAX_DEPTH:
            raise NibFormatError(f"views nest too deep (over {MAX_DEPTH})")
        root = read_nib_data(data, f"prototype {identifier}")
        prototypes[identifier] = _graph_from_root(root, shared, depth).to_json()
    return prototypes


def _pairs(dictionary) -> list[tuple]:
    """An archived dictionary's (key, value) pairs (NIBArchive or keyed)."""
    if not isinstance(dictionary, Archived):
        return []
    if "NS.keys" in dictionary.fields:
        return list(
            zip(dictionary.get("NS.keys"), dictionary.get("NS.objects"), strict=False)
        )
    flat = dictionary.get("UINibEncoderEmptyKey") or []
    return list(zip(flat[::2], flat[1::2], strict=False))


def _nib_control(cls: str, obj: Archived) -> dict[str, Any]:
    if cls == "NSSplitView":
        return {
            "vertical": bool(obj.get("NSIsVertical")),
            "dividerStyle": obj.get("NSDividerStyle", 1),
        }
    if cls == "NSGridView":
        return {
            "rows": len(obj.get("NSGrid_rows") or []),
            "columns": len(obj.get("NSGrid_columns") or []),
            "rowSpacing": float(obj.get("NSGrid_rowSpacing", 6.0)),
            "columnSpacing": float(obj.get("NSGrid_columnSpacing", 6.0)),
        }
    if cls == "NSSwitch":
        return {"state": 1 if obj.get("NSControlContents") else 0}
    if cls == "NSTextView":
        return _nib_text(obj)
    if cls == "NSTableView":
        return _nib_table(obj)
    if cls == "NSMatrix":
        return _nib_matrix(obj)
    if cls == "NSBox":
        cell = obj.get("NSTitleCell")
        return _box(
            obj.get("NSBoxType", 0),
            obj.get("NSTitlePosition", 2),
            obj.get("NSBorderType", 3),
            bool(obj.get("NSTransparent")),
            cell.get("NSContents") if isinstance(cell, Archived) else "",
        )
    if cls == "NSScrollView":
        flags, clip = obj.get("NSsFlags", 0), obj.get("NSContentView")
        clip_class = _nib_classes(clip)[1] if isinstance(clip, Archived) else None
        return {
            "hasVerticalScroller": bool(flags & _SCROLL_VERTICAL),
            "hasHorizontalScroller": bool(flags & _SCROLL_HORIZONTAL),
            "autohidesScrollers": bool(flags & _SCROLL_AUTOHIDES),
            "clipViewClass": clip_class,
        }
    if cls == "NSStackView":
        return {
            "orientation": obj.get("NSStackViewOrientation", 0),
            "alignment": obj.get("NSStackViewAlignment", 10),
            "distribution": obj.get("NSStackViewdistribution", -1),
            "spacing": float(obj.get("NSStackViewSpacing", 8.0)),
            "edgeInsets": [
                float(obj.get(f"NSStackViewEdgeInsets.{side}", 0.0)) for side in _INSETS
            ],
            "detachesHiddenViews": bool(obj.get("NSStackViewDetachesHiddenViews")),
        }
    if cls == "NSProgressIndicator":
        return {
            "minValue": float(obj.get("NSMinValue", 0.0)),
            "maxValue": float(obj.get("NSMaxValue", 100.0)),
            "value": float(obj.get("NSProgressIndicatorDoubleValue", 0.0)),
            "indeterminate": bool(obj.get("NSpiFlags", 0) & _PI_INDETERMINATE),
        }
    cell = obj.get("NSCell")
    if not isinstance(cell, Archived):
        return {}
    flags = cell.get("NSCellFlags", 0) & 0xFFFFFFFF
    props: dict[str, Any] = {"enabled": not flags & _CELL_DISABLED}
    if cls in ("NSTextField", "NSSecureTextField", "NSSearchField"):
        props.update(
            title=_contents(cell.get("NSContents")),
            editable=bool(flags & _CELL_EDITABLE),
            bezeled=bool(flags & _CELL_BEZELED),
            continuous=bool(obj.get("NSControlContinuous", False)),
        )
        if cls == "NSSearchField":
            search_flags = cell.get("NSSearchFieldFlags") or b"\0"
            props.update(
                placeholder=cell.get("NSPlaceholderString") or "",
                sendsSearchStringImmediately=bool(search_flags[0] & _SEARCH_IMMEDIATE),
            )
        formatter = cell.get("NSFormatter")
        if isinstance(formatter, Archived) and formatter.cls == "NSNumberFormatter":
            props["formatter"] = {"minimum": None, "maximum": None}
            props["formatter"].update(_nib_limits(formatter))
    elif cls == "NSButton":
        button_flags = (cell.get("NSButtonFlags", 0) & 0xFFFFFFFF) >> 16
        props.update(
            title=cell.get("NSContents") or "",
            buttonType=_nib_button_type(cell),
            state=1 if flags & _CELL_ON else 0,
            bordered=bool(button_flags & _BUTTON_BORDERED),
        )
        image = cell.get("NSNormalImage")
        if isinstance(image, Archived) and image.cls == "NSCustomResource":
            position = _NIB_IMAGE_POSITIONS.get(button_flags & 0x78, 0)
            props.update(image=image.get("NSResourceName"), imagePosition=position)
    elif cls == "NSSlider":
        props.update(
            minValue=float(cell.get("NSMinValue", 0.0)),
            maxValue=float(cell.get("NSMaxValue", 1.0)),
            value=float(cell.get("NSValue", 0.0)),
            continuous=bool(obj.get("NSControlContinuous", flags & 0x00080000)),
        )
    elif cls == "NSSegmentedControl":
        segments = []
        for item in cell.get("NSSegmentImages") or []:
            image = item.get("NSSegmentItemImage")
            named = isinstance(image, Archived) and image.cls == "NSCustomResource"
            segments.append(
                _segment(
                    item.get("NSSegmentItemLabel") or "",
                    item.get("NSSegmentItemWidth", 0),
                    bool(item.get("NSSegmentItemSelected")),
                    item.get("NSSegmentItemTag", 0),
                    image.get("NSResourceName") if named else None,
                )
            )
        props.update(segments=segments, trackingMode=cell.get("NSTrackingMode", 0))
    elif cls == "NSComboBox":
        props.update(
            _combo(
                _contents(cell.get("NSContents")),
                bool(flags & _CELL_EDITABLE),
                [str(item) for item in cell.get("NSPopUpListData") or []],
                bool(cell.get("NSCompletes")),
                cell.get("NSVisibleItemCount", 5),
                bool(cell.get("NSUsesDataSource")),
            )
        )
    elif cls == "NSPathControl":
        url = cell.get("NSContents")
        props.update(
            url=url.get("NS.relative") if isinstance(url, Archived) else None,
            editable=bool(flags & _CELL_EDITABLE),
            allowedTypes=cell.get("NSAllowedTypes") or None,
        )
    elif cls == "NSImageView":
        image = cell.get("NSContents")
        named = isinstance(image, Archived) and image.cls == "NSCustomResource"
        props.update(
            image=image.get("NSResourceName") if named else None,
            imageScaling=cell.get("NSScale", 0),
        )
    elif cls == "NSPopUpButton":
        items = (cell.get("NSMenu") or Archived("NSMenu")).get("NSMenuItems") or []
        selected = cell.get("NSMenuItem")
        index = next((i for i, item in enumerate(items) if item is selected), -1)
        props.update(
            items=[item.get("NSTitle") or "" for item in items],
            selectedIndex=cell.get("NSSelectedIndex", index),
        )
    return props


def _nib_limits(formatter: Archived) -> dict[str, float]:
    """A number formatter's set ``minimum``/``maximum`` (NaN means unset)."""
    limits = {}
    for key, name in (("minimum", "NS.min"), ("maximum", "NS.max")):
        value = _decimal(formatter.get(name))
        if value is not None:
            limits[key] = value
    return limits


def _decimal(value: Any) -> float | None:
    """A formatter limit as a float; ``None`` when unset. ibtool archives limits
    as numbers or ``NSDecimalNumber`` (little-endian 16-bit mantissa words, the
    first ``NS.length`` of them used); length 0 with the sign set is NaN, which
    Interface Builder writes for "no limit"."""
    if not isinstance(value, Archived):
        return None if value is None else float(value)
    length, negative = value.get("NS.length", 0), value.get("NS.negative", False)
    data, exponent = value.get("NS.mantissa") or b"", value.get("NS.exponent", 0)
    if not (
        isinstance(length, int)
        and 0 <= length <= _DECIMAL_WORDS
        and isinstance(data, bytes)
        and len(data) <= 2 * _DECIMAL_WORDS
        and isinstance(exponent, int)
        and -128 <= exponent <= 127
    ):  # NSDecimal: 8 mantissa words, a signed 8-bit exponent
        raise NibFormatError("malformed NSDecimalNumber")
    if length == 0:
        return None if negative else 0.0
    order = "<" if value.get("NS.mantissa.bo", 1) == 1 else ">"
    words = struct.unpack(f"{order}{len(data) // 2}H", data[: len(data) // 2 * 2])
    mantissa = sum(word << (16 * i) for i, word in enumerate(words[:length]))
    number = float(mantissa) * 10.0**exponent
    return -number if negative else number


def _contents(value: Any) -> str:
    """A cell's archived object value as its title (a formatted field archives
    an NSNumber: 3 -> "3", 2.5 -> "2.5")."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value or ""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def _nib_button_type(cell: Archived) -> int:
    image = cell.get("NSAlternateImage")
    name = image.get("NSImageName") if isinstance(image, Archived) else None
    if name == "NSSwitch":
        return 3
    if name == "NSRadioButton":
        return 4
    return 7 if cell.get("NSAuxButtonType") == 7 else 0


def _nib_tooltips(connections: list) -> dict[int, str]:
    tips = {}
    for item in connections:
        if (
            isinstance(item, Archived)
            and item.cls == "NSIBHelpConnector"
            and item.get("NSFile") == "NSToolTipHelpKey"
        ):
            tips[id(item.get("NSDestination"))] = item.get("NSMarker")
    return tips


def _nib_connections(builder: _Builder, connections: list) -> None:
    for item in connections:
        if not isinstance(item, Archived):
            continue
        source, target = id(item.get("NSSource")), id(item.get("NSDestination"))
        if item.cls == "NSNibOutletConnector":
            builder.pending.append(
                (source, target, "outlet", item.get("NSLabel"), None)
            )
        elif item.cls == "NSNibControlConnector":
            builder.pending.append(
                (source, target, "action", item.get("NSLabel"), None)
            )
        elif item.cls == "NSNibBindingConnector":
            event = (source, target, "binding", item.get("NSBinding"))
            builder.pending.append((*event, item.get("NSKeyPath")))
