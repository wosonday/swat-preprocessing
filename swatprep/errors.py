"""Typed exceptions for swatprep.

Hierarchy:
    SWATPrepError
    ├── ConfigError          – bad YAML, missing required fields
    ├── InputValidationError – input file missing, wrong columns, bad CRS
    ├── ProjectionError      – CRS mismatch or reprojection failure
    ├── ProcessingError      – algorithmic failure during preprocessing
    └── WriterError          – I/O error writing output files
"""


class SWATPrepError(Exception):
    """Base exception for all swatprep errors."""


class ConfigError(SWATPrepError):
    """Raised when project configuration is invalid or incomplete."""


class InputValidationError(SWATPrepError):
    """Raised when an input file fails structural or content validation."""


class ProjectionError(SWATPrepError):
    """Raised on CRS mismatch or reprojection failure."""


class ProcessingError(SWATPrepError):
    """Raised when a preprocessing step fails algorithmically."""


class WriterError(SWATPrepError):
    """Raised when writing an output file fails."""
