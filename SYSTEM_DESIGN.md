# swatprep - System Design Document

**Version:** 0.2 (reviewed design)  
**Date:** 2026-06-18  
**Scope:** Small Python library + CLI that prepares raw DEM, land-use, soil, weather, and streamflow data for SWAT Classic / SWAT+ workflows without replacing QSWAT+ or SWAT+ Editor.

---

## 1. Design Decision

This project should be a **preprocessor + format writer**, not a full watershed/HRU generator.

SWAT/SWAT+ setup has two different jobs:

1. Prepare reliable input datasets: projection, clipping, reclassification, schema validation, unit conversion, temporal coverage checks, and SWAT-compatible weather/soil/lookup files.
2. Build the model structure: watershed delineation, stream network, subbasins, LSUs/HRUs, routing objects, and SWAT+ project database.

For a small tool, job 1 is the right scope. Job 2 is already handled by QSWAT+, QSWAT, SWAT+ Editor, TauDEM, WhiteboxTools, and related GIS workflows. Reimplementing that logic would create high scientific and maintenance risk.

The library will therefore produce a **SWAT-ready input package** that can be used by QSWAT+/SWAT+ Editor or by a downstream scripted workflow.

---

## 2. Goals and Non-Goals

### 2.1 Goals

| # | Goal |
|---|------|
| G1 | Validate and normalize raw DEM, land-use, soil, weather, and streamflow inputs |
| G2 | Reproject and clip geospatial inputs to a project boundary or basin mask |
| G3 | Reclassify land-use rasters to SWAT land-use codes using a user lookup table |
| G4 | Convert soil source tables into SWAT-compatible `usersoil`-style tables where source data are sufficient |
| G5 | Convert station weather time series into SWAT/SWAT+ daily text files and weather generator statistics |
| G6 | Convert observed streamflow into calibration/validation-ready daily observation files |
| G7 | Provide both Python API and CLI |
| G8 | Make runs reproducible from one YAML config file |
| G9 | Produce a machine-readable QA manifest describing files, assumptions, warnings, and validation results |

### 2.2 Non-Goals for MVP

| # | Non-goal | Reason |
|---|----------|--------|
| NG1 | Full watershed delineation from DEM | QSWAT+/TauDEM/WhiteboxTools already solve this; DEM hydrologic conditioning is easy to get wrong |
| NG2 | HRU/LSU generation | SWAT+ HRU logic depends on editor/project database conventions and threshold choices |
| NG3 | Writing a complete SWAT+ `project.sqlite` | Version-specific schema changes make this fragile for a small library |
| NG4 | Model calibration, sensitivity, or uncertainty analysis | Belongs to SWAT+ Toolbox, PEST, or separate calibration workflows |
| NG5 | Automatic public data download | Useful later, but not needed for the first reliable library |
| NG6 | GUI that replaces QSWAT+ / SWAT+ Editor | QSWAT+ and SWAT+ Editor already provide the visual workflow. *Revised 2026-10:* a thin Streamlit web app (`app/`) now edits and runs this tool's YAML only; see `docs/superpowers/specs/2026-10-27-phase2-project-page-design.md` |

---

## 3. Target Outputs

The output is an importable folder, not a complete runnable model.

```
output/
  manifest.json
  qa_report.md
  spatial/
    dem_info.json
  landuse/
    landuse_lookup.csv
    landuse_raster_codes.csv
  soil/
    usersoil.csv
    soil_raster_codes.csv
  weather/                 # format follows project.targets (default: swatplus)
    stations.csv
    StationA.pcp           # SWAT+ daily files (year/doy rows)
    StationA.tmp
    pcp.cli tmp.cli        # SWAT+ index files
    wgn.csv
  observed/
    streamflow_ST001.csv
    streamflow_meta.csv
```

Exact file names may be refined during implementation, but the contract is stable: each writer produces files plus manifest entries that say what was written and how it was validated.

---

## 4. Functional Requirements

