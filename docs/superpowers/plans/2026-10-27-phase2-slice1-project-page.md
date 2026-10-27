# Phase 2 · Slice 1: Open → Validate → Build → Results — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `Project` page that opens an existing `config.yaml` (workspace list, pasted path or Browse), validates and builds it through the swatprep API, and shows the QA results, styled with the OpenDesign theme.

**Architecture:** Pure-Python services (`fs_browser`, `project_io`, `runner`) hold all logic and are unit-tested; thin Streamlit modules (`app/ui/*`, `app/pages/1_Project.py`) only render. Theme comes from `.streamlit/config.toml`, mapped from OpenDesign tokens.

**Tech Stack:** Python 3.12, Streamlit 1.66, ruamel.yaml (round-trip), pytest + `streamlit.testing.v1.AppTest`, uv, Docker.

**Spec:** `docs/superpowers/specs/2026-10-27-phase2-project-page-design.md` (sections 2, 4, 5, 6.1, 7).

## Global Constraints

- All code, comments and UI text in English; sentence case labels ("Open from workspace", "Validate", "Build").
- No emoji in buttons, titles or status text; status = Material icon + word (`pass`/`warn`/`fail`, `ok`/`missing`).
- `app/services/*` never imports `streamlit`; dependency direction `pages → ui → services → swatprep`.
- Do not modify `swatprep/` (core).
- Theme values exactly as spec section 7.1.
- Run tests with `uv run python -m pytest` (never bare `pytest`).
- Verified in a Linux sandbox on 2026-10-27: full suite **283 passed**.

## File Map

| File | Status | Responsibility |
|---|---|---|
| `pyproject.toml`, `uv.lock` | modify | add `ruamel-yaml>=0.18` to the `app` extra |
| `.streamlit/config.toml` | create | OpenDesign theme (light + dark) |
| `Dockerfile` | modify | copy `.streamlit/` into the runtime image |
| `app/ui/__init__.py` | create | package marker |
| `app/ui/status.py` | create | Material-icon status labels |
| `app/Home.py` | modify | use status labels instead of emoji |
| `app/services/fs_browser.py` | create | safe folder listing for Browse |
| `app/services/project_io.py` | create | ruamel load/save/dump, list configs |
| `app/services/runner.py` | create | validate/build → `RunResult`, never raises |
| `app/ui/browse.py` | create | Browse dialog |
| `app/ui/results.py` | create | render a `RunResult` |
| `app/pages/1_Project.py` | create | the Project page |
| `tests/ui/conftest.py` | create | `example_project` fixture (copy of `examples/`) |
| `tests/ui/test_fs_browser.py`, `test_project_io.py`, `test_runner.py`, `test_pages.py` | create | tests |

---

### Task 0: Branch

- [ ] **Step 1:**

```powershell
git switch main
git pull
git switch -c feature/project-page
```

---

### Task 1: Dependency, theme, status labels on Home

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (via uv), `app/Home.py`, `Dockerfile`
- Create: `.streamlit/config.toml`, `app/ui/__init__.py` (empty), `app/ui/status.py`
- Test: `tests/ui/test_pages.py` (first test only)

**Interfaces:**
- Produces: `app.ui.status.STATUS: dict[str, str]`, `app.ui.status.ok_label(ok: bool, yes="ok", no="missing") -> str`

- [ ] **Step 1: Add the dependency**

```powershell
uv add --optional app "ruamel.yaml>=0.18"
git diff pyproject.toml
```

Expected: the `app` extra lists `ruamel-yaml>=0.18` and `streamlit>=1.40`.

- [ ] **Step 2: Write the failing test** `tests/ui/test_pages.py`

```python
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[2] / "app"


def test_home_renders(monkeypatch, tmp_path):
    monkeypatch.setenv("SWATPREP_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(tmp_path))
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=30).run()
    assert not at.exception
    assert at.title[0].value == "swatprep"
```

- [ ] **Step 3: Create `app/ui/__init__.py` (empty) and `app/ui/status.py`**

