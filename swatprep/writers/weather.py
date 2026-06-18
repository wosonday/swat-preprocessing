"""WeatherWriter: write SWAT Classic .pcp / .tmp station files and wgn.csv.

SWAT Classic file formats follow:
    Neitsch, S.L. et al. (2011). SWAT Input/Output File Documentation,
    Version 2009. Texas Water Resources Institute Technical Report 365.

Format summary
--------------
.pcp (precipitation):
    Line 1  : title string
    Line 2-4: Lati, Long, Elev
    Line 5  : start date minus one day (YYYYMMDD)
    Line 6+ : one value per day, right-justified 10 chars, 3 decimal places

.tmp (temperature):
    Same header; each data line has two values: Tmax then Tmin (10 chars each).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..core.weather import WeatherResult
from ..errors import WriterError


class WeatherWriter:
    """Write SWAT-ready weather files from a WeatherResult."""

    def __init__(self, result: WeatherResult, output_dir: Path) -> None:
        self.result = result
        self.output_dir = output_dir

    def write(self) -> list[Path]:
        """Write all weather files; return list of created paths."""
        out = self.output_dir
        out.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        stations = self.result.stations
        daily = self.result.daily

        precip_wide = daily.get("precip")
        tmax_wide = daily.get("tmax")
        tmin_wide = daily.get("tmin")

        for sid, meta in stations.iterrows():
            name = str(meta.get("name", sid))
            lat = float(meta["lat"])
            lon = float(meta["lon"])
            elev = float(meta["elev"])

            if precip_wide is not None and sid in precip_wide.columns:
                p = out / f"{sid}.pcp"
                _write_pcp(p, name, lat, lon, elev, precip_wide[sid])
                written.append(p)

            if tmax_wide is not None and sid in tmax_wide.columns:
                tx = tmax_wide[sid]
                tn = tmin_wide[sid] if (tmin_wide is not None and sid in tmin_wide.columns) else None
                t = out / f"{sid}.tmp"
                _write_tmp(t, name, lat, lon, elev, tx, tn)
                written.append(t)

        # WGN statistics CSV
        if not self.result.wgn_stats.empty:
            wgn_path = out / "wgn.csv"
            self.result.wgn_stats.to_csv(wgn_path, index=False)
            written.append(wgn_path)

        # Station list for SWAT Classic pcp.pcp / tmp.tmp master files
        sta_path = out / "stations.csv"
        stations.reset_index().to_csv(sta_path, index=False)
        written.append(sta_path)

        return written


# ---------------------------------------------------------------------------
# Format writers
# ---------------------------------------------------------------------------


def _header_lines(title: str, lat: float, lon: float, elev: float) -> list[str]:
    return [
        title,
        f"Lati{lat:10.2f}",
        f"Long{lon:10.2f}",
        f"Elev{elev:10.2f}",
    ]


def _start_date_line(series: pd.Series) -> str:
    """SWAT requires the date ONE DAY BEFORE the first data record."""
    first_date = pd.Timestamp(series.index[0])
    day_before = first_date - pd.Timedelta(days=1)
    return day_before.strftime("%Y%m%d")


def _write_pcp(
    path: Path,
    station_name: str,
    lat: float,
    lon: float,
    elev: float,
    precip: pd.Series,
) -> None:
    lines = _header_lines(f"Precipitation data: {station_name}", lat, lon, elev)
    lines.append(_start_date_line(precip))
    for val in precip:
        v = val if pd.notna(val) else -99.0
        lines.append(f"{v:10.3f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_tmp(
    path: Path,
    station_name: str,
    lat: float,
    lon: float,
    elev: float,
    tmax: pd.Series,
    tmin: pd.Series | None,
) -> None:
    lines = _header_lines(f"Temperature data: {station_name}", lat, lon, elev)
    lines.append(_start_date_line(tmax))
    for i, tx_val in enumerate(tmax):
        tx = tx_val if pd.notna(tx_val) else -99.0
        if tmin is not None:
            tn_val = tmin.iloc[i] if i < len(tmin) else None
            tn = tn_val if pd.notna(tn_val) else -99.0
        else:
            tn = -99.0
        lines.append(f"{tx:10.3f}{tn:10.3f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
