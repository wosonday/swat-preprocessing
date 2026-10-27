import shutil
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture(autouse=True)
def isolated_history(tmp_path_factory, monkeypatch):
    """Never touch the real ~/.swatprep during tests."""
    monkeypatch.setenv("SWATPREP_STATE_DIR", str(tmp_path_factory.mktemp("state")))


@pytest.fixture
def example_project(tmp_path: Path) -> Path:
    """A copy of examples/config_minimal.yaml + examples/data in tmp_path; returns the config path."""
    shutil.copytree(EXAMPLES / "data", tmp_path / "data")
    config = tmp_path / "config_minimal.yaml"
    shutil.copy(EXAMPLES / "config_minimal.yaml", config)
    return config
