"""Project page: open or create a config, edit it as a form, validate, build and review QA."""
import os
import string
from pathlib import Path

import streamlit as st

from app.services import project_io, runner
from app.services.form_layout import SECTIONS
from app.services.form_state import count_for, file_errors, new_config, schema_errors
from app.services.recent import add_recent, load_recent
from app.services.runner import RunResult
from app.services.settings import load_settings
from app.ui.branding import setup_page
from app.ui.browse import browse_dialog
from app.ui.explore import render_explore
from app.ui.fields import FormContext, reset_form_state, toggle_part
from app.ui.results import render_result
from app.ui.sections import render_project, render_section

ALL = "All configured"

setup_page("Project · swatprep")
settings = load_settings()
state = st.session_state

if "project_dir" not in state:
    history = load_recent()
    state["project_dir"] = history[0] if history else os.environ.get("SWATPREP_WORKSPACE", "")


def _folder(raw: str) -> Path | None:
    folder = Path(raw.strip()) if raw and raw.strip() else None
    return folder if folder and folder.is_dir() else None


def _roots(project_dir: Path | None) -> dict[str, Path]:
    """Places the Browse dialog can start from: the project, the data root, home, and drives on Windows."""
    candidates: dict[str, Path | None] = {"Project": project_dir, "Data": settings.data_root}
    if os.environ.get("SWATPREP_WORKSPACE"):
        candidates["Workspace"] = settings.workspace
    candidates["Home"] = Path.home()
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            candidates[f"{letter}:"] = Path(f"{letter}:/")
    return {name: p for name, p in candidates.items() if p is not None and p.is_dir()}


def _use_recent() -> None:
    state["project_dir"] = state["recent_choice"]


def _open_from_list() -> None:
    state["config_path"] = str(Path(state["project_dir"].strip()) / state["config_choice"])


def _create(key: str) -> None:
    target = Path(state[key].strip())
    if target.exists():
        state["new_error"] = f"{target} already exists. Open it instead."
        return
    project_io.save_yaml(new_config(state["new_name"].strip() or target.parent.name, state["new_crs"].strip()), target)
    state["new_error"] = None
    state["config_path"] = str(target)


def _load(path: Path, project_dir: Path | None) -> None:
    state["cfg"] = project_io.load_yaml(path)
    state["clean_yaml"] = project_io.dump_yaml(state["cfg"])  # what "no changes" looks like
    state["loaded_path"] = str(path)
    state["errors_on"] = False
    state["file_errors"] = {}
    reset_form_state()
    inside = project_dir is not None and path.resolve().is_relative_to(project_dir.resolve())
    add_recent(project_dir if inside else path.parent)


def _discard() -> None:
    state["loaded_path"] = None  # forces a reload from disk


# ---------------------------------------------------------------- sidebar: project folder / config
with st.sidebar:
    st.subheader("Project folder")
    history = load_recent()
    if history:
        st.selectbox("Recent", history, index=None, placeholder="Choose a recent folder…", key="recent_choice",
                     on_change=_use_recent)
    st.text_input("Folder", key="project_dir", placeholder="Paste a folder path…")
    project_dir = _folder(state["project_dir"])
    roots = _roots(project_dir)
    if st.button("Browse", icon=":material/folder_open:", key="browse_project"):
        browse_dialog("project_dir", roots, pick="dir")
    if state["project_dir"].strip() and project_dir is None:
        st.caption(":red[:material/error: Folder not found]")

    st.subheader("Config")
    configs = project_io.list_configs(project_dir) if project_dir else []
    st.selectbox("Open config", [p.relative_to(project_dir).as_posix() for p in configs], index=None,
                 placeholder="Choose a config…" if configs else "No config in this folder", key="config_choice",
                 on_change=_open_from_list, disabled=not configs)
    st.text_input("Config path", key="config_path", placeholder="Paste a path to config.yaml…")
    if st.button("Browse", icon=":material/folder_open:", key="browse_config"):
        browse_dialog("config_path", roots, suffixes=(".yaml", ".yml"))
    with st.expander("New config"):
        new_key = f"new_path::{project_dir}"
        with st.form("new_config", border=False):
            st.text_input("File", key=new_key, value=str((project_dir or Path.home()) / "config.yaml"))
            st.text_input("Project name", key="new_name", placeholder="MaDa_Basin_2026")
            st.text_input("CRS", key="new_crs", placeholder="EPSG:32648")
            st.form_submit_button("Create", icon=":material/add:", on_click=_create, args=(new_key,))
        if state.get("new_error"):
            st.error(state["new_error"], icon=":material/error:")

