# Tài liệu ôn tập: tối ưu `swatprep` (fill NetCDF, chọn ô lưới, xử lý raster lớn)

*Soạn ngày 22/10/2026 cho dự án `swat-preprocessing`. Mọi đoạn mã trong tài liệu được nhúng tự động từ kho mã và các script kiểm thử thật, không chép tay.*

## 0. Cách sử dụng tài liệu

Tài liệu trả lời lần lượt: (1) đã đổi gì, (2) vì sao đổi, (3) các hàm liên kết với nhau như thế nào, (4) đã kiểm thử bằng mã nào, và (5) rút ra bài học gì cho các dự án sau. Mỗi vấn đề được trình bày theo cùng một khung để dễ ôn:

> **Triệu chứng → Nguyên nhân → Mục tiêu → Giải pháp → Ví dụ số liệu → Kiểm thử**

Khuyến nghị học theo thứ tự: Mục 1 (bản đồ hàm) → Mục 3 (từng thay đổi) → Mục 5 (bài tập tự kiểm tra).

---

## 1. Bản đồ cấu trúc: các hàm liên kết với nhau như thế nào

### 1.1 Nguyên tắc thiết kế (nhớ 4 ý)

1. **YAML là hợp đồng**: cấu hình được kiểm tra bằng Pydantic (`config.py`) ngay khi đọc, trước khi xử lý dữ liệu.
2. **Tách ba tầng**: `core/*` (xử lý, trả về *Result + danh sách QACheck*), `writers/*` (ghi file), `converters/*` (chuyển định dạng). Tầng `core` không ghi file.
3. **"Tiền tệ chung" của thời tiết** là `WeatherResult.daily`: từ điển `{biến → DataFrame(ngày × mã trạm)}`. Mọi nguồn (CSV, NetCDF) đều phải trả về đúng dạng này, nên bộ điền khuyết không cần biết dữ liệu đến từ đâu.
4. **QACheck thay cho ngoại lệ** ở những lỗi chấp nhận được: mỗi kiểm tra có `status` là `pass`, `warn` hoặc `fail`. Chỉ lỗi cấu hình/đầu vào hỏng nặng mới ném `SWATPrepError`.

### 1.2 Lệnh `swatprep fill weather` (có NetCDF)

```
cli.fill_weather                      (nhận cờ CLI)
 └─ fill_setup.resolve_fill_inputs    (gộp: CLI > YAML weather.fill > mặc định; kiểm tra bằng Pydantic)
     ├─ config.WeatherConfig / WeatherFillConfig / FillNetCDFConfig   (có search_radius)
     └─ fill_setup._build_source  ──►  NetCDFFillSource | CsvFillSource      (giao thức FillSource.load)
 └─ core.weather_fill.WeatherGapFiller.run
     ├─ WeatherPreprocessor(real_cfg).run()        → dữ liệu thực đo (daily + stations)
     ├─ fill_source.load(stations, index, variables)
     │    └─ NetCDFFillSource.load
     │         ├─ _axis_name      tìm trục lat/lon/time
     │         ├─ _match_lon      đưa kinh độ trạm về quy ước của lưới
     │         ├─ _nearest        ô gần nhất theo từng trục (+ kiểm tra "trong lưới")
     │         ├─ _candidates     các ô lân cận, sắp từ gần đến xa
     │         ├─ (đọc hộp bao MỘT lần: isel(box) → ndarray)
     │         └─ _first_valid    ô đầu tiên có dữ liệu ở mọi biến
     └─ _correct_and_fill   (mỗi trạm × biến: hiệu chỉnh ratio/offset rồi chỉ điền ngày thiếu)
 └─ writers.weather_fill.WeatherFillWriter.write   → CSV đã điền + fill_report.csv
```

### 1.3 Lệnh `swatprep build` (phần raster đã đổi)

```
cli.build → api.SWATPrepProject.build
   ├─ core.dem.DEMPreprocessor.run        → utils.raster.masked_stats   (đọc theo dải)
   ├─ core.landuse.LandUsePreprocessor    → utils.raster.unique_codes   (đọc theo dải)
   └─ core.soil.SoilPreprocessor          → utils.raster.unique_codes
                  utils.raster.unique_codes / masked_stats ─► iter_strips (sinh các Window theo hàng)
```

### 1.4 Lệnh mới `swatprep clip`

```
cli.clip → utils.raster.clip_raster
            ├─ geopandas.read_file + to_crs(CRS của raster)    (đưa ranh giới về CRS raster)
            ├─ tính cửa sổ (cột/hàng) từ hộp bao ranh giới
            └─ ghi từng dải: src.read(window) → [che ngoài đa giác nếu --mask] → dst.write(window)
```

Lệnh `clip` độc lập với `build`: chạy trước một lần, rồi trỏ `dem.path`, `landuse.raster`, `soil.raster` vào file đã cắt.

---

## 2. Tóm tắt thay đổi

| # | Tệp | Thay đổi | Lý do ngắn gọn |
|---|---|---|---|
| 1 | `swatprep/core/fill_sources.py` | Đọc **hộp bao** của các ô một lần, rồi chọn ô từng trạm bằng NumPy | Việc chọn điểm kiểu vector buộc giải nén lại mọi chunk theo thời gian cho từng ô: chậm khoảng 20–40 lần trên dữ liệu đo được |
| 2 | `swatprep/core/fill_sources.py` | `_match_lon` chỉ đổi kinh độ khi cần; `_nearest` làm tròn khoảng cách; thêm `_candidates`, `_first_valid` | Sai số dấu phẩy động làm trạm nằm giữa hai ô chọn nhầm ô biển (toàn NaN) |
| 3 | `swatprep/config.py`, `fill_setup.py`, `cli.py` | Thêm `search_radius` (YAML) và `--fill-search-radius` (CLI) | Cho phép tìm ô lân cận có dữ liệu; `0` giữ hành vi "chỉ ô gần nhất" |
| 4 | `swatprep/utils/raster.py` | Thêm `iter_strips`, `masked_stats`, `unique_codes`; `read_unique_codes` dùng lại | Không đọc cả raster vào RAM (DEM 17,4 tỷ điểm ảnh gây `MemoryError`) |
| 5 | `swatprep/core/dem.py`, `landuse.py`, `soil.py` | Gọi các hàm đọc theo dải thay cho `ds.read(...)` | Cùng lý do trên; kết quả giữ nguyên |
| 6 | `swatprep/utils/raster.py`, `cli.py` | Thêm `clip_raster` và lệnh `swatprep clip` | Cắt raster về vùng lưu vực trước khi xử lý |
| 7 | `tests/*` | +35 test mới; sửa `test_api` | Khóa hành vi mới; sửa kỳ vọng cũ sai (`ST001.pcp` → `StationA.pcp`) |
| 8 | `utils/raster.py`, `dem.py`, `landuse.py`, `soil.py`, `api.py` | `build` chỉ đọc cửa sổ của `project.boundary` | Trước đó mỗi lần `build` quét 54,6 tỷ điểm ảnh dù lưu vực rất nhỏ |
| 9 | `config.py`, `core/clip.py`, `api.py`, `cli.py` | Mục `clip:` trong YAML (chỉ cần `src`, `dst`) | Cắt và xuất raster ngay trong `build` |
| 10 | `core/clip.py`, `config.py`, `core/landuse.py`, `core/soil.py`, `api.py` | `build` cắt raster và lọc bảng cùng lúc vào `output_dir` (`clip: true` mặc định) | Một lần chạy, một thư mục đầu ra |
| 11 | `README.md`, `TESTING_GUIDE.md` | Ghi chú NetCDF, `search_radius`, `clip`, ranh giới, số test | Tài liệu đồng bộ |

Kết quả kiểm thử toàn bộ: trước khi sửa **162 đạt, 1 lỗi** (lỗi có sẵn ở `test_api`); sau khi sửa **198 đạt** (khi đã cài `geopandas`); khi chưa có `geopandas`, các test dùng `geopandas` được bỏ qua.

---

## 3. Từng thay đổi chi tiết

### 3.1 Vì sao `fill` chậm, và cách sửa (hộp bao)

**Triệu chứng.** `swatprep fill weather` với NetCDF 1980–2014 (12.784 ngày, lưới 161 × 121) chạy rất lâu.

**Nguyên nhân (đã đo, không đoán).** File lưu mỗi ngày là một khối (chunk) `[1, 161, 121]`, nén zlib mức 9. Lưu như vậy rất tốt để lấy *bản đồ một ngày* nhưng tệ nhất để lấy *chuỗi thời gian tại một ô*, vì mỗi ngày phải giải nén cả khối 161 × 121 chỉ để lấy một giá trị. Mã cũ chọn điểm kiểu vector (`isel` với `DataArray` có chiều `station`). Với bộ nhớ đệm chunk của HDF5 có hạn, mỗi ô khác nhau lại giải nén lại toàn bộ các khối theo thời gian. Phép đo cho thấy thời gian không tăng đều mà **tăng vọt** khi số ngày vượt khoảng 730:

| Số ngày đọc | 365 | 730 | 1.460 | 2.920 |
|---|---|---|---|---|
| Thời gian (file thật, 1 biến) | 0,09 s | 0,12 s | 11,4 s | 23,2 s |

Trên file thật, cách cũ cần khoảng **95 giây cho mỗi biến** (đo trực tiếp: precip 95,0 s, tmax 94,5 s), tức khoảng 4,8 phút cho ba biến.

**Mục tiêu.** Giữ nguyên kết quả, nhưng mỗi khối nén chỉ giải nén **một lần**.

**Giải pháp.** Đọc một lần "hộp bao" (khối chữ nhật nhỏ chứa mọi ô cần), đưa vào mảng NumPy `(thời gian, vĩ độ, kinh độ)`, rồi chọn ô từng trạm bằng chỉ số NumPy trong bộ nhớ. Cắt hộp bao gồm cả các ô ứng viên lân cận (mục 3.2).

*Đoạn mã đọc hộp bao trong phiên bản mới:*

