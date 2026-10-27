"""Form layout as data: which fields each section shows, in which order, and how paths behave."""
from __future__ import annotations

from pydantic import BaseModel

from swatprep.config import (
    ClipItemConfig, DEMConfig, FillCSVConfig, FillNetCDFConfig, LandUseConfig, ProjectConfig, SoilConfig,
    StreamflowConfig, SWATPrepConfig, WeatherConfig, WeatherFillConfig, WeatherSourceConfig, WeatherUnitsConfig,
)

# Field order per model. Every field of every config model must appear here (checked by tests).
LAYOUT: dict[type[BaseModel], list[str]] = {
    SWATPrepConfig: ["project", "clip", "dem", "landuse", "soil", "weather", "streamflow"],
    ProjectConfig: ["name", "crs", "boundary", "output_dir", "targets"],
    ClipItemConfig: ["src", "dst", "mask", "resampling", "resolution"],
    DEMConfig: ["path", "output_name", "clip", "resampling", "resolution"],
    LandUseConfig: ["raster", "lookup", "source_code_col", "swat_code_col", "swat_name_col",
                    "output_name", "clip", "output_lookup", "resolution"],
    SoilConfig: ["raster", "table", "soil_key_col", "output_usersoil", "usersoil_format",
                 "output_name", "clip", "output_lookup", "resolution"],
    WeatherConfig: ["stations", "data_dir", "file_pattern", "precip", "temp", "format", "variables",
                    "start", "end", "units", "missing_policy", "fill"],
    WeatherSourceConfig: ["stations", "data_dir", "file_pattern"],
    WeatherUnitsConfig: ["precip", "temperature"],
    WeatherFillConfig: ["type", "output_dir", "min_overlap_days", "run_in_build", "csv", "netcdf"],
    FillCSVConfig: ["stations", "data_dir", "file_pattern"],
    FillNetCDFConfig: ["path", "var_map", "lat_name", "lon_name", "time_name", "search_radius"],
    StreamflowConfig: ["path", "format", "glob", "stations", "date_col", "station_id_col", "value_col", "units"],
}

# Optional sections of the root config, in tab order: key -> (tab label, model)
SECTIONS: dict[str, tuple[str, type[BaseModel]]] = {
    "clip": ("Clip", ClipItemConfig),
    "dem": ("DEM", DEMConfig),
    "landuse": ("Land use", LandUseConfig),
    "soil": ("Soil", SoilConfig),
    "weather": ("Weather", WeatherConfig),
    "streamflow": ("Streamflow", StreamflowConfig),
}

# What a Path field points at. Default: "file".
#   dir: a folder; file_or_dir: either; output: written by swatprep, may not exist yet.
PATH_KINDS: dict[tuple[type[BaseModel], str], str] = {
    (ProjectConfig, "output_dir"): "output",
    (ClipItemConfig, "dst"): "output",
    (WeatherConfig, "data_dir"): "dir",
    (WeatherSourceConfig, "data_dir"): "dir",
    (WeatherFillConfig, "output_dir"): "output",
    (FillCSVConfig, "data_dir"): "dir",
    (StreamflowConfig, "path"): "file_or_dir",
}

# Labels that read better than the field name.
LABELS: dict[str, str] = {
    "crs": "CRS",
    "output_dir": "Output folder",
    "dem": "DEM",
    "src": "Source raster",
    "dst": "Output raster",
    "data_dir": "Data folder",
    "stations": "Stations file",
    "var_map": "Variable map",
    "usersoil_format": "Usersoil format",
    "output_usersoil": "Write usersoil",
    "output_lookup": "Write lookup",
    "clip": "Clip to boundary",
    "mask": "Mask outside boundary",
    "missing_policy": "Missing data policy",
    "min_overlap_days": "Minimum overlap (days)",
    "run_in_build": "Fill during build",
    "search_radius": "Search radius (cells)",
}


def path_kind(model: type[BaseModel], name: str) -> str:
    return PATH_KINDS.get((model, name), "file")


def all_models(root: type[BaseModel] = SWATPrepConfig) -> list[type[BaseModel]]:
    """The root model and every model nested inside it."""
    from app.services.form_model import field_spec

    seen: list[type[BaseModel]] = []
    stack = [root]
    while stack:
        model = stack.pop()
        if model in seen:
            continue
        seen.append(model)
        for name in model.model_fields:
            nested = field_spec(model, name).nested
            if nested is not None:
                stack.append(nested)
    return seen
