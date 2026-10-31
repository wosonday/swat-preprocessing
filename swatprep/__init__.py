"""swatprep — Preprocessing library for SWAT/SWAT+ input data.

Public API:
    from swatprep import SWATPrepProject
    from swatprep.config import SWATPrepConfig
    from swatprep.qa import QACheck
"""

from importlib.metadata import PackageNotFoundError, version

from .api import SWATPrepProject, PrepareResult
from .config import SWATPrepConfig
from .qa import QACheck

try:
    __version__ = version("swatprep")  # single source of truth: pyproject.toml
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0+unknown"

__all__ = [
    "SWATPrepProject",
    "PrepareResult",
    "SWATPrepConfig",
    "QACheck",
    "__version__",
]
