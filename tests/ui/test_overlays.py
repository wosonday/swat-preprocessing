import json
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from app.services.explore_data import load_config
from app.services.overlays import (Overlay, extent_table, load_overlays, next_color, overlays_file, read_overlay,
                                   save_overlays, station_points)

BASIN = box(105.0, 19.6, 105.4, 20.2)          # degrees


def write_shp(path: Path, geoms, crs="EPSG:4326", **cols) -> Path:
    gpd.GeoDataFrame(cols or None, geometry=geoms, crs=crs).to_file(path)
    return path


def test_layers_round_trip_through_the_project_file(tmp_path):
    items = [Overlay(str(tmp_path / "q.csv"), "#ff7528"), Overlay(str(tmp_path / "s.shp"), "#8e44ad", visible=False)]
    save_overlays(tmp_path, items)
    assert overlays_file(tmp_path) == tmp_path / ".swatprep" / "map_layers.json"
    assert load_overlays(tmp_path) == items


def test_broken_or_missing_file_means_no_layers(tmp_path):
    assert load_overlays(tmp_path) == []
    overlays_file(tmp_path).parent.mkdir()
    overlays_file(tmp_path).write_text("{not json", encoding="utf-8")
    assert load_overlays(tmp_path) == []


def test_next_color_skips_used_ones():
    first = next_color([])
    assert next_color([Overlay("a", first)]) != first


def test_csv_points_with_swat_headers(tmp_path):
    csv = tmp_path / "Q_stations.csv"
    csv.write_text("ID,NAME,LAT,LONG\nQ1,Xa La,19.9,105.2\nQ2,Ban Na,20.1,105.3\n", encoding="utf-8")
    view = read_overlay(csv)
    assert view.error is None and view.kind == "point" and view.count == 2
    assert [p["label"] for p in view.points] == ["Xa La", "Ban Na"]
    assert view.points[0]["position"] == pytest.approx([105.2, 19.9])


def test_csv_in_utm_is_reprojected(tmp_path):
    csv = tmp_path / "utm.csv"
    csv.write_text("id,lat,lon\nP1,2200000,600000\n", encoding="utf-8")    # northing, easting in UTM 48N
    lon, lat = read_overlay(csv, csv_crs="EPSG:32648").points[0]["position"]
    assert 105.9 < lon < 106.0 and 19.8 < lat < 19.95


def test_polygons_are_outlines_with_area(tmp_path):
    shp = write_shp(tmp_path / "big.shp", [box(104.9, 19.5, 105.5, 20.3)])
    view = read_overlay(shp, project_crs="EPSG:32648")
    assert view.kind == "polygon" and view.count == 1 and view.geojson["features"]
    assert view.bounds == pytest.approx((104.9, 19.5, 105.5, 20.3))
    assert 5000 < view.area_km2 < 6000          # 0.6° × 0.8° near 20° N


def test_projected_shapefile_is_shown_in_degrees(tmp_path):
    shp = write_shp(tmp_path / "utm.shp", [Point(600000, 2200000)], crs="EPSG:32648")
    lon, lat = read_overlay(shp).points[0]["position"]
    assert 105.9 < lon < 106.0


def test_errors_never_raise(tmp_path):
    assert "not found" in read_overlay(tmp_path / "missing.shp").error
    gpd.GeoDataFrame(geometry=[Point(1, 1)]).to_file(tmp_path / "nocrs.shp")
    assert "no CRS" in read_overlay(tmp_path / "nocrs.shp").error
    (tmp_path / "bad.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    assert "lat" in read_overlay(tmp_path / "bad.csv").error


def test_rain_stations_come_from_the_config(example_project):
    view = station_points(load_config(example_project)[0])
    assert view.error is None and view.count == 1 and view.points[0]["label"] == "StationA"


def test_extent_table_flags_layers_that_cover_the_basin(tmp_path):
    basin = read_overlay(write_shp(tmp_path / "basin.shp", [BASIN]))
    big = read_overlay(write_shp(tmp_path / "big.shp", [box(104.9, 19.5, 105.5, 20.3)]))
    small = read_overlay(write_shp(tmp_path / "small.shp", [box(105.1, 19.7, 105.2, 19.8)]))
    table = extent_table([("Boundary", basin), ("big.shp", big), ("small.shp", small)], basin.bounds).set_index("layer")
    assert table.loc["big.shp", "covers_boundary"] == "yes"
    assert table.loc["small.shp", "covers_boundary"] == "no"
    assert table.loc["Boundary", "covers_boundary"] == "—"
