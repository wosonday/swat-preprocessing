"""One renderer per config section; Weather and Clip have nested or repeated parts."""
from __future__ import annotations

import streamlit as st

from swatprep.config import (
    ClipItemConfig, FillCSVConfig, FillNetCDFConfig, ProjectConfig, WeatherConfig, WeatherFillConfig,
    WeatherSourceConfig, WeatherUnitsConfig,
)

from app.services.form_layout import SECTIONS
from app.ui.fields import FORM, FormContext, render_model, reset_form_state, section_at, toggle_part


def render_project(ctx: FormContext) -> None:
    render_model(ctx, ProjectConfig, "project")


def render_simple(ctx: FormContext, key: str) -> None:
    render_model(ctx, SECTIONS[key][1], key)


def _remove_clip(ctx: FormContext, index: int) -> None:
    del ctx.cfg["clip"][index]
    for k in [k for k in st.session_state if str(k).startswith(FORM + "clip.")]:
        del st.session_state[k]


def render_clip(ctx: FormContext) -> None:
    st.caption("Crop extra rasters to the project boundary.")
    items = ctx.cfg["clip"]
    for i in range(len(items)):
        with st.container(border=True):
            head, btn = st.columns([5, 1], vertical_alignment="center")
            head.markdown(f"**Raster {i + 1}**")
            btn.button("Remove", icon=":material/delete:", key=f"{FORM}clip_remove::{i}", width="stretch",
                       on_click=_remove_clip, args=(ctx, i), disabled=len(items) == 1)
            render_model(ctx, ClipItemConfig, f"clip.{i}")
    st.button("Add raster", icon=":material/add:", key=FORM + "clip_add", on_click=items.append, args=({},))


def _units(ctx: FormContext) -> None:
    weather = ctx.cfg["weather"]
    weather.setdefault("units", {})
    render_model(ctx, WeatherUnitsConfig, "weather.units")
    if not weather["units"]:
        del weather["units"]  # still the defaults: keep the YAML clean


def render_weather(ctx: FormContext) -> None:
    st.markdown("**Stations**")
    render_model(ctx, WeatherConfig, "weather", only=["stations", "data_dir", "file_pattern"])
    for part, label in (("precip", "Separate precipitation source"), ("temp", "Separate temperature source")):
        if toggle_part(ctx, "weather", part, label):
            with st.container(border=True):
                render_model(ctx, WeatherSourceConfig, f"weather.{part}")

    st.markdown("**Period and variables**")
    render_model(ctx, WeatherConfig, "weather", only=["variables", "start", "end", "format", "missing_policy"])
    with st.expander("Units"):
        _units(ctx)

    st.markdown("**Gap filling**")
    if toggle_part(ctx, "weather", "fill", "Fill missing values"):
        with st.container(border=True):
            render_model(ctx, WeatherFillConfig, "weather.fill")
            fill = section_at(ctx.cfg, "weather.fill")
            kind = fill.get("type", "csv")
            fill.setdefault(kind, {})
            for other in ("csv", "netcdf"):
                if other != kind and not fill.get(other, True):
                    del fill[other]   # an empty block of the unused type fails validation (its fields are required)
            model = FillCSVConfig if kind == "csv" else FillNetCDFConfig
            st.markdown(f"**{'CSV stations' if kind == 'csv' else 'NetCDF grid'}**")
            render_model(ctx, model, f"weather.fill.{kind}")


RENDERERS = {
    "clip": render_clip,
    "weather": render_weather,
}


def render_section(ctx: FormContext, key: str) -> None:
    RENDERERS.get(key, lambda c: render_simple(c, key))(ctx)


__all__ = ["render_project", "render_section", "reset_form_state"]
