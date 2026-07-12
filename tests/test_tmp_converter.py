"""Tests for TmpConverter (swatprep/converters/swat2012_input.py)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from swatprep.converters import TmpConverter
from swatprep.qa import failures


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_master(tmp_path: Path, stations: list[dict]) -> Path:
    p = tmp_path / "master_tmp.txt"
    pd.DataFrame(stations).to_csv(p, index=False)
    return p


def _make_csv(tmp_path: Path, station: str,
              n_days: int = 5, tmax: float = 30.0, tmin: float = 20.0,
              start: str = "1990-01-01") -> Path:
    dates = pd.date_range(start, periods=n_days, freq="D").strftime("%Y-%m-%d")
    df = pd.DataFrame({"date": list(dates), "tmax": [tmax] * n_days, "tmin": [tmin] * n_days})
    p = tmp_path / f"tmp_{station}.txt"
    df.to_csv(p, index=False)
    return p


def _make_swat_classic(tmp_path: Path, station: str,
                       pairs: list[tuple[float, float]],
                       start: str = "1990-01-01",
                       tmin_first: bool = True) -> Path:
    """Write SWAT Classic temp file (line 0 = YYYYMMDD, rest = val1,val2)."""
    header = pd.Timestamp(start).strftime("%Y%m%d")
    if tmin_first:
        lines = [f"{tn},{tx}" for tx, tn in pairs]
    else:
        lines = [f"{tx},{tn}" for tx, tn in pairs]
    content = "\n".join([header] + lines) + "\n"
    p = tmp_path / f"tmp_{station}.txt"
    p.write_text(content)
    return p


_STATIONS = [
    {"ID": 1, "NAME": "tmp_ALPHA", "LAT": 13.95, "LONG": 108.65, "ELEVATION": 416},
    {"ID": 2, "NAME": "tmp_BETA",  "LAT": 14.65, "LONG": 107.83, "ELEVATION": 616},
]


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestTmpConverter:
    def test_two_stations_written(self, tmp_path):
        master = _make_master(tmp_path, _STATIONS)
        _make_csv(tmp_path, "ALPHA")
        _make_csv(tmp_path, "BETA")
        result = TmpConverter(master, tmp_path, tmp_path / "out").convert()
        assert len(result.files_written) == 2

    def test_output_filenames(self, tmp_path):
        master = _make_master(tmp_path, _STATIONS)
        _make_csv(tmp_path, "ALPHA")
        _make_csv(tmp_path, "BETA")
        result = TmpConverter(master, tmp_path, tmp_path / "out").convert()
        names = {p.name for p in result.files_written}
        assert "tmp_ALPHA.tmp" in names
        assert "tmp_BETA.tmp" in names

    def test_header_lines(self, tmp_path):
        """Output must have 4-line SWAT header: title / Lati / Long / Elev."""
        master = _make_master(tmp_path, [_STATIONS[0]])
        _make_csv(tmp_path, "ALPHA", n_days=3)
        out = tmp_path / "out"
        TmpConverter(master, tmp_path, out).convert()
        lines = (out / "tmp_ALPHA.tmp").read_text().splitlines()
        assert lines[0] == "tmp_ALPHA"
        assert lines[1].startswith("Lati")
        assert "13.950" in lines[1]
        assert lines[2].startswith("Long")
        assert "108.650" in lines[2]
        assert lines[3].startswith("Elev")
        assert "416.000" in lines[3]

    def test_date_line(self, tmp_path):
        """Line 5 (index 4) must be YYYYMMDD start date."""
        master = _make_master(tmp_path, [_STATIONS[0]])
        _make_csv(tmp_path, "ALPHA", start="1995-06-15")
        out = tmp_path / "out"
        TmpConverter(master, tmp_path, out).convert()
        lines = (out / "tmp_ALPHA.tmp").read_text().splitlines()
        assert lines[4] == "19950615"

    def test_value_format(self, tmp_path):
        """Daily values: tmax and tmin each formatted as %10.3f on same line."""
        master = _make_master(tmp_path, [_STATIONS[0]])
        _make_csv(tmp_path, "ALPHA", n_days=1, tmax=32.5, tmin=18.0)
        out = tmp_path / "out"
        TmpConverter(master, tmp_path, out).convert()
        lines = (out / "tmp_ALPHA.tmp").read_text().splitlines()
        val_line = lines[5]
        assert val_line == "    32.500    18.000"
        assert len(val_line) == 20   # 2 × 10 chars

    def test_tmin_first_true(self, tmp_path):
        """SWAT Classic: tmin_first=True means col0=tmin, col1=tmax."""
        master = _make_master(tmp_path, [_STATIONS[0]])
        # Write file where col0=tmin(10), col1=tmax(35)
        _make_swat_classic(tmp_path, "ALPHA", [(35.0, 10.0)],
                           tmin_first=True)
        out = tmp_path / "out"
        TmpConverter(master, tmp_path, out, tmin_first=True).convert()
        lines = (out / "tmp_ALPHA.tmp").read_text().splitlines()
        # Output must be tmax=35 then tmin=10
        assert "35.000" in lines[5]
        assert "10.000" in lines[5]
        assert lines[5].index("35.000") < lines[5].index("10.000")

    def test_tmin_first_false(self, tmp_path):
        """SWAT Classic: tmin_first=False means col0=tmax, col1=tmin."""
        master = _make_master(tmp_path, [_STATIONS[0]])
        # Write file where col0=tmax(35), col1=tmin(10)
        _make_swat_classic(tmp_path, "ALPHA", [(35.0, 10.0)],
                           tmin_first=False)
        out = tmp_path / "out"
        TmpConverter(master, tmp_path, out, tmin_first=False).convert()
        lines = (out / "tmp_ALPHA.tmp").read_text().splitlines()
        assert "35.000" in lines[5]
        assert "10.000" in lines[5]
        assert lines[5].index("35.000") < lines[5].index("10.000")

    def test_csv_input(self, tmp_path):
        """Accepts CSV with date, tmax, tmin columns."""
        master = _make_master(tmp_path, [_STATIONS[0]])
        df = pd.DataFrame({
            "date": ["1990-03-01", "1990-03-02"],
            "tmax": [28.0, 29.0],
            "tmin": [15.0, 16.0],
        })
        df.to_csv(tmp_path / "tmp_ALPHA.txt", index=False)
        out = tmp_path / "out"
        result = TmpConverter(master, tmp_path, out).convert()
        assert len(result.files_written) == 1
        lines = (out / "tmp_ALPHA.tmp").read_text().splitlines()
        assert len(lines) == 7   # header(4) + date(1) + 2 data rows

    def test_nan_replaced_by_nodata(self, tmp_path):
        """NaN values must be replaced by no_data_value (-99.0)."""
        master = _make_master(tmp_path, [_STATIONS[0]])
        df = pd.DataFrame({
            "date": ["1990-01-01", "1990-01-02"],
            "tmax": [30.0, float("nan")],
            "tmin": [18.0, float("nan")],
        })
        df.to_csv(tmp_path / "tmp_ALPHA.txt", index=False)
        out = tmp_path / "out"
        TmpConverter(master, tmp_path, out, no_data_value=-99.0).convert()
        lines = (out / "tmp_ALPHA.tmp").read_text().splitlines()
        assert "   -99.000" in lines[6]

    def test_no_fail_qa_all_matched(self, tmp_path):
        master = _make_master(tmp_path, _STATIONS)
        _make_csv(tmp_path, "ALPHA")
        _make_csv(tmp_path, "BETA")
        result = TmpConverter(master, tmp_path, tmp_path / "out").convert()
        assert failures(result.qa) == []
        assert result.unmatched == []

    def test_unmatched_station_is_warn(self, tmp_path):
        """Station in master with no raw file → warn, not fail, not counted."""
        master = _make_master(tmp_path, _STATIONS)
        _make_csv(tmp_path, "ALPHA")  # BETA has no file
        result = TmpConverter(master, tmp_path, tmp_path / "out").convert()
        assert failures(result.qa) == []
        assert "tmp_BETA" in result.unmatched
        assert len(result.files_written) == 1

    def test_day_count(self, tmp_path):
        master = _make_master(tmp_path, [_STATIONS[0]])
        _make_csv(tmp_path, "ALPHA", n_days=7)
        result = TmpConverter(master, tmp_path, tmp_path / "out").convert()
        assert result.stations[0].n_days == 7

    def test_missing_master_raises(self, tmp_path):
        from swatprep.errors import InputValidationError
        raised = False
        try:
            TmpConverter(tmp_path / "no.txt", tmp_path, tmp_path / "out").convert()
        except InputValidationError:
            raised = True
        assert raised


# ---------------------------------------------------------------------------
# Live test
# ---------------------------------------------------------------------------


class TestTmpConverterLive:
    UPLOADS = Path("/sessions/gracious-focused-allen/mnt/uploads")

    def test_live_ankhe(self, tmp_path):
        try:
            if not (self.UPLOADS / "master_tmp.txt").exists():
                pytest.skip("Upload files not available")
        except (PermissionError, OSError):
            pytest.skip("Upload directory not accessible in this session")

        master_df = pd.read_csv(self.UPLOADS / "master_tmp.txt")
        ankhe = master_df[master_df["NAME"] == "tmp_ANKHE"]
        ankhe.to_csv(tmp_path / "master.txt", index=False)

        result = TmpConverter(
            master_path=tmp_path / "master.txt",
            data_dir=self.UPLOADS,
            out_dir=tmp_path / "out",
        ).convert()

        assert len(result.files_written) == 1
        lines = result.files_written[0].read_text().splitlines()
        assert lines[0] == "tmp_ANKHE"
        assert "13.950" in lines[1]
        # Each value line must be exactly 20 chars (2 × 10)
        for line in lines[5:25]:
            assert len(line) == 20, f"Bad width: {repr(line)}"
