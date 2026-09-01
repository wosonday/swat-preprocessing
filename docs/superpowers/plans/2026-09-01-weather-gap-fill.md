# Weather Gap-Fill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone `swatprep fill weather` step that fills missing days in observed station data using a bias-corrected external source (satellite/reanalysis, pre-extracted by the user into swatprep's own per-station CSV format), writing output that drops straight into `weather.data_dir` for the normal `build()` pipeline.

**Architecture:** Reuse `WeatherConfig`/`WeatherPreprocessor` to load both the real and the external-fill station data into `daily: dict[str, pd.DataFrame]` (identical `DatetimeIndex`, since both loads share the same `start`/`end`). A new `WeatherGapFiller` computes one bias-correction value per station × variable from the overlap period (ratio for `precip`, additive offset otherwise) and fills only the real station's missing days. A new `WeatherFillWriter` writes the result back out as `stations.csv` + `{id}.csv` per station + `fill_report.csv`, in the same shape `WeatherPreprocessor` already reads.

**Tech Stack:** Python 3.10+, pandas, Click, pytest (existing stack — no new dependencies).

## Global Constraints

- Match existing code style: `from __future__ import annotations`, type hints, dataclasses for result types.
- No new third-party dependencies.
- Reuse `WeatherConfig` / `WeatherPreprocessor` for loading both sources — do not reimplement CSV reading, reindexing, or per-station column matching.
- Bias correction only: multiplicative ratio for `precip` (`factor = mean(obs[overlap]) / mean(fill[overlap])`, clipped `>= 0`, skipped if `mean(fill[overlap]) <= 0`), additive offset for `tmax`/`tmin`/`solar`/`humidity`/`wind` (`offset = mean(obs[overlap]) - mean(fill[overlap])`). One overall value per station per variable — no monthly granularity.
- A day the real station already has a value for is never overwritten, under any circumstance.
- `--min-overlap-days` (default `10`): overlap `> 0` but below threshold still fills, QA status `"warn"`. Overlap `== 0` skips filling entirely for that station/variable (stays `NaN`), QA status `"warn"`. The "correction is mathematically undefined" check (`mean(fill[overlap]) <= 0` for precip) is independent of this threshold and checked first.
- A real station with no matching `id` in the fill source is a `QACheck(status="warn")`, not an error — one bad station never blocks the rest.
- This stays a separate, explicit CLI step (`swatprep fill weather`), run before `build()` — not wired into the config-driven pipeline.
- No raster/NetCDF fill sources, no automatic data download, no streamflow gap-filling — out of scope for this plan.
- Run tests with `uv run pytest tests/<file> -v` from the worktree root.
- Design spec (source of truth for all decisions below): `docs/superpowers/specs/2026-09-01-weather-gap-fill-design.md`.

---

## Task 1: `WeatherGapFiller` — bias correction and fill logic

**Files:**
- Create: `swatprep/core/weather_fill.py`
- Test: `tests/test_weather_fill.py`

