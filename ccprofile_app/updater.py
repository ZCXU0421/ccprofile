"""Self-update: detect, download, verify and replace the ccprofile bundle."""

import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from .constants import (
    GITHUB_REPO,
    UPDATE_CHECK_FILE,
    UPDATE_CHECK_INTERVAL,
    UPDATE_USER_AGENT,
    VERSION,
)
from .display import BOLD, CYAN, GREEN, RESET, kv, panel
from .i18n import t
from .terminal import confirm_action


class UpdateError(Exception):
    """Recoverable update failure with a user-facing message."""


class RateLimitedError(UpdateError):
    """GitHub API rate limit hit."""


_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


def parse_version(s):
    """Parse 'v?MAJOR.MINOR.PATCH[-pre]' into (major, minor, patch, pre|None)."""
    m = _VERSION_RE.match((s or "").strip())
    if not m:
        raise ValueError(f"invalid version: {s!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4))


def _version_key(parsed):
    major, minor, patch, pre = parsed
    # A release (pre is None) sorts after any prerelease of the same x.y.z.
    return (major, minor, patch, 0 if pre else 1, pre or "")


def is_newer(latest, current, include_prerelease=False):
    """Return True if `latest` is strictly newer than `current`."""
    lp = parse_version(latest)
    cp = parse_version(current)
    if lp[3] and not include_prerelease:
        return False  # ignore prereleases unless explicitly asked
    return _version_key(lp) > _version_key(cp)


def platform_asset():
    """Return the release asset filename for the current platform."""
    if sys.platform == "darwin":
        if platform.machine() == "arm64":
            return "ccprofile-macos-arm64.tar.gz"
        raise UpdateError(t("update.err_unsupported"))
    if sys.platform == "linux":
        return "ccprofile-linux.tar.gz"
    if sys.platform == "win32":
        return "ccprofile-windows.zip"
    raise UpdateError(t("update.err_unsupported"))


def expected_sha256(asset_name, text):
    """Return the expected SHA256 hex for `asset_name` parsed from SHA256SUMS text."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1] == asset_name:
            return parts[0].lower()
    return None


def should_check_now(cache, now_ts, interval=UPDATE_CHECK_INTERVAL):
    """Return True if a new network check is allowed (> interval since last)."""
    last = cache.get("last_check_ts")
    if last is None:
        return True
    return now_ts - last >= interval