| # | Requirement |
|---|-------------|
| F1 | Read project configuration from YAML and validate paths, CRS, required columns, date ranges, and target formats |
| F2 | Accept a project boundary as GeoPackage/Shapefile/GeoJSON; use it as the spatial processing mask |
| F3 | Accept DEM as GeoTIFF; validate CRS/nodata/resolution; reproject and clip to the boundary |
| F4 | Accept land-use raster as GeoTIFF; reproject, clip, reclassify to SWAT codes, and report unmapped classes |
| F5 | Accept soil raster plus source soil table as CSV/SQLite; reproject, clip, validate required soil parameters, and write `usersoil.csv` |
| F6 | Accept weather CSV files; validate station metadata, daily continuity, units, and required variables |
| F7 | Write SWAT-compatible precipitation and temperature station files for supported variables |
| F8 | Compute weather generator monthly statistics from available daily station data |
| F9 | Accept observed streamflow CSV; normalize dates/units and write calibration-ready daily observation files |
| F10 | Produce `manifest.json` and `qa_report.md` for reproducibility and review |
| F11 | Provide `swatprep validate`, `swatprep build`, and `swatprep inspect` CLI commands |

---

## 5. Architecture

### 5.1 Component Diagram

```
Raw Vietnamese .day files
    |
    v
converters/                          ← optional pre-processing layer
    DayFilesConverter                    merge .day → per-station CSV
    StationWeatherConverter              read raw pcp/tmp master+data (SWAT
                                          Classic style or CSV) → WeatherResult,
                                          written by WeatherWriter (SWAT2012) /
                                          SWATPlusWeatherWriter (SWAT+)
    StreamflowConverter              reshape streamflow CSVs
    |
    v (per-station CSV / WeatherResult / validated inputs)

config.yaml
    |
    v
ProjectConfig
    |
    v
SWATPrepProject
    |
    +-- SpatialPreprocessor
    |     +-- DEMPreprocessor
    |     +-- LandUsePreprocessor
    |     +-- SoilPreprocessor
    |
    +-- TimeSeriesPreprocessor
    |     +-- WeatherPreprocessor
    |     +-- StreamflowPreprocessor
    |
    +-- QACollector
    |
    +-- Writers
          +-- SpatialPackageWriter
          +-- SWATPlusWeatherWriter   (targets: swatplus, default)
          +-- WeatherWriter           (targets: swat, SWAT Classic)
          +-- SoilWriter
          +-- ObservationWriter
          +-- ManifestWriter
```

Weather output format is selected by `project.targets`; see
[`docs/WEATHER_OUTPUT.md`](docs/WEATHER_OUTPUT.md).

The `converters/` layer runs independently of `build()`. It is a one-time
pre-processing step that converts raw Vietnamese station data into formats that
the pipeline's preprocessors can consume. Each converter returns a
`SWAT2012ConvertResult` (or similar) with `qa: list[QACheck]`.

### 5.2 Data Flow

```
Raw inputs
  |
  v
Config validation
  |
  v
Per-input preprocessing
  |
  +-- spatial: CRS, nodata, clip, reclass, lookup coverage
  +-- weather: date range, units, missing values, station metadata
  +-- streamflow: date range, units, station/reach mapping
  |
  v
QA checks
  |
  v
Format writers
  |
  v
SWAT-ready input package
```

All processors return typed result objects. Writers do not repeat processing; they only serialize validated results.

---

## 6. Python API

### 6.1 High-Level API

```python
from swatprep import SWATPrepProject

project = SWATPrepProject.from_config("config.yaml")
result = project.build()

print(result.output_dir)
print(result.manifest_path)
print(result.warning_count)
```

### 6.2 Partial API

```python
from swatprep.core.weather import WeatherPreprocessor
from swatprep.writers.weather import WeatherWriter

weather = WeatherPreprocessor.from_config(config.weather).process()
WeatherWriter(config.output.weather_dir).write(weather)
```

Partial APIs are included so users can test one data type without running the full pipeline.

---

## 7. CLI

```bash
# Validate config and source files without writing processed outputs
swatprep validate config.yaml

# Prepare all configured inputs
swatprep build config.yaml

# Prepare one domain for debugging
swatprep build config.yaml --only weather
swatprep build config.yaml --only landuse

# Inspect one input file
swatprep inspect raster data/dem.tif
swatprep inspect weather data/weather/ST001.csv
```

The CLI exits non-zero when validation fails. Warnings are allowed only when the config explicitly permits them, such as known weather gaps.

---

## 8. Config Schema

