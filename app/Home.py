"""Home page: environment health report."""
import streamlit as st

from app.services.environment import get_report

st.set_page_config(page_title="swatprep", layout="wide")
st.title("swatprep")

report = get_report()

if report.ok:
    st.success("Environment is ready.")
else:
    st.error("Environment has problems. See the ❌ items below.")

st.caption(f"Python {report.python}")

st.subheader("Packages")
st.table([{"Package": k, "Version": v} for k, v in report.packages.items()])

for title, checks in (("GDAL drivers", report.drivers), ("Folders", report.folders)):
    st.subheader(title)
    for c in checks:
        st.write(f"{'✅' if c.ok else '❌'} **{c.name}**: {c.detail}")