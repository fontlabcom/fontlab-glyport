# this_file: src/fontlab_glyport/ui/nib_loader.py
"""Instantiate a NIB/XIB ``UIGraph`` as Qt-backed Cocoa views (R031).

``instantiate(graph, owner, appkit)`` substitutes ``owner`` for File's Owner,
builds every view with its frame and control properties, nests subviews
(a window's content view becomes its ``contentView``, a scroll view's
document its ``documentView``; windows stay hidden),
sets outlets on their source objects, wires target/action and binds values.
A class the graph names but neither ``classes`` (the plugin's own Python
classes) nor ``appkit`` provides is a blocked case: ``UnsupportedCapability``
naming the class and its source id, never an inert placeholder widget.
Connections that cannot be honoured (an action sent to First Responder, an
outlet on a view such as ``nextKeyView``) are listed in ``diagnostics``.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

from .._strict import caller_location
from ..errors import UnsupportedCapability
from .cocoa import NSMakeRect
from .cocoa_controls import NSNumberFormatter
from .graph import Node, UIGraph
from .images import find_image
from .nib_graph import graph_from_nib, graph_from_xib

_PUSH_TYPES = (0, 7)


@dataclass
class NibInstance:
    """Objects built from one graph; ``top_level`` keeps them alive (R027)."""

    objects: dict[str, Any]
    top_level: list[Any]
    diagnostics: list[str] = field(default_factory=list)


def load_graph(path: str | Path) -> UIGraph:
    """A ``.nib`` (file or bundle) or ``.xib`` path as a ``UIGraph``."""
    path = Path(path)
    if path.suffix == ".xib":
        return graph_from_xib(path)
    return graph_from_nib(path)


def find_nib(name: str, resources: str | Path) -> Path | None:
    """``name.nib`` (deployed, preferred) or ``name.xib`` under ``resources``.

    Searches ``resources`` and its ``Base.lproj``/``en.lproj``/``English.lproj``.
    """
    root = Path(resources)
    for folder in (
        root,
        root / "Base.lproj",
        root / "en.lproj",
        root / "English.lproj",
    ):
        for suffix in (".nib", ".xib"):
            candidate = folder / (name + suffix)
            if candidate.exists():
                return candidate
    return None


def _blocked(what: str, node: Node) -> UnsupportedCapability:
    capability = f"nib.{what}"
    where = f" (source id {node.source_id})" if node.source_id else ""
    return UnsupportedCapability(
        f"Unsupported capability: {capability}{where}",
        capability=capability,
        location=caller_location(),
    )


def instantiate(
    graph: UIGraph,
    owner: Any,
    appkit: Mapping[str, Any],
    *,
    classes: Mapping[str, type] | None = None,
    resources: Iterable[str | Path] = (),
) -> NibInstance:
    """Build ``graph``'s objects with ``owner`` as File's Owner; named images
    are looked up in the ``resources`` folders (the plugin bundle's)."""
    classes = dict(classes or {})
    resources = list(resources)
    instance = NibInstance({}, [])
    data = graph.to_json()
    for raw in data["nodes"]:
        node = Node.from_json(raw)
        if node.source_class == "NSTableColumn":  # built by its table
            table = instance.objects[node.parent_id]
            column = table.tableColumns()[node.properties["index"]]
            instance.objects[node.node_id] = column
            continue
        obj = _build(node, owner, appkit, classes)
        if node.source_class == "NSTableView":  # prototypes need the NIB context
            obj._load_table(node.properties, (appkit, classes, resources))
        if node.properties.get("clipViewClass"):
            clip = node.properties["clipViewClass"]
            instance.diagnostics.append(f"clip view class {clip} not used")
        if node.properties.get("image"):
            _set_image(instance, obj, node.properties["image"], appkit, resources)
        for index, segment in enumerate(node.properties.get("segments") or []):
            if segment.get("image"):
                setter = partial(obj.setImage_forSegment_, index=index)
                _set_image(instance, setter, segment["image"], appkit, resources)
        instance.objects[node.node_id] = obj
        parent = instance.objects.get(node.parent_id) if node.parent_id else None
        if parent is not None and node.properties.get("contentView"):
            parent.setContentView_(obj)
        elif parent is not None and node.properties.get("documentView"):
            parent.setDocumentView_(obj)
        elif parent is not None:
            parent.addSubview_(obj)
        elif obj is not None and obj is not owner:
            instance.top_level.append(obj)
    constraints = 0
    for connection in data["connections"]:
        if connection["event"] == "constraint":
            constraints += 1
        else:
            _connect(instance, connection)
    if constraints:
        instance.diagnostics.append(
            f"{constraints} Auto Layout constraints parsed; Interface Builder "
            "frames are used (constraints are not solved)"
        )
    return instance


def _build(node: Node, owner, appkit, classes) -> Any:
    props = node.properties
    if node.source_class == "NSCustomObject":
        role = props.get("role")
        if role == "owner":
            return owner
        if role in ("firstResponder", "application"):
            return None
        cls = classes.get(props.get("className"))
        if cls is None:
            raise _blocked(f"object.{props.get('className')}", node)
        return cls.alloc().init()
    if node.source_class == "NSUserDefaultsController":
        return appkit["NSUserDefaultsController"].sharedUserDefaultsController()
    if node.source_class == "NSNumberFormatter":
        return _formatter(props)
    if node.source_class == "NSArrayController":
        return appkit["NSArrayController"].alloc().init()
    if node.source_class in ("NSWindow", "NSPanel"):
        return _window(node, appkit, classes)
    custom = props.get("customClass")
    cls = classes.get(custom) or appkit.get(custom) if custom else None
    if cls is None and custom is None:
        cls = appkit.get(node.source_class)
    if cls is None:
        raise _blocked(custom or node.source_class, node)
    view = cls.alloc().initWithFrame_(NSMakeRect(*(props.get("frame") or (0, 0, 0, 0))))
    _configure(view, node.source_class, props)
    return view


def _configure(view, base: str, props: Mapping[str, Any]) -> None:
    view.setAutoresizingMask_(props.get("autoresizingMask", 0))
    if "tabLabel" in props:  # a tab view item's page (NSTabView.addSubview_)
        view.__dict__["_tab_label"] = props["tabLabel"]
        view.__dict__["_tab_identifier"] = props.get("tabIdentifier")
    if props.get("arranged"):  # a stack view's arranged view (NSStackView.addSubview_)
        view.__dict__["_nib_arranged"] = True
    if props.get("hidden"):
        view.setHidden_(True)
    if props.get("toolTip"):
        view.setToolTip_(props["toolTip"])
    if "enabled" in props and hasattr(view, "setEnabled_"):
        view.setEnabled_(props["enabled"])
    if base in ("NSTextField", "NSSecureTextField", "NSSearchField"):
        view.setStringValue_(props.get("title", ""))
        view.setEditable_(props.get("editable", False))
        view.setBezeled_(props.get("bezeled", False))
        view.setContinuous_(props.get("continuous", False))
        if base == "NSSearchField":
            view.setPlaceholderString_(props.get("placeholder", ""))
            if props.get("sendsSearchStringImmediately"):
                view.setContinuous_(True)
        if props.get("formatter"):
            view.setFormatter_(_formatter(props["formatter"]))
    elif base == "NSProgressIndicator":
        view.setMinValue_(props.get("minValue", 0.0))
        view.setMaxValue_(props.get("maxValue", 100.0))
        view.setDoubleValue_(props.get("value", 0.0))
        view.setIndeterminate_(props.get("indeterminate", False))
    elif base == "NSButton":
        if props.get("buttonType", 0) not in _PUSH_TYPES:
            view.setButtonType_(props["buttonType"])
        view.setTitle_(props.get("title", ""))
        view.setState_(props.get("state", 0))
        if not props.get("bordered", True):
            view.setBordered_(False)
        if "imagePosition" in props:
            view.setImagePosition_(props["imagePosition"])
    elif base == "NSSplitView":
        view.setVertical_(props.get("vertical", False))
        view.setDividerStyle_(props.get("dividerStyle", 1))
    elif base == "NSGridView":
        view._rows, view._columns = props.get("rows", 0), props.get("columns", 0)
        view.setRowSpacing_(props.get("rowSpacing", 6.0))
        view.setColumnSpacing_(props.get("columnSpacing", 6.0))
    elif base == "NSSegmentedControl":
        view._load_segments(props.get("segments", []), props.get("trackingMode", 0))
    elif base == "NSSwitch":
        view.setState_(props.get("state", 0))
    elif base == "NSSlider":
        view.setMinValue_(props.get("minValue", 0.0))
        view.setMaxValue_(props.get("maxValue", 1.0))
        view.setDoubleValue_(props.get("value", 0.0))
        view.setContinuous_(props.get("continuous", False))
    elif base == "NSTextView":
        view.setString_(props.get("string", ""))
        view.setEditable_(props.get("editable", True))
        view.setSelectable_(props.get("selectable", True))
    elif base == "NSComboBox":
        view.setUsesDataSource_(props.get("usesDataSource", False))
        view.addItemsWithObjectValues_(props.get("items", []))
        view.setStringValue_(props.get("title", ""))
        view.setEditable_(props.get("editable", True))
        view.setCompletes_(props.get("completes", True))
        view.setNumberOfVisibleItems_(props.get("numberOfVisibleItems", 5))
    elif base == "NSPathControl":
        view.setURL_(props.get("url"))
        view.setEditable_(props.get("editable", False))
        view.setAllowedTypes_(props.get("allowedTypes"))
    elif base == "NSMatrix":
        view._load_cells(
            props.get("cells", []),
            props.get("rows", 0),
            props.get("columns", 0),
            props.get("mode", 0),
            props.get("cellSize"),
            props.get("intercellSpacing"),
        )
    elif base == "NSBox":
        view.setBoxType_(props.get("boxType", 0))
        view.setTitlePosition_(props.get("titlePosition", 2))
        view.setBorderType_(props.get("borderType", 3))
        view.setTransparent_(props.get("transparent", False))
        view.setTitle_(props.get("title", ""))
    elif base == "NSScrollView":
        view.setHasVerticalScroller_(props.get("hasVerticalScroller", False))
        view.setHasHorizontalScroller_(props.get("hasHorizontalScroller", False))
        view.setAutohidesScrollers_(props.get("autohidesScrollers", False))
    elif base == "NSImageView":
        view.setImageScaling_(props.get("imageScaling", 0))
    elif base == "NSStackView":
        view.setOrientation_(props.get("orientation", 0))  # resets the alignment
        view.setAlignment_(props.get("alignment", 10))
        view.setDistribution_(props.get("distribution", -1))
        view.setSpacing_(props.get("spacing", 8.0))
        view.setEdgeInsets_(props.get("edgeInsets", (0, 0, 0, 0)))
        view.setDetachesHiddenViews_(props.get("detachesHiddenViews", True))
    elif base == "NSPopUpButton":
        view.addItemsWithTitles_(props.get("items", []))
        view.selectItemAtIndex_(props.get("selectedIndex", -1))


def _window(node: Node, appkit, classes) -> Any:
    """Windows are built hidden; the script orders them front."""
    props, custom = node.properties, node.properties.get("customClass")
    cls = (classes.get(custom) or appkit.get(custom)) if custom else None
    if cls is None and custom is None:
        cls = appkit.get(node.source_class)
    if cls is None:
        raise _blocked(custom or node.source_class, node)
    rect = NSMakeRect(*(props.get("contentRect") or (0, 0, 0, 0)))
    window = cls.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, props.get("styleMask", 0), 2, True
    )
    window.setTitle_(props.get("title", ""))
    return window


