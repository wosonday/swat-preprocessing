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
