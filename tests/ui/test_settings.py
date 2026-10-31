from pathlib import Path

from app.services.settings import load_settings


def test_not_set_when_env_unset(monkeypatch):
    monkeypatch.delenv("SWATPREP_DATA_ROOT", raising=False)
    monkeypatch.delenv("SWATPREP_WORKSPACE", raising=False)
    s = load_settings()
    assert s.data_root is None
    assert s.workspace is None


def test_empty_variable_counts_as_not_set(monkeypatch):
    monkeypatch.setenv("SWATPREP_DATA_ROOT", "")
    assert load_settings().data_root is None


def test_reads_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SWATPREP_DATA_ROOT", str(tmp_path / "d"))
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(tmp_path / "w"))
    s = load_settings()
    assert s.data_root == tmp_path / "d"
    assert s.workspace == tmp_path / "w"
    assert isinstance(s.data_root, Path)
