import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.services.project_io import load_yaml
from app.services.recent import add_recent, load_recent

PAGE = str(Path(__file__).resolve().parents[2] / "app" / "pages" / "1_Project.py")


@pytest.fixture
def home(monkeypatch):
    monkeypatch.delenv("SWATPREP_WORKSPACE", raising=False)
    return AppTest.from_file(PAGE, default_timeout=60).run()


def test_projects_screen_when_nothing_is_open(home):
    assert not home.exception and home.title[0].value == "Projects"
    assert [s.value for s in home.main.subheader] == ["Recent projects", "Open project folder", "New project"]
    assert home.text_input(key="home_open_dir").value == ""


def test_open_a_folder_opens_its_only_config(home, example_project, open_project):
    open_project(home, example_project.parent)
    assert home.title[0].value == "ExampleBasin_2024"
    assert home.selectbox(key="config_choice").options == ["config_minimal.yaml"]
    assert load_recent() == [str(example_project.parent.resolve())]


def test_open_a_missing_folder(home, tmp_path):
    home.text_input(key="home_open_dir").set_value(str(tmp_path / "nope"))
    home.button(key="home_open").click().run()
    assert home.title[0].value == "Projects"
    assert "Folder not found" in home.error[0].value


def test_recent_project_opens(monkeypatch, example_project):
    monkeypatch.delenv("SWATPREP_WORKSPACE", raising=False)
    add_recent(example_project.parent)
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    assert "1 config" in at.markdown[0].value
    at.button(key="home_recent::0").click().run()
    assert not at.exception and at.title[0].value == "ExampleBasin_2024"


def test_new_project_creates_folder_and_config(home, tmp_path):
    folder = tmp_path / "basins" / "SeSan"
    home.text_input(key="home_new_dir").set_value(str(folder))
    home.selectbox(key="home_new_crs").select("EPSG:32648")
    home.button(key="home_create").click().run()
    assert not home.exception
    assert load_yaml(folder / "config.yaml")["project"] == {
        "name": "SeSan", "crs": "EPSG:32648", "output_dir": "./output", "targets": ["swatplus"]}
    assert home.title[0].value == "SeSan"


def test_new_project_refuses_a_folder_with_a_config(home, example_project):
    shutil.copy(example_project, example_project.parent / "config.yaml")
    home.text_input(key="home_new_dir").set_value(str(example_project.parent))
    home.button(key="home_create").click().run()
    assert home.title[0].value == "Projects" and "Open it instead" in home.error[0].value


def test_default_config_and_switching(home, example_project, open_project):
    shutil.copy(example_project, example_project.parent / "config.yaml")
    open_project(home, example_project.parent)
    assert home.selectbox(key="config_choice").value == "config.yaml"
    home.selectbox(key="config_choice").select("config_minimal.yaml").run()
    assert home.session_state["config_path"] == str(example_project.resolve())


def test_unsaved_changes_lock_switching(home, example_project, open_project):
    open_project(home, example_project.parent)
    home.selectbox(key="f::dem.resampling").select("cubic").run()
    assert home.selectbox(key="config_choice").disabled
    assert home.button(key="change_project").disabled and home.button(key="new_config").disabled
    assert any("Save or discard your changes first" in c.value for c in home.sidebar.caption)
    home.button(key="save").click().run()
    assert not home.selectbox(key="config_choice").disabled


def test_change_project_returns_to_the_projects_screen(home, example_project, open_project):
    open_project(home, example_project.parent)
    home.button(key="change_project").click().run()
    assert home.title[0].value == "Projects"


def test_project_without_config(home, tmp_path, open_project):
    open_project(home, tmp_path)
    assert home.title[0].value == tmp_path.name
    assert "no config yet" in home.info[0].value


def test_new_config_dialog_offers_a_free_name_and_the_open_crs(home, example_project, open_project):
    # Creating from the dialog is checked in the browser: AppTest reruns the whole page, which closes a
    # dialog opened by a button. The rules it applies are tested in test_projects.py.
    open_project(home, example_project.parent)
    home.button(key="new_config").click().run()
    assert not home.exception
    assert home.text_input(key="new_config_file").value == "config.yaml"
    assert home.text_input(key="new_config_name").value == example_project.parent.name
    assert home.selectbox(key="new_config_crs").value == "EPSG:32648"
