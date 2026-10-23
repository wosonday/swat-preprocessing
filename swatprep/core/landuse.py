"""LandUsePreprocessor: validate lookup table and cross-check with raster values.

rasterio is optional (swatprep[geo]). When not installed, the raster cross-check
is skipped with a warn QA check; lookup table validation still runs fully.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..config import LandUseConfig
from ..errors import InputValidationError
from ..qa import QACheck
from ..utils.raster import resolve_window, unique_codes
from .clip import basin_rows

try:
    import rasterio  # type: ignore
    _HAS_RASTERIO = True
except ImportError:
    _HAS_RASTERIO = False


@dataclass
class LandUseResult:
    """Output of LandUsePreprocessor.run()."""

    raster_path: Path
    lookup: pd.DataFrame
    raster_codes: set | None
    code_mapping: dict[int, int]
    unmatched_codes: set
    qa: list[QACheck] = field(default_factory=list)
    vlookup: pd.DataFrame | None = None  # LANDUSE_ID, SWAT_CODE (QSWAT / QSWAT+ lookup table)


class LandUsePreprocessor:
    """Validate land-use lookup table and cross-check unique raster codes."""

    def __init__(self, cfg: LandUseConfig, boundary: Path | None = None) -> None:
        self.cfg = cfg
        self.boundary = boundary  # project.boundary: codes read only inside its window
        self._windowed = False  # True once the boundary window was actually applied

    def run(self) -> LandUseResult:
        qa: list[QACheck] = []
        lookup = self._load_lookup(qa)
        raster_codes = self._read_raster_codes(qa)
        unmatched = self._cross_check(lookup, raster_codes, qa)
        mapping = _build_class_id_mapping(lookup, self.cfg.source_code_col)  # ids of the full table
        if self._windowed and raster_codes:
            lookup = basin_rows(lookup, self.cfg.source_code_col, raster_codes, "landuse", qa)
        return LandUseResult(
            raster_path=self.cfg.raster,
            lookup=lookup,
            raster_codes=raster_codes,
            code_mapping=mapping,
            unmatched_codes=unmatched,
            qa=qa,
            vlookup=self._vlookup(lookup, qa) if self.cfg.output_lookup else None,
        )

    def _vlookup(self, lookup: pd.DataFrame, qa: list[QACheck]) -> pd.DataFrame:
        """Two-column table raster value -> SWAT land-use code (one row per value, sorted)."""
        cfg = self.cfg
        df = lookup[[cfg.source_code_col, cfg.swat_code_col]].dropna()
        df.columns = ["LANDUSE_ID", "SWAT_CODE"]
        df = df.drop_duplicates("LANDUSE_ID").astype({"LANDUSE_ID": int})
        df = df.sort_values("LANDUSE_ID").reset_index(drop=True)
        qa.append(QACheck(
            name="landuse_vlookup", status="pass",
            message=f"land-use VLOOKUP table: {len(df)} row(s) (LANDUSE_ID -> SWAT_CODE)",
        ))
        return df

    def _load_lookup(self, qa: list[QACheck]) -> pd.DataFrame:
        cfg = self.cfg
        df = pd.read_csv(cfg.lookup)

        required = {cfg.source_code_col, cfg.swat_code_col, cfg.swat_name_col}
        missing = required - set(df.columns)
        if missing:
            raise InputValidationError(
                "Land-use lookup CSV missing columns: " + ", ".join(sorted(missing))
            )

        df[cfg.source_code_col] = pd.to_numeric(
            df[cfg.source_code_col], errors="coerce"
        ).astype("Int64")

        duplicates = int(df[cfg.source_code_col].duplicated().sum())
        if duplicates:
            qa.append(QACheck(
                name="landuse_lookup_duplicates",
                status="warn",
                message=str(duplicates) + " duplicate source code(s) in lookup table",
                context={"count": duplicates},
            ))

        qa.append(QACheck(
            name="landuse_lookup_loaded",
            status="pass",
            message=str(len(df)) + " land-use class(es) loaded from " + cfg.lookup.name,
        ))
        return df

    def _read_raster_codes(self, qa: list[QACheck]) -> set | None:
        if not _HAS_RASTERIO:
            qa.append(QACheck(
                name="rasterio_missing",
                status="warn",
                message=(
                    "rasterio not installed -- raster code extraction skipped. "
                    "Install swatprep[geo] to enable cross-check."
                ),
            ))
            return None

        try:
            with rasterio.open(self.cfg.raster) as ds:
                window = resolve_window(ds, self.boundary, qa, "landuse")
                codes = unique_codes(ds, window=window)
                self._windowed = window is not None
        except Exception as exc:
            qa.append(QACheck(
                name="landuse_raster_read_failed",
                status="fail",
                message="Could not read land-use raster: " + str(self.cfg.raster),
                context={"path": str(self.cfg.raster), "error": str(exc)},
            ))
            return None

        qa.append(QACheck(
            name="landuse_raster_read",
            status="pass",
            message=str(len(codes)) + " unique land-use code(s) found in raster",
        ))
        return codes

    def _cross_check(
        self,
        lookup: pd.DataFrame,
        raster_codes: set | None,
        qa: list[QACheck],
    ) -> set:
        if raster_codes is None:
            return set()

        known_codes = set(
            lookup[self.cfg.source_code_col].dropna().astype(int).tolist()
        )
        unmatched = raster_codes - known_codes

        if unmatched:
            top10 = str(sorted(unmatched)[:10])
            qa.append(QACheck(
                name="landuse_unmatched_codes",
                status="fail",
                message=(
                    str(len(unmatched)) + " raster land-use code(s) have no entry in "
                    "the lookup table (first 10): " + top10
                ),
                context={"unmatched_count": len(unmatched), "sample": sorted(unmatched)[:10]},
            ))
        else:
            qa.append(QACheck(
                name="landuse_cross_check",
                status="pass",
                message="All raster land-use codes are present in the lookup table.",
            ))

        return unmatched


def _build_class_id_mapping(lookup: "pd.DataFrame", source_code_col: str) -> "dict[int, int]":
    """Map source raster code → sequential 1-based SWAT class ID."""
    mapping: dict[int, int] = {}
    class_id = 1
    for code in lookup[source_code_col].dropna():
        try:
            key = int(code)
        except (ValueError, TypeError):
            continue
        if key not in mapping:
            mapping[key] = class_id
            class_id += 1
    return mapping
