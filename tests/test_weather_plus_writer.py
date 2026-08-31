"""Tests for SWATPlusWeatherWriter's weather-sta.cli / weather-wgn.cli output."""
from __future__ import annotations

from datetime import date

import pandas as pd

from swatprep.config import WeatherConfig
from swatprep.core.weather import WeatherPreprocessor
from swatprep.writers.weather_plus import SWATPlusWeatherWriter


def _make_cfg(stations_csv, data_dir, **kwargs) -> WeatherConfig:
    defaults = dict(
        stations=stations_csv,
        data_dir=data_dir,
        start=date(2000, 1, 1),
        end=date(2000, 1, 10),
    )
    defaults.update(kwargs)
    return WeatherConfig(**defaults)


def test_weather_sta_cli_written(weather_stations_csv, weather_data_dir, tmp_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    written = SWATPlusWeatherWriter(result, out).write()
    assert (out / "weather-sta.cli") in written


def test_weather_sta_cli_lists_both_stations(weather_stations_csv, weather_data_dir, tmp_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    lines = (out / "weather-sta.cli").read_text(encoding="utf-8").splitlines()
    assert lines[1].split()[:2] == ["name", "wgn"]
    body = "\n".join(lines[2:])
    assert "StationA" in body
    assert "StationB" in body


def test_weather_sta_cli_references_written_files(weather_stations_csv, weather_data_dir, tmp_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    lines = (out / "weather-sta.cli").read_text(encoding="utf-8").splitlines()
    station_a_row = next(ln for ln in lines[2:] if ln.split()[0] == "StationA")
    fields = station_a_row.split()
    # columns: name wgn pcp tmp slr hmd wnd pet atmo_dep
    assert fields[2] == "StationA"  # pcp file stem == station name (no collisions)
    assert fields[3] == "StationA"  # tmp file stem
    assert fields[4] == "sim"       # no slr data in the fixture -> "sim"
    assert fields[7] == "null"      # pet
    assert fields[8] == "null"      # atmo_dep


def test_weather_wgn_cli_written(weather_stations_csv, weather_data_dir, tmp_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    written = SWATPlusWeatherWriter(result, out).write()
    assert (out / "weather-wgn.cli") in written


def test_weather_wgn_cli_has_12_rows_per_station(weather_stations_csv, weather_data_dir, tmp_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    lines = (out / "weather-wgn.cli").read_text(encoding="utf-8").splitlines()
    # header line + (group header + column header + 12 rows) per station
    body = lines[1:]
    assert len(body) == 2 * (2 + 12)  # 2 stations in the fixture


def test_weather_wgn_cli_column_header(weather_stations_csv, weather_data_dir, tmp_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    lines = (out / "weather-wgn.cli").read_text(encoding="utf-8").splitlines()
    assert "tmp_max_ave" in lines[2]
    assert "wnd_ave" in lines[2]
