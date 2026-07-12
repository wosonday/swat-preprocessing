"""Deprecated: PCPConverter has been merged into swat2012_input.py.

This module is kept for backward compatibility only. Import from swatprep.converters:

    from swatprep.converters import PCPConverter, PCPStationResult, PCPConvertResult
"""
from .swat2012 import (  # noqa: F401
    PCPConverter,
    StationResult as PCPStationResult,
    SWAT2012ConvertResult as PCPConvertResult,
)
