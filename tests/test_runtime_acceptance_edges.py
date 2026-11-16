# this_file: tests/test_runtime_acceptance_edges.py
"""Failure and integration checks use only synthetic owned inputs."""

import json
import os
import plistlib
import subprocess
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from fontlab_glyport import ExecutionContext, inspect_source, install_plugin, run_script
from fontlab_glyport.adaptation_entries import archive_members
from fontlab_glyport.adaptation_modern import adapt_modern
from fontlab_glyport.cli import verify_manifest
from fontlab_glyport.dependencies import request_service, run_process
from fontlab_glyport.entrypoints import (
    ExecutionHost,
    ExecutionOptions,
    PluginRegistration,
)
from fontlab_glyport.errors import AdaptationError, Cancelled, DependencyUnavailable
from fontlab_glyport.profiles import select_profile
from fontlab_glyport.receipt import ReceiptEnvironment, validate_receipt


def fixture_host():
    return ExecutionHost(
        lambda operation: operation(),
        ReceiptEnvironment("fixture", "1", "3.11", "5.15", "test", "test"),
    )


def test_glyphs4_import_has_documented_minimum():
    result = select_profile(
        sources={
            "modern.py": b"from GlyphsApp import GSNameParticle\nlayer.shapes.append(path)\n"
        }
    )
    assert result.profile == "glyphs4"
    conflict = select_profile(
        metadata={"GlyphsVersion": "2"},
        sources={"m.py": b"from GlyphsApp import GSMetric\n"},
    )
    assert conflict.profile == "auto"


@pytest.mark.parametrize("profile", ["glyphs3", "glyphs4"])
def test_modern_cache_identity_integrity_and_no_fissix(tmp_path, profile):
    source = tmp_path / "source.py"
    source.write_bytes("# coding: utf-8\ntext='Łódź'\n".encode())
    with patch.dict(sys.modules, {"fissix": None}):
        adapted = adapt_modern(source, profile=profile, cache_dir=tmp_path / "cache")
        assert adapted.path.read_bytes() == source.read_bytes()
        assert adapted.translate(2, 4).line == 2
        assert adapt_modern(
            source, profile=profile, cache_dir=tmp_path / "cache"
        ).cache_hit
    adapted.path.write_text("broken")
    with pytest.raises(ValueError, match="integrity"):
        adapt_modern(source, profile=profile, cache_dir=tmp_path / "cache")


def test_unsupported_newer_syntax_fails_at_original_location(tmp_path):
    source = tmp_path / "future.py"
    source.write_text("type Name = str\n")
    with pytest.raises(AdaptationError) as caught:
        run_script(source, profile="glyphs4", host=fixture_host())
    assert caught.value.location.path == str(source)
    assert caught.value.handle.state == "failed"


def test_missing_dependency_reports_name_for_lexical_and_dynamic_imports(tmp_path):
    source = tmp_path / "source.py"
    for code in (
        "import fontParts",
        "import importlib; importlib.import_module('fontParts')",
    ):
        source.write_text(code)
        with (
            patch.dict(sys.modules, {"fontParts": None}),
            pytest.raises(DependencyUnavailable, match="fontParts"),
        ):
            ExecutionContext(tmp_path, "glyphs3").run(source)
    source.write_text("import drawBot")
    with pytest.raises(DependencyUnavailable, match="rendering backend"):
        ExecutionContext(tmp_path, "glyphs3").run(source)


def test_explicit_drawbot_provider_remains_scoped(tmp_path):
    source = tmp_path / "source.py"
    source.write_text("from drawBot import render\nvalue = render()")
    module = ModuleType("drawBot")
    module.render = lambda: b"owned-render-output"
    context = ExecutionContext(
        tmp_path, "glyphs3", adapters={"drawBot": lambda: module}
    )
    context.run(source)
    assert context.globals["value"] == b"owned-render-output"
    context.close()


