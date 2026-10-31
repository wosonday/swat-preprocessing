# Phase 4a – Explore + Streamflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Configure / Explore switch to the Project page and an Explore › Streamflow view (summary table, hydrograph, flow duration curve, monthly climatology with WMO-No. 1203 rules), and ship it with the app icon as v0.4.0.

**Architecture:** Pure-pandas services (`climatology`, `flow_stats`) and a core-reading service (`explore_data`, which calls `swatprep.core.streamflow.StreamflowPreprocessor` and never raises) sit under `app/services/` with no Streamlit import. `app/ui/charts.py` turns DataFrames into Altair charts; `app/ui/explore.py` renders the view and caches reads with `st.cache_data`. The page swaps the form tabs for `render_explore` when Explore is selected.

**Tech Stack:** Python 3.12, pandas, numpy, Altair 6 and Streamlit 1.66 (both already locked), pytest + `streamlit.testing.v1.AppTest`, uv.

Spec: `docs/superpowers/specs/2026-10-31-phase4-visualization-design.md` (sections 3–6, 9, 10: slice 4a).

## Global Constraints

- No new dependencies: `uv.lock` may change only the `swatprep` version line.
- `app/services/*` must not import `streamlit`.
- All code, UI text and commit messages in English; sentence case; no emoji in status text (Material icons only).
- Colours: missing data `#f04142` (theme red); chart labels `#757575` (readable on `#ffffff` and `#202020`).
- WMO-No. 1203 rules exactly as in spec section 5: `sum` invalid with any missing day; `mean` invalid with ≥ 11 missing or ≥ 5 consecutive missing; estimated days ≤ 10 and < 5 in a row; climatology `ok` when `n_valid ≥ 0.8 × n_years`.
- FDC: Weibull plotting position `exceedance_pct = 100·m/(n+1)`.
- Explore reads the **saved** config file, never the unsaved form.
- Run tests with `uv run python -m pytest` (never a system pytest).
- Baseline before this plan: **342 passed**. After: **378 passed**.

## File Structure

| File | Responsibility |
|---|---|
| `app/services/climatology.py` (new) | Monthly values with WMO completeness rules; 12-month climatology |
| `app/services/flow_stats.py` (new) | FDC, flow quantiles, per-station summary |
| `app/services/explore_data.py` (new) | Load the saved config; read streamflow through the core; trim a station's series |
| `app/ui/charts.py` (new) | Altair: hydrograph, FDC chart, climatology chart |
| `app/ui/explore.py` (new) | Explore UI: view switch, Reload data, Streamflow view, caching |
| `app/pages/1_Project.py` (modify) | Configure / Explore switch; results only in Configure |
| `tests/ui/test_climatology.py`, `test_flow_stats.py`, `test_explore_data.py`, `test_charts.py`, `test_explore_page.py` (new) | Tests |
| `pyproject.toml`, `CHANGELOG.md`, `docs/USER_GUIDE_VI.md`, `AGENTS.md`, `TESTING_GUIDE.md`, spec §11 (modify) | Version 0.4.0 and docs |

---

### Task 1: Commit the app icon work

The icon files are already in the working tree (uncommitted). Commit them first so the Explore work has a clean base.

**Files:** `app/assets/*`, `app/ui/branding.py`, `app/Home.py`, `app/pages/1_Project.py`, `pyproject.toml`, `scripts/install.bat`, `scripts/install.sh`, `README.md`, `README_VI.md`, `CHANGELOG.md`, `tests/ui/test_launch.py`

- [ ] **Step 1: Create the branch and check the baseline**

```bash
git switch main && git pull
git switch -c feature/phase4a-explore
uv sync --locked --extra geo --extra app --extra dev
uv run python -m pytest -q
```
Expected: `342 passed`.

- [ ] **Step 2: Commit**

```bash
git add app/assets app/ui/branding.py app/Home.py app/pages/1_Project.py pyproject.toml scripts/install.bat scripts/install.sh README.md README_VI.md CHANGELOG.md tests/ui/test_launch.py
git commit -m "feat(app): app icon for the browser tab, sidebar, Desktop shortcut and Linux menu"
git add docs/superpowers/specs/2026-10-31-phase4-visualization-design.md docs/superpowers/plans/2026-10-31-phase4a-explore-streamflow.md
git commit -m "docs: phase 4 visualization design and slice 4a plan"
```

---

### Task 2: `climatology.py` – monthly values and climatology (WMO-No. 1203)

**Files:**
- Create: `app/services/climatology.py`
- Test: `tests/ui/test_climatology.py`

**Interfaces:**
- Produces:
  - `monthly_values(daily: pd.Series, kind: Literal["sum", "mean"], estimated: pd.Series | None = None) -> pd.DataFrame` with columns `year, month, value, n_days, n_missing, n_estimated, max_gap, max_est_run, valid, reason`.
  - `monthly_climatology(monthly: pd.DataFrame, min_fraction: float = 0.8) -> pd.DataFrame` with 12 rows and columns `month, mean, n_valid, n_years, ok`.
  - `MONTHLY_COLUMNS: list[str]`

- [ ] **Step 1: Write the failing tests** – `tests/ui/test_climatology.py`

