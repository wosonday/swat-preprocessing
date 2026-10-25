from app.services.environment import check_folder, get_report


def test_writable_folder_ok(tmp_path):
    assert check_folder("workspace", tmp_path, need_write=True).ok


def test_missing_folder_not_ok(tmp_path):
    c = check_folder("data_root", tmp_path / "nope", need_write=False)
    assert not c.ok and "not found" in c.detail


def test_file_is_not_a_folder(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert not check_folder("data_root", f, need_write=False).ok


def test_report_never_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("SWATPREP_DATA_ROOT", str(tmp_path / "missing"))
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(tmp_path))
    r = get_report()
    assert "swatprep" in r.packages
    assert {c.name for c in r.drivers} == {"GTiff", "AIG", "ESRI Shapefile", "GPKG"}
    assert not r.ok  # data_root không tồn tại

def test_unwritable_folder_not_ok(monkeypatch, tmp_path):
    def always_denied(*args, **kwargs):
        raise PermissionError("read-only file system")

    monkeypatch.setattr("app.services.environment.tempfile.TemporaryFile", always_denied)
    c = check_folder("workspace", tmp_path, need_write=True)
    assert not c.ok