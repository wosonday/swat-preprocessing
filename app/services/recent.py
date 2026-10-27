"""Remember the project folders the user opened, newest first (stored in ~/.swatprep/)."""
from __future__ import annotations

import json
import os
from pathlib import Path

MAX_RECENT = 10


def state_file() -> Path:
    base = os.environ.get("SWATPREP_STATE_DIR") or Path.home() / ".swatprep"
    return Path(base) / "recent_projects.json"


def load_recent() -> list[str]:
    """Saved folders that still exist; a missing or unreadable file means no history."""
    try:
        items = json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [p for p in items if isinstance(p, str) and Path(p).is_dir()][:MAX_RECENT]


def add_recent(folder: Path) -> list[str]:
    """Put folder first in the history and save it; saving is best effort."""
    entry = str(Path(folder).resolve())
    items = [entry] + [p for p in load_recent() if p != entry]
    items = items[:MAX_RECENT]
    try:
        target = state_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(items, indent=2), encoding="utf-8")
    except OSError:
        pass  # read-only home (e.g. some containers): keep the history for this session only
    return items
