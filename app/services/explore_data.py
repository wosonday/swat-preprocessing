"""Read config inputs through the swatprep core for the Explore views; never raises."""
from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class WeatherView:
    stations: pd.DataFrame = field(default_factory=pd.DataFrame)   # id (index), name, lat, lon, elev
    observed: dict[str, pd.DataFrame] = field(default_factory=dict)  # variable -> every day × station; NaN = missing
    filled: dict[str, pd.DataFrame] | None = None                 # same shape, from weather.fill.output_dir
    fill_report: pd.DataFrame | None = None
    fill_note: str | None = None                                  # why there is no filled data
    error: str | None = None


def load_weather(cfg: SWATPrepConfig) -> WeatherView:
    """Observed data as Build reads it (missing days kept as NaN) and, if present, the gap-filled copy."""
    from swatprep.core.weather import WeatherPreprocessor

    weather = cfg.weather.model_copy(update={"missing_policy": "warn", "fill": None})
    try:
        result = WeatherPreprocessor(weather).run()
    except Exception as exc:
        return WeatherView(error=str(exc) or type(exc).__name__)
    view = WeatherView(stations=result.stations, observed=result.daily)

    fill = cfg.weather.fill
    out = fill.output_dir if fill is not None else None
    if out is None:
        return view
    if weather.data_dir is not None and Path(out).resolve() == Path(weather.data_dir).resolve():
        view.fill_note = "weather.data_dir already points at the filled data, so Observed shows the filled values."
        return view
    if not (out / "stations.csv").is_file():
        view.fill_note = "No filled data yet: run Build with weather.fill.run_in_build, or `swatprep fill weather`."
        return view
    filled_cfg = weather.model_copy(update={"stations": out / "stations.csv", "data_dir": out,
                                            "file_pattern": "{id}.csv", "precip": None, "temp": None})
    try:
        view.filled = WeatherPreprocessor(filled_cfg).run().daily
    except Exception as exc:
        view.fill_note = f"Cannot read the filled data: {exc}"
        return view
    report = out / "fill_report.csv"
    view.fill_report = pd.read_csv(report, dtype={"station_id": str}) if report.is_file() else None
    return view
