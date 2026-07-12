# Hướng Dẫn Test swatprep — Từ Đầu Đến Cuối

Hướng dẫn này bao gồm toàn bộ vòng đời test: cài đặt môi trường → chạy unit tests → test CLI thủ công → chạy pipeline thực tế với dữ liệu Việt Nam.

---

## 1. Chuẩn Bị Môi Trường

### 1.1 Cài đặt package

```bash
cd swat-preprocessing/
pip install -e ".[dev]"          # swatprep + pytest, pydantic, pandas, click
pip install -e ".[geo]"          # tuỳ chọn: rasterio cho DEM/LandUse/Soil
```

### 1.2 Kiểm tra cài đặt

```bash
swatprep --version               # phải in ra phiên bản
swatprep --help                  # liệt kê các lệnh
swatprep convert --help          # liệt kê subcommands convert
```

---

## 2. Chạy Toàn Bộ Unit Tests

```bash
cd swat-preprocessing/
python -m pytest -v
```

**Kết quả mong đợi:**
```
129 passed, 3 skipped in ~3s
```

3 test skip là do yêu cầu `rasterio` (cài với `pip install -e ".[geo]"`).

### 2.1 Chạy từng module test

```bash
python -m pytest tests/test_qa.py -v              # QA checks cơ bản
python -m pytest tests/test_config.py -v          # Config validation
python -m pytest tests/test_converters.py -v      # DayFilesConverter, StreamflowConverter, CLI
python -m pytest tests/test_pcp_converter.py -v   # PCPConverter (SWAT 2012 format)
python -m pytest tests/test_weather_plus.py -v    # SWATPlusWeatherConverter (SWAT+)
python -m pytest tests/test_weather.py -v         # WeatherPreprocessor core
python -m pytest tests/test_streamflow.py -v      # StreamflowPreprocessor core
python -m pytest tests/test_dem.py tests/test_landuse.py tests/test_soil.py -v
```

### 2.2 Chạy chỉ live tests (dùng dữ liệu thực)

```bash
python -m pytest -v -k "live"
```

Live tests trong dự án:
- `test_live_ankhe` — đọc `R_ANKHE.day` + `master_pcp.txt`, viết SWAT 2012 `.pcp`
- `test_live_value_precision` — kiểm tra format số trong file thực
- `test_live_pcp_header_and_format` — kiểm tra header SWAT+ từ `R_ANKHE.day`

---

## 3. Test CLI Thủ Công

### 3.1 Validate config

```bash
swatprep validate examples/config_minimal.yaml
```

### 3.2 Inspect file

```bash
swatprep inspect weather examples/data/weather/ST001.csv
swatprep inspect raster examples/data/dem_30m.tif   # yêu cầu rasterio
```

---

## 4. Pipeline Converter: Dữ Liệu Khí Hậu Việt Nam

### Bước 1 — Merge files `.day` thành CSV per-station

**Input:** thư mục chứa `R_STATION.day`, `Tx_STATION.day`, `Tm_STATION.day`

```bash
swatprep convert climate r aw_day_files/ merged_csvs/
```

**Output:** mỗi trạm một CSV với cột `date, precip, tmax, tmin`

```
merged_csvs/
├── ANKHE.csv
├── BATO.csv
└── PLEIKU.csv
```

**Python API:**

```python
from pathlib import Path
from swatprep.converters import DayFilesConverter

result = DayFilesConverter(
    data_dir=Path("raw/"),
    out_dir=Path("merged/"),
).convert()

print(f"Stations: {result.stations_found}")
print(f"Files: {len(result.files_written)}")
```

---

### Bước 2a — SWAT 2012 `.pcp` files (PCPConverter)

**Input:** `master_pcp.txt` + thư mục `R_STATION.day`

Format `master_pcp.txt`:
```
ID,NAME,LAT,LONG,ELEVATION
15,pcp_ANKHE,13.95,108.65,416
```

```bash
swatprep convert pcp master_pcp.txt raw_day_files/ swat_pcp/
```

**Output SWAT 2012:**
```
pcp_ANKHE
Lati      13.950
Long     108.650
Elev     416.000
19770101
     0.000
     5.500
```

**Python API:**

```python
from swatprep.converters import PCPConverter

result = PCPConverter(
    master_path=Path("master_pcp.txt"),
    data_dir=Path("raw/"),
    out_dir=Path("swat_pcp/"),
).convert()

print(f"Written: {len(result.files_written)}")
print(f"Unmatched: {result.unmatched}")
```

**Kiểm tra file output:**

```bash
head -8 swat_pcp/pcp_ANKHE.pcp
```

---

### Bước 2b — SWAT+ weather files (SWATPlusWeatherConverter)

**Input:** merged CSVs (từ Bước 1) + `master_pcp.txt`

```python
from swatprep.converters import SWATPlusWeatherConverter

result = SWATPlusWeatherConverter(
    data_dir=Path("merged/"),
    out_dir=Path("swatplus/"),
    metadata=Path("master_pcp.txt"),
).convert()
```

