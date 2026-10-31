"""Working paths read from environment variables (Twelve-Factor: Config)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DATA_ROOT_VAR = "SWATPREP_DATA_ROOT"
WORKSPACE_VAR = "SWATPREP_WORKSPACE"


@dataclass(frozen=True)
class Settings:
    data_root: Path | None  # None: not set (normal for a local install)
    workspace: Path | None


def _path(var: str) -> Path | None:
    value = os.environ.get(var)
    return Path(value) if value else None  # an empty variable counts as not set


def load_settings() -> Settings:
    return Settings(data_root=_path(DATA_ROOT_VAR), workspace=_path(WORKSPACE_VAR))
