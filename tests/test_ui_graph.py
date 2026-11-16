# this_file: tests/test_ui_graph.py
"""The versioned UI graph keeps vanilla layout facts and resolves posSize exactly."""

import json

import pytest

from fontlab_glyport.ui.graph import (
    UI_GRAPH_VERSION,
    Connection,
    Frame,
    Node,
    UIGraph,
    resolve_frame,
)


def _sample() -> UIGraph:
    graph = UIGraph()
    win = graph.add_node("vanilla.Window", frame=Frame.from_pos_size((300, 200)))
    btn = graph.add_node(
        "vanilla.Button",
        parent_id=win.node_id,
        frame=Frame(10, -30, -10, 20),
        properties={"title": "OK", "sizeStyle": "small"},
        source_id="script.py:12",
        attribute_name="w.ok",
    )
    graph.add_node(
        "vanilla.TextBox", parent_id=win.node_id, frame=Frame(0, 0, "auto", "auto")
    )
    graph.connect(btn.node_id, win.node_id, "action", "okCallback", argument=None)
    return graph


def test_add_node_when_called_repeatedly_then_ids_increment_and_children_keep_order():
    graph = _sample()
    assert [n["node_id"] for n in graph.to_json()["nodes"]] == ["n1", "n2", "n3"]
    assert [c.node_id for c in graph.children("n1")] == ["n2", "n3"]
    assert graph.children("n2") == ()


def test_add_node_when_parent_unknown_then_value_error():
    with pytest.raises(ValueError, match="n9"):
        UIGraph().add_node("vanilla.Button", parent_id="n9")


def test_connect_when_endpoint_unknown_then_value_error():
    graph = _sample()
    with pytest.raises(ValueError, match="n9"):
        graph.connect("n2", "n9", "action", "cb")


def test_node_fields_when_added_then_stored_verbatim():
    node = _sample().children("n1")[0]
    assert isinstance(node, Node)
    assert node.source_class == "vanilla.Button"
    assert node.source_id == "script.py:12"
    assert node.attribute_name == "w.ok"
    assert node.parent_id == "n1"
    assert node.frame == Frame(10, -30, -10, 20)
    assert node.properties == {"title": "OK", "sizeStyle": "small"}
    assert node.resources == {}


def test_to_json_when_round_tripped_then_equal_and_json_serializable():
    graph = _sample()
    data = graph.to_json()
    assert data["version"] == UI_GRAPH_VERSION == 1
    text = json.dumps(data, sort_keys=True)
    rebuilt = UIGraph.from_json(json.loads(text))
    assert rebuilt.to_json() == data
    assert rebuilt.children("n1") == graph.children("n1")


def test_from_json_when_extended_then_ids_continue():
    rebuilt = UIGraph.from_json(_sample().to_json())
    assert rebuilt.add_node("vanilla.Button").node_id == "n4"


def test_connection_when_serialized_then_fields_present():
    data = _sample().to_json()
    assert data["connections"] == [
        {
            "owner_id": "n2",
            "target_id": "n1",
            "event": "action",
            "selector": "okCallback",
            "argument": None,
        }
    ]
    assert Connection(**data["connections"][0]).event == "action"


@pytest.mark.parametrize("version", [0, 2, None, "1"])
def test_from_json_when_version_differs_then_value_error(version):
    data = _sample().to_json()
    data["version"] = version
    with pytest.raises(ValueError, match="version"):
        UIGraph.from_json(data)


def test_from_json_when_version_missing_then_value_error():
    with pytest.raises(ValueError, match="version"):
        UIGraph.from_json({"nodes": [], "connections": []})


@pytest.mark.parametrize(
    ("frame", "parent", "expected"),
    [
        (Frame(10, 20, 100, 50), (300, 200), (10, 20, 100, 50)),
        (Frame(-110, -60, 100, 50), (300, 200), (190, 140, 100, 50)),
        (Frame(10, 20, 0, 0), (300, 200), (10, 20, 290, 180)),
        (Frame(10, 20, -10, -20), (300, 200), (10, 20, 280, 160)),
        (Frame(-100, -50, 0, 0), (300, 200), (200, 150, 100, 50)),
        (Frame(-100, -50, -10, -5), (300, 200), (200, 150, 90, 45)),
        (Frame(0.5, 1.25, 10.5, 2.75), (300, 200), (0.5, 1.25, 10.5, 2.75)),
        (Frame(-0.5, 0, -0.25, 0), (10.5, 8), (10.0, 0, 0.25, 8)),
        (Frame.from_pos_size((300, 200)), (1000, 800), (0, 0, 300, 200)),
        (Frame.from_pos_size((10, 20, 30, 40)), (300, 200), (10, 20, 30, 40)),
    ],
)
def test_resolve_frame_when_vanilla_posSize_then_edges_follow_rules(
    frame, parent, expected
):
    assert resolve_frame(frame, *parent) == expected


def test_resolve_frame_when_auto_then_uses_size_hint():
    frame = Frame(5, 6, "auto", "auto")
    assert resolve_frame(frame, 300, 200, size_hint=(80, 22)) == (5, 6, 80, 22)
    assert resolve_frame(frame, 300, 200) == (5, 6, 0, 0)
    mixed = Frame(5, 6, 40, "auto")
    assert resolve_frame(mixed, 300, 200, size_hint=(80, 22)) == (5, 6, 40, 22)


def test_frame_when_left_is_auto_or_length_wrong_then_error():
    with pytest.raises(TypeError):
        Frame("auto", 0, 1, 1)
    with pytest.raises(ValueError):
        Frame.from_pos_size((1, 2, 3))
    with pytest.raises(TypeError):
        Frame(0, 0, "wide", 1)
