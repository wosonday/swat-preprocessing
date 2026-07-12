"""Tests for SWATPrepProject API."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from swatprep.api import SWATPrepProject, PrepareResult
from swatprep.config import SWATPrepConfig
from swatprep.errors import ConfigError

_has_rasterio = importlib.util.find_spec("rasterio") is not None


def test_prepare_with_no_domains_succeeds_and_does_not_create_output_dir(tmp_dir):
    """With no domains configured, build() returns a result without touching the filesystem."""
    output_dir = tmp_dir / "output"
    cfg = SWATPrepConfig.model_validate({
        "project": {
            "name": "test_basin",
            "crs": "EPSG:32648",
            "output_dir": str(output_dir),
        }
    })
    project = SWATPrepProject(cfg)
    result = project.build()

    assert isinstance(result, PrepareResult)
    assert not output_dir.exists()   # no files written -> dir not created


def test_build_only_unknown_domain_raises(tmp_dir):
    cfg = SWATPrepConfig.model_validate({
        "project": {"name": "t", "crs": "EPSG:4326", "output_dir": str(tmp_dir / "out")}
    })
    project = SWATPrepProject(cfg)
    with pytest.raises(ConfigError):
        project.build(only="nonexistent")


def test_build_dem_without_rasterio_succeeds_with_warn(tmp_dir):
    """DEM domain runs; without rasterio it emits a warn but not a failure."""
    import swatprep.core.dem as dem_mod
    original = dem_mod._HAS_RASTERIO
    try:
        dem_mod._HAS_RASTERIO = False
        output_dir = tmp_dir / "output"
        dem_path = tmp_dir / "dem.tif"
        dem_path.write_bytes(b"")

        cfg = SWATPrepConfig.model_validate({
            "project": {
                "name": "t",
                "crs": "EPSG:4326",
                "output_dir": str(output_dir),
            },
            "dem": {"path": str(dem_path)},
        })
        result = SWATPrepProject(cfg).build(only="dem")

        assert result.success            # warn is not a failure
        assert result.warning_count > 0  # rasterio_missing warn was emitted
    finally:
        dem_mod._HAS_RASTERIO = original


@pytest.mark.skipif(
    not _has_rasterio,
    reason="rasterio not installed -- install swatprep[geo] to run this test",
)
def test_example_config_builds_end_to_end(tmp_dir):
    """Full pipeline end-to-end with example data (requires rasterio)."""
    cfg = SWATPrepConfig.from_yaml(Path("examples/config_minimal.yaml"))
    cfg.project.output_dir = tmp_dir / "example_output"

    result = SWATPrepProject(cfg).build()

    assert result.success
    assert result.manifest_path is not None
    assert (cfg.project.output_dir / "manifest.json").exists()
    assert (cfg.project.output_dir / "spatial" / "dem_info.json").exists()
    assert (cfg.project.output_dir / "landuse" / "landuse_lookup.csv").exists()
    assert (cfg.project.output_dir / "soil" / "usersoil.csv").exists()
    assert (cfg.project.output_dir / "weather" / "ST001.pcp").exists()
    assert (cfg.project.output_dir / "observed" / "streamflow_ST001.csv").exists()
