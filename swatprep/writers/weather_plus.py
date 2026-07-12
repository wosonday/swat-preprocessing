"""SWATPlusWeatherWriter: write SWAT+ daily weather files from a WeatherResult.

Unlike :class:`~swatprep.writers.weather.WeatherWriter` (which emits SWAT
Classic ``.pcp`` / ``.tmp`` files), this writer produces the SWAT+ daily
weather format plus the per-variable ``.cli`` index files that SWAT+ /
QSWAT+ / SWAT+ Editor expect.

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


@dataclass(frozen=True)
class _Spec:
    key: str                 # primary daily-variable key in WeatherResult.daily
    ext: str                 # output file extension
    cli: str                 # .cli index filename
    descr: str               # data-file header description
    cli_desc: str            # .cli header description
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

        for spec in _SPECS:
            frame = daily.get(spec.key)
            if frame is None or frame.empty:
                continue

            second_frame = daily.get(spec.second) if spec.second else None
            idx = frame.index
            year_arr = idx.year.to_numpy()
            doy_arr = idx.day_of_year.to_numpy()
            nbyr = int(idx.year.max() - idx.year.min() + 1)
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

        # WGN statistics and station list (shared reference outputs)
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
