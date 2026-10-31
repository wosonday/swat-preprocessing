# Hướng Dẫn Test swatprep — Từ Đầu Đến Cuối

Hướng dẫn này bao gồm toàn bộ vòng đời test: cài đặt môi trường → chạy unit tests → test CLI thủ công → chạy pipeline thực tế với dữ liệu Việt Nam.

---

## 1. Chuẩn Bị Môi Trường

### 1.1 Cài đặt package

```bash
cd swat-preprocessing/
uv sync --extra geo --extra app --extra dev   # lõi + raster + giao diện web + pytest, đúng phiên bản trong uv.lock
# hoặc: pip install -e ".[geo,app,dev]"
```

### 1.2 Kiểm tra cài đặt

```bash
uv run swatprep --version        # phải in ra đúng `version` trong pyproject.toml
uv run swatprep --help           # liệt kê các lệnh
uv run swatprep convert --help   # liệt kê subcommands convert
```

---

## 2. Chạy Toàn Bộ Unit Tests

```bash
cd swat-preprocessing/
uv run python -m pytest -q
```

**Kết quả mong đợi** (v0.3.1, đã cài đủ `geo`, `app`, `dev`):
```
413 passed   (khoảng 10-25 s; test build wheel trong tests/ui/test_launch.py chiếm phần lớn)
```

Nếu chưa cài `rasterio`/`geopandas` (nhóm `geo`), các test raster và `clip` sẽ bị skip.

### 2.0 Test giao diện web (`tests/ui/`)

| Tệp | Kiểm tra |
|---|---|
| `test_settings.py`, `test_environment.py` | Biến môi trường, báo cáo môi trường (không bao giờ ném lỗi) |
| `test_fs_browser.py`, `test_project_io.py`, `test_recent.py` | Liệt kê thư mục an toàn, YAML giữ comment, thư mục gần đây |
| `test_form_model.py`, `test_form_state.py` | Kiểu trường -> ô nhập; **đồng bộ `LAYOUT` với `config.py`**; ghi YAML không thêm mặc định |
| `test_runner.py` | Validate/Build trên bản sao `examples/` (end-to-end) |
| `test_pages.py`, `test_project_form.py` | Trang chạy qua `streamlit.testing.v1.AppTest`: mở config, sửa, lưu, bật/tắt mục, lỗi tại ô, Build |
| `test_launch.py` | Lệnh `swatprep-ui`; wheel có đủ trang và theme |

```bash
uv run python -m pytest tests/ui -q
```

### 2.1 Chạy từng module test

```bash
python -m pytest tests/test_qa.py -v              # QA checks cơ bản
python -m pytest tests/test_config.py -v          # Config validation
python -m pytest tests/test_converters.py -v      # DayFilesConverter, StreamflowConverter, CLI
python -m pytest tests/test_station_weather_converter.py -v  # StationWeatherConverter (raw SWAT2012/CSV input)
python -m pytest tests/test_weather_plus_writer.py -v  # SWATPlusWeatherWriter (SWAT+ data files + weather-sta.cli/weather-wgn.cli)
python -m pytest tests/test_weather.py -v         # WeatherPreprocessor core
python -m pytest tests/test_streamflow.py -v      # StreamflowPreprocessor core
python -m pytest tests/test_dem.py tests/test_landuse.py tests/test_soil.py -v
```

### 2.2 Live tests

Bộ test hiện tại không còn live test nào chạy trên dữ liệu thực ngoài repo
(các live test trước đây thuộc `test_pcp_converter.py`/`test_weather_plus.py`,
đã bị xoá cùng `PCPConverter`/`TmpConverter`/`SWATPlusWeatherConverter`). Toàn
bộ test hiện dùng fixture tổng hợp trong `tests/conftest.py`.

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
├── STATION01.csv
├── STATION03.csv
└── STATION02.csv
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

### Bước 2 — SWAT2012 và/hoặc SWAT+ weather files (StationWeatherConverter)

**Input:** `master_pcp.txt`/`master_tmp.txt` + thư mục file trạm thô
(`pcp_STATION.txt`/`tmp_STATION.txt` kiểu SWAT Classic, hoặc CSV).

Format `master_pcp.txt`:
```
ID,NAME,LAT,LONG,ELEVATION
15,pcp_STATION01,15.0,105.0,100
```

```bash
swatprep convert weather \
  --pcp-master master_pcp.txt --pcp-dir raw_pcp/ \
  --tmp-master master_tmp.txt --tmp-dir raw_tmp/ \
  --target swat2012 --target swatplus \
  weather_out/
```