**Interfaces:**
- Consumes: `WeatherConfig` (`swatprep/config.py`), `WeatherPreprocessor` (`swatprep/core/weather.py`, unchanged — `WeatherPreprocessor(cfg).run() -> WeatherResult` with `.stations: pd.DataFrame` and `.daily: dict[str, pd.DataFrame]`), `QACheck` (`swatprep/qa.py`).
- Produces: `WeatherFillResult` dataclass (`stations: pd.DataFrame`, `daily: dict[str, pd.DataFrame]`, `report: pd.DataFrame`, `qa: list[QACheck]`) and `WeatherGapFiller(real_cfg: WeatherConfig, fill_cfg: WeatherConfig, min_overlap_days: int = 10)` with `.run() -> WeatherFillResult` — used by Task 2 (writer) and Task 3 (CLI).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_weather_fill.py`:

```python
"""Tests for WeatherGapFiller (swatprep/core/weather_fill.py)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_stations_csv(tmp_path: Path, filename: str, rows: list[dict]) -> Path:
    df = pd.DataFrame(rows)
    p = tmp_path / filename
    df.to_csv(p, index=False)
    return p


def _write_station_csv(data_dir: Path, station_id: str, dates: list[str], **cols) -> None:
    data = {"date": dates}
    data.update(cols)
    pd.DataFrame(data).to_csv(data_dir / f"{station_id}.csv", index=False)


_META = {"name": "StationS1", "lat": 15.0, "lon": 105.0, "elev": 100}


class TestWeatherGapFillerPrecipRatio:
    def test_ratio_correction_fills_precip_and_preserves_real_values(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02", "2000-01-03", "2000-01-04", "2000-01-05", "2000-01-06"]
        _write_station_csv(real_dir, "S1", dates, precip=[2.0, None, 4.0, None, 6.0, 3.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[1.0, 5.0, 2.0, 10.0, 3.0, 1.5])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-06", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-06", missing_policy="warn",
        )

        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()

        filled = result.daily["precip"]["S1"]
        assert filled.iloc[0] == 2.0                    # real value untouched
        assert filled.iloc[1] == pytest.approx(10.0)     # 5.0 * factor(2.0)
        assert filled.iloc[2] == 4.0                     # real value untouched
        assert filled.iloc[3] == pytest.approx(20.0)     # 10.0 * factor(2.0)

        row = result.report[
            (result.report["station_id"] == "S1") & (result.report["variable"] == "precip")
        ].iloc[0]
        assert row["n_missing"] == 2
        assert row["n_filled"] == 2
        assert row["n_still_missing"] == 0
        assert row["n_overlap"] == 4
        assert row["correction_type"] == "ratio"
        assert row["correction_value"] == pytest.approx(2.0)
        assert row["status"] == "pass"

    def test_precip_zero_fill_mean_skips_correction(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02"]
        _write_station_csv(real_dir, "S1", dates, precip=[1.0, None])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[0.0, 0.0])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-02", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-02", missing_policy="warn",
        )

        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()

        filled = result.daily["precip"]["S1"]
        assert pd.isna(filled.iloc[1])

        row = result.report.iloc[0]
        assert row["n_missing"] == 1
        assert row["n_filled"] == 0
        assert row["n_overlap"] == 1
        assert row["status"] == "warn"


class TestWeatherGapFillerTemperatureOffset:
    def test_offset_correction_fills_temperature(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02", "2000-01-03", "2000-01-04", "2000-01-05", "2000-01-06"]
        _write_station_csv(real_dir, "S1", dates, tmax=[20.0, None, 24.0, None, 28.0, 22.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, tmax=[15.0, 19.0, 19.0, 23.0, 23.0, 17.0])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["tmax"],
            start="2000-01-01", end="2000-01-06", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["tmax"],
            start="2000-01-01", end="2000-01-06", missing_policy="warn",
        )

        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()

        filled = result.daily["tmax"]["S1"]
        assert filled.iloc[0] == 20.0                   # real value untouched
        assert filled.iloc[1] == pytest.approx(24.0)     # 19.0 + offset(5.0)
        assert filled.iloc[3] == pytest.approx(28.0)     # 23.0 + offset(5.0)

        row = result.report.iloc[0]
        assert row["correction_type"] == "offset"
        assert row["correction_value"] == pytest.approx(5.0)
        assert row["status"] == "pass"


class TestWeatherGapFillerOverlapEdgeCases:
    def test_zero_overlap_skips_fill(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02"]
        _write_station_csv(real_dir, "S1", dates, precip=[None, 5.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[3.0, None])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-02", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-02", missing_policy="warn",
        )

        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()

        filled = result.daily["precip"]["S1"]
        assert pd.isna(filled.iloc[0])

        row = result.report.iloc[0]
        assert row["n_missing"] == 1
        assert row["n_filled"] == 0
        assert row["n_overlap"] == 0
        assert row["status"] == "warn"

    def test_low_overlap_below_threshold_warns_but_still_fills(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02", "2000-01-03"]
        _write_station_csv(real_dir, "S1", dates, precip=[2.0, None, 4.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[1.0, 5.0, 2.0])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-03", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-03", missing_policy="warn",
        )

        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=5).run()

        filled = result.daily["precip"]["S1"]
        assert filled.iloc[1] == pytest.approx(10.0)   # 5.0 * factor(2.0) -- still filled

        row = result.report.iloc[0]
        assert row["n_overlap"] == 2
        assert row["n_filled"] == 1
        assert row["status"] == "warn"                 # below min_overlap_days=5

    def test_station_missing_from_fill_source_warns_and_skips(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller
        from swatprep.qa import warnings

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [
            {"id": "S1", **_META},
            {"id": "S2", "name": "StationS2", "lat": 15.1, "lon": 105.1, "elev": 110},
        ])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02"]
        _write_station_csv(real_dir, "S1", dates, precip=[1.0, 2.0])
        _write_station_csv(real_dir, "S2", dates, precip=[None, 3.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[1.5, 2.5])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-02", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-02", missing_policy="warn",
        )

        result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()

        filled_s2 = result.daily["precip"]["S2"]
        assert pd.isna(filled_s2.iloc[0])

        row = result.report[result.report["station_id"] == "S2"].iloc[0]
        assert row["n_missing"] == 1
        assert row["n_filled"] == 0
        assert row["status"] == "warn"

        assert any("S2" in c.message and "no fill source" in c.message for c in warnings(result.qa))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_weather_fill.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swatprep.core.weather_fill'`.

- [ ] **Step 3: Write the implementation**

Create `swatprep/core/weather_fill.py`:

```python
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

from dataclasses import dataclass, field

import pandas as pd

from ..config import WeatherConfig
from ..qa import QACheck
from .weather import WeatherPreprocessor

_RATIO_VARS = {"precip"}


@dataclass
class WeatherFillResult:
    """Output of WeatherGapFiller.run()."""

    stations: pd.DataFrame          # id(index), name, lat, lon, elev -- from the real source
    daily: dict[str, pd.DataFrame]  # {variable: filled wide_df} -- same shape as WeatherResult.daily
    report: pd.DataFrame            # station_id, variable, n_missing, n_filled, n_still_missing,
                                     # n_overlap, correction_type, correction_value, status
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

    return filled, report


class WeatherGapFiller:
    """Fill missing days in a real WeatherConfig's station data using a
    second, external-source WeatherConfig, via bias correction computed
    from each station's overlap period.
    """

    def __init__(
        self,
        real_cfg: WeatherConfig,
        fill_cfg: WeatherConfig,
        min_overlap_days: int = 10,
    ) -> None:
        self.real_cfg = real_cfg
        self.fill_cfg = fill_cfg
        self.min_overlap_days = min_overlap_days

    def run(self) -> WeatherFillResult:
        qa: list[QACheck] = []
        real_result = WeatherPreprocessor(self.real_cfg).run()
        fill_result = WeatherPreprocessor(self.fill_cfg).run()

        filled_daily: dict[str, pd.DataFrame] = {}
        report_rows: list[dict] = []

        for var, obs_wide in real_result.daily.items():
            fill_wide = fill_result.daily.get(var)
            filled_wide = obs_wide.copy()

            for sid in obs_wide.columns:
                obs = obs_wide[sid]

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

                if report["status"] == "warn":
                    if report["n_overlap"] == 0:
                        msg = f"{sid}: no overlap for '{var}', cannot compute correction"
                    elif report["correction_type"] is None:
                        msg = (
                            f"{sid}: cannot compute precip ratio for '{var}' "
                            f"(fill-source mean is zero over overlap)"
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

            filled_daily[var] = filled_wide

        qa.append(QACheck(
            name="weather_fill_done",
            status="pass",
            message=f"Gap-fill complete: {len(report_rows)} station x variable combination(s) processed",
        ))

        return WeatherFillResult(
            stations=real_result.stations,
            daily=filled_daily,
            report=pd.DataFrame(report_rows),
            qa=qa,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_weather_fill.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add swatprep/core/weather_fill.py tests/test_weather_fill.py
git commit -m "feat: add WeatherGapFiller bias-correction and fill logic"
```

---

## Task 2: `WeatherFillWriter` — write filled output in swatprep-native format

**Files:**
- Create: `swatprep/writers/weather_fill.py`
- Test: `tests/test_weather_fill.py` (append)

**Interfaces:**
- Consumes: `WeatherFillResult` (Task 1).
- Produces: `WeatherFillWriter(result: WeatherFillResult, output_dir: Path)` with `.write() -> list[Path]` — used by Task 3 (CLI).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_weather_fill.py`:

```python
class TestWeatherFillWriter:
    def _build_result(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather_fill import WeatherGapFiller

        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02", "2000-01-03"]
        _write_station_csv(real_dir, "S1", dates, precip=[2.0, None, 4.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[1.0, 5.0, 2.0])

        real_cfg = WeatherConfig(
            stations=real_sta, data_dir=real_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-03", missing_policy="warn",
        )
        fill_cfg = WeatherConfig(
            stations=fill_sta, data_dir=fill_dir, variables=["precip"],
            start="2000-01-01", end="2000-01-03", missing_policy="warn",
        )
        return WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=1).run()

    def test_writes_stations_station_files_and_report(self, tmp_path):
        from swatprep.writers.weather_fill import WeatherFillWriter

        result = self._build_result(tmp_path)
        out = tmp_path / "out"
        written = WeatherFillWriter(result, out).write()

        assert (out / "stations.csv") in written
        assert (out / "S1.csv") in written
        assert (out / "fill_report.csv") in written

    def test_station_csv_format_matches_native_convention(self, tmp_path):
        from swatprep.writers.weather_fill import WeatherFillWriter

        result = self._build_result(tmp_path)
        out = tmp_path / "out"
        WeatherFillWriter(result, out).write()

        df = pd.read_csv(out / "S1.csv")
        assert list(df.columns) == ["date", "precip"]
        assert df["date"].iloc[0] == "2000-01-01"
        assert df["precip"].iloc[0] == 2.0
        assert df["precip"].iloc[1] == pytest.approx(10.0)  # filled value

    def test_stations_csv_has_native_columns(self, tmp_path):
        from swatprep.writers.weather_fill import WeatherFillWriter

        result = self._build_result(tmp_path)
        out = tmp_path / "out"
        WeatherFillWriter(result, out).write()

        df = pd.read_csv(out / "stations.csv")
        assert list(df.columns) == ["id", "name", "lat", "lon", "elev"]
        assert df["id"].iloc[0] == "S1"

    def test_round_trip_loadable_by_weather_preprocessor(self, tmp_path):
        from swatprep.config import WeatherConfig
        from swatprep.core.weather import WeatherPreprocessor
        from swatprep.writers.weather_fill import WeatherFillWriter
        from swatprep.qa import failures

        result = self._build_result(tmp_path)
        out = tmp_path / "out"
        WeatherFillWriter(result, out).write()

        reload_cfg = WeatherConfig(
            stations=out / "stations.csv", data_dir=out, variables=["precip"],
            start="2000-01-01", end="2000-01-03", missing_policy="fail",
        )
        reloaded = WeatherPreprocessor(reload_cfg).run()

        assert failures(reloaded.qa) == []
        precip = reloaded.daily["precip"]["S1"]
        assert precip.isna().sum() == 0  # the filled day introduced no new gap
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_weather_fill.py -v -k Writer`
Expected: FAIL with `ModuleNotFoundError: No module named 'swatprep.writers.weather_fill'`.

- [ ] **Step 3: Write the implementation**

Create `swatprep/writers/weather_fill.py`:

```python
"""WeatherFillWriter: write a WeatherFillResult back out in swatprep's
native per-station CSV format (the same shape WeatherPreprocessor already
reads), ready to point weather.data_dir at.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..core.weather_fill import WeatherFillResult


