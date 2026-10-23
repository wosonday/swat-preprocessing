"""Small raster helpers used by SWAT preprocessing processors and writers."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..errors import InputValidationError
from ..qa import QACheck


def iter_strips(ds, max_pixels: int = 16_000_000, window=None):
    """Yield row strips (rasterio Windows) of at most ~max_pixels each.

    Covers the whole raster, or only `window` when given. Lets big rasters be
    processed with bounded memory instead of ds.read().
    """
    from rasterio.windows import Window

    w = window or Window(0, 0, ds.width, ds.height)
    width, height = int(w.width), int(w.height)
    rows = max(1, max_pixels // width)
    for row in range(0, height, rows):
        yield Window(int(w.col_off), int(w.row_off) + row, width, min(rows, height - row))


def masked_stats(ds, band: int = 1, max_pixels: int = 16_000_000, window=None):
    """(min, max, mean, n_valid) of valid (non-NoData) pixels, streamed by strips."""
    vmin, vmax, total, count = np.inf, -np.inf, 0.0, 0
    for win in iter_strips(ds, max_pixels, window):
        data = ds.read(band, window=win, masked=True)
        n = int(data.count())
        if n:
            vmin = min(vmin, float(data.min()))
            vmax = max(vmax, float(data.max()))
            total += float(data.sum(dtype="float64"))
            count += n
    return (vmin, vmax, total / count, count) if count else (None, None, None, 0)


def unique_codes(ds, band: int = 1, max_pixels: int = 16_000_000, window=None) -> set:
    """Unique valid (non-NoData) pixel values, streamed by strips."""
    codes: set = set()
    for win in iter_strips(ds, max_pixels, window):
        data = ds.read(band, window=win, masked=True)
        codes.update(np.unique(data.compressed()).tolist())
    return codes


def _read_boundary(boundary_path: Path, crs):
    """Boundary GeoDataFrame reprojected to `crs` (needs swatprep[geo])."""
    import geopandas as gpd

    gdf = gpd.read_file(boundary_path)
    if gdf.crs is None:
        raise InputValidationError(f"Boundary has no CRS: {boundary_path}")
    return gdf.to_crs(crs)


def _window_of(ds, bounds):
    """(col0, row0, width, height) of `bounds` (raster CRS), rounded outwards and
    limited to the raster; InputValidationError if they do not overlap."""
    l, b, r, t = bounds
    inv = ~ds.transform
    cols, rows = zip(*[
        (inv.a * x + inv.b * y + inv.c, inv.d * x + inv.e * y + inv.f)
        for x, y in ((l, b), (l, t), (r, b), (r, t))
    ])
    if not np.isfinite([*cols, *rows]).all():
        raise InputValidationError(
            "Boundary cannot be converted to the raster CRS (wrong or missing CRS?)")
    c0, c1 = max(int(np.floor(min(cols))), 0), min(int(np.ceil(max(cols))), ds.width)
    r0, r1 = max(int(np.floor(min(rows))), 0), min(int(np.ceil(max(rows))), ds.height)
    if c0 >= c1 or r0 >= r1:
        raise InputValidationError("Boundary does not overlap the raster extent")
    return c0, r0, c1 - c0, r1 - r0


def boundary_window(ds, boundary_path: Path):
    """rasterio Window covering the boundary's bounding box in the open raster `ds`."""
    from rasterio.windows import Window

    if ds.crs is None:
        raise InputValidationError("Raster has no CRS, cannot use the project boundary")
    c0, r0, w, h = _window_of(ds, _read_boundary(boundary_path, ds.crs).total_bounds)
    return Window(c0, r0, w, h)


def resolve_window(ds, boundary_path, qa: list, label: str):
    """Window of the project boundary, or None to scan the whole raster.

    Appends a QACheck to `qa`: pass when the window is used, warn when the
    boundary could not be applied (the whole raster is then scanned).
    """
    if boundary_path is None:
        return None
    try:
        win = boundary_window(ds, boundary_path)
    except ImportError:
        reason = "geopandas not installed (pip install 'swatprep[geo]')"
    except Exception as exc:  # unreadable boundary, no CRS, no overlap, ...
        reason = str(exc)
    else:
        pct = 100.0 * win.width * win.height / (ds.width * ds.height)
        qa.append(QACheck(
            name=f"{label}_boundary_window", status="pass",
            message=f"{label}: read only the project-boundary window "
                    f"({int(win.width)} x {int(win.height)} px, {pct:.4f}% of the raster)",
            context={"window": [int(win.col_off), int(win.row_off),
                                int(win.width), int(win.height)]},
        ))
        return win
    qa.append(QACheck(
        name=f"{label}_boundary_ignored", status="warn",
        message=f"{label}: project.boundary not applied, scanning the whole raster: {reason}",
    ))
    return None


