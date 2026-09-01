"""WeatherWriter: write SWAT Classic (SWAT2012) .pcp/.tmp station files and a
master metadata file per domain (pcp / tmp).

Reference: Arnold, J.G. et al. (2012). SWAT: Model Use, Calibration, and Validation.
Transactions of the ASABE, 55(4), 1491-1508.

Format summary
--------------
Per-station file (`{pcp_|tmp_}{station}.txt`):
    Line 1  : date of the FIRST data record (YYYYMMDD) -- no day-before offset.
    Line 2+ : one value per day (pcp), or "tmin,tmax" per day (tmp).

There is no metadata header block in the per-station file (no title / Lati /
Long / Elev lines) -- station metadata lives only in the master file. This
matches the real SWAT2012 vendor-data convention (verified against a known
working SWAT2012 project's raw station files), not the older
Neitsch-documentation-derived 4-line-header convention this writer used to
produce.

Master (metadata) file (`master_pcp.txt` / `master_tmp.txt`):
    ID,NAME,LAT,LONG,ELEVATION      (uppercase columns; NAME carries the
                                      domain prefix, e.g. "pcp_ANKHE")
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..core.weather import WeatherResult


class WeatherWriter:
    """Write SWAT2012-ready weather files from a WeatherResult."""

    PCP_PREFIX = "pcp_"
    TMP_PREFIX = "tmp_"

    def __init__(self, result: WeatherResult, output_dir: Path) -> None:
        self.result = result
        self.output_dir = output_dir

    def write(self) -> list[Path]:
        """Write all weather files; return list of created paths."""
        out = self.output_dir
        out.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        daily = self.result.daily

        precip_wide = daily.get("precip")
        tmax_wide = daily.get("tmax")
        tmin_wide = daily.get("tmin")

        precip_stations = self.result.precip_stations if self.result.precip_stations is not None else self.result.stations
        temp_stations = self.result.temp_stations if self.result.temp_stations is not None else self.result.stations

        if precip_wide is not None:
            for sid, meta in precip_stations.iterrows():
                if sid not in precip_wide.columns:
                    continue
                code = str(meta.get("name", sid))
                p = out / f"{self.PCP_PREFIX}{code}.txt"
                _write_pcp(p, precip_wide[sid])
                written.append(p)
            written_precip_stations = precip_stations.loc[precip_stations.index.isin(precip_wide.columns)]
            written.append(self._write_master(out, written_precip_stations, self.PCP_PREFIX, "master_pcp.txt"))

        if tmax_wide is not None:
            for sid, meta in temp_stations.iterrows():
                if sid not in tmax_wide.columns:
                    continue
                code = str(meta.get("name", sid))
                tx = tmax_wide[sid]
                tn = tmin_wide[sid] if (tmin_wide is not None and sid in tmin_wide.columns) else None
                t = out / f"{self.TMP_PREFIX}{code}.txt"
                _write_tmp(t, tx, tn)
                written.append(t)
            written_temp_stations = temp_stations.loc[temp_stations.index.isin(tmax_wide.columns)]
            written.append(self._write_master(out, written_temp_stations, self.TMP_PREFIX, "master_tmp.txt"))

        if not self.result.wgn_stats.empty:
            wgn_path = out / "wgn.csv"
            self.result.wgn_stats.to_csv(wgn_path, index=False)
            written.append(wgn_path)

        return written

    @staticmethod
    def _write_master(out: Path, stations: pd.DataFrame, prefix: str, filename: str) -> Path:
        df = stations.reset_index()
        master = pd.DataFrame({
            "ID": df["id"],
            "NAME": prefix + df["name"].astype(str),
            "LAT": df["lat"],
            "LONG": df["lon"],
            "ELEVATION": df["elev"],
        })
        path = out / filename
        master.to_csv(path, index=False)
        return path


# ---------------------------------------------------------------------------
# Format writers
# ---------------------------------------------------------------------------


def _fmt_value(v: float) -> str:
    """Compact numeric formatting matching the real SWAT2012 vendor convention
    (no fixed-width padding, e.g. "0.0", "1.5" -- not "     1.500")."""
    s = f"{float(v):.3f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    return s


def _write_pcp(path: Path, precip: pd.Series) -> None:
    lines = [pd.Timestamp(precip.index[0]).strftime("%Y%m%d")]
    for val in precip:
        v = val if pd.notna(val) else -99.0
        lines.append(_fmt_value(v))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_tmp(path: Path, tmax: pd.Series, tmin: pd.Series | None) -> None:
    lines = [pd.Timestamp(tmax.index[0]).strftime("%Y%m%d")]
    for i, tx_val in enumerate(tmax):
        tx = tx_val if pd.notna(tx_val) else -99.0
        if tmin is not None:
            tn_val = tmin.iloc[i] if i < len(tmin) else None
            tn = tn_val if pd.notna(tn_val) else -99.0
        else:
            tn = -99.0
        # Real SWAT2012 vendor convention writes tmin,tmax per line (not tmax,tmin).
        lines.append(f"{_fmt_value(tn)},{_fmt_value(tx)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
