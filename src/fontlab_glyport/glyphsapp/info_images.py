# this_file: src/fontlab_glyport/glyphsapp/info_images.py
"""Image registration order with explicit decoder/type/registry dependencies.

No Cocoa, UTType or drawing fidelity is implied by an owned recording provider.
Nil image decoding has no fabricated successful registry entry.
"""

from posixpath import join, splitext

from .info_runtime import provider_method, state_for


def load_icons(manager, folder):
    provider = state_for(manager).provider
    resolved = provider_method(provider, "resolve_path")(folder)
    if resolved is None:
        return
    names = provider_method(provider, "directory_entries")(resolved)
    for name in names if names is not None else ():
        path = provider_method(provider, "resolve_path")(join(resolved, name))
        if not provider_method(provider, "is_image")(path):
            continue
        title = splitext(name)[0]
        if title.endswith("@2x"):
            continue
        image = provider_method(provider, "load_image")(path)
        if image is not None:
            image.setName_(title)
            if title.endswith("Template"):
                image.setTemplate_(True)


def load_global_icons(manager):
    provider = state_for(manager).provider
    path = join(provider_method(provider, "user_support_path")(), "Info", "Icons")
    manager.loadCustomIcons_(path)
    image = provider_method(provider, "draw_emoji_icon")(17, 17, True)
    if image is not None:
        image.setName_("GSEmojiIcon")
    return True