def test_zip_entrypoint_preserves_archive_identity_and_resource_paths(tmp_path):
    archive = tmp_path / "script.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(
            "__main__.py",
            "# GLYPHS_VERSION: 3\nfrom pathlib import Path\nvalue=Path(__file__).with_name('data.txt').read_text()",
        )
        stream.writestr("data.txt", "owned-resource")
    handle = run_script(archive, host=fixture_host())
    assert handle.context.globals["value"] == "owned-resource"
    assert handle.receipt.source.sha256 == inspect_source(archive).source_id
    assert handle.receipt.artifacts
    cache_files = [Path(artifact.path) for artifact in handle.receipt.artifacts]
    handle.close()
    assert all(path.exists() for path in cache_files), (
        "receipt artifacts must survive handle close"
    )


def test_bundle_entry_order_and_shared_globals(tmp_path):
    bundle = tmp_path / "Fixture.glyphsPlugin"
    (bundle / "Contents/Resources").mkdir(parents=True)
    (bundle / "Contents/Info.plist").write_bytes(
        plistlib.dumps(
            {
                "GlyphsVersion": "3",
                "PyMainFileNames": ["z_first.py", "a_second.py"],
                "NSPrincipalClass": "Fixture",
            }
        )
    )
    (bundle / "Contents/Resources/z_first.py").write_text("value=41")
    (bundle / "Contents/Resources/a_second.py").write_text(
        "value += 1\nclass Fixture: pass"
    )
    host = fixture_host()
    seen = []

    def register(context, assessment):
        assert context.globals["value"] == 42
        return PluginRegistration(
            lambda: seen.append("removed"), evidence=("fixture:hooks",)
        )

    host.plugin_installer = register
    handle = install_plugin(bundle, host=host)
    assert validate_receipt(handle.receipt.to_dict(), public=False) == []
    handle.close()
    assert seen == ["removed"]


def test_failure_receipt_persists_and_close_is_idempotent(tmp_path):
    source = tmp_path / "bad.py"
    source.write_text("raise RuntimeError('owned-failure')")
    receipt = tmp_path / "receipt.json"
    with pytest.raises(RuntimeError) as caught:
        run_script(
            source,
            profile="glyphs3",
            host=fixture_host(),
            options=ExecutionOptions(receipt_path=receipt),
        )
    data = json.loads(receipt.read_text())
    assert validate_receipt(data, public=False) == []
    assert any(stage["status"] == "failed" for stage in data["stages"])
    handle = caught.value.handle
    snapshot = handle.receipt
    handle.close()
    handle.close()
    assert handle.receipt == snapshot


def test_existing_receipt_refuses_before_execution(tmp_path):
    marker = tmp_path / "executed"
    source = tmp_path / "script.py"
    source.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')"
    )
    output = tmp_path / "receipt.json"
    output.write_text("preserve")
    with pytest.raises(FileExistsError):
        run_script(
            source,
            profile="glyphs3",
            host=fixture_host(),
            options=ExecutionOptions(receipt_path=output),
        )
    assert output.read_text() == "preserve"
    assert not marker.exists()


def test_foreign_bytecode_inspection_and_native_zip_rejection(tmp_path):
    source = tmp_path / "foreign.pyc"
    source.write_bytes(b"bad!" + bytes(12))
    assert any(
        d.code == "PYC_VERSION_UNSUPPORTED" for d in inspect_source(source).diagnostics
    )
    archive = tmp_path / "native.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("plugin.so", bytes.fromhex("cffaedfe"))
    with pytest.raises(DependencyUnavailable, match="Compiled"):
        archive_members(archive)


def test_service_controlled_success_error_timeout_and_post_cancel():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/fail":
                self.send_error(503)
                return
            self.send_response(200)
            self.end_headers()
            if self.path == "/slow":
                import time

                time.sleep(0.15)
            try:
                self.wfile.write(b"owned-response")
            except BrokenPipeError:
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert request_service(url, timeout=1) == b"owned-response"
        with pytest.raises(DependencyUnavailable):
            request_service(url + "/fail", timeout=1)
        with pytest.raises(DependencyUnavailable):
            request_service(url + "/slow", timeout=0.03)
        cancelled = []

        def transport(url, timeout):
            cancelled.append(True)
            return b"complete"

        with pytest.raises(Cancelled):
            request_service(
                url, timeout=1, transport=transport, cancelled=lambda: bool(cancelled)
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_process_timeout_kills_descendant_pipe_holders():
    code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)']); time.sleep(10)"
    import time

    started = time.monotonic()
    with pytest.raises(DependencyUnavailable, match="timed out"):
        run_process([sys.executable, "-c", code], timeout=0.1)
    assert time.monotonic() - started < 2, (
        "descendant stdout pipes must not block cleanup"
    )


