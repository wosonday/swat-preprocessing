"""Tests for StationWeatherConverter."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _make_master(tmp_path: Path, filename: str, stations: list[dict]) -> Path:
    df = pd.DataFrame(stations)
    p = tmp_path / filename
    df.to_csv(p, index=False)
    return p


def _write_swat_pcp(path: Path, start: str, values: list[float]) -> None:
    lines = [pd.Timestamp(start).strftime("%Y%m%d")]
    lines.extend(str(v) for v in values)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_swat_tmp(path: Path, start: str, pairs: list[tuple[float, float]]) -> None:
    """pairs = [(tmin, tmax), ...] -- matches the tmin,tmax convention used
    by real SWAT2012 vendor temperature files."""
    lines = [pd.Timestamp(start).strftime("%Y%m%d")]
    lines.extend(f"{tn},{tx}" for tn, tx in pairs)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


_PCP_STATIONS = [
    {"ID": 1, "NAME": "pcp_ALPHA", "LAT": 13.95, "LONG": 108.65, "ELEVATION": 416},
    {"ID": 2, "NAME": "pcp_BETA",  "LAT": 14.65, "LONG": 107.83, "ELEVATION": 616},
]

_TMP_STATIONS = [
    {"ID": 1, "NAME": "tmp_ALPHA", "LAT": 13.95, "LONG": 108.65, "ELEVATION": 416},
]


class TestStationWeatherConverterPrecip:
    def test_reads_swat_classic_precip(self, tmp_path):
        from swatprep.converters.station_weather import StationWeatherConverter

        master = _make_master(tmp_path, "master_pcp.txt", _PCP_STATIONS)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_swat_pcp(raw_dir / "pcp_ALPHA.txt", "1990-01-01", [0.0, 0.3, 1.5])
        _write_swat_pcp(raw_dir / "pcp_BETA.txt", "1990-01-01", [0.0, 0.0, 2.1])

        result = StationWeatherConverter(pcp_master=master, pcp_dir=raw_dir).convert()

        assert "precip" in result.daily
        assert set(result.daily["precip"].columns) == {"1", "2"}
        assert list(result.daily["precip"]["1"]) == [0.0, 0.3, 1.5]
        assert result.temp_stations is None
        assert result.stations.loc["1", "name"] == "ALPHA"
        assert result.stations.loc["1", "lat"] == 13.95

    def test_missing_raw_file_is_warn(self, tmp_path):
        from swatprep.converters.station_weather import StationWeatherConverter
        from swatprep.qa import failures, warnings

        master = _make_master(tmp_path, "master_pcp.txt", _PCP_STATIONS)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_swat_pcp(raw_dir / "pcp_ALPHA.txt", "1990-01-01", [0.0, 0.3, 1.5])
        # BETA has no raw file

        result = StationWeatherConverter(pcp_master=master, pcp_dir=raw_dir).convert()

        assert failures(result.qa) == []
        assert any("pcp_BETA" in c.message for c in warnings(result.qa))
        assert set(result.daily["precip"].columns) == {"1"}

    def test_csv_fallback_for_precip(self, tmp_path):
        from swatprep.converters.station_weather import StationWeatherConverter

        master = _make_master(tmp_path, "master_pcp.txt", [_PCP_STATIONS[0]])
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        df = pd.DataFrame({"date": ["1990-01-01", "1990-01-02"], "precip": [0.0, 0.3]})
        df.to_csv(raw_dir / "pcp_ALPHA.txt", index=False)

        result = StationWeatherConverter(pcp_master=master, pcp_dir=raw_dir).convert()

        assert list(result.daily["precip"]["1"]) == [0.0, 0.3]

    def test_requires_at_least_one_group(self):
        from swatprep.converters.station_weather import StationWeatherConverter
        from swatprep.errors import InputValidationError

        with pytest.raises(InputValidationError, match="at least one"):
            StationWeatherConverter()

    def test_master_without_dir_raises(self, tmp_path):
        """pcp_master given without pcp_dir must fail __init__'s pairing check
        (not the earlier "at least one" check -- pcp_master alone satisfies that)."""
        from swatprep.converters.station_weather import StationWeatherConverter
        from swatprep.errors import InputValidationError

        with pytest.raises(InputValidationError, match="together"):
            StationWeatherConverter(pcp_master=tmp_path / "master_pcp.txt")

    def test_no_data_value_converted_to_nan(self, tmp_path):
        from swatprep.converters.station_weather import StationWeatherConverter

        master = _make_master(tmp_path, "master_pcp.txt", [_PCP_STATIONS[0]])
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        # Write precip file with -99.0 sentinel value among real values
        _write_swat_pcp(raw_dir / "pcp_ALPHA.txt", "1990-01-01", [0.5, -99.0, 1.2, -99.0, 0.8])

        result = StationWeatherConverter(pcp_master=master, pcp_dir=raw_dir).convert()

        precip_data = list(result.daily["precip"]["1"])
        # Check that the sentinel values (-99.0) have been converted to NaN
        assert precip_data[0] == 0.5
        assert pd.isna(precip_data[1])  # was -99.0
        assert precip_data[2] == 1.2
        assert pd.isna(precip_data[3])  # was -99.0
        assert precip_data[4] == 0.8


class TestStationWeatherConverterTemperature:
    def test_reads_swat_classic_tmp(self, tmp_path):
        from swatprep.converters.station_weather import StationWeatherConverter

        master = _make_master(tmp_path, "master_tmp.txt", _TMP_STATIONS)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_swat_tmp(raw_dir / "tmp_ALPHA.txt", "1990-01-01",
                         [(16.4, 24.9), (15.3, 24.1)])

        result = StationWeatherConverter(tmp_master=master, tmp_dir=raw_dir).convert()

        assert list(result.daily["tmax"]["1"]) == [24.9, 24.1]
        assert list(result.daily["tmin"]["1"]) == [16.4, 15.3]
        assert result.precip_stations is None

    def test_combined_precip_and_temp(self, tmp_path):
        from swatprep.converters.station_weather import StationWeatherConverter

        pcp_master = _make_master(tmp_path, "master_pcp.txt", _PCP_STATIONS)
        pcp_dir = tmp_path / "pcp_raw"
        pcp_dir.mkdir()
        _write_swat_pcp(pcp_dir / "pcp_ALPHA.txt", "1990-01-01", [0.0, 0.3, 1.5])
        _write_swat_pcp(pcp_dir / "pcp_BETA.txt", "1990-01-01", [0.0, 0.0, 2.1])

        tmp_master = _make_master(tmp_path, "master_tmp.txt", _TMP_STATIONS)
        tmp_dir = tmp_path / "tmp_raw"
        tmp_dir.mkdir()
        _write_swat_tmp(tmp_dir / "tmp_ALPHA.txt", "1990-01-01",
                         [(16.4, 24.9), (15.3, 24.1), (16.0, 22.8)])

        result = StationWeatherConverter(
            pcp_master=pcp_master, pcp_dir=pcp_dir,
            tmp_master=tmp_master, tmp_dir=tmp_dir,
        ).convert()

        assert set(result.daily["precip"].columns) == {"1", "2"}
        assert set(result.daily["tmax"].columns) == {"1"}
        assert set(result.stations.index) == {"1", "2"}
        assert not result.wgn_stats.empty
        # WGN station set = union of precip and tmax columns -> both "1" and "2"
        assert set(result.wgn_stats["station_id"]) == {"1", "2"}