raw = state.get("config_path", "").strip()
path = Path(raw) if raw else None
if path is None or not path.is_file():
    st.title("Project")
    if path is None:
        st.info("Open a config to start: choose one from the workspace, paste a path, browse, or create a new one.")
    else:
        st.error(f"Config not found: `{path}`", icon=":material/error:")
    st.stop()

if state.get("loaded_path") != str(path):
    try:
        _load(path, project_dir)
    except project_io.ConfigFileError as exc:
        state["loaded_path"] = None
        st.title("Project")
        st.error(f"Cannot read the config: {exc}", icon=":material/error:")
        st.stop()

cfg: dict = state["cfg"]
cfg.setdefault("project", {})
ctx = FormContext(cfg=cfg, base_dir=path.parent, roots=_roots(project_dir) or {"Config folder": path.parent})

# ---------------------------------------------------------------- sidebar: functions / save
with st.sidebar:
    st.subheader("Functions")
    for key, (label, _model) in SECTIONS.items():
        toggle_part(ctx, "", key, label, factory=(lambda: [{}]) if key == "clip" else dict)

# ---------------------------------------------------------------- header and actions
st.title((cfg.get("project") or {}).get("name") or path.stem)
st.caption(f"`{path}`")

configured = [k for k in SECTIONS if k in cfg]
col_run, col_validate, col_build = st.columns([2, 1, 1], vertical_alignment="bottom")
only = col_run.selectbox("Run", [ALL, *configured], key="run_only")
do_validate = col_validate.button("Validate", icon=":material/fact_check:", key="validate", width="stretch")
do_build = col_build.button("Build", type="primary", icon=":material/play_arrow:", key="build", width="stretch")

if do_validate or do_build:
    action = "build" if do_build else "validate"
    project_io.save_yaml(cfg, path)  # validate and build read the file
    state["clean_yaml"] = project_io.dump_yaml(cfg)
    state["errors_on"] = True
    problems = schema_errors(cfg)
    if problems:
        result = RunResult(ok=False, error=f"Fix {len(problems)} field(s) marked in the form, then try again.")
        state["file_errors"] = {}
    else:
        with st.spinner("Validating…"):
            result = runner.validate(path)
        state["file_errors"] = file_errors(result.checks)
        if do_build and result.ok:
            with st.status("Building…") as status:
                result = runner.build(path, None if only == ALL else only)
                state["last_run"] = (str(path), action, result)
                status.update(label="Build finished." if result.ok else "Build failed.",
                              state="complete" if result.ok else "error")
    state["last_run"] = (str(path), action, result)

errors = {**schema_errors(cfg), **state.get("file_errors", {})} if state.get("errors_on") else {}
ctx.errors = errors


# ---------------------------------------------------------------- configure (form tabs) or explore
def _tab_label(key: str, label: str) -> str:
    n = count_for(errors, key)
    return f"{label} ({n})" if n else label


mode = st.segmented_control("Mode", ["Configure", "Explore"], default="Configure", required=True, key="mode",
                            label_visibility="collapsed")
if mode == "Configure":
    labels = [_tab_label("project", "Project")] + [_tab_label(k, SECTIONS[k][0]) for k in configured] + ["YAML"]
    tabs = st.tabs(labels)
    with tabs[0]:
        render_project(ctx)
    for key, tab in zip(configured, tabs[1:-1]):
        with tab:
            render_section(ctx, key)
    with tabs[-1]:
        st.code(project_io.dump_yaml(cfg), language="yaml")
else:
    render_explore(path, unsaved=project_io.dump_yaml(cfg) != state["clean_yaml"])

# ---------------------------------------------------------------- sidebar: save (after the form, so it sees every edit)
with st.sidebar:
    st.divider()
    unsaved = project_io.dump_yaml(cfg) != state["clean_yaml"]
    if unsaved:
        st.caption(":orange[:material/edit: Unsaved changes]")
    save_col, discard_col = st.columns(2)
    if save_col.button("Save", icon=":material/save:", key="save", width="stretch", disabled=not unsaved):
        project_io.save_yaml(cfg, path)
        state["clean_yaml"] = project_io.dump_yaml(cfg)
        st.toast("Config saved.", icon=":material/check_circle:")
        st.rerun()
    discard_col.button("Discard", icon=":material/undo:", key="discard", width="stretch", disabled=not unsaved,
                       on_click=_discard)

last = state.get("last_run")
if mode == "Configure" and last and last[0] == str(path):
    st.divider()
    render_result(last[1], last[2])
