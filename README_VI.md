# swatprep

`swatprep` là thư viện Python kèm CLI để chuẩn bị dữ liệu DEM, sử dụng đất, thổ nhưỡng, khí tượng và
dòng chảy quan trắc cho SWAT Classic và SWAT+. Anh/chị mô tả dự án một lần trong file YAML rồi chạy
`swatprep build`.

Công cụ giới hạn có chủ ý ở vai trò **tiền xử lý và ghi định dạng đầu vào**; không thay thế QSWAT,
QSWAT+, SWAT+ Editor, TauDEM, WhiteboxTools, SWAT+ Toolbox, PEST hay quy trình hiệu chỉnh.

Tài liệu chi tiết: **[docs/USER_GUIDE_VI.md](docs/USER_GUIDE_VI.md)** (hướng dẫn từng bước, mọi tham số YAML)
· [examples/config_full.yaml](examples/config_full.yaml) (file mẫu có chú thích) ·
[docs/WEATHER_OUTPUT.md](docs/WEATHER_OUTPUT.md) · [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) ·
[TESTING_GUIDE.md](TESTING_GUIDE.md).

## Chức năng

| Nhóm | Nội dung |
|---|---|
| Cấu hình | YAML kiểm tra bằng Pydantic; đường dẫn tương đối tính từ file YAML; `validate` báo mọi file thiếu trong một lần |
| Raster (DEM, sử dụng đất, thổ nhưỡng) | Cắt theo `project.boundary`, **chiếu về `project.crs`**, tuỳ chọn `resolution`; tiết kiệm bộ nhớ (đọc theo dải, chỉ đọc cửa sổ lưu vực); thống kê DEM; đối chiếu mã raster với bảng tra / bảng đất; bảng chỉ giữ các mã có trong lưu vực; raster đã cắt và bảng ghi cùng một `output_dir` |
| Khí tượng | Kiểm tra CSV trạm và số liệu ngày, tính thống kê WGN, xuất **SWAT+** hoặc **SWAT Classic** (`project.targets`), nguồn mưa / nhiệt độ tách riêng, `file_pattern`; **điền ngày thiếu** từ nguồn CSV hoặc NetCDF theo ngày, có hiệu chỉnh sai lệch từng trạm |
| Dòng chảy | Kiểm tra CSV dạng dài và ghi theo trạm |
| Kiểm soát chất lượng | Mọi bước trả về kiểm tra `pass` / `warn` / `fail`; mỗi lần build ghi `manifest.json` và `qa_report.md` |
| Chuyển đổi | File `.day`, bảng dòng chảy dạng rộng, file trạm thô -> CSV / SWAT2012 / SWAT+ |

Ngoài phạm vi: phân định lưu vực, sinh HRU/LSU, `project.sqlite` SWAT+ hoàn chỉnh, hiệu chỉnh và phân
tích bất định, tự động tải dữ liệu, giao diện đồ họa.

## Cài đặt

```bash
pip install -e .[geo,dev]     # đầy đủ: raster, cắt, chiếu lại (rasterio, geopandas, shapely)
pip install -e .[dev]         # bản nhẹ: cấu hình, QA, khí tượng, dòng chảy
swatprep --version
```

## Bắt đầu nhanh

1. Viết `config.yaml` (lấy [`examples/config_full.yaml`](examples/config_full.yaml) làm gốc).
2. `swatprep validate config.yaml`: kiểm tra YAML và mọi file đầu vào có tồn tại.
3. *(tuỳ chọn)* `swatprep fill weather --config config.yaml`: điền ngày thiếu của trạm.
4. `swatprep build config.yaml` (hoặc `--only clip|dem|landuse|soil|weather|streamflow`).
5. Đọc `output/qa_report.md`, sửa mọi dòng `fail`, xem lại các dòng `warn`.

## Cách viết YAML

Quy tắc ngắn gọn (chi tiết trong hướng dẫn):

- Chỉ `project` là bắt buộc; mục nào không khai báo sẽ bị bỏ qua.
- Đường dẫn tương đối tính từ thư mục chứa file YAML. Trên Windows nên viết `D:/data/x.tif` (dấu `/`)
  hoặc nhân đôi dấu `\` trong dấu nháy kép.
- Ngày viết dạng chuỗi ISO `"2000-01-01"`; `weather.end` không được trước `weather.start`.
- Trường bỏ trống sẽ nhận giá trị mặc định (xem bảng bên dưới).

Ví dụ đầy đủ và hợp lệ:

```yaml
project:
  name: "Chu_basin"
  crs: "EPSG:32648"                      # CRS đích của mọi raster đã cắt
  boundary: "./data/boundary.shp"        # có ranh giới thì dem / landuse / soil tự được cắt
  output_dir: "./output"
  targets: ["swatplus"]                  # swatplus | swat | cả hai