```python
import numpy as np
import pandas as pd
import pytest

from app.services.climatology import monthly_climatology, monthly_values


def july(values=1.0) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2005-07-01", "2005-07-31"), dtype=float)


def one(daily, kind, estimated=None) -> pd.Series:
    table = monthly_values(daily, kind, estimated)
    assert len(table) == 1
    return table.iloc[0]


def test_full_month_sum_is_valid():
    row = one(july(2.0), "sum")
    assert row["valid"] and row["value"] == pytest.approx(62.0) and row["n_days"] == 31


def test_sum_with_one_missing_day_is_invalid():
    s = july(); s.iloc[10] = np.nan
    row = one(s, "sum")
    assert not row["valid"] and row["reason"] == "missing days" and np.isnan(row["value"])


@pytest.mark.parametrize("n_missing, valid", [(10, True), (11, False)])
def test_mean_allows_up_to_ten_scattered_missing_days(n_missing, valid):
    s = july(); s.iloc[0:2 * n_missing:2] = np.nan   # every other day: never 2 in a row
    row = one(s, "mean")
    assert bool(row["valid"]) is valid and row["n_missing"] == n_missing
    if not valid:
        assert row["reason"] == "11+ missing days"


@pytest.mark.parametrize("run, valid", [(4, True), (5, False)])
def test_mean_rejects_five_consecutive_missing_days(run, valid):
    s = july(); s.iloc[3:3 + run] = np.nan
    row = one(s, "mean")
    assert bool(row["valid"]) is valid and row["max_gap"] == run
    if not valid:
        assert row["reason"] == "5+ consecutive missing days"


@pytest.mark.parametrize("n_est, valid", [(10, True), (11, False)])
def test_at_most_ten_estimated_days(n_est, valid):
    est = pd.Series(False, index=july().index); est.iloc[0:2 * n_est:2] = True
    row = one(july(), "sum", est)
    assert bool(row["valid"]) is valid and row["n_estimated"] == n_est
    if not valid:
        assert row["reason"] == "more than 10 estimated days"


@pytest.mark.parametrize("run, valid", [(4, True), (5, False)])
def test_estimated_days_not_five_in_a_row(run, valid):
    est = pd.Series(False, index=july().index); est.iloc[0:run] = True
    row = one(july(), "sum", est)
    assert bool(row["valid"]) is valid and row["max_est_run"] == run


def test_days_outside_the_series_count_as_missing():
    s = pd.Series(1.0, index=pd.date_range("2005-07-15", "2005-08-31"))
    table = monthly_values(s, "sum")
    assert list(table["month"]) == [7, 8]
    assert table.iloc[0]["n_missing"] == 14 and not table.iloc[0]["valid"]
    assert table.iloc[1]["valid"]


def test_empty_series_gives_empty_table():
    assert monthly_values(pd.Series(dtype=float), "sum").empty


def five_julys(valid_years: int) -> pd.DataFrame:
    rows = [{"year": 2000 + i, "month": 7, "value": 10.0 * (i + 1), "valid": i < valid_years} for i in range(5)]
    return pd.DataFrame(rows)


@pytest.mark.parametrize("valid_years, ok", [(4, True), (3, False)])
def test_climatology_needs_eighty_percent_of_years(valid_years, ok):
    clim = monthly_climatology(five_julys(valid_years)).set_index("month")
    assert bool(clim.loc[7, "ok"]) is ok
    assert clim.loc[7, "n_valid"] == valid_years and clim.loc[7, "n_years"] == 5
    assert clim.loc[7, "mean"] == pytest.approx(np.mean([10.0 * (i + 1) for i in range(valid_years)]))


def test_climatology_has_twelve_months_even_without_data():
    clim = monthly_climatology(five_julys(5))
    assert list(clim["month"]) == list(range(1, 13))
    assert clim.set_index("month").loc[1, "n_years"] == 0 and not clim.set_index("month").loc[1, "ok"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/ui/test_climatology.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'app.services.climatology'`.

- [ ] **Step 3: Implement** – `app/services/climatology.py`

