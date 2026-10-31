import json

from app.services.raster_view import LayerView
from app.ui.maps import layer_deck

VIEW = LayerView(png=b"\x89PNG fake", bounds=(105.0, 14.4, 105.1, 14.5))
BOUNDARY = {"type": "FeatureCollection", "features": []}


def spec(deck) -> dict:
    return json.loads(deck.to_json())


def test_raster_and_boundary_layers():
    layers = spec(layer_deck(VIEW, BOUNDARY, 0.6, "Light"))["layers"]
    assert [layer["@@type"] for layer in layers] == ["BitmapLayer", "GeoJsonLayer"]
    assert layers[0]["bounds"] == [105.0, 14.4, 105.1, 14.5] and layers[0]["opacity"] == 0.6
    assert layers[0]["image"].startswith("data:image/png;base64,")


def test_no_boundary_layer_without_boundary():
    assert len(spec(layer_deck(VIEW, None, 1.0, "Light"))["layers"]) == 1


def test_view_is_centred_on_the_layer():
    state = spec(layer_deck(VIEW, None, 1.0, "Light"))["initialViewState"]
    assert abs(state["longitude"] - 105.05) < 0.01 and abs(state["latitude"] - 14.45) < 0.01


def test_basemap_none_sends_no_tile_requests():
    deck = spec(layer_deck(VIEW, None, 1.0, "None"))
    assert deck.get("mapProvider") is None and deck.get("mapStyle") is None
    assert spec(layer_deck(VIEW, None, 1.0, "Dark"))["mapProvider"] == "carto"