```python
def load(self, stations, index, variables):
    try:
        import xarray as xr
    except ImportError as e:
        raise InputValidationError(
            "NetCDF fill source needs xarray: pip install 'swatprep[nc]'"
        ) from e

    cfg, qa = self.cfg, []
    no_map = [v for v in variables if v not in cfg.var_map]
    if no_map:
        raise InputValidationError(
            f"weather.fill.netcdf.var_map has no entry for: {', '.join(no_map)}"
        )

    with xr.open_dataset(cfg.path) as ds:
        lat_n = _axis_name(ds, cfg.lat_name, _LAT_CANDIDATES, "lat_name")
        lon_n = _axis_name(ds, cfg.lon_name, _LON_CANDIDATES, "lon_name")
        time_n = _axis_name(ds, cfg.time_name, _TIME_CANDIDATES, "time_name")
        missing = [n for v in variables if (n := cfg.var_map[v]) not in ds.data_vars]
        if missing:
            raise InputValidationError(
                f"NetCDF variable(s) not found: {', '.join(missing)}. "
                f"Available: {', '.join(ds.data_vars)}"
            )
        if ds[time_n].dtype.kind != "M":
            raise InputValidationError(
                "NetCDF time axis uses a non-standard calendar; "
                "convert it to a standard (Gregorian) daily calendar first."
            )

        glat = np.asarray(ds[lat_n].values, float)
        glon = np.asarray(ds[lon_n].values, float)
        lats = stations["lat"].to_numpy(float)
        lons = _match_lon(stations["lon"].to_numpy(float), glon)
        ilat, ok_lat = _nearest(glat, lats)
        ilon, ok_lon = _nearest(glon, lons)
        ok = ok_lat & ok_lon
        for sid in stations.index[~ok]:
            qa.append(QACheck(
                name=f"netcdf_extract:{sid}:outside_grid", status="warn",
                message=f"{sid}: station is outside the NetCDF grid, no fill source",
            ))
        if not ok.any():
            raise InputValidationError("No station lies inside the NetCDF grid.")

        ids = list(stations.index[ok])
        cands = [
            _candidates(glat, glon, la, lo, i, j, cfg.search_radius)
            for la, lo, i, j in zip(lats[ok], lons[ok], ilat[ok], ilon[ok])
        ]
        # Đọc MỘT lần hộp bao của mọi ô ứng viên (ít lần giải nén chunk),
        # sau đó chọn ô từng trạm bằng NumPy.
        rc = np.array([c for cs in cands for c in cs])
        i0, j0 = int(rc[:, 0].min()), int(rc[:, 1].min())
        box = {
            lat_n: slice(i0, int(rc[:, 0].max()) + 1),
            lon_n: slice(j0, int(rc[:, 1].max()) + 1),
        }
        slabs = {
            v: ds[cfg.var_map[v]].isel(box).transpose(time_n, lat_n, lon_n).values
            for v in variables
        }
        times = pd.DatetimeIndex(ds[time_n].values).normalize()

        kept, cells = [], []
        for sid, cs in zip(ids, cands):
            cell = _first_valid(cs, slabs, i0, j0)
            if cell is None:
                qa.append(QACheck(
                    name=f"netcdf_extract:{sid}:no_valid_cell", status="warn",
                    message=f"{sid}: no cell with data within {cfg.search_radius} "
                            "cell(s) of the station, no fill source",
                ))
                continue
            if cell != cs[0]:
                qa.append(QACheck(
                    name=f"netcdf_extract:{sid}:neighbor_cell", status="warn",
                    message=f"{sid}: nearest cell has no data; used cell "
                            f"(lat={glat[cell[0]]:g}, lon={glon[cell[1]]:g}) instead",
                    context={"nearest": [int(x) for x in cs[0]],
                             "used": [int(x) for x in cell]},
                ))
            kept.append(sid)
            cells.append(cell)
        if not kept:
            raise InputValidationError(
                "No station has a NetCDF cell with data; check the grid or search_radius."
            )

        daily: dict[str, pd.DataFrame] = {}
        for var in variables:
            arr = np.stack([slabs[var][:, i - i0, j - j0] for i, j in cells], axis=1)
            df = pd.DataFrame(arr, index=times, columns=kept)
            df = df[~df.index.duplicated(keep="first")]
            daily[var] = df.reindex(index)

    qa.append(QACheck(
        name="netcdf_loaded", status="pass",
        message=f"NetCDF fill source: {len(kept)} station(s), "
                f"variables: {', '.join(variables)}",
    ))
    return daily, qa
```

Ba đoạn then chốt trong hàm trên: (1) `box = {...}` xác định hộp bao từ **mọi** ô ứng viên; (2) `slabs = {...}` đọc hộp bao **một lần cho mỗi biến** (`.isel(box)...values` là thời điểm duy nhất chạm vào đĩa); (3) `np.stack([slabs[var][:, i - i0, j - j0] ...])` chọn cột từng trạm trong bộ nhớ, trừ `i0, j0` để đổi từ chỉ số lưới sang chỉ số trong hộp.

*Phiên bản cũ (để đối chiếu):*

```python
def load(self, stations, index, variables):
    try:
        import xarray as xr
    except ImportError as e:
        raise InputValidationError(
            "NetCDF fill source needs xarray: pip install 'swatprep[nc]'"
        ) from e

    cfg, qa = self.cfg, []
    no_map = [v for v in variables if v not in cfg.var_map]
    if no_map:
        raise InputValidationError(
            f"weather.fill.netcdf.var_map has no entry for: {', '.join(no_map)}"
        )

    with xr.open_dataset(cfg.path) as ds:
        lat_n = _axis_name(ds, cfg.lat_name, _LAT_CANDIDATES, "lat_name")
        lon_n = _axis_name(ds, cfg.lon_name, _LON_CANDIDATES, "lon_name")
        time_n = _axis_name(ds, cfg.time_name, _TIME_CANDIDATES, "time_name")
        missing = [n for v in variables if (n := cfg.var_map[v]) not in ds.data_vars]
        if missing:
            raise InputValidationError(
                f"NetCDF variable(s) not found: {', '.join(missing)}. "
                f"Available: {', '.join(ds.data_vars)}"
            )
        if ds[time_n].dtype.kind != "M":
            raise InputValidationError(
                "NetCDF time axis uses a non-standard calendar; "
                "convert it to a standard (Gregorian) daily calendar first."
            )

        ilat, ok_lat = _nearest(ds[lat_n].values, stations["lat"].to_numpy(float))
        grid_lon = ds[lon_n].values
        ilon, ok_lon = _nearest(
            grid_lon, _match_lon(stations["lon"].to_numpy(float), grid_lon)
        )
        ok = ok_lat & ok_lon
        for sid in stations.index[~ok]:
            qa.append(QACheck(
                name=f"netcdf_extract:{sid}:outside_grid", status="warn",
                message=f"{sid}: station is outside the NetCDF grid, no fill source",
            ))
        if not ok.any():
            raise InputValidationError("No station lies inside the NetCDF grid.")

        sel = {
            lat_n: xr.DataArray(ilat[ok], dims="station"),
            lon_n: xr.DataArray(ilon[ok], dims="station"),
        }
        times = pd.DatetimeIndex(ds[time_n].values).normalize()
        daily: dict[str, pd.DataFrame] = {}
        for var in variables:
            arr = ds[cfg.var_map[var]].isel(sel).transpose(time_n, "station").values
            df = pd.DataFrame(arr, index=times, columns=stations.index[ok])
            df = df[~df.index.duplicated(keep="first")]
            daily[var] = df.reindex(index)

    qa.append(QACheck(
        name="netcdf_loaded", status="pass",
        message=f"NetCDF fill source: {int(ok.sum())} station(s), "
                f"variables: {', '.join(variables)}",
    ))
    return daily, qa
```

**Ví dụ số liệu.**

| | Cũ | Mới |
|---|---|---|
| Trích 1 biến, 11 trạm, toàn bộ 12.784 ngày | khoảng 95 s | vài giây (cả 3 biến: khoảng 4–6 s) |
| Cả lệnh `fill weather` (đọc CSV + trích + hiệu chỉnh + ghi) | vài phút | **10,9 s**, bộ nhớ đỉnh **437 MB** |

Bản tái hiện độc lập (dữ liệu giả lập, cùng chunk `[1, lat, lon]` + zlib mức 9, 3.000 ngày):

| Số ngày | A: chọn điểm vector (cũ) | B: hộp bao (mới) | Kết quả giống nhau |
|---|---|---|---|
| 365 | 0,13 s | 0,00 s | có |
| 730 | 0,15 s | 0,00 s | có |
| 1.460 | **17,21 s** | 0,43 s | có |
| 2.920 | **39,03 s** | 0,98 s | có |

**Giới hạn cần nhớ.** Bộ nhớ của hộp bao là `số ngày × số vĩ độ × số kinh độ × 4 byte × số biến`. Với lưu vực nhỏ, giá trị này chỉ vài MB. Nếu các trạm trải khắp cả lưới 161 × 121, mỗi biến khoảng 1 GB, và khi đó nên đọc theo từng năm.

**Kiểm thử.** `test_bounding_box_read_equals_pointwise_selection` so sánh giá trị đọc theo hộp bao với phép chọn điểm của xarray; `test_extracts_nearest_cell_per_station` khóa kết quả theo từng ô.

### 3.2 Chọn ô lưới: lỗi trạm CUAONG và cách khắc phục

**Triệu chứng.** Trạm CUAONG không được fill (tmax thiếu 49% và không điền được).

**Nguyên nhân (chuỗi nguyên nhân, từ gốc đến ngọn).**

1. CUAONG ở kinh độ 107,35°, đúng giữa hai ô 107,3° và 107,4° (lưới 0,1°), nên khoảng cách tới hai ô **bằng nhau**.
2. Hàm cũ `_match_lon` luôn tính `(lon + 180) % 360 - 180`. Phép này cộng 180, trừ 180 và gây sai số dấu phẩy động: `107.35` thành `107.35000000000002` (xem Goldberg, 1991). Sai số nhỏ này đủ để lệch về ô 107,4.
3. Ô 107,4° nằm ở biển nên **toàn NaN**; ô 107,3° là đất liền, có dữ liệu bình thường.
4. Mã cũ chỉ lấy *một* ô gần nhất, không kiểm tra có dữ liệu hay không, nên không có gì để fill.

**Mục tiêu.** (a) Không tự gây sai số khi đổi quy ước kinh độ; (b) quy tắc hòa phải xác định và có thể giải thích; (c) nếu ô gần nhất không có dữ liệu thì dùng ô lân cận có dữ liệu và **báo cho người dùng**.

**Giải pháp.** Ba hàm hỗ trợ và một tham số cấu hình:

```python
def _match_lon(lons: np.ndarray, grid_lon: np.ndarray) -> np.ndarray:
    """Đưa kinh độ trạm về quy ước của lưới; chỉ đổi khi cần (tránh sai số 107.35 -> ...02)."""
    lons = np.asarray(lons, float)
    if np.nanmax(grid_lon) > 180:                    # lưới 0-360
        return np.where(lons < 0, lons + 360.0, lons)
    return np.where(lons > 180, lons - 360.0, lons)  # lưới -180..180
```

```python
def _nearest(grid: np.ndarray, coords: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Chỉ số ô gần nhất; và True nếu cách ô đó không quá một bước lưới."""
    grid = np.asarray(grid, float)
    # Làm tròn khoảng cách để các trường hợp hoà (trạm đúng giữa 2 ô) luôn về ô chỉ số thấp hơn,
    # không phụ thuộc nhiễu dấu phẩy động ~1e-14.
    idx = np.round(np.abs(grid[:, None] - coords[None, :]), 9).argmin(axis=0)
    step = np.median(np.abs(np.diff(grid))) if grid.size > 1 else np.inf
    return idx, np.abs(grid[idx] - coords) <= step
```

