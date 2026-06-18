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
- High-level API skeleton in `swatprep/api.py`
- CLI skeleton in `swatprep/cli.py`
- QA primitives in `swatprep/qa.py`
- Typed errors in `swatprep/errors.py`
- Tests in `tests/`

Not implemented:

- Domain processors under `swatprep/core/`
- Writers under `swatprep/writers/`
- Manifest and QA report writing
- End-to-end `prepare()` pipeline

`SWATPrepProject.prepare()` intentionally raises `NotImplementedError`.

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
- Add a GUI.
- Claim `prepare()` works until processors and writers exist and tests prove it.

## Hydrology and SWAT Assumptions

Treat preprocessing errors as hydrologic modeling risks, not just software
errors.

Important controls:

- CRS must be explicit. Spatial processing should use a projected target CRS.
- Units must be explicit. Do not guess precipitation, temperature, or flow units.
- Weather gaps should fail by default unless the config explicitly allows
  warnings.
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
- Use `apply_patch` for manual file edits.
- Keep docs honest about current implementation status.
- Avoid promising unsupported SWAT/SWAT+ file compatibility.

## Path Handling

Config paths loaded from YAML must resolve relative to the config file's
directory, not the process working directory.

This behavior is covered by tests and should not regress.

## Verification Commands

Run these before claiming work is complete:

```bash
pytest -q
python -m compileall swatprep tests
python -m build --sdist --wheel
```

For CLI changes, also run:

```bash
swatprep validate examples/config_minimal.yaml
python -m swatprep.cli validate examples/config_minimal.yaml
```

The example validation command is expected to exit non-zero until placeholder
input files under `examples/data/` exist.

## Documentation Rules

When updating docs:

- State implemented and not implemented features separately.
- Keep README aligned with `SYSTEM_DESIGN.md`.
- Mention expected failures when examples use placeholder data.
- Keep non-goals visible so future agents do not expand MVP into a full model
  builder.

## Git Note

This workspace may not be a valid git repository. If `git status` fails, do not
try to repair git metadata unless the user explicitly asks.
