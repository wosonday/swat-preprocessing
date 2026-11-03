"""Example 7: measure what makes the map slow, and what each v0.9.0 optimisation saves.

Run:  uv run python docs/learning/07_optimize_map.py [RASTER]
RASTER: one of your own rasters (e.g. a DEM); without it a synthetic 6000 x 6000 DEM is used.
Copies are written to the demo folder; the original is never changed.
"""
import functools
import json
import shutil
import sys
import time
from pathlib import Path

import geopandas as gpd
import rasterio
from demo_data import ROOT, make
from pydeck.bindings.json_tools import serialize
from rasterio.enums import Resampling

from app.services.overlays import read_overlay
from app.services.raster_view import Layer, render_layer
from app.ui.maps import layer_deck
from swatprep.utils.raster import add_overviews, masked_stats, store_stats


def best(fn, repeat=3):
    """Shortest of a few runs: the first run also pays for disk cache and imports."""
    times = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    return min(times)


def fresh(path, work):
    """Open the file anew for each run, as render_layer does (a reused handle keeps GDAL's block cache warm)."""
    def run():
        with rasterio.open(path) as src:
            return work(src)
    return run


source = Path(sys.argv[1]) if len(sys.argv) > 1 else make(6000)["dem"]
variants = {"as written by v0.8.0      ": ROOT / f"{source.stem}_plain{source.suffix}",
            "+ overviews               ": ROOT / f"{source.stem}_ovr{source.suffix}",
            "+ overviews + statistics  ": ROOT / f"{source.stem}_ovr_stats{source.suffix}"}
for i, path in enumerate(variants.values()):
    if not path.exists():
        shutil.copy(source, path)
        if i >= 1:
            add_overviews(path, categorical=False)      # what Build does since v0.9.0 (project.overviews)
        if i == 2:
            store_stats(path, categorical=False)        # GDAL STATISTICS_* tags in the GeoTIFF
print(f"raster: {source} ({source.stat().st_size / 1e6:.0f} MB)")

print("A. Raster preview (render_layer, longest side 1024 px)")
full_pass = best(fresh(source, masked_stats), repeat=1)
print(f"   (a full-resolution statistics pass, which v0.8.0 made on every first view: {full_pass:.2f} s)")
for label, path in variants.items():
    read = best(fresh(path, lambda src: src.read(1, out_shape=(1024, 1024), resampling=Resampling.bilinear)))
    total = best(lambda p=path: render_layer(Layer("DEM", p, "continuous")))
    shown = render_layer(Layer("DEM", path, "continuous")).stats["Range"]
    print(f"   {label}: total {total:.2f} s | decimated read {read:.2f} s | Range shown: {shown}")

print("B. Preview size vs max_px (bytes sent to the browser on every rerun)")
for px in (512, 1024, 2048):
    view = render_layer(Layer("DEM", variants["+ overviews               "], "continuous"), max_px=px)
    print(f"   max_px={px:4}: PNG {len(view.png) / 1e3:5.0f} kB, base64 in the Deck JSON ≈ {len(view.png) * 4 / 3 / 1e3:5.0f} kB")

print("C. Boundary outline (20 000 vertices) in the map payload")
boundary = make()["boundary"]
raw = json.loads(gpd.read_file(boundary).to_crs(4326).to_json())
light = read_overlay(boundary, project_crs="EPSG:32648")      # v0.9.0: simplified to extent/5000, 6 decimals
old_deck = layer_deck(None, raw, 0.8, "None")
print(f"   v0.8.0: full outline, pydeck's indented JSON: {len(serialize(old_deck)) / 1e3:6.0f} kB")
print(f"   full outline, compact JSON:                   {len(old_deck.to_json()) / 1e3:6.0f} kB")
print(f"   v0.9.0: simplified outline, compact JSON:     {len(layer_deck(None, light.geojson, 0.8, 'None').to_json()) / 1e3:6.0f} kB"
      f"  (area still {light.area_km2:.1f} km², from the full outline)")

print("D. Cache keyed by (path, modification time): the second call costs nothing")


@functools.lru_cache(maxsize=8)        # in the app: @st.cache_data, which also survives reruns and sessions
def cached(path, mtime):
    return read_overlay(path, project_crs="EPSG:32648")


first = best(lambda: cached(boundary, boundary.stat().st_mtime), repeat=1)
second = best(lambda: cached(boundary, boundary.stat().st_mtime), repeat=1)
print(f"   read_overlay: first {first:.3f} s, cached {second:.4f} s")
