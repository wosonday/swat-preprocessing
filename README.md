# swatprep

`swatprep` is a small Python library and CLI for preparing raw DEM, land-use,
soil, weather, and streamflow inputs for SWAT Classic and SWAT+ workflows.

The project is intentionally scoped as a **preprocessor and format writer**. It
does not replace QSWAT, QSWAT+, SWAT+ Editor, TauDEM, WhiteboxTools, SWAT+ Toolbox,
PEST, or any calibration workflow.

## Status

Current version: `0.1.0`

Implemented:

- YAML config schema with Pydantic
- Config-relative path resolution
- Project validation CLI
- `build()` orchestration for configured domains
- DEM metadata validation
- Land-use lookup validation and raster-code cross-check
- Soil table validation and raster-code cross-check
- Weather station/daily CSV validation and WGN statistic generation
- Weather output as **SWAT+** (default) or **SWAT Classic**, selected by
  `project.targets`, with split precip/temperature sources and a configurable
  `file_pattern`
- Streamflow CSV validation
- Writers for spatial metadata, land-use lookup, `usersoil.csv`, weather files,
  observed streamflow, `manifest.json`, and `qa_report.md`
- Raw-data converters (`swatprep convert …`) for turning vendor formats into
  swatprep CSVs or SWAT+/SWAT Classic files
- Unit tests for config, QA, processors, writers, CLI-oriented behavior, and
  manifest generation

Still intentionally out of scope:

- Full watershed delineation
- HRU/LSU generation
- Complete SWAT+ `project.sqlite` export
- Calibration, sensitivity, or uncertainty analysis
- Automatic public data download
- GUI

