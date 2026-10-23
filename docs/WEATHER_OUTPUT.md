# Weather Output & Formats

`swatprep build` turns per-station weather CSVs into SWAT-ready weather files.
The **format** it writes is selected by `project.targets` in your config — the
same `WeatherResult` can be emitted as **SWAT+** files, **SWAT Classic** files,
or both.

- [Choosing the output model (`targets`)](#choosing-the-output-model-targets)
- [Input: station CSVs and `file_pattern`](#input-station-csvs-and-file_pattern)
- [Split precip / temperature sources](#split-precip--temperature-sources)
- [SWAT+ output format](#swat-output-format)
- [SWAT Classic output format](#swat-classic-output-format)
- [Variable → file mapping](#variable--file-mapping)
- [Output directory layout](#output-directory-layout)
- [Programmatic use](#programmatic-use)
- [Converters vs. the build pipeline](#converters-vs-the-build-pipeline)

---

## Choosing the output model (`targets`)

```yaml
project:
  name: "ExampleBasin"
  crs: "EPSG:32648"
  output_dir: "./output"
  targets:
    - "swatplus"   # default
    # - "swat"     # add this line to also emit SWAT Classic files
```

| `targets` value | Weather writer | Files |
|---|---|---|
| `swatplus` (default) | `SWATPlusWeatherWriter` | `.pcp/.tmp/.hmd/.slr/.wnd` (with `year day value` rows) + per-variable `*.cli` index files + `weather-sta.cli`/`weather-wgn.cli` |
| `swat` | `WeatherWriter` | SWAT Classic `pcp_<name>.txt`/`tmp_<name>.txt` (no header block, un-offset start date) + `master_pcp.txt`/`master_tmp.txt` |
| both | both writers | each format in its own sub-directory (see [layout](#output-directory-layout)) |

`targets` defaults to `["swatplus"]`. If it is empty, `build()` falls back to
`swatplus`.

> **Why this matters:** SWAT+ Editor / QSWAT+ cannot read SWAT Classic weather
> files, and vice-versa. The two formats differ in header, per-row layout, and
> whether `.cli` index files are produced — see the format sections below.

---

## Input: station CSVs and `file_pattern`

Weather input is one CSV per station plus a station-metadata CSV:

**`stations.csv`** — one row per station:

```csv
id,name,lat,lon,elev
ST001,StationA,15.5,105.2,120
ST002,StationB,15.8,105.6,95
```

**Per-station daily CSV** — `date` plus one column per variable:

```csv
date,precip,tmax,tmin
2000-01-01,0.0,32.5,22.0
2000-01-02,5.2,28.3,20.5
```

The loader finds each station's daily file with **`file_pattern`**:

| Field | Default | Notes |
|---|---|---|
| `file_pattern` | `"{id}.csv"` | `{id}` → station id, `{name}` → station `name` column |

```yaml
weather:
  stations: "./data/weather_stations.csv"
  data_dir: "./data/weather"      # contains ST001.csv, ST002.csv, ...
  file_pattern: "{id}.csv"        # default — matches files named by station id
  variables: ["precip", "tmax", "tmin"]
  start: "2000-01-01"
  end:   "2000-12-31"
  missing_policy: "warn"          # "fail" | "warn"
```

If your daily files are named by station **name** (e.g. `StationA.csv`), set
`file_pattern: "{name}.csv"`.

> Output file names are always derived from the station **name**, regardless of
> `file_pattern`. `SWATPlusWeatherWriter` (SWAT+ output) dedups a shared name
> with a `{name}_{id}` suffix. `WeatherWriter` (SWAT Classic output) does
> **not** dedup — two stations sharing a name will overwrite one file.

---

## Split precip / temperature sources

Precipitation and temperature often come from different station networks. You
can give each its own station list, directory, and `file_pattern`:

```yaml
weather:
  variables: ["precip", "tmax", "tmin"]
  start: "2000-01-01"
  end:   "2000-12-31"

  precip:
    stations: "./data/precip_stations.csv"
    data_dir: "./data/precip"
    file_pattern: "{id}.csv"

  temp:
    stations: "./data/temp_stations.csv"
    data_dir: "./data/temp"
    file_pattern: "{name}.csv"
```

Rules:

- Set the top-level `stations` + `data_dir` **or** a per-group `precip` / `temp`
  block for each variable group you use. Validation fails otherwise.
- A per-group block overrides the top-level default for that group only.
- In split mode the SWAT Classic writer builds `master_pcp.txt` from the
  precip station group and `master_tmp.txt` from the temperature station
  group (each restricted to the stations whose data file was actually
  written); the SWAT+ writer still lists all stations in the union
  `stations.csv`.

> **Caveat:** split mode currently loads only `precip`, `tmax`, and `tmin`.
> `humidity`, `solar`, and `wind` are read only in unified mode (single
> top-level `stations` + `data_dir`).

---

## SWAT+ output format

One file per station per variable, with a 3-line header and `year day-of-year
value` rows:

**`StationA.pcp`**
```text
StationA.pcp: Precipitation data - file written by swatprep 2026-07-12 22:12:49
nbyr     tstep       lat       lon      elev
   1         0    15.500   105.200   120.000
2000    1    0.00000
2000    2    5.20000
```

**`StationA.tmp`** (two values per row: tmax then tmin)
```text
StationA.tmp: Temperature data - file written by swatprep 2026-07-12 22:12:49
nbyr     tstep       lat       lon      elev
   1         0    15.500   105.200   120.000
2000    1   32.50000    22.00000
2000    2   28.30000    20.50000
```

Each variable group also gets a `.cli` **index file** listing its data files —
this is what SWAT+ reads to discover the per-station files:

**`pcp.cli`**
```text
pcp.cli: Precipitation file names - file written by swatprep 2026-07-12 22:12:49
filename
StationA.pcp
StationB.pcp
```

Two additional "linking" files are written after the per-variable data and
`.cli` files -- these are what a SWAT+ `TxtInOut` folder actually reads to
resolve each station's climate data, and without them the output cannot be
dropped into a `TxtInOut` folder as-is:

- **`weather-sta.cli`** — one row per station: `name`, `wgn` (its WGN group
  name), then `pcp`/`tmp`/`slr`/`hmd`/`wnd` (the written data file's stem if
  that variable was written for the station, else `"sim"`), and `pet`/
  `atmo_dep` (always `"null"` — not computed by swatprep).
- **`weather-wgn.cli`** — the weather-generator statistics in SWAT+'s fixed
  format: one WGN group per station (group name = station name), each a
  3-line header (title, group header with lat/lon/elev/nbyr, column header)
  followed by 12 monthly rows built from `WeatherResult.wgn_stats`.

Missing values are written as `-99.0`. `wgn.csv` (the same WGN statistics in
csv-friendly form) and `stations.csv` are also written for reference.

---

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

`ID` is the **serial number (STT)** of the station in that file: 1, 2, 3, ... in the order of the stations
table. It is **not** the source station `id` (e.g. `ST009`). `master_pcp.txt` and `master_tmp.txt` are numbered
separately, so with split precipitation / temperature networks each file counts from 1. Only stations whose
data file was written get a row, so there are no gaps in the numbering.

---

## Variable → file mapping

| `variables` entry | SWAT+ file | `.cli` index | SWAT Classic file |
|---|---|---|---|
| `precip` | `<name>.pcp` | `pcp.cli` | `pcp_<name>.txt` |
| `tmax` + `tmin` | `<name>.tmp` | `tmp.cli` | `tmp_<name>.txt` |
| `humidity` | `<name>.hmd` | `hmd.cli` | — |
| `solar` | `<name>.slr` | `slr.cli` | — |
| `wind` | `<name>.wnd` | `wnd.cli` | — |

The SWAT Classic writer only emits `pcp_<name>.txt` and `tmp_<name>.txt`;
humidity/solar/wind are carried into the SWAT+ output and `wgn.csv` only.

---

## Output directory layout

**Single target** (e.g. `targets: ["swatplus"]`) — files land directly in
`output/weather/`:

```text
output/weather/
  StationA.pcp   StationA.tmp
  StationB.pcp   StationB.tmp
  pcp.cli        tmp.cli
  weather-sta.cli   weather-wgn.cli
  wgn.csv        stations.csv
```

**Both targets** (`targets: ["swatplus", "swat"]`) — each format gets its own
sub-directory so identically named files don't collide:

```text
output/weather/
  swatplus/
    StationA.pcp   StationA.tmp   pcp.cli   tmp.cli
    weather-sta.cli   weather-wgn.cli   wgn.csv   stations.csv
  swat/
    pcp_StationA.txt   tmp_StationA.txt
    pcp_StationB.txt   tmp_StationB.txt
    master_pcp.txt   master_tmp.txt   wgn.csv
```

---

## Programmatic use

The pipeline picks the writer for you based on `targets`. To call a writer
directly on a `WeatherResult`:

```python
from swatprep.core.weather import WeatherPreprocessor
from swatprep.writers.weather_plus import SWATPlusWeatherWriter
from swatprep.writers.weather import WeatherWriter

result = WeatherPreprocessor(cfg.weather).run()

SWATPlusWeatherWriter(result, out_dir / "swatplus").write()   # SWAT+
WeatherWriter(result, out_dir / "swat").write()               # SWAT Classic
```

Both writers take `(WeatherResult, output_dir)` and return the list of written
`Path`s.

---

## Converters vs. the build pipeline

Two different entry points can produce SWAT+/Classic weather files:

- **`swatprep build`** (this document) — runs the full preprocessing pipeline
  from a config and writes weather output using the writers above.
- **`swatprep convert ...`** — standalone converters that transform *raw*
  vendor formats (e.g. Vietnamese `.day` files, SWAT2012 vendor
  `pcp_<name>.txt`/`tmp_<name>.txt` station files) into swatprep CSVs or
  directly into SWAT+/SWAT2012 files, independent of the pipeline. See the
  converter reference in `DEVELOPER_GUIDE.md` (§8b).

Use converters to *prepare* raw data into per-station CSVs, then point
`weather.data_dir` at those CSVs and run `build`.
