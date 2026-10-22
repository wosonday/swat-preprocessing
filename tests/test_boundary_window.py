"""project.boundary limits what build reads from the DEM / land-use / soil rasters."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("rasterio")
gpd = pytest.importorskip("geopandas")

import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from swatprep.api import SWATPrepProject
from swatprep.config import DEMConfig, LandUseConfig, SWATPrepConfig
from swatprep.core.dem import DEMPreprocessor
from swatprep.core.landuse import LandUsePreprocessor
from swatprep.utils.raster import boundary_window, iter_strips, masked_stats, unique_codes


def _raster(path, data, nodata=0):
    arr = np.asarray(data, dtype="int16")
    with rasterio.open(
        path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
        dtype="int16", crs="EPSG:32648", transform=from_origin(500000, 1600000, 30, 30),
        nodata=nodata,
    ) as ds:
        ds.write(arr, 1)
    return path


def _boundary(path, geom):
    gpd.GeoDataFrame(geometry=[geom], crs="EPSG:32648").to_file(path, driver="GeoJSON")
    return path


@pytest.fixture
def grid(tmp_dir):
    """10 x 10 raster, value = 100 * row + col + 1 (never equals nodata 0)."""
    data = np.fromfunction(lambda r, c: 100 * r + c + 1, (10, 10))
    return _raster(tmp_dir / "g.tif", data), data


@pytest.fixture
def inner_box(tmp_dir):
    """Covers columns 2..5 and rows 3..6 of the grid (30 m pixels)."""
    return _boundary(tmp_dir / "b.geojson", box(500061, 1599791, 500179, 1599909))


def test_boundary_window_matches_expected_pixels(grid, inner_box):
    path, _ = grid
    with rasterio.open(path) as ds:
        w = boundary_window(ds, inner_box)
    assert (w.col_off, w.row_off, w.width, w.height) == (2, 3, 4, 4)


def test_iter_strips_with_window_covers_it_exactly_once(grid, inner_box):
    path, _ = grid
    with rasterio.open(path) as ds:
        w = boundary_window(ds, inner_box)
        strips = list(iter_strips(ds, max_pixels=8, window=w))   # 2 rows per strip
    assert [(s.row_off, s.height) for s in strips] == [(3, 2), (5, 2)]
    assert all(s.col_off == 2 and s.width == 4 for s in strips)


def test_stats_and_codes_with_window_equal_the_slice(grid, inner_box):
    path, data = grid
    sub = data[3:7, 2:6]
    with rasterio.open(path) as ds:
        w = boundary_window(ds, inner_box)
        vmin, vmax, mean, n = masked_stats(ds, window=w, max_pixels=8)
        codes = unique_codes(ds, window=w, max_pixels=8)
    assert (vmin, vmax, n) == (sub.min(), sub.max(), sub.size)
    assert mean == pytest.approx(sub.mean())
    assert codes == set(sub.ravel().tolist())


def test_dem_reports_only_the_boundary_window(grid, inner_box):
    path, data = grid
    res = DEMPreprocessor(DEMConfig(path=path), "EPSG:32648", boundary=inner_box).run()
    sub = data[3:7, 2:6]
    assert res.elevation_range == (float(sub.min()), float(sub.max()))
    assert any(c.name == "dem_boundary_window" and c.status == "pass" for c in res.qa)
    full = DEMPreprocessor(DEMConfig(path=path), "EPSG:32648").run()
    assert full.elevation_range == (1.0, float(data.max()))      # no boundary: whole raster


def test_dem_boundary_without_overlap_warns_and_scans_whole_raster(tmp_dir, grid):
    path, data = grid
    far = _boundary(tmp_dir / "far.geojson", box(900000, 1700000, 900100, 1700100))
    res = DEMPreprocessor(DEMConfig(path=path), "EPSG:32648", boundary=far).run()
    assert any(c.name == "dem_boundary_ignored" and c.status == "warn" for c in res.qa)
    assert res.elevation_range == (1.0, float(data.max()))


def test_landuse_codes_come_only_from_the_boundary_window(tmp_dir, inner_box):
    codes = np.ones((10, 10), "int16")
    codes[3:7, 2:6] = 5                                   # inside the boundary
    codes[0, 0] = 9                                       # outside the boundary
    raster = _raster(tmp_dir / "lu.tif", codes)
    lookup = tmp_dir / "lu.csv"
    pd.DataFrame({"code": [1, 5, 9], "swat_code": ["AGRL", "FRST", "URBN"],
                  "swat_name": ["a", "f", "u"]}).to_csv(lookup, index=False)
    cfg = LandUseConfig(raster=raster, lookup=lookup)
    assert LandUsePreprocessor(cfg, boundary=inner_box).run().raster_codes == {5}
    assert LandUsePreprocessor(cfg).run().raster_codes == {1, 5, 9}


def test_build_passes_project_boundary_to_dem(tmp_dir, grid, inner_box):
    path, _ = grid
    cfg = SWATPrepConfig.model_validate({
        "project": {"name": "t", "crs": "EPSG:32648", "output_dir": str(tmp_dir / "out"),
                    "boundary": str(inner_box)},
        "dem": {"path": str(path)},
    })
    result = SWATPrepProject(cfg).build(only="dem")
    assert any(c.name == "dem_boundary_window" for c in result.qa_checks)


def test_boundary_with_wrong_crs_gives_clear_error(tmp_dir, grid):
    path, _ = grid
    bad = tmp_dir / "bad.geojson"      # UTM metres but tagged EPSG:4326 -> cannot be reprojected
    gpd.GeoDataFrame(geometry=[box(499900, 1599900, 500200, 1600200)], crs="EPSG:4326") \
        .to_file(bad, driver="GeoJSON")
    with rasterio.open(path) as ds:
        with pytest.raises(Exception):
            boundary_window(ds, bad)
