import io

import streamlit as st
from ruamel.yaml import YAML

from app.services.form_model import field_spec
from app.ui.fields import _on_change, section_at
from swatprep.config import FillCSVConfig


def cfg_from(text: str):
    return YAML().load(io.StringIO(text))


def test_section_at_follows_dicts_and_lists():
    cfg = cfg_from("weather:\n  fill:\n    csv: {stations: a.csv}\nclip:\n  - {src: a.tif}\n")
    assert section_at(cfg, "weather.fill.csv")["stations"] == "a.csv"
    assert section_at(cfg, "clip.0")["src"] == "a.tif"


def test_change_for_a_section_that_is_gone_is_ignored():
    """A change can arrive for a block that was removed meanwhile (section switched off, fill type
    changed, clip item removed); there is nothing left to update, and it must not crash the page."""
    cfg = cfg_from("weather:\n  fill:\n    type: netcdf\n")
    spec = field_spec(FillCSVConfig, "file_pattern")
    st.session_state["f::weather.fill.csv.file_pattern"] = "{name}.csv"
    _on_change(cfg, "weather.fill.csv", spec, "f::weather.fill.csv.file_pattern")
    _on_change(cfg, "clip.0", spec, "f::weather.fill.csv.file_pattern")
    assert "csv" not in cfg["weather"]["fill"] and "clip" not in cfg
