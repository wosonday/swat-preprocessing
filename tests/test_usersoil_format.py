"""usersoil.csv follows the SWAT+ Editor layout (examples/example_usersoil_swatplus.csv)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from swatprep.config import SoilConfig
from swatprep.core.soil import USERSOIL_COLUMNS, SoilPreprocessor, format_usersoil
from swatprep.writers.soil import SoilWriter

EXAMPLE = Path(__file__).parent.parent / "examples" / "example_usersoil_swatplus.csv"


def test_layout_matches_swatplus_example():
    assert list(pd.read_csv(EXAMPLE).columns) == USERSOIL_COLUMNS
    assert len(USERSOIL_COLUMNS) == 152


def test_example_round_trips_unchanged():
    ex = pd.read_csv(EXAMPLE)
    out, ids, snam = format_usersoil(ex.assign(soil_id=ex["SEQN"]), "soil_id", [])
    pd.testing.assert_frame_equal(out, ex, check_dtype=False)
    assert snam.tolist() == ex["SNAM"].tolist()


def test_key_column_dropped_and_missing_columns_defaulted():
    t = pd.DataFrame({"soil_id": [5, 7], "SNAM": ["A", "B"], "HYDGRP": ["B", "C"],
                      "SOL_ZMX": [1000.0, 800.0], "NLAYERS": [1, 1], "SOL_Z1": [300, 250]})
    qa = []
    out, ids, snam = format_usersoil(t, "soil_id", qa)
    assert list(out.columns) == USERSOIL_COLUMNS
    assert out["ANION_EXCL"].tolist() == [0.5, 0.5] and out["SOL_PH10"].tolist() == [0, 0]
    assert out["OBJECTID"].tolist() == [1, 2]                         # không có OBJECTID -> 1..N
    assert any(c.name == "usersoil_formatted" and "soil_id" in c.message for c in qa)


def test_identical_rows_merged_and_conflicting_snam_renamed():
    base = {"HYDGRP": "C", "SOL_ZMX": 900.0, "NLAYERS": 1, "SOL_Z1": 300}
    t = pd.DataFrame([
        {"soil_id": 1, "SNAM": "X", **base},
        {"soil_id": 1, "SNAM": "X", **base},                          # trùng hệt -> gộp
        {"soil_id": 1, "SNAM": "X", **{**base, "SOL_ZMX": 500.0}},    # cùng tên, khác dữ liệu
        {"soil_id": 2, "SNAM": "X", **{**base, "SOL_ZMX": 500.0}},    # giống hàng 3, mã khác
    ])
    qa = []
    out, ids, snam = format_usersoil(t, "soil_id", qa)
    assert out["SNAM"].tolist() == ["X", "X_2"] and out["SNAM"].is_unique
    assert snam.tolist() == ["X", "X", "X_2", "X_2"]                  # vlookup khớp usersoil
    names = {c.name: c.status for c in qa}
    assert names["usersoil_duplicates_merged"] == "pass" and names["usersoil_snam_renamed"] == "warn"


def test_writer_outputs_swat_layout_and_raw_option(tmp_path):
    src = tmp_path / "s.csv"
    pd.DataFrame({"soil_id": [5], "SNAM": ["A"], "HYDGRP": ["B"], "SOL_ZMX": [1000.0],
                  "NLAYERS": [1]}).to_csv(src, index=False)
    ras = tmp_path / "r.tif"; ras.write_bytes(b"")
    for fmt, cols in (("swat", USERSOIL_COLUMNS), ("raw", ["soil_id", "SNAM", "HYDGRP", "SOL_ZMX", "NLAYERS"])):
        res = SoilPreprocessor(SoilConfig(raster=ras, table=src, usersoil_format=fmt)).run()
        SoilWriter(res, tmp_path / fmt).write()
        assert list(pd.read_csv(tmp_path / fmt / "usersoil.csv").columns) == cols
    assert pd.read_csv(tmp_path / "swat" / "usersoil.csv")["SOL_ZMX"].tolist() == [1000]
    assert "1000.0" not in (tmp_path / "swat" / "usersoil.csv").read_text()
