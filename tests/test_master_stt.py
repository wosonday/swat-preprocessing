"""master_pcp.txt / master_tmp.txt: ID is the serial number (STT) 1..N, not the source station id."""

from __future__ import annotations

import pandas as pd
import pytest

from swatprep.api import SWATPrepProject
from swatprep.config import SWATPrepConfig

D = pd.date_range("2000-01-01", "2000-01-05")


def _network(base, name, ids):
    d = base / name
    d.mkdir()
    rows = [{"id": i, "name": f"N{i}", "lat": 15 + k * 0.1, "lon": 105.0, "elev": 100 + k}
            for k, i in enumerate(ids)]
    pd.DataFrame(rows).to_csv(d / "stations.csv", index=False)
    for i in ids:
        pd.DataFrame({"date": D.strftime("%Y-%m-%d"), "precip": [1.0] * 5,
                      "tmax": [30.0] * 5, "tmin": [20.0] * 5}).to_csv(d / f"{i}.csv", index=False)
    return d


def _build(tmp_dir, weather):
    cfg = SWATPrepConfig.model_validate({
        "project": {"name": "t", "crs": "EPSG:32648", "output_dir": str(tmp_dir / "out"),
                    "targets": ["swat"]},
        "weather": {"variables": ["precip", "tmax", "tmin"], "start": "2000-01-01",
                    "end": "2000-01-05", **weather}})
    result = SWATPrepProject(cfg).build()
    assert result.success, [c for c in result.qa_checks if c.status == "fail"]
    return tmp_dir / "out" / "weather"


def test_master_id_is_serial_number_in_station_order(tmp_dir):
    d = _network(tmp_dir, "net", ["ST009", "ST002", "ST005"])        # id không tăng dần
    out = _build(tmp_dir, {"stations": str(d / "stations.csv"), "data_dir": str(d)})
    for name in ("master_pcp.txt", "master_tmp.txt"):
        m = pd.read_csv(out / name)
        assert list(m.columns) == ["ID", "NAME", "LAT", "LONG", "ELEVATION"]
        assert m["ID"].tolist() == [1, 2, 3]
    assert pd.read_csv(out / "master_pcp.txt")["NAME"].tolist() == ["pcp_NST009", "pcp_NST002", "pcp_NST005"]


def test_pcp_and_tmp_masters_are_numbered_separately(tmp_dir):
    p = _network(tmp_dir, "p", ["A1", "A2", "A3"])
    t = _network(tmp_dir, "t", ["B7", "B8"])
    out = _build(tmp_dir, {
        "precip": {"stations": str(p / "stations.csv"), "data_dir": str(p)},
        "temp": {"stations": str(t / "stations.csv"), "data_dir": str(t)}})
    assert pd.read_csv(out / "master_pcp.txt")["ID"].tolist() == [1, 2, 3]
    assert pd.read_csv(out / "master_tmp.txt")["ID"].tolist() == [1, 2]
