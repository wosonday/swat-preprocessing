"""Output rasters for the Explore map: list them, render a small RGBA preview, and count classes."""
from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from swatprep.config import SWATPrepConfig

# Web Mercator: deck.gl stretches a BitmapLayer linearly on screen, i.e. in EPSG:3857, so the preview is
# warped to 3857 and only its corner bounds are given in degrees.
MAP_CRS = "EPSG:3857"
VIRIDIS = ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"]
CATEGORIES = ["#1a74ff", "#00aa54", "#ff7528", "#f04142", "#8e44ad", "#87ea5c", "#f1c40f", "#16a085",
              "#d35400", "#2c3e50", "#e91e63", "#795548", "#00bcd4", "#9e9d24", "#5c6bc0", "#a1887f"]
LEGEND_COLUMNS = ["code", "label", "color", "pixels", "pct_area"]


@dataclass
class Layer:
    name: str
    path: Path
    kind: Literal["continuous", "categorical"]
    lookup: Path | None = None


@dataclass
class LayerView:
    png: bytes | None = None
    bounds: tuple[float, float, float, float] | None = None   # west, south, east, north (degrees)
    legend: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=LEGEND_COLUMNS))
    stats: dict = field(default_factory=dict)
    error: str | None = None


def _is_integer(path: Path) -> bool:
    import rasterio

    with rasterio.open(path) as src:
        return np.issubdtype(np.dtype(src.dtypes[0]), np.integer)


def output_layers(cfg: SWATPrepConfig) -> list[Layer]:
    """Rasters written by Build that exist on disk, in the order DEM, land use, soil, clip items."""
    out = cfg.project.output_dir
    layers: list[Layer] = []
    if cfg.dem is not None:
        layers.append(Layer("DEM", out / "spatial" / cfg.dem.output_name, "continuous"))
    if cfg.landuse is not None:
        layers.append(Layer("Land use", out / "landuse" / cfg.landuse.output_name, "categorical",
                            out / "landuse" / "landuse_vlookup.csv"))
    if cfg.soil is not None:
        layers.append(Layer("Soil", out / "soil" / cfg.soil.output_name, "categorical",
                            out / "soil" / "soil_vlookup.csv"))
    for item in cfg.clip or []:
        if item.dst.is_file():
            kind = "categorical" if _is_integer(item.dst) else "continuous"
            layers.append(Layer(f"Clip: {item.dst.name}", item.dst, kind))
    return [layer for layer in layers if layer.path.is_file()]


