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

    def test_zero_ratio_still_fills_but_flags_warn(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02", "2000-01-03"]
        # Overlap days are 0 and 2: real is 0.0 on both (mean(obs[overlap]) == 0),
        # fill is 2.0/3.0 on both (mean(fill[overlap]) == 2.5 > 0) -- so the
        # mean_fill<=0 skip guard does NOT trigger, but the resulting ratio is 0.0.
        _write_station_csv(real_dir, "S1", dates, precip=[0.0, None, 0.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[2.0, 5.0, 3.0])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-03", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-03", missing_policy="warn",
        )

        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()

        filled = result.daily["precip"]["S1"]
        assert filled.iloc[1] == 0.0  # missing day IS filled, with 0.0 (5.0 * 0.0)

        row = result.report.iloc[0]
        assert row["correction_type"] == "ratio"
        assert row["correction_value"] == pytest.approx(0.0)
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

    def test_upstream_preprocessor_qa_is_propagated_and_downgraded_to_warn(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller
        from swatprep.qa import failures, warnings

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [
            {"id": "S1", **_META},
            {"id": "S2", "name": "StationS2", "lat": 15.1, "lon": 105.1, "elev": 110},
        ])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02"]
        _write_station_csv(real_dir, "S1", dates, precip=[1.0, 2.0])
        # No S2.csv written -- S1 has a data file, S2's data file is entirely missing.

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

        # The upstream WeatherPreprocessor "fail" for S2's missing data file
        # must not surface as a fail here -- it should be downgraded to warn
        # and merged into this result's QA list, not silently dropped.
        assert failures(result.qa) == []
        assert any("S2" in c.message for c in warnings(result.qa))


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


class TestCLIFillWeather:
    def _build_inputs(self, tmp_path):
        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02", "2000-01-03"]
        _write_station_csv(real_dir, "S1", dates, precip=[2.0, None, 4.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[1.0, 5.0, 2.0])

        return real_sta, real_dir, fill_sta, fill_dir

    def test_cli_fill_weather_help(self):
        from click.testing import CliRunner
        from swatprep.cli import main

        runner = CliRunner()
        res = runner.invoke(main, ["fill", "weather", "--help"])
        assert res.exit_code == 0
        assert "--fill-stations" in res.output
        assert "--fill-search-radius" in res.output

    def test_cli_fill_weather_runs_end_to_end(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        real_sta, real_dir, fill_sta, fill_dir = self._build_inputs(tmp_path)
        out = tmp_path / "out"
        runner = CliRunner()
        res = runner.invoke(main, [
            "fill", "weather",
            "--stations", str(real_sta), "--data-dir", str(real_dir),
            "--fill-stations", str(fill_sta), "--fill-data-dir", str(fill_dir),
            "--variables", "precip",
            "--start", "2000-01-01", "--end", "2000-01-03",
            "--min-overlap-days", "1",
            str(out),
        ])

        assert res.exit_code == 0, res.output
        assert (out / "stations.csv").exists()
        assert (out / "S1.csv").exists()
        assert (out / "fill_report.csv").exists()

        df = pd.read_csv(out / "S1.csv")
        assert df["precip"].iloc[1] == pytest.approx(10.0)

    def test_cli_fill_weather_missing_required_option_fails(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        real_sta, real_dir, _fill_sta, _fill_dir = self._build_inputs(tmp_path)
        out = tmp_path / "out"
        runner = CliRunner()
        res = runner.invoke(main, [
            "fill", "weather",
            "--stations", str(real_sta), "--data-dir", str(real_dir),
            "--variables", "precip",
            "--start", "2000-01-01", "--end", "2000-01-03",
            str(out),
        ])

        assert res.exit_code != 0

    def test_cli_fill_weather_invalid_variable_name_fails_cleanly(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        real_sta, real_dir, fill_sta, fill_dir = self._build_inputs(tmp_path)
        out = tmp_path / "out"
        runner = CliRunner()
        res = runner.invoke(main, [
            "fill", "weather",
            "--stations", str(real_sta), "--data-dir", str(real_dir),
            "--fill-stations", str(fill_sta), "--fill-data-dir", str(fill_dir),
            "--variables", "rainfall",
            "--start", "2000-01-01", "--end", "2000-01-03",
            "--min-overlap-days", "1",
            str(out),
        ])

        assert res.exit_code == 1
        assert res.exception is None or isinstance(res.exception, SystemExit)
        assert "Config schema error" in res.output

    def test_cli_fill_weather_end_before_start_fails_cleanly(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        real_sta, real_dir, fill_sta, fill_dir = self._build_inputs(tmp_path)
        out = tmp_path / "out"
        runner = CliRunner()
        res = runner.invoke(main, [
            "fill", "weather",
            "--stations", str(real_sta), "--data-dir", str(real_dir),
            "--fill-stations", str(fill_sta), "--fill-data-dir", str(fill_dir),
            "--variables", "precip",
            "--start", "2000-01-05", "--end", "2000-01-01",
            "--min-overlap-days", "1",
            str(out),
        ])

        assert res.exit_code == 1
        assert res.exception is None or isinstance(res.exception, SystemExit)
        assert "Config schema error" in res.output
        assert "weather.end must be on or after weather.start" in res.output


# ---------------------------------------------------------------------------
# Virtual (ungauged) stations: no observed day at all
# ---------------------------------------------------------------------------

_DATES = ["2000-01-01", "2000-01-02", "2000-01-03", "2000-01-04"]
_KM_PER_DEG_LON_15N = 107.53   # 111.32 km * cos(15 deg)


def _virtual_setup(tmp_path, km: float, var: str = "precip", v1_file: bool = True):
    """G1 gauged at (15, 105); V1 `km` east of it with no observed value. The fill source
    is 1, 2, 3, 4 at both; G1 observed 2, 4, 6, 8 (ratio 2.0) or 2, 3, 4, 5 (offset +1.0)."""
    from swatprep.config import WeatherConfig

    lon_v1 = 105.0 + km / _KM_PER_DEG_LON_15N
    rows = [{"id": "G1", **_META}, {"id": "V1", **_META, "name": "Virtual", "lon": lon_v1}]
    real_sta = _write_stations_csv(tmp_path, "real_stations.csv", rows)
    fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", rows)
    real_dir, fill_dir = tmp_path / "real", tmp_path / "fill"
    real_dir.mkdir()
    fill_dir.mkdir()
    observed = [2.0, 4.0, 6.0, 8.0] if var == "precip" else [2.0, 3.0, 4.0, 5.0]
    # one missing day at G1 so it is filled too; the overlap is the other three days
    _write_station_csv(real_dir, "G1", _DATES, **{var: [*observed[:3], None]})
    if v1_file:
        _write_station_csv(real_dir, "V1", _DATES, **{var: [None] * 4})
    for sid in ("G1", "V1"):
        _write_station_csv(fill_dir, sid, _DATES, **{var: [1.0, 2.0, 3.0, 4.0]})

    def cfg(sta, d):
        return WeatherConfig(stations=sta, data_dir=d, variables=[var], start=_DATES[0], end=_DATES[-1],
                             missing_policy="warn")
    return cfg(real_sta, real_dir), cfg(fill_sta, fill_dir)


def _row(result, sid, var="precip"):
    rep = result.report
    return rep[(rep["station_id"] == sid) & (rep["variable"] == var)].iloc[0]


class TestVirtualStations:
    def _run(self, tmp_path, km, var="precip", **kw):
        from swatprep.core.weather_fill import WeatherGapFiller

        real_cfg, fill_cfg = _virtual_setup(tmp_path, km, var, kw.pop("v1_file", True))
        return WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1, fill_ungauged=True, **kw).run()

    def test_near_station_borrows_the_precip_ratio(self, tmp_path):
        result = self._run(tmp_path, km=10)
        assert list(result.daily["precip"]["V1"]) == pytest.approx([2.0, 4.0, 6.0, 8.0])
        row = _row(result, "V1")
        assert row["correction_type"] == "ratio"
        assert row["correction_value"] == pytest.approx(2.0)
        assert row["correction_from"] == "G1"
        assert row["distance_km"] == pytest.approx(10.0, abs=0.1)
        assert row["n_filled"] == 4 and row["n_still_missing"] == 0
        assert row["status"] == "warn"
        assert any("V1" in c.message and "G1" in c.message and "km" in c.message for c in result.qa)

    def test_near_station_borrows_the_temperature_offset(self, tmp_path):
        result = self._run(tmp_path, km=10, var="tmax")
        assert list(result.daily["tmax"]["V1"]) == pytest.approx([2.0, 3.0, 4.0, 5.0])
        assert _row(result, "V1", "tmax")["correction_type"] == "offset"

    def test_far_station_gets_raw_source_values(self, tmp_path):
        result = self._run(tmp_path, km=80)
        assert list(result.daily["precip"]["V1"]) == pytest.approx([1.0, 2.0, 3.0, 4.0])
        row = _row(result, "V1")
        assert row["correction_type"] == "none"
        assert pd.isna(row["correction_from"])
        assert any("raw" in c.message and "V1" in c.message for c in result.qa)

    def test_max_borrow_km_is_configurable(self, tmp_path):
        result = self._run(tmp_path, km=80, max_borrow_km=100)
        assert _row(result, "V1")["correction_from"] == "G1"

    def test_correction_off_gives_raw_values_even_when_near(self, tmp_path):
        result = self._run(tmp_path, km=10, correct_ungauged=False)
        assert list(result.daily["precip"]["V1"]) == pytest.approx([1.0, 2.0, 3.0, 4.0])
        assert _row(result, "V1")["correction_type"] == "none"

    def test_station_without_a_data_file_is_filled(self, tmp_path):
        result = self._run(tmp_path, km=10, v1_file=False)
        assert list(result.daily["precip"]["V1"]) == pytest.approx([2.0, 4.0, 6.0, 8.0])

    def test_gauged_station_keeps_its_own_correction(self, tmp_path):
        result = self._run(tmp_path, km=10)
        row = _row(result, "G1")
        assert row["correction_value"] == pytest.approx(2.0)
        assert pd.isna(row["correction_from"])
        assert result.daily["precip"]["G1"].iloc[3] == pytest.approx(8.0)

    def test_flag_off_keeps_the_old_behaviour(self, tmp_path):
        from swatprep.core.weather_fill import WeatherGapFiller

        real_cfg, fill_cfg = _virtual_setup(tmp_path, km=10)
        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()
        assert result.daily["precip"]["V1"].isna().all()
        assert _row(result, "V1")["n_filled"] == 0

    def test_only_a_donor_with_the_same_variable_is_used(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        rows = [{"id": "G1", **_META}, {"id": "V1", **_META, "lon": 105.05}]
        sta = _write_stations_csv(tmp_path, "stations.csv", rows)
        real_dir, fill_dir = tmp_path / "real", tmp_path / "fill"
        real_dir.mkdir()
        fill_dir.mkdir()
        # G1 has temperature only (precip empty): no precip ratio to lend
        _write_station_csv(real_dir, "G1", _DATES, precip=[None] * 4, tmax=[2.0, 3.0, 4.0, None])
        _write_station_csv(real_dir, "V1", _DATES, precip=[None] * 4, tmax=[None] * 4)
        for sid in ("G1", "V1"):
            _write_station_csv(fill_dir, sid, _DATES, precip=[1.0, 2.0, 3.0, 4.0], tmax=[1.0, 2.0, 3.0, 4.0])
        def cfg(d):
            return WeatherConfig(stations=sta, data_dir=d, variables=["precip", "tmax"],
                                 start=_DATES[0], end=_DATES[-1], missing_policy="warn")

        result = WeatherGapFiller(cfg(real_dir), cfg(fill_dir), min_overlap_days=1, fill_ungauged=True).run()

        assert _row(result, "V1", "tmax")["correction_from"] == "G1"
        precip = _row(result, "V1", "precip")
        assert precip["correction_type"] == "none" and pd.isna(precip["correction_from"])
        # G1 has no precip either: it is ungauged for precip and filled the same way
        assert _row(result, "G1", "precip")["correction_type"] == "none"

    def test_report_always_has_the_borrow_columns(self, tmp_path):
        from swatprep.core.weather_fill import WeatherGapFiller

        real_cfg, fill_cfg = _virtual_setup(tmp_path, km=10)
        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()
        assert {"correction_from", "distance_km"} <= set(result.report.columns)


class TestVirtualStationsConfig:
    def test_defaults(self):
        from swatprep.config import WeatherFillConfig

        cfg = WeatherFillConfig(type="csv", csv={"stations": "s.csv", "data_dir": "d"})
        assert (cfg.fill_ungauged, cfg.correct_ungauged, cfg.max_borrow_km) == (False, True, 50)

    def test_max_borrow_km_must_be_positive(self):
        from pydantic import ValidationError

        from swatprep.config import WeatherFillConfig

        with pytest.raises(ValidationError):
            WeatherFillConfig(type="csv", csv={"stations": "s.csv", "data_dir": "d"}, max_borrow_km=0)

    def test_cli_flags_fill_a_virtual_station(self, tmp_path):
        from click.testing import CliRunner

        from swatprep.cli import main

        real_cfg, fill_cfg = _virtual_setup(tmp_path, km=80)
        out = tmp_path / "out"
        base = ["fill", "weather", "--stations", str(real_cfg.stations), "--data-dir", str(real_cfg.data_dir),
                "--fill-stations", str(fill_cfg.stations), "--fill-data-dir", str(fill_cfg.data_dir),
                "--variables", "precip", "--start", _DATES[0], "--end", _DATES[-1], "--min-overlap-days", "1"]
        res = CliRunner().invoke(main, [*base, "--fill-ungauged", "--max-borrow-km", "100", str(out)])
        assert res.exit_code == 0, res.output
        assert list(pd.read_csv(out / "V1.csv")["precip"]) == pytest.approx([2.0, 4.0, 6.0, 8.0])

        res = CliRunner().invoke(main, [*base, "--fill-ungauged", "--no-correct-ungauged", str(out)])
        assert res.exit_code == 0, res.output
        assert list(pd.read_csv(out / "V1.csv")["precip"]) == pytest.approx([1.0, 2.0, 3.0, 4.0])

    def test_yaml_fields_reach_the_filler(self, tmp_path):
        from swatprep.fill_setup import resolve_fill_inputs

        real_cfg, fill_cfg = _virtual_setup(tmp_path, km=10)
        inputs = resolve_fill_inputs({
            "stations": real_cfg.stations, "data_dir": real_cfg.data_dir, "variables": "precip",
            "start": _DATES[0], "end": _DATES[-1], "fill_stations": fill_cfg.stations,
            "fill_data_dir": fill_cfg.data_dir, "out_dir": tmp_path / "out",
            "fill_ungauged": True, "correct_ungauged": False, "max_borrow_km": 20.0,
        })
        assert (inputs.fill_ungauged, inputs.correct_ungauged, inputs.max_borrow_km) == (True, False, 20.0)