```python
"""Status words with Material icons (OpenDesign: no emoji; pair colour with a word)."""
STATUS = {
    "pass": ":green[:material/check_circle: pass]",
    "warn": ":orange[:material/warning: warn]",
    "fail": ":red[:material/error: fail]",
}


def ok_label(ok: bool, yes: str = "ok", no: str = "missing") -> str:
    return f":green[:material/check_circle: {yes}]" if ok else f":red[:material/error: {no}]"
```

- [ ] **Step 4: Replace `app/Home.py`**

```python
"""Home page: environment health report."""
import streamlit as st

from app.services.environment import get_report
from app.ui.status import ok_label

st.set_page_config(page_title="swatprep", layout="wide")
st.title("swatprep")

report = get_report()

if report.ok:
    st.success("Environment is ready.", icon=":material/check_circle:")
else:
    st.error("Environment has problems. See the items marked missing below.", icon=":material/error:")

st.caption(f"Python {report.python}")

st.subheader("Packages")
st.table([{"Package": k, "Version": v} for k, v in report.packages.items()])

for title, checks in (("GDAL drivers", report.drivers), ("Folders", report.folders)):
    st.subheader(title)
    for c in checks:
        st.markdown(f"{ok_label(c.ok)} **{c.name}**: {c.detail}")
```

- [ ] **Step 5: Create `.streamlit/config.toml`**

```toml
# Theme from the OpenDesign design system: neutral greys carry the interface,
# green is kept for success feedback. Token names in comments.

[theme]
font = "Albert Sans:https://fonts.googleapis.com/css2?family=Albert+Sans:ital,wght@0,100..900;1,100..900&display=swap"
codeFont = "ui-monospace, SFMono-Regular, monospace"   # JiduMono Pro is not hosted; system mono fallback
baseFontSize = 14          # body 14px
baseFontWeight = 600       # body weight 600
headingFontWeights = 700
baseRadius = "4px"         # radius-medium (controls)
buttonRadius = "999px"     # radius-pill
showWidgetBorder = true
showSidebarBorder = true

[theme.light]
backgroundColor = "#ffffff"            # bg
secondaryBackgroundColor = "#fafafa"   # bg-panel
textColor = "#494949"                  # text
borderColor = "#dbdbdb"                # border
primaryColor = "#353535"               # selected
linkColor = "#1a74ff"                  # blue
blueColor = "#1a74ff"                  # blue
greenColor = "#00aa54"                 # green
greenBackgroundColor = "#f5ffee"       # green-bg
redColor = "#f04142"                   # red
orangeColor = "#ff7528"                # amber
codeBackgroundColor = "#fafafa"        # code-body-bg
codeTextColor = "#5c5c5c"              # text-muted (keep green for success only)
dataframeHeaderBackgroundColor = "#ededed"  # bg-subtle

[theme.dark]
backgroundColor = "#202020"            # bg
secondaryBackgroundColor = "#353535"   # bg-panel
textColor = "#ededed"                  # text
borderColor = "#5c5c5c"                # border
primaryColor = "#fafafa"               # text-strong (selected has no dark value)
linkColor = "#3aa5f0"                  # blue
blueColor = "#3aa5f0"                  # blue
greenColor = "#3bbf7d"                 # green
greenBackgroundColor = "#164111"       # green-bg
redColor = "#ff5e5e"                   # red
orangeColor = "#ffc740"                # amber
codeBackgroundColor = "#18181b"        # code-body-bg
codeTextColor = "#bdbdbd"              # text-muted
dataframeHeaderBackgroundColor = "#494949"  # bg-subtle
```

- [ ] **Step 6: Dockerfile** — in the runtime stage, after `COPY --chown=swat:swat app ./app`, add:

```dockerfile
COPY --chown=swat:swat .streamlit ./.streamlit
```

Reason: Streamlit reads `./.streamlit/config.toml` from its working directory (`/app`); without this line the image runs with the default theme.

- [ ] **Step 7: Run tests**

Run: `uv run python -m pytest tests/ui -q`
Expected: all pass (previous 7 + `test_home_renders`).

- [ ] **Step 8: Look at it**

