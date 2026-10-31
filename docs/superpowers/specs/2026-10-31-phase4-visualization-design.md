# swatprep – Giai đoạn 4: Trực quan hóa (Explore): Thiết kế

**Ngày:** 2026-10-31
**Trạng thái:** Đã duyệt thiết kế (Phần 1–4); chờ duyệt spec
**Phạm vi:** B (bản đồ kết quả), C (khí hậu theo trạm), D (dòng chảy). Ngoài phạm vi: A (bản đồ dữ liệu đầu vào trước Build), hyetograph ghép với hydrograph.

---

## 1. Mục tiêu

Cho phép kiểm tra chất lượng (QC) dữ liệu bằng mắt ngay trên trang Project, dùng config đang mở:

- **C – Weather:** độ đầy đủ số liệu theo trạm và tháng, trước/sau khi điền; chuỗi chi tiết có đánh dấu ngày đã điền và ngày còn thiếu; khí hậu tháng của mưa.
- **D – Streamflow:** hydrograph, đường duy trì lưu lượng (FDC), khí hậu tháng của dòng chảy.
- **B – Map:** raster kết quả trong `output/` trên nền bản đồ tương tác, kèm boundary, chú giải và thống kê.

## 2. Các quyết định đã chốt

| # | Quyết định | Lựa chọn |
|---|---|---|
| 1 | Vị trí | Bộ chọn **Configure / Explore** trên trang Project, dùng config đang mở |
| 2 | Weather | Heatmap độ đầy đủ *trạm × tháng* (Observed/Filled) + biểu đồ chi tiết chồng lớp + tóm tắt `fill_report.csv` + **khí hậu tháng của mưa** |
| 3 | Quy tắc ngày thiếu | Theo **WMO-No. 1203 (2017)**, mục 4.4.1–4.4.2 (xem mục 5) |
| 4 | Streamflow | Hydrograph (thang log) + FDC (Q5/Q50/Q95) + **khí hậu tháng của dòng chảy** |
| 5 | Map | Bản đồ tương tác **pydeck**, nền Carto/OSM, thanh độ trong suốt |
| 6 | Nguồn dữ liệu | **Dùng lại bộ đọc của lõi** (`WeatherPreprocessor`, `StreamflowPreprocessor`); bản đồ đọc raster trong `output/` |

## 3. Kiến trúc

Phụ thuộc một chiều `app/ui → app/services → swatprep`. `services/` không import Streamlit; `st.cache_data` chỉ dùng ở `ui/`. **Không thêm phụ thuộc mới:** Altair 6.x và pydeck 0.9.x đi kèm Streamlit 1.66; rasterio và geopandas đã có trong extra `geo`.

```
app/services/
  explore_data.py   # gọi lõi; không bao giờ ném lỗi
  climatology.py    # hàm thuần: độ đầy đủ, giá trị tháng theo WMO, khí hậu tháng
  flow_stats.py     # hàm thuần: FDC, phân vị, tóm tắt theo trạm
  raster_view.py    # lớp trong output/ → ảnh PNG RGBA + bounds EPSG:4326 + chú giải + thống kê
app/ui/
  explore.py        # render_explore(config_path): Weather / Streamflow / Map
  charts.py         # hàm tạo alt.Chart
```

### 3.1. Giao diện các module

**`explore_data.py`**

```python
def load_config(path: Path) -> tuple[SWATPrepConfig | None, str | None]
@dataclass
class FlowView:   daily: pd.DataFrame; units: str; error: str | None
@dataclass
class WeatherView:
    stations: pd.DataFrame                 # id (index), name, lat, lon, elev
    observed: dict[str, pd.DataFrame]      # biến → bảng ngày × trạm (NaN = thiếu)
    filled: dict[str, pd.DataFrame] | None # None nếu chưa có số liệu đã điền
    fill_report: pd.DataFrame | None
    error: str | None
def load_weather(cfg: SWATPrepConfig) -> WeatherView
def load_streamflow(cfg: SWATPrepConfig) -> FlowView
```

