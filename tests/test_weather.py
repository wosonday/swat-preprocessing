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
    empty_dir = tmp_dir / "empty"
    empty_dir.mkdir()
    cfg = _make_cfg(weather_stations_csv, empty_dir)
    with pytest.raises(InputValidationError, match="No valid station data files"):
        WeatherPreprocessor(cfg).run()


def test_missing_policy_fail_triggers_fail_check(weather_stations_csv, tmp_dir):
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
    cfg = _make_cfg(weather_stations_csv, data_dir, missing_policy="fail")
    result = WeatherPreprocessor(cfg).run()
    fail_checks = failures(result.qa)
    assert any("missing" in c.name for c in fail_checks)


def test_missing_policy_warn_allows_success(weather_stations_csv, tmp_dir):
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
        assert (wgn[col] == -99.0).all()


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
    assert "pcp_StationA.txt" in paths
    assert "pcp_StationB.txt" in paths
    assert "tmp_StationA.txt" in paths
    assert "tmp_StationB.txt" in paths
    assert "master_pcp.txt" in paths
    assert "master_tmp.txt" in paths
    assert "wgn.csv" in paths


def test_pcp_file_format(weather_stations_csv, weather_data_dir, tmp_dir):
    """No metadata header block; line 1 is the date of the FIRST record (no offset)."""
    from swatprep.writers.weather import WeatherWriter
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    WeatherWriter(result, out).write()
    pcp = (out / "pcp_StationA.txt").read_text(encoding="utf-8").splitlines()
    assert pcp[0] == "20000101"
    assert len(pcp) == 11  # date line + 10 daily values
    assert pcp[1] == "1.0"  # weather_data_dir fixture: StationA precip[0] == 1.0


def test_tmp_file_has_tmin_tmax_per_line(weather_stations_csv, weather_data_dir, tmp_dir):
    from swatprep.writers.weather import WeatherWriter
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    WeatherWriter(result, out).write()
    tmp_lines = (out / "tmp_StationA.txt").read_text(encoding="utf-8").splitlines()
    tmin_str, tmax_str = tmp_lines[1].split(",")
    assert float(tmin_str) == 22.0  # weather_data_dir fixture: StationA tmin[0]
    assert float(tmax_str) == 30.1  # weather_data_dir fixture: StationA tmax[0]


def test_master_pcp_has_uppercase_columns_and_prefix(weather_stations_csv, weather_data_dir, tmp_dir):
    from swatprep.writers.weather import WeatherWriter
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    WeatherWriter(result, out).write()
    master = pd.read_csv(out / "master_pcp.txt")
    assert list(master.columns) == ["ID", "NAME", "LAT", "LONG", "ELEVATION"]
    assert {"pcp_StationA", "pcp_StationB"}.issubset(set(master["NAME"]))


def test_master_pcp_excludes_stations_with_no_written_data_file(weather_stations_csv, tmp_dir):
    """A station whose raw data file is missing (only a fail QA, not a hard
    error since another station succeeds) must not appear in master_pcp.txt --
    that file is a real SWAT2012 model input, not just a reference list."""
    from swatprep.writers.weather import WeatherWriter

    data_dir = tmp_dir / "data"
    data_dir.mkdir()
    dates = pd.date_range("2000-01-01", periods=10, freq="D")
    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "precip": [1.0] * 10,
        "tmax": [30.0] * 10,
        "tmin": [20.0] * 10,
    })
    # Only ST001's data file is written; ST002's is missing entirely.
    df.to_csv(data_dir / "ST001.csv", index=False)

    cfg = _make_cfg(weather_stations_csv, data_dir)
    result = WeatherPreprocessor(cfg).run()

    from swatprep.qa import failures as _failures
    fail_checks = _failures(result.qa)
    assert any("data_file" in c.name for c in fail_checks)

    out = tmp_dir / "weather_out"
    WeatherWriter(result, out).write()
    master = pd.read_csv(out / "master_pcp.txt")
    assert "pcp_StationA" in set(master["NAME"])
    assert "pcp_StationB" not in set(master["NAME"])
    assert "ST002" not in set(master["ID"])


# ---------------------------------------------------------------------------
# Split-source mode (separate precip / temperature stations)
# ---------------------------------------------------------------------------


