"""Tests for PCPConverter (swatprep/converters/swat2012_input.py)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_master(tmp_path: Path, stations: list[dict]) -> Path:
    """Write a master_pcp.txt CSV."""
    df = pd.DataFrame(stations)
    p = tmp_path / "master_pcp.txt"
    df.to_csv(p, index=False)
    return p


def _make_day_file(tmp_path: Path, station: str, n_days: int = 5,
                   value: float = 2.5, start: str = "1990-01-01") -> Path:
    """Create a per-station raw CSV file using the default naming: R_{station}.day."""
    dates = pd.date_range(start=start, periods=n_days, freq="D").strftime("%Y-%m-%d")
    df = pd.DataFrame({"date": dates, "Rain": [value] * n_days})
    p = tmp_path / f"R_{station}.day"
    df.to_csv(p, index=False)
    return p


_STATIONS = [
    {"ID": 1, "NAME": "pcp_ALPHA", "LAT": 13.95, "LONG": 108.65, "ELEVATION": 416},
    {"ID": 2, "NAME": "pcp_BETA",  "LAT": 14.65, "LONG": 107.83, "ELEVATION": 616},
]


# ---------------------------------------------------------------------------
# PCPConverter
# ---------------------------------------------------------------------------


class TestPCPConverter:
    def test_two_stations_written(self, tmp_path):
        from swatprep.converters import PCPConverter

        master = _make_master(tmp_path, _STATIONS)
        _make_day_file(tmp_path, "ALPHA")
        _make_day_file(tmp_path, "BETA")
        result = PCPConverter(master, tmp_path, tmp_path / "out").convert()
        assert len(result.files_written) == 2

    def test_output_filenames(self, tmp_path):
        from swatprep.converters import PCPConverter

        master = _make_master(tmp_path, _STATIONS)
        _make_day_file(tmp_path, "ALPHA")
        _make_day_file(tmp_path, "BETA")
        result = PCPConverter(master, tmp_path, tmp_path / "out").convert()
        names = {p.name for p in result.files_written}
        assert "pcp_ALPHA.pcp" in names
        assert "pcp_BETA.pcp" in names

    def test_header_lines(self, tmp_path):
        """Output must have 4-line SWAT header: title / Lati / Long / Elev."""
        from swatprep.converters import PCPConverter

        master = _make_master(tmp_path, [_STATIONS[0]])
        _make_day_file(tmp_path, "ALPHA", n_days=3)
        out = tmp_path / "out"
        PCPConverter(master, tmp_path, out).convert()

        lines = (out / "pcp_ALPHA.pcp").read_text().splitlines()
        assert lines[0] == "pcp_ALPHA"
        assert lines[1].startswith("Lati")
        assert "13.950" in lines[1]
        assert lines[2].startswith("Long")
        assert "108.650" in lines[2]
        assert lines[3].startswith("Elev")
        assert "416.000" in lines[3]

    def test_date_line(self, tmp_path):
        """Line 5 must be YYYYMMDD of the first data entry."""
        from swatprep.converters import PCPConverter

        master = _make_master(tmp_path, [_STATIONS[0]])
        _make_day_file(tmp_path, "ALPHA", start="1990-03-15")
        out = tmp_path / "out"
        PCPConverter(master, tmp_path, out).convert()
        lines = (out / "pcp_ALPHA.pcp").read_text().splitlines()
        assert lines[4] == "19900315"

    def test_value_format(self, tmp_path):
        """Daily values must be 10-wide, 3 decimal places."""
        from swatprep.converters import PCPConverter

        master = _make_master(tmp_path, [_STATIONS[0]])
        _make_day_file(tmp_path, "ALPHA", n_days=1, value=5.5)
        out = tmp_path / "out"
        PCPConverter(master, tmp_path, out).convert()
        lines = (out / "pcp_ALPHA.pcp").read_text().splitlines()
        val_line = lines[5]
        assert val_line == "     5.500"
        assert len(val_line) == 10

    def test_day_count(self, tmp_path):
        from swatprep.converters import PCPConverter

        master = _make_master(tmp_path, [_STATIONS[0]])
        _make_day_file(tmp_path, "ALPHA", n_days=10)
        out = tmp_path / "out"
        result = PCPConverter(master, tmp_path, out).convert()
        assert result.stations[0].n_days == 10

    def test_no_fail_qa_all_matched(self, tmp_path):
        from swatprep.converters import PCPConverter
        from swatprep.qa import failures

        master = _make_master(tmp_path, _STATIONS)
        _make_day_file(tmp_path, "ALPHA")
        _make_day_file(tmp_path, "BETA")
        result = PCPConverter(master, tmp_path, tmp_path / "out").convert()
        assert failures(result.qa) == []
        assert result.unmatched == []

    def test_unmatched_station_is_warn(self, tmp_path):
        """Station in master with no .day file -> warn, not fail."""
        from swatprep.converters import PCPConverter
        from swatprep.qa import failures, warnings

        master = _make_master(tmp_path, _STATIONS)
        _make_day_file(tmp_path, "ALPHA")
        # BETA has no raw file
        result = PCPConverter(master, tmp_path, tmp_path / "out").convert()
        assert failures(result.qa) == []
        assert "pcp_BETA" in result.unmatched
        assert len(result.files_written) == 1

    def test_missing_master_raises(self, tmp_path):
        from swatprep.converters import PCPConverter
        from swatprep.errors import InputValidationError

        result_raises = False
        try:
            PCPConverter(tmp_path / "nonexistent.txt", tmp_path, tmp_path / "out").convert()
        except InputValidationError:
            result_raises = True
        assert result_raises

    def test_custom_out_suffix(self, tmp_path):
        from swatprep.converters import PCPConverter

        master = _make_master(tmp_path, [_STATIONS[0]])
        _make_day_file(tmp_path, "ALPHA")
        out = tmp_path / "out"
        PCPConverter(master, tmp_path, out, out_suffix=".txt").convert()
        assert (out / "pcp_ALPHA.txt").exists()

    def test_nan_replaced_by_nodata(self, tmp_path):
        from swatprep.converters import PCPConverter

        master = _make_master(tmp_path, [_STATIONS[0]])
        # Write raw file with NaN using default naming convention
        df = pd.DataFrame({
            "date": ["1990-01-01", "1990-01-02"],
            "Rain": [5.0, float("nan")],
        })
        df.to_csv(tmp_path / "R_ALPHA.day", index=False)
        out = tmp_path / "out"
        PCPConverter(master, tmp_path, out, no_data_value=-99.0).convert()
        lines = (out / "pcp_ALPHA.pcp").read_text().splitlines()
        assert "   -99.000" in lines


# ---------------------------------------------------------------------------
# Live test with uploaded sample data
# ---------------------------------------------------------------------------


class TestPCPConverterLiveData:
    """Integration tests against the actual uploaded ANKHE sample."""

    UPLOADS = Path("/sessions/gracious-focused-allen/mnt/uploads")

    def test_live_ankhe(self, tmp_path):
        """Convert R_ANKHE.day + master_pcp.txt -> valid pcp_ANKHE.pcp."""
        from swatprep.converters import PCPConverter

        try:
            if not (self.UPLOADS / "master_pcp.txt").exists():
                pytest.skip("Uploaded files not available")
        except (PermissionError, OSError):
            pytest.skip("Upload directory not accessible in this session")

        # Use only ANKHE row from master
        master_df = pd.read_csv(self.UPLOADS / "master_pcp.txt")
        ankhe = master_df[master_df["NAME"] == "pcp_ANKHE"]
        ankhe_master = tmp_path / "master.txt"
        ankhe.to_csv(ankhe_master, index=False)

        result = PCPConverter(
            master_path=ankhe_master,
            data_dir=self.UPLOADS,
            out_dir=tmp_path / "out",
        ).convert()

        assert len(result.files_written) == 1
        lines = result.files_written[0].read_text().splitlines()
        assert lines[0] == "pcp_ANKHE"
        assert "13.950" in lines[1]
        assert "108.650" in lines[2]
        assert "416.000" in lines[3]
        assert lines[4] == "19770101"
        # 15705 data rows in pcp_ANKHE.txt (from wc -l = 15706 incl. header line)
        assert len(lines) == 5 + 15705  # header(5) + data rows

    def test_live_value_precision(self, tmp_path):
        """Each value line must be exactly 10 chars wide."""
        from swatprep.converters import PCPConverter

        try:
            if not (self.UPLOADS / "master_pcp.txt").exists():
                pytest.skip("Uploaded files not available")
        except (PermissionError, OSError):
            pytest.skip("Upload directory not accessible in this session")

        master_df = pd.read_csv(self.UPLOADS / "master_pcp.txt")
        ankhe = master_df[master_df["NAME"] == "pcp_ANKHE"]
        ankhe_master = tmp_path / "master.txt"
    