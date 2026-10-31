"""Choices for project.crs: common CRSs first, then every non-deprecated EPSG projected CRS (from pyproj)."""
from __future__ import annotations

from functools import lru_cache

COMMON = {
    "EPSG:32647": "WGS 84 / UTM zone 47N",
    "EPSG:32648": "WGS 84 / UTM zone 48N",
    "EPSG:32649": "WGS 84 / UTM zone 49N",
    "EPSG:3405": "VN-2000 / UTM zone 48N",
    "EPSG:3406": "VN-2000 / UTM zone 49N",
}


def _epsg_projected() -> dict[str, str]:
    from pyproj.database import query_crs_info
    from pyproj.enums import PJType

    infos = query_crs_info(auth_name="EPSG", pj_types=[PJType.PROJECTED_CRS], allow_deprecated=False)
    return {f"EPSG:{info.code}": info.name for info in sorted(infos, key=lambda info: int(info.code))}


@lru_cache(maxsize=1)
def crs_options() -> dict[str, str]:
    """Code -> name; without pyproj (no `geo` extra) only the common ones."""
    try:
        others = _epsg_projected()
    except ImportError:
        others = {}
    return {**COMMON, **{code: name for code, name in others.items() if code not in COMMON}}


def crs_label(code: str) -> str:
    name = crs_options().get(code)
    return f"{code} · {name}" if name else code


def check_crs(value: str) -> tuple[str, str]:
    """("ok" | "warn" | "error" | "unknown", message) for a typed or chosen CRS."""
    try:
        from pyproj import CRS
        from pyproj.exceptions import CRSError
    except ImportError:
        return "unknown", "cannot check without pyproj"
    try:
        crs = CRS.from_user_input(str(value))
    except CRSError:
        return "error", "not a recognised CRS"
    if not crs.is_projected:
        return "warn", f"{crs.name} is not projected: use a projected CRS in metres"
    unit = crs.axis_info[0].unit_name if crs.axis_info else "unknown unit"
    return "ok", f"{crs.name} ({unit})"
