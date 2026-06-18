"""SoilWriter: write validated usersoil.csv and soil raster codes to the output package.

The preprocessor does not reformat the soil table — it validates and packages
the input CSV as-is so that it can be imported into SWAT+ via the ArcSWAT /
SWAT+ Editor soil database import workflow.

Reference: Neitsch, S.L. et al. (2011). SWAT Input/Output File Documentation,
Version 2009. Texas Water Resources Institute Technical Report 365.
"""

from __future__ import annotations

from pathlib import Path

from ..core.soil import SoilResult


class SoilWriter:
    """Write usersoil.csv and companion files to the output directory."""

    def __init__(self, result: SoilResult, output_dir: Path) -> None:
        self.result = result
        self.output_dir = output_dir

    def write(self) -> list[Path]:
        out = self.output_dir
        out.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []

        # Validated soil table → usersoil.csv (SWAT convention)
        usersoil_path = out / "usersoil.csv"
        self.result.soil_table.to_csv(usersoil_path, index=False)
        written.append(usersoil_path)

        # Raster codes summary (if available)
        if self.result.raster_codes is not None:
            import pandas as pd
            codes_path = out / "soil_raster_codes.csv"
            pd.DataFrame(
                sorted(self.result.raster_codes), columns=["raster_code"]
            ).to_csv(codes_path, index=False)
            written.append(codes_path)

        return written
