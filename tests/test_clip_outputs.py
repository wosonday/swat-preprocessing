"""build with project.boundary: clipped rasters + basin-only tables go to ONE output_dir."""

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
from swatprep.config import SWATPrepConfig


def _tif(path, data):
    with rasterio.open(
        path, "w", driver="GTiff", height=10, width=10, count=1, dtype="int16",
        crs="EPSG:32648", transform=from_origin(500000, 1600000, 30, 30), nodata=0,
    ) as ds:
        ds.write(np.asarray(data, "int16"), 1)


@pytest.fixture
def project(tmp_dir):
    """Rasters 10 x 10; basin = columns 2..5 / rows 3..6. Codes 5 (land) and 7 (soil) occur
    only inside the basin; codes 9 (land) and 8 (soil) only outside."""
    dem = np.fromfunction(lambda r, c: 100 * r + c + 1, (10, 10))
    land = np.ones((10, 10)); land[3:7, 2:6] = 5; land[0, 0] = 9
    soil = np.full((10, 10), 4); soil[3:7, 2:6] = 7; soil[0, 0] = 8
    _tif(tmp_dir / "dem.tif", dem); _tif(tmp_dir / "lu.tif", land); _tif(tmp_dir / "so.tif", soil)
    gpd.GeoDataFrame(geometry=[box(500061, 1599791, 500179, 1599909)], crs="EPSG:32648") \
        .to_file(tmp_dir / "b.geojson", driver="GeoJSON")
    pd.DataFrame({"code": [1, 5, 9], "swat_code": ["AGRL", "FRST", "URBN"],
                  "swat_name": ["a", "f", "u"]}).to_csv(tmp_dir / "lu.csv", index=False)
    pd.DataFrame({"soil_id": [4, 7, 8], "HYDGRP": ["A", "B", "C"], "SOL_ZMX": [1000] * 3,
                  "NLAYERS": [1] * 3}).to_csv(tmp_dir / "so.csv", index=False)

    def make(**flags):
        return SWATPrepConfig.model_validate({
            "project": {"name": "t", "crs": "EPSG:32648", "output_dir": str(tmp_dir / "out"),
                        "boundary": str(tmp_dir / "b.geojson")},
            "dem": {"path": str(tmp_dir / "dem.tif"), **flags},
            "landuse": {"raster": str(tmp_dir / "lu.tif"), "lookup": str(tmp_dir / "lu.csv"),
                        **flags},
            "soil": {"raster": str(tmp_dir / "so.tif"), "table": str(tmp_dir / "so.csv"),
                     **flags},
        })
    return tmp_dir / "out", make


def test_build_writes_clipped_rasters_and_basin_tables_into_output_dir(project):
    out, make = project
    result = SWATPrepProject(make()).build()

    assert result.success, [c for c in result.qa_checks if c.status == "fail"]
    for rel in ("spatial/dem_projected.tif", "landuse/landuse_clip.tif", "soil/soil_clip.tif"):
        assert (out / rel).exists(), rel
    with rasterio.open(out / "spatial" / "dem_projected.tif") as ds:
        assert (ds.width, ds.height) == (4, 4)
    assert pd.read_csv(out / "landuse" / "landuse_lookup.csv")["code"].tolist() == [5]
    assert pd.read_csv(out / "soil" / "usersoil.csv")["SNAM"].tolist() == [7]
    assert pd.read_csv(out / "landuse" / "landuse_raster_codes.csv")["raster_code"].tolist() == [5]


def test_clip_false_keeps_old_behaviour(project):
    out, make = project
    result = SWATPrepProject(make(clip=False)).build()

    assert not list(out.rglob("*.tif"))
    assert pd.read_csv(out / "landuse" / "landuse_lookup.csv")["code"].tolist() == [1, 5, 9]
    assert pd.read_csv(out / "soil" / "usersoil.csv")["SNAM"].tolist() == [4, 7, 8]
    assert not any("boundary_window" in c.name for c in result.qa_checks)


def test_second_build_does_not_reclip_but_still_rebuilds_tables(project):
    out, make = project
    SWATPrepProject(make()).build()
    again = SWATPrepProject(make()).build()
    names = [c.name for c in again.qa_checks]
    assert "clip_skipped:dem_projected.tif" in names and "landuse_table_filtered" in names


def test_custom_output_names(project):
    out, make = project
    cfg = make()
    cfg.dem.output_name, cfg.landuse.output_name = "dem_chu.tif", "lu_chu.tif"
    SWATPrepProject(cfg).build()
    assert (out / "spatial" / "dem_chu.tif").exists() and (out / "landuse" / "lu_chu.tif").exists()
