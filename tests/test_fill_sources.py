import numpy as np, pandas as pd, pytest
xr = pytest.importorskip("xarray")
pytest.importorskip("netCDF4")

from swatprep.config import FillNetCDFConfig, WeatherFillConfig
from swatprep.core.fill_sources import NetCDFFillSource
from swatprep.errors import InputValidationError

DATES = pd.date_range("2000-01-01", periods=4, freq="D")
STATIONS = pd.DataFrame(
    {"name": ["A", "B"], "lat": [15.1, 15.4], "lon": [105.1, 105.4], "elev": [1, 1]},
    index=pd.Index(["S1", "S2"], name="id"),
)

def _write_nc(path, lat=(16.0, 15.5, 15.0), lon=(105.0, 105.5), time=DATES):
    """precip = chỉ_số_lat*10 + chỉ_số_lon + ngày  -> mỗi ô nhận diện được."""
    shape = (len(time), len(lat), len(lon))
    base = np.fromfunction(lambda t, i, j: i * 10 + j + t, shape)
    xr.Dataset(
        {"pr": (("time", "lat", "lon"), base), "tasmax": (("time", "lat", "lon"), base + 20)},
        coords={"time": time, "lat": list(lat), "lon": list(lon)},
    ).to_netcdf(path)
    return path

def _cfg(path, **kw):
    return FillNetCDFConfig(path=path, var_map={"precip": "pr", "tmax": "tasmax"}, **kw)

def test_extracts_nearest_cell_per_station(tmp_path):
    daily, qa = NetCDFFillSource(_cfg(_write_nc(tmp_path / "g.nc"))).load(
        STATIONS, DATES, ["precip", "tmax"])
    assert daily["precip"]["S1"].tolist() == [20.0, 21.0, 22.0, 23.0]  # lat 15.0, lon 105.0
    assert daily["precip"]["S2"].tolist() == [11.0, 12.0, 13.0, 14.0]  # lat 15.5, lon 105.5
    assert daily["tmax"]["S1"].iloc[0] == 40.0

def test_station_outside_grid_is_warned_and_omitted(tmp_path):
    far = STATIONS.copy(); far.loc["S2", ["lat", "lon"]] = [40.0, 120.0]
    daily, qa = NetCDFFillSource(_cfg(_write_nc(tmp_path / "g.nc"))).load(far, DATES, ["precip"])
    assert list(daily["precip"].columns) == ["S1"]
    assert any(c.status == "warn" and "S2" in c.message for c in qa)

def test_longitude_0_360_grid_is_matched(tmp_path):
    nc = _write_nc(tmp_path / "g.nc", lon=(285.0, 285.5))
    sta = STATIONS.copy(); sta["lon"] = [-74.9, -74.6]
    daily, _ = NetCDFFillSource(_cfg(nc)).load(sta, DATES, ["precip"])
    assert daily["precip"]["S1"].iloc[0] == 20.0

def test_missing_netcdf_variable_raises_with_available_names(tmp_path):
    cfg = FillNetCDFConfig(path=_write_nc(tmp_path / "g.nc"), var_map={"precip": "rain"})
    with pytest.raises(InputValidationError, match="rain.*Available"):
        NetCDFFillSource(cfg).load(STATIONS, DATES, ["precip"])

def test_fill_config_block_must_match_type():
    with pytest.raises(ValueError, match="weather.fill.netcdf block is missing"):
        WeatherFillConfig(type="netcdf")
    with pytest.raises(ValueError, match="var_map"):
        FillNetCDFConfig(path="x.nc", var_map={"rain": "pr"})

# --- đọc theo hộp bao + ô lân cận có dữ liệu -------------------------------------------

def _write_masked_nc(path, nan_cols=(), lat=(15.5, 15.0), lon=(105.0, 105.5)):
    """Như _write_nc nhưng các cột kinh độ trong nan_cols toàn NaN (mô phỏng ô biển)."""
    shape = (len(DATES), len(lat), len(lon))
    base = np.fromfunction(lambda t, i, j: i * 10 + j + t, shape)
    base[:, :, list(nan_cols)] = np.nan
    xr.Dataset(
        {"pr": (("time", "lat", "lon"), base)},
        coords={"time": DATES, "lat": list(lat), "lon": list(lon)},
    ).to_netcdf(path)
    return path


def _mid(lat=15.0, lon=105.25):
    return pd.DataFrame({"name": ["M"], "lat": [lat], "lon": [lon], "elev": [1]},
                        index=pd.Index(["MID"], name="id"))


def test_bounding_box_read_equals_pointwise_selection(tmp_path):
    nc = _write_nc(tmp_path / "g.nc", lat=(16.0, 15.5, 15.0), lon=(105.0, 105.5))
    daily, _ = NetCDFFillSource(_cfg(nc, search_radius=0)).load(STATIONS, DATES, ["precip"])
    with xr.open_dataset(nc) as ds:
        ref = ds["pr"].sel(lat=[15.0, 15.5], lon=[105.0, 105.5])
        assert daily["precip"]["S1"].tolist() == ref.sel(lat=15.0, lon=105.0).values.tolist()
        assert daily["precip"]["S2"].tolist() == ref.sel(lat=15.5, lon=105.5).values.tolist()


def test_tied_station_with_nan_cell_falls_back_to_valid_neighbor(tmp_path):
    nc = _write_masked_nc(tmp_path / "g.nc", nan_cols=(0,))
    daily, qa = NetCDFFillSource(_cfg_pr(nc)).load(_mid(), DATES, ["precip"])
    assert daily["precip"]["MID"].tolist() == [11.0, 12.0, 13.0, 14.0]  # ô (15.0, 105.5)
    assert any(c.name == "netcdf_extract:MID:neighbor_cell" and c.status == "warn" for c in qa)


def test_search_radius_zero_does_not_look_at_neighbors(tmp_path):
    nc = _write_masked_nc(tmp_path / "g.nc", nan_cols=(0,))
    with pytest.raises(InputValidationError, match="No station has a NetCDF cell"):
        NetCDFFillSource(_cfg_pr(nc, search_radius=0)).load(_mid(), DATES, ["precip"])


def test_valid_nearest_cell_gives_no_neighbor_warning(tmp_path):
    nc = _write_masked_nc(tmp_path / "g.nc")
    _, qa = NetCDFFillSource(_cfg_pr(nc)).load(_mid(), DATES, ["precip"])
    assert not any("neighbor_cell" in c.name for c in qa)


def test_match_lon_changes_only_what_is_needed():
    from swatprep.core.fill_sources import _match_lon
    g180, g360 = np.array([107.3, 107.4]), np.array([285.0, 285.5])
    assert _match_lon(np.array([107.35]), g180)[0] == 107.35          # không sai số dấu phẩy động
    assert _match_lon(np.array([-74.9]), g360)[0] == pytest.approx(285.1)
    assert _match_lon(np.array([285.1]), g180)[0] == pytest.approx(-74.9)


def _cfg_pr(path, **kw):
    return FillNetCDFConfig(path=path, var_map={"precip": "pr"}, **kw)


def test_exact_midpoint_tie_goes_to_lower_index_cell(tmp_path):
    nc = _write_masked_nc(tmp_path / "g.nc", lon=(107.3, 107.4))
    sta = _mid(lat=15.0, lon=107.35)
    daily, qa = NetCDFFillSource(_cfg_pr(nc, search_radius=0)).load(sta, DATES, ["precip"])
    assert daily["precip"]["MID"].tolist() == [10.0, 11.0, 12.0, 13.0]  # ô (15.0, 107.3)
    assert qa[-1].status == "pass"
