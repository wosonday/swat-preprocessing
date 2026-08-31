"""Tests for swatprep.converters (DayFilesConverter + StreamflowConverter)."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_day_file(path: Path, rows: list) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "value"])
        for row in rows:
            writer.writerow(row)


def _make_climate_dir(tmp_path: Path) -> Path:
    data = tmp_path / "raw_climate"
    data.mkdir()
    dates = ["2000-01-01", "2000-01-02", "2000-01-03"]
    for prefix, vals in [
        ("R_", [1.0, 2.0, 3.0]),
        ("Tx_", [25.0, 26.0, 27.0]),
        ("Tm_", [18.0, 19.0, 20.0]),
    ]:
        for station in ("ALPHA", "BETA"):
            _write_day_file(data / f"{prefix}{station}.day", list(zip(dates, vals)))
    return data


# ---------------------------------------------------------------------------
# DayFilesConverter
# ---------------------------------------------------------------------------


class TestDayFilesConverter:
    def test_discover_two_stations(self, tmp_path):
        from swatprep.converters import DayFilesConverter

        data = _make_climate_dir(tmp_path)
        out = tmp_path / "out_climate"
        result = DayFilesConverter(data_dir=data, out_dir=out).convert()
        assert len(result.stations_found) == 2
        assert result.stations_found == {"ALPHA", "BETA"}

    def test_output_files_created(self, tmp_path):
        from swatprep.converters import DayFilesConverter

        data = _make_climate_dir(tmp_path)
        out = tmp_path / "out_climate"
        result = DayFilesConverter(data_dir=data, out_dir=out).convert()
        assert len(result.files_written) == 2
        names = {p.name for p in result.files_written}
        assert "ALPHA.csv" in names
        assert "BETA.csv" in names

    def test_merged_csv_has_all_columns(self, tmp_path):
        from swatprep.converters import DayFilesConverter

        data = _make_climate_dir(tmp_path)
        out = tmp_path / "out_climate"
        DayFilesConverter(data_dir=data, out_dir=out).convert()
        df = pd.read_csv(out / "ALPHA.csv")
        assert "date" in df.columns
        assert "precip" in df.columns
        assert "tmax" in df.columns
        assert "tmin" in df.columns

    def test_merged_csv_row_count(self, tmp_path):
        from swatprep.converters import DayFilesConverter

        data = _make_climate_dir(tmp_path)
        out = tmp_path / "out_climate"
        DayFilesConverter(data_dir=data, out_dir=out).convert()
        df = pd.read_csv(out / "ALPHA.csv")
        assert len(df) == 3

    def test_no_fail_qa_on_complete_data(self, tmp_path):
        from swatprep.converters import DayFilesConverter
        from swatprep.qa import failures

        data = _make_climate_dir(tmp_path)
        out = tmp_path / "out_climate"
        result = DayFilesConverter(data_dir=data, out_dir=out).convert()
        assert failures(result.qa) == []

    def test_empty_directory_raises(self, tmp_path):
        from swatprep.converters import DayFilesConverter
        from swatprep.errors import InputValidationError

        empty = tmp_path / "empty"
        empty.mkdir()
        out = tmp_path / "out"
        with pytest.raises(InputValidationError):
            DayFilesConverter(data_dir=empty, out_dir=out).convert()

    def test_custom_prefix_mapping(self, tmp_path):
        from swatprep.converters import DayFilesConverter

        data = tmp_path / "custom"
        data.mkdir()
        dates = ["2000-01-01", "2000-01-02"]
        _write_day_file(data / "P_STA1.txt", list(zip(dates, [5.0, 6.0])))
        out = tmp_path / "out"
        converter = DayFilesConverter(
            data_dir=data,
            out_dir=out,
            prefixes={"P_": ("Precip", "precip")},
            suffix=".txt",
        )
        result = converter.convert()
        assert len(result.stations_found) == 1
        df = pd.read_csv(out / "STA1.csv")
        assert "precip" in df.columns

    def test_partial_variables_no_fail(self, tmp_path):
        """Station with only 2 of 3 variables: no fail, tmin column absent."""
        from swatprep.converters import DayFilesConverter
        from swatprep.qa import failures

        data = tmp_path / "partial"
        data.mkdir()
        dates = ["2000-01-01", "2000-01-02"]
        _write_day_file(data / "R_STA.day", list(zip(dates, [1.0, 2.0])))
        _write_day_file(data / "Tx_STA.day", list(zip(dates, [25.0, 26.0])))
        out = tmp_path / "out"
        result = DayFilesConverter(data_dir=data, out_dir=out).convert()
        assert failures(result.qa) == []
        df = pd.read_csv(out / "STA.csv")
        assert "precip" in df.columns
        assert "tmax" in df.columns
        assert "tmin" not in df.columns


# ---------------------------------------------------------------------------
# StreamflowConverter -- wide_yyyymmdd format
# ---------------------------------------------------------------------------


def _make_wide_csv(tmp_path: Path, n_stations: int = 3, n_days: int = 4) -> Path:
    rows = []
    for day_offset in range(n_days):
        date_int = 20000101 + day_offset
        row = {"date": date_int}
        for i in range(1, n_stations + 1):
            row["Q_ST%03d" % i] = float(i * 10 + day_offset)
        rows.append(row)
    # Inject one NA
    rows[1]["Q_ST001"] = "NA"
    df = pd.DataFrame(rows)
    path = tmp_path / "flow_wide.csv"
    df.to_csv(path, index=False)
    return path


class TestStreamflowConverterWide:
    def test_stations_count(self, tmp_path):
        from swatprep.converters import StreamflowConverter

        src = _make_wide_csv(tmp_path, n_stations=3)
        out = tmp_path / "long.csv"
        result = StreamflowConverter(src, input_format="wide_yyyymmdd").convert(out)
        assert result.n_stations == 3

    def test_days_count(self, tmp_path):
        from swatprep.converters import StreamflowConverter

        src = _make_wide_csv(tmp_path, n_stations=3, n_days=4)
        out = tmp_path / "long.csv"
        result = StreamflowConverter(src, input_format="wide_yyyymmdd").convert(out)
        assert result.n_days == 4

    def test_output_file_created(self, tmp_path):
        from swatprep.converters import StreamflowConverter

        src = _make_wide_csv(tmp_path)
        out = tmp_path / "long.csv"
        result = StreamflowConverter(src, input_format="wide_yyyymmdd").convert(out)
        assert result.out_path.exists()

    def test_long_format_columns(self, tmp_path):
        from swatprep.converters import StreamflowConverter

        src = _make_wide_csv(tmp_path)
        out = tmp_path / "long.csv"
        StreamflowConverter(src, input_format="wide_yyyymmdd").convert(out)
        df = pd.read_csv(out)
        assert "date" in df.columns
        assert "station_id" in df.columns
        assert "flow" in df.columns

    def test_no_fail_qa(self, tmp_path):
        from swatprep.converters import StreamflowConverter
        from swatprep.qa import failures

        src = _make_wide_csv(tmp_path)
        out = tmp_path / "long.csv"
        result = StreamflowConverter(src, input_format="wide_yyyymmdd").convert(out)
        assert failures(result.qa) == []

    def test_row_count_equals_stations_x_days(self, tmp_path):
        from swatprep.converters import StreamflowConverter

        src = _make_wide_csv(tmp_path, n_stations=3, n_days=4)
        out = tmp_path / "long.csv"
        StreamflowConverter(src, input_format="wide_yyyymmdd").convert(out)
        df = pd.read_csv(out)
        assert len(df) == 3 * 4

    def test_na_values_preserved_as_nan(self, tmp_path):
        from swatprep.converters import StreamflowConverter

        src = _make_wide_csv(tmp_path, n_stations=3)
        out = tmp_path / "long.csv"
        StreamflowConverter(src, input_format="wide_yyyymmdd").convert(out)
        df = pd.read_csv(out)
        q1_rows = df[df["station_id"] == "Q_ST001"]
        assert q1_rows["flow"].isna().any()


# ---------------------------------------------------------------------------
# StreamflowConverter -- per_station format
# ---------------------------------------------------------------------------


def _make_per_station_dir(tmp_path: Path, n_stations: int = 2, n_days: int = 3) -> Path:
    d = tmp_path / "per_station"
    d.mkdir()
    dates = ["2000-01-%02d" % (day + 1) for day in range(n_days)]
    for i in range(1, n_stations + 1):
        df = pd.DataFrame({"date": dates, "discharge": [float(i) * 10] * n_days})
        df.to_csv(d / ("GAUGE%02d.csv" % i), index=False)
    return d


class TestStreamflowConverterPerStation:
    def test_stations_count(self, tmp_path):
        from swatprep.converters import StreamflowConverter

        src = _make_per_station_dir(tmp_path, n_stations=2)
        out = tmp_path / "long.csv"
        result = StreamflowConverter(
            src, input_format="per_station", glob_pattern="GAUGE*.csv"
        ).convert(out)
        assert result.n_stations == 2

    def test_output_file_created(self, tmp_path):
        from swatprep.converters import StreamflowConverter

        src = _make_per_station_dir(tmp_path)
        out = tmp_path / "long.csv"
        result = StreamflowConverter(
            src, input_format="per_station", glob_pattern="GAUGE*.csv"
        ).convert(out)
        assert result.out_path.exists()

    def test_long_format_columns(self, tmp_path):
        from swatprep.converters import StreamflowConverter

        src = _make_per_station_dir(tmp_path)
        out = tmp_path / "long.csv"
        StreamflowConverter(
            src, input_format="per_station", glob_pattern="GAUGE*.csv"
        ).convert(out)
        df = pd.read_csv(out)
        assert "date" in df.columns
        assert "station_id" in df.columns
        assert "flow" in df.columns

    def test_no_fail_qa(self, tmp_path):
        from swatprep.converters import StreamflowConverter
        from swatprep.qa import failures

        src = _make_per_station_dir(tmp_path)
        out = tmp_path / "long.csv"
        result = StreamflowConverter(
            src, input_format="per_station", glob_pattern="GAUGE*.csv"
        ).convert(out)
        assert failures(result.qa) == []

    def test_station_ids_match_filenames(self, tmp_path):
        from swatprep.converters import StreamflowConverter

        src = _make_per_station_dir(tmp_path, n_stations=2)
        out = tmp_path / "long.csv"
        result = StreamflowConverter(
            src, input_format="per_station", glob_pattern="GAUGE*.csv"
        ).convert(out)
        assert set(result.stations) == {"GAUGE01", "GAUGE02"}

    def test_single_file_per_station_mode(self, tmp_path):
        from swatprep.converters import StreamflowConverter

        dates = ["2000-01-01", "2000-01-02"]
        df = pd.DataFrame({"date": dates, "discharge": [5.0, 6.0]})
        single = tmp_path / "GAUGE01.csv"
        df.to_csv(single, index=False)
        out = tmp_path / "long.csv"
        result = StreamflowConverter(single, input_format="per_station").convert(out)
        assert result.n_stations == 1
        assert result.stations == ["GAUGE01"]


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------


class TestCLIConvert:
    def test_cli_convert_climate_help(self):
        from click.testing import CliRunner
        from swatprep.cli import main

        runner = CliRunner()
        res = runner.invoke(main, ["convert", "climate", "--help"])
        assert res.exit_code == 0
        assert "DATA_DIR" in res.output

    def test_cli_convert_streamflow_help(self):
        from click.testing import CliRunner
        from swatprep.cli import main

        runner = CliRunner()
        res = runner.invoke(main, ["convert", "streamflow", "--help"])
        assert res.exit_code == 0
        assert "SOURCE" in res.output

    def test_python_m_cli_runs(self):
        res = subprocess.run(
            [sys.executable, "-m", "swatprep.cli", "convert", "weather", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        assert res.returncode == 0
        assert "--pcp-master" in res.stdout

    def test_cli_convert_climate_runs(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        data = _make_climate_dir(tmp_path)
        out = tmp_path / "cli_out"
        runner = CliRunner()
        res = runner.invoke(main, ["convert", "climate", str(data), str(out)])
        assert res.exit_code == 0, res.output
        assert "Stations processed" in res.output

    def test_cli_convert_streamflow_wide_runs(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        src = _make_wide_csv(tmp_path)
        out = tmp_path / "long.csv"
        runner = CliRunner()
        res = runner.invoke(
            main,
            ["convert", "streamflow", str(src), str(out),
             "--format", "wide_yyyymmdd"],
        )
        assert res.exit_code == 0, res.output
        assert "Stations" in res.output

    def test_cli_convert_weather_swat2012(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        master = tmp_path / "master_pcp.txt"
        pd.DataFrame([{
            "ID": 1, "NAME": "pcp_ALPHA", "LAT": 13.95, "LONG": 108.65, "ELEVATION": 416,
        }]).to_csv(master, index=False)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        (raw_dir / "pcp_ALPHA.txt").write_text("20000101\n0.0\n0.3\n1.5\n", encoding="utf-8")

        out = tmp_path / "out"
        runner = CliRunner()
        res = runner.invoke(
            main,
            ["convert", "weather", "--pcp-master", str(master), "--pcp-dir", str(raw_dir),
             "--target", "swat2012", str(out)],
        )

        assert res.exit_code == 0, res.output
        assert (out / "pcp_ALPHA.txt").exists()
        assert (out / "master_pcp.txt").exists()

    def test_cli_convert_weather_swatplus(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        master = tmp_path / "master_pcp.txt"
        pd.DataFrame([{
            "ID": 1, "NAME": "pcp_ALPHA", "LAT": 13.95, "LONG": 108.65, "ELEVATION": 416,
        }]).to_csv(master, index=False)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        (raw_dir / "pcp_ALPHA.txt").write_text("20000101\n0.0\n0.3\n1.5\n", encoding="utf-8")

        out = tmp_path / "out"
        runner = CliRunner()
        res = runner.invoke(
            main,
            ["convert", "weather", "--pcp-master", str(master), "--pcp-dir", str(raw_dir),
             "--target", "swatplus", str(out)],
        )

        assert res.exit_code == 0, res.output
        assert (out / "pcp.cli").exists()
        assert (out / "weather-sta.cli").exists()
        assert (out / "weather-wgn.cli").exists()

    def test_cli_convert_weather_both_targets_use_subdirs(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        master = tmp_path / "master_pcp.txt"
        pd.DataFrame([{
            "ID": 1, "NAME": "pcp_ALPHA", "LAT": 13.95, "LONG": 108.65, "ELEVATION": 416,
        }]).to_csv(master, index=False)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        (raw_dir / "pcp_ALPHA.txt").write_text("20000101\n0.0\n0.3\n1.5\n", encoding="utf-8")

        out = tmp_path / "out"
        runner = CliRunner()
        res = runner.invoke(
            main,
            ["convert", "weather", "--pcp-master", str(master), "--pcp-dir", str(raw_dir),
             "--target", "swat2012", "--target", "swatplus", str(out)],
        )

        assert res.exit_code == 0, res.output
        assert (out / "swat2012" / "pcp_ALPHA.txt").exists()
        assert (out / "swatplus" / "pcp.cli").exists()

    def test_cli_convert_weather_requires_one_group(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        runner = CliRunner()
        res = runner.invoke(main, ["convert", "weather", str(tmp_path / "out")])

        assert res.exit_code != 0
