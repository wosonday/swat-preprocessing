"""Tests for swatprep.config — config schema validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from swatprep.config import SWATPrepConfig


# ---------------------------------------------------------------------------
# Minimal valid config
# ---------------------------------------------------------------------------


def test_minimal_config_loads(minimal_config_dict):
    cfg = SWATPrepConfig.model_validate(minimal_config_dict)
    assert cfg.project.name == "test_basin"
    assert cfg.project.crs == "EPSG:32648"
    assert cfg.dem is None
    assert cfg.landuse is None
    assert cfg.soil is None
    assert cfg.weather is None
    assert cfg.streamflow is None


def test_default_targets_is_swatplus(minimal_config_dict):
    cfg = SWATPrepConfig.model_validate(minimal_config_dict)
    assert cfg.project.targets == ["swatplus"]


def test_output_dir_defaults_to_output(minimal_config_dict):
    del minimal_config_dict["project"]["output_dir"]
    cfg = SWATPrepConfig.model_validate(minimal_config_dict)
    assert cfg.project.output_dir == Path("./output")


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------


def test_missing_project_name_fails():
    with pytest.raises(ValidationError):
        SWATPrepConfig.model_validate({"project": {"crs": "EPSG:32648"}})


def test_missing_project_crs_fails():
    with pytest.raises(ValidationError):
        SWATPrepConfig.model_validate({"project": {"name": "test"}})


def test_invalid_target_fails():
    with pytest.raises(ValidationError):
        SWATPrepConfig.model_validate({
            "project": {"name": "t", "crs": "EPSG:4326", "targets": ["bad_target"]}
        })


def test_both_targets_valid():
    cfg = SWATPrepConfig.model_validate({
        "project": {"name": "t", "crs": "EPSG:4326", "targets": ["swat", "swatplus"]}
    })
    assert set(cfg.project.targets) == {"swat", "swatplus"}


# ---------------------------------------------------------------------------
# Weather sub-config
# ---------------------------------------------------------------------------


def test_weather_config_defaults():
    cfg = SWATPrepConfig.model_validate({
        "project": {"name": "t", "crs": "EPSG:4326"},
        "weather": {
            "stations": "./stations.csv",
            "data_dir": "./weather",
            "start": "2000-01-01",
            "end": "2020-12-31",
        },
    })
    assert cfg.weather.missing_policy == "fail"
    assert cfg.weather.format == "csv"
    assert "precip" in cfg.weather.variables
    assert "tmax" in cfg.weather.variables
    assert "tmin" in cfg.weather.variables
    assert cfg.weather.units.precip == "mm"
    assert cfg.weather.units.temperature == "degC"


def test_weather_invalid_missing_policy_fails():
    with pytest.raises(ValidationError):
        SWATPrepConfig.model_validate({
            "project": {"name": "t", "crs": "EPSG:4326"},
            "weather": {
                "stations": "s.csv",
                "data_dir": "./w",
                "start": "2000-01-01",
                "end": "2020-12-31",
                "missing_policy": "ignore",  # invalid
            },
        })


def test_weather_invalid_variable_fails():
    with pytest.raises(ValidationError):
        SWATPrepConfig.model_validate({
            "project": {"name": "t", "crs": "EPSG:4326"},
            "weather": {
                "stations": "s.csv",
                "data_dir": "./w",
                "start": "2000-01-01",
                "end": "2020-12-31",
                "variables": ["precip", "ozone"],  # invalid
            },
        })


def test_weather_end_before_start_fails():
    with pytest.raises(ValidationError):
        SWATPrepConfig.model_validate({
            "project": {"name": "t", "crs": "EPSG:4326"},
            "weather": {
                "stations": "s.csv",
                "data_dir": "./w",
                "start": "2020-12-31",
                "end": "2020-01-01",
            },
        })


# ---------------------------------------------------------------------------
# Streamflow sub-config
# ---------------------------------------------------------------------------


def test_streamflow_config_defaults():
    cfg = SWATPrepConfig.model_validate({
        "project": {"name": "t", "crs": "EPSG:4326"},
        "streamflow": {"path": "./flow.csv"},
    })
    assert cfg.streamflow.date_col == "date"
    assert cfg.streamflow.station_id_col == "station_id"
    assert cfg.streamflow.value_col == "flow"
    assert cfg.streamflow.units == "m3s"


def test_streamflow_invalid_units_fails():
    with pytest.raises(ValidationError):
        SWATPrepConfig.model_validate({
            "project": {"name": "t", "crs": "EPSG:4326"},
            "streamflow": {"path": "./flow.csv", "units": "cms"},  # invalid
        })


# ---------------------------------------------------------------------------
# from_yaml
# ---------------------------------------------------------------------------


def test_from_yaml_loads(minimal_config_yaml):
    cfg = SWATPrepConfig.from_yaml(minimal_config_yaml)
    assert cfg.project.name == "test_basin"


def test_from_yaml_resolves_relative_paths_from_config_directory(tmp_dir):
    import yaml

    config_dir = tmp_dir / "project"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        yaml.dump({
            "project": {
                "name": "test_basin",
                "crs": "EPSG:32648",
                "boundary": "data/boundary.gpkg",
                "output_dir": "output",
            },
            "weather": {
                "stations": "data/stations.csv",
                "data_dir": "data/weather",
                "start": "2000-01-01",
                "end": "2000-12-31",
            },
        }),
        encoding="utf-8",
    )

    cfg = SWATPrepConfig.from_yaml(config_path)

    assert cfg.project.boundary == config_dir / "data/boundary.gpkg"
    assert cfg.project.output_dir == config_dir / "output"
    assert cfg.weather.stations == config_dir / "data/stations.csv"
    assert cfg.weather.data_dir == config_dir / "data/weather"


# ---------------------------------------------------------------------------
# configured_domains
# ---------------------------------------------------------------------------


def test_configured_domains_empty_when_no_domains(minimal_config_dict):
    cfg = SWATPrepConfig.model_validate(minimal_config_dict)
    assert cfg.configured_domains() == []


def test_configured_domains_reports_weather():
    cfg = SWATPrepConfig.model_validate({
        "project": {"name": "t", "crs": "EPSG:4326"},
        "weather": {
            "stations": "s.csv",
            "data_dir": "./w",
            "start": "2000-01-01",
            "end": "2000-12-31",
        },
    })
    domains = cfg.configured_domains()
    assert "weather" in domains
    assert "dem" not in domains