def _hex(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _ramp(values: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Viridis colours for values in [lo, hi] (N x 3, uint8)."""
    t = np.zeros_like(values) if hi <= lo else np.clip((values - lo) / (hi - lo), 0, 1)
    stops = np.linspace(0, 1, len(VIRIDIS))
    rgb = np.array([_hex(c) for c in VIRIDIS], dtype=float)
    return np.stack([np.interp(t, stops, rgb[:, k]) for k in range(3)], axis=-1).astype(np.uint8)


def _labels(lookup: Path | None) -> dict[int, str]:
    """First column = raster code, second column = label (LANDUSE_ID/SWAT_CODE, SOIL_ID/SNAM)."""
    if lookup is None or not lookup.is_file():
        return {}
    table = pd.read_csv(lookup)
    return {int(code): str(label) for code, label in zip(table.iloc[:, 0], table.iloc[:, 1])}


def _stored(src, categorical: bool) -> tuple[int, int, dict[int, int], float, float] | None:
    """The statistics Build keeps in the GeoTIFF (GDAL STATISTICS_* tags, class counts): exact and free."""
    import json

    from swatprep.utils.raster import CLASS_COUNTS_TAG

    tags = src.tags(1)
    try:
        total = src.width * src.height
        if categorical:
            counts = {int(code): int(n) for code, n in json.loads(tags[CLASS_COUNTS_TAG]).items()}
            return total, sum(counts.values()), counts, math.inf, -math.inf
        valid = round(total * float(tags["STATISTICS_VALID_PERCENT"]) / 100)
        return total, valid, {}, float(tags["STATISTICS_MINIMUM"]), float(tags["STATISTICS_MAXIMUM"])
    except (KeyError, ValueError, TypeError, AttributeError):
        return None


def _scan(src, categorical: bool, preview: np.ndarray) -> tuple[int, int, dict[int, int], float, float]:
    """Total pixels, valid pixels, class counts, min, max, for a raster without stored statistics.

    Categorical: exact counts over every pixel (a small class must stay in the legend), with the fast
    exact counter of the core. Continuous: from the `preview` already read (NaN = NoData), so no second
    pass over the full raster; exact when the preview is full resolution, approximate otherwise.
    """
    from swatprep.utils.raster import class_counts

    total = src.width * src.height
    if categorical:
        counts = {int(code): int(n) for code, n in class_counts(src).items()}
        return total, sum(counts.values()), counts, math.inf, -math.inf
    ok = ~np.isnan(preview)
    if not ok.any():
        return total, 0, {}, math.inf, -math.inf
    valid = round(total * float(ok.mean()))
    return total, valid, {}, float(preview[ok].min()), float(preview[ok].max())


def render_layer(layer: Layer, max_px: int = 1024) -> LayerView:
    """A PNG preview (longest side <= max_px) in Web Mercator with its bounds in degrees; never raises."""
    import rasterio
    from PIL import Image
    from rasterio.enums import Resampling
    from rasterio.warp import calculate_default_transform, reproject, transform_bounds

    from swatprep.utils.raster import gdal_env

    categorical = layer.kind == "categorical"
    resampling = Resampling.nearest if categorical else Resampling.bilinear
    try:
        with gdal_env(), rasterio.open(layer.path) as src:
            if src.crs is None:
                return LayerView(error=f"{layer.name}: layer has no CRS, so it cannot be placed on the map.")
            scale = max(src.width, src.height) / max_px
            h, w = (max(1, round(src.height / scale)), max(1, round(src.width / scale))) if scale > 1 \
                else (src.height, src.width)
            small = src.read(1, out_shape=(h, w), resampling=resampling, masked=True).astype("float64").filled(np.nan)
            small_transform = src.transform * src.transform.scale(src.width / w, src.height / h)
            dst_transform, dw, dh = calculate_default_transform(src.crs, MAP_CRS, w, h, *src.bounds)
            warped = np.full((dh, dw), np.nan)
            reproject(small, warped, src_transform=small_transform, src_crs=src.crs, src_nodata=np.nan,
                      dst_transform=dst_transform, dst_crs=MAP_CRS, dst_nodata=np.nan, resampling=resampling)
            stored = _stored(src, categorical)
            total, valid, counts, lo, hi = stored or _scan(src, categorical, small)
            approx = "≈ " if not stored and not categorical and (h, w) != (src.height, src.width) else ""
            stats = {"CRS": src.crs.to_string(), "Pixel size": f"{src.res[0]:g} × {src.res[1]:g}",
                     "Rows × columns": f"{src.height} × {src.width}",
                     "NoData": f"{approx}{100 * (total - valid) / total:.1f}%" if total else "n/a"}
    except Exception as exc:  # unreadable or corrupt file
        return LayerView(error=f"{layer.name}: {exc}")

    rgba = np.zeros((dh, dw, 4), dtype=np.uint8)
    ok = ~np.isnan(warped)
    if categorical:
        codes = sorted(counts)
        colors = {code: CATEGORIES[i % len(CATEGORIES)] for i, code in enumerate(codes)}
        for code, color in colors.items():
            rgba[ok & (warped == code), :3] = _hex(color)
        names = _labels(layer.lookup)
        legend = pd.DataFrame([[code, names.get(code, str(code)), colors[code], counts[code],
                                100 * counts[code] / valid] for code in codes], columns=LEGEND_COLUMNS)
    else:
        rgba[ok, :3] = _ramp(warped[ok], lo, hi)
        values = np.linspace(lo, hi, len(VIRIDIS)) if valid else []
        legend = pd.DataFrame([[None, f"{v:,.1f}", c, None, None] for v, c in zip(values, VIRIDIS)],
                              columns=LEGEND_COLUMNS)
        if valid:
            stats["Range"] = f"{approx}{lo:,.1f} – {hi:,.1f}"
    rgba[ok, 3] = 255
    buffer = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buffer, format="PNG")
    west = dst_transform.c
    north = dst_transform.f
    bounds = transform_bounds(MAP_CRS, "EPSG:4326", west, north + dh * dst_transform.e, west + dw * dst_transform.a, north)
    return LayerView(buffer.getvalue(), tuple(bounds), legend, stats)


def boundary_geojson(path: Path | None) -> tuple[dict | None, str | None]:
    """The project boundary in EPSG:4326 as GeoJSON, or (None, reason)."""
    if path is None:
        return None, None
    try:
        import geopandas as gpd

        frame = gpd.read_file(path)
        if frame.crs is None:
            return None, "Boundary has no CRS."
        return frame.to_crs("EPSG:4326").__geo_interface__, None
    except Exception as exc:
        return None, f"Boundary not shown: {exc}"
