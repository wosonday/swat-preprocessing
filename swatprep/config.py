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
    name: str = Field(
        description="Project name, written to manifest.json and the QA report. Example: `MaDa_Basin_2026`.",
    )
    crs: str = Field(
        description=(
            "Target projected CRS for all spatial outputs (metres). Clipped rasters are reprojected to it. "
            "Example: `EPSG:32648` (WGS 84 / UTM 48N) or `EPSG:3405` (VN-2000 / UTM 48N)."
        ),
    )
    boundary: Optional[Path] = Field(
        default=None,
        description=(
            "Basin outline (.shp, .gpkg, .geojson) with a CRS. When set, DEM, land use and soil are clipped "
            "to it; it may be in another CRS than the rasters."
        ),
    )
    output_dir: Path = Field(
        default=Path("./output"),
        description=(
            "Folder that receives every output (spatial/, landuse/, soil/, weather/, observed/, "
            "manifest.json). Relative paths are relative to the config file. Default `./output`."
        ),
    )
    targets: list[Literal["swatplus", "swat"]] = Field(
        default=["swatplus"],
        description=(
            "Model formats to write weather for: `swatplus` (SWAT+ .pcp/.tmp with .cli indexes) and/or `swat` "
            "(SWAT 2012 text files). With both, each gets its own sub-folder."
        ),
    )
    overviews: bool = Field(
        default=True,
        description=(
            "Add overviews (image pyramids) to the clipped rasters so the web app's map opens them quickly. "
            "Pixel values are unchanged; files grow by about a third (less for land use and soil)."
        ),
    )


class DEMConfig(BaseModel):
    path: Path = Field(
        description="Source DEM raster (GeoTIFF or ESRI grid). It may cover a much larger area than the basin.",
    )
    output_name: str = Field(
        default="dem_projected.tif",
        description=(
            "File name of the clipped DEM, written to `output/spatial/`. Default `dem_projected.tif`. "
            "Example: `dem_clip.tif`."
        ),
    )
    clip: bool = Field(
        default=True,
        description=(
            "Crop the DEM to project.boundary (needs a boundary). Off: keep the whole raster, only reproject "
            "it."
        ),
    )
    resampling: Literal["nearest", "bilinear", "cubic"] = Field(
        default="bilinear",
        description=(
            "How cell values are recomputed when the DEM is reprojected or resampled: `bilinear` (default, "
            "smooth) or `cubic`; `nearest` keeps the original values."
        ),
    )
    resolution: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Output pixel size in project.crs units (metres). Empty = keep the source resolution. Example: "
            "`30`."
        ),
    )


class ClipItemConfig(BaseModel):
    """One raster to crop to project.boundary: read `src`, write `dst`."""
    src: Path = Field(
        description="Raster to crop to project.boundary (any raster not covered by DEM, land use or soil).",
    )
    dst: Path = Field(
        description=(
            "Where the cropped raster is written. Relative paths are relative to the config file. Example: "
            "`./output/extra/ndvi_clip.tif`."
        ),
    )
    mask: bool = Field(
        default=False,
        description=(
            "Also set the pixels outside the boundary polygons to NoData. Off: crop to the boundary's "
            "bounding box only."
        ),
    )
    resampling: Literal["nearest", "bilinear", "cubic"] = Field(
        default="nearest",
        description=(
            "How cell values are recomputed when reprojected: `nearest` (default, keeps classes), `bilinear` "
            "or `cubic` for continuous values."
        ),
    )
    resolution: Optional[float] = Field(
        default=None,
        gt=0,
        description="Output pixel size in project.crs units. Empty = keep the source resolution.",
    )