See [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for the reviewed architecture.

## Install

For development:

```bash
pip install -e .[dev]
```

For geospatial validation:

```bash
pip install -e .[geo,dev]
```

The geospatial extra installs `rasterio`, `geopandas`, and `shapely`. These
dependencies stay optional so config, QA, CLI, weather, and streamflow workflows
can remain lightweight.

## CLI

Validate config and input paths:

```bash
swatprep validate examples/config_minimal.yaml
```

Run all configured domains:

```bash
swatprep build config.yaml
```

Run one domain:

```bash
swatprep build config.yaml --only weather
swatprep build config.yaml --only streamflow
```

The included example contains synthetic data and should validate successfully.

Inspect a weather CSV:

```bash
swatprep inspect weather path/to/station.csv
```

Inspect a raster:

```bash
swatprep inspect raster path/to/dem.tif
```

### Convert raw data

Standalone converters transform vendor formats into swatprep CSVs or directly
into SWAT files, independent of the `build` pipeline:

```bash
# Merge per-variable .day files (R_/Tx_/Tm_) into per-station CSVs
swatprep convert climate DATA_DIR OUT_DIR

# Wide or per-station streamflow → long-format CSV
swatprep convert streamflow SOURCE OUT_PATH

# Raw station files (SWAT Classic style or CSV) → SWAT2012 and/or SWAT+
swatprep convert weather --pcp-master MASTER.txt --pcp-dir DATA_DIR \
                         --tmp-master MASTER.txt --tmp-dir DATA_DIR \
                         --target swat2012 --target swatplus OUT_DIR
```

Use converters to *prepare* raw data into per-station CSVs, then point
`weather.data_dir` at them and run `swatprep build`. See
[`docs/WEATHER_OUTPUT.md`](docs/WEATHER_OUTPUT.md) for how weather output maps to
SWAT+/Classic.

### Fill gaps from an external source

`swatprep fill weather` fills missing days in observed station data using a
bias-corrected external source (e.g. satellite/reanalysis, pre-extracted by
you into the same per-station CSV format), before `build`:

```bash
swatprep fill weather \
  --stations STATIONS.csv --data-dir DATA_DIR \
  --fill-stations FILL_STATIONS.csv --fill-data-dir FILL_DATA_DIR \
  --variables precip,tmax,tmin --start 2000-01-01 --end 2000-12-31 \
  OUT_DIR
```

Point `weather.data_dir` at `OUT_DIR` and run `swatprep build` as normal.

The fill source can also be a daily gridded NetCDF (`--fill-netcdf FILE.nc
--fill-var-map precip=pr,tmax=tasmax,tmin=tasmin`, or the `weather.fill` YAML
block). The value of the grid cell nearest to each station is used; a station
exactly halfway between two cells takes the lower-index cell. If that cell has
no data (e.g. a sea cell), the nearest cell with data within `search_radius`
cells (default 1, `--fill-search-radius`) is used and a warning is reported.

### Clip a large raster to the basin

```bash
swatprep clip DEM.tif BOUNDARY.shp DEM_clip.tif          # crop to the boundary's bbox
swatprep clip LANDUSE.tif BOUNDARY.shp LU_clip.tif --mask  # also NoData outside the polygon
```

Needs `swatprep[geo]`. The raster is read strip by strip (bounded memory), the
boundary is reprojected to the raster CRS, and no resampling is done. Point
`dem.path` / `landuse.raster` / `soil.raster` at the clipped files before `build`.

The same can be done from `config.yaml` (needs `project.boundary`); `build` crops each
`src` to the boundary and writes `dst` (relative paths are relative to the YAML file),
before the other domains run, and skips a `dst` that is newer than its `src` and the boundary:

```yaml
clip:
  - src: D:/DATA/dem_asia.tif
    dst: ./data/spatial/dem_chu.tif
  - src: D:/DATA/landuse.tif
    dst: ./data/spatial/landuse_chu.tif
    mask: true          # optional: NoData outside the polygon (default false)
dem:
  path: ./data/spatial/dem_chu.tif      # use the clipped file
```

Run only this step with `swatprep build config.yaml --only clip`.

If `project.boundary` is set, `swatprep build` clips the `dem`, `landuse` and `soil` rasters
to it **in the same run and into the same `output_dir`**, with nothing extra to configure:

| Section | Clipped raster written to | Table written (restricted to the basin) |
|---|---|---|
| `dem` | `<output_dir>/spatial/<output_name>` (default `dem_projected.tif`) | `spatial/dem_info.json` |
| `landuse` | `<output_dir>/landuse/<output_name>` (default `landuse_clip.tif`) | `landuse/landuse_lookup.csv`: only classes present in the basin |
| `soil` | `<output_dir>/soil/<output_name>` (default `soil_clip.tif`) | `soil/usersoil.csv`: only soils present in the basin |

Checks and statistics describe the basin (only the boundary's window is read), and huge
regional rasters are never loaded whole. Each section accepts `clip: false` to turn this
off (whole raster scanned, full tables, no clipped file). The raster is cropped to the
boundary's bounding box and keeps its CRS (no reprojection). A clipped file that is newer
than its source and the boundary is not rewritten. If the boundary cannot be applied
(no `geopandas`, no CRS, no overlap) a warning or failed check is reported.

## Python API

```python
from swatprep import SWATPrepProject

project = SWATPrepProject.from_config("config.yaml")

checks = project.validate()
for check in checks:
    print(check.status, check.name, check.message)

result = project.build()
print(result.success)
print(result.output_dir)
print(result.manifest_path)
```

`build()` writes `manifest.json` and `qa_report.md` when at least one domain is
processed.

## Config Overview

Minimal config:

```yaml
project:
  name: "ExampleBasin_2024"
  crs: "EPSG:32648"
  output_dir: "./output"
  targets:
    - "swatplus"
```

Supported sections:

- `project`
- `dem`
- `landuse`
- `soil`
- `weather`
- `streamflow`

Relative paths are resolved from the directory containing the YAML file, not the
process working directory.

Weather dates are validated as ISO dates. `weather.end` must be on or after
`weather.start`.

A typical `weather` section (output format is driven by `project.targets`
above):

```yaml
weather:
  stations: "./data/weather_stations.csv"   # id, name, lat, lon, elev
  data_dir: "./data/weather"                # one CSV per station
  file_pattern: "{id}.csv"                   # default; use "{name}.csv" to match by name
  variables: ["precip", "tmax", "tmin"]
  start: "2000-01-01"
  end:   "2000-12-31"
  missing_policy: "warn"                     # "fail" | "warn"
```

Precipitation and temperature can be drawn from separate station networks via
`weather.precip` / `weather.temp` sub-blocks — see
[`docs/WEATHER_OUTPUT.md`](docs/WEATHER_OUTPUT.md).

## Expected Output

Depending on configured domains, `build()` can write:

```text
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
  weather/
    StationA.pcp     # SWAT+ daily precipitation (year/doy rows)
    StationA.tmp     # SWAT+ daily temperature
    pcp.cli tmp.cli  # SWAT+ per-variable index files
    weather-sta.cli  # SWAT+ station registry
    weather-wgn.cli  # SWAT+ WGN statistics
    wgn.csv
    stations.csv
  observed/
    streamflow_ST001.csv
    streamflow_meta.csv
```

The **weather** format follows `project.targets`: `swatplus` (default) writes
SWAT+ daily files plus per-variable `*.cli` indexes and the `weather-sta.cli`/
`weather-wgn.cli` linking files; `swat` writes SWAT Classic
`pcp_<name>.txt`/`tmp_<name>.txt` (no header block, un-offset start date)
plus `master_pcp.txt`/`master_tmp.txt`; listing both writes each format into
its own `weather/swatplus/` and `weather/swat/` sub-directory. Output file
names come from the station `name` column. See
[`docs/WEATHER_OUTPUT.md`](docs/WEATHER_OUTPUT.md) for the full reference,
including the `file_pattern` input-naming option (default `{id}.csv`) and split
precip/temp sources.

Invalid input should be reported as QA failures. Writers skip domains with hard
processor failures.

## Development

Run tests:

```bash
pytest -q
```

Check Python syntax:

```bash
python -m compileall swatprep tests
```

Build package:

```bash
python -m build --sdist --wheel
```

Current verified state:

- `pytest -q` passes with 87 tests.
- `python -m compileall swatprep tests` passes.

## Implementation Guidance

Keep each processor narrow and testable:

1. Load one data domain.
2. Validate required structure and hydrologic assumptions.
3. Return a typed result object with `qa: list[QACheck]`.
4. Let the writer serialize only validated result data.

Do not turn this project into a full SWAT+ model builder. QSWAT/QSWAT+ and
SWAT+ Editor remain responsible for watershed delineation, HRU/LSU generation,
routing objects, and complete project database construction.
