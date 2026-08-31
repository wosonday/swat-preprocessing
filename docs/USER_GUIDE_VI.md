# Huong Dan Su Dung swatprep - Step by Step

## Muc Luc

1. [Gioi thieu](#1-gioi-thieu)
2. [Cai dat](#2-cai-dat)
3. [Cau truc du lieu dau vao](#3-cau-truc-du-lieu-dau-vao)
4. [Viet file cau hinh YAML](#4-viet-file-cau-hinh-yaml)
5. [Validate cau hinh va du lieu](#5-validate-cau-hinh-va-du-lieu)
6. [Chay tien xu ly (prepare)](#6-chay-tien-xu-ly-prepare)
7. [Kiem tra du lieu dau vao (inspect)](#7-kiem-tra-du-lieu-dau-vao-inspect)
8. [Chuyen doi dinh dang du lieu (convert)](#8-chuyen-doi-dinh-dang-du-lieu-convert)
9. [Su dung Python API](#9-su-dung-python-api)
10. [Cau truc output](#10-cau-truc-output)
11. [Xu ly loi thuong gap](#11-xu-ly-loi-thuong-gap)

---

## 1. Gioi thieu

`swatprep` la thu vien Python kem CLI de chuan bi du lieu dau vao cho mo hinh SWAT Classic va SWAT+. Cong cu nay xu ly 5 domain du lieu:

| Domain | Mo ta |
|--------|-------|
| **DEM** | Digital Elevation Model - validate metadata, reprojection |
| **Land-use** | Ban do su dung dat - validate lookup table, cross-check ma raster |
| **Soil** | Ban do tho nhuong - validate bang soil properties, xuat `usersoil.csv` |
| **Weather** | Du lieu khi tuong - validate station CSV, tinh thong ke WGN |
| **Streamflow** | Du lieu dong chay quan trac - validate va chuyen dinh dang |

**Pham vi:** swatprep chi lam tien xu ly va ghi dinh dang. Khong thay the QSWAT/QSWAT+, SWAT+ Editor, hay cac cong cu delineation/calibration.

---

## 2. Cai dat

### Buoc 2.1: Yeu cau he thong

- Python >= 3.10
- `pip` hoac `uv` (khuyen dung `uv` de quan ly moi truong)

### Buoc 2.2: Cai dat co ban (khong can GIS)

```bash
cd D:\SWAT-model\swat-preprocessing
pip install -e .[dev]
```

Che do nay ho tro config, QA, CLI, weather va streamflow ma khong can thu vien GIS nang.

### Buoc 2.3: Cai dat day du (co GIS validation)

```bash
pip install -e .[geo,dev]
```

Extra `geo` se cai them: `rasterio`, `geopandas`, `shapely`. Can thiet de validate DEM, land-use raster va soil raster.

### Buoc 2.4: Kiem tra cai dat thanh cong

```bash
swatprep --version
```

Ket qua mong doi: `swatprep, version 0.1.0`

---

## 3. Cau truc du lieu dau vao

Truoc khi chay swatprep, ban can chuan bi du lieu theo cau truc sau:

### 3.1 DEM

- File raster (GeoTIFF `.tif` hoac ArcInfo Grid `hdr.adf`)
- Phai co CRS (he toa do) hop le

### 3.2 Land-use

**Raster:** File raster su dung dat (GeoTIFF hoac ArcInfo Grid)

**Lookup CSV:** Bang anh xa ma raster sang ma SWAT. Cau truc toi thieu:

```csv
code,swat_code,swat_name
1,FRST,Forest-Mixed
2,AGRL,Agricultural Land-Generic
3,URBN,Urban
4,WATR,Water
```

### 3.3 Soil

**Raster:** File raster tho nhuong

**Table CSV:** Bang tinh chat vat ly dat. Cot khoa mac dinh la `soil_id`.

### 3.4 Weather

**Station CSV:** Danh sach tram khi tuong. Cac cot bat buoc:

```csv
id,name,lat,lon,elev
ST001,STATION01,15.0,105.0,100
ST002,STATION02,15.1,105.1,120
```

**Data directory:** Thu muc chua file CSV theo tung tram, ten file = `{id}.csv`. Moi file co cac cot:

```csv
date,precip,tmax,tmin
2000-01-01,5.2,32.1,22.3
2000-01-02,0.0,33.5,23.1
```

### 3.5 Streamflow

File CSV dong chay quan trac dang long-format:

```csv
date,station_id,discharge
2000-01-01,GAUGE01,45.2
2000-01-02,GAUGE01,38.7
```

---

## 4. Viet file cau hinh YAML

File cau hinh (`config.yaml`) la trung tam dieu khien cua swatprep. Moi section tuong ung voi mot domain du lieu.

### 4.1 Cau hinh toi thieu (chi phan project)

```yaml
project:
  name: "ExampleBasin_2024"
  crs: "EPSG:32648"          # He toa do chieu UTM Zone 48N
  output_dir: "./output"
  targets:
    - "swatplus"              # "swat" | "swatplus" | ca hai
```

### 4.2 Cau hinh day du

```yaml
project:
  name: "ExampleBasin_2024"
  crs: "EPSG:32648"
  boundary: "./data/boundary.shp"   # (tuy chon) ranh gioi luu vuc
  output_dir: "./output"
  targets:
    - "swatplus"

dem:
  path: "./data/dem_30m.tif"
  output_name: "dem_projected.tif"

landuse:
  raster: "./data/landuse_2020.tif"
  lookup: "./data/landuse_lookup.csv"
  source_code_col: "code"       # ten cot ma goc trong lookup CSV
  swat_code_col: "swat_code"    # ten cot ma SWAT
  swat_name_col: "swat_name"    # ten cot ten SWAT

soil:
  raster: "./data/soil_map.tif"
  table: "./data/soil_properties.csv"
  soil_key_col: "soil_id"
  output_usersoil: true         # xuat file usersoil.csv

weather:
  stations: "./data/weather_stations.csv"
  data_dir: "./data/weather"    # thu muc chua {id}.csv
  format: "csv"
  variables:
    - "precip"
    - "tmax"
    - "tmin"
  start: "2000-01-01"           # ngay bat dau (ISO format)
  end: "2020-12-31"             # ngay ket thuc (>= start)
  units:
    precip: "mm"
    temperature: "degC"
  missing_policy: "fail"        # "fail" = dung khi thieu | "warn" = canh bao

streamflow:
  path: "./data/streamflow.csv"
  date_col: "date"
  station_id_col: "station_id"
  value_col: "discharge"
  units: "m3s"                  # "m3s" | "mm"
```

### 4.3 Quy tac quan trong

- **Duong dan tuong doi** duoc giai quyet theo thu muc chua file YAML, khong phai working directory.
- **Duong dan tuyet doi** cung duoc ho tro (vi du: `D:/data/...`).
- Chi can khai bao cac section ban su dung. Cac section khong khai bao se bi bo qua.
- `weather.end` phai >= `weather.start`.

---

## 5. Validate cau hinh va du lieu

**Muc dich:** Kiem tra cau hinh hop le va tat ca file dau vao ton tai, truoc khi chay xu ly.

### Buoc 5.1: Chay validate

```bash
swatprep validate config.yaml
```

### Buoc 5.2: Doc ket qua

Ky hieu output:

| Ky hieu | Y nghia |
|---------|---------|
| `v` | Pass - hop le |
| `!` | Warning - canh bao (van chay duoc) |
| `x` | Fail - loi (phai sua) |

Vi du output thanh cong:

```
  v file_exists:dem.path: D:/data/dem_30m.tif
  v file_exists:landuse.raster: D:/data/landuse_2020.tif
  v file_exists:landuse.lookup: D:/data/landuse_lookup.csv
  v file_exists:weather.stations: D:/data/weather_stations.csv
  v file_exists:weather.data_dir: D:/data/weather

Config OK -- project 'ExampleBasin_2024', domains: dem, landuse, soil, weather, streamflow
```

Vi du output loi:

```
  x file_exists:dem.path: File not found: D:/data/dem_30m.tif
  v file_exists:landuse.raster: D:/data/landuse_2020.tif

Failed: 1 check(s).
```

### Buoc 5.3: Sua loi va chay lai

Neu co loi `x`, kiem tra duong dan file trong config.yaml, dam bao file ton tai tai dia chi da khai bao. Chay lai `swatprep validate` cho den khi tat ca deu pass.

---

## 6. Chay tien xu ly (prepare)

### Buoc 6.1: Chay tat ca domain

```bash
swatprep build config.yaml
```

Lenh nay xu ly tat ca domain da khai bao trong config (dem, landuse, soil, weather, streamflow).

### Buoc 6.2: Chay mot domain cu the

De debug hoac xu ly tung phan:

```bash
swatprep build config.yaml --only weather
swatprep build config.yaml --only dem
swatprep build config.yaml --only landuse
swatprep build config.yaml --only soil
swatprep build config.yaml --only streamflow
```

### Buoc 6.3: Kiem tra ket qua

Output thanh cong:

```
Done  -> D:/QSWAT+/ExampleBasin/data
Manifest -> D:/QSWAT+/ExampleBasin/data/manifest.json
```

Hai file luon duoc tao khi co it nhat 1 domain xu ly thanh cong:

- `manifest.json` - danh sach file da tao, metadata
- `qa_report.md` - bao cao kiem tra chat luong

---

## 7. Kiem tra du lieu dau vao (inspect)

Su dung `inspect` de xem nhanh thong tin file dau vao truoc khi chay prepare.

### 7.1 Inspect raster (DEM, land-use, soil)

```bash
swatprep inspect raster D:/data/dem_30m.tif
```

Output:

```
File   : D:/data/dem_30m.tif
Driver : GTiff
CRS    : EPSG:32648
Bounds : BoundingBox(left=..., bottom=..., right=..., top=...)
Shape  : 1200 rows x 800 cols x 1 band(s)
Res    : (30.0, 30.0)
NoData : -9999.0
Dtype  : float32
```

**Yeu cau:** Can cai `swatprep[geo]` (rasterio).

### 7.2 Inspect weather CSV

```bash
swatprep inspect weather D:/data/weather/ST001.csv
```

Output:

```
File   : D:/data/weather/ST001.csv
Columns: ['date', 'precip', 'tmax', 'tmin']
Preview:
       date  precip   tmax   tmin
 2000-01-01     5.2   32.1   22.3
 2000-01-02     0.0   33.5   23.1
```

---

## 8. Chuyen doi dinh dang du lieu (convert)

swatprep cung cap cac lenh convert de chuyen dinh dang du lieu thu tu thanh dinh dang phu hop.

### 8.1 Convert climate (file .day sang CSV)

**Truong hop su dung:** Du lieu khi tuong dang file `.day` rieng le theo bien (R_STATION.day, Tx_STATION.day, Tm_STATION.day) can gop thanh CSV theo tram.

```bash
swatprep convert climate D:/data/raw_climate D:/data/weather_csv
```

**Tuy chon:**

| Option | Mac dinh | Mo ta |
|--------|----------|-------|
| `--suffix` | `.day` | Duoi file nguon |
| `--date-col` | `date` | Ten cot ngay |

**Mapping mac dinh:** `R_` = precip, `Tx_` = tmax, `Tm_` = tmin

### 8.2 Convert streamflow

**Truong hop su dung:** Chuyen du lieu dong chay tu wide-format hoac thu muc file rieng le sang long-format CSV.

**Tu wide-format CSV (cot = tram, dong = ngay):**

```bash
swatprep convert streamflow D:/data/streamflow_wide.csv D:/output/streamflow_long.csv
```

**Tu thu muc file rieng le:**

```bash
swatprep convert streamflow D:/data/streamflow_dir D:/output/streamflow_long.csv \
    --format per_station --glob "Q_*.csv"
```

### 8.3 Convert pcp (tao file .pcp cho SWAT 2012)

**Truong hop su dung:** Tao file .pcp dinh dang SWAT Classic tu file master metadata + file .day tho.

```bash
swatprep convert pcp D:/data/master.csv D:/data/raw_pcp D:/output/pcp_files
```

**Master CSV** can co cac cot: `ID, NAME, LAT, LONG, ELEVATION`

**Quy tac noi ten:** NAME=`pcp_STATION01` -> strip `pcp_` -> `STATION01` -> tim `R_STATION01.day`

**Tuy chon:**

| Option | Mac dinh | Mo ta |
|--------|----------|-------|
| `--name-prefix` | `pcp_` | Prefix cat bo tu cot NAME |
| `--raw-prefix` | `R_` | Prefix file .day |
| `--raw-suffix` | `.day` | Duoi file .day |
| `--value-col` | `Rain` | Ten cot gia tri mua |
| `--out-suffix` | `.pcp` | Duoi file output |

### 8.4 Convert tmp (tao file .tmp cho SWAT 2012)

**Truong hop su dung:** Tao file .tmp nhiet do dinh dang SWAT Classic.

```bash
swatprep convert tmp D:/data/master.csv D:/data/raw_tmp D:/output/tmp_files
```

**Tu dong phat hien dinh dang dau vao:**
- SWAT Classic: dong 1 = YYYYMMDD, cac dong tiep = `tmin,tmax`
- CSV: cac cot `date, tmax, tmin`

### 8.5 Convert swatplus (SWAT Classic -> SWAT+)

**Truong hop su dung:** Chuyen file .pcp va .tmp cua SWAT Classic sang dinh dang SWAT+.

```bash
swatprep convert swatplus D:/data/master.csv D:/data/pcp_dir D:/data/tmp_dir D:/output/swatplus
```

Lenh nay:
1. Doc master metadata
2. Ghep file pcp + tmp theo tung tram
3. Ghi file SWAT+ (.pcp, .tmp) va file index (pcp.cli, tmp.cli)

---

## 9. Su dung Python API

Ngoai CLI, ban co the su dung swatprep nhu thu vien Python trong script hoac Jupyter notebook.

### 9.1 Load config va validate

```python
from swatprep import SWATPrepProject

# Load tu file YAML
project = SWATPrepProject.from_config("config.yaml")

# Validate cau hinh va file
checks = project.validate()
for check in checks:
    print(f"[{check.status}] {check.name}: {check.message}")
```

### 9.2 Chay prepare

```python
result = project.build()

print(f"Thanh cong: {result.success}")
print(f"Output:    {result.output_dir}")
print(f"Manifest:  {result.manifest_path}")
print(f"Warnings:  {result.warning_count}")
print(f"Errors:    {result.error_count}")
```

### 9.3 Chay mot domain

```python
result = project.build(only="weather")
```

### 9.4 Truy cap config truc tiep

```python
from swatprep.config import SWATPrepConfig

cfg = SWATPrepConfig.from_yaml("config.yaml")
print(cfg.project.name)           # "ExampleBasin_2024"
print(cfg.project.crs)            # "EPSG:32648"
print(cfg.configured_domains())   # ["dem", "landuse", "soil", "weather", "streamflow"]
```

### 9.5 Su dung Converter truc tiep

```python
from swatprep.converters import DayFilesConverter

converter = DayFilesConverter(
    data_dir="D:/data/raw_climate",
    out_dir="D:/data/weather_csv",
)
result = converter.convert()
print(f"Tram: {result.stations_found}")
print(f"File da ghi: {result.files_written}")
```

---

## 10. Cau truc output

Sau khi chay `prepare`, thu muc output co cau truc:

```
output/
  manifest.json              # Danh sach file, metadata, trang thai
  qa_report.md               # Bao cao kiem tra chat luong

  spatial/                   # Domain: DEM
    dem_info.json             # Metadata DEM (CRS, bounds, resolution)
    dem_projected.tif         # DEM da reproject (neu can)

  landuse/                   # Domain: Land-use
    landuse_lookup.csv        # Bang anh xa ma
    landuse_raster_codes.csv  # Ma raster thuc te

  soil/                      # Domain: Soil
    usersoil.csv              # Bang tinh chat dat cho SWAT
    soil_raster_codes.csv     # Ma raster thuc te

  weather/                   # Domain: Weather
    ST001.pcp                 # Du lieu mua theo tram
    ST001.tmp                 # Du lieu nhiet do theo tram
    wgn.csv                   # Thong ke Weather Generator
    stations.csv              # Metadata tram

  observed/                  # Domain: Streamflow
    streamflow_ST001.csv      # Du lieu dong chay theo tram
    streamflow_meta.csv       # Metadata tram quan trac
```

---

## 11. Xu ly loi thuong gap

### Loi 1: Config schema error

```
Config schema error:
1 validation error for SWATPrepConfig
weather -> end
  Input should be a valid date (type=date_parsing)
```

**Nguyen nhan:** Dinh dang ngay sai.
**Cach sua:** Dung dinh dang ISO: `"2020-12-31"` (co dau ngoac kep).

### Loi 2: File not found

```
  x file_exists:dem.path: File not found: ./data/dem_30m.tif
```

**Nguyen nhan:** File khong ton tai tai dia chi khai bao.
**Cach sua:** Kiem tra duong dan trong config.yaml. Luu y duong dan tuong doi tinh tu thu muc chua file YAML.

### Loi 3: weather.end truoc weather.start

```
weather.end must be on or after weather.start
```

**Nguyen nhan:** Ngay ket thuc < ngay bat dau.
**Cach sua:** Dam bao `end >= start`.

### Loi 4: Thieu rasterio khi inspect raster

```
Install swatprep[geo] to inspect rasters.
```

**Cach sua:** `pip install -e .[geo,dev]`

### Loi 5: Weather writing skipped

```
  x weather_skipped: Weather writing skipped due to processor errors.
```

**Nguyen nhan:** Du lieu khi tuong khong hop le (thieu cot, gia tri sai, khoang trong).
**Cach sua:** Dung `swatprep inspect weather` de kiem tra tung file CSV. Kiem tra cac cot `date, precip, tmax, tmin` co day du va dung dinh dang.

---

## Quy trinh lam viec de xuat

```
1. Chuan bi du lieu thu    ->  Dat file vao thu muc co cau truc
2. Viet config.yaml        ->  Khai bao duong dan va tham so
3. swatprep validate       ->  Kiem tra config + file ton tai
4. swatprep inspect        ->  Xem nhanh noi dung file (tuy chon)
5. swatprep convert        ->  Chuyen dinh dang neu can (tuy chon)
6. swatprep build        ->  Chay tien xu ly chinh
7. Kiem tra output          ->  Doc manifest.json va qa_report.md
8. Nap vao QSWAT+/Editor  ->  Dua output vao workflow mo hinh hoa
```
