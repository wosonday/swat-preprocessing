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
- `prepare()` orchestration for configured domains
- DEM metadata validation
- Land-use lookup validation and raster-code cross-check
- Soil table validation and raster-code cross-check
- Weather station/daily CSV validation and WGN statistic generation
- Streamflow CSV validation
- Writers for spatial metadata, land-use lookup, `usersoil.csv`, weather files,
  observed streamflow, `manifest.json`, and `qa_report.md`
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
swatprep prepare config.yaml
```

Run one domain:

```bash
swatprep prepare config.yaml --only weather
swatprep prepare config.yaml --only streamflow
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

## Python API

```python
from swatprep import SWATPrepProject

project = SWATPrepProject.from_config("config.yaml")

checks = project.validate()
for check in checks:
    print(check.status, check.name, check.message)

result = project.prepare()
print(result.success)
print(result.output_dir)
print(result.manifest_path)
```

`prepare()` writes `manifest.json` and `qa_report.md` when at least one domain is
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

## Expected Output

Depending on configured domains, `prepare()` can write:

```text
output/
  manifest.json
  qa_report.md
  spatial/
    dem_info.json
    dem_projected.tif
  landuse/
    landuse_lookup.csv
    landuse_raster_codes.csv
    landuse_swat.tif
  soil/
    usersoil.csv
    soil_raster_codes.csv
  weather/
    ST001.pcp
    ST001.tmp
    wgn.csv
    stations.csv
  observed/
    streamflow_ST001.csv
    streamflow_meta.csv
```

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