class LandUseConfig(BaseModel):
    raster: Path = Field(
        description="Land-use raster with integer class codes (for example ESA WorldCover).",
    )
    lookup: Path = Field(
        description="CSV that maps each raster code to a SWAT land-use code; its column names are set below.",
    )
    source_code_col: str = Field(
        default="code",
        description="Column of the lookup CSV with the raster codes. Default `code`. Example: `LANDUSE_ID`.",
    )
    swat_code_col: str = Field(
        default="swat_code",
        description="Column of the lookup CSV with the 4-letter SWAT codes (AGRL, FRST, …). Default `swat_code`.",
    )
    swat_name_col: str = Field(
        default="swat_name",
        description=(
            "Column of the lookup CSV with the class names shown in reports and on the map. Default "
            "`swat_name`; the code column may be reused."
        ),
    )
    output_name: str = Field(
        default="landuse_clip.tif",
        description=(
            "File name of the clipped land-use raster, written to `output/landuse/`. Default "
            "`landuse_clip.tif`."
        ),
    )
    clip: bool = Field(
        default=True,
        description="Crop to project.boundary and keep only the classes found in the basin.",
    )
    output_lookup: bool = Field(
        default=True,
        description="Write `landuse/landuse_vlookup.csv` (LANDUSE_ID, SWAT_CODE) for QSWAT / QSWAT+.",
    )
    resolution: Optional[float] = Field(
        default=None,
        gt=0,
        description="Output pixel size in project.crs units. Empty = keep the source resolution.",
    )


class SoilConfig(BaseModel):
    raster: Path = Field(
        description="Soil raster with integer soil ids (for example HWSD `hdr.adf`).",
    )
    table: Path = Field(
        description="CSV or SQLite with the physical parameters of each soil.",
    )
    soil_key_col: str = Field(
        default="soil_id",
        description="Column of the soil table that matches the raster values. Default `soil_id`. Example: `SOIL_ID`.",
    )
    output_usersoil: bool = Field(
        default=True,
        description="Write `soil/usersoil.csv` for the soils present in the basin.",
    )
    # "swat": usersoil.csv in the 152-column SWAT+ layout (SWAT+ Editor example); "raw": input table as is
    usersoil_format: Literal["swat", "raw"] = Field(
        default="swat",
        description="`swat`: the 152-column SWAT+ usersoil layout; `raw`: the input table as is.",
    )
    output_name: str = Field(
        default="soil_clip.tif",
        description="File name of the clipped soil raster, written to `output/soil/`. Default `soil_clip.tif`.",
    )
    clip: bool = Field(
        default=True,
        description="Crop to project.boundary and keep only the soils found in the basin.",
    )
    output_lookup: bool = Field(
        default=True,
        description=(
            "Write `soil/soil_vlookup.csv` (key column SOIL_ID for SWAT+, SEQN for SWAT 2012, and SNAM) for "
            "QSWAT / QSWAT+."
        ),
    )
    resolution: Optional[float] = Field(
        default=None,
        gt=0,
        description="Output pixel size in project.crs units. Empty = keep the source resolution.",
    )


class WeatherUnitsConfig(BaseModel):
    precip: str = Field(
        default="mm",
        description="Unit of the precipitation values in the station files. Default `mm`.",
    )
    temperature: str = Field(
        default="degC",
        description="Unit of the temperature values in the station files. Default `degC`.",
    )


class WeatherSourceConfig(BaseModel):
    """Per-variable-group station source (optional override)."""
    stations: Path = Field(
        description=(
            "Station table of this source: columns id, name, lat, lon, elev in any case "
            "(ID,NAME,LAT,LONG,ELEV also works)."
        ),
    )
    data_dir: Path = Field(
        description="Folder with one CSV per station (columns date and the variables).",
    )
    file_pattern: str = Field(
        default="{id}.csv",
        description="Name of each station file: `{id}.csv` (default) or `{name}.csv` to match by station name.",
    )

class FillCSVConfig(BaseModel):
    stations: Path = Field(
        description="Station table of the fill source (same columns as the observed stations).",
    )
    data_dir: Path = Field(
        description="Folder with one CSV per station of the fill source.",
    )
    file_pattern: str = Field(
        default="{id}.csv",
        description="Name of each fill-source file: `{id}.csv` (default) or `{name}.csv`.",
    )

