"""Tests for SWATPlusWeatherConverter."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import pytest
from swatprep.converters import SWATPlusWeatherConverter
from swatprep.qa import failures, warnings as qa_warnings


def _make_master(tmp_path, stations):
    df = pd.DataFrame(stations)
    p = tmp_path / "master.txt"
    df.to_csv(p, index=False)
    return p


def _make_station_csv(data_dir, station, n_days=5, start="2000-01-01",
                      cols=("precip", "tmax", "tmin")):
    dates = pd.date_range(start=start, periods=n_days, freq="D").strftime("%Y-%m-%d")
    data = {"date": list(dates)}
    for col in cols:
        data[col] = [float(i + 1) for i in range(n_days)]
    pd.DataFrame(data).to_csv(data_dir / f"{station}.csv", index=False)


_META = [
    {"ID": 1, "NAME": "pcp_ALPHA", "LAT": 13.95, "LONG": 108.65, "ELEVATION": 416},
    {"ID": 2, "NAME": "pcp_BETA",  "LAT": 14.65, "LONG": 107.83, "ELEVATION": 616},
]


class TestSWATPlusWeatherConverter:
    def test_pcp_file_created(self, tmp_path):
        master = _make_master(tmp_path, [_META[0]])
        data = tmp_path / "data"; data.mkdir()
        _make_station_csv(data, "ALPHA")
        result = SWATPlusWeatherConverter(data, tmp_path / "out", master).convert()
        assert "alpha.pcp" in {p.name for p in result.data_files}

    def test_tem_file_created(self, tmp_path):
        master = _make_master(tmp_path, [_META[0]])
        data = tmp_path / "data"; data.mkdir()
        _make_station_csv(data, "ALPHA")
        result = SWATPlusWeatherConverter(data, tmp_path / "out", master).convert()
        assert "alpha.tmp" in {p.name for p in result.data_files}

    def test_no_tem_without_tmin(self, tmp_path):
        master = _make_master(tmp_path, [_META[0]])
        data = tmp_path / "data"; data.mkdir()
        _make_station_csv(data, "ALPHA", cols=("precip", "tmax"))
        result = SWATPlusWeatherConverter(data, tmp_path / "out", master).convert()
        assert "alpha.tmp" not in {p.name for p in result.data_files}

    def test_cli_files_written(self, tmp_path):
        master = _make_master(tmp_path, _META)
        data = tmp_path / "data"; data.mkdir()
        for s in ("ALPHA", "BETA"):
            _make_station_csv(data, s)
        result = SWATPlusWeatherConverter(data, tmp_path / "out", master).convert()
        cli_names = {p.name for p in result.cli_files}
        assert "pcp.cli" in cli_names and "tmp.cli" in cli_names

    def test_pcp_header_line2(self, tmp_path):
        master = _make_master(tmp_path, [_META[0]])
        data = tmp_path / "data"; data.mkdir()
        _make_station_csv(data, "ALPHA")
        out = tmp_path / "out"
        SWATPlusWeatherConverter(data, out, master).convert()
        lines = (out / "alpha.pcp").read_text().splitlines()
        assert lines[1] == "nbyr     tstep       lat       lon      elev"
        assert "13.950" in lines[2]
        assert "108.650" in lines[2]
        assert "416.000" in lines[2]

    def test_pcp_data_row_width(self, tmp_path):
        master = _make_master(tmp_path, [_META[0]])
        data = tmp_path / "data"; data.mkdir()
        _make_station_csv(data, "ALPHA", n_days=1, cols=("precip",))
        out = tmp_path / "out"
        SWATPlusWeatherConverter(data, out, master).convert()
        lines = (out / "alpha.pcp").read_text().splitlines()
        assert lines[3][:4] == "2000"
        assert lines[3][4:9] == "    1"
        assert len(lines[3]) == 22

    def test_tem_two_col_exact_format(self, tmp_path):
        master = _make_master(tmp_path, [_META[0]])
        data = tmp_path / "data"; data.mkdir()
        df = pd.DataFrame({"date": ["2000-01-01"], "tmax": [25.0], "tmin": [9.0]})
        df.to_csv(data / "ALPHA.csv", index=False)
        out = tmp_path / "out"
        SWATPlusWeatherConverter(data, out, master).convert()
        lines = (out / "alpha.tmp").read_text().splitlines()
        assert lines[3] == "2000    1   25.00000     9.00000  "

    def test_cli_lists_filenames(self, tmp_path):
        master = _make_master(tmp_path, _META)
        data = tmp_path / "data"; data.mkdir()
        for s in ("ALPHA", "BETA"):
            _make_station_csv(data, s, cols=("precip",))
        out = tmp_path / "out"
        SWATPlusWeatherConverter(data, out, master).convert()
        cli_lines = (out / "pcp.cli").read_text().splitlines()
        assert cli_lines[1] == "filename"
        assert "alpha.pcp" in cli_lines and "beta.pcp" in cli_lines

    def test_missing_csv_is_warn(self, tmp_path):
        master = _make_master(tmp_path, _META)
        data = tmp_path / "data"; data.mkdir()
        _make_station_csv(data, "ALPHA")
        result = SWATPlusWeatherConverter(data, tmp_path / "out", master).convert()
        assert failures(result.qa) == []

    def test_no_fail_qa(self, tmp_path):
        master = _make_master(tmp_path, _META)
        data = tmp_path / "data"; data.mkdir()
        for s in ("ALPHA", "BETA"):
            _make_station_csv(data, s)
        result = SWATPlusWeatherConverter(data, tmp_path / "out", master).convert()
        assert failures(result.qa) == []

    def test_doy_feb1_leap(self, tmp_path):
        master = _make_master(tmp_path, [_META[0]])
        data = tmp_path / "data"; data.mkdir()
        df = pd.DataFrame({"date": ["2000-02-01"], "precip": [5.0]})
        df.to_csv(data / "ALPHA.csv", index=False)
        out = tmp_path / "out"
        SWATPlusWeatherConverter(data, out, master).convert()
        lines = (out / "alpha.pcp").read_text().splitlines()
        assert lines[3][4:9] == "   32"

    def test_nan_nodata(self, tmp_path):
        master = _make_master(tmp_path, [_META[0]])
        data = tmp_path / "data"; data.mkdir()
        df = pd.DataFrame({"date": ["2000-01-01", "2000-01-02"], "precip": [5.0, float("nan")]})
        df.to_csv(data / "ALPHA.csv", index=False)
        out = tmp_path / "out"
        SWATPlusWeatherConverter(data, out, master, no_data_value=-99.0).convert()
        lines = (out / "alpha.pcp").read_text().splitlines()
        assert "  -99.00000" in lines[4]

    def test_negative_precip_warn(self, tmp_path):
        master = _make_master(tmp_path, [_META[0]])
        data = tmp_path / "data"; data.mkdir()
        df = pd.DataFrame({"date": ["2000-01-01", "2000-01-02"], "precip": [5.0, -1.0]})
        df.to_csv(data / "ALPHA.csv", index=False)
        result = SWATPlusWeatherConverter(data, tmp_path / "out", master).convert()
        assert any("negative" in c.message for c in qa_warnings(result.qa))

    def test_tmax_lt_tmin_warn(self, tmp_path):
        master = _make_master(tmp_path, [_META[0]])
        data = tmp_path / "data"; data.mkdir()
        df = pd.DataFrame({"date": ["2000-01-01"], "tmax": [15.0], "tmin": [25.0]})
        df.to_csv(data / "ALPHA.csv", index=False)
        result = SWATPlusWeatherConverter(data, tmp_path / "out", master).convert()
        assert any("tmax < tmin" in c.message for c in qa_warnings(result.qa))


class TestSWATPlusLive:
    UPLOADS = Path("/sessions/example-session/mnt/uploads")

    def test_live_pcp_header_and_format(self, tmp_path):
        try:
            if not (self.UPLOADS / "master_pcp.txt").exists():
                pytest.skip("Upload files not available")
        except (PermissionError, OSError):
            pytest.skip("Upload directory not accessible in this session")
        r = pd.read_csv(self.UPLOADS / "R_STATION01.day")
        r.columns = ["date", "precip"]
        data_dir = tmp_path / "data"; data_dir.mkdir()
        r.to_csv(data_dir / "STATION01.csv", index=False)
        master_df = pd.read_csv(self.UPLOADS / "master_pcp.txt")
        station01 = master_df[master_df["NAME"] == "pcp_STATION01"]
        station01.to_csv(tmp_path / "master.txt", index=False)
        out = tmp_path / "out"
        result = SWATPlusWeatherConverter(data_dir, out, tmp_path / "master.txt").convert()
        assert failures(result.qa) == []
        lines = (out / "station01.pcp").read_text().splitlines()
        assert lines[1] == "nbyr     tstep       lat       lon      elev"
        assert "13.950" in lines[2]
        assert lines[3][:4] == "1977"
        for line in lines[3:23]:
            assert len(line) == 22, f"Bad width: {repr(line)}"
