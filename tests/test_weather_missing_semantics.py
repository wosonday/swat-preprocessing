"""Khoá hành vi 'thiếu số liệu' và 'fill' được mô tả trong docs/WEATHER_MISSING_FILL_VI.md."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from swatprep.api import SWATPrepProject
from swatprep.config import SWATPrepConfig, WeatherConfig
from swatprep.core.weather import WeatherPreprocessor
from swatprep.core.weather_fill import WeatherGapFiller
from swatprep.writers.weather_fill import WeatherFillWriter

D = pd.date_range("2000-01-01", "2000-01-10")
STA = {"id": "S1", "name": "Sta1", "lat": 15.0, "lon": 105.0, "elev": 100}
NAN = np.nan
OBS_P = [2, 4, NAN, 6, NAN, 0, 8, NAN, 10, 0]            # ngày 3, 5, 8 thiếu
OBS_TX = [30, 31, NAN, 29, 30, 31, 32, NAN, 30, 29]       # ngày 3, 8 thiếu
FIL_P = [1, 3, 5, 3, 4, 0, 4, NAN, 5, 0]                  # ngày 8 cũng thiếu ở nguồn điền
FIL_TX = [28, 29, 29, 27, 28, 29, 30, 31, 28, 27]


def _station_dir(base, name, **cols):
    d = base / name
    d.mkdir()
    pd.DataFrame({"date": D.strftime("%Y-%m-%d"), **cols}).to_csv(d / "S1.csv", index=False)
    pd.DataFrame([STA]).to_csv(d / "stations.csv", index=False)
    return d


def _cfg(d, policy="warn", end="2000-01-10", variables=("precip", "tmax")):
    return WeatherConfig(stations=d / "stations.csv", data_dir=d, variables=list(variables),
                         start="2000-01-01", end=end, missing_policy=policy)


@pytest.fixture
def dirs(tmp_dir):
    return (_station_dir(tmp_dir, "obs", precip=OBS_P, tmax=OBS_TX),
            _station_dir(tmp_dir, "grid", precip=FIL_P, tmax=FIL_TX))


def test_blank_and_absent_rows_both_count_as_missing(tmp_dir):
    d = _station_dir(tmp_dir, "obs", precip=OBS_P, tmax=OBS_TX)
    df = pd.read_csv(d / "S1.csv")
    df.drop(index=[0]).to_csv(d / "S1.csv", index=False)         # ngày 1: không có hàng
    res = WeatherPreprocessor(_cfg(d)).run()
    p = res.daily["precip"]["S1"]
    assert p.isna().sum() == 4                                   # ngày 1, 3, 5, 8
    assert [c.status for c in res.qa if c.name == "missing:S1:precip"] == ["warn"]


def test_missing_policy_fail_vs_warn(dirs):
    obs, _ = dirs
    st = lambda p: next(c.status for c in WeatherPreprocessor(_cfg(obs, p)).run().qa
                        if c.name == "missing:S1:precip")
    assert st("fail") == "fail" and st("warn") == "warn"


def test_build_writes_minus_99_for_missing_days(tmp_dir, dirs):
    obs, _ = dirs
    cfg = SWATPrepConfig.model_validate({
        "project": {"name": "t", "crs": "EPSG:32648", "output_dir": str(tmp_dir / "out"),
                    "targets": ["swat"]},
        "weather": {"stations": str(obs / "stations.csv"), "data_dir": str(obs),
                    "variables": ["precip", "tmax"], "start": "2000-01-01", "end": "2000-01-10",
                    "missing_policy": "warn"}})
    SWATPrepProject(cfg).build()
    lines = (tmp_dir / "out" / "weather" / "pcp_Sta1.txt").read_text().split()
    assert lines[0] == "20000101" and lines[3] == "-99.0"        # ngày 3 thiếu -> -99


def test_fill_worked_example(dirs, tmp_dir):
    obs, grid = dirs
    res = WeatherGapFiller(_cfg(obs), _cfg(grid), min_overlap_days=3).run()
    p, t = res.daily["precip"]["S1"], res.daily["tmax"]["S1"]
    # mưa: hệ số = tổng(đo)/tổng(lưới) trên 7 ngày trùng = 30/16 = 1.875
    assert p.iloc[2] == pytest.approx(5 * 1.875) and p.iloc[4] == pytest.approx(4 * 1.875)
    assert np.isnan(p.iloc[7])                                   # nguồn điền cũng thiếu
    assert list(p.iloc[[0, 1, 3, 5, 6, 8, 9]]) == [OBS_P[i] for i in (0, 1, 3, 5, 6, 8, 9)]
    # nhiệt độ: độ lệch = 30.25 - 28.25 = 2.0 trên 8 ngày trùng
    assert t.iloc[2] == pytest.approx(29 + 2.0) and t.iloc[7] == pytest.approx(31 + 2.0)
    row = res.report.query("variable == 'precip'").iloc[0]
    assert (row.n_missing, row.n_filled, row.n_still_missing, row.n_overlap) == (3, 2, 1, 7)
    assert row.correction_type == "ratio" and row.correction_value == pytest.approx(1.875)


def test_low_overlap_warns_but_still_fills(dirs):
    obs, grid = dirs
    res = WeatherGapFiller(_cfg(obs), _cfg(grid), min_overlap_days=30).run()
    assert any(c.name == "weather_fill:precip:S1:low_confidence" for c in res.qa)
    assert res.daily["precip"]["S1"].iloc[2] == pytest.approx(9.375)


def test_fill_ignores_missing_policy_fail(dirs):
    """Với missing_policy: fail, build dừng nhưng fill vẫn chạy (lỗi thiếu hạ xuống cảnh báo)."""
    obs, grid = dirs
    res = WeatherGapFiller(_cfg(obs, "fail"), _cfg(grid, "fail"), min_overlap_days=3).run()
    assert not any(c.status == "fail" for c in res.qa)


def test_fill_output_covers_only_start_end_and_keeps_blanks(dirs, tmp_dir):
    obs, grid = dirs
    res = WeatherGapFiller(_cfg(obs, end="2000-01-08"), _cfg(grid, end="2000-01-08"),
                           min_overlap_days=3).run()
    out = tmp_dir / "filled"
    WeatherFillWriter(res, out).write()
    df = pd.read_csv(out / "S1.csv")
    assert df["date"].iloc[0] == "2000-01-01" and df["date"].iloc[-1] == "2000-01-08"
    assert len(df) == 8                                          # không có ngày 9, 10
    assert df["precip"].isna().sum() == 1                        # ngày 8 vẫn trống
    assert (out / "fill_report.csv").exists()


def test_minus_99_in_csv_is_a_real_value_not_missing(tmp_dir):
    d = _station_dir(tmp_dir, "obs", precip=[1, -99, 3, 4, 5, 6, 7, 8, 9, 10], tmax=OBS_TX)
    res = WeatherPreprocessor(_cfg(d, variables=("precip",))).run()
    assert res.daily["precip"]["S1"].iloc[1] == -99
    assert not any(c.name == "missing:S1:precip" for c in res.qa)


def test_no_files_error_names_the_file_it_looked_for_and_hints_file_pattern(tmp_dir):
    from swatprep.errors import InputValidationError
    d = tmp_dir / "obs"; d.mkdir()
    pd.DataFrame([{"id": 1, "name": "CHILINH", "lat": 21.0, "lon": 106.0, "elev": 5}]) \
        .to_csv(d / "stations.csv", index=False)
    pd.DataFrame({"date": ["2000-01-01"], "precip": [1.0]}).to_csv(d / "CHILINH.csv", index=False)
    with pytest.raises(InputValidationError) as e:
        WeatherPreprocessor(_cfg(d, variables=("precip",), end="2000-01-01")).run()
    msg = str(e.value)
    assert "'1.csv'" in msg and '{name}.csv' in msg and str(d) in msg