class FillNetCDFConfig(BaseModel):
    path: Path = Field(
        description="Daily gridded NetCDF file. Example: `OBS.Vietnam.1980-2014.nc`.",
    )
    var_map: dict[str, str] = Field(
        description=(
            "Which variable of the NetCDF holds each swatprep variable. Example: precip → `pr`, tmax → "
            "`tasmax`, tmin → `tasmin`. List the names with `xarray.open_dataset(path)`."
        ),
    )
    lat_name: str = Field(
        default="auto",
        description="Name of the latitude axis in the NetCDF; `auto` finds lat / latitude / y.",
    )
    lon_name: str = Field(
        default="auto",
        description="Name of the longitude axis in the NetCDF; `auto` finds lon / longitude / x.",
    )
    time_name: str = Field(
        default="auto",
        description="Name of the time axis in the NetCDF; `auto` finds it.",
    )
    search_radius: int = Field(
        default=1,
        ge=0,
        le=5,
        description="If the nearest cell has no data, look this many cells around it (0–5). Default `1`.",
    )

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
    type: Literal["csv", "netcdf"] = Field(
        default="csv",
        description=(
            "Source used to fill the gaps: `csv` (other stations' files) or `netcdf` (a daily grid; the "
            "nearest cell with data is used)."
        ),
    )
    output_dir: Optional[Path] = Field(
        default=None,
        description=(
            "Folder for the filled station files, stations.csv and fill_report.csv. Must differ from Data "
            "folder. Example: `./filled`."
        ),
    )
    min_overlap_days: int = Field(
        default=10,
        ge=0,
        description=(
            "Days on which both the station and the fill source have values. Fewer than this: the gap is "
            "still filled but flagged low confidence. Default `10`."
        ),
    )
    run_in_build: bool = Field(
        default=False,
        description=(
            "Build fills the gaps first (into Output folder of Fill) and then builds the weather files from "
            "the filled data."
        ),
    )
    fill_ungauged: bool = Field(
        default=False,
        description=(
            "Also fill stations with no observed day at all (or no data file): every day comes from the fill "
            "source. Use it for virtual stations placed where there is no gauge."
        ),
    )
    correct_ungauged: bool = Field(
        default=True,
        description=(
            "For those stations, apply the bias correction of the nearest gauged station (same variable) "
            "within Max borrow distance; off, or no such station: raw fill-source values."
        ),
    )
    max_borrow_km: float = Field(
        default=50,
        gt=0,
        description=(
            "Largest distance (km) to the gauged station whose correction is borrowed. Default `50`."
        ),
    )
    csv: Optional[FillCSVConfig] = Field(
        default=None,
        description="Station files used as the fill source.",
    )
    netcdf: Optional[FillNetCDFConfig] = Field(
        default=None,
        description="Daily gridded NetCDF used as the fill source (precipitation in mm, temperature in degC).",
    )

    @model_validator(mode="after")
    def validate_block_matches_type(self) -> "WeatherFillConfig":
        if getattr(self, self.type) is None:
            raise ValueError(
                f"weather.fill.type is '{self.type}' but the "
                f"weather.fill.{self.type} block is missing"
            )
        return self


