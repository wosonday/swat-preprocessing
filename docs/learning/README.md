# Mã mẫu cho tài liệu học

Đi kèm [`../LEARNING_GUIDE_VI.md`](../LEARNING_GUIDE_VI.md). Chạy từ thư mục gốc của kho mã, sau
`uv sync --extra geo --extra app --extra dev`. Các script không ghi gì vào kho mã: dữ liệu tạm nằm trong thư mục
tạm của hệ thống (`swatprep_demo`, `swatprep_*`, `fill_*`).

| Tệp | Lệnh | Nội dung |
|---|---|---|
| `01_api_build.py` | `uv run python docs/learning/01_api_build.py` | Toàn bộ lõi qua Python API: config → validate → build → QA |
| `02_processor_pattern.py` | `uv run python docs/learning/02_processor_pattern.py` | Hợp đồng processor → QA → writer |
| `03_fill_virtual_station.py` | `uv run python docs/learning/03_fill_virtual_station.py` | Điền số liệu, trạm ảo mượn hệ số trạm gần nhất |
| `04_form_from_model.py` | `uv run python docs/learning/04_form_from_model.py` | Web app sinh form từ model Pydantic, ghi YAML, báo lỗi |
| `05_map_preview.py` | `uv run python docs/learning/05_map_preview.py` | Raster → PNG EPSG:3857 → pydeck → HTML |
| `06_map_select_app.py` | `uv run streamlit run docs/learning/06_map_select_app.py` | Bấm trạm trên bản đồ → biểu đồ mưa (cache) |
| `07_optimize_map.py` | `uv run python docs/learning/07_optimize_map.py [RASTER]` | Đo các nút thắt của bản đồ, so sánh v0.8.0 với v0.9.0 (overviews, thống kê lưu sẵn, đường viền gọn) |
| `demo_data.py` | (được các script 05–07 gọi) | Lưu vực tổng hợp: DEM, ranh giới 20 000 đỉnh, 5 trạm mưa 2010–2014 |
