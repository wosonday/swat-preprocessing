from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.services.project_io import load_yaml
from app.services.recent import load_recent

PAGE = str(Path(__file__).resolve().parents[2] / "app" / "pages" / "1_Project.py")


@pytest.fixture
def page(monkeypatch, example_project):
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(example_project.parent))
    monkeypatch.setenv("SWATPREP_DATA_ROOT", str(example_project.parent / "data"))
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    at.selectbox(key="config_choice").select("config_minimal.yaml").run()
    assert not at.exception
    return at


def test_tabs_follow_configured_sections(page):
    assert [t.label for t in page.tabs] == ["Project", "DEM", "Land use", "Soil", "Weather", "Streamflow", "YAML"]


def test_opening_does_not_mark_unsaved(page):
    assert page.button(key="save").disabled


def test_edit_and_save_keeps_comments(page, example_project):
    page.selectbox(key="f::dem.resampling").select("cubic").run()
    assert page.session_state["cfg"]["dem"]["resampling"] == "cubic"
    assert not page.button(key="save").disabled
    page.button(key="save").click().run()
    text = example_project.read_text(encoding="utf-8")
    assert "resampling: cubic" in text
    assert "# UTM Zone 48N" in text


def test_validate_saves_without_adding_defaults(page, example_project):
    original = example_project.read_text(encoding="utf-8")
    page.button(key="validate").click().run()
    assert example_project.read_text(encoding="utf-8") == original


def test_toggle_section_off_and_on_keeps_values(page):
    page.toggle(key="f::on::soil").set_value(False).run()
    assert "soil" not in page.session_state["cfg"]
    assert "Soil" not in [t.label for t in page.tabs]
    page.toggle(key="f::on::soil").set_value(True).run()
    assert page.session_state["cfg"]["soil"]["soil_key_col"] == "soil_id"


def test_clip_add_and_remove(page):
    page.toggle(key="f::on::clip").set_value(True).run()
    assert page.session_state["cfg"]["clip"] == [{}]
    page.button(key="f::clip_add").click().run()
    assert len(page.session_state["cfg"]["clip"]) == 2
    page.button(key="f::clip_remove::0").click().run()
    assert len(page.session_state["cfg"]["clip"]) == 1


def test_weather_fill_block_follows_type(page):
    page.toggle(key="f::on::weather.fill").set_value(True).run()
    fill = page.session_state["cfg"]["weather"]["fill"]
    assert "csv" in fill
    page.selectbox(key="f::weather.fill.type").select("netcdf").run()
    assert "netcdf" in page.session_state["cfg"]["weather"]["fill"]


def test_validate_marks_missing_file_on_the_field(page, example_project):
    (example_project.parent / "data" / "dem_30m.tif").unlink()
    page.button(key="validate").click().run()
    assert not page.exception
    assert "DEM (1)" in [t.label for t in page.tabs]
    assert any("File not found" in m.value for m in page.markdown)


def test_schema_error_blocks_build_and_shows_on_field(page):
    page.text_input(key="f::project.crs").set_value("").run()
    page.button(key="build").click().run()
    _, action, result = page.session_state["last_run"]
    assert action == "build" and not result.ok and "Fix 1 field" in result.error
    assert "Project (1)" in [t.label for t in page.tabs]


def test_build_from_form(page, example_project):
    page.button(key="build").click().run()
    _, action, result = page.session_state["last_run"]
    assert action == "build" and result.ok
    assert (example_project.parent / "output" / "manifest.json").is_file()


def test_new_config(monkeypatch, tmp_path):
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(tmp_path))
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    target = tmp_path / "basin" / "config.yaml"
    [t for t in at.text_input if t.label == "File"][0].set_value(str(target))
    at.text_input(key="new_name").set_value("Basin")
    at.text_input(key="new_crs").set_value("EPSG:32648")
    submit = [b for b in at.button if b.label == "Create"][0]
    submit.click().run()
    assert not at.exception
    assert target.is_file()
    assert load_yaml(target)["project"]["name"] == "Basin"
    assert at.title[0].value == "Basin"


def test_project_folder_outside_the_repo(monkeypatch, example_project):
    monkeypatch.delenv("SWATPREP_WORKSPACE", raising=False)
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    assert at.text_input(key="project_dir").value == ""
    assert at.selectbox(key="config_choice").disabled

    at.text_input(key="project_dir").set_value(str(example_project.parent)).run()
    assert at.selectbox(key="config_choice").options == ["config_minimal.yaml"]
    at.selectbox(key="config_choice").select("config_minimal.yaml").run()
    assert not at.exception
    assert at.title[0].value == "ExampleBasin_2024"
    assert load_recent() == [str(example_project.parent.resolve())]


def test_recent_folder_is_preselected(monkeypatch, example_project):
    monkeypatch.delenv("SWATPREP_WORKSPACE", raising=False)
    from app.services.recent import add_recent

    add_recent(example_project.parent)
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    assert at.text_input(key="project_dir").value == str(example_project.parent.resolve())


def test_missing_project_folder_is_flagged(monkeypatch, tmp_path):
    monkeypatch.delenv("SWATPREP_WORKSPACE", raising=False)
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    at.text_input(key="project_dir").set_value(str(tmp_path / "nope")).run()
    assert any("Folder not found" in c.value for c in at.caption)
