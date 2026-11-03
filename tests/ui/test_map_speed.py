"""v0.9.0: lighter map payload (simplified outlines, compact JSON) and faster previews."""
import json

import geopandas as gpd
import numpy as np
import pydeck as pdk
import pytest
import rasterio
from pydeck.bindings.json_tools import serialize
from rasterio.transform import from_origin
from shapely.geometry import Point, Polygon

from app.services.overlays import SIMPLIFY_FRACTION, read_overlay
from app.services.raster_view import Layer, render_layer
from app.ui.maps import layer_deck
from swatprep.utils.raster import add_overviews


@pytest.fixture
def detailed_basin(tmp_path):
    """A digitised-looking outline, 20 000 vertices, about 60 km across (UTM 48N)."""
    t = np.linspace(0, 2 * np.pi, 20_000, endpoint=False)
    r = 30_000 * (1 + 0.08 * np.sin(7 * t) + 0.01 * np.sin(211 * t))
    poly = Polygon(np.c_[600_000 + r * np.cos(t), 1_600_000 + r * np.sin(t)])
    path = tmp_path / "basin.geojson"
    gpd.GeoDataFrame({"name": ["Basin"]}, geometry=[poly], crs="EPSG:32648").to_file(path)
    return path, poly


def _vertices(geojson) -> int:
    return sum(len(ring) for f in geojson["features"] for ring in f["geometry"]["coordinates"])


def test_outline_is_simplified_for_display_only(detailed_basin):
    path, poly = detailed_basin
    view = read_overlay(path, project_crs="EPSG:32648")
    assert _vertices(view.geojson) < 4_000                       # from 20 001
    assert view.area_km2 == pytest.approx(poly.area / 1e6)      # area and extent from the full geometry
    full = gpd.GeoSeries([poly], crs="EPSG:32648").to_crs(4326)
    assert view.bounds == pytest.approx(tuple(full.total_bounds))


def test_simplified_outline_stays_within_the_tolerance(detailed_basin):
    path, poly = detailed_basin
    shown = gpd.GeoDataFrame.from_features(read_overlay(path, project_crs="EPSG:32648").geojson, crs=4326)
    shown = shown.to_crs("EPSG:32648").geometry.iloc[0]
    width = max(poly.bounds[2] - poly.bounds[0], poly.bounds[3] - poly.bounds[1])
    assert shown.hausdorff_distance(poly) <= width * SIMPLIFY_FRACTION + 0.5   # + rounding to 1e-6 degree


def test_coordinates_are_rounded_to_six_decimals(detailed_basin):
    path, _ = detailed_basin
    view = read_overlay(path, project_crs="EPSG:32648")
    x, y = view.geojson["features"][0]["geometry"]["coordinates"][0][0]
    assert x == round(x, 6) and y == round(y, 6)


def test_outline_without_project_crs_is_simplified_in_utm(detailed_basin):
    path, _ = detailed_basin
    assert _vertices(read_overlay(path).geojson) < 4_000


def test_points_are_kept(tmp_path):
    path = tmp_path / "pts.geojson"
    gpd.GeoDataFrame({"name": ["a", "b"]}, geometry=[Point(105.1234567, 15.0), Point(105.2, 15.1)],
                     crs=4326).to_file(path)
    view = read_overlay(path)
    assert [p["position"] for p in view.points] == [[105.123457, 15.0], [105.2, 15.1]]


def test_deck_json_is_compact_and_equivalent(detailed_basin):
    path, _ = detailed_basin
    deck = layer_deck(None, read_overlay(path, project_crs="EPSG:32648").geojson, 0.8, "None")
    text = deck.to_json()
    assert "\n" not in text and ", " not in text
    assert json.loads(text) == json.loads(serialize(deck))      # same content as pydeck's indented JSON
    assert isinstance(deck, pdk.Deck)


def test_detailed_outline_payload_is_small(detailed_basin):
    path, _ = detailed_basin
    deck = layer_deck(None, read_overlay(path, project_crs="EPSG:32648").geojson, 0.8, "None")
    assert len(deck.to_json()) < 150_000                         # 2.4 MB before v0.9.0


def _tif(path, data, nodata):
    with rasterio.open(path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1,
                       dtype=data.dtype.name, crs="EPSG:32648", transform=from_origin(500000, 1600000, 30, 30),
                       nodata=nodata, tiled=True, blockxsize=256, blockysize=256) as ds:
        ds.write(data, 1)
    return path


def test_large_continuous_preview_reports_approximate_stats(tmp_path):
    data = np.fromfunction(lambda r, c: r + c, (2400, 2400), dtype="float32")
    tif = _tif(tmp_path / "dem.tif", data, -9999)
    add_overviews(tif, categorical=False)
    view = render_layer(Layer("DEM", tif, "continuous"), max_px=600)
    assert view.stats["Range"].startswith("≈ ") and view.stats["NoData"].startswith("≈ ")
    lo, hi = (float(v.replace(",", "")) for v in view.stats["Range"][2:].split(" – "))
    assert lo == pytest.approx(0, abs=10) and hi == pytest.approx(4798, abs=10)


def test_large_categorical_legend_stays_exact(tmp_path):
    data = np.ones((2400, 2400), dtype="uint8")
    data[:5, :5] = 7                                             # a 25-pixel class: invisible in the preview
    data[-1, -1] = 0
    tif = _tif(tmp_path / "lu.tif", data, 0)
    add_overviews(tif, categorical=True)
    legend = render_layer(Layer("Land use", tif, "categorical"), max_px=600).legend.set_index("code")
    assert legend.loc[7, "pixels"] == 25 and legend.loc[1, "pixels"] == 2400 * 2400 - 26


def test_preview_uses_statistics_stored_by_build(tmp_path):
    """Stats written by Build are used as they are: exact, and no pass over the pixels."""
    data = np.fromfunction(lambda r, c: r + c, (2400, 2400), dtype="float32")
    tif = _tif(tmp_path / "dem.tif", data, -9999)
    with rasterio.open(tif, "r+") as ds:          # deliberately different from the pixels: proves they are read
        ds.update_tags(1, STATISTICS_MINIMUM="-5", STATISTICS_MAXIMUM="9000", STATISTICS_VALID_PERCENT="80")
    view = render_layer(Layer("DEM", tif, "continuous"), max_px=600)
    assert view.stats["Range"] == "-5.0 – 9,000.0" and view.stats["NoData"] == "20.0%"


def test_preview_uses_class_counts_stored_by_build(tmp_path):
    import json

    from swatprep.utils.raster import CLASS_COUNTS_TAG

    tif = _tif(tmp_path / "lu.tif", np.ones((100, 100), dtype="uint8"), 0)
    with rasterio.open(tif, "r+") as ds:
        ds.update_tags(1, **{CLASS_COUNTS_TAG: json.dumps({"1": 9000, "4": 1000})})
    legend = render_layer(Layer("Land use", tif, "categorical")).legend.set_index("code")
    assert legend.loc[4, "pixels"] == 1000 and legend.loc[1, "pct_area"] == pytest.approx(90)
