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
OBSERVED = "#8a8a8a"  # neutral grey line for measured values
FILLED = "#ff7528"    # theme orange for gap-filled values
SERIES = [OBSERVED, FILLED]       # colours of the Observed and Filled series


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


def climatology_chart(clims: dict[str, pd.DataFrame], title: str) -> alt.LayerChart:
    """Bars per month (one per series, side by side when more than one); label = valid years / years."""
    df = pd.concat([c.assign(series=name) for name, c in clims.items()], ignore_index=True)
    df = df.assign(
        name=[MONTHS[m - 1] for m in df["month"]],
        years=[f"{v}/{n}" for v, n in zip(df["n_valid"], df["n_years"])],
        label_y=df["mean"].fillna(0),
    )
    x = alt.X("name:N", sort=MONTHS, title=None, axis=alt.Axis(labelAngle=0))
    split = {"xOffset": alt.XOffset("series:N", sort=list(clims))} if len(clims) > 1 else {}
    color = {"color": alt.Color("series:N", title=None, scale=alt.Scale(domain=list(clims), range=SERIES),
                                legend=alt.Legend(orient="top"))} if len(clims) > 1 else {}
    bars = alt.Chart(df).mark_bar().encode(
        x=x, y=alt.Y("mean:Q", title=title), **split, **color,
        opacity=alt.condition("datum.ok", alt.value(1.0), alt.value(0.35)),
        tooltip=[alt.Tooltip("series:N", title="Data"), alt.Tooltip("name:N", title="Month"),
                 alt.Tooltip("mean:Q", format=",.2f"), alt.Tooltip("years:N", title="Valid years")],
    )
    labels = alt.Chart(df).mark_text(dy=-6, fontSize=10, color=LABEL).encode(
        x=x, y="label_y:Q", text="years:N", **split)
    return alt.layer(bars, labels).properties(height=HEIGHT)


def completeness_heatmap(table: pd.DataFrame, names: dict[str, str] | None = None) -> alt.LayerChart:
    """Station × month cells: faint grey when complete, orange to red by the share of missing days."""
    df = table.assign(name=[(names or {}).get(s, s) for s in table["station"]],
                      days=[f"{m}/{n} days missing" for m, n in zip(table["n_missing"], table["n_days"])])
    january = "substring(datum.value, 5, 7) == '01' ? substring(datum.value, 0, 4) : ''"
    x = alt.X("period:O", title=None, axis=alt.Axis(labelExpr=january, labelAngle=0, ticks=False))
    y = alt.Y("name:N", title=None, sort=None)
    tip = [alt.Tooltip("name:N", title="Station"), alt.Tooltip("period:N", title="Month"),
           alt.Tooltip("days:N", title="Missing")]
    base = alt.Chart(df).mark_rect(color=OBSERVED, opacity=0.15).encode(x=x, y=y, tooltip=tip)
    gaps = alt.Chart(df[df["n_missing"] > 0]).mark_rect().encode(
        x=x, y=y, tooltip=tip,
        color=alt.Color("pct_missing:Q", title="Missing (%)", scale=alt.Scale(domain=[0, 100], scheme="orangered")))
    return alt.layer(base, gaps).properties(height=alt.Step(20))


def weather_detail(observed: pd.Series, filled: pd.Series | None, title: str, bars: bool = False) -> alt.LayerChart:
    """Observed values, filled values (points) and days still missing (red rules)."""
    df = pd.DataFrame({"date": observed.index, "value": observed.to_numpy(dtype=float)})
    df["segment"] = df["value"].isna().cumsum()
    final = df["value"] if filled is None else \
        df["value"].fillna(pd.Series(filled.reindex(observed.index).to_numpy(dtype=float)))
    zoom = alt.selection_interval(bind="scales", encodings=["x"])
    x = alt.X("date:T", title=None)
    y = alt.Y("value:Q", title=title)
    tip = [alt.Tooltip("date:T"), alt.Tooltip("value:Q", format=",.2f")]
    base = alt.Chart(df.dropna(subset=["value"]))
    obs = (base.mark_bar(color=OBSERVED, width=1) if bars else
           base.mark_line(color=OBSERVED, strokeWidth=1)).encode(x=x, y=y, detail="segment:N", tooltip=tip)
    layers = [obs.add_params(zoom)]
    if filled is not None:
        est = pd.DataFrame({"date": df["date"], "value": final})[df["value"].isna() & final.notna()]
        layers.append(alt.Chart(est).mark_point(color=FILLED, filled=True, size=18).encode(
            x=x, y=y, tooltip=[alt.Tooltip("date:T", title="Filled"), alt.Tooltip("value:Q", format=",.2f")]))
    gaps = df[final.isna()]
    layers.append(alt.Chart(gaps).mark_rule(color=MISSING, opacity=0.4).encode(
        x="date:T", tooltip=[alt.Tooltip("date:T", title="Missing")]))
    return alt.layer(*layers).properties(height=HEIGHT)
