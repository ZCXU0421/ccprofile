#!/usr/bin/env bash
# ccprofile installer for macOS/Linux
# Run: bash install.sh
#
# Can be run standalone — if no binary is found locally, it will
# automatically download the correct one from GitHub Releases.

set -e

INSTALL_DIR="$HOME/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RELEASES_URL="https://github.com/ZCXU0421/ccprofile/releases/latest/download"
CHECKSUMS_NAME="SHA256SUMS"
TMP_FILE=""
TMP_CHECKSUM=""

download_file() {
    local url="$1"
    local output="$2"

    if command -v curl >/dev/null 2>&1; then
        curl -sLf "$url" -o "$output"
    elif command -v wget >/dev/null 2>&1; then
        wget -q "$url" -O "$output"
    else
        echo "[ERROR] Neither curl nor wget found. Please install one and retry."
        return 127
    fi
}

cleanup_temp_files() {
    if [ -n "$TMP_FILE" ] && [ -f "$TMP_FILE" ]; then
        rm -f "$TMP_FILE"
    fi
    if [ -n "$TMP_CHECKSUM" ] && [ -f "$TMP_CHECKSUM" ]; then
        rm -f "$TMP_CHECKSUM"
    fi
}

verify_checksum() {
    local file="$1"
    local file_name="$2"
    local checksums_file="$3"
    local expected=""
    local actual=""

    if ! expected="$(awk -v name="$file_name" '$2 == name { print $1; found = 1; exit } END { if (!found) exit 1 }' "$checksums_file")"; then
        echo "[ERROR] Checksum for $file_name not found in $CHECKSUMS_NAME."
        return 1
    fi

    if command -v sha256sum >/dev/null 2>&1; then
        actual="$(sha256sum "$file" | awk '{print $1}')"
    elif command -v shasum >/dev/null 2>&1; then
        actual="$(shasum -a 256 "$file" | awk '{print $1}')"
    else
        echo "[ERROR] Neither sha256sum nor shasum found. Cannot verify download."
        return 1
    fi

    if [ "$actual" != "$expected" ]; then
        echo "[ERROR] SHA256 checksum mismatch for $file_name."
        echo "        Expected: $expected"
        echo "        Actual:   $actual"
        return 1
    fi
}

trap cleanup_temp_files EXIT

echo "========================================"
echo "  ccprofile installer"
echo "========================================"
echo ""

# Determine the binary name — check local paths first
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

# If no local binary, download from GitHub Releases
if [ -z "$BINARY" ]; then
    echo "[INFO] No local binary found, downloading from GitHub Releases..."

    REMOTE_NAME=""
    if [ "$(uname -s)" = "Darwin" ]; then
        if [ "$(uname -m)" = "arm64" ]; then
            REMOTE_NAME="ccprofile-macos-arm64"
        else
            REMOTE_NAME="ccprofile-macos-intel"
        fi
    elif [ "$(uname -s)" = "Linux" ]; then
        REMOTE_NAME="ccprofile-linux"
    else
        echo "[ERROR] Unsupported OS: $(uname -s)"
        exit 1
    fi

    DOWNLOAD_URL="$RELEASES_URL/$REMOTE_NAME"
    TMP_FILE="$(mktemp)"
    TMP_CHECKSUM="$(mktemp)"

    echo "  Downloading $DOWNLOAD_URL ..."
    if ! download_file "$DOWNLOAD_URL" "$TMP_FILE"; then
        echo "[ERROR] Download failed. Please check your internet connection."
        exit 1
    fi

    echo "  Downloading $RELEASES_URL/$CHECKSUMS_NAME ..."
    if ! download_file "$RELEASES_URL/$CHECKSUMS_NAME" "$TMP_CHECKSUM"; then
        echo "[ERROR] Checksum download failed. Refusing to install an unverified binary."
        exit 1
    fi

    echo "  Verifying SHA256 checksum ..."
    if ! verify_checksum "$TMP_FILE" "$REMOTE_NAME" "$TMP_CHECKSUM"; then
        exit 1
    fi

    BINARY="$TMP_FILE"
    chmod +x "$TMP_FILE"
    echo "  Download verified."
    echo ""
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
