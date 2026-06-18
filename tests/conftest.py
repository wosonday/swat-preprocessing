"""Shared pytest fixtures for swatprep tests.

All fixtures use synthetic, minimal data — no real basin datasets required.
"""

from __future__ import annotations

import textwrap
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir():
    """Temporary directory cleaned up after each test."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def minimal_config_dict():
    """Smallest valid config: only project section, no domains."""
    return {
        "project": {
            "name": "test_basin",
            "crs": "EPSG:32648",
            "output_dir": "./output",
            "targets": ["swatplus"],
        }
    }


@pytest.fixture
def minimal_config_yaml(tmp_dir):
    """Write minimal_config_dict to a temp YAML file; return its path."""
    import yaml

    data = {
        "project": {
            "name": "test_basin",
            "crs": "EPSG:32648",
            "output_dir": str(tmp_dir / "output"),
            "targets": ["swatplus"],
        }
    }
    config_path = tmp_dir / "config_minimal.yaml"
    config_path.write_text(yaml.dump(data), encoding="utf-8")
    return config_path


@pytest.fixture
def weather_stations_csv(tmp_dir):
    """Minimal stations metadata CSV."""
    content = textwrap.dedent("""\
        id,name,lat,lon,elev
        ST001,StationA,15.5,105.2,120
        ST002,StationB,15.8,105.6,95
    """)
    path = tmp_dir / "stations.csv"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def weather_data_dir(tmp_dir):
    """Directory with two minimal station CSV files (daily precip + tmax + tmin)."""
    import pandas as pd

    data_dir = tmp_dir / "weather"
    data_dir.mkdir()

    dates = pd.date_range("2000-01-01", periods=10, freq="D")
    for sid in ("ST001", "ST002"):
        df = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "precip": [1.0, 0.0, 5.2, 0.0, 0.0, 3.1, 0.0, 0.0, 0.0, 2.5],
            "tmax": [30.1, 31.2, 29.5, 28.0, 32.0, 27.5, 26.0, 28.9, 31.0, 30.5],
            "tmin": [22.0, 21.5, 20.0, 19.5, 23.0, 18.0, 17.5, 20.1, 22.5, 21.0],
        })
        df.to_csv(data_dir / f"{sid}.csv", index=False)

    return data_dir


@pytest.fixture
def streamflow_csv(tmp_dir):
    """Minimal streamflow CSV."""
    import pandas as pd

    dates = pd.date_range("2000-01-01", periods=10, freq="D")
    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "station_id": ["ST001"] * 10,
        "flow": [10.5, 9.8, 12.1, 8.3, 7.5, 11.2, 9.0, 8.8, 10.1, 9.5],
    })
    path = tmp_dir / "streamflow.csv"
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def landuse_lookup_csv(tmp_dir):
    """Land-use lookup: source_code → SWAT code + name."""
    content = textwrap.dedent("""\
        code,swat_code,swat_name
        10,AGRL,Agricultural Land Generic
        20,FRST,Forest Evergreen
        30,URBN,Residential
        40,WATR,Water
    """)
    path = tmp_dir / "landuse_lookup.csv"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def soil_table_csv(tmp_dir):
    """Minimal soil table with SWAT-required columns."""
    content = textwrap.dedent("""\
        soil_id,HYDGRP,SOL_ZMX,NLAYERS,SOL_Z1,SOL_BD1,SOL_AWC1,SOL_K1,SOL_CBN1,CLAY1,SILT1,SAND1
        1001,B,1500,2,300,1.35,0.18,12.5,1.2,25,40,35
        1002,C,2000,2,400,1.42,0.15,8.0,0.8,35,30,35
        1003,A,1000,1,200,1.28,0.22,25.0,1.5,15,50,35
    """)
    path = tmp_dir / "soil_table.csv"
    path.write_text(content, encoding="utf-8")
    return path