```python
def _candidates(glat, glon, lat, lon, ci, cj, radius):
    """(i, j) các ô trong ±radius quanh ô (ci, cj), xếp từ gần trạm nhất đến xa nhất."""
    ii = np.arange(max(ci - radius, 0), min(ci + radius, glat.size - 1) + 1)
    jj = np.arange(max(cj - radius, 0), min(cj + radius, glon.size - 1) + 1)
    dlat = (glat[ii] - lat)[:, None]
    dlon = (glon[jj] - lon)[None, :] * np.cos(np.radians(lat))
    order = np.argsort(np.round(dlat**2 + dlon**2, 12).ravel(), kind="stable")
    return [(int(ii[k // jj.size]), int(jj[k % jj.size])) for k in order]
```

```python
def _first_valid(cands, slabs, i0, j0):
    """Ô đầu tiên có ít nhất một giá trị hữu hạn ở MỌI biến; None nếu không có."""
    for i, j in cands:
        if all(np.isfinite(s[:, i - i0, j - j0]).any() for s in slabs.values()):
            return i, j
    return None
```

Giải thích từng ý:

- `_match_lon` chỉ cộng/trừ 360 **khi thật sự cần** (lưới 0–360 mà kinh độ âm, hoặc ngược lại). Với `107.35` trên lưới −180..180, giá trị được giữ nguyên, bit-by-bit.
- `_nearest` làm tròn khoảng cách đến 9 chữ số thập phân trước khi `argmin`. Khi hai ô cách đều (trạm đúng giữa), kết quả luôn là ô có **chỉ số thấp hơn**, không phụ thuộc nhiễu 1e-14.
- `_candidates` liệt kê các ô trong ±`search_radius` ô quanh ô gần nhất, xếp từ gần trạm nhất đến xa nhất. Khoảng cách kinh độ được nhân `cos(vĩ độ)` để xấp xỉ khoảng cách thực.
- `_first_valid` lấy ô đầu tiên có **ít nhất một giá trị hữu hạn ở mọi biến**; không có thì trả `None`.

Khi ô gần nhất bị bỏ qua, hệ thống thêm cảnh báo `netcdf_extract:<trạm>:neighbor_cell` (ghi cả hai chỉ số ô). Nếu không có ô nào hợp lệ trong bán kính, trạm bị bỏ khỏi nguồn fill kèm cảnh báo `no_valid_cell`.

Tham số mới:

```yaml
weather:
  fill:
    netcdf:
      path: D:/DATA/OBS.nc
      var_map: { precip: pr, tmax: tasmax, tmin: tasmin }
      search_radius: 1        # 0 = chỉ ô gần nhất; 1..5 = tìm ô lân cận có dữ liệu
```

Tương đương CLI: `--fill-search-radius 1`.

**Ví dụ số liệu thật (Chu basin).** Bốn trạm nằm đúng giữa hai ô lưới, nên ô được chọn thay đổi so với lần chạy trước:

| Trạm | Kinh độ | Ô cũ | Ô mới | Ghi chú |
|---|---|---|---|---|
| HUULUNG | 106,350 | 106,4 | 106,3 | cả hai đều có dữ liệu |
| LUCNGAN | 106,550 | 106,6 | 106,5 | cả hai đều có dữ liệu |
| SONDONG | 106,850 | 106,9 | 106,8 | cả hai đều có dữ liệu |
| CUAONG | 107,350 | 107,4 (biển, NaN) | 107,3 (đất liền) | từ **không fill được** sang fill được 7.007 ngày tmax |

Bảy trạm còn lại có kết quả **giống hệt** cách cũ (so sánh từng giá trị, kể cả NaN). Với bốn trạm trên, việc chọn ô nào ở mức hòa không có ý nghĩa vật lý; quy tắc mới chỉ làm kết quả có thể lặp lại. Vì vậy cần **chạy lại `fill weather` và `build`** để làm mới dữ liệu đã tạo trước đó.

**Kiểm thử.**

- `test_tied_station_with_nan_cell_falls_back_to_valid_neighbor`: trạm giữa hai ô, ô gần nhất toàn NaN → dùng ô bên cạnh, có cảnh báo `neighbor_cell`.
- `test_search_radius_zero_does_not_look_at_neighbors`: `search_radius=0` thì không tìm ô lân cận.
- `test_valid_nearest_cell_gives_no_neighbor_warning`: ô gần nhất hợp lệ thì không cảnh báo.
- `test_match_lon_changes_only_what_is_needed`: `107.35` giữ nguyên, quy đổi 0–360 vẫn đúng.
- `test_exact_midpoint_tie_goes_to_lower_index_cell`: quy tắc hòa.

Đã xác nhận các test này **thật sự phân biệt** mã cũ và mới: chạy chúng trên mã cũ thì 3 test thất bại.

### 3.3 Raster lớn: đọc theo dải thay vì nạp toàn bộ

**Triệu chứng.** `swatprep build` ném `MemoryError: Unable to allocate 16.2 GiB` trong `dem.py`.

**Nguyên nhân.** `ds.read(1, masked=True)` nạp **cả** raster (17,4 tỷ điểm ảnh) vào RAM; `landuse.py` và `soil.py` cũng gọi `ds.read(1)` rồi `flatten().tolist()`, càng tốn thêm.

**Mục tiêu.** Bộ nhớ tối đa không phụ thuộc kích thước raster, kết quả không đổi.

**Giải pháp.** Đọc theo các dải hàng (rasterio `Window`) có kích thước giới hạn bởi `max_pixels` (mặc định 16 triệu điểm ảnh, khoảng 32 MB với int16), cộng dồn thống kê qua từng dải:

```python
def iter_strips(ds, max_pixels: int = 16_000_000, window=None):
    """Yield row strips (rasterio Windows) of at most ~max_pixels each.

    Covers the whole raster, or only `window` when given. Lets big rasters be
    processed with bounded memory instead of ds.read().
    """
    from rasterio.windows import Window

    w = window or Window(0, 0, ds.width, ds.height)
    width, height = int(w.width), int(w.height)
    rows = max(1, max_pixels // width)
    for row in range(0, height, rows):
        yield Window(int(w.col_off), int(w.row_off) + row, width, min(rows, height - row))
```

```python
def masked_stats(ds, band: int = 1, max_pixels: int = 16_000_000, window=None):
    """(min, max, mean, n_valid) of valid (non-NoData) pixels, streamed by strips."""
    vmin, vmax, total, count = np.inf, -np.inf, 0.0, 0
    for win in iter_strips(ds, max_pixels, window):
        data = ds.read(band, window=win, masked=True)
        n = int(data.count())
        if n:
            vmin = min(vmin, float(data.min()))
            vmax = max(vmax, float(data.max()))
            total += float(data.sum(dtype="float64"))
            count += n
    return (vmin, vmax, total / count, count) if count else (None, None, None, 0)
```

```python
def unique_codes(ds, band: int = 1, max_pixels: int = 16_000_000, window=None) -> set:
    """Unique valid (non-NoData) pixel values, streamed by strips."""
    codes: set = set()
    for win in iter_strips(ds, max_pixels, window):
        data = ds.read(band, window=win, masked=True)
        codes.update(np.unique(data.compressed()).tolist())
    return codes
```

Điểm mấu chốt của `masked_stats`: **không giữ mảng**, chỉ giữ bốn số (`min`, `max`, tổng, số điểm hợp lệ) và tính trung bình ở cuối; tổng cộng dồn bằng `float64` để tránh tràn/làm tròn.

Chỗ gọi trong `dem.py` (trước và sau):

```python
# Trước
data = ds.read(1, masked=True)
if data.count() == 0: ...
elev_min = float(data.min()); elev_max = float(data.max()); elev_mean = float(data.mean())

# Sau
elev_min, elev_max, elev_mean, n_valid = masked_stats(ds)
if n_valid == 0: ...
```

**Ví dụ số liệu** (raster giả lập 50.000 × 50.000 int16, nén; nạp hết cần 4,66 GiB):

| | Cũ | Mới |
|---|---|---|
| Kiểm tra DEM | `MemoryError: Unable to allocate 4.66 GiB` (giới hạn 3 GB bộ nhớ ảo) | thành công, **7,7 s**, bộ nhớ đỉnh **412 MB** |

Thời gian tăng gần tuyến tính theo số điểm ảnh; với DEM thật 17,4 tỷ điểm ảnh, ước tính vài phút tùy tốc độ đĩa (đây là ước lượng, chưa đo trên DEM thật).

**Kiểm thử** (`tests/test_raster_utils.py`): `test_iter_strips_cover_every_row_exactly_once` (mỗi hàng được đọc đúng một lần), `test_masked_stats_streamed_equals_full_read` (kết quả theo dải = đọc toàn bộ, thử nhiều kích thước dải), `test_masked_stats_all_nodata_returns_zero_count`, `test_unique_codes_streamed_excludes_nodata`.

### 3.4 Cắt raster theo ranh giới (`clip_raster` và `swatprep clip`)

**Mục tiêu.** Cắt DEM/land-use/soil về vùng lưu vực trước khi xử lý để mọi bước sau chạy nhanh và nhẹ; đồng thời không cần công cụ GDAL dòng lệnh bên ngoài.

**Giải pháp.** `rasterio` là lớp Python bọc GDAL, nên cắt cửa sổ thực chất là một thao tác của GDAL. Hàm mới:

```python
def clip_raster(
    src_path: Path,
    dst_path: Path,
    boundary_path: Path,
    mask: bool = False,
    max_pixels: int = 16_000_000,
) -> Path:
    """Crop a raster to the boundary's bounding box (optionally mask outside the polygons).

    The boundary is reprojected to the raster CRS. Only the needed window is read,
    strip by strip, so memory stays bounded even for very large rasters.
    No resampling or reprojection of the raster itself is done.
    """
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.windows import Window

    src_path, dst_path = Path(src_path), Path(dst_path)
    with rasterio.open(src_path) as src:
        if src.crs is None:
            raise InputValidationError(f"Raster has no CRS, cannot clip: {src_path}")
        if mask and src.nodata is None:
            raise InputValidationError("mask=True needs a raster with a NoData value")
        gdf = _read_boundary(boundary_path, src.crs)
        c0, r0, width, height = _window_of(src, gdf.total_bounds)
        profile = src.profile.copy()
        profile.update(
            driver="GTiff", width=width, height=height, tiled=True,
            blockxsize=256, blockysize=256, compress="deflate", BIGTIFF="IF_SAFER",
            transform=src.window_transform(Window(c0, r0, width, height)),
        )
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        step = max(1, max_pixels // width)
        with rasterio.open(dst_path, "w", **profile) as dst:
            for row in range(0, height, step):
                h = min(step, height - row)
                win = Window(c0, r0 + row, width, h)
                data = src.read(window=win)
                if mask:
                    inside = geometry_mask(
                        gdf.geometry, out_shape=(h, width),
                        transform=src.window_transform(win), invert=True,
                    )
                    data[:, ~inside] = src.nodata
                dst.write(data, window=Window(0, row, width, h))
    return dst_path
```

