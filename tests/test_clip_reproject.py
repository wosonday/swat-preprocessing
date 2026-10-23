"""Clipped rasters are reprojected to project.crs (clip_raster, clip domain, per-domain clip)."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("rasterio")
gpd = pytest.importorskip("geopandas")

import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from swatprep.core.clip import ClipProcessor, clip_into_output
from swatprep.config import ClipItemConfig
from swatprep.utils.raster import clip_raster

LON0, LAT0, PX = 105.0, 21.0, 0.001          # ~111 m x ~104 m cells, EPSG:4326


def _geo_tif(path, data, dtype="int16", nodata=0):
    data = np.asarray(data, dtype)
    with rasterio.open(
        path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1,
        dtype=dtype, crs="EPSG:4326", transform=from_origin(LON0, LAT0, PX, PX), nodata=nodata,
    ) as ds:
        ds.write(data, 1)


@pytest.fixture
def geo(tmp_dir):
    """100 x 100 geographic raster of class codes + boundary (EPSG:4326) inside it."""
    codes = np.full((100, 100), 3, "int16"); codes[40:60, 40:60] = 7
    _geo_tif(tmp_dir / "lu.tif", codes)
    gpd.GeoDataFrame(geometry=[box(105.03, 20.93, 105.07, 20.97)], crs="EPSG:4326") \
        .to_file(tmp_dir / "b.geojson", driver="GeoJSON")
    return tmp_dir


def test_clip_reprojects_to_dst_crs(geo):
    out = clip_raster(geo / "lu.tif", geo / "o.tif", geo / "b.geojson", dst_crs="EPSG:32648")
    with rasterio.open(out) as ds:
        assert ds.crs.to_epsg() == 32648
        assert ds.res[0] > 1 and ds.res[1] > 1                    # metres, no longer degrees
        assert 30 < ds.width < 80


def test_clip_keeps_crs_without_dst_crs(geo):
    with rasterio.open(clip_raster(geo / "lu.tif", geo / "o.tif", geo / "b.geojson")) as ds:
        assert ds.crs.to_epsg() == 4326


def test_nearest_keeps_class_codes(geo):
    out = clip_raster(geo / "lu.tif", geo / "o.tif", geo / "b.geojson", dst_crs="EPSG:32648")
    with rasterio.open(out) as ds:
        assert set(np.unique(ds.read(1))) <= {0, 3, 7}            # no interpolated codes


def test_bilinear_interpolates_dem(geo):
    dem = np.fromfunction(lambda r, c: 10.0 * c, (100, 100)).astype("float32")
    _geo_tif(geo / "dem.tif", dem, "float32", nodata=-9999)
    out = clip_raster(geo / "dem.tif", geo / "d.tif", geo / "b.geojson",
                      dst_crs="EPSG:32648", resampling="bilinear")
    with rasterio.open(out) as ds:
        vals = ds.read(1)
        assert len(np.unique(vals)) > 50 and vals.min() >= 0       # smooth values, no codes


def test_resolution_sets_pixel_size(geo):
    out = clip_raster(geo / "lu.tif", geo / "o.tif", geo / "b.geojson",
                      dst_crs="EPSG:32648", resolution=30)
    with rasterio.open(out) as ds:
        assert ds.res == (30.0, 30.0)


def test_mask_works_after_reprojection(geo):
    gpd.GeoDataFrame(geometry=[box(105.03, 20.93, 105.05, 20.97)], crs="EPSG:4326") \
        .to_file(geo / "half.geojson", driver="GeoJSON")
    out = clip_raster(geo / "lu.tif", geo / "m.tif", geo / "half.geojson",
                      mask=True, dst_crs="EPSG:32648")
    with rasterio.open(out) as ds:
        a = ds.read(1)
        assert (a == 0).any() and (a == 3).any()


def test_unknown_resampling_is_rejected(geo):
    from swatprep.errors import InputValidationError
    with pytest.raises(InputValidationError):
        clip_raster(geo / "lu.tif", geo / "o.tif", geo / "b.geojson", resampling="magic")


def test_clip_processor_reclips_stale_crs(geo):
    """A clip made earlier in the source CRS must be redone once project.crs is set."""
    item = ClipItemConfig(src=geo / "lu.tif", dst=geo / "o" / "c.tif")
    ClipProcessor([item], geo / "b.geojson").run()                      # no reprojection
    with rasterio.open(item.dst) as ds:
        assert ds.crs.to_epsg() == 4326
    res = ClipProcessor([item], geo / "b.geojson", "EPSG:32648").run()
    assert any(q.name.startswith("clip_written") for q in res.qa)
    with rasterio.open(item.dst) as ds:
        assert ds.crs.to_epsg() == 32648
    res = ClipProcessor([item], geo / "b.geojson", "EPSG:32648").run()  # now up to date
    assert any(q.name.startswith("clip_skipped") for q in res.qa)


def test_clip_into_output_reprojects(geo):
    qa = []
    b = clip_into_output(geo / "lu.tif", "lu_clip.tif", geo / "out", geo / "b.geojson", True, qa,
                         dst_crs="EPSG:32648")
    assert b is not None
    with rasterio.open(geo / "out" / "lu_clip.tif") as ds:
        assert ds.crs.to_epsg() == 32648


def test_build_outputs_are_in_project_crs(geo):
    """Geographic DEM / land use / soil rasters come out of build() in EPSG:32648."""
    import pandas as pd
    from swatprep.api import SWATPrepProject
    from swatprep.config import SWATPrepConfig

    dem = np.fromfunction(lambda r, c: r + c + 1.0, (100, 100)).astype("float32")
    _geo_tif(geo / "dem.tif", dem, "float32", nodata=-9999)
    _geo_tif(geo / "so.tif", np.full((100, 100), 7, "int16"))
    pd.DataFrame({"code": [3, 7], "swat_code": ["AGRL", "FRST"], "swat_name": ["a", "f"]}) \
        .to_csv(geo / "lu.csv", index=False)
    pd.DataFrame({"soil_id": [7], "HYDGRP": ["B"], "SOL_ZMX": [1000], "NLAYERS": [1]}) \
        .to_csv(geo / "so.csv", index=False)
    cfg = SWATPrepConfig.model_validate({
        "project": {"name": "t", "crs": "EPSG:32648", "output_dir": str(geo / "out"),
                    "boundary": str(geo / "b.geojson")},
        "dem": {"path": str(geo / "dem.tif")},
        "landuse": {"raster": str(geo / "lu.tif"), "lookup": str(geo / "lu.csv")},
        "soil": {"raster": str(geo / "so.tif"), "table": str(geo / "so.csv")},
    })
    result = SWATPrepProject(cfg).build()
    assert result.success, [c for c in result.qa_checks if c.status == "fail"]
    for rel in ("spatial/dem_projected.tif", "landuse/landuse_clip.tif", "soil/soil_clip.tif"):
        with rasterio.open(geo / "out" / rel) as ds:
            assert ds.crs.to_epsg() == 32648, rel
    assert any(c.name == "dem_crs_reprojected" for c in result.qa_checks)
