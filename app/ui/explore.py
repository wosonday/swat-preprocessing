"""Explore: charts and maps of the data behind the saved config."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from app.services.climatology import completeness, monthly_climatology, monthly_values
from app.services.explore_data import FlowView, WeatherView, load_config, load_streamflow, load_weather, station_series
from app.services.flow_stats import summary
from app.services.raster_view import LayerView, boundary_geojson, output_layers, render_layer
from app.ui.charts import UNITS, climatology_chart, completeness_heatmap, fdc_chart, hydrograph, weather_detail
from app.ui.maps import BASEMAPS, layer_deck

VIEWS = ["Weather", "Streamflow", "Map"]
VARIABLES = {"precip": "Precipitation", "tmax": "Max temperature", "tmin": "Min temperature",
             "wind": "Wind speed", "solar": "Solar radiation", "humidity": "Relative humidity"}


@st.cache_data(show_spinner="Reading streamflow…", max_entries=8)
def _flow(path: str, mtime: float, token: int) -> FlowView:
    """Cached by config path + modification time; `token` changes on Reload data."""
    cfg, _ = load_config(Path(path))
    return load_streamflow(cfg)


@st.cache_data(show_spinner="Reading weather…", max_entries=8)
def _weather_data(path: str, mtime: float, token: int) -> WeatherView:
    cfg, _ = load_config(Path(path))
    return load_weather(cfg)


@st.cache_data(show_spinner="Rendering the layer…", max_entries=16)
def _layer(name: str, path: str, kind: str, lookup: str | None, mtime: float, token: int) -> LayerView:
    """Cached by raster path + modification time; `token` changes on Reload data."""
    from app.services.raster_view import Layer

    return render_layer(Layer(name, Path(path), kind, Path(lookup) if lookup else None))


@st.cache_data(show_spinner=False, max_entries=8)
def _boundary(path: str | None, mtime: float, token: int) -> tuple[dict | None, str | None]:
    return boundary_geojson(Path(path) if path else None)


def _mtime(path: Path | None) -> float:
    return path.stat().st_mtime if path is not None and path.exists() else 0.0


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

    if view == "Weather":
        if cfg.weather is None:
            st.info("This config has no weather section.", icon=":material/info:")
            return
        _weather(_weather_data(str(path), path.stat().st_mtime, token), cfg)
    elif view == "Streamflow":
        if cfg.streamflow is None:
            st.info("This config has no streamflow section.", icon=":material/info:")
            return
        _streamflow(_flow(str(path), path.stat().st_mtime, token))
    elif view == "Map":
        _map(cfg, token)


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
    st.altair_chart(climatology_chart({"Observed": clim}, title), width="stretch")
    weak = [m for m, ok, n in zip(clim["month"], clim["ok"], clim["n_years"]) if n and not ok]
    rule = "at most 10 missing days and fewer than 5 in a row" if kind == "mean" else "no missing day"
    st.caption(f"Labels: valid years / years. A month is valid with {rule} (WMO-No. 1203); "
               "the mean needs valid months in at least 80% of the years.")
    if weak:
        st.warning(f"{len(weak)} month(s) below 80% of years are shown faded.", icon=":material/warning:")


def _map(cfg, token: int) -> None:
    layers = output_layers(cfg)
    if not layers:
        st.info("Run Build to see the output maps.", icon=":material/info:")
        return
    layer_col, opacity_col, basemap_col = st.columns([2, 2, 2], vertical_alignment="bottom")
    name = layer_col.selectbox("Layer", [layer.name for layer in layers], key="map_layer")
    opacity = opacity_col.slider("Opacity", 0.0, 1.0, 0.8, 0.05, key="map_opacity")
    basemap = basemap_col.segmented_control("Basemap", BASEMAPS, default=BASEMAPS[0], required=True, key="map_basemap")
    layer = next(layer for layer in layers if layer.name == name)

    lookup = str(layer.lookup) if layer.lookup else None
    view = _layer(layer.name, str(layer.path), layer.kind, lookup, _mtime(layer.path), token)
    if view.error:
        st.error(view.error, icon=":material/error:")
        return
    boundary_path = cfg.project.boundary
    boundary, boundary_error = _boundary(str(boundary_path) if boundary_path else None, _mtime(boundary_path), token)
    st.pydeck_chart(layer_deck(view, boundary, opacity, basemap), height=520)
    if boundary_error:
        st.caption(boundary_error)
    if basemap != "None":
        st.caption("Basemap tiles come from CARTO / OpenStreetMap; choose None to work offline.")

    legend_col, stats_col = st.columns([3, 2])
    with legend_col:
        st.markdown("**Legend**")
        if layer.kind == "categorical":
            table = view.legend[["color", "code", "label", "pct_area"]]
            config = {"color": st.column_config.TextColumn("", width="small"), "code": "Code", "label": "Name",
                      "pct_area": st.column_config.NumberColumn("Area (%)", format="%.1f")}
        else:
            table = view.legend[["color", "label"]]
            config = {"color": st.column_config.TextColumn("", width="small"), "label": "Value"}
        swatch = table.style.map(lambda c: f"background-color: {c}; color: {c}", subset=["color"])
        st.dataframe(swatch, hide_index=True, column_config=config)
    with stats_col:
        st.markdown("**Layer**")
        st.dataframe([{"Property": k, "Value": v} for k, v in view.stats.items()], hide_index=True)


def _unit(cfg, variable: str) -> str:
    units = cfg.weather.units
    return {"precip": units.precip, "tmax": units.temperature, "tmin": units.temperature}.get(variable, "")


def _weather(data: WeatherView, cfg) -> None:
    if data.error:
        st.error(data.error, icon=":material/error:")
        return
    variables = list(data.observed)
    var_col, source_col = st.columns([3, 2], vertical_alignment="bottom")
    var = var_col.selectbox("Variable", variables, format_func=lambda v: VARIABLES.get(v, v), key="wx_var")
    sources = ["Observed", "Filled"] if data.filled else ["Observed"]
    source = source_col.segmented_control("Data", sources, default="Observed", required=True, key="wx_source")
    if data.fill_note:
        st.caption(data.fill_note)
    unit = _unit(cfg, var)
    title = f"{VARIABLES.get(var, var)} ({unit})" if unit else VARIABLES.get(var, var)
    names = {str(i): str(n) for i, n in data.stations.get("name", pd.Series(dtype=str)).items()}

    st.subheader("Completeness")
    shown = data.filled if source == "Filled" and data.filled and var in data.filled else data.observed
    st.altair_chart(completeness_heatmap(completeness(shown[var]), names), width="stretch")
    st.caption("Share of missing days per station and month" +
               (", after filling." if shown is data.filled else ", as measured."))

    st.subheader("Station")
    stations = list(data.observed[var].columns)
    sid = st.selectbox("Station", stations, format_func=lambda s: f"{s} · {names[str(s)]}" if names.get(str(s))
                       and names[str(s)] != str(s) else str(s), key="wx_station")
    observed = data.observed[var][sid]
    filled = data.filled[var][sid] if data.filled and var in data.filled and sid in data.filled[var] else None
    st.altair_chart(weather_detail(observed, filled, title, bars=var == "precip"), width="stretch")
    if filled is not None:
        st.caption("Grey: measured. Orange points: filled. Red: still missing. Drag to zoom, double-click to reset.")
    else:
        st.caption(f"{int(observed.isna().sum())} missing days, marked in red. Drag to zoom, double-click to reset.")
    report = data.fill_report
    if report is not None:
        row = report[(report["station_id"].astype(str) == str(sid)) & (report["variable"] == var)]
        if not row.empty:
            r = row.iloc[0]
            correction = (f"{r['correction_type']} {float(r['correction_value']):.3f}"
                          if pd.notna(r.get("correction_value")) else "none")
            st.caption(f"Fill report: {int(r['n_missing'])} missing, {int(r['n_filled'])} filled, "
                       f"{int(r['n_still_missing'])} still missing; overlap {int(r['n_overlap'])} days; "
                       f"correction {correction}; status {r['status']}.")

    if "precip" in data.observed and sid in data.observed["precip"]:
        st.subheader("Monthly climatology of precipitation")
        obs = data.observed["precip"][sid]
        clims = {"Observed": monthly_climatology(monthly_values(obs, "sum"))}
        if data.filled and "precip" in data.filled and sid in data.filled["precip"]:
            fil = data.filled["precip"][sid].reindex(obs.index)
            clims["Filled"] = monthly_climatology(monthly_values(fil, "sum", estimated=obs.isna() & fil.notna()))
        st.altair_chart(climatology_chart(clims, f"Mean monthly total ({_unit(cfg, 'precip')})"), width="stretch")
        st.caption("Labels: valid years / years. A month counts only with no missing day; filled days count when "
                   "at most 10 per month and fewer than 5 in a row (WMO-No. 1203). Faded: valid in fewer than 80% "
                   "of the years.")
