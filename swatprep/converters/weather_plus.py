# SWATPlusWeatherConverter: write SWAT+ daily weather files from merged station CSVs.
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from ..errors import InputValidationError
from ..qa import QACheck


@dataclass
class _VarSpec:
    ext: str
    cli_name: str
    description: str
    cli_desc: str
    cols: list[str]
    two_col: bool = False


_VAR_SPECS: list[_VarSpec] = [
    _VarSpec(".pcp", "pcp.cli", "Precipitation data", "Precipitation file names", ["precip"]),
    _VarSpec(".tmp", "tmp.cli", "Temperature data",   "Temperature file names",   ["tmax", "tmin"], two_col=True),
    _VarSpec(".hmd", "hmd.cli", "Relative humidity data", "Relative humidity file names", ["rhum"]),
    _VarSpec(".slr", "slr.cli", "Solar radiation data",   "Solar radiation file names",   ["solar"]),
    _VarSpec(".wnd", "wnd.cli", "Wind speed data",        "Wind speed file names",        ["wind"]),
]


@dataclass
class SWATPlusWeatherStation:
    name: str
    lat: float
    lon: float
    elev: float
    files_written: list[Path] = field(default_factory=list)
    n_days: int = 0
    qa: list[QACheck] = field(default_factory=list)


@dataclass
class SWATPlusWeatherResult:
    stations: list[SWATPlusWeatherStation]
    cli_files: list[Path]
    data_files: list[Path]
    qa: list[QACheck] = field(default_factory=list)

    @property
    def files_written(self) -> list[Path]:
        return self.cli_files + self.data_files


