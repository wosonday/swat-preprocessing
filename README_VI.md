# swatprep

`swatprep` là một thư viện Python nhỏ kèm CLI để chuẩn bị dữ liệu DEM, sử dụng
đất, thổ nhưỡng, khí tượng và dòng chảy quan trắc cho quy trình SWAT Classic và
SWAT+.

Dự án được giới hạn có chủ ý ở vai trò **tiền xử lý dữ liệu và ghi định dạng đầu
vào**. Công cụ này không thay thế QSWAT, QSWAT+, SWAT+ Editor, TauDEM,
WhiteboxTools, SWAT+ Toolbox, PEST hay workflow hiệu chỉnh mô hình.

## Trạng Thái

Phiên bản hiện tại: `0.1.0`

Đã có:

- Schema cấu hình YAML bằng Pydantic
- Resolve đường dẫn tương đối theo thư mục chứa file cấu hình
- CLI validate cấu hình và đường dẫn dữ liệu
- Orchestration `build()` cho các domain đã cấu hình
- Validate metadata DEM
- Validate lookup sử dụng đất và cross-check mã raster
- Validate bảng soil và cross-check mã raster
- Validate station/daily CSV khí tượng và tính thống kê WGN
- Output khí tượng dạng **SWAT+** (mặc định) hoặc **SWAT Classic**, chọn qua
  `project.targets`; hỗ trợ nguồn precip/temp tách riêng và `file_pattern` tuỳ chỉnh
- Validate CSV dòng chảy quan trắc
- Writer cho metadata không gian, lookup sử dụng đất, `usersoil.csv`, file thời
  tiết, dòng chảy quan trắc, `manifest.json` và `qa_report.md`
- Bộ chuyển đổi dữ liệu thô (`swatprep convert …`) từ định dạng gốc sang CSV
  swatprep hoặc file SWAT+/SWAT Classic
- Unit test cho config, QA, processors, writers, behavior CLI/API và manifest

Vẫn ngoài phạm vi:

- Delineation lưu vực đầy đủ
- Sinh HRU/LSU
- Export hoàn chỉnh SWAT+ `project.sqlite`
- Hiệu chỉnh mô hình, phân tích độ nhạy hoặc bất định
- Tự động tải dữ liệu công khai
- GUI

Xem thêm [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md).

## Cài Đặt

Cài cho phát triển:

```bash
pip install -e .[dev]
```

Cài thêm GIS validation:

```bash
pip install -e .[geo,dev]
```

Extra `geo` cài `rasterio`, `geopandas` và `shapely`. Các phụ thuộc GIS vẫn là
optional để phần config, QA, CLI, weather và streamflow dùng được trong môi
trường nhẹ.

## CLI

Validate cấu hình và đường dẫn:

```bash
swatprep validate examples/config_minimal.yaml
```

Chạy toàn bộ domain đã cấu hình:

```bash
swatprep build config.yaml
```

Chạy một domain:

```bash
swatprep build config.yaml --only weather
swatprep build config.yaml --only streamflow
```

Example đi kèm có dữ liệu synthetic và phải validate thành công.

Inspect CSV khí tượng:

```bash
swatprep inspect weather path/to/station.csv
```

Inspect raster:

```bash
swatprep inspect raster path/to/dem.tif
```

### Chuyển đổi dữ liệu thô

Các converter độc lập chuyển định dạng gốc sang CSV swatprep hoặc trực tiếp
sang file SWAT, không phụ thuộc pipeline `build`:

```bash
# Gộp file .day theo biến (R_/Tx_/Tm_) thành CSV theo trạm
swatprep convert climate DATA_DIR OUT_DIR

# Dòng chảy dạng wide hoặc per-station → CSV long-format
swatprep convert streamflow SOURCE OUT_PATH

# Mưa / nhiệt độ thô → SWAT 2012 (Classic) .pcp / .tmp
swatprep convert pcp MASTER_PATH DATA_DIR OUT_DIR
swatprep convert tmp MASTER_PATH DATA_DIR OUT_DIR

# pcp + tmp (SWAT Classic) → file khí tượng SWAT+ (.pcp/.tmp + pcp.cli/tmp.cli)
swatprep convert swatplus MASTER_PATH PCP_DIR TMP_DIR OUT_DIR
```

