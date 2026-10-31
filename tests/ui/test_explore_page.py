from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAGE = str(Path(__file__).resolve().parents[2] / "app" / "pages" / "1_Project.py")


@pytest.fixture
def page(monkeypatch, example_project):
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(example_project.parent))
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    at.selectbox(key="config_choice").select("config_minimal.yaml").run()
    return at


def explore(at):
    at.segmented_control(key="mode").set_value("Explore").run()
    assert not at.exception
    return at


def test_explore_shows_streamflow_instead_of_the_form(page):
    explore(page)
    assert len(page.tabs) == 0
    assert page.segmented_control(key="explore_view").value == "Streamflow"
    assert page.selectbox(key="flow_station").value == "ST001"
    assert [s.value for s in page.main.subheader] == ["Hydrograph", "Flow duration curve", "Monthly climatology"]


def test_log_scale_toggle_runs(page):
    explore(page).toggle(key="flow_log").set_value(True).run()
    assert not page.exception


def test_config_without_streamflow(page, example_project):
    text = example_project.read_text(encoding="utf-8")
    example_project.write_text(text.split("streamflow:")[0], encoding="utf-8")
    page.session_state["loaded_path"] = None
    page.run()
    explore(page)
    assert any("no streamflow section" in i.value for i in page.info)


def test_unsaved_edits_are_flagged(page):
    page.selectbox(key="f::dem.resampling").select("cubic").run()
    explore(page)
    assert any("save to explore your changes" in i.value for i in page.info)


def test_back_to_configure_keeps_edits(page):
    page.selectbox(key="f::dem.resampling").select("cubic").run()
    explore(page).segmented_control(key="mode").set_value("Configure").run()
    assert page.selectbox(key="f::dem.resampling").value == "cubic"
