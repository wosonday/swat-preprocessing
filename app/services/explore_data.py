"""Read config inputs through the swatprep core for the Explore views; never raises."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from swatprep.config import SWATPrepConfig


def load_config(path: Path) -> tuple[SWATPrepConfig | None, str | None]:
    try:
        return SWATPrepConfig.from_yaml(path), None
    except ValidationError as exc:
        return None, f"Config is not valid ({exc.error_count()} problem(s)): fix it in Configure."
    except Exception as exc:  # unreadable file, bad YAML
        return None, f"Cannot read the config: {exc}"


@dataclass
class FlowView:
    daily: pd.DataFrame       # DatetimeIndex (every day) × station id; NaN = missing
    units: str = "m3s"
    error: str | None = None


def load_streamflow(cfg: SWATPrepConfig) -> FlowView:
    from swatprep.core.streamflow import StreamflowPreprocessor

    units = cfg.streamflow.units
    try:
        wide = StreamflowPreprocessor(cfg.streamflow).run().daily
    except Exception as exc:
        return FlowView(pd.DataFrame(), units, str(exc) or type(exc).__name__)
    if wide.empty:
        return FlowView(wide, units)
    days = pd.date_range(wide.index.min(), wide.index.max(), freq="D", name="date")
    return FlowView(wide.reindex(days), units)


def station_series(wide: pd.DataFrame, station: str) -> pd.Series:
    """The station's daily values from its first to its last observation."""
    s = wide[station]
    first, last = s.first_valid_index(), s.last_valid_index()
    return s.iloc[0:0] if first is None else s.loc[first:last]
