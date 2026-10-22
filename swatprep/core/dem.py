"""DEMPreprocessor: validate a Digital Elevation Model for SWAT/SWAT+ use.

rasterio is optional (part of swatprep[geo]). When not installed, metadata
extraction is skipped with a warn QA check so the pipeline can continue.

Checks performed (when rasterio is available):
  1. File can be opened.
  2. CRS is defined (warn if missing).
  3. CRS matches project target CRS (warn if different).
  4. NoData value is set (warn if missing).
  5. Elevation statistics are plausible (min < max, not all-NaN).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import DEMConfig
from ..qa import QACheck
from ..utils.raster import masked_stats, resolve_window

try:
    import rasterio  # type: ignore
    _HAS_RASTERIO = True
except ImportError:
    _HAS_RASTERIO = False


@dataclass
class DEMResult:
    """Output of DEMPreprocessor.run()."""

    path: Path
    output_name: str
    crs: str | None
    shape: tuple | None
    resolution: tuple | None
    elevation_range: tuple | None
    nodata: float | None
    qa: list[QACheck] = field(default_factory=list)


class DEMPreprocessor:
    """Validate a DEM raster for SWAT/SWAT+ use."""

    def __init__(
        self, cfg: DEMConfig, project_crs: str | None = None, boundary: Path | None = None,
    ) -> None:
        self.cfg = cfg
        self.project_crs = project_crs
        self.boundary = boundary  # project.boundary: statistics limited to its window

    def run(self) -> DEMResult:
        qa: list[QACheck] = []

        if not self.cfg.path.exists():
            qa.append(QACheck(
                name="dem_file_exists",
                status="fail",
                message="DEM file not found: " + str(self.cfg.path),
                context={"path": str(self.cfg.path)},
            ))
            return DEMResult(
                path=self.cfg.path,
                output_name=self.cfg.output_name,
                crs=None, shape=None, resolution=None,
                elevation_range=None, nodata=None, qa=qa,
            )

        if not _HAS_RASTERIO:
            qa.append(QACheck(
                name="rasterio_missing",
                status="warn",
                message=(
                    "rasterio not installed -- DEM metadata checks skipped. "
                    "Install swatprep[geo] to enable full validation."
                ),
            ))
            return DEMResult(
                path=self.cfg.path,
                output_name=self.cfg.output_name,
                crs=None, shape=None, resolution=None,
                elevation_range=None, nodata=None, qa=qa,
            )

        return self._inspect_with_rasterio(qa)

    def _inspect_with_rasterio(self, qa: list[QACheck]) -> DEMResult:
        try:
            ds = rasterio.open(self.cfg.path)
        except Exception as exc:
            qa.append(QACheck(
                name="dem_raster_read_failed",
                status="fail",
                message="Could not read DEM raster: " + str(self.cfg.path),
                context={"path": str(self.cfg.path), "error": str(exc)},
            ))
            return DEMResult(
                path=self.cfg.path,
                output_name=self.cfg.output_name,
                crs=None, shape=None, resolution=None,
                elevation_range=None, nodata=None, qa=qa,
            )

        with ds:
            crs_str = str(ds.crs) if ds.crs else None
            shape = (ds.height, ds.width)
            resolution = ds.res
            nodata = ds.nodata

            # CRS checks
            if crs_str is None:
                qa.append(QACheck(
                    name="dem_crs_missing",
                    status="warn",
                    message="DEM has no CRS defined -- reproject before use in SWAT.",
                ))
            elif self.project_crs and crs_str != self.project_crs:
                qa.append(QACheck(
                    name="dem_crs_mismatch",
                    status="warn",
                    message=(
                        "DEM CRS (" + crs_str + ") differs from project CRS "
                        "(" + str(self.project_crs) + "). Reprojection required."
                    ),
                    context={"dem_crs": crs_str, "project_crs": self.project_crs},
                ))
            else:
                qa.append(QACheck(
                    name="dem_crs",
                    status="pass",
                    message="DEM CRS: " + str(crs_str),
                ))

            # NoData check
            if nodata is None:
                qa.append(QACheck(
                    name="dem_nodata_missing",
                    status="warn",
                    message="DEM has no NoData value set.",
                ))

            # Elevation statistics
            window = resolve_window(ds, self.boundary, qa, "dem")
            elev_min, elev_max, elev_mean, n_valid = masked_stats(ds, window=window)
            if n_valid == 0:
                qa.append(QACheck(
                    name="dem_all_nodata",
                    status="fail",
                    message="DEM contains no valid (non-NoData) pixels.",
                ))
                return DEMResult(
                    path=self.cfg.path, output_name=self.cfg.output_name,
                    crs=crs_str, shape=shape,
                    resolution=resolution, elevation_range=None,
                    nodata=nodata, qa=qa,
                )

            if elev_min >= elev_max:
                qa.append(QACheck(
                    name="dem_flat",
                    status="warn",
                    message=(
                        "DEM appears flat: min=" + str(round(elev_min, 1))
                        + " max=" + str(round(elev_max, 1))
                        + ". Verify the raster is correct."
                    ),
                    context={"elev_min": elev_min, "elev_max": elev_max},
                ))
            else:
                qa.append(QACheck(
                    name="dem_elevation_stats",
                    status="pass",
                    message=(
                        "Elevation range: "
                        + str(round(elev_min, 1)) + " -- " + str(round(elev_max, 1))
                        + " m (mean " + str(round(elev_mean, 1)) + " m)"
                    ),
                    context={
                        "elev_min": elev_min,
                        "elev_max": elev_max,
                        "elev_mean": elev_mean,
                    },
                ))

            return DEMResult(
                path=self.cfg.path,
                output_name=self.cfg.output_name,
                crs=crs_str,
                shape=shape,
                resolution=resolution,
                elevation_range=(elev_min, elev_max),
                nodata=nodata,
                qa=qa,
            )
