<img src="app/assets/icon.svg" width="72" alt="" align="right">

# swatprep

`swatprep` is a small Python library and CLI that prepares raw DEM, land-use, soil, weather and
streamflow inputs for SWAT Classic and SWAT+ workflows. You describe a project once in a YAML file
and run `swatprep build`, or fill the same YAML in the **web app** (`swatprep-ui`), which also charts and maps
the data behind it.

It is deliberately a **preprocessor and format writer**. It does not replace QSWAT, QSWAT+,
SWAT+ Editor, TauDEM, WhiteboxTools, SWAT+ Toolbox, PEST or any calibration workflow.

Full guides: **[docs/USER_GUIDE_VI.md](docs/USER_GUIDE_VI.md)** (Vietnamese, step by step, every YAML
option) · **[docs/LEARNING_GUIDE_VI.md](docs/LEARNING_GUIDE_VI.md)** (Vietnamese, how the code fits together, with
runnable examples in [docs/learning/](docs/learning/)) · [examples/config_full.yaml](examples/config_full.yaml) (annotated template) ·
[docs/WEATHER_OUTPUT.md](docs/WEATHER_OUTPUT.md) · [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) ·
[TESTING_GUIDE.md](TESTING_GUIDE.md) · [docs/INSTALL.md](docs/INSTALL.md) (team install, Vietnamese) ·
[docs/RELEASING.md](docs/RELEASING.md) · [CHANGELOG.md](CHANGELOG.md).

## What it does

| Area | Features |
|---|---|
| Configuration | Pydantic-validated YAML; paths relative to the YAML file; `validate` reports every missing file at once |
| Rasters (DEM, land use, soil) | Crop to `project.boundary`, **reproject to `project.crs`**, optional output `resolution`; memory-bounded (strip reads, boundary window); DEM statistics; raster-code cross-check against the lookup / soil table; tables restricted to the basin; clipped rasters and tables written into one `output_dir` |
| Weather | Station / daily CSV validation, WGN statistics, **SWAT+** or **SWAT Classic** output (`project.targets`), split precip / temperature sources, `file_pattern`; **gap filling** from a CSV or daily NetCDF source with per-station bias correction, including **virtual stations** (no observed day) that borrow the nearest gauge's correction |
| Streamflow | Long-format CSV validation and per-station output |
| Quality assurance | Every step returns `pass` / `warn` / `fail` checks; `manifest.json` and `qa_report.md` are written for each build |
| Converters | Vendor `.day` files, wide streamflow tables, raw station files to CSV / SWAT2012 / SWAT+ |
| Web app | **Configure**: a form over the same YAML (comments kept): projects screen, sections on or off, paste or browse for files, a searchable CRS list, an ⓘ description on every field and a **Show help** switch, Validate (errors shown on the field) and Build with the QA table. **Explore**: weather completeness heatmap, observed vs filled series and monthly precipitation climatology; streamflow hydrograph, flow duration curve and monthly climatology (WMO-No. 1203 completeness rules); an interactive **Map** of the output rasters with the boundary, rain stations, extra layers (`.shp`, `.gpkg`, `.geojson`, CSV points) and an extents table |
| Distribution | One-click install without Docker (`install.bat` / `install.sh`), Docker image `ghcr.io/wosonday/swatprep`, a GitHub Release per version |

