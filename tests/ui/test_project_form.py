from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


PAGE = str(Path(__file__).resolve().parents[2] / "app" / "pages" / "1_Project.py")


@pytest.fixture
def page(monkeypatch, example_project, open_project):
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(example_project.parent))
    monkeypatch.setenv("SWATPREP_DATA_ROOT", str(example_project.parent / "data"))
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    open_project(at, example_project.parent)
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
    fill = page.session_state["cfg"]["weather"]["fill"]
    assert "netcdf" in fill
    assert "csv" not in fill        # an empty block of the other type would fail validation (csv: {} needs fields)


def test_validate_marks_missing_file_on_the_field(page, example_project):
    (example_project.parent / "data" / "dem_30m.tif").unlink()
    page.button(key="validate").click().run()
    assert not page.exception
    assert "DEM (1)" in [t.label for t in page.tabs]
    assert any("File not found" in m.value for m in page.markdown)


def test_schema_error_blocks_build_and_shows_on_field(page):
    page.selectbox(key="f::project.crs").set_value(None).run()
    page.button(key="build").click().run()
    _, action, result = page.session_state["last_run"]
    assert action == "build" and not result.ok and "Fix 1 field" in result.error
    assert "Project (1)" in [t.label for t in page.tabs]


def test_build_from_form(page, example_project):
    page.button(key="build").click().run()
    _, action, result = page.session_state["last_run"]
    assert action == "build" and result.ok
    assert (example_project.parent / "output" / "manifest.json").is_file()


def test_crs_is_a_searchable_list(page):
    crs = page.selectbox(key="f::project.crs")
    assert crs.value == "EPSG:32648" and len(crs.options) > 1000
    assert crs.options[0] == "EPSG:32647 · WGS 84 / UTM zone 47N"
    crs.select("EPSG:3405").run()
    assert page.session_state["cfg"]["project"]["crs"] == "EPSG:3405"


def test_custom_crs_in_the_config_stays_selected(monkeypatch, example_project, open_project):
    proj = "+proj=utm +zone=48 +datum=WGS84 +units=m +no_defs"
    text = example_project.read_text(encoding="utf-8").replace('crs: "EPSG:32648"', f'crs: "{proj}"')
    example_project.write_text(text, encoding="utf-8")
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(example_project.parent))
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    open_project(at, example_project.parent)
    crs = at.selectbox(key="f::project.crs")
    assert crs.value == proj and crs.options[0] == proj
    assert at.button(key="save").disabled


def test_unknown_crs_is_flagged(monkeypatch, example_project, open_project):
    text = example_project.read_text(encoding="utf-8").replace('crs: "EPSG:32648"', 'crs: "EPSG:999999"')
    example_project.write_text(text, encoding="utf-8")
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(example_project.parent))
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    open_project(at, example_project.parent)
    assert any("not a recognised CRS" in c.value for c in at.caption)


NETCDF_FILL = """  fill:
    type: netcdf
    output_dir: "./data/filled"
    netcdf:
      path: "./data/grid.nc"
      var_map: { precip: pr, tmax: tasmax }

"""


def test_variable_map_edits_survive_explore(monkeypatch, example_project, open_project):
    text = example_project.read_text(encoding="utf-8").replace("streamflow:", NETCDF_FILL + "streamflow:", 1)
    example_project.write_text(text, encoding="utf-8")
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(example_project.parent))
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    open_project(at, example_project.parent)
    # an edit in the table is written to cfg on that run (AppTest cannot type into st.data_editor)
    at.session_state["cfg"]["weather"]["fill"]["netcdf"]["var_map"]["tmin"] = "tasmin"
    at.segmented_control(key="mode").set_value("Explore").run()
    at.segmented_control(key="mode").set_value("Configure").run()
    assert at.session_state["cfg"]["weather"]["fill"]["netcdf"]["var_map"] == {
        "precip": "pr", "tmax": "tasmax", "tmin": "tasmin"}
    assert any(c.value == "Variable map *" for c in at.caption)


def test_empty_block_of_the_unused_fill_type_is_dropped(monkeypatch, example_project, open_project):
    block = NETCDF_FILL.replace("  fill:\n", "  fill:\n    csv: {}\n")
    text = example_project.read_text(encoding="utf-8").replace("streamflow:", block + "streamflow:", 1)
    example_project.write_text(text, encoding="utf-8")
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(example_project.parent))
    at = open_project(AppTest.from_file(PAGE, default_timeout=60).run(), example_project.parent)
    assert "csv" not in at.session_state["cfg"]["weather"]["fill"]
    at.button(key="validate").click().run()
    assert not any(k.startswith("weather.fill.csv") for k in at.session_state.get("file_errors", {}))
    _, _, result = at.session_state["last_run"]
    assert "weather.fill.csv" not in (result.error or "")


def test_empty_variable_map_still_has_its_columns(monkeypatch, example_project, open_project):
    block = NETCDF_FILL.replace("      var_map: { precip: pr, tmax: tasmax }\n", "")
    text = example_project.read_text(encoding="utf-8").replace("streamflow:", block + "streamflow:", 1)
    example_project.write_text(text, encoding="utf-8")
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(example_project.parent))
    at = open_project(AppTest.from_file(PAGE, default_timeout=60).run(), example_project.parent)
    table = next(e.value for e in at.get("dataframe") if e.key == "f::weather.fill.netcdf.var_map")
    assert list(table.columns) == ["variable", "name"] and table.empty
