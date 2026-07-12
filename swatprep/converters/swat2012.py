"""SWAT 2012 station file converters: PCPConverter and TmpConverter.

Both converters share the same master-file lookup, case-insensitive file
discovery, SWAT Classic format detection, and output header structure.
They differ only in how daily values are read and written:

  PCPConverter  — single value per line  (.pcp)
  TmpConverter  — tmax + tmin per line   (.tmp)

SWAT 2012 file format (Arnold et al., 2012):
    Line 1:  station name (title)
    Line 2:  Lati   XX.XXX
    Line 3:  Long   XXX.XXX
    Line 4:  Elev   XXXX.XXX
    Line 5:  YYYYMMDD  (date of first data entry)
    Line 6+: daily value(s) at %10.3f per value

Usage:
    from swatprep.converters import PCPConverter, TmpConverter
    from pathlib import Path

    pcp = PCPConverter(
        master_path=Path("master_pcp.txt"),
        data_dir=Path("raw/"),
        out_dir=Path("swat_pcp/"),
    ).convert()

    tmp = TmpConverter(
        master_path=Path("master_tmp.txt"),
        data_dir=Path("raw_tmp/"),
        out_dir=Path("swat_tmp/"),
    ).convert()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..errors import InputValidationError
from ..qa import QACheck


# ---------------------------------------------------------------------------
# Unified result types
# ---------------------------------------------------------------------------


@dataclass
class StationResult:
    """Per-station conversion outcome — shared by PCPConverter and TmpConverter."""
    name: str        # e.g. "pcp_ANKHE"
    station: str     # e.g. "ANKHE"
    lat: float
    lon: float
    elev: float
    out_path: Path | None
    n_days: int
    qa: list[QACheck] = field(default_factory=list)


@dataclass
class SWAT2012ConvertResult:
    """Aggregate result — shared by PCPConverter and TmpConverter."""
    stations: list[StationResult]
    files_written: list[Path]
    unmatched: list[str]          # NAME entries with no matching raw file
    qa: list[QACheck] = field(default_factory=list)


# Backward-compatible aliases (older code may reference these names)
PCPStationResult = StationResult
TmpStationResult = StationResult
PCPConvertResult = SWAT2012ConvertResult
TmpConvertResult = SWAT2012ConvertResult


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class _BaseStationConverter(ABC):
    """Shared logic for per-station SWAT 2012 file converters.

    Subclasses must implement:
      - _tag      (property) — short prefix for QA names, e.g. "pcp" / "tmp"
      - _write_station()    — read raw file and write one SWAT 2012 output file
    """

    def __init__(
        self,
        master_path: Path,
        data_dir: Path,
        out_dir: Path,
        name_col: str = "NAME",
        lat_col: str = "LAT",
        lon_col: str = "LONG",
        elev_col: str = "ELEVATION",
        name_prefix: str = "",
        raw_prefix: str = "",
        raw_suffix: str = ".txt",
        no_data_value: float = -99.0,
    ) -> None:
        self.master_path = Path(master_path)
        self.data_dir = Path(data_dir)
        self.out_dir = Path(out_dir)
        self.name_col = name_col
        self.lat_col = lat_col
        self.lon_col = lon_col
        self.elev_col = elev_col
        self.name_prefix = name_prefix
        self.raw_prefix = raw_prefix
        self.raw_suffix = raw_suffix
        self.no_data_value = no_data_value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self) -> SWAT2012ConvertResult:
        """Process all stations in master file and write SWAT 2012 output files."""
        qa: list[QACheck] = []
        master = self._read_master(qa)
        self.out_dir.mkdir(parents=True, exist_ok=True)

        station_results: list[StationResult] = []
        files_written: list[Path] = []
        unmatched: list[str] = []

        for _, row in master.iterrows():
            name = str(row[self.name_col]).strip()
            station = name[len(self.name_prefix):] if name.startswith(self.name_prefix) else name
            lat = float(row[self.lat_col])
            lon = float(row[self.lon_col])
            elev = float(row[self.elev_col])

            raw_file = self._find_raw_file(station)

            if raw_file is None:
                unmatched.append(name)
                station_results.append(StationResult(
                    name=name, station=station, lat=lat, lon=lon, elev=elev,
                    out_path=None, n_days=0,
                    qa=[QACheck(
                        name=f"{self._tag}:{name}:missing_raw",
                        status="warn",
                        message=(
                            f"{name}: raw file not found "
                            f"({self.raw_prefix}{station}{self.raw_suffix})"
                        ),
                    )],
                ))
                continue

            out_path, s_qa, n_days = self._write_station(name, station, lat, lon, elev, raw_file)
            station_results.append(StationResult(
                name=name, station=station, lat=lat, lon=lon, elev=elev,
                out_path=out_path, n_days=n_days, qa=s_qa,
            ))
            if out_path is not None:
                files_written.append(out_path)

        for sr in station_results:
            for c in sr.qa:
                if c.status == "fail":
                    qa.append(c)

        n_ok = len(files_written)
        n_miss = len(unmatched)
        qa.append(QACheck(
            name=f"{self._tag}_converter_done",
            status="pass" if n_miss == 0 else "warn",
            message=(
                f"{type(self).__name__}: {n_ok} station(s) written, "
                f"{n_miss} unmatched."
                + (f" Unmatched: {unmatched[:5]}" if unmatched else "")
            ),
            context={"n_ok": n_ok, "n_unmatched": n_miss, "out_dir": str(self.out_dir)},
        ))
        return SWAT2012ConvertResult(
            stations=station_results,
            files_written=files_written,
            unmatched=unmatched,
            qa=qa,
        )

    # ------------------------------------------------------------------
    # Abstract interface for subclasses
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def _tag(self) -> str:
        """Short prefix for QA check names (e.g. "pcp", "tmp")."""

    @abstractmethod
    def _write_station(
        self,
        name: str,
        station: str,
        lat: float,
        lon: float,
        elev: float,
        raw_file: Path,
    ) -> tuple[Path | None, list[QACheck], int]:
        """Read raw file and write one SWAT 2012 output file.

        Returns:
            (out_path, qa_checks, n_days_written)
        """

    # ------------------------------------------------------------------
    # Shared internals
    # ------------------------------------------------------------------

    def _find_raw_file(self, station: str) -> Path | None:
        """Locate raw data file for station, case-insensitively."""
        exact = self.data_dir / f"{self.raw_prefix}{station}{self.raw_suffix}"
        if exact.exists():
            return exact
        target = f"{self.raw_prefix}{station}{self.raw_suffix}".lower()
        for candidate in self.data_dir.iterdir():
            if candidate.name.lower() == target:
                return candidate
        return None

    @staticmethod
    def _is_swat_format(raw_file: Path) -> bool:
        """Return True if file starts with an 8-digit YYYYMMDD date (SWAT Classic input)."""
        try:
            first_line = raw_file.open().readline().strip()
            return len(first_line) == 8 and first_line.isdigit()
        except OSError:
            return False

    def _read_master(self, qa: list[QACheck]) -> pd.DataFrame:
        if not self.master_path.exists():
            raise InputValidationError(f"master_path not found: {self.master_path}")
        df = pd.read_csv(self.master_path)
        required = {self.name_col, self.lat_col, self.lon_col, self.elev_col}
        missing_cols = required - set(df.columns)
        if missing_cols:
            raise InputValidationError(
                f"master file missing columns: {missing_cols}. Found: {list(df.columns)}"
            )
        qa.append(QACheck(
            name=f"{self._tag}_master_read",
            status="pass",
            message=f"Master loaded: {len(df)} station(s) from {self.master_path.name}",
        ))
        return df

    @staticmethod
    def _swat_header(name: str, lat: float, lon: float, elev: float) -> list[str]:
        """Return 4-line SWAT Classic header."""
        return [
            name,
            f"Lati{lat:12.3f}",
            f"Long{lon:12.3f}",
            f"Elev{elev:12.3f}",
        ]


# ---------------------------------------------------------------------------
# PCPConverter
# ---------------------------------------------------------------------------


class PCPConverter(_BaseStationConverter):
    """Convert raw precipitation files + master metadata to SWAT 2012 .pcp files.

    Matching logic:
        master NAME "pcp_ANKHE"  →  raw file "R_ANKHE.day"  →  output "pcp_ANKHE.pcp"

    Input formats auto-detected:
        SWAT Classic: line 1 = YYYYMMDD, subsequent lines = daily float values.
        CSV: columns date + value_col (default "Rain").

    Args:
        master_path:   Path to master CSV (ID, NAME, LAT, LONG, ELEVATION).
        data_dir:      Directory containing raw precipitation files.
        out_dir:       Directory where .pcp output files will be written.
        name_col:      Column for station names in master (default "NAME").
        lat_col:       Column for latitude (default "LAT").
        lon_col:       Column for longitude (default "LONG").
        elev_col:      Column for elevation in metres (default "ELEVATION").
        name_prefix:   Prefix to strip from NAME to derive station code (default "pcp_").
        raw_prefix:    Prefix for raw data files (default "R_").
        raw_suffix:    Suffix for raw data files (default ".day").
        date_col:      Date column name in CSV files (default "date").
        value_col:     Value column name in CSV files (default "Rain").
        out_suffix:    Output file suffix (default ".pcp").
        no_data_value: SWAT no-data marker (default -99.0).
    """

    def __init__(
        self,
        master_path: Path,
        data_dir: Path,
        out_dir: Path,
        name_col: str = "NAME",
        lat_col: str = "LAT",
        lon_col: str = "LONG",
        elev_col: str = "ELEVATION",
        name_prefix: str = "pcp_",
        raw_prefix: str = "R_",
        raw_suffix: str = ".day",
        date_col: str = "date",
        value_col: str = "Rain",
        out_suffix: str = ".pcp",
        no_data_value: float = -99.0,
    ) -> None:
        super().__init__(
            master_path=master_path,
            data_dir=data_dir,
            out_dir=out_dir,
            name_col=name_col,
            lat_col=lat_col,
            lon_col=lon_col,
            elev_col=elev_col,
            name_prefix=name_prefix,
            raw_prefix=raw_prefix,
            raw_suffix=raw_suffix,
            no_data_value=no_data_value,
        )
        self.date_col = date_col
        self.value_col = value_col
        self.out_suffix = out_suffix

    @property
    def _tag(self) -> str:
        return "pcp"

    def _write_station(
        self, name: str, station: str, lat: float, lon: float, elev: float, raw_file: Path
    ) -> tuple[Path | None, list[QACheck], int]:
        qa: list[QACheck] = []
        try:
            if self._is_swat_format(raw_file):
                df = self._read_swat_pcp(raw_file)
                qa.append(QACheck(
                    name=f"pcp:{name}:swat_input",
                    status="pass",
                    message=f"{raw_file.name}: detected SWAT Classic input format.",
                ))
            else:
                df = pd.read_csv(raw_file, parse_dates=[self.date_col])
        except Exception as exc:
            qa.append(QACheck(
                name=f"pcp:{name}:read_error",
                status="fail",
                message=f"Could not read {raw_file.name}: {exc}",
            ))
            return None, qa, 0

        # Resolve value column: prefer configured name, fall back to first non-date column
        if self.value_col in df.columns:
            val_col = self.value_col
        else:
            data_cols = [c for c in df.columns if c != self.date_col]
            if not data_cols:
                qa.append(QACheck(
                    name=f"pcp:{name}:no_value_col",
                    status="fail",
                    message=f"{raw_file.name}: no data column found.",
                ))
                return None, qa, 0
            val_col = data_cols[0]
            qa.append(QACheck(
                name=f"pcp:{name}:col_fallback",
                status="warn",
                message=f"Column '{self.value_col}' not found; using '{val_col}' instead.",
            ))

        df = df.sort_values(self.date_col)
        first_date = df[self.date_col].iloc[0]

        lines = self._swat_header(name, lat, lon, elev)
        lines.append(first_date.strftime("%Y%m%d"))
        values = df[val_col].fillna(self.no_data_value)
        lines.extend(f"{v:10.3f}" for v in values)

        out_path = self.out_dir / f"{name}{self.out_suffix}"
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        n_days = len(df)
        qa.append(QACheck(
            name=f"pcp:{name}:ok",
            status="pass",
            message=(
                f"{name}: {n_days} days written "
                f"({first_date.date()} -- {df[self.date_col].iloc[-1].date()})"
            ),
            context={"station": name, "n_days": n_days, "lat": lat, "lon": lon, "elev": elev},
        ))
        return out_path, qa, n_days

    def _read_swat_pcp(self, raw_file: Path) -> pd.DataFrame:
        """Read SWAT Classic precipitation input: line 1 = YYYYMMDD, rest = float."""
        lines = raw_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        start_date = pd.to_datetime(lines[0].strip(), format="%Y%m%d")
        values = []
        for ln in lines[1:]:
            ln = ln.strip()
            if ln:
                try:
                    values.append(float(ln))
                except ValueError:
                    values.append(float("nan"))
        dates = pd.date_range(start=start_date, periods=len(values), freq="D")
        return pd.DataFrame({"date": dates, self.value_col: values})


# ---------------------------------------------------------------------------
# TmpConverter
# ---------------------------------------------------------------------------


class TmpConverter(_BaseStationConverter):
    """Convert raw temperature files + master metadata to SWAT 2012 .tmp files.

    Matching logic:
        master NAME "tmp_ANKHE"  →  raw file "tmp_ANKHE.txt"  →  output "tmp_ANKHE.tmp"

    Input formats auto-detected:
        SWAT Classic: line 1 = YYYYMMDD, rest = "val1,val2" per line.
        CSV: columns date + tmax_col + tmin_col.

    Args:
        master_path:   Path to master CSV (ID, NAME, LAT, LONG, ELEVATION).
        data_dir:      Directory containing raw temperature files.
        out_dir:       Directory where .tmp output files will be written.
        name_col:      Column for station names in master (default "NAME").
        lat_col:       Column for latitude (default "LAT").
        lon_col:       Column for longitude (default "LONG").
        elev_col:      Column for elevation in metres (default "ELEVATION").
        name_prefix:   Prefix to strip from NAME (default "tmp_").
        raw_prefix:    Prefix for raw temperature files (default "tmp_").
        raw_suffix:    Suffix for raw temperature files (default ".txt").
        tmin_first:    If True (default), SWAT Classic input columns are tmin,tmax.
        tmax_col:      Column name for tmax in CSV input (default "tmax").
        tmin_col:      Column name for tmin in CSV input (default "tmin").
        date_col:      Date column name in CSV input (default "date").
        out_suffix:    Output file suffix (default ".tmp").
        no_data_value: SWAT no-data marker (default -99.0).
        separator:     Separator between two values in SWAT Classic input (default ",").
    """

    def __init__(
        self,
        master_path: Path,
        data_dir: Path,
        out_dir: Path,
        name_col: str = "NAME",
        lat_col: str = "LAT",
        lon_col: str = "LONG",
        elev_col: str = "ELEVATION",
        name_prefix: str = "tmp_",
        raw_prefix: str = "tmp_",
        raw_suffix: str = ".txt",
        tmin_first: bool = True,
        tmax_col: str = "tmax",
        tmin_col: str = "tmin",
        date_col: str = "date",
        out_suffix: str = ".tmp",
        no_data_value: float = -99.0,
        separator: str = ",",
    ) -> None:
        super().__init__(
            master_path=master_path,
            data_dir=data_dir,
            out_dir=out_dir,
            name_col=name_col,
            lat_col=lat_col,
            lon_col=lon_col,
            elev_col=elev_col,
            name_prefix=name_prefix,
            raw_prefix=raw_prefix,
            raw_suffix=raw_suffix,
            no_data_value=no_data_value,
        )
        self.tmin_first = tmin_first
        self.tmax_col = tmax_col
        self.tmin_col = tmin_col
        self.date_col = date_col
        self.out_suffix = out_suffix
        self.separator = separator

    @property
    def _tag(self) -> str:
        return "tmp"

    def _write_station(
        self, name: str, station: str, lat: float, lon: float, elev: float, raw_file: Path
    ) -> tuple[Path | None, list[QACheck], int]:
        qa: list[QACheck] = []
        try:
            if self._is_swat_format(raw_file):
                df = self._read_swat_tmp(raw_file)
                qa.append(QACheck(
                    name=f"tmp:{name}:swat_input",
                    status="pass",
                    message=(
                        f"{raw_file.name}: detected SWAT Classic input "
                        f"(tmin_first={self.tmin_first})."
                    ),
                ))
            else:
                df = pd.read_csv(raw_file, parse_dates=[self.date_col])
        except Exception as exc:
            qa.append(QACheck(
                name=f"tmp:{name}:read_error",
                status="fail",
                message=f"Could not read {raw_file.name}: {exc}",
            ))
            return None, qa, 0

        if self.tmax_col not in df.columns or self.tmin_col not in df.columns:
            qa.append(QACheck(
                name=f"tmp:{name}:missing_cols",
                status="fail",
                message=(
                    f"{raw_file.name}: columns '{self.tmax_col}'/'{self.tmin_col}' not found. "
                    f"Available: {list(df.columns)}"
                ),
            ))
            return None, qa, 0

        df = df.sort_values(self.date_col)
        first_date = df[self.date_col].iloc[0]

        lines = self._swat_header(name, lat, lon, elev)
        lines.append(first_date.strftime("%Y%m%d"))
        tmax_arr = df[self.tmax_col].fillna(self.no_data_value)
        tmin_arr = df[self.tmin_col].fillna(self.no_data_value)
        lines.extend(f"{tx:10.3f}{tn:10.3f}" for tx, tn in zip(tmax_arr, tmin_arr))

        out_path = self.out_dir / f"{name}{self.out_suffix}"
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        n_days = len(df)
        qa.append(QACheck(
            name=f"tmp:{name}:ok",
            status="pass",
            message=(
                f"{name}: {n_days} days written "
                f"({first_date.date()} -- {df[self.date_col].iloc[-1].date()})"
            ),
            context={"station": name, "n_days": n_days},
        ))
        return out_path, qa, n_days

    def _read_swat_tmp(self, raw_file: Path) -> pd.DataFrame:
        """Read SWAT Classic temp input: line 1 = YYYYMMDD, rest = val1,val2 per line."""
        lines = raw_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        start_date = pd.to_datetime(lines[0].strip(), format="%Y%m%d")
        tmax_vals, tmin_vals = [], []
        for ln in lines[1:]:
            ln = ln.strip()
            if not ln:
                continue
            parts = ln.split(self.separator)
            if len(parts) >= 2:
                try:
                    v1, v2 = float(parts[0].strip()), float(parts[1].strip())
                except ValueError:
                    v1 = v2 = float("nan")
                if self.tmin_first:
                    tmin_vals.append(v1)
                    tmax_vals.append(v2)
                else:
                    tmax_vals.append(v1)
                    tmin_vals.append(v2)
            else:
                tmax_vals.append(float("nan"))
                tmin_vals.append(float("nan"))

        n = min(len(tmax_vals), len(tmin_vals))
        dates = pd.date_range(start=start_date, periods=n, freq="D")
        return pd.DataFrame({"date": dates, "tmax": tmax_vals[:n], "tmin": tmin_vals[:n]})
