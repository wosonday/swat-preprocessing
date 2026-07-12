"""Deprecated: TmpConverter has been merged into swat2012_input.py.

This module is kept for backward compatibility only. Import from swatprep.converters:

    from swatprep.converters import TmpConverter, TmpStationResult, TmpConvertResult
"""
from .swat2012 import (  # noqa: F401
    TmpConverter,
    StationResult as TmpStationResult,
    SWAT2012ConvertResult as TmpConvertResult,
)
