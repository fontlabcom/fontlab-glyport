# this_file: tests/test_ui_nib_limits.py
"""Hostile NIB/XIB inputs are rejected with NibFormatError, never expanded (R031)."""

import plistlib
import struct

import pytest

from fontlab_glyport.ui import nib_archive, nib_graph
from fontlab_glyport.ui.nib_archive import NibFormatError, read_nib
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib


class Keyed:
    """Build an NSKeyedArchiver plist: objects are dicts, references are UIDs."""

    def __init__(self):
        self.objects = ["$null"]

    def add(self, cls, **fields):
        self.objects.append(None)
        index = len(self.objects) - 1
        self.objects.append({"$classname": cls, "$classes": [cls, "NSObject"]})
        record = {"$class": plistlib.UID(index + 1)}
        record.update(fields)
        self.objects[index] = record
        return plistlib.UID(index)

    def array(self, uids):
        return self.add("NSMutableArray", **{"NS.objects": list(uids)})

    def write(self, path, root):
        top = {"IB.objectdata": root}
        data = {
            "$version": 100000,
            "$archiver": "NSKeyedArchiver",
            "$top": top,
            "$objects": self.objects,
        }
        path.write_bytes(plistlib.dumps(data, fmt=plistlib.FMT_BINARY))
        return path


def _nib_with_views(tmp_path, make_views):
    k = Keyed()
    owner = k.add("NSCustomObject", NSClassName="Owner")
    top = make_views(k)
    root = k.add(
        "NSIBObjectData",
        NSRoot=owner,
        NSObjectsKeys=k.array([owner, top]),
        NSObjectsValues=k.array([owner, owner]),
        NSConnections=k.array([]),
    )
    return k.write(tmp_path / "x.nib", root)


def _view(k, subviews=()):
    return k.add(
        "NSView",
        NSFrame="{{0, 0}, {10, 10}}",
        NSvFlags=12,
        NSSubviews=k.array(subviews),
    )


def test_nib_when_view_shared_by_two_parents_then_rejected(tmp_path):
    def views(k):
        leaf = _view(k)
        return _view(k, [_view(k, [leaf]), _view(k, [leaf])])

    with pytest.raises(NibFormatError, match="more than once"):
        graph_from_nib(_nib_with_views(tmp_path, views))


def test_nib_when_subviews_cycle_then_rejected(tmp_path):
    def views(k):
        a = _view(k)
        k.objects[a.data]["NSSubviews"] = k.array([a])  # a view inside itself
        return a

    with pytest.raises(NibFormatError):
        graph_from_nib(_nib_with_views(tmp_path, views))


def test_nib_when_nesting_too_deep_then_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(nib_graph, "MAX_DEPTH", 5)

    def views(k):
        view = _view(k)
        for _ in range(8):
            view = _view(k, [view])
        return view

    with pytest.raises(NibFormatError, match="deep"):
        graph_from_nib(_nib_with_views(tmp_path, views))


def test_nib_when_too_many_nodes_then_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(nib_graph, "MAX_NODES", 10)
    with pytest.raises(NibFormatError, match="nodes"):
        graph_from_nib(
            _nib_with_views(tmp_path, lambda k: _view(k, [_view(k) for _ in range(20)]))
        )


def _nibarchive(objects=0, keys=0, values=0, classes=0, body=b""):
    header = struct.pack("<10I", 1, 10, objects, 50, keys, 50, values, 50, classes, 50)
    return nib_archive.MAGIC + header + body


def test_nibarchive_when_varint_too_wide_then_rejected(tmp_path):
    path = tmp_path / "v.nib"
    path.write_bytes(_nibarchive(objects=1, body=b"\x00" * 10_001 + b"\x81\x81\x81"))
    with pytest.raises(NibFormatError, match="varint"):
        read_nib(path)


def test_nibarchive_when_counts_exceed_data_then_rejected(tmp_path):
    path = tmp_path / "c.nib"
    path.write_bytes(_nibarchive(objects=10_000_000))
    with pytest.raises(NibFormatError):
        read_nib(path)


def test_nib_when_file_too_large_then_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(nib_archive, "MAX_BYTES", 64)
    path = tmp_path / "big.nib"
    path.write_bytes(_nibarchive(body=b"\x00" * 100))
    with pytest.raises(NibFormatError, match="large"):
        read_nib(path)


def test_keyed_when_reference_chain_too_deep_then_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(nib_archive, "MAX_DECODE_DEPTH", 20)
    k = Keyed()
    node = k.add("Leaf")
    for _ in range(50):
        node = k.add("Wrap", inner=node)
    path = k.write(tmp_path / "deep.nib", k.add("NSIBObjectData", NSRoot=node))
    with pytest.raises(NibFormatError, match="deep"):
        read_nib(path)


def test_xib_when_doctype_or_entity_then_rejected(tmp_path):
    path = tmp_path / "bomb.xib"
    path.write_text(
        '<?xml version="1.0"?><!DOCTYPE document [<!ENTITY a "aaaa">]>'
        '<document type="com.apple.InterfaceBuilder3.Cocoa.XIB"><objects/></document>'
    )
    with pytest.raises(NibFormatError, match="DTD"):
        graph_from_xib(path)


def test_xib_when_nesting_too_deep_then_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(nib_graph, "MAX_DEPTH", 5)
    inner = '<customView id="leaf"/>'
    for index in range(8):
        inner = f'<customView id="v{index}"><subviews>{inner}</subviews></customView>'
    path = tmp_path / "deep.xib"
    path.write_text(
        '<document type="com.apple.InterfaceBuilder3.Cocoa.XIB"><objects>'
        + inner
        + "</objects></document>"
    )
    with pytest.raises(NibFormatError, match="deep"):
        graph_from_xib(path)


def test_xib_when_utf16_with_entity_then_rejected(tmp_path):
    text = (
        '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE document [<!ENTITY x "EXPANDED">]>'
        '<document type="com.apple.InterfaceBuilder3.Cocoa.XIB"><objects>'
        '<customObject id="-2" customClass="&x;"/></objects></document>'
    )
    path = tmp_path / "u16.xib"
    path.write_bytes(text.encode("utf-16"))
    with pytest.raises(NibFormatError, match="DTD"):
        graph_from_xib(path)


def test_xib_when_xml_tree_too_deep_even_in_ignored_elements_then_rejected(tmp_path):
    inner = "<x>" * 2000 + "</x>" * 2000
    path = tmp_path / "deepxml.xib"
    path.write_text(
        '<document type="com.apple.InterfaceBuilder3.Cocoa.XIB"><objects>'
        f'<customObject id="-2"><connections>{inner}</connections></customObject>'
        "</objects></document>"
    )
    with pytest.raises(NibFormatError, match="XML"):
        graph_from_xib(path)


def test_xib_when_too_many_elements_then_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(nib_graph, "MAX_XML_ELEMENTS", 50)
    path = tmp_path / "wide.xib"
    path.write_text(
        '<document type="com.apple.InterfaceBuilder3.Cocoa.XIB"><objects>'
        + "<x/>" * 100
        + "</objects></document>"
    )
    with pytest.raises(NibFormatError, match="XML"):
        graph_from_xib(path)
