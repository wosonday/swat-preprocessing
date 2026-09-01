"""Tests for SWATPlusWeatherWriter's output format.

Includes both the weather-sta.cli / weather-wgn.cli linking-file tests and
the ported data-file format regression tests that used to live in the
deleted tests/test_weather_plus.py (against the now-deleted
SWATPlusWeatherConverter) -- SWATPlusWeatherWriter emits the exact same
on-disk format, so these assertions still pin real requirements.
"""
from __future__ import annotations

import textwrap
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


def _make_single_station(tmp_dir, sid="ALPHA", name="ALPHA", lat=13.95, lon=108.65, elev=416):
    """Write a one-station stations.csv; returns its path."""
    sta = tmp_dir / "stations.csv"
    sta.write_text(textwrap.dedent(f"""\
        id,name,lat,lon,elev
        {sid},{name},{lat},{lon},{elev}
    """), encoding="utf-8")
    return sta


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


# ---------------------------------------------------------------------------
# Data-file format (ported from the deleted tests/test_weather_plus.py,
# adapted from SWATPlusWeatherConverter to SWATPlusWeatherWriter)
# ---------------------------------------------------------------------------


def test_pcp_header_line2(tmp_dir):
    """3-line header: title, 'nbyr tstep lat lon elev' column labels, then
    the lat/lon/elev data row formatted to 3 decimal places."""
    sta = _make_single_station(tmp_dir, lat=13.95, lon=108.65, elev=416)
    data_dir = tmp_dir / "data"
    data_dir.mkdir()
    dates = pd.date_range("2000-01-01", periods=5, freq="D")
    pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "precip": [1.0] * 5}).to_csv(
        data_dir / "ALPHA.csv", index=False
    )
    cfg = _make_cfg(sta, data_dir, variables=["precip"], end=date(2000, 1, 5))
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    lines = (out / "ALPHA.pcp").read_text(encoding="utf-8").splitlines()
    assert lines[1] == "nbyr     tstep       lat       lon      elev"
    assert "13.950" in lines[2]
    assert "108.650" in lines[2]
    assert "416.000" in lines[2]


def test_pcp_data_row_width(tmp_dir):
    """A precip data row is a fixed 22 chars: year(4) + doy(5) + value(11,5dp) + 2 trailing spaces."""
    sta = _make_single_station(tmp_dir)
    data_dir = tmp_dir / "data"
    data_dir.mkdir()
    pd.DataFrame({"date": ["2000-01-01"], "precip": [1.0]}).to_csv(
        data_dir / "ALPHA.csv", index=False
    )
    cfg = _make_cfg(sta, data_dir, variables=["precip"], start=date(2000, 1, 1), end=date(2000, 1, 1))
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    lines = (out / "ALPHA.pcp").read_text(encoding="utf-8").splitlines()
    data_row = lines[3]
    assert data_row[:4] == "2000"
    assert data_row[4:9] == "    1"
    assert len(data_row) == 22


def test_tmp_two_col_exact_format(tmp_dir):
    """tmp data row format is exactly '{year:4d}{doy:5d}{tmax:11.5f} {tmin:11.5f}  '."""
    sta = _make_single_station(tmp_dir)
    data_dir = tmp_dir / "data"
    data_dir.mkdir()
    pd.DataFrame({"date": ["2000-01-01"], "tmax": [25.0], "tmin": [9.0]}).to_csv(
        data_dir / "ALPHA.csv", index=False
    )
    cfg = _make_cfg(sta, data_dir, variables=["tmax", "tmin"], start=date(2000, 1, 1), end=date(2000, 1, 1))
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    lines = (out / "ALPHA.tmp").read_text(encoding="utf-8").splitlines()
    assert lines[3] == "2000    1   25.00000     9.00000  "


def test_doy_feb1_leap_year(tmp_dir):
    """Feb 1 2000 (a leap year) is day-of-year 32."""
    sta = _make_single_station(tmp_dir)
    data_dir = tmp_dir / "data"
    data_dir.mkdir()
    pd.DataFrame({"date": ["2000-02-01"], "precip": [5.0]}).to_csv(
        data_dir / "ALPHA.csv", index=False
    )
    cfg = _make_cfg(sta, data_dir, variables=["precip"], start=date(2000, 2, 1), end=date(2000, 2, 1))
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    lines = (out / "ALPHA.pcp").read_text(encoding="utf-8").splitlines()
    assert lines[3][4:9] == "   32"


def test_nan_precip_written_as_minus99(tmp_dir):
    """Missing/NaN values are written as -99.00000 (11-char width, 5 decimals)."""
    sta = _make_single_station(tmp_dir)
    data_dir = tmp_dir / "data"
    data_dir.mkdir()
    pd.DataFrame({
        "date": ["2000-01-01", "2000-01-02"],
        "precip": [5.0, float("nan")],
    }).to_csv(data_dir / "ALPHA.csv", index=False)
    cfg = _make_cfg(
        sta, data_dir, variables=["precip"], missing_policy="warn",
        start=date(2000, 1, 1), end=date(2000, 1, 2),
    )
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    lines = (out / "ALPHA.pcp").read_text(encoding="utf-8").splitlines()
    assert "  -99.00000" in lines[4]


def test_pcp_cli_lists_written_filenames(tmp_dir):
    """pcp.cli (and other per-variable .cli files) list the exact written
    filenames under a 'filename' header line."""
    sta = tmp_dir / "stations.csv"
    sta.write_text(textwrap.dedent("""\
        id,name,lat,lon,elev
        A1,ALPHA,13.95,108.65,416
        A2,BETA,14.65,107.83,616
    """), encoding="utf-8")
    data_dir = tmp_dir / "data"
    data_dir.mkdir()
    dates = pd.date_range("2000-01-01", periods=5, freq="D")
    for sid in ("A1", "A2"):
        pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "precip": [1.0] * 5}).to_csv(
            data_dir / f"{sid}.csv", index=False
        )
    cfg = _make_cfg(sta, data_dir, variables=["precip"], end=date(2000, 1, 5))
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    cli_lines = (out / "pcp.cli").read_text(encoding="utf-8").splitlines()
    assert cli_lines[1] == "filename"
    assert "ALPHA.pcp" in cli_lines
    assert "BETA.pcp" in cli_lines
