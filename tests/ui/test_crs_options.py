from app.services import crs_options as module
from app.services.crs_options import COMMON, check_crs, crs_label, crs_options


def test_common_crs_come_first_then_all_epsg_projected():
    options = crs_options()
    assert list(options)[:len(COMMON)] == list(COMMON)
    assert len(options) > 1000 and "EPSG:9210" in options        # VN-2000 / TM-3 105-45
    assert "EPSG:4326" not in options                              # geographic, not projected


def test_label_shows_code_and_name():
    assert crs_label("EPSG:3405") == "EPSG:3405 · VN-2000 / UTM zone 48N"
    assert crs_label("+proj=utm +zone=48") == "+proj=utm +zone=48"


def test_without_pyproj_only_common(monkeypatch):
    def no_pyproj():
        raise ImportError("pyproj")

    monkeypatch.setattr(module, "_epsg_projected", no_pyproj)
    crs_options.cache_clear()
    try:
        assert crs_options() == COMMON
    finally:
        crs_options.cache_clear()


def test_check_crs():
    assert check_crs("EPSG:32648") == ("ok", "WGS 84 / UTM zone 48N (metre)")
    assert check_crs("EPSG:4326")[0] == "warn"
    assert check_crs("VN-2000 / UTM") == ("error", "not a recognised CRS")
    assert check_crs("+proj=utm +zone=48 +datum=WGS84 +units=m +no_defs")[0] == "ok"
