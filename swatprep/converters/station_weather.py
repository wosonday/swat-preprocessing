"""StationWeatherConverter: read raw per-station weather files (SWAT Classic
style or CSV) plus station master metadata into a WeatherResult, ready to be
written by WeatherWriter (SWAT2012) or SWATPlusWeatherWriter (SWAT+).

Input layout — SWAT Classic style (matches real vendor exports):
    master_pcp.txt         ID,NAME,LAT,LONG,ELEVATION  (NAME e.g. "pcp_ANKHE")
    pcp_ANKHE.txt           YYYYMMDD header line, one value per line

    master_tmp.txt         ID,NAME,LAT,LONG,ELEVATION  (NAME e.g. "tmp_ANKHE")
    tmp_ANKHE.txt           YYYYMMDD header line, "tmin,tmax" per line

CSV is also auto-detected per station file (columns "date" + the expected
variable column(s)), for stations whose raw data wasn't exported in SWAT
Classic style.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..core.weather import WeatherResult, compute_wgn_stats
from ..errors import InputValidationError
from ..qa import QACheck


class StationWeatherConverter:
    """Read raw SWAT2012-style (or CSV) station weather files into a WeatherResult."""

    def __init__(
        self,
        pcp_master: Path | None = None,
        pcp_dir: Path | None = None,
        tmp_master: Path | None = None,
        tmp_dir: Path | None = None,
        name_col: str = "NAME",
        lat_col: str = "LAT",
        lon_col: str = "LONG",
        elev_col: str = "ELEVATION",
        id_col: str = "ID",
        pcp_name_prefix: str = "pcp_",
        tmp_name_prefix: str = "tmp_",
        pcp_raw_suffix: str = ".txt",
        tmp_raw_suffix: str = ".txt",
        no_data_value: float = -99.0,
    ) -> None:
        if pcp_master is None and tmp_master is None:
            raise InputValidationError(
                "StationWeatherConverter needs at least one of pcp_master or tmp_master."
            )
        if (pcp_master is None) != (pcp_dir is None):
            raise InputValidationError("pcp_master and pcp_dir must be given together.")
        if (tmp_master is None) != (tmp_dir is None):
            raise InputValidationError("tmp_master and tmp_dir must be given together.")

        self.pcp_master = Path(pcp_master) if pcp_master is not None else None
        self.pcp_dir = Path(pcp_dir) if pcp_dir is not None else None
        self.tmp_master = Path(tmp_master) if tmp_master is not None else None
        self.tmp_dir = Path(tmp_dir) if tmp_dir is not None else None
        self.name_col = name_col
        self.lat_col = lat_col
        self.lon_col = lon_col
        self.elev_col = elev_col
        self.id_col = id_col
        self.pcp_name_prefix = pcp_name_prefix
        self.tmp_name_prefix = tmp_name_prefix
        self.pcp_raw_suffix = pcp_raw_suffix
        self.tmp_raw_suffix = tmp_raw_suffix
        self.no_data_value = no_data_value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self) -> WeatherResult:
        qa: list[QACheck] = []
        precip_stations_df: pd.DataFrame | None = None
        temp_stations_df: pd.DataFrame | None = None
        daily: dict[str, pd.DataFrame] = {}

        if self.pcp_master is not None:
            precip_stations_df = self._read_master(self.pcp_master, self.pcp_name_prefix, "precip", qa)
            precip_daily = self._read_group(
                precip_stations_df, self.pcp_dir, self.pcp_name_prefix,
                self.pcp_raw_suffix, ["precip"], "precip", qa,
            )
            daily.update(precip_daily)

        if self.tmp_master is not None:
            temp_stations_df = self._read_master(self.tmp_master, self.tmp_name_prefix, "temperature", qa)
            temp_daily = self._read_group(
                temp_stations_df, self.tmp_dir, self.tmp_name_prefix,
                self.tmp_raw_suffix, ["tmax", "tmin"], "temperature", qa,
            )
            daily.update(temp_daily)

        frames = [df for df in (precip_stations_df, temp_stations_df) if df is not None]
        all_stations = pd.concat(frames)
        all_stations = all_stations[~all_stations.index.duplicated(keep="first")]

        wgn = compute_wgn_stats(all_stations, daily, qa)

        return WeatherResult(
            stations=all_stations,
            precip_stations=precip_stations_df,
            temp_stations=temp_stations_df,
            daily=daily,
            wgn_stats=wgn,
            qa=qa,
        )

    # ------------------------------------------------------------------
    # Master (metadata) reading
    # ------------------------------------------------------------------

    def _read_master(self, path: Path, prefix: str, label: str, qa: list[QACheck]) -> pd.DataFrame:
        if not path.exists():
            raise InputValidationError(f"master file not found: {path}")
        from ..core.weather import station_column

        # headers match without case; LONG/LONGITUDE, LATITUDE and ELEVATION are read as lon, lat and elev
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig", skipinitialspace=True)
        df.columns = [station_column(c) for c in df.columns]
        col = {role: station_column(getattr(self, f"{role}_col")) for role in ("id", "name", "lat", "lon", "elev")}
        missing = set(col.values()) - set(df.columns)
        if missing:
            raise InputValidationError(
                f"master file ({label}) missing columns: {sorted(missing)}. Found: {list(df.columns)}. "
                "Headers may be in any case, e.g. ID,NAME,LAT,LONG,ELEV."
            )

        records = []
        for _, row in df.iterrows():
            full_name = str(row[col["name"]]).strip()
            code = full_name[len(prefix):] if full_name.startswith(prefix) else full_name
            try:
                records.append({
                    "id": str(row[col["id"]]).strip(),
                    "name": code,
                    "lat": float(row[col["lat"]]),
                    "lon": float(row[col["lon"]]),
                    "elev": float(row[col["elev"]]),
                })
            except (TypeError, ValueError) as exc:
                raise InputValidationError(
                    f"master file ({label}): lat, lon and elev must be numbers (station {full_name}): {exc}"
                ) from exc
        out = pd.DataFrame.from_records(records).set_index("id")

        qa.append(QACheck(
            name=f"station_weather:{label}:master_loaded",
            status="pass",
            message=f"{len(out)} station(s) loaded from {path.name} ({label})",
        ))
        return out

    # ------------------------------------------------------------------
    # Raw per-station file reading
    # ------------------------------------------------------------------

    def _read_group(
        self,
        stations: pd.DataFrame,
        data_dir: Path,
        prefix: str,
        raw_suffix: str,
        variables: list[str],
        label: str,
        qa: list[QACheck],
    ) -> dict[str, pd.DataFrame]:
        per_station: dict[str, dict[str, pd.Series]] = {var: {} for var in variables}

        for sid, meta in stations.iterrows():
            full_name = f"{prefix}{meta['name']}"
            raw_file = self._find_raw_file(data_dir, full_name, raw_suffix)
            if raw_file is None:
                qa.append(QACheck(
                    name=f"station_weather:{label}:{sid}:missing_raw",
                    status="warn",
                    message=f"{full_name}: raw file not found ({full_name}{raw_suffix})",
                ))
                continue

            try:
                df = self._read_raw_file(raw_file, variables)
            except Exception as exc:
                qa.append(QACheck(
                    name=f"station_weather:{label}:{sid}:read_error",
                    status="fail",
                    message=f"Could not read {raw_file.name}: {exc}",
                ))
                continue

            indexed = df.set_index("date")
            for var in variables:
                per_station[var][sid] = indexed[var]

        result: dict[str, pd.DataFrame] = {
            var: pd.DataFrame(cols) for var, cols in per_station.items() if cols
        }

        if not result:
            raise InputValidationError(
                f"No valid station data files found for {label}. "
                f"Check the data directory and master file."
            )

        qa.append(QACheck(
            name=f"station_weather:{label}:daily_loaded",
            status="pass",
            message=(
                f"Daily data loaded ({label}): "
                f"{len(next(iter(result.values())).columns)} station(s), "
                f"variables: {', '.join(result.keys())}"
            ),
        ))
        return result

    @staticmethod
    def _find_raw_file(data_dir: Path, stem: str, suffix: str) -> Path | None:
        """Locate a raw station file, case-insensitively."""
        exact = data_dir / f"{stem}{suffix}"
        if exact.exists():
            return exact
        target = f"{stem}{suffix}".lower()
        for candidate in data_dir.iterdir():
            if candidate.name.lower() == target:
                return candidate
        return None

    @staticmethod
    def _is_swat_format(raw_file: Path) -> bool:
        """True if the file starts with an 8-digit YYYYMMDD date (SWAT Classic input)."""
        try:
            first_line = raw_file.open().readline().strip()
            return len(first_line) == 8 and first_line.isdigit()
        except OSError:
            return False

    def _read_raw_file(self, raw_file: Path, variables: list[str]) -> pd.DataFrame:
        if self._is_swat_format(raw_file):
            if variables == ["precip"]:
                df = self._read_swat_pcp(raw_file)
            else:
                df = self._read_swat_tmp(raw_file)
        else:
            df = pd.read_csv(raw_file, parse_dates=["date"])
            missing = set(variables) - set(df.columns)
            if missing:
                raise InputValidationError(f"{raw_file.name}: missing column(s) {sorted(missing)}")
            df = df[["date", *variables]]

        # Replace no_data_value sentinel with NaN for all variable columns
        for var in variables:
            df[var] = df[var].replace(self.no_data_value, float("nan"))

        return df

    @staticmethod
    def _read_swat_pcp(raw_file: Path) -> pd.DataFrame:
        """SWAT Classic precip input: line 1 = YYYYMMDD, rest = one float per line."""
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
        return pd.DataFrame({"date": dates, "precip": values})

    @staticmethod
    def _read_swat_tmp(raw_file: Path) -> pd.DataFrame:
        """SWAT Classic temp input: line 1 = YYYYMMDD, rest = "tmin,tmax" per line."""
        lines = raw_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        start_date = pd.to_datetime(lines[0].strip(), format="%Y%m%d")
        tmax_vals: list[float] = []
        tmin_vals: list[float] = []
        for ln in lines[1:]:
            ln = ln.strip()
            if not ln:
                continue
            parts = ln.split(",")
            if len(parts) >= 2:
                try:
                    tn, tx = float(parts[0].strip()), float(parts[1].strip())
                except ValueError:
                    tn = tx = float("nan")
                tmin_vals.append(tn)
                tmax_vals.append(tx)
            else:
                tmax_vals.append(float("nan"))
                tmin_vals.append(float("nan"))
        n = min(len(tmax_vals), len(tmin_vals))
        dates = pd.date_range(start=start_date, periods=n, freq="D")
        return pd.DataFrame({"date": dates, "tmax": tmax_vals[:n], "tmin": tmin_vals[:n]})
