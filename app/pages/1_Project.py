"""Project page: open a project folder, pick or create a config in it, edit it, validate, build and explore."""
import os
import string
from pathlib import Path

import streamlit as st

from app.services import project_io, runner
from app.services.form_layout import SECTIONS
from app.services.form_state import count_for, file_errors, schema_errors
from app.services.projects import default_config, list_configs
from app.services.runner import RunResult
from app.services.settings import load_settings
from app.ui.branding import setup_page
from app.ui.explore import render_explore
from app.ui.fields import FormContext, reset_form_state, toggle_part
from app.ui.project_sidebar import new_config_dialog, render_config_picker, render_project_header
from app.ui.projects_home import render_home
from app.ui.results import render_result
from app.ui.sections import render_project, render_section

ALL = "All configured"

setup_page("Project · swatprep")
settings = load_settings()
state = st.session_state


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


def _load(path: Path) -> None:
    state["cfg"] = project_io.load_yaml(path)
    state["clean_yaml"] = project_io.dump_yaml(state["cfg"])  # what "no changes" looks like
    state["loaded_path"] = str(path)
    state["errors_on"] = False
    state["file_errors"] = {}
    reset_form_state()


def _discard() -> None:
    state["loaded_path"] = None  # forces a reload from disk


# ---------------------------------------------------------------- no project open: the Projects screen
project = Path(state["project"]) if state.get("project") else None
if project is None or not project.is_dir():
    state["project"] = None
    render_home(_roots(None))
    st.stop()

# ---------------------------------------------------------------- project open: pick its config
configs = list_configs(project)
current = Path(state["config_path"]) if state.get("config_path") else None
if current not in configs:
    current = default_config(project)
    state["config_path"] = str(current) if current else None

load_error = None
if current is not None and state.get("loaded_path") != str(current):
    try:
        _load(current)
    except project_io.ConfigFileError as exc:
        state["loaded_path"] = None
        load_error = exc
loaded = current is not None and state.get("loaded_path") == str(current)
locked = loaded and project_io.dump_yaml(state["cfg"]) != state["clean_yaml"]

with st.sidebar:
    render_project_header(project, locked)
    crs = (state["cfg"].get("project") or {}).get("crs") if loaded else None
    crs = str(crs) if crs else None   # ruamel gives a quoted-string subclass; widgets and pyproj need str
    render_config_picker(project, configs, current, locked, crs=crs)

if current is None:
    st.title(project.name or str(project))
    st.info("This project has no config yet.", icon=":material/info:")
    if st.button("New config", type="primary", icon=":material/add:", key="first_config"):
        new_config_dialog(project)
    st.stop()
if not loaded:
    st.title(project.name or str(project))
    st.error(f"Cannot read `{current.name}`: {load_error}", icon=":material/error:")
    st.stop()
path = current

cfg: dict = state["cfg"]
cfg.setdefault("project", {})
ctx = FormContext(cfg=cfg, base_dir=path.parent, roots=_roots(project))

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
