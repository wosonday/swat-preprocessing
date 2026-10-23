"""StreamflowPreprocessor: load and validate daily discharge data."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..config import StreamflowConfig
from ..errors import InputValidationError
from ..qa import QACheck


@dataclass
class StreamflowResult:
    """Output of StreamflowPreprocessor.run()."""

    daily: pd.DataFrame   # DatetimeIndex × station_id, values in cfg.units
    units: str            # "m3s" or "mm"
    qa: list[QACheck] = field(default_factory=list)


class StreamflowPreprocessor:
    """Load, validate, and normalize daily streamflow (long CSV or per-station files)."""

    def __init__(self, cfg: StreamflowConfig) -> None:
        self.cfg = cfg

    def _read_per_station(self, qa: list[QACheck]) -> pd.DataFrame:
        """Read one station file or a folder of them into the long layout.

        The station id is the file name without extension (Q_HT_0006.csv -> Q_HT_0006)."""
        cfg = self.cfg
        if cfg.path.is_dir():
            files = sorted(cfg.path.glob(cfg.glob))
        elif cfg.path.is_file():
            files = [cfg.path]
        else:
            raise InputValidationError(f"Streamflow path not found: {cfg.path}")
        if not files:
            raise InputValidationError(
                f"No files matching '{cfg.glob}' in {cfg.path} (set streamflow.glob)")
        if cfg.stations is not None:
            have = {f.stem: f for f in files}
            absent = [sid for sid in cfg.stations if sid not in have]
            if absent:
                raise InputValidationError(
                    f"streamflow.stations not found in {cfg.path}: {', '.join(absent)}")
            files = [have[sid] for sid in cfg.stations]
        parts = []
        for f in files:
            d = pd.read_csv(f)
            if cfg.date_col not in d.columns:
                raise InputValidationError(
                    f"{f.name}: date column '{cfg.date_col}' not found "
                    f"(columns: {', '.join(map(str, d.columns))})")
            if cfg.value_col in d.columns:
                col = cfg.value_col
            else:
                others = [c for c in d.columns if c != cfg.date_col]
                if len(others) != 1:
                    raise InputValidationError(
                        f"{f.name}: cannot tell which column is the flow "
                        f"(columns: {', '.join(map(str, d.columns))}); set streamflow.value_col")
                col = others[0]
            parts.append(pd.DataFrame({
                cfg.date_col: pd.to_datetime(d[cfg.date_col]),
                cfg.station_id_col: f.stem,
                cfg.value_col: d[col],
            }))
        qa.append(QACheck(
            name="streamflow_per_station_read", status="pass",
            message=f"per-station files: {len(files)} station(s) read from {cfg.path.name}"))
        return pd.concat(parts, ignore_index=True)

    def run(self) -> StreamflowResult:
        qa: list[QACheck] = []
        cfg = self.cfg

        if cfg.format == "per_station":
            df = self._read_per_station(qa)
        else:
            df = pd.read_csv(cfg.path)
            # ---- validate required columns ----------------------------
            required = {cfg.date_col, cfg.station_id_col, cfg.value_col}
            missing = required - set(df.columns)
            if missing:
                raise InputValidationError(
                    f"Streamflow CSV missing columns: {', '.join(sorted(missing))} "
                    f"(the file has: {', '.join(map(str, df.columns))}). If each file is ONE station "
                    "(columns date + discharge), set streamflow.format: per_station; otherwise "
                    "set date_col / station_id_col / value_col."
                )
            df[cfg.date_col] = pd.to_datetime(df[cfg.date_col])
            if cfg.stations is not None:
                df[cfg.station_id_col] = df[cfg.station_id_col].astype(str)
                absent = [sid for sid in cfg.stations if sid not in set(df[cfg.station_id_col])]
                if absent:
                    raise InputValidationError(
                        f"streamflow.stations not found in {cfg.path.name}: {', '.join(absent)}")
                df = df[df[cfg.station_id_col].isin(cfg.stations)]

        # ---- coerce value to numeric ----------------------------------
        df[cfg.value_col] = pd.to_numeric(df[cfg.value_col], errors="coerce")

        # ---- pivot to wide --------------------------------------------
        # Use pivot() not pivot_table() so NaN values are preserved
        wide = df.pivot(
            index=cfg.date_col,
            columns=cfg.station_id_col,
            values=cfg.value_col,
        )
        wide.index = pd.DatetimeIndex(wide.index)
        wide.index.name = "date"
        wide = wide.sort_index()
        wide.columns.name = None  # clean up MultiIndex remnant

        stations = list(wide.columns)

        # ---- missing value checks ------------------------------------
        for sid in stations:
            missing_pct = wide[sid].isna().mean() * 100
            if missing_pct > 0:
                qa.append(QACheck(
                    name=f"missing:streamflow:{sid}",
                    status="warn",
                    message=f"Station {sid}: {missing_pct:.1f}% missing values",
                    context={"station": sid, "missing_pct": round(missing_pct, 2)},
                ))

        # ---- negative value check ------------------------------------
        neg_count = int((wide < 0).sum().sum())
        if neg_count > 0:
            qa.append(QACheck(
                name="streamflow_negative",
                status="warn",
                message=f"{neg_count} negative discharge value(s) found",
                context={"count": neg_count},
            ))

        qa.append(QACheck(
            name="streamflow_loaded",
            status="pass",
            message=(
                f"{len(wide)} days × {len(stations)} station(s) loaded, "
                f"units={cfg.units}"
            ),
        ))

        return StreamflowResult(daily=wide, units=cfg.units, qa=qa)