```powershell
uv run streamlit run app/Home.py
```

Expected: grey neutral theme, Albert Sans, status lines read `ok GTiff: available` with a green check icon, no emoji.

- [ ] **Step 9: Commit**

```powershell
git add pyproject.toml uv.lock .streamlit Dockerfile app/ui app/Home.py tests/ui/test_pages.py
git commit -m "feat(ui): OpenDesign theme, Material status labels, ruamel.yaml dependency"
```

---

### Task 2: `fs_browser` (safe folder listing)

**Files:**
- Create: `app/services/fs_browser.py`
- Test: `tests/ui/test_fs_browser.py`

**Interfaces:**
- Produces: `OutsideRootError(ValueError)`; `Entry(name: str, path: Path, is_dir: bool, size: int | None)`; `resolve_inside(root: Path, sub: str | Path = "") -> Path`; `list_dir(root: Path, sub: str | Path = "", suffixes: tuple[str, ...] = ()) -> list[Entry]`; `human_size(size: int | None) -> str`

- [ ] **Step 1: Write the failing tests** `tests/ui/test_fs_browser.py`

```python
import pytest

from app.services.fs_browser import OutsideRootError, human_size, list_dir, resolve_inside


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "b_dir").mkdir()
    (tmp_path / "A_dir").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "z.tif").write_bytes(b"x" * 10)
    (tmp_path / "a.csv").write_text("id\n")
    (tmp_path / ".env").write_text("SECRET=1")
    return tmp_path


def test_folders_first_then_files_sorted_case_insensitive(tree):
    names = [e.name for e in list_dir(tree)]
    assert names == ["A_dir", "b_dir", "a.csv", "z.tif"]


def test_hidden_entries_are_skipped(tree):
    assert not any(e.name.startswith(".") for e in list_dir(tree))


def test_suffix_filter_keeps_folders(tree):
    names = [e.name for e in list_dir(tree, suffixes=(".tif",))]
    assert names == ["A_dir", "b_dir", "z.tif"]


def test_files_have_size_folders_do_not(tree):
    entries = {e.name: e for e in list_dir(tree)}
    assert entries["z.tif"].size == 10
    assert entries["A_dir"].size is None


def test_subfolder_listing(tree):
    (tree / "A_dir" / "dem.tif").write_text("")
    assert [e.name for e in list_dir(tree, "A_dir")] == ["dem.tif"]


def test_traversal_outside_root_is_refused(tree):
    with pytest.raises(OutsideRootError):
        list_dir(tree, "../")


def test_root_itself_is_allowed(tree):
    assert resolve_inside(tree, "") == tree.resolve()


def test_human_size():
    assert human_size(None) == ""
    assert human_size(512) == "512 B"
    assert human_size(1536) == "1.5 KB"
    assert human_size(5 * 1024**3) == "5.0 GB"
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run python -m pytest tests/ui/test_fs_browser.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'app.services.fs_browser'`.

- [ ] **Step 3: Implement** `app/services/fs_browser.py`

```python
"""List folders and files inside an allowed root, refusing path traversal."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class OutsideRootError(ValueError):
    """Raised when a requested path resolves outside the allowed root."""


@dataclass(frozen=True)
class Entry:
    name: str
    path: Path
    is_dir: bool
    size: int | None  # bytes; None for folders


def resolve_inside(root: Path, sub: str | Path = "") -> Path:
    """Return root/sub resolved, or raise OutsideRootError if it escapes root."""
    base = Path(root).resolve()
    target = (base / sub).resolve()
    if not target.is_relative_to(base):
        raise OutsideRootError(f"{sub} is outside {base}")
    return target


def list_dir(root: Path, sub: str | Path = "", suffixes: tuple[str, ...] = ()) -> list[Entry]:
    """Folders first, then files (filtered by suffix), each sorted by name; hidden entries skipped."""
    folder = resolve_inside(root, sub)
    entries: list[Entry] = []
    for p in folder.iterdir():
        if p.name.startswith("."):
            continue
        if p.is_dir():
            entries.append(Entry(p.name, p, True, None))
        elif not suffixes or p.suffix.lower() in suffixes:
            entries.append(Entry(p.name, p, False, p.stat().st_size))
    return sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))


def human_size(size: int | None) -> str:
    """1536 -> '1.5 KB'; None -> ''."""
    if size is None:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return ""
```

