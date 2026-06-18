"""Small raster helpers used by SWAT preprocessing processors and writers."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def read_unique_codes(path: Path) -> set[int]:
    """Return unique integer raster values, excluding NoData."""
    import rasterio

    with rasterio.open(path) as ds:
        data = ds.read(1)
        nodata = ds.nodata
        if nodata is None:
            mask = np.ones_like(data, dtype=bool)
        else:
            mask = data != nodata
        return {int(v) for v in data[mask].flatten().tolist()}


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
