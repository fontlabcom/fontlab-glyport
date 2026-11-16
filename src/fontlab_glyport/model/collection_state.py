# this_file: src/fontlab_glyport/model/collection_state.py
"""Restore native collection identities as well as geometry after failed edits."""

# Copy-on-write rebinds keys, objects and node-to-shape references. Selection
# observations and parent links belong to those same identities.
_BINDINGS = ("_objects", "_object_keys", "_parents", "_node_shapes", "_selection_flags")


def _tokens(backend, layer_id):
    children = {
        token for token, parent in backend._parents.items() if parent == layer_id
    }
    nodes = {token for token, parent in backend._parents.items() if parent in children}
    return {layer_id} | children | nodes | backend._layer_members.get(layer_id, set())


def _snapshot(backend, layer_id):
    tokens = _tokens(backend, layer_id)
    maps = {
        name: {k: v for k, v in getattr(backend, name).items() if k in tokens}
        for name in _BINDINGS
    }
    return {
        "tokens": tokens,
        "maps": maps,
        "keys": {k: v for k, v in backend._keys.items() if v in tokens},
        "members": set(backend._layer_members.get(layer_id, ())),
        "owned": set(backend._owned_shapes),
        "component_history": {
            key: value
            for key, value in backend._prepared.items()
            if key[0] == "component_history" and key[1] == layer_id
        },
        "history": {
            name: {
                key: token
                for key, token in getattr(backend, name).items()
                if token in tokens
            }
            for name in ("_history_aliases", "_history_slots")
        },
    }


def snapshot_bindings(backend, layer_id, peers):
    """Include sessions whose proxies also follow this layer's shape clones."""
    result = [(backend, layer_id, _snapshot(backend, layer_id))]
    document = backend._object_keys[layer_id][0]
    package_id = backend._object_keys[document][2]
    native_layer = backend._objects[layer_id]
    native_id = getattr(native_layer, "id", None)
    if native_id is None:  # a pending layer has no shape or peer clone yet
        return result
    for peer in peers:
        if peer is backend:
            continue
        peer_document = peer._keys.get((package_id, "font", package_id))
        if peer_document is None:
            continue
        for token, key in peer._object_keys.items():
            if key[:2] != (peer_document, "layer"):
                continue
            layer = peer._objects.get(token)
            if layer is not None and getattr(layer, "id", None) == native_id:
                result.append((peer, token, _snapshot(peer, token)))
    return result


def restore_bindings(states):
    for backend, layer_id, state in states:
        affected = _tokens(backend, layer_id) | state["tokens"]
        for key, token in list(backend._keys.items()):
            if token in affected:
                del backend._keys[key]
        backend._keys.update(state["keys"])
        for name, saved in state["history"].items():
            mapping = getattr(backend, name)
            for key, token in list(mapping.items()):
                if token in affected:
                    del mapping[key]
            mapping.update(saved)
        for name in _BINDINGS:
            mapping = getattr(backend, name)
            for token in affected:
                mapping.pop(token, None)
            mapping.update(state["maps"][name])
        backend._layer_members[layer_id] = set(state["members"])
        backend._owned_shapes = set(state["owned"])
        for key in tuple(backend._prepared):
            if key[0] == "component_history" and key[1] == layer_id:
                del backend._prepared[key]
        backend._prepared.update(state["component_history"])
        backend._revision += 1  # every session's record cache must see restoration
