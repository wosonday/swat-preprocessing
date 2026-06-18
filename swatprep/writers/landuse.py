"""LandUseWriter: write land-use lookup and raster code summary."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..core.landuse import LandUseResult


class LandUseWriter:
    """Write land-use preprocessor outputs to *output_dir/landuse/*."""

    def __init__(self, result: LandUseResult, output_dir: Path) -> None:
        self.result = result
        self.output_dir = output_dir / "landuse"

    def write(self) -> list[Path]:
        """Write all land-use output files and return their paths."""
        out = self.output_dir
        out.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []

        # Validated lookup table
        lookup_path = out / "landuse_lookup.csv"
        self.result.lookup.to_csv(lookup_path, index=False)
        written.append(lookup_path)

        # Raster codes summary (if available)
        if self.result.raster_codes is not None:
            codes_path = out / "landuse_raster_codes.csv"
            pd.DataFrame(
                sorted(self.result.raster_codes), columns=["raster_code"]
            ).to_csv(codes_path, index=False)
            written.append(codes_path)

            # Unmatched codes (if any)
            if self.result.unmatched_codes:
                unmatched_path = out / "landuse_unmatched_codes.csv"
                pd.DataFrame(
                    sorted(self.result.unmatched_codes), columns=["unmatched_raster_code"]
                ).to_csv(unmatched_path, index=False)
                written.append(unmatched_path)

        return written
