# Weather gap-fill from an external bias-corrected source

Date: 2026-09-01
Status: Approved for planning

## Problem

`swatprep` currently only *detects* missing days in weather station data —
`WeatherConfig.missing_policy` ("fail"/"warn") controls whether a gap becomes
a QA failure or a warning, but the gap itself is never filled. Nothing in the
codebase imputes a value for a missing day.

Users preparing SWAT/SWAT+ weather input commonly have an external data
source (most often a satellite/reanalysis product such as CHIRPS or ERA5,
already extracted by the user into a per-station time series at each real
station's coordinates — swatprep does not fetch or extract this data itself)
that can plausibly stand in for missing observed days, once corrected for the
systematic bias between the external source and the real gauge.

## Goal

Add a standalone preprocessing step, `swatprep fill weather`, that:

1. Reads the real (observed) station data and an external fill source, both
   in swatprep's existing per-station CSV format.
2. For each station × variable, computes a bias-correction factor from the
   days where both sources have data (the "overlap" period).
3. Fills only the real station's missing days using the corrected external
   value — never touches a day the real station already has.
4. Writes the result back out in the same per-station CSV format swatprep
   already reads elsewhere, so it drops straight into `weather.data_dir` for
   the normal `swatprep build` pipeline.

This is a data-preparation step, run *before* `build()`, not a new domain
inside the config-driven pipeline — consistent with how `swatprep convert`
already works (raw/imperfect data in, swatprep-standard CSVs out).

## Non-goals

- **No automatic data download.** The user supplies the external source as
  files already on disk (matches the existing "out of scope: automatic
  public data download" boundary in `README.md`).
- **No raster/NetCDF ingestion in this iteration.** The external source is
  CSV point-series only for now (see Architecture below for how the design
  leaves room for a raster/NetCDF reader later without touching the
  correction/fill logic).
- **No monthly-resolution correction.** One overall bias-correction value
  per station per variable, not 12 monthly values — keeps the minimum
  overlap-data requirement low, which matters because real-world overlap
  periods between a gauge record and a satellite product are often short.
- **Streamflow gap-filling** is out of scope for this spec (weather only,
  per explicit scoping decision during brainstorming).

## Architecture

Reuse the existing `WeatherConfig`/`WeatherSourceConfig`/`WeatherPreprocessor`
machinery for *loading* both sources — don't reimplement CSV reading,
reindexing, or per-station column matching. Both the real station data and
the external fill source are, structurally, just another `WeatherConfig`
(`stations` CSV + `data_dir` + `file_pattern`), and `WeatherPreprocessor.run()`
already turns that into a `daily: dict[str, pd.DataFrame]` (variable → wide
`DatetimeIndex × station_id` table, gaps already reindexed to `NaN`) for a
given `start`/`end` range. Loading both sources with the *same* `start`/`end`
guarantees their wide tables share an identical `DatetimeIndex`, so per-station
series from each side are already date-aligned — no separate join step needed.

```
--stations/--data-dir (real)         --fill-stations/--fill-data-dir (external)
        │                                          │
        ▼                                          ▼
  WeatherConfig ──▶ WeatherPreprocessor.run() ──▶ WeatherResult.daily
        │                                          │
        └──────────────────┬───────────────────────┘
                            ▼
              swatprep/core/weather_fill.py
              (new: WeatherGapFiller)
                            │
        per station × variable:
          1. overlap = obs.notna() & fill.notna()
          2. correction from overlap (ratio for precip, offset otherwise)
          3. fill obs's NaN days from corrected external values
          4. record a fill_report.csv row (counts + correction + status)
                            │
                            ▼
              stations.csv + {id}.csv per station (swatprep-native format)
              + fill_report.csv
                            │
                            ▼
         point weather.data_dir here → swatprep build (unchanged)
```

`WeatherGapFiller` operates on `daily: dict[str, pd.DataFrame]` — the exact
type `WeatherPreprocessor` already produces and `StationWeatherConverter`
(from the earlier weather-converter-unification work) also produces. It does
not know or care how each side's `daily` dict was built. A future
raster/NetCDF fill-source reader would only need to produce the same
`dict[str, pd.DataFrame]` shape (e.g. by extracting a value per day per
station coordinate) — `WeatherGapFiller`'s correction/fill logic would not
change. Not built now; the seam is free from reusing this existing type.

## Station matching

Real and fill-source stations are matched by `id` (the same primary key
`WeatherConfig.stations` already uses). The fill-source `stations.csv` is
expected to use the same station IDs as the real one — natural for this use
case, since the fill source is *already* a per-real-station extraction at
that station's coordinates (so its `lat`/`lon`/`elev` columns are typically
identical to the real station's, even though only `id` is actually used for
matching).

A real station with missing days but no matching `id` in the fill source
gets a `QACheck(status="warn")` ("no fill source for station X") and is left
unfilled for that variable — not an error, matches the existing "one bad
station must not block the rest" QA convention.

## Correction algorithm

Computed once per station × variable, from the overlap days (both sources
non-`NaN` on that day):

- **`precip`** — multiplicative ratio:
  `factor = mean(obs[overlap]) / mean(fill[overlap])`. Applied as
  `filled = fill_value * factor`, clipped to `>= 0` (precipitation can't be
  negative). If `mean(fill[overlap]) <= 0` the ratio is undefined — skip
  filling that station/variable, `QACheck(status="warn")`.
- **`tmax` / `tmin` / `solar` / `humidity` / `wind`** — additive offset:
  `offset = mean(obs[overlap]) - mean(fill[overlap])`. Applied as
  `filled = fill_value + offset`.
- Filling only ever writes into days where the real station is `NaN`. A day
  the real station already has a value for is never touched, regardless of
  what the fill source says.
- `--min-overlap-days` (default `10`): if the overlap count is below this
  threshold but still `> 0`, filling proceeds but the QA status for that
  station/variable is `"warn"` ("low confidence: only N overlap day(s)"). If
  overlap is exactly `0`, no correction can be computed — filling is skipped
  entirely for that station/variable (days stay `NaN`, still catchable by
  `missing_policy` in the later `build()` run), `QACheck(status="warn")`.
- Check order: the "correction is mathematically undefined" case
  (`mean(fill[overlap]) <= 0` for precip) is checked first, independent of
  `--min-overlap-days` — an undefined ratio skips filling regardless of how
  much overlap exists. The `--min-overlap-days` threshold only downgrades
  confidence for a correction that *was* computable.

## CLI

New command, alongside the existing `convert` group:

```bash
swatprep fill weather \
  --stations STATIONS.csv --data-dir DATA_DIR [--file-pattern "{id}.csv"] \
  --fill-stations FILL_STATIONS.csv --fill-data-dir FILL_DATA_DIR [--fill-file-pattern "{id}.csv"] \
  --variables precip,tmax,tmin \
  --start 2000-01-01 --end 2000-12-31 \
  [--min-overlap-days 10] \
  OUT_DIR
```

- `--stations`/`--data-dir` and `--fill-stations`/`--fill-data-dir` are both
  **required** (unlike `convert weather`'s optional pcp/tmp groups — gap-fill
  needs both a real source and a fill source to do anything).
  `--file-pattern`/`--fill-file-pattern` default to `"{id}.csv"`, matching
  `WeatherSourceConfig.file_pattern`'s existing default.
- `--variables` is a comma-separated list from the same six
  `WeatherConfig.variables` accepts (`precip,tmax,tmin,wind,solar,humidity`);
  default `precip,tmax,tmin` (matches `WeatherConfig`'s own default).
- `--start`/`--end` are required (same ISO-date requirement as
  `WeatherConfig`) and apply to loading *both* sources.
- Internally, both `WeatherConfig` objects are built with
  `missing_policy="warn"` (never `"fail"`) — the fill step's job is
  precisely to work with data that has gaps, so it must not raise on them.

## Output

Written to `OUT_DIR`:

- `stations.csv` — copied from the real station metadata (`id,name,lat,lon,elev`).
- `{id}.csv` per real station — same shape as the existing example
  (`examples/data/weather/ST001.csv`): `date` + one column per requested
  variable, covering `--start`..`--end`. Non-missing days are the original
  observed values, unchanged; missing days are filled where a correction was
  available, otherwise left blank/`NaN` as before.
- `fill_report.csv` — one row per station × variable actually attempted:
  `station_id, variable, n_missing, n_filled, n_still_missing, n_overlap, correction_type (ratio|offset), correction_value, status (pass|warn)`.

Point `weather.data_dir` (and `weather.stations`) at `OUT_DIR` and run
`swatprep build` as normal — no changes needed to the build pipeline itself.

## Testing

- `WeatherGapFiller` unit tests (new `tests/test_weather_fill.py`): ratio
  correction for precip (including the `mean(fill[overlap]) <= 0` skip
  case), additive offset for temperature, a day the real station already has
  is never overwritten, `--min-overlap-days` threshold behavior (below
  threshold → warn but still fills; zero overlap → skip, stays `NaN`), a
  station present in the real data but absent from the fill source (warn,
  skip).
- CLI tests (extend `tests/test_converters.py` or a new
  `TestCLIFillWeather` group): end-to-end run producing `stations.csv`,
  per-station CSVs, and `fill_report.csv` with expected content; missing
  required option (e.g. no `--fill-stations`) fails with a clear error.
- Round-trip/integration test: filled output directory can be pointed at
  `WeatherConfig.stations`/`data_dir` and loaded by `WeatherPreprocessor`
  without new gaps introduced by the fill step's CSV writer (i.e. verifies
  the output format is genuinely compatible with the existing loader, not
  just superficially similar).

## Out of scope

- Raster/NetCDF fill sources (architecture leaves room, not built).
- Streamflow or any non-weather domain gap-filling.
- Automatic download/fetch of external reference data.
- Monthly or seasonal bias-correction granularity (single overall factor
  only).
- Wiring gap-fill into the config-driven `build()` pipeline automatically —
  it stays a separate, explicit `swatprep fill weather` step the user runs
  before `build()`, mirroring `swatprep convert`.
