"""Sidebar of an open project: which project, which config, and a dialog for a new config."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.services.projects import ProjectError, create_config, free_config_name
from app.ui.fields import crs_select

LOCKED = "Save or discard your changes first."


def _close() -> None:
    for key in ("project", "config_path", "loaded_path"):
        st.session_state[key] = None


def _choose(project: Path) -> None:
    st.session_state["config_path"] = str(project / st.session_state["config_choice"])


def render_project_header(project: Path, locked: bool) -> None:
    st.subheader(project.name or str(project))
    st.caption(f"`{project}`")
    st.button("Change project", icon=":material/swap_horiz:", key="change_project", on_click=_close,
              disabled=locked, width="stretch")


def render_config_picker(project: Path, configs: list[Path], current: Path | None, locked: bool,
                         crs: str | None = None) -> None:
    """`crs`: the open config's CRS, offered as the default of a new config."""
    st.subheader("Config")
    names = [p.name for p in configs]
    if names:
        if current is not None and current.name in names:
            st.session_state["config_choice"] = current.name
        st.selectbox("Config", names, key="config_choice", on_change=_choose, args=(project,), disabled=locked,
                     label_visibility="collapsed")
    if st.button("New config", icon=":material/add:", key="new_config", disabled=locked, width="stretch"):
        new_config_dialog(project, crs=crs)
    if locked:
        st.caption(f":orange[:material/lock: {LOCKED}]")


@st.dialog("New config")
def new_config_dialog(project: Path, name: str = "", crs: str | None = None) -> None:
    st.caption(f"Created in `{project}`")
    file_name = st.text_input("File name", value=free_config_name(project), key="new_config_file")
    project_name = st.text_input("Project name", value=name or project.name, key="new_config_name")
    if crs and "new_config_crs" not in st.session_state:
        st.session_state["new_config_crs"] = crs
    crs_value = crs_select("CRS", key="new_config_crs")
    if st.button("Create", type="primary", icon=":material/add:", key="new_config_create"):
        try:
            path = create_config(project, file_name, project_name, crs_value or "")
        except ProjectError as exc:
            st.error(str(exc), icon=":material/error:")
            return
        for key in ("new_config_file", "new_config_name", "new_config_crs"):
            st.session_state.pop(key, None)
        st.session_state["config_path"] = str(path)
        st.rerun()
