# this_file: src/fontlab_glyport/glyphsapp/info_document.py
"""GSDocument's retained URL/manager control flow over explicit file primitives.

No NSDocument or FontLab file-monitor adapter is assumed. A document may own
``_file_primitives`` with ``file_url(document)``, ``set_file_url(document,url)``
(the superclass setter), and ``file_type(document)``. URLs must supply the actual
selectors used below. Observer selectors are dispatched on the current receiver;
their absence is the source's conditional branch, not an installed observer.
"""

from inspect import getattr_static

from ..errors import UnsupportedCapability

_MONITORED_TYPES = (
    "com.schriftgestaltung.glyphs",
    "org.unifiedfontobject.ufo",
    "com.glyphsapp.glyphspackage",
    "com.glyphsapp.iconset",
)


def primitive(document, name, *args):
    """Require each NSDocument file primitive independently; never synthesize it."""
    provider = vars(document).get("_file_primitives")
    method = getattr(provider, name, None)
    if not callable(method):
        raise UnsupportedCapability(
            f"Document file primitive {name} requires an explicit lawful adapter",
            capability=f"GSDocument.file_primitives.{name}",
        )
    return method(document, *args)


def required_selector(value, name, *args):
    """Nil messaging is explicit; arbitrary Python equality/path coercion is not."""
    if value is None:
        return None
    method = getattr(value, name, None)
    if not callable(method):
        raise UnsupportedCapability(
            f"Document primitive selector {name} is unavailable",
            capability=f"GSDocument.file_primitives.{name}",
        )
    return method(*args)


def optional_selector(document, name):
    """Check the owned receiver surface without triggering _Strict's fallback.

    A declared descriptor's errors and noncallable selector errors propagate.
    Dynamic Objective-C method resolution needs a separately qualified adapter.
    """
    try:
        getattr_static(document, name)
    except AttributeError:
        return
    getattr(document, name)()


def should_monitor(file_type):
    """Short-circuit the four retained isEqualToString: calls in source order."""
    for literal in _MONITORED_TYPES:
        equal = (
            file_type == literal
            if type(file_type) is str
            else required_selector(file_type, "isEqualToString_", literal)
        )
        if equal:
            return True
    return False


def load_custom(document):
    """Compute parent before synchronization; replace only after init returns."""
    folder = required_selector(document.fileURL(), "URLByDeletingLastPathComponent")
    with document._glyph_info_lock:
        if folder is None:
            document._local_glyph_info = None
        else:
            from .info_manager import GSGlyphsInfo

            allocated = GSGlyphsInfo.alloc()
            manager = allocated.initWithLocalFile_forFont_(folder, document.font)
            document._local_glyph_info = manager
    return True


def set_file_url(document, url):
    """Keep superclass, optional observers and receiver reload in retained order."""
    previous = document.fileURL()
    equal = (url is None and previous is None) or required_selector(
        url, "isEqual_", previous
    )
    if equal:
        primitive(document, "set_file_url", url)
        return
    optional_selector(document, "stopObservingFile")
    primitive(document, "set_file_url", url)
    if document.shouldMonitorFile_(document.fileType()):
        document.startObservingFileIfSupported()
    optional_selector(document, "updateFileObservers")
    document.loadCustomGlyphsData()
