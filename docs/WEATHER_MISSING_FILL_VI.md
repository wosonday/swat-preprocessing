# Số liệu khí tượng thiếu: `missing_policy` và `fill`

Tài liệu này giải thích chính xác thế nào là "ngày thiếu", `missing_policy` làm gì, lệnh
`swatprep fill weather` làm gì, và hai thứ này **khác nhau** ra sao. Mọi mô tả dưới đây được kiểm chứng
bằng `tests/test_weather_missing_semantics.py` (ví dụ số ở mục 5 chính là dữ liệu của bài kiểm thử).

## Mục lục

1. [Tóm tắt một bảng](#1-tóm-tắt-một-bảng)
2. [Thế nào là "ngày thiếu"](#2-thế-nào-là-ngày-thiếu)
3. [`missing_policy`: thiếu thì dừng hay chỉ cảnh báo](#3-missing_policy-thiếu-thì-dừng-hay-chỉ-cảnh-báo)
4. [`fill`: điền ngày thiếu](#4-fill-điền-ngày-thiếu)
5. [Ví dụ tính tay từng bước](#5-ví-dụ-tính-tay-từng-bước)
6. [Các tham số của `weather.fill`](#6-các-tham-số-của-weatherfill)
7. [File kết quả của `fill`](#7-file-kết-quả-của-fill)
8. [Quy trình hai bước và cách khai báo](#8-quy-trình-hai-bước-và-cách-khai-báo)
9. [Những chỗ hay nhầm (hỏi đáp)](#9-những-chỗ-hay-nhầm-hỏi-đáp)
10. [Tài liệu tham khảo](#10-tài-liệu-tham-khảo)

---

## 1. Tóm tắt một bảng

| Khái niệm | Nó là gì | Lệnh nào dùng | Có thay đổi số liệu không? |
|---|---|---|---|
| **Ngày thiếu** | Ngày trong `[start, end]` mà biến đó trống hoặc không có hàng trong CSV | cả `build` và `fill` | Không |
| **`weather.missing_policy`** | Quy định `build` coi ngày thiếu là **lỗi** (`fail`) hay **cảnh báo** (`warn`) | **chỉ `build`** | Không |
| **`swatprep fill weather`** | Lệnh **riêng**, điền ngày thiếu bằng nguồn ngoài đã hiệu chỉnh | **chỉ `fill`** | Có, nhưng ghi ra thư mục mới, không sửa file gốc |
| **`weather.fill.min_overlap_days`** | Ngưỡng số ngày trùng để **cảnh báo** hiệu chỉnh kém tin cậy | **chỉ `fill`** | Không chặn việc điền |
| **`weather.start` / `end`** | Khoảng thời gian cần số liệu; ngoài khoảng này không xét, không ghi | cả hai | Không |
| **`weather.fill.run_in_build`** | `true`: `build` chạy `fill` trước rồi dựng weather từ kết quả đã điền | **chỉ `build`** | Có (ghi CSV đã điền ra `fill.output_dir`) |

Điều quan trọng nhất: **mặc định `build` không tự điền ngày thiếu**. Khối `weather.fill` trong
`config.yaml` bị `build` bỏ qua; chỉ `swatprep fill weather` đọc nó. Muốn `build` tự điền rồi dựng kết quả
trong **một lệnh, một file**, đặt `weather.fill.run_in_build: true` (mục 8.2).

---

## 2. Thế nào là "ngày thiếu"

`swatprep` dựng một dãy ngày liên tục từ `start` đến `end`, rồi so với CSV của từng trạm. Một ngày
được tính là **thiếu** cho một biến khi:

| Tình huống trong CSV | Có tính là thiếu? |
|---|---|
| Ô của biến đó **để trống** (`2000-01-03,,31.0`) | Có |
| **Không có hàng** cho ngày đó (CSV nhảy từ 01-02 sang 01-04) | Có |
| Có giá trị bằng `0` (mưa 0 mm) | **Không**: 0 là số liệu hợp lệ |
| Có giá trị `-99` hay `-999` | **Không được nhận ra là thiếu**: sẽ bị coi là số thật. Hãy đổi thành ô trống trước khi chạy |
| Ngày nằm trước `start` hoặc sau `end` | Không xét, và không được ghi ra |

Các lỗi sau **không phải** "ngày thiếu" mà là lỗi cấu trúc (luôn là `fail`, không phụ thuộc `missing_policy`):

| Lỗi | Tên kiểm tra | Nguyên nhân |
|---|---|---|
| Không thấy file của trạm | `data_file:<trạm>` | Sai `data_dir` hoặc `file_pattern` |
| File thiếu cột của biến yêu cầu | `variables:<trạm>` | Cột không có trong CSV hoặc `weather.variables` ghi thừa biến |

Mức thiếu được báo theo từng trạm và từng biến: `missing:<trạm>:<biến>`, kèm phần trăm ngày thiếu.

---

## 3. `missing_policy`: thiếu thì dừng hay chỉ cảnh báo

```yaml
weather:
  missing_policy: "warn"      # "fail" (mặc định) | "warn"
```

`missing_policy` chỉ quyết định **mức độ** của kiểm tra `missing:<trạm>:<biến>` khi chạy `build`:

| Giá trị | Kiểm tra `missing:...` | Điều gì xảy ra ở `build` |
|---|---|---|
| `fail` (mặc định) | `fail` | Mục weather bị coi là có lỗi nặng: **không ghi file weather**, báo `weather_skipped`, `result.success = False` |
| `warn` | `warn` | Vẫn ghi file weather. Ngày thiếu được ghi là **`-99`** trong file SWAT (xem dưới) |

**Ngày thiếu được ghi thế nào khi `warn`:**

- SWAT Classic (`pcp_<tên>.txt`, `tmp_<tên>.txt`) và SWAT+ (`.pcp`, `.tmp`) đều ghi **`-99`**.
- Theo quy ước của SWAT, giá trị `-99` nghĩa là "không có số liệu"; mô hình sẽ sinh số liệu bằng bộ tạo thời
  tiết (WGN) cho ngày đó (Arnold và cs., 2012; Neitsch và cs., 2011).
- Thống kê WGN do `swatprep` tính (`wgn.csv`) **bỏ qua ngày thiếu**, nên trạm thiếu nhiều vẫn có thống kê, nhưng
  càng thiếu nhiều thì thống kê càng kém tin cậy.

**Khi nào chọn gì:**

| Mục tiêu | Chọn |
|---|---|
| Muốn chắc chắn dữ liệu đầu vào đầy đủ, dừng ngay nếu còn lỗ | `fail` |
| Chấp nhận để SWAT sinh số liệu cho ngày thiếu, hoặc đang kiểm tra dữ liệu và muốn xem toàn bộ báo cáo | `warn` |
| Vừa chạy `fill` xong và còn vài ngày thiếu không điền được | `warn` |

`missing_policy` **không** ảnh hưởng `swatprep fill weather`. Khi `fill`, mọi lỗi thiếu (kể cả khi đặt `fail`) được
hạ xuống cảnh báo để một trạm lỗi không chặn các trạm còn lại.

---

## 4. `fill`: điền ngày thiếu

### 4.1 Mục đích và điều kiện

Điền ngày thiếu của **trạm thực đo** bằng một chuỗi **ngoài** (ví dụ lưới tái phân tích, quan trắc lưới) tại
đúng vị trí trạm. `swatprep` **không tải và không trích xuất** dữ liệu ngoài hộ; nguồn ngoài phải là:

- **NetCDF lưới theo ngày**, mưa tính bằng mm, nhiệt độ bằng °C, hoặc
- **CSV theo trạm** cùng mã trạm với trạm thực đo (anh/chị tự trích sẵn).

### 4.2 Các bước `fill` thực hiện

Cho từng trạm và từng biến trong `weather.variables`:

1. Đọc chuỗi thực đo trong `[start, end]` (ngày thiếu là `NaN`).
2. Lấy chuỗi nguồn ngoài tại trạm: với NetCDF là giá trị ô lưới gần trạm nhất (xem 6.2).
3. Xác định **các ngày trùng**: ngày mà **cả hai** chuỗi đều có số liệu.
4. Tính **một** hệ số hiệu chỉnh cho cả trạm và biến này, trên toàn bộ các ngày trùng:
   - **Mưa**: `hệ số = trung bình(thực đo) / trung bình(nguồn ngoài)` trên các ngày trùng.
     Ngày điền: `nguồn ngoài × hệ số` (không để âm).
   - **Mọi biến khác** (`tmax`, `tmin`, `wind`, `solar`, `humidity`):
     `độ lệch = trung bình(thực đo) − trung bình(nguồn ngoài)`. Ngày điền: `nguồn ngoài + độ lệch`.
5. Chỉ điền vào **ngày thực đo đang thiếu mà nguồn ngoài có giá trị**. Ngày đã có số liệu đo **không bao giờ bị sửa**.

Đây là phương pháp hiệu chỉnh tuyến tính (linear scaling) được mô tả trong Teutschbein và Seibert (2012):
nhân hệ số cho đại lượng không âm như mưa, cộng độ lệch cho nhiệt độ.

### 4.3 Những điều `fill` KHÔNG làm

| Không làm | Hệ quả |
|---|---|
| Không sửa ngày đã có số liệu đo | Số liệu gốc luôn được giữ |
| Không ghi đè file gốc | Kết quả ghi vào `output_dir` riêng |
| Không điền ngoài `[start, end]` | Mở rộng giai đoạn phải đổi `start`/`end` |
| Không điền khi nguồn ngoài cũng thiếu ngày đó | Ngày đó vẫn trống (đếm vào `n_still_missing`) |
| Không hiệu chỉnh theo tháng hay mùa | Chỉ một hệ số cho cả giai đoạn trùng; mưa nhiều mùa rõ rệt có thể cần kiểm tra thêm |
| Không giới hạn miền giá trị ngoài việc mưa không âm | Độ ẩm, bức xạ, gió dùng độ lệch và **có thể ra ngoài miền hợp lý** (vd độ ẩm > 1, gió < 0); hãy kiểm tra các biến này |
| Không tạo trạm mới | Chỉ điền cho trạm có trong `weather.stations` |
| Không tự chọn trạm lân cận nếu không có nguồn | Báo `no_fill_source`, ngày thiếu giữ nguyên |

### 4.4 Chọn ô lưới (với NetCDF)

- Dùng ô gần trạm nhất. Trạm nằm đúng giữa hai ô thì lấy ô có chỉ số nhỏ hơn.
- Ô đó không có dữ liệu (vd ô biển) thì tìm ô có dữ liệu gần nhất trong `search_radius` ô và báo
  `netcdf_extract:<trạm>:neighbor_cell`.
- Không có ô nào có dữ liệu trong bán kính: `no_valid_cell`. Trạm nằm ngoài lưới: `outside_grid`.

---

## 5. Ví dụ tính tay từng bước

Một trạm `S1`, 10 ngày (`2000-01-01` đến `2000-01-10`). Dấu `—` là ngày thiếu.

| Ngày | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Mưa **đo** | 2 | 4 | — | 6 | — | 0 | 8 | — | 10 | 0 |
| Mưa **nguồn ngoài** | 1 | 3 | 5 | 3 | 4 | 0 | 4 | — | 5 | 0 |
| Tmax **đo** | 30 | 31 | — | 29 | 30 | 31 | 32 | — | 30 | 29 |
| Tmax **nguồn ngoài** | 28 | 29 | 29 | 27 | 28 | 29 | 30 | 31 | 28 | 27 |

**Mưa.** Ngày trùng (cả hai có số): 1, 2, 4, 6, 7, 9, 10, tức `n_overlap = 7`.

- Tổng đo trên các ngày trùng: 2 + 4 + 6 + 0 + 8 + 10 + 0 = 30.
- Tổng nguồn ngoài: 1 + 3 + 3 + 0 + 4 + 5 + 0 = 16.
- Hệ số = 30 / 16 = **1,875** (cùng số ngày nên tỷ lệ trung bình bằng tỷ lệ tổng).
- Ngày thiếu: 3, 5, 8 (`n_missing = 3`).
  - Ngày 3: 5 × 1,875 = **9,375**.
  - Ngày 5: 4 × 1,875 = **7,5**.
  - Ngày 8: nguồn ngoài cũng trống nên **vẫn trống**.
- Kết quả: `n_filled = 2`, `n_still_missing = 1`.

**Tmax.** Ngày trùng: 1, 2, 4, 5, 6, 7, 9, 10 (`n_overlap = 8`).

- Trung bình đo = 242 / 8 = 30,25; trung bình nguồn ngoài = 226 / 8 = 28,25; độ lệch = **+2,0**.
- Ngày 3: 29 + 2 = **31,0**. Ngày 8: 31 + 2 = **33,0**. Cả hai ngày đều điền được.

Các ngày 1, 2, 4, 5 (tmax), 6, 7, 9, 10 giữ nguyên giá trị đo.

---

## 6. Các tham số của `weather.fill`

```yaml
weather:
  stations: ./data/obs/stations.csv
  data_dir: ./data/obs
  variables: [precip, tmax, tmin]
  start: "1981-01-01"
  end: "2014-12-31"
  fill:
    type: netcdf              # csv | netcdf: khối cùng tên phải có mặt
    output_dir: ./data/filled
    min_overlap_days: 365
    netcdf:
      path: ./data/grid.nc
      var_map: { precip: pr, tmax: tasmax, tmin: tasmin }
      search_radius: 1
```

### 6.1 Nhóm "dữ liệu thực đo" (đọc như `weather` bình thường)

`stations`, `data_dir`, `file_pattern`, `variables`, `start`, `end` mô tả **trạm thực đo** cần điền. `start`/`end`
quyết định giai đoạn được đọc, được điền và được ghi.

### 6.2 `weather.fill`

| Tham số | Mặc định | Ý nghĩa chính xác |
|---|---|---|
| `type` | `csv` | Loại nguồn điền. Phải có khối `csv:` hoặc `netcdf:` tương ứng, nếu không YAML bị từ chối |
| `output_dir` | không | Thư mục ghi kết quả. Có thể thay bằng đối số `OUT_DIR` của lệnh |
| `min_overlap_days` | `10` | Nếu số ngày trùng **ít hơn** giá trị này, chỉ **phát cảnh báo** `low_confidence`; **việc điền vẫn được thực hiện**. Hệ số tính trên quá ít ngày có thể lệch nhiều |
| `netcdf.path` | bắt buộc | File NetCDF lưới theo **ngày**, mưa mm, nhiệt độ °C |
| `netcdf.var_map` | bắt buộc | Tên biến `swatprep` → tên biến trong file. Khoá hợp lệ: `precip, tmax, tmin, wind, solar, humidity` |
| `netcdf.lat_name`, `lon_name`, `time_name` | `auto` | Chỉ đặt khi tên trục không thuộc nhóm thông dụng (`lat/latitude/y`, `lon/longitude/x`, `time/date`) |
| `netcdf.search_radius` | `1` (0 đến 5) | Số ô tìm quanh ô gần nhất khi ô đó không có dữ liệu. `0` = không tìm thêm |
| `csv.stations`, `data_dir`, `file_pattern` | | Nguồn điền dạng CSV theo trạm (cùng mã trạm với trạm thực đo) |

Chọn `min_overlap_days`: số ngày trùng nên đủ để trung bình ổn định, ví dụ vài năm dữ liệu đối với mưa
(mưa ngày rất biến động). Giá trị `365` trong ví dụ nghĩa là "cảnh báo nếu trùng chưa đủ một năm".

---

## 7. File kết quả của `fill`

Trong `output_dir`:

| File | Nội dung |
|---|---|
| `stations.csv` | Danh sách trạm (`id, name, lat, lon, elev`) lấy từ trạm thực đo |
| `<id>.csv` | Mỗi trạm một file. Cột `date` và mỗi biến trong `variables`; **mỗi ngày của `[start, end]` một hàng**; ngày còn thiếu để **ô trống** |
| `fill_report.csv` | Một hàng cho mỗi cặp trạm × biến |

Các cột của `fill_report.csv`:

| Cột | Ý nghĩa |
|---|---|
| `station_id`, `variable` | Trạm và biến |
| `n_missing` | Số ngày thiếu **trước** khi điền |
| `n_filled` | Số ngày đã điền |
| `n_still_missing` | Số ngày vẫn thiếu sau khi điền (`n_missing − n_filled`) |
| `n_overlap` | Số ngày trùng dùng để tính hiệu chỉnh |
| `correction_type` | `ratio` (mưa), `offset` (biến khác), hoặc trống nếu không tính được |
| `correction_value` | Hệ số hoặc độ lệch |
| `status` | `pass`, hoặc `warn` khi: không có ngày trùng; trung bình nguồn ngoài của mưa bằng 0; hệ số mưa bằng 0 (trạm không có mưa trong giai đoạn trùng, nên mọi ngày điền đều bằng 0); số ngày trùng < `min_overlap_days` |

Cách đọc nhanh: sắp xếp theo `n_still_missing` giảm dần để thấy trạm còn lỗ, và lọc `status == warn` để thấy hiệu chỉnh đáng ngờ.

Các kiểm tra in ra màn hình khi chạy:

| Tên | Ý nghĩa |
|---|---|
| `weather_fill:<biến>:<trạm>:no_fill_source` | Không có nguồn điền cho trạm/biến; ngày thiếu giữ nguyên |
| `weather_fill:<biến>:<trạm>:low_confidence` | Không có ngày trùng, hệ số không tính được, hệ số mưa bằng 0, hoặc trùng ít hơn `min_overlap_days` |
| `netcdf_extract:<trạm>:neighbor_cell` / `no_valid_cell` / `outside_grid` | Xem mục 4.4 |
| `weather_fill_done` | Đã xử lý xong, kèm số tổ hợp trạm × biến |

---

## 8. Quy trình điền rồi build: hai cách khai báo

### 8.1 Cách A: hai file, hai lệnh (rõ ràng nhất)

```
config.fill.yaml   --swatprep fill weather-->   data/filled/   --(đọc bởi)-->   config.yaml --swatprep build--> output/weather
 (dữ liệu thực đo     (điền ngày thiếu)           (CSV đã điền)                   (weather.data_dir = data/filled)
  + nguồn lưới)
```

**Bước 1. `config.fill.yaml`** trỏ vào **dữ liệu thực đo** và khối `fill:` (xem mục 6). Chạy:

```bash
swatprep fill weather --config config.fill.yaml
```

**Bước 2. `config.yaml`** trỏ vào **thư mục đã điền**, không phải thư mục gốc:

```yaml
weather:
  stations: ./data/filled/stations.csv     # đầu ra của bước 1
  data_dir: ./data/filled                  # đầu ra của bước 1
  variables: [precip, tmax, tmin]
  start: "1981-01-01"
  end: "2014-12-31"                        # phải nằm trong giai đoạn đã điền ở bước 1
  missing_policy: "warn"                   # ngày còn thiếu sẽ thành -99
```

**Quy tắc khớp giữa hai bước:**

| Điều cần khớp | Vì sao |
|---|---|
| `config.yaml` `start`/`end` phải nằm **trong** `[start, end]` của bước `fill` | `fill` chỉ ghi các ngày trong giai đoạn của nó. Ngày ngoài giai đoạn đó không có hàng, nên `build` coi là thiếu |
| `variables` của bước 2 là tập con của bước 1 | Chỉ các biến đã điền mới có cột trong file |
| `file_pattern` của bước 2 khớp tên file `fill` ghi | `fill` luôn ghi `<id>.csv` (đặt tên theo mã trạm), nên bước 2 dùng `{id}.csv` |

Có thể chạy `fill` mà không cần file thứ hai: đặt khối `fill:` ngay trong `config.yaml` và chạy
`swatprep fill weather --config config.yaml`. Khi đó `build` (không có `run_in_build`) vẫn đọc `weather.stations`/
`data_dir`, tức dữ liệu **gốc**, nên phải đổi đường dẫn sang thư mục đã điền trước khi build, hoặc dùng cách B.

### 8.2 Cách B: một file, một lệnh `build` (`run_in_build`)

Muốn `swatprep build` vừa điền ngày thiếu, vừa xuất file đã điền, vừa dựng kết quả SWAT, đặt
`weather.fill.run_in_build: true`. Khi đó `weather.stations` / `weather.data_dir` là **dữ liệu thực đo** (đầu vào),
còn `fill.output_dir` là nơi ghi CSV đã điền:

```yaml
project:
  name: "Chu basin"
  crs: "EPSG:32648"
  targets: ["swatplus"]
weather:
  stations: ./data/obs/stations.csv        # dữ liệu THỰC ĐO (không phải thư mục đã điền)
  data_dir: E:/_data/_DataReview/climate_swatplus
  variables: [precip, tmax, tmin]
  start: "1981-01-01"
  end: "2014-12-31"
  missing_policy: "warn"                   # ngày không điền được sẽ thành -99
  fill:
    run_in_build: true                     # build tự điền trước rồi mới dựng
    type: netcdf
    output_dir: ./data/filled              # nơi ghi CSV đã điền + fill_report.csv
    min_overlap_days: 365
    netcdf:
      path: D:/DATA/OBS.Vietnam.1980-2014.nc
      var_map: { precip: pr, tmax: tasmax, tmin: tasmin }
```

```bash
swatprep build config.yaml                 # điền -> xuất data/filled -> dựng output/weather
```

Thứ tự bên trong lần `build`: (1) đọc dữ liệu thực đo; (2) điền ngày thiếu; (3) ghi `stations.csv`, `<id>.csv`,
`fill_report.csv` vào `fill.output_dir`; (4) đọc lại chính các file đó để ghi file SWAT/SWAT+ vào
`output/weather`. Vì bước (4) đọc từ file vừa ghi, **cái được dựng luôn trùng với cái được xuất**. QA có thêm
`weather_fill_in_build` và toàn bộ kiểm tra `weather_fill:*`.

Điều kiện và lưu ý:

| Điều kiện / lưu ý | Lý do |
|---|---|
| Cần `fill.output_dir` | Nơi ghi CSV đã điền |
| `fill.output_dir` phải **khác** `weather.data_dir` | Nếu trùng, file thực đo sẽ bị ghi đè; `build` dừng với lỗi cấu hình |
| Dùng một mạng trạm (`stations` + `data_dir`), không dùng `weather.precip`/`weather.temp` | File đã điền gộp mọi biến theo trạm; mạng trạm tách riêng chưa được hỗ trợ ở chế độ này |
| Không trỏ `weather.stations`/`data_dir` vào `fill.output_dir` | Lần đầu thư mục chưa tồn tại; lần sau sẽ coi dữ liệu đã điền là dữ liệu thực đo |
| Mặc định `run_in_build: false` | Giữ nguyên hành vi cũ: `build` không điền |
| `swatprep fill weather` bỏ qua `run_in_build` | Lệnh này luôn điền và ghi, không dựng file SWAT |
| `--only weather` cũng điền | Vì điền là một phần của mục weather |

### 8.3 Dùng cờ dòng lệnh

Có thể dùng cờ dòng lệnh thay cho YAML; cờ **ghi đè** giá trị trong YAML:

```bash
swatprep fill weather --config config.fill.yaml --fill-search-radius 2 --min-overlap-days 730
```

---

## 9. Những chỗ hay nhầm (hỏi đáp)

**H1. Tôi đặt `missing_policy: warn` thì `build` có tự điền ngày thiếu không?**
Không. `warn` chỉ làm cho ngày thiếu thành cảnh báo (rồi ghi `-99`). Muốn điền phải chạy `swatprep fill weather`,
hoặc đặt `weather.fill.run_in_build: true` để `build` tự điền (mục 8.2).

**H2. Tôi đã chạy `fill` nhưng `build` vẫn báo thiếu.**
Kiểm tra theo thứ tự: (a) `weather.data_dir` và `weather.stations` của `config.yaml` có trỏ vào thư mục `fill`
đã ghi không; (b) trong `fill_report.csv`, trạm đó có `n_still_missing > 0` không (nguồn ngoài cũng thiếu hoặc
không có nguồn); (c) `end` của `config.yaml` có vượt giai đoạn đã điền không (ngày vượt không có hàng, nên thiếu).

**H3. `min_overlap_days` có ngăn việc điền khi trùng ít không?**
Không. Chỉ phát cảnh báo `low_confidence`; việc điền vẫn được thực hiện. Muốn bỏ kết quả của trạm đó, hãy đọc
`fill_report.csv` và tự loại trạm hoặc bổ sung dữ liệu.

**H4. `fill` có ghi đè file CSV thực đo không?**
Không. Kết quả ghi vào `output_dir`. Nếu đặt `output_dir` trùng `data_dir` thì file gốc sẽ bị ghi đè, nên **đừng
đặt trùng**.

**H5. Trong `config.fill.yaml` tôi đặt `missing_policy: fail`, `fill` có dừng không?**
Không. `fill` hạ mọi lỗi thiếu xuống cảnh báo. Thiếu file trạm cũng chỉ là cảnh báo; trạm đó được bỏ qua.

**H6. Số liệu thiếu của tôi ghi là `-99` trong CSV. Có được nhận ra không?**
Không. `swatprep` chỉ coi ô trống và hàng vắng là thiếu. `-99` sẽ bị tính là số thật (mưa −99 mm) và làm
sai hệ số hiệu chỉnh. Đổi `-99` thành ô trống trước khi chạy `validate`/`fill`/`build`.

**H7. Vì sao ngày điền cho mưa luôn bằng 0 ở một trạm?**
Trạm đó không có mưa trong toàn bộ các ngày trùng, nên hệ số mưa bằng 0 và mọi ngày điền bằng 0. Báo cáo ghi
`status = warn`. Đây thường do giai đoạn trùng quá ngắn hoặc dữ liệu đo của trạm sai.

**H8. Tôi nên điền hay để SWAT tự sinh số liệu (`-99`)?**
Điền khi nguồn ngoài đáng tin và có nhiều ngày trùng: ngày được điền bám theo diễn biến thực của từng ngày
(sự kiện mưa), trong khi số sinh từ WGN chỉ giữ đặc trưng thống kê. Để `-99` khi không có nguồn ngoài tốt hoặc
trùng quá ít; lúc đó nên đặt `missing_policy: warn` và đọc kỹ mức thiếu.

**H9. `search_radius` có làm lệch số liệu không?**
Có thể, vì ô thay thế nằm xa trạm hơn. Mỗi lần dùng ô lân cận đều có cảnh báo `neighbor_cell`; hãy xem lại các trạm ven biển.

---

## 10. Tài liệu tham khảo

- Arnold, J.G., Kiniry, J.R., Srinivasan, R., Williams, J.R., Haney, E.B., Neitsch, S.L. (2012). *Soil and Water
  Assessment Tool Input/Output Documentation, Version 2012*. Texas Water Resources Institute, TR-439.
- Neitsch, S.L., Arnold, J.G., Kiniry, J.R., Williams, J.R. (2011). *Soil and Water Assessment Tool Theoretical
  Documentation, Version 2009*. Texas Water Resources Institute, TR-406.
- Teutschbein, C., Seibert, J. (2012). Bias correction of regional climate model simulations for hydrological
  climate-change impact studies: Review and evaluation of different methods. *Journal of Hydrology*, 456-457, 12-29.
