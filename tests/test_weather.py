"""Tests for WeatherPreprocessor and WeatherWriter."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from swatprep.config import WeatherConfig
from swatprep.core.weather import WeatherPreprocessor
from swatprep.errors import InputValidationError
from swatprep.qa import failures


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cfg(stations_csv, data_dir, **kwargs) -> WeatherConfig:
    defaults = dict(
        stations=stations_csv,
        data_dir=data_dir,
        start=date(2000, 1, 1),
        end=date(2000, 1, 10),
    )
    defaults.update(kwargs)
    return WeatherConfig(**defaults)


# ---------------------------------------------------------------------------
# Stations loading
# ---------------------------------------------------------------------------


def test_stations_loaded(weather_stations_csv, weather_data_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    assert set(result.stations.index) == {"ST001", "ST002"}
    assert "lat" in result.stations.columns


def test_stations_missing_column_raises(tmp_dir, weather_data_dir):
    bad_csv = tmp_dir / "bad_stations.csv"
    bad_csv.write_text("id,name,lat\nST001,A,15.5\n", encoding="utf-8")
    cfg = _make_cfg(bad_csv, weather_data_dir)
    with pytest.raises(InputValidationError, match="missing required columns"):
        WeatherPreprocessor(cfg).run()


# ---------------------------------------------------------------------------
# Daily data loading
# ---------------------------------------------------------------------------


def test_daily_loaded_for_all_stations(weather_stations_csv, weather_data_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    assert "precip" in result.daily
    assert "tmax" in result.daily
    assert "tmin" in result.daily
    assert set(result.daily["precip"].columns) == {"ST001", "ST002"}


def test_daily_shape_matches_date_range(weather_stations_csv, weather_data_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    precip = result.daily["precip"]
    assert len(precip) == 10  # 2000-01-01 to 2000-01-10


def test_missing_data_file_produces_fail_qa(weather_stations_csv, tmp_dir):
    # data_dir exists but no files inside
    empty_dir = tmp_dir / "empty"
    empty_dir.mkdir()
    cfg = _make_cfg(weather_stations_csv, empty_dir)
    with pytest.raises(InputValidationError, match="No valid station data files"):
        WeatherPreprocessor(cfg).run()


def test_missing_policy_fail_triggers_fail_check(weather_stations_csv, tmp_dir):
    """If a station has NaN after reindex and policy=fail, a fail QA check is emitted."""
    data_dir = tmp_dir / "data"
    data_dir.mkdir()
    # Only 5 days of data, config asks for 10 → gap → missing
    dates = pd.date_range("2000-01-01", periods=5, freq="D")
    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "precip": [1.0, 0.0, 2.0, 0.0, 1.5],
        "tmax": [30.0] * 5,
        "tmin": [20.0] * 5,
    })
    df.to_csv(data_dir / "ST001.csv", index=False)
    df.to_csv(data_dir / "ST002.csv", index=False)

    cfg = _make_cfg(weather_stations_csv, data_dir, missing_policy="fail")
    result = WeatherPreprocessor(cfg).run()
    fail_checks = failures(result.qa)
    assert any("missing" in c.name for c in fail_checks)


def test_missing_policy_warn_allows_success(weather_stations_csv, tmp_dir):
    """Same gap, but policy=warn → no fail QA checks."""
    data_dir = tmp_dir / "data"
    data_dir.mkdir()
    dates = pd.date_range("2000-01-01", periods=5, freq="D")
    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "precip": [1.0, 0.0, 2.0, 0.0, 1.5],
        "tmax": [30.0] * 5,
        "tmin": [20.0] * 5,
    })
    df.to_csv(data_dir / "ST001.csv", index=False)
    df.to_csv(data_dir / "ST002.csv", index=False)

    cfg = _make_cfg(weather_stations_csv, data_dir, missing_policy="warn")
    result = WeatherPreprocessor(cfg).run()
    fail_checks = failures(result.qa)
    assert not fail_checks


# ---------------------------------------------------------------------------
# WGN statistics
# ---------------------------------------------------------------------------


def test_wgn_has_12_rows_per_station(weather_stations_csv, weather_data_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    wgn = result.wgn_stats
    for sid in ("ST001", "ST002"):
        assert len(wgn[wgn["station_id"] == sid]) == 12


def test_wgn_columns_present(weather_stations_csv, weather_data_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    expected = {"TMPMX", "TMPMN", "TMPSTDMX", "TMPSTDMN",
                "PCPMM", "PCPSTD", "PCPSKW", "PR_W1", "PR_W2", "PCPD",
                "RAINHHMX", "SOLARAV", "DEWPT", "WNDAV"}
    assert expected.issubset(set(result.wgn_stats.columns))


def test_wgn_unavailable_params_are_minus99(weather_stations_csv, weather_data_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    wgn = result.wgn_stats
    for col in ("RAINHHMX", "SOLARAV", "DEWPT", "WNDAV"):
        assert (wgn[col] == -99.0).all(), f"{col} should be -99 (not computed from daily data)"


# ---------------------------------------------------------------------------
# WeatherWriter integration
# ---------------------------------------------------------------------------


def test_weather_writer_creates_pcp_and_tmp(weather_stations_csv, weather_data_dir, tmp_dir):
    from swatprep.writers.weather import WeatherWriter

    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()

    out = tmp_dir / "weather_out"
    written = WeatherWriter(result, out).write()

    paths = [p.name for p in written]
    assert "ST001.pcp" in paths
    assert "ST002.pcp" in paths
    assert "ST001.tmp" in paths
    assert "ST002.tmp" in paths
    assert "wgn.csv" in paths


def test_pcp_file_format(weather_stations_csv, weather_data_dir, tmp_dir):
    from swatprep.writers.weather import WeatherWriter

    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()

    out = tmp_dir / "weather_out"
    WeatherWriter(result, out).write()

    pcp = (out / "ST001.pcp").read_text(encoding="utf-8").splitlines()
    # Line 0: title, lines 1-3: Lati/Long/Elev, line 4: date, lines 5+: data
    assert pcp[0].startswith("Precipitation data")
    assert pcp[1].startswith("Lati")
    assert pcp[4] == "19991231"  # day before 2000-01-01
    # Data lines: 10.3f format → 10 chars
    assert len(pcp[5].strip()) > 0


def test_tmp_file_has_two_values_per_line(weather_stations_csv, weather_data_dir, tmp_dir):
    from swatprep.writers.weather import WeatherWriter

    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()

    out = tmp_dir / "weather_out"
    WeatherWriter(result, out).write()

    tmp_lines = (out / "ST001.tmp").read_text(encoding="utf-8").splitlines()
    data_line = tmp_lines[5]  # first data line
    # Two 10-char fields → 20 chars
    assert len(data_line) == 20
