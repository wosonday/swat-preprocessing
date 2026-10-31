"""Draw config fields as Streamlit inputs; every change is written straight into the raw config dict."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import streamlit as st
from pydantic import BaseModel

from app.services.crs_options import check_crs, crs_label, crs_options
from app.services.form_layout import LABELS, LAYOUT, path_kind
from app.services.form_model import FieldSpec, field_spec, humanize
from app.services.form_state import apply, from_widget, to_widget
from app.ui.browse import browse_dialog

FORM = "f::"  # prefix of every form widget key, so a new config can clear them all
DATE_RANGE = (date(1900, 1, 1), date(2100, 12, 31))
WIDE = {"path", "mapping", "multichoice", "text_list"}


@dataclass
class FormContext:
    cfg: dict
    base_dir: Path  # relative paths in the config are relative to this folder
    roots: dict[str, Path]
    errors: dict[str, str] = field(default_factory=dict)


def reset_form_state() -> None:
    for key in [k for k in st.session_state if str(k).startswith(FORM)]:
        del st.session_state[key]


def section_at(cfg: dict, path: str):
    """'weather.fill.netcdf' -> cfg['weather']['fill']['netcdf']; 'clip.0' -> cfg['clip'][0]."""
    node = cfg
    for part in path.split("."):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _label(spec: FieldSpec) -> str:
    return LABELS.get(spec.name, humanize(spec.name)) + (" *" if spec.required else "")


def _on_change(ctx_cfg: dict, section_path: str, spec: FieldSpec, key: str) -> None:
    apply(section_at(ctx_cfg, section_path), spec, st.session_state[key])


def _error(ctx: FormContext, path: str) -> None:
    if path in ctx.errors:
        st.markdown(f":red[:material/error: {ctx.errors[path]}]")


def _path_status(ctx: FormContext, raw: str, kind: str) -> None:
    if not raw.strip():
        return
    p = Path(raw.strip())
    p = p if p.is_absolute() else ctx.base_dir / p
    if kind == "output":
        text = ":green[:material/check_circle: exists]" if p.exists() else ":gray[:material/info: will be created]"
    else:
        ok = {"file": p.is_file(), "dir": p.is_dir(), "file_or_dir": p.exists()}[kind]
        text = ":green[:material/check_circle: found]" if ok else ":red[:material/error: not found]"
    st.caption(text)


def _mapping(ctx: FormContext, section: dict, spec: FieldSpec, path: str, key: str) -> None:
    init_key = key + "::init"
    if init_key not in st.session_state:
        st.session_state[init_key] = [
            {"variable": k, "name": v} for k, v in to_widget(spec, section.get(spec.name)).items()
        ]
    rows = st.data_editor(
        st.session_state[init_key], key=key, num_rows="dynamic", width="stretch",
        column_config={
            "variable": st.column_config.SelectboxColumn(
                "Variable", options=["precip", "tmax", "tmin", "wind", "solar", "humidity"], required=True),
            "name": st.column_config.TextColumn("Name in file", required=True),
        },
    )
    value = {r["variable"]: r["name"] for r in rows if r.get("variable") and r.get("name")}
    st.caption(_label(spec))
    apply(section, spec, value)


def crs_select(label: str, key: str, **kwargs) -> str | None:
    """A searchable list of projected CRSs that also accepts a typed or pasted value (EPSG code, WKT, PROJ)."""
    options = list(crs_options())
    current = st.session_state.get(key)
    if current == "":
        st.session_state[key] = current = None
    if current and current not in options:
        options.insert(0, current)               # a custom CRS already in the config stays selectable
    value = st.selectbox(label, options, index=None, format_func=crs_label, accept_new_options=True, key=key,
                         placeholder="Search by EPSG code or name, or paste a CRS…", **kwargs)
    if value:
        status, message = check_crs(value)
        style = {"ok": ":green[:material/check_circle: ", "warn": ":orange[:material/warning: ",
                 "error": ":red[:material/error: ", "unknown": ":gray[:material/info: "}[status]
        st.caption(style + message + "]")
    return value


def render_field(ctx: FormContext, model: type[BaseModel], name: str, section_path: str) -> None:
    spec = field_spec(model, name)
    section = section_at(ctx.cfg, section_path)
    path = f"{section_path}.{name}"
    key = FORM + path
    if spec.kind == "mapping":
        _mapping(ctx, section, spec, path, key)
        _error(ctx, path)
        return
    if key not in st.session_state:
        st.session_state[key] = to_widget(spec, section.get(name))
    common = {"key": key, "on_change": _on_change, "args": (ctx.cfg, section_path, spec, key)}
    label = _label(spec)

    if spec.kind == "path":
        kind = path_kind(model, name)
        col_in, col_btn = st.columns([5, 1], vertical_alignment="bottom")
        col_in.text_input(label, placeholder="Paste a path or browse…", **common)
        with col_btn:
            if st.button("Browse", icon=":material/folder_open:", key=key + "::browse", width="stretch"):
                browse_dialog(key, ctx.roots, pick=kind)
        _path_status(ctx, st.session_state[key], kind)
        if from_widget(spec, st.session_state[key]) != from_widget(spec, to_widget(spec, section.get(name))):
            apply(section, spec, st.session_state[key])  # value set by the Browse dialog
    elif spec.kind == "choice":
        st.selectbox(label, spec.choices, **common)
    elif spec.kind == "multichoice":
        st.multiselect(label, spec.choices, **common)
    elif spec.kind == "bool":
        st.checkbox(label, **common)
    elif spec.kind == "number":
        lo = None if spec.min_value is None else (int(spec.min_value) if spec.integer else float(spec.min_value))
        hi = None if spec.max_value is None else (int(spec.max_value) if spec.integer else float(spec.max_value))
        st.number_input(label, min_value=lo, max_value=hi, step=1 if spec.integer else None,
                        placeholder="Leave empty for automatic", **common)
    elif spec.kind == "date":
        st.date_input(label, min_value=DATE_RANGE[0], max_value=DATE_RANGE[1], **common)
    elif spec.kind == "text_list":
        st.text_input(label, placeholder="Comma-separated, empty for all", **common)
    elif path == "project.crs":
        crs_select(label, **common)
    else:
        st.text_input(label, **common)
    _error(ctx, path)


def render_model(ctx: FormContext, model: type[BaseModel], section_path: str, only: list[str] | None = None) -> None:
    """Draw the plain (non-nested) fields of a model; short fields share a row two by two."""
    names = [n for n in (only or LAYOUT[model]) if field_spec(model, n).kind not in ("model", "model_list")]
    row: list[str] = []

    def flush() -> None:
        if row:
            for col, n in zip(st.columns(2), row):
                with col:
                    render_field(ctx, model, n, section_path)
            row.clear()

    for name in names:
        if field_spec(model, name).kind in WIDE:
            flush()
            render_field(ctx, model, name, section_path)
        else:
            row.append(name)
            if len(row) == 2:
                flush()
    flush()


def toggle_part(ctx: FormContext, parent_path: str, name: str, label: str, factory=dict) -> bool:
    """A switch that adds or removes an optional block; a removed block is kept for this session."""
    parent = section_at(ctx.cfg, parent_path) if parent_path else ctx.cfg
    path = f"{parent_path}.{name}" if parent_path else name
    stash = st.session_state.setdefault(FORM + "stash", {})
    on = st.toggle(label, value=name in parent, key=FORM + "on::" + path)
    if on and name not in parent:
        parent[name] = stash.pop(path, None) or factory()
    elif not on and name in parent:
        stash[path] = parent.pop(name)
    return on