Các quyết định thiết kế quan trọng:

- Ranh giới được đưa về CRS của raster (`to_crs`), **không** đổi raster, nên không cần resample và không mất giá trị gốc.
- Cửa sổ tính từ `total_bounds`, làm tròn **ra ngoài** (`floor`/`ceil`) để không mất điểm ảnh biên; được giới hạn trong phạm vi raster.
- Không dùng `rasterio.mask.mask(crop=True)` vì hàm đó đọc cả vùng cắt vào RAM; ở đây đọc/ghi theo dải.
- `mask=True` đặt giá trị NoData cho điểm ảnh ngoài đa giác (yêu cầu raster có NoData). Mặc định chỉ cắt theo hộp bao, đủ dùng khi ranh giới là hình chữ nhật (như `ht_chu_boudingbox.shp`).
- Đầu ra GeoTIFF có xếp ô (`tiled`) và nén `deflate`, `BIGTIFF=IF_SAFER`.

Cách dùng:

```bash
swatprep clip DEM.tif boundary.shp DEM_clip.tif
swatprep clip LANDUSE.tif boundary.shp LU_clip.tif --mask
```

**Ví dụ số liệu.** Cắt cửa sổ 500 × 500 từ raster 50.000 × 50.000: **0,24 s**, bộ nhớ đỉnh 162 MB.

**Kiểm thử.** `test_clip_bbox_crops_expected_window` (đúng cửa sổ, đúng `transform`), `test_clip_is_identical_when_strips_are_small` (dải nhỏ cho kết quả giống hệt), `test_clip_reprojects_boundary_to_raster_crs` (ranh giới ở EPSG:4326), `test_clip_mask_sets_pixels_outside_polygon_to_nodata`, `test_clip_outside_extent_raises`, `test_clip_accepts_plain_string_paths`, và hai test CLI.

**Việc chưa làm (nêu rõ để không hiểu nhầm).** `clip` không đổi CRS của raster. Nếu DEM khác `project.crs`, hiện chỉ có cảnh báo `dem_crs_mismatch`; cần `gdalwarp -t_srs EPSG:32648` hoặc `rasterio.warp` để chiếu lại. `copy_raster` và `reclassify_raster` vẫn đọc cả raster nhưng pipeline hiện chưa gọi chúng.

### 3.5 `build` vẫn chậm: quét toàn bộ raster dù lưu vực rất nhỏ

**Triệu chứng.** Sau khi đã đọc theo dải (mục 3.3), `swatprep build` cho dự án Chu basin vẫn rất chậm.

**Nguyên nhân (đã đo trên raster thật).** Đọc theo dải chỉ giải quyết *bộ nhớ*, không giảm *khối lượng đọc*: mỗi lần `build` vẫn quét **mọi điểm ảnh**. Và `project.boundary` đã được khai báo trong YAML nhưng `build` không dùng đến.

| Raster | Kích thước | Cách lưu | Cửa sổ của `ht_chu.shp` |
|---|---|---|---|
| DEM `as_dem_3s_UTM48N.tif` | 17,4 tỷ điểm ảnh, 34,7 GB | int16, **không nén**, dải 1 hàng, không overview | 551 × 591 = 0,3 triệu (0,002%) |
| Land-use `vietnam_worldcover_2021.tif` | 36,3 tỷ điểm ảnh, 1,2 GB | uint8, nén deflate, EPSG:4326 | 6601 × 6591 = 43,5 triệu (0,12%) |
| Soil `hdr.adf` | 0,93 tỷ điểm ảnh | int16 | 117 × 125 (0,002%) |

Tốc độ đọc đo được qua cầu nối thư mục: DEM khoảng 19 triệu điểm ảnh/giây, tức quét hết khoảng 15 phút; land-use khoảng 2 phút. Trên ổ đĩa gốc của máy Windows con số sẽ khác, nhưng khối lượng 54,6 tỷ điểm ảnh mỗi lần là như nhau.

Hệ quả thứ hai là **kết quả sai ngữ cảnh**: báo cáo QA cũ ghi độ cao −277 đến 8.642 m (cả dãy Himalaya) và 3.820 mã đất, trong đó 3.744 mã "không có trong bảng đất" (lỗi `soil_unmatched_codes`). Trong lưu vực chỉ có độ cao 6–1.045 m, 6 mã land-use và 4 mã đất.

**Giải pháp.** `build` dùng `project.boundary` để chỉ đọc cửa sổ bao quanh lưu vực:

```python
def boundary_window(ds, boundary_path: Path):
    """rasterio Window covering the boundary's bounding box in the open raster `ds`."""
    from rasterio.windows import Window

    if ds.crs is None:
        raise InputValidationError("Raster has no CRS, cannot use the project boundary")
    c0, r0, w, h = _window_of(ds, _read_boundary(boundary_path, ds.crs).total_bounds)
    return Window(c0, r0, w, h)
```

```python
def resolve_window(ds, boundary_path, qa: list, label: str):
    """Window of the project boundary, or None to scan the whole raster.

    Appends a QACheck to `qa`: pass when the window is used, warn when the
    boundary could not be applied (the whole raster is then scanned).
    """
    if boundary_path is None:
        return None
    try:
        win = boundary_window(ds, boundary_path)
    except ImportError:
        reason = "geopandas not installed (pip install 'swatprep[geo]')"
    except Exception as exc:  # unreadable boundary, no CRS, no overlap, ...
        reason = str(exc)
    else:
        pct = 100.0 * win.width * win.height / (ds.width * ds.height)
        qa.append(QACheck(
            name=f"{label}_boundary_window", status="pass",
            message=f"{label}: read only the project-boundary window "
                    f"({int(win.width)} x {int(win.height)} px, {pct:.4f}% of the raster)",
            context={"window": [int(win.col_off), int(win.row_off),
                                int(win.width), int(win.height)]},
        ))
        return win
    qa.append(QACheck(
        name=f"{label}_boundary_ignored", status="warn",
        message=f"{label}: project.boundary not applied, scanning the whole raster: {reason}",
    ))
    return None
```

`iter_strips`, `masked_stats` và `unique_codes` nhận thêm tham số `window`; `DEMPreprocessor`, `LandUsePreprocessor`, `SoilPreprocessor` nhận `boundary` và `api.SWATPrepProject.build` truyền `cfg.project.boundary` vào. Nếu không áp dụng được ranh giới (thiếu `geopandas`, ranh giới không có CRS, không giao với raster) thì phát cảnh báo `*_boundary_ignored` và quét toàn bộ như trước. Không khai báo `project.boundary` thì hành vi cũ giữ nguyên.

**Kết quả đo trên dữ liệu thật.**

| | Trước | Sau |
|---|---|---|
| DEM | quét 17,4 tỷ điểm ảnh (ước khoảng 15 phút qua cầu nối) | **1,3 s**, độ cao 6–1.045 m |
| Land-use | quét 36,3 tỷ điểm ảnh (ước khoảng 2 phút) | **0,9 s**, 6 mã: 10, 30, 40, 50, 60, 80 |
| Soil | 3.820 mã, 3.744 không khớp (lỗi) | **<0,1 s**, 4 mã (4265, 4267, 4348, 4383), cả 4 có trong `soil_merged.csv` |
| Bộ nhớ đỉnh | | 386 MB |

**Kiểm thử** (`tests/test_boundary_window.py`): cửa sổ đúng, `iter_strips` phủ đúng một lần, thống kê/mã theo cửa sổ bằng phép cắt mảng, DEM và land-use chỉ phản ánh lưu vực, ranh giới không giao thì cảnh báo và quét toàn bộ, và `build(only="dem")` truyền `project.boundary`.

**Lưu ý.** Cửa sổ là hộp bao của ranh giới, nên vùng nằm trong hộp nhưng ngoài đa giác vẫn được tính (đủ cho kiểm tra mã/thống kê; chưa che theo đa giác trong `build`).

### 3.6 Khai báo cắt và xuất raster trong `config.yaml` (`clip:`)

**Mục tiêu.** Chỉ cần khai báo `src` và `dst` trong YAML, `build` tự cắt raster theo `project.boundary` và ghi `dst`.

```yaml
project:
  boundary: D:/DATA/boundary/ht_chu.shp      # bắt buộc khi có clip
clip:
  - src: D:/DATA/dem_asia.tif
    dst: ./data/spatial/dem_chu.tif
  - src: D:/DATA/landuse.tif
    dst: ./data/spatial/landuse_chu.tif
    mask: true                               # tùy chọn, mặc định false
dem:
  path: ./data/spatial/dem_chu.tif           # dùng tệp đã cắt
```

**Cách các phần liên kết.**

```
config.ClipItemConfig(src, dst, mask)      ← kiểm tra bằng Pydantic; "clip" cần project.boundary
SWATPrepConfig.configured_domains()        ← "clip" đứng ĐẦU, nên chạy trước dem/landuse/soil
api.SWATPrepProject.build                  → core.clip.ClipProcessor.run
                                              └─ utils.raster.clip_raster   (đọc/ghi theo dải)
api.SWATPrepProject.validate               ← tệp là dst của clip thì không báo "thiếu" (sẽ được tạo)
```

```python
class ClipProcessor:
    """Crop each `clip` item (src -> dst) to the project boundary's bounding box."""

    def __init__(self, items: list[ClipItemConfig], boundary: Path) -> None:
        self.items = items
        self.boundary = boundary

    def run(self) -> ClipResult:
        res = ClipResult()
        for item in self.items:
            name = item.dst.name
            if not item.src.exists():
                res.qa.append(QACheck(
                    name=f"clip_src_missing:{name}", status="fail",
                    message=f"clip source not found: {item.src}",
                ))
            elif item.src.resolve() == item.dst.resolve():
                res.qa.append(QACheck(
                    name=f"clip_same_file:{name}", status="fail",
                    message="clip src and dst are the same file",
                ))
            elif self._is_fresh(item):
                res.qa.append(QACheck(
                    name=f"clip_skipped:{name}", status="pass",
                    message=f"{name} is newer than its source and the boundary; "
                            "not re-clipped (delete it to force)",
                ))
            else:
                self._clip(item, res)
        return res

    def _clip(self, item: ClipItemConfig, res: ClipResult) -> None:
        name = item.dst.name
        try:
            clip_raster(item.src, item.dst, self.boundary, mask=item.mask)
        except ImportError:
            res.qa.append(QACheck(
                name=f"clip_failed:{name}", status="fail",
                message="clipping needs geopandas and rasterio: pip install 'swatprep[geo]'",
            ))
        except Exception as exc:
            res.qa.append(QACheck(
                name=f"clip_failed:{name}", status="fail",
                message=f"could not clip {item.src.name}: {exc}",
                context={"src": str(item.src), "dst": str(item.dst)},
            ))
        else:
            res.written.append(item.dst)
            res.qa.append(QACheck(
                name=f"clip_written:{name}", status="pass",
                message=f"{item.src.name} clipped to the boundary -> {item.dst}",
            ))

    def _is_fresh(self, item: ClipItemConfig) -> bool:
        """True when dst exists and is newer than the source and all boundary files."""
        if not item.dst.exists():
            return False
        b = self.boundary
        sidecars = [p for p in b.parent.glob(b.stem + ".*") if p.is_file()] or [b]
        newest = max(p.stat().st_mtime for p in [item.src, *sidecars])
        return item.dst.stat().st_mtime >= newest
```

