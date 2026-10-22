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
    """NetCDF lưới theo ngày; lấy giá trị ô gần nhất *có dữ liệu* tại mỗi trạm."""

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

            glat = np.asarray(ds[lat_n].values, float)
            glon = np.asarray(ds[lon_n].values, float)
            lats = stations["lat"].to_numpy(float)
            lons = _match_lon(stations["lon"].to_numpy(float), glon)
            ilat, ok_lat = _nearest(glat, lats)
            ilon, ok_lon = _nearest(glon, lons)
            ok = ok_lat & ok_lon
            for sid in stations.index[~ok]:
                qa.append(QACheck(
                    name=f"netcdf_extract:{sid}:outside_grid", status="warn",
                    message=f"{sid}: station is outside the NetCDF grid, no fill source",
                ))
            if not ok.any():
                raise InputValidationError("No station lies inside the NetCDF grid.")

            ids = list(stations.index[ok])
            cands = [
                _candidates(glat, glon, la, lo, i, j, cfg.search_radius)
                for la, lo, i, j in zip(lats[ok], lons[ok], ilat[ok], ilon[ok])
            ]
            # Đọc MỘT lần hộp bao của mọi ô ứng viên (ít lần giải nén chunk),
            # sau đó chọn ô từng trạm bằng NumPy.
            rc = np.array([c for cs in cands for c in cs])
            i0, j0 = int(rc[:, 0].min()), int(rc[:, 1].min())
            box = {
                lat_n: slice(i0, int(rc[:, 0].max()) + 1),
                lon_n: slice(j0, int(rc[:, 1].max()) + 1),
            }
            slabs = {
                v: ds[cfg.var_map[v]].isel(box).transpose(time_n, lat_n, lon_n).values
                for v in variables
            }
            times = pd.DatetimeIndex(ds[time_n].values).normalize()

            kept, cells = [], []
            for sid, cs in zip(ids, cands):
                cell = _first_valid(cs, slabs, i0, j0)
                if cell is None:
                    qa.append(QACheck(
                        name=f"netcdf_extract:{sid}:no_valid_cell", status="warn",
                        message=f"{sid}: no cell with data within {cfg.search_radius} "
                                "cell(s) of the station, no fill source",
                    ))
                    continue
                if cell != cs[0]:
                    qa.append(QACheck(
                        name=f"netcdf_extract:{sid}:neighbor_cell", status="warn",
                        message=f"{sid}: nearest cell has no data; used cell "
                                f"(lat={glat[cell[0]]:g}, lon={glon[cell[1]]:g}) instead",
                        context={"nearest": [int(x) for x in cs[0]],
                                 "used": [int(x) for x in cell]},
                    ))
                kept.append(sid)
                cells.append(cell)
            if not kept:
                raise InputValidationError(
                    "No station has a NetCDF cell with data; check the grid or search_radius."
                )

            daily: dict[str, pd.DataFrame] = {}
            for var in variables:
                arr = np.stack([slabs[var][:, i - i0, j - j0] for i, j in cells], axis=1)
                df = pd.DataFrame(arr, index=times, columns=kept)
                df = df[~df.index.duplicated(keep="first")]
                daily[var] = df.reindex(index)

        qa.append(QACheck(
            name="netcdf_loaded", status="pass",
            message=f"NetCDF fill source: {len(kept)} station(s), "
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
    # Làm tròn khoảng cách để các trường hợp hoà (trạm đúng giữa 2 ô) luôn về ô chỉ số thấp hơn,
    # không phụ thuộc nhiễu dấu phẩy động ~1e-14.
    idx = np.round(np.abs(grid[:, None] - coords[None, :]), 9).argmin(axis=0)
    step = np.median(np.abs(np.diff(grid))) if grid.size > 1 else np.inf
    return idx, np.abs(grid[idx] - coords) <= step


def _match_lon(lons: np.ndarray, grid_lon: np.ndarray) -> np.ndarray:
    """Đưa kinh độ trạm về quy ước của lưới; chỉ đổi khi cần (tránh sai số 107.35 -> ...02)."""
    lons = np.asarray(lons, float)
    if np.nanmax(grid_lon) > 180:                    # lưới 0-360
        return np.where(lons < 0, lons + 360.0, lons)
    return np.where(lons > 180, lons - 360.0, lons)  # lưới -180..180


def _candidates(glat, glon, lat, lon, ci, cj, radius):
    """(i, j) các ô trong ±radius quanh ô (ci, cj), xếp từ gần trạm nhất đến xa nhất."""
    ii = np.arange(max(ci - radius, 0), min(ci + radius, glat.size - 1) + 1)
    jj = np.arange(max(cj - radius, 0), min(cj + radius, glon.size - 1) + 1)
    dlat = (glat[ii] - lat)[:, None]
    dlon = (glon[jj] - lon)[None, :] * np.cos(np.radians(lat))
    order = np.argsort(np.round(dlat**2 + dlon**2, 12).ravel(), kind="stable")
    return [(int(ii[k // jj.size]), int(jj[k % jj.size])) for k in order]


def _first_valid(cands, slabs, i0, j0):
    """Ô đầu tiên có ít nhất một giá trị hữu hạn ở MỌI biến; None nếu không có."""
    for i, j in cands:
        if all(np.isfinite(s[:, i - i0, j - j0]).any() for s in slabs.values()):
            return i, j
    return None