- Weather đọc với `cfg.weather.model_copy(update={"missing_policy": "warn", "fill": None})`; không sửa tệp config.
- **Filled:** nếu `fill.output_dir/stations.csv` tồn tại, đọc lại bằng `WeatherPreprocessor` với `stations = output_dir/stations.csv`, `data_dir = output_dir`, `file_pattern = "{id}.csv"` (giống `fill_for_build`). `fill_report.csv` đọc bằng `pd.read_csv` nếu có.
- **Ngày được điền** (`estimated`) = `observed.isna() & filled.notna()`.
- **Streamflow:** `StreamflowPreprocessor` chỉ giữ các ngày có trong tệp, nên mỗi trạm được **dàn lại theo ngày** từ ngày có số liệu đầu tiên đến ngày cuối cùng; ngày vắng mặt thành `NaN`.
- Mọi ngoại lệ (`InputValidationError`, `OSError`, ...) được bắt và trả về trong `error`.

**`climatology.py`**

```python
def monthly_values(daily: pd.Series, kind: Literal["sum", "mean"],
                   estimated: pd.Series | None = None) -> pd.DataFrame
    # cột: year, month, value, n_days, n_missing, n_estimated, max_gap, max_est_run, valid, reason
def monthly_climatology(monthly: pd.DataFrame, min_fraction: float = 0.8) -> pd.DataFrame
    # 12 dòng: month, mean, n_valid, n_years, ok
def completeness(wide: pd.DataFrame) -> pd.DataFrame
    # dạng dài: station, period ("YYYY-MM"), n_days, n_missing, pct_missing
```

**`flow_stats.py`**

```python
def fdc(series: pd.Series) -> pd.DataFrame          # cột: exceedance_pct, flow (giảm dần)
def flow_quantile(series: pd.Series, pct: float) -> float  # Q5 = lưu lượng bị vượt 5% thời gian
def summary(wide: pd.DataFrame) -> pd.DataFrame     # mỗi trạm: start, end, pct_missing, min, mean, max, q5, q50, q95
```

**`raster_view.py`**

```python
@dataclass
class Layer:     name: str; path: Path; kind: Literal["continuous", "categorical"]; lookup: Path | None
@dataclass
class LayerView: png: bytes | None; bounds: tuple[float, float, float, float] | None
                 legend: pd.DataFrame; stats: dict; error: str | None
def output_layers(cfg: SWATPrepConfig) -> list[Layer]   # chỉ các tệp đã tồn tại
def render_layer(layer: Layer, max_px: int = 1024) -> LayerView
def boundary_geojson(path: Path | None) -> dict | None   # EPSG:4326
```

- Lớp: DEM `output/spatial/<dem.output_name>` (continuous); landuse `output/landuse/<output_name>` + `landuse_vlookup.csv` (categorical); soil `output/soil/<output_name>` + `soil_vlookup.csv` (categorical); `clip[].dst`: kiểu số nguyên → categorical, còn lại → continuous.

## 4. Giao diện

**Trang Project:** `st.segmented_control` **Configure | Explore** ở đầu vùng chính; trong Explore, một `st.segmented_control` thứ hai chọn **Weather | Streamflow | Map**. Không dùng `st.tabs` cho các phần này: theo mặc định Streamlit tính toán và gửi nội dung **mọi tab** ở mỗi lần rerun, kể cả tab đang ẩn. Chế độ chạy lười (`st.tabs(..., on_change="rerun")` + `tab.open`) chỉ có ở các bản Streamlit mới, trong khi `pyproject.toml` cho phép `streamlit>=1.40`; `segmented_control` (có từ 1.40) chỉ chạy phần đang chọn mà không cần nâng mức tối thiểu.

**Explore** dùng tệp config **đã lưu**. Nếu form có thay đổi chưa lưu: *"Showing the saved config; save to explore your changes."* Cache được làm mới khi thời điểm sửa tệp config đổi, hoặc khi bấm **Reload data**. Mục không có trong config → thông báo ngắn trong phần đó, không phải lỗi.

### 4.1. Streamflow (D)

