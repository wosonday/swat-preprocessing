"""Working paths read from environment variables (Twelve-Factor: Config)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DATA_ROOT_VAR = "SWATPREP_DATA_ROOT"
WORKSPACE_VAR = "SWATPREP_WORKSPACE"


@dataclass(frozen=True)
class Settings:
    data_root: Path
    workspace: Path


def load_settings() -> Settings:
    return Settings(
        data_root=Path(os.environ.get(DATA_ROOT_VAR) or "data"),
        workspace=Path(os.environ.get(WORKSPACE_VAR) or "workspace"),
    )