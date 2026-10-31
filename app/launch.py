"""Start the web app: `swatprep-ui [streamlit options]`, e.g. `swatprep-ui --server.port 8502`."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


def streamlit_argv(extra: list[str]) -> list[str]:
    return ["streamlit", "run", str(APP_DIR / "Home.py"), *extra]


def main(argv: list[str] | None = None) -> None:
    from streamlit.web import cli as stcli

    # Streamlit reads ./.streamlit/config.toml from the working directory: run from the
    # app folder so the theme ships with the package wherever the user starts it.
    os.chdir(APP_DIR)
    sys.argv = streamlit_argv(sys.argv[1:] if argv is None else argv)
    sys.exit(stcli.main())
