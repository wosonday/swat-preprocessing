"""pydeck map for the Explore Map view (raster preview, boundary and overlays in, pdk.Deck out)."""
from __future__ import annotations

import base64

import pydeck as pdk

from app.services.overlays import OverlayView
from app.services.raster_view import LayerView

BASEMAPS = ["Light", "Dark", "None"]
BOUNDARY = [26, 116, 255]   # theme blue #1a74ff


def _rgb(color: str) -> list[int]:
    return [int(color[i:i + 2], 16) for i in (1, 3, 5)]


def _bounds_of(view: LayerView | None, overlays: list[tuple[OverlayView, str]]) -> list[list[float]]:
    boxes = [view.bounds] if view is not None and view.bounds else []
    boxes += [o.bounds for o, _ in overlays if o.bounds]
    return [[b[0], b[1]] for b in boxes] + [[b[2], b[3]] for b in boxes] or [[105.0, 16.0]]


def layer_deck(view: LayerView | None, boundary: dict | None, opacity: float, basemap: str,
               overlays: list[tuple[OverlayView, str]] = ()) -> pdk.Deck:
    """`overlays`: (layer, colour) pairs drawn over the raster: points as dots, lines and polygons as outlines."""
    layers = []
    if view is not None:
        west, south, east, north = view.bounds
        # pdk.types.String: pydeck would otherwise read a plain string as a JavaScript expression
        image = pdk.types.String("data:image/png;base64," + base64.b64encode(view.png).decode("ascii"))
        layers.append(pdk.Layer("BitmapLayer", image=image, bounds=[west, south, east, north], opacity=opacity))
    if boundary:
        layers.append(pdk.Layer("GeoJsonLayer", boundary, stroked=True, filled=False,
                                get_line_color=BOUNDARY, line_width_min_pixels=2))
    for layer, color in overlays:      # outlines first, so points stay on top
        if layer.geojson:
            layers.append(pdk.Layer("GeoJsonLayer", layer.geojson, stroked=True, filled=False,
                                    get_line_color=_rgb(color), line_width_min_pixels=2, pickable=True))
    for layer, color in overlays:
        if layer.points:
            # pdk.types.String again: a plain "pixels" would become the expression @@=pixels (huge circles)
            layers.append(pdk.Layer("ScatterplotLayer", layer.points, get_position="position",
                                    get_fill_color=_rgb(color), get_line_color=[255, 255, 255], stroked=True,
                                    radius_units=pdk.types.String("pixels"), get_radius=5,
                                    line_width_min_pixels=1, pickable=True))
    state = pdk.data_utils.compute_view(_bounds_of(view, list(overlays)))
    tooltip = {"text": "{label}"} if overlays else False
    if basemap == "None":
        return pdk.Deck(layers=layers, initial_view_state=state, map_provider=None, map_style=None, tooltip=tooltip)
    return pdk.Deck(layers=layers, initial_view_state=state, map_provider="carto", map_style=basemap.lower(),
                    tooltip=tooltip)