```python
"""Monthly values and monthly climatology with the WMO-No. 1203 (2017) completeness rules.

- "sum" (precipitation, runoff depth): a month is valid only with no missing day (4.4.1 c).
- "mean" (discharge): a month is invalid with 11+ missing days or 5+ consecutive missing days (4.4.1 a).
- Estimated (gap-filled) days count as data, but at most 10 per month and fewer than 5 in a row (4.4.1 c, 4.6).
- A month of the climatology is reliable when valid in at least 80% of the years (4.4.2).
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

MONTHLY_COLUMNS = ["year", "month", "value", "n_days", "n_missing", "n_estimated",
                   "max_gap", "max_est_run", "valid", "reason"]


def _longest_run(mask: pd.Series) -> int:
    best = run = 0
    for flag in mask.to_numpy():
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def _reason(kind: str, n_missing: int, max_gap: int, n_est: int, est_run: int) -> str:
    if kind == "sum" and n_missing:
        return "missing days"
    if kind == "mean" and n_missing >= 11:
        return "11+ missing days"
    if kind == "mean" and max_gap >= 5:
        return "5+ consecutive missing days"
    if n_est > 10:
        return "more than 10 estimated days"
    if est_run >= 5:
        return "5+ consecutive estimated days"
    return ""


def monthly_values(daily: pd.Series, kind: Literal["sum", "mean"],
                   estimated: pd.Series | None = None) -> pd.DataFrame:
    """One row per calendar month spanned by `daily`'s index; days outside the index count as missing."""
    if daily.empty:
        return pd.DataFrame(columns=MONTHLY_COLUMNS)
    days = pd.date_range(daily.index.min().to_period("M").start_time,
                         daily.index.max().to_period("M").end_time.normalize(), freq="D")
    values = daily.astype(float).reindex(days)
    est = pd.Series(False, index=days) if estimated is None else estimated.reindex(days, fill_value=False).astype(bool)
    rows = []
    for period, month in values.groupby(values.index.to_period("M")):
        missing = month.isna()
        est_m = est.loc[month.index] & ~missing
        n_missing, n_est = int(missing.sum()), int(est_m.sum())
        gap, est_run = _longest_run(missing), _longest_run(est_m)
        reason = _reason(kind, n_missing, gap, n_est, est_run)
        value = (month.sum() if kind == "sum" else month.mean()) if not reason else np.nan
        rows.append([period.year, period.month, value, len(month), n_missing, n_est, gap, est_run, not reason, reason])
    return pd.DataFrame(rows, columns=MONTHLY_COLUMNS)


def monthly_climatology(monthly: pd.DataFrame, min_fraction: float = 0.8) -> pd.DataFrame:
    """12 rows: mean of the valid monthly values, how many years were valid, and whether that reaches min_fraction."""
    rows = []
    for m in range(1, 13):
        sub = monthly[monthly["month"] == m]
        n_years, n_valid = len(sub), int(sub["valid"].sum())
        mean = float(sub.loc[sub["valid"], "value"].mean()) if n_valid else np.nan
        ok = n_years > 0 and n_valid >= min_fraction * n_years - 1e-9
        rows.append([m, mean, n_valid, n_years, ok])
    return pd.DataFrame(rows, columns=["month", "mean", "n_valid", "n_years", "ok"])
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/ui/test_climatology.py -q`
Expected: `15 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/services/climatology.py tests/ui/test_climatology.py
git commit -m "feat(app): monthly values and climatology with WMO-No. 1203 completeness rules"
```

---

### Task 3: `flow_stats.py` – flow duration curve and summary

**Files:**
- Create: `app/services/flow_stats.py`
- Test: `tests/ui/test_flow_stats.py`

**Interfaces:**
- Produces:
  - `fdc(series: pd.Series) -> pd.DataFrame` with columns `exceedance_pct, flow`, flow descending.
  - `flow_quantile(series: pd.Series, pct: float) -> float` (NaN without data).
  - `summary(wide: pd.DataFrame) -> pd.DataFrame` with columns `station, start, end, pct_missing, min, mean, max, q5, q50, q95`.

- [ ] **Step 1: Write the failing tests** – `tests/ui/test_flow_stats.py`

```python
import numpy as np
import pandas as pd
import pytest

from app.services.flow_stats import fdc, flow_quantile, summary


def test_weibull_quantiles_of_one_to_ninety_nine():
    s = pd.Series(np.arange(1, 100, dtype=float))
    assert flow_quantile(s, 50) == pytest.approx(50)
    assert flow_quantile(s, 5) == pytest.approx(95)
    assert flow_quantile(s, 95) == pytest.approx(5)


def test_fdc_is_sorted_and_skips_nan():
    curve = fdc(pd.Series([3.0, np.nan, 1.0, 2.0]))
    assert list(curve["flow"]) == [3.0, 2.0, 1.0]
    assert list(curve["exceedance_pct"]) == pytest.approx([25.0, 50.0, 75.0])


@pytest.mark.parametrize("values", [[], [4.0, 4.0, 4.0], [0.0, 0.0]])
def test_degenerate_series_do_not_fail(values):
    s = pd.Series(values, dtype=float)
    q = flow_quantile(s, 50)
    assert (np.isnan(q) if not values else q == values[0])


def test_summary_counts_missing_between_first_and_last_value():
    days = pd.date_range("2000-01-01", periods=6)
    wide = pd.DataFrame({"A": [np.nan, 1.0, np.nan, 3.0, 2.0, np.nan], "B": [np.nan] * 6}, index=days)
    table = summary(wide).set_index("station")
    assert table.loc["A", "pct_missing"] == 25.0       # 1 of the 4 days from Jan 2 to Jan 5
    assert table.loc["A", "max"] == 3.0 and str(table.loc["A", "start"]) == "2000-01-02"
    assert pd.isna(table.loc["B", "mean"])
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/ui/test_flow_stats.py -q`
Expected: `ModuleNotFoundError: No module named 'app.services.flow_stats'`.

- [ ] **Step 3: Implement** – `app/services/flow_stats.py`

```python
"""Flow duration curve (Weibull plotting position) and per-station streamflow summary."""
from __future__ import annotations

import numpy as np
import pandas as pd


def fdc(series: pd.Series) -> pd.DataFrame:
    """Valid values sorted high to low; exceedance_pct = 100 * m / (n + 1)."""
    flow = np.sort(series.dropna().to_numpy(dtype=float))[::-1]
    rank = np.arange(1, len(flow) + 1)
    return pd.DataFrame({"exceedance_pct": 100 * rank / (len(flow) + 1), "flow": flow})


def flow_quantile(series: pd.Series, pct: float) -> float:
    """Flow exceeded pct % of the time (Q5 = high flow, Q95 = low flow); NaN without data."""
    curve = fdc(series)
    if curve.empty:
        return float("nan")
    return float(np.interp(pct, curve["exceedance_pct"], curve["flow"]))


def summary(wide: pd.DataFrame) -> pd.DataFrame:
    """One row per station; pct_missing counts the days between its first and last value."""
    rows = []
    for sid in wide.columns:
        s = wide[sid]
        first, last = s.first_valid_index(), s.last_valid_index()
        if first is None:
            rows.append({"station": sid})
            continue
        span = s.loc[first:last]
        rows.append({
            "station": sid, "start": first.date(), "end": last.date(),
            "pct_missing": round(100 * float(span.isna().mean()), 1),
            "min": span.min(), "mean": span.mean(), "max": span.max(),
            "q5": flow_quantile(span, 5), "q50": flow_quantile(span, 50), "q95": flow_quantile(span, 95),
        })
    return pd.DataFrame(rows, columns=["station", "start", "end", "pct_missing", "min", "mean", "max",
                                       "q5", "q50", "q95"])
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/ui/test_flow_stats.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/services/flow_stats.py tests/ui/test_flow_stats.py
git commit -m "feat(app): flow duration curve, flow quantiles and station summary"
```

