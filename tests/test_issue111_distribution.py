# this_file: tests/test_issue111_distribution.py
"""Check source contracts and fresh distributions supplied by the build audit."""

import email
import os
import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

import pytest
from packaging.requirements import Requirement

ROOT = Path(__file__).parents[1]


def test_readme_when_split_then_installation_and_protocol_links_remain_available():
    readme = (ROOT / "README.md").read_text()
    assert len(readme.splitlines()) < 200, "Keep installation guidance readable"
    assert "src_docs/md/guides/COMPATIBILITY.md" in readme
    protocol = (ROOT / "src_docs/md/guides/COMPATIBILITY.md").read_text()
    for section in (
        "Python 2 source adaptation",
        "Execution receipts and errors",
        "Owned execution scopes",
        "Live model",
        "GlyphsApp host services",
        "Vanilla UI",
        "Runtime entry points",
        "Plugins and editor drawing",
        "Cocoa backend selection",
    ):
        assert section in protocol, f"Preserve existing protocol guidance: {section}"
    assert (
        "src_docs/md/guides/COMPATIBILITY.md"
        in tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"][
            "build"
        ]["targets"]["sdist"]["only-include"]
    )


def test_imports_when_host_unavailable_then_public_and_fake_backend_remain_lazy():
    code = """
import importlib.abc
import sys
class NoHost(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'fontlab', 'fontgate', 'PythonQt',
                                      'AppKit', 'Foundation', 'Cocoa', 'objc'}:
            raise AssertionError('Eager host import: ' + fullname)
sys.meta_path.insert(0, NoHost())
import fontlab_glyport as gp
from fontlab_glyport.model.fake_backend import FakeBackend
for name in ('activate', 'deactivate', 'run_script', 'install_plugin',
             'inspect_source', 'ExecutionContext', 'Receipt'):
    assert callable(getattr(gp, name)), name
assert FakeBackend().fonts
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="module")
def distributions():
    directory = os.environ.get("GLYPORT_DISTRIBUTION_DIR")
    if directory is None:
        pytest.skip("Set GLYPORT_DISTRIBUTION_DIR to fresh wheel/sdist output")
    directory = Path(directory)
    wheels, sdists = list(directory.glob("*.whl")), list(directory.glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1, "Audit one explicit build at a time"
    with zipfile.ZipFile(wheels[0]) as wheel:
        wheel_files = {name: wheel.read(name) for name in wheel.namelist()}
    with tarfile.open(sdists[0]) as sdist:
        sdist_files = {
            str(
                PurePosixPath(member.name).relative_to(member.name.split("/")[0])
            ): sdist.extractfile(member).read()
            for member in sdist.getmembers()
            if member.isfile()
        }
    return wheel_files, sdist_files


def test_artifacts_when_built_then_only_intended_members_and_source_bytes_ship(
    distributions,
):
    wheel, sdist = distributions
    source_files = {
        str(path.relative_to(ROOT / "src")): path.read_bytes()
        for path in (ROOT / "src").rglob("*")
        if path.is_file() and not {"__pycache__", ".DS_Store"}.intersection(path.parts)
    }
    runtime = {
        name: content
        for name, content in wheel.items()
        if not any(part.endswith(".dist-info") for part in PurePosixPath(name).parts)
    }
    assert runtime == source_files, "Do not drop APIs or add runtime payloads"
    for name, content in source_files.items():
        assert sdist[f"src/{name}"] == content, name
    metadata_files = {
        "METADATA",
        "WHEEL",
        "entry_points.txt",
        "RECORD",
        "licenses/LICENSE",
        "licenses/LICENSE-UNICODE-3.0",
        "licenses/NOTICE",
    }
    for name in wheel.keys() - runtime.keys():
        assert name.split(".dist-info/", 1)[1] in metadata_files, name
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    allowed = config["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"]
    for name in sdist:
        assert name in {"PKG-INFO", ".gitignore"} or any(
            name == root or name.startswith(root + "/") for root in allowed
        ), name
    for name in (*wheel, *sdist):
        parts = PurePosixPath(name).parts
        assert not (
            {".local", ".venv", ".git", "__pycache__", ".DS_Store"} & set(parts)
        ), name
        assert not name.endswith((".pyc", ".pyo", ".whl")), name
    private_paths = (
        str(ROOT.resolve()).encode(),
        (str(Path.home()) + "/").encode(),
    )
    for name, content in (*wheel.items(), *sdist.items()):
        assert not any(path in content for path in private_paths), name
    # Apache-2.0 LICENSE always; NOTICE records provenance (T15).
    for license_name in ("LICENSE", "LICENSE-UNICODE-3.0", "NOTICE"):
        if not (ROOT / license_name).exists():
            continue  # the Finder-metadata fixture ships LICENSE only
        license_bytes = (ROOT / license_name).read_bytes()
        assert sdist[license_name] == license_bytes, license_name
        assert (
            next(
                content
                for name, content in wheel.items()
                if name.endswith(f".dist-info/licenses/{license_name}")
            )
            == license_bytes
        ), license_name


@pytest.fixture
def source_with_finder_metadata(tmp_path, monkeypatch):
    """Finder metadata is local source state; archives retain a strict payload."""
    package = tmp_path / "src" / "fontlab_glyport"
    package.mkdir(parents=True)
    runtime = b"public_value = 1\n"
    license_bytes = b"Fixture license\n"
    (package / "__init__.py").write_bytes(runtime)
    for parent in (tmp_path / "src", package):
        (parent / ".DS_Store").write_bytes(b"owner Finder metadata")
    (tmp_path / "LICENSE").write_bytes(license_bytes)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.hatch.build.targets.sdist]\nonly-include = ["src", "LICENSE"]\n'
    )
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    wheel = {
        "fontlab_glyport/__init__.py": runtime,
        "fontlab_glyport-0.0.dist-info/licenses/LICENSE": license_bytes,
    }
    sdist = {"src/fontlab_glyport/__init__.py": runtime, "LICENSE": license_bytes}
    return wheel, sdist


def test_artifact_contract_when_source_has_finder_metadata_then_preserves_it_locally(
    source_with_finder_metadata,
):
    test_artifacts_when_built_then_only_intended_members_and_source_bytes_ship(
        source_with_finder_metadata
    )
    for parent in (ROOT / "src", ROOT / "src/fontlab_glyport"):
        assert (parent / ".DS_Store").read_bytes() == b"owner Finder metadata"


@pytest.mark.parametrize(
    "member", ["fontlab_glyport/.DS_Store", "fontlab_glyport/unexpected.py"]
)
def test_artifact_contract_when_wheel_adds_payload_then_refuses_it(
    source_with_finder_metadata,
    member,
):
    wheel, sdist = source_with_finder_metadata
    wheel[member] = b"extra payload"
    with pytest.raises(
        AssertionError, match="Do not drop APIs or add runtime payloads"
    ):
        test_artifacts_when_built_then_only_intended_members_and_source_bytes_ship(
            (wheel, sdist)
        )


def test_artifact_contract_when_sdist_adds_finder_metadata_then_refuses_it(
    source_with_finder_metadata,
):
    wheel, sdist = source_with_finder_metadata
    sdist["src/fontlab_glyport/.DS_Store"] = b"extra Finder metadata"
    with pytest.raises(AssertionError):
        test_artifacts_when_built_then_only_intended_members_and_source_bytes_ship(
            (wheel, sdist)
        )


def test_artifacts_when_built_then_metadata_preserves_extras_entrypoint_and_readme(
    distributions,
):
    wheel, sdist = distributions
    metadata = email.message_from_bytes(
        next(
            content
            for name, content in wheel.items()
            if name.endswith(".dist-info/METADATA")
        )
    )
    package_info = email.message_from_bytes(sdist["PKG-INFO"])
    for message in (metadata, package_info):
        assert message["Name"] == "fontlab-glyport"
        assert message["Requires-Python"] == ">=3.11"
        assert message["License-Expression"] == "Apache-2.0 AND Unicode-3.0 AND CC0-1.0"
        assert message.get_all("License-File") == [
            "LICENSE",
            "LICENSE-UNICODE-3.0",
            "NOTICE",
        ]
        assert set(message.get_all("Provides-Extra")) == {
            "test",
            "cocoa",
            "geometry",
            "boolean",
            "glyphdata",
            "native",
        }
        requirements = message.get_all("Requires-Dist")
        assert "glyphslib>=6.16.1" in requirements
        assert "fontlab-fontlabapp>=1.2.10" in requirements, (
            "One App floor for every shared module (README 'Shared App mechanics'); "
            "the audited private candidate supplies all imported contracts"
        )
        app_requirement = Requirement(
            next(r for r in requirements if r.startswith("fontlab-fontlabapp>="))
        )
        for old_release in ("0.2.23", "0.2.24", "0.2.25"):
            assert old_release not in app_requirement.specifier, (
                f"App {old_release} lacks the audited contract closure"
            )
        assert "1.2.10" in app_requirement.specifier, (
            "The genuine reviewed App candidate must satisfy the floor"
        )
        assert "1.2.9" not in app_requirement.specifier, "App 1.2.10 is the release floor (own_menu seam)"
        assert "0.2.26.dev0" not in app_requirement.specifier, (
            "Retain the stricter whole-cohort floor; qtsafe alone is insufficient"
        )
        assert "glyphslib>=6.16.1; extra == 'glyphdata'" in requirements
        # Core metadata is UTF-8; retain bytes before the email ASCII fallback.
        payload = message.get_payload(decode=True)
        assert payload.strip() == (ROOT / "README.md").read_bytes().strip()
    entrypoints = next(
        content
        for name, content in wheel.items()
        if name.endswith(".dist-info/entry_points.txt")
    ).decode()
    assert "glyport = fontlab_glyport.cli:main" in entrypoints


def test_sdist_when_migration_tests_ship_then_exact_helper_ships(distributions):
    _, sdist = distributions
    helper = "tools/migrate_app_paths.py"
    assert sdist.get(helper) == (ROOT / helper).read_bytes(), (
        "Packaged migration tests need their exact authored helper"
    )


def test_sdist_when_docs_relocated_then_relative_markdown_links_resolve(distributions):
    _, sdist = distributions
    for name in (
        "README.md",
        "src_docs/md/index.md",
        "src_docs/md/guides/GLYPH_INFO_MANAGER.md",
        "src_docs/md/guides/LAYER_IDENTITIES.md",
        "src_docs/md/guides/glyph-descriptions.md",
        "src_docs/md/guides/COMPATIBILITY.md",
        "src_docs/md/guides/custom-parameters.md",
        "src_docs/md/guides/arabic-presentation.md",
        "src_docs/md/guides/legacy-and-ros.md",
        "src_docs/md/guides/unicode-lookup.md",
        "src_docs/md/guides/production-metadata.md",
    ):
        text = sdist[name].decode()
        assert text == (ROOT / name).read_text()
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#", 1)[0]
            resolved = os.path.normpath(str(PurePosixPath(name).parent / target))
            assert resolved in sdist, f"Broken {name} link: {target}"
