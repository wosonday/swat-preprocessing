"""Explore › Map: output rasters, the boundary, rain stations and extra layers kept per project."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.services.overlays import (CSV_SUFFIXES, STATIONS_COLOR, VECTOR_SUFFIXES, Overlay, OverlayView, extent_table,
                                   load_overlays, next_color, read_overlay, read_station_points, save_overlays,
                                   stations_path)
from app.services.raster_view import Layer, LayerView, output_layers, render_layer
from app.ui.browse import browse_dialog
from app.ui.maps import BASEMAPS, layer_deck

NO_RASTER = "No output raster yet"


def _mtime(path: Path | None) -> float:
    return path.stat().st_mtime if path is not None and Path(path).exists() else 0.0


@st.cache_data(show_spinner="Rendering the layer…", max_entries=16)
def _layer(name: str, path: str, kind: str, lookup: str | None, mtime: float, token: int) -> LayerView:
    """Cached by raster path + modification time; `token` changes on Reload data."""
    return render_layer(Layer(name, Path(path), kind, Path(lookup) if lookup else None))


@st.cache_data(show_spinner=False, max_entries=32)
def _overlay(path: str, csv_crs: str, project_crs: str | None, mtime: float, token: int) -> OverlayView:
    return read_overlay(Path(path), csv_crs, project_crs)


@st.cache_data(show_spinner=False, max_entries=8)
def _station_view(path: str, mtime: float, token: int) -> OverlayView:
    return read_station_points(Path(path))


def _stations(cfg, token: int) -> OverlayView | None:
    path = stations_path(cfg)
    return _station_view(str(path), _mtime(path), token) if path else None


def _save(project: Path, items: list[Overlay]) -> None:
    try:
        save_overlays(project, items)
    except OSError as exc:
        st.session_state["overlay_error"] = f"Cannot save the layer list: {exc}"


def _toggle(project: Path, index: int) -> None:
    items = load_overlays(project)
    items[index].visible = st.session_state[f"overlay_on::{index}"]
    _save(project, items)


def _remove(project: Path, index: int) -> None:
    items = load_overlays(project)
    items.pop(index)
    _save(project, items)


def _add(project: Path, project_crs: str) -> None:
    state = st.session_state
    raw = state.get("overlay_path", "").strip()
    path = Path(raw).expanduser() if raw else None
    if path is not None and not path.is_absolute():
        path = project / path
    if path is None or path.suffix.lower() not in CSV_SUFFIXES + VECTOR_SUFFIXES:
        state["overlay_error"] = "Choose a .shp, .gpkg, .geojson, .csv or .txt file."
        return
    csv_crs = state.get("overlay_crs", "").strip() or "EPSG:4326"
    view = read_overlay(path, csv_crs, project_crs)
    if view.error:
        state["overlay_error"] = view.error
        return
    items = load_overlays(project)
    if any(Path(i.path) == path.resolve() for i in items):
        state["overlay_error"] = f"{path.name} is already on the map."
        return
    items.append(Overlay(str(path.resolve()), next_color(items), crs=csv_crs))
    _save(project, items)
    state["overlay_error"] = None
    state["overlay_path"] = ""


def render_map(cfg, project: Path, roots: dict[str, Path], token: int) -> None:
    state = st.session_state
    project_crs = cfg.project.crs
    rasters = output_layers(cfg)

    layer_col, opacity_col, basemap_col = st.columns([2, 2, 2], vertical_alignment="bottom")
    names = [layer.name for layer in rasters] or [NO_RASTER]
    name = layer_col.selectbox("Layer", names, key="map_layer", disabled=not rasters)
    opacity = opacity_col.slider("Opacity", 0.0, 1.0, 0.8, 0.05, key="map_opacity", disabled=not rasters)
    basemap = basemap_col.segmented_control("Basemap", BASEMAPS, default=BASEMAPS[0], required=True, key="map_basemap")

    layer, view = None, None
    if rasters:
        layer = next(r for r in rasters if r.name == name)
        lookup = str(layer.lookup) if layer.lookup else None
        view = _layer(layer.name, str(layer.path), layer.kind, lookup, _mtime(layer.path), token)
        if view.error:
            st.error(view.error, icon=":material/error:")
            view = None

    boundary_path = cfg.project.boundary
    boundary = _overlay(str(boundary_path), "EPSG:4326", project_crs, _mtime(boundary_path), token) \
        if boundary_path else None
    stations = _stations(cfg, token)
    items = load_overlays(project)
    extras = [(item, _overlay(item.path, item.crs, project_crs, _mtime(Path(item.path)), token)) for item in items]

    drawn = []
    if stations is not None and not stations.error and state.get("overlay_stations", True):
        drawn.append((stations, STATIONS_COLOR))
    drawn += [(v, item.color) for item, v in extras if item.visible and not v.error]
    st.pydeck_chart(layer_deck(view, boundary.geojson if boundary and not boundary.error else None, opacity,
                               basemap, overlays=drawn), height=520)
    if boundary is not None and boundary.error:
        st.caption(f"Boundary not shown: {boundary.error}")
    if not rasters:
        st.caption("Run Build to add the DEM, land use and soil rasters to the map.")
    if basemap != "None":
        st.caption("Basemap tiles come from CARTO / OpenStreetMap; choose None to work offline.")

    _overlay_panel(project, project_crs, roots, stations, extras)
    _extents(boundary, layer, view, stations, extras)
    if view is not None:
        _legend(layer, view)


def _describe(view: OverlayView) -> str:
    if view.error:
        return f":red[{view.error}]"
    noun = {"point": "point", "line": "line", "polygon": "polygon"}.get(view.kind, "feature")
    return f":gray[{view.count} {noun}{'' if view.count == 1 else 's'}]"


def _overlay_panel(project: Path, project_crs: str, roots, stations, extras) -> None:
    state = st.session_state
    st.markdown("**Overlays**")
    if stations is not None:
        on_col, text_col = st.columns([3, 2], vertical_alignment="center")
        on_col.checkbox("Rain stations (config)", value=True, key="overlay_stations")
        text_col.markdown(f"<span style='color:{STATIONS_COLOR}'>●</span> " + _describe(stations),
                          unsafe_allow_html=True)
    for i, (item, view) in enumerate(extras):
        on_col, text_col, del_col = st.columns([3, 2, 1], vertical_alignment="center")
        state[f"overlay_on::{i}"] = item.visible
        on_col.checkbox(Path(item.path).name, key=f"overlay_on::{i}",
                        on_change=_toggle, args=(project, i), disabled=bool(view.error))
        text_col.markdown(f"<span style='color:{item.color}'>■</span> " + _describe(view), unsafe_allow_html=True)
        del_col.button("Remove", key=f"overlay_remove::{i}", on_click=_remove, args=(project, i), width="stretch")

    with st.expander("Add layer", icon=":material/add:"):
        path_col, browse_col = st.columns([4, 1], vertical_alignment="bottom")
        path_col.text_input("File", key="overlay_path", placeholder="A .shp, .gpkg, .geojson, or a .csv of points")
        if browse_col.button("Browse", icon=":material/folder_open:", key="overlay_browse", width="stretch"):
            browse_dialog("overlay_path", roots, suffixes=CSV_SUFFIXES + VECTOR_SUFFIXES)
        if state.get("overlay_path", "").strip().lower().endswith(CSV_SUFFIXES):
            state.setdefault("overlay_crs", "EPSG:4326")
            st.text_input("CSV coordinates CRS", key="overlay_crs",
                          help="EPSG:4326 when lat/lon are degrees; a projected CRS such as EPSG:32648 when they "
                               "are metres (lat = northing, lon = easting).")
        st.button("Add", type="primary", icon=":material/add:", key="overlay_add", on_click=_add,
                  args=(project, project_crs))
        if state.get("overlay_error"):
            st.error(state["overlay_error"], icon=":material/error:")
    st.caption(f"The list is kept for this project in `{project / '.swatprep' / 'map_layers.json'}`.")


def _extents(boundary, layer, view, stations, extras) -> None:
    rows = []
    if boundary is not None and not boundary.error:
        rows.append(("Boundary", boundary))
    if view is not None:
        rows.append((layer.name, OverlayView(layer.name, bounds=view.bounds)))
    if stations is not None and not stations.error and st.session_state.get("overlay_stations", True):
        rows.append(("Rain stations (config)", stations))
    rows += [(Path(item.path).name, v) for item, v in extras if item.visible and not v.error]
    if not rows:
        return
    st.markdown("**Extents**")
    table = extent_table(rows, boundary.bounds if boundary is not None and not boundary.error else None)
    st.dataframe(table, hide_index=True, column_config={
        "layer": "Layer", "covers_boundary": "Covers boundary",
        **{c: st.column_config.NumberColumn(c.capitalize(), format="%.4f") for c in ("west", "south", "east", "north")},
        "area_km2": st.column_config.NumberColumn("Area (km²)", format="%.1f"),
    })
    st.caption("Extents in degrees (WGS 84). *Covers boundary*: the layer's extent contains the boundary's extent.")


def _legend(layer, view: LayerView) -> None:
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
