"""Example 6: an interactive map in Streamlit: click a station, see its rainfall; heavy work is cached.

Run:  uv run streamlit run docs/learning/06_map_select_app.py
Uses the synthetic basin of demo_data.py (5 stations, 5 years of daily rain).
"""
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st
from demo_data import make

from swatprep.core.weather import read_stations

PATHS = make()
LAYER_ID = "stations"     # with on_select, every layer needs an id; it is also the key of the selection


@st.cache_data(show_spinner=False)
def stations(path: str, mtime: float) -> pd.DataFrame:
    """Read once per file version: the mtime in the key makes an edited file be read again."""
    table = read_stations(Path(path)).reset_index()
    return table.assign(position=table[["lon", "lat"]].values.tolist())


@st.cache_data(show_spinner=False)
def rainfall(path: str, mtime: float) -> pd.Series:
    return pd.read_csv(path, parse_dates=["date"]).set_index("date")["precip"]


path = PATHS["stations"]
table = stations(str(path), path.stat().st_mtime)

layer = pdk.Layer("ScatterplotLayer", table, id=LAYER_ID, get_position="position",
                  get_fill_color=[0, 170, 84], get_line_color=[255, 255, 255], stroked=True,
                  radius_units=pdk.types.String("pixels"),   # a plain "pixels" would be read as JavaScript
                  get_radius=8, line_width_min_pixels=1, pickable=True, auto_highlight=True)
view = pdk.data_utils.compute_view(table[["lon", "lat"]].values.tolist())
view.zoom = min(view.zoom - 0.5, 11)      # a little margin around the stations
deck = pdk.Deck(layers=[layer], initial_view_state=view, map_provider=None, map_style=None,
                tooltip={"text": "{id} · {name}"})

event = st.pydeck_chart(deck, on_select="rerun", selection_mode="single-object", key="station_map", height=360)
picked = event.selection.objects.get(LAYER_ID, [])
if not picked:
    st.info("Click a station on the map.")
else:
    sid = picked[0]["id"]
    csv = PATHS["rain"] / f"{sid}.csv"
    st.subheader(f"{sid} · {picked[0]['name']}")
    if csv.is_file():
        monthly = rainfall(str(csv), csv.stat().st_mtime).resample("MS").sum()
        st.bar_chart(monthly, y_label="Monthly rainfall (mm)")
    else:
        st.warning(f"No data file for {sid}.")
