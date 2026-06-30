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
import threading
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
    UPDATE_REVERIFY_INTERVAL,
    UPDATE_USER_AGENT,
    VERSION,
)
from .display import BOLD, GREEN, RESET, kv
from .i18n import t
from .storage import atomic_write_text
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


def _pre_ident_key(ident):
    """Sort key for one dot-separated pre-release identifier (SemVer 11).

    Numeric identifiers (all digits) compare numerically and rank below
    alphanumeric ones; alphanumeric identifiers compare in ASCII order.
    isascii() guards int() against non-ASCII digit characters (superscripts,
    other scripts) whose str.isdigit() is also True.
    """
    if ident.isascii() and ident.isdigit():
        return (0, int(ident), "")
    return (1, 0, ident)


def _version_key(parsed):
    major, minor, patch, pre = parsed
    # A release (pre is None) sorts after any prerelease of the same x.y.z.
    # Pre-release precedence follows SemVer 11: compare dot-separated
    # identifiers left to right, numeric ones numerically; when all preceding
    # identifiers are equal, a shorter identifier list ranks lower.
    idents = [] if not pre else [_pre_ident_key(i) for i in pre.split(".")]
    return (major, minor, patch, 1 if not pre else 0, idents)


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
    """Return the expected SHA256 hex for `asset_name` parsed from SHA256SUMS text.

    Accepts both text mode (`<hash>  <asset>`) and binary mode (`<hash> *<asset>`
    as emitted by `sha256sum -b`).
    """
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            name = parts[-1]
            if name.startswith("*"):  # binary-mode marker
                name = name[1:]
            if name == asset_name:
                return parts[0].lower()
    return None


def should_check_now(cache, now_ts, interval=UPDATE_CHECK_INTERVAL,
                     reverify_interval=UPDATE_REVERIFY_INTERVAL):
    """Return True if a new network check is allowed.

    Re-checks are throttled to ``interval`` (default 24h) so we don't hammer
    GitHub. Exception: when the cache already advertises a version newer than
    the running one, re-verify on the much shorter ``reverify_interval`` so a
    release that was deleted or superseded (e.g. a throwaway test release)
    stops producing a phantom "new version available" hint within an hour
    instead of waiting out the full 24h window.
    """
    last = cache.get("last_check_ts")
    if last is None:
        return True
    latest = cache.get("latest_known")
    if latest:
        try:
            pending = is_newer(latest, VERSION)
        except ValueError:
            pending = False  # cached value not a parseable version: normal throttle
        if pending:
            return now_ts - last >= reverify_interval
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
        # GitHub signals rate limiting with 429, or 403 only when the rate-limit
        # budget is actually exhausted (X-RateLimit-Remaining: 0). Other 403s
        # (geographic blocks, etc.) are reported as generic network errors so we
        # don't mislead the user into "try again later".
        remaining = e.headers.get("X-RateLimit-Remaining") if e.headers else None
        if e.code == 429 or (e.code == 403 and remaining == "0"):
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


def _release_from_payload(data):
    """Convert one GitHub release API object into a release dict."""
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


def fetch_latest_release(include_prerelease=False):
    """Return the latest release info.

    By default this queries the stable /releases/latest endpoint, which
    excludes pre-releases. When include_prerelease is True it lists all
    releases and returns the highest version, including pre-releases, so
    'ccprofile update --prerelease' can reach a newest build that is only
    published as a pre-release. Falls back to the release-tag redirect on
    rate limit (stable path only).
    """
    if include_prerelease:
        return _fetch_newest_release_any()

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        data = _http_get_json(api_url)
    except RateLimitedError:
        redirect_url = f"https://github.com/{GITHUB_REPO}/releases/latest"
        try:
            tag = _http_head_location(redirect_url)
        except UpdateError:
            raise RateLimitedError(t("update.err_rate_limited"))
        # The redirect exposes only the tag; reuse the shared payload builder so
        # the v-stripping and dict shape stay in one place.
        return _release_from_payload({"tag_name": tag, "body": "", "assets": []})

    return _release_from_payload(data)


def _fetch_newest_release_any():
    """Return the newest release (incl. pre-releases) by scanning /releases.

    /releases/latest excludes pre-releases, so to honor --prerelease we list
    releases and pick the highest version ourselves. Only the first page
    (per_page=30) is scanned, which comfortably covers this project's release
    history. RateLimitedError propagates unchanged: no redirect fallback can
    honor pre-releases.
    """
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=30"
    data = _http_get_json(api_url)
    if not isinstance(data, list):
        raise UpdateError(t("update.err_network"))
    best = None
    best_key = None
    for item in data:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        try:
            key = _version_key(parse_version(item.get("tag_name", "")))
        except ValueError:
            continue  # skip tags we cannot rank (e.g. 'nightly')
        if best_key is None or key > best_key:
            best_key = key
            best = item
    if best is None:
        raise UpdateError(t("update.err_network"))
    return _release_from_payload(best)


