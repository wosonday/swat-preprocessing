"""Tests for raster utility helpers."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("rasterio")

import rasterio
from rasterio.transform import from_origin

from swatprep.utils.raster import (
    copy_raster, iter_strips, masked_stats, read_unique_codes, reclassify_raster, unique_codes,
)


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


def test_iter_strips_cover_every_row_exactly_once(tmp_dir):
    raster = tmp_dir / "r.tif"
    _write_tiny_raster(raster, np.arange(70).reshape(10, 7))
    with rasterio.open(raster) as ds:
        wins = list(iter_strips(ds, max_pixels=21))        # 3 rows per strip
        assert [(w.row_off, w.height) for w in wins] == [(0, 3), (3, 3), (6, 3), (9, 1)]
        assert all(w.width == 7 for w in wins)


def test_masked_stats_streamed_equals_full_read(tmp_dir):
    raster = tmp_dir / "dem.tif"
    data = np.arange(60).reshape(6, 10) + 100
    data[2, 3] = -9999
    data[5, :] = -9999
    _write_tiny_raster(raster, data, nodata=-9999)
    with rasterio.open(raster) as ds:
        full = ds.read(1, masked=True)
        for max_pixels in (10, 25, 10_000):                 # many strips ... one strip
            vmin, vmax, mean, n = masked_stats(ds, max_pixels=max_pixels)
            assert (vmin, vmax, n) == (float(full.min()), float(full.max()), int(full.count()))
            assert mean == pytest.approx(float(full.mean()))


def test_masked_stats_all_nodata_returns_zero_count(tmp_dir):
    raster = tmp_dir / "empty.tif"
    _write_tiny_raster(raster, [[0, 0], [0, 0]], nodata=0)
    with rasterio.open(raster) as ds:
        assert masked_stats(ds) == (None, None, None, 0)


def test_unique_codes_streamed_excludes_nodata(tmp_dir):
    raster = tmp_dir / "codes.tif"
    _write_tiny_raster(raster, [[0, 10, 20], [20, 30, 0], [40, 0, 10]])
    with rasterio.open(raster) as ds:
        assert unique_codes(ds, max_pixels=3) == {10, 20, 30, 40}


# --- clip_raster -----------------------------------------------------------------------

try:
    import geopandas as gpd
    from shapely.geometry import Polygon, box
except ImportError:                      # swatprep[geo] không đầy đủ: chỉ bỏ qua test clip
    gpd = None

from swatprep.errors import InputValidationError
from swatprep.utils.raster import clip_raster

needs_geopandas = pytest.mark.skipif(gpd is None, reason="geopandas not installed")


def _grid(tmp_dir, n=10):
    """Raster n x n, pixel 30 m, giá trị = hàng*100 + cột (+1 để khác nodata 0)."""
    raster = tmp_dir / "g.tif"
    _write_tiny_raster(raster, np.fromfunction(lambda i, j: i * 100 + j + 1, (n, n)))
    return raster


def _boundary(tmp_dir, geom, crs="EPSG:32648", name="b.geojson"):
    path = tmp_dir / name
    gpd.GeoDataFrame(geometry=[geom], crs=crs).to_file(path, driver="GeoJSON")
    return path


@needs_geopandas
def test_clip_bbox_crops_expected_window(tmp_dir):
    raster = _grid(tmp_dir)
    # gốc (500000, 1600000), pixel 30 m: cột 2..5 -> x 500060..500180 ; hàng 3..6 -> y 1599910..1599790
    b = _boundary(tmp_dir, box(500061, 1599791, 500179, 1599909))
    out = clip_raster(raster, tmp_dir / "o" / "c.tif", b)
    with rasterio.open(out) as ds, rasterio.open(raster) as src:
        assert (ds.width, ds.height) == (4, 4)
        assert ds.transform.c == 500060 and ds.transform.f == 1599910
        assert np.array_equal(ds.read(1), src.read(1)[3:7, 2:6])
        assert ds.nodata == src.nodata and ds.crs == src.crs


@needs_geopandas
def test_clip_is_identical_when_strips_are_small(tmp_dir):
    raster = _grid(tmp_dir)
    b = _boundary(tmp_dir, box(500061, 1599791, 500179, 1599909))
    a = clip_raster(raster, tmp_dir / "a.tif", b)
    s = clip_raster(raster, tmp_dir / "s.tif", b, max_pixels=4)   # 1 hàng mỗi dải
    with rasterio.open(a) as x, rasterio.open(s) as y:
        assert np.array_equal(x.read(), y.read())


@needs_geopandas
def test_clip_reprojects_boundary_to_raster_crs(tmp_dir):
    raster = _grid(tmp_dir)
    geom = gpd.GeoSeries([box(500061, 1599791, 500179, 1599909)], crs="EPSG:32648")
    b = _boundary(tmp_dir, geom.to_crs("EPSG:4326").iloc[0], crs="EPSG:4326", name="w.geojson")
    with rasterio.open(clip_raster(raster, tmp_dir / "c.tif", b)) as ds:
        assert (ds.width, ds.height) == (4, 4)


@needs_geopandas
def test_clip_mask_sets_pixels_outside_polygon_to_nodata(tmp_dir):
    raster = _grid(tmp_dir)
    tri = Polygon([(500000, 1599700), (500300, 1599700), (500300, 1600000)])  # nửa dưới-phải
    b = _boundary(tmp_dir, tri)
    with rasterio.open(clip_raster(raster, tmp_dir / "m.tif", b, mask=True)) as ds:
        d = ds.read(1)
        assert d[0, 0] == 0 and d[-1, -1] != 0          # góc trên-trái ngoài, dưới-phải trong
    with rasterio.open(clip_raster(raster, tmp_dir / "n.tif", b)) as ds:
        assert (ds.read(1) != 0).all()                   # bbox crop: không che


@needs_geopandas
def test_clip_outside_extent_raises(tmp_dir):
    raster = _grid(tmp_dir)
    b = _boundary(tmp_dir, box(600000, 1700000, 600100, 1700100))
    with pytest.raises(InputValidationError, match="does not overlap"):
        clip_raster(raster, tmp_dir / "x.tif", b)


@needs_geopandas
def test_cli_clip_writes_cropped_raster(tmp_dir):
    from click.testing import CliRunner
    from swatprep.cli import main

    raster = _grid(tmp_dir)
    b = _boundary(tmp_dir, box(500061, 1599791, 500179, 1599909))
    out = tmp_dir / "cli.tif"
    res = CliRunner().invoke(main, ["clip", str(raster), str(b), str(out)])
    assert res.exit_code == 0, res.output
    with rasterio.open(out) as ds:
        assert (ds.width, ds.height) == (4, 4)


@needs_geopandas
def test_cli_clip_reports_non_overlapping_boundary(tmp_dir):
    from click.testing import CliRunner
    from swatprep.cli import main

    raster = _grid(tmp_dir)
    b = _boundary(tmp_dir, box(600000, 1700000, 600100, 1700100))
    res = CliRunner().invoke(main, ["clip", str(raster), str(b), str(tmp_dir / "x.tif")])
    assert res.exit_code == 1 and "does not overlap" in res.output


@needs_geopandas
def test_clip_accepts_plain_string_paths(tmp_dir):
    raster = _grid(tmp_dir)
    b = _boundary(tmp_dir, box(500061, 1599791, 500179, 1599909))
    out = clip_raster(str(raster), str(tmp_dir / "s.tif"), str(b))
    assert out.exists()
