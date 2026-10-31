# Agent Guide

This file gives coding agents working in this repository the project context,
scope boundaries, and verification rules.

## Project Mission

`swatprep` prepares raw input datasets for SWAT Classic and SWAT+ workflows. It
is a Python library plus CLI that validates, normalizes, and writes
SWAT-compatible input packages.

The project is **not** a replacement for QSWAT, QSWAT+, SWAT+ Editor, TauDEM,
WhiteboxTools, PEST, or SWAT+ Toolbox.

## Current Implementation State

Implemented:

- Config schema in `swatprep/config.py`
- High-level prepare orchestration in `swatprep/api.py`
- CLI in `swatprep/cli.py`
- QA primitives in `swatprep/qa.py`
- Typed errors in `swatprep/errors.py`
- Domain processors under `swatprep/core/` (weather via `WeatherPreprocessor`,
  WGN helpers in `swatprep/core/_wgn.py` including SOLARAV/DEWPT/WNDAV)
- Converters layer under `swatprep/converters/`:
  - `climate.py` — `DayFilesConverter`: merges per-variable `.day` files into
    per-station CSVs
  - `station_weather.py` — `StationWeatherConverter`: reads raw per-station
    pcp/tmp master files + data directories (SWAT Classic style or CSV) into a
    `WeatherResult`, which `writers/weather.py`'s `WeatherWriter` or
    `writers/weather_plus.py`'s `SWATPlusWeatherWriter` then write out —
    conversion (reading) and formatting (writing) are separate concerns, one
    writer per target format
  - `streamflow.py` — `StreamflowConverter`
- Writers under `swatprep/writers/`
- Manifest and QA report writing
- Tests in `tests/` (141 pass, 7 skip as of last baseline)

Not implemented:

- Full watershed delineation
- HRU/LSU generation
- Complete SWAT+ `project.sqlite` export
- Calibration or uncertainty workflow
- RAINHHMX (requires sub-daily data; always written as -99)

`SWATPrepProject.build()` runs configured domains and writes a manifest when
at least one domain is processed.

## Architecture: Converters Layer

`swatprep/converters/` is an independent conversion layer that sits between raw
field data and `swatprep/core/`'s `WeatherPreprocessor`-shaped `WeatherResult`.
It does not depend on `swatprep/core/`.

Key classes:

| Class | Input | Output |
|-------|-------|--------|
| `DayFilesConverter` | `R_*.day`, `Tx_*.day`, `Tm_*.day` | `{STATION}.csv` |
| `StationWeatherConverter` | pcp/tmp master file(s) + raw per-station data dir(s) | `WeatherResult` (write with `WeatherWriter` or `SWATPlusWeatherWriter`) |

CLI: `swatprep convert weather --pcp-master ... --pcp-dir ... --tmp-master ...
--tmp-dir ... --target swat2012|swatplus OUT_DIR` (see `swatprep/cli.py`'s
`convert_weather` command). This replaced the earlier `convert pcp`/
`convert tmp`/`convert swatplus` commands and the `PCPConverter`/
`TmpConverter`/`SWATPlusWeatherConverter` classes they used, which no longer
exist.

Most converters return typed result objects with `files_written` and
`qa: list[QACheck]`. `StationWeatherConverter` is the exception — it only
reads raw station files and returns a `WeatherResult` (no `files_written`;
still has `.qa`), since writing is delegated to `WeatherWriter`/
`SWATPlusWeatherWriter`.

## SWAT File Format Notes

