# this_file: tests/test_issue122_t15_docs.py
"""Public documents state one App floor and no repeated prose (issue 122 T15).

The floor in README.md and DEPENDENCIES.md must equal the pyproject
requirement. Repeated sentences were the symptom of appended candidate notes.
The Apache-2.0 Vanilla session code needs its licence text and NOTICE entry.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
APP_VERSION = re.compile(
    r"(?<![\w-])fontlab-fontlabapp>=(\d+\.\d+\.\d+(?:\.dev\d+)?)(?![\w.]*\d)"
)
# Any App floor mention, however spaced or truncated: each must also be strict.
LOOSE_APP_VERSION = re.compile(
    r"(?<![\w-])(?:fontlab-fontlabapp|App)\s*[<>=!~]=?\s*\d", re.IGNORECASE
)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _app_floor() -> str:
    """The version in pyproject's ``fontlab-fontlabapp>=`` requirement."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    (requirement,) = [
        dep for dep in project["dependencies"] if dep.startswith("fontlab-fontlabapp")
    ]
    return requirement.split(">=", 1)[1]


def _prose_sentences(text: str) -> list[str]:
    """Sentences outside fenced code and tables, whitespace-normalized."""
    prose, fenced = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if not fenced and not line.lstrip().startswith("|"):
            prose.append(line)
    words = " ".join(" ".join(prose).split())
    return [part for part in SENTENCE_END.split(words) if len(part) > 30]


def test_docs_when_app_version_named_then_it_is_the_pyproject_floor() -> None:
    floor = _app_floor()
    for name in ("README.md", "DEPENDENCIES.md"):
        text = (ROOT / name).read_text()
        assert len(LOOSE_APP_VERSION.findall(text)) == len(APP_VERSION.findall(text)), (
            f"{name} has App floor mentions the strict form does not accept"
        )
        named = set(APP_VERSION.findall(text))
        assert named == {floor}, f"{name} names App versions {named}, floor {floor}"


def test_loose_detector_when_near_misses_then_strict_form_rejects_them() -> None:
    for near in (
        "App>=1.1.0",
        "fontlab-fontlabapp >= 1.1.0",
        "fontlab-fontlabapp>=1.1.0.1",
        "fontlab-fontlabapp>=1.2",
        "fontlab-fontlabapp==1.2.0",
        "App > 1.2.0",
    ):
        assert LOOSE_APP_VERSION.findall(near), f"{near!r} must be detected"
        assert len(APP_VERSION.findall(near)) < len(LOOSE_APP_VERSION.findall(near))
    assert APP_VERSION.findall("my-fontlabapp>=1.2.0") == []
    exact = "`fontlab-fontlabapp>=1.2.0` and `fontlab-fontlabapp>=1.3.0.dev4`"
    assert APP_VERSION.findall(exact) == ["1.2.0", "1.3.0.dev4"]
    assert len(LOOSE_APP_VERSION.findall(exact)) == 2


def test_readme_when_read_then_no_sentence_repeats() -> None:
    sentences = _prose_sentences((ROOT / "README.md").read_text())
    repeated = {s for s in sentences if sentences.count(s) > 1}
    assert repeated == set(), repeated


def test_readme_when_read_then_one_shared_app_mechanics_table() -> None:
    text = (ROOT / "README.md").read_text()
    assert text.count("## Shared App mechanics") == 1
    used = set(
        re.findall(
            r"fontlabapp\.([a-z_]+(?:\.[a-z_]+)*)",
            "".join(p.read_text() for p in (ROOT / "src").rglob("*.py")),
        )
    )
    table = set(re.findall(r"^\| `([a-z_]+(?:\.[a-z_]+)*)` \|", text, re.MULTILINE))
    assert used <= table, f"README table misses App modules: {sorted(used - table)}"


def test_license_when_apache_session_code_ships_then_notice_and_text_ship() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    files = project["project"]["license-files"]
    assert files == ["LICENSE", "LICENSE-UNICODE-3.0", "NOTICE"]
    assert project["project"]["license"] == "Apache-2.0 AND Unicode-3.0 AND CC0-1.0"
    sdist = project["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"]
    assert set(files) <= set(sdist)
    notice = (ROOT / "NOTICE").read_text()
    assert "src/fontlab_glyport/ui/session.py" in notice
    assert "Apache License, Version 2.0" in (ROOT / "LICENSE").read_text()
    header = (ROOT / "src/fontlab_glyport/ui/session.py").read_text().splitlines()[1]
    assert header == "# SPDX-License-Identifier: Apache-2.0"


def test_unicode_data_when_shipped_then_public_license_and_provenance_are_present():
    import json

    path = ROOT / "src/fontlab_glyport/data/unicode17_lowercase.json"
    data = json.loads(path.read_text())
    assert data["unicode_version"] == "17.0.0", "Casing must not drift with Python"
    assert len(data["lowercase"]) == 1488, "Retain the complete scalar mapping"
    assert data["lowercase"]["1C89"] == ["1C8A"], "Do not fall back to Python14 data"
    assert "UNICODE LICENSE V3" in (ROOT / "LICENSE-UNICODE-3.0").read_text()
    assert "unicode17_lowercase.json" in (ROOT / "NOTICE").read_text()
    assert (
        "2e1efc1dcb59c575eedf5ccae60f95229f706ee6d031835247d843c11d96470c"
        in (ROOT / "DEPENDENCIES.md").read_text()
    )