dem:
  path: "./data/dem.tif"
  output_name: "dem_projected.tif"       # -> output/spatial/
  resampling: bilinear                   # nearest | bilinear | cubic (khi phải chiếu lại)
  resolution: 30                         # tuỳ chọn; theo đơn vị của project.crs

landuse:
  raster: "./data/landuse.tif"
  lookup: "./data/landuse_lookup.csv"
  source_code_col: "code"
  swat_code_col: "swat_code"
  swat_name_col: "swat_name"
  output_name: "landuse_clip.tif"        # -> output/landuse/ (luôn lấy mẫu nearest)
  resolution: 10

soil:
  raster: "./data/soil.tif"
  table: "./data/usersoil.csv"
  soil_key_col: "SOIL_ID"
  output_name: "soil_clip.tif"           # -> output/soil/

weather:
  stations: "./data/stations.csv"        # id, name, lat, lon, elev
  data_dir: "./data/weather"             # mỗi trạm một CSV
  file_pattern: "{id}.csv"               # hoặc "{name}.csv"
  variables: [precip, tmax, tmin]
  start: "2000-01-01"
  end: "2020-12-31"
  missing_policy: "warn"                 # fail | warn

streamflow:
  path: "./data/streamflow.csv"
  date_col: "date"
  station_id_col: "station_id"
  value_col: "flow"
  units: "m3s"                           # m3s | mm
```

### Bảng tham chiếu các mục

| Mục | Bắt buộc | Tuỳ chọn (mặc định) |
|---|---|---|
| `project` | `name`, `crs` | `boundary` (không), `output_dir` (`./output`), `targets` (`[swatplus]`) |
| `dem` | `path` | `output_name` (`dem_projected.tif`), `clip` (`true`), `resampling` (`bilinear`), `resolution` |
| `landuse` | `raster`, `lookup` | `source_code_col` (`code`), `swat_code_col` (`swat_code`), `swat_name_col` (`swat_name`), `output_name` (`landuse_clip.tif`), `clip` (`true`), `output_lookup` (`true`), `resolution` |
| `soil` | `raster`, `table` | `soil_key_col` (`soil_id`), `output_usersoil` (`true`), `usersoil_format` (`swat`), `output_name` (`soil_clip.tif`), `clip` (`true`), `output_lookup` (`true`), `resolution` |
| `weather` | `start`, `end` và một nguồn (`stations` + `data_dir`, hoặc `precip` / `temp`) | `file_pattern` (`{id}.csv`), `variables` (`[precip, tmax, tmin]`), `units`, `missing_policy` (`fail`), `fill` |
| `streamflow` | `path` | `format` (`long`; `per_station` for one-station files, id = file name), `glob` (`Q_*.csv`), `date_col` (`date`), `station_id_col` (`station_id`), `value_col` (`flow`), `units` (`m3s`) |
| `clip` (danh sách) | mỗi mục: `src`, `dst` | `mask` (`false`), `resampling` (`nearest`), `resolution`; cần `project.boundary` |

## Cắt raster và chiếu về CRS dự án

Khi `project.boundary` được đặt, `build` cắt `dem`, `landuse`, `soil` theo lưu vực và **chiếu về
`project.crs`** trong cùng một lần chạy; raster và bảng đã lọc được ghi chung vào `output_dir`:

| Mục | Raster ghi vào | Bảng ghi |
|---|---|---|
| `dem` | `<output_dir>/spatial/<output_name>` | `spatial/dem_info.json` |
| `landuse` | `<output_dir>/landuse/<output_name>` | `landuse/landuse_lookup.csv` (các lớp có trong lưu vực) |
| `soil` | `<output_dir>/soil/<output_name>` | `soil/usersoil.csv` (các loại đất có trong lưu vực, bố cục 152 cột của SWAT+) |

- Chỉ cửa sổ quanh ranh giới được đọc và chiếu lại, nên raster khu vực hay toàn châu lục không bao giờ
  bị nạp nguyên.
- Sử dụng đất và thổ nhưỡng dùng lấy mẫu `nearest` (mã lớp không bị nội suy); DEM dùng `dem.resampling`
  (mặc định `bilinear`). Không đặt `resolution` thì GDAL chọn kích thước ô gần với raster gốc.
- File đã cắt được làm lại khi nguồn hoặc ranh giới mới hơn, hoặc khi CRS / độ phân giải không còn khớp
  cấu hình; ngược lại được giữ nguyên (`clip_skipped`).
- Đặt `clip: false` trong từng mục để tắt (quét cả raster, bảng đầy đủ, không ghi raster đã cắt).
- Có thể dùng độc lập:

```bash
swatprep clip DEM.tif BOUNDARY.shp DEM_clip.tif --crs EPSG:32648 --resampling bilinear --resolution 30
swatprep clip LANDUSE.tif BOUNDARY.shp LU_clip.tif --crs EPSG:32648 --mask
```

## Điền ngày thiếu cho số liệu khí tượng

`swatprep fill weather` điền các ngày thiếu của trạm đo từ nguồn lưới hoặc nguồn theo trạm do anh/chị tự
trích xuất (vệ tinh, tái phân tích) trước khi `build`:

```yaml
weather:
  stations: ./data/obs/stations.csv
  data_dir: ./data/obs
  variables: [precip, tmax, tmin]
  start: "1981-01-01"
  end: "2014-12-31"
  fill:
    type: netcdf                    # csv | netcdf
    output_dir: ./data/filled
    min_overlap_days: 365           # mặc định 10
    netcdf:
      path: ./data/grid.nc          # theo ngày; mm và degC
      var_map: { precip: pr, tmax: tasmax, tmin: tasmin }
      search_radius: 1              # 0-5; tìm ô có dữ liệu quanh ô gần nhất
