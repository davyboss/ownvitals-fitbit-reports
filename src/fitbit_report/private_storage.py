from __future__ import annotations

import os
import tempfile
from pathlib import Path


def ensure_private_directory(
    path: Path,
    *,
    restrict_existing: bool = True,
) -> Path:
    """Create a sensitive-data directory and restrict it to the current OS user."""
    path = Path(path)
    existed = path.exists()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix" and (restrict_existing or not existed):
        path.chmod(0o700)
    return path


def restrict_private_file(path: Path) -> Path:
    """Apply owner-only POSIX permissions to an existing sensitive file."""
    path = Path(path)
    if os.name == "posix" and path.exists():
        path.chmod(0o600)
    return path


def write_private_text(path: Path, value: str, *, encoding: str = "utf-8") -> Path:
    return _write_private(path, value.encode(encoding))


def write_private_bytes(path: Path, value: bytes) -> Path:
    return _write_private(path, value)


def _write_private(path: Path, value: bytes) -> Path:
    """Atomically replace a sensitive file without a permissive creation window."""
    path = Path(path)
    # A configured file may live directly in an existing shared directory.
    # Protect the file without unexpectedly changing that directory's policy.
    ensure_private_directory(path.parent, restrict_existing=False)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            restrict_private_file(temporary_path)
            temporary.write(value)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
        restrict_private_file(path)
        return path
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
