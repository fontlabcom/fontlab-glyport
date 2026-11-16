# this_file: src/fontlab_glyport/cocoa_backend.py
"""Select real PyObjC imports without passing native modules to alias loaders."""

import importlib
import sys
from importlib.machinery import ExtensionFileLoader
from pathlib import Path

COCOA_ROOTS = frozenset({"objc", "Foundation", "AppKit", "Cocoa"})


def select_backend(request: str):
    """Return selected backend, fallback reason, and untouched native modules."""
    if request not in {"auto", "native", "qt"}:
        raise ValueError("cocoa_backend must be auto, native or qt")
    collisions = [
        name
        for name, module in sys.modules.copy().items()
        if name.split(".")[0] in COCOA_ROOTS and not native_module(name, module)
    ]
    if collisions:
        raise ImportError(
            "Cocoa module collision (not genuine PyObjC): "
            + ", ".join(sorted(collisions))
        )
    if request == "qt":
        return "qt", None, {}
    if sys.platform != "darwin":
        if request == "native":
            raise ImportError("Native Cocoa requires macOS and PyObjC")
        return "qt", "Native Cocoa requires macOS", {}
    try:
        modules = {
            name: importlib.import_module(name)
            for name in ("objc", "Foundation", "AppKit", "Cocoa")
        }
    except ImportError as error:
        if request == "native":
            raise ImportError(
                f"Native Cocoa requires PyObjC (install the cocoa extra): {error}"
            ) from error
        return "qt", f"PyObjC unavailable: {error}", {}
    if not all(native_module(name, module) for name, module in modules.items()):
        raise ImportError(
            "Native Cocoa requires genuine PyObjC bridge/framework modules"
        )
    return "native", None, modules


def _bridge():
    """Verify the cached bridge against its compiled extension, without imports."""
    bridge = sys.modules.get("objc")
    extension = sys.modules.get("objc._objc")
    if bridge is None or extension is None:
        return None
    spec = vars(extension).get("__spec__")
    if spec is None or not isinstance(spec.loader, ExtensionFileLoader):
        return None
    values = vars(bridge)
    if any(
        values.get(name) is not vars(extension).get(name) or values.get(name) is None
        for name in ("objc_class", "lookUpClass")
    ):
        return None
    return bridge


def native_module(name: str, module) -> bool:
    """Check bridge identity, native classes and package-relative provenance.

    Target installations are supported: no installation-directory name is
    assumed. Descendants must belong to their verified framework package.
    """
    root_name = name.split(".")[0]
    if root_name not in COCOA_ROOTS:
        return False
    bridge = _bridge()
    root = sys.modules.get(root_name)
    if bridge is None or root is None or vars(module).get("__name__") != name:
        return False
    if root_name != "objc":
        class_name = "NSObject" if root_name == "Foundation" else "NSColor"
        try:
            cls = getattr(root, class_name)
            if not isinstance(cls, bridge.objc_class) or cls is not bridge.lookUpClass(
                class_name
            ):
                return False
        except (AttributeError, TypeError, LookupError):
            return False
        lazy = vars(root).get("__getattr__")
        if (
            not callable(lazy)
            or getattr(lazy, "__module__", None) != "objc._lazyimport"
        ):
            return False
    path = vars(module).get("__file__")
    root_path = vars(root).get("__file__")
    if not path or not root_path:
        return False
    return Path(path).resolve().is_relative_to(Path(root_path).resolve().parent)
