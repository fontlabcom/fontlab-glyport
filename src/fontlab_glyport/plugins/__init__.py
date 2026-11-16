# this_file: src/fontlab_glyport/plugins/__init__.py
"""Glyphs SDK plugin protocols on a host bridge (R025-R027).

``base`` holds the seven SDK base classes, ``host`` the host contract,
``menus`` the ``Glyphs.menu`` proxy, ``loader`` the load/unload lifecycle
and ``fontlab_host`` the FontLab 9 host.
"""

from ..errors import UnsupportedCapability


def register_plugin(context, assessment):
    """The registrar ``install_plugin`` calls (entrypoints ``_native_registrar``).

    Loads the bundle's principal class (or its only plugin class) with
    ``loader.load_plugin`` into the context's ``FontLabSession`` plugin
    environment and returns a ``PluginRegistration`` whose ``unload`` is the
    handle's deterministic unload. A failed load raises; nothing stays
    registered.
    """
    from ..entrypoints import PluginRegistration
    from .base import PLUGIN_CLASSES
    from .loader import load_plugin

    session = getattr(context, "fontlab_session", None)
    if session is None:
        raise UnsupportedCapability(
            "Plugin registration needs the FontLab session adapters",
            capability="plugin:registration",
        )
    env = session.plugin_env()
    name = assessment.principal_class
    if name:
        cls = context.globals.get(name)
        is_plugin = isinstance(cls, type) and issubclass(cls, PLUGIN_CLASSES)
        candidates = [cls] if is_plugin else []
    else:
        candidates = [
            value
            for value in context.globals.values()
            if isinstance(value, type)
            and issubclass(value, PLUGIN_CLASSES)
            and value.__module__ != "GlyphsApp.plugins"
        ]
    if len(candidates) != 1:
        raise UnsupportedCapability(
            "Glyphs plugin class not found or ambiguous: "
            f"{name or [c.__name__ for c in candidates]}",
            capability="plugin:principal-class",
        )
    handle = load_plugin(candidates[0], env)
    if handle.status != "loaded":
        raise UnsupportedCapability(
            f"Plugin failed to load: {handle.error!r}", capability="plugin:load"
        ) from handle.error
    registered = len(handle.tokens) + len(handle.painters)
    evidence = (
        f"{handle.kind} {candidates[0].__name__} loaded: {registered} host registrations",
        *handle.diagnostics,
    )
    return PluginRegistration(
        unload=handle.unload, evidence=evidence, plugin=handle.plugin
    )