def test_verifier_cancellation_retains_denominator(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "regression_targets": [
                    {"id": str(i), "path": f"repo/{i}.py", "sha256": None}
                    for i in range(32)
                ],
            }
        )
    )
    calls = []

    def runner(row):
        calls.append(row["id"])
        raise Cancelled("fixture cancel")

    report = verify_manifest(manifest, runner=runner)
    assert len(calls) == 1
    assert report["summary"]["blocked"] == 32


@pytest.mark.parametrize(
    "script",
    [
        "native_02_adaptation_callbacks.py",
        "native_03_dependency_routes.py",
        "native_04_public_handles.py",
        "native_05_manifest_verification.py",
    ],
)
def test_native_driver_snippets_compile_and_execute_in_isolated_harness(
    tmp_path, script
):
    if "03_" in script and sys.version_info[:2] != (3, 11):
        pytest.skip("bytecode driver intentionally requires a 3.11 interpreter")
    repo = Path(__file__).resolve().parents[1]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "regression_targets": [
                    {"id": str(i), "path": f"repo/{i}.py", "sha256": None}
                    for i in range(32)
                ],
            }
        )
    )
    harness = """
import contextlib,io,runpy,sys,types
class FontLab:
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def run(self,code,**variables):
        namespace = dict(variables)
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            exec(compile(code,'<remopy-harness>','exec'),namespace)
        return types.SimpleNamespace(value=namespace.get('result'),stdout=out.getvalue(),stderr=err.getvalue())
module=types.ModuleType('fontlab_remopy')
module.FontLab=FontLab
sys.modules['fontlab_remopy']=module
sys.modules['fontlab']=types.ModuleType('fontlab')
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1]).parent/'tests'))
from ui_doubles import make_qt
qt=make_qt()
qt.QtGui.QApplication.instance=staticmethod(lambda: object())
sys.modules['PythonQt']=qt
sys.path.insert(0,sys.argv[1])
driver=sys.argv[2]
sys.argv=[driver]+sys.argv[3:]
runpy.run_path(driver,run_name='__main__')
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            harness,
            str(repo / "native-drivers"),
            str(repo / "native-drivers" / script),
            "--repo",
            str(repo),
            "--manifest",
            str(manifest),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "passed", result.stdout


def test_scoped_subprocess_adapter_requires_deadline_and_keeps_exit_contract(tmp_path):
    source = tmp_path / "process.py"
    source.write_text("import subprocess\nsubprocess.run(['never-spawned'])")
    context = ExecutionContext(tmp_path, "glyphs3")
    with pytest.raises(DependencyUnavailable, match="timeout"):
        context.run(source)
    source.write_text(
        "import subprocess, sys\nresult = subprocess.run([sys.executable, '-c', 'raise SystemExit(7)'], timeout=1)\n"
    )
    context.run(source)
    assert context.globals["result"].returncode == 7
    context.cancel()
    with pytest.raises(Cancelled):
        context.run(source)
    context.close()


@pytest.mark.parametrize("survivors", [(), ("source.py",), ("map.json",)])
def test_modern_cache_when_key_dir_is_emptied_then_it_is_rebuilt(tmp_path, survivors):
    source = tmp_path / "script.py"
    source.write_bytes(b"x = 1\n")
    first = adapt_modern(source, profile="modern", cache_dir=tmp_path / "cache")
    (key_dir,) = (tmp_path / "cache" / "fontlab-glyport").iterdir()
    for child in list(key_dir.iterdir()):
        if child.name not in survivors:
            child.unlink()
    again = adapt_modern(source, profile="modern", cache_dir=tmp_path / "cache")
    assert not again.cache_hit
    assert again.path.read_bytes() == b"x = 1\n"
    assert adapt_modern(source, profile="modern", cache_dir=tmp_path / "cache").cache_hit
    assert first.original_sha256 == again.original_sha256
