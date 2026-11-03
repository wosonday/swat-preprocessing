"""Synthetic basin for the map examples: a DEM, a detailed boundary, rain stations and their daily rain.

Everything is written once to <temp>/swatprep_demo and reused. Coordinates are UTM 48N (EPSG:32648),
around 105.9°E, 14.9°N; no real data is involved.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(tempfile.gettempdir()) / "swatprep_demo"
CRS = "EPSG:32648"
X0, Y0, CELL = 600_000, 1_660_000, 30          # upper-left corner and pixel size (m)


def make(size: int = 3000, overviews: bool = False) -> dict[str, Path]:
    """Return paths of dem.tif, boundary.geojson, stations.csv and the rain folder (created if missing)."""
    import geopandas as gpd
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from shapely.geometry import Polygon

    ROOT.mkdir(exist_ok=True)
    dem = ROOT / f"dem_{size}{'_ovr' if overviews else ''}.tif"
    if not dem.exists():
        rng = np.random.default_rng(0)
        profile = {"driver": "GTiff", "width": size, "height": size, "count": 1, "dtype": "float32", "crs": CRS,
                   "transform": from_origin(X0, Y0, CELL, CELL), "nodata": -9999.0, "tiled": True,
                   "blockxsize": 512, "blockysize": 512, "compress": "deflate"}
        with rasterio.open(dem, "w", **profile) as dst:
            for r0 in range(0, size, 500):                     # write by strips: bounded memory
                rows = min(500, size - r0)
                y, x = np.mgrid[r0:r0 + rows, 0:size]
                z = 400 + 600 * np.exp(-((x - size / 2) ** 2 + (y - size / 3) ** 2) / (0.1 * size ** 2)) \
                    + 40 * np.sin(x / 90) * np.cos(y / 130) + rng.normal(0, 3, (rows, size))
                dst.write(z.astype("float32"), 1, window=rasterio.windows.Window(0, r0, size, rows))
            if overviews:
                dst.build_overviews([2, 4, 8, 16, 32], Resampling.average)   # pyramids for fast previews

    basin = 3000                                    # the basin is the same whatever the DEM size
    cx, cy, half = X0 + basin * CELL / 2, Y0 - basin * CELL / 2, basin * CELL / 2
    boundary = ROOT / "boundary.geojson"
    if not boundary.exists():                                   # a digitised-looking outline, 20 000 vertices
        t = np.linspace(0, 2 * np.pi, 20_000, endpoint=False)
        r = 0.7 * half * (1 + 0.08 * np.sin(7 * t) + 0.01 * np.sin(211 * t))
        poly = Polygon(np.c_[cx + r * np.cos(t), cy + r * np.sin(t)])
        gpd.GeoDataFrame({"name": ["Demo basin"]}, geometry=[poly], crs=CRS).to_file(boundary)

    stations = ROOT / "stations.csv"
    rain = ROOT / "rain"
    if not stations.exists():
        points = gpd.GeoSeries.from_xy(cx + half * np.array([-0.5, 0.1, 0.45, -0.2, 0.3]),
                                       cy + half * np.array([0.4, 0.55, -0.1, -0.5, 0.2]), crs=CRS).to_crs(4326)
        ids = [f"ST{i:03d}" for i in range(1, 6)]
        pd.DataFrame({"id": ids, "name": [f"Station {i}" for i in range(1, 6)], "lat": points.y.round(5),
                      "lon": points.x.round(5), "elev": [420, 610, 380, 350, 500]}).to_csv(stations, index=False)
        rain.mkdir(exist_ok=True)
        days = pd.date_range("2010-01-01", "2014-12-31", freq="D")
        rng = np.random.default_rng(1)
        season = 1 + 0.9 * np.sin(2 * np.pi * (days.dayofyear - 120) / 365)   # wet season peaking in July-August
        for k, sid in enumerate(ids):
            wet = rng.random(len(days)) < 0.25 * season
            value = np.where(wet, rng.gamma(0.8, 12 * (1 + 0.1 * k), len(days)), 0.0)
            pd.DataFrame({"date": days.strftime("%Y-%m-%d"), "precip": value.round(1)}).to_csv(
                rain / f"{sid}.csv", index=False)
    return {"dem": dem, "boundary": boundary, "stations": stations, "rain": rain}
