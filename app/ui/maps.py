"""pydeck map for the Explore Map view (LayerView in, pdk.Deck out)."""
from __future__ import annotations

import base64

import pydeck as pdk

from app.services.raster_view import LayerView

BASEMAPS = ["Light", "Dark", "None"]
BOUNDARY = [26, 116, 255]   # theme blue #1a74ff


def layer_deck(view: LayerView, boundary: dict | None, opacity: float, basemap: str) -> pdk.Deck:
    west, south, east, north = view.bounds
    # pdk.types.String: pydeck would otherwise read a plain string as a JavaScript expression
    image = pdk.types.String("data:image/png;base64," + base64.b64encode(view.png).decode("ascii"))
    layers = [pdk.Layer("BitmapLayer", image=image, bounds=[west, south, east, north], opacity=opacity)]
    if boundary:
        layers.append(pdk.Layer("GeoJsonLayer", boundary, stroked=True, filled=False,
                                get_line_color=BOUNDARY, line_width_min_pixels=2))
    state = pdk.data_utils.compute_view([[west, south], [east, north]])
    if basemap == "None":
        return pdk.Deck(layers=layers, initial_view_state=state, map_provider=None, map_style=None, tooltip=False)
    return pdk.Deck(layers=layers, initial_view_state=state, map_provider="carto", map_style=basemap.lower(),
                    tooltip=False)
