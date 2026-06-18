"""SpatialWriter: write DEM metadata summary to the output package."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..core.dem import DEMResult


class SpatialWriter:
    """Write DEM inspection summary to output/spatial/."""

    def __init__(self, result: DEMResult, output_dir: Path) -> None:
        self.result = result
        self.output_dir = output_dir

    def write(self) -> list[Path]:
        out = self.output_dir
        out.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []

        summary = {
            "source_path": str(self.result.path),
            "crs": self.result.crs,
            "shape": list(self.result.shape) if self.result.shape else None,
            "resolution": list(self.result.resolution) if self.result.resolution else None,
            "elevation_range": (
                list(self.result.elevation_range)
                if self.result.elevation_range else None
            ),
            "nodata": self.result.nodata,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        info_path = out / "dem_info.json"
        info_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        written.append(info_path)

        return written
