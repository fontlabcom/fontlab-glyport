# this_file: src/fontlab_glyport/glyphsapp/info_shared.py
"""Shared pointer ownership differs between fixed allocation and plain init.

``sharedManager`` synchronizes creation of the fixed class; ``init`` has its
own once-only block, which publishes the receiver captured by NSObject's init.
These guards preserve Python graph identity, not complete native resources,
observer lifetime, dispatch_once token ABI or every concurrent initialization.
"""

from threading import Lock, RLock

_shared_monitor = RLock()
_shared_once = Lock()


def initialize_shared(receiver: object) -> object:
    """Initialize the first actual receiver; a subtype slot is never consulted."""
    from .info_manager import GSGlyphsInfo

    if not isinstance(receiver, GSGlyphsInfo):
        raise TypeError("GSGlyphsInfo.init requires a GSGlyphsInfo receiver")
    if GSGlyphsInfo._shared is None:
        with _shared_once:
            if GSGlyphsInfo._shared is None:
                GSGlyphsInfo._shared = receiver
                receiver._shared_info_flag = True
                receiver._fixed_index = None
                receiver._public_indexes = {}
                from .info_runtime import InfoState, current_provider, provider_method

                provider = current_provider()
                if provider is not None:
                    from .info_manager_observation import register_observer

                    state = vars(receiver).get("_lifecycle")
                    if state is None:
                        state = InfoState(provider, None, True)
                    state.provider = provider
                    state.shared = True
                    receiver._lifecycle = state
                    receiver._fixed_index = state.index
                    state.queue = provider_method(provider, "new_queue")()
                    count = provider_method(provider, "active_processor_count")()
                    state.queue.setMaxConcurrentOperationCount_(count)
                    receiver.loadSidebarInfoForDocument_(None)
                    receiver.loadGlyphInfo()
                    state.queue.waitUntilAllOperationsAreFinished()
                    register_observer(receiver)
    return GSGlyphsInfo._shared


def shared_manager() -> object:
    """Synchronize fixed-base allocation, retaining an existing direct-init result."""
    from .info_manager import GSGlyphsInfo

    with _shared_monitor:
        if GSGlyphsInfo._shared is None:
            GSGlyphsInfo._shared = GSGlyphsInfo.new()
        return GSGlyphsInfo._shared
