"""Click-based CLI for swatprep.

Entry point: swatprep (registered in pyproject.toml)

Commands:
    swatprep validate config.yaml
    swatprep build config.yaml [--only DOMAIN]
    swatprep inspect raster PATH
    swatprep inspect weather PATH
    swatprep convert climate DATA_DIR OUT_DIR
    swatprep convert streamflow SOURCE OUT_PATH
    swatprep convert weather [--pcp-master ... --pcp-dir ...] [--tmp-master ... --tmp-dir ...] OUT_DIR
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
    """swatprep -- Preprocess raw data for SWAT/SWAT+ workflows."""


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
            symbol = {"pass": "v", "warn": "!", "fail": "x"}[c.status]
            click.echo(f"  {symbol} {c.name}: {c.message}")

        if warn_list:
            click.echo(f"\nWarnings: {len(warn_list)}")
        if fail_list:
            click.echo(f"\nFailed: {len(fail_list)} check(s).", err=True)
            sys.exit(1)

        domains = cfg.configured_domains()
        click.echo(
            f"\nConfig OK -- project '{cfg.project.name}', "
            f"domains: {', '.join(domains) or 'none configured'}"
        )

    except ValidationError as e:
        click.echo(f"Config schema error:\n{e}", err=True)
        sys.exit(1)
    except SWATPrepError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# build
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
def build(config: Path, only: str | None) -> None:
    """Prepare input data and write SWAT-ready output package."""
    try:
        from .api import SWATPrepProject

        project = SWATPrepProject.from_config(config)
        result = project.build(only=only)

        if result.manifest_path:
            click.echo(f"Done  -> {result.output_dir}")
            click.echo(f"Manifest -> {result.manifest_path}")
        else:
            click.echo("No domains configured -- nothing to build.")

        if result.warning_count:
            click.echo(f"Warnings: {result.warning_count}")
        if not result.success:
            click.echo(f"Failed: {result.error_count} error(s).", err=True)
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
        click.echo(f"Shape  : {ds.height} rows x {ds.width} cols x {ds.count} band(s)")
        click.echo(f"Res    : {ds.res}")
        click.echo(f"NoData : {ds.nodata}")
        click.echo(f"Dtype  : {ds.dtypes[0]}")


def _inspect_weather(path: Path) -> None:
    import pandas as pd

    df = pd.read_csv(path, nrows=5)
    click.echo(f"File   : {path}")
    click.echo(f"Columns: {list(df.columns)}")
    click.echo(f"Preview:\n{df.to_string(index=False)}")


# ---------------------------------------------------------------------------
# convert
# ---------------------------------------------------------------------------


@main.group()
def convert() -> None:
    """Convert raw data formats to swatprep-compatible CSV files."""


@convert.command("climate")
@click.argument("data_dir", type=click.Path(exists=True, path_type=Path))
@click.argument("out_dir", type=click.Path(path_type=Path))
@click.option("--suffix", default=".day", show_default=True, help="File suffix.")
@click.option(
    "--date-col", default="date", show_default=True,
    help="Name of the date column in source files.",
)
def convert_climate(data_dir: Path, out_dir: Path, suffix: str, date_col: str) -> None:
    """Merge per-variable .day files into per-station CSV files.

    Uses default default prefix mapping:
    R_STATION.day -> precip, Tx_STATION.day -> tmax, Tm_STATION.day -> tmin.

    DATA_DIR  Directory containing files like R_STATION.day, Tx_STATION.day ...
    OUT_DIR   Directory where per-station merged CSVs will be written.
    """
    from .converters import DayFilesConverter
    from .qa import failures, warnings

    converter = DayFilesConverter(
        data_dir=data_dir,
        out_dir=out_dir,
        prefixes=None,
        suffix=suffix,
        date_col=date_col,
    )
    result = converter.convert()

    warn_list = warnings(result.qa)
    fail_list = failures(result.qa)

    for c in result.qa:
        symbol = {"pass": "v", "warn": "!", "fail": "x"}[c.status]
        click.echo(f"  {symbol} {c.name}: {c.message}")

    click.echo(f"\nStations processed : {len(result.stations_found)}")
    click.echo(f"Files written      : {len(result.files_written)}")
    click.echo(f"Output dir         : {out_dir}")

    if warn_list:
        click.echo(f"Warnings: {len(warn_list)}")
    if fail_list:
        click.echo(f"Failed: {len(fail_list)} check(s).", err=True)
        sys.exit(1)

@convert.command("streamflow")
@click.argument("source", type=click.Path(exists=True, path_type=Path))
@click.argument("out_path", type=click.Path(path_type=Path))
@click.option(
    "--format", "input_format",
    type=click.Choice(["wide_yyyymmdd", "per_station"]),
    default="wide_yyyymmdd", show_default=True,
    help=(
        "Input format: wide_yyyymmdd for wide CSV with YYYYMMDD date column, "
        "per_station for directory of individual station CSVs."
    ),
)
@click.option(
    "--glob", "glob_pattern", default="Q_*.csv", show_default=True,
    help="Glob pattern for per_station mode.",
)
@click.option("--date-col", default="date", show_default=True)
@click.option("--value-col", default="flow", show_default=True,
              help="Name of flow column in output.")
@click.option("--src-value-col", default="discharge", show_default=True,
              help="Name of flow column in per-station source files.")
def convert_streamflow(
    source: Path,
    out_path: Path,
    input_format: str,
    glob_pattern: str,
    date_col: str,
    value_col: str,
    src_value_col: str,
) -> None:
    """Convert streamflow data to long-format CSV for swatprep.

    SOURCE    Wide-format CSV file OR directory of per-station CSVs.
    OUT_PATH  Path for the long-format output CSV.
    """
    from .converters import StreamflowConverter
    from .qa import failures, warnings

    converter = StreamflowConverter(
        source=source,
        input_format=input_format,
        glob_pattern=glob_pattern,
        date_col=date_col,
        value_col=value_col,
        src_value_col=src_value_col,
    )
    result = converter.convert(out_path=out_path)

    warn_list = warnings(result.qa)
    fail_list = failures(result.qa)

    for c in result.qa:
        symbol = {"pass": "v", "warn": "!", "fail": "x"}[c.status]
        click.echo(f"  {symbol} {c.name}: {c.message}")

    click.echo(f"\nStations : {result.n_stations}")
    click.echo(f"Days     : {result.n_days}")
    click.echo(f"Output   : {out_path}")

    if warn_list:
        click.echo(f"Warnings: {len(warn_list)}")
    if fail_list:
        click.echo(f"Failed: {len(fail_list)} check(s).", err=True)
        sys.exit(1)


@convert.command("weather")
@click.option("--pcp-master", type=click.Path(exists=True, path_type=Path), default=None,
              help="Master CSV for precipitation stations (ID,NAME,LAT,LONG,ELEVATION).")
@click.option("--pcp-dir", type=click.Path(exists=True, path_type=Path), default=None,
              help="Directory containing raw precipitation station files.")
@click.option("--tmp-master", type=click.Path(exists=True, path_type=Path), default=None,
              help="Master CSV for temperature stations (ID,NAME,LAT,LONG,ELEVATION).")
@click.option("--tmp-dir", type=click.Path(exists=True, path_type=Path), default=None,
              help="Directory containing raw temperature station files.")
@click.option("--target", "targets", multiple=True,
              type=click.Choice(["swat2012", "swatplus"]), default=("swat2012",),
              show_default=True,
              help="Output format to write. Repeatable, e.g. --target swat2012 --target swatplus.")
@click.argument("out_dir", type=click.Path(path_type=Path))
def convert_weather(
    pcp_master: Path | None,
    pcp_dir: Path | None,
    tmp_master: Path | None,
    tmp_dir: Path | None,
    targets: tuple[str, ...],
    out_dir: Path,
) -> None:
    """Convert raw station weather files to SWAT2012 and/or SWAT+ format.

    Reads a precipitation group (--pcp-master + --pcp-dir) and/or a
    temperature group (--tmp-master + --tmp-dir) of raw per-station files,
    auto-detecting SWAT Classic style (YYYYMMDD header + one value per line)
    or CSV. At least one group must be given.

    Writes to OUT_DIR for each --target given. When more than one target is
    given, each is written to its own OUT_DIR/<target>/ subdirectory so the
    two formats' filenames don't collide.

    OUT_DIR   Directory where the converted weather files will be written.
    """
    from .converters.station_weather import StationWeatherConverter
    from .qa import failures, warnings

    converter = StationWeatherConverter(
        pcp_master=pcp_master, pcp_dir=pcp_dir,
        tmp_master=tmp_master, tmp_dir=tmp_dir,
    )
    result = converter.convert()

    for c in result.qa:
        symbol = {"pass": "v", "warn": "!", "fail": "x"}[c.status]
        click.echo(f"  {symbol} {c.name}: {c.message}")

    fail_list = failures(result.qa)
    if fail_list:
        click.echo(f"Failed: {len(fail_list)} check(s).", err=True)
        sys.exit(1)

    multi = len(targets) > 1
    written: list[Path] = []
    for target in targets:
        dest = out_dir / target if multi else out_dir
        if target == "swat2012":
            from .writers.weather import WeatherWriter
            written += WeatherWriter(result, dest).write()
        elif target == "swatplus":
            from .writers.weather_plus import SWATPlusWeatherWriter
            written += SWATPlusWeatherWriter(result, dest).write()

    click.echo(f"\nFiles written : {len(written)}")
    click.echo(f"Output dir    : {out_dir}")
    click.echo(f"Targets       : {', '.join(targets)}")

    warn_list = warnings(result.qa)
    if warn_list:
        click.echo(f"Warnings: {len(warn_list)}")


if __name__ == "__main__":
    main()