Các quyết định thiết kế:

- Tệp nguồn không tồn tại, `src` trùng `dst`, thiếu `geopandas`: mỗi trường hợp là một QACheck `fail` với tên riêng (`clip_src_missing`, `clip_same_file`, `clip_failed`); không ném ngoại lệ thô.
- **Bỏ qua khi còn mới:** nếu `dst` tồn tại và mới hơn `src` và mọi tệp cùng tên của ranh giới (`.shp`, `.dbf`, `.prj`, ...), `build` không cắt lại (`clip_skipped`). Muốn ép cắt lại thì xóa `dst`. Đổi `mask` không tự kích hoạt cắt lại.
- Đường dẫn tương đối trong `src`/`dst` được tính từ thư mục chứa YAML (như các mục khác).
- `swatprep build config.yaml --only clip` chỉ chạy bước này.

**Ví dụ số liệu (raster thật của Chu basin).** Ba raster (DEM 17,4 tỷ điểm ảnh, land-use 36,3 tỷ, soil) được cắt và ghi trong **2,2 s**; lần chạy thứ hai (bỏ qua vì còn mới) **0,28 s**. Đầu ra: `dem_chu.tif` 551 × 591 (414 KB), `landuse_chu.tif` 6601 × 6591 (1,9 MB), `soil_chu.tif` 117 × 125 (1 KB). Land-use vẫn ở EPSG:4326 vì `clip` không chiếu lại.

**Kiểm thử** (`tests/test_clip_domain.py`): đường dẫn tương đối và thứ tự domain, bắt buộc có `project.boundary`, ghi đúng nội dung rồi bỏ qua rồi cắt lại khi nguồn đổi, `dem` đọc tệp đã cắt ngay trong cùng một lần `build`, và lỗi thiếu nguồn.

### 3.7 Cắt raster và lọc bảng cùng lúc, cùng một thư mục `output_dir`

**Mục tiêu.** Một lần `build` vừa cắt raster theo `project.boundary`, vừa dựng bảng chỉ gồm các lớp/đất có trong lưu vực, và mọi thứ nằm dưới cùng `project.output_dir`.

| Mục YAML | Raster đã cắt | Bảng |
|---|---|---|
| `dem` | `output/spatial/<output_name>` | `spatial/dem_info.json` |
| `landuse` | `output/landuse/<output_name>` (mặc định `landuse_clip.tif`) | `landuse/landuse_lookup.csv` chỉ giữ lớp có trong lưu vực |
| `soil` | `output/soil/<output_name>` (mặc định `soil_clip.tif`) | `soil/usersoil.csv` chỉ giữ đất có trong lưu vực |

Mỗi mục có khóa `clip` (mặc định `true`); đặt `clip: false` để quay về hành vi cũ. Không cần khai báo thêm `src`/`dst`: `src` là `dem.path`, `landuse.raster`, `soil.raster`; `dst` suy ra từ `output_dir`.

**Cách các hàm liên kết.**

```
api.SWATPrepProject.build  (mỗi domain: dem / landuse / soil)
  ├─ core.clip.clip_into_output   → ClipProcessor → utils.raster.clip_raster   (ghi raster đã cắt vào output_dir)
  │       trả về boundary (hoặc None nếu clip=false / thiếu nguồn)
  ├─ <Domain>Preprocessor(cfg, boundary=...)
  │       ├─ utils.raster.resolve_window → unique_codes / masked_stats          (chỉ đọc cửa sổ lưu vực)
  │       └─ core.clip.basin_rows        (lọc bảng theo mã có trong lưu vực)
  └─ writers.*                    (ghi bảng đã lọc vào output_dir)
```

```python
def clip_into_output(src, name, out_dir, boundary, enabled, qa) -> Path | None:
    """Domain-level clip: write `out_dir/name` cropped to `boundary`, appending QA to `qa`.

    Returns the boundary to use for window-limited reads, or None when clipping is
    off (`enabled` False, no boundary) or the source is missing (the domain's own
    preprocessor reports that).
    """
    if not enabled or boundary is None or not Path(src).exists():
        return None
    qa.extend(ClipProcessor([ClipItemConfig(src=src, dst=out_dir / name)], boundary).run().qa)
    return boundary
```

```python
def basin_rows(df: pd.DataFrame, key_col: str, codes: set, label: str, qa: list) -> pd.DataFrame:
    """Rows of `df` whose `key_col` code is present in the basin (`codes`)."""
    keep = pd.to_numeric(df[key_col], errors="coerce").isin(codes)
    out = df[keep]
    qa.append(QACheck(
        name=f"{label}_table_filtered", status="pass",
        message=f"{label}: table restricted to the {len(out)} of {len(df)} row(s) "
                "whose code occurs inside the project boundary",
    ))
    return out
```

Quyết định thiết kế quan trọng:

- Bảng chỉ bị lọc khi cửa sổ ranh giới **thực sự được áp dụng** (`_windowed`), nên khi không có ranh giới thì bảng giữ nguyên như trước.
- Mã lớp SWAT (`code_mapping`) vẫn tính từ bảng **đầy đủ**, để số thứ tự lớp không đổi theo từng lưu vực.
- Việc kiểm tra "mã raster có trong bảng" chạy trên bảng đầy đủ trước khi lọc.
- `dem.output_name` mặc định `dem_projected.tif` nhưng tệp **chỉ được cắt, chưa chiếu lại**; nếu DEM khác `project.crs` vẫn có cảnh báo `dem_crs_mismatch`.

**Ví dụ số liệu (Chu basin, ghi vào thư mục tạm).** Cả lần `build` (DEM 17,4 tỷ + land-use 36,3 tỷ + soil + weather) chạy **6,1 s**, 23 kiểm tra đều đạt, không còn lỗi `soil_unmatched_codes`. `landuse_lookup.csv`: 6 trong 11 lớp; `usersoil.csv`: 4 trong 105 dòng. Ba raster đã cắt nằm cùng `output/`.

**Phát hiện thêm.** Tệp mẫu `examples/data/boundary.geojson` chứa tọa độ UTM nhưng không khai báo CRS (GeoJSON mặc định là EPSG:4326), nên chiếu sang EPSG:32648 cho ra giá trị vô hạn. Khi `build` bắt đầu dùng ranh giới, lỗi này lộ ra và làm hỏng test đầu-cuối. Đã thêm khai báo CRS vào tệp mẫu và thêm kiểm tra: tọa độ không hữu hạn thì báo "Boundary cannot be converted to the raster CRS (wrong or missing CRS?)".

**Kiểm thử** (`tests/test_clip_outputs.py`): raster đã cắt và bảng đã lọc nằm chung `output_dir`; `clip: false` giữ hành vi cũ; lần `build` thứ hai không cắt lại (`clip_skipped`) nhưng vẫn dựng lại bảng; tên tệp đầu ra tùy chỉnh.

### 3.8 Sửa test cũ sai kỳ vọng

`test_example_config_builds_end_to_end` kỳ vọng file `ST001.pcp`, nhưng writer đặt tên file theo **tên trạm** (`StationA.pcp`, vì `weather_stations.csv` có `ST001,StationA`). Đây là lỗi của test, không phải của mã; đã sửa kỳ vọng.

---
## 4. Mã dùng để đo và kiểm thử

Nguyên tắc làm việc đã dùng: **đo trước, sửa sau, đo lại sau khi sửa, và luôn đối chiếu kết quả cũ–mới**. Các script dưới đây là mã thật đã chạy. Với dữ liệu thật của anh/chị, cần sửa đường dẫn cho phù hợp; `t.yaml` trong các script là bản sao của `config.fill.yaml` với `netcdf.path` trỏ tới bản sao cục bộ của file NetCDF (đọc từ đĩa cục bộ nhanh và ổn định hơn đọc qua thư mục chia sẻ).

### 4.1 Xem cấu trúc NetCDF và ước lượng chi phí đọc (dữ liệu thật)

Mục đích: mở file, xem chunk, thử đọc 1 năm × 11 trạm, kiểm tra đơn vị/giá trị NaN tại từng trạm.

```python
import time, numpy as np, xarray as xr
t=time.time(); ds=xr.open_dataset("local.nc"); print(f"open_dataset: {time.time()-t:.2f}s", flush=True)
lat=ds["lat"].values; lon=ds["lon"].values
st=[(21.083,106.383),(21.383,106.55),(21.5,106.35),(21.9,106.317),(21.033,106.75),(21.833,106.767),(21.333,106.85),(21.533,107.1),(20.967,107.067),(21.333,107.4),(21.017,107.35)]
ilat=np.array([np.abs(lat-a).argmin() for a,b in st]); ilon=np.array([np.abs(lon-b).argmin() for a,b in st])
print("ô gần nhất CUAONG:", float(lat[ilat[-1]]), float(lon[ilon[-1]]), flush=True)
sel={"lat":xr.DataArray(ilat,dims="s"),"lon":xr.DataArray(ilon,dims="s")}
# thử trên 1 năm (365 chunk) để ước lượng
t=time.time(); a=ds["tasmax"].isel(time=slice(0,365)).isel(sel).values; dt=time.time()-t
print(f"1 năm (365 ngày) x 1 biến: {dt:.2f}s  -> ước 35 năm x 3 biến ~ {dt*35*3:.0f}s", flush=True)
# so sánh: đọc 1 ô đơn, 1 năm
t=time.time(); b=ds["tasmax"].isel(time=slice(0,365),lat=int(ilat[0]),lon=int(ilon[0])).values; print(f"1 ô, 1 năm: {time.time()-t:.2f}s", flush=True)
# kiểm tra giá trị: đơn vị và mask tại CUAONG
sub=ds["tasmax"].isel(time=slice(0,365)).isel(sel).values
print("tasmax mẫu (năm 1980), trung bình theo trạm:", np.nanmean(sub,axis=0).round(1))
print("tỉ lệ NaN theo trạm:", np.isnan(sub).mean(axis=0).round(2))
pr=ds["pr"].isel(time=slice(0,365)).isel(sel).values
print("pr  mẫu (năm 1980): trung bình mm/ngày theo trạm:", np.nanmean(pr,axis=0).round(1), "| max:", float(np.nanmax(pr)))
```

