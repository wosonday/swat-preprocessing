# Weather Converter Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace swatprep's duplicated, format-buggy SWAT2012/SWAT+ weather converters with one `StationWeatherConverter` (raw station files → `WeatherResult`) that hands off to the existing `WeatherWriter` / `SWATPlusWeatherWriter` classes, fixing the SWAT2012 output format and completing the SWAT+ output with `weather-sta.cli` / `weather-wgn.cli`.

**Architecture:** `StationWeatherConverter` (new) reads raw per-station files (SWAT Classic style or CSV) plus uppercase-column master metadata into a `WeatherResult` — the same type the config-driven `build()` pipeline already produces. From there, `target="swat2012"` or `target="swatplus"` picks the writer (`WeatherWriter` / `SWATPlusWeatherWriter`) that already exists and now owns 100% of output-format logic. `converters/swat2012.py` and `converters/weather_plus.py`, which currently duplicate that formatting logic (incorrectly, in the SWAT2012 case), are deleted.

**Tech Stack:** Python 3.10+, pandas, Click, pytest (existing stack — no new dependencies).

## Global Constraints

- Match existing code style: `from __future__ import annotations` at the top of every module, type hints on public methods, dataclasses for result types.
- No new third-party dependencies — everything here is buildable with `pandas` + stdlib, already in `pyproject.toml`.
- QA pattern: a missing/bad per-station file is a `QACheck(status="warn")`, never a hard failure — one bad station must not block the rest (existing convention, e.g. `swatprep/core/weather.py`).
- This is a breaking CLI change (`swatprep convert pcp` / `tmp` / `swatplus` are removed, no deprecated aliases) — acceptable per the approved design spec, project is pre-1.0 (`0.1.0`).
- Run tests with `pytest tests/<file> -v` (per `DEVELOPER_GUIDE.md`); if `pytest` isn't on PATH in the execution environment, run `pip install -e .[dev]` first.
- Design spec (source of truth for all format decisions below): `docs/superpowers/specs/2026-08-31-weather-converter-unification-design.md`.

---

## Task 1: Extract `compute_wgn_stats` as a standalone function

**Files:**
- Modify: `swatprep/core/weather.py:301-345` (the `WeatherPreprocessor._compute_wgn` method and its call site at line 73)
- Test: `tests/test_weather.py` (existing WGN tests — no new tests, this is a pure refactor; they must stay green)

**Interfaces:**
- Produces: `compute_wgn_stats(stations: pd.DataFrame, daily: dict[str, pd.DataFrame], qa: list[QACheck]) -> pd.DataFrame` — module-level function in `swatprep/core/weather.py`, used by `WeatherPreprocessor.run()` (Task 1) and `StationWeatherConverter.convert()` (Task 2).

This is a pure refactor (same body, different scope) so it follows a "characterize, refactor, re-verify" cycle instead of new-test TDD.

- [ ] **Step 1: Run the existing WGN tests to confirm a green baseline**

Run: `pytest tests/test_weather.py -v -k wgn`
Expected: `test_wgn_has_12_rows_per_station`, `test_wgn_columns_present`, `test_wgn_unavailable_params_are_minus99` all PASS.

- [ ] **Step 2: Extract the method body into a standalone function**

In `swatprep/core/weather.py`, the class currently has (starting at line 301):

```python
    def _compute_wgn(
        self,
        stations: pd.DataFrame,
        daily: dict[str, pd.DataFrame],
        qa: list[QACheck],
    ) -> pd.DataFrame:
        """Compute SWAT weather generator monthly statistics per station.

        Parameters computed following Neitsch et al. (2011) SWAT Theoretical
        Documentation, Chapter 1 (Climate).
        """
        precip_wide = daily.get("precip")
        tmax_wide   = daily.get("tmax")
        tmin_wide   = daily.get("tmin")
        solar_wide  = daily.get("solar")
        rhum_wide   = daily.get("humidity")
        wind_wide   = daily.get("wind")

        station_ids = list(
            set(precip_wide.columns if precip_wide is not None else [])
            | set(tmax_wide.columns if tmax_wide is not None else [])
        )

        rows = []
        for sid in station_ids:
            p     = precip_wide[sid] if (precip_wide is not None and sid in precip_wide) else None
            tx    = tmax_wide[sid]   if (tmax_wide   is not None and sid in tmax_wide)   else None
            tn    = tmin_wide[sid]   if (tmin_wide   is not None and sid in tmin_wide)   else None
            solar = solar_wide[sid]  if (solar_wide  is not None and sid in solar_wide)  else None
            rhum  = rhum_wide[sid]   if (rhum_wide   is not None and sid in rhum_wide)   else None
            wind  = wind_wide[sid]   if (wind_wide   is not None and sid in wind_wide)   else None

            for month in range(1, 13):
                row: dict = {"station_id": sid, "month": month}
                _fill_temp_stats(row, tx, tn, month)
                _fill_precip_stats(row, p, month)
                _fill_climate_stats(row, solar, rhum, wind, tx, tn, month)
                rows.append(row)

        qa.append(QACheck(
            name="wgn_computed",
            status="pass",
            message=f"WGN stats computed for {len(station_ids)} station(s) × 12 months",
        ))
        return pd.DataFrame(rows)
```

Replace it with a thin delegating method, and add the standalone function immediately above `class WeatherPreprocessor:`:

```python
def compute_wgn_stats(
    stations: pd.DataFrame,
    daily: dict[str, pd.DataFrame],
    qa: list[QACheck],
) -> pd.DataFrame:
    """Compute SWAT weather generator monthly statistics per station.

    Parameters computed following Neitsch et al. (2011) SWAT Theoretical
    Documentation, Chapter 1 (Climate).

    `stations` is accepted for interface symmetry with the rest of the
    pipeline but is not read here — WGN stats are derived purely from the
    daily variable columns. Shared by WeatherPreprocessor and
    StationWeatherConverter so both compute WGN stats identically.
    """
    precip_wide = daily.get("precip")
    tmax_wide   = daily.get("tmax")
    tmin_wide   = daily.get("tmin")
    solar_wide  = daily.get("solar")
    rhum_wide   = daily.get("humidity")
    wind_wide   = daily.get("wind")

    station_ids = list(
        set(precip_wide.columns if precip_wide is not None else [])
        | set(tmax_wide.columns if tmax_wide is not None else [])
    )

    rows = []
    for sid in station_ids:
        p     = precip_wide[sid] if (precip_wide is not None and sid in precip_wide) else None
        tx    = tmax_wide[sid]   if (tmax_wide   is not None and sid in tmax_wide)   else None
        tn    = tmin_wide[sid]   if (tmin_wide   is not None and sid in tmin_wide)   else None
        solar = solar_wide[sid]  if (solar_wide  is not None and sid in solar_wide)  else None
        rhum  = rhum_wide[sid]   if (rhum_wide   is not None and sid in rhum_wide)   else None
        wind  = wind_wide[sid]   if (wind_wide   is not None and sid in wind_wide)   else None

        for month in range(1, 13):
            row: dict = {"station_id": sid, "month": month}
            _fill_temp_stats(row, tx, tn, month)
            _fill_precip_stats(row, p, month)
            _fill_climate_stats(row, solar, rhum, wind, tx, tn, month)
            rows.append(row)

    qa.append(QACheck(
        name="wgn_computed",
        status="pass",
        message=f"WGN stats computed for {len(station_ids)} station(s) × 12 months",
    ))
    return pd.DataFrame(rows)
```

