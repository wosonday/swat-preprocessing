"""Tests for DEMPreprocessor and SpatialWriter."""

from __future__ import annotations

import json

import numpy as np
import pytest

from swatprep.config import DEMConfig
from swatprep.core.dem import DEMPreprocessor
from swatprep.qa import failures


def _make_cfg(path, **kwargs) -> DEMConfig:
    return DEMConfig(path=path, **kwargs)


def _write_dem_raster(path, values):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    data = np.array(values, dtype="float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype=data.dtype,
        crs="EPSG:32648",
        transform=from_origin(500000, 1600000, 30, 30),
        nodata=-9999,
    ) as ds:
        ds.write(data, 1)


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------


def test_missing_file_produces_fail_qa(tmp_dir):
    cfg = _make_cfg(tmp_dir / "nonexistent.tif")
    result = DEMPreprocessor(cfg).run()
    assert failures(result.qa)
    assert any(c.name == "dem_file_exists" for c in result.qa)


def test_invalid_raster_produces_fail_qa(tmp_dir):
    pytest.importorskip("rasterio")
    import swatprep.core.dem as mod
    mod._HAS_RASTERIO = True
    try:
        dem = tmp_dir / "dem.tif"
        dem.write_bytes(b"")
        result = DEMPreprocessor(_make_cfg(dem)).run()
        assert failures(result.qa)
        assert any(c.name == "dem_raster_read_failed" for c in result.qa)
    finally:
        try:
            import rasterio  # noqa: F401
            mod._HAS_RASTERIO = True
        except ImportError:
            mod._HAS_RASTERIO = False



# ---------------------------------------------------------------------------
# Rasterio not installed -> graceful degradation
# ---------------------------------------------------------------------------


def test_no_rasterio_produces_warn_not_fail(tmp_dir):
    import swatprep.core.dem as mod
    original = mod._HAS_RASTERIO
    try:
        mod._HAS_RASTERIO = False
        dem = tmp_dir / "dem.tif"
        dem.write_bytes(b"")
        result = DEMPreprocessor(_make_cfg(dem)).run()
        assert not failures(result.qa)
        assert result.crs is None
        assert result.shape is None
    finally:
        mod._HAS_RASTERIO = original


def test_no_rasterio_result_has_correct_path(tmp_dir):
    import swatprep.core.dem as mod
    original = mod._HAS_RASTERIO
    try:
        mod._HAS_RASTERIO = False
        dem = tmp_dir / "dem.tif"
        dem.write_bytes(b"")
        result = DEMPreprocessor(_make_cfg(dem)).run()
        assert result.path == dem
    finally:
        mod._HAS_RASTERIO = original


# ---------------------------------------------------------------------------
# SpatialWriter
# ---------------------------------------------------------------------------


def test_spatial_writer_creates_dem_info(tmp_dir):
    from swatprep.writers.spatial import SpatialWriter
    import swatprep.core.dem as mod

    original = mod._HAS_RASTERIO
    try:
        mod._HAS_RASTERIO = False
        dem = tmp_dir / "dem.tif"
        dem.write_bytes(b"")
        result = DEMPreprocessor(_make_cfg(dem)).run()
        out = tmp_dir / "spatial_out"
        written = SpatialWriter(result, out).write()
        names = [p.name for p in written]
        assert "dem_info.json" in names
    finally:
        mod._HAS_RASTERIO = original