- [ ] **Step 4: Run to see them pass**

Run: `uv run python -m pytest tests/ui/test_fs_browser.py -q`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```powershell
git add app/services/fs_browser.py tests/ui/test_fs_browser.py
git commit -m "feat(ui): safe folder listing for the Browse dialog"
```

---

### Task 3: `project_io` (ruamel round-trip)

**Files:**
- Create: `app/services/project_io.py`, `tests/ui/conftest.py`
- Test: `tests/ui/test_project_io.py`

**Interfaces:**
- Produces: `ConfigFileError(message, line=None, column=None)`; `load_yaml(path: Path) -> dict`; `dump_yaml(data: dict) -> str`; `save_yaml(data: dict, path: Path) -> None`; `list_configs(workspace: Path) -> list[Path]`; fixture `example_project -> Path` (config path inside a `tmp_path` copy of `examples/`)

- [ ] **Step 1: Fixture** `tests/ui/conftest.py`

```python
import shutil
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def example_project(tmp_path: Path) -> Path:
    """A copy of examples/config_minimal.yaml + examples/data in tmp_path; returns the config path."""
    shutil.copytree(EXAMPLES / "data", tmp_path / "data")
    config = tmp_path / "config_minimal.yaml"
    shutil.copy(EXAMPLES / "config_minimal.yaml", config)
    return config
```

- [ ] **Step 2: Write the failing tests** `tests/ui/test_project_io.py`

```python
import pytest

from app.services.project_io import ConfigFileError, dump_yaml, list_configs, load_yaml, save_yaml


def test_round_trip_keeps_file_unchanged(example_project):
    original = example_project.read_text(encoding="utf-8")
    save_yaml(load_yaml(example_project), example_project)
    assert example_project.read_text(encoding="utf-8") == original


def test_edit_keeps_comments(example_project):
    data = load_yaml(example_project)
    data["project"]["name"] = "Renamed"
    text = dump_yaml(data)
    assert "name: Renamed" in text or 'name: "Renamed"' in text
    assert "# UTM Zone 48N" in text


def test_syntax_error_reports_line(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("project:\n  name: [unclosed\n  crs: EPSG:32648\n", encoding="utf-8")
    with pytest.raises(ConfigFileError) as info:
        load_yaml(bad)
    assert info.value.line is not None


def test_top_level_must_be_mapping(tmp_path):
    bad = tmp_path / "list.yaml"
    bad.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigFileError):
        load_yaml(bad)


def test_save_creates_parent_folders(tmp_path):
    target = tmp_path / "new" / "config.yaml"
    save_yaml({"project": {"name": "X"}}, target)
    assert load_yaml(target)["project"]["name"] == "X"


def test_list_configs_up_to_three_levels(tmp_path):
    for rel in ["a.yaml", "p1/config.yml", "p1/sub/c.yaml", "p1/sub/deep/too_deep.yaml"]:
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("project: {}\n")
    found = [p.relative_to(tmp_path).as_posix() for p in list_configs(tmp_path)]
    assert found == ["a.yaml", "p1/config.yml", "p1/sub/c.yaml"]


def test_list_configs_missing_workspace(tmp_path):
    assert list_configs(tmp_path / "missing") == []
```

- [ ] **Step 3: Run to see them fail**

Run: `uv run python -m pytest tests/ui/test_project_io.py -q`
Expected: `ModuleNotFoundError: No module named 'app.services.project_io'`.

- [ ] **Step 4: Implement** `app/services/project_io.py`

