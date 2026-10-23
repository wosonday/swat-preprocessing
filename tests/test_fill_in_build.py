"""One YAML: weather.fill.run_in_build makes `build` fill the gaps, export them, then build from them."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from swatprep.api import SWATPrepProject
from swatprep.config import SWATPrepConfig
from swatprep.errors import ConfigError

D = pd.date_range("2000-01-01", "2000-01-10")
NAN = np.nan


def _net(base, name, precip, tmax):
    d = base / name
    d.mkdir()
    pd.DataFrame([{"id": "S1", "name": "Sta1", "lat": 15.0, "lon": 105.0, "elev": 100}]) \
        .to_csv(d / "stations.csv", index=False)
    pd.DataFrame({"date": D.strftime("%Y-%m-%d"), "precip": precip, "tmax": tmax, "tmin": 20.0}) \
        .to_csv(d / "S1.csv", index=False)
    return d


@pytest.fixture
def make(tmp_dir):
    obs = _net(tmp_dir, "obs", [2, 4, NAN, 6, NAN, 0, 8, NAN, 10, 0], [30] * 10)
    grid = _net(tmp_dir, "grid", [1, 3, 5, 3, 4, 0, 4, NAN, 5, 0], [28] * 10)

    def cfg(run_in_build=True, **weather):
        return SWATPrepConfig.model_validate({
            "project": {"name": "t", "crs": "EPSG:32648", "output_dir": str(tmp_dir / "out"),
                        "targets": ["swat"]},
            "weather": {"stations": str(obs / "stations.csv"), "data_dir": str(obs),
                        "variables": ["precip", "tmax", "tmin"], "start": "2000-01-01",
                        "end": "2000-01-10", "missing_policy": "warn",
                        "fill": {"type": "csv", "output_dir": str(tmp_dir / "filled"),
                                 "min_overlap_days": 3, "run_in_build": run_in_build,
                                 "csv": {"stations": str(grid / "stations.csv"),
                                         "data_dir": str(grid)}},
                        **weather}})
    return cfg


def _pcp(tmp_dir):
    return [float(x) for x in (tmp_dir / "out" / "weather" / "pcp_Sta1.txt").read_text().split()[1:]]


def test_run_in_build_fills_exports_and_builds_from_filled(make, tmp_dir):
    result = SWATPrepProject(make()).build()
    assert result.success
    p = _pcp(tmp_dir)
    assert p[2] == pytest.approx(9.375) and p[4] == pytest.approx(7.5)   # ngày 3, 5 đã điền
    assert p[7] == -99.0                                                 # ngày 8: nguồn ngoài cũng thiếu
    assert (tmp_dir / "filled" / "S1.csv").exists() and (tmp_dir / "filled" / "fill_report.csv").exists()
    assert any(c.name == "weather_fill_in_build" for c in result.qa_checks)


def test_default_does_not_fill(make, tmp_dir):
    SWATPrepProject(make(run_in_build=False)).build()
    assert _pcp(tmp_dir)[2] == -99.0
    assert not (tmp_dir / "filled").exists()


def test_output_dir_must_differ_from_data_dir(make, tmp_dir):
    cfg = make()
    cfg.weather.fill.output_dir = cfg.weather.data_dir
    with pytest.raises(ConfigError, match="differ"):
        SWATPrepProject(cfg).build()


def test_run_in_build_rejects_split_networks(make, tmp_dir):
    cfg = make(precip={"stations": str(tmp_dir / "obs" / "stations.csv"), "data_dir": str(tmp_dir / "obs")})
    with pytest.raises(ConfigError, match="one station network"):
        SWATPrepProject(cfg).build()


def test_fill_writer_lists_only_stations_that_have_data(make, tmp_dir):
    """A station without a data file must not appear in the filled stations.csv."""
    obs = tmp_dir / "obs"
    st = pd.read_csv(obs / "stations.csv")
    pd.concat([st, st.assign(id="S2", name="Sta2")]).to_csv(obs / "stations.csv", index=False)
    SWATPrepProject(make()).build()
    assert pd.read_csv(tmp_dir / "filled" / "stations.csv")["id"].tolist() == ["S1"]
