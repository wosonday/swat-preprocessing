"""The Projects screen: shown when no project folder is open."""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from app.services.projects import ProjectError, create_project, list_configs
from app.services.recent import add_recent, load_recent
from app.ui.browse import browse_dialog
from app.ui.fields import crs_select


def open_project(folder: Path) -> None:
    """Make `folder` the open project; the page then opens its default config."""
    st.session_state["project"] = str(Path(folder).resolve())
    add_recent(Path(folder))
    st.session_state["config_path"] = None
    st.session_state["loaded_path"] = None


def _open_typed() -> None:
    raw = st.session_state.get("home_open_dir", "").strip()
    folder = Path(raw) if raw else None
    if folder is None or not folder.is_dir():
        st.session_state["home_error"] = "Folder not found. Use New project to create it."
        return
    st.session_state["home_error"] = None
    open_project(folder)


def _create() -> None:
    raw = st.session_state.get("home_new_dir", "").strip()
    if not raw:
        st.session_state["home_new_error"] = "Choose a folder for the new project."
        return
    try:
        create_project(Path(raw), st.session_state.get("home_new_name", ""), st.session_state.get("home_new_crs") or "")
    except ProjectError as exc:
        st.session_state["home_new_error"] = str(exc)
        return
    st.session_state["home_new_error"] = None
    open_project(Path(raw))


def _count(folder: str) -> str:
    n = len(list_configs(Path(folder)))
    return f"{n} config" + ("" if n == 1 else "s")


def render_home(roots: dict[str, Path]) -> None:
    state = st.session_state
    st.title("Projects")
    st.caption("A project is a folder; its configs are the .yaml files in that folder.")
    left, right = st.columns(2, gap="large")

    with left, st.container(border=True):
        st.subheader("Recent projects")
        history = load_recent()
        if not history:
            st.caption("No recent projects yet.")
        for i, folder in enumerate(history):
            name_col, open_col = st.columns([4, 1], vertical_alignment="center")
            name_col.markdown(f"**{Path(folder).name}**  \n:gray[{folder} · {_count(folder)}]")
            open_col.button("Open", key=f"home_recent::{i}", on_click=open_project, args=(Path(folder),),
                            width="stretch")

    with right:
        with st.container(border=True):
            st.subheader("Open project folder")
            state.setdefault("home_open_dir", os.environ.get("SWATPREP_WORKSPACE", ""))
            path_col, browse_col = st.columns([3, 1], vertical_alignment="bottom")
            path_col.text_input("Folder", key="home_open_dir", placeholder="Paste a folder path…")
            if browse_col.button("Browse", icon=":material/folder_open:", key="home_open_browse", width="stretch"):
                browse_dialog("home_open_dir", roots, pick="dir")
            st.button("Open", type="primary", icon=":material/folder_open:", key="home_open", on_click=_open_typed)
            if state.get("home_error"):
                st.error(state["home_error"], icon=":material/error:")

        with st.container(border=True):
            st.subheader("New project")
            path_col, browse_col = st.columns([3, 1], vertical_alignment="bottom")
            path_col.text_input("Folder", key="home_new_dir", placeholder="A new or empty folder, e.g. D:\\Basin\\SeSan")
            if browse_col.button("Browse", icon=":material/folder_open:", key="home_new_browse", width="stretch"):
                browse_dialog("home_new_dir", roots, pick="output")
            st.text_input("Project name", key="home_new_name", placeholder="Defaults to the folder name")
            crs_select("CRS", key="home_new_crs")
            st.button("Create", icon=":material/add:", key="home_create", on_click=_create)
            if state.get("home_new_error"):
                st.error(state["home_new_error"], icon=":material/error:")
