"""Example 3: gap filling with a virtual station (v0.8.0): borrow the nearest gauge's correction.

Run:  uv run python docs/learning/03_fill_virtual_station.py
G1 is gauged; V1 has no observed day and lies about 10 km east of G1.
"""
import tempfile
from pathlib import Path

import pandas as pd

from swatprep.config import WeatherConfig
from swatprep.core.weather_fill import WeatherGapFiller, haversine_km

root = Path(tempfile.mkdtemp(prefix="fill_"))
days = pd.date_range("2000-01-01", periods=4, freq="D").strftime("%Y-%m-%d")
stations = pd.DataFrame({"id": ["G1", "V1"], "name": ["Gauge", "Virtual"], "lat": [15.0, 15.0],
                         "lon": [105.0, 105.093], "elev": [100, 100]})


def network(name: str, series: dict[str, list]) -> WeatherConfig:
    folder = root / name
    folder.mkdir()
    stations.to_csv(folder / "stations.csv", index=False)
    for sid, values in series.items():
        pd.DataFrame({"date": days, "precip": values}).to_csv(folder / f"{sid}.csv", index=False)
    return WeatherConfig(stations=folder / "stations.csv", data_dir=folder, variables=["precip"],
                         start=days[0], end=days[-1], missing_policy="warn")


observed = network("obs", {"G1": [2.0, 4.0, 6.0, None], "V1": [None] * 4})
grid = network("grid", {"G1": [1.0, 2.0, 3.0, 4.0], "V1": [1.0, 2.0, 3.0, 4.0]})   # e.g. extracted from a NetCDF

print(f"distance G1-V1: {haversine_km(15.0, 105.0, 15.0, 105.093):.1f} km")
for options in ({}, {"fill_ungauged": True}, {"fill_ungauged": True, "max_borrow_km": 5}):
    result = WeatherGapFiller(observed, grid, min_overlap_days=1, **options).run()
    v1 = result.report.set_index("station_id").loc["V1"]
    print(f"\n{options or 'default'}")
    print("  V1 filled:", result.daily["precip"]["V1"].tolist())
    print(f"  correction: {v1['correction_type']} {v1['correction_value']}, from {v1['correction_from']}, "
          f"{v1['distance_km']} km, status {v1['status']}")