```python
"""Read and write config YAML from the UI, keeping comments and key order."""
from __future__ import annotations

import io
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError

YAML_PATTERNS = ("*.yaml", "*.yml", "*/*.yaml", "*/*.yml", "*/*/*.yaml", "*/*/*.yml")


class ConfigFileError(Exception):
    """A config file could not be read; line/column are 1-based when known."""

    def __init__(self, message: str, line: int | None = None, column: int | None = None):
        super().__init__(message)
        self.line = line
        self.column = column


def _yaml() -> YAML:
    yaml = YAML()  # round-trip mode: keeps comments, order and quotes
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def load_yaml(path: Path) -> dict:
    """Load a config file as an editable mapping (a dict subclass)."""
    try:
        data = _yaml().load(Path(path).read_text(encoding="utf-8"))
    except MarkedYAMLError as exc:
        mark = exc.problem_mark
        line = mark.line + 1 if mark else None
        column = mark.column + 1 if mark else None
        raise ConfigFileError(f"{exc.problem} (line {line}, column {column})", line, column) from exc
    if not isinstance(data, dict):
        raise ConfigFileError("The config must be a mapping of sections (project:, dem:, …).")
    return data


def dump_yaml(data: dict) -> str:
    buffer = io.StringIO()
    _yaml().dump(data, buffer)
    return buffer.getvalue()


def save_yaml(data: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(data), encoding="utf-8")


def list_configs(workspace: Path) -> list[Path]:
    """YAML files up to three folders deep in the workspace, sorted."""
    workspace = Path(workspace)
    if not workspace.is_dir():
        return []
    found = {p for pattern in YAML_PATTERNS for p in workspace.glob(pattern) if p.is_file()}
    return sorted(found, key=lambda p: str(p).lower())
```

Note: `indent(mapping=2, sequence=4, offset=2)` matches the list style used in `examples/config_minimal.yaml` (`  targets:` / `    - "swatplus"`), which is why the round-trip test is byte-identical.

- [ ] **Step 5: Run to see them pass**

Run: `uv run python -m pytest tests/ui/test_project_io.py -q`
Expected: `7 passed`.

- [ ] **Step 6: Commit**

```powershell
git add app/services/project_io.py tests/ui/conftest.py tests/ui/test_project_io.py
git commit -m "feat(ui): load/save config YAML keeping comments (ruamel round-trip)"
```

---

### Task 4: `runner` (validate/build, never raises)

**Files:**
- Create: `app/services/runner.py`
- Test: `tests/ui/test_runner.py`

**Interfaces:**
- Consumes: `swatprep.SWATPrepProject.from_config(path)`, `.validate() -> list[QACheck]`, `.build(only) -> PrepareResult(output_dir, manifest_path, qa_checks, success)`; fixture `example_project`
- Produces: `RunResult(ok, checks, error, traceback, output_dir, manifest_path, seconds)` with `.count(status) -> int`; `validate(config_path: Path) -> RunResult`; `build(config_path: Path, only: str | None = None) -> RunResult`

- [ ] **Step 1: Write the failing tests** `tests/ui/test_runner.py`

```python
from app.services import runner


def test_validate_example_passes(example_project):
    result = runner.validate(example_project)
    assert result.ok
    assert result.count("fail") == 0
    assert result.count("pass") == 9


def test_validate_reports_missing_file(example_project):
    (example_project.parent / "data" / "dem_30m.tif").unlink()
    result = runner.validate(example_project)
    assert not result.ok
    failed = [c.name for c in result.checks if c.status == "fail"]
    assert failed == ["file_exists:dem.path"]


def test_schema_error_is_reported_not_raised(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("project:\n  name: X\n", encoding="utf-8")  # crs missing
    result = runner.validate(cfg)
    assert not result.ok
    assert "project.crs" in result.error


def test_unexpected_error_is_captured(example_project, monkeypatch):
    def boom(_path):
        raise RuntimeError("boom")

    monkeypatch.setattr(runner.SWATPrepProject, "from_config", boom)
    result = runner.validate(example_project)
    assert not result.ok
    assert "boom" in result.error
    assert result.traceback is not None


def test_build_example_end_to_end(example_project):
    result = runner.build(example_project)
    assert result.ok, result.error
    assert result.count("fail") == 0
    assert result.manifest_path is not None and result.manifest_path.is_file()
    assert result.output_dir == example_project.parent / "output"
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run python -m pytest tests/ui/test_runner.py -q`
Expected: `ModuleNotFoundError: No module named 'app.services.runner'`.