Out of scope: watershed delineation, HRU/LSU generation, a complete SWAT+ `project.sqlite`,
calibration or uncertainty analysis, automatic data download, a GUI that replaces QSWAT+ or SWAT+ Editor
(the web app only edits and runs this tool's YAML).

## Install

| Who | How |
|---|---|
| Users on Windows (no Python or Docker needed) | Download and double-click [`install.bat`](https://github.com/wosonday/swat-preprocessing/releases/latest/download/install.bat). It installs the latest release and adds a **SWATprep** shortcut to the Desktop; run it again to update, or `install.bat v0.3.0` for a given version. Guide: [docs/INSTALL.md](docs/INSTALL.md) |
| Users on Linux / macOS | `curl -LO https://github.com/wosonday/swat-preprocessing/releases/latest/download/install.sh && sh install.sh` |
| Developers | `uv sync --extra geo --extra app --extra dev`, then `uv run swatprep --version` and `uv run swatprep-ui` (or the short alias `uv run app`) |
| Docker | `docker run --rm -p 127.0.0.1:8501:8501 -v "<data>:/data:ro" -v "<projects>:/workspace" ghcr.io/wosonday/swatprep:latest` (or a version tag such as `:0.3.0`) |

Extras: `geo` (rasterio, geopandas, shapely: rasters, clipping, reprojection), `app` (Streamlit web app),
`dev` (pytest). Without `geo`, config checks, QA, weather and streamflow still work. `pip install -e .[geo,app,dev]`
works too; uv is preferred because it installs exactly the versions in `uv.lock`.

## Quick start

### Web app

1. Start **SWATprep** (Desktop shortcut, or `swatprep-ui`); the browser opens. The app only listens on
   this computer (`localhost`).
2. On the **Project** page, the **Projects** screen lists recent projects; open a project folder or create
   a new one (a folder plus its first `config.yaml`). A project's configs are the `.yaml` files in that
   folder: pick one in the sidebar or add one with **New config**.
3. Switch on the sections you need (DEM, Land use, Soil, Weather, Streamflow, Clip) and fill the fields;
   paths can be pasted or picked with **Browse**.
4. **Validate**: missing files and invalid values are marked on the fields. **Build**: review the QA
   table and download `manifest.json`.
5. Switch to **Explore** to chart the weather and streamflow data and to see the rasters, stations and your own
   layers on the **Map**. Turn on **Show help** in the sidebar to read what each field does.

The form reads and writes the same `config.yaml` (comments and key order are kept), so a config made in
the app also runs with the CLI. Paths are saved as the app sees them; in Docker that means `/data/...`.

### Command line

1. Write `config.yaml` (start from [`examples/config_full.yaml`](examples/config_full.yaml)).
2. `swatprep validate config.yaml`: checks the YAML and that every input file exists.
3. *(optional)* `swatprep fill weather --config config.yaml`: fills missing station days.
4. `swatprep build config.yaml` (or `--only clip|dem|landuse|soil|weather|streamflow`).
5. Read `output/qa_report.md`, fix every `fail`, review each `warn`.

## Writing the YAML

Rules in short (details in the guide):

- Only `project` is required; a section you leave out is skipped.
- Relative paths are resolved from the folder that holds the YAML file. On Windows write `D:/data/x.tif`
  (forward slashes) or double the backslashes inside double quotes.
- Dates are ISO strings: `"2000-01-01"`. `weather.end` must not be before `weather.start`.
- Defaults are listed below; any field you omit takes its default.

A complete, valid example:

```yaml
project:
  name: "Chu_basin"
  crs: "EPSG:32648"                      # target CRS of every clipped raster
  boundary: "./data/boundary.shp"        # enables automatic clipping of dem / landuse / soil
  output_dir: "./output"
  targets: ["swatplus"]                  # swatplus | swat | both

dem:
  path: "./data/dem.tif"
  output_name: "dem_projected.tif"       # -> output/spatial/
  resampling: bilinear                   # nearest | bilinear | cubic (used when reprojecting)
  resolution: 30                         # optional; units of project.crs

landuse:
  raster: "./data/landuse.tif"
  lookup: "./data/landuse_lookup.csv"
  source_code_col: "code"
  swat_code_col: "swat_code"
  swat_name_col: "swat_name"
  output_name: "landuse_clip.tif"        # -> output/landuse/ (always nearest-neighbour)
  resolution: 10

soil:
  raster: "./data/soil.tif"
  table: "./data/usersoil.csv"
  soil_key_col: "SOIL_ID"
  output_name: "soil_clip.tif"           # -> output/soil/

weather:
  stations: "./data/stations.csv"        # id, name, lat, lon, elev
  data_dir: "./data/weather"             # one CSV per station
  file_pattern: "{id}.csv"               # or "{name}.csv"
  variables: [precip, tmax, tmin]
  start: "2000-01-01"
  end: "2020-12-31"
  missing_policy: "warn"                 # fail | warn

streamflow:
  path: "./data/streamflow.csv"
  date_col: "date"
  station_id_col: "station_id"
  value_col: "flow"
  units: "m3s"                           # m3s | mm
```

### Section reference

| Section | Required fields | Optional fields (default) |
|---|---|---|
| `project` | `name`, `crs` | `boundary` (none), `output_dir` (`./output`), `targets` (`[swatplus]`), `overviews` (`true`) |
| `dem` | `path` | `output_name` (`dem_projected.tif`), `clip` (`true`), `resampling` (`bilinear`), `resolution` |
| `landuse` | `raster`, `lookup` | `source_code_col` (`code`), `swat_code_col` (`swat_code`), `swat_name_col` (`swat_name`), `output_name` (`landuse_clip.tif`), `clip` (`true`), `output_lookup` (`true`), `resolution` |
| `soil` | `raster`, `table` | `soil_key_col` (`soil_id`), `output_usersoil` (`true`), `usersoil_format` (`swat`), `output_name` (`soil_clip.tif`), `clip` (`true`), `output_lookup` (`true`), `resolution` |
| `weather` | `start`, `end`, and a source (`stations` + `data_dir`, or `precip` / `temp`) | `file_pattern` (`{id}.csv`), `variables` (`[precip, tmax, tmin]`), `units`, `missing_policy` (`fail`), `fill` |
| `streamflow` | `path` | `format` (`long`; `per_station` for one-station files, id = file name), `glob` (`Q_*.csv`), `date_col` (`date`), `station_id_col` (`station_id`), `value_col` (`flow`), `units` (`m3s`) |
| `clip` (list) | each item: `src`, `dst` | `mask` (`false`), `resampling` (`nearest`), `resolution`; needs `project.boundary` |

## Clipping and reprojection

When `project.boundary` is set, `build` crops `dem`, `landuse` and `soil` to the basin and
**reprojects them to `project.crs`** in the same run, writing the rasters and the basin-only tables
into the same `output_dir`:

| Section | Raster written to | Table written |
|---|---|---|
| `dem` | `<output_dir>/spatial/<output_name>` | `spatial/dem_info.json` |
| `landuse` | `<output_dir>/landuse/<output_name>` | `landuse/landuse_lookup.csv` (classes present in the basin) |
| `soil` | `<output_dir>/soil/<output_name>` | `soil/usersoil.csv` (soils present in the basin, 152-column SWAT+ layout) |

- Only the window around the boundary is read and warped, so regional or continental rasters are never
  loaded whole.
- Land use and soil use nearest-neighbour resampling (class codes are never interpolated); the DEM uses
  `dem.resampling` (default `bilinear`). Without `resolution`, GDAL picks a pixel size close to the source.
- A clipped file is rewritten when its source or the boundary is newer, or when its CRS / resolution no
  longer matches the config; otherwise it is kept (`clip_skipped`).
- `clip: false` in a section turns this off for it (whole raster scanned, full tables, no clipped file).
- With `project.overviews: true` (default) every clipped raster also gets internal **overviews** (`average` for the
  DEM, `mode` for class rasters) and GDAL **statistics** tags (plus class pixel counts), so the web app's map opens
  large rasters about ten times faster with exact values; pixel values are unchanged, files grow by about a third.
  GDAL uses every CPU core for clipping and overviews (set `GDAL_NUM_THREADS` to limit it).
- The same operation is available stand-alone:

```bash
swatprep clip DEM.tif BOUNDARY.shp DEM_clip.tif --crs EPSG:32648 --resampling bilinear --resolution 30
swatprep clip LANDUSE.tif BOUNDARY.shp LU_clip.tif --crs EPSG:32648 --mask
```

## Filling missing weather days

`swatprep fill weather` fills missing days of observed stations from a gridded or per-station source
that you extracted yourself (satellite or reanalysis), before `build`:

```yaml
weather:
  stations: ./data/obs/stations.csv
  data_dir: ./data/obs
  variables: [precip, tmax, tmin]
  start: "1981-01-01"
  end: "2014-12-31"
  fill:
    type: netcdf                    # csv | netcdf
    output_dir: ./data/filled
    min_overlap_days: 365           # default 10
    netcdf:
      path: ./data/grid.nc          # daily; mm and degC
      var_map: { precip: pr, tmax: tasmax, tmin: tasmin }
      search_radius: 1              # 0-5; look for a cell with data around the nearest one
```

```bash
swatprep fill weather --config config.fill.yaml
```

`build` fills gaps only when `weather.fill.run_in_build: true` is set (one file, one command: it fills from
the observed `weather.stations` / `data_dir`, exports the filled CSVs to `weather.fill.output_dir`, then builds from
them; `output_dir` must differ from `data_dir`). Otherwise it ignores the `weather.fill` block. `weather.missing_policy` only
controls whether `build` treats a gap as an error (`fail`, nothing is written) or a warning (`warn`, gaps
are written as `-99`). A gap is an empty cell or a missing row in the station CSV; `-99` in the CSV is
read as a real value. Details: [docs/WEATHER_MISSING_FILL_VI.md](docs/WEATHER_MISSING_FILL_VI.md).

For every station and variable, the external series is bias-corrected on the days both sources have
data (linear scaling; Teutschbein and Seibert, 2012): precipitation is multiplied by the ratio of means,
temperature is shifted by the difference of means. Days that already have an observation are never
changed. Results go to `output_dir` together with `fill_report.csv`; point `weather.stations` and
`weather.data_dir` of the build config at that folder. The grid cell nearest to a station is used (a tie
takes the lower-index cell); if it has no data, the nearest cell with data within `search_radius` is
used and a warning is reported.

**Virtual stations.** A station with no observed day (or no data file) has no overlap, so by default it is not
filled and is written as `-99`. Set `fill_ungauged: true` to fill it entirely from the source: with
`correct_ungauged: true` (default) it takes the correction of the nearest gauged station of the same variable
within `max_borrow_km` (default 50 km, great-circle distance), otherwise raw source values. `fill_report.csv`
records `correction_from` and `distance_km`.

```yaml
  fill:
    type: netcdf
    output_dir: ./data/filled
    fill_ungauged: true
    correct_ungauged: true
    max_borrow_km: 50
```

## Command line

| Command | Purpose |
|---|---|
| `swatprep validate CONFIG` | Check the YAML and the existence of every input file; writes nothing |
| `swatprep build CONFIG [--only DOMAIN]` | Run all configured domains or one |
| `swatprep fill weather --config CONFIG` | Fill missing station days (flags override the YAML, e.g. `--fill-ungauged`, `--no-correct-ungauged`, `--max-borrow-km 30`) |
| `swatprep clip RASTER BOUNDARY OUT [--mask] [--crs] [--resampling] [--resolution] [--no-overviews]` | Crop (and optionally reproject) one raster; adds overviews and statistics unless `--no-overviews` |
| `swatprep inspect raster\|weather PATH` | Quick look at a raster or weather CSV |
| `swatprep convert climate\|streamflow\|weather ...` | Convert vendor formats |

```bash
swatprep convert climate DATA_DIR OUT_DIR                        # R_/Tx_/Tm_ .day files -> per-station CSV
swatprep convert streamflow SOURCE OUT_PATH                      # wide or per-station -> long CSV
swatprep convert weather --pcp-master M.txt --pcp-dir D --tmp-master T.txt --tmp-dir E \
                         --target swat2012 --target swatplus OUT_DIR
```

## Python API

```python
from swatprep import SWATPrepProject

project = SWATPrepProject.from_config("config.yaml")
for check in project.validate():
    print(check.status, check.name, check.message)

result = project.build()                      # or project.build(only="soil")
print(result.success, result.output_dir, result.manifest_path)
```

## Output

```text
output/
  manifest.json            # files written, domains processed, QA summary
  qa_report.md             # every pass / warn / fail check
  spatial/    dem_projected.tif  dem_info.json
  landuse/    landuse_clip.tif  landuse_lookup.csv  landuse_vlookup.csv  landuse_raster_codes.csv
  soil/       soil_clip.tif  usersoil.csv  soil_vlookup.csv  soil_raster_codes.csv
  weather/    StationA.pcp  StationA.tmp  pcp.cli tmp.cli  weather-sta.cli  weather-wgn.cli  wgn.csv  stations.csv  swatplus_wgn_*.csv
  observed/   streamflow_ST001.csv  streamflow_meta.csv
```

`landuse_vlookup.csv` (`LANDUSE_ID, SWAT_CODE`) and `soil_vlookup.csv` are two-column raster-value lookup
tables: one row per value, sorted, restricted to the basin when clipping, first row kept for repeated codes
(set `output_lookup: false` in `landuse` / `soil` to skip them). The soil lookup header follows
`project.targets`: `swat` writes `SEQN, SNAM`; `swatplus` (default) writes `SOIL_ID, SNAM`.
When both are selected, `soil_vlookup.csv` contains the SWAT+ lookup and `soil_vlookup_swat.csv` the Classic
lookup. `soil_key_col` still selects the source table's join key, independently of the output header.

`project.targets` also selects the weather format: `swatplus` (default) writes SWAT+ daily files plus
`*.cli` index and linking files; `swat` writes SWAT Classic `pcp_<name>.txt` / `tmp_<name>.txt` and
`master_*.txt` (whose `ID` column is the serial number 1, 2, 3, ... of the station, numbered separately in `master_pcp` and `master_tmp`); both write into `weather/swatplus/` and `weather/swat/`. See
[docs/WEATHER_OUTPUT.md](docs/WEATHER_OUTPUT.md). Invalid input is reported as QA failures, and domains
with hard failures are not written.

## Common QA messages

| Check | Meaning | Fix |
|---|---|---|
| `soil_unmatched_codes` | A raster soil code is not in the table's `soil_key_col` | Add the row (code `0` is usually "WATER") or map to a similar soil |
| `landuse_unmatched_codes` | A raster class is not in the lookup | Add the row to the lookup |
| `*_boundary_ignored` | The boundary could not be applied, the whole raster is scanned | Boundary needs a CRS and must overlap the raster |
| `dem_crs_reprojected` | The DEM CRS differs from `project.crs` and the clipped DEM was reprojected | Informational |
| `missing:<station>:<var>` | Missing values in the date range | `fill`, or `missing_policy: warn` |

## Development

```bash
uv sync --extra geo --extra app --extra dev
uv run python -m pytest -q        # core and web app tests (tests/ui uses Streamlit AppTest)
uv run swatprep-ui                # run the web app from source (alias: uv run app)
uv build                          # sdist and wheel
```

New to the code? Start with [docs/LEARNING_GUIDE_VI.md](docs/LEARNING_GUIDE_VI.md): core libraries, how the CLI,
API and web app reach the same processors, how the form is generated from the Pydantic models, how the map is built
and what makes it fast, with measured numbers and runnable scripts in [docs/learning/](docs/learning/).

The web app lives in `app/` and depends one way on the core: `pages` -> `ui` -> `services` -> `swatprep`.
`app/services` never imports Streamlit and holds the tested logic. Every config field must have a
`description` (shown as the field's help) and be listed in `app/services/form_layout.py`; tests fail otherwise.
CI tests every pull request; a tag `vX.Y.Z` publishes the Docker image and a GitHub Release
([docs/RELEASING.md](docs/RELEASING.md)).

Keep each processor narrow and testable: load one domain, validate structure and hydrologic
assumptions, return a typed result with `qa: list[QACheck]`, and let the writer serialize only
validated data. Do not turn this project into a full SWAT+ model builder.

## References

- Arnold, J.G. et al. (2012). *SWAT Input/Output Documentation, Version 2012*. Texas Water Resources
  Institute, TR-439.
- Bieger, K. et al. (2017). Introduction to SWAT+. *J. Am. Water Resour. Assoc.*, 53(1), 115-130.
- Teutschbein, C. and Seibert, J. (2012). Bias correction of regional climate model simulations for
  hydrological climate-change impact studies. *J. Hydrol.*, 456-457, 12-29.
- Vogel, R.M. and Fennessey, N.M. (1994). Flow-duration curves. I: New interpretation and confidence intervals.
  *J. Water Resour. Plann. Manage.*, 120(4), 485-504.
- World Meteorological Organization (2017). *WMO Guidelines on the Calculation of Climate Normals* (WMO-No. 1203).
