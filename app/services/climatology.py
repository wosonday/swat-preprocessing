"""Monthly values and monthly climatology with the WMO-No. 1203 (2017) completeness rules.

- "sum" (precipitation, runoff depth): a month is valid only with no missing day (4.4.1 c).
- "mean" (discharge): a month is invalid with 11+ missing days or 5+ consecutive missing days (4.4.1 a).
- Estimated (gap-filled) days count as data, but at most 10 per month and fewer than 5 in a row (4.4.1 c, 4.6).
- A month of the climatology is reliable when valid in at least 80% of the years (4.4.2).
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

MONTHLY_COLUMNS = ["year", "month", "value", "n_days", "n_missing", "n_estimated",
                   "max_gap", "max_est_run", "valid", "reason"]


def _longest_run(mask: pd.Series) -> int:
    best = run = 0
    for flag in mask.to_numpy():
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def _reason(kind: str, n_missing: int, max_gap: int, n_est: int, est_run: int) -> str:
    if kind == "sum" and n_missing:
        return "missing days"
    if kind == "mean" and n_missing >= 11:
        return "11+ missing days"
    if kind == "mean" and max_gap >= 5:
        return "5+ consecutive missing days"
    if n_est > 10:
        return "more than 10 estimated days"
    if est_run >= 5:
        return "5+ consecutive estimated days"
    return ""


def monthly_values(daily: pd.Series, kind: Literal["sum", "mean"],
                   estimated: pd.Series | None = None) -> pd.DataFrame:
    """One row per calendar month spanned by `daily`'s index; days outside the index count as missing."""
    if daily.empty:
        return pd.DataFrame(columns=MONTHLY_COLUMNS)
    days = pd.date_range(daily.index.min().to_period("M").start_time,
                         daily.index.max().to_period("M").end_time.normalize(), freq="D")
    values = daily.astype(float).reindex(days)
    est = pd.Series(False, index=days) if estimated is None else estimated.reindex(days, fill_value=False).astype(bool)
    rows = []
    for period, month in values.groupby(values.index.to_period("M")):
        missing = month.isna()
        est_m = est.loc[month.index] & ~missing
        n_missing, n_est = int(missing.sum()), int(est_m.sum())
        gap, est_run = _longest_run(missing), _longest_run(est_m)
        reason = _reason(kind, n_missing, gap, n_est, est_run)
        value = (month.sum() if kind == "sum" else month.mean()) if not reason else np.nan
        rows.append([period.year, period.month, value, len(month), n_missing, n_est, gap, est_run, not reason, reason])
    return pd.DataFrame(rows, columns=MONTHLY_COLUMNS)


def monthly_climatology(monthly: pd.DataFrame, min_fraction: float = 0.8) -> pd.DataFrame:
    """12 rows: mean of the valid monthly values, how many years were valid, and whether that reaches min_fraction."""
    rows = []
    for m in range(1, 13):
        sub = monthly[monthly["month"] == m]
        n_years, n_valid = len(sub), int(sub["valid"].sum())
        mean = float(sub.loc[sub["valid"], "value"].mean()) if n_valid else np.nan
        ok = n_years > 0 and n_valid >= min_fraction * n_years - 1e-9
        rows.append([m, mean, n_valid, n_years, ok])
    return pd.DataFrame(rows, columns=["month", "mean", "n_valid", "n_years", "ok"])


def completeness(wide: pd.DataFrame) -> pd.DataFrame:
    """Missing days per station and calendar month (long table for a heatmap)."""
    rows = []
    for station in wide.columns:
        for period, month in wide[station].groupby(wide.index.to_period("M")):
            n_missing = int(month.isna().sum())
            rows.append([str(station), str(period), len(month), n_missing, round(100 * n_missing / len(month), 1)])
    return pd.DataFrame(rows, columns=["station", "period", "n_days", "n_missing", "pct_missing"])
