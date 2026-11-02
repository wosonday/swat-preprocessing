# swatprep – Explore › Map: trạm và lớp shapefile ngoài (chỉ web app)

**Ngày:** 2026-11-02
**Trạng thái:** Đã duyệt; đã triển khai trong v0.7.0
**Nền:** v0.6.1. Phát hành: `v0.7.0` (cùng bản sửa `KeyError` trong `section_at` và `uv.lock` 0.6.1).

## 1. Mục tiêu

Trên Explore › Map, xem vị trí **trạm mưa** và **trạm dòng chảy** so với lưu vực, và chồng **shapefile ngoài** lên DEM / land use / soil để ước lượng phạm vi (extent) của chúng. Chỉ thuộc web app: không đổi `config.yaml`, lõi `swatprep` hay CLI.

## 2. Quyết định

| # | Câu hỏi | Lựa chọn |
|---|---|---|
| 1 | Toạ độ trạm dòng chảy và lớp ngoài | **Add layer** chung: vector (`.shp`, `.gpkg`, `.geojson`/`.json`) hoặc CSV điểm (`lat`, `lon`, chấp nhận `LAT`, `LONG`…). Trạm mưa lấy tự động từ config |
| 2 | Ghi nhớ | Theo dự án, trong `<dự án>/.swatprep/map_layers.json` (đường dẫn, màu, bật/tắt, CRS của CSV); không chép dữ liệu |

## 3. Giao diện

```
Layer [Land use ▾]   Opacity [──●──]   Basemap [Light|Dark|None]
┌──────────────────────── bản đồ ─────────────────────────┐
│ raster + boundary · ● trạm mưa · ● điểm lớp thêm · ▭ viền │
└──────────────────────────────────────────────────────────┘
Overlays
 [x] Rain stations (config)   12 points
 [x] Q_stations.csv           3 points      [Remove]
 [x] subbasins.shp            24 polygons   [Remove]
 Add layer: Path [..........] [Browse]  CSV coordinates CRS [EPSG:4326]  [Add]
Extents
 Layer | West | South | East | North | Area (km²) | Covers boundary
```

- **Trạm mưa:** `weather.precip.stations` nếu có, không thì `weather.stations`; đọc bằng `swatprep.core.weather.read_stations` (nhận `ID,NAME,LAT,LONG,ELEV`). `lat`/`lon` được hiểu là độ WGS84. Chấm xanh lá `#00aa54`, viền trắng, tooltip là tên trạm.
- **Lớp thêm:**
  - Vector đọc bằng geopandas, chiếu sang EPSG:4326 để hiển thị; không có CRS → lỗi *"has no CRS (missing .prj?)"*, không đoán.
  - CSV/TXT: tên cột theo quy tắc của bảng trạm (không phân biệt hoa thường; `long`, `longitude`, `latitude` là bí danh); cần `lat` và `lon`; nhãn lấy từ `name`, không có thì `id`. Ô *CSV coordinates CRS* mặc định `EPSG:4326`; dùng CRS chiếu (vd `EPSG:32648`) khi cột là toạ độ mét (`lat` = northing, `lon` = easting).
  - Điểm → `ScatterplotLayer` (bán kính 5 px); đường và đa giác → `GeoJsonLayer` chỉ vẽ viền (2 px, không tô) để vẫn thấy raster.
  - Màu lần lượt từ bảng `#ff7528, #8e44ad, #e91e63, #f1c40f, #16a085, #795548, #00bcd4, #2c3e50` (tránh xanh dương của boundary và xanh lá của trạm mưa); màu chưa dùng được chọn trước.
- **Bật/tắt, Add, Remove** ghi ngay vào `map_layers.json`. Tệp không còn → dòng báo *not found*, không vẽ, vẫn giữ trong danh sách (để Remove hoặc khôi phục tệp).
- **Extents** (một dòng cho boundary, raster đang chọn, trạm mưa và mỗi lớp thêm đang bật): phạm vi theo độ; diện tích (km²) cho lớp đa giác tính trong `project.crs`; *Covers boundary* = khung bao của lớp chứa khung bao của boundary (`yes`/`no`; `—` cho chính boundary hoặc khi không có boundary).
- Bản đồ hiện cả khi **chưa Build** (chưa có raster): boundary, trạm và lớp thêm vẫn vẽ; ô *Layer* hiện *"No output raster yet"*.
- Khung nhìn ban đầu vừa với tất cả lớp đang hiện.

## 4. Mã

| File | Vai trò |
|---|---|
| `app/services/overlays.py` (mới, Python thuần) | `Overlay(path, color, visible=True, crs="EPSG:4326")`; `overlays_file(project)`; `load_overlays(project)` (tệp hỏng/thiếu → `[]`); `save_overlays(project, items)`; `next_color(items)`; `OverlayView(name, kind, count, points, geojson, bounds, area_km2, error)`; `read_overlay(path, csv_crs="EPSG:4326", project_crs=None)` (không bao giờ ném lỗi); `station_points(cfg)`; `extent_table(rows, boundary_bounds)` → DataFrame `layer, west, south, east, north, area_km2, covers_boundary` |
| `app/ui/maps.py` (sửa) | `layer_deck(view, boundary, opacity, basemap, overlays=())`: `view` có thể là `None`; thêm lớp điểm/đường; tooltip `{label}`; khung nhìn theo tất cả bounds |
| `app/ui/explore.py` (sửa) | Khối *Overlays*, *Add layer*, *Extents*; đọc lớp có cache theo (đường dẫn, thời điểm sửa tệp, CRS) |

Thư mục dự án = thư mục chứa config đang mở. `kind` ∈ `point`, `line`, `polygon`, `mixed`; đối tượng điểm của tệp hỗn hợp vẫn vẽ bằng `ScatterplotLayer`.

## 5. Kiểm thử

- `tests/ui/test_overlays.py`: JSON ghi rồi đọc lại; JSON hỏng → `[]`; màu tiếp theo khác màu đã dùng; CSV `ID,NAME,LAT,LONG`; CSV UTM 48N chiếu đúng; đa giác có bounds và diện tích; shapefile UTM hiển thị theo độ; tệp mất / không CRS / CSV thiếu cột → `error`, không ném; trạm mưa từ `examples/`; bảng Extents đánh dấu `yes`/`no`/`—`.
- `tests/ui/test_maps.py`: deck có `ScatterplotLayer` và `GeoJsonLayer` của lớp thêm; deck dựng được khi `view=None`.
- `tests/ui/test_explore_page.py` (AppTest): Map hiện bản đồ khi chưa Build (có trạm mưa); thêm một lớp CSV rồi xoá; `map_layers.json` được ghi.
- Kiểm chứng trên trình duyệt: dữ liệu thử có trạm, shapefile rộng hơn lưu vực, CSV UTM; giao diện sáng và tối.

## 6. Ghi chú triển khai

- pydeck đọc mọi chuỗi như biểu thức JavaScript: `radius_units="pixels"` thành `@@=pixels` và các điểm thành vòng tròn khổng lồ phủ kín bản đồ; phải bọc `pdk.types.String("pixels")` (có test).
- Viền (GeoJSON) được vẽ trước, điểm vẽ sau cùng để không bị viền che.
- Mã bản đồ tách khỏi `app/ui/explore.py` sang `app/ui/map_view.py`.
- Kiểm chứng trên dữ liệu thử: lưu vực elip 64,0 km² (tính tay π·5,4·3,78 ≈ 64,1 km²), shapefile mở rộng `yes`, tiểu lưu vực `no`, CSV UTM 48N đặt đúng chỗ; sáng và tối.
