"""List folders and files inside an allowed root, refusing path traversal."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class OutsideRootError(ValueError):
    """Raised when a requested path resolves outside the allowed root."""


@dataclass(frozen=True)
class Entry:
    name: str
    path: Path
    is_dir: bool
    size: int | None  # bytes; None for folders


def resolve_inside(root: Path, sub: str | Path = "") -> Path:
    """Return root/sub resolved, or raise OutsideRootError if it escapes root."""
    base = Path(root).resolve()
    target = (base / sub).resolve()
    if not target.is_relative_to(base):
        raise OutsideRootError(f"{sub} is outside {base}")
    return target


def list_dir(root: Path, sub: str | Path = "", suffixes: tuple[str, ...] = ()) -> list[Entry]:
    """Folders first, then files (filtered by suffix), each sorted by name; hidden entries skipped."""
    folder = resolve_inside(root, sub)
    entries: list[Entry] = []
    for p in folder.iterdir():
        if p.name.startswith("."):
            continue
        if p.is_dir():
            entries.append(Entry(p.name, p, True, None))
        elif not suffixes or p.suffix.lower() in suffixes:
            entries.append(Entry(p.name, p, False, p.stat().st_size))
    return sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))


def human_size(size: int | None) -> str:
    """1536 -> '1.5 KB'; None -> ''."""
    if size is None:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return ""
