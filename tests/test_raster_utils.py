"""Tests for raster utility helpers."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("rasterio")

import rasterio
from rasterio.transform import from_origin

from swatprep.utils.raster import copy_raster, read_unique_codes, reclassify_raster


def _write_tiny_raster(path, data, nodata=0):
    arr = np.array(data, dtype="int16")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=arr.shape[0],
        width=arr.shape[1],
        count=1,
        dtype=arr.dtype,
        crs="EPSG:32648",
        transform=from_origin(500000, 1600000, 30, 30),
        nodata=nodata,
    ) as ds:
        ds.write(arr, 1)


def test_read_unique_codes_excludes_nodata(tmp_dir):
    raster = tmp_dir / "codes.tif"
    _write_tiny_raster(raster, [[0, 10, 20], [20, 30, 0]])

    assert read_unique_codes(raster) == {10, 20, 30}


def test_reclassify_raster_preserves_metadata_and_maps_codes(tmp_dir):
    src = tmp_dir / "landuse.tif"
    dst = tmp_dir / "landuse_swat.tif"
    _write_tiny_raster(src, [[0, 10, 20], [20, 30, 0]])

    reclassify_raster(src, dst, {10: 101, 20: 202, 30: 303}, nodata=0)

    with rasterio.open(dst) as ds:
        data = ds.read(1)
        assert ds.crs.to_string() == "EPSG:32648"
        assert ds.nodata == 0
        assert data.tolist() == [[0, 101, 202], [202, 303, 0]]


def test_copy_raster_writes_destination(tmp_dir):
    src = tmp_dir / "dem.tif"
    dst = tmp_dir / "dem_projected.tif"
    _write_tiny_raster(src, [[100, 101], [102, 103]], nodata=-9999)

    copy_raster(src, dst)

    with rasterio.open(dst) as ds:
        assert ds.read(1).tolist() == [[100, 101], [102, 103]]
        assert ds.nodata == -9999
