# this_file: src/fontlab_glyport/execution.py
"""Owned Python execution scopes; no native host or interpreter isolation claims."""

import builtins
import importlib
import importlib.abc
import importlib.util
import os
import sys
import threading
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from types import ModuleType
from weakref import WeakSet

from .cocoa_backend import COCOA_ROOTS
from .errors import (
    AdaptationError,
    DependencyUnavailable,
    HostUnavailable,
    PartialFailure,
    UnsupportedCapability,
)
from .receipt import ReceiptDiagnostic, SourceLocation, Stage

_LOCK = threading.Lock()
_COCOA_CONTEXTS = WeakSet()


def check_cocoa_request(request: str) -> None:
    """Refuse incompatible retained requests before importing or publishing aliases."""
    if request not in {"auto", "native", "qt"}:
        raise ValueError("cocoa_backend must be auto, native or qt")
    if any(
        not context._closed and context._cocoa_request != request
        for context in _COCOA_CONTEXTS
    ):
        raise ValueError(
            "Close retained handles and deactivate before changing cocoa_backend"
        )


_ADAPTERS = (
    "GlyphsApp",
    "GlyphsApp.plugins",
    "GlyphsApp.UI",
    "vanilla",
    "AppKit",
    "Foundation",
    "Cocoa",
    "objc",
)


def _utf8_open(file, mode="r", buffering=-1, encoding=None, *args, **kwargs):
    """Scripts' ``open``: text files default to UTF-8, as in Glyphs' Python
    (UTF-8 mode). FontLab's embedded Python defaults to ASCII."""
    if encoding is None and "b" not in mode:
        encoding = "utf-8"
    return builtins.open(file, mode, buffering, encoding, *args, **kwargs)


def placeholder(name: str, translate: Callable | None = None) -> ModuleType:
    """Return an explicit unsupported provider, preserving the caller location."""
    module = ModuleType(name)
    module.__path__ = []

    def missing(attribute: str) -> object:
        if attribute.startswith("__"):
            raise AttributeError(attribute)
        frame = traceback.extract_stack()[-2]
        capability = f"{name}.{attribute}"
        location = SourceLocation(frame.filename, frame.lineno, (frame.colno or 0) + 1)
        if translate:
            location = translate(location)
        raise UnsupportedCapability(
            f"Unsupported capability: {capability}",
            capability=capability,
            location=location,
        )

    module.__getattr__ = missing
    return module


class Output:
    """Text stream forwarding writes to an injected Macro/Output route."""

    def __init__(self, sink: Callable[[str], object] | None = None) -> None:
        self.strings: list[str] = []
        self.sink = sink or self.strings.append

    def write(self, text: str) -> int:
        self.sink(text)
        return len(text)

    def flush(self) -> None:
        pass


class _Loader(importlib.abc.Loader):
    def __init__(self, context: "ExecutionContext", name: str, path: Path | None):
        self.context, self.name, self.path = context, name, path

    def create_module(self, spec):
        if self.path is None and spec.name == self.name:
            module = self.context.import_module(self.name)
            self.context._cocoa_aliases[self.name] = module
            return module
        provider = self.context.adapters.get(self.name)
        return provider() if provider else None

    def exec_module(self, module):
        if self.path:
            module.__dict__["__builtins__"] = self.context.builtins
            exec(self.context._compile(self.path), module.__dict__)  # noqa: S102 - owned script execution


class _Finder(importlib.abc.MetaPathFinder):
    def __init__(self, context: "ExecutionContext") -> None:
        self.context = context

    def find_spec(self, fullname, path=None, target=None):
        if (
            self.context._route_cocoa
            and self.context.cocoa_backend == "qt"
            and fullname in COCOA_ROOTS
        ):
            return importlib.util.spec_from_loader(
                fullname, _Loader(self.context, fullname, None), is_package=True
            )
        prefix = self.context.namespace + "."
        if not fullname.startswith(prefix):
            return None
        name = fullname[len(prefix) :]
        source = self.context._source(name)
        if source is None and name not in self.context.adapters:
            return None
        package = source is None or source.name in {"__init__.py", "__init__.pyc"}
        loader = _Loader(self.context, name, source)
        spec = importlib.util.spec_from_loader(fullname, loader, is_package=package)
        if source:
            spec.origin = str(source)
            spec.has_location = True
            if package:
                spec.submodule_search_locations = [str(source.parent)]
        return spec


