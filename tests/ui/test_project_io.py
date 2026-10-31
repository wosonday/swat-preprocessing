import pytest

from app.services.project_io import ConfigFileError, dump_yaml, load_yaml, save_yaml


def test_round_trip_keeps_file_unchanged(example_project):
    original = example_project.read_text(encoding="utf-8")
    save_yaml(load_yaml(example_project), example_project)
    assert example_project.read_text(encoding="utf-8") == original


def test_edit_keeps_comments(example_project):
    data = load_yaml(example_project)
    data["project"]["name"] = "Renamed"
    text = dump_yaml(data)
    assert "name: Renamed" in text or 'name: "Renamed"' in text
    assert "# UTM Zone 48N" in text


def test_syntax_error_reports_line(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("project:\n  name: [unclosed\n  crs: EPSG:32648\n", encoding="utf-8")
    with pytest.raises(ConfigFileError) as info:
        load_yaml(bad)
    assert info.value.line is not None


def test_top_level_must_be_mapping(tmp_path):
    bad = tmp_path / "list.yaml"
    bad.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigFileError):
        load_yaml(bad)


def test_save_creates_parent_folders(tmp_path):
    target = tmp_path / "new" / "config.yaml"
    save_yaml({"project": {"name": "X"}}, target)
    assert load_yaml(target)["project"]["name"] == "X"
