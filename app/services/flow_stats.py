"""Flow duration curve (Weibull plotting position) and per-station streamflow summary."""
from __future__ import annotations

import numpy as np
import pandas as pd


def fdc(series: pd.Series) -> pd.DataFrame:
    """Valid values sorted high to low; exceedance_pct = 100 * m / (n + 1)."""
    flow = np.sort(series.dropna().to_numpy(dtype=float))[::-1]
    rank = np.arange(1, len(flow) + 1)
    return pd.DataFrame({"exceedance_pct": 100 * rank / (len(flow) + 1), "flow": flow})


def flow_quantile(series: pd.Series, pct: float) -> float:
    """Flow exceeded pct % of the time (Q5 = high flow, Q95 = low flow); NaN without data."""
    curve = fdc(series)
    if curve.empty:
        return float("nan")
    return float(np.interp(pct, curve["exceedance_pct"], curve["flow"]))


def summary(wide: pd.DataFrame) -> pd.DataFrame:
    """One row per station; pct_missing counts the days between its first and last value."""
    rows = []
    for sid in wide.columns:
        s = wide[sid]
        first, last = s.first_valid_index(), s.last_valid_index()
        if first is None:
            rows.append({"station": sid})
            continue
        span = s.loc[first:last]
        rows.append({
            "station": sid, "start": first.date(), "end": last.date(),
            "pct_missing": round(100 * float(span.isna().mean()), 1),
            "min": span.min(), "mean": span.mean(), "max": span.max(),
            "q5": flow_quantile(span, 5), "q50": flow_quantile(span, 50), "q95": flow_quantile(span, 95),
        })
    return pd.DataFrame(rows, columns=["station", "start", "end", "pct_missing", "min", "mean", "max",
                                       "q5", "q50", "q95"])