class WeatherFillWriter:
    """Write a WeatherFillResult as stations.csv + {id}.csv per station +
    fill_report.csv."""

    def __init__(self, result: WeatherFillResult, output_dir: Path) -> None:
        self.result = result
        self.output_dir = output_dir

    def write(self) -> list[Path]:
        out = self.output_dir
        out.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []

        stations = self.result.stations
        sta_path = out / "stations.csv"
        stations.reset_index().to_csv(sta_path, index=False)
        written.append(sta_path)

        variables = list(self.result.daily.keys())
        for sid in stations.index:
            cols: dict[str, pd.Series] = {}
            for var in variables:
                wide = self.result.daily[var]
                if sid in wide.columns:
                    cols[var] = wide[sid]
            if not cols:
                continue
            df = pd.DataFrame(cols)
            df.index.name = "date"
            path = out / f"{sid}.csv"
            df.reset_index().to_csv(path, index=False, date_format="%Y-%m-%d")
            written.append(path)

        report_path = out / "fill_report.csv"
        self.result.report.to_csv(report_path, index=False)
        written.append(report_path)

        return written
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_weather_fill.py -v`
Expected: all 10 tests PASS (6 from Task 1 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add swatprep/writers/weather_fill.py tests/test_weather_fill.py
git commit -m "feat: add WeatherFillWriter for swatprep-native filled output"
```

