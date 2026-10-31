#!/usr/bin/env sh
# SWATprep installer for Linux and macOS.
#   sh install.sh            install or update to the latest release
#   sh install.sh v0.3.0     install a given release
set -eu
REPO="wosonday/swat-preprocessing"
API="${SWATPREP_RELEASES_API:-https://api.github.com/repos/${REPO}/releases/latest}"

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    echo "Looking up the latest release..."
    VERSION="$(curl -fsSL "$API" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
    if [ -z "$VERSION" ]; then
        echo "Could not find the latest release. Try again later, or run: sh install.sh v0.3.0" >&2
        exit 1
    fi
fi
SWATPREP_SOURCE="${SWATPREP_SOURCE:-swatprep[geo,app] @ https://github.com/${REPO}/archive/refs/tags/${VERSION}.zip}"

if [ -n "${SWATPREP_DRY_RUN:-}" ]; then
    echo "Would install ${VERSION} from: ${SWATPREP_SOURCE}"
    exit 0
fi

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

echo "Done: SWATprep ${VERSION}. Start it with: $BIN/swatprep-ui"
