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
