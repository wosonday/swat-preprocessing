"""A project is a folder; its configs are the YAML files at the folder's root."""
from __future__ import annotations

from pathlib import Path

from app.services import project_io
from app.services.form_state import new_config

CONFIG_SUFFIXES = (".yaml", ".yml")


class ProjectError(Exception):
    """A project or config could not be created; the message is shown to the user."""


def list_configs(folder: Path) -> list[Path]:
    try:
        files = [p for p in Path(folder).iterdir() if p.is_file()]
    except OSError:
        return []
    return sorted(p for p in files if p.suffix.lower() in CONFIG_SUFFIXES and not p.name.startswith("."))


def default_config(folder: Path) -> Path | None:
    configs = list_configs(folder)
    preferred = [p for p in configs if p.name == "config.yaml"]
    return (preferred or configs or [None])[0]


def free_config_name(folder: Path) -> str:
    name, n = "config.yaml", 1
    while (Path(folder) / name).exists():
        n += 1
        name = f"config_{n}.yaml"
    return name


def create_config(folder: Path, file_name: str, name: str, crs: str) -> Path:
    file_name = file_name.strip()
    if not file_name or Path(file_name).name != file_name or "\\" in file_name or file_name in (".", ".."):
        raise ProjectError("Give a file name only, without folders, e.g. config_dry.yaml.")
    if Path(file_name).suffix.lower() not in CONFIG_SUFFIXES:
        raise ProjectError("The file name must end with .yaml or .yml.")
    target = Path(folder) / file_name
    if target.exists():
        raise ProjectError(f"{file_name} already exists in this project.")
    try:
        project_io.save_yaml(new_config(name.strip() or Path(folder).name, crs.strip()), target)
    except OSError as exc:
        raise ProjectError(f"Cannot create {target}: {exc}") from exc
    return target


def create_project(folder: Path, name: str, crs: str) -> Path:
    folder = Path(folder)
    if (folder / "config.yaml").exists():
        raise ProjectError(f"{folder} already has a config.yaml. Open it instead.")
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProjectError(f"Cannot create {folder}: {exc}") from exc
    return create_config(folder, "config.yaml", name, crs)
