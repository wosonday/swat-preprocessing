"""WeatherFillWriter: write a WeatherFillResult back out in swatprep's
native per-station CSV format (the same shape WeatherPreprocessor already
reads), ready to point weather.data_dir at.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..core.weather_fill import WeatherFillResult


class WeatherFillWriter:
    """Write a WeatherFillResult as stations.csv + {id}.csv per station +
    fill_report.csv."""

    def __init__(self, result: WeatherFillResult, output_dir: Path) -> None:
        self.result = result
        self.output_dir = output_dir

    def write(self) -> list[Path]:
        out = self.output_dir
        out.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []

        stations = self.result.stations
        sta_path = out / "stations.csv"
        stations.reset_index().to_csv(sta_path, index=False)
        written.append(sta_path)

        variables = list(self.result.daily.keys())
        for sid in stations.index:
            cols: dict[str, pd.Series] = {}
            for var in variables:
                wide = self.result.daily[var]
                if sid in wide.columns:
                    cols[var] = wide[sid]
            if not cols:
                continue
            df = pd.DataFrame(cols)
            df.index.name = "date"
            path = out / f"{sid}.csv"
            df.reset_index().to_csv(path, index=False, date_format="%Y-%m-%d")
            written.append(path)

        report_path = out / "fill_report.csv"
        self.result.report.to_csv(report_path, index=False)
        written.append(report_path)

        return written
