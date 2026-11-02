# swatprep – Fill: trạm ảo (trạm không có số liệu đo)

**Ngày:** 2026-11-02
**Trạng thái:** Đã duyệt; triển khai trong v0.8.0
**Nền:** v0.7.0 (+ field help).

## 1. Vấn đề

`WeatherGapFiller` hiệu chỉnh nguồn điền (CSV hoặc lưới NetCDF) theo **giai đoạn trùng** giữa trạm đo và nguồn điền (linear scaling: tỉ số cho mưa, độ lệch cho nhiệt độ). Một trạm **không có ngày đo nào** (trạm ảo, tạo ra để lấy giá trị lưới tại một vị trí) có `n_overlap = 0`, nên không tính được hệ số và không ngày nào được điền: tệp SWAT ra toàn `-99` (vd SonDiem, OBS1/OBS2).

## 2. Quyết định (phương án C + tick hiệu chỉnh)

| Trường (`weather.fill`) | Mặc định | Ý nghĩa |
|---|---|---|
| `fill_ungauged` | `false` | Trạm không có ngày đo nào (hoặc không có tệp) được điền toàn bộ từ nguồn điền |
| `correct_ungauged` | `true` | Mượn hệ số hiệu chỉnh của **trạm có đo gần nhất** (cùng biến) |
| `max_borrow_km` | `50` | Chỉ mượn khi trạm đó cách trong bán kính này (km, khoảng cách haversine) |

- `fill_ungauged: false` → hành vi cũ, không đổi.
- Trạm cho hệ số (*donor*): trạm có đo, cùng biến, hệ số tính được và `status = pass` (đủ `min_overlap_days`, tỉ số khác 0).
- Có donor trong `max_borrow_km` → áp hệ số của donor gần nhất; không có, hoặc `correct_ungauged: false` → dùng **giá trị thô** của nguồn điền (`correction_type = none`, mưa vẫn kẹp ≥ 0).
- Trạm có đo nhưng không trùng ngày nào với nguồn điền vẫn như cũ (không điền, `warn`): đó là dấu hiệu sai thời kỳ, không phải trạm ảo.
- Trạm ảo luôn `status = warn`. Báo cáo thêm hai cột `correction_from` (id trạm donor) và `distance_km`.
- QA, vd: *"OBS1: no observations for 'precip'; filled from the source with the correction of station 1 (8.3 km)"* hoặc *"… filled with raw source values (no gauged station within 50 km)"*.
- Trạm có trong bảng trạm nhưng không có tệp số liệu được coi là trạm ảo khi `fill_ungauged: true` (cần ít nhất một tệp trạm để đọc dữ liệu đo).

Cơ sở: hiệu chỉnh tuyến tính (linear scaling) của Teutschbein & Seibert (2012); việc chuyển hệ số từ trạm lân cận dựa trên giả định sai số của sản phẩm lưới biến đổi chậm trong không gian, nên giới hạn bằng bán kính (`max_borrow_km`).

## 3. Mã

| File | Thay đổi |
|---|---|
| `swatprep/config.py` | 3 trường mới trong `WeatherFillConfig` (có `description`) |
| `app/services/form_layout.py` | Thêm vào `LAYOUT[WeatherFillConfig]` |
| `swatprep/core/weather_fill.py` | `WeatherGapFiller(..., fill_ungauged, correct_ungauged, max_borrow_km)`; hai lượt: trạm có đo trước, trạm ảo sau; `haversine_km` |
| `swatprep/fill_setup.py` | `FillInputs` mang 3 tham số; `fill_for_build` truyền vào |
| `swatprep/cli.py` | `--fill-ungauged`, `--no-correct-ungauged`, `--max-borrow-km` |

## 4. Kiểm thử (`tests/test_weather_fill.py`)

Trạm đo G1 (tỉ số 2.0 / độ lệch +1.0) và trạm ảo V1: cách 10 km → mượn hệ số; cách 80 km → giá trị thô; `correct_ungauged: false` → giá trị thô; cờ tắt → hành vi cũ; trạm không có tệp; chỉ mượn cùng biến; trạm có đo không bao giờ mượn; cột báo cáo; YAML và CLI.

## Tài liệu tham khảo

- Teutschbein, C., & Seibert, J. (2012). Bias correction of regional climate model simulations for hydrological climate-change impact studies: Review and evaluation of different methods. *Journal of Hydrology*, 456–457, 12–29. https://doi.org/10.1016/j.jhydrol.2012.05.052
