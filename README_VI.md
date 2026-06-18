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
- Orchestration `prepare()` cho các domain đã cấu hình
- Validate metadata DEM
- Validate lookup sử dụng đất và cross-check mã raster
- Validate bảng soil và cross-check mã raster
- Validate station/daily CSV khí tượng và tính thống kê WGN
- Validate CSV dòng chảy quan trắc
- Writer cho metadata không gian, lookup sử dụng đất, `usersoil.csv`, file thời
  tiết, dòng chảy quan trắc, `manifest.json` và `qa_report.md`
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
swatprep prepare config.yaml
```

Chạy một domain:

```bash
swatprep prepare config.yaml --only weather
swatprep prepare config.yaml --only streamflow
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

## Python API

```python
from swatprep import SWATPrepProject

project = SWATPrepProject.from_config("config.yaml")

checks = project.validate()
for check in checks:
    print(check.status, check.name, check.message)

result = project.prepare()
print(result.success)
print(result.output_dir)
print(result.manifest_path)
```

`prepare()` ghi `manifest.json` và `qa_report.md` khi có ít nhất một domain được
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

## Output Dự Kiến

Tùy domain được cấu hình, `prepare()` có thể ghi:

```text
output/
  manifest.json
  qa_report.md
  spatial/
    dem_info.json
    dem_projected.tif
  landuse/
    landuse_lookup.csv
    landuse_raster_codes.csv
    landuse_swat.tif
  soil/
    usersoil.csv
    soil_raster_codes.csv
  weather/
    ST001.pcp
    ST001.tmp
    wgn.csv
    stations.csv
  observed/
    streamflow_ST001.csv
    streamflow_meta.csv
```

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