def test_split_source_loads_different_stations(tmp_dir):
    import textwrap
    from swatprep.config import WeatherSourceConfig
    from swatprep.writers.weather import WeatherWriter

    precip_sta = tmp_dir / "precip_stations.csv"
    precip_sta.write_text(textwrap.dedent("""\
        id,name,lat,lon,elev
        P1,PrecipA,14.0,108.7,300
        P2,PrecipB,13.4,108.5,200
        P3,PrecipC,13.0,109.0,50
    """), encoding="utf-8")
    precip_dir = tmp_dir / "precip_data"
    precip_dir.mkdir()
    dates = pd.date_range("2000-01-01", periods=10, freq="D")
    for sid in ("P1", "P2", "P3"):
        df = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "precip": [1.0] * 10})
        df.to_csv(precip_dir / f"{sid}.csv", index=False)

    temp_sta = tmp_dir / "temp_stations.csv"
    temp_sta.write_text(textwrap.dedent("""\
        id,name,lat,lon,elev
        T1,TempA,14.0,108.7,300
    """), encoding="utf-8")
    temp_dir = tmp_dir / "temp_data"
    temp_dir.mkdir()
    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "tmax": [30.0] * 10,
        "tmin": [20.0] * 10,
    })
    df.to_csv(temp_dir / "T1.csv", index=False)

    cfg = WeatherConfig(
        precip=WeatherSourceConfig(stations=precip_sta, data_dir=precip_dir),
        temp=WeatherSourceConfig(stations=temp_sta, data_dir=temp_dir),
        variables=["precip", "tmax", "tmin"],
        start=date(2000, 1, 1),
        end=date(2000, 1, 10),
    )
    result = WeatherPreprocessor(cfg).run()
    assert set(result.daily["precip"].columns) == {"P1", "P2", "P3"}
    assert set(result.daily["tmax"].columns) == {"T1"}
    assert set(result.daily["tmin"].columns) == {"T1"}

    out = tmp_dir / "weather_out"
    written = WeatherWriter(result, out).write()
    paths = [p.name for p in written]
    assert "pcp_PrecipA.txt" in paths
    assert "tmp_TempA.txt" in paths
    assert "tmp_PrecipA.txt" not in paths
    assert "master_pcp.txt" in paths
    assert "master_tmp.txt" in paths

    from swatprep.qa import failures as _failures
    assert not _failures(result.qa)


def test_split_source_precip_only(tmp_dir):
    from swatprep.config import WeatherSourceConfig

    sta = tmp_dir / "stations.csv"
    sta.write_text("id,name,lat,lon,elev\nS1,A,15,105,100\n", encoding="utf-8")
    data_dir = tmp_dir / "data"
    data_dir.mkdir()
    dates = pd.date_range("2000-01-01", periods=10, freq="D")
    pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "precip": [2.0] * 10}).to_csv(
        data_dir / "S1.csv", index=False
    )
    cfg = WeatherConfig(
        precip=WeatherSourceConfig(stations=sta, data_dir=data_dir),
        variables=["precip"],
        start=date(2000, 1, 1),
        end=date(2000, 1, 10),
    )
    result = WeatherPreprocessor(cfg).run()
    assert "precip" in result.daily
    assert result.temp_stations is None


def test_file_pattern_by_name(tmp_dir):
    """file_pattern='{name}.csv' matches files by station name, not id."""
    import textwrap
    from swatprep.config import WeatherSourceConfig

    sta = tmp_dir / "stations.csv"
    sta.write_text(textwrap.dedent("""\
        id,name,lat,lon,elev
        1,STATION01,14,108.7,300
        2,AYUNPA,13.4,108.5,200
    """), encoding="utf-8")
    data_dir = tmp_dir / "data"
    data_dir.mkdir()
    dates = pd.date_range("2000-01-01", periods=10, freq="D")
    for name in ("STATION01", "AYUNPA"):
        df = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "precip": [1.0] * 10,
            "tmax": [30.0] * 10,
            "tmin": [20.0] * 10,
        })
        df.to_csv(data_dir / f"{name}.csv", index=False)

    cfg = WeatherConfig(
        stations=sta,
        data_dir=data_dir,
        file_pattern="{name}.csv",
        variables=["precip", "tmax", "tmin"],
        start=date(2000, 1, 1),
        end=date(2000, 1, 10),
    )
    result = WeatherPreprocessor(cfg).run()
    assert set(result.daily["precip"].columns) == {"1", "2"}
    from swatprep.qa import failures as _failures
    assert not _failures(result.qa)