def read_unique_codes(path: Path) -> set[int]:
    """Return unique integer raster values, excluding NoData."""
    import rasterio

    with rasterio.open(path) as ds:
        return {int(v) for v in unique_codes(ds)}


def reclassify_raster(
    src_path: Path,
    dst_path: Path,
    mapping: dict[int, int],
    nodata: int | float | None = None,
) -> Path:
    """Write a reclassified copy of a single-band raster."""
    import rasterio

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(src_path) as src:
        data = src.read(1)
        src_nodata = src.nodata if nodata is None else nodata
        out = np.full(data.shape, src_nodata if src_nodata is not None else 0, dtype="int32")

        for source_code, target_code in mapping.items():
            out[data == source_code] = target_code

        profile = src.profile.copy()
        profile.update(dtype="int32", nodata=src_nodata)

        with rasterio.open(dst_path, "w", **profile) as dst:
            dst.write(out, 1)

    return dst_path


def copy_raster(src_path: Path, dst_path: Path) -> Path:
    """Copy a raster dataset preserving metadata and pixel values."""
    import rasterio

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(src_path) as src:
        profile = src.profile.copy()
        data = src.read()
        with rasterio.open(dst_path, "w", **profile) as dst:
            dst.write(data)
    return dst_path


def clip_raster(
    src_path: Path,
    dst_path: Path,
    boundary_path: Path,
    mask: bool = False,
    max_pixels: int = 16_000_000,
    dst_crs=None,
    resampling: str = "nearest",
    resolution: float | None = None,
) -> Path:
    """Crop a raster to the boundary's bounding box (optionally mask outside the polygons).

    The boundary is reprojected to the output CRS. Only the needed window is read,
    strip by strip, so memory stays bounded even for very large rasters.

    dst_crs     target CRS (e.g. "EPSG:32648"); None or equal to the source CRS = keep it.
                When it differs, the raster is warped lazily (WarpedVRT) and only the
                cropped window is computed.
    resampling  "nearest" (class codes) | "bilinear" | "cubic" (continuous data such as a DEM).
    resolution  output pixel size in dst_crs units; None = GDAL default for the source.
    """
    from contextlib import nullcontext

    import rasterio
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from rasterio.features import geometry_mask
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import calculate_default_transform
    from rasterio.windows import Window

    src_path, dst_path = Path(src_path), Path(dst_path)
    with rasterio.open(src_path) as src:
        if src.crs is None:
            raise InputValidationError(f"Raster has no CRS, cannot clip: {src_path}")
        if mask and src.nodata is None:
            raise InputValidationError("mask=True needs a raster with a NoData value")
        try:
            method = Resampling[resampling]
        except KeyError:
            raise InputValidationError(f"Unknown resampling '{resampling}'") from None
        target = CRS.from_user_input(dst_crs) if dst_crs else src.crs

        if target == src.crs and resolution is None:
            ds, ctx = src, nullcontext(src)
        else:
            tf, w, h = calculate_default_transform(
                src.crs, target, src.width, src.height, *src.bounds, resolution=resolution)
            ds = WarpedVRT(src, crs=target, transform=tf, width=w, height=h,
                           resampling=method, nodata=src.nodata)
            ctx = ds
        with ctx:
            gdf = _read_boundary(boundary_path, target)
            c0, r0, width, height = _window_of(ds, gdf.total_bounds)
            profile = src.profile.copy()
            profile.update(
                driver="GTiff", width=width, height=height, tiled=True, crs=target,
                blockxsize=256, blockysize=256, compress="deflate", BIGTIFF="IF_SAFER",
                transform=ds.window_transform(Window(c0, r0, width, height)),
            )
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            step = max(1, max_pixels // width)
            with rasterio.open(dst_path, "w", **profile) as dst:
                for row in range(0, height, step):
                    h_ = min(step, height - row)
                    win = Window(c0, r0 + row, width, h_)
                    data = ds.read(window=win)
                    if mask:
                        inside = geometry_mask(
                            gdf.geometry, out_shape=(h_, width),
                            transform=ds.window_transform(win), invert=True,
                        )
                        data[:, ~inside] = src.nodata
                    dst.write(data, window=Window(0, row, width, h_))
    return dst_path
