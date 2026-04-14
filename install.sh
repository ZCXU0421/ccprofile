#!/usr/bin/env bash
# ccprofile installer for macOS/Linux
# Run: bash install.sh

set -e

INSTALL_DIR="$HOME/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================"
echo "  ccprofile installer"
echo "========================================"
echo ""

# Determine the binary name — check dist/ first, then script directory
BINARY=""
for DIR in "$SCRIPT_DIR/dist" "$SCRIPT_DIR"; do
    if [ -f "$DIR/ccprofile" ]; then
        BINARY="$DIR/ccprofile"
        break
    elif [ "$(uname -s)" = "Darwin" ]; then
        if [ -f "$DIR/ccprofile-macos-arm64" ]; then
            BINARY="$DIR/ccprofile-macos-arm64"
            break
        elif [ -f "$DIR/ccprofile-macos-intel" ]; then
            BINARY="$DIR/ccprofile-macos-intel"
            break
        elif [ -f "$DIR/ccprofile-macos" ]; then
            BINARY="$DIR/ccprofile-macos"
            break
        fi
    elif [ -f "$DIR/ccprofile-linux" ]; then
        BINARY="$DIR/ccprofile-linux"
        break
    fi
done

if [ -z "$BINARY" ]; then
    echo "[ERROR] No ccprofile binary found in $SCRIPT_DIR/dist or $SCRIPT_DIR"
    exit 1
fi

# Create install directory
mkdir -p "$INSTALL_DIR"
echo "[1/3] Install directory: $INSTALL_DIR"

# Copy and set permissions
cp "$BINARY" "$INSTALL_DIR/ccprofile"
chmod +x "$INSTALL_DIR/ccprofile"
echo "[2/3] Installed ccprofile to $INSTALL_DIR/ccprofile"

# Add to PATH in shell config — detect the user's login shell, not the
# shell that happens to be running this script (e.g. bash invoked on macOS).
SHELL_RC=""
LOGIN_SHELL="${SHELL:-}"
if [ -z "$LOGIN_SHELL" ]; then
    LOGIN_SHELL="$(dscl . -read ~/ UserShell 2>/dev/null | awk '{print $2}' || true)"
fi
case "$LOGIN_SHELL" in
    */zsh)  SHELL_RC="$HOME/.zshrc" ;;
    */bash) SHELL_RC="$HOME/.bashrc" ;;
    *)      if [ -n "$ZSH_VERSION" ]; then
                SHELL_RC="$HOME/.zshrc"
            elif [ -n "$BASH_VERSION" ]; then
                SHELL_RC="$HOME/.bashrc"
            fi ;;
esac

NEED_SOURCE=false
if [ -n "$SHELL_RC" ]; then
    if ! echo "$PATH" | tr ':' '\n' | grep -qxF "$INSTALL_DIR"; then
        # Check if already in rc file
        if ! grep -q "$INSTALL_DIR" "$SHELL_RC" 2>/dev/null; then
            echo "" >> "$SHELL_RC"
            echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$SHELL_RC"
        fi
        echo "[3/3] Added $INSTALL_DIR to PATH in $SHELL_RC"
        echo ""
        echo "NOTE: Run 'source $SHELL_RC' or restart your terminal."
        NEED_SOURCE=true
    else
        echo "[3/3] $INSTALL_DIR is already in PATH"
    fi
else
    echo "[3/3] Please add $INSTALL_DIR to your PATH manually"
fi

echo ""
echo "Installation complete! You can now use: ccprofile"
