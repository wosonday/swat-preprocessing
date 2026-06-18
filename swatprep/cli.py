"""Click-based CLI for swatprep.

Entry point: swatprep (registered in pyproject.toml)

Commands:
    swatprep validate config.yaml
    swatprep prepare config.yaml [--only DOMAIN]
    swatprep inspect raster PATH
    swatprep inspect weather PATH
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from pydantic import ValidationError

from .errors import SWATPrepError


@click.group()
@click.version_option(package_name="swatprep")
def main() -> None:
    """swatprep — Preprocess raw data for SWAT/SWAT+ workflows."""


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@main.command()
@click.argument("config", type=click.Path(exists=True, path_type=Path))
def validate(config: Path) -> None:
    """Validate config and input file existence without writing outputs."""
    try:
        from .config import SWATPrepConfig
        from .api import SWATPrepProject
        from .qa import failures, warnings

        cfg = SWATPrepConfig.from_yaml(config)
        project = SWATPrepProject(cfg)
        checks = project.validate()

        warn_list = warnings(checks)
        fail_list = failures(checks)

        for c in checks:
            symbol = {"pass": "✓", "warn": "!", "fail": "✗"}[c.status]
            click.echo(f"  {symbol} {c.name}: {c.message}")

        if warn_list:
            click.echo(f"\nWarnings: {len(warn_list)}")
        if fail_list:
            click.echo(f"\nFailed: {len(fail_list)} check(s).", err=True)
            sys.exit(1)

        domains = cfg.configured_domains()
        click.echo(
            f"\nConfig OK — project '{cfg.project.name}', "
            f"domains: {', '.join(domains) or 'none configured'}"
        )

    except ValidationError as e:
        click.echo(f"Config schema error:\n{e}", err=True)
        sys.exit(1)
    except SWATPrepError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------

_DOMAINS = ("dem", "landuse", "soil", "weather", "streamflow")


@main.command()
@click.argument("config", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--only",
    default=None,
    type=click.Choice(_DOMAINS),
    help="Run only one domain (useful for debugging).",
)
def prepare(config: Path, only: str | None) -> None:
    """Prepare input data and write SWAT-ready output package."""
    try:
        from .api import SWATPrepProject

        project = SWATPrepProject.from_config(config)
        result = project.prepare(only=only)

        click.echo(f"Done → {result.output_dir}")
        if result.warning_count:
            click.echo(f"Warnings: {result.warning_count}")
        if not result.success:
            click.echo(f"Failed: {result.error_count} error(s).", err=True)
            sys.exit(1)

    except NotImplementedError as e:
        click.echo(f"Not implemented yet: {e}", err=True)
        sys.exit(1)
    except SWATPrepError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValidationError as e:
        click.echo(f"Config schema error:\n{e}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


@main.command()
@click.argument("kind", type=click.Choice(["raster", "weather"]))
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def inspect(kind: str, path: Path) -> None:
    """Inspect a raw input file and print a summary."""
    if kind == "raster":
        _inspect_raster(path)
    elif kind == "weather":
        _inspect_weather(path)


def _inspect_raster(path: Path) -> None:
    try:
        import rasterio  # type: ignore
    except ImportError:
        click.echo("Install swatprep[geo] to inspect rasters.", err=True)
        sys.exit(1)

    with rasterio.open(path) as ds:
        click.echo(f"File   : {path}")
        click.echo(f"Driver : {ds.driver}")
        click.echo(f"CRS    : {ds.crs}")
        click.echo(f"Bounds : {ds.bounds}")
        click.echo(f"Shape  : {ds.height} rows × {ds.width} cols × {ds.count} band(s)")
        click.echo(f"Res    : {ds.res}")
        click.echo(f"NoData : {ds.nodata}")
        click.echo(f"Dtype  : {ds.dtypes[0]}")


def _inspect_weather(path: Path) -> None:
    import pandas as pd

    df = pd.read_csv(path, nrows=5)
    click.echo(f"File   : {path}")
    click.echo(f"Columns: {list(df.columns)}")
    click.echo(f"Preview:\n{df.to_string(index=False)}")


if __name__ == "__main__":
    main()
