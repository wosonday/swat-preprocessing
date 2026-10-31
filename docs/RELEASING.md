# Releasing swatprep — Docker image & CI

> Quy trình phát hành phiên bản mới của `swatprep` và image `ghcr.io/wosonday/swatprep`.
> Rút ra từ các lần phát hành 0.2.2 và 0.2.3 (10/2026).

---

## 1. Pipeline Overview

```
Pull Request ──► job "test"  (uv sync --locked + pytest trên ubuntu)
Push main ─────► job "test" ──pass──► job "image" ──► ghcr.io/wosonday/swatprep:latest
Push tag vX.Y.Z► job "test" ──pass──► job "image" ──► ghcr.io/wosonday/swatprep:X.Y.Z
```

- Workflow: `.github/workflows/ci.yml`.
- Image chỉ được publish khi job `test` qua (`needs: test`).
- `latest` thay đổi mỗi lần merge; `X.Y.Z` là bản cố định để tái lập kết quả.

**Nguyên tắc:** tên tag Git (`vX.Y.Z`) = tag image (`X.Y.Z`) = `version` trong `pyproject.toml` = `swatprep --version`.

---

## 2. Release Checklist

Mỗi 🛑 là điểm dừng: chỉ làm tiếp khi kết quả đúng như mô tả.

### 2.1. Nhánh phát hành

```bash
git switch main
git pull
git switch -c release/X.Y.Z
```

Sửa `version = "X.Y.Z"` trong `pyproject.toml` và dòng `VERSION="vX.Y.Z"` trong `scripts/install.bat`, `scripts/install.sh`, rồi:

```bash
uv lock
git diff
```

🛑 `git diff` chỉ có 4 thay đổi: `pyproject.toml`, dòng `version` của `swatprep` trong `uv.lock`, và `VERSION` trong hai script cài đặt.

```bash
uv sync --locked --extra geo --extra app --extra dev
uv run python -m pytest -q
uv run swatprep --version
```

🛑 Toàn bộ test qua và `swatprep, version X.Y.Z`.

```bash
git add pyproject.toml uv.lock scripts/install.bat scripts/install.sh
git commit -m "release: X.Y.Z"
git push -u origin release/X.Y.Z
```

### 2.2. Pull Request

Mở PR `release/X.Y.Z` → `main`, chờ job `test` ✅, merge.

🛑 Trang PR hiện **Merged**.

### 2.3. Tag trên `main` (chỉ sau khi đã merge)

```bash
git switch main
git pull
git log --oneline -1
uv run swatprep --version
```

🛑 `git pull` có kéo về thay đổi (không phải `Already up to date`), `git log` hiện commit merge của PR phát hành, `swatprep --version` là `X.Y.Z`.

```bash
git tag vX.Y.Z
git rev-parse --short vX.Y.Z
```

🛑 Commit in ra trùng với commit merge ở trên.

```bash
git push origin vX.Y.Z
```

### 2.4. Kiểm chứng image

Chờ lần chạy CI của tag `vX.Y.Z` trên tab **Actions** ✅ (cả `test` và `image`), rồi:

```bash
docker pull ghcr.io/wosonday/swatprep:X.Y.Z
docker run --rm ghcr.io/wosonday/swatprep:X.Y.Z swatprep --version
```

🛑 `Downloaded newer image` (digest mới) và `swatprep, version X.Y.Z`.

---

## 3. Running the App (người dùng)

### 3.1. Không cần Docker (khuyến nghị cho nhóm)

Xem `docs/INSTALL.md`: tải `scripts/install.bat` (Windows) hoặc `scripts/install.sh` (Linux/macOS), chạy một lần; sau đó mở bằng biểu tượng *SWATprep*. Chạy lại script để cập nhật lên phiên bản ghi trong script.

### 3.2. Bằng Docker image

Image có sẵn `SWATPREP_DATA_ROOT=/data` và `SWATPREP_WORKSPACE=/workspace`.

```bash
docker run --rm -p 127.0.0.1:8501:8501 \
  -v "/đường/dẫn/data:/data:ro" \
  -v "/đường/dẫn/workspace:/workspace" \
  ghcr.io/wosonday/swatprep:X.Y.Z
```

Mở `http://localhost:8501`. Đổi cổng máy bằng số bên trái của `-p` (ví dụ `127.0.0.1:8080:8501`).

Người phát triển dùng `uv run swatprep-ui` (hoặc `docker compose up --build` để kiểm tra image) (đường dẫn và cổng lấy từ `.env`, mẫu ở `.env.example`).

---

## 4. Known Pitfalls

| Triệu chứng | Nguyên nhân | Cách nhận biết / xử lý |
|---|---|---|
| Image `X.Y.Z` in ra phiên bản cũ | Tag gắn vào commit **trước khi** PR phát hành được merge | `git rev-parse --short vX.Y.Z` khác commit merge. Xoá tag (`git tag -d vX.Y.Z`, `git push origin --delete vX.Y.Z`) rồi tag lại sau khi merge |
| `docker pull` báo `Image is up to date` với digest cũ | Pull trước khi CI build xong | Chờ tab Actions ✅; so digest với trang Packages |
| `docker pull` báo `denied` | Image chưa tồn tại (CI chưa chạy/thất bại) hoặc package đang Private | Kiểm tra tab Actions và visibility của package |
| CI/Docker lỗi `--locked` | Sửa `version` trong `pyproject.toml` nhưng chưa `uv lock` | Luôn chạy `uv lock` sau khi sửa `pyproject.toml` |
| Workflow không chạy | `.gitignore` chặn `.github/` | `git check-ignore -v .github/workflows/ci.yml` phải không in gì |
| Lỗi lọt vào `main` | Merge PR khi `test` đỏ | Bật ruleset: *Require status checks* → `test` |
| `failed to connect to the docker API` (Windows) | Docker Desktop chưa chạy | Mở Docker Desktop, chờ *Engine running* |

---

## 5. Versioning

Theo [Semantic Versioning 2.0.0](https://semver.org/):

- **PATCH** (`0.2.2 → 0.2.3`): sửa lỗi, thay đổi nhỏ tương thích ngược (ví dụ thêm `ENV` mặc định).
- **MINOR** (`0.2.x → 0.3.0`): thêm tính năng tương thích ngược (ví dụ trang Build trong UI).
- **MAJOR**: thay đổi phá vỡ tương thích (định dạng config, output).

Không sửa hoặc xoá tag đã có người sử dụng; phát hành bản mới thay vì ghi đè.
