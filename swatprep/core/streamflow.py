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
    """Load, validate, and normalize daily streamflow from a long-format CSV."""

    def __init__(self, cfg: StreamflowConfig) -> None:
        self.cfg = cfg

    def run(self) -> StreamflowResult:
        qa: list[QACheck] = []
        cfg = self.cfg

        df = pd.read_csv(cfg.path, parse_dates=[cfg.date_col])

        # ---- validate required columns --------------------------------
        required = {cfg.date_col, cfg.station_id_col, cfg.value_col}
        missing = required - set(df.columns)
        if missing:
            raise InputValidationError(
                f"Streamflow CSV missing columns: {', '.join(sorted(missing))}"
            )

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
