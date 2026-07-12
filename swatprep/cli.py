"""Click-based CLI for swatprep.

Entry point: swatprep (registered in pyproject.toml)

Commands:
    swatprep validate config.yaml
    swatprep build config.yaml [--only DOMAIN]
    swatprep inspect raster PATH
    swatprep inspect weather PATH
    swatprep convert climate DATA_DIR OUT_DIR
    swatprep convert streamflow SOURCE OUT_PATH
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

    Uses default Vietnamese USTH prefix mapping:
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

@convert.command("pcp")
@click.argument("master_path", type=click.Path(exists=True, path_type=Path))
@click.argument("data_dir", type=click.Path(exists=True, path_type=Path))
@click.argument("out_dir", type=click.Path(path_type=Path))
@click.option("--name-prefix", default="pcp_", show_default=True,
              help="Prefix to strip from NAME column to get station code.")
@click.option("--raw-prefix", default="R_", show_default=True,
              help="Prefix for raw .day files (e.g. R_ for R_ANKHE.day).")
@click.option("--raw-suffix", default=".day", show_default=True,
              help="File suffix for raw data files.")
@click.option("--value-col", default="Rain", show_default=True,
              help="Column name for precipitation values in .day files.")
@click.option("--out-suffix", default=".pcp", show_default=True,
              help="Output file suffix (.pcp or .txt for legacy SWAT).")
def convert_pcp(
    master_path: Path,
    data_dir: Path,
    out_dir: Path,
    name_prefix: str,
    raw_prefix: str,
    raw_suffix: str,
    value_col: str,
    out_suffix: str,
) -> None:
    """Build SWAT 2012 .pcp files from master metadata + raw .day files.

    Reads MASTER_PATH (CSV with ID, NAME, LAT, LONG, ELEVATION), matches each
    station to its raw file in DATA_DIR, and writes SWAT-format .pcp files to
    OUT_DIR with the 4-line header (title / Lati / Long / Elev).

    Matching: NAME="pcp_ANKHE" -> strip "pcp_" -> "ANKHE" -> "R_ANKHE.day"

    MASTER_PATH  Master CSV file (ID,NAME,LAT,LONG,ELEVATION).
    DATA_DIR     Directory containing raw R_STATION.day files.
    OUT_DIR      Directory where .pcp output files will be written.
    """
    from .converters import PCPConverter
    from .qa import failures, warnings

    converter = PCPConverter(
        master_path=master_path,
        data_dir=data_dir,
        out_dir=out_dir,
        name_prefix=name_prefix,
        raw_prefix=raw_prefix,
        raw_suffix=raw_suffix,
        value_col=value_col,
        out_suffix=out_suffix,
    )
    result = converter.convert()

    warn_list = warnings(result.qa)
    fail_list = failures(result.qa)

    for sr in result.stations:
   
        if sr.out_path:
            click.echo(f"  v {sr.name}: {sr.n_days} days -> {sr.out_path.name}")
        else:
            for c in sr.qa:
                if c.status != "pass":
                    click.echo(f"  ! {sr.name}: {c.message}")

    click.echo(f"\nWritten    : {len(result.files_written)}")
    click.echo(f"Unmatched  : {len(result.unmatched)}")
    click.echo(f"Output dir : {out_dir}")

    if result.unmatched:
        click.echo(f"Unmatched stations: {result.unmatched}")

    fail_list = failures(result.qa)
    if fail_list:
        click.echo(f"Failed: {len(fail_list)} check(s).", err=True)
        sys.exit(1)


@convert.command("tmp")
@click.argument("master_path", type=click.Path(exists=True, path_type=Path))
@click.argument("data_dir", type=click.Path(exists=True, path_type=Path))
@click.argument("out_dir", type=click.Path(path_type=Path))
@click.option("--name-prefix", default="tmp_", show_default=True,
              help="Prefix to strip from NAME column to get station code.")
@click.option("--raw-prefix", default="tmp_", show_default=True,
              help="Prefix for raw temperature files (e.g. tmp_ for tmp_ANKHE.txt).")
@click.option("--raw-suffix", default=".txt", show_default=True,
              help="File suffix for raw temperature files.")
@click.option("--tmin-first/--tmax-first", default=True, show_default=True,
              help="Column order in SWAT Classic input: tmin,tmax (default) or tmax,tmin.")
@click.option("--separator", default=",", show_default=True,
              help="Separator between tmin and tmax values in input file.")
@click.option("--out-suffix", default=".tmp", show_default=True,
              help="Output file suffix.")
def convert_tmp(
    master_path: Path,
    data_dir: Path,
    out_dir: Path,
    name_prefix: str,
    raw_prefix: str,
    raw_suffix: str,
    tmin_first: bool,
    separator: str,
    out_suffix: str,
) -> None:
    """Build SWAT 2012 .tmp files from master metadata + raw temperature files.

    Reads MASTER_PATH (CSV with ID, NAME, LAT, LONG, ELEVATION), matches each
    station to its raw file in DATA_DIR, and writes SWAT 2012 .tmp files with
    the 4-line header (title / Lati / Long / Elev) + daily tmax tmin pairs.

    Auto-detects input format:
      - SWAT Classic: line 1 = YYYYMMDD, rest = "tmin,tmax" per line.
      - CSV: columns date, tmax, tmin.

    Matching: NAME="tmp_ANKHE" -> strip "tmp_" -> "ANKHE" -> "tmp_ANKHE.txt"

    MASTER_PATH  Master CSV file (ID,NAME,LAT,LONG,ELEVATION).
    DATA_DIR     Directory containing raw tmp_STATION.txt files.
    OUT_DIR      Directory where .tmp output files will be written.
    """
    from .converters import TmpConverter
    from .qa import failures, warnings

    converter = TmpConverter(
        master_path=master_path,
        data_dir=data_dir,
        out_dir=out_dir,
        name_prefix=name_prefix,
        raw_prefix=raw_prefix,
        raw_suffix=raw_suffix,
        tmin_first=tmin_first,
        separator=separator,
        out_suffix=out_suffix,
    )
    result = converter.convert()

    warn_list = warnings(result.qa)
    fail_list = failures(result.qa)

    for sr in result.stations:
        if sr.out_path:
            click.echo(f"  v {sr.name}: {sr.n_days} days -> {sr.out_path.name}")
        else:
            for c in sr.qa:
                if c.status != "pass":
                    click.echo(f"  ! {sr.name}: {c.message}")

    click.echo(f"\nWritten    : {len(result.files_written)}")
    click.echo(f"Unmatched  : {len(result.unmatched)}")
    click.echo(f"Output dir : {out_dir}")

    if result.unmatched:
        click.echo(f"Unmatched stations: {result.unmatched}")

    if warn_list:
        click.echo(f"Warnings: {len(warn_list)}")
    if fail_list:
        click.echo(f"Failed: {len(fail_list)} check(s).", err=True)
        sys.exit(1)


@convert.command("swatplus")
@click.argument("master_path", type=click.Path(exists=True, path_type=Path))
@click.argument("pcp_dir",    type=click.Path(exists=True, path_type=Path))
@click.argument("tmp_dir",    type=click.Path(exists=True, path_type=Path))
@click.argument("out_dir",    type=click.Path(path_type=Path))
@click.option("--name-prefix",  default="pcp_", show_default=True,
              help="Prefix to strip from master NAME (pcp_ -> ANKHE).")
@click.option("--pcp-prefix",   default="pcp_", show_default=True,
              help="Prefix for pcp files (pcp_ANKHE.txt).")
@click.option("--pcp-suffix",   default=".txt",  show_default=True)
@click.option("--tmp-prefix",   default="tmp_", show_default=True,
              help="Prefix for tmp files (tmp_ANKHE.txt).")
@click.option("--tmp-suffix",   default=".txt",  show_default=True)
@click.option("--tmin-first/--tmax-first", default=True, show_default=True,
              help="Column order in tmp file: tmin,tmax (default) or tmax,tmin.")
@click.option("--separator",    default=",",    show_default=True,
              help="Separator between tmin and tmax in tmp file.")
def convert_swatplus(
    master_path: Path,
    pcp_dir: Path,
    tmp_dir: Path,
    out_dir: Path,
    name_prefix: str,
    pcp_prefix: str,
    pcp_suffix: str,
    tmp_prefix: str,
    tmp_suffix: str,
    tmin_first: bool,
    separator: str,
) -> None:
    """Build SWAT+ weather files from SWAT Classic pcp + tmp files.

    Reads MASTER_PATH for station metadata. For each station, reads the
    SWAT Classic pcp file from PCP_DIR and the tmp file from TMP_DIR,
    merges them, then writes SWAT+ .pcp + .tmp files and pcp.cli/tmp.cli.

    Matching: NAME="pcp_ANKHE" -> station "ANKHE"
              -> PCP_DIR/pcp_ANKHE.txt + TMP_DIR/tmp_ANKHE.txt

    MASTER_PATH  Master CSV (ID,NAME,LAT,LONG,ELEVATION).
    PCP_DIR      Directory with pcp_STATION.txt files.
    TMP_DIR      Directory with tmp_STATION.txt files.
    OUT_DIR      Directory for SWAT+ output files.
    """
    import pandas as pd
    from .converters.pcp import PCPConverter
    from .converters.tmp import TmpConverter
    from .converters.weather_plus import SWATPlusWeatherConverter
    from .qa import failures, warnings

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Use a temp merged CSV dir
    import tempfile
    merged_dir = Path(tempfile.mkdtemp(prefix="swatprep_merged_"))

    # Read master
    master_df = pd.read_csv(master_path)
    name_col = "NAME"

    pcp_conv = PCPConverter(
        master_path=master_path,
        data_dir=pcp_dir,
        out_dir=out_dir,
        name_prefix=name_prefix,
        raw_prefix=pcp_prefix,
        raw_suffix=pcp_suffix,
    )
    tmp_conv = TmpConverter(
        master_path=master_path,
        data_dir=tmp_dir,
        out_dir=out_dir,
        name_prefix=name_prefix,
        raw_prefix=tmp_prefix,
        raw_suffix=tmp_suffix,
        tmin_first=tmin_first,
        separator=separator,
    )

    n_ok = 0
    n_miss = 0

    for _, row in master_df.iterrows():
        name = str(row[name_col]).strip()
        station = name[len(name_prefix):] if name.startswith(name_prefix) else name

        pcp_file = pcp_conv._find_raw_file(station)
        tmp_file = tmp_conv._find_raw_file(station)

        if pcp_file is None and tmp_file is None:
            click.echo(f"  ! {station}: both pcp and tmp files not found")
            n_miss += 1
            continue

        # Read pcp
        if pcp_file is None:
            df_pcp = None
        elif not pcp_conv._is_swat_format(pcp_file):
            click.echo(f"  ! {station}: {pcp_file.name} is not SWAT Classic format — skipping", err=True)
            n_miss += 1
            continue
        else:
            df_pcp = pcp_conv._read_swat_pcp(pcp_file)
            df_pcp = df_pcp.rename(columns={pcp_conv.value_col: "precip"})

        # Read tmp
        if tmp_file is None:
            df_tmp = None
        elif not tmp_conv._is_swat_format(tmp_file):
            click.echo(f"  ! {station}: {tmp_file.name} is not SWAT Classic format — skipping", err=True)
            n_miss += 1
            continue
        else:
            df_tmp = tmp_conv._read_swat_tmp(tmp_file)

        # Merge
        if df_pcp is not None and df_tmp is not None:
            df = pd.merge(df_pcp, df_tmp, on="date", how="outer")
        elif df_pcp is not None:
            df = df_pcp
        else:
            df = df_tmp

        df.to_csv(merged_dir / f"{station}.csv", index=False)
        click.echo(f"  v {station}: {len(df)} days merged")
        n_ok += 1

    if n_ok == 0:
        click.echo("No stations merged. Aborting.", err=True)
        sys.exit(1)

    # Run SWATPlusWeatherConverter on merged CSVs
    result = SWATPlusWeatherConverter(
        data_dir=merged_dir,
        out_dir=out_dir,
        metadata=master_path,
        meta_name_prefix=name_prefix,
    ).convert()

    warn_list = warnings(result.qa)
    fail_list = failures(result.qa)

    click.echo(f"\nSWAT+ files written : {len(result.data_files)}")
    click.echo(f"CLI index files     : {len(result.cli_files)}")
    click.echo(f"Output dir          : {out_dir}")

    for f in result.cli_files:
        click.echo(f"  {f.name}")

    if warn_list:
        click.echo(f"Warnings: {len(warn_list)}")
    if fail_list:
        click.echo(f"Failed: {len(fail_list)} check(s).", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
