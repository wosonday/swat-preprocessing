# swatprep – Màn hình Projects: config chỉ nằm trong dự án

**Ngày:** 2026-10-31
**Trạng thái:** Đã duyệt (phương án 2: màn hình bắt đầu ở vùng chính)
**Nền:** v0.5.0. Phát hành dự kiến: `v0.6.0` (tính năng mới, SemVer MINOR).

## 1. Vấn đề

Thanh bên trang Project có ba cách mở config (danh sách trong thư mục dự án tìm sâu 3 cấp, ô *Config path* trỏ tới bất kỳ đâu, khung *New config* tạo file ở bất kỳ đâu). Config có thể nằm ngoài dự án nên người dùng không rõ "dự án" là gì.

## 2. Quyết định

| # | Câu hỏi | Lựa chọn |
|---|---|---|
| 1 | Mô hình | **Một dự án = một thư mục, có thể nhiều config**, tất cả ở **gốc** thư mục dự án (`*.yaml`, `*.yml`) |
| 2 | Tạo dự án | Ứng dụng tạo thư mục (kể cả thư mục cha) và `config.yaml` đầu tiên; không tạo khung `data/` |
| 3 | Bố cục | **Màn hình Projects** ở vùng chính khi chưa mở dự án; thanh bên gọn khi đã mở |

## 3. Luồng

**Màn hình Projects** (chưa mở dự án):

- *Recent projects*: tối đa 10 thư mục gần nhất còn tồn tại (`~/.swatprep/recent_projects.json`), mỗi mục: tên thư mục, đường dẫn, số config, nút **Open**. Thư mục đã mất không hiện (hành vi sẵn có của `load_recent`).
- *Open project folder*: ô đường dẫn (điền sẵn `SWATPREP_WORKSPACE` nếu có, ví dụ `/workspace` trong Docker) + **Browse** (chọn thư mục) + **Open**. Thư mục không tồn tại → *"Folder not found. Use New project to create it."*
- *New project*: Folder + Browse, Name (mặc định tên thư mục), CRS (danh sách tìm kiếm được), **Create** → tạo thư mục và `config.yaml`, mở dự án. Đã có `config.yaml` → báo lỗi, đề nghị Open.

**Khi đã mở dự án** – thanh bên: tên thư mục, đường dẫn, **Change project**; *Config*: chọn trong các config ở gốc dự án, **+ New config** (hộp thoại: File name mặc định tên chưa dùng `config.yaml`, `config_2.yaml`…; Project name; CRS). Sau đó là Functions và Save/Discard như cũ.

- Config mở mặc định: `config.yaml` nếu có, nếu không thì file đầu tiên theo tên.
- Còn thay đổi chưa lưu → ô Config, **+ New config** và **Change project** bị khoá, kèm *"Save or discard your changes first."* (trước đây đổi config sẽ âm thầm bỏ thay đổi).
- Dự án chưa có config → vùng chính: *"This project has no config yet."* + **+ New config**.

**Bỏ:** ô *Config path* và nút Browse của nó, khung *New config* cũ, `project_io.list_configs` (tìm sâu 3 cấp), các khoá `project_dir`, `recent_choice`, `config_choice` cũ, `new_path::*`.

## 4. Mã

| File | Vai trò |
|---|---|
| `app/services/projects.py` (mới) | `CONFIG_SUFFIXES`, `ProjectError`, `list_configs(folder)`, `default_config(folder)`, `free_config_name(folder)`, `create_config(folder, file_name, name, crs)`, `create_project(folder, name, crs)` – Python thuần |
| `app/ui/projects_home.py` (mới) | `render_home(roots)`: màn hình Projects |
| `app/ui/project_sidebar.py` (mới) | `render_project_header(project, locked)`, `render_config_picker(project, configs, current, locked)`, `new_config_dialog(project)` |
| `app/pages/1_Project.py` | Điều phối: `state["project"]` rỗng → `render_home`; có → thanh bên, form, Explore như cũ |
| `app/services/project_io.py` | Bỏ `list_configs` |

Trạng thái phiên: `state["project"]` (str thư mục đang mở hoặc `None`), `state["config_path"]` (config đang mở). `create_config` từ chối tên rỗng, có thành phần đường dẫn (`/`, `\`, `..`), sai đuôi hoặc đã tồn tại; lỗi hệ điều hành (`OSError`) được gói thành `ProjectError` để hiện ngay trên giao diện.

## 5. Kiểm thử

- `tests/ui/test_projects.py`: chỉ liệt kê config ở gốc; mặc định `config.yaml`; tên tăng dần; tạo dự án khi thư mục cha chưa có; từ chối tên xấu và file đã tồn tại; `create_project` từ chối thư mục đã có `config.yaml`.
- `tests/ui/test_projects_home.py` (AppTest): màn hình Projects khi mới mở; Recent mở được dự án; Open thư mục không tồn tại báo lỗi; New project tạo thư mục + config và mở form; dự án một config tự mở; + New config tạo file trong dự án và mở nó; thay đổi chưa lưu khoá đổi config và Change project; Change project quay về màn hình Projects; dự án không có config hiện gợi ý.
- Cập nhật các test đang dùng `config_choice`, `project_dir`, `config_path`, `new_name`, `new_crs`.
