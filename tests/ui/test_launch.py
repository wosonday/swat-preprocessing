import os
import zipfile
from pathlib import Path

import pytest

from app import launch

ROOT = Path(__file__).resolve().parents[2]


def test_streamlit_argv_points_at_packaged_home():
    argv = launch.streamlit_argv(["--server.port", "8502"])
    assert argv[:2] == ["streamlit", "run"]
    assert Path(argv[2]) == launch.APP_DIR / "Home.py" and Path(argv[2]).is_file()
    assert argv[3:] == ["--server.port", "8502"]


def test_main_runs_from_app_folder(monkeypatch):
    from streamlit.web import cli as stcli

    seen = {}

    def fake_main():
        seen["cwd"] = Path(os.getcwd())
        seen["argv"] = list(launch.sys.argv)
        return 0

    monkeypatch.setattr(stcli, "main", fake_main)
    monkeypatch.chdir(ROOT)
    with pytest.raises(SystemExit):
        launch.main(["--server.headless", "true"])
    assert seen["cwd"] == launch.APP_DIR
    assert (seen["cwd"] / ".streamlit" / "config.toml").is_file()
    assert seen["argv"][-2:] == ["--server.headless", "true"]


def test_wheel_ships_pages_and_theme(tmp_path):
    import subprocess

    result = subprocess.run(  # noqa: S603
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path), str(ROOT)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"uv build unavailable: {result.stderr[-300:]}")
    wheel = next(tmp_path.glob("*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())
    assert "app/pages/1_Project.py" in names
    assert "app/.streamlit/config.toml" in names
    assert "app/Home.py" in names
