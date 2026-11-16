# this_file: src/fontlab_glyport/entrypoints.py
"""Public lifecycle entry points with explicit host dispatch and receipt snapshots.

ExecutionHost is the integration seam for GUI dispatch, model/UI providers and
plugin hook registration. A missing registrar never counts as installation.
Persisted runtime receipts are private (public=False); publish aliases separately.
"""

import hashlib
import importlib.metadata
import platform
import plistlib
import tempfile
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from .errors import (
    GlyportError,
    HostUnavailable,
    StaleNativeObject,
    UnsupportedCapability,
)
from .execution import ExecutionContext, check_cocoa_request
from .inspection import inspect_source
from .profile_versions import PROFILE_VERSIONS
from .receipt import (
    Artifact,
    Capability,
    Receipt,
    ReceiptAdapter,
    ReceiptDiagnostic,
    ReceiptEnvironment,
    ReceiptSource,
    Stage,
    write_receipt,
)


@dataclass(frozen=True)
class ExecutionOptions:
    source_root: Path | None = None
    dependency_paths: tuple[Path, ...] = ()
    receipt_path: Path | None = None
    cocoa_backend: str = "auto"


@dataclass(frozen=True)
class PluginRegistration:
    unload: Callable[[], object]
    windows: tuple[object, ...] = ()
    evidence: tuple[str, ...] = ()
    plugin: object = None  # the loaded plugin instance, for drivers and tests


@dataclass
class ExecutionHost:
    """An explicit host gateway; dispatch must execute on the native GUI thread.

    adapter_factory receives the context and resolved font; plugin_installer
    must attach every required hook atomically, rolling back its own failures.
    Registration returns evidence and an idempotent teardown function.
    """

    dispatch: Callable
    environment: ReceiptEnvironment
    adapter_factory: Callable = lambda context, font: {}
    current_font: Callable = lambda: None
    plugin_installer: Callable | None = None
    sink: Callable | None = None


def _native_host() -> ExecutionHost:
    try:
        import fontlab  # noqa: F401 - presence identifies the actual host
        from PythonQt import QtGui
    except ImportError as error:
        raise HostUnavailable(
            "run_script/install_plugin require FontLab or an explicit ExecutionHost."
        ) from error

    def dispatch(operation):
        # The measured PythonQt host lacks QThread.currentThread. Match the
        # existing Pythonqtside host boundary instead of guessing a Qt API.
        app = QtGui.QApplication.instance()
        if app is None or threading.current_thread() is not threading.main_thread():
            raise HostUnavailable(
                "Call from FontLab's GUI thread or inject a GUI-thread dispatcher."
            )
        return operation()

    def adapters(context, font):
        from .glyphsapp.fontlab_session import FontLabSession
        from .model.fontlab_backend import OwnedPackage

        if font is not None and not isinstance(font, OwnedPackage):
            raise UnsupportedCapability(
                "Explicit font must be an OwnedPackage, or use a host adapter_factory for that font type.",
                capability="execution:font-binding",
            )
        # Profile version is a compatibility value, never the FontLab version.
        # One session per context: GlyphsApp (+ menu, drawing callbacks),
        # GlyphsApp.plugins, vanilla(.dialogs), AppKit/Foundation/Cocoa, objc;
        # plugins.register_plugin uses the same session for install_plugin.
        session = FontLabSession(
            context,
            version=PROFILE_VERSIONS[context.profile],
            packages=[font] if font is not None else None,
            interactive=True,
        )
        return session.adapters()

    environment = ReceiptEnvironment(
        "FontLab",
        None,
        platform.python_version(),
        None,
        platform.system(),
        platform.machine(),
    )
    return ExecutionHost(
        dispatch,
        environment,
        adapter_factory=adapters,
        plugin_installer=_native_registrar,
    )


def _native_registrar(context, assessment) -> PluginRegistration:
    """L2 integration seam: register_plugin(context, assessment) -> PluginRegistration."""
    import importlib

    name = "fontlab_glyport.plugins.register_plugin"
    try:
        plugins = importlib.import_module("fontlab_glyport.plugins")
    except ModuleNotFoundError as error:
        if error.name != "fontlab_glyport.plugins":
            raise
        raise UnsupportedCapability(
            f"Missing native registrar: {name}", capability=name
        ) from error
    registrar = getattr(plugins, "register_plugin", None)
    if not callable(registrar):
        raise UnsupportedCapability(
            f"Missing native registrar: {name}", capability=name
        )
    return registrar(context, assessment)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _version() -> str:
    try:
        return importlib.metadata.version("fontlab-glyport")
    except importlib.metadata.PackageNotFoundError:
        return "uninstalled"


