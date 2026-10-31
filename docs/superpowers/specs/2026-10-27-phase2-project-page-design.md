# swatprep – Giai đoạn 2: trang Project (form config, Validate, Build) — Thiết kế

**Ngày:** 2026-10-27
**Trạng thái:** Đã duyệt từng phần (1–4); chờ duyệt bản viết
**Tiền đề:** Giai đoạn 1 và 5 xong (`docs/superpowers/specs/2026-10-24-streamlit-docker-design.md`), image `0.2.3`.

---

## 1. Mục tiêu

Web app là một `config.yaml` có giao diện: cùng mô hình `SWATPrepConfig`, cùng `SWATPrepProject.build()`, nên kết quả giống hệt CLI. Người dùng bật/tắt chức năng, dán đường dẫn hoặc dùng Browse, chọn tuỳ chọn, rồi Validate và Build.

### Quyết định đã chốt

| Câu hỏi | Lựa chọn |
|---|---|
| Nhập dữ liệu | Form tương đương YAML; bật/tắt từng mục |
| Browse | Trình duyệt thư mục tự viết, giới hạn trong `DATA_ROOT` và `WORKSPACE` |
| Sinh form | `field_widget` chung theo kiểu Pydantic + bố cục khai báo bằng dữ liệu (`LAYOUT`) + test đồng bộ |
| Đường dẫn trong YAML | Đường dẫn tuyệt đối mà app nhìn thấy (hoặc giữ nguyên như trong tệp đã mở). Không sửa lõi |
| Bố cục | Một trang `app/pages/1_Project.py`: thanh bên + tab + Validate/Build + kết quả |
| Đọc/ghi YAML | `ruamel.yaml` round-trip (giữ comment, thứ tự, định dạng) trong `app/` |
| Giao diện | Hệ thống thiết kế OpenDesign (mục 7) |

Ngoài phạm vi: chạy Build nền, biến môi trường trong đường dẫn config, trang tiện ích (Giai đoạn 3), bản đồ/biểu đồ (Giai đoạn 4).

## 2. Kiến trúc

```
app/
  Home.py                 (giữ; đổi biểu tượng trạng thái theo mục 7.3)
  pages/1_Project.py      UI: thanh bên, tab, nút, kết quả
  ui/widgets.py           field_widget, path_widget, hộp thoại Browse (import streamlit)
  services/               Python thuần, không import streamlit
    settings.py, environment.py   (giữ)
    fs_browser.py         list_dir(root, sub) → thư mục, tệp; chặn thoát khỏi root
    form_model.py         field_spec(Model, field) → kind, default, choices, giới hạn
    form_layout.py        LAYOUT (mục → danh sách trường), PATH_KINDS
    project_io.py         load_yaml, save_yaml (ruamel), list_configs(workspace)
    runner.py             validate(path), build(path, only) → RunResult; không ném lỗi
.streamlit/config.toml    theme OpenDesign
```

Phụ thuộc một chiều: `pages → ui → services → swatprep`.

### Luồng dữ liệu

```
Open → load_yaml → dict thô → session_state["cfg"] ⇄ ô nhập
Save → model_validate(dict) (cảnh báo nếu lỗi) → save_yaml
Validate → Save → schema → SWATPrepProject.from_config(path).validate()
Build → Save → schema → SWATPrepProject.from_config(path).build(only) → kết quả
```

Form giữ **dict thô** từ YAML, không giữ `SWATPrepConfig`, vì `from_yaml()` đổi đường dẫn tương đối thành tuyệt đối. Pydantic chỉ dùng để kiểm tra.

## 3. Cơ chế form

### 3.1. `field_spec`

| Kiểu trong `config.py` | kind |
|---|---|
| `Path`, `Optional[Path]` | `path` |
| `Literal[...]` | `choice` |
| `list[Literal[...]]` | `multichoice` |
| `bool` | `bool` |
| `float`, `int`, `Optional[...]` | `number` (giới hạn từ `gt/ge/le`; trống = `None`) |
| `date` | `date` |
| `str` | `text` |
| `list[str]` | `text_list` (phân tách dấu phẩy) |
| `dict[str, str]` | `mapping` (bảng hai cột) |
| `BaseModel` lồng nhau, `list[BaseModel]` | do bố cục xử lý (`weather.precip/temp/units/fill`, `clip[]`) |

