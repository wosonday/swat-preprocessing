"""High-level API for swatprep.

    from swatprep import SWATPrepProject

    project = SWATPrepProject.from_config("config.yaml")
    result = project.prepare()

    print(result.output_dir)
    print(result.warning_count)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import SWATPrepConfig
from .errors import ConfigError
from .qa import QACheck, all_pass, failures, warnings


@dataclass
class PrepareResult:
    output_dir: Path
    manifest_path: Path | None
    qa_checks: list[QACheck] = field(default_factory=list)

    @property
    def warning_count(self) -> int:
        return len(warnings(self.qa_checks))

    @property
    def error_count(self) -> int:
        return len(failures(self.qa_checks))

    @property
    def success(self) -> bool:
        return self.error_count == 0


_VALID_DOMAINS = ("dem", "landuse", "soil", "weather", "streamflow")


class SWATPrepProject:
    """Orchestrates config loading, preprocessing, and writing."""

    def __init__(self, config: SWATPrepConfig) -> None:
        self.config = config

    @classmethod
    def from_config(cls, path: str | Path) -> "SWATPrepProject":
        """Load config from YAML and return a project instance."""
        return cls(SWATPrepConfig.from_yaml(path))

    def prepare(self, only: str | None = None) -> PrepareResult:
        """Run the preprocessing pipeline.

        Args:
            only: If set, run only this domain (dem | landuse | soil | weather | streamflow).

        Returns:
            PrepareResult with QA checks and output paths.
        """
        if only is not None and only not in _VALID_DOMAINS:
            raise ConfigError(
                f"Unknown domain '{only}'. Valid options: {', '.join(_VALID_DOMAINS)}"
            )

        # Milestone 2+: each domain will call its processor and writer here.
        raise NotImplementedError(
            "Processors not yet implemented. "
            "Run 'swatprep validate' to check config and file paths."
        )

    def validate(self) -> list[QACheck]:
        """Check config completeness and input file existence.

        Returns QACheck list. Does not write any output.
        """
        checks: list[QACheck] = []
        cfg = self.config

        # Project boundary
        if cfg.project.boundary is not None:
            _check_path(cfg.project.boundary, "project.boundary", checks)

        # Per-domain file checks
        if cfg.dem:
            _check_path(cfg.dem.path, "dem.path", checks)

        if cfg.landuse:
            _check_path(cfg.landuse.raster, "landuse.raster", checks)
            _check_path(cfg.landuse.lookup, "landuse.lookup", checks)

        if cfg.soil:
            _check_path(cfg.soil.raster, "soil.raster", checks)
            _check_path(cfg.soil.table, "soil.table", checks)

        if cfg.weather:
            _check_path(cfg.weather.stations, "weather.stations", checks)
            _check_path(cfg.weather.data_dir, "weather.data_dir", checks)

        if cfg.streamflow:
            _check_path(cfg.streamflow.path, "streamflow.path", checks)

        return checks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_path(path: Path, label: str, checks: list[QACheck]) -> None:
    if path.exists():
        checks.append(QACheck(name=f"file_exists:{label}", status="pass", message=str(path)))
    else:
        checks.append(
            QACheck(
                name=f"file_exists:{label}",
                status="fail",
                message=f"File not found: {path}",
                context={"path": str(path)},
            )
        )