class WeatherConfig(BaseModel):
    stations: Optional[Path] = Field(
        default=None,
        description=(
            "Station table: columns id, name, lat, lon, elev in any case (ID,NAME,LAT,LONG,ELEV also works); "
            "a .txt is fine if it is CSV. Used for all variables unless a separate source is set."
        ),
    )
    data_dir: Optional[Path] = Field(
        default=None,
        description=(
            "Folder with one CSV per station: a `date` column and one column per variable (precip, tmax, "
            "tmin, …)."
        ),
    )
    precip: Optional[WeatherSourceConfig] = Field(
        default=None,
        description="A separate station network for precipitation (its own stations file and folder).",
    )
    temp: Optional[WeatherSourceConfig] = Field(
        default=None,
        description="A separate station network for tmax / tmin.",
    )
    file_pattern: str = Field(
        default="{id}.csv",
        description="Name of each station file: `{id}.csv` (default) or `{name}.csv` to match by station name.",
    )
    format: Literal["csv"] = Field(
        default="csv",
        description="Format of the station files. Only `csv` for now.",
    )
    variables: list[ Literal["precip", "tmax", "tmin", "wind", "solar", "humidity"] ] = Field(
        default=["precip", "tmax", "tmin"],
        description="Variables to read and write. Default precip, tmax, tmin; wind, solar and humidity are optional.",
    )
    start: date = Field(
        description="First day of the period (YYYY-MM-DD). Days without data in the period count as missing.",
    )
    end: date = Field(
        description="Last day of the period (YYYY-MM-DD); on or after Start.",
    )
    units: WeatherUnitsConfig = Field(
        default_factory=WeatherUnitsConfig,
        description="Units of the values in the station files.",
    )
    missing_policy: Literal["fail", "warn"] = Field(
        default="fail",
        description=(
            "What Build does when a station has missing days: `fail` stops with an error, `warn` writes the "
            "files with -99 for the missing days. Fill the gaps first with Fill missing values."
        ),
    )
    fill: Optional[WeatherFillConfig] = Field(
        default=None,
        description=(
            "Fill missing days from another source (station CSVs or a gridded NetCDF), bias-corrected per "
            "station."
        ),
    )

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
    path: Path = Field(
        description=(
            "Observed discharge: one long CSV (format long), or one station file / a folder of station files "
            "(format per_station)."
        ),
    )
    # long: one file, a row per day and station. per_station: each file is one station
    # (columns date + one flow column); the station id is the file name without extension.
    format: Literal["long", "per_station"] = Field(
        default="long",
        description=(
            "`long`: one file with a row per day and station; `per_station`: each file is one station (date + "
            "discharge), its id is the file name."
        ),
    )
    glob: str = Field(
        default="Q_*.csv",
        description="per_station with a folder: which files to read. Default `Q_*.csv`.",
    )
    stations: Optional[list[str]] = Field(
        default=None,
        description="Keep only these station ids (comma-separated). Empty = all stations found.",
    )
    date_col: str = Field(
        default="date",
        description="Date column. Default `date`.",
    )
    station_id_col: str = Field(
        default="station_id",
        description="Station id column (format long). Default `station_id`.",
    )
    value_col: str = Field(
        default="flow",
        description=(
            "Discharge column. Default `flow`; per_station files with a single value column are read "
            "automatically."
        ),
    )
    units: Literal["m3s", "mm"] = Field(
        default="m3s",
        description="Unit of the discharge values: `m3s` (m³/s) or `mm` (runoff depth).",
    )


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


class SWATPrepConfig(BaseModel):
    project: ProjectConfig = Field(
        description="Project settings: name, CRS, boundary and output folder.",
    )
    clip: Optional[list[ClipItemConfig]] = Field(
        default=None,
        min_length=1,
        description="Extra rasters to crop to the boundary.",
    )
    dem: Optional[DEMConfig] = Field(
        default=None,
        description="Digital elevation model.",
    )
    landuse: Optional[LandUseConfig] = Field(
        default=None,
        description="Land-use raster and its lookup to SWAT codes.",
    )
    soil: Optional[SoilConfig] = Field(
        default=None,
        description="Soil raster and soil parameter table.",
    )
    weather: Optional[WeatherConfig] = Field(
        default=None,
        description="Daily weather station data and gap filling.",
    )
    streamflow: Optional[StreamflowConfig] = Field(
        default=None,
        description="Observed discharge for calibration.",
    )

    @model_validator(mode="after")
    def clip_needs_boundary(self) -> "SWATPrepConfig":
        if self.clip and self.project.boundary is None:
            raise ValueError("'clip' needs project.boundary to be set")
        return self

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
            for name in ("clip", "dem", "landuse", "soil", "weather", "streamflow")
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

        for item in self.clip or []:
            for field_name in ("src", "dst"):
                value = getattr(item, field_name)
                if not value.is_absolute():
                    setattr(item, field_name, base_dir / value)

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
