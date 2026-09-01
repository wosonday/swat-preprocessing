"""Tests for WeatherGapFiller (swatprep/core/weather_fill.py)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_stations_csv(tmp_path: Path, filename: str, rows: list[dict]) -> Path:
    df = pd.DataFrame(rows)
    p = tmp_path / filename
    df.to_csv(p, index=False)
    return p


def _write_station_csv(data_dir: Path, station_id: str, dates: list[str], **cols) -> None:
    data = {"date": dates}
    data.update(cols)
    pd.DataFrame(data).to_csv(data_dir / f"{station_id}.csv", index=False)


_META = {"name": "StationS1", "lat": 15.0, "lon": 105.0, "elev": 100}


class TestWeatherGapFillerPrecipRatio:
    def test_ratio_correction_fills_precip_and_preserves_real_values(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02", "2000-01-03", "2000-01-04", "2000-01-05", "2000-01-06"]
        _write_station_csv(real_dir, "S1", dates, precip=[2.0, None, 4.0, None, 6.0, 3.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[1.0, 5.0, 2.0, 10.0, 3.0, 1.5])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-06", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-06", missing_policy="warn",
        )

        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()

        filled = result.daily["precip"]["S1"]
        assert filled.iloc[0] == 2.0                    # real value untouched
        assert filled.iloc[1] == pytest.approx(10.0)     # 5.0 * factor(2.0)
        assert filled.iloc[2] == 4.0                     # real value untouched
        assert filled.iloc[3] == pytest.approx(20.0)     # 10.0 * factor(2.0)

        row = result.report[
            (result.report["station_id"] == "S1") & (result.report["variable"] == "precip")
        ].iloc[0]
        assert row["n_missing"] == 2
        assert row["n_filled"] == 2
        assert row["n_still_missing"] == 0
        assert row["n_overlap"] == 4
        assert row["correction_type"] == "ratio"
        assert row["correction_value"] == pytest.approx(2.0)
        assert row["status"] == "pass"

    def test_precip_zero_fill_mean_skips_correction(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02"]
        _write_station_csv(real_dir, "S1", dates, precip=[1.0, None])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[0.0, 0.0])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-02", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-02", missing_policy="warn",
        )

        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()

        filled = result.daily["precip"]["S1"]
        assert pd.isna(filled.iloc[1])

        row = result.report.iloc[0]
        assert row["n_missing"] == 1
        assert row["n_filled"] == 0
        assert row["n_overlap"] == 1
        assert row["status"] == "warn"


class TestWeatherGapFillerTemperatureOffset:
    def test_offset_correction_fills_temperature(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02", "2000-01-03", "2000-01-04", "2000-01-05", "2000-01-06"]
        _write_station_csv(real_dir, "S1", dates, tmax=[20.0, None, 24.0, None, 28.0, 22.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, tmax=[15.0, 19.0, 19.0, 23.0, 23.0, 17.0])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["tmax"],
            start="2000-01-01", end="2000-01-06", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["tmax"],
            start="2000-01-01", end="2000-01-06", missing_policy="warn",
        )

        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()

        filled = result.daily["tmax"]["S1"]
        assert filled.iloc[0] == 20.0                   # real value untouched
        assert filled.iloc[1] == pytest.approx(24.0)     # 19.0 + offset(5.0)
        assert filled.iloc[3] == pytest.approx(28.0)     # 23.0 + offset(5.0)

        row = result.report.iloc[0]
        assert row["correction_type"] == "offset"
        assert row["correction_value"] == pytest.approx(5.0)
        assert row["status"] == "pass"


class TestWeatherGapFillerOverlapEdgeCases:
    def test_zero_overlap_skips_fill(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02"]
        _write_station_csv(real_dir, "S1", dates, precip=[None, 5.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[3.0, None])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-02", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-02", missing_policy="warn",
        )

        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()

        filled = result.daily["precip"]["S1"]
        assert pd.isna(filled.iloc[0])

        row = result.report.iloc[0]
        assert row["n_missing"] == 1
        assert row["n_filled"] == 0
        assert row["n_overlap"] == 0
        assert row["status"] == "warn"

    def test_low_overlap_below_threshold_warns_but_still_fills(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02", "2000-01-03"]
        _write_station_csv(real_dir, "S1", dates, precip=[2.0, None, 4.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[1.0, 5.0, 2.0])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-03", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-03", missing_policy="warn",
        )

        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=5).run()

        filled = result.daily["precip"]["S1"]
        assert filled.iloc[1] == pytest.approx(10.0)   # 5.0 * factor(2.0) -- still filled

        row = result.report.iloc[0]
        assert row["n_overlap"] == 2
        assert row["n_filled"] == 1
        assert row["status"] == "warn"                 # below min_overlap_days=5

    def test_station_missing_from_fill_source_warns_and_skips(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller
        from swatprep.qa import warnings

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [
            {"id": "S1", **_META},
            {"id": "S2", "name": "StationS2", "lat": 15.1, "lon": 105.1, "elev": 110},
        ])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02"]
        _write_station_csv(real_dir, "S1", dates, precip=[1.0, 2.0])
        _write_station_csv(real_dir, "S2", dates, precip=[None, 3.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[1.5, 2.5])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-02", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-02", missing_policy="warn",
        )

        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()

        filled_s2 = result.daily["precip"]["S2"]
        assert pd.isna(filled_s2.iloc[0])

        row = result.report[result.report["station_id"] == "S2"].iloc[0]
        assert row["n_missing"] == 1
        assert row["n_filled"] == 0
        assert row["status"] == "warn"

        assert any("S2" in c.message and "no fill source" in c.message for c in warnings(result.qa))


class TestWeatherFillWriter:
    def _build_result(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02", "2000-01-03"]
        _write_station_csv(real_dir, "S1", dates, precip=[2.0, None, 4.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[1.0, 5.0, 2.0])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-03", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-03", missing_policy="warn",
        )
        return WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()

    def test_writes_stations_station_files_and_report(self, tmp_path):
        from swatprep.writers.weather_fill import WeatherFillWriter

        result = self._build_result(tmp_path)
        out = tmp_path / "out"
        written = WeatherFillWriter(result, out).write()

        assert (out / "stations.csv") in written
        assert (out / "S1.csv") in written
        assert (out / "fill_report.csv") in written

    def test_station_csv_format_matches_native_convention(self, tmp_path):
        from swatprep.writers.weather_fill import WeatherFillWriter

        result = self._build_result(tmp_path)
        out = tmp_path / "out"
        WeatherFillWriter(result, out).write()

        df = pd.read_csv(out / "S1.csv")
        assert list(df.columns) == ["date", "precip"]
        assert df["date"].iloc[0] == "2000-01-01"
        assert df["precip"].iloc[0] == 2.0
        assert df["precip"].iloc[1] == pytest.approx(10.0)  # filled value

    def test_stations_csv_has_native_columns(self, tmp_path):
        from swatprep.writers.weather_fill import WeatherFillWriter

        result = self._build_result(tmp_path)
        out = tmp_path / "out"
        WeatherFillWriter(result, out).write()

        df = pd.read_csv(out / "stations.csv")
        assert list(df.columns) == ["id", "name", "lat", "lon", "elev"]
        assert df["id"].iloc[0] == "S1"

    def test_round_trip_loadable_by_weather_preprocessor(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather import WeatherPreprocessor
        from swatprep.writers.weather_fill import WeatherFillWriter
        from swatprep.qa import failures

        result = self._build_result(tmp_path)
        out = tmp_path / "out"
        WeatherFillWriter(result, out).write()

        reload_cfg = WeatherConfig(
            stations=out / "stations.csv", data_dir=out, variables=["precip"],
            start="2000-01-01", end="2000-01-03", missing_policy="fail",
        )
        reloaded = WeatherPreprocessor(reload_cfg).run()

        assert failures(reloaded.qa) == []
        precip = reloaded.daily["precip"]["S1"]
        assert precip.isna().sum() == 0  # the filled day introduced no new gap
