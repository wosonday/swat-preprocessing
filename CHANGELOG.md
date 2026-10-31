# Changelog

All notable changes to swatprep. Versions follow [Semantic Versioning](https://semver.org/);
each version has a Git tag `vX.Y.Z`, a Docker image `ghcr.io/wosonday/swatprep:X.Y.Z` and, from 0.3.0,
a [GitHub Release](https://github.com/wosonday/swat-preprocessing/releases).

## [Unreleased]

### Added
- **Projects** screen on the Project page when no project is open: recent projects (with their number of
  configs), open a project folder, or create a new project (the folder and its first `config.yaml`).
- **New config** dialog in the sidebar: creates a config inside the open project from a file name only
  (a free name such as `config_2.yaml` is suggested, the CRS of the open config is offered).

### Changed
- Station tables (`weather.stations`, `weather.precip/temp.stations`, `fill.csv.stations` and the master
  files of `swatprep convert`) are read without regard to case or spaces in the header, so both
  `id,name,lat,lon,elev` and the SWAT master layout `ID,NAME,LAT,LONG,ELEV` work; `LONGITUDE`,
  `LATITUDE` and `ELEVATION` are accepted too. Station ids stay text (`0012` keeps its zeros), and a
  non-numeric lat / lon / elev is reported with the station id.
- A project is a folder and its configs are the `.yaml` / `.yml` files at its root; the sidebar shows the
  project, **Change project** and the list of its configs.
- With unsaved changes, switching config or project is locked until you Save or Discard (it used to
  drop the changes silently).

### Removed
- The **Config path** field, its Browse button and the old **New config** panel that could create a
  config anywhere; configs are no longer searched three folders deep.

### Fixed
- The form jumped back to the **Project** tab whenever a tab's error count changed (for example after
  Validate, or when fixing a field); the selected tab is now kept.
- An empty **Variable map** table had no columns, so nothing could be typed into it; it now always shows
  the *Variable* and *Name in file* columns, and half-filled rows are ignored until both cells are set.
- Switching **Fill → Type** left an empty block of the other type in the YAML (for example `csv: {}` with
  `type: netcdf`), which failed validation with errors on fields the form did not show. The empty block of
  the unused type is now removed, also when an existing config is opened.
- Edits in the **Variable map** table of `weather.fill.netcdf` were lost, and the old rows written back,
  after the table was hidden for a run: switching to Explore, switching the fill type, or turning gap
  filling off and on. The table is now rebuilt from the config in that case.

## [0.5.0] - 2026-10-31

### Added
- Explore **Weather**: a station × month heatmap of missing days (measured, or after gap filling), each
  station's series with filled values and the days still missing, the fill report line, and the monthly
  climatology of precipitation for measured and filled data side by side.
- Explore **Map**: the DEM, land-use, soil and clip rasters written by Build on an interactive map (pydeck)
  with the project boundary, opacity, a Light / Dark / None basemap, a legend with SWAT names and the share
  of area of each class, and the layer's CRS, pixel size and NoData share.
- **CRS list**: `project.crs` (and the CRS of a new config) is a searchable list of common CRSs for
  Vietnam plus every EPSG projected CRS; any other value can still be typed or pasted, and a status line
  says whether it is a recognised projected CRS.

## [0.4.0] - 2026-10-31

### Added
- **Explore** on the Project page (switch **Configure | Explore**): charts of the data behind the saved
  config. First view, **Streamflow**: per-station summary (period, % missing, min/mean/max, Q5/Q50/Q95),
  hydrograph with log scale and missing days in red, flow duration curve (Weibull plotting position) and
  monthly climatology that applies the WMO-No. 1203 completeness rules and flags months valid in fewer
  than 80% of the years.
- App icon (a river network converging on its outlet): browser tab, sidebar logo, Windows Desktop
  shortcut (`icon.ico`, 16-256 px) and Linux application menu; source in `app/assets/icon.svg`.

## [0.3.1] - 2026-10-31

### Changed
- README, README_VI, DEVELOPER_GUIDE, TESTING_GUIDE, USER_GUIDE_VI, AGENTS and SYSTEM_DESIGN describe the
  web app, the install without Docker, the Docker image and the release process.

### Fixed
- `swatprep.__version__` now reads the installed package version instead of a hard-coded `0.1.0`.

## [0.3.0] - 2026-10-31

### Added
- **Project** page in the web app: choose a project folder (with recent folders), open or create a
  config, edit every config field in a form generated from the Pydantic models, Browse for files and
  folders, Validate with errors shown on the fields, Build with a QA table and `manifest.json` download.
- YAML is read and written with ruamel.yaml, keeping comments and key order.
- `swatprep-ui` command; install without Docker with `scripts/install.bat` / `scripts/install.sh`
  (latest release by default, or a given version).
- OpenDesign theme (light and dark) shipped inside the package.
- CI job that publishes a GitHub Release with the installers for each version tag.

### Changed
- `SWATPREP_DATA_ROOT` and `SWATPREP_WORKSPACE` are optional; a local install binds to `localhost` only.
- The Docker image starts the app with `swatprep-ui`.

## [0.2.3] - 2026-10-27

### Changed
- Docker image sets `SWATPREP_DATA_ROOT=/data` and `SWATPREP_WORKSPACE=/workspace` by default.
- `docker-compose.yaml`: port configurable with `SWATPREP_PORT`.

## [0.2.2] - 2026-10-25

### Added
- Streamlit web app with an environment report (package versions, GDAL drivers, folders).
- Docker image (Python 3.12, uv, `libexpat1`, non-root user) and `docker-compose.yaml`.
- CI: tests on every pull request; image published to `ghcr.io/wosonday/swatprep` from `main` and tags.

## Earlier

Core library and CLI (`validate`, `build`, `fill`, `clip`, `inspect`, `convert`); see the Git history.
