import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.explore_data import load_config, load_streamflow, load_weather, station_series


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


def test_load_weather_keeps_missing_days(filled_project):
    view = load_weather(load_config(filled_project)[0])
    assert view.error is None and set(view.observed) == {"precip", "tmax", "tmin"}
    precip = view.observed["precip"]["ST001"]
    assert len(precip) == 10 and int(precip.isna().sum()) == 2


def test_load_weather_reads_the_filled_copy_and_report(filled_project):
    view = load_weather(load_config(filled_project)[0])
    assert view.filled is not None and int(view.filled["precip"]["ST001"].isna().sum()) == 0
    assert view.fill_report.loc[0, "correction_type"] == "ratio" and view.fill_note is None


def test_fill_not_run_yet(filled_project):
    shutil.rmtree(filled_project.parent / "data" / "filled")
    view = load_weather(load_config(filled_project)[0])
    assert view.filled is None and view.fill_note.startswith("No filled data yet")


def test_missing_policy_fail_does_not_stop_explore(filled_project):
    cfg = load_config(filled_project)[0]
    assert cfg.weather.missing_policy == "fail"
    assert load_weather(cfg).error is None


def test_unreadable_weather_is_an_error(example_project):
    shutil.rmtree(example_project.parent / "data" / "weather")
    view = load_weather(load_config(example_project)[0])
    assert view.error and not view.observed
