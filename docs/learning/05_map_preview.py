"""Example 5: the Explore map pipeline without Streamlit: raster -> PNG in EPSG:3857 -> pydeck -> HTML.

Run:  uv run python docs/learning/05_map_preview.py
Writes map_preview.html into the demo folder; open it in a browser.
"""
import time

from demo_data import ROOT, make

from app.services.overlays import read_overlay, read_station_points
from app.services.raster_view import Layer, render_layer
from app.ui.maps import layer_deck

paths = make()
start = time.perf_counter()
view = render_layer(Layer("DEM", paths["dem"], "continuous"), max_px=1024)          # 1. raster -> small PNG
print(f"1. preview: {len(view.png) / 1e3:.0f} kB PNG in {time.perf_counter() - start:.2f} s; stats {view.stats}")

boundary = read_overlay(paths["boundary"], project_crs="EPSG:32648")                  # 2. vector -> GeoJSON (degrees)
stations = read_station_points(paths["stations"])                                    # 3. station table -> points
print(f"2. boundary: {boundary.kind}, {boundary.area_km2:.1f} km²   3. stations: {stations.count} points")

deck = layer_deck(view, boundary.geojson, opacity=0.8, basemap="None",               # 4. every layer -> one Deck
                  overlays=[(stations, "#00aa54")])
print("4. layers:", [layer.type for layer in deck.layers])
print(f"   payload sent to the browser on every rerun: {len(deck.to_json()) / 1e3:.0f} kB")
out = ROOT / "map_preview.html"
deck.to_html(str(out), open_browser=False)
print("   open", out)