---

### Task 4: `explore_data.py` – read the saved config and streamflow through the core

**Files:**
- Create: `app/services/explore_data.py`
- Test: `tests/ui/test_explore_data.py` (uses the `example_project` fixture from `tests/ui/conftest.py`: a copy of `examples/config_minimal.yaml` + `examples/data/`; its streamflow is 10 days, 2000-01-01 → 2000-01-10, station `ST001`, units `m3s`)

**Interfaces:**
- Consumes: `swatprep.config.SWATPrepConfig.from_yaml(path)`, `swatprep.core.streamflow.StreamflowPreprocessor(cfg.streamflow).run().daily` (wide DataFrame, DatetimeIndex of the dates present in the file × station id).
- Produces:
  - `load_config(path: Path) -> tuple[SWATPrepConfig | None, str | None]`
  - `@dataclass FlowView(daily: pd.DataFrame, units: str = "m3s", error: str | None = None)` – `daily` has every day between the first and last date.
  - `load_streamflow(cfg: SWATPrepConfig) -> FlowView` (requires `cfg.streamflow is not None`; never raises)
  - `station_series(wide: pd.DataFrame, station: str) -> pd.Series`

- [ ] **Step 1: Write the failing tests** – `tests/ui/test_explore_data.py`

```python
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.explore_data import load_config, load_streamflow, station_series


def test_load_config_reports_schema_problems(tmp_path: Path):
    bad = tmp_path / "config.yaml"
    bad.write_text("project:\n  name: x\n", encoding="utf-8")   # crs missing
    cfg, error = load_config(bad)
    assert cfg is None and error.startswith("Config is not valid (1 problem(s))")


def test_load_streamflow_reads_the_example(example_project):
    cfg, error = load_config(example_project)
    view = load_streamflow(cfg)
    assert error is None and view.error is None and view.units == "m3s"
    assert list(view.daily.columns) == ["ST001"] and len(view.daily) == 10


def test_absent_days_become_nan(example_project):
    csv = example_project.parent / "data" / "streamflow.csv"
    lines = csv.read_text(encoding="utf-8").splitlines()
    csv.write_text("\n".join(lines[:4] + lines[6:]) + "\n", encoding="utf-8")   # drop Jan 4 and Jan 5
    view = load_streamflow(load_config(example_project)[0])
    assert len(view.daily) == 10 and int(view.daily["ST001"].isna().sum()) == 2


def test_unreadable_streamflow_is_an_error_not_an_exception(example_project):
    (example_project.parent / "data" / "streamflow.csv").unlink()
    view = load_streamflow(load_config(example_project)[0])
    assert view.error and view.daily.empty


def test_station_series_trims_to_observed_period():
    wide = pd.DataFrame({"A": [np.nan, 1.0, np.nan, 2.0, np.nan]}, index=pd.date_range("2000-01-01", periods=5))
    s = station_series(wide, "A")
    assert s.index[0] == pd.Timestamp("2000-01-02") and s.index[-1] == pd.Timestamp("2000-01-04")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/ui/test_explore_data.py -q`
Expected: `ModuleNotFoundError: No module named 'app.services.explore_data'`.

- [ ] **Step 3: Implement** – `app/services/explore_data.py`

```python
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
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/ui/test_explore_data.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/services/explore_data.py tests/ui/test_explore_data.py
git commit -m "feat(app): read the saved config and streamflow through the core for Explore"
```

---

### Task 5: `charts.py` – hydrograph, FDC and climatology charts

**Files:**
- Create: `app/ui/charts.py`
- Test: `tests/ui/test_charts.py`

**Interfaces:**
- Consumes: `fdc`, `flow_quantile` (Task 3); `monthly_values`, `monthly_climatology` (Task 2, tests only).
- Produces:
  - `UNITS: dict[str, str]` (`{"m3s": "m³/s", "mm": "mm"}`), `MONTHS`, `MISSING`, `LABEL`, `HEIGHT`
  - `hydrograph(series: pd.Series, units: str, log: bool = False) -> alt.LayerChart` – layer 0 is the line (`detail` = `segment`, x-zoom bound to scales), layer 1 the red rules of missing days.
  - `fdc_chart(series: pd.Series, units: str) -> alt.LayerChart` – log y; points and labels Q5, Q50, Q95.
  - `climatology_chart(clim: pd.DataFrame, title: str) -> alt.LayerChart` – bars faded when `ok` is false; label `n_valid/n_years`.

- [ ] **Step 1: Write the failing tests** – `tests/ui/test_charts.py`

