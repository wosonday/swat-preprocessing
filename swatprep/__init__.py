"""swatprep — Preprocessing library for SWAT/SWAT+ input data.

Public API:
    from swatprep import SWATPrepProject
    from swatprep.config import SWATPrepConfig
    from swatprep.qa import QACheck
"""

from .api import SWATPrepProject, PrepareResult
from .config import SWATPrepConfig
from .qa import QACheck

__version__ = "0.1.0"

__all__ = [
    "SWATPrepProject",
    "PrepareResult",
    "SWATPrepConfig",
    "QACheck",
    "__version__",
]
