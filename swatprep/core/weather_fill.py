"""WeatherGapFiller: fill missing days in observed weather station data from
an external bias-corrected source (e.g. satellite/reanalysis, already
extracted by the user into swatprep's per-station CSV format at each real
station's coordinates -- swatprep does not fetch or extract external data
itself).

Reuses WeatherPreprocessor to load both the real and fill sources, so this
module only implements the bias-correction and fill logic. See
docs/superpowers/specs/2026-09-01-weather-gap-fill-design.md for the design.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import pandas as pd

from ..config import WeatherConfig
from ..qa import QACheck
from .weather import WeatherPreprocessor
from .fill_sources import CsvFillSource, FillSource

_RATIO_VARS = {"precip"}


@dataclass
class WeatherFillResult:
    """Output of WeatherGapFiller.run()."""

    stations: pd.DataFrame          # id(index), name, lat, lon, elev -- from the real source
    daily: dict[str, pd.DataFrame]  # {variable: filled wide_df} -- same shape as WeatherResult.daily
    report: pd.DataFrame            # station_id, variable, n_missing, n_filled, n_still_missing,
                                     # n_overlap, correction_type, correction_value, status,
                                     # correction_from, distance_km (virtual stations only)
    qa: list[QACheck] = field(default_factory=list)


def _correct_and_fill(
    obs: pd.Series, fill: pd.Series, var: str, min_overlap_days: int,
) -> tuple[pd.Series, dict]:
    """Bias-correct `fill` against `obs` using their overlap period, then
    fill only `obs`'s missing days from the corrected values.

    Never modifies a day `obs` already has a value for. Returns
    (filled_series, report_dict).
    """
    n_missing = int(obs.isna().sum())
    report = {
        "n_missing": n_missing,
        "n_filled": 0,
        "n_still_missing": n_missing,
        "n_overlap": 0,
        "correction_type": None,
        "correction_value": None,
        "status": "pass",
    }

    if n_missing == 0:
        return obs.copy(), report

    overlap_mask = obs.notna() & fill.notna()
    n_overlap = int(overlap_mask.sum())
    report["n_overlap"] = n_overlap

    if n_overlap == 0:
        report["status"] = "warn"
        return obs.copy(), report

    if var in _RATIO_VARS:
        mean_fill = fill[overlap_mask].mean()
        if mean_fill <= 0:
            report["status"] = "warn"
            return obs.copy(), report
        correction_value = obs[overlap_mask].mean() / mean_fill
        correction_type = "ratio"
    else:
        correction_value = obs[overlap_mask].mean() - fill[overlap_mask].mean()
        correction_type = "offset"

    missing_mask = obs.isna() & fill.notna()
    if correction_type == "ratio":
        fill_values = (fill[missing_mask] * correction_value).clip(lower=0)
    else:
        fill_values = fill[missing_mask] + correction_value

    filled = obs.copy()
    filled.loc[fill_values.index] = fill_values

    n_filled = int(len(fill_values))
    report["n_filled"] = n_filled
    report["n_still_missing"] = n_missing - n_filled
    report["correction_type"] = correction_type
    report["correction_value"] = correction_value
    if n_overlap < min_overlap_days:
        report["status"] = "warn"
    if correction_type == "ratio" and correction_value == 0:
        report["status"] = "warn"

    return filled, report


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km on a sphere of radius 6371.0088 km (mean Earth radius)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def _fill_ungauged(obs: pd.Series, fill: pd.Series, correction: tuple[str, float] | None) -> tuple[pd.Series, dict]:
    """A station with no observed day: every day from `fill`, corrected with a borrowed
    (type, value) or raw when `correction` is None."""
    n_missing = int(obs.isna().sum())
    kind, value = correction if correction else ("none", None)
    values = fill[fill.notna()]
    if kind == "ratio":
        values = values * value
    elif kind == "offset":
        values = values + value
    if kind in ("ratio", "none") and fill.name in _RATIO_VARS:
        values = values.clip(lower=0)
    filled = obs.copy()
    filled.loc[values.index] = values
    return filled, {
        "n_missing": n_missing, "n_filled": len(values), "n_still_missing": n_missing - len(values),
        "n_overlap": 0, "correction_type": kind, "correction_value": value, "status": "warn",
    }


class WeatherGapFiller:
    """Fill missing days in a real WeatherConfig's station data using a
    second, external-source WeatherConfig, via bias correction computed
    from each station's overlap period.
    """

    def __init__(
            self,
            real_cfg: WeatherConfig,
            fill_source: FillSource | WeatherConfig,
            min_overlap_days: int = 10,
            fill_ungauged: bool = False,
            correct_ungauged: bool = True,
            max_borrow_km: float = 50.0,
            ) -> None:
        if isinstance(fill_source, WeatherConfig):  # tương thích ngược
            fill_source = CsvFillSource(fill_source)
        self.real_cfg = real_cfg
        self.fill_source = fill_source
        self.min_overlap_days = min_overlap_days
        self.fill_ungauged = fill_ungauged
        self.correct_ungauged = correct_ungauged
        self.max_borrow_km = max_borrow_km

    def run(self) -> WeatherFillResult:
        qa: list[QACheck] = []
        real_result = WeatherPreprocessor(self.real_cfg).run()
        fill_daily, fill_qa = self.fill_source.load(
            real_result.stations,
            next(iter(real_result.daily.values())).index,
            list(real_result.daily),
            )

        # Propagate QA from both upstream WeatherPreprocessor runs (e.g. a
        # station's data file entirely missing, or missing a requested
        # variable column) instead of silently discarding it. Any "fail" is
        # downgraded to "warn" here -- one bad station in either source must
        # not block the rest of the gap-fill run.
        for check in [*real_result.qa, *fill_qa]:
            if check.status == "fail":
                qa.append(replace(check, status="warn"))
            else:
                qa.append(check)

        filled_daily: dict[str, pd.DataFrame] = {}
        report_rows: list[dict] = []

        for var, obs_wide in real_result.daily.items():
            fill_wide = fill_daily.get(var)
            if self.fill_ungauged:   # a listed station without a data file is a virtual station too
                absent = [sid for sid in real_result.stations.index if sid not in obs_wide.columns]
                obs_wide = obs_wide.reindex(columns=[*obs_wide.columns, *absent])
            filled_wide = obs_wide.copy()
            donors: dict[str, tuple[str, float]] = {}   # gauged station -> its passing (type, value)
            ungauged: list[str] = []

            for sid in obs_wide.columns:
                obs = obs_wide[sid]
                if self.fill_ungauged and obs.notna().sum() == 0 and fill_wide is not None \
                        and sid in fill_wide.columns:
                    ungauged.append(sid)   # second pass, once every gauged correction is known
                    continue

                if fill_wide is None or sid not in fill_wide.columns:
                    n_missing = int(obs.isna().sum())
                    if n_missing:
                        qa.append(QACheck(
                            name=f"weather_fill:{var}:{sid}:no_fill_source",
                            status="warn",
                            message=(
                                f"{sid}: no fill source available for '{var}', "
                                f"{n_missing} day(s) remain missing"
                            ),
                        ))
                    report_rows.append({
                        "station_id": sid, "variable": var,
                        "n_missing": n_missing, "n_filled": 0,
                        "n_still_missing": n_missing, "n_overlap": 0,
                        "correction_type": None, "correction_value": None,
                        "status": "warn" if n_missing else "pass",
                    })
                    continue

                filled_series, report = _correct_and_fill(
                    obs, fill_wide[sid], var, self.min_overlap_days,
                )
                filled_wide[sid] = filled_series
                if report["status"] == "pass" and report["correction_type"] is not None:
                    donors[sid] = (report["correction_type"], report["correction_value"])

                if report["status"] == "warn":
                    if report["n_overlap"] == 0:
                        msg = f"{sid}: no overlap for '{var}', cannot compute correction"
                    elif report["correction_type"] is None:
                        msg = (
                            f"{sid}: cannot compute precip ratio for '{var}' "
                            f"(fill-source mean is zero over overlap)"
                        )
                    elif report["correction_type"] == "ratio" and report["correction_value"] == 0:
                        msg = (
                            f"{sid}: '{var}' fill applied with a zero correction factor -- "
                            f"real station recorded no precipitation over the overlap period, "
                            f"all filled days will be 0.0"
                        )
                    else:
                        msg = (
                            f"{sid}: low confidence for '{var}' -- "
                            f"only {report['n_overlap']} overlap day(s)"
                        )
                    qa.append(QACheck(
                        name=f"weather_fill:{var}:{sid}:low_confidence",
                        status="warn",
                        message=msg,
                    ))

                report_rows.append({"station_id": sid, "variable": var, **report})

            for sid in ungauged:
                report = self._fill_virtual(sid, var, obs_wide, fill_wide, filled_wide, donors,
                                            real_result.stations, qa)
                report_rows.append({"station_id": sid, "variable": var, **report})

            filled_daily[var] = filled_wide

        qa.append(QACheck(
            name="weather_fill_done",
            status="pass",
            message=f"Gap-fill complete: {len(report_rows)} station x variable combination(s) processed",
        ))

        report = pd.DataFrame(report_rows)
        for col in ("correction_from", "distance_km"):
            if col not in report.columns:
                report[col] = None
        return WeatherFillResult(
            stations=real_result.stations,
            daily=filled_daily,
            report=report,
            qa=qa,
        )

    def _fill_virtual(self, sid, var, obs_wide, fill_wide, filled_wide, donors, stations, qa) -> dict:
        """Fill a station with no observed day; borrow the nearest donor's correction within range."""
        donor, distance = None, None
        if self.correct_ungauged and donors:
            here = stations.loc[sid]
            distance, donor = min(
                (haversine_km(here["lat"], here["lon"], stations.loc[d, "lat"], stations.loc[d, "lon"]), d)
                for d in donors
            )
            if distance > self.max_borrow_km:
                donor, distance = None, None
        series = fill_wide[sid].rename(var)
        filled, report = _fill_ungauged(obs_wide[sid], series, donors[donor] if donor else None)
        filled_wide[sid] = filled
        if donor:
            how = f"with the correction of station {donor} ({distance:.1f} km)"
        elif not self.correct_ungauged:
            how = "with raw source values (correction off)"
        else:
            how = f"with raw source values (no gauged station within {self.max_borrow_km:g} km)"
        qa.append(QACheck(
            name=f"weather_fill:{var}:{sid}:virtual_station", status="warn",
            message=f"{sid}: no observations for '{var}'; {report['n_filled']} day(s) filled from the source {how}",
        ))
        return {**report, "correction_from": donor, "distance_km": round(distance, 2) if donor else None}
