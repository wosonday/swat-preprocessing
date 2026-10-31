from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[2] / "app"


def test_home_renders(monkeypatch, tmp_path):
    monkeypatch.setenv("SWATPREP_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(tmp_path))
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=30).run()
    assert not at.exception
    assert at.title[0].value == "swatprep"


def test_project_page_starts_on_the_projects_screen(monkeypatch, tmp_path):
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(tmp_path))
    at = AppTest.from_file(str(APP / "pages" / "1_Project.py"), default_timeout=30).run()
    assert not at.exception
    assert at.title[0].value == "Projects"
    assert at.text_input(key="home_open_dir").value == str(tmp_path)


def test_project_page_validate_and_build(monkeypatch, example_project, open_project):
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(example_project.parent))
    monkeypatch.setenv("SWATPREP_DATA_ROOT", str(example_project.parent / "data"))
    at = AppTest.from_file(str(APP / "pages" / "1_Project.py"), default_timeout=60).run()
    open_project(at, example_project.parent)

    at.button(key="validate").click().run()
    assert not at.exception
    _, action, result = at.session_state["last_run"]
    assert action == "validate" and result.ok and result.count("pass") == 9

    at.button(key="build").click().run()
    assert not at.exception
    _, action, result = at.session_state["last_run"]
    assert action == "build" and result.ok
    assert (example_project.parent / "output" / "manifest.json").is_file()
