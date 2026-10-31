import numpy as np
import pandas as pd

from app.services.climatology import monthly_climatology, monthly_values
from app.ui.charts import climatology_chart, fdc_chart, hydrograph


def flow() -> pd.Series:
    s = pd.Series(np.linspace(1, 20, 40), index=pd.date_range("2000-01-01", periods=40))
    s.iloc[5:8] = np.nan
    s.iloc[20] = 0.0
    return s


def y_scale(chart) -> str | None:
    return chart.to_dict()["layer"][0]["encoding"]["y"].get("scale", {}).get("type")


def test_hydrograph_log_toggle():
    assert y_scale(hydrograph(flow(), "m3s")) == "linear"
    assert y_scale(hydrograph(flow(), "m3s", log=True)) == "log"


def test_hydrograph_marks_missing_days_and_breaks_the_line():
    spec = hydrograph(flow(), "m3s").to_dict()
    datasets = spec["datasets"]
    sizes = sorted(len(rows) for rows in datasets.values())
    assert sizes == [3, 37]                       # 3 missing ticks, 37 plotted days
    assert spec["layer"][0]["encoding"]["detail"]["field"] == "segment"


def test_hydrograph_log_drops_zero_flow():
    sizes = sorted(len(rows) for rows in hydrograph(flow(), "m3s", log=True).to_dict()["datasets"].values())
    assert sizes == [3, 36]


def test_fdc_is_log_and_labels_quantiles():
    spec = fdc_chart(flow(), "m3s").to_dict()
    assert spec["layer"][0]["encoding"]["y"]["scale"]["type"] == "log"
    labels = [row["label"] for rows in spec["datasets"].values() for row in rows if "label" in row]
    assert labels == ["Q5", "Q50", "Q95"]


def test_climatology_chart_has_twelve_bars_with_year_labels():
    s = pd.Series(1.0, index=pd.date_range("2000-01-01", "2001-12-31"))
    spec = climatology_chart(monthly_climatology(monthly_values(s, "mean")), "Mean monthly flow").to_dict()
    rows = next(iter(spec["datasets"].values()))
    assert len(rows) == 12 and rows[0]["years"] == "2/2"
