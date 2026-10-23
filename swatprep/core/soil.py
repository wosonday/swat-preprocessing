"""SoilPreprocessor: validate soil parameter table and cross-check with raster.

rasterio is optional -- raster cross-check is skipped when not installed.

Minimal required SWAT usersoil columns (Arnold et al. 2012):
    soil_key_col  (default "soil_id") -- join key matching raster codes
    HYDGRP        -- hydrologic soil group (A, B, C, D)
    SOL_ZMX       -- maximum root depth (mm)
    NLAYERS       -- number of soil layers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..config import SoilConfig
from ..errors import InputValidationError
from ..qa import QACheck
from ..utils.raster import resolve_window, unique_codes
from .clip import basin_rows

try:
    import rasterio  # type: ignore
    _HAS_RASTERIO = True
except ImportError:
    _HAS_RASTERIO = False

_REQUIRED_COLS = {"HYDGRP", "SOL_ZMX", "NLAYERS"}

# SWAT+ usersoil layout (152 columns), identical to the SWAT+ Editor example usersoil.csv.
_LAYER_FIELDS = ("SOL_Z", "SOL_BD", "SOL_AWC", "SOL_K", "SOL_CBN", "CLAY", "SILT", "SAND",
                 "ROCK", "SOL_ALB", "USLE_K", "SOL_EC")
USERSOIL_COLUMNS: list[str] = (
    ["OBJECTID", "MUID", "SEQN", "SNAM", "S5ID", "CMPPCT", "NLAYERS", "HYDGRP", "SOL_ZMX",
     "ANION_EXCL", "SOL_CRK", "TEXTURE"]
    + [f"{f}{i}" for i in range(1, 11) for f in _LAYER_FIELDS]
    + [f"SOL_CAL{i}" for i in range(1, 11)]
    + [f"SOL_PH{i}" for i in range(1, 11)]
)
_TEXT_COLS = {"SNAM", "HYDGRP", "TEXTURE"}
_INT_COLS = {"OBJECTID", "MUID", "SEQN", "S5ID", "NLAYERS"}
_DEFAULTS = {"ANION_EXCL": 0.5, "SOL_CRK": 0.5}  # SWAT defaults, as in the SWAT+ example


def format_usersoil(
    table: pd.DataFrame, key_col: str, qa: list[QACheck]
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Lay the soil table out exactly like the SWAT+ example usersoil.csv.

    Returns ``(usersoil, ids, snam)``: the 152-column table (one row per distinct soil, SNAM
    unique, key column dropped), and for every INPUT row its raster code and final SNAM
    (used for soil_vlookup.csv so that both files agree).
    """
    df = table.copy()
    lower = {str(c).strip().lower(): c for c in df.columns}
    ids = pd.to_numeric(df[key_col], errors="coerce")
    cols: dict[str, pd.Series | float | str] = {}
    defaulted: list[str] = []
    for col in USERSOIL_COLUMNS:
        src = lower.get(col.lower())
        if src is None:
            defaulted.append(col)
            if col == "SNAM":
                cols[col] = df[key_col].astype(str)
            else:
                cols[col] = "" if col in _TEXT_COLS else _DEFAULTS.get(col, 0)
        elif col in _TEXT_COLS:
            cols[col] = df[src].fillna("").astype(str).str.strip()
        else:
            cols[col] = pd.to_numeric(df[src], errors="coerce").fillna(0)
    out = pd.DataFrame({c: (v if isinstance(v, pd.Series) else pd.Series(v, index=df.index))
                        for c, v in cols.items()}, index=df.index)
    for col in _INT_COLS:
        out[col] = out[col].astype(int)
    blank = out["SNAM"].eq("")
    out.loc[blank, "SNAM"] = df.loc[blank, key_col].astype(str)

    # Same data repeated (e.g. one HWSD component listed twice) -> keep a single row.
    content = [c for c in out.columns if c != "OBJECTID"]
    gid = out.groupby(content, sort=False).ngroup()
    first = ~gid.duplicated()
    merged = int((~first).sum())
    uniq = out[first].copy()
    # Same SNAM but different data -> unique names Name, Name_2, Name_3 (QSWAT+/SWAT+ key on SNAM).
    k = uniq.groupby("SNAM").cumcount()
    renamed = int((k > 0).sum())
    uniq.loc[k > 0, "SNAM"] = uniq.loc[k > 0, "SNAM"] + "_" + (k[k > 0] + 1).astype(str)
    snam = gid.map(dict(zip(gid[first], uniq["SNAM"])))
    if not uniq["OBJECTID"].is_unique or (uniq["OBJECTID"] == 0).all():
        uniq["OBJECTID"] = range(1, len(uniq) + 1)

    dropped = [str(c) for c in df.columns if str(c).strip().lower() not in
               {c.lower() for c in USERSOIL_COLUMNS}]
    msg = f"usersoil.csv: {len(uniq)} soil(s) x {len(USERSOIL_COLUMNS)} columns (SWAT+ layout)"
    if dropped:
        msg += f"; columns outside the layout not written: {', '.join(dropped[:8])}" \
               + (" ..." if len(dropped) > 8 else "")
    qa.append(QACheck(name="usersoil_formatted", status="pass", message=msg,
                      context={"rows": len(uniq), "dropped": dropped, "defaulted": defaulted}))
    if "SNAM" in defaulted:
        qa.append(QACheck(
            name="usersoil_snam_generated", status="warn",
            message=f"the soil table has no SNAM column; SNAM was set to the value of "
                    f"'{key_col}' (soil_vlookup.csv uses the same names)"))
    if merged:
        qa.append(QACheck(
            name="usersoil_duplicates_merged", status="pass",
            message=f"{merged} row(s) with identical data and SNAM merged into one in usersoil.csv",
            context={"count": merged}))
    if renamed:
        qa.append(QACheck(
            name="usersoil_snam_renamed", status="warn",
            message=f"{renamed} row(s) share a SNAM with different data; renamed with a suffix "
                    "(Name_2, Name_3, ...) so SNAM is unique",
            context={"count": renamed}))
    return uniq.reset_index(drop=True), ids, snam
