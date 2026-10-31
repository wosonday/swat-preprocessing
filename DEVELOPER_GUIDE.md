# swatprep — Developer & User Guide

> **Scope**: `swatprep` là một thư viện Python preprocessing chuyên dụng.  
> Nó **không** chạy SWAT, không delineate watershed, không calibrate.  
> Nó nhận raw data đầu vào và xuất ra một **SWAT-ready input package** đã được kiểm tra chất lượng.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Installation & Setup](#2-installation--setup)
3. [Configuration Reference](#3-configuration-reference)
4. [CLI — Command-Line Interface](#4-cli--command-line-interface)
5. [Python API](#5-python-api)
6. [QA System](#6-qa-system)
7. [Processors (Core Layer)](#7-processors-core-layer)
8. [Writers (Output Layer)](#8-writers-output-layer)
8b. [Converters Layer (Raw Data Pre-processing)](#8b-converters-layer-raw-data-pre-processing)
9. [Output Package Structure](#9-output-package-structure)
10. [Error Handling](#10-error-handling)
11. [Extending the Library](#11-extending-the-library)
12. [Testing](#12-testing)
13. [Complete End-to-End Example](#13-complete-end-to-end-example)
14. [Web App and Distribution](#14-web-app-and-distribution)

---

## 1. Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────┐
│                           User Interface                              │
│                                                                       │
│   CLI (swatprep validate / build / inspect)                         │
│   Python API (SWATPrepProject.build())                              │
└──────────────────────┬────────────────────────────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────────────────────────────┐
│                      config.py  ←  YAML file                         │
│   SWATPrepConfig (Pydantic v2)                                        │
│   ProjectConfig | DEMConfig | LandUseConfig | SoilConfig |            │
│   WeatherConfig | StreamflowConfig                                    │
└──────────────────────┬────────────────────────────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────────────────────────────┐
│                         api.py — Orchestrator                        │
│   SWATPrepProject.build()                                           │
│                                                                       │
│   for each configured domain:                                         │
│     1. Run Processor  →  Result dataclass + list[QACheck]             │
│     2. If no failures(qa):  Run Writer  →  list[Path]                 │
│   Write Manifest + QA Report                                          │
└──────────────────────┬────────────────────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ core/    │  │writers/  │  │ qa.py    │
   │          │  │          │  │          │
   │ DEM      │  │ Spatial  │  │ QACheck  │
   │ LandUse  │  │ LandUse  │  │ failures │
   │ Soil     │  │ Soil     │  │ warnings │
   │ Weather  │  │ Weather  │  │ all_pass │
   │ Streamfl │  │ Observ.  │  └──────────┘
   └──────────┘  │ Manifest │
                 └──────────┘
```

### Data-flow trong một domain (ví dụ Weather)

```
YAML config
    │
    ▼
WeatherConfig (validated Pydantic model)
    │
    ▼
WeatherPreprocessor.run()
    ├── _load_stations()  →  pd.DataFrame (indexed by station id)
    ├── _load_daily()     →  dict[var, wide_DataFrame]
    └── _compute_wgn()    →  pd.DataFrame (12 rows × n_stations)
    │
    ▼
WeatherResult(stations, precip_stations, temp_stations, daily, wgn_stats, qa=[...])
    │
    ▼  (only if failures(qa) == [])
Writer chosen by project.targets:
    ├── "swatplus" → SWATPlusWeatherWriter.write()
    │       ├── {name}.pcp/.tmp/.hmd/.slr/.wnd  — SWAT+ daily files (year/doy rows)
    │       ├── pcp.cli / tmp.cli / ...         — SWAT+ index files
    │       ├── wgn.csv
    │       └── stations.csv
    └── "swat"     → WeatherWriter.write()
            ├── {name}.pcp  — SWAT Classic precipitation file
            ├── {name}.tmp  — SWAT Classic temperature file
            ├── wgn.csv
            └── stations.csv
```

> Weather output format depends on `project.targets`. See
> [`docs/WEATHER_OUTPUT.md`](docs/WEATHER_OUTPUT.md) for the full format
> reference, split precip/temp sources, and `file_pattern`.

### Nguyên tắc thiết kế

| Nguyên tắc | Hiện thực hoá |
|---|---|
| **Preprocessing only** | Không delineate watershed, không chạy SWAT |
| **QA gate** | Writer chỉ chạy nếu processor không có `fail` check |
| **rasterio optional** | Khi thiếu, emit `warn` và tiếp tục; không crash |
| **Path resolution** | Paths trong YAML resolve relative từ thư mục của file YAML |
| **Idempotent** | Chạy lại cùng config trên cùng data → cùng output |
| **Single responsibility** | Processor xử lý logic; Writer chỉ serialize |

---

## 2. Installation & Setup

### Yêu cầu hệ thống

- Python ≥ 3.10 (dự án ghim 3.12 trong `.python-version`)
- uv (khuyến nghị; cài đúng phiên bản trong `uv.lock`) hoặc pip

### Cài đặt cơ bản

```bash
# Clone project
git clone <repo-url>
cd swat-preprocessing

# Cài đầy đủ bằng uv (khuyến nghị): lõi + raster (geo) + giao diện web (app) + test (dev)
uv sync --extra geo --extra app --extra dev

# Hoặc bằng pip (editable install)
pip install -e ".[geo,app,dev]"
```

Nhóm tuỳ chọn: `geo` (rasterio, geopandas, shapely), `app` (streamlit, ruamel.yaml), `dev` (pytest,
pytest-cov). Người dùng cuối không cần các bước này: xem [docs/INSTALL.md](docs/INSTALL.md).

### Kiểm tra cài đặt

```bash
uv run swatprep --version
# swatprep, version 0.3.1   (luôn khớp `version` trong pyproject.toml)

uv run python -c "import swatprep; print(swatprep.__version__)"
```

### Cấu trúc thư mục project

```
swat-preprocessing/
├── pyproject.toml          # build config, dependencies, entry points
├── swatprep/
│   ├── __init__.py         # public exports: SWATPrepProject, SWATPrepConfig, QACheck
│   ├── api.py              # SWATPrepProject, PrepareResult (orchestrator)
│   ├── cli.py              # Click CLI: validate / build / inspect
│   ├── config.py           # Pydantic v2 schema cho YAML config
│   ├── errors.py           # Exception hierarchy
│   ├── qa.py               # QACheck, failures(), warnings(), all_pass()
│   ├── core/               # Processors (read + validate + compute)
│   │   ├── dem.py
│   │   ├── landuse.py
│   │   ├── soil.py
│   │   ├── weather.py
│   │   └── streamflow.py
│   ├── converters/         # Pre-processing layer (raw Vietnamese/vendor data → SWAT inputs)
│   │   ├── __init__.py     # public exports for all converters
│   │   ├── climate.py      # DayFilesConverter (merge .day files → per-station CSV)
│   │   ├── station_weather.py # StationWeatherConverter (raw pcp/tmp master+data → WeatherResult)
│   │   └── streamflow.py   # StreamflowConverter
│   ├── writers/            # Writers (serialize to files)
│   │   ├── spatial.py      # DEM → dem_info.json
│   │   ├── landuse.py      # LandUse → CSV files
│   │   ├── soil.py         # Soil → usersoil.csv
│   │   ├── weather.py      # WeatherWriter → SWAT2012 pcp_<name>.txt/tmp_<name>.txt + master files
│   │   ├── weather_plus.py # SWATPlusWeatherWriter → SWAT+ .pcp/.tmp/.cli + weather-sta.cli/weather-wgn.cli
│   │   ├── observations.py # Streamflow → streamflow_{id}.csv
│   │   └── manifest.py     # manifest.json + qa_report.md
│   └── utils/
│       └── raster.py       # Raster helpers (requires rasterio)
└── tests/
    ├── conftest.py          # Fixtures dùng chung
    ├── test_config.py
    ├── test_qa.py
    ├── test_api.py
    ├── test_converters.py   # DayFilesConverter, StreamflowConverter, CLI
    ├── test_station_weather_converter.py  # StationWeatherConverter (SWAT2012 raw + CSV input)
    ├── test_weather.py
    ├── test_weather_plus_writer.py  # SWATPlusWeatherWriter (data files + weather-sta.cli/weather-wgn.cli)
    ├── test_streamflow.py
    ├── test_landuse.py
    ├── test_soil.py
    ├── test_dem.py
    └── test_manifest.py
```

---

## 3. Configuration Reference

Config được viết bằng YAML và load qua `SWATPrepConfig.from_yaml("config.yaml")`.  
Tất cả paths trong YAML được **resolve tương đối từ vị trí file config**.

### Ví dụ config đầy đủ

```yaml
project:
  name: "mekong_upper_basin"
  crs: "EPSG:32648"             # UTM Zone 48N — CRS mục tiêu của project
  boundary: "./boundary.gpkg"   # tuỳ chọn — GeoPackage/Shapefile/GeoJSON
  output_dir: "./output"        # thư mục chứa kết quả
  targets:
    - swatplus                  # "swat" | "swatplus" | cả hai

dem:
  path: "./data/dem_30m.tif"
  output_name: "dem_projected.tif"   # tên file trong output package

landuse:
  raster: "./data/landuse.tif"
  lookup: "./data/landuse_lookup.csv"
  source_code_col: "code"       # tên cột chứa giá trị raster
  swat_code_col: "swat_code"    # tên cột chứa mã SWAT (AGRL, FRST, ...)
  swat_name_col: "swat_name"    # tên cột mô tả

soil:
  raster: "./data/soil.tif"
  table: "./data/usersoil.csv"
  soil_key_col: "soil_id"       # cột join giữa raster và bảng soil
  output_usersoil: true

weather:
  stations: "./data/weather/stations.csv"
  data_dir: "./data/weather/daily/"
  variables: [precip, tmax, tmin]
  start: "2000-01-01"
  end: "2020-12-31"
  missing_policy: "fail"        # "fail" | "warn"
  units:
    precip: "mm"
    temperature: "degC"

streamflow:
  path: "./data/streamflow.csv"
  date_col: "date"
  station_id_col: "station_id"
  value_col: "flow"
  units: "m3s"                  # "m3s" | "mm"
```

### Schema chi tiết

#### `project` (bắt buộc)

| Field | Type | Default | Mô tả |
|---|---|---|---|
| `name` | str | — | Tên project, dùng trong manifest |
| `crs` | str | — | CRS mục tiêu, e.g. `"EPSG:32648"` |
| `boundary` | Path? | `null` | File ranh giới watershed |
| `output_dir` | Path | `"./output"` | Thư mục output |
| `targets` | list | `["swatplus"]` | `"swat"`, `"swatplus"`, hoặc cả hai |

#### `dem` (tuỳ chọn)

| Field | Type | Default | Mô tả |
|---|---|---|---|
| `path` | Path | — | Đường dẫn đến file DEM (GeoTIFF) |
| `output_name` | str | `"dem_projected.tif"` | Tên file trong output |

#### `landuse` (tuỳ chọn)

| Field | Type | Default | Mô tả |
|---|---|---|---|
| `raster` | Path | — | Raster phân loại sử dụng đất |
| `lookup` | Path | — | CSV ánh xạ code raster → mã SWAT |
| `source_code_col` | str | `"code"` | Tên cột code raster trong lookup CSV |
| `swat_code_col` | str | `"swat_code"` | Tên cột mã SWAT |
| `swat_name_col` | str | `"swat_name"` | Tên cột mô tả SWAT |

**Định dạng file `landuse_lookup.csv`:**
```csv
code,swat_code,swat_name
10,AGRL,Agricultural Land Generic
20,FRST,Forest Evergreen
30,URBN,Residential
40,WATR,Water
```

#### `soil` (tuỳ chọn)

| Field | Type | Default | Mô tả |
|---|---|---|---|
| `raster` | Path | — | Raster phân loại loại đất |
| `table` | Path | — | CSV thông số đất (SWAT usersoil format) |
| `soil_key_col` | str | `"soil_id"` | Cột join giữa raster và bảng |
| `output_usersoil` | bool | `true` | Xuất file usersoil.csv |

**Cột bắt buộc trong soil table:**

| Cột | Mô tả |
|---|---|
| `soil_id` (hoặc `soil_key_col`) | Khoá join với raster |
| `HYDGRP` | Hydrologic soil group: A, B, C, D, A/D, B/D, C/D |
| `SOL_ZMX` | Maximum root depth (mm) |
| `NLAYERS` | Số lớp đất |

**Cột layer-1 được khuyến nghị** (thiếu sẽ ra `warn`):  
`SOL_Z1`, `SOL_BD1`, `SOL_AWC1`, `SOL_K1`, `SOL_CBN1`

#### `weather` (tuỳ chọn)

| Field | Type | Default | Mô tả |
|---|---|---|---|
| `stations` | Path | — | CSV metadata trạm (id, name, lat, lon, elev) |
| `data_dir` | Path | — | Thư mục chứa file CSV theo ngày per trạm |
| `file_pattern` | str | `"{id}.csv"` | Mẫu tên file input; `{id}` hoặc `{name}` |
| `precip` | block | — | Nguồn riêng cho mưa (`stations`,`data_dir`,`file_pattern`) |
| `temp` | block | — | Nguồn riêng cho nhiệt độ (`stations`,`data_dir`,`file_pattern`) |
| `variables` | list | `["precip","tmax","tmin"]` | Biến cần xử lý |
| `start` | date | — | Ngày bắt đầu (YYYY-MM-DD) |
| `end` | date | — | Ngày kết thúc (YYYY-MM-DD) |
| `missing_policy` | str | `"fail"` | `"fail"` hoặc `"warn"` khi có missing data |
| `units.precip` | str | `"mm"` | Đơn vị lượng mưa |
| `units.temperature` | str | `"degC"` | Đơn vị nhiệt độ |

> Định dạng output (SWAT+ hay SWAT Classic) do `project.targets` quyết định.
> Xem [`docs/WEATHER_OUTPUT.md`](docs/WEATHER_OUTPUT.md) để biết chi tiết
> `file_pattern`, nguồn tách `precip`/`temp`, và cả hai định dạng file.

**Định dạng `stations.csv`:**
```csv
id,name,lat,lon,elev
ST001,Chiang Rai,19.9,99.8,390
ST002,Chiang Mai,18.8,98.9,310
```

**Định dạng file dữ liệu ngày `{station_id}.csv`:**
```csv
date,precip,tmax,tmin
2000-01-01,0.0,32.5,22.0
2000-01-02,5.2,28.3,20.5
```

#### `streamflow` (tuỳ chọn)

| Field | Type | Default | Mô tả |
|---|---|---|---|
| `path` | Path | — | CSV dòng chảy dạng long-format |
| `date_col` | str | `"date"` | Tên cột ngày |
| `station_id_col` | str | `"station_id"` | Tên cột ID trạm |
| `value_col` | str | `"flow"` | Tên cột giá trị |
| `units` | str | `"m3s"` | `"m3s"` (m³/s) hoặc `"mm"` |

**Định dạng `streamflow.csv`:**
```csv
date,station_id,flow
2000-01-01,ST001,152.3
2000-01-01,ST002,89.7
2000-01-02,ST001,148.9
```

---

## 4. CLI — Command-Line Interface

Sau khi cài đặt, lệnh `swatprep` có sẵn trong terminal.

### `swatprep validate CONFIG`

Kiểm tra config và sự tồn tại của các file đầu vào — **không ghi output**.

```bash
swatprep validate config.yaml
```

Ví dụ output:
```
  v file_exists:dem.path: /data/dem_30m.tif
  v file_exists:weather.stations: /data/weather/stations.csv
  x file_exists:soil.raster: File not found: /data/soil.tif

Failed: 1 check(s).
```

Exit code: `0` nếu tất cả pass, `1` nếu có failure.

---

### `swatprep build CONFIG [--only DOMAIN]`

Chạy toàn bộ pipeline và ghi output package.

```bash
# Chạy tất cả domains đã cấu hình
swatprep build config.yaml

# Chỉ chạy một domain
swatprep build config.yaml --only weather
swatprep build config.yaml --only dem
swatprep build config.yaml --only landuse
swatprep build config.yaml --only soil
swatprep build config.yaml --only streamflow
```

Ví dụ output:
```
Done  -> /project/output
Manifest -> /project/output/manifest.json
Warnings: 2
```

Exit code: `0` thành công, `1` có lỗi.

---

### `swatprep inspect KIND PATH`

Xem metadata của một file đầu vào mà không xử lý.

```bash
# Inspect raster (yêu cầu swatprep[geo])
swatprep inspect raster data/dem_30m.tif
# File   : data/dem_30m.tif
# Driver : GTiff
# CRS    : EPSG:32648
# Bounds : BoundingBox(left=300000, bottom=1800000, right=600000, top=2100000)
# Shape  : 10000 rows x 10000 cols x 1 band(s)
# Res    : (30.0, 30.0)
# NoData : -9999.0
# Dtype  : float32

# Inspect weather CSV
swatprep inspect weather data/weather/daily/ST001.csv
# File   : ST001.csv
# Columns: ['date', 'precip', 'tmax', 'tmin']
# Preview:
#  date  precip  tmax  tmin
#  2000-01-01     0.0  32.5  22.0
```

---

## 5. Python API

### `SWATPrepProject`

Class chính để sử dụng swatprep trong Python code.

```python
from swatprep import SWATPrepProject

# Load từ file YAML
project = SWATPrepProject.from_config("config.yaml")

# Hoặc từ SWATPrepConfig đã build sẵn
from swatprep import SWATPrepConfig
cfg = SWATPrepConfig.from_yaml("config.yaml")
project = SWATPrepProject(cfg)
```

#### `SWATPrepProject.build(only=None) → PrepareResult`

Chạy toàn bộ pipeline.

```python
result = project.build()

print(result.output_dir)      # Path
print(result.manifest_path)   # Path | None
print(result.warning_count)   # int
print(result.error_count)     # int
print(result.success)         # bool (True nếu error_count == 0)

# Xem toàn bộ QA checks
for check in result.qa_checks:
    print(f"{check.status:5s}  {check.name}: {check.message}")

# Chỉ chạy một domain
result = project.build(only="weather")
```

#### `SWATPrepProject.validate() → list[QACheck]`

Chỉ kiểm tra file existence, không ghi gì.

```python
checks = project.validate()
from swatprep.qa import failures
if failures(checks):
    print("Missing files:")
    for c in failures(checks):
        print(f"  {c.message}")
```

---

### `PrepareResult`

```python
@dataclass
class PrepareResult:
    output_dir: Path
    manifest_path: Path | None
    qa_checks: list[QACheck]

    # Properties:
    warning_count: int    # số lượng QACheck có status="warn"
    error_count: int      # số lượng QACheck có status="fail"
    success: bool         # True khi error_count == 0
```

---

### Sử dụng trực tiếp các Processor

Bạn có thể gọi từng processor riêng lẻ mà không qua `build()`:

```python
from pathlib import Path
from swatprep.config import WeatherConfig
from swatprep.core.weather import WeatherPreprocessor

cfg = WeatherConfig(
    stations=Path("data/stations.csv"),
    data_dir=Path("data/daily/"),
    variables=["precip", "tmax", "tmin"],
    start="2000-01-01",
    end="2020-12-31",
)
result = WeatherPreprocessor(cfg).run()

print(result.stations)          # pd.DataFrame
print(result.daily["precip"])   # pd.DataFrame (DatetimeIndex × station_id)
print(result.wgn_stats)         # pd.DataFrame (12 months × n_stations)
print(result.qa)                # list[QACheck]
```

---

## 6. QA System

Mọi processor đều trả về một `list[QACheck]`. Writer chỉ chạy khi không có failure.

### `QACheck`

```python
@dataclass
class QACheck:
    name: str                              # tên định danh duy nhất
    status: Literal["pass", "warn", "fail"]
    message: str                           # mô tả human-readable
    context: dict[str, Any] = {}           # metadata bổ sung

    def is_ok(self) -> bool: ...           # True nếu pass hoặc warn
    def as_dict(self) -> dict: ...         # serialize thành dict
```

### Helper functions

```python
from swatprep.qa import failures, warnings, all_pass

checks = processor.run().qa

# Lọc theo status
fail_list = failures(checks)   # list[QACheck] — chỉ status="fail"
warn_list = warnings(checks)   # list[QACheck] — chỉ status="warn"
ok = all_pass(checks)          # bool — True khi không có fail

# Pattern phổ biến
if failures(checks):
    for c in failures(checks):
        print(f"FAIL: {c.name} — {c.message}")
```

### QA Gate trong Writer

```python
# Pattern trong api.py — writers chỉ chạy nếu không có failure
result = Processor(cfg).run()
all_qa.extend(result.qa)

if not failures(result.qa):   # ← QA gate
    written = Writer(result, output_dir).write()
```

### Status meanings

| Status | Ý nghĩa | Hành động |
|---|---|---|
| `pass` | Kiểm tra thành công | Tiếp tục bình thường |
| `warn` | Có vấn đề nhỏ nhưng pipeline vẫn chạy | Log và tiếp tục |
| `fail` | Lỗi nghiêm trọng | **Chặn writer** của domain đó |

---

## 7. Processors (Core Layer)

### DEMPreprocessor

**File:** `swatprep/core/dem.py`

```python
from swatprep.config import DEMConfig
from swatprep.core.dem import DEMPreprocessor, DEMResult

cfg = DEMConfig(path=Path("dem.tif"), output_name="dem_projected.tif")
result: DEMResult = DEMPreprocessor(cfg, project_crs="EPSG:32648").run()
```

**Checks thực hiện:**

| Check name | Status | Điều kiện |
|---|---|---|
| `dem_file_exists` | fail | File không tìm thấy |
| `rasterio_missing` | warn | rasterio chưa cài — bỏ qua metadata |
| `dem_raster_read_failed` | fail | Không mở được file raster |
| `dem_crs_missing` | warn | File không có CRS |
| `dem_crs_mismatch` | warn | CRS khác với project CRS |
| `dem_crs` | pass | CRS hợp lệ |
| `dem_nodata_missing` | warn | Không có NoData value |
| `dem_all_nodata` | fail | Toàn bộ pixel là NoData |
| `dem_flat` | warn | min ≥ max elevation |
| `dem_elevation_stats` | pass | Thống kê elevation hợp lệ |

**`DEMResult` fields:**

```python
@dataclass
class DEMResult:
    path: Path
    output_name: str
    crs: str | None              # e.g. "EPSG:32648"
    shape: tuple | None          # (height, width)
    resolution: tuple | None     # (x_res, y_res) in map units
    elevation_range: tuple | None  # (min, max) in metres
    nodata: float | None
    qa: list[QACheck]
```

---

### LandUsePreprocessor

**File:** `swatprep/core/landuse.py`

```python
from swatprep.config import LandUseConfig
from swatprep.core.landuse import LandUsePreprocessor, LandUseResult

cfg = LandUseConfig(
    raster=Path("landuse.tif"),
    lookup=Path("landuse_lookup.csv"),
)
result: LandUseResult = LandUsePreprocessor(cfg).run()
```

**Checks thực hiện:**

| Check name | Status | Điều kiện |
|---|---|---|
| `landuse_lookup_duplicates` | warn | Có code trùng lặp trong lookup |
| `landuse_lookup_loaded` | pass | Lookup load thành công |
| `rasterio_missing` | warn | rasterio chưa cài |
| `landuse_raster_read_failed` | fail | Không đọc được raster |
| `landuse_raster_read` | pass | Đọc raster thành công |
| `landuse_unmatched_codes` | fail | Có code raster không có trong lookup |
| `landuse_cross_check` | pass | Tất cả code đều có trong lookup |

**`LandUseResult` fields:**

```python
@dataclass
class LandUseResult:
    raster_path: Path
    lookup: pd.DataFrame           # Bảng lookup đã validate
    raster_codes: set | None       # Unique codes từ raster (None nếu không có rasterio)
    code_mapping: dict[int, int]   # {raster_code: swat_class_id} — 1-based
    unmatched_codes: set           # Codes trong raster nhưng không có trong lookup
    qa: list[QACheck]
```

**Hàm nội bộ:**

```python
def _build_class_id_mapping(lookup: pd.DataFrame, source_code_col: str) -> dict[int, int]:
    """Ánh xạ raster code → sequential 1-based SWAT class ID."""
```

---

### SoilPreprocessor

**File:** `swatprep/core/soil.py`

```python
from swatprep.config import SoilConfig
from swatprep.core.soil import SoilPreprocessor, SoilResult

cfg = SoilConfig(raster=Path("soil.tif"), table=Path("usersoil.csv"))
result: SoilResult = SoilPreprocessor(cfg).run()
```

**Checks thực hiện:**

| Check name | Status | Điều kiện |
|---|---|---|
| `soil_missing_required_cols` | fail | Thiếu HYDGRP, SOL_ZMX, hoặc NLAYERS |
| `soil_missing_layer1_cols` | warn | Thiếu SOL_Z1/BD1/AWC1/K1/CBN1 |
| `soil_invalid_hydgrp` | warn | HYDGRP có giá trị ngoài tập {A,B,C,D,...} |
| `soil_table_loaded` | pass | Bảng đất load thành công |
| `rasterio_missing` | warn | rasterio chưa cài |
| `soil_raster_read_failed` | fail | Không đọc được raster |
| `soil_raster_read` | pass | Đọc raster thành công |
| `soil_unmatched_codes` | fail | Có code raster không có trong bảng đất |
| `soil_cross_check` | pass | Tất cả code khớp |

**`SoilResult` fields:**

```python
@dataclass
class SoilResult:
    soil_table: pd.DataFrame   # Bảng đất đã validate
    raster_codes: set | None   # Unique codes từ raster
    unmatched_codes: set       # Codes không khớp
    qa: list[QACheck]
```

---

### WeatherPreprocessor

**File:** `swatprep/core/weather.py`

```python
from swatprep.config import WeatherConfig
from swatprep.core.weather import WeatherPreprocessor, WeatherResult
from datetime import date

cfg = WeatherConfig(
    stations=Path("stations.csv"),
    data_dir=Path("daily/"),
    variables=["precip", "tmax", "tmin"],
    start=date(2000, 1, 1),
    end=date(2020, 12, 31),
)
result: WeatherResult = WeatherPreprocessor(cfg).run()
```

**WGN Parameters được tính:**

| Param | Mô tả | Nguồn dữ liệu |
|---|---|---|
| `TMPMX` | Mean max temp (°C) by month | tmax |
| `TMPMN` | Mean min temp (°C) by month | tmin |
| `TMPSTDMX` | Std dev max temp | tmax |
| `TMPSTDMN` | Std dev min temp | tmin |
| `PCPMM` | Mean monthly precip (mm) | precip |
| `PCPSTD` | Std dev precip on wet days | precip |
| `PCPSKW` | Skew coeff of daily precip | precip |
| `PR_W1` | P(wet\|dry) — Markov chain | precip |
| `PR_W2` | P(wet\|wet) — Markov chain | precip |
| `PCPD` | Mean days of precip per month | precip |
| `RAINHHMX` | Max 0.5h rainfall | **−99.0** (unavailable) |
| `SOLARAV` | Mean solar radiation | **−99.0** (unavailable) |
| `DEWPT` | Mean dew point temp | **−99.0** (unavailable) |
| `WNDAV` | Mean wind speed | **−99.0** (unavailable) |

> `−99.0` là SWAT sentinel: giá trị sẽ được nội suy từ map trong mô hình.

**Hàm nội bộ:**

```python
def _markov_probs(wet: pd.Series) -> tuple[float, float]:
    """Tính P(wet|dry) và P(wet|wet) từ chuỗi boolean."""

def _fill_temp_stats(row, tmax, tmin, month):
    """Điền TMPMX, TMPMN, TMPSTDMX, TMPSTDMN cho một tháng."""

def _fill_precip_stats(row, precip, month):
    """Điền PCPMM, PCPSTD, PCPSKW, PR_W1, PR_W2, PCPD cho một tháng."""
```

**`WeatherResult` fields:**

```python
@dataclass
class WeatherResult:
    stations: pd.DataFrame              # indexed by station id
    daily: dict[str, pd.DataFrame]      # {"precip": wide_df, "tmax": wide_df, ...}
    wgn_stats: pd.DataFrame             # 12 × n_stations rows
    qa: list[QACheck]
```

---

### StreamflowPreprocessor

**File:** `swatprep/core/streamflow.py`

```python
from swatprep.config import StreamflowConfig
from swatprep.core.streamflow import StreamflowPreprocessor, StreamflowResult

cfg = StreamflowConfig(path=Path("streamflow.csv"), units="m3s")
result: StreamflowResult = StreamflowPreprocessor(cfg).run()

print(result.daily)   # pd.DataFrame: DatetimeIndex × station_id
print(result.units)   # "m3s"
```

> **Quan trọng:** Dùng `df.pivot()` thay vì `df.pivot_table()` để giữ nguyên
> giá trị `NaN` (pivot_table mặc định drop NaN).

**Checks thực hiện:**

| Check name | Status | Điều kiện |
|---|---|---|
| `missing:streamflow:{sid}` | warn | Có missing values |
| `streamflow_negative` | warn | Có giá trị âm |
| `streamflow_loaded` | pass | Load thành công |

**`StreamflowResult` fields:**

```python
@dataclass
class StreamflowResult:
    daily: pd.DataFrame   # DatetimeIndex × station_id (wide format)
    units: str            # "m3s" hoặc "mm"
    qa: list[QACheck]
```

---

## 8. Writers (Output Layer)

Writers nhận Result dataclass và ghi files. Chúng không thực hiện validation — đó là trách nhiệm của Processor.

### SpatialWriter

**File:** `swatprep/writers/spatial.py`  
**Output dir:** `output/spatial/`

```python
from swatprep.writers.spatial import SpatialWriter

written = SpatialWriter(dem_result, output_dir / "spatial").write()
# Trả về: [Path("output/spatial/dem_info.json")]
```

**Files được tạo:**

| File | Nội dung |
|---|---|
| `dem_info.json` | Metadata: source_path, crs, shape, resolution, elevation_range, nodata, generated_at |

---

### LandUseWriter

**File:** `swatprep/writers/landuse.py`  
**Output dir:** `output/landuse/`

```python
from swatprep.writers.landuse import LandUseWriter

written = LandUseWriter(lu_result, output_dir / "landuse").write()
```

**Files được tạo:**

| File | Điều kiện | Nội dung |
|---|---|---|
| `landuse_lookup.csv` | luôn | Bảng lookup đã validate |
| `landuse_raster_codes.csv` | khi có rasterio | Tất cả unique codes trong raster |
| `landuse_unmatched_codes.csv` | khi có unmatched | Codes không có trong lookup |

---

### SoilWriter

**File:** `swatprep/writers/soil.py`  
**Output dir:** `output/soil/`

```python
from swatprep.writers.soil import SoilWriter

written = SoilWriter(soil_result, output_dir / "soil").write()
```

**Files được tạo:**

| File | Điều kiện | Nội dung |
|---|---|---|
| `usersoil.csv` | luôn | Bảng đất gốc (SWAT usersoil format) |
| `soil_raster_codes.csv` | khi có rasterio | Unique codes trong raster |

---

### Weather writers (chọn theo `project.targets`)

`build()` chọn writer dựa trên `project.targets`:

| `targets` | Writer | File |
|---|---|---|
| `"swatplus"` (mặc định) | `SWATPlusWeatherWriter` (`writers/weather_plus.py`) | `.pcp/.tmp/.hmd/.slr/.wnd` + `*.cli` + `weather-sta.cli`/`weather-wgn.cli` |
| `"swat"` | `WeatherWriter` (`writers/weather.py`) | SWAT Classic `pcp_<name>.txt`/`tmp_<name>.txt` + `master_pcp.txt`/`master_tmp.txt` |
| cả hai | cả hai | mỗi định dạng vào thư mục con `swatplus/` và `swat/` |

> Xem [`docs/WEATHER_OUTPUT.md`](docs/WEATHER_OUTPUT.md) cho tham chiếu đầy đủ.

#### SWATPlusWeatherWriter (mặc định)

**File:** `swatprep/writers/weather_plus.py` · **Output dir:** `output/weather/`

```python
from swatprep.writers.weather_plus import SWATPlusWeatherWriter

written = SWATPlusWeatherWriter(weather_result, output_dir / "weather").write()
```

Mỗi file có header 3 dòng (`nbyr tstep lat lon elev`) + các dòng `year doy value`,
kèm file chỉ mục `.cli`:

```text
StationA.pcp: Precipitation data - file written by swatprep 2026-07-12 22:12:49
nbyr     tstep       lat       lon      elev
   1         0    15.500   105.200   120.000
2000    1    0.00000
2000    2    5.20000
```

Sau các file dữ liệu và `.cli` theo biến, writer còn ghi hai file "linking"
mà một `TxtInOut` thật sự đọc để phân giải dữ liệu khí hậu của từng trạm:
`weather-sta.cli` (đăng ký trạm) và `weather-wgn.cli` (thống kê WGN theo
định dạng cố định của SWAT+). Xem `docs/WEATHER_OUTPUT.md` để biết chi tiết
cột.

#### WeatherWriter (SWAT Classic)

**File:** `swatprep/writers/weather.py`  
**Output dir:** `output/weather/`

```python
from swatprep.writers.weather import WeatherWriter

written = WeatherWriter(weather_result, output_dir / "weather").write()
```

**Files được tạo:**

| File | Nội dung |
|---|---|
| `pcp_{name}.txt` | SWAT Classic precipitation file |
| `tmp_{name}.txt` | SWAT Classic temperature file |
| `master_pcp.txt` | Metadata trạm precip (chỉ các trạm đã ghi file dữ liệu) — `ID,NAME,LAT,LONG,ELEVATION`; `ID` là số thứ tự (STT) 1..N theo thứ tự bảng trạm, không phải mã trạm gốc |
| `master_tmp.txt` | Metadata trạm temperature (chỉ các trạm đã ghi file dữ liệu) |
| `wgn.csv` | Weather Generator parameters (14 cols × n_stations × 12 tháng) |

> Tên file output lấy từ cột `name` của trạm. `WeatherWriter` (SWAT Classic)
> KHÔNG thêm hậu tố khi hai trạm trùng tên — file sau sẽ ghi đè file trước.
> (`SWATPlusWeatherWriter` cho SWAT+ có dedup, thêm hậu tố `_{id}`.)

**Định dạng SWAT Classic `pcp_StationA.txt`:** (dòng 1 là ngày bản ghi đầu tiên, không lệch ngày)
```
20000101
0.0
5.2
0.0
```

**Định dạng SWAT Classic `tmp_StationA.txt`** (`tmin,tmax` mỗi dòng):
```
20000101
22.0,30.1
20.0,29.5
```

> Không có header block metadata (không có title/Lati/Long/Elev) — metadata
> trạm chỉ nằm trong `master_pcp.txt`/`master_tmp.txt`. Dòng 1 là ngày của
> bản ghi dữ liệu **đầu tiên** (YYYYMMDD), không lệch ngày. Giá trị được ghi
> gọn (không đệm độ rộng cố định), khớp quy ước dữ liệu vendor SWAT2012 thật.
> Xem [`docs/WEATHER_OUTPUT.md`](docs/WEATHER_OUTPUT.md) để biết chi tiết đầy đủ.

---

### ObservationWriter

**File:** `swatprep/writers/observations.py`  
**Output dir:** `output/observed/`

```python
from swatprep.writers.observations import ObservationWriter

written = ObservationWriter(flow_result, output_dir / "observed").write()
```

**Files được tạo:**

| File | Nội dung |
|---|---|
| `streamflow_{station_id}.csv` | Dòng chảy ngày theo trạm |
| `streamflow_meta.csv` | Metadata: units, date range, n_days, mean_flow |

---

### ManifestWriter (write_manifest function)

**File:** `swatprep/writers/manifest.py`

```python
from swatprep.writers.manifest import write_manifest

manifest_path, report_path = write_manifest(
    output_dir=Path("output"),
    project_name="mekong_basin",
    domains=["weather", "soil"],
    all_qa=all_qa_checks,
)
```

**Files được tạo:**

**`manifest.json`** — Machine-readable record:
```json
{
  "schema_version": "1.0",
  "project": "mekong_basin",
  "created_at": "2025-01-15T08:30:00+00:00",
  "domains_processed": ["weather", "soil"],
  "output_dir": "/project/output",
  "files": {
    "weather": ["ST001.pcp", "ST001.tmp", "stations.csv", "wgn.csv"],
    "soil": ["usersoil.csv"]
  },
  "qa_summary": {"pass": 12, "warn": 1, "fail": 0}
}
```

**`qa_report.md`** — Human-readable QA table:
```markdown
# QA Report — mekong_basin

| Status | Check | Message |
|--------|-------|---------|
| ✅ pass | `stations_loaded` | 2 station(s) loaded |
| ⚠️ warn | `missing:ST001:precip` | ST001 precip: 2.3% missing |
| ✅ pass | `wgn_computed` | WGN stats for 2 stations × 12 months |
```

---

## 8b. Converters Layer (Raw Data Pre-processing)

The `converters/` package is a **separate pre-processing step** that runs
*before* (or independently of) the main `build()` pipeline. It converts raw
vendor/Vietnamese station data (`.day` files, SWAT Classic-style master +
per-station files) into either per-station CSVs (`DayFilesConverter`) or a
`WeatherResult` ready to hand to `WeatherWriter`/`SWATPlusWeatherWriter`
(`StationWeatherConverter`).

Converters do **not** appear in `api.py` / `build()`. They are called
standalone, either via CLI or Python API.

---

### DayFilesConverter

**File:** `swatprep/converters/climate.py`

Merges multiple `.day` variable files into one per-station CSV.

```python
from swatprep.converters import DayFilesConverter

result = DayFilesConverter(
    data_dir=Path("raw/"),       # contains R_STATION01.day, Tx_STATION01.day, Tm_STATION01.day
    out_dir=Path("merged/"),
).convert()

print(result.stations_found)    # ["STATION01", "STATION03", ...]
print(result.files_written)     # [Path("merged/STATION01.csv"), ...]
```

---

### StationWeatherConverter

**File:** `swatprep/converters/station_weather.py`

Reads raw per-station weather files (SWAT Classic style, i.e. a
`YYYYMMDD`-header + one-value-per-line `pcp_<name>.txt`/`tmp_<name>.txt`
layout matching real vendor exports — or a `date` + variable-column CSV,
auto-detected per station file) plus a pcp/tmp master metadata file, into a
`WeatherResult` — the same type `WeatherPreprocessor` produces for the
`build()` pipeline. It does **not** write any output files itself:
*reading* raw vendor data is `StationWeatherConverter`'s only job; *writing*
stays the sole responsibility of `WeatherWriter` (SWAT2012) /
`SWATPlusWeatherWriter` (SWAT+), so there is one single source of truth per
output format regardless of which entry point produced the `WeatherResult`.

At least one of the `pcp_*` / `tmp_*` group must be given; the two groups are
independent (you can convert precip only, temperature only, or both).

```python
from swatprep.converters.station_weather import StationWeatherConverter
from swatprep.writers.weather import WeatherWriter
from swatprep.writers.weather_plus import SWATPlusWeatherWriter

result = StationWeatherConverter(
    pcp_master=Path("master_pcp.txt"),
    pcp_dir=Path("raw_pcp/"),
    tmp_master=Path("master_tmp.txt"),
    tmp_dir=Path("raw_tmp/"),
).convert()

WeatherWriter(result, Path("out/swat2012")).write()      # SWAT2012 format
SWATPlusWeatherWriter(result, Path("out/swatplus")).write()  # SWAT+ format
```

**CLI equivalent** — `swatprep convert weather` (replaces the removed
`convert pcp` / `convert tmp` / `convert swatplus` commands):

```bash
swatprep convert weather \
  --pcp-master master_pcp.txt --pcp-dir ./raw_pcp \
  --tmp-master master_tmp.txt --tmp-dir ./raw_tmp \
  --target swat2012 --target swatplus \
  OUT_DIR
```

`--target` accepts `swat2012` (or its alias `swat`) and/or `swatplus`, and
may be repeated; with more than one target, each is written to its own
`OUT_DIR/<target>/` subdirectory. See `swatprep/cli.py`'s `convert_weather`
docstring for the exact option list.

---

## 9. Output Package Structure

Sau khi chạy `prepare`, output directory có cấu trúc:

```
output/
├── manifest.json            # Machine-readable package record
├── qa_report.md             # Human-readable QA summary
├── spatial/
│   └── dem_info.json
├── landuse/
│   ├── landuse_lookup.csv
│   └── landuse_raster_codes.csv
├── soil/
│   └── usersoil.csv
├── weather/
│   ├── ST001.pcp
│   ├── ST001.tmp
│   ├── ST002.pcp
│   ├── ST002.tmp
│   ├── wgn.csv
│   └── stations.csv
└── observed/
    ├── streamflow_ST001.csv
    ├── streamflow_ST002.csv
    └── streamflow_meta.csv
```

---

## 10. Error Handling

### Exception Hierarchy

```
SWATPrepError                    # Base class
├── ConfigError                  # YAML sai, thiếu fields bắt buộc
├── InputValidationError         # File thiếu cột, sai định dạng
├── ProjectionError              # CRS mismatch, reprojection thất bại
├── ProcessingError              # Lỗi thuật toán trong preprocessing
└── WriterError                  # Lỗi I/O khi ghi output
```

### Khi nào throw Exception vs emit QACheck

| Tình huống | Xử lý |
|---|---|
| File không tìm thấy | `QACheck(status="fail")` — pipeline tiếp tục cho domain khác |
| Cột bắt buộc thiếu trong CSV | `raise InputValidationError` — dừng domain ngay lập tức |
| rasterio chưa cài | `QACheck(status="warn")` — tiếp tục không có raster check |
| CRS không khớp | `QACheck(status="warn")` — ghi warning và tiếp tục |
| Config schema sai | `pydantic.ValidationError` — dừng trước khi chạy |

### Xử lý lỗi trong code

```python
from swatprep.errors import SWATPrepError, ConfigError, InputValidationError

try:
    result = project.build()
except ConfigError as e:
    print(f"Config lỗi: {e}")
except InputValidationError as e:
    print(f"Input không hợp lệ: {e}")
except SWATPrepError as e:
    print(f"Lỗi chung: {e}")
```

---

## 11. Extending the Library

### Thêm một Processor mới

Ví dụ thêm `ReservoirPreprocessor`:

**Bước 1:** Thêm config vào `config.py`

```python
class ReservoirConfig(BaseModel):
    path: Path
    capacity_col: str = "capacity_mcm"

class SWATPrepConfig(BaseModel):
    # ...existing fields...
    reservoir: Optional[ReservoirConfig] = None
```

**Bước 2:** Tạo `swatprep/core/reservoir.py`

```python
@dataclass
class ReservoirResult:
    data: pd.DataFrame
    qa: list[QACheck] = field(default_factory=list)

class ReservoirPreprocessor:
    def __init__(self, cfg: ReservoirConfig) -> None:
        self.cfg = cfg

    def run(self) -> ReservoirResult:
        qa: list[QACheck] = []
        # ... validation logic ...
        return ReservoirResult(data=df, qa=qa)
```

**Bước 3:** Tạo `swatprep/writers/reservoir.py`

```python
class ReservoirWriter:
    def __init__(self, result: ReservoirResult, output_dir: Path) -> None:
        self.result = result
        self.output_dir = output_dir

    def write(self) -> list[Path]:
        # ... write files ...
        return written
```

**Bước 4:** Wiring vào `api.py`

```python
if "reservoir" in domains_to_run and cfg.reservoir is not None:
    from .core.reservoir import ReservoirPreprocessor
    from .writers.reservoir import ReservoirWriter

    result = ReservoirPreprocessor(cfg.reservoir).run()
    all_qa.extend(result.qa)
    domains_run.append("reservoir")

    if not failures(result.qa):
        written = ReservoirWriter(result, output_dir / "reservoir").write()
```

**Bước 5:** Cập nhật CLI `_VALID_DOMAINS`

```python
_VALID_DOMAINS = ("dem", "landuse", "soil", "weather", "streamflow", "reservoir")
```

**Bước 6:** Thêm tests `tests/test_reservoir.py`

---

## 12. Testing

### Chạy tests

```bash
# Tất cả tests (lõi + giao diện web)
uv run python -m pytest -q

# Một file cụ thể
uv run python -m pytest tests/test_weather.py -v

# Một test cụ thể
uv run python -m pytest tests/test_weather.py::test_wgn_stats_have_12_rows -v

# Với coverage report
uv run python -m pytest tests/ --cov=swatprep --cov-report=html

# Chỉ tests không cần rasterio
uv run python -m pytest tests/ -v -k "not rasterio"
```

Dùng `python -m pytest` thay vì `pytest`: nếu `.venv` thiếu pytest, lệnh báo lỗi rõ ràng thay vì âm thầm
chạy pytest của Python hệ thống.

### Fixture quan trọng trong `conftest.py`

| Fixture | Trả về | Mô tả |
|---|---|---|
| `tmp_dir` | `Path` | Thư mục tạm thời (tự dọn sau mỗi test) |
| `weather_stations_csv` | `Path` | CSV 2 trạm (ST001, ST002) |
| `weather_data_dir` | `Path` | Thư mục có 10 ngày data per trạm |
| `streamflow_csv` | `Path` | Long-format CSV 1 trạm, 10 ngày |
| `landuse_lookup_csv` | `Path` | Lookup 4 loại sử dụng đất |
| `soil_table_csv` | `Path` | Bảng đất 3 record |
| `minimal_config_yaml` | `Path` | YAML config tối thiểu (chỉ project section) |

### Cấu trúc test patterns

```python
# Pattern 1: Test processor với mock data
def test_something(weather_stations_csv, weather_data_dir, tmp_dir):
    cfg = WeatherConfig(
        stations=weather_stations_csv,
        data_dir=weather_data_dir,
        variables=["precip", "tmax", "tmin"],
        start=date(2000, 1, 1),
        end=date(2000, 1, 10),
    )
    result = WeatherPreprocessor(cfg).run()
    assert not failures(result.qa)

# Pattern 2: Mock _HAS_RASTERIO để test degradation
def test_no_rasterio_warn(soil_table_csv, tmp_dir):
    import swatprep.core.soil as mod
    original = mod._HAS_RASTERIO
    try:
        mod._HAS_RASTERIO = False
        result = SoilPreprocessor(...).run()
        assert result.raster_codes is None
        assert not failures(result.qa)
    finally:
        mod._HAS_RASTERIO = original

# Pattern 3: Skip khi rasterio không có
def test_requires_rasterio(tmp_dir):
    pytest.importorskip("rasterio")
    # ... test chỉ chạy khi rasterio được cài ...
```

---

## 13. Complete End-to-End Example

### 1. Chuẩn bị dữ liệu đầu vào

```
project/
├── config.yaml
└── data/
    ├── dem_30m.tif
    ├── landuse.tif
    ├── landuse_lookup.csv
    ├── soil.tif
    ├── usersoil.csv
    ├── streamflow.csv
    └── weather/
        ├── stations.csv
        └── daily/
            ├── ST001.csv
            └── ST002.csv
```

### 2. Viết config.yaml

```yaml
project:
  name: "mekong_upper"
  crs: "EPSG:32648"
  output_dir: "./output"
  targets: ["swatplus"]

dem:
  path: "./data/dem_30m.tif"

landuse:
  raster: "./data/landuse.tif"
  lookup: "./data/landuse_lookup.csv"

soil:
  raster: "./data/soil.tif"
  table: "./data/usersoil.csv"

weather:
  stations: "./data/weather/stations.csv"
  data_dir: "./data/weather/daily/"
  variables: [precip, tmax, tmin]
  start: "2000-01-01"
  end: "2020-12-31"
  missing_policy: "warn"

streamflow:
  path: "./data/streamflow.csv"
  units: "m3s"
```

### 3. Validate trước khi chạy

```bash
cd project/
swatprep validate config.yaml
```

### 4. Chạy pipeline đầy đủ

```bash
swatprep build config.yaml
# Done  -> /project/output
# Manifest -> /project/output/manifest.json
```

### 5. Kiểm tra kết quả

```bash
cat output/manifest.json
cat output/qa_report.md
ls output/weather/
```

### 6. Sử dụng kết quả trong Python

```python
import json, pandas as pd

# Đọc manifest
with open("output/manifest.json") as f:
    manifest = json.load(f)

print(manifest["qa_summary"])     # {"pass": 15, "warn": 2, "fail": 0}
print(manifest["domains_processed"])  # ["dem", "landuse", "soil", "weather", "streamflow"]

# Đọc WGN stats
wgn = pd.read_csv("output/weather/wgn.csv")
print(wgn[["station_id", "month", "PCPMM", "PR_W1", "PR_W2"]].head(12))

# Đọc dòng chảy
flow = pd.read_csv("output/observed/streamflow_ST001.csv", parse_dates=["date"])
print(flow.describe())
```

### 7. Chỉ tái chạy một domain

```bash
# Sau khi sửa dữ liệu weather
swatprep build config.yaml --only weather
```

### 8. Sử dụng Python API cho scripting nâng cao

```python
from swatprep import SWATPrepProject
from swatprep.qa import failures, warnings

project = SWATPrepProject.from_config("config.yaml")

# Validate trước
checks = project.validate()
if failures(checks):
    raise SystemExit("Input files missing — run 'swatprep validate' for details")

# Chạy pipeline
result = project.build()

# Xử lý kết quả
if not result.success:
    for c in failures(result.qa_checks):
        print(f"ERROR [{c.name}]: {c.message}")
        print(f"  Context: {c.context}")
else:
    print(f"Success! Output: {result.output_dir}")
    print(f"Warnings: {result.warning_count}")
```

---

## 14. Web App and Distribution

### Kiến trúc

```
app/
  Home.py                 trang chủ: báo cáo môi trường (phiên bản, driver GDAL, thư mục)
  pages/1_Project.py      trang Project: thư mục dự án, form config, Validate, Build, kết quả
  launch.py               lệnh `swatprep-ui`: chạy Streamlit từ thư mục app/
  .streamlit/config.toml  theme OpenDesign (light/dark), chỉ nghe localhost
  ui/                     mã Streamlit dùng chung (fields, sections, browse, results, status)
  services/               Python thuần, không import streamlit, có test
    settings.py           SWATPREP_DATA_ROOT / SWATPREP_WORKSPACE (tuỳ chọn)
    environment.py        báo cáo môi trường, không bao giờ ném lỗi
    form_model.py         field_spec(): kiểu Pydantic -> loại ô nhập
    form_layout.py        LAYOUT (thứ tự trường), SECTIONS, PATH_KINDS, LABELS
    form_state.py         đổi giá trị ô nhập <-> dict YAML; ánh xạ lỗi về trường
    project_io.py         đọc/ghi YAML bằng ruamel (giữ comment)
    runner.py             validate/build -> RunResult, không bao giờ ném lỗi
    fs_browser.py         liệt kê thư mục, chặn path traversal
    recent.py             thư mục dự án gần đây (~/.swatprep/)
    projects.py           dự án = thư mục; config = file .yaml ở gốc; tạo dự án / config
```

Phụ thuộc một chiều: `pages -> ui -> services -> swatprep`. Lõi `swatprep/` không biết gì về giao diện.

### Thêm một trường cấu hình mới

1. Thêm trường vào model trong `swatprep/config.py` (kèm test của lõi).
2. Thêm tên trường vào `LAYOUT[<Model>]` trong `app/services/form_layout.py`, đúng vị trí muốn hiển thị.
   Nếu là `Path`, khai báo `PATH_KINDS` khi nó là thư mục (`dir`), tệp hoặc thư mục (`file_or_dir`) hay
   đầu ra (`output`). Nhãn đẹp hơn tên trường: thêm vào `LABELS`.
3. Chạy `uv run python -m pytest tests/ui -q`: `test_layout_covers_every_config_field` báo lỗi nếu quên
   bước 2; `test_every_field_type_is_supported` báo lỗi nếu trường dùng kiểu form chưa hỗ trợ.

Form không ghi giá trị mặc định vào YAML và không đổi khoá chưa sửa; mọi thay đổi đi qua
`form_state.apply()`.

### Chạy và đóng gói

| Mục đích | Lệnh |
|---|---|
| Chạy từ mã nguồn | `uv run swatprep-ui` (thêm tham số Streamlit, ví dụ `--server.port 8502`) |
| Kiểm tra gói cài đặt | `uv build`; `tests/ui/test_launch.py` kiểm tra wheel có `app/pages/*.py` và `app/.streamlit/config.toml` |
| Docker | `docker compose up --build` -> `http://localhost:8501` |
| Người dùng cuối | `scripts/install.bat`, `scripts/install.sh` (`uv tool install` từ archive của tag); xem [docs/INSTALL.md](docs/INSTALL.md) |

`pages/` không có `__init__.py` nên được đóng gói qua `[tool.setuptools.package-data]`. Streamlit đọc
`.streamlit/config.toml` theo thư mục làm việc, vì vậy `launch.py` đổi thư mục làm việc sang `app/`
trước khi chạy.

### Phát hành

Quy trình đầy đủ và các lỗi thường gặp: [docs/RELEASING.md](docs/RELEASING.md). Tóm tắt: tăng
`version` trong `pyproject.toml` -> `uv lock` -> PR, merge -> `git tag vX.Y.Z` trên `main` -> CI build
image `ghcr.io/wosonday/swatprep:X.Y.Z` và tạo GitHub Release kèm hai script cài đặt.

---

## References

- Arnold, J.G. et al. (2012). SWAT: Model Use, Calibration, and Validation. *Transactions of the ASABE*, 55(4), 1491–1508.
- Neitsch, S.L. et al. (2011). *SWAT Input/Output File Documentation, Version 2009*. Texas Water Resources Institute Technical Report 365.
- Neitsch, S.L. et al. (2011). *SWAT Theoretical Documentation, Version 2009*. Texas Water Resources Institute Technical Report 406. (Chapter 1: Climate — WGN statistics)
