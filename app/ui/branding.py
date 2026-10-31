"""App icon and page setup shared by every page."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parents[1] / "assets"
ICON_PNG = ASSETS / "icon.png"   # browser tab and sidebar logo
ICON_ICO = ASSETS / "icon.ico"   # Windows Desktop shortcut (16-256 px)


def setup_page(title: str) -> None:
    """Must be the first Streamlit call of a page."""
    st.set_page_config(page_title=title, page_icon=str(ICON_PNG), layout="wide")
    st.logo(str(ICON_PNG), size="large")
