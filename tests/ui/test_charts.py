import numpy as np
import pandas as pd

from app.services.climatology import monthly_climatology, monthly_values
from app.services.climatology import completeness
from app.ui.charts import climatology_chart, completeness_heatmap, fdc_chart, hydrograph, weather_detail


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
    spec = climatology_chart({"Observed": monthly_climatology(monthly_values(s, "mean"))}, "Mean monthly flow").to_dict()
    rows = next(iter(spec["datasets"].values()))
    assert len(rows) == 12 and rows[0]["years"] == "2/2"


def test_climatology_chart_compares_observed_and_filled():
    s = pd.Series(1.0, index=pd.date_range("2000-01-01", "2000-12-31"))
    clim = monthly_climatology(monthly_values(s, "sum"))
    spec = climatology_chart({"Observed": clim, "Filled": clim}, "Mean monthly total (mm)").to_dict()
    bars = spec["layer"][0]["encoding"]
    assert bars["xOffset"]["field"] == "series" and bars["color"]["field"] == "series"
    assert bars["color"]["scale"]["domain"] == ["Observed", "Filled"] == bars["xOffset"]["sort"]
    assert len(next(iter(spec["datasets"].values()))) == 24


def test_heatmap_encodes_station_month_and_missing_share():
    wide = pd.DataFrame({"ST1": [1.0, np.nan, 2.0]}, index=pd.date_range("2000-01-30", periods=3))
    spec = completeness_heatmap(completeness(wide), {"ST1": "Station one"}).to_dict()
    enc = spec["layer"][1]["encoding"]
    assert (enc["x"]["field"], enc["y"]["field"], enc["color"]["field"]) == ("period", "name", "pct_missing")
    rows = next(iter(spec["datasets"].values()))
    assert rows[0]["name"] == "Station one" and rows[0]["days"] == "1/2 days missing"


def test_weather_detail_shows_filled_points_and_remaining_gaps():
    days = pd.date_range("2000-01-01", periods=6)
    observed = pd.Series([1.0, np.nan, np.nan, 2.0, np.nan, 3.0], index=days)
    filled = pd.Series([1.0, 5.0, 6.0, 2.0, np.nan, 3.0], index=days)
    spec = weather_detail(observed, filled, "Precipitation (mm)", bars=True).to_dict()
    assert [layer["mark"]["type"] for layer in spec["layer"]] == ["bar", "point", "rule"]
    sizes = [len(spec["datasets"][layer["data"]["name"]]) for layer in spec["layer"]]
    assert sizes == [3, 2, 1]           # 3 observed, 2 filled, 1 still missing


def test_weather_detail_without_fill_marks_every_gap():
    observed = pd.Series([1.0, np.nan, 2.0], index=pd.date_range("2000-01-01", periods=3))
    spec = weather_detail(observed, None, "Max temperature (degC)").to_dict()
    assert [layer["mark"]["type"] for layer in spec["layer"]] == ["line", "rule"]
