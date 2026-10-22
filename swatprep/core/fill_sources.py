"""Fill sources for WeatherGapFiller: CSV or daily gridded NetCDF."""
from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd

from ..config import FillNetCDFConfig, WeatherConfig
from ..errors import InputValidationError
from ..qa import QACheck
from .weather import WeatherPreprocessor

_LAT_CANDIDATES = ("lat", "latitude", "y")
_LON_CANDIDATES = ("lon", "longitude", "x")
_TIME_CANDIDATES = ("time", "date")


class FillSource(Protocol):
    def load(
        self, stations: pd.DataFrame, index: pd.DatetimeIndex, variables: list[str],
    ) -> tuple[dict[str, pd.DataFrame], list[QACheck]]: ...


class CsvFillSource:
    """CSV theo trạm, nạp bằng WeatherPreprocessor (hành vi cũ)."""

    def __init__(self, cfg: WeatherConfig) -> None:
        self.cfg = cfg

    def load(self, stations, index, variables):
        result = WeatherPreprocessor(self.cfg).run()
        return result.daily, result.qa


class NetCDFFillSource:
    """NetCDF lưới theo ngày; lấy giá trị ô gần nhất tại mỗi trạm thực đo."""

    def __init__(self, cfg: FillNetCDFConfig) -> None:
        self.cfg = cfg

    def load(self, stations, index, variables):
        try:
            import xarray as xr
        except ImportError as e:
            raise InputValidationError(
                "NetCDF fill source needs xarray: pip install 'swatprep[nc]'"
            ) from e

        cfg, qa = self.cfg, []
        no_map = [v for v in variables if v not in cfg.var_map]
        if no_map:
            raise InputValidationError(
                f"weather.fill.netcdf.var_map has no entry for: {', '.join(no_map)}"
            )

        with xr.open_dataset(cfg.path) as ds:
            lat_n = _axis_name(ds, cfg.lat_name, _LAT_CANDIDATES, "lat_name")
            lon_n = _axis_name(ds, cfg.lon_name, _LON_CANDIDATES, "lon_name")
            time_n = _axis_name(ds, cfg.time_name, _TIME_CANDIDATES, "time_name")
            missing = [n for v in variables if (n := cfg.var_map[v]) not in ds.data_vars]
            if missing:
                raise InputValidationError(
                    f"NetCDF variable(s) not found: {', '.join(missing)}. "
                    f"Available: {', '.join(ds.data_vars)}"
                )
            if ds[time_n].dtype.kind != "M":
                raise InputValidationError(
                    "NetCDF time axis uses a non-standard calendar; "
                    "convert it to a standard (Gregorian) daily calendar first."
                )

            ilat, ok_lat = _nearest(ds[lat_n].values, stations["lat"].to_numpy(float))
            grid_lon = ds[lon_n].values
            ilon, ok_lon = _nearest(
                grid_lon, _match_lon(stations["lon"].to_numpy(float), grid_lon)
            )
            ok = ok_lat & ok_lon
            for sid in stations.index[~ok]:
                qa.append(QACheck(
                    name=f"netcdf_extract:{sid}:outside_grid", status="warn",
                    message=f"{sid}: station is outside the NetCDF grid, no fill source",
                ))
            if not ok.any():
                raise InputValidationError("No station lies inside the NetCDF grid.")

            sel = {
                lat_n: xr.DataArray(ilat[ok], dims="station"),
                lon_n: xr.DataArray(ilon[ok], dims="station"),
            }
            times = pd.DatetimeIndex(ds[time_n].values).normalize()
            daily: dict[str, pd.DataFrame] = {}
            for var in variables:
                arr = ds[cfg.var_map[var]].isel(sel).transpose(time_n, "station").values
                df = pd.DataFrame(arr, index=times, columns=stations.index[ok])
                df = df[~df.index.duplicated(keep="first")]
                daily[var] = df.reindex(index)

        qa.append(QACheck(
            name="netcdf_loaded", status="pass",
            message=f"NetCDF fill source: {int(ok.sum())} station(s), "
                    f"variables: {', '.join(variables)}",
        ))
        return daily, qa


def _axis_name(ds, requested: str, candidates: tuple[str, ...], option: str) -> str:
    names = [requested] if requested != "auto" else list(candidates)
    for name in names:
        if name in ds.variables:
            return name
    raise InputValidationError(
        f"Cannot find axis in NetCDF (tried: {', '.join(names)}). "
        f"Set weather.fill.netcdf.{option}."
    )


def _nearest(grid: np.ndarray, coords: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Chỉ số ô gần nhất; và True nếu cách ô đó không quá một bước lưới."""
    grid = np.asarray(grid, float)
    idx = np.abs(grid[:, None] - coords[None, :]).argmin(axis=0)
    step = np.median(np.abs(np.diff(grid))) if grid.size > 1 else np.inf
    return idx, np.abs(grid[idx] - coords) <= step


def _match_lon(lons: np.ndarray, grid_lon: np.ndarray) -> np.ndarray:
    """Đưa kinh độ trạm về quy ước của lưới (0–360 hoặc −180–180)."""
    return lons % 360 if np.nanmax(grid_lon) > 180 else (lons + 180) % 360 - 180