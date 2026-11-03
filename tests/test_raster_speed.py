"""v0.9.0: overviews on output rasters, exact fast class counts, GDAL threads."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("rasterio")
gpd = pytest.importorskip("geopandas")

import rasterio
from click.testing import CliRunner
from rasterio.transform import from_origin
from shapely.geometry import box

from swatprep.api import SWATPrepProject
from swatprep.config import ClipItemConfig, ProjectConfig, SWATPrepConfig
from swatprep.core.clip import ClipProcessor
from swatprep.utils.raster import (
    CLASS_COUNTS_TAG,
    add_overviews,
    class_counts,
    gdal_env,
    masked_stats,
    overview_factors,
    store_stats,
    unique_codes,
)

N = 1200            # 1200 px: overviews 2 (600 px) and 4 (300 px); 8 would be 150 px < 256


def _tif(path, data, nodata=0):
    data = np.asarray(data)
    with rasterio.open(path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1,
                       dtype=data.dtype.name, crs="EPSG:32648", transform=from_origin(500000, 1600000, 30, 30),
                       nodata=nodata) as ds:
        ds.write(data, 1)
    return path


def _checker(n=N, dtype="uint8"):
    """Classes 1 and 3 in a 1-pixel checkerboard: 'average' would invent class 2, 'mode' cannot."""
    r, c = np.indices((n, n))
    return np.where((r + c) % 2, 1, 3).astype(dtype)


def _boundary(tmp_dir, n=N):
    path = tmp_dir / "b.geojson"
    gpd.GeoDataFrame(geometry=[box(500000 + 1, 1600000 - n * 30 + 1, 500000 + n * 30 - 1, 1600000 - 1)],
                     crs="EPSG:32648").to_file(path, driver="GeoJSON")
    return path


# ---------------------------------------------------------------------------- overviews


@pytest.mark.parametrize("size, expected", [((5000, 3000), [2, 4, 8, 16]), ((1024, 10), [2, 4]),
                                            ((300, 200), []), ((511, 511), [])])
def test_overview_factors_stop_at_256_pixels(size, expected):
    assert overview_factors(*size) == expected


def test_categorical_overviews_use_mode_so_no_class_is_invented(tmp_dir):
    tif = _tif(tmp_dir / "lu.tif", _checker())
    assert add_overviews(tif, categorical=True) == [2, 4]
    with rasterio.open(tif) as ds:
        assert ds.overviews(1) == [2, 4]
        small = ds.read(1, out_shape=(N // 4, N // 4))
    assert set(np.unique(small)) <= {1, 3}


def test_continuous_overviews_average(tmp_dir):
    tif = _tif(tmp_dir / "dem.tif", _checker(dtype="float32"), nodata=-9999)
    add_overviews(tif, categorical=False)
    with rasterio.open(tif) as ds:
        assert ds.read(1, out_shape=(N // 2, N // 2)).mean() == pytest.approx(2.0)


def test_add_overviews_is_idempotent_and_skips_small_rasters(tmp_dir):
    tif = _tif(tmp_dir / "lu.tif", _checker())
    add_overviews(tif, categorical=True)
    mtime = tif.stat().st_mtime_ns
    assert add_overviews(tif, categorical=True) == [2, 4]
    assert tif.stat().st_mtime_ns == mtime                     # not rebuilt
    small = _tif(tmp_dir / "small.tif", _checker(100))
    assert add_overviews(small, categorical=True) == []


def test_clip_processor_adds_overviews_and_can_skip_them(tmp_dir):
    src, boundary = _tif(tmp_dir / "lu.tif", _checker()), _boundary(tmp_dir)
    on = ClipItemConfig(src=src, dst=tmp_dir / "on.tif")
    off = ClipItemConfig(src=src, dst=tmp_dir / "off.tif")
    qa = ClipProcessor([on], boundary).run().qa
    ClipProcessor([off], boundary, overviews=False).run()
    with rasterio.open(on.dst) as a, rasterio.open(off.dst) as b:
        assert a.overviews(1) == [2, 4] and b.overviews(1) == []
    assert any(c.name == "overviews_added:on.tif" and c.status == "pass" for c in qa)


def test_up_to_date_raster_without_overviews_gets_them_without_reclipping(tmp_dir):
    src, boundary = _tif(tmp_dir / "lu.tif", _checker()), _boundary(tmp_dir)
    item = ClipItemConfig(src=src, dst=tmp_dir / "out.tif")
    ClipProcessor([item], boundary, overviews=False).run()     # an output from an older version
    qa = ClipProcessor([item], boundary).run().qa
    names = [c.name for c in qa]
    assert "clip_skipped:out.tif" in names and "overviews_added:out.tif" in names
    with rasterio.open(item.dst) as ds:
        assert ds.overviews(1) == [2, 4]


def test_build_adds_overviews_unless_switched_off(tmp_dir):
    dem = _tif(tmp_dir / "dem.tif", np.fromfunction(lambda r, c: r + c, (N, N), dtype="float32"), nodata=-9999)
    boundary = _boundary(tmp_dir)

    def build(**project):
        cfg = SWATPrepConfig.model_validate({
            "project": {"name": "t", "crs": "EPSG:32648", "output_dir": str(tmp_dir / "out"),
                        "boundary": str(boundary), **project},
            "dem": {"path": str(dem)}})
        assert SWATPrepProject(cfg).build().success
        with rasterio.open(tmp_dir / "out" / "spatial" / "dem_projected.tif") as ds:
            return ds.overviews(1)

    assert build(overviews=False) == []
    assert build() == [2, 4]                                   # second build: up to date, overviews added


def test_overviews_field_defaults_on_and_is_documented():
    field = ProjectConfig.model_fields["overviews"]
    assert field.default is True and "map" in field.description


def test_cli_clip_no_overviews(tmp_dir):
    from swatprep.cli import main

    src, boundary = _tif(tmp_dir / "lu.tif", _checker()), _boundary(tmp_dir)
    for flag, expected in (("--no-overviews", []), ("--overviews", [2, 4])):
        out = tmp_dir / f"o{flag}.tif"
        res = CliRunner().invoke(main, ["clip", str(src), str(boundary), str(out), flag])
        assert res.exit_code == 0, res.output
        with rasterio.open(out) as ds:
            assert ds.overviews(1) == expected


# ---------------------------------------------------------------------------- exact, faster scans


@pytest.mark.parametrize("dtype, nodata", [("uint8", 0), ("int16", -32768), ("int32", -1)])
def test_class_counts_equal_numpy_unique(tmp_dir, dtype, nodata):
    rng = np.random.default_rng(0)
    data = rng.integers(1, 40, (300, 300)).astype(dtype)
    data[:20] = nodata
    if dtype == "int32":
        data[50, 50] = 9_000_000                               # a code far from the others: no huge bincount
    tif = _tif(tmp_dir / "c.tif", data, nodata=nodata)
    valid = data[data != nodata]
    codes, counts = np.unique(valid, return_counts=True)
    with rasterio.open(tif) as ds:
        assert class_counts(ds, max_pixels=10_000) == dict(zip(codes.tolist(), counts.tolist()))
        assert unique_codes(ds) == set(codes.tolist())


def test_class_counts_respect_the_window(tmp_dir):
    from rasterio.windows import Window

    data = np.ones((100, 100), dtype="int16")
    data[:, 50:] = 2
    with rasterio.open(_tif(tmp_dir / "w.tif", data)) as ds:
        assert class_counts(ds, window=Window(60, 0, 40, 10)) == {2: 400}


def test_masked_stats_ignore_nan_and_nodata(tmp_dir):
    data = np.arange(100, dtype="float32").reshape(10, 10)
    data[0, 0], data[0, 1] = -9999, np.nan
    with rasterio.open(_tif(tmp_dir / "s.tif", data, nodata=-9999)) as ds:
        vmin, vmax, mean, n = masked_stats(ds, max_pixels=30)
    valid = data[(data != -9999) & ~np.isnan(data)]
    assert (vmin, vmax, n) == (2.0, 99.0, 98) and mean == pytest.approx(valid.mean())


def test_gdal_env_uses_all_cpus_unless_the_user_set_it(monkeypatch):
    monkeypatch.delenv("GDAL_NUM_THREADS", raising=False)
    with gdal_env():
        assert rasterio.env.getenv()["GDAL_NUM_THREADS"] == "ALL_CPUS"
    monkeypatch.setenv("GDAL_NUM_THREADS", "2")
    with gdal_env():
        assert rasterio.env.getenv()["GDAL_NUM_THREADS"] == "2"


# ---------------------------------------------------------------------------- statistics stored in the GeoTIFF


def test_store_stats_writes_gdal_statistics(tmp_dir):
    data = np.arange(10_000, dtype="float32").reshape(100, 100)
    data[0, :10] = -9999
    tif = _tif(tmp_dir / "dem.tif", data, nodata=-9999)
    store_stats(tif, categorical=False)
    valid = data[data != -9999]
    with rasterio.open(tif) as ds:
        tags = ds.tags(1)
    assert float(tags["STATISTICS_MINIMUM"]) == valid.min() and float(tags["STATISTICS_MAXIMUM"]) == valid.max()
    assert float(tags["STATISTICS_MEAN"]) == pytest.approx(valid.mean())
    assert float(tags["STATISTICS_STDDEV"]) == pytest.approx(valid.std(), rel=1e-6)
    assert float(tags["STATISTICS_VALID_PERCENT"]) == pytest.approx(99.9)


def test_store_stats_writes_class_counts_for_categorical_rasters(tmp_dir):
    import json

    data = _checker(100)
    data[0, 0] = 0
    tif = _tif(tmp_dir / "lu.tif", data)
    store_stats(tif, categorical=True)
    with rasterio.open(tif) as ds:
        counts = json.loads(ds.tags(1)[CLASS_COUNTS_TAG])
    assert counts == {"1": 5000, "3": 4999}


def test_clipped_outputs_carry_statistics(tmp_dir):
    src, boundary = _tif(tmp_dir / "lu.tif", _checker()), _boundary(tmp_dir)
    item = ClipItemConfig(src=src, dst=tmp_dir / "out.tif")
    ClipProcessor([item], boundary).run()
    with rasterio.open(item.dst) as ds:
        assert CLASS_COUNTS_TAG in ds.tags(1) and "STATISTICS_MAXIMUM" in ds.tags(1)