def _set_image(instance, target, name: str, appkit, resources) -> None:
    """Give ``target`` (a view, or a one-argument setter) the named image."""
    for root in resources:
        path = find_image(name, root)
        if path is not None:
            image = appkit["NSImage"].alloc().initWithContentsOfFile_(str(path))
            (target if callable(target) else target.setImage_)(image)
            return
    instance.diagnostics.append(f"image {name} not found")


def _formatter(limits: Mapping[str, Any]) -> NSNumberFormatter:
    formatter = NSNumberFormatter.alloc().init()
    formatter.setMinimum_(limits.get("minimum"))
    formatter.setMaximum_(limits.get("maximum"))
    return formatter


def _connect(instance: NibInstance, connection: Mapping[str, Any]) -> None:
    source = instance.objects.get(connection["owner_id"])
    target = instance.objects.get(connection["target_id"])
    event, selector = connection["event"], connection["selector"]
    if event == "outlet":
        setter = getattr(source, f"set{selector[:1].upper()}{selector[1:]}_", None)
        if callable(setter):  # key-value coding: a setter wins (delegate, dataSource)
            setter(target)
        elif source is None or _is_view(source):
            instance.diagnostics.append(f"outlet {selector} on a view: not set")
        else:
            setattr(source, selector, target)
    elif event == "action":
        if target is None:
            instance.diagnostics.append(
                f"action {selector} to First Responder: unwired"
            )
            return
        source.setTarget_(target)
        source.setAction_(selector)
    elif event == "binding":
        source.bind_toObject_withKeyPath_options_(
            selector, target, connection["argument"], None
        )


def _is_view(obj: Any) -> bool:
    return hasattr(obj, "addSubview_") and hasattr(obj, "_qt")