| Thành phần | Chi tiết |
|---|---|
| Bảng tổng quan | `flow_stats.summary` cho mọi trạm |
| Chọn trạm | Selectbox |
| Hydrograph | Đường theo ngày; kéo chuột để phóng to; **Log scale** (ngày lưu lượng ≤ 0 không vẽ, ghi chú *"n zero-flow days not shown"*); ngày thiếu là vạch đỏ dưới trục |
| FDC | x: % thời gian vượt; y: log; đánh dấu Q5, Q50, Q95 |
| Khí hậu tháng | 12 cột; nhãn *n_valid/n_years*; tháng có `ok = False` vẽ màu nhạt kèm cảnh báo. `units: m3s` → `kind="mean"`; `units: mm` → `kind="sum"` |

### 4.2. Weather (C)

| Thành phần | Chi tiết |
|---|---|
| Bộ điều khiển | **Variable** (từ `weather.variables`); **Data**: Observed / Filled (chỉ hiện khi `filled` khác `None`) |
| Heatmap | y: trạm; x: năm-tháng; màu: % thiếu; tooltip *"ST003 · 2005-07 · 3/31 days missing"*. Filled → phần còn thiếu sau khi điền |
| Biểu đồ chi tiết | Chọn trạm; đường xám = quan trắc; điểm màu = đã điền; vạch đỏ = còn thiếu; dòng tóm tắt từ `fill_report.csv` (n_missing, n_filled, n_still_missing, correction_type, correction_value) |
| Khí hậu mưa | Cột ghép đôi Observed / Filled theo tháng (`kind="sum"`); nhãn và cờ như 4.1. Chỉ hiện khi `precip` có trong `weather.variables` |

### 4.3. Map (B)

| Thành phần | Chi tiết |
|---|---|
| Chọn lớp | Từ `output_layers`; rỗng → *"Run Build to see the output maps."* |
| Bộ điều khiển | **Opacity** (0–1); **Basemap**: Light / Dark / None |
| Bản đồ | `pdk.Layer("BitmapLayer", image=<data URI PNG>, bounds=...)` + `GeoJsonLayer` viền boundary; khung nhìn vừa với bounds |
| Chú giải | Continuous: thang màu min–max. Categorical: ô màu, mã, tên SWAT (từ vlookup), % diện tích |
| Thống kê | CRS, kích thước pixel, hàng × cột, % NoData |

**Xử lý raster:**

1. Đọc thu nhỏ bằng `src.read(1, out_shape=..., masked=True)` sao cho cạnh dài ≤ `max_px`; rasterio dùng overview nếu có.
2. Chiếu sang EPSG:4326 bằng `rasterio.warp.reproject`: `nearest` cho categorical, `bilinear` cho continuous.
3. Tô màu bằng bảng màu cố định trong mã (không dùng matplotlib); NoData → alpha 0; mã hoá PNG bằng Pillow (đi kèm Streamlit).
4. % diện tích tính trên **độ phân giải gốc**: đọc theo khối (`src.block_windows`) và cộng dồn bằng `np.unique(..., return_counts=True)`.

## 5. Quy tắc tính giá trị tháng (WMO-No. 1203, 2017)

Một **tháng lịch** gồm mọi ngày của tháng đó. Ngày nằm ngoài khoảng dữ liệu được tính là **thiếu** (cách bảo thủ, không cần trường hợp đặc biệt cho tháng đầu/cuối). Ngày được điền tính là **có số liệu**, nhưng được đếm riêng (`n_estimated`).

| `kind` | Tháng hợp lệ khi | `reason` khi không hợp lệ | Căn cứ |
|---|---|---|---|
| `sum` (mưa; dòng chảy `mm`) | `n_missing == 0` | `missing days` | 4.4.1(c) |
| `mean` (dòng chảy `m3s`) | `n_missing ≤ 10` **và** `max_gap ≤ 4` | `11+ missing days` / `5+ consecutive missing days` | 4.4.1(a) |
| cả hai, khi có ngày điền | `n_estimated ≤ 10` **và** `max_est_run ≤ 4` | `more than 10 estimated days` / `5+ consecutive estimated days` | 4.4.1(c), 4.6 |

- `value`: tổng (`sum`) hoặc trung bình (`mean`) các ngày có số liệu; `NaN` khi không hợp lệ.
- **Khí hậu tháng** của tháng *m*: trung bình `value` của các năm hợp lệ; `n_years` = số năm-tháng *m* trong khoảng dữ liệu; `ok = n_valid ≥ 0.8 × n_years` (4.4.2).
- Giao diện gọi là **"Monthly climatology"**, không gọi là "normal" (chuẩn khí hậu 30 năm của WMO), vì giai đoạn dự án thường ngắn hơn 30 năm.

