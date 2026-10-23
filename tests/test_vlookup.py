"""VLOOKUP tables (raster value -> SWAT code / soil name) written by build()."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("rasterio")
import rasterio
from rasterio.transform import from_origin

from swatprep.api import SWATPrepProject
from swatprep.config import SWATPrepConfig


def _tif(path, data):
    with rasterio.open(path, "w", driver="GTiff", height=4, width=4, count=1, dtype="int16",
                       crs="EPSG:32648", transform=from_origin(500000, 1600000, 30, 30),
                       nodata=-1) as ds:
        ds.write(np.asarray(data, "int16"), 1)


@pytest.fixture
def make(tmp_dir):
    lu = np.full((4, 4), 10); lu[0, 0] = 50
    so = np.full((4, 4), 7); so[0, 0] = 5
    _tif(tmp_dir / "lu.tif", lu); _tif(tmp_dir / "so.tif", so)
    pd.DataFrame({"ID": [50, 10, 10, 80], "CODE": ["URBN", "FRST", "AGRL", "WATR"]}) \
        .to_csv(tmp_dir / "lu.csv", index=False)                       # 10 bị lặp, 80 không có trong raster
    pd.DataFrame({"SOIL_ID": [7, 5, 5], "SNAM": ["B", "A", "A2"], "HYDGRP": ["B", "A", "A"],
                  "SOL_ZMX": [1000] * 3, "NLAYERS": [1] * 3}).to_csv(tmp_dir / "so.csv", index=False)

    def build(landuse=None, soil=None):
        cfg = SWATPrepConfig.model_validate({
            "project": {"name": "t", "crs": "EPSG:32648", "output_dir": str(tmp_dir / "out")},
            "landuse": {"raster": str(tmp_dir / "lu.tif"), "lookup": str(tmp_dir / "lu.csv"),
                        "source_code_col": "ID", "swat_code_col": "CODE", "swat_name_col": "CODE",
                        **(landuse or {})},
            "soil": {"raster": str(tmp_dir / "so.tif"), "table": str(tmp_dir / "so.csv"),
                     "soil_key_col": "SOIL_ID", **(soil or {})}})
        return SWATPrepProject(cfg).build(), tmp_dir / "out"
    return build


def test_landuse_vlookup_has_qswat_columns_one_row_per_value(make):
    result, out = make()
    vl = pd.read_csv(out / "landuse" / "landuse_vlookup.csv")
    assert list(vl.columns) == ["LANDUSE_ID", "SWAT_CODE"]
    assert vl.to_dict("records") == [{"LANDUSE_ID": 10, "SWAT_CODE": "FRST"},   # lặp: giữ hàng đầu
                                     {"LANDUSE_ID": 50, "SWAT_CODE": "URBN"},
                                     {"LANDUSE_ID": 80, "SWAT_CODE": "WATR"}]
    assert any(c.name == "landuse_vlookup" for c in result.qa_checks)


def test_soil_vlookup_keeps_first_snam_and_warns_on_duplicates(make):
    result, out = make()
    vl = pd.read_csv(out / "soil" / "soil_vlookup.csv")
    assert list(vl.columns) == ["SOIL_ID", "SNAM"]
    assert vl.to_dict("records") == [{"SOIL_ID": 5, "SNAM": "A"}, {"SOIL_ID": 7, "SNAM": "B"}]
    assert any(c.name == "soil_vlookup_duplicates" and c.status == "warn" for c in result.qa_checks)
    assert len(pd.read_csv(out / "soil" / "usersoil.csv")) == 3         # usersoil.csv giữ đủ


def test_output_lookup_false_skips_files(make):
    _, out = make(landuse={"output_lookup": False}, soil={"output_lookup": False})
    assert not (out / "landuse" / "landuse_vlookup.csv").exists()
    assert not (out / "soil" / "soil_vlookup.csv").exists()


def test_soil_without_snam_column_swat_format_generates_snam(make, tmp_dir):
    pd.read_csv(tmp_dir / "so.csv").drop(columns="SNAM").to_csv(tmp_dir / "so.csv", index=False)
    result, out = make()
    vl = pd.read_csv(out / "soil" / "soil_vlookup.csv")
    assert vl["SNAM"].astype(str).tolist() == ["5", "7"]               # SNAM = mã đất
    assert any(c.name == "usersoil_snam_generated" and c.status == "warn" for c in result.qa_checks)


def test_soil_without_snam_column_raw_format_warns_and_skips(make, tmp_dir):
    pd.read_csv(tmp_dir / "so.csv").drop(columns="SNAM").to_csv(tmp_dir / "so.csv", index=False)
    result, out = make(soil={"usersoil_format": "raw"})
    assert not (out / "soil" / "soil_vlookup.csv").exists()
    assert any(c.name == "soil_vlookup_skipped" for c in result.qa_checks)