def _snapshot_adaptation(handle) -> None:
    adapted_sources = tuple(handle.context._maps.values())
    handle._adaptations = tuple(
        a for adapted in adapted_sources for a in adapted.adaptations
    )
    for adapted in adapted_sources:
        for diagnostic in adapted.diagnostics:
            if diagnostic not in handle._diagnostics:
                handle._diagnostics.append(diagnostic)
    handle._artifacts = tuple(
        artifact
        for adapted in adapted_sources
        for artifact in (
            Artifact(
                "adapted-source",
                str(adapted.path),
                hashlib.sha256(adapted.path.read_bytes()).hexdigest(),
            ),
            Artifact("source-map", adapted.source_map.path, adapted.source_map.sha256),
        )
    )
    if adapted_sources:
        if handle.context.profile in {"glyphs3", "glyphs4"}:
            from .adaptation_modern import PIPELINE_VERSION
        else:
            from .adaptation import PIPELINE_VERSION
        handle._pipeline_version = PIPELINE_VERSION


class RunHandle:
    """Own callbacks/resources until close; receipts are immutable snapshots."""

    def __init__(self, path: Path, host: ExecutionHost, options: ExecutionOptions):
        self.id = uuid.uuid4().hex
        self.state = "created"
        self._windows: list[object] = []
        self.context: ExecutionContext | None = None
        self._host, self._options, self._path = host, options, path
        self._temporary = tempfile.TemporaryDirectory(prefix="glyport-run-")
        self._stages, self._diagnostics = [], []
        self._invalid = False
        self._assessment = None
        self._adaptations = ()
        self._artifacts = ()
        self._pipeline_version = "runtime-2"
        self._released = False

    @property
    def cocoa_backend(self):
        return self.context.cocoa_backend if self.context else None

    @property
    def cocoa_fallback_reason(self):
        return self.context.cocoa_fallback_reason if self.context else None

    @property
    def windows(self) -> list[object]:
        """Current owned windows, including ones opened by delayed callbacks."""
        return self._windows + list(self.context.windows if self.context else ())

    @property
    def receipt(self) -> Receipt:
        assessment = self._assessment
        diagnostics = list(self._diagnostics)
        for diagnostic in self.context.diagnostics if self.context is not None else ():
            if diagnostic not in diagnostics:
                diagnostics.append(diagnostic)
        source = ReceiptSource(
            None,
            None,
            (
                self._path.relative_to(
                    Path(self._options.source_root).resolve()
                ).as_posix()
                if self._options.source_root
                else self._path.name
            ),
            assessment.source_id if assessment else None,
            {},
        )
        for name in ("repository", "revision", "sha256"):
            if getattr(source, name) is None:
                diagnostics.append(
                    ReceiptDiagnostic(
                        "FACT_UNAVAILABLE",
                        "info",
                        "Source fact was not supplied.",
                        field="source." + name,
                    )
                )
        for name in ("host", "host_build", "python", "qt", "os", "arch"):
            if getattr(self._host.environment, name) is None:
                diagnostics.append(
                    ReceiptDiagnostic(
                        "FACT_UNAVAILABLE",
                        "info",
                        "Host fact was not supplied.",
                        field="environment." + name,
                    )
                )
        profile = assessment.profile if assessment else "auto"
        return Receipt(
            self.id,
            source,
            self._host.environment,
            ReceiptAdapter(_version(), profile, self._pipeline_version),
            self._adaptations,
            tuple(
                Capability(
                    c,
                    "unexecuted",
                    ("Static requirement; native acceptance is separate.",),
                )
                for c in (assessment.required_capabilities if assessment else ())
            ),
            tuple(self._stages),
            self._artifacts,
            tuple(diagnostics),
        )

    def wrap(self, callback: Callable) -> Callable:
        wrapped = self.context.wrap(callback)

        def invoke(*args, **kwargs):
            if self._invalid:
                raise StaleNativeObject("The handle's document has been invalidated.")
            return self._host.dispatch(lambda: wrapped(*args, **kwargs))

        return invoke

    def invalidate_document(self) -> None:
        self._invalid = True
        self.close()

    def close(self) -> None:
        if self._released:
            return

        def teardown():
            started = _now()
            self.state = "closing"
            try:
                if self.context:
                    self.context.close()
            except BaseException:
                self.state = "failed"
                self._stages.append(
                    Stage(
                        "close",
                        "failed",
                        started,
                        _now(),
                        ("Resource teardown failed.",),
                    )
                )
                raise
            else:
                self.state = "closed"
                self._windows.clear()
                self._stages.append(
                    Stage(
                        "close", "passed", started, _now(), ("Owned context unloaded.",)
                    )
                )
            finally:
                self._temporary.cleanup()
                self._released = True

        self._host.dispatch(teardown)


