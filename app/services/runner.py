"""Validate and build a config through the swatprep API without ever raising."""
from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

from pydantic import ValidationError

from swatprep import QACheck, SWATPrepProject
from swatprep.errors import SWATPrepError


@dataclass
class RunResult:
    ok: bool
    checks: list[QACheck] = field(default_factory=list)
    error: str | None = None
    traceback: str | None = None
    output_dir: Path | None = None
    manifest_path: Path | None = None
    seconds: float = 0.0

    def count(self, status: str) -> int:
        return sum(1 for c in self.checks if c.status == status)


def _schema_message(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        where = ".".join(str(part) for part in err["loc"]) or "config"
        lines.append(f"{where}: {err['msg']}")
    return "Config is not valid:\n" + "\n".join(f"- {line}" for line in lines)


def _run(action) -> RunResult:
    start = perf_counter()
    try:
        result = action()
    except ValidationError as exc:
        result = RunResult(ok=False, error=_schema_message(exc))
    except (SWATPrepError, OSError) as exc:
        result = RunResult(ok=False, error=f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # unexpected bug -> report it, don't crash the page
        result = RunResult(ok=False, error=f"Unexpected error: {exc}", traceback=traceback.format_exc())
    result.seconds = perf_counter() - start
    return result


def validate(config_path: Path) -> RunResult:
    def action() -> RunResult:
        checks = SWATPrepProject.from_config(config_path).validate()
        return RunResult(ok=not any(c.status == "fail" for c in checks), checks=checks)

    return _run(action)


def build(config_path: Path, only: str | None = None) -> RunResult:
    def action() -> RunResult:
        prepared = SWATPrepProject.from_config(config_path).build(only=only)
        return RunResult(
            ok=prepared.success,
            checks=prepared.qa_checks,
            output_dir=prepared.output_dir,
            manifest_path=prepared.manifest_path,
        )

    return _run(action)
