# this_file: src/fontlab_glyport/glyphsapp/info_debug.py
"""Debug initialization: create the queue, read the CPU count, then load
the name-to-group table.

NSObject's identity initializer is the qualified owned Python boundary here;
no native allocation/substitution or resource-loading success is implied.
"""

from .info_runtime import InfoState, provider_method, require_provider


def initialize_debug(receiver):
    provider = require_provider()
    from .info_manager import GSGlyphsInfo

    if not isinstance(receiver, GSGlyphsInfo):
        raise TypeError(
            "Debug Glyph Info initialization requires a GSGlyphsInfo receiver"
        )
    state = vars(receiver).get("_lifecycle")
    if state is None:
        existing = vars(receiver).get("_fixed_index")
        state = InfoState(
            provider, None, bool(vars(receiver).get("_shared_info_flag", False))
        )
        if existing is None:
            # A fresh native object has nil raw index fields. These are distinct
            # from the dictionary initDebug allocates for sidebar groups.
            state.index.records = state.index.names = state.index.unicodes = None
        else:
            state.index = existing
        receiver._lifecycle = state
    state.provider = provider
    receiver._fixed_index = state.index
    state.queue = provider_method(provider, "new_queue")()
    count = provider_method(provider, "active_processor_count")()
    state.queue.setMaxConcurrentOperationCount_(count)
    state.name2Group = {}
    return receiver
