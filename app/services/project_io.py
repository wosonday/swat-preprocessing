"""Read and write config YAML from the UI, keeping comments and key order."""
from __future__ import annotations

import io
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError


class ConfigFileError(Exception):
    """A config file could not be read; line/column are 1-based when known."""

    def __init__(self, message: str, line: int | None = None, column: int | None = None):
        super().__init__(message)
        self.line = line
        self.column = column


def _yaml() -> YAML:
    yaml = YAML()  # round-trip mode: keeps comments, order and quotes
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def load_yaml(path: Path) -> dict:
    """Load a config file as an editable mapping (a dict subclass)."""
    try:
        data = _yaml().load(Path(path).read_text(encoding="utf-8"))
    except MarkedYAMLError as exc:
        mark = exc.problem_mark
        line = mark.line + 1 if mark else None
        column = mark.column + 1 if mark else None
        raise ConfigFileError(f"{exc.problem} (line {line}, column {column})", line, column) from exc
    if not isinstance(data, dict):
        raise ConfigFileError("The config must be a mapping of sections (project:, dem:, …).")
    return data


def dump_yaml(data: dict) -> str:
    buffer = io.StringIO()
    _yaml().dump(data, buffer)
    return buffer.getvalue()


def save_yaml(data: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(data), encoding="utf-8")
