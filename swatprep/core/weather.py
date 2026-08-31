"""WeatherPreprocessor: load, validate and compute WGN statistics.

Reference: Arnold, J.G. et al. (2012). SWAT: Model Use, Calibration, and Validation.
Transactions of the ASABE, 55(4), 1491-1508.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..config import WeatherConfig
from ..errors import InputValidationError
from ..qa import QACheck
from ._wgn import (
    _MISSING,
    fill_temp_stats as _fill_temp_stats,
    fill_precip_stats as _fill_precip_stats,
    fill_climate_stats as _fill_climate_stats,
)

_REQUIRED_STATION_COLS = {"id", "name", "lat", "lon", "elev"}
_WET_THRESHOLD = 0.1  # mm; day is "wet" if precip >= this value


@dataclass
class WeatherResult:
    """Output of WeatherPreprocessor.run()."""

    stations: pd.DataFrame          # id(index), name, lat, lon, elev (union of all)
    precip_stations: pd.DataFrame | None  # precip-specific station list
    temp_stations: pd.DataFrame | None    # temperature-specific station list
    daily: dict[str, pd.DataFrame]  # {variable: wide_df} — DatetimeIndex × station_id
    wgn_stats: pd.DataFrame         # station_id, month, TMPMX, TMPMN, …
    qa: list[QACheck] = field(default_factory=list)


def compute_wgn_stats(
    stations: pd.DataFrame,
    daily: dict[str, pd.DataFrame],
    qa: list[QACheck],
) -> pd.DataFrame:
    """Compute SWAT weather generator monthly statistics per station.

    Parameters computed following Neitsch et al. (2011) SWAT Theoretical
    Documentation, Chapter 1 (Climate).

    `stations` is accepted for interface symmetry with the rest of the
    pipeline but is not read here — WGN stats are derived purely from the
    daily variable columns. Shared by WeatherPreprocessor and
    StationWeatherConverter so both compute WGN stats identically.
    """
    precip_wide = daily.get("precip")
    tmax_wide   = daily.get("tmax")
    tmin_wide   = daily.get("tmin")
    solar_wide  = daily.get("solar")
    rhum_wide   = daily.get("humidity")
    wind_wide   = daily.get("wind")

    station_ids = list(
        set(precip_wide.columns if precip_wide is not None else [])
        | set(tmax_wide.columns if tmax_wide is not None else [])
    )

    rows = []
    for sid in station_ids:
        p     = precip_wide[sid] if (precip_wide is not None and sid in precip_wide) else None
        tx    = tmax_wide[sid]   if (tmax_wide   is not None and sid in tmax_wide)   else None
        tn    = tmin_wide[sid]   if (tmin_wide   is not None and sid in tmin_wide)   else None
        solar = solar_wide[sid]  if (solar_wide  is not None and sid in solar_wide)  else None
        rhum  = rhum_wide[sid]   if (rhum_wide   is not None and sid in rhum_wide)   else None
        wind  = wind_wide[sid]   if (wind_wide   is not None and sid in wind_wide)   else None

        for month in range(1, 13):
            row: dict = {"station_id": sid, "month": month}
            _fill_temp_stats(row, tx, tn, month)
            _fill_precip_stats(row, p, month)
            _fill_climate_stats(row, solar, rhum, wind, tx, tn, month)
            rows.append(row)

    qa.append(QACheck(
        name="wgn_computed",
        status="pass",
        message=f"WGN stats computed for {len(station_ids)} station(s) × 12 months",
    ))
    return pd.DataFrame(rows)


class WeatherPreprocessor:
    """Load, validate, and compute WGN monthly statistics from station CSVs.

    Supports two modes:
    - **Unified**: single ``stations`` + ``data_dir`` for all variables
      (every station CSV must contain all configured variables).
    - **Split**: separate ``precip`` and ``temperature`` sub-configs, each
      with its own ``stations`` + ``data_dir``.  Precip CSVs only need a
      ``precip`` column; temperature CSVs only need ``tmax``/``tmin``.
    """

    def __init__(self, cfg: WeatherConfig) -> None:
        self.cfg = cfg

    # convenience: is the config using split sources?
    @property
    def _is_split(self) -> bool:
        return self.cfg.precip is not None or self.cfg.temp is not None

    def run(self) -> WeatherResult:
        qa: list[QACheck] = []

        if self._is_split:
            precip_stations, temp_stations, daily = self._load_split(qa)
            # Union of all stations for writer's station list
            frames = [df for df in (precip_stations, temp_stations) if df is not None]
            all_stations = pd.concat(frames)
            all_stations = all_stations[~all_stations.index.duplicated(keep="first")]
        else:
            all_stations = self._load_stations(self.cfg.stations, qa)
            daily = self._load_daily_unified(all_stations, qa)
            precip_stations = all_stations
            temp_stations = all_stations

        wgn = compute_wgn_stats(all_stations, daily, qa)
        return WeatherResult(
            stations=all_stations,
            precip_stations=precip_stations,
            temp_stations=temp_stations,
            daily=daily,
            wgn_stats=wgn,
            qa=qa,
        )

    # ------------------------------------------------------------------
    # Station metadata
    # ------------------------------------------------------------------

    def _load_stations(
        self, path: Path, qa: list[QACheck], label: str = "",
    ) -> pd.DataFrame:
        tag = f" ({label})" if label else ""
        df = pd.read_csv(path, dtype={"id": str})
        missing_cols = _REQUIRED_STATION_COLS - set(df.columns)
        if missing_cols:
            raise InputValidationError(
                f"stations.csv{tag} missing required columns: "
                f"{', '.join(sorted(missing_cols))}"
            )
        qa.append(QACheck(
            name=f"stations_loaded{('_' + label) if label else ''}",
            status="pass",
            message=f"{len(df)} station(s) loaded from {path.name}{tag}",
        ))
        return df.set_index("id")

    # ------------------------------------------------------------------
    # Split-source loading (separate precip / temperature)
    # ------------------------------------------------------------------

    def _load_split(
        self, qa: list[QACheck],
    ) -> tuple[pd.DataFrame | None, pd.DataFrame | None, dict[str, pd.DataFrame]]:
        cfg = self.cfg
        full_range = pd.date_range(cfg.start, cfg.end, freq="D")
        daily: dict[str, pd.DataFrame] = {}
        precip_stations: pd.DataFrame | None = None
        temp_stations: pd.DataFrame | None = None

        precip_vars = [v for v in cfg.variables if v == "precip"]
        temp_vars = [v for v in cfg.variables if v in ("tmax", "tmin")]

        # --- precip ---
        if precip_vars:
            p_sta_path, p_data_dir = cfg.precip_source()
            p_pattern = cfg.precip.file_pattern if cfg.precip is not None else cfg.file_pattern
            precip_stations = self._load_stations(p_sta_path, qa, label="precip")
            p_daily = self._load_daily_group(
                precip_stations, p_data_dir, precip_vars, full_range, qa,
                label="precip", file_pattern=p_pattern,
            )
            daily.update(p_daily)

        # --- temperature ---
        if temp_vars:
            t_sta_path, t_data_dir = cfg.temp_source()
            t_pattern = cfg.temp.file_pattern if cfg.temp is not None else cfg.file_pattern
            temp_stations = self._load_stations(t_sta_path, qa, label="temperature")
            t_daily = self._load_daily_group(
                temp_stations, t_data_dir, temp_vars, full_range, qa,
                label="temperature", file_pattern=t_pattern,
            )
            daily.update(t_daily)

        return precip_stations, temp_stations, daily

    def _load_daily_group(
        self,
        stations: pd.DataFrame,
        data_dir: Path,
        variables: list[str],
        full_range: pd.DatetimeIndex,
        qa: list[QACheck],
        label: str = "",
        file_pattern: str = "{id}.csv",
    ) -> dict[str, pd.DataFrame]:
        """Load station CSVs for a specific variable group."""
        cfg = self.cfg
        per_station: dict[str, dict[str, pd.Series]] = {}

        for sid in stations.index:
            # Resolve file_pattern: {id} → station id, {name} → station name
            fname = file_pattern.format(id=sid, name=stations.loc[sid, "name"])
            fpath = data_dir / fname
            if not fpath.exists():
                qa.append(QACheck(
                    name=f"data_file:{label}:{sid}" if label else f"data_file:{sid}",
                    status="fail",
                    message=f"Missing data file: {fpath.name}",
                    context={"station": sid, "path": str(fpath), "group": label},
                ))
                continue

            df = pd.read_csv(fpath, parse_dates=["date"]).set_index("date").sort_index()

            missing_vars = set(variables) - set(df.columns)
            if missing_vars:
                qa.append(QACheck(
                    name=f"variables:{label}:{sid}" if label else f"variables:{sid}",
                    status="fail",
                    message=f"{sid}.csv missing columns: {', '.join(sorted(missing_vars))}",
                ))
                continue

            df = df.reindex(full_range)

            for var in variables:
                missing_pct = df[var].isna().mean() * 100
                if missing_pct > 0:
                    status = "fail" if cfg.missing_policy == "fail" else "warn"
                    qa.append(QACheck(
                        name=f"missing:{sid}:{var}",
                        status=status,
                        message=f"{sid} {var}: {missing_pct:.1f}% missing in date range",
                        context={"station": sid, "variable": var,
                                 "missing_pct": round(missing_pct, 2)},
                    ))

            per_station[sid] = {var: df[var] for var in variables}

        if not per_station:
            raise InputValidationError(
                f"No valid station data files found for {label or 'weather'}. "
                f"Check data_dir and station IDs."
            )

        result: dict[str, pd.DataFrame] = {}
        for var in variables:
            result[var] = pd.DataFrame(
                {sid: s[var] for sid, s in per_station.items() if var in s}
            )

        qa.append(QACheck(
            name=f"daily_loaded{'_' + label if label else ''}",
            status="pass",
            message=(
                f"Daily data loaded ({label}): {len(per_station)} station(s), "
                f"variables: {', '.join(variables)}, "
                f"{len(full_range)} days"
            ),
        ))
        return result

    # ------------------------------------------------------------------
    # Unified loading (original single-source mode)
    # ------------------------------------------------------------------

    def _load_daily_unified(
        self, stations: pd.DataFrame, qa: list[QACheck]
    ) -> dict[str, pd.DataFrame]:
        """Load per-station CSVs; return wide DataFrames keyed by variable."""
        cfg = self.cfg
        full_range = pd.date_range(cfg.start, cfg.end, freq="D")
        per_station: dict[str, dict[str, pd.Series]] = {}

        for sid in stations.index:
            fname = cfg.file_pattern.format(id=sid, name=stations.loc[sid, "name"])
            fpath = cfg.data_dir / fname
            if not fpath.exists():
                qa.append(QACheck(
                    name=f"data_file:{sid}",
                    status="fail",
                    message=f"Missing data file: {fpath.name}",
                    context={"station": sid, "path": str(fpath)},
                ))
                continue

            df = pd.read_csv(fpath, parse_dates=["date"]).set_index("date").sort_index()

            missing_vars = set(cfg.variables) - set(df.columns)
            if missing_vars:
                qa.append(QACheck(
                    name=f"variables:{sid}",
                    status="fail",
                    message=f"{sid}.csv missing columns: {', '.join(sorted(missing_vars))}",
                ))
                continue

            # Reindex to full date range — gaps become NaN
            df = df.reindex(full_range)

            for var in cfg.variables:
                missing_pct = df[var].isna().mean() * 100
                if missing_pct > 0:
                    status = "fail" if cfg.missing_policy == "fail" else "warn"
                    qa.append(QACheck(
                        name=f"missing:{sid}:{var}",
                        status=status,
                        message=f"{sid} {var}: {missing_pct:.1f}% missing in date range",
                        context={"station": sid, "variable": var,
                                 "missing_pct": round(missing_pct, 2)},
                    ))

            per_station[sid] = {var: df[var] for var in cfg.variables}

        if not per_station:
            raise InputValidationError(
                "No valid station data files found. Check weather.data_dir and station IDs."
            )

        # Pivot to wide format per variable
        daily: dict[str, pd.DataFrame] = {}
        for var in cfg.variables:
            daily[var] = pd.DataFrame(
                {sid: s[var] for sid, s in per_station.items() if var in s}
            )

        qa.append(QACheck(
            name="daily_loaded",
            status="pass",
            message=(
                f"Daily data loaded: {len(per_station)} station(s), "
                f"variables: {', '.join(cfg.variables)}, "
                f"{len(full_range)} days"
            ),
        ))
        return daily
