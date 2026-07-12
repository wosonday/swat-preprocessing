"""High-level API for swatprep.

    from swatprep import SWATPrepProject

    project = SWATPrepProject.from_config("config.yaml")
    result  = project.build()

    print(result.output_dir)
    print(result.warning_count)
    print(result.manifest_path)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import SWATPrepConfig
from .errors import ConfigError
from .qa import QACheck, failures, warnings


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
        return cls(SWATPrepConfig.from_yaml(path))

    def build(self, only: str | None = None) -> PrepareResult:
        """Run the full preprocessing pipeline.

        Args:
            only: If set, run only this domain. Manifest is still written.

        Returns:
            PrepareResult with QA checks, output_dir, and manifest_path.
        """
        if only is not None and only not in _VALID_DOMAINS:
            raise ConfigError(
                f"Unknown domain '{only}'. Valid: {', '.join(_VALID_DOMAINS)}"
            )

        cfg = self.config
        output_dir = cfg.project.output_dir
        all_qa: list[QACheck] = []
        domains_run: list[str] = []

        domains_to_run = [only] if only else cfg.configured_domains()

        # ------------------------------------------------------------------ #
        # DEM                                                                  #
        # ------------------------------------------------------------------ #
        if "dem" in domains_to_run and cfg.dem is not None:
            from .core.dem import DEMPreprocessor
            from .writers.spatial import SpatialWriter

            result = DEMPreprocessor(cfg.dem, project_crs=cfg.project.crs).run()
            all_qa.extend(result.qa)
            domains_run.append("dem")

            if not failures(result.qa):
                spatial_out = output_dir / "spatial"
                written = SpatialWriter(result, spatial_out).write()
                all_qa.append(QACheck(
                    name="dem_written",
                    status="pass",
                    message=f"{len(written)} spatial file(s) written to {spatial_out}",
                ))

        # ------------------------------------------------------------------ #
        # LandUse                                                              #
        # ------------------------------------------------------------------ #
        if "landuse" in domains_to_run and cfg.landuse is not None:
            from .core.landuse import LandUsePreprocessor
            from .writers.landuse import LandUseWriter

            result = LandUsePreprocessor(cfg.landuse).run()
            all_qa.extend(result.qa)
            domains_run.append("landuse")

            if not failures(result.qa):
                written = LandUseWriter(result, output_dir).write()
                all_qa.append(QACheck(
                    name="landuse_written",
                    status="pass",
                    message=f"{len(written)} land-use file(s) written to {output_dir / 'landuse'}",
                ))

        # ------------------------------------------------------------------ #
        # Soil                                                                 #
        # ------------------------------------------------------------------ #
        if "soil" in domains_to_run and cfg.soil is not None:
            from .core.soil import SoilPreprocessor
            from .writers.soil import SoilWriter

            result = SoilPreprocessor(cfg.soil).run()
            all_qa.extend(result.qa)
            domains_run.append("soil")

            if not failures(result.qa):
                soil_out = output_dir / "soil"
                written = SoilWriter(result, soil_out).write()
                all_qa.append(QACheck(
                    name="soil_written",
                    status="pass",
                    message=f"{len(written)} soil file(s) written to {soil_out}",
                ))

        # ------------------------------------------------------------------ #
        # Weather                                                              #
        # ------------------------------------------------------------------ #
        if "weather" in domains_to_run and cfg.weather is not None:
            from .core.weather import WeatherPreprocessor

            result = WeatherPreprocessor(cfg.weather).run()
            all_qa.extend(result.qa)
            domains_run.append("weather")

            if not failures(result.qa):
                weather_out = output_dir / "weather"
                targets = list(cfg.project.targets) or ["swatplus"]
                # When both models are requested, keep each format in its own
                # sub-directory so identically-named files don't collide.
                multi = len({"swatplus", "swat"} & set(targets)) > 1

                written: list[Path] = []
                for target in targets:
                    dest = weather_out / target if multi else weather_out
                    if target == "swatplus":
                        from .writers.weather_plus import SWATPlusWeatherWriter
                        written += SWATPlusWeatherWriter(result, dest).write()
                    elif target == "swat":
                        from .writers.weather import WeatherWriter
                        written += WeatherWriter(result, dest).write()

                all_qa.append(QACheck(
                    name="weather_written",
                    status="pass",
                    message=(
                        f"{len(written)} weather file(s) written to {weather_out} "
                        f"(targets: {', '.join(targets)})"
                    ),
                ))
            else:
                all_qa.append(QACheck(
                    name="weather_skipped",
                    status="fail",
                    message="Weather writing skipped due to processor errors.",
                ))

        # ------------------------------------------------------------------ #
        # Streamflow                                                           #
        # ------------------------------------------------------------------ #
        if "streamflow" in domains_to_run and cfg.streamflow is not None:
            from .core.streamflow import StreamflowPreprocessor
            from .writers.observations import ObservationWriter

            result = StreamflowPreprocessor(cfg.streamflow).run()
            all_qa.extend(result.qa)
            domains_run.append("streamflow")

            if not failures(result.qa):
                obs_out = output_dir / "observed"
                written = ObservationWriter(result, obs_out).write()
                all_qa.append(QACheck(
                    name="streamflow_written",
                    status="pass",
                    message=f"{len(written)} observation file(s) written to {obs_out}",
                ))

        # ------------------------------------------------------------------ #
        # Manifest + QA report                                                 #
        # ------------------------------------------------------------------ #
        manifest_path: Path | None = None
        if domains_run:
            from .writers.manifest import write_manifest
            manifest_path, report_path = write_manifest(
                output_dir=output_dir,
                project_name=cfg.project.name,
                domains=domains_run,
                all_qa=all_qa,
            )
            all_qa.append(QACheck(
                name="manifest_written",
                status="pass",
                message=f"Manifest written to {manifest_path.name}",
            ))

        return PrepareResult(
            output_dir=output_dir,
            manifest_path=manifest_path,
            qa_checks=all_qa,
        )

    def validate(self) -> list[QACheck]:
        """Check config completeness and input file existence."""
        checks: list[QACheck] = []
        cfg = self.config

        if cfg.project.boundary is not None:
            _check_path(cfg.project.boundary, "project.boundary", checks)
        if cfg.dem:
            _check_path(cfg.dem.path, "dem.path", checks)
        if cfg.landuse:
            _check_path(cfg.landuse.raster, "landuse.raster", checks)
            _check_path(cfg.landuse.lookup, "landuse.lookup", checks)
        if cfg.soil:
            _check_path(cfg.soil.raster, "soil.raster", checks)
            _check_path(cfg.soil.table, "soil.table", checks)
        if cfg.weather:
            if cfg.weather.stations is not None:
                _check_path(cfg.weather.stations, "weather.stations", checks)
            if cfg.weather.data_dir is not None:
                _check_path(cfg.weather.data_dir, "weather.data_dir", checks)
            if cfg.weather.precip is not None:
                _check_path(cfg.weather.precip.stations, "weather.precip.stations", checks)
                _check_path(cfg.weather.precip.data_dir, "weather.precip.data_dir", checks)
            if cfg.weather.temp is not None:
                _check_path(cfg.weather.temp.stations, "weather.temp.stations", checks)
                _check_path(cfg.weather.temp.data_dir, "weather.temp.data_dir", checks)
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
        checks.append(QACheck(
            name=f"file_exists:{label}",
            status="fail",
            message=f"File not found: {path}",
            context={"path": str(path)},
        ))