Then delete the old `_compute_wgn` method from inside `WeatherPreprocessor` entirely (don't keep a delegating stub — nothing else calls it as a method).

- [ ] **Step 3: Update the call site**

In `WeatherPreprocessor.run()` (around line 73), change:

```python
        wgn = self._compute_wgn(all_stations, daily, qa)
```

to:

```python
        wgn = compute_wgn_stats(all_stations, daily, qa)
```

- [ ] **Step 4: Run the WGN tests again to confirm no regression**

Run: `pytest tests/test_weather.py -v -k wgn`
Expected: same three tests still PASS.

- [ ] **Step 5: Run the full test_weather.py file to be safe**

Run: `pytest tests/test_weather.py -v`
Expected: all tests PASS (this file isn't otherwise touched yet).

- [ ] **Step 6: Commit**

```bash
git add swatprep/core/weather.py
git commit -m "refactor: extract compute_wgn_stats as a standalone function"
```

---

## Task 2: Create `StationWeatherConverter`

**Files:**
- Create: `swatprep/converters/station_weather.py`
- Test: `tests/test_station_weather_converter.py`

**Interfaces:**
- Consumes: `compute_wgn_stats(stations, daily, qa) -> pd.DataFrame` (Task 1), `WeatherResult` dataclass from `swatprep/core/weather.py` (fields: `stations`, `precip_stations`, `temp_stations`, `daily`, `wgn_stats`, `qa`), `QACheck` from `swatprep/qa.py`, `InputValidationError` from `swatprep/errors.py`.
- Produces: `StationWeatherConverter(pcp_master=None, pcp_dir=None, tmp_master=None, tmp_dir=None, name_col="NAME", lat_col="LAT", lon_col="LONG", elev_col="ELEVATION", id_col="ID", pcp_name_prefix="pcp_", tmp_name_prefix="tmp_", pcp_raw_suffix=".txt", tmp_raw_suffix=".txt", no_data_value=-99.0)` with `.convert() -> WeatherResult` — used by Task 6 (round-trip test) and Task 7 (CLI).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_station_weather_converter.py`:

```python
"""Tests for StationWeatherConverter."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _make_master(tmp_path: Path, filename: str, stations: list[dict]) -> Path:
    df = pd.DataFrame(stations)
    p = tmp_path / filename
    df.to_csv(p, index=False)
    return p


def _write_swat_pcp(path: Path, start: str, values: list[float]) -> None:
    lines = [pd.Timestamp(start).strftime("%Y%m%d")]
    lines.extend(str(v) for v in values)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_swat_tmp(path: Path, start: str, pairs: list[tuple[float, float]]) -> None:
    """pairs = [(tmin, tmax), ...] -- matches the tmin,tmax convention used
    by real SWAT2012 vendor temperature files."""
    lines = [pd.Timestamp(start).strftime("%Y%m%d")]
    lines.extend(f"{tn},{tx}" for tn, tx in pairs)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


_PCP_STATIONS = [
    {"ID": 1, "NAME": "pcp_ALPHA", "LAT": 13.95, "LONG": 108.65, "ELEVATION": 416},
    {"ID": 2, "NAME": "pcp_BETA",  "LAT": 14.65, "LONG": 107.83, "ELEVATION": 616},
]

_TMP_STATIONS = [
    {"ID": 1, "NAME": "tmp_ALPHA", "LAT": 13.95, "LONG": 108.65, "ELEVATION": 416},
]


class TestStationWeatherConverterPrecip:
    def test_reads_swat_classic_precip(self, tmp_path):
        from swatprep.converters.station_weather import StationWeatherConverter

        master = _make_master(tmp_path, "master_pcp.txt", _PCP_STATIONS)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_swat_pcp(raw_dir / "pcp_ALPHA.txt", "1990-01-01", [0.0, 0.3, 1.5])
        _write_swat_pcp(raw_dir / "pcp_BETA.txt", "1990-01-01", [0.0, 0.0, 2.1])

        result = StationWeatherConverter(pcp_master=master, pcp_dir=raw_dir).convert()

        assert "precip" in result.daily
        assert set(result.daily["precip"].columns) == {"1", "2"}
        assert list(result.daily["precip"]["1"]) == [0.0, 0.3, 1.5]
        assert result.temp_stations is None
        assert result.stations.loc["1", "name"] == "ALPHA"
        assert result.stations.loc["1", "lat"] == 13.95

    def test_missing_raw_file_is_warn(self, tmp_path):
        from swatprep.converters.station_weather import StationWeatherConverter
        from swatprep.qa import failures, warnings

        master = _make_master(tmp_path, "master_pcp.txt", _PCP_STATIONS)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_swat_pcp(raw_dir / "pcp_ALPHA.txt", "1990-01-01", [0.0, 0.3, 1.5])
        # BETA has no raw file

        result = StationWeatherConverter(pcp_master=master, pcp_dir=raw_dir).convert()

        assert failures(result.qa) == []
        assert any("pcp_BETA" in c.message for c in warnings(result.qa))
        assert set(result.daily["precip"].columns) == {"1"}

    def test_csv_fallback_for_precip(self, tmp_path):
        from swatprep.converters.station_weather import StationWeatherConverter

        master = _make_master(tmp_path, "master_pcp.txt", [_PCP_STATIONS[0]])
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        df = pd.DataFrame({"date": ["1990-01-01", "1990-01-02"], "precip": [0.0, 0.3]})
        df.to_csv(raw_dir / "pcp_ALPHA.txt", index=False)

        result = StationWeatherConverter(pcp_master=master, pcp_dir=raw_dir).convert()

        assert list(result.daily["precip"]["1"]) == [0.0, 0.3]

    def test_requires_at_least_one_group(self):
        from swatprep.converters.station_weather import StationWeatherConverter
        from swatprep.errors import InputValidationError

        with pytest.raises(InputValidationError, match="at least one"):
            StationWeatherConverter()

    def test_master_without_dir_raises(self, tmp_path):
        """pcp_master given without pcp_dir must fail __init__'s pairing check
        (not the earlier "at least one" check -- pcp_master alone satisfies that)."""
        from swatprep.converters.station_weather import StationWeatherConverter
        from swatprep.errors import InputValidationError

        with pytest.raises(InputValidationError, match="together"):
            StationWeatherConverter(pcp_master=tmp_path / "master_pcp.txt")


class TestStationWeatherConverterTemperature:
    def test_reads_swat_classic_tmp(self, tmp_path):
        from swatprep.converters.station_weather import StationWeatherConverter

        master = _make_master(tmp_path, "master_tmp.txt", _TMP_STATIONS)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_swat_tmp(raw_dir / "tmp_ALPHA.txt", "1990-01-01",
                         [(16.4, 24.9), (15.3, 24.1)])

        result = StationWeatherConverter(tmp_master=master, tmp_dir=raw_dir).convert()

        assert list(result.daily["tmax"]["1"]) == [24.9, 24.1]
        assert list(result.daily["tmin"]["1"]) == [16.4, 15.3]
        assert result.precip_stations is None

    def test_combined_precip_and_temp(self, tmp_path):
        from swatprep.converters.station_weather import StationWeatherConverter

        pcp_master = _make_master(tmp_path, "master_pcp.txt", _PCP_STATIONS)
        pcp_dir = tmp_path / "pcp_raw"
        pcp_dir.mkdir()
        _write_swat_pcp(pcp_dir / "pcp_ALPHA.txt", "1990-01-01", [0.0, 0.3, 1.5])
        _write_swat_pcp(pcp_dir / "pcp_BETA.txt", "1990-01-01", [0.0, 0.0, 2.1])

        tmp_master = _make_master(tmp_path, "master_tmp.txt", _TMP_STATIONS)
        tmp_dir = tmp_path / "tmp_raw"
        tmp_dir.mkdir()
        _write_swat_tmp(tmp_dir / "tmp_ALPHA.txt", "1990-01-01",
                         [(16.4, 24.9), (15.3, 24.1), (16.0, 22.8)])

        result = StationWeatherConverter(
            pcp_master=pcp_master, pcp_dir=pcp_dir,
            tmp_master=tmp_master, tmp_dir=tmp_dir,
        ).convert()

        assert set(result.daily["precip"].columns) == {"1", "2"}
        assert set(result.daily["tmax"].columns) == {"1"}
        assert set(result.stations.index) == {"1", "2"}
        assert not result.wgn_stats.empty
        # WGN station set = union of precip and tmax columns -> both "1" and "2"
        assert set(result.wgn_stats["station_id"]) == {"1", "2"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_station_weather_converter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swatprep.converters.station_weather'`.

- [ ] **Step 3: Write the implementation**

Create `swatprep/converters/station_weather.py`:

```python
"""StationWeatherConverter: read raw per-station weather files (SWAT Classic
style or CSV) plus station master metadata into a WeatherResult, ready to be
written by WeatherWriter (SWAT2012) or SWATPlusWeatherWriter (SWAT+).

Input layout — SWAT Classic style (matches real vendor exports):
    master_pcp.txt         ID,NAME,LAT,LONG,ELEVATION  (NAME e.g. "pcp_ANKHE")
    pcp_ANKHE.txt           YYYYMMDD header line, one value per line

    master_tmp.txt         ID,NAME,LAT,LONG,ELEVATION  (NAME e.g. "tmp_ANKHE")
    tmp_ANKHE.txt           YYYYMMDD header line, "tmin,tmax" per line

CSV is also auto-detected per station file (columns "date" + the expected
variable column(s)), for stations whose raw data wasn't exported in SWAT
Classic style.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..core.weather import WeatherResult, compute_wgn_stats
from ..errors import InputValidationError
from ..qa import QACheck


class StationWeatherConverter:
    """Read raw SWAT2012-style (or CSV) station weather files into a WeatherResult."""

    def __init__(
        self,
        pcp_master: Path | None = None,
        pcp_dir: Path | None = None,
        tmp_master: Path | None = None,
        tmp_dir: Path | None = None,
        name_col: str = "NAME",
        lat_col: str = "LAT",
        lon_col: str = "LONG",
        elev_col: str = "ELEVATION",
        id_col: str = "ID",
        pcp_name_prefix: str = "pcp_",
        tmp_name_prefix: str = "tmp_",
        pcp_raw_suffix: str = ".txt",
        tmp_raw_suffix: str = ".txt",
        no_data_value: float = -99.0,
    ) -> None:
        if pcp_master is None and tmp_master is None:
            raise InputValidationError(
                "StationWeatherConverter needs at least one of pcp_master or tmp_master."
            )
        if (pcp_master is None) != (pcp_dir is None):
            raise InputValidationError("pcp_master and pcp_dir must be given together.")
        if (tmp_master is None) != (tmp_dir is None):
            raise InputValidationError("tmp_master and tmp_dir must be given together.")

        self.pcp_master = Path(pcp_master) if pcp_master is not None else None
        self.pcp_dir = Path(pcp_dir) if pcp_dir is not None else None
        self.tmp_master = Path(tmp_master) if tmp_master is not None else None
        self.tmp_dir = Path(tmp_dir) if tmp_dir is not None else None
        self.name_col = name_col
        self.lat_col = lat_col
        self.lon_col = lon_col
        self.elev_col = elev_col
        self.id_col = id_col
        self.pcp_name_prefix = pcp_name_prefix
        self.tmp_name_prefix = tmp_name_prefix
        self.pcp_raw_suffix = pcp_raw_suffix
        self.tmp_raw_suffix = tmp_raw_suffix
        self.no_data_value = no_data_value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self) -> WeatherResult:
        qa: list[QACheck] = []
        precip_stations_df: pd.DataFrame | None = None
        temp_stations_df: pd.DataFrame | None = None
        daily: dict[str, pd.DataFrame] = {}

        if self.pcp_master is not None:
            precip_stations_df = self._read_master(self.pcp_master, self.pcp_name_prefix, "precip", qa)
            precip_daily = self._read_group(
                precip_stations_df, self.pcp_dir, self.pcp_name_prefix,
                self.pcp_raw_suffix, ["precip"], "precip", qa,
            )
            daily.update(precip_daily)

        if self.tmp_master is not None:
            temp_stations_df = self._read_master(self.tmp_master, self.tmp_name_prefix, "temperature", qa)
            temp_daily = self._read_group(
                temp_stations_df, self.tmp_dir, self.tmp_name_prefix,
                self.tmp_raw_suffix, ["tmax", "tmin"], "temperature", qa,
            )
            daily.update(temp_daily)

        frames = [df for df in (precip_stations_df, temp_stations_df) if df is not None]
        all_stations = pd.concat(frames)
        all_stations = all_stations[~all_stations.index.duplicated(keep="first")]

        wgn = compute_wgn_stats(all_stations, daily, qa)

        return WeatherResult(
            stations=all_stations,
            precip_stations=precip_stations_df,
            temp_stations=temp_stations_df,
            daily=daily,
            wgn_stats=wgn,
            qa=qa,
        )

    # ------------------------------------------------------------------
    # Master (metadata) reading
    # ------------------------------------------------------------------

    def _read_master(self, path: Path, prefix: str, label: str, qa: list[QACheck]) -> pd.DataFrame:
        if not path.exists():
            raise InputValidationError(f"master file not found: {path}")
        df = pd.read_csv(path, dtype={self.id_col: str})
        required = {self.name_col, self.lat_col, self.lon_col, self.elev_col, self.id_col}
        missing = required - set(df.columns)
        if missing:
            raise InputValidationError(
                f"master file ({label}) missing columns: {sorted(missing)}. Found: {list(df.columns)}"
            )

        records = []
        for _, row in df.iterrows():
            full_name = str(row[self.name_col]).strip()
            code = full_name[len(prefix):] if full_name.startswith(prefix) else full_name
            records.append({
                "id": str(row[self.id_col]).strip(),
                "name": code,
                "lat": float(row[self.lat_col]),
                "lon": float(row[self.lon_col]),
                "elev": float(row[self.elev_col]),
            })
        out = pd.DataFrame.from_records(records).set_index("id")

        qa.append(QACheck(
            name=f"station_weather:{label}:master_loaded",
            status="pass",
            message=f"{len(out)} station(s) loaded from {path.name} ({label})",
        ))
        return out

    # ------------------------------------------------------------------
    # Raw per-station file reading
    # ------------------------------------------------------------------

    def _read_group(
        self,
        stations: pd.DataFrame,
        data_dir: Path,
        prefix: str,
        raw_suffix: str,
        variables: list[str],
        label: str,
        qa: list[QACheck],
    ) -> dict[str, pd.DataFrame]:
        per_station: dict[str, dict[str, pd.Series]] = {var: {} for var in variables}

        for sid, meta in stations.iterrows():
            full_name = f"{prefix}{meta['name']}"
            raw_file = self._find_raw_file(data_dir, full_name, raw_suffix)
            if raw_file is None:
                qa.append(QACheck(
                    name=f"station_weather:{label}:{sid}:missing_raw",
                    status="warn",
                    message=f"{full_name}: raw file not found ({full_name}{raw_suffix})",
                ))
                continue

            try:
                df = self._read_raw_file(raw_file, variables)
            except Exception as exc:
                qa.append(QACheck(
                    name=f"station_weather:{label}:{sid}:read_error",
                    status="fail",
                    message=f"Could not read {raw_file.name}: {exc}",
                ))
                continue

            indexed = df.set_index("date")
            for var in variables:
                per_station[var][sid] = indexed[var]

        result: dict[str, pd.DataFrame] = {
            var: pd.DataFrame(cols) for var, cols in per_station.items() if cols
        }

        if not result:
            raise InputValidationError(
                f"No valid station data files found for {label}. "
                f"Check the data directory and master file."
            )

        qa.append(QACheck(
            name=f"station_weather:{label}:daily_loaded",
            status="pass",
            message=(
                f"Daily data loaded ({label}): "
                f"{len(next(iter(result.values())).columns)} station(s), "
                f"variables: {', '.join(result.keys())}"
            ),
        ))
        return result

    @staticmethod
    def _find_raw_file(data_dir: Path, stem: str, suffix: str) -> Path | None:
        """Locate a raw station file, case-insensitively."""
        exact = data_dir / f"{stem}{suffix}"
        if exact.exists():
            return exact
        target = f"{stem}{suffix}".lower()
        for candidate in data_dir.iterdir():
            if candidate.name.lower() == target:
                return candidate
        return None

    @staticmethod
    def _is_swat_format(raw_file: Path) -> bool:
        """True if the file starts with an 8-digit YYYYMMDD date (SWAT Classic input)."""
        try:
            first_line = raw_file.open().readline().strip()
            return len(first_line) == 8 and first_line.isdigit()
        except OSError:
            return False

    def _read_raw_file(self, raw_file: Path, variables: list[str]) -> pd.DataFrame:
        if self._is_swat_format(raw_file):
            if variables == ["precip"]:
                return self._read_swat_pcp(raw_file)
            return self._read_swat_tmp(raw_file)

        df = pd.read_csv(raw_file, parse_dates=["date"])
        missing = set(variables) - set(df.columns)
        if missing:
            raise InputValidationError(f"{raw_file.name}: missing column(s) {sorted(missing)}")
        return df[["date", *variables]]

    @staticmethod
    def _read_swat_pcp(raw_file: Path) -> pd.DataFrame:
        """SWAT Classic precip input: line 1 = YYYYMMDD, rest = one float per line."""
        lines = raw_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        start_date = pd.to_datetime(lines[0].strip(), format="%Y%m%d")
        values = []
        for ln in lines[1:]:
            ln = ln.strip()
            if ln:
                try:
                    values.append(float(ln))
                except ValueError:
                    values.append(float("nan"))
        dates = pd.date_range(start=start_date, periods=len(values), freq="D")
        return pd.DataFrame({"date": dates, "precip": values})

    @staticmethod
    def _read_swat_tmp(raw_file: Path) -> pd.DataFrame:
        """SWAT Classic temp input: line 1 = YYYYMMDD, rest = "tmin,tmax" per line."""
        lines = raw_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        start_date = pd.to_datetime(lines[0].strip(), format="%Y%m%d")
        tmax_vals: list[float] = []
        tmin_vals: list[float] = []
        for ln in lines[1:]:
            ln = ln.strip()
            if not ln:
                continue
            parts = ln.split(",")
            if len(parts) >= 2:
                try:
                    tn, tx = float(parts[0].strip()), float(parts[1].strip())
                except ValueError:
                    tn = tx = float("nan")
                tmin_vals.append(tn)
                tmax_vals.append(tx)
            else:
                tmax_vals.append(float("nan"))
                tmin_vals.append(float("nan"))
        n = min(len(tmax_vals), len(tmin_vals))
        dates = pd.date_range(start=start_date, periods=n, freq="D")
        return pd.DataFrame({"date": dates, "tmax": tmax_vals[:n], "tmin": tmin_vals[:n]})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_station_weather_converter.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add swatprep/converters/station_weather.py tests/test_station_weather_converter.py
git commit -m "feat: add StationWeatherConverter reading raw SWAT2012-style station files"
```

---

## Task 3: Fix `WeatherWriter` SWAT2012 format

**Files:**
- Modify: `swatprep/writers/weather.py` (full rewrite — small file)
- Modify: `tests/test_weather.py:153-188, 196-252` (existing SWAT2012-format assertions)

**Interfaces:**
- Consumes: `WeatherResult` (unchanged).
- Produces: `WeatherWriter(result, output_dir).write() -> list[Path]`. Per-station files are now named `pcp_{code}.txt` / `tmp_{code}.txt` (no header block, un-offset start date). Station metadata files are now `master_pcp.txt` / `master_tmp.txt` (columns `ID,NAME,LAT,LONG,ELEVATION`, `NAME` carrying the domain prefix) instead of `stations.csv` / `precip_stations.csv` / `temp_stations.csv`. Used by Task 6 (round-trip) and Task 7 (CLI).

- [ ] **Step 1: Update the existing tests to the new expected format**

In `tests/test_weather.py`, replace the `WeatherWriter integration` section (lines 153–188) with:

```python
def test_weather_writer_creates_pcp_and_tmp(weather_stations_csv, weather_data_dir, tmp_dir):
    from swatprep.writers.weather import WeatherWriter
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    written = WeatherWriter(result, out).write()
    paths = [p.name for p in written]
    assert "pcp_StationA.txt" in paths
    assert "pcp_StationB.txt" in paths
    assert "tmp_StationA.txt" in paths
    assert "tmp_StationB.txt" in paths
    assert "master_pcp.txt" in paths
    assert "master_tmp.txt" in paths
    assert "wgn.csv" in paths


def test_pcp_file_format(weather_stations_csv, weather_data_dir, tmp_dir):
    """No metadata header block; line 1 is the date of the FIRST record (no offset)."""
    from swatprep.writers.weather import WeatherWriter
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    WeatherWriter(result, out).write()
    pcp = (out / "pcp_StationA.txt").read_text(encoding="utf-8").splitlines()
    assert pcp[0] == "20000101"
    assert len(pcp) == 11  # date line + 10 daily values
    assert pcp[1] == "1.0"  # weather_data_dir fixture: StationA precip[0] == 1.0


def test_tmp_file_has_tmin_tmax_per_line(weather_stations_csv, weather_data_dir, tmp_dir):
    from swatprep.writers.weather import WeatherWriter
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    WeatherWriter(result, out).write()
    tmp_lines = (out / "tmp_StationA.txt").read_text(encoding="utf-8").splitlines()
    tmin_str, tmax_str = tmp_lines[1].split(",")
    assert float(tmin_str) == 22.0  # weather_data_dir fixture: StationA tmin[0]
    assert float(tmax_str) == 30.1  # weather_data_dir fixture: StationA tmax[0]


def test_master_pcp_has_uppercase_columns_and_prefix(weather_stations_csv, weather_data_dir, tmp_dir):
    from swatprep.writers.weather import WeatherWriter
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    WeatherWriter(result, out).write()
    master = pd.read_csv(out / "master_pcp.txt")
    assert list(master.columns) == ["ID", "NAME", "LAT", "LONG", "ELEVATION"]
    assert {"pcp_StationA", "pcp_StationB"}.issubset(set(master["NAME"]))
```

In the same file, in `test_split_source_loads_different_stations` (around lines 241–248), replace:

```python
    out = tmp_dir / "weather_out"
    written = WeatherWriter(result, out).write()
    paths = [p.name for p in written]
    assert "PrecipA.pcp" in paths
    assert "TempA.tmp" in paths
    assert "PrecipA.tmp" not in paths
    assert "precip_stations.csv" in paths
    assert "temp_stations.csv" in paths
```

with:

```python
    out = tmp_dir / "weather_out"
    written = WeatherWriter(result, out).write()
    paths = [p.name for p in written]
    assert "pcp_PrecipA.txt" in paths
    assert "tmp_TempA.txt" in paths
    assert "tmp_PrecipA.txt" not in paths
    assert "master_pcp.txt" in paths
    assert "master_tmp.txt" in paths
```

- [ ] **Step 2: Run the updated tests to verify they fail against the old writer**

Run: `pytest tests/test_weather.py -v -k "writer or pcp_file_format or tmp_file_has or master_pcp or split_source_loads"`
Expected: FAIL — `pcp_StationA.txt` etc. don't exist yet (old writer still produces `StationA.pcp` with a header block).

- [ ] **Step 3: Rewrite `swatprep/writers/weather.py`**

Replace the entire file content with:

```python
"""WeatherWriter: write SWAT Classic (SWAT2012) .pcp/.tmp station files and a
master metadata file per domain (pcp / tmp).

Reference: Arnold, J.G. et al. (2012). SWAT: Model Use, Calibration, and Validation.
Transactions of the ASABE, 55(4), 1491-1508.

Format summary
--------------
Per-station file (`{pcp_|tmp_}{station}.txt`):
    Line 1  : date of the FIRST data record (YYYYMMDD) -- no day-before offset.
    Line 2+ : one value per day (pcp), or "tmin,tmax" per day (tmp).

There is no metadata header block in the per-station file (no title / Lati /
Long / Elev lines) -- station metadata lives only in the master file. This
matches the real SWAT2012 vendor-data convention (verified against a known
working SWAT2012 project's raw station files), not the older
Neitsch-documentation-derived 4-line-header convention this writer used to
produce.

Master (metadata) file (`master_pcp.txt` / `master_tmp.txt`):
    ID,NAME,LAT,LONG,ELEVATION      (uppercase columns; NAME carries the
                                      domain prefix, e.g. "pcp_ANKHE")
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..core.weather import WeatherResult


class WeatherWriter:
    """Write SWAT2012-ready weather files from a WeatherResult."""

    PCP_PREFIX = "pcp_"
    TMP_PREFIX = "tmp_"

    def __init__(self, result: WeatherResult, output_dir: Path) -> None:
        self.result = result
        self.output_dir = output_dir

    def write(self) -> list[Path]:
        """Write all weather files; return list of created paths."""
        out = self.output_dir
        out.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        daily = self.result.daily

        precip_wide = daily.get("precip")
        tmax_wide = daily.get("tmax")
        tmin_wide = daily.get("tmin")

        precip_stations = self.result.precip_stations if self.result.precip_stations is not None else self.result.stations
        temp_stations = self.result.temp_stations if self.result.temp_stations is not None else self.result.stations

        if precip_wide is not None:
            for sid, meta in precip_stations.iterrows():
                if sid not in precip_wide.columns:
                    continue
                code = str(meta.get("name", sid))
                p = out / f"{self.PCP_PREFIX}{code}.txt"
                _write_pcp(p, precip_wide[sid])
                written.append(p)
            written.append(self._write_master(out, precip_stations, self.PCP_PREFIX, "master_pcp.txt"))

        if tmax_wide is not None:
            for sid, meta in temp_stations.iterrows():
                if sid not in tmax_wide.columns:
                    continue
                code = str(meta.get("name", sid))
                tx = tmax_wide[sid]
                tn = tmin_wide[sid] if (tmin_wide is not None and sid in tmin_wide.columns) else None
                t = out / f"{self.TMP_PREFIX}{code}.txt"
                _write_tmp(t, tx, tn)
                written.append(t)
            written.append(self._write_master(out, temp_stations, self.TMP_PREFIX, "master_tmp.txt"))

        if not self.result.wgn_stats.empty:
            wgn_path = out / "wgn.csv"
            self.result.wgn_stats.to_csv(wgn_path, index=False)
            written.append(wgn_path)

        return written

    @staticmethod
    def _write_master(out: Path, stations: pd.DataFrame, prefix: str, filename: str) -> Path:
        df = stations.reset_index()
        master = pd.DataFrame({
            "ID": df["id"],
            "NAME": prefix + df["name"].astype(str),
            "LAT": df["lat"],
            "LONG": df["lon"],
            "ELEVATION": df["elev"],
        })
        path = out / filename
        master.to_csv(path, index=False)
        return path


# ---------------------------------------------------------------------------
# Format writers
# ---------------------------------------------------------------------------


def _fmt_value(v: float) -> str:
    """Compact numeric formatting matching the real SWAT2012 vendor convention
    (no fixed-width padding, e.g. "0.0", "1.5" -- not "     1.500")."""
    s = f"{float(v):.3f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    return s


def _write_pcp(path: Path, precip: pd.Series) -> None:
    lines = [pd.Timestamp(precip.index[0]).strftime("%Y%m%d")]
    for val in precip:
        v = val if pd.notna(val) else -99.0
        lines.append(_fmt_value(v))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_tmp(path: Path, tmax: pd.Series, tmin: pd.Series | None) -> None:
    lines = [pd.Timestamp(tmax.index[0]).strftime("%Y%m%d")]
    for i, tx_val in enumerate(tmax):
        tx = tx_val if pd.notna(tx_val) else -99.0
        if tmin is not None:
            tn_val = tmin.iloc[i] if i < len(tmin) else None
            tn = tn_val if pd.notna(tn_val) else -99.0
        else:
            tn = -99.0
        lines.append(f"{_fmt_value(tn)},{_fmt_value(tx)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_weather.py -v`
Expected: all tests PASS (this includes the WGN tests from Task 1, which are unaffected).

- [ ] **Step 5: Commit**

```bash
git add swatprep/writers/weather.py tests/test_weather.py
git commit -m "fix: SWAT2012 writer drops header block and day-before offset, adds master file"
```

---

## Task 4: Update `docs/WEATHER_OUTPUT.md`

**Files:**
- Modify: `docs/WEATHER_OUTPUT.md` (the "SWAT Classic output format" section, currently lines 168–193)

**Interfaces:** None (documentation only).

- [ ] **Step 1: Replace the SWAT Classic output format section**

Find this block in `docs/WEATHER_OUTPUT.md`:

```markdown
## SWAT Classic output format

One file per station per variable, with a 4-line header, a start-date line
(the day **before** the first record), and one value per line:

**`StationA.pcp`**
```text
Precipitation data: StationA
Lati      15.500
Long     105.200
Elev     120.000
19991231
     0.000
     5.200
```

**`StationA.tmp`** (tmax and tmin, `%10.3f` each)
```text
Temperature data: StationA
Lati      15.500
Long     105.200
Elev     120.000
19991231
    32.500    22.000
    28.300    20.500
```
```

Replace it with:

```markdown
## SWAT Classic (SWAT2012) output format

One file per station per variable, **no metadata header block** -- just a
start-date line (the date of the **first** data record, not offset) followed
by one row per day. Station metadata lives in a separate master file, not in
each per-station file. This mirrors the real SWAT2012 vendor-data convention.

**`pcp_StationA.txt`**
```text
20000101
0.0
5.2
```

**`tmp_StationA.txt`** (`tmin,tmax` per line)
```text
20000101
22.0,32.5
20.0,28.3
```

**`master_pcp.txt`** / **`master_tmp.txt`** (one row per station, uppercase
columns, `NAME` carries the domain prefix):
```text
ID,NAME,LAT,LONG,ELEVATION
1,pcp_StationA,15.5,105.2,120.0
2,pcp_StationB,15.8,105.6,95.0
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/WEATHER_OUTPUT.md
git commit -m "docs: update SWAT Classic output format to match the fixed writer"
```

---

## Task 5: Add `weather-sta.cli` + `weather-wgn.cli` to `SWATPlusWeatherWriter`

**Files:**
- Modify: `swatprep/writers/weather_plus.py` (full rewrite — small file)
- Create: `tests/test_weather_plus_writer.py`

**Interfaces:**
- Consumes: `WeatherResult` (unchanged), in particular `result.wgn_stats` (columns: `station_id, month, TMPMX, TMPMN, TMPSTDMX, TMPSTDMN, RAINHHMX, PCPMM, PCPSTD, PCPSKW, PCPD, PR_W1, PR_W2, SOLARAV, DEWPT, WNDAV` — from Task 1's `compute_wgn_stats`).
- Produces: `SWATPlusWeatherWriter(result, output_dir).write() -> list[Path]` now also writes `weather-sta.cli` and `weather-wgn.cli` (in addition to the existing `.pcp/.tmp/.hmd/.slr/.wnd`, per-variable `.cli` files, `wgn.csv`, `stations.csv`). Used by Task 7 (CLI).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_weather_plus_writer.py`:

```python
"""Tests for SWATPlusWeatherWriter's weather-sta.cli / weather-wgn.cli output."""
from __future__ import annotations

from datetime import date

import pandas as pd

from swatprep.config import WeatherConfig
from swatprep.core.weather import WeatherPreprocessor
from swatprep.writers.weather_plus import SWATPlusWeatherWriter


def _make_cfg(stations_csv, data_dir, **kwargs) -> WeatherConfig:
    defaults = dict(
        stations=stations_csv,
        data_dir=data_dir,
        start=date(2000, 1, 1),
        end=date(2000, 1, 10),
    )
    defaults.update(kwargs)
    return WeatherConfig(**defaults)


def test_weather_sta_cli_written(weather_stations_csv, weather_data_dir, tmp_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    written = SWATPlusWeatherWriter(result, out).write()
    assert (out / "weather-sta.cli") in written


def test_weather_sta_cli_lists_both_stations(weather_stations_csv, weather_data_dir, tmp_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    lines = (out / "weather-sta.cli").read_text(encoding="utf-8").splitlines()
    assert lines[1].split()[:2] == ["name", "wgn"]
    body = "\n".join(lines[2:])
    assert "StationA" in body
    assert "StationB" in body


def test_weather_sta_cli_references_written_files(weather_stations_csv, weather_data_dir, tmp_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    lines = (out / "weather-sta.cli").read_text(encoding="utf-8").splitlines()
    station_a_row = next(ln for ln in lines[2:] if ln.split()[0] == "StationA")
    fields = station_a_row.split()
    # columns: name wgn pcp tmp slr hmd wnd pet atmo_dep
    assert fields[2] == "StationA"  # pcp file stem == station name (no collisions)
    assert fields[3] == "StationA"  # tmp file stem
    assert fields[4] == "sim"       # no slr data in the fixture -> "sim"
    assert fields[7] == "null"      # pet
    assert fields[8] == "null"      # atmo_dep


def test_weather_wgn_cli_written(weather_stations_csv, weather_data_dir, tmp_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    written = SWATPlusWeatherWriter(result, out).write()
    assert (out / "weather-wgn.cli") in written


def test_weather_wgn_cli_has_12_rows_per_station(weather_stations_csv, weather_data_dir, tmp_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    lines = (out / "weather-wgn.cli").read_text(encoding="utf-8").splitlines()
    # header line + (group header + column header + 12 rows) per station
    body = lines[1:]
    assert len(body) == 2 * (2 + 12)  # 2 stations in the fixture


def test_weather_wgn_cli_column_header(weather_stations_csv, weather_data_dir, tmp_dir):
    cfg = _make_cfg(weather_stations_csv, weather_data_dir)
    result = WeatherPreprocessor(cfg).run()
    out = tmp_dir / "weather_out"
    SWATPlusWeatherWriter(result, out).write()
    lines = (out / "weather-wgn.cli").read_text(encoding="utf-8").splitlines()
    assert "tmp_max_ave" in lines[2]
    assert "wnd_ave" in lines[2]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_weather_plus_writer.py -v`
Expected: FAIL — `weather-sta.cli` / `weather-wgn.cli` don't exist yet.

- [ ] **Step 3: Rewrite `swatprep/writers/weather_plus.py`**

Replace the entire file content with:

```python
"""SWATPlusWeatherWriter: write SWAT+ daily weather files from a WeatherResult.

Unlike :class:`~swatprep.writers.weather.WeatherWriter` (which emits SWAT
Classic ``.pcp`` / ``.tmp`` files), this writer produces the SWAT+ daily
weather format plus the ``.cli`` index files that SWAT+ / QSWAT+ / SWAT+
Editor expect -- including the two "linking" files SWAT+'s TxtInOut actually
reads to resolve each station's climate data: ``weather-sta.cli`` (station
registry) and ``weather-wgn.cli`` (WGN statistics in SWAT+'s fixed format).

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

``weather-sta.cli`` (one row per station)::

    name  wgn  pcp  tmp  slr  hmd  wnd  pet  atmo_dep

Each of pcp/tmp/slr/hmd/wnd is the written data file's stem (no extension)
if that variable was written for the station, else "sim". pet/atmo_dep are
not computed by swatprep and are always "null".

``weather-wgn.cli`` -- one WGN group per station (group name == station
name), each a 3-line header (title, group header, column header) followed
by 12 monthly rows, built directly from ``WeatherResult.wgn_stats``.

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

# (WGN column in WeatherResult.wgn_stats, weather-wgn.cli column header)
_WGN_COLUMN_MAP: list[tuple[str, str]] = [
    ("TMPMX", "tmp_max_ave"),
    ("TMPMN", "tmp_min_ave"),
    ("TMPSTDMX", "tmp_max_sd"),
    ("TMPSTDMN", "tmp_min_sd"),
    ("PCPMM", "pcp_ave"),
    ("PCPSTD", "pcp_sd"),
    ("PCPSKW", "pcp_skew"),
    ("PR_W1", "wet_dry"),
    ("PR_W2", "wet_wet"),
    ("PCPD", "pcp_days"),
    ("RAINHHMX", "pcp_hhr"),
    ("SOLARAV", "slr_ave"),
    ("DEWPT", "dew_ave"),
    ("WNDAV", "wnd_ave"),
]

# weather-sta.cli variable columns, in order -- matches _Spec.ext[1:] below.
_STA_VAR_KEYS = ["pcp", "tmp", "slr", "hmd", "wnd"]


@dataclass(frozen=True)
class _Spec:
    key: str                 # primary daily-variable key in WeatherResult.daily
    ext: str                 # output file extension
    cli: str                 # .cli index filename
    descr: str                # data-file header description
    cli_desc: str             # .cli header description
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
        station_files: dict[object, dict[str, str]] = {}
        global_nbyr = 0

        for spec in _SPECS:
            frame = daily.get(spec.key)
            if frame is None or frame.empty:
                continue

            second_frame = daily.get(spec.second) if spec.second else None
            idx = frame.index
            year_arr = idx.year.to_numpy()
            doy_arr = idx.day_of_year.to_numpy()
            nbyr = int(idx.year.max() - idx.year.min() + 1)
            global_nbyr = max(global_nbyr, nbyr)
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
                station_files.setdefault(sid, {})[spec.ext[1:]] = stem

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

        # weather-sta.cli / weather-wgn.cli -- the linking files SWAT+ actually
        # reads to resolve each station's climate data.
        if not self.result.wgn_stats.empty:
            sids = list(self.result.wgn_stats["station_id"].unique())
            wgn_names = self._assign_wgn_names(stations, sids)
            written.append(_write_weather_wgn(out, self.result.wgn_stats, stations, wgn_names, global_nbyr, ts))
            written.append(_write_weather_sta(out, station_files, wgn_names, ts))

        # WGN statistics and station list (existing reference outputs, kept
        # alongside weather-wgn.cli for csv-friendly inspection)
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

    @classmethod
    def _assign_wgn_names(cls, stations: pd.DataFrame, sids: list) -> dict:
        """One WGN group name per station id, collision-free (reuses the same
        dedup rule as data-file stems, computed once so weather-sta.cli and
        weather-wgn.cli agree on the same name)."""
        used: set[str] = set()
        names: dict = {}
        for sid in sids:
            name, *_ = cls._station_meta(stations, sid)
            names[sid] = cls._unique_stem(name, sid, used)
        return names


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


def _write_weather_wgn(
    out: Path,
    wgn_stats: pd.DataFrame,
    stations: pd.DataFrame,
    wgn_names: dict,
    nbyr: int,
    ts: str,
) -> Path:
    lines = [f"weather-wgn.cli: written by swatprep {ts}"]
    col_header = "".join(f"{h:>14}" for _, h in _WGN_COLUMN_MAP)
    for sid, name in wgn_names.items():
        if sid in stations.index:
            meta = stations.loc[sid]
            lat, lon, elev = float(meta["lat"]), float(meta["lon"]), float(meta["elev"])
        else:
            lat = lon = elev = 0.0
        lines.append(f"{name:<24}{lat:14.5f}{lon:14.5f}{elev:14.5f}{nbyr:10d}")
        lines.append(col_header)
        rows = wgn_stats[wgn_stats["station_id"] == sid].sort_values("month")
        for _, row in rows.iterrows():
            lines.append("".join(f"{float(row[src]):14.5f}" for src, _ in _WGN_COLUMN_MAP))
    path = out / "weather-wgn.cli"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_weather_sta(
    out: Path,
    station_files: dict,
    wgn_names: dict,
    ts: str,
) -> Path:
    header = "".join(f"{h:<27}" for h in ["name", "wgn", *_STA_VAR_KEYS]) + "".join(
        f"{h:<10}" for h in ["pet", "atmo_dep"]
    )
    lines = [f"weather-sta.cli: written by swatprep {ts}", header]
    for sid, name in wgn_names.items():
        files = station_files.get(sid, {})
        row_vars = [files.get(key, "sim") for key in _STA_VAR_KEYS]
        row = "".join(f"{v:<27}" for v in [name, name, *row_vars]) + "".join(
            f"{v:<10}" for v in ["null", "null"]
        )
        lines.append(row)
    path = out / "weather-sta.cli"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_weather_plus_writer.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Run the full weather test suite to check for regressions**

Run: `pytest tests/test_weather.py tests/test_weather_plus_writer.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add swatprep/writers/weather_plus.py tests/test_weather_plus_writer.py
git commit -m "feat: write weather-sta.cli and weather-wgn.cli for SWAT+ output"
```

---

## Task 6: Round-trip test (`StationWeatherConverter` → `WeatherWriter` → `StationWeatherConverter`)

**Files:**
- Modify: `tests/test_station_weather_converter.py` (append one test class)

**Interfaces:**
- Consumes: `StationWeatherConverter` (Task 2), `WeatherWriter` (Task 3).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_station_weather_converter.py`:

```python
class TestStationWeatherConverterRoundTrip:
    def test_round_trip_through_weather_writer(self, tmp_path):
        from swatprep.converters.station_weather import StationWeatherConverter
        from swatprep.writers.weather import WeatherWriter

        master = _make_master(tmp_path, "master_pcp.txt", _PCP_STATIONS)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_swat_pcp(raw_dir / "pcp_ALPHA.txt", "1990-01-01", [0.0, 0.3, 1.5])
        _write_swat_pcp(raw_dir / "pcp_BETA.txt", "1990-01-01", [0.0, 0.0, 2.1])

        result1 = StationWeatherConverter(pcp_master=master, pcp_dir=raw_dir).convert()

        out = tmp_path / "out"
        WeatherWriter(result1, out).write()

        result2 = StationWeatherConverter(
            pcp_master=out / "master_pcp.txt", pcp_dir=out,
        ).convert()

        assert list(result2.daily["precip"]["1"]) == [0.0, 0.3, 1.5]
        assert list(result2.daily["precip"]["2"]) == [0.0, 0.0, 2.1]
        assert result2.stations.loc["1", "name"] == "ALPHA"
        assert result2.stations.loc["2", "name"] == "BETA"
```

- [ ] **Step 2: Run the test to verify it fails (or passes for the wrong reason)**

Run: `pytest tests/test_station_weather_converter.py -v -k round_trip`
Expected: If Task 2 and Task 3 are already done, this should already PASS on first run — it's exercising two already-implemented pieces together for the first time, not new code. Confirm it passes; if it fails, the mismatch between `WeatherWriter`'s output naming/format and `StationWeatherConverter`'s reading assumptions needs fixing (see Step 3).

- [ ] **Step 3: Fix any mismatch found, then re-run**

If Step 2 failed, the most likely cause is a filename or master-column mismatch between Task 3's `WeatherWriter._write_master`/`_write_pcp` and Task 2's `StationWeatherConverter._read_master`/`_find_raw_file` defaults (both must agree: uppercase `ID,NAME,LAT,LONG,ELEVATION` columns, `pcp_{code}.txt` filenames). Fix the mismatch in whichever file is wrong relative to the design spec (`docs/superpowers/specs/2026-08-31-weather-converter-unification-design.md`), then re-run:

Run: `pytest tests/test_station_weather_converter.py -v -k round_trip`
Expected: PASS.

- [ ] **Step 4: Run the full converter test suite**

Run: `pytest tests/test_station_weather_converter.py tests/test_weather.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_station_weather_converter.py
git commit -m "test: verify StationWeatherConverter/WeatherWriter round-trip"
```

---

## Task 7: New `swatprep convert weather` CLI command; delete old converters

**Files:**
- Delete: `swatprep/converters/swat2012.py`, `swatprep/converters/pcp.py`, `swatprep/converters/tmp.py`, `swatprep/converters/weather_plus.py`
- Delete: `tests/test_pcp_converter.py`, `tests/test_tmp_converter.py`, `tests/test_weather_plus.py`
- Modify: `swatprep/converters/__init__.py`
- Modify: `swatprep/cli.py:283-597` (remove `convert pcp`/`convert tmp`/`convert swatplus`, add `convert weather`)
- Modify: `tests/test_converters.py` (remove the 3 obsolete CLI smoke tests, fix `test_python_m_cli_runs`)

**Interfaces:**
- Consumes: `StationWeatherConverter` (Task 2), `WeatherWriter` (Task 3), `SWATPlusWeatherWriter` (Task 5).
- Produces: `swatprep convert weather [OPTIONS] OUT_DIR` CLI command. Used by Task 8's CLI tests.

- [ ] **Step 1: Delete the obsolete converter modules and their dedicated test files**

```bash
git rm swatprep/converters/swat2012.py swatprep/converters/pcp.py swatprep/converters/tmp.py swatprep/converters/weather_plus.py
git rm tests/test_pcp_converter.py tests/test_tmp_converter.py tests/test_weather_plus.py
```

- [ ] **Step 2: Update `swatprep/converters/__init__.py`**

Replace its entire content with:

```python
from .climate import DayFilesConverter
from .streamflow import StreamflowConverter
from .station_weather import StationWeatherConverter
```

- [ ] **Step 3: Remove the obsolete CLI smoke tests from `tests/test_converters.py`**

Delete the three test methods `test_cli_convert_pcp_runs`, `test_cli_convert_tmp_runs`, `test_cli_convert_swatplus_runs` (currently lines 366–445 of `tests/test_converters.py`, the last three methods in `TestCLIConvert` / end of file).

Replace `test_python_m_cli_runs` (currently lines 329–338):

```python
    def test_python_m_cli_runs(self):
        res = subprocess.run(
            [sys.executable, "-m", "swatprep.cli", "convert", "swatplus", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        assert res.returncode == 0
        assert "PCP_DIR" in res.stdout
```

with:

```python
    def test_python_m_cli_runs(self):
        res = subprocess.run(
            [sys.executable, "-m", "swatprep.cli", "convert", "weather", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        assert res.returncode == 0
        assert "--pcp-master" in res.stdout
```

(The new `convert weather` CLI tests themselves are added in Task 8, appended after this point in the same class.)

- [ ] **Step 4: Run the trimmed `test_converters.py` to verify it fails on the updated smoke test**

Run: `pytest tests/test_converters.py -v -k test_python_m_cli_runs`
Expected: FAIL — `swatprep convert weather` doesn't exist yet.

- [ ] **Step 5: Replace the `convert pcp`/`convert tmp`/`convert swatplus` commands in `swatprep/cli.py`**

Delete everything from the `@convert.command("pcp")` decorator (currently line 283) through the end of the file, **including** the trailing `if __name__ == "__main__": main()` guard (currently lines 599–601) — the replacement below supplies its own copy of that guard, so leaving the original in place would duplicate it.

In its place, add:

```python
@convert.command("weather")
@click.option("--pcp-master", type=click.Path(exists=True, path_type=Path), default=None,
              help="Master CSV for precipitation stations (ID,NAME,LAT,LONG,ELEVATION).")
@click.option("--pcp-dir", type=click.Path(exists=True, path_type=Path), default=None,
              help="Directory containing raw precipitation station files.")
@click.option("--tmp-master", type=click.Path(exists=True, path_type=Path), default=None,
              help="Master CSV for temperature stations (ID,NAME,LAT,LONG,ELEVATION).")
@click.option("--tmp-dir", type=click.Path(exists=True, path_type=Path), default=None,
              help="Directory containing raw temperature station files.")
@click.option("--target", "targets", multiple=True,
              type=click.Choice(["swat2012", "swatplus"]), default=("swat2012",),
              show_default=True,
              help="Output format to write. Repeatable, e.g. --target swat2012 --target swatplus.")
@click.argument("out_dir", type=click.Path(path_type=Path))
def convert_weather(
    pcp_master: Path | None,
    pcp_dir: Path | None,
    tmp_master: Path | None,
    tmp_dir: Path | None,
    targets: tuple[str, ...],
    out_dir: Path,
) -> None:
    """Convert raw station weather files to SWAT2012 and/or SWAT+ format.

    Reads a precipitation group (--pcp-master + --pcp-dir) and/or a
    temperature group (--tmp-master + --tmp-dir) of raw per-station files,
    auto-detecting SWAT Classic style (YYYYMMDD header + one value per line)
    or CSV. At least one group must be given.

    Writes to OUT_DIR for each --target given. When more than one target is
    given, each is written to its own OUT_DIR/<target>/ subdirectory so the
    two formats' filenames don't collide.

    OUT_DIR   Directory where the converted weather files will be written.
    """
    from .converters.station_weather import StationWeatherConverter
    from .qa import failures, warnings

    converter = StationWeatherConverter(
        pcp_master=pcp_master, pcp_dir=pcp_dir,
        tmp_master=tmp_master, tmp_dir=tmp_dir,
    )
    result = converter.convert()

    for c in result.qa:
        symbol = {"pass": "v", "warn": "!", "fail": "x"}[c.status]
        click.echo(f"  {symbol} {c.name}: {c.message}")

    fail_list = failures(result.qa)
    if fail_list:
        click.echo(f"Failed: {len(fail_list)} check(s).", err=True)
        sys.exit(1)

    multi = len(targets) > 1
    written: list[Path] = []
    for target in targets:
        dest = out_dir / target if multi else out_dir
        if target == "swat2012":
            from .writers.weather import WeatherWriter
            written += WeatherWriter(result, dest).write()
        elif target == "swatplus":
            from .writers.weather_plus import SWATPlusWeatherWriter
            written += SWATPlusWeatherWriter(result, dest).write()

    click.echo(f"\nFiles written : {len(written)}")
    click.echo(f"Output dir    : {out_dir}")
    click.echo(f"Targets       : {', '.join(targets)}")

    warn_list = warnings(result.qa)
    if warn_list:
        click.echo(f"Warnings: {len(warn_list)}")


if __name__ == "__main__":
    main()
```

Also update the module docstring at the top of `swatprep/cli.py` (lines 5–12) to add the new command; replace:

```python
Commands:
    swatprep validate config.yaml
    swatprep build config.yaml [--only DOMAIN]
    swatprep inspect raster PATH
    swatprep inspect weather PATH
    swatprep convert climate DATA_DIR OUT_DIR
    swatprep convert streamflow SOURCE OUT_PATH
```

with:

```python
Commands:
    swatprep validate config.yaml
    swatprep build config.yaml [--only DOMAIN]
    swatprep inspect raster PATH
    swatprep inspect weather PATH
    swatprep convert climate DATA_DIR OUT_DIR
    swatprep convert streamflow SOURCE OUT_PATH
    swatprep convert weather [--pcp-master ... --pcp-dir ...] [--tmp-master ... --tmp-dir ...] OUT_DIR
```

- [ ] **Step 6: Run the smoke test to verify it now passes**

Run: `pytest tests/test_converters.py -v -k test_python_m_cli_runs`
Expected: PASS.

- [ ] **Step 7: Run the full test suite to check nothing else references the deleted modules**

Run: `pytest tests/ -v -k "not rasterio"`
Expected: all PASS, no `ImportError`/`ModuleNotFoundError` for `swat2012`, `pcp`, `tmp`, or `weather_plus` converter modules.

- [ ] **Step 8: Commit**

```bash
git add -A swatprep/converters swatprep/cli.py tests/test_converters.py
git commit -m "feat: replace convert pcp/tmp/swatplus with a unified convert weather command"
```

---

## Task 8: CLI tests for `swatprep convert weather`

**Files:**
- Modify: `tests/test_converters.py` (append to `TestCLIConvert`)

**Interfaces:** None (final consumer of Task 7's CLI command).

- [ ] **Step 1: Write the failing tests**

Append these methods to the `TestCLIConvert` class at the end of `tests/test_converters.py` (after the updated `test_python_m_cli_runs` from Task 7):

```python
    def test_cli_convert_weather_swat2012(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        master = tmp_path / "master_pcp.txt"
        pd.DataFrame([{
            "ID": 1, "NAME": "pcp_ALPHA", "LAT": 13.95, "LONG": 108.65, "ELEVATION": 416,
        }]).to_csv(master, index=False)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        (raw_dir / "pcp_ALPHA.txt").write_text("20000101\n0.0\n0.3\n1.5\n", encoding="utf-8")

        out = tmp_path / "out"
        runner = CliRunner()
        res = runner.invoke(
            main,
            ["convert", "weather", "--pcp-master", str(master), "--pcp-dir", str(raw_dir),
             "--target", "swat2012", str(out)],
        )

        assert res.exit_code == 0, res.output
        assert (out / "pcp_ALPHA.txt").exists()
        assert (out / "master_pcp.txt").exists()

    def test_cli_convert_weather_swatplus(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        master = tmp_path / "master_pcp.txt"
        pd.DataFrame([{
            "ID": 1, "NAME": "pcp_ALPHA", "LAT": 13.95, "LONG": 108.65, "ELEVATION": 416,
        }]).to_csv(master, index=False)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        (raw_dir / "pcp_ALPHA.txt").write_text("20000101\n0.0\n0.3\n1.5\n", encoding="utf-8")

        out = tmp_path / "out"
        runner = CliRunner()
        res = runner.invoke(
            main,
            ["convert", "weather", "--pcp-master", str(master), "--pcp-dir", str(raw_dir),
             "--target", "swatplus", str(out)],
        )

        assert res.exit_code == 0, res.output
        assert (out / "pcp.cli").exists()
        assert (out / "weather-sta.cli").exists()
        assert (out / "weather-wgn.cli").exists()

    def test_cli_convert_weather_both_targets_use_subdirs(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        master = tmp_path / "master_pcp.txt"
        pd.DataFrame([{
            "ID": 1, "NAME": "pcp_ALPHA", "LAT": 13.95, "LONG": 108.65, "ELEVATION": 416,
        }]).to_csv(master, index=False)
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        (raw_dir / "pcp_ALPHA.txt").write_text("20000101\n0.0\n0.3\n1.5\n", encoding="utf-8")

        out = tmp_path / "out"
        runner = CliRunner()
        res = runner.invoke(
            main,
            ["convert", "weather", "--pcp-master", str(master), "--pcp-dir", str(raw_dir),
             "--target", "swat2012", "--target", "swatplus", str(out)],
        )

        assert res.exit_code == 0, res.output
        assert (out / "swat2012" / "pcp_ALPHA.txt").exists()
        assert (out / "swatplus" / "pcp.cli").exists()

    def test_cli_convert_weather_requires_one_group(self, tmp_path):
        from click.testing import CliRunner
        from swatprep.cli import main

        runner = CliRunner()
        res = runner.invoke(main, ["convert", "weather", str(tmp_path / "out")])

        assert res.exit_code != 0
```

- [ ] **Step 2: Run the tests to verify they fail (or already pass)**

Run: `pytest tests/test_converters.py -v -k convert_weather`
Expected: If Task 7 is complete, these should already PASS — they exercise the already-built CLI command for the first time with these exact scenarios, not new production code. Confirm all 4 PASS.

- [ ] **Step 3: If any test fails, fix the mismatch**

Likely causes: `--target` default behavior, subdirectory naming (`out_dir / target`), or `StationWeatherConverter`'s `InputValidationError` not propagating as a non-zero CLI exit code (Click surfaces unhandled exceptions as exit code 1 by default under `CliRunner`, so `test_cli_convert_weather_requires_one_group` should pass without extra handling — if it doesn't, check that `StationWeatherConverter()` with no arguments actually raises before any output is written). Fix in `swatprep/cli.py` per the design spec, then re-run Step 2's command.

- [ ] **Step 4: Run the complete test suite**

Run: `pytest tests/ -v -k "not rasterio"`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_converters.py
git commit -m "test: add CLI tests for swatprep convert weather"
```

---

## Final verification

- [ ] Run the complete suite once more end-to-end: `pytest tests/ -v -k "not rasterio"` — expect all green.
- [ ] Grep for any leftover references to the deleted symbols: `grep -rn "PCPConverter\|TmpConverter\|SWATPlusWeatherConverter\|converters.swat2012\|converters.weather_plus\b" swatprep/ tests/ docs/ README.md` — expect no matches outside of history/specs.
- [ ] Skim `README.md`'s "Implemented" list for any mention of the removed `convert pcp`/`tmp`/`swatplus` commands and update if present.
