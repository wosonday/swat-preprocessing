import json
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


def test_map_before_build_shows_the_boundary_and_stations(page):
    explore(page, "Map")
    assert not page.exception and len(page.get("deck_gl_json_chart")) == 1
    assert page.selectbox(key="map_layer").options == ["No output raster yet"]
    assert page.checkbox(key="overlay_stations").value
    assert any("Run Build to add the DEM" in c.value for c in page.caption)


def test_add_and_remove_an_overlay(page, example_project):
    project = example_project.parent
    (project / "Q_stations.csv").write_text("ID,NAME,LAT,LONG\nQ1,Xa La,15.6,105.3\n", encoding="utf-8")
    explore(page, "Map")
    page.text_input(key="overlay_path").set_value("Q_stations.csv").run()
    page.button(key="overlay_add").click().run()
    assert not page.exception
    saved = json.loads((project / ".swatprep" / "map_layers.json").read_text(encoding="utf-8"))
    assert [Path(i["path"]).name for i in saved] == ["Q_stations.csv"] and saved[0]["crs"] == "EPSG:4326"
    assert page.checkbox(key="overlay_on::0").value
    assert "Q_stations.csv" in list(page.get("dataframe")[0].value["layer"])        # Extents table
    page.button(key="overlay_remove::0").click().run()
    assert json.loads((project / ".swatprep" / "map_layers.json").read_text(encoding="utf-8")) == []


def test_bad_overlay_is_reported(page, example_project):
    (example_project.parent / "bad.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    explore(page, "Map")
    page.text_input(key="overlay_path").set_value("bad.csv").run()
    page.button(key="overlay_add").click().run()
    assert "needs lat and lon" in page.error[0].value


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
