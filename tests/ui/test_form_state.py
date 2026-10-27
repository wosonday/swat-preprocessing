from datetime import date

from app.services.form_model import field_spec
from app.services.form_state import (
    apply, count_for, file_errors, from_widget, new_config, schema_errors, to_widget,
)
from app.services.project_io import load_yaml
from swatprep.config import DEMConfig, FillNetCDFConfig, ProjectConfig, StreamflowConfig, WeatherConfig
from swatprep.qa import QACheck


def test_to_widget_uses_default_when_absent():
    assert to_widget(field_spec(DEMConfig, "resampling"), None) == "bilinear"
    assert to_widget(field_spec(DEMConfig, "path"), None) == ""
    assert to_widget(field_spec(DEMConfig, "resolution"), None) is None


def test_date_and_list_conversions():
    assert to_widget(field_spec(WeatherConfig, "start"), "2000-01-31") == date(2000, 1, 31)
    stations = field_spec(StreamflowConfig, "stations")
    assert to_widget(stations, ["A", "B"]) == "A, B"
    assert from_widget(stations, " A, ,B ") == ["A", "B"]
    assert from_widget(stations, "") is None


def test_apply_does_not_add_defaults():
    section = {}
    apply(section, field_spec(DEMConfig, "resampling"), "bilinear")
    apply(section, field_spec(DEMConfig, "clip"), True)
    apply(section, field_spec(DEMConfig, "resolution"), None)
    assert section == {}


def test_apply_adds_changed_values():
    section = {}
    apply(section, field_spec(DEMConfig, "resampling"), "cubic")
    apply(section, field_spec(DEMConfig, "path"), " /data/dem.tif ")
    apply(section, field_spec(DEMConfig, "resolution"), 30.0)
    assert section == {"resampling": "cubic", "path": "/data/dem.tif", "resolution": 30.0}


def test_apply_keeps_unchanged_existing_keys_as_they_are():
    section = {"start": "1981-01-01", "resolution": 30, "output_name": "dem_projected.tif"}
    apply(section, field_spec(WeatherConfig, "start"), date(1981, 1, 1))
    apply(section, field_spec(DEMConfig, "resolution"), 30.0)
    apply(section, field_spec(DEMConfig, "output_name"), "dem_projected.tif")
    assert section == {"start": "1981-01-01", "resolution": 30, "output_name": "dem_projected.tif"}


def test_apply_removes_cleared_optional_key():
    section = {"boundary": "./b.geojson"}
    apply(section, field_spec(ProjectConfig, "boundary"), "")
    assert section == {}


def test_mapping_round_trip():
    spec = field_spec(FillNetCDFConfig, "var_map")
    assert to_widget(spec, {"precip": "pr"}) == {"precip": "pr"}
    assert from_widget(spec, {}) is None


def test_schema_errors_locations():
    errors = schema_errors({"project": {"name": "X"}, "dem": {}})
    assert "project.crs" in errors and "dem.path" in errors


def test_schema_errors_model_level_message():
    cfg = new_config("X", "EPSG:32648")
    cfg["weather"] = {"stations": "s.csv", "data_dir": "d", "start": "2001-01-01", "end": "2000-01-01"}
    errors = schema_errors(cfg)
    assert "weather" in errors and "on or after" in errors["weather"]


def test_example_config_is_valid(example_project):
    assert schema_errors(load_yaml(example_project)) == {}


def test_file_errors_from_checks():
    checks = [
        QACheck("file_exists:dem.path", "fail", "File not found: x"),
        QACheck("file_exists:clip[0].src", "fail", "File not found: y"),
        QACheck("file_exists:soil.table", "pass", "ok"),
    ]
    assert file_errors(checks) == {"dem.path": "File not found: x", "clip.0.src": "File not found: y"}


def test_count_for_section():
    errors = {"dem.path": "a", "dem.resolution": "b", "demx": "c", "weather": "d"}
    assert count_for(errors, "dem") == 2
    assert count_for(errors, "weather") == 1