```

```bash
swatprep fill weather --config config.fill.yaml
```

`build` chỉ điền ngày thiếu khi đặt `weather.fill.run_in_build: true` (một file, một lệnh: điền từ dữ liệu thực đo
`weather.stations` / `data_dir`, xuất CSV đã điền vào `weather.fill.output_dir`, rồi dựng từ đó; `output_dir` phải khác
`data_dir`). Nếu không, `build` bỏ qua khối `weather.fill`. `weather.missing_policy` chỉ quy định
`build` coi ngày thiếu là lỗi (`fail`, không ghi gì) hay cảnh báo (`warn`, ngày thiếu ghi là `-99`). Ngày thiếu là
ô trống hoặc ngày vắng hàng trong CSV của trạm; giá trị `-99` trong CSV được đọc như số thật. Chi tiết:
[docs/WEATHER_MISSING_FILL_VI.md](docs/WEATHER_MISSING_FILL_VI.md).

Với từng trạm và từng biến, chuỗi ngoài được hiệu chỉnh trên các ngày hai nguồn cùng có số liệu
(tỷ lệ tuyến tính; Teutschbein và Seibert, 2012): mưa nhân hệ số tỷ lệ trung bình, nhiệt độ cộng độ
lệch trung bình. Ngày đã có số liệu đo không bao giờ bị thay đổi. Kết quả ghi vào `output_dir` kèm
`fill_report.csv`; sau đó trỏ `weather.stations` và `weather.data_dir` của file build vào thư mục này.
Ô lưới gần trạm nhất được dùng (trạm nằm đúng giữa hai ô lấy ô chỉ số thấp hơn); ô đó không có dữ liệu
thì lấy ô có dữ liệu gần nhất trong `search_radius` và có cảnh báo.

## Dòng lệnh

| Lệnh | Chức năng |
|---|---|
| `swatprep validate CONFIG` | Kiểm tra YAML và sự tồn tại của file đầu vào; không ghi gì |
| `swatprep build CONFIG [--only MỤC]` | Chạy mọi mục đã khai báo hoặc một mục |
| `swatprep fill weather --config CONFIG` | Điền ngày thiếu (cờ dòng lệnh ghi đè YAML) |
| `swatprep clip RASTER BOUNDARY OUT [--mask] [--crs] [--resampling] [--resolution]` | Cắt (và tuỳ chọn chiếu) một raster |
| `swatprep inspect raster\|weather PATH` | Xem nhanh raster hoặc CSV khí tượng |
| `swatprep convert climate\|streamflow\|weather ...` | Chuyển đổi định dạng gốc |

```bash
swatprep convert climate DATA_DIR OUT_DIR                        # .day R_/Tx_/Tm_ -> CSV theo trạm
swatprep convert streamflow SOURCE OUT_PATH                      # dạng rộng / theo trạm -> CSV dạng dài
swatprep convert weather --pcp-master M.txt --pcp-dir D --tmp-master T.txt --tmp-dir E \
                         --target swat2012 --target swatplus OUT_DIR
