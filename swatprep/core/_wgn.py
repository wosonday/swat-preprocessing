"""WGN monthly statistics helpers for WeatherPreprocessor.

References:
  - Neitsch et al. (2011). SWAT Theoretical Documentation, Chapter 1.
  - Buck (1981). New equations for computing vapor pressure and enhancement
    factor. J. Appl. Meteorol., 20(12), 1527-1532.
"""
from __future__ import annotations

import math

import pandas as pd

_WET_THRESHOLD = 0.1   # mm; day is "wet" if precip >= this value
_MISSING = -99.0       # SWAT sentinel for unavailable parameters


# ---------------------------------------------------------------------------
# Temperature
# ---------------------------------------------------------------------------


def fill_temp_stats(row: dict, tmax, tmin, month: int) -> None:
    """Monthly mean and std-dev of tmax and tmin (°C)."""
    for src, mx_key, std_key in [
        (tmax, "TMPMX",    "TMPSTDMX"),
        (tmin, "TMPMN",    "TMPSTDMN"),
    ]:
        if src is not None:
            m = src[src.index.month == month].dropna()
            row[mx_key]  = round(float(m.mean()), 2) if len(m)     else _MISSING
            row[std_key] = round(float(m.std()),  2) if len(m) > 1 else 0.0
        else:
            row[mx_key] = row[std_key] = _MISSING


# ---------------------------------------------------------------------------
# Precipitation
# ---------------------------------------------------------------------------


def fill_precip_stats(row: dict, precip, month: int) -> None:
    """Fill PCPMM, PCPSTD, PCPSKW, PR_W1, PR_W2, PCPD, RAINHHMX.

    RAINHHMX (max half-hourly rainfall) requires sub-daily data; always -99.
    """
    row["RAINHHMX"] = _MISSING

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
    n_years  = max(1, p.index.year.nunique())

    row["PCPMM"]  = round(float(p.sum() / n_years), 2)
    row["PCPSTD"] = round(float(wet_vals.std()),  2) if len(wet_vals) > 1 else 0.0
    row["PCPSKW"] = round(float(wet_vals.skew()), 2) if len(wet_vals) > 2 else 0.0
    row["PCPD"]   = round(float(wet_mask.sum() / n_years), 2)

    pr_w1, pr_w2 = markov_probs(wet_mask)
    row["PR_W1"] = round(pr_w1, 4)
    row["PR_W2"] = round(pr_w2, 4)


def markov_probs(wet_mask: pd.Series) -> tuple[float, float]:
    """Markov wet/dry transition probabilities (within-year only).

    Returns:
        (PR_W1, PR_W2) = (P(wet|dry), P(wet|wet))
    """
    if len(wet_mask) < 2:
        return 0.0, 0.0

    d2w = d2d = w2w = w2d = 0
    for _yr, grp in wet_mask.groupby(wet_mask.index.year):
        arr = grp.values
        for i in range(len(arr) - 1):
            if arr[i]:
                if arr[i + 1]:
                    w2w += 1
                else:
                    w2d += 1
            else:
                if arr[i + 1]:
                    d2w += 1
                else:
                    d2d += 1

    pr_w1 = d2w / (d2w + d2d) if (d2w + d2d) > 0 else 0.0
    pr_w2 = w2w / (w2w + w2d) if (w2w + w2d) > 0 else 0.0
    return pr_w1, pr_w2


# ---------------------------------------------------------------------------
# Climate: solar / dew point / wind
# ---------------------------------------------------------------------------


def _dewpoint(t_celsius: float, rh_fraction: float) -> float:
    """Dew point temperature (°C) via Buck (1981) equation.

    Args:
        t_celsius:   Air temperature in °C.
        rh_fraction: Relative humidity as fraction 0-1.
    """
    rh_pct = max(1.0, min(100.0, rh_fraction * 100.0))
    a, b = 17.625, 243.04          # Buck equation constants
    gamma = math.log(rh_pct / 100.0) + a * t_celsius / (b + t_celsius)
    return b * gamma / (a - gamma)


def fill_climate_stats(
    row: dict,
    solar,
    rhum,
    wind,
    tmax,
    tmin,
    month: int,
) -> None:
    """Fill SOLARAV, DEWPT, WNDAV from daily data when available.

    Falls back to _MISSING (-99) if the variable is absent.

    Args:
        solar: Daily solar radiation Series (MJ/m²/day), or None.
        rhum:  Daily relative humidity Series (fraction 0-1), or None.
        wind:  Daily wind speed Series (m/s), or None.
        tmax:  Daily max temperature Series (°C), or None (for DEWPT).
        tmin:  Daily min temperature Series (°C), or None (for DEWPT).
        month: Calendar month (1-12).
    """
    # SOLARAV — monthly mean solar radiation (MJ/m²/day)
    if solar is not None:
        s = solar[solar.index.month == month].dropna()
        row["SOLARAV"] = round(float(s.mean()), 4) if len(s) else _MISSING
    else:
        row["SOLARAV"] = _MISSING

    # DEWPT — monthly mean dew point (°C) from rhum + Tmean
    if rhum is not None and (tmax is not None or tmin is not None):
        idx = rhum.index[rhum.index.month == month]
        rh_m = rhum.loc[idx].dropna()
        # Build Tmean from available temperature series
        if tmax is not None and tmin is not None:
            tmean_m = ((tmax.loc[idx] + tmin.loc[idx]) / 2.0).dropna()
        elif tmax is not None:
            tmean_m = tmax.loc[idx].dropna()
        else:
            tmean_m = tmin.loc[idx].dropna()
        common = rh_m.index.intersection(tmean_m.index)
        if len(common) > 0:
            dp_vals = [
                _dewpoint(float(tmean_m.loc[d]), float(rh_m.loc[d]))
                for d in common
            ]
            row["DEWPT"] = round(float(sum(dp_vals) / len(dp_vals)), 2)
        else:
            row["DEWPT"] = _MISSING
    else:
        row["DEWPT"] = _MISSING

    # WNDAV — monthly mean wind speed (m/s)
    if wind is not None:
        w = wind[wind.index.month == month].dropna()
        row["WNDAV"] = round(float(w.mean()), 4) if len(w) else _MISSING
    else:
        row["WNDAV"] = _MISSING
