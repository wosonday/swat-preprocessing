"""Example 1: the whole core through the Python API (config -> validate -> build -> QA).

Run from the repository root:  uv run python docs/learning/01_api_build.py
It copies examples/ into a temporary folder, so nothing in the repository is written.
"""
import shutil
import tempfile
from pathlib import Path

from swatprep import SWATPrepProject
from swatprep.qa import failures, warnings

work = Path(tempfile.mkdtemp(prefix="swatprep_"))
shutil.copytree(Path("examples"), work / "examples")
config = work / "examples" / "config_minimal.yaml"

project = SWATPrepProject.from_config(config)       # YAML -> Pydantic model; relative paths -> absolute
print("Domains:", project.config.configured_domains())

checks = project.validate()                          # only checks that input files exist
print("validate:", len(failures(checks)), "fail(s)")

result = project.build()                             # processors -> writers -> manifest.json, qa_report.md
print("build success:", result.success, "| warnings:", len(warnings(result.qa_checks)))
for check in result.qa_checks:
    if check.name.endswith("_written"):
        print(f"  {check.status:4}  {check.name}: {check.message}")
print("manifest:", result.manifest_path.relative_to(work))