```

## Python API

```python
from swatprep import SWATPrepProject

project = SWATPrepProject.from_config("config.yaml")
for check in project.validate():
    print(check.status, check.name, check.message)

result = project.build()                      # hoặc project.build(only="soil")
print(result.success, result.output_dir, result.manifest_path)
```

## Kết quả

```text
output/
  manifest.json            # file đã ghi, mục đã chạy, tóm tắt QA
  qa_report.md             # mọi kiểm tra pass / warn / fail
  spatial/    dem_projected.tif  dem_info.json
  landuse/    landuse_clip.tif  landuse_lookup.csv  landuse_vlookup.csv  landuse_raster_codes.csv
  soil/       soil_clip.tif  usersoil.csv  soil_vlookup.csv  soil_raster_codes.csv
  weather/    StationA.pcp  StationA.tmp  pcp.cli tmp.cli  weather-sta.cli  weather-wgn.cli  wgn.csv  stations.csv  swatplus_wgn_*.csv
  observed/   streamflow_ST001.csv  streamflow_meta.csv
```

`landuse_vlookup.csv` (`LANDUSE_ID, SWAT_CODE`) và `soil_vlookup.csv` (`SOIL_ID, SNAM`) là hai bảng tra cứu hai cột
(giá trị raster -> mã / tên) mà QSWAT / QSWAT+ yêu cầu: mỗi giá trị một hàng, sắp tăng dần, chỉ gồm giá trị có trong
lưu vực khi cắt, mã lặp giữ hàng đầu (đặt `output_lookup: false` trong `landuse` / `soil` để không ghi).

`project.targets` chọn định dạng khí tượng: `swatplus` (mặc định) ghi file SWAT+ kèm các file `*.cli`;
`swat` ghi SWAT Classic `pcp_<tên>.txt` / `tmp_<tên>.txt` và `master_*.txt` (cột `ID` là số thứ tự 1, 2, 3, ... của trạm, đánh số riêng trong `master_pcp` và `master_tmp`); chọn cả hai thì ghi vào
`weather/swatplus/` và `weather/swat/`. Xem [docs/WEATHER_OUTPUT.md](docs/WEATHER_OUTPUT.md). Đầu vào
không hợp lệ được báo thành lỗi QA và mục có lỗi nặng không được ghi.

## Thông báo QA thường gặp

| Kiểm tra | Ý nghĩa | Cách xử lý |
|---|---|---|
| `soil_unmatched_codes` | Mã đất trong raster không có trong cột `soil_key_col` của bảng | Thêm hàng (mã `0` thường là "WATER") hoặc gán đất tương đương |
| `landuse_unmatched_codes` | Lớp trong raster không có trong bảng tra | Thêm hàng vào bảng tra |
| `*_boundary_ignored` | Không dùng được ranh giới nên quét cả raster | Ranh giới cần có CRS và phải chồng lên raster |
| `dem_crs_reprojected` | CRS DEM khác `project.crs`, DEM đã cắt đã được chiếu lại | Chỉ là thông tin |
| `missing:<trạm>:<biến>` | Thiếu số liệu trong khoảng thời gian | Dùng `fill` hoặc `missing_policy: warn` |

## Phát triển

```bash
pytest -q                                   # test raster cần  pip install -e .[geo,dev]
python -m compileall swatprep tests
python -m build --sdist --wheel
```

Giữ mỗi processor nhỏ và dễ test: nạp một domain, kiểm tra cấu trúc và giả định thủy văn, trả về result
có `qa: list[QACheck]`, và để writer chỉ ghi dữ liệu đã được kiểm tra. Không biến dự án này thành công
cụ dựng mô hình SWAT+ hoàn chỉnh.

## Tài liệu tham khảo

- Arnold, J.G. và cs. (2012). *SWAT Input/Output Documentation, Version 2012*. Texas Water Resources
  Institute, TR-439.
- Bieger, K. và cs. (2017). Introduction to SWAT+. *J. Am. Water Resour. Assoc.*, 53(1), 115-130.
- Teutschbein, C., Seibert, J. (2012). Bias correction of regional climate model simulations for
  hydrological climate-change impact studies. *J. Hydrol.*, 456-457, 12-29.
