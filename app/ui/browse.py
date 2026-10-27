"""Browse dialog: pick a file or folder inside DATA_ROOT or WORKSPACE and write it to a session key."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.services.fs_browser import OutsideRootError, human_size, list_dir


def _enter(sub_key: str, sub: str) -> None:
    st.session_state[sub_key] = sub


def _pick(target_key: str, path: Path) -> None:
    st.session_state[target_key] = str(path)


@st.dialog("Browse", width="large")
def browse_dialog(target_key: str, roots: dict[str, Path], suffixes: tuple[str, ...] = (), pick: str = "file") -> None:
    """pick: 'file', 'dir', 'file_or_dir' or 'output' (a folder that may hold new files)."""
    root_key, sub_key = f"{target_key}::root", f"{target_key}::sub"
    root_name = st.radio("Root", list(roots), horizontal=True, key=root_key, on_change=_enter, args=(sub_key, ""))
    root = roots[root_name]
    sub = st.session_state.get(sub_key, "")
    here = root / sub
    st.caption(f"`{here.as_posix()}`")

    try:
        entries = list_dir(root, sub, suffixes)
    except (OutsideRootError, OSError) as exc:
        st.error(f"Cannot open this folder: {exc}", icon=":material/error:")
        return

    if sub:
        parent = Path(sub).parent.as_posix()
        st.button("Up one level", icon=":material/arrow_upward:", key=f"{target_key}::up",
                  on_click=_enter, args=(sub_key, "" if parent == "." else parent))
    for e in (e for e in entries if e.is_dir):
        st.button(e.name, icon=":material/folder:", key=f"{target_key}::d::{e.name}",
                  on_click=_enter, args=(sub_key, (Path(sub) / e.name).as_posix()))

    if pick in ("dir", "file_or_dir", "output"):
        if st.button("Use this folder", type="primary", icon=":material/check:", key=f"{target_key}::here",
                     on_click=_pick, args=(target_key, here)):
            st.rerun()
    if pick == "dir" or pick == "output":
        return

    files = [e for e in entries if not e.is_dir]
    if not files:
        st.caption("No matching files in this folder.")
        return
    labels = {e.name: f"{e.name} · {human_size(e.size)}" for e in files}
    choice = st.radio("Files", list(labels), format_func=labels.get, index=None, key=f"{target_key}::file")
    if choice and st.button("Select", type="primary", key=f"{target_key}::select",
                            on_click=_pick, args=(target_key, here / choice)):
        st.rerun()
