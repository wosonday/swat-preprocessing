from __future__ import annotations

import platform
import tempfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

# from scipy.stats import false_discovery_control

from .settings import Settings, load_settings

PACKAGES = ("swatprep", "streamlit", "rasterio", "geopandas", "pandas", "xarray", "netcdf4")
RASTER_DRIVERS = ("GTiff", "AIG")
VECTOR_DRIVERS = ("ESRI Shapefile", "GPKG")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class EnvironmentReport:
    python: str
    packages: dict[str, str]
    drivers: list[Check]
    folders: list[Check]

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.drivers + self.folders)


def check_folder(name: str, path: Path, need_write: bool) -> Check:
    if not path.exists():
        return Check(name, False, f"not found: {path}")
    if not path.is_dir():
        return Check(name, False, f"not a directory: {path}")
    if need_write:
        try:
            with tempfile.TemporaryFile(dir=path):
                pass
        except OSError as exc:
            return Check(name, False, f"not writable: {path} ({exc})")
    return Check(name, True, str(path))


def package_versions() -> dict[str, str]:
    out = {}
    for pkg in PACKAGES:
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = "not installed"
    try:
        import rasterio
        out["GDAL (rasterio)"] = rasterio.__gdal_version__
    except Exception as exc:
        out["GDAL (rasterio)"] = f"error: {exc}"
    return out


def _driver_checks(names, list_drivers) -> list[Check]:
    try:
        available = list_drivers()
    except Exception as exc:  # missing/broken library -> report it, don't crash the page
        return [Check(n, False, f"error: {exc}") for n in names]
    return [Check(n, n in available, "available" if n in available else "missing") for n in names]


def _rasterio_drivers():
    import rasterio
    with rasterio.Env() as env:
        return env.drivers()


def _pyogrio_drivers():  # geopandas read shapefile/GPKG via pyogrio
    import pyogrio
    return pyogrio.list_drivers()


def get_report(settings: Settings | None = None) -> EnvironmentReport:
    s = settings or load_settings()
    return EnvironmentReport(
        python=platform.python_version(),
        packages=package_versions(),
        drivers=_driver_checks(RASTER_DRIVERS, _rasterio_drivers)
        + _driver_checks(VECTOR_DRIVERS, _pyogrio_drivers),
        folders=[
            check_folder("data_root", s.data_root, need_write=False),
            check_folder("workspace", s.workspace, need_write=True),
        ],
    )