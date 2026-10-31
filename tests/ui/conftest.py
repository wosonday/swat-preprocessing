import shutil
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture(autouse=True)
def isolated_history(tmp_path_factory, monkeypatch):
    """Never touch the real ~/.swatprep during tests."""
    monkeypatch.setenv("SWATPREP_STATE_DIR", str(tmp_path_factory.mktemp("state")))


@pytest.fixture
def open_project():
    """Open a project folder from the Projects screen of an AppTest page."""
    def _open(at, folder: Path):
        at.text_input(key="home_open_dir").set_value(str(folder))
        at.button(key="home_open").click().run()
        assert not at.exception
        return at
    return _open


@pytest.fixture
def example_project(tmp_path: Path) -> Path:
    """A copy of examples/config_minimal.yaml + examples/data in tmp_path; returns the config path."""
    shutil.copytree(EXAMPLES / "data", tmp_path / "data")
    config = tmp_path / "config_minimal.yaml"
    shutil.copy(EXAMPLES / "config_minimal.yaml", config)
    return config


FILL_BLOCK = """  fill:
    type: csv
    output_dir: "./data/filled"
    csv:
      stations: "./data/weather_stations.csv"
      data_dir: "./data/weather"

"""


@pytest.fixture
def filled_project(example_project: Path) -> Path:
    """example_project with Jan 3-4 precip missing in the observed file and a filled copy in data/filled."""
    data = example_project.parent / "data"
    filled = data / "filled"
    filled.mkdir()
    shutil.copy(data / "weather_stations.csv", filled / "stations.csv")
    shutil.copy(data / "weather" / "ST001.csv", filled / "ST001.csv")
    (filled / "fill_report.csv").write_text(
        "station_id,variable,n_missing,n_filled,n_still_missing,n_overlap,correction_type,correction_value,status\n"
        "ST001,precip,2,2,0,8,ratio,1.05,warn\n", encoding="utf-8")
    observed = data / "weather" / "ST001.csv"
    lines = observed.read_text(encoding="utf-8").splitlines()
    for i in (3, 4):                                   # 2000-01-03 and 2000-01-04: empty precip
        date, _precip, tmax, tmin = lines[i].split(",")
        lines[i] = f"{date},,{tmax},{tmin}"
    observed.write_text("\n".join(lines) + "\n", encoding="utf-8")
    text = example_project.read_text(encoding="utf-8")
    example_project.write_text(text.replace("streamflow:", FILL_BLOCK + "streamflow:", 1), encoding="utf-8")
    return example_project
