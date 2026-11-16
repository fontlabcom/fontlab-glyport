# this_file: src/fontlab_glyport/_public/GlyphsApp/_binding.py
"""Session ownership for public imports; construction reuses the runtime facade."""

from threading import RLock

from fontlab_glyport.errors import HostUnavailable, UnsupportedCapability

_default = None
_context = None
_backend = None
_profile = None
_dispatch = None
_lock = RLock()


def _active():
    from ..bootstrap import _active as activation

    return activation if activation is not None and not activation.closed else None


def refuse_independent_activation() -> None:
    """Reject a second retained context before activation touches the host."""
    if _default is not None:
        raise UnsupportedCapability(
            "The public GlyphsApp API is already bound; call activate() before "
            "accessing the public API to share its session, or call "
            "fontlab_glyport.GlyphsApp.unbind() first.",
            capability="GlyphsApp.session",
        )


def unbind() -> None:
    """Release only the independently owned default session, then allow rebinding."""
    global _default, _context, _backend, _profile, _dispatch
    with _lock:
        if _default is not None:
            if _context is not None:
                (_dispatch or (lambda call: call()))(_context.close)
            else:
                _default.Glyphs._remove_all_callbacks()
                _default.Glyphs._bridge.close()
        _default = _context = _backend = _profile = _dispatch = None


def use_backend(backend, *, profile: str) -> None:
    """Build a host-free facade using an explicitly supplied model backend."""
    from ..glyphsapp import make_glyphsapp_module
    from ..glyphsapp.fontlab_bridge import FontLabGlyphsBridge
    from ..model import Model
    from ..model.backend import ModelBackend
    from ..profile_versions import PROFILE_VERSIONS

    global _default, _backend, _profile
    if profile not in PROFILE_VERSIONS:
        raise ValueError(f"Unknown compatibility profile: {profile!r}")
    if not isinstance(backend, ModelBackend):
        raise TypeError("backend must implement ModelBackend")
    with _lock:
        if _active() is not None:
            raise UnsupportedCapability("Deactivate before using an explicit backend")
        if _default is not None:
            if backend is _backend and profile == _profile:
                return
            raise UnsupportedCapability("The public GlyphsApp API is already bound")
        # This bridge's constructor is lazy; noninteractive dialogs stay off.
        # Host services still raise HostUnavailable when no FontLab is present.
        bridge = FontLabGlyphsBridge(log=print, version=PROFILE_VERSIONS[profile])
        _default = make_glyphsapp_module(
            Model(backend),
            bridge,
            error_sink=lambda error, event: print(f"{event}: {error}"),
        )
        _backend, _profile = backend, profile


def facade():
    """Reuse activation, otherwise lazily retain one default FontLabSession."""
    global _default, _context, _dispatch
    with _lock:
        active = _active()
        if active is not None:
            return active.modules["GlyphsApp"]
        if _default is not None:
            return _default
        from pathlib import Path

        from ..entrypoints import _native_host
        from ..execution import ExecutionContext

        try:
            host = _native_host()
        except HostUnavailable as error:
            raise HostUnavailable(
                "Public GlyphsApp requires FontLab; outside FontLab call "
                "fontlab_glyport.GlyphsApp.use_backend(backend) before accessing exports."
            ) from error

        def build():
            context = ExecutionContext(Path.cwd(), "glyphs4", sink=host.sink)
            try:
                providers = host.adapter_factory(context, host.current_font())
                context.adapters.update(providers)
                with context:
                    module = context.import_module("GlyphsApp")
                return context, module
            except BaseException:
                context.close()
                raise

        _context, _default = host.dispatch(build)
        _dispatch = host.dispatch
        return _default