Dùng converter để *chuẩn bị* dữ liệu thô thành CSV theo trạm, rồi trỏ
`weather.data_dir` vào đó và chạy `swatprep build`. Xem
[`docs/WEATHER_OUTPUT.md`](docs/WEATHER_OUTPUT.md).

## Python API

```python
from swatprep import SWATPrepProject

project = SWATPrepProject.from_config("config.yaml")

checks = project.validate()
for check in checks:
    print(check.status, check.name, check.message)

result = project.build()
print(result.success)
print(result.output_dir)
print(result.manifest_path)
```

`build()` ghi `manifest.json` và `qa_report.md` khi có ít nhất một domain được
xử lý.

## Cấu Hình

Cấu hình tối thiểu:

```yaml
project:
  name: "ExampleBasin_2024"
  crs: "EPSG:32648"
  output_dir: "./output"
  targets:
    - "swatplus"
```

Các section được hỗ trợ:

- `project`
- `dem`
- `landuse`
- `soil`
- `weather`
- `streamflow`

Đường dẫn tương đối được resolve theo thư mục chứa file YAML, không phụ thuộc
working directory của process.

Ngày trong phần weather được validate theo định dạng ISO. `weather.end` phải lớn
hơn hoặc bằng `weather.start`.

Một section `weather` điển hình (định dạng output do `project.targets` ở trên
quyết định):

```yaml
weather:
  stations: "./data/weather_stations.csv"   # id, name, lat, lon, elev
  data_dir: "./data/weather"                # mỗi trạm một CSV
  file_pattern: "{id}.csv"                   # mặc định; dùng "{name}.csv" để khớp theo tên
  variables: ["precip", "tmax", "tmin"]
  start: "2000-01-01"
  end:   "2000-12-31"
  missing_policy: "warn"                     # "fail" | "warn"
```

Mưa và nhiệt độ có thể lấy từ hai mạng lưới trạm khác nhau qua sub-block
`weather.precip` / `weather.temp` — xem
[`docs/WEATHER_OUTPUT.md`](docs/WEATHER_OUTPUT.md).

## Output Dự Kiến

Tùy domain được cấu hình, `build()` có thể ghi:

```text
output/
  manifest.json
  qa_report.md
  spatial/
    dem_info.json
  landuse/
    landuse_lookup.csv
    landuse_raster_codes.csv
  soil/
    usersoil.csv
    soil_raster_codes.csv
  weather/
    StationA.pcp     # SWAT+ daily (dòng year/doy value)
    StationA.tmp
    pcp.cli tmp.cli  # file chỉ mục SWAT+
    wgn.csv
    stations.csv
  observed/
    streamflow_ST001.csv
    streamflow_meta.csv
```

Định dạng **weather** theo `project.targets`: `swatplus` (mặc định) ghi file
SWAT+ kèm `*.cli`; `swat` ghi SWAT Classic `.pcp/.tmp`; chọn cả hai thì mỗi
định dạng vào thư mục con `weather/swatplus/` và `weather/swat/`. Tên file lấy
từ cột `name`. Xem [`docs/WEATHER_OUTPUT.md`](docs/WEATHER_OUTPUT.md) để biết
chi tiết `file_pattern` (mặc định `{id}.csv`) và nguồn tách precip/temp.

Input không hợp lệ phải được báo thành QA failure. Writer bỏ qua domain có lỗi
processor nghiêm trọng.

## Phát Triển

Chạy test:

```bash
pytest -q
```

Kiểm tra cú pháp Python:

```bash
python -m compileall swatprep tests
```

Build package:

```bash
python -m build --sdist --wheel
```

Trạng thái kiểm chứng hiện tại:

- `pytest -q` pass với 87 tests.
- `python -m compileall swatprep tests` pass.

## Hướng Dẫn Triển Khai

Giữ mỗi processor nhỏ và dễ test:

1. Load một domain dữ liệu.
2. Validate cấu trúc bắt buộc và giả định thủy văn.
3. Trả về result dataclass có `qa: list[QACheck]`.
4. Writer chỉ serialize dữ liệu đã được validate.

Không biến project này thành công cụ dựng mô hình SWAT+ hoàn chỉnh. QSWAT/QSWAT+
và SWAT+ Editor vẫn chịu trách nhiệm delineation lưu vực, sinh HRU/LSU, routing
objects và xây dựng project database đầy đủ.
