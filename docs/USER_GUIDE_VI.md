# Hướng dẫn sử dụng swatprep và viết file cấu hình YAML

Tài liệu này hướng dẫn từng bước cách viết `config.yaml`, ý nghĩa của từng tham số, các chức năng
của `swatprep` và cách xử lý lỗi thường gặp. Mỗi ví dụ YAML đầy đủ (có mục `project:`) trong tài
liệu đều được kiểm tra tự động bằng `tests/test_docs_yaml.py`, nên có thể sao chép và dùng ngay.

## Mục lục

1. [Tổng quan và quy trình làm việc](#1-tổng-quan-và-quy-trình-làm-việc)
2. [Cài đặt](#2-cài-đặt)
3. [Quy tắc viết file YAML](#3-quy-tắc-viết-file-yaml)
4. [Tham chiếu từng mục của config.yaml](#4-tham-chiếu-từng-mục-của-configyaml)
5. [Các chức năng chính](#5-các-chức-năng-chính)
6. [Ví dụ hoàn chỉnh: lưu vực sông Chu](#6-ví-dụ-hoàn-chỉnh-lưu-vực-sông-chu)
7. [Đọc kết quả](#7-đọc-kết-quả)
8. [Lệnh dòng lệnh (CLI)](#8-lệnh-dòng-lệnh-cli)
9. [Python API](#9-python-api)
10. [Xử lý lỗi thường gặp](#10-xử-lý-lỗi-thường-gặp)
11. [Tài liệu tham khảo](#11-tài-liệu-tham-khảo)

---

## 1. Tổng quan và quy trình làm việc

`swatprep` là công cụ **tiền xử lý và ghi định dạng** cho SWAT Classic và SWAT+. Công cụ không thay
thế QSWAT/QSWAT+, SWAT+ Editor hay các bước phân định lưu vực, sinh HRU và hiệu chỉnh.

Mỗi dự án có một file `config.yaml` (hoặc hai file nếu cần điền số liệu thiếu). Quy trình đề nghị:

```
(1) Chuẩn bị dữ liệu gốc  ->  (2) Viết config.yaml  ->  (3) swatprep validate
        ->  (4) [tuỳ chọn] swatprep fill weather  ->  (5) swatprep build  ->  (6) đọc qa_report.md
```

Các mục (domain) của cấu hình và việc `build` làm với từng mục:

| Mục | Đầu vào | `build` thực hiện | Đầu ra chính |
|---|---|---|---|
| `project` | tên, CRS, ranh giới | đặt CRS đích và thư mục xuất | `manifest.json`, `qa_report.md` |
| `dem` | raster DEM | cắt theo ranh giới, chiếu về `project.crs`, thống kê độ cao | `spatial/dem_projected.tif`, `dem_info.json` |
| `landuse` | raster + bảng tra | cắt, chiếu, đối chiếu mã raster với bảng, lọc lớp có trong lưu vực | `landuse/landuse_clip.tif`, `landuse_lookup.csv` |
| `soil` | raster + bảng đất | cắt, chiếu, đối chiếu mã, lọc đất có trong lưu vực | `soil/soil_clip.tif`, `usersoil.csv` |
| `weather` | trạm + CSV theo trạm | kiểm tra số liệu, tính thống kê WGN, ghi file SWAT/SWAT+ | `weather/*` |
| `streamflow` | CSV dạng dài | kiểm tra, ghi theo trạm | `observed/*` |
| `clip` (tuỳ chọn) | danh sách raster | cắt riêng từng raster | file `dst` đã khai báo |

Thứ tự `build` chạy: `clip` -> `dem` -> `landuse` -> `soil` -> `weather` -> `streamflow` -> ghi manifest.

---

## 2. Cài đặt

**Người dùng** (không cần Python hay Docker): tải và nhấp đúp `install.bat` theo
[docs/INSTALL.md](INSTALL.md). Sau khi cài, mở **SWATprep** trên Desktop để dùng giao diện web; mọi
tham số YAML trong tài liệu này đều có ô nhập tương ứng trên trang **Project**, và lệnh `swatprep`
(CLI) cũng có sẵn.

**Người phát triển** (Python 3.10 trở lên; dự án dùng 3.12):

```bash
cd D:\SWAT-model\swat-preprocessing
uv sync --extra geo --extra app --extra dev   # đầy đủ: raster, giao diện web, test
uv run swatprep --version
uv run swatprep-ui                            # mở giao diện web
```

Có thể dùng pip thay uv: `pip install -e .[geo,app,dev]`. Bản nhẹ không có GIS: bỏ `geo`.

Bản nhẹ vẫn chạy được weather, streamflow và kiểm tra cấu hình. Các chức năng raster (đọc mã, cắt,
chiếu lại) cần `[geo]`; thiếu thư viện thì `build` báo cảnh báo `rasterio_missing` hoặc lỗi cắt rõ ràng.

---

## 3. Quy tắc viết file YAML

### 3.1 Cú pháp cơ bản

| Quy tắc | Ví dụ đúng | Lỗi hay gặp |
|---|---|---|
| Thụt lề bằng **dấu cách** (2 dấu cách), không dùng Tab | `project:`<br>`··name: "A"` | Tab làm YAML không đọc được |
| Khoá và giá trị cách nhau `: ` (có dấu cách sau `:`) | `crs: "EPSG:32648"` | `crs:"EPSG:32648"` |
| Ngày viết dạng chuỗi ISO | `start: "2000-01-01"` | `start: 01/01/2000` |
| Danh sách viết `[a, b]` hoặc từng dòng bắt đầu bằng `-` | `variables: [precip, tmax]` | |
| Chú thích bắt đầu bằng `#` | `# ghi chú` | |
| Mã có `:` hoặc ký tự đặc biệt nên đặt trong dấu nháy | `crs: "EPSG:32648"` | |

### 3.2 Đường dẫn

- **Đường dẫn tương đối** được tính từ **thư mục chứa file YAML**, không phụ thuộc thư mục đang chạy lệnh.
  Nhờ vậy cùng một file chạy đúng ở mọi nơi.
- **Đường dẫn tuyệt đối** vẫn dùng được. Trên Windows nên dùng `/` hoặc đặt dấu nháy kép nếu dùng `\`:

```yaml
dem:
  path: D:/DATA_STORAGE/_data/1_DEM/as_dem_3s_UTM48N.tif     # nên dùng dấu /
  # path: "D:\\DATA_STORAGE\\_data\\1_DEM\\as_dem.tif"       # dùng \ thì phải nhân đôi trong dấu nháy kép
```

- Việc kiểm tra file có tồn tại hay không được làm ở `validate`/`build`, không phải lúc đọc YAML. Nhờ đó
  `validate` có thể báo **tất cả** file thiếu trong một lần chạy.

### 3.3 Mục nào bắt buộc

- Chỉ `project` là bắt buộc. Các mục `dem`, `landuse`, `soil`, `weather`, `streamflow`, `clip` đều
  tuỳ chọn: **mục nào không khai báo sẽ không được xử lý**.
- Khi `project.boundary` được đặt, `dem`, `landuse`, `soil` tự được cắt (xem mục 5.1). Muốn tắt cho
  từng mục, đặt `clip: false` ở mục đó.

### 3.4 Bốn bước viết một config mới (có ví dụ)

**Bước 1. Khai báo `project`.** Mục tiêu: xác định CRS đích và nơi ghi kết quả.

```yaml
project:
  name: "Chu_basin"
  crs: "EPSG:32648"           # UTM 48N cho lưu vực ở kinh độ 102-108°E
  boundary: "./data/boundary.geojson"
  output_dir: "./output"
  targets: ["swatplus"]
```

**Bước 2. Thêm từng mục dữ liệu và chạy `swatprep validate` sau mỗi mục.** Cách này giúp định vị lỗi
sớm: lỗi luôn nằm ở mục vừa thêm.

**Bước 3. Chạy riêng mục vừa thêm** với `swatprep build config.yaml --only soil` để xem báo cáo QA của
đúng mục đó.

**Bước 4. Chạy toàn bộ** `swatprep build config.yaml` và đọc `output/qa_report.md`.

Ví dụ cấu hình tối thiểu (hợp lệ, chỉ có `project`):

```yaml
project:
  name: "ExampleBasin_2024"
  crs: "EPSG:32648"
```

---

## 4. Tham chiếu từng mục của config.yaml

Ký hiệu: **BB** = bắt buộc. Cột "Mặc định" để trống nghĩa là không có mặc định.
File mẫu có chú thích đầy đủ: [`examples/config_full.yaml`](../examples/config_full.yaml).

### 4.1 `project`

| Trường | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `name` | chuỗi | BB | Tên dự án, ghi vào `manifest.json` |
| `crs` | chuỗi | BB | CRS đích (hệ tọa độ **chiếu**, vd `EPSG:32648`). Mọi raster đã cắt được chiếu về CRS này. Trên giao diện web: chọn trong danh sách (gõ để tìm, vd `48N`, `VN-2000`) hoặc dán giá trị khác |
| `boundary` | đường dẫn | không | Ranh giới lưu vực (`.shp`, `.gpkg`, `.geojson`). Có thì `dem/landuse/soil` tự được cắt |
| `output_dir` | đường dẫn | `./output` | Thư mục ghi toàn bộ kết quả |
| `targets` | danh sách | `["swatplus"]` | `swatplus`, `swat` hoặc cả hai: quyết định định dạng weather |

Lưu ý: file `boundary` **phải có CRS** (shapefile cần `.prj`; GeoJSON cần khai báo CRS). Công cụ tự
chiếu ranh giới về CRS của từng raster nên ranh giới và raster được phép khác CRS nhau.

### 4.2 `dem`

| Trường | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `path` | đường dẫn | BB | Raster DEM gốc (có thể rất lớn) |
| `output_name` | chuỗi | `dem_projected.tif` | Tên file đã cắt, ghi vào `<output_dir>/spatial/` |
| `clip` | true/false | `true` | Cắt theo ranh giới; `false` thì quét cả raster, không ghi raster mới |
| `resampling` | `nearest`/`bilinear`/`cubic` | `bilinear` | Cách lấy mẫu lại khi phải chiếu về `project.crs` |
| `resolution` | số > 0 | không | Kích thước ô đầu ra (theo đơn vị của `project.crs`, mét với UTM) |

```yaml
dem:
  path: D:/DATA/dem_asia_utm48.tif
  output_name: "dem_chu.tif"
  resampling: bilinear
  resolution: 30
```

### 4.3 `landuse`

| Trường | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `raster` | đường dẫn | BB | Raster phân loại sử dụng đất |
| `lookup` | đường dẫn | BB | CSV bảng tra mã raster sang mã SWAT |
| `source_code_col` | chuỗi | `code` | Cột mã trong raster |
| `swat_code_col` | chuỗi | `swat_code` | Cột mã SWAT (`FRST`, `AGRL`, ...) |
| `swat_name_col` | chuỗi | `swat_name` | Cột tên lớp |
| `output_name` | chuỗi | `landuse_clip.tif` | Tên raster đã cắt, ghi vào `<output_dir>/landuse/` |
| `clip` | true/false | `true` | Cắt và chỉ giữ các lớp có trong lưu vực |
| `output_lookup` | true/false | `true` | Ghi bảng VLOOKUP `landuse_vlookup.csv` (`LANDUSE_ID`, `SWAT_CODE`), xem 5.2 |
| `resolution` | số > 0 | không | Kích thước ô đầu ra; luôn lấy mẫu `nearest` để giữ nguyên mã lớp |

Ví dụ bảng tra cho raster ESA WorldCover (Zanaga và cs., 2022); tên cột đặt tùy ý rồi khai báo bằng `*_col`:

```csv
LANDUSE_ID,SWAT_CODE
10,FRST
40,AGRL
50,URBN
80,WATR
```

```yaml
landuse:
  raster: D:/DATA/vietnam_worldcover_2021.tif
  lookup: D:/DATA/esa2021_landuse.csv
  source_code_col: "LANDUSE_ID"
  swat_code_col: "SWAT_CODE"
  swat_name_col: "SWAT_CODE"
```

### 4.4 `soil`

| Trường | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `raster` | đường dẫn | BB | Raster mã đất (vd HWSD `hdr.adf`) |
| `table` | đường dẫn | BB | Bảng thông số đất dạng `usersoil` (CSV hoặc SQLite) |
| `soil_key_col` | chuỗi | `soil_id` | Cột khoá của bảng, khớp với mã trong raster (vd `SOIL_ID`) |
| `output_usersoil` | true/false | `true` | Ghi `usersoil.csv` |
| `usersoil_format` | `swat` / `raw` | `swat` | `swat`: `usersoil.csv` đúng bố cục 152 cột của SWAT+ Editor (xem 5.2c); `raw`: ghi nguyên bảng đầu vào |
| `output_name` | chuỗi | `soil_clip.tif` | Tên raster đã cắt, ghi vào `<output_dir>/soil/` |
| `clip` | true/false | `true` | Cắt và chỉ giữ các loại đất có trong lưu vực |
| `output_lookup` | true/false | `true` | Ghi bảng VLOOKUP `soil_vlookup.csv` (`SOIL_ID`, `SNAM`), xem 5.2; cần cột `SNAM` trong bảng đất |
| `resolution` | số > 0 | không | Kích thước ô đầu ra; luôn lấy mẫu `nearest` |

Cột bắt buộc của bảng đất: `HYDGRP` (nhóm thủy văn A/B/C/D hoặc A/D, B/D, C/D), `SOL_ZMX`, `NLAYERS`.
Cột khuyến nghị cho lớp 1: `SOL_Z1`, `SOL_BD1`, `SOL_AWC1`, `SOL_K1`, `SOL_CBN1` (xem Arnold và cs., 2012).

Mã `0` trong raster HWSD thường là **nước/không có dữ liệu**. Nếu raster khai báo NoData khác 0
(HWSD dùng -32768) thì mã 0 vẫn được tính như một loại đất, nên bảng đất cần có một hàng
`SOIL_ID = 0` (loại "WATER") để không bị cảnh báo `soil_unmatched_codes`.

### 4.5 `weather`

| Trường | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `stations` | đường dẫn | (xem dưới) | CSV trạm: `id, name, lat, lon, elev`. Tên cột không phân biệt hoa/thường; nhận cả kiểu master file SWAT `ID,NAME,LAT,LONG,ELEV` (hoặc `ELEVATION`, `LATITUDE`, `LONGITUDE`); đuôi `.txt` cũng được nếu nội dung là CSV |
| `data_dir` | đường dẫn | (xem dưới) | Thư mục chứa mỗi trạm một CSV |
| `file_pattern` | chuỗi | `{id}.csv` | Quy ước đặt tên file; dùng `{name}.csv` để khớp theo tên trạm |
| `format` | `csv` | `csv` | Định dạng đầu vào (hiện chỉ có CSV) |
| `variables` | danh sách | `[precip, tmax, tmin]` | Gồm `precip, tmax, tmin, wind, solar, humidity` |
| `start`, `end` | ngày ISO | BB | Khoảng thời gian; `end >= start` |
| `units.precip` | chuỗi | `mm` | Đơn vị mưa |
| `units.temperature` | chuỗi | `degC` | Đơn vị nhiệt độ |
| `missing_policy` | `fail`/`warn` | `fail` | Chỉ tác động `build`: ngày thiếu là lỗi (`fail`: không ghi weather) hay cảnh báo (`warn`: vẫn ghi, ngày thiếu thành `-99`). **Không tự điền** ngày thiếu, xem [`WEATHER_MISSING_FILL_VI.md`](WEATHER_MISSING_FILL_VI.md) |
| `precip`, `temp` | khối con | không | Nguồn riêng (stations + data_dir + file_pattern) cho mưa / nhiệt độ |
| `fill` | khối con | không | Cấu hình điền ngày thiếu. Lệnh `swatprep fill weather` luôn đọc khối này; `build` chỉ dùng khi `fill.run_in_build: true` |

Phải có nguồn cho từng nhóm biến: hoặc đặt `stations` + `data_dir` chung, hoặc đặt `precip`
(cho mưa) và `temp` (cho nhiệt độ). Nếu không, đọc YAML sẽ báo lỗi ngay.

CSV của mỗi trạm có cột `date` và các biến cần dùng:

```csv
date,precip,tmax,tmin
2000-01-01,5.2,32.1,22.3
2000-01-02,0.0,33.5,23.1
```

Mưa và nhiệt độ từ hai mạng lưới trạm khác nhau:

```yaml
weather:
  precip:
    stations: ./data/pcp_stations.csv
    data_dir: ./data/pcp
  temp:
    stations: ./data/tmp_stations.csv
    data_dir: ./data/tmp
  variables: [precip, tmax, tmin]
  start: "1981-01-01"
  end: "2014-12-31"
```

Định dạng đầu ra theo `project.targets`: `swatplus` ghi `.pcp/.tmp` kèm `*.cli`; `swat` ghi
`pcp_<tên>.txt/tmp_<tên>.txt` kèm `master_*.txt`; chọn cả hai thì mỗi loại vào thư mục con riêng
`weather/swatplus/` và `weather/swat/`. Chi tiết: [`WEATHER_OUTPUT.md`](WEATHER_OUTPUT.md).

Với `swat`, cột `ID` của `master_pcp.txt` và `master_tmp.txt` là **số thứ tự (STT)** 1, 2, 3, ... theo thứ tự các trạm
trong `stations.csv`, không phải mã trạm gốc (vd `ST009`). Hai file được đánh số độc lập, nên khi mưa và nhiệt độ
lấy từ hai mạng lưới khác nhau, mỗi file đều bắt đầu từ 1. Cột `NAME` giữ tiền tố `pcp_` / `tmp_` cùng tên trạm.

### 4.6 `weather.fill` (điền ngày thiếu)

| Trường | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `type` | `csv`/`netcdf` | `csv` | Loại nguồn dùng để điền; khối cùng tên phải có mặt |
| `output_dir` | đường dẫn | không | Nơi ghi CSV đã điền và `fill_report.csv` |
| `run_in_build` | true/false | `false` | `true`: `swatprep build` tự điền trước (dữ liệu gốc là `weather.stations`/`data_dir`), ghi CSV đã điền vào `output_dir` rồi dựng weather từ đó: một file, một lệnh. Cần `output_dir` khác `data_dir` |
| `min_overlap_days` | số nguyên >= 0 | `10` | Ngưỡng cảnh báo: số ngày trùng giữa số liệu đo và nguồn điền ít hơn giá trị này thì báo `low_confidence`. **Không chặn việc điền** |
| `netcdf.path` | đường dẫn | BB | File NetCDF lưới **theo ngày**, mưa mm, nhiệt độ °C |
| `netcdf.var_map` | từ điển | BB | Tên biến swatprep -> tên biến trong file, vd `{precip: pr, tmax: tasmax, tmin: tasmin}` |
| `netcdf.lat_name`, `lon_name`, `time_name` | chuỗi | `auto` | Chỉ đặt khi tên trục không thuộc nhóm thông dụng |
| `netcdf.search_radius` | 0-5 | `1` | Ô gần nhất không có dữ liệu (vd ô biển) thì tìm ô có dữ liệu trong bán kính này |
| `csv.stations`, `data_dir`, `file_pattern` | | | Khi nguồn điền là CSV theo trạm (cùng mã trạm) |

### 4.7 `streamflow`

| Trường | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `path` | đường dẫn | BB | `format: long`: CSV dạng dài (mỗi dòng một ngày và một trạm). `format: per_station`: một file trạm hoặc một thư mục chứa nhiều file |
| `format` | `long`/`per_station` | `long` | `per_station`: mỗi file là MỘT trạm, gồm cột ngày và một cột lưu lượng (vd `date,discharge`); mã trạm lấy từ **tên file** (`Q_HT_0006.csv` -> `Q_HT_0006`) |
| `glob` | chuỗi | `Q_*.csv` | Chỉ dùng khi `path` là thư mục và `format: per_station`: mẫu tên file cần đọc |
| `stations` | danh sách | tất cả | Chỉ giữ các trạm này (mã trạm; với `per_station` là tên file không đuôi). Mã không tồn tại thì báo lỗi, nêu rõ mã nào |
| `date_col` | chuỗi | `date` | Cột ngày |
| `station_id_col` | chuỗi | `station_id` | Cột mã trạm (chỉ dạng `long`) |
| `value_col` | chuỗi | `flow` | Cột lưu lượng. Với `per_station`, tên cột trong file; tự nhận nếu file chỉ có một cột ngoài ngày (vd `discharge`) |
| `units` | `m3s`/`mm` | `m3s` | Đơn vị lưu lượng |

Ví dụ file một trạm (`Q_HT_0006.csv`) và cấu hình tương ứng:

```csv
"date","discharge"
1958-01-01,3
1958-01-02,3.88
```

```yaml
streamflow:
  path: D:/DATA_STORAGE/_data/_DataReview/dailyStreamflow_end2019/Q_HT_0006.csv   # hoặc cả thư mục (dùng glob)
  format: per_station
  units: m3s
```

Nhiều trạm cho một lưu vực: trỏ `path` vào **thư mục** chứa các file trạm; chọn trạm bằng `stations` (hoặc `glob`):

```yaml
streamflow:
  path: D:/DATA_STORAGE/_data/_DataReview/dailyStreamflow_end2019   # thư mục
  format: per_station
  stations: [Q_HT_0006, Q_HT_0007, Q_HT_0009]    # bỏ dòng này để lấy mọi file khớp glob (Q_*.csv)
```

Kết quả ghi vào `output/observed/`: `streamflow_<trạm>.csv` (cột `date`, `flow_m3s`) và `streamflow_meta.csv`.
Lỗi `Streamflow CSV missing columns: flow, station_id` nghĩa là file không phải dạng dài; hãy đặt `format: per_station`.

### 4.8 `clip` (tuỳ chọn, ít cần)

Danh sách raster cần cắt riêng, mỗi mục chỉ cần `src` và `dst`. Cần `project.boundary`.

| Trường | Mặc định | Ý nghĩa |
|---|---|---|
| `src`, `dst` | BB | Raster nguồn và nơi ghi |
| `mask` | `false` | `true`: ô ngoài đa giác ranh giới thành NoData (cần raster có NoData) |
| `resampling` | `nearest` | `nearest`/`bilinear`/`cubic` |
| `resolution` | không | Kích thước ô đầu ra, theo đơn vị của `project.crs` |

```yaml
project:
  name: "Chu_basin"
  crs: "EPSG:32648"
  boundary: ./data/boundary.geojson
clip:
  - src: D:/DATA/dem_asia.tif
    dst: ./data/spatial/dem_chu.tif
    resampling: bilinear
  - src: D:/DATA/landuse.tif
    dst: ./data/spatial/landuse_chu.tif
    mask: true
```

Với `dem`, `landuse`, `soil` **không cần** mục `clip:`: `build` tự cắt và chiếu về `project.crs`.

---

## 5. Các chức năng chính

### 5.1 Cắt raster và chiếu về CRS của dự án

**Mục tiêu:** đưa các raster khu vực rộng (cả châu Á, cả nước) về đúng phạm vi lưu vực, cùng một hệ tọa độ.

**Cách hoạt động (chỉ khi `project.boundary` được đặt):**

1. Ranh giới được chiếu về CRS của raster nguồn để xác định cửa sổ cần đọc (hình chữ nhật bao lưu vực).
2. Nếu CRS của raster khác `project.crs`, raster được chiếu lại **chỉ trong cửa sổ đó**, nên bộ nhớ và thời
   gian không phụ thuộc kích thước raster gốc (thử trên raster 60.000 x 60.000 ô: khoảng 0,4 giây).
3. Kết quả ghi thành GeoTIFF có nén vào `<output_dir>/spatial|landuse|soil/` (cùng thư mục với bảng).
4. Các phép kiểm tra và thống kê chỉ đọc cửa sổ lưu vực.

**Cách lấy mẫu lại:** DEM dùng `bilinear` (đại lượng liên tục); landuse và soil luôn dùng `nearest` để không
tạo ra mã lớp giả (mã phân loại là số định danh, không thể nội suy).

**Kích thước ô:** không đặt `resolution` thì GDAL tự chọn kích thước gần với raster gốc. Raster gốc ở độ
(0,0001° ≈ 11 m) sẽ cho ô khoảng 10,7 m. Muốn ô tròn (10 m, 30 m) hãy đặt `resolution`.

**Khi nào cắt lại:** nếu file đã cắt mới hơn raster nguồn và mọi file của ranh giới, **đồng thời** đã ở đúng
`project.crs` và đúng `resolution`, nó được giữ nguyên (QA `clip_skipped`). Ngược lại (đổi CRS, đổi
`resolution`, nguồn hoặc ranh giới được cập nhật) nó được làm lại. Xoá file đã cắt để ép làm lại.

**Tắt cắt:** `clip: false` ở từng mục (quét cả raster, không ghi raster mới, bảng giữ nguyên đầy đủ).

**Ví dụ cho cùng một lưu vực:**

```yaml
project:
  name: "Chu_basin"
  crs: "EPSG:32648"
  boundary: D:/DATA/boundary/ht_chu.shp
  output_dir: ./output
dem:
  path: D:/DATA/dem_asia.tif
  resolution: 30
landuse:
  raster: D:/DATA/vietnam_worldcover_2021.tif   # EPSG:4326 -> được chiếu về EPSG:32648
  lookup: D:/DATA/esa2021_landuse.csv
  source_code_col: LANDUSE_ID
  swat_code_col: SWAT_CODE
  swat_name_col: SWAT_CODE
  resolution: 10
soil:
  raster: D:/DATA/hwsd/hdr.adf
  table: D:/DATA/usersoil.csv
  soil_key_col: SOIL_ID
```

Kết quả kiểm tra: mở `output/landuse/landuse_clip.tif` trong QGIS hoặc chạy `swatprep inspect raster` và xem
dòng `CRS`; báo cáo QA có dòng `clip_written:...` ghi rõ CRS đích.

### 5.2 Lọc bảng theo lưu vực

Khi raster đã được cắt, bảng tra sử dụng đất và bảng đất chỉ giữ các mã **có trong lưu vực** (QA
`landuse_table_filtered`, `soil_table_filtered`). Việc đối chiếu mã raster với bảng được làm trên bảng đầy đủ
trước khi lọc, nên mã nào thiếu trong bảng vẫn được báo.

### 5.2b Bảng VLOOKUP cho QSWAT / QSWAT+ và Excel

Ngoài bảng đã lọc, `build` ghi thêm hai bảng **tra cứu hai cột** (giá trị raster -> mã/tên), đúng dạng QSWAT và
QSWAT+ yêu cầu khi nạp raster sử dụng đất và thổ nhưỡng (Dile và cs., 2016):

| File | Cột | Nội dung | Dùng làm |
|---|---|---|---|
| `landuse/landuse_vlookup.csv` | `LANDUSE_ID`, `SWAT_CODE` | Giá trị raster sử dụng đất -> mã lớp SWAT (`FRST`, `AGRL`, ...) | Bảng tra sử dụng đất khi nạp raster vào QSWAT/QSWAT+ |
| `soil/soil_vlookup.csv` | `SOIL_ID`, `SNAM` | Giá trị raster đất -> tên đất `SNAM` trong `usersoil.csv` | Bảng tra thổ nhưỡng khi nạp raster vào QSWAT/QSWAT+ |

`landuse_vlookup.csv`:

```csv
LANDUSE_ID,SWAT_CODE
10,FRST
40,AGRL
80,WATR
```

`soil_vlookup.csv`:

```csv
SOIL_ID,SNAM
4265,Ag17-1-2a-4265
4267,Ao107-2bc-4267
11375,Bd15-2a-4630
```

Quy tắc tạo bảng:

- Mỗi giá trị chỉ một hàng, **sắp tăng dần**; tiêu đề cột cố định như trên dù bảng gốc đặt tên cột khác
  (`source_code_col`, `swat_code_col`, `soil_key_col`).
- Có `project.boundary` thì bảng chỉ gồm các giá trị **có trong lưu vực**, giống `landuse_lookup.csv` và `usersoil.csv`.
- Mã bị lặp trong bảng gốc: giữ hàng **đầu tiên**. Với đất, nếu một `SOIL_ID` có nhiều hàng khác tên thì báo
  `soil_vlookup_duplicates` (cảnh báo); `usersoil.csv` vẫn liệt kê đủ mọi loại đất khác nhau.
- Giá trị có trong raster nhưng **không có trong bảng gốc** (ví dụ mã đất 4324) không được thêm vào, vì không
  thể tự đặt tên; kiểm tra `*_unmatched_codes` đã báo các mã này. Hãy bổ sung vào bảng gốc rồi chạy lại.
- Thiếu cột `SNAM` trong bảng đất: với `usersoil_format: swat` `SNAM` được lấy bằng mã đất (cảnh báo
  `usersoil_snam_generated`); với `raw` không ghi `soil_vlookup.csv`, báo `soil_vlookup_skipped`.
- Tắt bằng `output_lookup: false` ở mục `landuse` hoặc `soil`.

Dùng trong Excel: mở `landuse_vlookup.csv`, rồi tra mã của một ô raster bằng
`=VLOOKUP(40, landuse_vlookup!A:B, 2, FALSE)` (kết quả `AGRL`).

### 5.2c Bố cục `usersoil.csv` theo SWAT+

Mặc định (`usersoil_format: swat`) `usersoil.csv` có **đúng 152 cột, đúng thứ tự** như tệp mẫu của SWAT+ Editor
(`examples/example_usersoil_swatplus.csv`):

```text
OBJECTID,MUID,SEQN,SNAM,S5ID,CMPPCT,NLAYERS,HYDGRP,SOL_ZMX,ANION_EXCL,SOL_CRK,TEXTURE,
SOL_Z1,SOL_BD1,SOL_AWC1,SOL_K1,SOL_CBN1,CLAY1,SILT1,SAND1,ROCK1,SOL_ALB1,USLE_K1,SOL_EC1,   (lặp cho lớp 2..10)
SOL_CAL1..SOL_CAL10,  SOL_PH1..SOL_PH10
```

Cách chuyển bảng của anh/chị sang bố cục này:

| Việc | Quy tắc |
|---|---|
| Cột khoá (`soil_key_col`, vd `SOIL_ID`) | **Không ghi** vào `usersoil.csv`; mã raster -> `SNAM` nằm ở `soil_vlookup.csv`. Tên cột không thuộc bố cục cũng bị bỏ (QA liệt kê) |
| Cột thiếu trong bảng gốc | Điền `0`; riêng `ANION_EXCL` và `SOL_CRK` điền `0.5` (mặc định của SWAT); `TEXTURE` để trống |
| Không có cột `SNAM` | `SNAM` lấy bằng mã đất (cảnh báo `usersoil_snam_generated`); `soil_vlookup.csv` dùng đúng tên này |
| Hàng trùng hệt (cùng `SNAM`, cùng dữ liệu) | Gộp thành một hàng (`usersoil_duplicates_merged`) |
| Cùng `SNAM` nhưng khác dữ liệu | Đổi tên `Tên_2`, `Tên_3`, ... để `SNAM` duy nhất (cảnh báo `usersoil_snam_renamed`) |
| `OBJECTID` thiếu hoặc trùng | Đánh lại 1..N |
| Số nguyên | Ghi `1000` thay vì `1000.0` |

`soil_vlookup.csv` luôn dùng đúng `SNAM` đã ghi trong `usersoil.csv`, kể cả tên đã đổi `_2`. Muốn giữ nguyên bảng
đầu vào, đặt `usersoil_format: raw`.

### 5.3 Đối chiếu mã raster với bảng

| Kiểm tra | Mức | Ý nghĩa và cách xử lý |
|---|---|---|
| `landuse_unmatched_codes` | fail | Mã raster không có trong bảng tra: thêm hàng vào `lookup` |
| `soil_unmatched_codes` | fail | Mã raster không có trong cột `soil_key_col` của bảng đất: thêm hàng, hoặc gán đất tương đương |
| `landuse_lookup_duplicates` | warn | Mã nguồn bị lặp trong bảng tra |
| `soil_invalid_hydgrp` | warn | `HYDGRP` ngoài A, B, C, D, A/D, B/D, C/D |
| `soil_missing_required_cols` | fail | Thiếu `HYDGRP`, `SOL_ZMX` hoặc `NLAYERS` |

### 5.4 Điền ngày thiếu cho số liệu khí tượng (`fill`)

**Mục tiêu:** điền các ngày thiếu của trạm đo bằng nguồn lưới (vd NetCDF tái phân tích/quan trắc lưới).

> Mô tả đầy đủ (định nghĩa ngày thiếu, `missing_policy`, ví dụ tính tay, file kết quả, hỏi đáp) nằm ở
> [`WEATHER_MISSING_FILL_VI.md`](WEATHER_MISSING_FILL_VI.md). Ba điểm cần nhớ: (1) `build` **không** tự điền;
> (2) ngày đã có số liệu đo không bao giờ bị sửa; (3) ô CSV để trống hoặc ngày vắng hàng mới là "thiếu",
> còn giá trị `-99` được coi là số thật.

**Phương pháp:** hiệu chỉnh sai lệch tuyến tính (linear scaling) theo từng trạm và từng biến, tính trên các
ngày hai nguồn cùng có số liệu (Teutschbein và Seibert, 2012): mưa nhân với hệ số
`trung bình(đo) / trung bình(lưới)` (kết quả không âm); nhiệt độ cộng độ lệch
`trung bình(đo) - trung bình(lưới)`. Ngày đã có số liệu đo **không bao giờ bị sửa**.

**Chọn ô lưới:** ô gần nhất với trạm; trạm nằm đúng giữa hai ô lấy ô chỉ số thấp hơn. Nếu ô đó không có dữ
liệu (vd ô biển), lấy ô gần nhất có dữ liệu trong `search_radius` và báo `neighbor_cell`.

**Cách chạy:** có hai cách. (A) hai file: chạy `swatprep fill weather --config config.fill.yaml`, rồi
`swatprep build config.yaml` với `weather.data_dir` trỏ vào thư mục đã điền. (B) một file: đặt
`weather.fill.run_in_build: true` và chỉ chạy `swatprep build config.yaml` (xem mục 8.2 trong
[`WEATHER_MISSING_FILL_VI.md`](WEATHER_MISSING_FILL_VI.md)). Cách A:

```bash
swatprep fill weather --config config.fill.yaml
```

Đầu ra: `<fill.output_dir>/<id>.csv` mỗi trạm, `stations.csv` và `fill_report.csv` (số ngày thiếu, số ngày đã
điền, số ngày trùng, loại và giá trị hiệu chỉnh, trạng thái). Sau đó trỏ `weather.stations` và
`weather.data_dir` của `config.yaml` vào thư mục này. Trạng thái `warn`/`low_confidence` nghĩa là số ngày trùng
ít hơn `min_overlap_days`: nên xem lại trước khi dùng.

Ví dụ `config.fill.yaml`:

```yaml
project:
  name: "Chu basin"
  crs: "EPSG:32648"
weather:
  stations: ./data/obs/stations.csv
  data_dir: ./data/obs
  variables: [precip, tmax, tmin]
  start: "1981-01-01"
  end: "2014-12-31"
  fill:
    type: netcdf
    output_dir: ./data/filled
    min_overlap_days: 365
    netcdf:
      path: D:/DATA/OBS.Vietnam.1980-2014.nc
      var_map: { precip: pr, tmax: tasmax, tmin: tasmin }
```

### 5.5 Kiểm tra chất lượng (QA)

Mỗi bước tạo ra các kiểm tra với mức **pass**, **warn** hoặc **fail**:

- `pass`: hợp lệ.
- `warn`: vẫn chạy được nhưng nên xem lại.
- `fail`: lỗi phải sửa. Mục có lỗi nặng **không được ghi kết quả** (vd `weather_skipped`).

Một số kiểm tra thường gặp: `file_exists:*` (khi `validate`), `dem_crs_reprojected` (DEM đã được chiếu về CRS dự án),
`dem_nodata_missing`, `landuse_cross_check`, `soil_cross_check`, `*_boundary_window` (đã đọc đúng cửa sổ lưu vực),
`*_boundary_ignored` (không dùng được ranh giới, quét cả raster), `missing:<trạm>:<biến>` (thiếu số liệu),
`streamflow_negative`, `clip_written`, `clip_skipped`, `clip_failed`. Toàn bộ nằm trong `qa_report.md`.

---

## 6. Ví dụ hoàn chỉnh: lưu vực sông Chu

Quy trình hai bước, hai file.

**Bước 1. `config.fill.yaml`** (điền ngày thiếu, xem mục 5.4) rồi chạy:

```bash
swatprep fill weather --config config.fill.yaml
```

**Bước 2. `config.yaml`** (kiểm tra và dựng kết quả):

```yaml
project:
  name: "Chu basin"
  crs: "EPSG:32648"
  output_dir: ./output
  targets: ["swat"]
  boundary: D:/DATA_STORAGE/_data/1_catchmentFiles/boundary/ht_chu.shp

weather:
  stations: ./data/filled/stations.csv
  data_dir: ./data/filled
  variables: [precip, tmax, tmin]
  start: "1981-01-01"
  end: "2014-12-31"
  missing_policy: "warn"

dem:
  path: D:/DATA_STORAGE/_data/1_DEM/HydroSheds/as_dem_3s_UTM48N.tif
  output_name: "dem_clip.tif"
  resolution: 30

landuse:
  raster: D:/DATA_STORAGE/_data/2_LandUse/esa-worldcover/vietnam_worldcover_2021.tif
  lookup: D:/DATA_STORAGE/_data/2_LandUse/esa2021_landuse.csv
  source_code_col: "LANDUSE_ID"
  swat_code_col: "SWAT_CODE"
  swat_name_col: "SWAT_CODE"
  output_name: "landuse_clip.tif"
  resolution: 10

soil:
  raster: D:/DATA_STORAGE/_data/3_Soil/hwsd/hdr.adf
  table: D:/DATA_STORAGE/_data/3_Soil/usersoil.csv
  soil_key_col: "SOIL_ID"
  output_name: "soil_clip.tif"
```

Chạy:

```bash
swatprep validate config.yaml
swatprep build config.yaml
```

---

## 7. Đọc kết quả

```text
output/
  manifest.json            # danh sách file, miền đã chạy, thời gian, tóm tắt QA
  qa_report.md             # báo cáo QA đầy đủ (pass/warn/fail)
  spatial/   dem_clip.tif   dem_info.json
  landuse/   landuse_clip.tif   landuse_lookup.csv   landuse_vlookup.csv   landuse_raster_codes.csv
  soil/      soil_clip.tif   usersoil.csv   soil_vlookup.csv   soil_raster_codes.csv
  weather/   <trạm>.pcp  <trạm>.tmp  *.cli  wgn.csv  stations.csv      # theo project.targets
             swatplus_wgn_stations.csv  swatplus_wgn_monthly.csv  swatplus_wgn_onefile.csv   # nhập WGN vào SWAT+ Editor
  observed/  streamflow_<trạm>.csv   streamflow_meta.csv
```

**Nhập dữ liệu sinh thời tiết (WGN) vào SWAT+ Editor.** Trong Editor chọn *Weather generator > Import* rồi dùng
một trong hai cách (cột đúng thứ tự mẫu của Editor):

| Cách chọn trong Editor | Tệp dùng | Cột |
|---|---|---|
| Two files (hai tệp) | `swatplus_wgn_stations.csv` + `swatplus_wgn_monthly.csv` | trạm: `id,name,lat,lon,elev,rain_yrs`; tháng: `id,wgn_id,month,tmp_max_ave,...,wnd_ave` |
| One file (một tệp) | `swatplus_wgn_onefile.csv` | `name,lat,lon,elev,rain_yrs` rồi 14 biến cho từng tháng 1..12 (173 cột, đọc theo vị trí) |

Không dùng `wgn.csv` để nhập: đó là bảng thống kê nội bộ (`station_id,month,TMPMX,...`), thiếu `rain_yrs`; Editor
sẽ báo `NOT NULL constraint failed: weather_wgn_cli.rain_yrs`. `rain_yrs` ghi số năm của chuỗi số liệu.
Ba biến `slr_ave`, `dew_ave`, `wnd_ave` (và `pcp_hhr`) là `-99` khi không có số liệu; hãy thay bằng giá trị thật trong Editor trước khi chạy mô hình.

Cách đọc nhanh: mở `qa_report.md`, tìm các dòng `fail` trước, sau đó `warn`. Mỗi kiểm tra có tên (vd
`soil_unmatched_codes`) khớp với bảng ở mục 5.3 và 10.

### 7.1 Xem dữ liệu trên giao diện web (Explore)

Trên trang **Project**, chọn **Explore** (cạnh **Configure**) để xem biểu đồ của dữ liệu mà config
**đã lưu** trỏ tới; nếu form còn thay đổi chưa lưu, app nhắc lưu trước. **Reload data** đọc lại dữ liệu
khi file đầu vào vừa được sửa bên ngoài app.

**Weather** (cần mục `weather`):

| Thành phần | Ý nghĩa |
|---|---|
| Variable / Data | Chọn biến; **Filled** chỉ có khi `weather.fill.output_dir` đã có số liệu đã điền |
| Completeness | Ô trạm × tháng: xám nhạt là đủ ngày, cam → đỏ theo % ngày thiếu; ở Filled là phần **còn** thiếu sau khi điền |
| Station | Chuỗi ngày của một trạm: xám là đo thực, chấm cam là giá trị đã điền, vạch đỏ là ngày còn thiếu; kèm dòng tóm tắt từ `fill_report.csv` |
| Khí hậu tháng của mưa | Cột đôi Observed / Filled cho mỗi tháng; tháng chỉ được tính khi không thiếu ngày nào, ngày đã điền được tính nếu ≤ 10 ngày/tháng và < 5 ngày liên tiếp |

Dùng heatmap để biết trạm nào, giai đoạn nào thiếu nhiều trước khi chọn trạm cho mô hình; so cột Observed
và Filled để thấy bước điền làm thay đổi khí hậu tháng đến mức nào.

**Streamflow** (cần mục `streamflow`):

| Thành phần | Ý nghĩa |
|---|---|
| Bảng tổng quan | Mỗi trạm: giai đoạn, % ngày thiếu, min/trung bình/max, Q5/Q50/Q95 |
| Hydrograph | Lưu lượng theo ngày; vạch đỏ là ngày thiếu; **Log scale** để xem dòng kiệt; kéo để phóng to |
| Đường duy trì lưu lượng | % thời gian lưu lượng bị vượt (vị trí vẽ Weibull m/(n+1)); Q5 là dòng lũ, Q95 là dòng kiệt |
| Khí hậu tháng | Trung bình của các tháng hợp lệ; nhãn *năm hợp lệ/số năm* |

Tháng hợp lệ theo WMO-No. 1203 (2017): với `units: m3s` (trung bình tháng), thiếu tối đa 10 ngày và
không quá 4 ngày liên tiếp; với `units: mm` (tổng tháng), không thiếu ngày nào. Tháng có số năm hợp lệ
dưới 80% được vẽ nhạt và có cảnh báo: giá trị trung bình của tháng đó chưa đáng tin.

**Map** (cần chạy **Build** trước): xem các raster trong `output/` (DEM, land use, soil, các mục `clip`)
trên bản đồ, kèm đường ranh giới `project.boundary`.

| Thành phần | Ý nghĩa |
|---|---|
| Layer / Opacity | Chọn lớp; giảm độ đục để nhìn nền bản đồ bên dưới |
| Basemap | Light / Dark: nền CARTO–OpenStreetMap (cần internet); None: không có nền, làm việc offline |
| Legend | DEM: thang màu theo độ cao; land use / soil: mã, tên SWAT (từ `*_vlookup.csv`), % diện tích tính trên độ phân giải gốc |
| Layer | CRS, kích thước pixel, số hàng × cột, % NoData |

Kiểm tra nhanh: lưu vực phải nằm đúng chỗ trên nền bản đồ (nằm giữa biển hay lệch khỏi sông là dấu hiệu
sai CRS), raster phải lấp kín ranh giới, và các lớp có % diện tích hợp lý.

---

## 8. Lệnh dòng lệnh (CLI)

| Lệnh | Chức năng |
|---|---|
| `swatprep validate CONFIG` | Kiểm tra YAML và file đầu vào tồn tại, không ghi gì |
| `swatprep build CONFIG [--only MỤC]` | Chạy tất cả hoặc một mục: `clip, dem, landuse, soil, weather, streamflow` |
| `swatprep fill weather --config CONFIG` | Điền ngày thiếu (xem 5.4); có thể dùng cờ thay cho YAML |
| `swatprep clip RASTER BOUNDARY OUT [--mask] [--crs EPSG] [--resampling M] [--resolution R]` | Cắt (và tuỳ chọn chiếu) một raster, không cần YAML |
| `swatprep inspect raster PATH` / `inspect weather PATH` | Xem nhanh thông tin raster (CRS, kích thước, NoData) hoặc CSV khí tượng |
| `swatprep convert climate DATA_DIR OUT_DIR` | Gộp `R_*.day`, `Tx_*.day`, `Tm_*.day` thành CSV theo trạm |
| `swatprep convert streamflow SOURCE OUT [--format ...]` | Dòng chảy dạng rộng hoặc theo trạm -> dạng dài |
| `swatprep convert weather --pcp-master ... --target swat2012 --target swatplus OUT_DIR` | File trạm thô -> SWAT2012 và/hoặc SWAT+ |

Ví dụ cắt và chiếu một raster độc lập:

```bash
swatprep clip D:/DATA/lu.tif D:/DATA/ht_chu.shp lu_chu.tif --crs EPSG:32648 --resolution 10
swatprep clip D:/DATA/dem.tif D:/DATA/ht_chu.shp dem_chu.tif --crs EPSG:32648 --resampling bilinear
```

Các cờ `--fill-*` của `fill weather` (ghi đè giá trị trong YAML): `--fill-netcdf`, `--fill-var-map`,
`--fill-search-radius`, `--min-overlap-days`, `--variables`, `--start`, `--end`.

---

## 9. Python API

```python
from swatprep import SWATPrepProject

project = SWATPrepProject.from_config("config.yaml")
for c in project.validate():
    print(c.status, c.name, c.message)

result = project.build()                 # hoặc project.build(only="soil")
print(result.success, result.output_dir, result.manifest_path)
print([c for c in result.qa_checks if c.status == "fail"])
```

---

## 10. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| `Config schema error ... Input should be a valid date` | Ngày viết sai dạng | Dùng `"YYYY-MM-DD"` trong dấu nháy |
| `'clip' needs project.boundary to be set` | Có mục `clip:` nhưng chưa đặt ranh giới | Đặt `project.boundary` |
| `Precip variables configured but no source` | Có `precip` trong `variables` mà thiếu nguồn | Đặt `weather.stations/data_dir` hoặc `weather.precip` |
| `No valid station data files found` (build dừng ngay) | Không có file CSV nào khớp `file_pattern`. Thường do cột `id` của `stations.csv` là số thứ tự (1, 2, 3...) trong khi file đặt theo tên trạm (`CHILINH.csv`) | Thông báo lỗi nêu tên file đã tìm (vd `'1.csv'`). Đặt `weather.file_pattern: "{name}.csv"` để khớp theo cột `name`, hoặc đổi `id` thành tên file |
| Editor báo `NOT NULL constraint failed: weather_wgn_cli.rain_yrs` khi nhập WGN | Đã chọn `wgn.csv` (bảng nội bộ) thay vì tệp nhập của Editor | Dùng `swatplus_wgn_stations.csv` + `swatplus_wgn_monthly.csv` (hai tệp) hoặc `swatplus_wgn_onefile.csv` (một tệp), xem mục 7 |
| `file_exists:... File not found` | Sai đường dẫn hoặc sai thư mục gốc | Nhớ đường dẫn tương đối tính từ thư mục chứa YAML |
| `Boundary has no CRS` | Ranh giới thiếu `.prj` hoặc CRS | Gán CRS cho ranh giới (QGIS: Export với CRS) |
| `Boundary does not overlap the raster extent` | Ranh giới nằm ngoài raster, hoặc ranh giới gán sai CRS | Kiểm tra CRS của ranh giới và phạm vi raster |
| `Boundary cannot be converted to the raster CRS` | Tọa độ ranh giới không khớp CRS khai báo | Sửa khai báo CRS của ranh giới |
| `*_boundary_ignored` (warn) | Không dùng được ranh giới nên quét cả raster (chậm) | Xem lý do trong thông báo, sửa như hai dòng trên |
| `soil_unmatched_codes` | Mã raster không có trong cột `soil_key_col` của bảng đất | Thêm hàng; mã `0` thêm hàng `WATER`; hoặc chọn đất tương đương |
| `landuse_unmatched_codes` | Mã raster không có trong bảng tra | Thêm hàng vào `lookup` |
| Raster đã cắt vẫn ở CRS cũ | Bản cũ chưa được làm lại | Chạy lại `build` (tự cắt lại khi khác CRS) hoặc xoá file đã cắt |
| `clip_failed ... needs geopandas and rasterio` | Chưa cài thư viện GIS | `pip install -e .[geo]` |
| `weather_skipped` | Số liệu khí tượng có lỗi nặng | Xem các dòng `fail` ngay trước đó; `missing_policy: warn` để chỉ cảnh báo khi thiếu số liệu |
| `fill`: `neighbor_cell` / `no_valid_cell` / `outside_grid` | Ô lưới của trạm không có dữ liệu hoặc ngoài lưới | Tăng `search_radius` (tối đa 5), hoặc kiểm tra tọa độ trạm |
| Build chậm | Ranh giới không áp dụng được nên quét cả raster | Kiểm tra QA `*_boundary_window`; đặt `project.boundary` |

---

## 11. Tài liệu tham khảo

- Arnold, J.G., Kiniry, J.R., Srinivasan, R., Williams, J.R., Haney, E.B., Neitsch, S.L. (2012). *Soil and Water
  Assessment Tool Input/Output Documentation, Version 2012*. Texas Water Resources Institute, TR-439.
- Bieger, K., Arnold, J.G., Rathjens, H., White, M.J., Bosch, D.D., Allen, P.M., Volk, M., Srinivasan, R. (2017).
  Introduction to SWAT+, a completely restructured version of the Soil and Water Assessment Tool.
  *Journal of the American Water Resources Association*, 53(1), 115-130.
- FAO, IIASA, ISRIC, ISS-CAS, JRC (2012). *Harmonized World Soil Database (version 1.2)*. FAO, Rome and IIASA, Laxenburg.
- Teutschbein, C., Seibert, J. (2012). Bias correction of regional climate model simulations for hydrological climate-change
  impact studies: Review and evaluation of different methods. *Journal of Hydrology*, 456-457, 12-29.
- Dile, Y.T., Daggupati, P., George, C., Srinivasan, R., Arnold, J. (2016). Introducing a new open source GIS user interface for the SWAT model. *Environmental Modelling & Software*, 85, 129-138.
- Zanaga, D. và cs. (2022). *ESA WorldCover 10 m 2021 v200*. Zenodo, doi:10.5281/zenodo.7254221.
