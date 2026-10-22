"""`clip:` section of config.yaml: crop rasters to project.boundary (src -> dst) during build."""

from __future__ import annotations

import os

import numpy as np
import pytest
import yaml

pytest.importorskip("rasterio")
gpd = pytest.importorskip("geopandas")

import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from swatprep.api import SWATPrepProject
from swatprep.config import SWATPrepConfig


def _write(tmp_dir):
    """10 x 10 raster and a boundary covering its columns 2..5 / rows 3..6."""
    data = np.fromfunction(lambda r, c: 100 * r + c + 1, (10, 10)).astype("int16")
    with rasterio.open(
        tmp_dir / "src.tif", "w", driver="GTiff", height=10, width=10, count=1, dtype="int16",
        crs="EPSG:32648", transform=from_origin(500000, 1600000, 30, 30), nodata=0,
    ) as ds:
        ds.write(data, 1)
    gpd.GeoDataFrame(geometry=[box(500061, 1599791, 500179, 1599909)], crs="EPSG:32648") \
        .to_file(tmp_dir / "b.geojson", driver="GeoJSON")
    return data


def _config(tmp_dir, **extra):
    """Write a config.yaml with relative paths and load it (as the CLI does)."""
    cfg = {
        "project": {"name": "t", "crs": "EPSG:32648", "output_dir": "./out",
                    "boundary": "./b.geojson"},
        "clip": [{"src": "./src.tif", "dst": "./clipped/dem_clip.tif"}],
        **extra,
    }
    (tmp_dir / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return SWATPrepConfig.from_yaml(tmp_dir / "config.yaml")


def test_clip_section_resolves_relative_paths_and_is_a_domain(tmp_dir):
    _write(tmp_dir)
    cfg = _config(tmp_dir)
    assert cfg.clip[0].src == (tmp_dir / "src.tif").resolve()
    assert cfg.clip[0].dst.is_absolute() and cfg.clip[0].mask is False
    assert cfg.configured_domains() == ["clip"]


def test_clip_requires_project_boundary():
    with pytest.raises(ValueError, match="project.boundary"):
        SWATPrepConfig.model_validate({
            "project": {"name": "t", "crs": "EPSG:32648"},
            "clip": [{"src": "a.tif", "dst": "b.tif"}],
        })


def test_build_clip_writes_cropped_raster_then_skips_when_up_to_date(tmp_dir):
    data = _write(tmp_dir)
    cfg = _config(tmp_dir)
    first = SWATPrepProject(cfg).build(only="clip")
    assert first.success and any(c.name == "clip_written:dem_clip.tif" for c in first.qa_checks)
    with rasterio.open(cfg.clip[0].dst) as ds:
        assert np.array_equal(ds.read(1), data[3:7, 2:6])

    second = SWATPrepProject(cfg).build(only="clip")
    assert any(c.name == "clip_skipped:dem_clip.tif" for c in second.qa_checks)

    os.utime(cfg.clip[0].src, (2e9, 2e9))                      # source modified later -> redo
    third = SWATPrepProject(cfg).build(only="clip")
    assert any(c.name == "clip_written:dem_clip.tif" for c in third.qa_checks)


def test_clip_runs_before_dem_which_reads_the_clipped_file(tmp_dir):
    _write(tmp_dir)
    cfg = _config(tmp_dir, dem={"path": "./clipped/dem_clip.tif"})
    assert not cfg.dem.path.exists()
    assert all(c.status == "pass" for c in SWATPrepProject(cfg).validate()
               if "dem.path" in c.name)                        # "will be created by clip"
    result = SWATPrepProject(cfg).build()
    assert result.success
    info = (tmp_dir / "out" / "spatial" / "dem_info.json").read_text(encoding="utf-8")
    assert '"shape": [\n    4,\n    4\n  ]' in info


def test_clip_missing_source_fails_with_clear_check(tmp_dir):
    _write(tmp_dir)
    (tmp_dir / "src.tif").unlink()
    cfg = _config(tmp_dir)
    result = SWATPrepProject(cfg).build(only="clip")
    assert not result.success
    assert any(c.name.startswith("clip_src_missing") for c in result.qa_checks)
    assert any(c.status == "fail" and "clip[0].src" in c.name for c in SWATPrepProject(cfg).validate())