---

## Task 3: `swatprep fill weather` CLI command

**Files:**
- Modify: `swatprep/cli.py`
- Test: `tests/test_weather_fill.py` (append)

**Interfaces:**
- Consumes: `WeatherConfig` (`swatprep/config.py`), `WeatherGapFiller` (Task 1), `WeatherFillWriter` (Task 2).
- Produces: `swatprep fill weather [OPTIONS] OUT_DIR` CLI command.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_weather_fill.py`:

```python
class TestCLIFillWeather:
    def _build_inputs(self, tmp_path):
        real_sta = _write_stations_csv(tmp_path, "real_stations.csv", [{"id": "S1", **_META}])
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        dates = ["2000-01-01", "2000-01-02", "2000-01-03"]
        _write_station_csv(real_dir, "S1", dates, precip=[2.0, None, 4.0])

        fill_sta = _write_stations_csv(tmp_path, "fill_stations.csv", [{"id": "S1", **_META}])
        fill_dir = tmp_path / "fill"
        fill_dir.mkdir()
        _write_station_csv(fill_dir, "S1", dates, precip=[1.0, 5.0, 2.0])

        return real_sta, real_dir, fill_sta, fill_dir

    def test_cli_fill_weather_help(self):
        from click.testing import CliRunner
        from swatprep.cli import main

        runner = CliRunner()
        res = runner.invoke(main, ["fill", "weather", "--help"])
        assert res.exit_code == 0
        assert "--fill-stations" in res.output

    def test_cli_fill_weather_runs_end_to_end(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        real_sta, real_dir, fill_sta, fill_dir = self._build_inputs(tmp_path)
        out = tmp_path / "out"
        runner = CliRunner()
        res = runner.invoke(main, [
            "fill", "weather",
            "--stations", str(real_sta), "--data-dir", str(real_dir),
            "--fill-stations", str(fill_sta), "--fill-data-dir", str(fill_dir),
            "--variables", "precip",
            "--start", "2000-01-01", "--end", "2000-01-03",
            "--min-overlap-days", "1",
            str(out),
        ])

        assert res.exit_code == 0, res.output
        assert (out / "stations.csv").exists()
        assert (out / "S1.csv").exists()
        assert (out / "fill_report.csv").exists()

        df = pd.read_csv(out / "S1.csv")
        assert df["precip"].iloc[1] == pytest.approx(10.0)

    def test_cli_fill_weather_missing_required_option_fails(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        real_sta, real_dir, _fill_sta, _fill_dir = self._build_inputs(tmp_path)
        out = tmp_path / "out"
        runner = CliRunner()
        res = runner.invoke(main, [
            "fill", "weather",
            "--stations", str(real_sta), "--data-dir", str(real_dir),
            "--variables", "precip",
            "--start", "2000-01-01", "--end", "2000-01-03",
            str(out),
        ])

        assert res.exit_code != 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_weather_fill.py -v -k CLI`
Expected: FAIL — `fill` is not a recognized command group yet.

- [ ] **Step 3: Add the `fill weather` command to `swatprep/cli.py`**

In `swatprep/cli.py`, update the module docstring's command list (lines 5–12) from:

```python
"""Click-based CLI for swatprep.

Entry point: swatprep (registered in pyproject.toml)

Commands:
    swatprep validate config.yaml
    swatprep build config.yaml [--only DOMAIN]
    swatprep inspect raster PATH
    swatprep inspect weather PATH
    swatprep convert climate DATA_DIR OUT_DIR
    swatprep convert streamflow SOURCE OUT_PATH
    swatprep convert weather [--pcp-master ... --pcp-dir ...] [--tmp-master ... --tmp-dir ...] OUT_DIR
"""
```

to:

```python
"""Click-based CLI for swatprep.

Entry point: swatprep (registered in pyproject.toml)

Commands:
    swatprep validate config.yaml
    swatprep build config.yaml [--only DOMAIN]
    swatprep inspect raster PATH
    swatprep inspect weather PATH
    swatprep convert climate DATA_DIR OUT_DIR
    swatprep convert streamflow SOURCE OUT_PATH
    swatprep convert weather [--pcp-master ... --pcp-dir ...] [--tmp-master ... --tmp-dir ...] OUT_DIR
    swatprep fill weather --stations ... --data-dir ... --fill-stations ... --fill-data-dir ... OUT_DIR
"""
```

Then, immediately before the final `if __name__ == "__main__":` block (currently the last two lines of the file), add:

```python
# ---------------------------------------------------------------------------
# fill
# ---------------------------------------------------------------------------


@main.group()
def fill() -> None:
    """Fill gaps in observed data using an external bias-corrected source."""


@fill.command("weather")
@click.option("--stations", type=click.Path(exists=True, path_type=Path), required=True,
              help="Station metadata CSV for the real (observed) data (id,name,lat,lon,elev).")
@click.option("--data-dir", type=click.Path(exists=True, path_type=Path), required=True,
              help="Directory of real per-station daily CSVs.")
@click.option("--file-pattern", default="{id}.csv", show_default=True,
              help="Filename pattern for real station files.")
@click.option("--fill-stations", type=click.Path(exists=True, path_type=Path), required=True,
              help="Station metadata CSV for the external fill source (same station ids as --stations).")
@click.option("--fill-data-dir", type=click.Path(exists=True, path_type=Path), required=True,
              help="Directory of external fill-source per-station daily CSVs.")
@click.option("--fill-file-pattern", default="{id}.csv", show_default=True,
              help="Filename pattern for fill-source station files.")
@click.option("--variables", default="precip,tmax,tmin", show_default=True,
              help="Comma-separated list from: precip,tmax,tmin,wind,solar,humidity.")
@click.option("--start", required=True, help="ISO start date (YYYY-MM-DD).")
@click.option("--end", required=True, help="ISO end date (YYYY-MM-DD).")
@click.option("--min-overlap-days", default=10, show_default=True, type=int,
              help="Minimum overlapping days needed to trust a bias correction.")
@click.argument("out_dir", type=click.Path(path_type=Path))
def fill_weather(
    stations: Path,
    data_dir: Path,
    file_pattern: str,
    fill_stations: Path,
    fill_data_dir: Path,
    fill_file_pattern: str,
    variables: str,
    start: str,
    end: str,
    min_overlap_days: int,
    out_dir: Path,
) -> None:
    """Fill missing days in observed weather station data from an external
    bias-corrected source, writing swatprep-ready per-station CSVs.

    Computes one overall bias-correction value per station per variable from
    the days where both --data-dir and --fill-data-dir have data (ratio for
    precip, additive offset otherwise), then fills only the real station's
    missing days. A day the real station already has is never overwritten.

    OUT_DIR   Directory where filled station CSVs + fill_report.csv are written.
    """
    from .config import WeatherConfig
    from .core.weather_fill import WeatherGapFiller
    from .writers.weather_fill import WeatherFillWriter
    from .qa import failures, warnings

    var_list = [v.strip() for v in variables.split(",") if v.strip()]

    real_cfg = WeatherConfig(
        stations=stations, data_dir=data_dir, file_pattern=file_pattern,
        variables=var_list, start=start, end=end, missing_policy="warn",
    )
    fill_cfg = WeatherConfig(
        stations=fill_stations, data_dir=fill_data_dir, file_pattern=fill_file_pattern,
        variables=var_list, start=start, end=end, missing_policy="warn",
    )

    result = WeatherGapFiller(real_cfg, fill_cfg, min_overlap_days=min_overlap_days).run()

    for c in result.qa:
        symbol = {"pass": "v", "warn": "!", "fail": "x"}[c.status]
        click.echo(f"  {symbol} {c.name}: {c.message}")

    fail_list = failures(result.qa)
    if fail_list:
        click.echo(f"Failed: {len(fail_list)} check(s).", err=True)
        sys.exit(1)

    written = WeatherFillWriter(result, out_dir).write()

    click.echo(f"\nFiles written : {len(written)}")
    click.echo(f"Output dir    : {out_dir}")

    warn_list = warnings(result.qa)
    if warn_list:
        click.echo(f"Warnings: {len(warn_list)}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_weather_fill.py -v`
Expected: all 13 tests PASS (10 from Tasks 1–2 + 3 new).

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `uv run pytest tests/ -v -k "not rasterio"`
Expected: all PASS, no `ImportError`/`ModuleNotFoundError`.

- [ ] **Step 6: Commit**

```bash
git add swatprep/cli.py tests/test_weather_fill.py
git commit -m "feat: add swatprep fill weather CLI command"
```

---

## Final verification

- [ ] Run the complete suite once more end-to-end: `uv run pytest tests/ -v -k "not rasterio"` — expect all green.
- [ ] Confirm `swatprep fill weather --help` runs and documents all options: `uv run python -m swatprep.cli fill weather --help`.
- [ ] Skim `README.md`'s CLI section — if it lists `swatprep convert ...` examples, add a matching one-line `swatprep fill weather ...` example for discoverability (optional polish, not a functional requirement).