class PluginHandle(RunHandle):
    plugin: object = None  # the registrar's loaded plugin instance

    def unload(self) -> None:
        self.close()


def _prepare(handle: RunHandle, profile: str, font: object, plugin: bool) -> None:
    from .adaptation_entries import unpack_archive

    path, options = handle._path, handle._options
    root = (
        Path(options.source_root).resolve()
        if options.source_root
        else path
        if path.is_dir()
        else path.parent
    )
    if not path.is_relative_to(root):
        raise ValueError("Entry point must be inside source_root")
    assessment = inspect_source(path, profile=profile)
    if assessment.profile == "auto" and not any(
        d.code == "PROFILE_AMBIGUOUS" or d.severity == "error"
        for d in assessment.diagnostics
    ):
        assessment = replace(assessment, profile="glyphs4")
        handle._diagnostics.append(
            ReceiptDiagnostic(
                "PROFILE_RUNTIME_DEFAULT",
                "info",
                "Unresolved auto profile executes with the Glyphs 4 compatibility version.",
            )
        )
    handle._assessment = assessment
    if path.suffix == ".zip":
        root = unpack_archive(path, Path(handle._temporary.name) / "entry")
        path = root / "__main__.py"
        if not path.exists():
            path = root / "__main__.pyc"
        if not path.exists():
            raise UnsupportedCapability(
                "ZIP entry requires __main__.py or __main__.pyc.",
                capability="dependency:archive",
            )
    handle._diagnostics.extend(
        ReceiptDiagnostic(d.code, d.severity, d.message) for d in assessment.diagnostics
    )
    if assessment.profile == "auto":
        raise UnsupportedCapability(
            "An explicit profile is required for ambiguous source.",
            capability="execution:profile",
        )
    if plugin and handle._host.plugin_installer is None:
        raise UnsupportedCapability(
            "Plugin registration requires an explicit host plugin_installer.",
            capability="plugin:registration",
        )
    dependencies = []
    for index, dependency in enumerate(options.dependency_paths):
        dependency = Path(dependency)
        if not dependency.is_absolute():
            dependency = root / dependency
        if dependency.suffix == ".zip":
            dependency = unpack_archive(
                dependency, Path(handle._temporary.name) / f"dependency-{index}"
            )
        if not dependency.is_dir():
            raise FileNotFoundError(dependency)
        dependencies.append(dependency)
    context = handle.context = ExecutionContext(
        root,
        assessment.profile,
        sink=handle._host.sink,
        dependency_paths=tuple(dependencies),
        cache_dir=Path(tempfile.gettempdir()) / "fontlab-glyport-runtime-cache",
        shared_globals=plugin,
        implicit_imports=() if plugin else ("GlyphsApp",),
    )
    context.adapters.update(handle._host.adapter_factory(context, font))
    context.configure_cocoa(options.cocoa_backend)
    handle.state = "prepared"
    entries = assessment.entrypoints if plugin else (path.name,)
    if plugin:
        plist = path / "Contents/Info.plist"
        metadata = plistlib.loads(plist.read_bytes()) if plist.is_file() else {}
        declared = metadata.get("PyMainFileNames", [])
        if declared:
            entries = tuple("Contents/Resources/" + name for name in declared)
            if any(entry not in assessment.entrypoints for entry in entries):
                raise UnsupportedCapability(
                    "Declared plugin entry point is unavailable.",
                    capability="plugin:entrypoint",
                )
        elif len(entries) > 1:
            raise UnsupportedCapability(
                "Multiple plugin entries require PyMainFileNames to declare execution order.",
                capability="plugin:entrypoint",
            )
    if not entries:
        raise UnsupportedCapability(
            "No supported Python entry point was discovered.",
            capability="execution:entrypoint",
        )
    for entry in entries:
        try:
            stage = context.run(path if not plugin else path / entry)
        except BaseException:
            if context.last_stage:
                handle._stages.append(context.last_stage)
            _snapshot_adaptation(handle)
            raise
        handle._stages.append(stage)
        _snapshot_adaptation(handle)
        if stage.status != "passed":
            raise UnsupportedCapability(
                f"Script exited with status {context.exit_status!r}.",
                capability="execution:exit",
            )
    if plugin:
        started = _now()
        if assessment.principal_class and not isinstance(
            context.globals.get(assessment.principal_class), type
        ):
            raise UnsupportedCapability(
                "Declared principal class was not defined by the plugin entry points.",
                capability="plugin:principal-class",
            )
        with context:
            registration = handle._host.plugin_installer(context, assessment)
        if (
            not isinstance(registration, PluginRegistration)
            or not registration.evidence
        ):
            if isinstance(registration, PluginRegistration):
                context.wrap(registration.unload)()
            raise UnsupportedCapability(
                "Plugin registration must return hook evidence and teardown.",
                capability="plugin:registration",
            )
        context.on_close(context.wrap(registration.unload))
        handle._windows.extend(registration.windows)
        handle.plugin = registration.plugin
        handle._stages.append(
            Stage("registration", "passed", started, _now(), registration.evidence)
        )
    handle.state = "active"


