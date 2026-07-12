"""StreamflowConverter: convert Vietnamese streamflow data formats to swatprep
long-format CSV.

Supported input formats:

Format A — Per-station files:
    cols: date (ISO YYYY-MM-DD), discharge (m3/s)
    e.g. Q_BA_0001.csv, Q_BA_0002.csv

Format B — Wide format with YYYYMMDD dates:
    cols: date (YYYYMMDD int or str), Q_HT_0001, Q_HT_0002, ... (NA for missing)
    e.g. dailyStreamflow_68gauges.csv

Output (swatprep StreamflowPreprocessor expects):
    long-format CSV: date (YYYY-MM-DD), station_id, flow

Usage:
    from swatprep.converters import StreamflowConverter
    from pathlib import Path

    # Convert wide-format file
    conv = StreamflowConverter(
        source=Path("data/dailyStreamflow_68gauges.csv"),
        input_format="wide_yyyymmdd",
        value_col="flow",
    )
    result = conv.convert(out_path=Path("data/streamflow_long.csv"))

    # Merge multiple per-station files
    conv = StreamflowConverter(
        source=Path("data/streamflow/"),
        input_format="per_station",
        glob_pattern="Q_*.csv",
        date_col="date",
        value_col="discharge",
    )
    result = conv.convert(out_path=Path("data/streamflow_long.csv"))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

from ..errors import InputValidationError
from ..qa import QACheck


@dataclass
class StreamflowConvertResult:
    """Result of StreamflowConverter.convert()."""
    out_path: Path
    n_stations: int
    n_days: int
    stations: list[str]
    qa: list[QACheck] = field(default_factory=list)


class StreamflowConverter:
    """Convert streamflow data to swatprep long-format CSV.

    Args:
        source:        Path to a single CSV file (wide format) OR a directory
                       of per-station files.
        input_format:  "wide_yyyymmdd" or "per_station".
        glob_pattern:  Glob pattern when source is a directory (default "Q_*.csv").
        date_col:      Name of the date column (default "date").
        value_col:     Target name for the flow column in output (default "flow").
        station_id_col: Target name for the station column in output (default "station_id").
        src_value_col: Source column name in per-station files (default "discharge").
        units:         Unit label written to meta (default "m3s").
    """

    def __init__(
        self,
        source: Path,
        input_format: Literal["wide_yyyymmdd", "per_station"] = "wide_yyyymmdd",
        glob_pattern: str = "Q_*.csv",
        date_col: str = "date",
        value_col: str = "flow",
        station_id_col: str = "station_id",
        src_value_col: str = "discharge",
        units: str = "m3s",
    ) -> None:
        self.source = Path(source)
        self.input_format = input_format
        self.glob_pattern = glob_pattern
        self.date_col = date_col
        self.value_col = value_col
        self.station_id_col = station_id_col
        self.src_value_col = src_value_col
        self.units = units

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self, out_path: Path) -> StreamflowConvertResult:
        """Convert to long-format CSV and write to out_path.

        Returns:
            StreamflowConvertResult with metadata and QA checks.
        """
        qa: list[QACheck] = []

        if self.input_format == "wide_yyyymmdd":
            long = self._read_wide_yyyymmdd(qa)
        elif self.input_format == "per_station":
            long = self._read_per_station(qa)
        else:
            raise InputValidationError(
                f"Unknown input_format '{self.input_format}'. "
                "Use 'wide_yyyymmdd' or 'per_station'."
            )

        stations = sorted(long[self.station_id_col].unique().tolist())
        n_days = long[self.date_col].nunique()

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        long.to_csv(out_path, index=False, date_format="%Y-%m-%d")

        qa.append(QACheck(
            name="streamflow_converter_done",
            status="pass",
            message=(
                f"Converted {len(stations)} station(s) × {n_days} days "
                f"to long-format CSV: {out_path.name}"
            ),
            context={"n_stations": len(stations), "n_days": n_days, "units": self.units},
        ))

        return StreamflowConvertResult(
            out_path=out_path,
            n_stations=len(stations),
            n_days=n_days,
            stations=stations,
            qa=qa,
        )

    # ------------------------------------------------------------------
    # Format A: wide YYYYMMDD
    # ------------------------------------------------------------------

    def _read_wide_yyyymmdd(self, qa: list[QACheck]) -> pd.DataFrame:
        """Read wide-format file with YYYYMMDD integer dates and NA strings."""
        if not self.source.is_file():
            raise InputValidationError(
                f"Source file not found: {self.source}"
            )

        df = pd.read_csv(self.source, dtype={self.date_col: str}, na_values=["NA", "N/A", ""])
        if self.date_col not in df.columns:
            raise InputValidationError(
                f"Date column '{self.date_col}' not found in {self.source.name}"
            )

        # Parse YYYYMMDD -> datetime
        df[self.date_col] = pd.to_datetime(
            df[self.date_col].astype(str).str.strip(), format="%Y%m%d", errors="coerce"
        )
        bad_dates = df[self.date_col].isna().sum()
        if bad_dates > 0:
            qa.append(QACheck(
                name="streamflow_bad_dates",
                status="warn",
                message=f"{bad_dates} date(s) could not be parsed and were dropped.",
            ))
            df = df.dropna(subset=[self.date_col])

        station_cols = [c for c in df.columns if c != self.date_col]
        qa.append(QACheck(
            name="streamflow_wide_read",
            status="pass",
            message=f"Wide-format: {len(station_cols)} stations, {len(df)} days",
        ))

        # Melt to long format
        long = df.melt(
            id_vars=[self.date_col],
            value_vars=station_cols,
            var_name=self.station_id_col,
            value_name=self.value_col,
        )
        long = long.rename(columns={self.date_col: self.date_col})
        long = long.sort_values([self.station_id_col, self.date_col]).reset_index(drop=True)
        return long

    # ------------------------------------------------------------------
    # Format B: per-station files
    # ------------------------------------------------------------------

    def _read_per_station(self, qa: list[QACheck]) -> pd.DataFrame:
        """Read directory of per-station CSV files, merge to long format."""
        if self.source.is_file():
            files = [self.source]
        elif self.source.is_dir():
            files = sorted(self.source.glob(self.glob_pattern))
        else:
            raise InputValidationError(
                f"Source path not found: {self.source}"
            )

        if not files:
            raise InputValidationError(
                f"No files matching '{self.glob_pattern}' in {self.source}"
            )

        frames: list[pd.DataFrame] = []
        for fpath in files:
            station_id = fpath.stem   # Q_BA_0001 from Q_BA_0001.csv
            try:
                df = pd.read_csv(fpath, parse_dates=[self.date_col])
                if self.src_value_col not in df.columns:
                    # Try first non-date column as fallback
                    data_cols = [c for c in df.columns if c != self.date_col]
                    if data_cols:
                        df = df.rename(columns={data_cols[0]: self.src_value_col})
                    else:
                        qa.append(QACheck(
                            name=f"streamflow:{station_id}:no_value_col",
                            status="warn",
                            message=f"No value column in {fpath.name}",
                        ))
                        continue

                sub = df[[self.date_col, self.src_value_col]].copy()
                sub[self.station_id_col] = station_id
                sub = sub.rename(columns={
                    self.date_col: self.date_col,
                    self.src_value_col: self.value_col,
                })
                frames.append(sub)
                qa.append(QACheck(
                    name=f"streamflow:{station_id}:ok",
                    status="pass",
                    message=f"{station_id}: {len(df)} rows loaded from {fpath.name}",
                ))
            except Exception as exc:
                qa.append(QACheck(
                    name=f"streamflow:{station_id}:error",
                    status="warn",
                    message=f"Could not read {fpath.name}: {exc}",
                ))

        if not frames:
            raise InputValidationError(
                "No per-station files could be loaded. Check glob_pattern and src_value_col."
            )

        long = pd.concat(frames, ignore_index=True)
        long = long[[self.date_col, self.station_id_col, self.value_col]]
        long = long.sort_values([self.station_id_col, self.date_col]).reset_index(drop=True)
        return long