_RECOMMENDED_LAYER1 = {"SOL_Z1", "SOL_BD1", "SOL_AWC1", "SOL_K1", "SOL_CBN1"}
_VALID_HYDGRP = {"A", "B", "C", "D", "A/D", "B/D", "C/D"}


@dataclass
class SoilResult:
    """Output of SoilPreprocessor.run()."""

    soil_table: pd.DataFrame
    raster_codes: set | None
    unmatched_codes: set
    qa: list[QACheck] = field(default_factory=list)
    vlookup: pd.DataFrame | None = None  # SOIL_ID, SNAM (QSWAT / QSWAT+ lookup table)
    usersoil: pd.DataFrame | None = None  # SWAT+ layout table; None -> write soil_table as is


class SoilPreprocessor:
    """Validate soil parameter table and cross-check unique raster codes."""

    def __init__(self, cfg: SoilConfig, boundary: Path | None = None) -> None:
        self.cfg = cfg
        self.boundary = boundary  # project.boundary: codes read only inside its window
        self._windowed = False  # True once the boundary window was actually applied

    def run(self) -> SoilResult:
        qa: list[QACheck] = []
        table = self._load_table(qa)
        raster_codes = self._read_raster_codes(qa)
        unmatched = self._cross_check(table, raster_codes, qa)
        if self._windowed and raster_codes:
            table = basin_rows(table, self.cfg.soil_key_col, raster_codes, "soil", qa)
        usersoil = None
        ids, snam = pd.to_numeric(table[self.cfg.soil_key_col], errors="coerce"), None
        if "SNAM" in table.columns:
            snam = table["SNAM"]
        if self.cfg.usersoil_format == "swat":
            usersoil, ids, snam = format_usersoil(table, self.cfg.soil_key_col, qa)
        return SoilResult(
            soil_table=table,
            raster_codes=raster_codes,
            unmatched_codes=unmatched,
            qa=qa,
            vlookup=self._vlookup(ids, snam, qa) if self.cfg.output_lookup else None,
            usersoil=usersoil,
        )

    def _vlookup(self, ids: pd.Series, snam: pd.Series | None,
                 qa: list[QACheck]) -> pd.DataFrame | None:
        """Two-column table raster value -> soil name SNAM (one row per SOIL_ID, sorted)."""
        if snam is None:
            qa.append(QACheck(
                name="soil_vlookup_skipped", status="warn",
                message="soil VLOOKUP table not written: the soil table has no SNAM column",
            ))
            return None
        df = pd.DataFrame({"SOIL_ID": ids, "SNAM": snam}).dropna()
        df = df.astype({"SOIL_ID": int})
        dup = int(df["SOIL_ID"].duplicated().sum())
        if dup:
            qa.append(QACheck(
                name="soil_vlookup_duplicates", status="warn",
                message=f"{dup} extra row(s) share a SOIL_ID; the VLOOKUP table keeps the first "
                        "SNAM of each (usersoil.csv still lists every distinct soil)",
                context={"count": dup},
            ))
        df = df.drop_duplicates("SOIL_ID").sort_values("SOIL_ID").reset_index(drop=True)
        qa.append(QACheck(
            name="soil_vlookup", status="pass",
            message=f"soil VLOOKUP table: {len(df)} row(s) (SOIL_ID -> SNAM)",
        ))
        return df

    def _load_table(self, qa: list[QACheck]) -> pd.DataFrame:
        cfg = self.cfg
        df = pd.read_csv(cfg.table)

        if cfg.soil_key_col not in df.columns:
            raise InputValidationError(
                "Soil table missing key column '" + cfg.soil_key_col + "'. "
                "Set soil.soil_key_col in config."
            )

        missing_req = _REQUIRED_COLS - set(df.columns)
        if missing_req:
            qa.append(QACheck(
                name="soil_missing_required_cols",
                status="fail",
                message="Soil table missing required SWAT columns: " + ", ".join(sorted(missing_req)),
                context={"missing": sorted(missing_req)},
            ))

        missing_rec = _RECOMMENDED_LAYER1 - set(df.columns)
        if missing_rec:
            qa.append(QACheck(
                name="soil_missing_layer1_cols",
                status="warn",
                message="Soil table missing recommended layer-1 columns: " + ", ".join(sorted(missing_rec)),
                context={"missing": sorted(missing_rec)},
            ))

        if "HYDGRP" in df.columns:
            invalid_grp = set(df["HYDGRP"].dropna().unique()) - _VALID_HYDGRP
            if invalid_grp:
                qa.append(QACheck(
                    name="soil_invalid_hydgrp",
                    status="warn",
                    message="Unexpected HYDGRP values: " + str(sorted(invalid_grp)),
                    context={"values": sorted(invalid_grp)},
                ))

        qa.append(QACheck(
            name="soil_table_loaded",
            status="pass",
            message=str(len(df)) + " soil record(s) loaded from " + cfg.table.name,
        ))
        return df

    def _read_raster_codes(self, qa: list[QACheck]) -> set | None:
        if not _HAS_RASTERIO:
            qa.append(QACheck(
                name="rasterio_missing",
                status="warn",
                message=(
                    "rasterio not installed -- soil raster code extraction skipped. "
                    "Install swatprep[geo] to enable cross-check."
                ),
            ))
            return None

        try:
            with rasterio.open(self.cfg.raster) as ds:
                window = resolve_window(ds, self.boundary, qa, "soil")
                codes = unique_codes(ds, window=window)
                self._windowed = window is not None
        except Exception as exc:
            qa.append(QACheck(
                name="soil_raster_read_failed",
                status="fail",
                message="Could not read soil raster: " + str(self.cfg.raster),
                context={"path": str(self.cfg.raster), "error": str(exc)},
            ))
            return None

        qa.append(QACheck(
            name="soil_raster_read",
            status="pass",
            message=str(len(codes)) + " unique soil code(s) found in raster",
        ))
        return codes

    def _cross_check(
        self,
        table: pd.DataFrame,
        raster_codes: set | None,
        qa: list[QACheck],
    ) -> set:
        if raster_codes is None:
            return set()

        cfg = self.cfg
        known_codes = set(
            pd.to_numeric(table[cfg.soil_key_col], errors="coerce").dropna().astype(int).tolist()
        )
        unmatched = raster_codes - known_codes

        if unmatched:
            top10 = str(sorted(unmatched)[:10])
            qa.append(QACheck(
                name="soil_unmatched_codes",
                status="fail",
                message=(
                    str(len(unmatched)) + " raster soil code(s) have no entry in the "
                    "soil table (first 10): " + top10
                ),
                context={"unmatched_count": len(unmatched), "sample": sorted(unmatched)[:10]},
            ))
        else:
            qa.append(QACheck(
                name="soil_cross_check",
                status="pass",
                message="All raster soil codes are present in the soil table.",
            ))

        return unmatched