class _ScriptGlobals(dict):
    """Resolve optional host globals on their first Python name lookup.

    A dict subclass also serves function LOAD_GLOBAL, so ``Layer`` retains
    the real layer's identity (and empty selections resolve to actual None).
    """

    def __init__(self):
        super().__init__()
        self.lazy = {}

    def defer(self, name, resolve):
        self.pop(name, None)
        self.lazy[name] = resolve

    def __missing__(self, name):
        if name not in self.lazy:
            raise KeyError(name)
        value = self.lazy[name]()
        self[name] = value
        del self.lazy[name]
        return value

    def get(self, name, default=None):
        if name in self.lazy:
            return self[name]
        return super().get(name, default)

    def __contains__(self, name):
        return super().__contains__(name) or name in self.lazy


class _ScriptBuiltins(dict):
    """Class-body LOAD_NAME skips globals.__missing__; resolve lazies here.

    This mapping belongs to one script's globals, including its later
    callbacks. Imported helper modules keep ordinary context builtins.
    """

    def __init__(self, base, globals):
        super().__init__(base)
        self.globals = globals

    def __missing__(self, name):
        if name in self.globals.lazy:
            return self.globals[name]
        raise KeyError(name)


class ExecutionContext:
    """Serialize active scopes and retain owned modules until explicit close.

    Providers are zero-argument callables returning ModuleType. Shared script
    globals are opt-in; ordinary runs use a fresh dictionary.
    """

    def __init__(
        self,
        source_root: str | Path,
        profile: str,
        adapters: dict[str, Callable[[], ModuleType]] | None = None,
        *,
        sink: Callable[[str], object] | None = None,
        cache_dir: str | Path | None = None,
        shared_globals: bool = False,
        dependency_paths: tuple[Path, ...] = (),
        implicit_imports: tuple[str, ...] = (),
    ) -> None:
        self._route_cocoa = False
        self.cocoa_backend = "qt"
        self.cocoa_fallback_reason = None
        self.native_cocoa = {}
        self.source_root = Path(source_root).resolve()
        # Modules star-imported into each script's globals before it runs
        # (Glyphs menu scripts see ``from GlyphsApp import *``).
        self.implicit_imports = tuple(implicit_imports)
        self.profile = profile
        self._maps: dict = {}
        self.adapters = {
            name: lambda name=name: placeholder(name, self._translate)
            for name in _ADAPTERS
        }
        self.adapters.update(adapters or {})
        from .adaptation_imports import cocoa_adapters

        self.adapters.update(
            {
                name: provider
                for name, provider in cocoa_adapters(self._translate).items()
                if not adapters or name not in adapters
            }
        )
        from .dependencies import process_adapter

        self._cancel_event = threading.Event()
        if not adapters or "subprocess" not in adapters:
            self.adapters["subprocess"] = lambda: process_adapter(
                self._cancel_event.is_set, self._translate
            )
        self.namespace = "_glyport_" + uuid.uuid4().hex
        self.roots = [self.source_root]
        resources = self.source_root / "Contents" / "Resources"
        if resources.is_dir():
            self.roots.insert(0, resources)
        self.roots.extend(Path(path).resolve() for path in dependency_paths)
        self._dynamic_roots: list[Path] = []
        self._scope_paths: dict[str, int] = {}
        # A symlink placed directly in a dependency directory is an explicit
        # grant: Glyphs users install helper repositories under the package
        # name (mekkablue--Glyphs-Scripts as Scripts/mekkablue). Links inside
        # the source itself still may not escape.
        self._granted = [
            entry.resolve()
            for path in dependency_paths
            for entry in Path(path).iterdir()
            if entry.is_symlink()
        ]
        self.output = Output(sink)
        self.cache_dir = cache_dir
        self.shared_globals = shared_globals
        self.globals: dict = _ScriptGlobals()
        self.windows: set[object] = set()
        self.exit_status: object = None
        self.last_stage: Stage | None = None
        self.diagnostics = []
        self._modules: dict[str, ModuleType] = {}
        self._active = self._closed = False
        self._depth = 0
        self._thread: int | None = None
        self._finder = _Finder(self)
        self._close_hooks: list[Callable[[], object]] = []
        self._run_end_hooks: list[Callable[[], object]] = []
        self.builtins = dict(vars(builtins), __import__=self._import, open=_utf8_open)
        if self.profile == "glyphs2":
            from .runtime import LEGACY_BUILTINS

            for name, fallback in LEGACY_BUILTINS.items():
                self.builtins.setdefault(name, fallback)
        self._importlib = ModuleType("importlib")
        self._importlib.__dict__.update(vars(importlib))
        self._importlib.import_module = self.import_module

    def _collect_paths(self):
        """Keep additions even when no import used them in this scope.

        This cooperative scope cannot attribute a mutation to a plugin versus
        host code executing during it. Scope-added paths are an import-routing
        convenience, not a security trust boundary or proof of authorship.
        """
        for index, entry in enumerate(sys.path):
            if isinstance(entry, str) and entry not in self._path_snapshot:
                self._scope_paths[entry] = index
                try:
                    root = Path(entry).resolve()
                    if root.is_dir() and root not in self._dynamic_roots:
                        self._dynamic_roots.append(root)
                except (OSError, RuntimeError, ValueError):
                    continue  # Python also ignores unusable path entries.

    def _source(self, name: str) -> Path | None:
        # Explicitly added Python helpers receive our scoped builtins.
        if self._active:
            self._collect_paths()
        roots = [*self.roots, *self._dynamic_roots]
        for root in roots:
            base = root.joinpath(*name.split("."))
            for candidate in (
                base / "__init__.py",
                base.with_suffix(".py"),
                base / "__init__.pyc",
                base.with_suffix(".pyc"),
            ):
                if candidate.is_file():
                    if not any(
                        candidate.resolve().is_relative_to(path)
                        for path in (*roots, *self._granted)
                    ):
                        raise DependencyUnavailable(
                            "Imported module resolves outside the configured source/dependency roots: "
                            + name,
                            capability="dependency:" + name,
                        )
                    return candidate
        return None

    def configure_cocoa(self, request: str) -> None:
        """Choose native imports after host adapter construction, before execution."""
        from . import bootstrap
        from .cocoa_backend import select_backend

        check_cocoa_request(request)
        active = bootstrap._active
        if active is not None and request != active._cocoa_request:
            raise ValueError("Deactivate before changing cocoa_backend")
        retained = (
            active.context
            if active is not None
            else next(
                (context for context in _COCOA_CONTEXTS if not context._closed), None
            )
        )
        if retained is not None:
            self.cocoa_backend = retained.cocoa_backend
            self.cocoa_fallback_reason = retained.cocoa_fallback_reason
            self.native_cocoa = retained.native_cocoa
        else:
            self.cocoa_backend, self.cocoa_fallback_reason, self.native_cocoa = (
                select_backend(request)
            )
        self._route_cocoa = True
        self._cocoa_request = request
        _COCOA_CONTEXTS.add(self)

    def _owned(self, name: str) -> bool:
        if name.split(".")[0] in self.native_cocoa:
            return False
        return (
            name.split(".")[0] in self.adapters
            or self._source(name.split(".")[0]) is not None
        )

    def import_module(self, name: str, package: str | None = None) -> ModuleType:
        if not self._active:
            raise RuntimeError("Imports require an active execution context")
        if name.startswith("."):
            name = importlib.util.resolve_name(name, package)
        if (
            "robofab" in self.adapters
            and name.removeprefix(self.namespace + ".").split(".")[0] == "robofab"
        ):
            from .glyphsapp.legacy_dialogs import check_legacy_collisions

            # Check before importlib can return a cached private provider.
            check_legacy_collisions()
        if name == "importlib":
            return self._importlib
        if self._owned(name):
            name = self.namespace + "." + name
        elif name.split(".")[0] in {
            "drawBot",
            "drawbot",
            "fontTools",
            "fontParts",
            "robofab",
        }:
            # Use the same dependency contract for dynamic and lexical imports.
            return self._import(name, fromlist=("*",))
        return importlib.import_module(name)

    def _import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if level:
            package = (globals or {}).get("__package__")
            name = importlib.util.resolve_name("." * level + name, package)
        private = name.startswith(self.namespace + ".")
        if not private and not self._owned(name) and name != "importlib":
            from .dependencies import dependency_route

            route = dependency_route(name)
            if route.route == "adapter-required":
                raise DependencyUnavailable(route.message, capability="drawing:drawbot")
            try:
                return builtins.__import__(name, globals, locals, fromlist, 0)
            except ImportError as error:
                if name.split(".")[0] in {"fontTools", "fontParts", "robofab"}:
                    raise DependencyUnavailable(
                        route.message + f" Import failed: {error}",
                        capability="dependency:" + name,
                    ) from error
                raise
        module = self.import_module(name)
        for item in fromlist or ():
            if item != "*" and item not in vars(module):
                child = name + "." + item
                logical = child.removeprefix(self.namespace + ".")
                if logical in self.adapters or self._source(logical):
                    self.import_module(child)
        if fromlist:
            return module
        logical = name.removeprefix(self.namespace + ".")
        return self.import_module(logical.split(".")[0])

    def __enter__(self):
        if self._closed:
            raise RuntimeError("Execution context is closed")
        if self._active and self._thread == threading.get_ident():
            # Same-thread re-entry (run inside ``with``, callbacks during run).
            self._depth += 1
            return self
        if not _LOCK.acquire(blocking=False):
            raise RuntimeError(
                "Another execution scope is active; profiles cannot coexist actively"
            )
        self._snapshot = dict(sys.modules)
        self._path_snapshot = list(sys.path)
        for entry, index in sorted(self._scope_paths.items(), key=lambda item: item[1]):
            if entry not in sys.path:
                sys.path.insert(min(index, len(sys.path)), entry)
        self._active = True
        self._thread = threading.get_ident()
        try:
            root = ModuleType(self.namespace)
            root.__path__ = [str(p) for p in self.roots]
            sys.modules[self.namespace] = root
            sys.modules.update(self._modules)
            sys.meta_path.insert(0, self._finder)
            from .cocoa_backend import native_module

            # Absolute imports inside helpers must see the forced Qt route too.
            self._cocoa_aliases = {}
            if self.cocoa_backend == "qt":
                native_names = {
                    name
                    for name, module in self._snapshot.items()
                    if native_module(name, module)
                }
                for name in native_names:
                    sys.modules.pop(name, None)
                roots = (
                    COCOA_ROOTS
                    if self._route_cocoa
                    else COCOA_ROOTS.intersection(native_names)
                )
                for name in roots:
                    module = self.import_module(name)
                    self._cocoa_aliases[name] = module
                    sys.modules[name] = module
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self._active:
            return
        if threading.get_ident() != self._thread:
            raise RuntimeError("Only the activating thread may exit this context")
        if self._depth:
            self._depth -= 1
            return
        collected = False
        try:
            try:
                self._collect_paths()
                collected = True
            finally:
                if self._finder in sys.meta_path:
                    sys.meta_path.remove(self._finder)
                owned = {
                    k: v
                    for k, v in sys.modules.copy().items()
                    if k == self.namespace or k.startswith(self.namespace + ".")
                }
                if exc_type is None and collected:
                    self._modules.update(owned)
                for key in owned:
                    sys.modules.pop(key, None)
                for name, module in getattr(self, "_cocoa_aliases", {}).items():
                    if sys.modules.get(name) is module:
                        sys.modules.pop(name, None)
                sys.modules.update(self._snapshot)
                if isinstance(sys.path, list):
                    sys.path[:] = self._path_snapshot
                else:
                    sys.path = self._path_snapshot
        finally:
            self._active = False
            _LOCK.release()

    def add_diagnostic(self, diagnostic: ReceiptDiagnostic) -> None:
        if diagnostic not in self.diagnostics:
            self.diagnostics.append(diagnostic)

    def on_run_end(self, hook: Callable[[], object]) -> None:
        """Register cleanup for every run, including failed script execution."""
        if self._closed:
            raise RuntimeError("Execution context is closed")
        if not callable(hook):
            raise TypeError("run-end hook must be callable")
        self._run_end_hooks.append(hook)

    def _finish_run(self) -> None:
        errors = []
        for hook in self._run_end_hooks:
            try:
                hook()
            except BaseException as error:  # noqa: BLE001 - attempt every cleanup
                errors.append(error)
        if errors:
            error = next((e for e in errors if not isinstance(e, Exception)), errors[0])
            for other in errors:
                if other is not error:
                    error.add_note(f"Additional run cleanup failure: {other!r}")
            raise error

    def on_close(self, hook: Callable[[], object]) -> None:
        """Register ``hook`` to run once, newest first, at the start of close()."""
        if not callable(hook):
            raise TypeError(f"close hook must be callable, not {type(hook).__name__}")
        if self._closed:
            raise RuntimeError("Execution context is closed")
        self._close_hooks.append(hook)

    def cancel(self) -> None:
        """Signal cooperative cancellation to owned external process operations."""
        self._cancel_event.set()

    def _run_close_hooks(self) -> list[BaseException]:
        errors = []
        while self._close_hooks:  # pop first: each hook runs exactly once
            try:
                self._close_hooks.pop()()
            except BaseException as error:  # noqa: BLE001 - re-raised after teardown
                errors.append(error)
        return errors

    def close(self) -> None:
        """Run close hooks, then unload retained modules; repeated calls are harmless.

        Hooks run while the context is still usable (``wrap`` works). A failing
        hook, even one exiting the process, does not stop later hooks or
        teardown. Afterwards the first process exit/interrupt is re-raised as
        is; otherwise ``PartialFailure`` carries every hook error in run order.
        """
        try:
            errors = self._run_close_hooks()
        finally:
            self._close_hooks.clear()
            self._run_end_hooks.clear()
            self._depth = 0
            self.__exit__(None, None, None)
            self._modules.clear()
            self._maps.clear()
            self.globals = {}
            self._closed = True
            _COCOA_CONTEXTS.discard(self)
        exits = [e for e in errors if not isinstance(e, Exception)]
        if exits:
            raise exits[0]
        if errors:
            details = "; ".join(f"{type(e).__name__}: {e}" for e in errors)
            failure = PartialFailure(f"{len(errors)} close hook(s) failed: {details}")
            failure.errors = tuple(errors)
            raise failure from errors[0]

    def wrap(self, callback: Callable) -> Callable:
        """Retain this context for a callback invoked after the script returns."""

        @wraps(callback)
        def invoke(*args, **kwargs):
            with self:
                previous = sys.stdout, sys.stderr
                try:
                    sys.stdout = sys.stderr = self.output
                    return callback(*args, **kwargs)
                finally:
                    sys.stdout, sys.stderr = previous

        return invoke

    def _translate(self, location: SourceLocation) -> SourceLocation:
        adapted = self._maps.get(location.path)
        if adapted:
            return adapted.translate(location.line, location.column)
        return location

    def _compile(self, path: Path):
        if path.suffix == ".pyc":
            from .adaptation_entries import read_code

            return read_code(path)
        if self.cache_dir is not None:
            if self.profile in {"glyphs3", "glyphs4"}:
                from .adaptation_modern import adapt_modern

                try:
                    adapted = adapt_modern(
                        path, profile=self.profile, cache_dir=self.cache_dir
                    )
                except (SyntaxError, ValueError, OSError) as error:
                    raise AdaptationError(
                        f"{self.profile} source must be supported by Python 3.11: {error}",
                        location=SourceLocation(
                            str(path),
                            getattr(error, "lineno", None) or 1,
                            getattr(error, "offset", None) or 1,
                        ),
                        capability="source:python311",
                    ) from error
                self._maps[str(path)] = adapted
                return adapted.compile()
            from .adaptation import adapt_source  # lazy: needs fissix

            adapted = adapt_source(path, profile=self.profile, cache_dir=self.cache_dir)
            self._maps[str(path)] = adapted
            return adapted.compile()
        return compile(path.read_bytes(), str(path), "exec")

    def _script_font(self, glyphs):
        try:
            return glyphs.font
        except HostUnavailable as error:
            self.add_diagnostic(
                ReceiptDiagnostic(
                    "SCRIPT_GLOBALS_UNAVAILABLE",
                    "info",
                    f"Font/Layer bootstrap unavailable: {error}",
                    capability="Glyphs.scriptGlobals",
                )
            )
            return None

    @staticmethod
    def _script_layer(globals):
        font = globals["Font"]
        return None if font is None else next(iter(font.selectedLayers), None)

    def run(self, path: str | Path) -> Stage:
        """Execute an owned script, recording exits and restoring output streams."""
        path = Path(path).resolve()
        root = next((r for r in self.roots if path.is_relative_to(r)), None)
        if root is None:
            raise ValueError("Script must be inside source_root or bundle resources")
        package = ".".join(path.relative_to(root).parts[:-1])
        started = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        status, evidence = "failed", []

        def cleanup_failed(phase: str, error: BaseException) -> None:
            nonlocal status
            status = "failed"
            message = (
                f"Execution cleanup failed ({phase}): {type(error).__name__}: {error}"
            )
            evidence.append(message)
            self.add_diagnostic(
                ReceiptDiagnostic(
                    "EXECUTION_CLEANUP_FAILED",
                    "error",
                    message,
                    capability="execution:cleanup",
                )
            )

        self.exit_status = None
        with self:
            previous = sys.stdout, sys.stderr
            previous_directory = Path.cwd()
            try:
                os.chdir(path.parent)
                if not self.shared_globals:
                    self.globals = _ScriptGlobals()
                self.globals.update(
                    __file__=str(path),
                    __name__="__main__",
                    __package__=self.namespace + ("." + package if package else ""),
                    __spec__=None,
                    __builtins__=_ScriptBuiltins(self.builtins, self.globals),
                )
                for name in self.implicit_imports:
                    module = self.import_module(name)
                    public = getattr(module, "__all__", None) or [
                        key for key in vars(module) if not key.startswith("_")
                    ]
                    self.globals.update({key: getattr(module, key) for key in public})
                    if name == "GlyphsApp" and "Glyphs" in vars(module):
                        self.globals.defer(
                            "Font",
                            lambda glyphs=module.Glyphs: self._script_font(glyphs),
                        )
                        self.globals.defer(
                            "Layer",
                            lambda globals=self.globals: self._script_layer(globals),
                        )
                sys.stdout = sys.stderr = self.output
                try:
                    exec(self._compile(path), self.globals)  # noqa: S102 - requested execution
                    status = "passed"
                except SystemExit as error:
                    self.exit_status = error.code
                    status = (
                        "passed" if error.code is None or error.code == 0 else "failed"
                    )
                    evidence.append(f"SystemExit: {error.code!r}")
            finally:
                original_error = sys.exception()
                try:
                    self._finish_run()
                except BaseException as error:
                    cleanup_failed("run-end hooks", error)
                    if original_error is None or not isinstance(error, Exception):
                        raise
                    original_error.add_note(f"glyport run cleanup failed: {error!r}")
                    self.output.write(f"glyport run cleanup failed: {error!r}\n")
                finally:
                    sys.stdout, sys.stderr = previous
                    try:
                        self._collect_paths()
                    except BaseException as error:
                        cleanup_failed("path collection", error)
                        raise
                    finally:
                        try:
                            os.chdir(previous_directory)
                        except BaseException as error:
                            cleanup_failed("cwd restoration", error)
                            raise
                        finally:
                            finished = (
                                datetime.now(UTC).isoformat().replace("+00:00", "Z")
                            )
                            self.last_stage = Stage(
                                "execution", status, started, finished, tuple(evidence)
                            )
        return self.last_stage