**SWAT 2012** (per-station file `pcp_<name>.txt` / `tmp_<name>.txt`, written
by `writers/weather.py`'s `WeatherWriter`):
- No metadata header block (no title / `Lati` / `Long` / `Elev` lines).
- Line 1: start date `YYYYMMDD` — the date of the **first** data record, not
  offset by a day.
- Data lines: compact values, no fixed-width padding (pcp: one value per
  line; tmp: `tmin,tmax` per line).
- Station metadata (`ID,NAME,LAT,LONG,ELEVATION`, uppercase) lives in a
  separate `master_pcp.txt` / `master_tmp.txt`, not in the per-station file.
- This matches the real SWAT2012 vendor-data convention; see
  `docs/WEATHER_OUTPUT.md` for the full format reference.

**SWAT+** (`.pcp`, `.tmp`, `.hmd`, `.slr`, `.wnd`, written by
`writers/weather_plus.py`'s `SWATPlusWeatherWriter`):
- Line 1: descriptive title
- Line 2: `nbyr     tstep       lat       lon      elev`
- Line 3: `{nbyr:4d}{0:10d}{lat:10.3f}{lon:10.3f}{elev:10.3f}`
- Data lines: `{year:4d}{doy:5d}{val:11.5f}  ` (2 trailing spaces required by
  SWAT+ Editor format)
- Temperature data: `{year:4d}{doy:5d}{tmax:11.5f} {tmin:11.5f}  `
- `SWATPlusWeatherWriter` also writes `weather-sta.cli` (station registry)
  and `weather-wgn.cli` (WGN statistics in SWAT+'s fixed format) — the
  linking files a `TxtInOut` folder actually reads to resolve each station's
  climate data.

## WGN Monthly Statistics

`WeatherPreprocessor._compute_wgn()` computes 12 monthly rows per station using
helpers in `swatprep/core/_wgn.py`:

- `TMPMX`, `TMPMN`, `TMPSTDMX`, `TMPSTDMN` — from `tmax`/`tmin` columns
- `PCPMM`, `PCPSTD`, `PCPSKW`, `PR_W1`, `PR_W2`, `PCPD` — from `precip` column
  (Markov chain probabilities computed within-year only, no cross-year transitions)
- `SOLARAV` — monthly mean solar radiation if `solar` column present, else -99
- `DEWPT` — monthly mean dew point via Buck (1981) equation from `rhum` + Tmean,
  else -99
- `WNDAV` — monthly mean wind speed if `wind` column present, else -99
- `RAINHHMX` — always -99 (requires sub-daily data)

## Scope Rules

Stay inside the reviewed design in `SYSTEM_DESIGN.md`.

Do:

- Build a preprocessor and format writer.
- Use one processor per data domain: DEM, land-use, soil, weather, streamflow.
- Use typed result objects and `QACheck` records.
- Fail by default on unsafe ambiguity: missing files, missing columns, unmapped
  classes, invalid dates, unclear units.
- Keep geospatial dependencies optional under `swatprep[geo]`.
- Use small synthetic fixtures in tests.

Do not:

- Implement full watershed delineation for MVP.
- Generate HRUs/LSUs for MVP.
- Write a full SWAT+ `project.sqlite` for MVP.
- Add calibration or sensitivity analysis.
- Add automatic public data download.
- Add a GUI that replaces QSWAT+ or SWAT+ Editor. The Streamlit web app in `app/` only edits and runs
  this tool's YAML: keep logic in `app/services/` (no Streamlit imports, tested), keep `app/pages/` and
  `app/ui/` thin, and never import `app` from `swatprep/`.
- Claim SWAT/SWAT+ model compatibility beyond the files the tests cover.

## Hydrology and SWAT Assumptions

Treat preprocessing errors as hydrologic modeling risks, not just software errors.

Important controls:

- CRS must be explicit. Spatial processing should use a projected target CRS.
- Units must be explicit. Do not guess precipitation, temperature, or flow units.
- Weather gaps should fail by default unless the config explicitly allows warnings.
- Land-use and soil lookup mismatches should fail by default.
- Soil source tables vary by region. Start with a clear CSV contract before
  adding SSURGO/HWSD adapters.
- Model performance metrics such as NSE, KGE, PBIAS, RMSE, and MAE belong to
  calibration/validation workflows, not preprocessing unit tests.

## Coding Rules

- Keep changes small and directly tied to the task.
- Prefer existing patterns over new abstractions.
- Do not refactor unrelated code.
- Add tests before changing behavior.
- Keep docs honest about current implementation status.
- Avoid promising unsupported SWAT/SWAT+ file compatibility.

## File Size Warning (Windows Linter)

A Windows-side linter truncates `.py` files that exceed approximately 10 950 bytes
after an edit. Symptoms: `SyntaxError` at the truncation point, or null bytes
(`\x00`) padding the file to a fixed size.

Workarounds:
- Write large files via `python3 -c "open(path,'w').write(content)"` or
  `shutil.copy('/tmp/file', dest)` — bypasses the linter.
- Append missing tail: `python3 -c "open(f).read() + tail" > f`.
- Split large modules: extract helper functions into a sibling `_helpers.py`.
- After any edit, verify with `python3 -c "import ast; ast.parse(open(f).read())"`.

## Path Handling

Config paths loaded from YAML must resolve relative to the config file's
directory, not the process working directory.

This behavior is covered by tests and should not regress.

## Verification Commands

Run these before claiming work is complete:

```bash
uv sync --extra geo --extra app --extra dev
uv run python -m pytest -q
uv run python -m compileall swatprep app tests
uv build
```

Current baseline (v0.6.0): `uv run python -m pytest -q` passes with **447 tests**.
Use `python -m pytest`, not bare `pytest`, so a missing dev install fails loudly.

When a field is added to `swatprep/config.py`, add it to `LAYOUT` in
`app/services/form_layout.py`; `tests/ui/test_form_model.py` fails otherwise.

For CLI changes, also run:

```bash
swatprep validate examples/config_minimal.yaml
python -m swatprep.cli validate examples/config_minimal.yaml
```

The example validation command is expected to exit 0 because synthetic input
files are included under `examples/data/`.

## Documentation Rules

When updating docs:

- State implemented and not implemented features separately.
- Keep README aligned with `SYSTEM_DESIGN.md`.
- Keep example behavior accurate; `examples/config_minimal.yaml` should validate
  and prepare successfully with the included synthetic data.
- Keep non-goals visible so future agents do not expand MVP into a full model
  builder.

## Git Note

This workspace may not be a valid git repository. If `git status` fails, do not
try to repair git metadata unless the user explicitly asks.