def _assert_inside(path, base):
    """Raise UpdateError if `path` does not resolve within `base`."""
    try:
        path.relative_to(base)
    except ValueError:
        raise UpdateError(t("update.err_extract"))


def _safe_tar_extract(tar, dest_dir):
    """Extract a tar rejecting path-traversal members and escaping links."""
    dest = Path(dest_dir).resolve()
    for member in tar.getmembers():
        member_dest = (dest / member.name).resolve()
        _assert_inside(member_dest, dest)
        if member.issym() or member.islnk():
            # A link whose name is inside dest but whose target escapes must be
            # rejected too. Hardlink targets are archive-relative (under dest);
            # symlink targets resolve relative to the member's own directory.
            base = dest if member.islnk() else member_dest.parent
            link_dest = (base / member.linkname).resolve()
            _assert_inside(link_dest, dest)
    tar.extractall(dest)


def _safe_zip_extract(zf, dest_dir):
    """Extract a zip rejecting path-traversal members."""
    dest = Path(dest_dir).resolve()
    for member in zf.infolist():
        member_dest = (dest / member.filename).resolve()
        _assert_inside(member_dest, dest)
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
        try:
            shutil.move(str(backup), str(target))
        except OSError:
            pass  # best-effort restore; the backup remains as <target>.old
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
    # Paths are interpolated inside double-quoted cmd arguments. Inside quotes
    # only `%` is dangerous (env-var expansion); Windows paths never contain `"`,
    # and ^&|<>() are literal there. Double `%` so a path containing a literal
    # percent can't expand another variable.
    esc_target = str(target).replace("%", "%%")
    esc_staging_parent = str(staging_parent).replace("%", "%%")
    esc_staging_bundle = str(staging_bundle).replace("%", "%%")
    failed_marker = "%TEMP%\\ccprofile-update-failed.txt"
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        # Wait for the updater PID to exit. Bounded (60s) so a recycled PID, or
        # a process that refuses to die, cannot pin this watcher forever.
        "set /a waits=0",
        "set /a tries=0",
        ":wait",
        "set /a waits+=1",
        "if %waits% gtr 60 goto giveup",
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
        "if %ERRORLEVEL% equ 0 (",
        "    timeout /t 1 >nul",
        "    goto wait",
        ")",
        # Replace the target dir. `move`'s ERRORLEVEL is the real success signal.
        # The post-move existence probe deliberately does NOT branch back to
        # :replace: staging is consumed by a successful move, so re-entering
        # :replace would rmdir the just-installed bundle and then fail to move a
        # now-missing source — bricking the install. After a successful move we
        # only wait for the FS, then accept.
        ":replace",
        "set /a tries+=1",
        "if %tries% gtr 30 goto giveup",
        f'if exist "{esc_target}" rmdir /s /q "{esc_target}"',
        f'if exist "{esc_target}" (',
        "    timeout /t 1 >nul",
        "    goto replace",
        ")",
        f'move /y "{esc_staging_bundle}" "{esc_target}" >nul',
        "if errorlevel 1 (",
        "    timeout /t 1 >nul",
        "    goto replace",
        ")",
        f'if not exist "{esc_target}\\ccprofile.exe" timeout /t 2 >nul',
        "goto done",
        ":giveup",
        f'echo ccprofile update failed after %tries% replacements, %waits% waits > "{failed_marker}"',
        f'rmdir /s /q "{esc_staging_parent}"',
        'del "%~f0"',
        "exit /b 1",
        ":done",
        f'rmdir /s /q "{esc_staging_parent}"',
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
        atomic_write_text(UPDATE_CHECK_FILE, json.dumps(cache, ensure_ascii=False))
    except OSError:
        pass


# True after this process has replaced its bundle via cmd_update. emit_launch_hint()
# consults it to stay silent: the in-memory VERSION is then stale relative to the
# just-installed bundle, so a hint would misleadingly advertise the version we
# just updated to.
_updated_this_run = False

# Set once maybe_check_on_launch() has spawned the background fetch, so repeated
# calls in the same process (menu path, then exit) only start one worker.
_launch_check_started = False