Mặc định lấy từ `FieldInfo.default`; trường bắt buộc đánh dấu `*`.

### 3.2. `LAYOUT` và `PATH_KINDS`

`LAYOUT` liệt kê trường theo thứ tự hiển thị cho mỗi model (`ProjectConfig`, `DEMConfig`, `ClipItemConfig`, `LandUseConfig`, `SoilConfig`, `WeatherConfig`, `WeatherSourceConfig`, `WeatherUnitsConfig`, `WeatherFillConfig`, `FillCSVConfig`, `FillNetCDFConfig`, `StreamflowConfig`).

`PATH_KINDS`: `file` (mặc định), `dir` (`weather.data_dir`, `*.data_dir`), `file_or_dir` (`streamflow.path`), `output` (`project.output_dir`, `clip[].dst`, `weather.fill.output_dir`; không báo thiếu).

### 3.3. Ghi YAML

- Bật mục: thêm `section: {}`; tắt: gỡ khỏi dict và cất tạm trong phiên.
- Giá trị bằng mặc định không được thêm vào YAML, trừ khi khoá đã có trong tệp lúc mở.
- `ruamel.yaml` round-trip: mở rồi lưu không sửa gì → nội dung và comment giữ nguyên.

### 3.4. Browse

`st.dialog`: chọn gốc (Data/Workspace), breadcrumb, `..`, thư mục trước tệp, kích thước tệp; Select điền đường dẫn vào ô. `list_dir` từ chối đường dẫn ngoài gốc. Ô dán thủ công luôn có; trạng thái tồn tại hiển thị ngay; gợi ý "In Docker, data paths start with /data".

## 4. Validate, Build, kết quả, lỗi

| Nút | Hành vi |
|---|---|
| Save | Luôn lưu; cảnh báo nếu schema lỗi |
| Validate | Lưu → schema → tệp tồn tại |
| Build | Lưu → schema → `build(only)`; hộp chọn Run: tất cả hoặc một mục |

- Lỗi schema: `ValidationError.errors()[].loc` → hiện dưới ô tương ứng; nhãn tab có số lỗi.
- Lỗi tệp: `file_exists:<section>.<field>` → gắn về ô.
- Kết quả: số pass/warn/fail (`st.metric`), bảng QA lọc theo trạng thái, thư mục output, tải `manifest.json`, hiển thị `qa_report.md`; giữ trong `session_state`.
- `runner` bắt `SWATPrepError` và `Exception` → `RunResult(ok=False, error, traceback)`; UI hiện lỗi + traceback thu gọn.
- YAML lỗi khi mở: hiện dòng/cột (`problem_mark`).
- Giới hạn: Build đồng bộ; khoá nút trong lúc chạy; không có thanh tiến độ chi tiết.

## 5. Kiểm thử

| Tầng | Nội dung |
|---|---|
| Đơn vị | `fs_browser` (liệt kê, sắp xếp, chặn traversal); `form_model` (mọi kind); `form_layout` ↔ `config.py` (hai chiều); `project_io` (round-trip giữ comment, không thêm mặc định, lỗi YAML có dòng); `runner` (pass/fail gắn trường, lỗi bất ngờ không ném ra) |
| End-to-end | `runner.build()` trên bản sao `examples/` trong `tmp_path` → `manifest.json`, `error_count == 0` (≈20 s) |
| Giao diện | `streamlit.testing.v1.AppTest`: trang chạy không lỗi; bật DEM → có tab DEM |
| Thủ công | Config thật trên `D:` (Windows) và trong Docker |

Đã kiểm chứng trước (2026-10-27): `swatprep validate examples/config_minimal.yaml` 9/9 tồn tại; `build` thành công, 1 cảnh báo.

## 6. Thứ tự xây dựng (mỗi lát một PR)

