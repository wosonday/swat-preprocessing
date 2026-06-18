"""ObservationWriter: write daily streamflow files for use as observed data.

SWAT Classic uses a reach-output format (.rch) for calibration, but the
most portable approach for preprocessed observed data is a dated CSV that
calibration tools (SWAT-CUP, PEST, etc.) can consume directly.

Output layout
-------------
observed/
    streamflow_{station_id}.csv   — daily observed discharge, one column per run
    streamflow_meta.csv           — station metadata (id, units, date range)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..core.streamflow import StreamflowResult


class ObservationWriter:
    """Write daily streamflow observation files from a StreamflowResult."""

    def __init__(self, result: StreamflowResult, output_dir: Path) -> None:
        self.result = result
        self.output_dir = output_dir

    def write(self) -> list[Path]:
        """Write observation CSVs; return list of created paths."""
        out = self.output_dir
        out.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        wide = self.result.daily
        units = self.result.units

        for sid in wide.columns:
            series = wide[sid].rename("flow_" + units)
            df = series.reset_index()
            df.columns = ["date", f"flow_{units}"]
            p = out / f"streamflow_{sid}.csv"
            df.to_csv(p, index=False, date_format="%Y-%m-%d")
            written.append(p)

        # Metadata summary
        meta_rows = []
        for sid in wide.columns:
            s = wide[sid].dropna()
            meta_rows.append({
                "station_id": sid,
                "units": units,
                "start_date": str(wide.index[0].date()),
                "end_date": str(wide.index[-1].date()),
                "n_days": len(wide),
                "n_valid": int(s.count()),
                "mean_flow": round(float(s.mean()), 3) if len(s) else None,
            })
        meta_path = out / "streamflow_meta.csv"
        pd.DataFrame(meta_rows).to_csv(meta_path, index=False)
        written.append(meta_path)

        return written
