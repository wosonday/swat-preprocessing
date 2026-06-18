"""WeatherPreprocessor: load, validate and compute WGN statistics.

Reference: Arnold, J.G. et al. (2012). SWAT: Model Use, Calibration, and Validation.
Transactions of the ASABE, 55(4), 1491-1508.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import WeatherConfig
from ..errors import InputValidationError
from ..qa import QACheck

_REQUIRED_STATION_COLS = {"id", "name", "lat", "lon", "elev"}
_WET_THRESHOLD = 0.1  # mm; day is "wet" if precip >= this value
_MISSING = -99.0      # SWAT sentinel for unavailable parameters


@dataclass
class WeatherResult:
    """Output of WeatherPreprocessor.run()."""

    stations: pd.DataFrame          # id(index), name, lat, lon, elev
    daily: dict[str, pd.DataFrame]  # {variable: wide_df} — DatetimeIndex × station_id
    wgn_stats: pd.DataFrame         # station_id, month, TMPMX, TMPMN, …
    qa: list[QACheck] = field(default_factory=list)


class WeatherPreprocessor:
    """Load, validate, and compute WGN monthly statistics from station CSVs."""

    def __init__(self, cfg: WeatherConfig) -> None:
        self.cfg = cfg

    def run(self) -> WeatherResult:
        qa: list[QACheck] = []
        stations = self._load_stations(qa)
        daily = self._load_daily(stations, qa)
        wgn = self._compute_wgn(stations, daily, qa)
        return WeatherResult(stations=stations, daily=daily, wgn_stats=wgn, qa=qa)

    # ------------------------------------------------------------------
    # Station metadata
    # ------------------------------------------------------------------

    def _load_stations(self, qa: list[QACheck]) -> pd.DataFrame:
        path = self.cfg.stations
        df = pd.read_csv(path, dtype={"id": str})
        missing_cols = _REQUIRED_STATION_COLS - set(df.columns)
        if missing_cols:
            raise InputValidationError(
                f"stations.csv missing required columns: {', '.join(sorted(missing_cols))}"
            )
        qa.append(QACheck(
            name="stations_loaded",
            status="pass",
            message=f"{len(df)} station(s) loaded from {path.name}",
        ))
        return df.set_index("id")

    # ------------------------------------------------------------------
    # Daily time series
    # ------------------------------------------------------------------

    def _load_daily(
        self, stations: pd.DataFrame, qa: list[QACheck]
    ) -> dict[str, pd.DataFrame]:
        """Load per-station CSVs; return wide DataFrames keyed by variable."""
        cfg = self.cfg
        full_range = pd.date_range(cfg.start, cfg.end, freq="D")
        per_station: dict[str, dict[str, pd.Series]] = {}

        for sid in stations.index:
            fpath = cfg.data_dir / f"{sid}.csv"
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

    # ------------------------------------------------------------------
    # WGN statistics
    # ------------------------------------------------------------------

    def _compute_wgn(
        self,
        stations: pd.DataFrame,
        daily: dict[str, pd.DataFrame],
        qa: list[QACheck],
    ) -> pd.DataFrame:
        """Compute SWAT weather generator monthly statistics per station.

        Parameters computed following Neitsch et al. (2011) SWAT Theoretical
        Documentation, Chapter 1 (Climate).
        """
        precip_wide = daily.get("precip")
        tmax_wide = daily.get("tmax")
        tmin_wide = daily.get("tmin")

        station_ids = list(
            set(precip_wide.columns if precip_wide is not None else [])
            | set(tmax_wide.columns if tmax_wide is not None else [])
        )

        rows = []
        for sid in station_ids:
            p = precip_wide[sid] if (precip_wide is not None and sid in precip_wide) else None
            tx = tmax_wide[sid] if (tmax_wide is not None and sid in tmax_wide) else None
            tn = tmin_wide[sid] if (tmin_wide is not None and sid in tmin_wide) else None

            for month in range(1, 13):
                row: dict = {"station_id": sid, "month": month}
                _fill_temp_stats(row, tx, tn, month)
                _fill_precip_stats(row, p, month)
                rows.append(row)

        qa.append(QACheck(
            name="wgn_computed",
            status="pass",
            message=f"WGN stats computed for {len(station_ids)} station(s) × 12 months",
        ))
        return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Per-month statistics helpers
# ---------------------------------------------------------------------------


def _fill_temp_stats(row: dict, tmax, tmin, month: int) -> None:
    for src, mx_key, std_key in [(tmax, "TMPMX", "TMPSTDMX"), (tmin, "TMPMN", "TMPSTDMN")]:
        if src is not None:
            m = src[src.index.month == month].dropna()
            row[mx_key] = round(float(m.mean()), 2) if len(m) else _MISSING
            row[std_key] = round(float(m.std()), 2) if len(m) > 1 else 0.0
        else:
            row[mx_key] = row[std_key] = _MISSING


def _fill_precip_stats(row: dict, precip, month: int) -> None:
    """Fill PCPMM, PCPSTD, PCPSKW, PR_W1, PR_W2, PCPD plus unavailable params."""
    unavailable_keys = ("RAINHHMX", "SOLARAV", "DEWPT", "WNDAV")
    for k in unavailable_keys:
        row[k] = _MISSING

    if precip is None:
        for k in ("PCPMM", "PCPSTD", "PCPSKW", "PR_W1", "PR_W2", "PCPD"):
            row[k] = _MISSING
        return

    p = precip[precip.index.month == month].dropna()
    if len(p) == 0:
        for k in ("PCPMM", "PCPSTD", "PCPSKW", "PR_W1", "PR_W2", "PCPD"):
            row[k] = _MISSING
        return

    wet_mask = p >= _WET_THRESHOLD
    wet_vals = p[wet_mask]

    # Approximate mean monthly total from available data
    n_years = max(1.0, len(p) / 30.44)
    row["PCPMM"] = round(float(p.sum() / n_years), 2)
    row["PCPSTD"] = round(float(wet_vals.std()), 2) if len(wet_vals) > 1 else 0.0
    row["PCPSKW"] = round(float(wet_vals.skew()), 2) if len(wet_vals) > 2 else 0.0

    pr_w1, pr_w2 = _markov_probs(wet_mask)
    row["PR_W1"] = round(pr_w1, 4)
    row["PR_W2"] = round(pr_w2, 4)
    row["PCPD"] = round(float(wet_mask.sum() / n_years), 1)


def _markov_probs(wet: pd.Series) -> tuple[float, float]:
    """Return P(wet|dry) and P(wet|wet) from a boolean Series."""
    if len(wet) < 2:
        return 0.0, 0.0
    prev = wet.values[:-1]
    curr = wet.values[1:]
    dry_prev = ~prev
    wet_prev = prev
    pr_w1 = float(curr[dry_prev].mean()) if dry_prev.sum() > 0 else 0.0
    pr_w2 = float(curr[wet_prev].mean()) if wet_prev.sum() > 0 else 0.0
    return pr_w1, pr_w2
