import io
import shutil
from pathlib import Path

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

from app.services.explore_data import load_config
from app.services.raster_view import Layer, boundary_geojson, output_layers, render_layer


def write_tif(path: Path, data: np.ndarray, nodata, crs="EPSG:32648") -> Path:
    profile = dict(driver="GTiff", height=data.shape[0], width=data.shape[1], count=1, dtype=data.dtype.name,
                   transform=from_origin(500000, 1600000, 30, 30), nodata=nodata, crs=crs)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
    return path


@pytest.fixture
def landuse(tmp_path) -> Layer:
    data = np.ones((100, 200), dtype="int16")
    data[:, 100:] = 2
    data[:10, :10] = 0                                      # NoData corner (top-left)
    tif = write_tif(tmp_path / "lu.tif", data, nodata=0)
    lookup = tmp_path / "landuse_vlookup.csv"
    lookup.write_text("LANDUSE_ID,SWAT_CODE\n1,AGRL\n2,FRST\n", encoding="utf-8")
    return Layer("Land use", tif, "categorical", lookup)


def image(view) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(view.png)))


def test_categorical_preview_is_small_and_transparent_at_nodata(landuse):
    view = render_layer(landuse, max_px=50)
    rgba = image(view)
    assert view.error is None and max(rgba.shape[:2]) <= 60   # warping may add a few pixels
    assert rgba[0, 0, 3] == 0 and rgba[-1, -1, 3] == 255


def test_bounds_are_the_raster_extent_in_degrees(landuse):
    view = render_layer(landuse)
    expected = transform_bounds("EPSG:32648", "EPSG:4326", 500000, 1600000 - 100 * 30, 500000 + 200 * 30, 1600000)
    assert view.bounds == pytest.approx(expected, abs=5e-4)   # within ~1 pixel: 30 m ≈ 0.0003°


def test_legend_has_swat_names_and_full_resolution_areas(landuse):
    legend = render_layer(landuse, max_px=50).legend.set_index("code")
    assert list(legend["label"]) == ["AGRL", "FRST"]
    assert legend["pct_area"].sum() == pytest.approx(100)
    assert legend.loc[1, "pixels"] == 100 * 100 - 10 * 10 and legend.loc[2, "pixels"] == 100 * 100


def test_stats_report_nodata_share(landuse):
    stats = render_layer(landuse).stats
    assert stats["NoData"] == "0.5%" and stats["Rows × columns"] == "100 × 200" and stats["CRS"] == "EPSG:32648"


def test_continuous_layer_has_a_five_step_legend(tmp_path):
    dem = write_tif(tmp_path / "dem.tif", np.linspace(100, 500, 400, dtype="float32").reshape(20, 20), nodata=-9999)
    view = render_layer(Layer("DEM", dem, "continuous"))
    assert list(view.legend["label"]) == ["100.0", "200.0", "300.0", "400.0", "500.0"]
    assert view.stats["Range"] == "100.0 – 500.0"


def test_layer_without_crs_is_an_error(tmp_path):
    tif = write_tif(tmp_path / "nocrs.tif", np.ones((5, 5), dtype="int16"), nodata=0, crs=None)
    view = render_layer(Layer("X", tif, "categorical"))
    assert view.png is None and "no CRS" in view.error


def test_output_layers_lists_only_built_files(example_project):
    cfg, _ = load_config(example_project)
    assert output_layers(cfg) == []
    spatial = example_project.parent / "output" / "spatial"
    spatial.mkdir(parents=True)
    shutil.copy(example_project.parent / "data" / "dem_30m.tif", spatial / "dem_projected.tif")
    assert [(layer.name, layer.kind) for layer in output_layers(cfg)] == [("DEM", "continuous")]


def test_boundary_geojson(example_project):
    geojson, error = boundary_geojson(example_project.parent / "data" / "boundary.geojson")
    assert error is None and geojson["type"] == "FeatureCollection" and geojson["features"]
    assert boundary_geojson(None) == (None, None)
    assert boundary_geojson(example_project.parent / "missing.geojson")[1].startswith("Boundary not shown")