- [ ] **Step 3: Implement** `app/services/runner.py`

```python
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
```

- [ ] **Step 4: Run to see them pass**

Run: `uv run python -m pytest tests/ui/test_runner.py -q`
Expected: `5 passed` (the end-to-end build on `examples/` takes about a second).

- [ ] **Step 5: Commit**

```powershell
git add app/services/runner.py tests/ui/test_runner.py
git commit -m "feat(ui): runner wraps validate/build and reports errors as results"
```

---

### Task 5: Browse dialog, results view, Project page

**Files:**
- Create: `app/ui/browse.py`, `app/ui/results.py`, `app/pages/1_Project.py`
- Test: `tests/ui/test_pages.py` (append two tests)

**Interfaces:**
- Consumes: Tasks 2–4; `app.services.settings.load_settings() -> Settings(data_root, workspace)`
- Produces: `browse_dialog(target_key: str, roots: dict[str, Path], suffixes: tuple[str, ...] = ()) -> None`; `render_result(action: str, result: RunResult) -> None`; session keys `config_choice`, `config_path`, `run_only`, `last_run = (path: str, action: str, RunResult)`; widget keys `validate`, `build`, `browse_config`

- [ ] **Step 1: Append the failing tests** to `tests/ui/test_pages.py`

```python
def test_project_page_without_config_shows_hint(monkeypatch, tmp_path):
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(tmp_path))
    at = AppTest.from_file(str(APP / "pages" / "1_Project.py"), default_timeout=30).run()
    assert not at.exception
    assert "Open a config" in at.info[0].value


def test_project_page_validate_and_build(monkeypatch, example_project):
    monkeypatch.setenv("SWATPREP_WORKSPACE", str(example_project.parent))
    monkeypatch.setenv("SWATPREP_DATA_ROOT", str(example_project.parent / "data"))
    at = AppTest.from_file(str(APP / "pages" / "1_Project.py"), default_timeout=60).run()
    at.selectbox(key="config_choice").select("config_minimal.yaml").run()
    assert at.text_input(key="config_path").value == str(example_project)

    at.button(key="validate").click().run()
    assert not at.exception
    _, action, result = at.session_state["last_run"]
    assert action == "validate" and result.ok and result.count("pass") == 9

    at.button(key="build").click().run()
    assert not at.exception
    _, action, result = at.session_state["last_run"]
    assert action == "build" and result.ok
    assert (example_project.parent / "output" / "manifest.json").is_file()
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run python -m pytest tests/ui/test_pages.py -q`
Expected: the two new tests fail (`1_Project.py` does not exist).

- [ ] **Step 3: Create** `app/ui/browse.py`

```python
"""Browse dialog: pick a file inside DATA_ROOT or WORKSPACE and write it to a session key."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.services.fs_browser import OutsideRootError, human_size, list_dir


def _state(target_key: str) -> tuple[str, str]:
    return f"{target_key}__root", f"{target_key}__sub"


def _enter(sub_key: str, sub: str) -> None:
    st.session_state[sub_key] = sub


def _pick(target_key: str, path: Path) -> None:
    st.session_state[target_key] = str(path)


@st.dialog("Browse", width="large")
def browse_dialog(target_key: str, roots: dict[str, Path], suffixes: tuple[str, ...] = ()) -> None:
    root_key, sub_key = _state(target_key)
    names = list(roots)
    root_name = st.radio("Root", names, horizontal=True, key=root_key, on_change=_enter, args=(sub_key, ""))
    root = roots[root_name]
    sub = st.session_state.get(sub_key, "")
    st.caption(f"`{(root / sub).as_posix()}`")

    try:
        entries = list_dir(root, sub, suffixes)
    except (OutsideRootError, OSError) as exc:
        st.error(f"Cannot open this folder: {exc}")
        return

    if sub:
        parent = Path(sub).parent.as_posix()
        st.button("Up one level", icon=":material/arrow_upward:", key=f"{target_key}__up",
                  on_click=_enter, args=(sub_key, "" if parent == "." else parent))
    for e in (e for e in entries if e.is_dir):
        st.button(e.name, icon=":material/folder:", key=f"{target_key}__d__{e.name}",
                  on_click=_enter, args=(sub_key, (Path(sub) / e.name).as_posix()))

    files = [e for e in entries if not e.is_dir]
    if not files:
        st.caption("No matching files in this folder.")
        return
    labels = {e.name: f"{e.name} · {human_size(e.size)}" for e in files}
    choice = st.radio("Files", list(labels), format_func=labels.get, index=None, key=f"{target_key}__file")
    if choice and st.button("Select", type="primary", key=f"{target_key}__select",
                            on_click=_pick, args=(target_key, root / sub / choice)):
        st.rerun()
```

