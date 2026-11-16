# this_file: tests/test_ui_graph_delegation.py
"""Foreign frame policy wraps App records and the shared graph algorithms."""

import dataclasses
import inspect
import json
import pickle

import fontlabapp.qt.ui_graph as shared
import pytest

from fontlab_glyport.ui.graph import Connection, Frame, Node, UIGraph, resolve_frame


def test_graph_when_adapter_loaded_then_shared_algorithms_and_compatibility_records():
    assert issubclass(UIGraph, shared.UIGraph)
    assert issubclass(Node, shared.Node)
    assert Connection is shared.Connection
    assert UIGraph.connect is shared.UIGraph.connect
    assert UIGraph.to_json is shared.UIGraph.to_json
    assert Node.to_json is shared.Node.to_json
    assert list(inspect.signature(Node).parameters) == [
        "node_id",
        "source_class",
        "source_id",
        "parent_id",
        "frame",
        "properties",
        "resources",
        "attribute_name",
    ]
    assert inspect.signature(Node).parameters["frame"].annotation == Frame | None
    assert (
        inspect.signature(UIGraph.add_node).parameters["frame"].annotation
        == Frame | None
    )
    assert inspect.signature(UIGraph).parameters == {}


@pytest.mark.parametrize(
    "frame", [None, Frame(10, -30, -10, 20), Frame(0, 0, "auto", "auto")]
)
def test_graph_when_round_tripped_then_frame_type_json_pickle_and_frozen_contract(
    frame,
):
    graph = UIGraph()
    root = graph.add_node("vanilla.Window")
    node = graph.add_node(
        "vanilla.Button",
        parent_id=root.node_id,
        frame=frame,
        properties={"title": "OK"},
    )
    graph.connect(node.node_id, root.node_id, "action", "okCallback")
    assert type(node) is Node and node.frame is frame
    raw = graph.to_json()
    assert raw["nodes"][1]["frame"] == (frame.to_json() if frame else None)
    restored = UIGraph.from_json(json.loads(json.dumps(raw)))
    assert type(restored) is UIGraph
    assert restored.children("n1") == (node,)
    assert type(restored.children("n1")[0]) is Node
    assert restored.add_node("vanilla.Button").node_id == "n3"
    assert pickle.loads(pickle.dumps(node)) == node
    with pytest.raises(dataclasses.FrozenInstanceError):
        node.frame = None


def test_add_node_when_called_then_original_arguments_forward_to_shared_builder(
    monkeypatch,
):
    seen = []
    marker = object()
    frame = Frame(1, 2, 3, 4)

    def add(self, source_class, **kwargs):
        seen.append((source_class, kwargs))
        return marker

    monkeypatch.setattr(shared.UIGraph, "add_node", add)
    assert (
        UIGraph().add_node(
            "vanilla.Button",
            parent_id="n1",
            frame=frame,
            properties={"text": "x"},
            resources={"image": "i"},
            source_id="source",
            attribute_name="button",
        )
        is marker
    )
    assert seen == [
        (
            "vanilla.Button",
            {
                "parent_id": "n1",
                "frame": frame,
                "properties": {"text": "x"},
                "resources": {"image": "i"},
                "source_id": "source",
                "attribute_name": "button",
            },
        )
    ]


def test_node_when_frame_fields_missing_or_invalid_then_original_refusal():
    with pytest.raises(KeyError, match="frame"):
        Node.from_json({"node_id": "n1", "source_class": "Control"})
    data = Node("n1", "Control").to_json()
    data["frame"] = {"left": "auto", "top": 0, "width": 1, "height": 1}
    with pytest.raises(TypeError, match="Frame.left"):
        Node.from_json(data)
    assert resolve_frame(Frame(-10, -20, "auto", -5), 100, 200, size_hint=(30, 40)) == (
        90,
        180,
        30,
        15,
    )


@pytest.mark.parametrize("pos_size", ["auto", (30, 40), (1, 2, 3, 4)])
def test_frame_when_vanilla_input_then_stays_in_adapter(pos_size):
    frame = Frame.from_pos_size(pos_size)
    assert type(frame) is Frame
    assert not hasattr(shared, "resolve_frame") and not hasattr(shared, "Frame")