```yaml
project:
  name: "MaDa_Basin_2024"
  crs: "EPSG:32648"
  boundary: "./data/boundary.gpkg"
  output_dir: "./output"
  targets: ["swatplus", "swat"]

dem:
  path: "./data/dem_30m.tif"
  output_name: "dem_projected.tif"

landuse:
  raster: "./data/landuse_2020.tif"
  lookup: "./data/landuse_lookup.csv"
  source_code_col: "code"
  swat_code_col: "swat_code"
  swat_name_col: "swat_name"

soil:
  raster: "./data/soil_map.tif"
  table: "./data/soil_properties.csv"
  soil_key_col: "soil_id"
  output_usersoil: true

weather:
  stations: "./data/weather_stations.csv"
  data_dir: "./data/weather"
  format: "csv"
  variables: ["precip", "tmax", "tmin"]
  start: "2000-01-01"
  end: "2020-12-31"
  units:
    precip: "mm"
    temperature: "degC"
  missing_policy: "fail"

streamflow:
  path: "./data/streamflow.csv"
  date_col: "date"
  station_id_col: "station_id"
  value_col: "flow"
  units: "m3s"
```

---

## 9. Data Contracts

### 9.1 Processor Results

```python
@dataclass
class DEMResult:
    raster_path: Path
    crs: str
    bounds: tuple[float, float, float, float]
    resolution: tuple[float, float]
    nodata: float | int | None
    qa: list[QACheck]

@dataclass
class LandUseResult:
    raster_path: Path
    lookup: pd.DataFrame
    class_area: pd.DataFrame
    unmapped_codes: list[int]
    qa: list[QACheck]

@dataclass
class SoilResult:
    raster_path: Path
    usersoil: pd.DataFrame
    missing_required_params: pd.DataFrame
    qa: list[QACheck]

@dataclass
class WeatherResult:
    stations: pd.DataFrame
    daily: dict[str, pd.DataFrame]
    wgn_stats: pd.DataFrame
    qa: list[QACheck]

@dataclass
class StreamflowResult:
    daily: pd.DataFrame
    units: str
    missing_summary: pd.DataFrame
    qa: list[QACheck]
```

### 9.2 QA Check

```python
@dataclass
class QACheck:
    name: str
    status: Literal["pass", "warn", "fail"]
    message: str
    context: dict[str, Any]
```

The QA model is intentionally small. It gives enough structure for tests, CLI reporting, and `manifest.json` without building a large reporting framework.

---

## 10. Package Structure

```
swat-preprocessing/
  swatprep/
    __init__.py
    api.py
    cli.py
    config.py
    errors.py
    qa.py
    core/
      __init__.py
      dem.py
      landuse.py
      soil.py
      weather.py
      streamflow.py
    converters/                      ← pre-processing layer (independent of build())
      __init__.py
      climate.py                     ← DayFilesConverter (merge .day files → CSV)
      station_weather.py             ← StationWeatherConverter (raw pcp/tmp master+data → WeatherResult)
      streamflow.py                  ← StreamflowConverter
    writers/
      __init__.py
      manifest.py
      spatial.py
      soil.py
      weather.py                     ← WeatherWriter (SWAT2012)
      weather_plus.py                ← SWATPlusWeatherWriter (SWAT+)
      observations.py
    utils/
      __init__.py
      raster.py
      tables.py
      units.py
  tests/
    conftest.py
    test_config.py
    test_dem.py
    test_landuse.py
    test_soil.py
    test_weather.py
    test_streamflow.py
    test_converters.py
    test_pcp_converter.py
    test_weather_plus.py
    test_writers.py
  examples/
    config_minimal.yaml
  SYSTEM_DESIGN.md
  DEVELOPER_GUIDE.md
  TESTING_GUIDE.md
  pyproject.toml
```

No `swatplus/schema.py` or complete SQLite writer is included in MVP. That can be added later only after a specific SWAT+ version and import contract are verified.

---

## 11. Dependency Strategy

### Core Dependencies

| Library | Purpose |
|---------|---------|
| `pydantic>=2` | Config validation |
| `click` | CLI |
| `pandas` | Tabular processing |
| `numpy` | Numeric processing |
| `pyyaml` | YAML config loading |

### Geospatial Extra

| Library | Purpose |
|---------|---------|
| `rasterio` | Raster read/write, reprojection, clipping |
| `geopandas` | Boundary/vector I/O |
| `shapely` | Geometry operations |

### Optional Later