Why callbacks (`on_click`): Streamlit forbids changing a widget's session value after that widget has been drawn in the same run; callbacks run before the rerun, so setting `config_path` there is safe. `st.rerun()` after Select closes the dialog.

- [ ] **Step 4: Create** `app/ui/results.py`

```python
"""Render a runner.RunResult: counts, errors, QA table, output links."""
from __future__ import annotations

import streamlit as st

from app.services.runner import RunResult


def render_result(action: str, result: RunResult) -> None:
    st.subheader(f"{action.capitalize()} results")
    st.caption(f"Finished in {result.seconds:.1f} s.")

    if result.error:
        st.error(result.error, icon=":material/error:")
        if result.traceback:
            with st.expander("Technical details"):
                st.code(result.traceback, language="text")

    if not result.checks:
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Pass", result.count("pass"))
    c2.metric("Warn", result.count("warn"))
    c3.metric("Fail", result.count("fail"))

    show = st.segmented_control("Show", ["all", "fail", "warn", "pass"], default="all", key=f"{action}__filter")
    rows = [
        {"Status": c.status, "Check": c.name, "Message": c.message}
        for c in result.checks
        if show in (None, "all") or c.status == show
    ]
    st.dataframe(rows, hide_index=True, width="stretch")

    if result.output_dir:
        st.caption(f"Output folder: `{result.output_dir}`")
    if result.manifest_path and result.manifest_path.is_file():
        st.download_button("Download manifest.json", result.manifest_path.read_bytes(),
                           file_name="manifest.json", mime="application/json", icon=":material/download:")
        report = result.manifest_path.with_name("qa_report.md")
        if report.is_file():
            with st.expander("QA report"):
                st.markdown(report.read_text(encoding="utf-8"))
```

- [ ] **Step 5: Create** `app/pages/1_Project.py`

```python
"""Project page: open a config, validate it, build it and review the QA results."""
from pathlib import Path

import streamlit as st

from app.services import project_io, runner
from app.services.settings import load_settings
from app.ui.browse import browse_dialog
from app.ui.results import render_result

DOMAINS = ("clip", "dem", "landuse", "soil", "weather", "streamflow")
ALL = "All configured"

st.set_page_config(page_title="Project · swatprep", layout="wide")
settings = load_settings()


def _open_from_list() -> None:
    st.session_state["config_path"] = str(settings.workspace / st.session_state["config_choice"])


with st.sidebar:
    st.subheader("Config")
    configs = project_io.list_configs(settings.workspace)
    st.selectbox("Open from workspace", [p.relative_to(settings.workspace).as_posix() for p in configs],
                 index=None, placeholder="Choose a config…", key="config_choice", on_change=_open_from_list)
    st.text_input("Config path", key="config_path", placeholder="Paste a path to config.yaml…")
    if st.button("Browse", icon=":material/folder_open:", key="browse_config"):
        browse_dialog("config_path", {"Workspace": settings.workspace, "Data": settings.data_root},
                      suffixes=(".yaml", ".yml"))

raw = st.session_state.get("config_path", "").strip()
if not raw:
    st.title("Project")
    st.info("Open a config to start: choose one from the workspace, paste a path, or browse.")
    st.stop()

path = Path(raw)
if not path.is_file():
    st.title("Project")
    st.error(f"Config not found: `{path}`", icon=":material/error:")
    st.stop()

try:
    data = project_io.load_yaml(path)
except project_io.ConfigFileError as exc:
    st.title("Project")
    st.error(f"Cannot read the config: {exc}", icon=":material/error:")
    st.stop()

name = (data.get("project") or {}).get("name") or path.stem
st.title(name)
st.caption(f"`{path}`")
with st.expander("YAML"):
    st.code(path.read_text(encoding="utf-8"), language="yaml")

configured = [d for d in DOMAINS if d in data]
col_run, col_validate, col_build = st.columns([2, 1, 1], vertical_alignment="bottom")
only = col_run.selectbox("Run", [ALL, *configured], key="run_only")
if col_validate.button("Validate", icon=":material/fact_check:", key="validate", width="stretch"):
    with st.spinner("Validating…"):
        st.session_state["last_run"] = (str(path), "validate", runner.validate(path))
if col_build.button("Build", type="primary", icon=":material/play_arrow:", key="build", width="stretch"):
    with st.status("Building…") as status:
        result = runner.build(path, None if only == ALL else only)
        status.update(label="Build finished." if result.ok else "Build failed.",
                      state="complete" if result.ok else "error")
    st.session_state["last_run"] = (str(path), "build", result)

last = st.session_state.get("last_run")
if last and last[0] == str(path):
    render_result(last[1], last[2])
```

