# this_file: src/fontlab_glyport/bootstrap.py
"""Explicit ordinary-import aliases backed by one retained native session."""

import sys
from pathlib import Path
from types import ModuleType

from .execution import _LOCK, ExecutionContext, check_cocoa_request
from .profile_versions import PROFILE_VERSIONS

_ROOTS = {"GlyphsApp", "AppKit", "Foundation", "Cocoa", "objc", "vanilla", "robofab"}
_active = None


def _collisions(allowed=None) -> list[str]:
    from .cocoa_backend import native_module

    allowed = allowed or {}
    return sorted(
        name
        for name, module in sys.modules.copy().items()
        if name.split(".")[0] in _ROOTS
        and allowed.get(name) is not module
        and not native_module(name, module)
    )


class Activation:
    """Retain adapters, callbacks and owned windows until explicit close.

    Only public aliases still pointing to our modules are removed. Unrelated
    imports and replacements made by the caller survive deactivation.
    """

    def __init__(self, host, profile: str):
        self.host, self.profile = host, profile
        self.context = ExecutionContext(Path.cwd(), profile, sink=host.sink)
        self.modules: dict[str, ModuleType] = {}
        self.closed = False
        self._restored = {}
        self._masked = {}
        self._namespaces: list[tuple[dict, dict]] = []

    @property
    def cocoa_backend(self):
        return self.context.cocoa_backend

    @property
    def cocoa_fallback_reason(self):
        return self.context.cocoa_fallback_reason

    def bind(self, namespace: dict) -> None:
        """Supply Glyphs menu globals without overwriting caller-owned values."""
        module = self.modules["GlyphsApp"]
        names = vars(module).get(
            "__all__", [n for n in vars(module) if not n.startswith("_")]
        )
        exports = {name: getattr(module, name) for name in names}
        if "Glyphs" in exports:
            # Legacy menu scripts receive this per-execution font snapshot.
            exports.setdefault("Font", getattr(exports["Glyphs"], "font", None))
        collisions = [
            name
            for name, value in exports.items()
            if name in namespace and namespace[name] is not value
        ]
        if collisions:
            raise ValueError(
                "Caller namespace collision: " + ", ".join(sorted(collisions))
            )
        added = {
            name: value for name, value in exports.items() if name not in namespace
        }
        namespace.update(added)
        self._namespaces.append((namespace, added))

    def close(self) -> None:
        """Release the native session exactly once, even when cleanup raises."""
        if self.closed:
            return

        def cleanup():
            global _active
            if _LOCK.locked():
                raise RuntimeError("Deactivate outside an active execution scope")
            try:
                self.context.close()
            finally:
                for name, module in self.modules.items():
                    if sys.modules.get(name) is module:
                        if name in self._restored:
                            sys.modules[name] = self._restored[name]
                        else:
                            del sys.modules[name]
                for name, module in self._masked.items():
                    if name not in sys.modules:
                        sys.modules[name] = module
                self._masked.clear()
                for namespace, added in reversed(self._namespaces):
                    for name, value in added.items():
                        if namespace.get(name) is value:
                            del namespace[name]
                self._namespaces.clear()
                self.modules.clear()
                self.closed = True
                if _active is self:
                    _active = None

        self.host.dispatch(cleanup)


def activate(
    *,
    profile: str = "glyphs4",
    namespace: dict | None = None,
    cocoa_backend: str = "auto",
) -> Activation:
    """Enable ordinary Glyphs imports in FontLab's GUI thread until deactivate.

    Existing compatibility-name modules are refused, including foreign child
    modules. Source rewriting and scoped dependency routing remain the domain
    of run_script/install_plugin. GlyphsApp exports are supplied in caller globals
    (or explicit namespace); conflicting values are refused. Repeating the same
    profile returns its handle and can bind another script namespace.
    """
    namespace = sys._getframe(1).f_globals if namespace is None else namespace
    if not isinstance(namespace, dict):
        raise TypeError("namespace must be a dictionary")
    if profile not in PROFILE_VERSIONS:
        raise ValueError(f"Unknown compatibility profile: {profile!r}")
    from .GlyphsApp._binding import refuse_independent_activation

    refuse_independent_activation()
    from . import entrypoints

    host = _active.host if _active is not None else entrypoints._native_host()

    def prepare():
        global _active
        if _LOCK.locked():
            raise RuntimeError("Activate outside an active execution scope")
        if _active is not None:
            if _active.profile != profile:
                raise ValueError("Deactivate before changing the compatibility profile")
            if cocoa_backend != _active._cocoa_request:
                raise ValueError("Deactivate before changing cocoa_backend")
            _active.bind(namespace)
            return _active
        check_cocoa_request(cocoa_backend)
        collisions = _collisions()
        if collisions:
            raise ImportError(
                "Compatibility module collision: " + ", ".join(collisions)
            )
        handle = Activation(host, profile)
        handle._cocoa_request = cocoa_backend
        try:
            providers = host.adapter_factory(handle.context, host.current_font())
            handle.context.adapters.update(providers)
            handle.context.configure_cocoa(cocoa_backend)
            # The context lock/finder exist only during construction and later
            # wrapped callbacks, never for the activation's entire lifetime.
            with handle.context:
                for name in sorted(providers, key=lambda n: (n.count("."), n)):
                    if (
                        name.split(".")[0] in _ROOTS
                        and name.split(".")[0] not in handle.context.native_cocoa
                    ):
                        handle.modules[name] = handle.context.import_module(name)
            # Providers can import third-party modules while constructing. Do
            # not overwrite one introduced after the initial collision check.
            collisions = _collisions(handle.context.native_cocoa)
            if collisions:
                raise ImportError(
                    "Compatibility module collision: " + ", ".join(collisions)
                )
            handle.bind(namespace)
            handle._restored = {
                name: sys.modules[name]
                for name in handle.modules
                if name in sys.modules
            }
            if handle.cocoa_backend == "qt":
                from .cocoa_backend import native_module

                handle._masked = {
                    name: module
                    for name, module in sys.modules.copy().items()
                    if native_module(name, module) and name not in handle.modules
                }
                for name in handle._masked:
                    del sys.modules[name]
            sys.modules.update(handle.modules)
            _active = handle
            return handle
        except BaseException:
            handle.close()
            raise

    return host.dispatch(prepare)


def deactivate() -> None:
    """Close the retained activation; repeated calls are harmless."""
    if _active is not None:
        _active.close()