class SWATPlusWeatherConverter:
    """Convert merged station CSVs to SWAT+ daily weather files (.pcp/.tmp/.hmd/.slr/.wnd)."""

    _DEFAULT_COL_MAP = {
        "precip": "precip", "tmax": "tmax", "tmin": "tmin",
        "rhum": "rhum", "solar": "solar", "wind": "wind",
    }

    def __init__(
        self,
        data_dir: Path,
        out_dir: Path,
        metadata: "Path | pd.DataFrame",
        meta_name_col: str = "NAME",
        meta_name_prefix: str = "pcp_",
        meta_lat_col: str = "LAT",
        meta_lon_col: str = "LONG",
        meta_elev_col: str = "ELEVATION",
        date_col: str = "date",
        col_map: "dict[str, str] | None" = None,
        no_data_value: float = -99.0,
        file_stem_fmt: str = "{station}",
    ) -> None:
        self.data_dir = Path(data_dir)
        self.out_dir = Path(out_dir)
        self.metadata = metadata
        self.meta_name_col = meta_name_col
        self.meta_name_prefix = meta_name_prefix
        self.meta_lat_col = meta_lat_col
        self.meta_lon_col = meta_lon_col
        self.meta_elev_col = meta_elev_col
        self.date_col = date_col
        self.col_map = {**self._DEFAULT_COL_MAP, **(col_map or {})}
        self.no_data_value = no_data_value
        self.file_stem_fmt = file_stem_fmt

    def convert(self) -> SWATPlusWeatherResult:
        qa: list[QACheck] = []
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta_df = self._load_metadata(qa)
        self.out_dir.mkdir(parents=True, exist_ok=True)

        cli_registry: dict[str, list[str]] = {spec.cli_name: [] for spec in _VAR_SPECS}
        station_results: list[SWATPlusWeatherStation] = []
        all_data_files: list[Path] = []

        for _, row in meta_df.iterrows():
            name = str(row[self.meta_name_col]).strip()
            station = name[len(self.meta_name_prefix):] if name.startswith(self.meta_name_prefix) else name
            lat  = float(row[self.meta_lat_col])
            lon  = float(row[self.meta_lon_col])
            elev = float(row[self.meta_elev_col])

            csv_path = self.data_dir / f"{station}.csv"
            if not csv_path.exists():
                station_results.append(SWATPlusWeatherStation(
                    name=station, lat=lat, lon=lon, elev=elev,
                    qa=[QACheck(name=f"swatplus:{station}:missing_csv", status="warn",
                                message=f"{station}: merged CSV not found ({csv_path.name})")],
                ))
                continue

            df = pd.read_csv(csv_path, parse_dates=[self.date_col])
            df = df.sort_values(self.date_col)
            sr = SWATPlusWeatherStation(name=station, lat=lat, lon=lon, elev=elev, n_days=len(df))
            file_stem = self.file_stem_fmt.format(station=station.lower())

            for spec in _VAR_SPECS:
                available = [c for c in spec.cols if self.col_map.get(c, c) in df.columns]
                if (spec.two_col and len(available) < 2) or (not spec.two_col and not available):
                    continue

                data_filename = f"{file_stem}{spec.ext}"
                out_path = self.out_dir / data_filename
                n_written, val_qa = self._write_data_file(df, spec, lat, lon, elev, out_path, ts, station)
                sr.files_written.append(out_path)
                all_data_files.append(out_path)
                cli_registry[spec.cli_name].append(data_filename)
                sr.qa.extend(val_qa)
                qa.extend(val_qa)
                sr.qa.append(QACheck(
                    name=f"swatplus:{station}:{spec.ext.lstrip(chr(46))}:ok",
                    status="pass",
                    message=f"{station}{spec.ext}: {n_written} days",
                ))

            if not sr.files_written:
                sr.qa.append(QACheck(name=f"swatplus:{station}:no_vars", status="warn",
                                     message=f"{station}: no matching variable columns found in {csv_path.name}"))
            station_results.append(sr)

        cli_files = self._write_cli_files(cli_registry, ts)
        n_stations = sum(1 for sr in station_results if sr.files_written)
        qa.append(QACheck(
            name="swatplus_weather_done", status="pass",
            message=(f"SWAT+ weather: {n_stations} station(s) processed, "
                     f"{len(all_data_files)} data files + {len(cli_files)} .cli files written."),
        ))
        return SWATPlusWeatherResult(stations=station_results, cli_files=cli_files,
                                     data_files=all_data_files, qa=qa)

    def _load_metadata(self, qa: list[QACheck]) -> pd.DataFrame:
        if isinstance(self.metadata, pd.DataFrame):
            df = self.metadata
        else:
            p = Path(self.metadata)
            if not p.exists():
                raise InputValidationError(f"metadata file not found: {p}")
            df = pd.read_csv(p)
        required = {self.meta_name_col, self.meta_lat_col, self.meta_lon_col, self.meta_elev_col}
        missing = required - set(df.columns)
        if missing:
            raise InputValidationError(f"metadata missing columns: {missing}")
        qa.append(QACheck(name="swatplus_meta_read", status="pass",
                          message=f"Metadata loaded: {len(df)} station(s)"))
        return df

    def _validate_data(self, df: pd.DataFrame, spec: _VarSpec, station: str) -> list[QACheck]:
        """QA warn checks: negative precip, tmax < tmin."""
        qa: list[QACheck] = []
        if spec.ext == ".pcp":
            col = self.col_map.get("precip", "precip")
            if col in df.columns:
                n_neg = int((df[col].dropna() < 0).sum())
                if n_neg:
                    qa.append(QACheck(name=f"swatplus:{station}:pcp:negative", status="warn",
                                      message=f"{station}.pcp: {n_neg} row(s) with negative precipitation."))
        elif spec.ext == ".tmp":
            tx_col = self.col_map.get("tmax", "tmax")
            tn_col = self.col_map.get("tmin", "tmin")
            if tx_col in df.columns and tn_col in df.columns:
                mask = df[tx_col].notna() & df[tn_col].notna()
                n_inv = int((df.loc[mask, tx_col] < df.loc[mask, tn_col]).sum())
                if n_inv:
                    qa.append(QACheck(name=f"swatplus:{station}:tmp:tmax_lt_tmin", status="warn",
                                      message=f"{station}.tmp: {n_inv} row(s) where tmax < tmin."))
        return qa

    def _write_data_file(
        self, df: pd.DataFrame, spec: _VarSpec,
        lat: float, lon: float, elev: float,
        out_path: Path, ts: str, station: str = "",
    ) -> tuple[int, list[QACheck]]:
        val_qa = self._validate_data(df, spec, station)
        dates = df[self.date_col]
        nbyr = int(dates.dt.year.max() - dates.dt.year.min() + 1)
        fmt3 = "{:4d}{:10d}{:10.3f}{:10.3f}{:10.3f}"
        header = [
            f"{out_path.name}: {spec.description} - file written by swatprep {ts}",
            "nbyr     tstep       lat       lon      elev",
            fmt3.format(nbyr, 0, lat, lon, elev),
        ]
        year_arr = dates.dt.year.to_numpy()
        doy_arr  = dates.dt.day_of_year.to_numpy()
        if spec.two_col:
            tx_col = self.col_map.get("tmax", "tmax")
            tn_col = self.col_map.get("tmin", "tmin")
            tx_arr = df[tx_col].fillna(self.no_data_value).to_numpy()
            tn_arr = df[tn_col].fillna(self.no_data_value).to_numpy()
            data_lines = [
                f"{y:4d}{d:5d}{tx:11.5f} {tn:11.5f}  "
                for y, d, tx, tn in zip(year_arr, doy_arr, tx_arr, tn_arr)
            ]
        else:
            col = self.col_map.get(spec.cols[0], spec.cols[0])
            val_arr = df[col].fillna(self.no_data_value).to_numpy()
            data_lines = [
                f"{y:4d}{d:5d}{v:11.5f}  "
                for y, d, v in zip(year_arr, doy_arr, val_arr)
            ]
        out_path.write_text("\n".join(header + data_lines) + "\n", encoding="utf-8")
        return len(df), val_qa

    def _write_cli_files(self, registry: dict[str, list[str]], ts: str) -> list[Path]:
        cli_paths: list[Path] = []
        spec_by_cli = {s.cli_name: s for s in _VAR_SPECS}
        for cli_name, filenames in registry.items():
            if not filenames:
                continue
            spec = spec_by_cli[cli_name]
            out_lines = [f"{cli_name}: {spec.cli_desc} - file written by swatprep {ts}",
                         "filename"] + filenames
            p = self.out_dir / cli_name
            p.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
            cli_paths.append(p)
        return cli_paths
