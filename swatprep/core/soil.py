"""SoilPreprocessor: validate soil parameter table and cross-check with raster.

rasterio is optional -- raster cross-check is skipped when not installed.

Minimal required SWAT usersoil columns (Arnold et al. 2012):
    soil_key_col  (default "soil_id") -- join key matching raster codes
    HYDGRP        -- hydrologic soil group (A, B, C, D)
    SOL_ZMX       -- maximum root depth (mm)
    NLAYERS       -- number of soil layers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..config import SoilConfig
from ..errors import InputValidationError
from ..qa import QACheck
from ..utils.raster import resolve_window, unique_codes
from .clip import basin_rows

try:
    import rasterio  # type: ignore
    _HAS_RASTERIO = True
except ImportError:
    _HAS_RASTERIO = False

_REQUIRED_COLS = {"HYDGRP", "SOL_ZMX", "NLAYERS"}
_RECOMMENDED_LAYER1 = {"SOL_Z1", "SOL_BD1", "SOL_AWC1", "SOL_K1", "SOL_CBN1"}
_VALID_HYDGRP = {"A", "B", "C", "D", "A/D", "B/D", "C/D"}


@dataclass
class SoilResult:
    """Output of SoilPreprocessor.run()."""

    soil_table: pd.DataFrame
    raster_codes: set | None
    unmatched_codes: set
    qa: list[QACheck] = field(default_factory=list)


class SoilPreprocessor:
    """Validate soil parameter table and cross-check unique raster codes."""

    def __init__(self, cfg: SoilConfig, boundary: Path | None = None) -> None:
        self.cfg = cfg
        self.boundary = boundary  # project.boundary: codes read only inside its window
        self._windowed = False  # True once the boundary window was actually applied

    def run(self) -> SoilResult:
        qa: list[QACheck] = []
        table = self._load_table(qa)
        raster_codes = self._read_raster_codes(qa)
        unmatched = self._cross_check(table, raster_codes, qa)
        if self._windowed and raster_codes:
            table = basin_rows(table, self.cfg.soil_key_col, raster_codes, "soil", qa)
        return SoilResult(
            soil_table=table,
            raster_codes=raster_codes,
            unmatched_codes=unmatched,
            qa=qa,
        )

    def _load_table(self, qa: list[QACheck]) -> pd.DataFrame:
        cfg = self.cfg
        df = pd.read_csv(cfg.table)

        if cfg.soil_key_col not in df.columns:
            raise InputValidationError(
                "Soil table missing key column '" + cfg.soil_key_col + "'. "
                "Set soil.soil_key_col in config."
            )

        missing_req = _REQUIRED_COLS - set(df.columns)
        if missing_req:
            qa.append(QACheck(
                name="soil_missing_required_cols",
                status="fail",
                message="Soil table missing required SWAT columns: " + ", ".join(sorted(missing_req)),
                context={"missing": sorted(missing_req)},
            ))

        missing_rec = _RECOMMENDED_LAYER1 - set(df.columns)
        if missing_rec:
            qa.append(QACheck(
                name="soil_missing_layer1_cols",
                status="warn",
                message="Soil table missing recommended layer-1 columns: " + ", ".join(sorted(missing_rec)),
                context={"missing": sorted(missing_rec)},
            ))

        if "HYDGRP" in df.columns:
            invalid_grp = set(df["HYDGRP"].dropna().unique()) - _VALID_HYDGRP
            if invalid_grp:
                qa.append(QACheck(
                    name="soil_invalid_hydgrp",
                    status="warn",
                    message="Unexpected HYDGRP values: " + str(sorted(invalid_grp)),
                    context={"values": sorted(invalid_grp)},
                ))

        qa.append(QACheck(
            name="soil_table_loaded",
            status="pass",
            message=str(len(df)) + " soil record(s) loaded from " + cfg.table.name,
        ))
        return df

    def _read_raster_codes(self, qa: list[QACheck]) -> set | None:
        if not _HAS_RASTERIO:
            qa.append(QACheck(
                name="rasterio_missing",
                status="warn",
                message=(
                    "rasterio not installed -- soil raster code extraction skipped. "
                    "Install swatprep[geo] to enable cross-check."
                ),
            ))
            return None

        try:
            with rasterio.open(self.cfg.raster) as ds:
                window = resolve_window(ds, self.boundary, qa, "soil")
                codes = unique_codes(ds, window=window)
                self._windowed = window is not None
        except Exception as exc:
            qa.append(QACheck(
                name="soil_raster_read_failed",
                status="fail",
                message="Could not read soil raster: " + str(self.cfg.raster),
                context={"path": str(self.cfg.raster), "error": str(exc)},
            ))
            return None

        qa.append(QACheck(
            name="soil_raster_read",
            status="pass",
            message=str(len(codes)) + " unique soil code(s) found in raster",
        ))
        return codes

    def _cross_check(
        self,
        table: pd.DataFrame,
        raster_codes: set | None,
        qa: list[QACheck],
    ) -> set:
        if raster_codes is None:
            return set()

        cfg = self.cfg
        known_codes = set(
            pd.to_numeric(table[cfg.soil_key_col], errors="coerce").dropna().astype(int).tolist()
        )
        unmatched = raster_codes - known_codes

        if unmatched:
            top10 = str(sorted(unmatched)[:10])
            qa.append(QACheck(
                name="soil_unmatched_codes",
                status="fail",
                message=(
                    str(len(unmatched)) + " raster soil code(s) have no entry in the "
                    "soil table (first 10): " + top10
                ),
                context={"unmatched_count": len(unmatched), "sample": sorted(unmatched)[:10]},
            ))
        else:
            qa.append(QACheck(
                name="soil_cross_check",
                status="pass",
                message="All raster soil codes are present in the soil table.",
            ))

        return unmatched
