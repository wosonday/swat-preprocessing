"""SoilWriter: write validated usersoil.csv and soil raster codes to the output package.

By default (soil.usersoil_format: swat) usersoil.csv uses the 152-column SWAT+ layout of
the SWAT+ Editor example file; with "raw" the input table is written unchanged.

Reference: Neitsch, S.L. et al. (2011). SWAT Input/Output File Documentation,
Version 2009. Texas Water Resources Institute Technical Report 365.
"""

from __future__ import annotations

from pathlib import Path

from ..core.soil import SoilResult


class SoilWriter:
    """Write usersoil.csv and companion files to the output directory."""

    def __init__(self, result: SoilResult, output_dir: Path,
                 targets: list[str] | None = None) -> None:
        self.result = result
        self.output_dir = output_dir
        self.targets = set(targets or ["swatplus"])

    def write(self) -> list[Path]:
        out = self.output_dir
        out.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []

        # Validated soil table → usersoil.csv (SWAT convention)
        usersoil_path = out / "usersoil.csv"
        table = self.result.usersoil if self.result.usersoil is not None else self.result.soil_table
        table.to_csv(usersoil_path, index=False, float_format="%.10g")
        written.append(usersoil_path)

        # Output headers follow the selected model; keep processor data unchanged.
        if self.result.vlookup is not None:
            vl_path = out / "soil_vlookup.csv"
            key = "SOIL_ID" if "swatplus" in self.targets else "SEQN"
            self.result.vlookup.rename(columns={"SOIL_ID": key}).to_csv(vl_path, index=False)
            written.append(vl_path)
            if {"swat", "swatplus"} <= self.targets:
                classic_path = out / "soil_vlookup_swat.csv"
                self.result.vlookup.rename(columns={"SOIL_ID": "SEQN"}).to_csv(
                    classic_path, index=False)
                written.append(classic_path)

        # Raster codes summary (if available)
        if self.result.raster_codes is not None:
            import pandas as pd
            codes_path = out / "soil_raster_codes.csv"
            pd.DataFrame(
                sorted(self.result.raster_codes), columns=["raster_code"]
            ).to_csv(codes_path, index=False)
            written.append(codes_path)

        return written
