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
from .display import BOLD, GREEN, RESET, kv
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
    """Return True if a new network check is allowed (interval or more since last)."""
    last = cache.get("last_check_ts")
    if last is None:
        return True
    return now_ts - last >= interval


def _ssl_context():
    """TLS context; prefer certifi's CA bundle (bundled in frozen builds)."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _http_get_json(url, timeout=10):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UPDATE_USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            data = resp.read()
        return json.loads(data.decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RateLimitedError(t("update.err_rate_limited"))
        raise UpdateError(t("update.err_network"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        raise UpdateError(t("update.err_network"))


def _http_head_location(url, timeout=5):
    """Follow the `releases/latest` redirect and read the tag from the final URL."""
    req = urllib.request.Request(url, headers={"User-Agent": UPDATE_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            final = resp.geturl()
    except urllib.error.URLError:
        raise UpdateError(t("update.err_network"))
    return final.rstrip("/").rsplit("/", 1)[-1]


def fetch_latest_release():
    """Return latest release info, falling back to the redirect tag on rate limit."""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        data = _http_get_json(api_url)
    except RateLimitedError:
        redirect_url = f"https://github.com/{GITHUB_REPO}/releases/latest"
        try:
            tag = _http_head_location(redirect_url)
        except UpdateError:
            raise RateLimitedError(t("update.err_rate_limited"))
        version = tag[1:] if tag.startswith("v") else tag
        return {"tag": tag, "version": version, "body": "", "assets": {}}

    tag = data.get("tag_name", "")
    version = tag[1:] if tag.startswith("v") else tag
    body = data.get("body") or ""
    assets = {}
    for a in data.get("assets", []):
        name = a.get("name")
        url = a.get("browser_download_url")
        if name and url:
            assets[name] = url
    return {"tag": tag, "version": version, "body": body, "assets": assets}


def _safe_tar_extract(tar, dest_dir):
    """Extract a tar rejecting path-traversal members."""
    dest = Path(dest_dir).resolve()
    for member in tar.getmembers():
        member_dest = (dest / member.name).resolve()
        try:
            member_dest.relative_to(dest)
        except ValueError:
            raise UpdateError(t("update.err_extract"))
    tar.extractall(dest)


def _safe_zip_extract(zf, dest_dir):
    """Extract a zip rejecting path-traversal members."""
    dest = Path(dest_dir).resolve()
    for member in zf.infolist():
        member_dest = (dest / member.filename).resolve()
        try:
            member_dest.relative_to(dest)
        except ValueError:
            raise UpdateError(t("update.err_extract"))
    zf.extractall(dest)


def download_to(url, dest, timeout=30):
    """Stream `url` to `dest` (a path). Raises UpdateError on failure."""
    if not url.startswith("https://"):
        raise UpdateError(t("update.err_network"))
    req = urllib.request.Request(url, headers={"User-Agent": UPDATE_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        raise UpdateError(t("update.err_network"))


def verify_sha256(path, expected):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().lower() == expected.lower()


def extract_bundle(archive_path, dest_dir):
    """Extract the release archive; return the inner `ccprofile/` directory."""
    archive_path = Path(archive_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    if archive_path.suffix == ".zip":
        try:
            with zipfile.ZipFile(archive_path) as zf:
                _safe_zip_extract(zf, dest_dir)
        except (zipfile.BadZipFile, OSError):
            raise UpdateError(t("update.err_extract"))
    else:
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                _safe_tar_extract(tar, dest_dir)
        except (tarfile.TarError, OSError):
            raise UpdateError(t("update.err_extract"))
    bundle = dest_dir / "ccprofile"
    exe_name = "ccprofile.exe" if sys.platform == "win32" else "ccprofile"
    if not (bundle / exe_name).exists():
        raise UpdateError(t("update.err_extract"))
    return bundle


def is_frozen():
    """Return True when running as a PyInstaller build."""
    return getattr(sys, "frozen", False)


def _bundle_dir():
    """Return the onedir bundle directory containing the running executable."""
    return Path(sys.executable).parent


def replace_bundle_unix(new_bundle_dir):
    """Atomically swap the bundle dir on macOS/Linux (safe while running)."""
    new_bundle_dir = Path(new_bundle_dir)
    target = _bundle_dir()
    backup = target.with_name(target.name + ".old")
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)

    try:
        shutil.move(str(target), str(backup))
    except OSError:
        raise UpdateError(t("update.err_install"))
    try:
        shutil.move(str(new_bundle_dir), str(target))
    except Exception:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(backup), str(target))
        raise UpdateError(t("update.err_install"))
    shutil.rmtree(backup, ignore_errors=True)


def replace_bundle_windows(new_bundle_dir):
    """Stage the new bundle and spawn a detached .bat to swap after we exit.

    Windows locks the running .exe + _internal DLLs, so the actual file
    replacement happens once this process has terminated.
    """
    new_bundle_dir = Path(new_bundle_dir)
    pid = os.getpid()
    staging_parent = Path(tempfile.gettempdir()) / f"ccprofile-update-{pid}"
    staging_bundle = staging_parent / "ccprofile"
    if staging_parent.exists():
        shutil.rmtree(staging_parent, ignore_errors=True)
    staging_parent.mkdir(parents=True)
    shutil.move(str(new_bundle_dir), str(staging_bundle))

    target = _bundle_dir()
    bat_path = staging_parent.with_suffix(".bat")
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        ":wait",
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
        "if %ERRORLEVEL% equ 0 (",
        "    timeout /t 1 >nul",
        "    goto wait",
        ")",
        "set /a tries=0",
        ":replace",
        "set /a tries+=1",
        "if %tries% gtr 30 goto giveup",
        f'rmdir /s /q "{target}"',
        f'if exist "{target}" (',
        "    timeout /t 1 >nul",
        "    goto replace",
        ")",
        f'move /y "{staging_bundle}" "{target}" >nul',
        f'if not exist "{target}\\ccprofile.exe" (',
        "    timeout /t 2 >nul",
        "    goto replace",
        ")",
        "goto done",
        ":giveup",
        f'echo ccprofile update failed after %tries% attempts > "{staging_parent}\\UPDATE_FAILED.txt"',
        "exit /b 1",
        ":done",
        f'rmdir /s /q "{staging_parent}"',
        'del "%~f0"',
    ]
    bat_path.write_text("\r\n".join(lines), encoding="utf-8")

    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
        subprocess, "DETACHED_PROCESS", 0
    )
    subprocess.Popen(
        ["cmd", "/c", "start", "/b", str(bat_path)],
        creationflags=creationflags,
        close_fds=True,
    )


def _load_check_cache():
    try:
        return json.loads(UPDATE_CHECK_FILE.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_check_cache(cache):
    try:
        UPDATE_CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
        UPDATE_CHECK_FILE.write_text(
            json.dumps(cache, ensure_ascii=False), "utf-8"
        )
    except OSError:
        pass


def maybe_check_on_launch():
    """Silently check for a newer release at most once per interval; hint on stderr."""
    if os.environ.get("CCPROFILE_NO_UPDATE_CHECK") == "1":
        return
    if not is_frozen():
        return

    cache = _load_check_cache()
    now = int(time.time())
    if should_check_now(cache, now):
        try:
            release = fetch_latest_release()
            cache["last_check_ts"] = now
            cache["latest_known"] = release["version"]
            _save_check_cache(cache)
        except UpdateError:
            return

    latest = cache.get("latest_known")
    if latest and is_newer(latest, VERSION):
        print(t("update.launch_hint", version=latest), file=sys.stderr)


def cmd_update(args):
    """Check for a newer release and update the installed bundle."""
    check = getattr(args, "check", False)
    yes = getattr(args, "yes", False)
    force = getattr(args, "force", False)
    prerelease = getattr(args, "prerelease", False)

    print(t("update.checking"))
    try:
        release = fetch_latest_release()
    except UpdateError as e:
        print(str(e))
        return

    latest = release["version"]
    print(kv(t("update.current"), VERSION))
    print(kv(t("update.latest"), latest))

    newer = is_newer(latest, VERSION, include_prerelease=prerelease)
    if not newer and not force:
        print(t("update.up_to_date"))
        return

    if newer:
        print(f"{GREEN}{t('update.new_available')}{RESET}")

    body = (release.get("body") or "").strip()
    if body:
        print(f"{BOLD}{t('update.changelog')}{RESET}")
        for line in body.splitlines():
            print(f"  {line}")

    if check:
        return

    if not yes:
        if not confirm_action(t("update.confirm", version=latest), default_yes=True):
            print(t("update.canceled"))
            return

    if not is_frozen():
        print(t("update.err_not_frozen"))
        return

    try:
        asset_name = platform_asset()
    except UpdateError as e:
        print(str(e))
        return

    asset_url = release["assets"].get(asset_name)
    if not asset_url:
        asset_url = f"https://github.com/{GITHUB_REPO}/releases/latest/download/{asset_name}"
    checksums_url = release["assets"].get(
        "SHA256SUMS"
    ) or f"https://github.com/{GITHUB_REPO}/releases/latest/download/SHA256SUMS"

    tmpdir = Path(tempfile.mkdtemp(prefix="ccprofile-update-"))
    new_bundle = None
    try:
        asset_path = tmpdir / asset_name
        sums_path = tmpdir / "SHA256SUMS"
        print(t("update.downloading", asset=asset_name))
        download_to(asset_url, asset_path)
        download_to(checksums_url, sums_path)
        print(t("update.verifying"))
        expected = expected_sha256(asset_name, sums_path.read_text("utf-8"))
        if not expected:
            print(t("update.err_checksum_missing"))
            return
        if not verify_sha256(asset_path, expected):
            print(t("update.err_checksum"))
            return
        print(t("update.extracting"))
        new_bundle = extract_bundle(asset_path, tmpdir / "extracted")
    except UpdateError as e:
        print(str(e))
        shutil.rmtree(tmpdir, ignore_errors=True)
        return

    try:
        if sys.platform == "win32":
            replace_bundle_windows(new_bundle)
            print(t("update.success_windows"))
        else:
            replace_bundle_unix(new_bundle)
            print(t("update.success_unix", version=latest))
    except UpdateError as e:
        print(str(e))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
