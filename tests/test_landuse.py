"""Tests for LandUsePreprocessor and LandUseWriter."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from swatprep.config import LandUseConfig
from swatprep.core.landuse import LandUsePreprocessor
from swatprep.errors import InputValidationError
from swatprep.qa import failures


def _make_cfg(raster_path, lookup_path, **kwargs) -> LandUseConfig:
    return LandUseConfig(raster=raster_path, lookup=lookup_path, **kwargs)


def _write_landuse_raster(path, values):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    data = np.array(values, dtype="int16")
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
        nodata=0,
    ) as ds:
        ds.write(data, 1)


# ---------------------------------------------------------------------------
# Lookup CSV loading
# ---------------------------------------------------------------------------


def test_lookup_loads(landuse_lookup_csv, tmp_dir):
    dummy_raster = tmp_dir / "lu.tif"
    dummy_raster.write_bytes(b"")
    cfg = _make_cfg(dummy_raster, landuse_lookup_csv)
    result = LandUsePreprocessor(cfg).run()
    assert len(result.lookup) == 4
    assert "swat_code" in result.lookup.columns


def test_lookup_missing_column_raises(tmp_dir):
    bad_lookup = tmp_dir / "bad.csv"
    bad_lookup.write_text("code,swat_code\n10,AGRL\n", encoding="utf-8")  # missing swat_name
    dummy_raster = tmp_dir / "lu.tif"
    dummy_raster.write_bytes(b"")
    cfg = _make_cfg(dummy_raster, bad_lookup)
    with pytest.raises(InputValidationError, match="missing columns"):
        LandUsePreprocessor(cfg).run()


def test_custom_column_names(tmp_dir):
    lookup = tmp_dir / "custom.csv"
    lookup.write_text(
        "src,sc,sn\n10,AGRL,Agriculture\n20,FRST,Forest\n",
        encoding="utf-8",
    )
    dummy_raster = tmp_dir / "lu.tif"
    dummy_raster.write_bytes(b"")
    cfg = _make_cfg(
        dummy_raster, lookup,
        source_code_col="src", swat_code_col="sc", swat_name_col="sn"
    )
    result = LandUsePreprocessor(cfg).run()
    assert len(result.lookup) == 2


def test_duplicate_codes_produce_warn_qa(tmp_dir):
    lookup = tmp_dir / "dup.csv"
    lookup.write_text(
        "code,swat_code,swat_name\n10,AGRL,Agri\n10,FRST,Forest\n",
        encoding="utf-8",
    )
    dummy_raster = tmp_dir / "lu.tif"
    dummy_raster.write_bytes(b"")
    cfg = _make_cfg(dummy_raster, lookup)
    result = LandUsePreprocessor(cfg).run()
    assert any(c.name == "landuse_lookup_duplicates" for c in result.qa)


# ---------------------------------------------------------------------------
# Rasterio not installed → graceful degradation
# ---------------------------------------------------------------------------


def test_no_rasterio_produces_warn_and_none_codes(landuse_lookup_csv, tmp_dir):
    """Without rasterio, raster_codes is None and a warn QA check is emitted."""
    import swatprep.core.landuse as mod
    original = mod._HAS_RASTERIO
    try:
        mod._HAS_RASTERIO = False
        dummy_raster = tmp_dir / "lu.tif"
        dummy_raster.write_bytes(b"")
        cfg = _make_cfg(dummy_raster, landuse_lookup_csv)
        result = LandUsePreprocessor(cfg).run()
        assert result.raster_codes is None
        assert any("rasterio" in c.name for c in result.qa)
        assert not failures(result.qa)  # warn, not fail
    finally:
        mod._HAS_RASTERIO = original


def test_no_rasterio_unmatched_is_empty_set(landuse_lookup_csv, tmp_dir):
    import swatprep.core.landuse as mod
    original = mod._HAS_RASTERIO
    try:
        mod._HAS_RASTERIO = False
        dummy_raster = tmp_dir / "lu.tif"
        dummy_raster.write_bytes(b"")
        result = LandUsePreprocessor(_make_cfg(dummy_raster, landuse_lookup_csv)).run()
        assert result.unmatched_codes == set()
    finally:
        mod._HAS_RASTERIO = original


# ---------------------------------------------------------------------------
# LandUseWriter
# ---------------------------------------------------------------------------


def test_landuse_writer_creates_lookup_csv(landuse_lookup_csv, tmp_dir):
    from swatprep.writers.landuse import LandUseWriter
    import swatprep.core.landuse as mod

def test_landuse_writer_creates_lookup_csv(landuse_lookup_csv, tmp_dir):
    from swatprep.writers.landuse import LandUseWriter
    import swatprep.core.landuse as mod

    original = mod._HAS_RASTERIO
    try:
        mod._HAS_RASTERIO = False
        dummy_raster = tmp_dir / "lu.tif"
        dummy_raster.write_bytes(b"")
        cfg = _make_cfg(dummy_raster, landuse_lookup_csv)
        result = LandUsePreprocessor(cfg).run()
        out = tmp_dir / "lu_out"
        written = LandUseWriter(result, out).write()
        names = [p.name for p in written]
        assert "landuse_lookup.csv" in names
    finally:
        mod._HAS_RASTERIO = original