1. **Mở → Validate → Build → Kết quả:** `project_io`, `runner`, `fs_browser` + Browse; theme (mục 7); xem YAML chỉ đọc.
2. **Form cơ bản:** `form_model`, `form_layout`, `field_widget`, `path_widget`; tab Project, DEM, Land use, Soil, Streamflow; bật/tắt; Save; test đồng bộ.
3. **Weather + Clip:** nguồn mưa/nhiệt, `fill` CSV/NetCDF theo `type`, `var_map`, `clip[]` thêm/xoá.
4. **Hoàn thiện:** lỗi tại ô, số lỗi trên tab, "Unsaved changes", khoá nút khi Build.

Sau lát 4: phát hành `v0.3.0` theo `docs/RELEASING.md`.

## 7. Giao diện: OpenDesign

Nguồn: hệ thống thiết kế OpenDesign (claude.ai artifact). Màu xám trung tính làm nền giao diện; xanh `brand` (#87ea5c) chỉ dùng tiết kiệm cho phản hồi thành công. Màn hình gọn, kiểu công cụ.

### 7.1. `.streamlit/config.toml`

| Tuỳ chọn Streamlit | Token OpenDesign | Light | Dark |
|---|---|---|---|
| `backgroundColor` | `bg` | `#ffffff` | `#202020` |
| `secondaryBackgroundColor` | `bg-panel` | `#fafafa` | `#353535` |
| `textColor` | `text` | `#494949` | `#ededed` |
| `borderColor` | `border` | `#dbdbdb` | `#5c5c5c` |
| `primaryColor` | `selected` (light); `text-strong` (dark, vì `selected` không có giá trị dark) | `#353535` | `#fafafa` |
| `linkColor`, `blueColor` | `blue` | `#1a74ff` | `#3aa5f0` |
| `greenColor` | `green` | `#00aa54` | `#3bbf7d` |
| `greenBackgroundColor` | `green-bg` | `#f5ffee` | `#164111` |
| `redColor` | `red` | `#f04142` | `#ff5e5e` |
| `orangeColor` | `amber` | `#ff7528` | `#ffc740` |
| `codeBackgroundColor` | `code-body-bg` | `#fafafa` | `#18181b` |
| `dataframeHeaderBackgroundColor` | `bg-subtle` | `#ededed` | `#494949` |

Kiểu chữ và hình khối:

- `font = "Albert Sans:https://fonts.googleapis.com/css2?family=Albert+Sans:ital,wght@0,100..900;1,100..900&display=swap"` (Albert Sans có trên Google Fonts).
- `codeFont = "ui-monospace, SFMono-Regular, monospace"`. JiduMono Pro của hệ thống không có bản host; dùng fallback mono của chính hệ thống.
- `baseFontSize = 14`, `baseFontWeight = 600` (`body`); `headingFontWeights = 700`.
- `baseRadius = "4px"` (`radius-medium`, controls); `buttonRadius = "999px"` (`radius-pill`).
- `showWidgetBorder = true`; `showSidebarBorder = true`.
- Dùng `[theme.light]` và `[theme.dark]` để người dùng chuyển theme trong menu Settings.

### 7.2. Nội dung (theo brand book)

- Sentence case cho mọi nhãn, nút, tiêu đề: "Open config…", "Validate", "Build", "Save".
- Nhãn = động từ + đối tượng; xác nhận là câu quá khứ ngắn có dấu chấm: "Config saved.", "Build finished."
- Dấu `…` cho placeholder và trạng thái đang chạy: "Building…", "Search files…".
- Lỗi nêu thứ bị lỗi và cách xử lý: "DEM file not found" + nút "Browse".

### 7.3. Biểu tượng trạng thái

OpenDesign không dùng emoji trong nút, tiêu đề, văn bản trạng thái. Thay ✅ ❌ ⚠️ bằng Material Symbols có sẵn của Streamlit (`:material/check_circle:`, `:material/error:`, `:material/warning:`) **luôn kèm chữ** (pass/warn/fail), vì màu trạng thái light theme dưới 4,5:1 với chữ nhỏ. Hệ thống gốc dùng Remix Icon; Streamlit chỉ hỗ trợ sẵn Material Symbols, nên đây là thay thế gần nhất (ghi nhận lệch).

## 8. Tiêu chí hoàn thành

- [ ] Toàn bộ test qua (Windows, Linux, CI).
- [ ] Chép `examples/` vào workspace → Open `config_minimal.yaml` → Validate 9/9 → Build 0 fail → tải `manifest.json`, cả Windows lẫn Docker.
- [ ] Dựng lại config tương đương `config_minimal.yaml` từ form + Browse → Build thành công.
- [ ] Config thật trên `D:` chạy được qua giao diện (Windows).
- [ ] Giao diện dùng theme OpenDesign ở cả light và dark; không còn emoji trong trạng thái.
- [ ] `ghcr.io/wosonday/swatprep:0.3.0` publish và kiểm chứng.

## 9. Ghi chú triển khai (2026-10-27)

Lát 1–4 đã xây xong và kiểm thử (327 test qua trên Linux; Playwright: light, dark, lỗi tại ô, Browse, Build trên `examples/`). Khác biệt so với thiết kế:

- **Dark `primaryColor = #757575`** (giá trị suy ra, không phải token): Streamlit luôn vẽ chữ trắng trên nút chính, nên `text-strong` (#fafafa) làm chữ biến mất. #757575 cho chữ trắng 4,6:1 và 3,5:1 so với `bg` (WCAG AA). Trên thanh bên (`bg-panel` #353535) công tắc chỉ đạt 2,7:1; trạng thái vẫn thể hiện qua vị trí núm.
- **Build** chạy Validate trước; nếu thiếu tệp thì dừng và đánh dấu tại ô. Không khoá nút trong lúc Build (Streamlit đồng bộ); kết quả được lưu vào `session_state` ngay khi `build()` trả về.
- Mỗi ô nhập ghi vào dict qua `on_change`, nên số lỗi trên tab và chỉ báo "Unsaved changes" luôn phản ánh lần sửa mới nhất. Khối Save đặt sau form để thấy cả thay đổi từ hộp thoại Browse.
- "Unsaved changes" so với bản dump lúc mở (không so với văn bản tệp), để định dạng khác mặc định của ruamel không bị coi là thay đổi.
- Thêm **New config** (tạo `config.yaml` tối thiểu trong workspace) và **Discard** (tải lại từ đĩa).
- **Project folder do người dùng chọn** (2026-10-27): thanh bên có ô *Folder* (dán hoặc Browse), danh sách *Recent* (tối đa 10, lưu ở `~/.swatprep/recent_projects.json`, đổi chỗ bằng `SWATPREP_STATE_DIR`). *Open config* liệt kê YAML trong thư mục đó; *New config* mặc định `<folder>/config.yaml`. Browse bắt đầu từ Project, Data, Workspace (chỉ khi `SWATPREP_WORKSPACE` được đặt), Home và các ổ đĩa trên Windows. Mặc định: thư mục gần nhất, nếu không có thì `SWATPREP_WORKSPACE` (Docker: `/workspace`).
- **Cài đặt không cần Docker** (2026-10-31): lệnh `swatprep-ui` (`app/launch.py`) chạy Streamlit từ thư mục `app/`, nơi có `app/.streamlit/config.toml` (nguồn theme duy nhất, đóng gói qua `package-data` cùng `pages/*.py`). Người dùng cài bằng `scripts/install.bat` / `scripts/install.sh` (`uv tool install` từ archive của tag, tạo lối tắt Desktop/menu). Bản cài cục bộ chỉ nghe `localhost`; Docker ghi đè bằng `--server.address=0.0.0.0`. `SWATPREP_DATA_ROOT`/`SWATPREP_WORKSPACE` là tuỳ chọn: chưa đặt thì trang Home hiện "not set (optional)". Giới hạn: `uv tool install` không dùng `uv.lock`, nên phiên bản thư viện có thể mới hơn bản đã test (trang Home hiển thị phiên bản thực tế).
