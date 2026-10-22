"""Pydantic v2 config schema for swatprep.

Load from YAML:
    cfg = SWATPrepConfig.from_yaml("config.yaml")

Paths in YAML are resolved relative to the config file's directory,
so the same config works regardless of the working directory at run time.
Existence checks happen in preprocessing, not here, so validate can
report all missing files at once.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator


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
    lookup: Path  # CSV columns: source_code_col, swat_code_col, swat_name_col
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


class WeatherSourceConfig(BaseModel):
    """Per-variable-group station source (optional override)."""
    stations: Path  # CSV: id, name, lat, lon, elev
    data_dir: Path  # directory; one CSV per station
    file_pattern: str = "{id}.csv"  # e.g. "{name}.csv" to match by station name

class FillCSVConfig(BaseModel):
    stations: Path
    data_dir: Path
    file_pattern: str = "{id}.csv"

class FillNetCDFConfig(BaseModel):
    path: Path
    var_map: dict[str, str]
    lat_name: str = "auto"
    lon_name: str = "auto"
    time_name: str = "auto"

    @model_validator(mode="after")
    def validate_var_map(self) -> "FillNetCDFConfig":
        valid = {"precip", "tmax", "tmin", "wind", "solar", "humidity"}
        bad = set(self.var_map) - valid
        if not self.var_map or bad:
            raise ValueError(
                "weather.fill.netcdf.var_map must be non-empty with keys from "
                f"{sorted(valid)}; invalid: {sorted(bad)}"
                )
        return self

class WeatherFillConfig(BaseModel):
    type: Literal["csv", "netcdf"] = "csv"
    output_dir: Optional[Path] = None
    min_overlap_days: int = Field(default=10, ge=0)
    csv: Optional[FillCSVConfig] = None
    netcdf: Optional[FillNetCDFConfig] = None

    @model_validator(mode="after")
    def validate_block_matches_type(self) -> "WeatherFillConfig":
        if getattr(self, self.type) is None:
            raise ValueError(
                f"weather.fill.type is '{self.type}' but the "
                f"weather.fill.{self.type} block is missing"
            )
        return self


class WeatherConfig(BaseModel):
    stations: Optional[Path] = None   # CSV: id, name, lat, lon, elev (default for all)
    data_dir: Optional[Path] = None   # directory; one CSV per station (default for all)
    precip: Optional[WeatherSourceConfig] = None      # override for precip
    temp: Optional[WeatherSourceConfig] = None         # override for tmax/tmin
    file_pattern: str = "{id}.csv"  # e.g. "{name}.csv" to match by station name
    format: Literal["csv"] = "csv"
    variables: list[
        Literal["precip", "tmax", "tmin", "wind", "solar", "humidity"]
    ] = Field(default=["precip", "tmax", "tmin"])
    start: date  # ISO "YYYY-MM-DD"
    end: date    # ISO "YYYY-MM-DD"
    units: WeatherUnitsConfig = Field(default_factory=WeatherUnitsConfig)
    missing_policy: Literal["fail", "warn"] = "fail"
    fill: Optional[WeatherFillConfig] = None  # chỉ dùng cho `swatprep fill weather`

    @model_validator(mode="after")
    def validate_date_range(self) -> "WeatherConfig":
        if self.end < self.start:
            raise ValueError("weather.end must be on or after weather.start")
        return self

    @model_validator(mode="after")
    def validate_sources(self) -> "WeatherConfig":
        """Ensure at least one source is configured for each variable group."""
        has_default = self.stations is not None and self.data_dir is not None
        precip_vars = {"precip"} & set(self.variables)
        temp_vars = {"tmax", "tmin"} & set(self.variables)

        if precip_vars and not has_default and self.precip is None:
            raise ValueError(
                "Precip variables configured but no source: "
                "set weather.stations/data_dir or weather.precip.stations/data_dir"
            )
        if temp_vars and not has_default and self.temp is None:
            raise ValueError(
                "Temperature variables configured but no source: "
                "set weather.stations/data_dir or weather.temp.stations/data_dir"
            )
        return self

    def precip_source(self) -> tuple[Path, Path]:
        """Return (stations_path, data_dir) for precipitation."""
        if self.precip is not None:
            return self.precip.stations, self.precip.data_dir
        return self.stations, self.data_dir  # type: ignore[return-value]

    def temp_source(self) -> tuple[Path, Path]:
        """Return (stations_path, data_dir) for temperature."""
        if self.temp is not None:
            return self.temp.stations, self.temp.data_dir
        return self.stations, self.data_dir  # type: ignore[return-value]


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
        """Load and validate config from a YAML file.

        All relative paths are resolved against the config file's directory.
        """
        config_path = Path(path).resolve()
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        cfg = cls.model_validate(data)
        cfg._resolve_relative_paths(config_path.parent)
        return cfg

    def configured_domains(self) -> list[str]:
        """Return the list of optional domains that are configured."""
        return [
            name
            for name in ("dem", "landuse", "soil", "weather", "streamflow")
            if getattr(self, name) is not None
        ]

    def _resolve_relative_paths(self, base_dir: Path) -> None:
        """Resolve relative path fields to be absolute, anchored at base_dir."""
        _PATH_FIELDS = [
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
        for section_name, field_name in _PATH_FIELDS:
            section = getattr(self, section_name)
            if section is None:
                continue
            value: Optional[Path] = getattr(section, field_name)
            if value is not None and not value.is_absolute():
                setattr(section, field_name, base_dir / value)

        # Resolve sub-source paths for weather.precip / weather.temp
        if self.weather is not None:
            for sub_name in ("precip", "temp"):
                sub = getattr(self.weather, sub_name)
                if sub is None:
                    continue
                for field_name in ("stations", "data_dir"):
                    value = getattr(sub, field_name)
                    if value is not None and not value.is_absolute():
                        setattr(sub, field_name, base_dir / value)

        fill = self.weather.fill if self.weather is not None else None
        if fill is not None:
            targets = [(fill, "output_dir")]
            if fill.csv is not None:
                targets += [(fill.csv, "stations"), (fill.csv, "data_dir")]
            if fill.netcdf is not None:
                targets += [(fill.netcdf, "path")]
            for obj, field_name in targets:
                value = getattr(obj, field_name)
                if value is not None and not value.is_absolute():
                    setattr(obj, field_name, base_dir / value)