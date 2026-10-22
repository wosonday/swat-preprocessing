"""ClipProcessor: crop rasters to project.boundary and write them (config section `clip`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..config import ClipItemConfig
from ..qa import QACheck
from ..utils.raster import clip_raster


@dataclass
class ClipResult:
    """Output of ClipProcessor.run(): the rasters written and the QA checks."""

    written: list[Path] = field(default_factory=list)
    qa: list[QACheck] = field(default_factory=list)


class ClipProcessor:
    """Crop each `clip` item (src -> dst) to the project boundary's bounding box."""

    def __init__(self, items: list[ClipItemConfig], boundary: Path) -> None:
        self.items = items
        self.boundary = boundary

    def run(self) -> ClipResult:
        res = ClipResult()
        for item in self.items:
            name = item.dst.name
            if not item.src.exists():
                res.qa.append(QACheck(
                    name=f"clip_src_missing:{name}", status="fail",
                    message=f"clip source not found: {item.src}",
                ))
            elif item.src.resolve() == item.dst.resolve():
                res.qa.append(QACheck(
                    name=f"clip_same_file:{name}", status="fail",
                    message="clip src and dst are the same file",
                ))
            elif self._is_fresh(item):
                res.qa.append(QACheck(
                    name=f"clip_skipped:{name}", status="pass",
                    message=f"{name} is newer than its source and the boundary; "
                            "not re-clipped (delete it to force)",
                ))
            else:
                self._clip(item, res)
        return res

    def _clip(self, item: ClipItemConfig, res: ClipResult) -> None:
        name = item.dst.name
        try:
            clip_raster(item.src, item.dst, self.boundary, mask=item.mask)
        except ImportError:
            res.qa.append(QACheck(
                name=f"clip_failed:{name}", status="fail",
                message="clipping needs geopandas and rasterio: pip install 'swatprep[geo]'",
            ))
        except Exception as exc:
            res.qa.append(QACheck(
                name=f"clip_failed:{name}", status="fail",
                message=f"could not clip {item.src.name}: {exc}",
                context={"src": str(item.src), "dst": str(item.dst)},
            ))
        else:
            res.written.append(item.dst)
            res.qa.append(QACheck(
                name=f"clip_written:{name}", status="pass",
                message=f"{item.src.name} clipped to the boundary -> {item.dst}",
            ))

    def _is_fresh(self, item: ClipItemConfig) -> bool:
        """True when dst exists and is newer than the source and all boundary files."""
        if not item.dst.exists():
            return False
        b = self.boundary
        sidecars = [p for p in b.parent.glob(b.stem + ".*") if p.is_file()] or [b]
        newest = max(p.stat().st_mtime for p in [item.src, *sidecars])
        return item.dst.stat().st_mtime >= newest


def clip_into_output(src, name, out_dir, boundary, enabled, qa) -> Path | None:
    """Domain-level clip: write `out_dir/name` cropped to `boundary`, appending QA to `qa`.

    Returns the boundary to use for window-limited reads, or None when clipping is
    off (`enabled` False, no boundary) or the source is missing (the domain's own
    preprocessor reports that).
    """
    if not enabled or boundary is None or not Path(src).exists():
        return None
    qa.extend(ClipProcessor([ClipItemConfig(src=src, dst=out_dir / name)], boundary).run().qa)
    return boundary


def basin_rows(df: pd.DataFrame, key_col: str, codes: set, label: str, qa: list) -> pd.DataFrame:
    """Rows of `df` whose `key_col` code is present in the basin (`codes`)."""
    keep = pd.to_numeric(df[key_col], errors="coerce").isin(codes)
    out = df[keep]
    qa.append(QACheck(
        name=f"{label}_table_filtered", status="pass",
        message=f"{label}: table restricted to the {len(out)} of {len(df)} row(s) "
                "whose code occurs inside the project boundary",
    ))
    return out
