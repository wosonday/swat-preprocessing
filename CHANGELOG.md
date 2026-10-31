# Changelog

All notable changes to swatprep. Versions follow [Semantic Versioning](https://semver.org/);
each version has a Git tag `vX.Y.Z`, a Docker image `ghcr.io/wosonday/swatprep:X.Y.Z` and, from 0.3.0,
a [GitHub Release](https://github.com/wosonday/swat-preprocessing/releases).

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
