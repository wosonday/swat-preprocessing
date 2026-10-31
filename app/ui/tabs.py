"""Tabs that stay on the chosen tab when their labels change."""
from __future__ import annotations

import streamlit as st


def stable_tabs(ids: list[str], labels: list[str], key: str):
    """st.tabs that remembers the selected tab by id.

    Streamlit identifies tabs by their labels, so a label that changes (an error count such as
    "Weather (1)") rebuilds the tabs and selects the first one. The id of the chosen tab is kept in
    session state and passed back as `default`, so the user stays where they were.
    """
    memory = key + "::id"

    def remember() -> None:
        chosen = st.session_state.get(key)
        if chosen in labels:              # labels of the run that drew these tabs
            st.session_state[memory] = ids[labels.index(chosen)]

    current = st.session_state.get(memory)
    default = labels[ids.index(current)] if current in ids else labels[0]
    return st.tabs(labels, key=key, default=default, on_change=remember)
