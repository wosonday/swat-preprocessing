"""QA primitives used by all preprocessors and writers.

Each preprocessing step appends QACheck objects to a list.
Writers inspect that list before serialising: any "fail" blocks the write.
The ManifestWriter serialises the full list to manifest.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class QACheck:
    """One validation result from a preprocessor or writer."""

    name: str
    status: Literal["pass", "warn", "fail"]
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def is_ok(self) -> bool:
        """True when the check is not a hard failure."""
        return self.status in ("pass", "warn")

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "context": self.context,
        }


def failures(checks: list[QACheck]) -> list[QACheck]:
    """Return only the checks that have status 'fail'."""
    return [c for c in checks if c.status == "fail"]


def warnings(checks: list[QACheck]) -> list[QACheck]:
    """Return only the checks that have status 'warn'."""
    return [c for c in checks if c.status == "warn"]


def all_pass(checks: list[QACheck]) -> bool:
    """True when no check has status 'fail'."""
    return not failures(checks)