## 6. FDC

Sắp xếp giá trị hợp lệ giảm dần, hạng *m* = 1…*n*, xác suất vượt theo vị trí vẽ Weibull: *p* = 100·*m*/(*n* + 1) (%). `flow_quantile(series, k)` nội suy tuyến tính `flow` theo `exceedance_pct` tại *k*. Ví dụ chuỗi 1…99: Q50 = 50, Q5 = 95, Q95 = 5.

## 7. Xử lý lỗi

| Tình huống | Xử lý |
|---|---|
| Config sai schema | Explore không vẽ: *"Config is not valid: fix it in Configure"* + số lỗi |
| Lõi báo lỗi khi đọc | Hiện nguyên thông báo của lõi trong phần đó; các phần khác vẫn chạy |
| `missing_policy: fail` | Explore luôn đọc với `"warn"` (mục 3.1) |
| Có `fill.output_dir` nhưng chưa có `stations.csv` | Ẩn Filled; ghi chú *"No filled data yet: run Build with run_in_build, or `swatprep fill weather`"* |
| Không có `fill_report.csv` | Bỏ dòng tóm tắt |
| Raster không có CRS | `error = "Layer has no CRS"` |
| Không có `project.boundary` | Bản đồ không có viền |
| Không có vlookup | Chú giải chỉ có mã |
| Raster hỏng | Lỗi riêng lớp đó |

## 8. Hiệu năng

| Hạng mục | Quy mô điển hình | Biện pháp |
|---|---|---|
| Weather 30 trạm × 6 biến × 30 năm | ≈ 2 triệu giá trị (≈ 16 MB) | `st.cache_data` |
| Hydrograph 30 năm | ≈ 11.000 điểm | Altair qua Arrow |
| Heatmap 30 trạm × 360 tháng | ≈ 11.000 ô | — |
| DEM ≈ 11 triệu pixel | ảnh ≤ 1024 px | đọc thu nhỏ; % diện tích đọc theo khối |

Thời gian nạp thực tế đo trên `examples/` khi triển khai và ghi vào mục 11.

**Quyền riêng tư:** nền bản đồ do trình duyệt tải từ Carto/OpenStreetMap; máy chủ ô bản đồ biết khu vực đang xem nhưng không nhận dữ liệu dự án. Basemap **None** không gửi yêu cầu nào ra ngoài.

## 9. Kiểm thử

TDD; dữ liệu nhỏ tự tạo, có đáp án biết trước.

- **`climatology`:**
  - Tháng đủ ngày → hợp lệ.
  - `sum` thiếu 1 ngày → `missing days`.
  - 10 / 11 ngày điền → hợp lệ / không hợp lệ.
  - 4 / 5 ngày điền liên tiếp → hợp lệ / không hợp lệ.
  - `mean` thiếu 10 rời rạc / 11 → hợp lệ / không hợp lệ.
  - 4 / 5 liên tiếp → hợp lệ / không hợp lệ.
  - 5 năm: 4 / 3 năm hợp lệ → `ok` True / False.
  - Chuỗi bắt đầu giữa tháng → tháng đầu có ngày thiếu.
  - `completeness` đếm đúng.
- **`flow_stats`:**
  - Chuỗi 1…99 → Q5 = 95, Q50 = 50, Q95 = 5.
  - `NaN` bị bỏ qua.
  - Chuỗi rỗng, hằng số, toàn 0 → không lỗi.
- **`explore_data`:**
  - Dữ liệu `examples/` → có `observed`.
  - `missing_policy: fail` → không lỗi.
  - `data_dir` sai → `error`.
  - Có thư mục fill → có `filled` và `estimated` đúng.
  - Streamflow có ngày vắng → `NaN` sau khi dàn lại.
- **`raster_view`:**
  - GeoTIFF nhỏ trong `tmp_path` (EPSG:32648, có NoData) → ảnh ≤ `max_px`, NoData alpha 0, bounds 4326 đúng, tổng % diện tích = 100, tên lớp từ vlookup.
  - Không có CRS → `error`.
  - `output_layers` chỉ liệt kê tệp tồn tại.
