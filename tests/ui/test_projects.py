from pathlib import Path

import pytest

from app.services.project_io import load_yaml
from app.services.projects import (ProjectError, create_config, create_project, default_config, free_config_name,
                                   list_configs)


def touch(folder: Path, *names: str) -> None:
    for name in names:
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text("project: {}\n", encoding="utf-8")


def test_lists_only_yaml_files_at_the_project_root(tmp_path):
    touch(tmp_path, "b.yml", "a.yaml", "notes.txt", "data/config.yaml", ".hidden.yaml")
    assert [p.name for p in list_configs(tmp_path)] == ["a.yaml", "b.yml"]
    assert list_configs(tmp_path / "missing") == []


def test_default_config_prefers_config_yaml(tmp_path):
    assert default_config(tmp_path) is None
    touch(tmp_path, "b.yaml", "a.yaml")
    assert default_config(tmp_path).name == "a.yaml"
    touch(tmp_path, "config.yaml")
    assert default_config(tmp_path).name == "config.yaml"


def test_free_config_name_counts_up(tmp_path):
    assert free_config_name(tmp_path) == "config.yaml"
    touch(tmp_path, "config.yaml", "config_2.yaml")
    assert free_config_name(tmp_path) == "config_3.yaml"


def test_create_config_inside_the_project(tmp_path):
    path = create_config(tmp_path, "dry.yaml", "Basin", "EPSG:32648")
    assert path == tmp_path / "dry.yaml"
    assert load_yaml(path)["project"] == {"name": "Basin", "crs": "EPSG:32648", "output_dir": "./output",
                                          "targets": ["swatplus"]}


@pytest.mark.parametrize("name", ["", "  ", "../x.yaml", "sub/x.yaml", "sub\\x.yaml", "x.txt", "x"])
def test_create_config_rejects_bad_names(tmp_path, name):
    with pytest.raises(ProjectError):
        create_config(tmp_path, name, "Basin", "EPSG:32648")


def test_create_config_does_not_overwrite(tmp_path):
    touch(tmp_path, "config.yaml")
    with pytest.raises(ProjectError, match="already exists"):
        create_config(tmp_path, "config.yaml", "Basin", "EPSG:32648")


def test_create_project_makes_missing_folders(tmp_path):
    folder = tmp_path / "basins" / "SeSan"
    path = create_project(folder, "", "EPSG:32648")
    assert path == folder / "config.yaml"
    assert load_yaml(path)["project"]["name"] == "SeSan"


def test_create_project_refuses_an_existing_config(tmp_path):
    touch(tmp_path, "config.yaml")
    with pytest.raises(ProjectError, match="Open it instead"):
        create_project(tmp_path, "Basin", "EPSG:32648")


def test_os_errors_become_project_errors(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(ProjectError):
        create_project(blocker / "inside", "Basin", "EPSG:32648")    # parent is a file
