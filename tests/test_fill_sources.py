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