```python
import numpy as np
import pandas as pd

from app.services.climatology import monthly_climatology, monthly_values
from app.ui.charts import climatology_chart, fdc_chart, hydrograph


def flow() -> pd.Series:
    s = pd.Series(np.linspace(1, 20, 40), index=pd.date_range("2000-01-01", periods=40))
    s.iloc[5:8] = np.nan
    s.iloc[20] = 0.0
    return s


def y_scale(chart) -> str | None:
    return chart.to_dict()["layer"][0]["encoding"]["y"].get("scale", {}).get("type")


def test_hydrograph_log_toggle():
    assert y_scale(hydrograph(flow(), "m3s")) == "linear"
    assert y_scale(hydrograph(flow(), "m3s", log=True)) == "log"


def test_hydrograph_marks_missing_days_and_breaks_the_line():
    spec = hydrograph(flow(), "m3s").to_dict()
    sizes = sorted(len(rows) for rows in spec["datasets"].values())
    assert sizes == [3, 37]                       # 3 missing days, 37 plotted days
    assert spec["layer"][0]["encoding"]["detail"]["field"] == "segment"


def test_hydrograph_log_drops_zero_flow():
    sizes = sorted(len(rows) for rows in hydrograph(flow(), "m3s", log=True).to_dict()["datasets"].values())
    assert sizes == [3, 36]


def test_fdc_is_log_and_labels_quantiles():
    spec = fdc_chart(flow(), "m3s").to_dict()
    assert spec["layer"][0]["encoding"]["y"]["scale"]["type"] == "log"
    labels = [row["label"] for rows in spec["datasets"].values() for row in rows if "label" in row]
    assert labels == ["Q5", "Q50", "Q95"]


def test_climatology_chart_has_twelve_bars_with_year_labels():
    s = pd.Series(1.0, index=pd.date_range("2000-01-01", "2001-12-31"))
    spec = climatology_chart(monthly_climatology(monthly_values(s, "mean")), "Mean monthly flow").to_dict()
    rows = next(iter(spec["datasets"].values()))
    assert len(rows) == 12 and rows[0]["years"] == "2/2"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/ui/test_charts.py -q`
Expected: `ModuleNotFoundError: No module named 'app.ui.charts'`.

- [ ] **Step 3: Implement** – `app/ui/charts.py`

```python
"""Altair charts for the Explore views (data in, alt.Chart out)."""
from __future__ import annotations

import altair as alt
import pandas as pd

from app.services.flow_stats import fdc, flow_quantile

MISSING = "#f04142"   # theme red
LABEL = "#757575"     # readable on the light (#ffffff) and dark (#202020) backgrounds
UNITS = {"m3s": "m³/s", "mm": "mm"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
HEIGHT = 260


def hydrograph(series: pd.Series, units: str, log: bool = False) -> alt.LayerChart:
    df = pd.DataFrame({"date": series.index, "flow": series.to_numpy(dtype=float)})
    drop = df["flow"].isna() | ((df["flow"] <= 0) if log else False)
    df["segment"] = drop.cumsum()   # a new line after every dropped day: gaps are not bridged
    zoom = alt.selection_interval(bind="scales", encodings=["x"])
    line = alt.Chart(df[~drop]).mark_line(strokeWidth=1).encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("flow:Q", title=f"Flow ({UNITS[units]})", scale=alt.Scale(type="log" if log else "linear")),
        detail="segment:N",
        tooltip=[alt.Tooltip("date:T"), alt.Tooltip("flow:Q", format=",.3f")],
    ).add_params(zoom)
    missing = alt.Chart(df[df["flow"].isna()]).mark_rule(color=MISSING, opacity=0.4).encode(
        x="date:T", tooltip=[alt.Tooltip("date:T", title="Missing")])
    return alt.layer(line, missing).properties(height=HEIGHT)


def fdc_chart(series: pd.Series, units: str) -> alt.LayerChart:
    positive = series[series > 0]
    curve = fdc(positive)
    marks = pd.DataFrame([{"label": f"Q{p}", "exceedance_pct": p, "flow": flow_quantile(series, p)}
                          for p in (5, 50, 95)])
    marks = marks[marks["flow"] > 0]
    y = alt.Y("flow:Q", title=f"Flow ({UNITS[units]})", scale=alt.Scale(type="log"))
    x = alt.X("exceedance_pct:Q", title="Time flow is exceeded (%)", scale=alt.Scale(domain=[0, 100]))
    line = alt.Chart(curve).mark_line().encode(x=x, y=y)
    points = alt.Chart(marks).mark_point(filled=True, size=50).encode(
        x=x, y=y, tooltip=["label:N", alt.Tooltip("flow:Q", format=",.3f")])
    labels = points.mark_text(align="left", dx=6, dy=-6, color=LABEL).encode(text="label:N")
    return alt.layer(line, points, labels).properties(height=HEIGHT)


def climatology_chart(clim: pd.DataFrame, title: str) -> alt.LayerChart:
    df = clim.assign(
        name=[MONTHS[m - 1] for m in clim["month"]],
        years=[f"{v}/{n}" for v, n in zip(clim["n_valid"], clim["n_years"])],
        label_y=clim["mean"].fillna(0),
    )
    x = alt.X("name:N", sort=MONTHS, title=None, axis=alt.Axis(labelAngle=0))
    bars = alt.Chart(df).mark_bar().encode(
        x=x, y=alt.Y("mean:Q", title=title),
        opacity=alt.condition("datum.ok", alt.value(1.0), alt.value(0.35)),
        tooltip=[alt.Tooltip("name:N", title="Month"), alt.Tooltip("mean:Q", format=",.2f"),
                 alt.Tooltip("years:N", title="Valid years")],
    )
    labels = alt.Chart(df).mark_text(dy=-6, fontSize=11, color=LABEL).encode(x=x, y="label_y:Q", text="years:N")
    return alt.layer(bars, labels).properties(height=HEIGHT)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/ui/test_charts.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/ui/charts.py tests/ui/test_charts.py
git commit -m "feat(app): hydrograph, flow duration curve and climatology charts"
```

