"""Map overlays for Explore: rain stations from the config and extra vector / CSV point layers kept per project."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from swatprep.config import SWATPrepConfig

COLORS = ["#ff7528", "#8e44ad", "#e91e63", "#f1c40f", "#16a085", "#795548", "#00bcd4", "#2c3e50"]
STATIONS_COLOR = "#00aa54"
CSV_SUFFIXES = (".csv", ".txt")
VECTOR_SUFFIXES = (".shp", ".gpkg", ".geojson", ".json")
# Outlines sent to the map are simplified (Douglas-Peucker) with a tolerance of extent / 5000: about 0.2 px
# on a 1000 px wide map, invisible until zoomed in 5x. Area and extent always come from the full geometry.
SIMPLIFY_FRACTION = 1 / 5000
DECIMALS = 6                     # 1e-6 degree ≈ 0.1 m: more digits only make the map payload bigger


@dataclass
class Overlay:
    path: str
    color: str
    visible: bool = True
    crs: str = "EPSG:4326"   # coordinates of a CSV layer; vector files carry their own CRS


@dataclass
class OverlayView:
    name: str
    kind: str = ""                                      # point | line | polygon | mixed
    count: int = 0
    points: list[dict] = field(default_factory=list)    # {"position": [lon, lat], "label": str}
    geojson: dict | None = None                         # lines and polygons, EPSG:4326
    bounds: tuple[float, float, float, float] | None = None   # west, south, east, north (degrees)
    area_km2: float | None = None
    error: str | None = None


def overlays_file(project: Path) -> Path:
    return Path(project) / ".swatprep" / "map_layers.json"


def load_overlays(project: Path) -> list[Overlay]:
    try:
        items = json.loads(overlays_file(project).read_text(encoding="utf-8"))
        return [Overlay(**{k: v for k, v in item.items() if k in Overlay.__dataclass_fields__}) for item in items]
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def save_overlays(project: Path, items: list[Overlay]) -> None:
    target = overlays_file(project)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps([asdict(i) for i in items], indent=2), encoding="utf-8")


def next_color(items: list[Overlay]) -> str:
    used = {i.color for i in items}
    return next((c for c in COLORS if c not in used), COLORS[len(items) % len(COLORS)])


def _read_csv_points(path: Path, crs: str):
    import geopandas as gpd

    from swatprep.core.weather import station_column

    table = pd.read_csv(path, dtype=str, encoding="utf-8-sig", skipinitialspace=True)
    table.columns = [station_column(c) for c in table.columns]
    if not {"lat", "lon"} <= set(table.columns):
        raise ValueError(f"needs lat and lon columns (LAT, LONG also work); found: {', '.join(table.columns)}")
    label = table["name"] if "name" in table else table["id"] if "id" in table else pd.Series(range(1, len(table) + 1))
    x, y = pd.to_numeric(table["lon"], errors="coerce"), pd.to_numeric(table["lat"], errors="coerce")
    if x.isna().any() or y.isna().any():
        raise ValueError("lat and lon must be numbers on every row")
    return gpd.GeoDataFrame({"label": label.astype(str).str.strip()}, geometry=gpd.points_from_xy(x, y), crs=crs)


def _read_vector(path: Path):
    import geopandas as gpd

    frame = gpd.read_file(path)
    if frame.crs is None:
        raise ValueError("has no CRS (missing .prj?)")
    names = [c for c in frame.columns if c.lower() in ("name", "label", "id")]
    frame["label"] = frame[names[0]].astype(str) if names else path.stem
    return frame[["label", "geometry"]]


def _metric_crs(frame, project_crs: str | None):
    """The project CRS when it is projected (metres), otherwise the UTM zone of the layer."""
    from pyproj import CRS

    if project_crs:
        crs = CRS.from_user_input(project_crs)
        if crs.is_projected:
            return crs
    return frame.to_crs("EPSG:4326").estimate_utm_crs()


def _display(others, project_crs: str | None):
    """Lines and polygons for the map: simplified in metres, then rounded to DECIMALS in degrees."""
    import shapely

    try:
        metric = others.to_crs(_metric_crs(others, project_crs))
        west, south, east, north = metric.total_bounds
        tolerance = max(east - west, north - south) * SIMPLIFY_FRACTION
        if tolerance > 0:
            metric = metric.set_geometry(metric.simplify(tolerance, preserve_topology=True))
        shown = metric.to_crs("EPSG:4326")
    except Exception:  # no CRS database, odd geometry: send it as it is
        shown = others.to_crs("EPSG:4326")
    return shown.set_geometry(shapely.set_precision(shown.geometry.values, 10 ** -DECIMALS))


def _view(name: str, frame, project_crs: str | None) -> OverlayView:
    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty]
    shown = frame.to_crs("EPSG:4326")
    types = set(shown.geom_type.str.replace("Multi", ""))
    kind = {"Point": "point", "LineString": "line", "Polygon": "polygon"}.get(types.pop(), "mixed") \
        if len(types) == 1 else "mixed"
    is_point = shown.geom_type.isin(["Point", "MultiPoint"])
    singles = shown[is_point].explode(index_parts=False)          # a MultiPoint becomes one row per point
    points = [{"position": [round(g.x, DECIMALS), round(g.y, DECIMALS)], "label": label}
              for g, label in zip(singles.geometry, singles["label"])]
    others = frame[~is_point.to_numpy()]
    area = None
    polygons = frame[frame.geom_type.isin(["Polygon", "MultiPolygon"])]
    if len(polygons) and project_crs:
        area = float(polygons.to_crs(project_crs).area.sum() / 1e6)
    return OverlayView(
        name=name, kind=kind, count=len(shown), points=points,
        geojson=json.loads(_display(others, project_crs).to_json(drop_id=True)) if len(others) else None,
        bounds=tuple(float(v) for v in shown.total_bounds) if len(shown) else None, area_km2=area,
    )


def read_overlay(path: Path, csv_crs: str = "EPSG:4326", project_crs: str | None = None) -> OverlayView:
    """A vector file or a CSV of points, ready for the map; problems come back in `error`."""
    path = Path(path)
    if not path.is_file():
        return OverlayView(name=path.name, error=f"{path.name}: not found")
    try:
        frame = _read_csv_points(path, csv_crs) if path.suffix.lower() in CSV_SUFFIXES else _read_vector(path)
        return _view(path.name, frame, project_crs)
    except Exception as exc:  # unreadable file, bad CRS, missing columns
        return OverlayView(name=path.name, error=f"{path.name}: {exc}")


def stations_path(cfg: SWATPrepConfig) -> Path | None:
    """The rain-station table of the config: the precipitation source first, then weather.stations."""
    weather = cfg.weather
    if weather is None:
        return None
    return weather.precip.stations if weather.precip is not None else weather.stations


def read_station_points(path: Path) -> OverlayView:
    """Station table (id, name, lat, lon, elev in any case) as points; lat/lon are degrees (WGS84)."""
    name = "Rain stations (config)"
    try:
        import geopandas as gpd

        from swatprep.core.weather import read_stations

        table = read_stations(Path(path))
        frame = gpd.GeoDataFrame({"label": table["name"].astype(str)},
                                 geometry=gpd.points_from_xy(table["lon"], table["lat"]), crs="EPSG:4326")
        return _view(name, frame, None)
    except Exception as exc:
        return OverlayView(name=name, error=f"Rain stations: {exc}")


def station_points(cfg: SWATPrepConfig) -> OverlayView | None:
    path = stations_path(cfg)
    return None if path is None else read_station_points(path)


def _covers(bounds, target) -> str:
    if bounds is None or target is None:
        return "—"
    return "yes" if bounds[0] <= target[0] and bounds[1] <= target[1] and bounds[2] >= target[2] \
        and bounds[3] >= target[3] else "no"


def extent_table(rows: list[tuple[str, OverlayView]], boundary_bounds) -> pd.DataFrame:
    """One row per layer: extent in degrees, polygon area and whether its extent covers the boundary's."""
    out = []
    for name, view in rows:
        b = view.bounds
        out.append({
            "layer": name,
            "west": b[0] if b else None, "south": b[1] if b else None,
            "east": b[2] if b else None, "north": b[3] if b else None,
            "area_km2": view.area_km2 if view.area_km2 is not None else float("nan"),
            "covers_boundary": "—" if name == "Boundary" else _covers(b, boundary_bounds),
        })
    return pd.DataFrame(out, columns=["layer", "west", "south", "east", "north", "area_km2", "covers_boundary"])
