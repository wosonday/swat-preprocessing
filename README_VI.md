# swatprep

`swatprep` là một thư viện Python nhỏ kèm CLI để chuẩn bị dữ liệu đầu vào thô
cho quy trình xây dựng mô hình SWAT Classic và SWAT+.

Dữ liệu mục tiêu gồm DEM, sử dụng đất, thổ nhưỡng, khí tượng và dòng chảy quan
trắc. Phạm vi dự án được giới hạn có chủ ý ở vai trò **tiền xử lý dữ liệu và
ghi định dạng đầu vào**, không thay thế QSWAT, QSWAT+, SWAT+ Editor, TauDEM,
WhiteboxTools hay các công cụ hiệu chỉnh mô hình.

## Trạng Thái Dự Án

Phiên bản hiện tại: `0.1.0`

Đã có:

- Schema cấu hình bằng Pydantic
- Nạp cấu hình YAML, trong đó đường dẫn tương đối được resolve theo vị trí file
  cấu hình
- Khung API cấp cao `SWATPrepProject`
- Khung CLI bằng Click
- Cấu trúc kiểm tra QA với `QACheck`
- Unit test cho cấu hình, API skeleton và QA

Chưa có:

- Processor cho DEM, land-use, soil, weather và streamflow
- Writer định dạng text cho SWAT Classic / SWAT+
- Writer cho `manifest.json` và `qa_report.md`
- Pipeline end-to-end tạo gói dữ liệu SWAT-ready

Hiện tại `swatprep prepare` sẽ raise `NotImplementedError` cho tới khi các
processor và writer được triển khai.

## Phạm Vi Thiết Kế

Thiết lập mô hình SWAT/SWAT+ có hai nhóm việc khác nhau:

1. Chuẩn bị dữ liệu đầu vào đáng tin cậy: hệ tọa độ, cắt theo ranh giới lưu vực,
   kiểm tra lookup, chuyển đổi đơn vị, kiểm tra chuỗi thời gian khí tượng và tạo
   bảng/file tương thích SWAT.
2. Xây dựng cấu trúc mô hình: delineation lưu vực, mạng sông suối, subbasin,
   LSU/HRU, đối tượng routing và database dự án SWAT+ hoàn chỉnh.

`swatprep` tập trung vào nhóm việc 1. Nhóm việc 2 nên để QSWAT/QSWAT+, SWAT+
Editor, TauDEM, WhiteboxTools hoặc một workflow chuyên biệt khác xử lý.

Xem thêm kiến trúc đã review trong [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md).

## Cài Đặt

Cài cho phát triển:

```bash
pip install -e .[dev]
```

Cài thêm phụ thuộc GIS cho các processor không gian trong tương lai:

```bash
pip install -e .[geo]
```

Extra `geo` cài `rasterio`, `geopandas` và `shapely`. Các phụ thuộc GIS được
tách riêng để phần config, CLI và tiện ích không gian nhẹ vẫn có thể dùng trong
môi trường tối giản.

## CLI

Kiểm tra cấu hình và đường dẫn dữ liệu đầu vào:

```bash
swatprep validate examples/config_minimal.yaml
```

Chạy tiền xử lý sau khi processor được triển khai:

```bash
swatprep prepare examples/config_minimal.yaml
```

Kiểm tra nhanh file CSV khí tượng:

```bash
swatprep inspect weather path/to/station.csv
```

Kiểm tra nhanh raster:

```bash
swatprep inspect raster path/to/dem.tif
```

File cấu hình mẫu hiện trỏ tới dữ liệu placeholder trong `examples/data/`, vì
vậy `swatprep validate examples/config_minimal.yaml` được kỳ vọng sẽ fail cho
tới khi các file dữ liệu mẫu thật sự tồn tại.

## Python API

```python
from swatprep import SWATPrepProject

project = SWATPrepProject.from_config("examples/config_minimal.yaml")
checks = project.validate()

for check in checks:
    print(check.status, check.name, check.message)
```

API chuẩn bị dữ liệu cấp cao dự kiến là:

```python
result = project.prepare()
print(result.output_dir)
print(result.manifest_path)
print(result.warning_count)
```

Lệnh gọi này hiện chưa được triển khai.

## Tổng Quan Cấu Hình

Cấu hình tối thiểu:

```yaml
project:
  name: "ExampleBasin_2024"
  crs: "EPSG:32648"
  output_dir: "./output"
  targets:
    - "swatplus"
```

Các section đã được schema hỗ trợ:

- `project`
- `dem`
- `landuse`
- `soil`
- `weather`
- `streamflow`

Đường dẫn tương đối được resolve theo thư mục chứa file YAML. Điều này giúp một
run có thể tái lập được dù chạy từ các working directory khác nhau.

Ngày trong phần weather được validate theo định dạng ISO. `weather.end` phải
lớn hơn hoặc bằng `weather.start`.

## Output MVP Dự Kiến

Khi hoàn thiện MVP, công cụ sẽ tạo một gói dữ liệu SWAT-ready, không phải một mô
hình hoàn chỉnh có thể chạy ngay:

```text
output/
  manifest.json
  qa_report.md
  spatial/
  weather/
  observed/
  swatplus_import/
  swat_classic_import/
```

Mọi file được ghi ra phải có trong `manifest.json`. Nếu QA có lỗi nghiêm trọng,
writer phải chặn việc ghi output.

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

Trạng thái đã kiểm chứng gần nhất:

- `pytest -q` pass với 27 tests.
- `python -m compileall swatprep tests` pass.
- `python -m build --sdist --wheel` pass.

## Thứ Tự Triển Khai Khuyến Nghị

1. Manifest writer và QA report writer
2. Weather CSV processor và writer cho precipitation/temperature
3. Streamflow observation processor
4. Validate lookup và reclassify land-use
5. Validate soil table và writer `usersoil.csv`
6. Validate, clip và reproject DEM
7. Ví dụ end-to-end bằng dữ liệu synthetic

Mỗi bước nên có test độc lập với fixture synthetic nhỏ.

## Ngoài Phạm Vi MVP

Không thêm các phần sau vào MVP:

- Delineation lưu vực đầy đủ từ DEM
- Sinh HRU/LSU
- Writer hoàn chỉnh cho SWAT+ `project.sqlite`
- Hiệu chỉnh mô hình, phân tích độ nhạy hoặc bất định
- Tự động tải dữ liệu công khai
- GUI

Các phần này chỉ nên xem là mở rộng tương lai sau khi lõi tiền xử lý dữ liệu đã
hoạt động ổn định và có test.
