import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAGE = str(Path(__file__).resolve().parents[2] / "app" / "pages" / "1_Project.py")


@pytest.fixture
def page(monkeypatch, example_project, open_project):
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(example_project.parent))
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    return open_project(at, example_project.parent)


def explore(at, view="Streamflow"):
    at.segmented_control(key="mode").set_value("Explore").run()
    assert not at.exception
    at.segmented_control(key="explore_view").set_value(view).run()
    assert not at.exception
    return at


def test_explore_opens_on_weather_instead_of_the_form(page):
    page.segmented_control(key="mode").set_value("Explore").run()
    assert not page.exception and len(page.tabs) == 0
    assert page.segmented_control(key="explore_view").value == "Weather"


def test_streamflow_view(page):
    explore(page)
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


def test_map_asks_for_a_build_first(page):
    explore(page, "Map")
    assert any("Run Build to see the output maps" in i.value for i in page.info)


def test_map_shows_built_layers(page, example_project):
    spatial = example_project.parent / "output" / "spatial"
    spatial.mkdir(parents=True)
    shutil.copy(example_project.parent / "data" / "dem_30m.tif", spatial / "dem_projected.tif")
    explore(page, "Map")
    assert not page.exception
    assert page.selectbox(key="map_layer").options == ["DEM"]
    assert len(page.get("deck_gl_json_chart")) == 1


@pytest.fixture
def filled_page(monkeypatch, filled_project, open_project):
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(filled_project.parent))
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    return open_project(at, filled_project.parent)


def test_weather_view_with_filled_data(filled_page):
    explore(filled_page, "Weather")
    assert filled_page.segmented_control(key="wx_source").options == ["Observed", "Filled"]
    assert [s.value for s in filled_page.main.subheader] == [
        "Completeness", "Station", "Monthly climatology of precipitation"]
    assert any("Fill report: 2 missing, 2 filled" in c.value for c in filled_page.caption)
    filled_page.segmented_control(key="wx_source").set_value("Filled").run()
    assert not filled_page.exception
    assert any("after filling" in c.value for c in filled_page.caption)


def test_weather_view_other_variable(filled_page):
    explore(filled_page, "Weather").selectbox(key="wx_var").select("tmax").run()
    assert not filled_page.exception
    assert filled_page.selectbox(key="wx_station").value == "ST001"


def test_weather_without_fill(page):
    explore(page, "Weather")
    assert page.segmented_control(key="wx_source").options == ["Observed"]
