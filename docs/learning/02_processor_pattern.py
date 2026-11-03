"""Example 2: the processor -> result + QA -> writer contract that every swatprep domain follows.

Run:  uv run python docs/learning/02_processor_pattern.py
"""
from dataclasses import dataclass, field

import pandas as pd

from swatprep.qa import QACheck, failures


@dataclass
class RainResult:
    """Typed result: the data, plus the QA list that travels with it."""
    daily: pd.DataFrame
    qa: list[QACheck] = field(default_factory=list)


class RainProcessor:
    """Load and check one domain; never write files and never print."""

    def __init__(self, daily: pd.DataFrame) -> None:
        self.daily = daily

    def run(self) -> RainResult:
        qa: list[QACheck] = []
        negative = int((self.daily < 0).sum().sum())
        qa.append(QACheck(
            name="rain_negative",
            status="fail" if negative else "pass",            # hydrologic rule: rain cannot be negative
            message=f"{negative} negative value(s)",
        ))
        missing = float(self.daily.isna().mean().mean() * 100)
        if missing:
            qa.append(QACheck(name="rain_missing", status="warn", message=f"{missing:.1f}% missing"))
        return RainResult(self.daily, qa)


class RainWriter:
    """Serialise only validated data: a 'fail' in the result blocks the write."""

    def write(self, result: RainResult) -> str:
        if failures(result.qa):
            raise ValueError("refusing to write data that failed QA")
        return result.daily.fillna(-99).to_csv()            # SWAT convention: -99 = missing


days = pd.date_range("2000-01-01", periods=4, freq="D")
good = pd.DataFrame({"S1": [0.0, 5.2, None, 1.0]}, index=days)
bad = pd.DataFrame({"S1": [0.0, -3.0, 2.0, 1.0]}, index=days)

for name, frame in (("good", good), ("bad", bad)):
    result = RainProcessor(frame).run()
    print(name, [(c.name, c.status) for c in result.qa])
    try:
        print(RainWriter().write(result))
    except ValueError as exc:
        print("  writer:", exc)
