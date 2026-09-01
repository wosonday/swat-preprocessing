"""SWATPlusWeatherWriter: write SWAT+ daily weather files from a WeatherResult.

Unlike :class:`~swatprep.writers.weather.WeatherWriter` (which emits SWAT
Classic ``.pcp`` / ``.tmp`` files), this writer produces the SWAT+ daily
weather format plus the ``.cli`` index files that SWAT+ / QSWAT+ / SWAT+
Editor expect -- including the two "linking" files SWAT+'s TxtInOut actually
reads to resolve each station's climate data: ``weather-sta.cli`` (station
registry) and ``weather-wgn.cli`` (WGN statistics in SWAT+'s fixed format).

SWAT+ daily file format (one file per station per variable)::

    <name>.pcp: Precipitation data - file written by swatprep <ts>
    nbyr     tstep       lat       lon      elev
    <nbyr>         0   <lat>   <lon>   <elev>
    <year> <doy>      <value>
    ...

``.cli`` index format (one per variable group present)::

    pcp.cli: Precipitation file names - file written by swatprep <ts>
    filename
    <station1>.pcp
    <station2>.pcp

``weather-sta.cli`` (one row per station)::

    name  wgn  pcp  tmp  slr  hmd  wnd  pet  atmo_dep

Each of pcp/tmp/slr/hmd/wnd is the written data file's stem (no extension)
if that variable was written for the station, else "sim". pet/atmo_dep are
not computed by swatprep and are always "null".

``weather-wgn.cli`` -- one WGN group per station (group name == station
name), each a 3-line header (title, group header, column header) followed
by 12 monthly rows, built directly from ``WeatherResult.wgn_stats``.

The daily rows carry an explicit ``year`` + ``day-of-year`` column, which is
what distinguishes SWAT+ input from SWAT Classic (a bare value-per-line list).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from ..core.weather import WeatherResult

_NODATA = -99.0

# (WGN column in WeatherResult.wgn_stats, weather-wgn.cli column header)
_WGN_COLUMN_MAP: list[tuple[str, str]] = [
    ("TMPMX", "tmp_max_ave"),
    ("TMPMN", "tmp_min_ave"),
    ("TMPSTDMX", "tmp_max_sd"),
    ("TMPSTDMN", "tmp_min_sd"),
    ("PCPMM", "pcp_ave"),
    ("PCPSTD", "pcp_sd"),
    ("PCPSKW", "pcp_skew"),
    ("PR_W1", "wet_dry"),
    ("PR_W2", "wet_wet"),
    ("PCPD", "pcp_days"),
    ("RAINHHMX", "pcp_hhr"),
    ("SOLARAV", "slr_ave"),
    ("DEWPT", "dew_ave"),
    ("WNDAV", "wnd_ave"),
]

# weather-sta.cli variable columns, in order -- matches _Spec.ext[1:] below.
_STA_VAR_KEYS = ["pcp", "tmp", "slr", "hmd", "wnd"]


@dataclass(frozen=True)
class _Spec:
    key: str                 # primary daily-variable key in WeatherResult.daily
    ext: str                 # output file extension
    cli: str                 # .cli index filename
    descr: str                # data-file header description
    cli_desc: str             # .cli header description
    second: str | None = None  # secondary key for two-column files (tmin)


# Ordered so pcp/tmp lead, matching SWAT+ Editor conventions.
_SPECS: list[_Spec] = [
    _Spec("precip",   ".pcp", "pcp.cli", "Precipitation data",     "Precipitation file names"),
    _Spec("tmax",     ".tmp", "tmp.cli", "Temperature data",       "Temperature file names", second="tmin"),
    _Spec("humidity", ".hmd", "hmd.cli", "Relative humidity data", "Relative humidity file names"),
    _Spec("solar",    ".slr", "slr.cli", "Solar radiation data",   "Solar radiation file names"),
    _Spec("wind",     ".wnd", "wnd.cli", "Wind speed data",        "Wind speed file names"),
]


class SWATPlusWeatherWriter:
    """Write SWAT+ daily weather files (+ .cli indexes) from a WeatherResult."""

    def __init__(self, result: WeatherResult, output_dir: Path) -> None:
        self.result = result
        self.output_dir = output_dir

    def write(self) -> list[Path]:
        out = self.output_dir
        out.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        daily = self.result.daily
        stations = self.result.stations

        written: list[Path] = []
        cli_registry: dict[str, list[str]] = {spec.cli: [] for spec in _SPECS}
        station_files: dict[object, dict[str, str]] = {}
        global_nbyr = 0

        for spec in _SPECS:
            frame = daily.get(spec.key)
            if frame is None or frame.empty:
                continue

            second_frame = daily.get(spec.second) if spec.second else None
            idx = frame.index
            year_arr = idx.year.to_numpy()
            doy_arr = idx.day_of_year.to_numpy()
            nbyr = int(idx.year.max() - idx.year.min() + 1)
            global_nbyr = max(global_nbyr, nbyr)
            # Uniqueness is scoped per variable: <name>.pcp and <name>.tmp
            # never collide, only two same-named stations within one variable do.
            used_stems: set[str] = set()

            for sid in frame.columns:
                name, lat, lon, elev = self._station_meta(stations, sid)
                stem = self._unique_stem(name, sid, used_stems)
                filename = f"{stem}{spec.ext}"
                fpath = out / filename

                primary = frame[sid].fillna(_NODATA).to_numpy()
                if spec.second is not None:
                    if second_frame is not None and sid in second_frame.columns:
                        secondary = second_frame[sid].fillna(_NODATA).to_numpy()
                    else:
                        secondary = None
                    _write_two_col(
                        fpath, filename, spec.descr, ts, nbyr, lat, lon, elev,
                        year_arr, doy_arr, primary, secondary,
                    )
                else:
                    _write_one_col(
                        fpath, filename, spec.descr, ts, nbyr, lat, lon, elev,
                        year_arr, doy_arr, primary,
                    )
                written.append(fpath)
                cli_registry[spec.cli].append(filename)
                station_files.setdefault(sid, {})[spec.ext[1:]] = stem

        # Per-variable .cli index files
        for spec in _SPECS:
            filenames = cli_registry[spec.cli]
            if not filenames:
                continue
            lines = [
                f"{spec.cli}: {spec.cli_desc} - file written by swatprep {ts}",
                "filename",
                *filenames,
            ]
            cli_path = out / spec.cli
            cli_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            written.append(cli_path)

        # weather-sta.cli / weather-wgn.cli -- the linking files SWAT+ actually
        # reads to resolve each station's climate data.
        if not self.result.wgn_stats.empty:
            # wgn_stats is built from a sorted station_id list (compute_wgn_stats),
            # so .unique() already preserves sorted order; sorted() here is
            # defense in depth to guarantee deterministic output regardless.
            sids = sorted(self.result.wgn_stats["station_id"].unique())
            wgn_names = self._assign_wgn_names(stations, sids)
            written.append(_write_weather_wgn(out, self.result.wgn_stats, stations, wgn_names, global_nbyr, ts))
            written.append(_write_weather_sta(out, station_files, wgn_names, ts))

        # WGN statistics and station list (existing reference outputs, kept
        # alongside weather-wgn.cli for csv-friendly inspection)
        if not self.result.wgn_stats.empty:
            wgn_path = out / "wgn.csv"
            self.result.wgn_stats.to_csv(wgn_path, index=False)
            written.append(wgn_path)

        sta_path = out / "stations.csv"
        stations.reset_index().to_csv(sta_path, index=False)
        written.append(sta_path)

        return written

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _station_meta(stations: pd.DataFrame, sid) -> tuple[str, float, float, float]:
        if sid in stations.index:
            meta = stations.loc[sid]
            name = str(meta["name"]) if "name" in meta else str(sid)
            return name, float(meta["lat"]), float(meta["lon"]), float(meta["elev"])
        return str(sid), 0.0, 0.0, 0.0

    @staticmethod
    def _unique_stem(name: str, sid, used: set[str]) -> str:
        """Derive a collision-free file stem (station names are not unique)."""
        stem = name
        if stem in used:
            stem = f"{name}_{sid}"
        used.add(stem)
        return stem

    @classmethod
    def _assign_wgn_names(cls, stations: pd.DataFrame, sids: list) -> dict:
        """One WGN group name per station id, collision-free (reuses the same
        dedup rule as data-file stems, computed once so weather-sta.cli and
        weather-wgn.cli agree on the same name)."""
        used: set[str] = set()
        names: dict = {}
        for sid in sids:
            name, *_ = cls._station_meta(stations, sid)
            names[sid] = cls._unique_stem(name, sid, used)
        return names


# ---------------------------------------------------------------------------
# Format writers
# ---------------------------------------------------------------------------


def _header_lines(
    filename: str, descr: str, ts: str,
    nbyr: int, lat: float, lon: float, elev: float,
) -> list[str]:
    return [
        f"{filename}: {descr} - file written by swatprep {ts}",
        "nbyr     tstep       lat       lon      elev",
        "{:4d}{:10d}{:10.3f}{:10.3f}{:10.3f}".format(nbyr, 0, lat, lon, elev),
    ]


def _write_one_col(
    path: Path, filename: str, descr: str, ts: str,
    nbyr: int, lat: float, lon: float, elev: float,
    year_arr, doy_arr, values,
) -> None:
    lines = _header_lines(filename, descr, ts, nbyr, lat, lon, elev)
    lines.extend(
        f"{y:4d}{d:5d}{v:11.5f}  "
        for y, d, v in zip(year_arr, doy_arr, values)
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_two_col(
    path: Path, filename: str, descr: str, ts: str,
    nbyr: int, lat: float, lon: float, elev: float,
    year_arr, doy_arr, primary, secondary,
) -> None:
    lines = _header_lines(filename, descr, ts, nbyr, lat, lon, elev)
    if secondary is None:
        lines.extend(
            f"{y:4d}{d:5d}{tx:11.5f} {_NODATA:11.5f}  "
            for y, d, tx in zip(year_arr, doy_arr, primary)
        )
    else:
        lines.extend(
            f"{y:4d}{d:5d}{tx:11.5f} {tn:11.5f}  "
            for y, d, tx, tn in zip(year_arr, doy_arr, primary, secondary)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_weather_wgn(
    out: Path,
    wgn_stats: pd.DataFrame,
    stations: pd.DataFrame,
    wgn_names: dict,
    nbyr: int,
    ts: str,
) -> Path:
    lines = [f"weather-wgn.cli: written by swatprep {ts}"]
    col_header = "".join(f"{h:>14}" for _, h in _WGN_COLUMN_MAP)
    for sid, name in wgn_names.items():
        if sid in stations.index:
            meta = stations.loc[sid]
            lat, lon, elev = float(meta["lat"]), float(meta["lon"]), float(meta["elev"])
        else:
            lat = lon = elev = 0.0
        lines.append(f"{name:<24}{lat:14.5f}{lon:14.5f}{elev:14.5f}{nbyr:10d}")
        lines.append(col_header)
        rows = wgn_stats[wgn_stats["station_id"] == sid].sort_values("month")
        for _, row in rows.iterrows():
            lines.append("".join(f"{float(row[src]):14.5f}" for src, _ in _WGN_COLUMN_MAP))
    path = out / "weather-wgn.cli"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_weather_sta(
    out: Path,
    station_files: dict,
    wgn_names: dict,
    ts: str,
) -> Path:
    header = "".join(f"{h:<27}" for h in ["name", "wgn", *_STA_VAR_KEYS]) + "".join(
        f"{h:<10}" for h in ["pet", "atmo_dep"]
    )
    lines = [f"weather-sta.cli: written by swatprep {ts}", header]
    for sid, name in wgn_names.items():
        files = station_files.get(sid, {})
        row_vars = [files.get(key, "sim") for key in _STA_VAR_KEYS]
        row = "".join(f"{v:<27}" for v in [name, name, *row_vars]) + "".join(
            f"{v:<10}" for v in ["null", "null"]
        )
        lines.append(row)
    path = out / "weather-sta.cli"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
