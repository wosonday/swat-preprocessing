"""DayFilesConverter: convert Vietnamese per-variable .day files to swatprep
per-station CSV format.

Input layout (typical Vietnamese meteorological data):
    data_dir/
        R_{STATION}.day      -- daily precipitation; cols: date, Rain
        Tx_{STATION}.day     -- daily Tmax;          cols: date, Tmax
        Tm_{STATION}.day     -- daily Tmin;          cols: date, Tmin

Output layout (swatprep WeatherPreprocessor expects):
    out_dir/
        {STATION}.csv        -- cols: date, precip, tmax, tmin

Usage:
    from swatprep.converters import DayFilesConverter
    from pathlib import Path

    conv = DayFilesConverter(
        data_dir=Path("data/weather/"),
        out_dir=Path("data/weather/converted/"),
    )
    result = conv.convert()
    print(result.stations_found)   # {"STATION01", "STATION02", ...}
    print(result.files_written)    # [Path("..."), ...]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..errors import InputValidationError
from ..qa import QACheck


# Default mapping: file prefix -> internal variable name -> output column name
_DEFAULT_PREFIXES: dict[str, tuple[str, str]] = {
    "R_":  ("Rain",  "precip"),
    "Tx_": ("Tmax",  "tmax"),
    "Tm_": ("Tmin",  "tmin"),
}
_DEFAULT_SUFFIX = ".day"


@dataclass
class ConvertResult:
    """Result of DayFilesConverter.convert()."""
    stations_found: set[str]
    files_written: list[Path]
    qa: list[QACheck] = field(default_factory=list)


class DayFilesConverter:
    """Merge per-variable .day files into per-station CSV files.

    Each output CSV has columns: date, precip, tmax, tmin
    (only the variables present in data_dir are included).
    """

    def __init__(
        self,
        data_dir: Path,
        out_dir: Path,
        prefixes: dict[str, tuple[str, str]] | None = None,
        suffix: str = _DEFAULT_SUFFIX,
        date_col: str = "date",
    ) -> None:
        """
        Args:
            data_dir:  Directory containing {PREFIX}{STATION}{suffix} files.
            out_dir:   Directory where {STATION}.csv files will be written.
            prefixes:  Mapping of file prefix to (source_col, target_col).
                       Defaults to {"R_": ("Rain","precip"),
                                    "Tx_": ("Tmax","tmax"),
                                    "Tm_": ("Tmin","tmin")}.
            suffix:    File extension (default ".day").
            date_col:  Name of the date column in source files.
        """
        self.data_dir = Path(data_dir)
        self.out_dir = Path(out_dir)
        self.prefixes = prefixes or _DEFAULT_PREFIXES
        self.suffix = suffix
        self.date_col = date_col

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self) -> ConvertResult:
        """Scan data_dir and write merged per-station CSV files.

        Returns:
            ConvertResult with stations_found, files_written, qa checks.
        """
        qa: list[QACheck] = []

        if not self.data_dir.exists():
            raise InputValidationError(f"data_dir does not exist: {self.data_dir}")

        # Discover all station names across all variable prefixes
        station_vars = self._discover_stations()
        if not station_vars:
            raise InputValidationError(
                f"No .day files found in {self.data_dir} with prefixes "
                f"{list(self.prefixes.keys())} and suffix '{self.suffix}'"
            )

        self.out_dir.mkdir(parents=True, exist_ok=True)
        files_written: list[Path] = []

        for station, var_files in sorted(station_vars.items()):
            out_path, station_qa = self._merge_station(station, var_files)
            qa.extend(station_qa)
            if out_path is not None:
                files_written.append(out_path)

        qa.append(QACheck(
            name="converter_done",
            status="pass",
            message=(
                f"Converted {len(files_written)} station(s) to {self.out_dir}. "
                f"Variables detected: {sorted({v for vf in station_vars.values() for v in vf})}"
            ),
        ))

        return ConvertResult(
            stations_found=set(station_vars.keys()),
            files_written=files_written,
            qa=qa,
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover_stations(self) -> dict[str, dict[str, tuple[Path, str]]]:
        """Return {station: {target_col: (file_path, source_col)}} for all files found."""
        station_vars: dict[str, dict[str, tuple[Path, str]]] = {}

        for prefix, (src_col, tgt_col) in self.prefixes.items():
            pattern = f"{prefix}*{self.suffix}"
            for fpath in sorted(self.data_dir.glob(pattern)):
                # station name = filename minus prefix and suffix
                stem = fpath.stem          # e.g. "R_STATION01"
                station = stem[len(prefix):]  # e.g. "STATION01"
                if station not in station_vars:
                    station_vars[station] = {}
                station_vars[station][tgt_col] = (fpath, src_col)

        return station_vars

    # ------------------------------------------------------------------
    # Per-station merge
    # ------------------------------------------------------------------

    def _merge_station(
        self,
        station: str,
        var_files: dict[str, tuple[Path, str]],
    ) -> tuple[Path | None, list[QACheck]]:
        """Load all variable files for a station and join them by date."""
        qa: list[QACheck] = []
        frames: list[pd.DataFrame] = []

        for tgt_col, (fpath, expected_src_col) in sorted(var_files.items()):
            try:
                df = pd.read_csv(
                    fpath,
                    parse_dates=[self.date_col],
                )
                # Use the configured source column name; fall back to first non-date column
                data_cols = [c for c in df.columns if c != self.date_col]
                if not data_cols:
                    qa.append(QACheck(
                        name=f"converter:{station}:{tgt_col}:no_data_col",
                        status="warn",
                        message=f"No data column in {fpath.name} (only '{self.date_col}')",
                    ))
                    continue

                if expected_src_col in df.columns:
                    src_col = expected_src_col
                else:
                    src_col = data_cols[0]
                    qa.append(QACheck(
                        name=f"converter:{station}:{tgt_col}:col_fallback",
                        status="warn",
                        message=(
                            f"{fpath.name}: column '{expected_src_col}' not found; "
                            f"using '{src_col}' instead."
                        ),
                    ))

                sub = df[[self.date_col, src_col]].rename(
                    columns={self.date_col: "date", src_col: tgt_col}
                )
                sub = sub.set_index("date")
                frames.append(sub)

            except Exception as exc:
                qa.append(QACheck(
                    name=f"converter:{station}:{tgt_col}:read_error",
                    status="warn",
                    message=f"Could not read {fpath.name}: {exc}",
                    context={"file": str(fpath), "error": str(exc)},
                ))

        if not frames:
            qa.append(QACheck(
                name=f"converter:{station}:skipped",
                status="warn",
                message=f"Station {station} skipped — no variable files could be loaded.",
            ))
            return None, qa

        # Outer join preserves the full date range of each variable
        merged = frames[0]
        for frame in frames[1:]:
            merged = merged.join(frame, how="outer")

        merged = merged.sort_index()
        merged.index.name = "date"

        # Reorder columns to standard order (only those present)
        col_order = [c for c in ("precip", "tmax", "tmin") if c in merged.columns]
        other_cols = [c for c in merged.columns if c not in col_order]
        merged = merged[col_order + other_cols]

        out_path = self.out_dir / f"{station}.csv"
        merged.reset_index().to_csv(out_path, index=False)
        qa.append(QACheck(
            name=f"converter:{station}:ok",
            status="pass",
            message=f"Merged {len(merged)} rows for station {station!r} -> {out_path.name}",
        ))
        return out_path, qa