# Newest version discovered by the background launch-check worker (or None until
# it finishes). Read by emit_launch_hint() at process exit.
_bg_latest = None


def maybe_check_on_launch():
    """Kick off a non-blocking background update check (once per process).

    The throttled network fetch runs on a daemon thread so it never delays the
    CLI; the resulting hint is printed by emit_launch_hint() at process exit,
    when the terminal is quiet. See _launch_check_worker for the fetch itself.
    """
    global _launch_check_started
    if _launch_check_started:
        return
    if os.environ.get("CCPROFILE_NO_UPDATE_CHECK") == "1":
        return
    if not is_frozen():
        return
    _launch_check_started = True
    threading.Thread(target=_launch_check_worker, daemon=True).start()


def _launch_check_worker():
    """Throttled background fetch; caches the newest known version. Never raises."""
    global _bg_latest
    try:
        cache = _load_check_cache()
        now = int(time.time())
        if should_check_now(cache, now):
            try:
                release = fetch_latest_release()
                cache["last_check_ts"] = now
                cache["latest_known"] = release["version"]
                _save_check_cache(cache)
            except UpdateError:
                pass  # transient failure: fall through to the cached hint below
        _bg_latest = cache.get("latest_known")
    except Exception:
        pass  # a background update check must never disturb the CLI


def emit_launch_hint():
    """Print the one-line update hint if a newer release is known.

    Uses the background worker's result on the happy path (no I/O); falls back
    to the on-disk cache if the worker has not finished yet. Respects
    _updated_this_run so a just-completed self-update stays silent.
    """
    if _updated_this_run:
        return
    latest = _bg_latest
    if latest is None:
        try:
            latest = _load_check_cache().get("latest_known")
        except Exception:
            return
    if latest and is_newer(latest, VERSION):
        print(t("update.launch_hint", version=latest), file=sys.stderr)


def cmd_update(args):
    """Check for a newer release and update the installed bundle."""
    global _updated_this_run
    check = getattr(args, "check", False)
    yes = getattr(args, "yes", False)
    force = getattr(args, "force", False)
    prerelease = getattr(args, "prerelease", False)

    print(t("update.checking"))
    try:
        release = fetch_latest_release(include_prerelease=prerelease)
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
    if force and is_newer(VERSION, latest, include_prerelease=prerelease):
        # --force reinstalls the same version; it must never downgrade.
        print(t("update.err_downgrade", current=VERSION, latest=latest))
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

    # Download from this specific release's tag so a pre-release asset is
    # fetched by its own tag rather than always the latest stable.
    asset_url = release["assets"].get(asset_name)
    if not asset_url:
        if release["assets"]:
            # The API listed assets but ours isn't among them — naming changed.
            # Don't guess a URL that would 404 as a generic network error.
            print(t("update.err_asset_missing", asset=asset_name))
            return
        # Rate-limit fallback: assets unknown, construct by tag.
        asset_url = f"https://github.com/{GITHUB_REPO}/releases/download/{release['tag']}/{asset_name}"
    checksums_url = release["assets"].get(
        "SHA256SUMS"
    ) or f"https://github.com/{GITHUB_REPO}/releases/download/{release['tag']}/SHA256SUMS"

    tmpdir = Path(tempfile.mkdtemp(prefix="ccprofile-update-"))
    try:
        asset_path = tmpdir / asset_name
        sums_path = tmpdir / "SHA256SUMS"
        print(t("update.downloading", asset=asset_name))
        _download_pair(asset_url, asset_path, checksums_url, sums_path)
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
        replace_bundle(new_bundle, version=latest)
        _updated_this_run = True
    except UpdateError as e:
        print(str(e))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _download_pair(asset_url, asset_path, checksums_url, sums_path):
    """Download the asset and its checksums concurrently (two independent fetches)."""
    errors = []

    def _fetch(url, dest):
        try:
            download_to(url, dest)
        except UpdateError as e:
            errors.append(e)

    th = threading.Thread(target=_fetch, args=(checksums_url, sums_path))
    th.start()
    _fetch(asset_url, asset_path)
    th.join()
    if errors:
        raise errors[0]


def replace_bundle(new_bundle_dir, *, version):
    """Replace the installed bundle and print a platform-appropriate success line.

    Centralizes the platform -> replace-strategy decision (mirroring
    platform_asset) so callers don't each re-implement the win32/unix split.
    """
    if sys.platform == "win32":
        replace_bundle_windows(new_bundle_dir)
        print(t("update.success_windows"))
    else:
        replace_bundle_unix(new_bundle_dir)
        print(t("update.success_unix", version=version))