Cách xem chunk và nén của một biến (đây là lệnh chẩn đoán quan trọng nhất):

```python
import xarray as xr
ds = xr.open_dataset("OBS.Vietnam.1980-2014.nc")
print(ds["tasmax"].encoding)   # xem 'chunksizes', 'zlib', 'complevel'
```

Kết quả trên file của anh/chị: `chunksizes=(1, 161, 121)`, `zlib=True`, `complevel=9`.

### 4.2 Đo từng giai đoạn của `fill` và dùng cProfile

```python
import time, resource, cProfile, pstats, io, sys
t0=time.time()
from swatprep.fill_setup import resolve_fill_inputs
from swatprep.core.weather_fill import WeatherGapFiller
from swatprep.core.weather import WeatherPreprocessor
print(f"import+setup: {time.time()-t0:.1f}s")
inp=resolve_fill_inputs({"config":"t.yaml"})
t=time.time(); real=WeatherPreprocessor(inp.real_cfg).run(); print(f"[1] đọc 11 CSV thực đo + tính WGN: {time.time()-t:.1f}s")
idx=next(iter(real.daily.values())).index
t=time.time(); daily,qa=inp.fill_source.load(real.stations, idx, list(real.daily)); print(f"[2] trích NetCDF (3 biến, 11 trạm): {time.time()-t:.1f}s")
t=time.time(); res=WeatherGapFiller(inp.real_cfg, inp.fill_source, 365).run(); print(f"[3] toàn bộ WeatherGapFiller.run (gồm 1+2 lại): {time.time()-t:.1f}s")
print(f"peak RSS: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB")
pr=cProfile.Profile(); pr.enable(); inp.fill_source.load(real.stations, idx, list(real.daily)); pr.disable()
s=io.StringIO(); pstats.Stats(pr,stream=s).sort_stats("cumulative").print_stats(8); print("\n".join(l for l in s.getvalue().splitlines() if "{" in l or ".py" in l)[:1500])
```

Cách đọc kết quả: so sánh các mốc `[1]` (CSV), `[2]` (NetCDF), `[3]` (toàn bộ). Nếu `[2]` chiếm gần hết thời gian thì nút cổ chai là nguồn fill, không phải phần hiệu chỉnh hay đọc CSV.

### 4.3 Đo mức "tăng vọt" theo số ngày: vector và hộp bao (dữ liệu thật)

```python
import time, numpy as np, xarray as xr, faulthandler
faulthandler.dump_traceback_later(140, exit=True)
ds=xr.open_dataset("local.nc"); lat=ds["lat"].values; lon=ds["lon"].values
st=[(21.083,106.383),(21.383,106.55),(21.5,106.35),(21.9,106.317),(21.033,106.75),(21.833,106.767),(21.333,106.85),(21.533,107.1),(20.967,107.067),(21.333,107.4),(21.017,107.35)]
ilat=np.array([np.abs(lat-a).argmin() for a,b in st]); ilon=np.array([np.abs(lon-b).argmin() for a,b in st])
sel={"lat":xr.DataArray(ilat,dims="s"),"lon":xr.DataArray(ilon,dims="s")}
print("lat idx",sorted(set(ilat)),"lon idx",sorted(set(ilon)))
for N in (365,730,1460,2920):
    t=time.time(); ds["tasmax"].isel(time=slice(0,N)).isel(sel).values; print(f"A) vectorized, {N} ngày: {time.time()-t:.2f}s", flush=True)
for N in (365,2920,12784):
    t=time.time()
    box=ds["tasmax"].isel(time=slice(0,N),lat=slice(ilat.min(),ilat.max()+1),lon=slice(ilon.min(),ilon.max()+1)).values
    out=box[:,ilat-ilat.min(),ilon-ilon.min()]
    print(f"B) đọc hộp bao 1 lần + numpy, {N} ngày: {time.time()-t:.2f}s  shape={out.shape}", flush=True)
```

### 4.4 Bản tái hiện độc lập, không cần dữ liệu của anh/chị

Tạo NetCDF giả lập có cùng cách chia chunk và nén, rồi so sánh hai cách đọc:

```python
"""Tạo NetCDF giả lập có cấu trúc chunk giống file thực: [1, nlat, nlon], zlib mức 9."""
import numpy as np, pandas as pd, xarray as xr, sys
ndays = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
lat = np.round(np.arange(8.0, 24.1, 0.1), 1)[:161]       # 161 vĩ độ
lon = np.round(np.arange(100.0, 112.1, 0.1), 1)[:121]    # 121 kinh độ
time = pd.date_range("1981-01-01", periods=ndays, freq="D")
rng = np.random.default_rng(0)
base = 25 + 5 * np.sin(2 * np.pi * np.arange(ndays) / 365.25)[:, None, None]
data = (base + rng.normal(0, 1, (ndays, lat.size, lon.size))).astype("float32")
data[:, :, :5] = np.nan                                    # vài cột "biển" toàn NaN
ds = xr.Dataset({"tasmax": (("time", "lat", "lon"), data)},
                coords={"time": time, "lat": lat, "lon": lon})
enc = {"tasmax": {"zlib": True, "complevel": 9, "chunksizes": (1, lat.size, lon.size)}}
ds.to_netcdf("synthetic.nc", encoding=enc)
print("đã tạo synthetic.nc", ndays, "ngày")
```

```python
"""So sánh hai cách trích chuỗi thời gian tại 11 ô: (A) chọn điểm kiểu vector; (B) đọc hộp bao một lần."""
import time, numpy as np, xarray as xr
ds = xr.open_dataset("synthetic.nc")
rng = np.random.default_rng(1)
ilat = rng.integers(40, 48, 11); ilon = rng.integers(60, 68, 11)       # 11 trạm trong một vùng nhỏ
sel = {"lat": xr.DataArray(ilat, dims="s"), "lon": xr.DataArray(ilon, dims="s")}
for n in (365, 730, 1460, 2920):
    t = time.time(); a = ds["tasmax"].isel(time=slice(0, n)).isel(sel).values
    ta = time.time() - t
    t = time.time()
    box = ds["tasmax"].isel(time=slice(0, n), lat=slice(ilat.min(), ilat.max() + 1),
                            lon=slice(ilon.min(), ilon.max() + 1)).values
    b = box[:, ilat - ilat.min(), ilon - ilon.min()]
    tb = time.time() - t
    print(f"{n:5d} ngày | A vector: {ta:6.2f}s | B hộp bao: {tb:5.2f}s | giống nhau: {np.array_equal(a, b, equal_nan=True)}")
```

Chạy: `python make_nc.py 3000` rồi `python bench_read.py`.

### 4.5 Kiểm tra bản sửa trên dữ liệu thật

```python
import time, resource, numpy as np, pandas as pd, xarray as xr
t0=time.time()
from swatprep.fill_setup import resolve_fill_inputs
from swatprep.core.weather_fill import WeatherGapFiller
from swatprep.core.weather import WeatherPreprocessor
print(f"import+cấu hình: {time.time()-t0:.1f}s", flush=True)
inp=resolve_fill_inputs({"config":"t.yaml"})
t=time.time(); real=WeatherPreprocessor(inp.real_cfg).run(); print(f"[1] đọc 11 CSV + WGN: {time.time()-t:.1f}s", flush=True)
idx=next(iter(real.daily.values())).index
t=time.time(); daily,qa=inp.fill_source.load(real.stations, idx, list(real.daily)); print(f"[2] trích NetCDF (bản sửa): {time.time()-t:.1f}s", flush=True)
for c in qa:
    if c.status!="pass": print("   QA:", c.status, c.message)
# so với cách cũ trên 730 ngày đầu (vùng cũ vẫn nhanh)
ds=xr.open_dataset("local.nc"); lat=ds.lat.values; lon=ds.lon.values; st=real.stations
il=np.array([np.abs(lat-a).argmin() for a in st["lat"]]); jl=np.array([np.abs(lon-b).argmin() for b in st["lon"]])
old=ds["tasmax"].isel(time=slice(0,730)).isel(lat=xr.DataArray(il,dims="s"),lon=xr.DataArray(jl,dims="s")).values
tm=pd.DatetimeIndex(ds.time.values).normalize()[:730]
cmp=daily["tmax"].reindex(tm).values
print("khớp cách cũ (730 ngày đầu):", np.allclose(np.nan_to_num(old,nan=-1),np.nan_to_num(cmp,nan=-1)), flush=True)
t=time.time(); res=WeatherGapFiller(inp.real_cfg, inp.fill_source, 365).run(); print(f"[3] toàn bộ fill (đọc+trích+hiệu chỉnh): {time.time()-t:.1f}s", flush=True)
print(f"peak RSS: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB")
r=res.report; print(r[r.station_id=="CUAONG"][["variable","n_missing","n_filled","n_overlap","correction_type"]].to_string(index=False))
print("tỉ lệ NaN của lưới tại CUAONG:", daily["precip"]["CUAONG"].isna().mean().round(3) if "CUAONG" in daily["precip"] else "CUAONG KHÔNG có trong nguồn fill")
```

Hai kiểm tra quan trọng trong script: (1) giá trị khớp cách cũ trên 730 ngày đầu; (2) tỷ lệ NaN của lưới tại từng trạm (phát hiện CUAONG toàn NaN).

### 4.6 So sánh mã cũ và mới trên toàn bộ trạm

Bước 1: lưu bản cũ thành `swatprep/core/fill_sources_old.py` (sao chép tệp cũ), chạy từng biến (mỗi biến khoảng 95 s nên chạy tách riêng):

```python
import os, sys, time, pandas as pd
from pathlib import Path
from swatprep.config import FillNetCDFConfig
from swatprep.core.fill_sources_old import NetCDFFillSource as Old
H=os.path.expanduser("~"); v=sys.argv[1]
st=pd.read_csv(f"{H}/mnt/Chu basin/data/obs/stations.csv", index_col="id")
cfg=FillNetCDFConfig(path=Path(f"{H}/prof/local.nc"), var_map={"precip":"pr","tmax":"tasmax","tmin":"tasmin"})
idx=pd.date_range("1981-01-01","1984-12-31")
t=time.time(); o,_=Old(cfg).load(st,idx,[v]); print(v,"old s",round(time.time()-t,1),flush=True)
o[v].to_pickle(f"/tmp/old_{v}.pkl")
```

Bước 2: so sánh với bản mới, cho biết ô nào thay đổi:

