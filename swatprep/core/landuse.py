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


class LandUsePreprocessor:
    """Validate land-use lookup table and cross-check unique raster codes."""

    def __init__(self, cfg: LandUseConfig) -> None:
        self.cfg = cfg

    def run(self) -> LandUseResult:
        qa: list[QACheck] = []
        lookup = self._load_lookup(qa)
        raster_codes = self._read_raster_codes(qa)
        unmatched = self._cross_check(lookup, raster_codes, qa)
        return LandUseResult(
            raster_path=self.cfg.raster,
            lookup=lookup,
            raster_codes=raster_codes,
            code_mapping=_build_class_id_mapping(lookup, self.cfg.source_code_col),
            unmatched_codes=unmatched,
            qa=qa,
        )

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

        import numpy as np

        try:
            with rasterio.open(self.cfg.raster) as ds:
                data = ds.read(1)
                nodata = ds.nodata
                if nodata is not None:
                    mask = data != int(nodata)
                else:
                    mask = np.ones_like(data, dtype=bool)
                codes = set(data[mask].flatten().tolist())
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
