"""Resolve `swatprep fill weather` inputs from YAML (weather.fill) and/or CLI flags."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import SWATPrepConfig, WeatherConfig, WeatherFillConfig
from .core.fill_sources import CsvFillSource, FillSource, NetCDFFillSource
from .errors import ConfigError


@dataclass
class FillInputs:
    real_cfg: WeatherConfig
    fill_source: FillSource
    min_overlap_days: int
    out_dir: Path


def parse_var_map(text: str) -> dict[str, str]:
    """'precip=pr,tmax=tasmax' -> {'precip': 'pr', 'tmax': 'tasmax'}."""
    out: dict[str, str] = {}
    for pair in (p.strip() for p in text.split(",") if p.strip()):
        key, sep, val = pair.partition("=")
        if not (sep and key.strip() and val.strip()):
            raise ConfigError(f"Invalid --fill-var-map entry '{pair}'; expected name=ncvar")
        out[key.strip()] = val.strip()
    return out


def _put(target: dict, pairs: dict) -> dict:
    """Chép các giá trị CLI khác None vào target (CLI ghi đè YAML)."""
    target.update({k: v for k, v in pairs.items() if v is not None})
    return target


def resolve_fill_inputs(o: dict) -> FillInputs:
    """`o`: tên tuỳ chọn CLI -> giá trị (None = không truyền cờ)."""
    fill: dict = {}
    if o.get("config"):
        weather = SWATPrepConfig.from_yaml(o["config"]).weather
        if weather is None:
            raise ConfigError("The config has no 'weather' section")
        base = weather.model_dump(exclude={"fill"})
        fill = weather.fill.model_dump() if weather.fill else {}
    else:
        base = {}

    _put(base, {k: o.get(k) for k in ("stations", "data_dir", "file_pattern", "start", "end")})
    if o.get("variables"):
        base["variables"] = [v.strip() for v in o["variables"].split(",") if v.strip()]
    base["missing_policy"] = "warn"  # bước fill phải chịu được dữ liệu thiếu
    real_cfg = WeatherConfig.model_validate(base)

    _put(fill, {
        "type": o.get("fill_source_type"),
        "min_overlap_days": o.get("min_overlap_days"),
        "output_dir": o.get("out_dir"),
    })
    csv = _put(dict(fill.get("csv") or {}), {
        "stations": o.get("fill_stations"),
        "data_dir": o.get("fill_data_dir"),
        "file_pattern": o.get("fill_file_pattern"),
    })
    nc = _put(dict(fill.get("netcdf") or {}), {
        "path": o.get("fill_netcdf"),
        "lat_name": o.get("fill_lat_name"),
        "lon_name": o.get("fill_lon_name"),
        "time_name": o.get("fill_time_name"),
        "search_radius": o.get("fill_search_radius"),
        "var_map": parse_var_map(o["fill_var_map"]) if o.get("fill_var_map") else None,
    })
    fill["csv"], fill["netcdf"] = csv or None, nc or None
    fill_cfg = WeatherFillConfig.model_validate(fill)

    if fill_cfg.output_dir is None:
        raise ConfigError("Give OUT_DIR on the command line or weather.fill.output_dir in YAML")

    return FillInputs(
        real_cfg=real_cfg,
        fill_source=_build_source(fill_cfg, real_cfg),
        min_overlap_days=fill_cfg.min_overlap_days,
        out_dir=fill_cfg.output_dir,
    )


def fill_for_build(weather: WeatherConfig, qa: list) -> WeatherConfig:
    """`build` with weather.fill.run_in_build: fill the gaps, write the filled CSVs to
    weather.fill.output_dir and return a WeatherConfig that reads them (QA appended to `qa`)."""
    from .core.weather_fill import WeatherGapFiller
    from .qa import QACheck
    from .writers.weather_fill import WeatherFillWriter

    fill_cfg = weather.fill
    out = fill_cfg.output_dir
    if out is None:
        raise ConfigError("weather.fill.run_in_build needs weather.fill.output_dir")
    if weather.precip is not None or weather.temp is not None:
        raise ConfigError("weather.fill.run_in_build needs one station network "
                          "(weather.stations + weather.data_dir), not weather.precip / weather.temp")
    if weather.data_dir is not None and Path(out).resolve() == Path(weather.data_dir).resolve():
        raise ConfigError("weather.fill.output_dir must differ from weather.data_dir "
                          "(the observed files would be overwritten)")
    real = weather.model_copy(update={"fill": None, "missing_policy": "warn"})
    result = WeatherGapFiller(real, _build_source(fill_cfg, real), fill_cfg.min_overlap_days).run()
    qa.extend(result.qa)
    written = WeatherFillWriter(result, out).write()
    qa.append(QACheck(
        name="weather_fill_in_build", status="pass",
        message=f"gaps filled before building: {len(written)} file(s) written to {out}; "
                "the weather output below is built from them",
    ))
    return weather.model_copy(update={
        "stations": Path(out) / "stations.csv", "data_dir": Path(out),
        "file_pattern": "{id}.csv", "fill": None,
    })


def _build_source(fill_cfg: WeatherFillConfig, real_cfg: WeatherConfig) -> FillSource:
    if fill_cfg.type == "netcdf":
        return NetCDFFillSource(fill_cfg.netcdf)
    csv = fill_cfg.csv
    return CsvFillSource(WeatherConfig(
        stations=csv.stations, data_dir=csv.data_dir, file_pattern=csv.file_pattern,
        variables=real_cfg.variables, start=real_cfg.start, end=real_cfg.end,
        missing_policy="warn",
    ))