- [ ] **Step 6: Run the whole suite**

Run: `uv run python -m pytest -q`
Expected: `283 passed` (2 existing warnings in core tests).

- [ ] **Step 7: Manual check (Windows)**

```powershell
New-Item -ItemType Directory -Force D:\SWAT-model\workspace\example
Copy-Item -Recurse -Force examples\* D:\SWAT-model\workspace\example\
$env:SWATPREP_WORKSPACE = "D:\SWAT-model\workspace"
$env:SWATPREP_DATA_ROOT = "D:\DATA_STORAGE\_data"
uv run streamlit run app/Home.py
```

On the Project page: choose `example/config_minimal.yaml` → Validate (Pass 9) → Build (Fail 0, Warn 1) → Download manifest.json; then Browse → Workspace → example → `config_minimal.yaml` → Select.

- [ ] **Step 8: Commit**

```powershell
git add app/ui/browse.py app/ui/results.py app/pages/1_Project.py tests/ui/test_pages.py
git commit -m "feat(ui): Project page to open, validate and build a config"
```

---

### Task 6: Docker check and pull request

- [ ] **Step 1: Build and run**

```powershell
docker compose up --build
```

Open `http://localhost:8501/Project`, repeat the Task 5 manual check with `example/config_minimal.yaml` (the workspace mount is `D:\SWAT-model\workspace`). The theme must look the same as on Windows.

- [ ] **Step 2: Push and open a PR**

```powershell
git add docs/superpowers/specs/2026-10-27-phase2-project-page-design.md docs/superpowers/plans
git commit -m "docs: phase 2 spec and slice 1 plan"
git push -u origin feature/project-page
```

Open the PR, wait for `test` to pass, merge. No release yet: `v0.3.0` comes after slice 4.

---

## Self-Review

- Spec coverage (slice 1 scope, spec §6.1): Open (workspace list, paste, Browse) ✔ Task 5; `project_io` with ruamel ✔ Task 3; `runner` never raising, schema errors as text ✔ Task 4; `fs_browser` traversal guard ✔ Task 2; results (metrics, filter, manifest download, QA report) ✔ Task 5; theme §7.1 ✔ Task 1; no emoji §7.3 ✔ Task 1/5; Docker theme ✔ Task 1 Step 6, Task 6. Deferred by spec to later slices: form fields, Save, inline field errors, unsaved indicator, button locking.
- Placeholders: none.
- Names: `RunResult`, `validate`, `build`, `load_yaml`, `dump_yaml`, `save_yaml`, `list_configs`, `ConfigFileError`, `list_dir`, `human_size`, `browse_dialog`, `render_result`, `ok_label`, `STATUS` are identical across tasks and tests.
