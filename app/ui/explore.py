"""Explore: charts of the data behind the saved config (Streamflow for now)."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.services.climatology import monthly_climatology, monthly_values
from app.services.explore_data import FlowView, load_config, load_streamflow, station_series
from app.services.flow_stats import summary
from app.ui.charts import UNITS, climatology_chart, fdc_chart, hydrograph

VIEWS = ["Streamflow"]


@st.cache_data(show_spinner="Reading streamflow…", max_entries=8)
def _flow(path: str, mtime: float, token: int) -> FlowView:
    """Cached by config path + modification time; `token` changes on Reload data."""
    cfg, _ = load_config(Path(path))
    return load_streamflow(cfg)


def render_explore(path: Path, unsaved: bool) -> None:
    if unsaved:
        st.info("Showing the saved config; save to explore your changes.", icon=":material/info:")
    cfg, error = load_config(path)
    if error:
        st.error(error, icon=":material/error:")
        return

    view_col, reload_col = st.columns([3, 1], vertical_alignment="bottom")
    view = view_col.segmented_control("View", VIEWS, default=VIEWS[0], required=True, key="explore_view")
    if reload_col.button("Reload data", icon=":material/refresh:", key="explore_reload", width="stretch"):
        st.session_state["explore_token"] = st.session_state.get("explore_token", 0) + 1
    token = st.session_state.get("explore_token", 0)

    if view == "Streamflow":
        if cfg.streamflow is None:
            st.info("This config has no streamflow section.", icon=":material/info:")
            return
        _streamflow(_flow(str(path), path.stat().st_mtime, token))


def _streamflow(data: FlowView) -> None:
    if data.error:
        st.error(data.error, icon=":material/error:")
        return
    if data.daily.empty:
        st.warning("No streamflow values found.", icon=":material/warning:")
        return
    unit = UNITS[data.units]

    st.dataframe(summary(data.daily), hide_index=True, column_config={
        "station": "Station", "start": "Start", "end": "End",
        "pct_missing": st.column_config.NumberColumn("Missing (%)", format="%.1f"),
        **{c: st.column_config.NumberColumn(f"{c.upper() if c[0] == 'q' else c.capitalize()} ({unit})", format="%.3f")
           for c in ("min", "mean", "max", "q5", "q50", "q95")},
    })
    station = st.selectbox("Station", list(data.daily.columns), key="flow_station")
    series = station_series(data.daily, station)

    st.subheader("Hydrograph")
    log = st.toggle("Log scale", key="flow_log")
    st.altair_chart(hydrograph(series, data.units, log), width="stretch")
    zeros = int((series <= 0).sum())
    if log and zeros:
        st.caption(f"{zeros} zero-flow days not shown on the log scale.")
    st.caption(f"{int(series.isna().sum())} missing days, marked in red. Drag to zoom, double-click to reset.")

    st.subheader("Flow duration curve")
    st.altair_chart(fdc_chart(series, data.units), width="stretch")

    st.subheader("Monthly climatology")
    kind = "mean" if data.units == "m3s" else "sum"
    clim = monthly_climatology(monthly_values(series, kind))
    title = f"Mean monthly flow ({unit})" if kind == "mean" else f"Mean monthly total ({unit})"
    st.altair_chart(climatology_chart(clim, title), width="stretch")
    weak = [m for m, ok, n in zip(clim["month"], clim["ok"], clim["n_years"]) if n and not ok]
    rule = "at most 10 missing days and fewer than 5 in a row" if kind == "mean" else "no missing day"
    st.caption(f"Labels: valid years / years. A month is valid with {rule} (WMO-No. 1203); "
               "the mean needs valid months in at least 80% of the years.")
    if weak:
        st.warning(f"{len(weak)} month(s) below 80% of years are shown faded.", icon=":material/warning:")
