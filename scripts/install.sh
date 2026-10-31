#!/usr/bin/env sh
# SWATprep installer for Linux and macOS. Run: sh install.sh  (run again to update)
set -eu
VERSION="v0.3.0"
SWATPREP_SOURCE="${SWATPREP_SOURCE:-swatprep[geo,app] @ https://github.com/wosonday/swat-preprocessing/archive/refs/tags/${VERSION}.zip}"

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    PATH="$HOME/.local/bin:$PATH"
fi

echo "Installing SWATprep ${VERSION}. This can take a few minutes the first time..."
uv tool install --python 3.12 --force "$SWATPREP_SOURCE"
BIN="$(uv tool dir --bin)"

if [ "$(uname)" = "Linux" ]; then
    APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    mkdir -p "$APPS"
    cat > "$APPS/swatprep.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=SWATprep
Comment=SWATprep web app
Exec=$BIN/swatprep-ui
Terminal=true
Categories=Science;
DESKTOP
    echo "Added SWATprep to the application menu."
fi

echo "Done. Start it with: $BIN/swatprep-ui"