---

### Task 6: Explore view and the Configure / Explore switch

**Files:**
- Create: `app/ui/explore.py`
- Modify: `app/pages/1_Project.py` (imports; the `# ---- form tabs` block; the final `last_run` block)
- Test: `tests/ui/test_explore_page.py`

**Interfaces:**
- Consumes: Tasks 2–5.
- Produces: `render_explore(path: Path, unsaved: bool) -> None`; widget keys `mode` (`"Configure" | "Explore"`), `explore_view`, `explore_reload`, `flow_station`, `flow_log`; session key `explore_token`.

- [ ] **Step 1: Write the failing tests** – `tests/ui/test_explore_page.py`

```python
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAGE = str(Path(__file__).resolve().parents[2] / "app" / "pages" / "1_Project.py")


@pytest.fixture
def page(monkeypatch, example_project):
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(example_project.parent))
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    at.selectbox(key="config_choice").select("config_minimal.yaml").run()
    return at


def explore(at):
    at.segmented_control(key="mode").set_value("Explore").run()
    assert not at.exception
    return at


def test_explore_shows_streamflow_instead_of_the_form(page):
    explore(page)
    assert len(page.tabs) == 0
    assert page.segmented_control(key="explore_view").value == "Streamflow"
    assert page.selectbox(key="flow_station").value == "ST001"
    assert [s.value for s in page.main.subheader] == ["Hydrograph", "Flow duration curve", "Monthly climatology"]


def test_log_scale_toggle_runs(page):
    explore(page).toggle(key="flow_log").set_value(True).run()
    assert not page.exception


def test_config_without_streamflow(page, example_project):
    text = example_project.read_text(encoding="utf-8")
    example_project.write_text(text.split("streamflow:")[0], encoding="utf-8")
    page.session_state["loaded_path"] = None
    page.run()
    explore(page)
    assert any("no streamflow section" in i.value for i in page.info)


def test_unsaved_edits_are_flagged(page):
    page.selectbox(key="f::dem.resampling").select("cubic").run()
    explore(page)
    assert any("save to explore your changes" in i.value for i in page.info)


def test_back_to_configure_keeps_edits(page):
    page.selectbox(key="f::dem.resampling").select("cubic").run()
    explore(page).segmented_control(key="mode").set_value("Configure").run()
    assert page.selectbox(key="f::dem.resampling").value == "cubic"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/ui/test_explore_page.py -q`
Expected: FAIL – `KeyError`/`ValueError` because no widget with key `mode` exists.

- [ ] **Step 3: Implement the view** – `app/ui/explore.py`

```python
"""Explore: charts of the data behind the saved config (Streamflow for now)."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.services.climatology import monthly_climatology, monthly_values
from app.services.explore_data import FlowView, load_config, load_streamflow, station_series
from app.services.flow_stats import summary
from app.ui.charts import UNITS, climatology_chart, fdc_chart, hydrograph

VIEWS = ["Streamflow"]


@st.cache_data(show_spinner="Reading streamflow…", max_entries=8)
def _flow(path: str, mtime: float, token: int) -> FlowView:
    """Cached by config path + modification time; `token` changes on Reload data."""
    cfg, _ = load_config(Path(path))
    return load_streamflow(cfg)


def render_explore(path: Path, unsaved: bool) -> None:
    if unsaved:
        st.info("Showing the saved config; save to explore your changes.", icon=":material/info:")
    cfg, error = load_config(path)
    if error:
        st.error(error, icon=":material/error:")
        return

    view_col, reload_col = st.columns([3, 1], vertical_alignment="bottom")
    view = view_col.segmented_control("View", VIEWS, default=VIEWS[0], required=True, key="explore_view")
    if reload_col.button("Reload data", icon=":material/refresh:", key="explore_reload", width="stretch"):
        st.session_state["explore_token"] = st.session_state.get("explore_token", 0) + 1
    token = st.session_state.get("explore_token", 0)

    if view == "Streamflow":
        if cfg.streamflow is None:
            st.info("This config has no streamflow section.", icon=":material/info:")
            return
        _streamflow(_flow(str(path), path.stat().st_mtime, token))


def _streamflow(data: FlowView) -> None:
    if data.error:
        st.error(data.error, icon=":material/error:")
        return
    if data.daily.empty:
        st.warning("No streamflow values found.", icon=":material/warning:")
        return
    unit = UNITS[data.units]

    st.dataframe(summary(data.daily), hide_index=True, column_config={
        "station": "Station", "start": "Start", "end": "End",
        "pct_missing": st.column_config.NumberColumn("Missing (%)", format="%.1f"),
        **{c: st.column_config.NumberColumn(f"{c.upper() if c[0] == 'q' else c.capitalize()} ({unit})", format="%.3f")
           for c in ("min", "mean", "max", "q5", "q50", "q95")},
    })
    station = st.selectbox("Station", list(data.daily.columns), key="flow_station")
    series = station_series(data.daily, station)

    st.subheader("Hydrograph")
    log = st.toggle("Log scale", key="flow_log")
    st.altair_chart(hydrograph(series, data.units, log), width="stretch")
    zeros = int((series <= 0).sum())
    if log and zeros:
        st.caption(f"{zeros} zero-flow days not shown on the log scale.")
    st.caption(f"{int(series.isna().sum())} missing days, marked in red. Drag to zoom, double-click to reset.")

    st.subheader("Flow duration curve")
    st.altair_chart(fdc_chart(series, data.units), width="stretch")

    st.subheader("Monthly climatology")
    kind = "mean" if data.units == "m3s" else "sum"
    clim = monthly_climatology(monthly_values(series, kind))
    title = f"Mean monthly flow ({unit})" if kind == "mean" else f"Mean monthly total ({unit})"
    st.altair_chart(climatology_chart(clim, title), width="stretch")
    weak = [m for m, ok, n in zip(clim["month"], clim["ok"], clim["n_years"]) if n and not ok]
    rule = "at most 10 missing days and fewer than 5 in a row" if kind == "mean" else "no missing day"
    st.caption(f"Labels: valid years / years. A month is valid with {rule} (WMO-No. 1203); "
               "the mean needs valid months in at least 80% of the years.")
    if weak:
        st.warning(f"{len(weak)} month(s) below 80% of years are shown faded.", icon=":material/warning:")
```

