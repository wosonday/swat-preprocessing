"""Pydantic v2 config schema for swatprep.

Load from YAML:
    cfg = SWATPrepConfig.from_yaml("config.yaml")

All Path fields are stored as-is (relative to the caller's working directory).
Existence checks happen at preprocessing time, not at load time, so that
`swatprep validate` can report all missing files at once rather than one by one.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic import model_validator


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------


class ProjectConfig(BaseModel):
    name: str
    crs: str  # e.g. "EPSG:32648" — target projected CRS for all spatial work
    boundary: Optional[Path] = None  # GeoPackage / Shapefile / GeoJSON
    output_dir: Path = Path("./output")
    targets: list[Literal["swatplus", "swat"]] = Field(default=["swatplus"])


class DEMConfig(BaseModel):
    path: Path
    output_name: str = "dem_projected.tif"


class LandUseConfig(BaseModel):
    raster: Path
    lookup: Path  # CSV with columns: source_code_col, swat_code_col, swat_name_col
    source_code_col: str = "code"
    swat_code_col: str = "swat_code"
    swat_name_col: str = "swat_name"


class SoilConfig(BaseModel):
    raster: Path
    table: Path  # CSV or SQLite with physical soil parameters
    soil_key_col: str = "soil_id"
    output_usersoil: bool = True


class WeatherUnitsConfig(BaseModel):
    precip: str = "mm"
    temperature: str = "degC"


class WeatherConfig(BaseModel):
    stations: Path  # CSV: id, name, lat, lon, elev
    data_dir: Path  # directory containing one CSV per station named {id}.csv
    format: Literal["csv"] = "csv"
    variables: list[
        Literal["precip", "tmax", "tmin", "wind", "solar", "humidity"]
    ] = Field(default=["precip", "tmax", "tmin"])
    start: date  # ISO date "YYYY-MM-DD"
    end: date  # ISO date "YYYY-MM-DD"
    units: WeatherUnitsConfig = Field(default_factory=WeatherUnitsConfig)
    missing_policy: Literal["fail", "warn"] = "fail"

    @model_validator(mode="after")
    def validate_date_range(self) -> "WeatherConfig":
        if self.end < self.start:
            raise ValueError("weather.end must be on or after weather.start")
        return self


class StreamflowConfig(BaseModel):
    path: Path
    date_col: str = "date"
    station_id_col: str = "station_id"
    value_col: str = "flow"
    units: Literal["m3s", "mm"] = "m3s"


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


class SWATPrepConfig(BaseModel):
    project: ProjectConfig
    dem: Optional[DEMConfig] = None
    landuse: Optional[LandUseConfig] = None
    soil: Optional[SoilConfig] = None
    weather: Optional[WeatherConfig] = None
    streamflow: Optional[StreamflowConfig] = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SWATPrepConfig":
        """Load and validate config from a YAML file."""
        config_path = Path(path)
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        cfg = cls.model_validate(data)
        cfg._resolve_relative_paths(config_path.parent)
        return cfg

    def configured_domains(self) -> list[str]:
        """Return which optional domains are configured."""
        domains = []
        for name in ("dem", "landuse", "soil", "weather", "streamflow"):
            if getattr(self, name) is not None:
                domains.append(name)
        return domains

    def _resolve_relative_paths(self, base_dir: Path) -> None:
        """Resolve YAML path fields relative to the config file location."""
        path_fields = [
            ("project", "boundary"),
            ("project", "output_dir"),
            ("dem", "path"),
            ("landuse", "raster"),
            ("landuse", "lookup"),
            ("soil", "raster"),
            ("soil", "table"),
            ("weather", "stations"),
            ("weather", "data_dir"),
            ("streamflow", "path"),
        ]
        for section_name, field_name in path_fields:
            section = getattr(self, section_name)
            if section is None:
                continue
            value = getattr(section, field_name)
            if value is not None and not value.is_absolute():
                setattr(section, field_name, base_dir / value)