```python
import os, time, numpy as np, pandas as pd
from pathlib import Path
from swatprep.config import FillNetCDFConfig
from swatprep.core.fill_sources import NetCDFFillSource as New, _match_lon, _nearest
import xarray as xr
H=os.path.expanduser("~")
st=pd.read_csv(f"{H}/mnt/Chu basin/data/obs/stations.csv", index_col="id")
nc=Path(f"{H}/prof/local.nc")
cfg=lambda r: FillNetCDFConfig(path=nc, var_map={"precip":"pr","tmax":"tasmax","tmin":"tasmin"}, search_radius=r)
idx=pd.date_range("1981-01-01","1984-12-31"); V=["precip","tmax"]
t=time.time(); n,qa=New(cfg(1)).load(st,idx,V); print("new s",round(time.time()-t,1))
old={v:pd.read_pickle(f"/tmp/old_{v}.pkl") for v in V}
with xr.open_dataset(nc) as ds:
    gl=ds.lon.values.astype(float); ga=ds.lat.values.astype(float); print("grid lon dtype",ds.lon.dtype)
lo_old=(st.lon.to_numpy(float)+180)%360-180
io=_nearest(gl,lo_old)[0]; inw=_nearest(gl,_match_lon(st.lon.to_numpy(float),gl))[0]
for k,s in enumerate(st.index):
    same=all(np.array_equal(old[v][s].to_numpy(), n[v][s].to_numpy(), equal_nan=True) for v in V)
    print(f"{s:8s} lon={st.lon.iloc[k]:.3f}  old cell lon={gl[io[k]]:.1f}  new cell lon={gl[inw[k]]:.1f}  identical={same}")
print([c.name for c in qa if c.status=="warn"])
```

Kết luận đã thu được: 7 trạm giống hệt; 4 trạm nằm giữa hai ô có ô được chọn khác nhau (mục 3.2).

### 4.7 Raster lớn: tạo dữ liệu thử và đo bộ nhớ

```python
"""Tạo GeoTIFF lớn (mặc định 50000 x 50000 int16, ~5 GB nếu nạp hết) nhưng file chỉ vài MB nhờ nén."""
import numpy as np, rasterio, sys
from rasterio.transform import from_origin
from rasterio.windows import Window
n = int(sys.argv[1]) if len(sys.argv) > 1 else 50000
prof = dict(driver="GTiff", width=n, height=n, count=1, dtype="int16", crs="EPSG:32648",
            transform=from_origin(500000, 2500000, 30, 30), nodata=-32768,
            tiled=True, blockxsize=512, blockysize=512, compress="deflate", BIGTIFF="YES")
with rasterio.open("big.tif", "w", **prof) as dst:
    rng = np.random.default_rng(0)
    for r in range(0, n, 512):
        h = min(512, n - r)
        dst.write((5 + (np.arange(n)[None, :] + r) % 1495).astype("int16") * np.ones((h, 1), "int16"),
                  1, window=Window(0, r, n, h))
print("đã tạo big.tif", n, "x", n)
```

```python
"""Chạy kiểm tra DEM trên big.tif và in thời gian + bộ nhớ đỉnh."""
import time, resource
from pathlib import Path
from swatprep.config import DEMConfig
from swatprep.core.dem import DEMPreprocessor
t = time.time()
try:
    r = DEMPreprocessor(DEMConfig(path=Path("big.tif")), project_crs="EPSG:32648").run()
    print("OK", r.shape, r.elevation_range, f"{time.time()-t:.1f}s",
          f"peakRSS={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB")
except MemoryError as e:
    print("MemoryError:", str(e)[:90])
```

Chạy bản cũ với giới hạn bộ nhớ ảo để thấy lỗi mà không làm sập máy (Linux/macOS):

```bash
( ulimit -v 3000000; PYTHONPATH=/duong/dan/ban_cu python run_dem.py )   # MemoryError
PYTHONPATH=/duong/dan/ban_moi python run_dem.py                          # OK, ~0.4 GB
```

Trên Windows, hãy theo dõi bằng Task Manager hoặc dùng `psutil.Process().memory_info().rss`.

### 4.8 Các test đơn vị đã thêm

*Test cho nguồn NetCDF (`tests/test_fill_sources.py`):*

```python
def _write_masked_nc(path, nan_cols=(), lat=(15.5, 15.0), lon=(105.0, 105.5)):
    """Như _write_nc nhưng các cột kinh độ trong nan_cols toàn NaN (mô phỏng ô biển)."""
    shape = (len(DATES), len(lat), len(lon))
    base = np.fromfunction(lambda t, i, j: i * 10 + j + t, shape)
    base[:, :, list(nan_cols)] = np.nan
    xr.Dataset(
        {"pr": (("time", "lat", "lon"), base)},
        coords={"time": DATES, "lat": list(lat), "lon": list(lon)},
    ).to_netcdf(path)
    return path

def _mid(lat=15.0, lon=105.25):
    return pd.DataFrame({"name": ["M"], "lat": [lat], "lon": [lon], "elev": [1]},
                        index=pd.Index(["MID"], name="id"))

def _cfg_pr(path, **kw):
    return FillNetCDFConfig(path=path, var_map={"precip": "pr"}, **kw)

def test_bounding_box_read_equals_pointwise_selection(tmp_path):
    nc = _write_nc(tmp_path / "g.nc", lat=(16.0, 15.5, 15.0), lon=(105.0, 105.5))
    daily, _ = NetCDFFillSource(_cfg(nc, search_radius=0)).load(STATIONS, DATES, ["precip"])
    with xr.open_dataset(nc) as ds:
        ref = ds["pr"].sel(lat=[15.0, 15.5], lon=[105.0, 105.5])
        assert daily["precip"]["S1"].tolist() == ref.sel(lat=15.0, lon=105.0).values.tolist()
        assert daily["precip"]["S2"].tolist() == ref.sel(lat=15.5, lon=105.5).values.tolist()

def test_tied_station_with_nan_cell_falls_back_to_valid_neighbor(tmp_path):
    nc = _write_masked_nc(tmp_path / "g.nc", nan_cols=(0,))
    daily, qa = NetCDFFillSource(_cfg_pr(nc)).load(_mid(), DATES, ["precip"])
    assert daily["precip"]["MID"].tolist() == [11.0, 12.0, 13.0, 14.0]  # ô (15.0, 105.5)
    assert any(c.name == "netcdf_extract:MID:neighbor_cell" and c.status == "warn" for c in qa)

def test_search_radius_zero_does_not_look_at_neighbors(tmp_path):
    nc = _write_masked_nc(tmp_path / "g.nc", nan_cols=(0,))
    with pytest.raises(InputValidationError, match="No station has a NetCDF cell"):
        NetCDFFillSource(_cfg_pr(nc, search_radius=0)).load(_mid(), DATES, ["precip"])

def test_match_lon_changes_only_what_is_needed():
    from swatprep.core.fill_sources import _match_lon
    g180, g360 = np.array([107.3, 107.4]), np.array([285.0, 285.5])
    assert _match_lon(np.array([107.35]), g180)[0] == 107.35          # không sai số dấu phẩy động
    assert _match_lon(np.array([-74.9]), g360)[0] == pytest.approx(285.1)
    assert _match_lon(np.array([285.1]), g180)[0] == pytest.approx(-74.9)

def test_exact_midpoint_tie_goes_to_lower_index_cell(tmp_path):
    nc = _write_masked_nc(tmp_path / "g.nc", lon=(107.3, 107.4))
    sta = _mid(lat=15.0, lon=107.35)
    daily, qa = NetCDFFillSource(_cfg_pr(nc, search_radius=0)).load(sta, DATES, ["precip"])
    assert daily["precip"]["MID"].tolist() == [10.0, 11.0, 12.0, 13.0]  # ô (15.0, 107.3)
    assert qa[-1].status == "pass"
```

*Test cho raster (`tests/test_raster_utils.py`):*

```python
def _grid(tmp_dir, n=10):
    """Raster n x n, pixel 30 m, giá trị = hàng*100 + cột (+1 để khác nodata 0)."""
    raster = tmp_dir / "g.tif"
    _write_tiny_raster(raster, np.fromfunction(lambda i, j: i * 100 + j + 1, (n, n)))
    return raster

def _boundary(tmp_dir, geom, crs="EPSG:32648", name="b.geojson"):
    path = tmp_dir / name
    gpd.GeoDataFrame(geometry=[geom], crs=crs).to_file(path, driver="GeoJSON")
    return path

def test_masked_stats_streamed_equals_full_read(tmp_dir):
    raster = tmp_dir / "dem.tif"
    data = np.arange(60).reshape(6, 10) + 100
    data[2, 3] = -9999
    data[5, :] = -9999
    _write_tiny_raster(raster, data, nodata=-9999)
    with rasterio.open(raster) as ds:
        full = ds.read(1, masked=True)
        for max_pixels in (10, 25, 10_000):                 # many strips ... one strip
            vmin, vmax, mean, n = masked_stats(ds, max_pixels=max_pixels)
            assert (vmin, vmax, n) == (float(full.min()), float(full.max()), int(full.count()))
            assert mean == pytest.approx(float(full.mean()))

@needs_geopandas
def test_clip_bbox_crops_expected_window(tmp_dir):
    raster = _grid(tmp_dir)
    # gốc (500000, 1600000), pixel 30 m: cột 2..5 -> x 500060..500180 ; hàng 3..6 -> y 1599910..1599790
    b = _boundary(tmp_dir, box(500061, 1599791, 500179, 1599909))
    out = clip_raster(raster, tmp_dir / "o" / "c.tif", b)
    with rasterio.open(out) as ds, rasterio.open(raster) as src:
        assert (ds.width, ds.height) == (4, 4)
        assert ds.transform.c == 500060 and ds.transform.f == 1599910
        assert np.array_equal(ds.read(1), src.read(1)[3:7, 2:6])
        assert ds.nodata == src.nodata and ds.crs == src.crs

@needs_geopandas
def test_clip_is_identical_when_strips_are_small(tmp_dir):
    raster = _grid(tmp_dir)
    b = _boundary(tmp_dir, box(500061, 1599791, 500179, 1599909))
    a = clip_raster(raster, tmp_dir / "a.tif", b)
    s = clip_raster(raster, tmp_dir / "s.tif", b, max_pixels=4)   # 1 hàng mỗi dải
    with rasterio.open(a) as x, rasterio.open(s) as y:
        assert np.array_equal(x.read(), y.read())

@needs_geopandas
def test_clip_mask_sets_pixels_outside_polygon_to_nodata(tmp_dir):
    raster = _grid(tmp_dir)
    tri = Polygon([(500000, 1599700), (500300, 1599700), (500300, 1600000)])  # nửa dưới-phải
    b = _boundary(tmp_dir, tri)
    with rasterio.open(clip_raster(raster, tmp_dir / "m.tif", b, mask=True)) as ds:
        d = ds.read(1)
        assert d[0, 0] == 0 and d[-1, -1] != 0          # góc trên-trái ngoài, dưới-phải trong
    with rasterio.open(clip_raster(raster, tmp_dir / "n.tif", b)) as ds:
        assert (ds.read(1) != 0).all()                   # bbox crop: không che
```

