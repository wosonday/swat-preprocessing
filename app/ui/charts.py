"""Altair charts for the Explore views (data in, alt.Chart out)."""
from __future__ import annotations

import altair as alt
import pandas as pd

from app.services.flow_stats import fdc, flow_quantile

MISSING = "#f04142"   # theme red
LABEL = "#757575"     # readable on the light (#ffffff) and dark (#202020) backgrounds
UNITS = {"m3s": "m³/s", "mm": "mm"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
HEIGHT = 260


def hydrograph(series: pd.Series, units: str, log: bool = False) -> alt.LayerChart:
    df = pd.DataFrame({"date": series.index, "flow": series.to_numpy(dtype=float)})
    drop = df["flow"].isna() | ((df["flow"] <= 0) if log else False)
    df["segment"] = drop.cumsum()   # a new line after every dropped day: gaps are not bridged
    zoom = alt.selection_interval(bind="scales", encodings=["x"])
    line = alt.Chart(df[~drop]).mark_line(strokeWidth=1).encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("flow:Q", title=f"Flow ({UNITS[units]})", scale=alt.Scale(type="log" if log else "linear")),
        detail="segment:N",
        tooltip=[alt.Tooltip("date:T"), alt.Tooltip("flow:Q", format=",.3f")],
    ).add_params(zoom)
    missing = alt.Chart(df[df["flow"].isna()]).mark_rule(color=MISSING, opacity=0.4).encode(
        x="date:T", tooltip=[alt.Tooltip("date:T", title="Missing")])
    return alt.layer(line, missing).properties(height=HEIGHT)


def fdc_chart(series: pd.Series, units: str) -> alt.LayerChart:
    positive = series[series > 0]
    curve = fdc(positive)
    marks = pd.DataFrame([{"label": f"Q{p}", "exceedance_pct": p, "flow": flow_quantile(series, p)}
                          for p in (5, 50, 95)])
    marks = marks[marks["flow"] > 0]
    y = alt.Y("flow:Q", title=f"Flow ({UNITS[units]})", scale=alt.Scale(type="log"))
    x = alt.X("exceedance_pct:Q", title="Time flow is exceeded (%)", scale=alt.Scale(domain=[0, 100]))
    line = alt.Chart(curve).mark_line().encode(x=x, y=y)
    points = alt.Chart(marks).mark_point(filled=True, size=50).encode(
        x=x, y=y, tooltip=["label:N", alt.Tooltip("flow:Q", format=",.3f")])
    labels = points.mark_text(align="left", dx=6, dy=-6, color=LABEL).encode(text="label:N")
    return alt.layer(line, points, labels).properties(height=HEIGHT)


def climatology_chart(clim: pd.DataFrame, title: str) -> alt.LayerChart:
    df = clim.assign(
        name=[MONTHS[m - 1] for m in clim["month"]],
        years=[f"{v}/{n}" for v, n in zip(clim["n_valid"], clim["n_years"])],
        label_y=clim["mean"].fillna(0),
    )
    x = alt.X("name:N", sort=MONTHS, title=None, axis=alt.Axis(labelAngle=0))
    bars = alt.Chart(df).mark_bar().encode(
        x=x, y=alt.Y("mean:Q", title=title),
        opacity=alt.condition("datum.ok", alt.value(1.0), alt.value(0.35)),
        tooltip=[alt.Tooltip("name:N", title="Month"), alt.Tooltip("mean:Q", format=",.2f"),
                 alt.Tooltip("years:N", title="Valid years")],
    )
    labels = alt.Chart(df).mark_text(dy=-6, fontSize=11, color=LABEL).encode(x=x, y="label_y:Q", text="years:N")
    return alt.layer(bars, labels).properties(height=HEIGHT)