def _execute(path, profile, font, options, host, plugin):
    options = ExecutionOptions() if options is None else options
    if not isinstance(options, ExecutionOptions):
        raise TypeError("options must be an ExecutionOptions record")
    host = host or _native_host()
    path = Path(path).expanduser()
    if not path.is_absolute() and options.source_root is not None:
        path = Path(options.source_root) / path
    path = path.resolve()
    if options.receipt_path and not Path(options.receipt_path).is_absolute():
        receipt_root = (
            Path(options.source_root).resolve()
            if options.source_root
            else path
            if path.is_dir()
            else path.parent
        )
        options = replace(options, receipt_path=receipt_root / options.receipt_path)
    if options.receipt_path:
        receipt_path = Path(options.receipt_path).resolve()
        if receipt_path.exists() or Path(options.receipt_path).is_symlink():
            raise FileExistsError(receipt_path)
        if path.is_dir() and receipt_path.is_relative_to(path):
            raise ValueError("Receipt output must be outside the original bundle")
    handle = (PluginHandle if plugin else RunHandle)(path, host, options)
    try:

        def execute():
            check_cocoa_request(options.cocoa_backend)
            resolved_font = font if font is not None else host.current_font()
            _prepare(handle, profile, resolved_font, plugin)

        host.dispatch(execute)
        if options.receipt_path:
            write_receipt(handle.receipt, options.receipt_path, public=False)
    except BaseException as error:
        handle._diagnostics.append(
            error.to_diagnostic()
            if isinstance(error, GlyportError)
            else ReceiptDiagnostic(
                "EXECUTION_FAILED", "error", f"{type(error).__name__}: {error}"
            )
        )
        if not handle._stages or handle._stages[-1].status != "failed":
            handle._stages.append(
                Stage("prepare", "failed", _now(), _now(), (type(error).__name__,))
            )
        try:
            handle.close()
        except BaseException as cleanup_error:  # noqa: BLE001 - retain primary failure and cleanup evidence
            handle._diagnostics.append(
                ReceiptDiagnostic("CLEANUP_FAILED", "error", str(cleanup_error))
            )
        handle.state = "failed"
        error.handle = handle
        if options.receipt_path:
            try:
                write_receipt(handle.receipt, options.receipt_path, public=False)
            except (OSError, ValueError) as receipt_error:
                handle._diagnostics.append(
                    ReceiptDiagnostic(
                        "RECEIPT_WRITE_FAILED", "error", str(receipt_error)
                    )
                )
        error.receipt = handle.receipt
        raise
    return handle


def run_script(
    path: str | Path,
    *,
    profile: str = "auto",
    font=None,
    options: ExecutionOptions | None = None,
    host: ExecutionHost | None = None,
) -> RunHandle:
    """Run original source through host dispatch; retain context for callbacks."""
    return _execute(path, profile, font, options, host, False)


def install_plugin(
    path: str | Path,
    *,
    profile: str = "auto",
    options: ExecutionOptions | None = None,
    host: ExecutionHost | None = None,
) -> PluginHandle:
    """Execute bundle Python and require evidenced host hook registration."""
    return _execute(path, profile, None, options, host, True)
