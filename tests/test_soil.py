"""Tests for SoilPreprocessor and SoilWriter."""

from __future__ import annotations

import numpy as np
import pytest

from swatprep.config import SoilConfig
from swatprep.core.soil import SoilPreprocessor
from swatprep.errors import InputValidationError
from swatprep.qa import failures, warnings


def _make_cfg(raster_path, table_path, **kwargs) -> SoilConfig:
    return SoilConfig(raster=raster_path, table=table_path, **kwargs)


def _write_soil_raster(path, values):
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
# Soil table loading
# ---------------------------------------------------------------------------


def test_soil_table_loads(soil_table_csv, tmp_dir):
    dummy_raster = tmp_dir / "soil.tif"
    dummy_raster.write_bytes(b"")
    cfg = _make_cfg(dummy_raster, soil_table_csv)
    result = SoilPreprocessor(cfg).run()
    assert len(result.soil_table) == 3
    assert "HYDGRP" in result.soil_table.columns


def test_soil_table_missing_key_col_raises(tmp_dir):
    bad_table = tmp_dir / "bad_soil.csv"
    bad_table.write_text("HYDGRP,SOL_ZMX\nB,1500\n", encoding="utf-8")
    dummy_raster = tmp_dir / "soil.tif"
    dummy_raster.write_bytes(b"")
    cfg = _make_cfg(dummy_raster, bad_table)
    with pytest.raises(InputValidationError, match="missing key column"):
        SoilPreprocessor(cfg).run()


def test_missing_required_swat_cols_produce_fail_qa(tmp_dir):
    # Table has key col but missing HYDGRP, SOL_ZMX, NLAYERS
    table = tmp_dir / "minimal.csv"
    table.write_text("soil_id,SOL_Z1\n1001,300\n", encoding="utf-8")
    dummy_raster = tmp_dir / "soil.tif"
    dummy_raster.write_bytes(b"")
    cfg = _make_cfg(dummy_raster, table)
    result = SoilPreprocessor(cfg).run()
    assert any(c.name == "soil_missing_required_cols" for c in result.qa)
    assert failures(result.qa)  # fail, not just warn


def test_missing_layer1_cols_produce_warn_qa(tmp_dir):
    # Has required cols but missing layer-1 detail columns
    table = tmp_dir / "no_layers.csv"
    table.write_text(
        "soil_id,HYDGRP,SOL_ZMX,NLAYERS\n1001,B,1500,2\n",
        encoding="utf-8",
    )
    dummy_raster = tmp_dir / "soil.tif"
    dummy_raster.write_bytes(b"")
    cfg = _make_cfg(dummy_raster, table)
    result = SoilPreprocessor(cfg).run()
    assert any(c.name == "soil_missing_layer1_cols" for c in result.qa)


def test_invalid_hydgrp_produces_warn(tmp_dir):
    table = tmp_dir / "bad_grp.csv"
    table.write_text(
        "soil_id,HYDGRP,SOL_ZMX,NLAYERS\n1001,X,1500,1\n",
        encoding="utf-8",
    )
    dummy_raster = tmp_dir / "soil.tif"
    dummy_raster.write_bytes(b"")
    result = SoilPreprocessor(_make_cfg(dummy_raster, table)).run()
    assert any(c.name == "soil_invalid_hydgrp" for c in result.qa)


# ---------------------------------------------------------------------------
# Rasterio not installed → graceful degradation
# ---------------------------------------------------------------------------


def test_no_rasterio_produces_warn_and_none_codes(soil_table_csv, tmp_dir):
    import swatprep.core.soil as mod
    original = mod._HAS_RASTERIO
    try:
        mod._HAS_RASTERIO = False
        dummy_raster = tmp_dir / "soil.tif"
        dummy_raster.write_bytes(b"")
        result = SoilPreprocessor(_make_cfg(dummy_raster, soil_table_csv)).run()
        assert result.raster_codes is None
        assert not failures(result.qa)
    finally:
        mod._HAS_RASTERIO = original


# ---------------------------------------------------------------------------
# SoilWriter
# ---------------------------------------------------------------------------


def test_soil_writer_creates_usersoil(soil_table_csv, tmp_dir):
    from swatprep.writers.soil import SoilWriter
    import swatprep.core.soil as mod

    original = mod._HAS_RASTERIO
    try:
        mod._HAS_RASTERIO = False
        dummy_raster = tmp_dir / "soil.tif"
        dummy_raster.write_bytes(b"")
        result = SoilPreprocessor(_make_cfg(dummy_raster, soil_table_csv)).run()
        out = tmp_dir / "soil_out"
        written = SoilWriter(result, out).write()
        names = [p.name for p in written]
        assert "usersoil.csv" in names
    finally:
        mod._HAS_RASTERIO = original


def test_usersoil_csv_has_same_rows_as_input(soil_table_csv, tmp_dir):
    import pandas as pd
    from swatprep.writers.soil import SoilWriter
    import swatprep.core.soil as mod

    original = mod._HAS_RASTERIO
    try:
        mod._HAS_RASTERIO = False
        dummy_raster = tmp_dir / "soil.tif"
        dummy_raster.write_bytes(b"")
        result = SoilPreprocessor(_make_cfg(dummy_raster, soil_table_csv)).run()
        out = tmp_dir / "soil_out2"
        SoilWriter(result, out).write()
        written_df = pd.read_csv(out / "usersoil.csv")
        # Written rows should match input rows
        assert len(written_df) == len(result.soil_table)
    finally:
        mod._HAS_RASTERIO = original
