# Complete swatprep MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the practical SWAT-ready preprocessing MVP without expanding into watershed delineation, HRU/LSU generation, or SWAT+ SQLite export.

**Architecture:** Keep the existing processor/result/writer pattern. Processors validate and return typed result objects with `QACheck`; writers serialize validated outputs only. Raster work stays optional behind `rasterio`.

**Tech Stack:** Python 3.10+, Pydantic, Click, pandas, numpy, optional rasterio/geopandas/shapely, pytest.

---

### Task 1: Stabilize Raster Error Handling

**Files:**
- Modify: `swatprep/core/dem.py`
- Modify: `swatprep/core/landuse.py`
- Modify: `swatprep/core/soil.py`
- Test: `tests/test_dem.py`, `tests/test_landuse.py`, `tests/test_soil.py`

- [x] Add regression tests for invalid raster files producing QA failures instead of uncaught `rasterio` exceptions.
- [x] Catch raster open/read failures in each raster processor and return result objects with fail QA.
- [x] Run `pytest tests/test_dem.py tests/test_landuse.py tests/test_soil.py -q`.

### Task 2: Add Minimal Raster Utilities

**Files:**
- Create: `swatprep/utils/raster.py`
- Test: `tests/test_raster_utils.py`

- [x] Add tests for reading unique raster codes, writing reclassified rasters, and copying raster with metadata.
- [x] Implement utility functions using `rasterio` only when installed.
- [x] Run `pytest tests/test_raster_utils.py -q`.

### Task 3: Complete Land-use MVP

**Files:**
- Modify: `swatprep/core/landuse.py`
- Modify: `swatprep/writers/landuse.py`
- Test: `tests/test_landuse.py`

- [x] Add test for writing `landuse_swat.tif` from a tiny valid source raster and lookup.
- [x] Store source raster path and code mapping in `LandUseResult`.
- [x] Writer writes `landuse_lookup.csv`, `landuse_raster_codes.csv`, and `landuse_swat.tif` when raster codes are available and all codes map.
- [x] Run `pytest tests/test_landuse.py -q`.

### Task 4: Complete Soil MVP

**Files:**
- Modify: `swatprep/core/soil.py`
- Modify: `swatprep/writers/soil.py`
- Test: `tests/test_soil.py`

- [x] Add test for writing `soil_raster_codes.csv` from a tiny valid source raster.
- [x] Ensure invalid soil raster becomes QA fail, not crash.
- [x] Writer keeps `usersoil.csv` behavior and writes raster code summary when available.
- [x] Run `pytest tests/test_soil.py -q`.

### Task 5: Complete DEM MVP

**Files:**
- Modify: `swatprep/core/dem.py`
- Modify: `swatprep/writers/spatial.py`
- Test: `tests/test_dem.py`

- [x] Add test for valid tiny DEM producing metadata and copied `dem_projected.tif`.
- [x] Keep no full hydrologic conditioning or delineation.
- [x] Writer writes `dem_info.json` and copies DEM to configured output name when readable.
- [x] Run `pytest tests/test_dem.py -q`.

### Task 6: Add Synthetic End-to-End Example

**Files:**
- Create or modify: `examples/data/*`
- Modify: `examples/config_minimal.yaml`
- Test: `tests/test_api.py`

- [x] Add tiny valid CSV fixtures and tiny GeoTIFF fixtures for example use.
- [x] Add test that `SWATPrepProject.from_config("examples/config_minimal.yaml").prepare()` succeeds.
- [x] Run `pytest tests/test_api.py -q`.

### Task 7: Update Documentation and Verify

**Files:**
- Modify: `README.md`
- Modify: `README_VI.md`
- Modify: `AGENTS.md`
- Modify: `DEVELOPER_GUIDE.md`

- [x] Update docs to state example config can run end-to-end.
- [x] Run `pytest -q`.
- [x] Run `python -m compileall swatprep tests`.
- [x] Run `python -m build --sdist --wheel --outdir /tmp/swatprep-build-check`.
- [x] Remove generated build/cache artifacts from the workspace.
