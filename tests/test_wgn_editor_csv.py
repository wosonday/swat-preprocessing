"""CSV files for SWAT+ Editor > Weather generator > Import (two-file and one-file formats)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from swatprep.core.weather import WeatherResult
from swatprep.writers.weather_plus import SWATPlusWeatherWriter, _WGN_COLUMN_MAP

TWO_FILE_MONTHLY = ["id", "wgn_id", "month", "tmp_max_ave", "tmp_min_ave", "tmp_max_sd", "tmp_min_sd",
                    "pcp_ave", "pcp_sd", "pcp_skew", "wet_dry", "wet_wet", "pcp_days", "pcp_hhr",
                    "slr_ave", "dew_ave", "wnd_ave"]


def _write(tmp_path):
    idx = pd.date_range("2000-01-01", "2002-12-31")
    daily = {"precip": pd.DataFrame({"A": np.ones(len(idx)), "B": np.ones(len(idx))}, index=idx),
             "tmax": pd.DataFrame({"A": 30.0, "B": 31.0}, index=idx),
             "tmin": pd.DataFrame({"A": 20.0, "B": 21.0}, index=idx)}
    rows = [{"station_id": s, "month": m, **{src: float(i + m) for i, (src, _) in enumerate(_WGN_COLUMN_MAP)}}
            for s in ("A", "B") for m in range(1, 13)]
    stations = pd.DataFrame({"name": ["Alpha", "Beta"], "lat": [21.0, 22.0], "lon": [105.0, 106.0],
                             "elev": [10.0, 20.0]}, index=pd.Index(["A", "B"], name="station_id"))
    res = WeatherResult(stations=stations, precip_stations=stations, temp_stations=stations,
                        daily=daily, wgn_stats=pd.DataFrame(rows), qa=[])
    SWATPlusWeatherWriter(res, tmp_path).write()


def test_two_file_format(tmp_path):
    _write(tmp_path)
    st = pd.read_csv(tmp_path / "swatplus_wgn_stations.csv")
    mo = pd.read_csv(tmp_path / "swatplus_wgn_monthly.csv")
    assert list(st.columns) == ["id", "name", "lat", "lon", "elev", "rain_yrs"]
    assert st["id"].tolist() == [1, 2] and st["rain_yrs"].tolist() == [3, 3]    # rain_yrs không rỗng
    assert list(mo.columns) == TWO_FILE_MONTHLY
    assert mo["id"].is_unique and len(mo) == 24 and set(mo["wgn_id"]) == {1, 2}


def test_one_file_format_is_173_columns_month_by_month(tmp_path):
    _write(tmp_path)
    one = pd.read_csv(tmp_path / "swatplus_wgn_onefile.csv")
    assert one.shape == (2, 173)
    assert list(one.columns[:7]) == ["name", "lat", "lon", "elev", "rain_yrs", "tmp_max_ave1", "tmp_min_ave1"]
    assert list(one.columns[-3:]) == ["slr_ave12", "dew_ave12", "wnd_ave12"]
    assert one.loc[0, "tmp_max_ave1"] == 1.0 and one.loc[0, "tmp_min_ave2"] == 3.0