- [ ] **Step 4: Wire it into the page** – `app/pages/1_Project.py`

Add the import after `from app.ui.browse import browse_dialog`:

```python
from app.ui.explore import render_explore
```

Replace the whole `# ---- form tabs` block (from that comment to the `st.code(... language="yaml")` line, including the unused `keys = [...]` line) with:

```python
# ---------------------------------------------------------------- configure (form tabs) or explore
def _tab_label(key: str, label: str) -> str:
    n = count_for(errors, key)
    return f"{label} ({n})" if n else label


mode = st.segmented_control("Mode", ["Configure", "Explore"], default="Configure", required=True, key="mode",
                            label_visibility="collapsed")
if mode == "Configure":
    labels = [_tab_label("project", "Project")] + [_tab_label(k, SECTIONS[k][0]) for k in configured] + ["YAML"]
    tabs = st.tabs(labels)
    with tabs[0]:
        render_project(ctx)
    for key, tab in zip(configured, tabs[1:-1]):
        with tab:
            render_section(ctx, key)
    with tabs[-1]:
        st.code(project_io.dump_yaml(cfg), language="yaml")
else:
    render_explore(path, unsaved=project_io.dump_yaml(cfg) != state["clean_yaml"])
```

Change the last block so results show only in Configure:

```python
last = state.get("last_run")
if mode == "Configure" and last and last[0] == str(path):
    st.divider()
    render_result(last[1], last[2])
```

Why a switch and not another tab: `st.tabs` runs every tab on every rerun by default, so charts would be recomputed on each keystroke in the form. The switch runs only the selected mode. Form widgets that are not drawn in Explore are re-created from `state["cfg"]` when the user returns (fields only set a widget key when it is absent), which `test_back_to_configure_keeps_edits` checks.

- [ ] **Step 5: Run the tests**

Run: `uv run python -m pytest tests/ui/test_explore_page.py tests/ui/test_project_form.py -q`
Expected: all pass (5 new + the existing Project form tests).

- [ ] **Step 6: Look at it**

Make a demo project with six years of synthetic flow (two stations, an 18-day and a 3-day gap) outside the repo, then open it:

```bash
mkdir demo4a && cp -r examples/data demo4a/data && cp examples/config_minimal.yaml demo4a/config.yaml
uv run python - <<'EOF'
import numpy as np, pandas as pd
rng = np.random.default_rng(1)
days = pd.date_range("2010-01-01", "2015-12-31")
base = 5 + 40 * np.exp(-((days.dayofyear.to_numpy() - 250) / 40.0) ** 2)
rows = []
for sid, scale in [("ST001", 1.0), ("ST002", 2.5)]:
    q = base * scale * np.exp(rng.normal(0, 0.35, len(days)))
    q[(days >= "2012-08-03") & (days <= "2012-08-20")] = np.nan
    q[(days >= "2014-03-10") & (days <= "2014-03-12")] = np.nan
    rows += [(d.date(), sid, round(v, 3)) for d, v in zip(days, q) if not np.isnan(v)]
pd.DataFrame(rows, columns=["date", "station_id", "flow"]).to_csv("demo4a/data/streamflow.csv", index=False)
EOF
uv run swatprep-ui
```

Paste the path of `demo4a/config.yaml` into **Config path**, choose **Explore**. Check in light and dark themes:
- Summary table: two rows, `Missing (%)` = 1.0.
- Hydrograph: red band in Aug 2012 and a thin red line in Mar 2014; the line is broken at both.
- FDC: points Q5, Q50, Q95 labelled.
- Climatology: Aug shows `5/6` (the 18-day gap invalidates Aug 2012), other months `6/6`; labels are readable in dark mode.

Delete `demo4a/` afterwards (it is not part of the repo).

- [ ] **Step 7: Commit**

```bash
git add app/ui/explore.py app/pages/1_Project.py tests/ui/test_explore_page.py
git commit -m "feat(app): Configure/Explore switch and the Explore Streamflow view"
```

---