Lệnh chạy:

```bash
python -m pytest -q                           # toàn bộ: 198 đạt (khi có rasterio + geopandas)
python -m pytest tests/test_fill_sources.py -v
python -m pytest tests/test_raster_utils.py -v
```

**Thủ thuật quan trọng khi viết test hồi quy:** sau khi viết test, chạy nó trên **mã cũ** để chắc chắn nó *thất bại đúng chỗ* (khóa được lỗi). Đã làm vậy: test về ô lân cận, `search_radius=0` và `_match_lon` đều thất bại trên mã cũ.

---

## 5. Bài tập tự kiểm tra

Mỗi câu có đáp án ngắn ngay dưới. Hãy tự trả lời trước khi xem.

**Câu 1.** Vì sao lấy 365 ngày thì nhanh, 1.460 ngày thì chậm hơn trăm lần, dù chỉ gấp 4 lần dữ liệu?
*Đáp án:* Bộ nhớ đệm chunk của HDF5 có hạn; vượt ngưỡng (khoảng 730 ngày ở cấu hình này) thì mỗi ô lại giải nén lại các khối thời gian. Chi phí chuyển từ "một lần" sang "số ô × số khối".

**Câu 2.** Chunk `[1, 161, 121]` tốt cho thao tác nào, tệ cho thao tác nào?
*Đáp án:* Tốt cho lấy bản đồ của một ngày; tệ cho lấy chuỗi thời gian của vài ô (phải giải nén cả khối 161 × 121 cho mỗi ngày).

**Câu 3.** Vì sao đọc hộp bao rồi chọn bằng NumPy lại nhanh hơn, dù đọc nhiều dữ liệu hơn mức cần?
*Đáp án:* Số lần giải nén giảm từ "mỗi ô một lượt" xuống "một lượt cho cả hộp"; phần dư (ô không dùng) rất nhỏ so với chi phí giải nén.

**Câu 4.** Tại sao `107.35` có thể trở thành `107.35000000000002` và hệ quả là gì?
*Đáp án:* Số thực nhị phân không biểu diễn chính xác phần lớn số thập phân; cộng rồi trừ 180 làm lộ sai số làm tròn. Khi trạm cách đều hai ô, sai số cỡ 1e-14 đủ quyết định ô nào "gần hơn".

**Câu 5.** Vì sao dùng `np.round(khoảng cách, 9)` trước `argmin`?
*Đáp án:* Để các khoảng cách "bằng nhau về mặt thực tế" thực sự bằng nhau, từ đó `argmin` luôn chọn chỉ số thấp hơn (quy tắc hòa ổn định).

**Câu 6.** Khi nào đặt `search_radius: 0`?
*Đáp án:* Khi cần đúng "ô gần nhất" và chấp nhận trạm bị loại nếu ô đó trống; ví dụ để đối chiếu với kết quả cũ hoặc kiểm tra nhạy.

**Câu 7.** `masked_stats` không giữ mảng nào, vậy làm sao có giá trị trung bình?
*Đáp án:* Cộng dồn tổng (`float64`) và số điểm hợp lệ qua các dải, cuối cùng chia: `trung bình = tổng / số điểm`.

**Câu 8.** Tại sao `clip` làm tròn cửa sổ ra ngoài (`floor`/`ceil`)?
*Đáp án:* Để không mất điểm ảnh nằm một phần trong ranh giới; chấp nhận dư tối đa một điểm ảnh ở mỗi cạnh.

**Câu 9.** Vì sao không nên dùng `rasterio.mask.mask(crop=True)` cho raster rất lớn?
*Đáp án:* Hàm trả về mảng trong RAM cho toàn bộ vùng cắt; đọc/ghi theo dải giữ bộ nhớ không đổi.

**Câu 10.** Test hồi quy tốt cần thỏa điều kiện gì?
*Đáp án:* Thất bại trên mã lỗi và đạt trên mã đã sửa; nhỏ, nhanh, tự dựng dữ liệu; một test chỉ khóa một hành vi.

---

## 6. Bài học và quy trình tái sử dụng

1. **Đo trước khi tối ưu.** Dùng ba bước: `time` từng giai đoạn → `cProfile` → thí nghiệm nhỏ cô lập giả thuyết (ví dụ thay đổi số ngày để thấy "bậc thang").
2. **Hiệu năng phụ thuộc cách lưu dữ liệu.** Luôn xem `encoding` (chunk, nén) của NetCDF và `block shape` của GeoTIFF trước khi chọn cách đọc. Hướng truy cập nên khớp hướng chunk.
3. **Bộ nhớ tỷ lệ với "cái đang giữ", không phải "cái đã xử lý".** Với raster: cộng dồn thống kê theo dải; chỉ giữ số nhỏ (min, max, tổng, đếm) hoặc tập mã duy nhất.
4. **Số thực: không so sánh và không biến đổi thừa.** Chỉ biến đổi dữ liệu khi cần (`_match_lon`), làm tròn trước khi so khoảng cách bằng nhau.
5. **Khi đầu vào có thể "gần đúng", báo cho người dùng.** Dùng ô lân cận thì phát cảnh báo `neighbor_cell`; không im lặng thay đổi dữ liệu.
6. **Giữ kết quả cũ làm chuẩn so sánh.** Mọi tối ưu phải chứng minh "giống hệt" ở những chỗ không cần đổi (7/11 trạm giống từng giá trị).
7. **Đọc theo dải giải quyết bộ nhớ, còn cắt vùng mới giải quyết thời gian.** Tính khối lượng đọc (điểm ảnh × byte) trước khi chạy; dùng `project.boundary` hoặc `swatprep clip` để chỉ đọc vùng cần dùng.
8. **Lưu ý môi trường Windows:** tệp `.py` lớn có thể bị cắt cụt bởi trình lint (xem `AGENTS.md`); kiểm tra bằng `ast.parse`. Kho mã có tệp CRLF lẫn LF, nên `git diff` có thể báo "đã sửa" cả tệp; dùng `git diff --ignore-cr-at-eol` để xem thay đổi thật.

### 6.1 Kiểm tra nhanh bất cứ khi nào sửa mã

```bash
python -m pytest -q
python - <<'PY'
import ast, pathlib
for p in pathlib.Path("swatprep").rglob("*.py"):
    ast.parse(p.read_text(encoding="utf-8"))
print("cú pháp đúng")
PY
git diff --stat --ignore-cr-at-eol
```

### 6.2 Quy trình làm việc cho một dự án mới

1. Chuẩn bị `stations.csv` (cột `id,name,lat,lon,elev`) và dữ liệu thực đo.
2. `swatprep clip` DEM/land-use/soil về vùng lưu vực (nếu raster lớn).
3. Viết `config.fill.yaml` (đầu vào thô + khối `weather.fill`), chạy `swatprep fill weather --config config.fill.yaml`.
4. Xem `fill_report.csv` và các cảnh báo `neighbor_cell`, `no_valid_cell`, `outside_grid`.
5. Viết `config.yaml` trỏ `weather.data_dir` vào thư mục đã điền; chạy `swatprep validate`, rồi `swatprep build`.

### 6.3 Việc còn mở (chưa làm, để lập kế hoạch)

- Kiểm tra sự tồn tại của đường dẫn trong `weather.fill` ở bước `validate` (hiện lỗi thiếu file ở bước chạy có thể hiện traceback thô).
- Chiếu lại (reproject) raster về `project.crs` trong cùng luồng với `clip`.
- Hiệu chỉnh sai số theo tháng thay vì một hệ số cả năm (xem Teutschbein và Seibert, 2012).
- `build --weather-source filled` để dùng dữ liệu đã điền mà không cần hai tệp YAML.
- Nếu hộp bao rất lớn, đọc NetCDF theo từng năm.

---

## 7. Tài liệu tham khảo

1. Teutschbein, C., & Seibert, J. (2012). Bias correction of regional climate model simulations for hydrological climate-change impact studies: Review and evaluation of different methods. *Journal of Hydrology*, 456–457, 12–29. https://doi.org/10.1016/j.jhydrol.2012.05.052 — cơ sở cho hiệu chỉnh sai số kiểu ratio/offset trong `fill`.
2. Hoyer, S., & Hamman, J. (2017). xarray: N-D labeled arrays and datasets in Python. *Journal of Open Research Software*, 5(1), 10. https://doi.org/10.5334/jors.148 — thư viện đọc NetCDF.
3. Rew, R., & Davis, G. (1990). NetCDF: An interface for scientific data access. *IEEE Computer Graphics and Applications*, 10(4), 76–82. https://doi.org/10.1109/38.56302 — mô hình dữ liệu NetCDF.
4. Goldberg, D. (1991). What every computer scientist should know about floating-point arithmetic. *ACM Computing Surveys*, 23(1), 5–48. https://doi.org/10.1145/103162.103163 — nền tảng cho sai số `107.35` → `107.35000000000002`.
5. Harris, C. R., et al. (2020). Array programming with NumPy. *Nature*, 585, 357–362. https://doi.org/10.1038/s41586-020-2649-2 — chỉ số mảng và phép `argmin`.
6. GDAL/OGR contributors (2022). *GDAL/OGR Geospatial Data Abstraction software Library*. Open Source Geospatial Foundation. https://doi.org/10.5281/zenodo.5884351 — nền của rasterio và các thao tác cắt cửa sổ.
7. McKinney, W. (2010). Data structures for statistical computing in Python. *Proceedings of the 9th Python in Science Conference*, 56–61. https://doi.org/10.25080/Majora-92bf1922-00a — pandas (`DataFrame` ngày × trạm).
8. Neitsch, S. L., Arnold, J. G., Kiniry, J. R., & Williams, J. R. (2011). *Soil and Water Assessment Tool Theoretical Documentation, Version 2009* (Technical Report No. 406). Texas Water Resources Institute. — ngữ cảnh SWAT.
9. Arnold, J. G., et al. (2012). SWAT: Model use, calibration, and validation. *Transactions of the ASABE*, 55(4), 1491–1508. https://doi.org/10.13031/2013.42256
10. Bieger, K., et al. (2017). Introduction to SWAT+, a completely restructured version of the Soil and Water Assessment Tool. *Journal of the American Water Resources Association*, 53(1), 115–130. https://doi.org/10.1111/1752-1688.12482

*Ghi chú về tính trung thực của số liệu:* các thời gian và bộ nhớ trong tài liệu là số đo thực tế trên môi trường thử nghiệm (Linux, Python 3.10, rasterio 1.4.4, xarray 2025.6.1); trên máy Windows của anh/chị, giá trị tuyệt đối sẽ khác nhưng quan hệ tỷ lệ (cũ so với mới) được kỳ vọng tương tự. Ước tính cho DEM 17,4 tỷ điểm ảnh chưa được đo trực tiếp.
