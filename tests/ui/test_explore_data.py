from pathlib import Path

import numpy as np
import pandas as pd

from app.services.explore_data import load_config, load_streamflow, station_series


def test_load_config_reports_schema_problems(tmp_path: Path):
    bad = tmp_path / "config.yaml"
    bad.write_text("project:\n  name: x\n", encoding="utf-8")   # crs missing
    cfg, error = load_config(bad)
    assert cfg is None and error.startswith("Config is not valid (1 problem(s))")


def test_load_streamflow_reads_the_example(example_project):
    cfg, error = load_config(example_project)
    view = load_streamflow(cfg)
    assert error is None and view.error is None and view.units == "m3s"
    assert list(view.daily.columns) == ["ST001"] and len(view.daily) == 10


def test_absent_days_become_nan(example_project):
    csv = example_project.parent / "data" / "streamflow.csv"
    lines = csv.read_text(encoding="utf-8").splitlines()
    csv.write_text("\n".join(lines[:4] + lines[6:]) + "\n", encoding="utf-8")   # drop Jan 4 and Jan 5
    view = load_streamflow(load_config(example_project)[0])
    assert len(view.daily) == 10 and int(view.daily["ST001"].isna().sum()) == 2


def test_unreadable_streamflow_is_an_error_not_an_exception(example_project):
    (example_project.parent / "data" / "streamflow.csv").unlink()
    view = load_streamflow(load_config(example_project)[0])
    assert view.error and view.daily.empty


def test_station_series_trims_to_observed_period():
    wide = pd.DataFrame({"A": [np.nan, 1.0, np.nan, 2.0, np.nan]}, index=pd.date_range("2000-01-01", periods=5))
    s = station_series(wide, "A")
    assert s.index[0] == pd.Timestamp("2000-01-02") and s.index[-1] == pd.Timestamp("2000-01-04")