- **UI:**
  - `AppTest`: chuyển sang Explore → chọn được ba phần, không ngoại lệ.
  - Config không có `streamflow` → thông báo.
  - `charts`: `to_dict()` có `scale.type == "log"` khi bật log; heatmap mã hóa đúng trường.

## 10. Chia lát và tiêu chí hoàn thành

| Lát | Nội dung | Phát hành |
|---|---|---|
| 4a | Bộ chọn Configure/Explore, `explore_data`, `climatology`, `flow_stats`, `charts` (phần dòng chảy), phần **Streamflow**; kèm icon app | `v0.4.0` |
| 4b | Phần **Weather**: heatmap, chi tiết, khí hậu mưa | `v0.5.0` |
| 4c | Phần **Map**: `raster_view`, pydeck | `v0.6.0` |

Mỗi lát hoàn thành khi:

- [ ] Toàn bộ test qua (342 + mới) trên Windows và CI Linux.
- [ ] `uv.lock` chỉ đổi dòng phiên bản (không thêm phụ thuộc).
- [ ] Wheel có module mới; `install.bat` cài thử chạy được.
- [ ] Ảnh chụp sáng/tối; ghi thời gian nạp trên `examples/`.
- [ ] Kiểm tra trên dữ liệu thật (laptop chính).
- [ ] Tài liệu: mục Explore trong `docs/USER_GUIDE_VI.md`; `CHANGELOG.md`; `README`; số test chuẩn trong `AGENTS.md`.

## 11. Ghi chú triển khai

### Lát 4a (v0.4.0)

- Thời gian đo trên dự án thử (2 trạm × 6 năm, 2.191 ngày): đọc dòng chảy qua lõi 0,02 s; bảng tổng quan
  + ba biểu đồ 0,15 s.
- Ngày thiếu trên hydrograph được vẽ bằng `mark_rule` cao hết biểu đồ (đỏ, độ mờ 0,4) thay cho vạch ngắn
  dưới trục: khi thử, vạch `mark_tick` với `y=alt.value(...)` không hiện trên biểu đồ.
- Nhãn trên biểu đồ dùng `#757575` để đọc được ở cả giao diện sáng và tối.
- Python 3.10 được khoá với Streamlit 1.65.0 (Streamlit 1.66 cần Python ≥ 3.11); bộ cài dùng Python 3.12.
- Bộ chọn Configure/Explore: các widget của form không được vẽ khi ở Explore nên Streamlit xoá trạng thái
  của chúng; khi quay lại Configure, giá trị được dựng lại từ `state["cfg"]` (test `test_back_to_configure_keeps_edits`).

## Tham khảo

- WMO (2017). *WMO Guidelines on the Calculation of Climate Normals* (WMO-No. 1203), mục 4.4.1, 4.4.2, 4.6. https://www.ncei.noaa.gov/pub/data/normals/WMO/Guidelines%20for%20the%20Calculation%20of%20Climate%20Normals.WMO%20No1203_en.pdf
- WMO (1989). *Calculation of Monthly and Annual 30-Year Standard Normals* (WMO/TD-No. 341).
- WMO (2011). *Guide to Climatological Practices* (WMO-No. 100), chương 3.
- Searcy, J. K. (1959). *Flow-Duration Curves*. USGS Water-Supply Paper 1542-A. https://pubs.usgs.gov/publication/wsp1542A
- Vogel, R. M. & Fennessey, N. M. (1994). Flow-duration curves. I: New interpretation and confidence intervals. *J. Water Resour. Plann. Manage.*, 120(4), 485–504.
- Streamlit – `st.tabs` (mặc định mọi tab đều được tính toán; `on_change="rerun"` + `tab.open`): https://docs.streamlit.io/develop/api-reference/layout/st.tabs
- Streamlit – Release notes 2026: https://docs.streamlit.io/develop/quick-reference/release-notes/2026
- Streamlit – `st.pydeck_chart`: https://docs.streamlit.io/develop/api-reference/charts/st.pydeck_chart
- deck.gl – BitmapLayer: https://deck.gl/docs/api-reference/layers/bitmap-layer
- rasterio – Resampling / decimated reads: https://rasterio.readthedocs.io/en/stable/topics/resampling.html
