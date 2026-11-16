# this_file: tests/test_glyph_ros.py
"""ROS data boundaries refuse before metadata changes or presentation processing."""

from types import SimpleNamespace as NS

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import GSCustomParameter, GSGlyph, Model, glyph_metadata
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.mark.parametrize("registry", ["CNS1", "GB1", "Japan1", "KR", "Korea1"])
@pytest.mark.parametrize("separator", ["-", ", "])
@pytest.mark.parametrize("supplement", ["7", "", "owned"])
def test_ros_when_bundled_map_is_required_then_refuses_exact_text_contract(
    registry, separator, supplement
):
    font = Model(FakeBackend()).font
    glyph = font.glyphs["A"]
    font.customParameters["ROS"] = separator.join(["Adobe", registry, supplement])
    before = (glyph.name, glyph.unicodes, glyph._case_state())
    with pytest.raises(UnsupportedCapability) as error:
        glyph.updateGlyphInfo()
    assert error.value.capability == "GSGlyphInfo.ROS.mappingData"
    assert (glyph.name, glyph.unicodes, glyph._case_state()) == before, (
        "Unavailable ROS data must refuse before any metadata write"
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "Adobe-Japan1",
        "Adobe-Japan1-7-extra",
        "Adobe,Japan1,7",
        "Adobe,  Japan1, 7",
        " Adobe-Japan1-7",
        "adobe-Japan1-7",
        "Adobe-Unknown-7",
        "Adobe, Japan1, 7-extra-more",
    ],
)
def test_ros_when_exact_shipped_resource_is_absent_then_keeps_original_record(value):
    # Three hyphen-separated pieces suppress the comma-form fallback entirely.
    glyph = NS(parent=NS(customParameters={"ROS": value}))
    info = NS(name="A", unicode="0041")
    assert glyph_metadata.ros_unicode(glyph, info) is info
    assert vars(info) == {"name": "A", "unicode": "0041"}


@pytest.mark.parametrize("value", ["Adobe-Japan1-7\n", "Adobe, Japan1, 7-extra"])
def test_ros_when_supplement_is_not_numeric_then_still_requires_map(value):
    glyph = NS(parent=NS(customParameters={"ROS": value}))
    with pytest.raises(UnsupportedCapability) as error:
        glyph_metadata.ros_unicode(glyph, NS(name="A"))
    assert error.value.capability == "GSGlyphInfo.ROS.mappingData"


@pytest.mark.parametrize("value", [False, 0, 1, 0.5, [], {}, object()])
def test_ros_when_nontext_requires_native_description_then_refuses(value):
    glyph = NS(parent=NS(customParameters={"ROS": value}))
    with pytest.raises(UnsupportedCapability) as error:
        glyph_metadata.ros_unicode(glyph, NS(name="A"))
    assert error.value.capability == "GSGlyphInfo.ROS.value"


def test_ros_when_record_or_parent_is_missing_then_does_not_read_parameters():
    assert glyph_metadata.ros_unicode(NS(), None) is None
    info = NS(name="A")
    assert glyph_metadata.ros_unicode(NS(parent=None), info) is info


def test_ros_when_first_active_parameter_is_unknown_then_preserves_active_order(
    owned_edit_info,
):
    font = Model(FakeBackend()).font
    font.parent._local_glyph_info = owned_edit_info
    glyph = font.glyphs["A"]
    first = GSCustomParameter("ROS", "Adobe-Unknown-7")
    second = GSCustomParameter("ROS", "Adobe-Japan1-7")
    font.customParameters.extend([first, second])
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0041", "0061"], (
        "An absent ROS map preserves the preceding additional-Unicode stage"
    )
    first.active = False
    with pytest.raises(UnsupportedCapability):
        glyph.updateGlyphInfo(changeName=False)


def test_ros_when_required_then_refuses_between_additional_and_presentation(
    monkeypatch,
):
    from fontlab_glyport.model import unicode_case

    font = Model(FakeBackend()).font
    glyph = font.glyphs.append(GSGlyph("alef-ar"))
    font.customParameters["ROS"] = "Adobe-Japan1-7"
    calls = []

    def additional(glyph, info, *args):
        calls.append("additional")
        return info

    def presentation(*args):
        raise AssertionError("ROS must finish before presentation processing")

    monkeypatch.setattr(unicode_case, "additional_unicode", additional)
    monkeypatch.setattr(unicode_case, "presentation_unicode", presentation)
    with pytest.raises(UnsupportedCapability):
        glyph_metadata.resolve(glyph)
    assert calls == ["additional"]


def test_ros_when_keep_name_bypasses_resolution_then_remains_bypassed():
    font = Model(FakeBackend()).font
    glyph = font.glyphs["A"]
    glyph.category = "Icon"
    font.customParameters["ROS"] = "Adobe-Japan1-7"
    assert glyph_metadata.resolve(glyph).category == "Icon"
