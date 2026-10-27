from app.services.recent import MAX_RECENT, add_recent, load_recent, state_file


def test_empty_history(tmp_path, monkeypatch):
    monkeypatch.setenv("SWATPREP_STATE_DIR", str(tmp_path / "state"))
    assert load_recent() == []


def test_newest_first_without_duplicates(tmp_path, monkeypatch):
    monkeypatch.setenv("SWATPREP_STATE_DIR", str(tmp_path / "state"))
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    add_recent(a)
    add_recent(b)
    add_recent(a)
    assert load_recent() == [str(a.resolve()), str(b.resolve())]


def test_missing_folders_are_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv("SWATPREP_STATE_DIR", str(tmp_path / "state"))
    gone = tmp_path / "gone"
    gone.mkdir()
    add_recent(gone)
    gone.rmdir()
    assert load_recent() == []


def test_history_is_capped(tmp_path, monkeypatch):
    monkeypatch.setenv("SWATPREP_STATE_DIR", str(tmp_path / "state"))
    for i in range(MAX_RECENT + 3):
        d = tmp_path / f"p{i}"
        d.mkdir()
        add_recent(d)
    assert len(load_recent()) == MAX_RECENT


def test_corrupt_file_means_no_history(tmp_path, monkeypatch):
    monkeypatch.setenv("SWATPREP_STATE_DIR", str(tmp_path))
    state_file().write_text("not json", encoding="utf-8")
    assert load_recent() == []
