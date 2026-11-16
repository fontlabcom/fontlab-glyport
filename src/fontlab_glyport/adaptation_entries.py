# this_file: src/fontlab_glyport/adaptation_entries.py
"""Non-Mach-O code loading and validated extraction into caller-owned storage."""

import hashlib
import marshal
import shutil
import stat
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import CodeType

from .errors import DependencyUnavailable

# CPython 3.11 final magic (3495), independent of the inspecting interpreter.
PY311_MAGIC = b"\xa7\x0d\x0d\x0a"
# Final-release bytecode magic of the CPython versions Glyphs plugins ship.
PYC_MAGIC = {
    b"\x03\xf3\x0d\x0a": "2.7",
    b"\x55\x0d\x0d\x0a": "3.8",
    b"\x61\x0d\x0d\x0a": "3.9",
    b"\x6f\x0d\x0d\x0a": "3.10",
    PY311_MAGIC: "3.11",
    b"\xcb\x0d\x0d\x0a": "3.12",
    b"\xf3\x0d\x0d\x0a": "3.13",
    b"\x2b\x0e\x0d\x0a": "3.14",
}


def pyc_version(data: bytes) -> str | None:
    """The CPython release whose bytecode magic starts ``data``, if known."""
    return PYC_MAGIC.get(data[:4])


def check_pyc(data: bytes, name: str = "bytecode") -> str:
    """Check the 16-byte PEP 552 header without unmarshalling foreign code."""
    if len(data) < 16 or data[:4] != PY311_MAGIC:
        raise DependencyUnavailable(
            f"{name}: Python 3.11 bytecode required; observed magic {data[:4].hex() or 'missing'}.",
            capability="python:bytecode",
            recovery_action="Supply Python 3.11 bytecode or original .py source.",
        )
    flags = int.from_bytes(data[4:8], "little")
    if flags not in (0, 1, 3):
        raise DependencyUnavailable(
            f"{name}: invalid Python 3.11 pyc flags {flags}.",
            capability="python:bytecode",
        )
    return "3.11"


def read_code(path: Path) -> CodeType:
    """Compile source or load checked 3.11 bytecode on a 3.11 interpreter only."""
    raw = path.read_bytes()
    if path.suffix != ".pyc":
        return compile(raw, str(path), "exec")
    check_pyc(raw, path.name)
    if sys.version_info[:2] != (3, 11):
        raise DependencyUnavailable(
            "Python 3.11 bytecode execution requires a Python 3.11 interpreter.",
            capability="python:bytecode",
        )
    try:
        code = marshal.loads(raw[16:])
    except (EOFError, ValueError, TypeError) as error:
        raise DependencyUnavailable(
            f"Invalid Python 3.11 bytecode payload: {path.name}",
            capability="python:bytecode",
        ) from error
    if not isinstance(code, CodeType):
        raise DependencyUnavailable(
            f"Bytecode payload is not code: {path.name}", capability="python:bytecode"
        )
    return code


def _members(archive: zipfile.ZipFile):
    """Yield ``(info, data)`` in name order after the path-safety checks."""
    seen = set()
    for info in sorted(archive.infolist(), key=lambda item: item.filename):
        name = info.filename
        parts = PurePosixPath(name).parts
        if (
            not parts
            or name.startswith("/")
            or ".." in parts
            or "\\" in name
            or ":" in parts[0]
            or name in seen
            or stat.S_ISLNK(info.external_attr >> 16)
        ):
            raise DependencyUnavailable(
                f"Unsafe or duplicate ZIP member: {name}",
                capability="dependency:archive",
            )
        seen.add(name)
        yield info, b"" if info.is_dir() else archive.read(info)


def _read_archive(path: Path, visit):
    try:
        with zipfile.ZipFile(path) as archive:
            return visit(_members(archive))
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        raise DependencyUnavailable(
            f"Cannot read ZIP archive {path.name}: {error}",
            capability="dependency:archive",
        ) from error


def archive_members(path: Path) -> tuple[tuple[str, bytes], ...]:
    """Read/validate all members before publishing; filenames never imply ABI."""
    from .inspection import MACH_O_MAGIC

    def check(members):
        result = []
        for info, data in members:
            name = info.filename
            if info.is_dir():
                continue
            if name.endswith(".pyc"):
                check_pyc(data, name)
            if name.endswith((".so", ".dylib")) or data[:4] in MACH_O_MAGIC:
                raise DependencyUnavailable(
                    f"Compiled dependency in ZIP is out of scope: {name}",
                    capability="native:mach-o",
                )
            result.append((name, data))
        return tuple(result)

    return _read_archive(Path(path), check)


@dataclass(frozen=True)
class ArchiveMember:
    """One ZIP member: ``kind`` is directory, bytecode, source, native or data;
    ``python`` is the bytecode's CPython release from its magic."""

    name: str
    kind: str
    size: int
    sha256: str | None
    python: str | None = None


def archive_inventory(path: str | Path) -> tuple[ArchiveMember, ...]:
    """Every member with its kind and bytecode version, foreign bytecode included.

    Only unreadable archives and unsafe member paths raise; nothing is extracted.
    """
    from .inspection import MACH_O_MAGIC

    def inventory(members):
        result = []
        for info, data in members:
            name = info.filename
            if info.is_dir():
                result.append(ArchiveMember(name, "directory", 0, None))
                continue
            if name.endswith(".pyc"):
                kind = "bytecode"
            elif name.endswith((".so", ".dylib")) or data[:4] in MACH_O_MAGIC:
                kind = "native"
            else:
                kind = "source" if name.endswith(".py") else "data"
            python = pyc_version(data) if kind == "bytecode" else None
            digest = hashlib.sha256(data).hexdigest()
            result.append(ArchiveMember(name, kind, len(data), digest, python))
        return tuple(result)

    return _read_archive(Path(path), inventory)


def choose_archive(paths, version: str = "3.11") -> Path | None:
    """The first archive whose bytecode is all ``version`` by magic (names ignored)."""
    for path in paths:
        try:
            members = archive_inventory(path)
        except DependencyUnavailable:
            continue
        versions = {m.python for m in members if m.kind == "bytecode"}
        native = any(m.kind == "native" for m in members)
        if versions == {version} and not native:
            return Path(path)
    return None


def unpack_archive(path: str | Path, destination: str | Path) -> Path:
    """Extract validated members to a new directory; originals remain untouched."""
    members = archive_members(Path(path))
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    staging = Path(tempfile.mkdtemp(prefix=".glyport-zip-", dir=destination.parent))
    try:
        for name, data in members:
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination.resolve()