### Task 7: Docs and version 0.4.0

**Files:** `pyproject.toml`, `uv.lock`, `CHANGELOG.md`, `docs/USER_GUIDE_VI.md`, `AGENTS.md`, `TESTING_GUIDE.md`, `docs/superpowers/specs/2026-10-31-phase4-visualization-design.md` (§11)

- [ ] **Step 1: Version**

In `pyproject.toml` set `version = "0.4.0"`, then:

```bash
uv lock
git diff uv.lock
```
Expected: only the `swatprep` `version` line changes.

- [ ] **Step 2: CHANGELOG** – replace the `## [Unreleased]` heading and its `### Added` list with:

```markdown
## [0.4.0] - YYYY-MM-DD

### Added
- **Explore** on the Project page (switch **Configure | Explore**): charts of the data behind the saved
  config. First view, **Streamflow**: per-station summary (period, % missing, min/mean/max, Q5/Q50/Q95),
  hydrograph with log scale and missing days in red, flow duration curve (Weibull plotting position) and
  monthly climatology that applies the WMO-No. 1203 completeness rules and flags months valid in fewer
  than 80% of the years.
- App icon (a river network converging on its outlet): browser tab, sidebar logo, Windows Desktop
  shortcut (`icon.ico`, 16-256 px) and Linux application menu; source in `app/assets/icon.svg`.
```

(Use the merge date for `YYYY-MM-DD`.)

- [ ] **Step 3: User guide** – in `docs/USER_GUIDE_VI.md`, add at the end of section `## 7. Đọc kết quả` (just before `## 8. Lệnh dòng lệnh (CLI)`):

```markdown
### 7.1 Xem dữ liệu trên giao diện web (Explore)

Trên trang **Project**, chọn **Explore** (cạnh **Configure**) để xem biểu đồ của dữ liệu mà config
**đã lưu** trỏ tới; nếu form còn thay đổi chưa lưu, app nhắc lưu trước. **Reload data** đọc lại dữ liệu
khi file đầu vào vừa được sửa bên ngoài app.

**Streamflow** (cần mục `streamflow`):

| Thành phần | Ý nghĩa |
|---|---|
| Bảng tổng quan | Mỗi trạm: giai đoạn, % ngày thiếu, min/trung bình/max, Q5/Q50/Q95 |
| Hydrograph | Lưu lượng theo ngày; vạch đỏ là ngày thiếu; **Log scale** để xem dòng kiệt; kéo để phóng to |
| Đường duy trì lưu lượng | % thời gian lưu lượng bị vượt (vị trí vẽ Weibull m/(n+1)); Q5 là dòng lũ, Q95 là dòng kiệt |
| Khí hậu tháng | Trung bình của các tháng hợp lệ; nhãn *năm hợp lệ/số năm* |

Tháng hợp lệ theo WMO-No. 1203 (2017): với `units: m3s` (trung bình tháng), thiếu tối đa 10 ngày và
không quá 4 ngày liên tiếp; với `units: mm` (tổng tháng), không thiếu ngày nào. Tháng có số năm hợp lệ
dưới 80% được vẽ nhạt và có cảnh báo: giá trị trung bình của tháng đó chưa đáng tin.
```

- [ ] **Step 4: Test baselines**

- `AGENTS.md`: change `Current baseline (v0.3.1): ... **341 tests**.` to `Current baseline (v0.4.0): `uv run python -m pytest -q` passes with **378 tests**.`
- `TESTING_GUIDE.md`: change `341 passed` to `378 passed`.

- [ ] **Step 5: Spec notes** – in the spec, replace `*(Cập nhật trong quá trình triển khai.)*` under `## 11. Ghi chú triển khai` with what was measured, e.g. load time of the demo project (`time` the first Explore render), and:

```markdown
- Ngày thiếu trên hydrograph được vẽ bằng `mark_rule` cao hết biểu đồ (đỏ, độ mờ 0,4) thay cho vạch ngắn
  dưới trục: khi thử, vạch `mark_tick` với `y=alt.value(...)` không hiện trên biểu đồ.
- Nhãn trên biểu đồ dùng `#757575` để đọc được ở cả giao diện sáng và tối.
- Python 3.10 được khoá với Streamlit 1.65.0 (Streamlit 1.66 cần Python ≥ 3.11); bộ cài dùng Python 3.12.
```

- [ ] **Step 6: Full suite and wheel**

```bash
uv sync --locked --extra geo --extra app --extra dev
uv run python -m pytest -q
uv run swatprep --version
```
Expected: `378 passed`; `swatprep, version 0.4.0`.

- [ ] **Step 7: Commit, push, PR**

```bash
git add pyproject.toml uv.lock CHANGELOG.md docs/USER_GUIDE_VI.md AGENTS.md TESTING_GUIDE.md docs/superpowers/specs/2026-10-31-phase4-visualization-design.md
git commit -m "release: 0.4.0 (Explore: streamflow; app icon)"
git push -u origin feature/phase4a-explore
```

Open the PR to `main`; wait for `test` ✅; merge. Then tag on `main` as in `docs/RELEASING.md` §2.3 (`git switch main && git pull && git tag v0.4.0 && git push origin v0.4.0`) and check the GitHub Release has `install.bat` / `install.sh`.

- [ ] **Step 8: Check the installed app**

Re-run `install.bat` from the release link; open **SWATprep** from the Desktop (shortcut shows the new icon); open a real project with streamflow; choose **Explore**.
