# swatprep – Streamlit UI và đóng gói Docker: Thiết kế

**Ngày:** 2026-10-24
**Trạng thái:** Đã duyệt (Phần 1–2); Phần 3 lồng vào quá trình triển khai
**Bối cảnh sử dụng:** Giai đoạn đầu dùng cá nhân trên Windows (Docker Desktop) để học; sau đó chia sẻ image cho đồng nghiệp (Docker Hub/GHCR).

---

## 1. Mục tiêu và phạm vi

Thêm giao diện Streamlit và đóng gói Docker cho `swatprep` mà **không thay đổi kiến trúc lõi**. Lõi (`swatprep/`) đã có API (`SWATPrepProject`) và CLI; phần mới chỉ là các "vỏ".

### Lộ trình

| Giai đoạn | Nội dung | Kết quả chạy được |
|---|---|---|
| 1a | App khung: `app/Home.py` + `services/` + test | `uv run streamlit run app/Home.py` |
| 1b | Docker: `Dockerfile`, `.dockerignore`, `compose.yaml`, `.env.example` | `docker compose up --build` → `localhost:8501` |
| 2 | Quy trình chính: soạn config (form dựa trên `SWATPrepConfig`), Validate, Build, xem QA/manifest | Tạo config → build → xem QA |
| 3 | Tiện ích: `convert`, `clip`, `fill`, `inspect` | Phủ toàn bộ CLI |
| 4 | Trực quan hóa: bản đồ raster + boundary, biểu đồ mưa/nhiệt độ/dòng chảy | Kiểm tra trực quan dữ liệu |
| 5 | Phân phối: tag phiên bản, push GHCR/Docker Hub, GitHub Actions | `docker run ...` trên máy khác |

Thứ tự theo kỹ thuật *walking skeleton* (Freeman & Pryce, 2009): app mỏng → đóng gói ngay → thêm tính năng.

## 2. Kiến trúc

```
app/pages  →  app/services  →  swatprep (lõi)
   (Streamlit)          (Python thuần)           (không đổi)
```

- Phụ thuộc một chiều. `services/` không import `streamlit`, test được bằng pytest.
- `app` là package (có `__init__.py`) được khai báo trong `pyproject.toml` để import nhất quán giữa Streamlit, pytest và Docker. Giữ tên `app` vì phân phối qua Docker image nên rủi ro trùng tên trong site-packages thấp.

### Cấu trúc thư mục

```
app/
  __init__.py
  Home.py
  pages/
  services/
    __init__.py
    settings.py       # SWATPREP_DATA_ROOT, SWATPREP_WORKSPACE
    environment.py    # get_report(): phiên bản, driver GDAL, thư mục
tests/ui/
  test_settings.py
  test_environment.py
.streamlit/config.toml
Dockerfile
.dockerignore
compose.yaml
.env.example
```

## 3. Quy ước đường dẫn (Twelve-Factor: Config)

| Biến | Windows | Docker | Quyền |
|---|---|---|---|
| `SWATPREP_DATA_ROOT` | `D:\DATA_STORAGE\_data` | `/data` | Chỉ đọc |
| `SWATPREP_WORKSPACE` | `D:\SWAT-model\workspace` | `/workspace` | Đọc/ghi |

Mã giao diện không bao giờ viết cứng đường dẫn.
Giai đoạn 2: lõi hỗ trợ `${VAR}` trong đường dẫn config (`os.path.expandvars`) để một `config.yaml` chạy được ở cả hai môi trường.

## 4. Docker image

- Nền: `python:3.12-slim-bookworm` + uv (ghim đúng phiên bản uv trên máy). Dùng `uv.lock` và wheel có sẵn GDAL/PROJ.
- Python 3.12 thống nhất cho máy và Docker (`.python-version`, tạo bằng `uv python pin 3.12`).
- Multi-stage:
  - **builder:** `uv sync --locked --no-install-project --no-editable --extra geo --extra app` → copy `README.md`, `swatprep/`, `app/` → `uv sync --locked --no-editable ...`.
  - **runtime:** cài `libexpat1` (wheel rasterio cho Linux không kèm thư viện này; thiếu thì `import rasterio` lỗi `libexpat.so.1`), user không phải root (`swat`), copy `.venv` + `app/`, `EXPOSE 8501`, `HEALTHCHECK` gọi `/_stcore/health`, `CMD streamlit run app/Home.py --server.address=0.0.0.0`.
- `compose.yaml`: cổng `127.0.0.1:8501:8501`; bind mount `/data` (read-only) và `/workspace`; đường dẫn máy chủ lấy từ `.env` (bắt buộc, dùng `${VAR:?}`); `.env` nằm trong `.gitignore`.
- Đã kiểm chứng (2026-10-25): `swatprep --version` → 0.2.2; `whoami` → swat; driver `GTiff`, `AIG`, `ESRI Shapefile`, `GPKG` đều có trong container.

## 5. Thay đổi trong dự án hiện có

1. `pyproject.toml`: thêm extra `app = ["streamlit"]` (thư viện bản đồ/biểu đồ bổ sung ở Giai đoạn 4); thêm `app*` vào `packages.find`; chạy `uv lock`.
2. `swatprep/__init__.py`: `__version__` lấy từ `importlib.metadata` (hết lệch giữa 0.1.0 và 0.2.2).
3. `.gitignore`: thêm `!.streamlit/` (dòng `.*/` hiện đang loại thư mục này).
4. Thêm `.dockerignore`: `.git/`, `.venv/`, `.idea/`, `.agents/`, `.claude/`, `.codex/`, `.pytest_cache/`, `**/__pycache__/`, `*.egg-info/`, `dist/`, `output/`, `workspace/`, `data/`, `.env`.
5. `.gitignore`: thêm `.env`.

## 6. Kiểm thử và xử lý lỗi (Giai đoạn 1)

- `tests/ui/test_settings.py`: giá trị mặc định; đọc từ biến môi trường (dùng `monkeypatch`).
- `tests/ui/test_environment.py`: báo cáo có đủ các khóa; thư mục thiếu thì báo `ok=False` thay vì ném lỗi; thư mục không ghi được thì báo rõ.
- `get_report()` không bao giờ ném ngoại lệ: mỗi mục kiểm tra trả về `ok` + `detail`.
- Smoke test trong container: `swatprep --version` in `0.2.2`; in `get_report().drivers` và `get_report().folders`. (Chạy `pytest` trong image để sau — image runtime không chứa nhóm `dev` và `tests/`.)

## 7. Tiêu chí hoàn thành Giai đoạn 1

- [ ] `uv run pytest` qua toàn bộ test cũ và mới trên Windows.
- [ ] `uv run streamlit run app/Home.py` hiển thị báo cáo môi trường.
- [ ] `docker compose up --build` → `http://localhost:8501` hiển thị cùng báo cáo, các driver `GTiff`, `AIG`, `ESRI Shapefile`, `GPKG` đều ✅, `/data` đọc được, `/workspace` ghi được.
- [ ] Container chạy bằng user không phải root; `docker ps` báo `healthy`.

## Tham khảo

- uv – Using uv in Docker: https://docs.astral.sh/uv/guides/integration/docker/
- Docker – Multi-stage builds: https://docs.docker.com/build/building/multi-stage/
- Docker – Bind mounts: https://docs.docker.com/engine/storage/bind-mounts/
- Streamlit – Deploy using Docker: https://docs.streamlit.io/deploy/tutorials/docker
- The Twelve-Factor App – Config: https://12factor.net/config
- Freeman, S. & Pryce, N. (2009). *Growing Object-Oriented Software, Guided by Tests*. Addison-Wesley.