**Output SWAT+:**
```
swatplus/
├── ankhe.pcp        # precipitation
├── ankhe.tmp        # tmax + tmin (2 cột, space separator)
├── pcp.cli          # index file
└── tmp.cli
```

**Kiểm tra format `.pcp`:**
```bash
head -5 swatplus/ankhe.pcp
# pcp_ANKHE SWAT+ pcp file
# nbyr     tstep       lat       lon      elev
#   43         0    13.950   108.650   416.000
# 1977    1    0.00000
```

**Kiểm tra format `.tmp` (2 cột):**
```bash
head -5 swatplus/ankhe.tmp
# 1977    1   25.00000    18.00000
```

---

### Bước 3 — Streamflow

**Format wide (YYYYMMDD date column):**

```bash
swatprep convert streamflow dailyStreamflow_68gauges.csv output/flow_long.csv \
    --format wide_yyyymmdd
```

**Format per-station (thư mục CSV riêng mỗi trạm):**

```bash
swatprep convert streamflow station_csvs/ output/flow_long.csv \
    --format per_station --glob "Q_*.csv"
```

---

## 5. Kiểm Tra QA Checks

Mọi converter trả về `list[QACheck]` với status `pass/warn/fail`.

| Status | Ý nghĩa |
|--------|---------|
| `pass` | Dữ liệu hợp lệ |
| `warn` | Thiếu file optional — pipeline vẫn chạy |
| `fail` | Lỗi nghiêm trọng — nên dừng |

```python
from swatprep.qa import failures, warnings

result = converter.convert()

for c in failures(result.qa):
    print(f"FAIL [{c.name}]: {c.message}")

for c in warnings(result.qa):
    print(f"WARN [{c.name}]: {c.message}")
```

---

## 6. Pipeline Đầy Đủ (End-to-End Script)

```python
from pathlib import Path
from swatprep.converters import (
    DayFilesConverter, PCPConverter,
    SWATPlusWeatherConverter, StreamflowConverter,
)

RAW_DIR    = Path("raw_data/")
MASTER     = Path("master_pcp.txt")
MERGED_DIR = Path("merged/")
SWAT_DIR   = Path("swat2012_pcp/")
PLUS_DIR   = Path("swatplus_weather/")
FLOW_OUT   = Path("output/streamflow_long.csv")

# Bước 1: merge .day files
r1 = DayFilesConverter(data_dir=RAW_DIR, out_dir=MERGED_DIR).convert()
print(f"[1] Merged {len(r1.stations_found)} stations -> {MERGED_DIR}")

# Bước 2a: SWAT 2012 .pcp
r2a = PCPConverter(master_path=MASTER, data_dir=RAW_DIR, out_dir=SWAT_DIR).convert()
print(f"[2a] SWAT 2012: {len(r2a.files_written)} files, unmatched={r2a.unmatched}")

# Bước 2b: SWAT+ weather
r2b = SWATPlusWeatherConverter(
    data_dir=MERGED_DIR, out_dir=PLUS_DIR, metadata=MASTER
).convert()
print(f"[2b] SWAT+: {len(r2b.files_written)} files")

# Bước 3: Streamflow
r3 = StreamflowConverter(
    source=Path("dailyStreamflow_68gauges.csv"),
    input_format="wide_yyyymmdd",
).convert(out_path=FLOW_OUT)
print(f"[3] Streamflow: {r3.n_stations} stations, {r3.n_days} days")
```

---

## 7. Cấu Trúc Test Suite

```
tests/
├── conftest.py              # fixtures dùng chung
├── test_qa.py               # 9 tests
├── test_config.py           # 16 tests
├── test_api.py              # 4 tests (1 skip nếu không có rasterio)
├── test_converters.py       # 25 tests (DayFilesConverter + StreamflowConverter + CLI)
├── test_pcp_converter.py    # 13 tests (2 live với R_ANKHE.day)
├── test_weather_plus.py     # 13 tests (1 live)
├── test_weather.py          # 14 tests
├── test_streamflow.py       # 11 tests
├── test_dem.py              # 4 tests
├── test_landuse.py          # 6 tests
├── test_soil.py             # 8 tests
├── test_manifest.py         # 6 tests
└── test_raster_utils.py     # 2 tests (skip nếu không có rasterio)
```

**Tổng: 129 tests pass, 3 skip (yêu cầu rasterio)**

---

## 8. Ghi Chú

**Stale `.pyc` cache:** Khi Edit tool cập nhật file `.py` trên Windows, mtime trong Linux sandbox có thể không cập nhật, khiến Python chạy code cũ từ cache. Fix bằng cách rewrite file qua Python:

```bash
python3 -c "
content = open('file.py').read()
open('file.py', 'w').write(content)
"
```

**Live tests yêu cầu file thực:**
- `R_ANKHE.day` — 15705 dòng dữ liệu mưa từ 1977-01-01
- `master_pcp.txt` — metadata 22 trạm