Với nhiều hơn một `--target`, mỗi định dạng được ghi vào thư mục con riêng:
`weather_out/swat2012/`, `weather_out/swatplus/`.

**Output SWAT2012** (`weather_out/swat2012/pcp_STATION01.txt`, không header metadata):
```
19770101
0.0
5.5
```

**Output SWAT+** (`weather_out/swatplus/STATION01.pcp`, header 3 dòng):
```
STATION01.pcp: Precipitation data - file written by swatprep ...
nbyr     tstep       lat       lon      elev
  43         0    15.000   105.000   100.000
1977    1    0.00000
1977    2    5.50000
```

**Python API:**

```python
from swatprep.converters.station_weather import StationWeatherConverter
from swatprep.writers.weather import WeatherWriter
from swatprep.writers.weather_plus import SWATPlusWeatherWriter

result = StationWeatherConverter(
    pcp_master=Path("master_pcp.txt"), pcp_dir=Path("raw_pcp/"),
    tmp_master=Path("master_tmp.txt"), tmp_dir=Path("raw_tmp/"),
).convert()

written_2012 = WeatherWriter(result, Path("weather_out/swat2012")).write()
written_plus = SWATPlusWeatherWriter(result, Path("weather_out/swatplus")).write()

print(f"SWAT2012: {len(written_2012)} files")
print(f"SWAT+:    {len(written_plus)} files")
```

**Kiểm tra file output:**

```bash
head -3 weather_out/swat2012/pcp_STATION01.txt
head -5 weather_out/swatplus/STATION01.pcp
cat weather_out/swatplus/weather-sta.cli    # station registry
cat weather_out/swatplus/weather-wgn.cli    # WGN statistics
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
from swatprep.converters import DayFilesConverter, StreamflowConverter
from swatprep.converters.station_weather import StationWeatherConverter
from swatprep.writers.weather import WeatherWriter
from swatprep.writers.weather_plus import SWATPlusWeatherWriter

RAW_DIR     = Path("raw_data/")
PCP_MASTER  = Path("master_pcp.txt")
TMP_MASTER  = Path("master_tmp.txt")
MERGED_DIR  = Path("merged/")
SWAT_DIR    = Path("swat2012_weather/")
PLUS_DIR    = Path("swatplus_weather/")
FLOW_OUT    = Path("output/streamflow_long.csv")

# Bước 1: merge .day files
r1 = DayFilesConverter(data_dir=RAW_DIR, out_dir=MERGED_DIR).convert()
print(f"[1] Merged {len(r1.stations_found)} stations -> {MERGED_DIR}")

# Bước 2: raw pcp/tmp station files -> WeatherResult -> SWAT2012 + SWAT+
r2 = StationWeatherConverter(
    pcp_master=PCP_MASTER, pcp_dir=RAW_DIR,
    tmp_master=TMP_MASTER, tmp_dir=RAW_DIR,
).convert()
w2a = WeatherWriter(r2, SWAT_DIR).write()
w2b = SWATPlusWeatherWriter(r2, PLUS_DIR).write()
print(f"[2a] SWAT2012: {len(w2a)} files")
print(f"[2b] SWAT+: {len(w2b)} files")

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
├── conftest.py                       # fixtures dùng chung
├── test_qa.py                        # 9 tests
├── test_config.py                    # 17 tests
├── test_api.py                       # 4 tests (1 skip nếu không có rasterio)
├── test_converters.py                # 30 tests (DayFilesConverter + StreamflowConverter + CLI)
├── test_station_weather_converter.py # 9 tests (StationWeatherConverter: raw SWAT2012/CSV input)
├── test_weather_plus_writer.py       # 12 tests (SWATPlusWeatherWriter: data files + weather-sta.cli/weather-wgn.cli)
├── test_weather.py                   # 19 tests
├── test_streamflow.py                # 11 tests
├── test_dem.py                       # 5 tests
├── test_landuse.py                   # 7 tests
├── test_soil.py                      # 8 tests
├── test_manifest.py                  # 6 tests
└── test_raster_utils.py              # skip nếu không có rasterio
```

**Tổng: `python -m pytest -v -k "not rasterio"` → xem output cho số liệu mới nhất.**

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
- `R_STATION01.day` — 15705 dòng dữ liệu mưa từ 1977-01-01
- `master_pcp.txt` — metadata 22 trạm