| Library | Purpose |
|---------|---------|
| `xarray` | NetCDF weather support |
| `netcdf4` | NetCDF backend |
| `sqlalchemy` | Future SWAT+ SQLite support |

Keep heavy geospatial dependencies behind an install extra, and the web app behind another:

```bash
pip install swatprep[geo]        # rasterio, geopandas, shapely
pip install swatprep[geo,app]    # + streamlit, ruamel.yaml (web app, `swatprep-ui`)
```

---

## 12. Error Handling

```python
class SWATPrepError(Exception): ...
class ConfigError(SWATPrepError): ...
class InputValidationError(SWATPrepError): ...
class ProjectionError(SWATPrepError): ...
class ProcessingError(SWATPrepError): ...
class WriterError(SWATPrepError): ...
```

Rules:

- Invalid config or missing required files: fail.
- Missing required table columns: fail.
- Unmapped land-use or soil codes: fail by default, warn only if explicitly allowed.
- Weather gaps: fail by default, warn only if `missing_policy: warn`.
- Unit assumptions must be explicit in config; no silent unit guessing.

---

## 13. Testing Strategy

Use small synthetic fixtures. Avoid real basin datasets in unit tests.

| Area | Required Checks |
|------|-----------------|
| Config | Valid config loads; missing required fields fail with clear messages |
| DEM | Output CRS matches project CRS; clipped raster bounds fit boundary |
| Land-use | All source codes map to SWAT codes; class area report sums to processed raster area |
| Soil | Required `usersoil` columns exist; missing physical parameters are reported |
| Weather | Date range is continuous; station IDs match metadata; WGN has 12 rows per station |
| Streamflow | Dates parse as daily series; units are preserved or converted explicitly |
| Writers | Expected files exist; manifest lists every output; QA failures block writing |
| End-to-end | `swatprep build examples/config_minimal.yaml` exits 0 with synthetic data |

Hydrologic model performance metrics such as NSE, KGE, and PBIAS are not part of preprocessing tests. They belong to later calibration/validation workflows after SWAT/SWAT+ simulation.

---

## 14. MVP Milestones

### Milestone 1 - Skeleton and Config

- Package structure
- Pydantic config
- CLI commands: `validate`, `prepare`
- Manifest and QA primitives
- Unit tests for config and QA

### Milestone 2 - Weather and Streamflow

- Weather CSV parser
- Station metadata validation
- Daily SWAT text writers for precipitation and temperature
- WGN monthly statistics
- Streamflow observation normalization

### Milestone 3 - Land-use and Soil

- Raster clip/reproject helper
- Land-use reclassification
- Soil raster/table validation
- `usersoil.csv` writer

### Milestone 4 - DEM and Full Package

- DEM validation, clip, reproject
- Spatial package writer
- Complete `manifest.json` and `qa_report.md`
- End-to-end synthetic example

---

## 15. Risks and Controls

| Risk | Control |
|------|---------|
| Users expect the tool to build a complete SWAT+ model | State clearly that MVP creates an import package, not a finished model |
| Soil databases differ by country/source | Start with CSV source table contract; add SSURGO/HWSD adapters later |
| SWAT/SWAT+ file formats vary by version | Keep writers narrow and covered by golden-file tests |
| Weather gaps bias simulation | Fail by default; report missing values by station/month/variable |
| CRS mistakes silently corrupt spatial outputs | Require target projected CRS and write CRS checks to manifest |
| Land-use lookup mismatch | Fail on unmapped classes unless user explicitly permits nodata masking |

---

## 16. Future Extensions

Add only after MVP is working and tested:

1. NetCDF weather support for gridded climate products.
2. IMERG/GPM precipitation adapter with gauge-bias correction hooks.
3. SSURGO/HWSD database adapters.
4. Optional WhiteboxTools/TauDEM wrapper for users who want scripted delineation.
5. SWAT+ version-specific SQLite export after validating against official SWAT+ Editor expectations.
6. HTML QA report.

---

## 17. Success Criteria

The design is successful when:

- A user can point the tool at raw local input files and one YAML config.
- The tool produces a deterministic SWAT-ready input package.
- Every output file is listed in `manifest.json`.
- QA failures are explicit and reproducible.
- Weather and streamflow outputs can be inspected directly and used in a SWAT/SWAT+ setup workflow.
- The MVP does not claim to replace QSWAT+, SWAT+ Editor, TauDEM, or calibration tools.
