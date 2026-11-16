# this_file: realuse/oracles/p-scrawl.py
"""Scrawl (jenskutilek--Scrawl-Glyphs/Scrawl.glyphsTool/.../plugin.py), a drawing tool:
it paints a bitmap sketch into the layer's user data with mouse drags.
Its result needs the tool registered in FontLab's toolbar and driven by mouse
events; FontLab 9.0.9783 has no Python tool API, 9784 adds Python tool
registration (owner question Q-107). Same rule as p-extrudetool (controller
ruling 2026-10-16): the plugin installs and its tool is either registered (at
least one host registration, no refused "tool:" hook) or refused precisely as
FontLab.register_tool, the ruled host limitation R054 on 9783 (the harness then
classifies the run and asserts registration separately, so 9783 never passes).
Without mouse input the font stays unchanged."""

import re


def registered(installed):
    evidence = installed.get("registration") or []
    counts = [
        int(m.group(1))
        for e in evidence
        if (m := re.search(r"loaded: (\d+) host registrations", e))
    ]
    refused = [e for e in evidence if e.startswith("tool:")]
    precise = bool(refused) and all("FontLab.register_tool" in e for e in refused)
    return (bool(counts) and counts[0] >= 1 and not refused) or precise, evidence


def check(o):
    installed = o.extra.get("install", {})
    ok, evidence = registered(installed)
    o.clause(
        "installed; tool registered, or refused precisely as FontLab.register_tool (R054)",
        installed.get("state") == "active" and not installed.get("capability") and ok,
        {
            "state": installed.get("state"),
            "error": installed.get("error"),
            "registration": evidence,
        },
    )
    o.unchanged()


def example(o):
    o.extra = {
        "install": {
            "state": "active",
            "registration": ["SelectTool Scrawl loaded: 1 host registrations"],
        }
    }


def no_tool_api(o):  # FontLab 9780 / glyport without tool registration
    o.extra = {
        "install": {
            "state": None,
            "error": "UnsupportedCapability",
            "capability": "FontLab.register_tool",
        }
    }


def tool_refused_otherwise(o):  # a refusal that is not the ruled host limitation
    o.extra = {
        "install": {
            "state": "active",
            "registration": [
                "SelectTool Scrawl loaded: 0 host registrations",
                "tool: Unsupported capability: GlyphsApp.GSToolbarItem",
            ],
        }
    }


def no_registration_evidence(o):
    o.extra = {"install": {"state": "active"}}


COUNTEREXAMPLES = [no_tool_api, tool_refused_otherwise, no_registration_evidence]
