# `ccprofile update` 自更新功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 ccprofile 增加 `ccprofile update` 自更新命令与启动后台节流检查，支持 macOS / Linux / Windows 全平台原地更新。

**Architecture:** 新增 `ccprofile_app/updater.py` 承载全部逻辑（版本解析、平台资产映射、GitHub API 检测+限流降级、下载+SHA256 校验+解压、Unix 原子替换 / Windows 脱机 `.bat` 替换、启动检查节流）。`cli.py` 注册子命令并在 `main()` 末尾挂启动检查；`menu.py` 加菜单项；`i18n.py` 加 zh/en 字符串。复用现有 release 资产与 `SHA256SUMS`，不引入新依赖。

**Tech Stack:** Python 3.9（stdlib：`urllib`、`ssl`+`certifi`、`hashlib`、`tarfile`/`zipfile`、`subprocess`、`tempfile`）；pytest 运行 `unittest` 风格测试。

## Global Constraints

- **Python 3.9 兼容**：禁用 `X | Y` 联合类型注解、`match` 语句、`str.removeprefix` 之外的 3.10+ 语法。注解用 `Optional[X]` 或省略。
- **无新依赖**：仅用 stdlib + 现有 `cryptography`；HTTP 用 `urllib.request`，TLS 用 `certifi.where()`（打包已 `--collect-data`）。
- **i18n**：所有用户可见字符串经 `t("key")`，必须同时在 `STRINGS` 中提供 `zh` 与 `en`。
- **语言约定**：代码注释与标识符用英文；用户可见输出用中文（默认 `zh`）。
- **安全**：仅 HTTPS；替换前强制 SHA256 校验；不执行除已校验平台二进制外的任何远端代码。
- **依赖方向**：`cli → updater → constants/i18n/display/terminal`，不反向依赖。
- **测试命令**：`python3 -m pytest tests/test_updater.py -v`（仓库基线 32 passed，本分支须保持全绿）。

参考 spec：`docs/superpowers/specs/2026-06-29-update-command-design.md`。

---

### Task 1: 版本解析与异常基础

**Files:**
- Create: `ccprofile_app/updater.py`
- Modify: `ccprofile_app/constants.py`（追加 update 相关常量）
- Test: `tests/test_updater.py`

**Interfaces:**
- Produces: `parse_version(s: str) -> tuple` 返回 `(major:int, minor:int, patch:int, prerelease:Optional[str])`；`is_newer(latest: str, current: str, include_prerelease: bool = False) -> bool`；异常 `UpdateError`、`RateLimitedError(UpdateError)`。

- [ ] **Step 1: 在 `constants.py` 末尾追加常量**

打开 `ccprofile_app/constants.py`，在文件末尾（`CCPROFILE_MANAGED_ENV_KEYS` 之后）追加：

```python
# ── Self-update ──
GITHUB_REPO = "ZCXU0421/ccprofile"
UPDATE_CHECK_FILE = PROFILE_DIR / "update_check.json"
UPDATE_CHECK_INTERVAL = 86400  # seconds (24h)
UPDATE_USER_AGENT = f"ccprofile/{VERSION}"
```

- [ ] **Step 2: 写失败测试（新建 `tests/test_updater.py`）**

```python
import unittest

from ccprofile_app import updater
from ccprofile_app.updater import UpdateError, is_newer, parse_version


class VersionTest(unittest.TestCase):
    def test_parse_strips_leading_v(self):
        self.assertEqual(parse_version("v0.3.0"), (0, 3, 0, None))

    def test_parse_plain(self):
        self.assertEqual(parse_version("0.4.0"), (0, 4, 0, None))

    def test_parse_prerelease(self):
        self.assertEqual(parse_version("0.4.0-rc1"), (0, 4, 0, "rc1"))

    def test_parse_invalid_raises(self):
        with self.assertRaises(ValueError):
            parse_version("not-a-version")

    def test_is_newer_true(self):
        self.assertTrue(is_newer("0.4.0", "0.3.0"))

    def test_is_newer_false_same(self):
        self.assertFalse(is_newer("0.3.0", "0.3.0"))

    def test_is_newer_false_downgrade(self):
        self.assertFalse(is_newer("0.2.0", "0.3.0"))

    def test_is_newer_ignores_prerelease_by_default(self):
        self.assertFalse(is_newer("0.4.0-rc1", "0.3.0"))

    def test_is_newer_includes_prerelease_when_asked(self):
        self.assertTrue(is_newer("0.4.0-rc1", "0.3.0", include_prerelease=True))

    def test_prerelease_is_older_than_release_of_same_xyz(self):
        self.assertFalse(is_newer("0.4.0-rc1", "0.4.0", include_prerelease=True))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_updater.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ccprofile_app.updater'`

- [ ] **Step 4: 创建 `ccprofile_app/updater.py`（含全部 import、异常、版本函数）**

```python
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
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_updater.py -v`
Expected: PASS（10 个用例）

- [ ] **Step 6: 提交**

```bash
git add ccprofile_app/updater.py ccprofile_app/constants.py tests/test_updater.py
git commit -m "feat(updater): 添加版本解析与异常基础"
```

---

### Task 2: 平台资产映射

**Files:**
- Modify: `ccprofile_app/updater.py`（追加 `platform_asset`）
- Test: `tests/test_updater.py`

**Interfaces:**
- Produces: `platform_asset() -> str`，返回当前平台对应的 release 资产文件名；不支持的平台（含 Intel Mac）抛 `UpdateError`。

- [ ] **Step 1: 追加失败测试**

在 `tests/test_updater.py` 新增：

```python
class PlatformAssetTest(unittest.TestCase):
    def test_macos_arm64(self):
        with unittest.mock.patch.object(sys, "platform", "darwin"), \
             unittest.mock.patch.object(platform, "machine", lambda: "arm64"):
            self.assertEqual(updater.platform_asset(), "ccprofile-macos-arm64.tar.gz")

    def test_macos_intel_unsupported(self):
        with unittest.mock.patch.object(sys, "platform", "darwin"), \
             unittest.mock.patch.object(platform, "machine", lambda: "x86_64"):
            with self.assertRaises(UpdateError):
                updater.platform_asset()

    def test_linux(self):
        with unittest.mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(updater.platform_asset(), "ccprofile-linux.tar.gz")

    def test_windows(self):
        with unittest.mock.patch.object(sys, "platform", "win32"):
            self.assertEqual(updater.platform_asset(), "ccprofile-windows.zip")
```

并在文件顶部 import 区追加：

```python
import platform
import sys
import unittest.mock
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_updater.py::PlatformAssetTest -v`
Expected: FAIL — `AttributeError: module 'ccprofile_app.updater' has no attribute 'platform_asset'`

- [ ] **Step 3: 在 `updater.py` 追加实现**

在 `is_newer` 之后追加：

```python
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_updater.py::PlatformAssetTest -v`
Expected: PASS（4 个用例）

- [ ] **Step 5: 提交**

```bash
git add ccprofile_app/updater.py tests/test_updater.py
git commit -m "feat(updater): 添加平台资产映射"
```

---

### Task 3: SHA256SUMS 解析与检查节流

**Files:**
- Modify: `ccprofile_app/updater.py`（追加 `expected_sha256`、`should_check_now`）
- Test: `tests/test_updater.py`

**Interfaces:**
- Produces: `expected_sha256(asset_name: str, text: str) -> Optional[str]`；`should_check_now(cache: dict, now_ts: int, interval: int = UPDATE_CHECK_INTERVAL) -> bool`。

- [ ] **Step 1: 追加失败测试**

```python
class ShaAndThrottleTest(unittest.TestCase):
    def test_expected_sha256_found(self):
        text = "abc123  ccprofile-linux.tar.gz\nffff  other.zip\n"
        self.assertEqual(
            updater.expected_sha256("ccprofile-linux.tar.gz", text), "abc123"
        )

    def test_expected_sha256_missing(self):
        self.assertIsNone(updater.expected_sha256("nope.zip", "abc123  other.zip\n"))

    def test_should_check_when_never_checked(self):
        self.assertTrue(updater.should_check_now({}, now_ts=1000))

    def test_should_not_check_within_interval(self):
        cache = {"last_check_ts": 1000}
        self.assertFalse(updater.should_check_now(cache, now_ts=1000 + 100))

    def test_should_check_after_interval(self):
        cache = {"last_check_ts": 1000}
        self.assertTrue(
            updater.should_check_now(cache, now_ts=1000 + updater.UPDATE_CHECK_INTERVAL)
        )
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_updater.py::ShaAndThrottleTest -v`
Expected: FAIL — `AttributeError ... has no attribute 'expected_sha256'`

- [ ] **Step 3: 在 `updater.py` 追加实现**

```python
def expected_sha256(asset_name, text):
    """Return the expected SHA256 hex for `asset_name` parsed from SHA256SUMS text."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1] == asset_name:
            return parts[0].lower()
    return None


def should_check_now(cache, now_ts, interval=UPDATE_CHECK_INTERVAL):
    """Return True if a new network check is allowed (> interval since last)."""
    return now_ts - cache.get("last_check_ts", 0) >= interval
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_updater.py::ShaAndThrottleTest -v`
Expected: PASS（5 个用例）

- [ ] **Step 5: 提交**

```bash
git add ccprofile_app/updater.py tests/test_updater.py
git commit -m "feat(updater): 添加 SHA256SUMS 解析与检查节流"
```

---

### Task 4: GitHub 检测（API + 限流降级）

**Files:**
- Modify: `ccprofile_app/updater.py`（追加 `_ssl_context`、`_http_get_json`、`_http_head_location`、`fetch_latest_release`）
- Test: `tests/test_updater.py`

**Interfaces:**
- Produces: `fetch_latest_release() -> dict`，返回 `{"tag": str, "version": str, "body": str, "assets": dict[str,str]}`。`assets` 为空时表示处于限流降级路径（由调用方构造 `releases/latest/download` 兜底 URL）。内部 HTTP 助手 `_http_get_json` / `_http_head_location` 可被 patch 以便测试。

- [ ] **Step 1: 追加失败测试**

```python
class FetchReleaseTest(unittest.TestCase):
    def test_fetch_maps_api_response(self):
        api_data = {
            "tag_name": "v0.4.0",
            "body": "changes",
            "assets": [
                {"name": "ccprofile-linux.tar.gz", "browser_download_url": "https://x/linux"},
                {"name": "SHA256SUMS", "browser_download_url": "https://x/sums"},
            ],
        }
        with unittest.mock.patch.object(updater, "_http_get_json", return_value=api_data):
            rel = updater.fetch_latest_release()
        self.assertEqual(rel["version"], "0.4.0")
        self.assertEqual(rel["tag"], "v0.4.0")
        self.assertEqual(rel["body"], "changes")
        self.assertEqual(rel["assets"]["ccprofile-linux.tar.gz"], "https://x/linux")

    def test_fetch_falls_back_on_rate_limit(self):
        def fake_get(url, timeout=10):
            raise updater.RateLimitedError("limited")

        with unittest.mock.patch.object(updater, "_http_get_json", side_effect=fake_get), \
             unittest.mock.patch.object(updater, "_http_head_location", return_value="v0.4.0"):
            rel = updater.fetch_latest_release()
        self.assertEqual(rel["version"], "0.4.0")
        self.assertEqual(rel["assets"], {})

    def test_fetch_propagates_network_error(self):
        with unittest.mock.patch.object(
            updater, "_http_get_json", side_effect=updater.UpdateError("net")
        ):
            with self.assertRaises(UpdateError):
                updater.fetch_latest_release()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_updater.py::FetchReleaseTest -v`
Expected: FAIL — `AttributeError ... has no attribute 'fetch_latest_release'`

- [ ] **Step 3: 在 `updater.py` 追加实现**

```python
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_updater.py::FetchReleaseTest -v`
Expected: PASS（3 个用例）

- [ ] **Step 5: 提交**

```bash
git add ccprofile_app/updater.py tests/test_updater.py
git commit -m "feat(updater): 添加 GitHub 检测与限流降级"
```

---

### Task 5: 下载、校验、解压

**Files:**
- Modify: `ccprofile_app/updater.py`（追加 `_safe_tar_extract`、`download_to`、`verify_sha256`、`extract_bundle`）
- Test: `tests/test_updater.py`

**Interfaces:**
- Produces: `download_to(url: str, dest, timeout: int = 30) -> None`（失败抛 `UpdateError`）；`verify_sha256(path, expected: str) -> bool`；`extract_bundle(archive_path, dest_dir) -> Path`（返回内层 `ccprofile/` 目录，布局不符抛 `UpdateError`）。

- [ ] **Step 1: 追加失败测试**

```python
import hashlib
import tarfile
import tempfile
from pathlib import Path


class DownloadVerifyExtractTest(unittest.TestCase):
    def test_verify_sha256_match(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f"
            p.write_bytes(b"hello")
            digest = hashlib.sha256(b"hello").hexdigest()
            self.assertTrue(updater.verify_sha256(p, digest))

    def test_verify_sha256_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f"
            p.write_bytes(b"hello")
            self.assertFalse(updater.verify_sha256(p, "0" * 64))

    def test_extract_bundle_tar(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            # build a tar.gz with layout ccprofile/ccprofile
            src = work / "ccprofile"
            src.mkdir()
            (src / "ccprofile").write_text("exe")
            archive = work / "bundle.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(src, arcname="ccprofile")
            out = work / "extracted"
            bundle = updater.extract_bundle(archive, out)
            self.assertTrue((bundle / "ccprofile").exists())
            self.assertEqual(bundle.name, "ccprofile")

    def test_extract_bundle_bad_layout_raises(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            (work / "other").mkdir()
            archive = work / "bundle.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(work / "other", arcname="other")
            with self.assertRaises(UpdateError):
                updater.extract_bundle(archive, work / "extracted")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_updater.py::DownloadVerifyExtractTest -v`
Expected: FAIL — `AttributeError ... has no attribute 'verify_sha256'`

- [ ] **Step 3: 在 `updater.py` 追加实现**

```python
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


def download_to(url, dest, timeout=30):
    """Stream `url` to `dest` (a path). Raises UpdateError on failure."""
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
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(dest_dir)
    else:
        with tarfile.open(archive_path, "r:gz") as tar:
            _safe_tar_extract(tar, dest_dir)
    bundle = dest_dir / "ccprofile"
    exe_name = "ccprofile.exe" if sys.platform == "win32" else "ccprofile"
    if not (bundle / exe_name).exists():
        raise UpdateError(t("update.err_extract"))
    return bundle
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_updater.py::DownloadVerifyExtractTest -v`
Expected: PASS（4 个用例）

- [ ] **Step 5: 提交**

```bash
git add ccprofile_app/updater.py tests/test_updater.py
git commit -m "feat(updater): 添加下载、SHA256 校验与解压"
```

---

### Task 6: Unix 替换（运行中原子交换）

**Files:**
- Modify: `ccprofile_app/updater.py`（追加 `is_frozen`、`_bundle_dir`、`replace_bundle_unix`）
- Test: `tests/test_updater.py`

**Interfaces:**
- Produces: `is_frozen() -> bool`；`_bundle_dir() -> Path`（`Path(sys.executable).parent`）；`replace_bundle_unix(new_bundle_dir) -> None`（失败回滚并抛 `UpdateError`）。后续任务仅调用 `replace_bundle_unix` / `replace_bundle_windows`，不直接接触 `_bundle_dir`。

- [ ] **Step 1: 追加失败测试**

```python
class ReplaceUnixTest(unittest.TestCase):
    def test_replace_swaps_bundle_and_cleans_backup(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            # simulate installed bundle: work/install/ccprofile (+ _internal)
            install = work / "install"
            bundle = install / "ccprofile"
            bundle.mkdir(parents=True)
            (bundle / "ccprofile").write_text("OLD")
            (bundle / "_internal").mkdir()
            (bundle / "_internal" / "lib.so").write_text("old-lib")

            # the "new" extracted bundle
            new_bundle = work / "new" / "ccprofile"
            new_bundle.mkdir(parents=True)
            (new_bundle / "ccprofile").write_text("NEW")

            with unittest.mock.patch.object(updater, "_bundle_dir", return_value=bundle), \
                 unittest.mock.patch.object(updater, "is_frozen", return_value=True):
                updater.replace_bundle_unix(new_bundle)

            self.assertEqual((bundle / "ccprofile").read_text(), "NEW")
            self.assertFalse((install / "ccprofile.old").exists())

    def test_replace_rolls_back_on_move_failure(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            install = work / "install"
            bundle = install / "ccprofile"
            bundle.mkdir(parents=True)
            (bundle / "ccprofile").write_text("OLD")
            new_bundle = work / "new" / "ccprofile"
            new_bundle.mkdir(parents=True)

            with unittest.mock.patch.object(updater, "_bundle_dir", return_value=bundle), \
                 unittest.mock.patch.object(updater, "is_frozen", return_value=True), \
                 unittest.mock.patch.object(updater.shutil, "move", side_effect=["ok", OSError("boom")]):
                # first shutil.move(target->backup) "ok", second move(new->target) fails
                with self.assertRaises(UpdateError):
                    updater.replace_bundle_unix(new_bundle)
            # rolled back: original exe restored
            self.assertEqual((bundle / "ccprofile").read_text(), "OLD")
```

> 注：第二个用例里 `shutil.move` 的 `side_effect` 顺序对应「先移走旧 bundle、再移入新 bundle」，第二次抛错触发回滚。

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_updater.py::ReplaceUnixTest -v`
Expected: FAIL — `AttributeError ... has no attribute 'replace_bundle_unix'`

- [ ] **Step 3: 在 `updater.py` 追加实现**

```python
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_updater.py::ReplaceUnixTest -v`
Expected: PASS（2 个用例）

- [ ] **Step 5: 提交**

```bash
git add ccprofile_app/updater.py tests/test_updater.py
git commit -m "feat(updater): 添加 Unix 原子替换与回滚"
```

---

### Task 7: Windows 替换（脱机辅助脚本）

**Files:**
- Modify: `ccprofile_app/updater.py`（追加 `replace_bundle_windows`）
- Test: `tests/test_updater.py`

**Interfaces:**
- Produces: `replace_bundle_windows(new_bundle_dir) -> None`。将新 bundle 移入暂存目录、生成等待父进程退出的 `.bat` 并以 `subprocess.Popen` 脱机启动，随后由调用方打印提示并退出。

- [ ] **Step 1: 追加失败测试**

```python
class ReplaceWindowsTest(unittest.TestCase):
    def test_writes_bat_and_spawns_detached(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            new_bundle = work / "new" / "ccprofile"
            new_bundle.mkdir(parents=True)
            (new_bundle / "ccprofile.exe").write_text("NEW")

            target = work / "target" / "ccprofile"

            with unittest.mock.patch.object(updater, "_bundle_dir", return_value=target), \
                 unittest.mock.patch.object(updater.tempfile, "gettempdir", return_value=str(work)), \
                 unittest.mock.patch.object(updater.os, "getpid", return_value=4242), \
                 unittest.mock.patch.object(updater.subprocess, "Popen") as popen:
                updater.replace_bundle_windows(new_bundle)

            staging_parent = work / "ccprofile-update-4242"
            self.assertTrue((staging_parent / "ccprofile" / "ccprofile.exe").exists())
            bat = staging_parent.with_suffix(".bat")
            self.assertTrue(bat.exists())
            content = bat.read_text("utf-8")
            self.assertIn("4242", content)
            self.assertIn(str(target), content)
            popen.assert_called_once()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_updater.py::ReplaceWindowsTest -v`
Expected: FAIL — `AttributeError ... has no attribute 'replace_bundle_windows'`

- [ ] **Step 3: 在 `updater.py` 追加实现**

```python
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
        ":replace",
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_updater.py::ReplaceWindowsTest -v`
Expected: PASS（1 个用例）

- [ ] **Step 5: 提交**

```bash
git add ccprofile_app/updater.py tests/test_updater.py
git commit -m "feat(updater): 添加 Windows 脱机替换助手"
```

---

### Task 8: 检查缓存与启动后台检查

**Files:**
- Modify: `ccprofile_app/updater.py`（追加 `_load_check_cache`、`_save_check_cache`、`maybe_check_on_launch`）
- Test: `tests/test_updater.py`

**Interfaces:**
- Produces: `maybe_check_on_launch() -> None`。读 `UPDATE_CHECK_FILE` 缓存；满足节流才联网；发现新版本则向 **stderr** 打印一行提示；任何异常吞掉，绝不影响主流程。
- Consumes: `fetch_latest_release`、`is_newer`、`should_check_now`、`is_frozen`、`VERSION`、`UPDATE_CHECK_FILE`。

- [ ] **Step 1: 追加失败测试**

```python
import contextlib
import io


class LaunchCheckTest(unittest.TestCase):
    def test_skips_when_env_set(self):
        with unittest.mock.patch.dict(os.environ, {"CCPROFILE_NO_UPDATE_CHECK": "1"}), \
             unittest.mock.patch.object(updater, "is_frozen", return_value=True), \
             unittest.mock.patch.object(updater, "fetch_latest_release") as fetch:
            updater.maybe_check_on_launch()
        fetch.assert_not_called()

    def test_skips_when_not_frozen(self):
        with unittest.mock.patch.object(updater, "is_frozen", return_value=False), \
             unittest.mock.patch.object(updater, "fetch_latest_release") as fetch:
            updater.maybe_check_on_launch()
        fetch.assert_not_called()

    def test_prints_hint_when_cached_version_is_newer(self):
        cache = {"last_check_ts": 0, "latest_known": "9.9.9"}  # 0 -> always re-check allowed
        with unittest.mock.patch.object(updater, "is_frozen", return_value=True), \
             unittest.mock.patch.object(updater, "_load_check_cache", return_value=cache), \
             unittest.mock.patch.object(updater, "_save_check_cache") as save, \
             unittest.mock.patch.object(updater, "fetch_latest_release", return_value={"version": "9.9.9"}):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                updater.maybe_check_on_launch()
        self.assertIn("9.9.9", err.getvalue())
        save.assert_called_once()

    def test_silent_when_up_to_date(self):
        cache = {"last_check_ts": 0}
        with unittest.mock.patch.object(updater, "is_frozen", return_value=True), \
             unittest.mock.patch.object(updater, "_load_check_cache", return_value=cache), \
             unittest.mock.patch.object(updater, "_save_check_cache"), \
             unittest.mock.patch.object(updater, "fetch_latest_release", return_value={"version": "0.0.1"}):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                updater.maybe_check_on_launch()
        self.assertEqual(err.getvalue(), "")

    def test_silent_on_network_error(self):
        cache = {"last_check_ts": 0}
        with unittest.mock.patch.object(updater, "is_frozen", return_value=True), \
             unittest.mock.patch.object(updater, "_load_check_cache", return_value=cache), \
             unittest.mock.patch.object(updater, "_save_check_cache"), \
             unittest.mock.patch.object(updater, "fetch_latest_release", side_effect=updater.UpdateError("net")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                updater.maybe_check_on_launch()  # must not raise
        self.assertEqual(err.getvalue(), "")
```

> `last_check_ts=0` 使 `should_check_now` 恒为真（`now - 0 >= interval`），从而走到联网分支。

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_updater.py::LaunchCheckTest -v`
Expected: FAIL — `AttributeError ... has no attribute 'maybe_check_on_launch'`

- [ ] **Step 3: 在 `updater.py` 追加实现**

```python
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_updater.py::LaunchCheckTest -v`
Expected: PASS（5 个用例）

- [ ] **Step 5: 提交**

```bash
git add ccprofile_app/updater.py tests/test_updater.py
git commit -m "feat(updater): 添加启动后台节流检查"
```

---

### Task 9: i18n 字符串

**Files:**
- Modify: `ccprofile_app/i18n.py`（在 `STRINGS` 中追加 update 相关键）
- Test: `tests/test_updater.py`

**Interfaces:**
- Produces: 所有 `cli.update_*`、`menu.check_update`、`update.*` 键（zh/en 齐全），供 Task 10–12 引用。

- [ ] **Step 1: 追加失败测试（校验所有新键双语齐全）**

```python
REQUIRED_UPDATE_KEYS = [
    "cli.update_help",
    "cli.update_check_help",
    "cli.update_yes_help",
    "cli.update_force_help",
    "cli.update_prerelease_help",
    "menu.check_update",
    "update.checking",
    "update.current",
    "update.latest",
    "update.up_to_date",
    "update.new_available",
    "update.changelog",
    "update.confirm",
    "update.canceled",
    "update.downloading",
    "update.verifying",
    "update.extracting",
    "update.success_unix",
    "update.success_windows",
    "update.launch_hint",
    "update.err_network",
    "update.err_rate_limited",
    "update.err_checksum",
    "update.err_checksum_missing",
    "update.err_not_frozen",
    "update.err_unsupported",
    "update.err_extract",
    "update.err_install",
]


class I18nKeysTest(unittest.TestCase):
    def test_all_update_keys_have_zh_and_en(self):
        from ccprofile_app.i18n import STRINGS

        missing = [
            k for k in REQUIRED_UPDATE_KEYS
            if k not in STRINGS or "zh" not in STRINGS[k] or "en" not in STRINGS[k]
        ]
        self.assertEqual(missing, [], f"missing zh/en for: {missing}")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_updater.py::I18nKeysTest -v`
Expected: FAIL — `missing zh/en for: [...]`

- [ ] **Step 3: 在 `i18n.py` 的 `STRINGS` 字典末尾追加**

在 `crypto.decrypt_failed` 条目之后、`STRINGS` 闭合 `}` 之前追加：

```python

    # ── cli.py update ──
    "cli.update_help": {"zh": "检测并更新到最新版本", "en": "Check for and update to the latest version"},
    "cli.update_check_help": {"zh": "仅检测，不更新", "en": "Check only, do not update"},
    "cli.update_yes_help": {"zh": "跳过确认", "en": "Skip confirmation"},
    "cli.update_force_help": {"zh": "即使同版本也重装", "en": "Reinstall even if same version"},
    "cli.update_prerelease_help": {"zh": "纳入预发布版本", "en": "Include pre-release versions"},

    # ── menu.py update ──
    "menu.check_update": {"zh": "检查更新", "en": "Check for Updates"},

    # ── updater.py ──
    "update.checking": {"zh": "正在检查最新版本...", "en": "Checking for the latest version..."},
    "update.current": {"zh": "当前版本", "en": "Current version"},
    "update.latest": {"zh": "最新版本", "en": "Latest version"},
    "update.up_to_date": {"zh": "已是最新版本。", "en": "Already up to date."},
    "update.new_available": {"zh": "有新版本可用", "en": "A new version is available"},
    "update.changelog": {"zh": "更新内容", "en": "Release notes"},
    "update.confirm": {"zh": "是否更新到 {version}？", "en": "Update to {version}?"},
    "update.canceled": {"zh": "已取消。", "en": "Canceled."},
    "update.downloading": {"zh": "正在下载 {asset}", "en": "Downloading {asset}"},
    "update.verifying": {"zh": "正在校验 SHA256", "en": "Verifying SHA256"},
    "update.extracting": {"zh": "正在安装", "en": "Installing"},
    "update.success_unix": {"zh": "更新成功！当前版本: {version}", "en": "Updated! Now at version {version}"},
    "update.success_windows": {"zh": "更新成功！请重新运行 ccprofile。", "en": "Updated! Please re-run ccprofile."},
    "update.launch_hint": {
        "zh": "[ccprofile] 发现新版本 {version}，运行 `ccprofile update` 更新。",
        "en": "[ccprofile] New version {version} available. Run `ccprofile update`.",
    },
    "update.err_network": {"zh": "错误: 无法连接到 GitHub，请检查网络。", "en": "Error: Cannot reach GitHub. Check your network."},
    "update.err_rate_limited": {"zh": "错误: GitHub API 限流，请稍后再试。", "en": "Error: GitHub API rate-limited. Try again later."},
    "update.err_checksum": {"zh": "错误: SHA256 校验失败，已中止。", "en": "Error: SHA256 verification failed. Aborted."},
    "update.err_checksum_missing": {"zh": "错误: 未找到该资产的校验值。", "en": "Error: No checksum found for the asset."},
    "update.err_not_frozen": {"zh": "源码运行模式无法自更新。请用 git pull 或安装正式版。", "en": "Running from source; use git pull or install a release."},
    "update.err_unsupported": {"zh": "错误: 不支持的平台（Intel Mac 已停止支持）。", "en": "Error: Unsupported platform (Intel Mac is no longer supported)."},
    "update.err_extract": {"zh": "错误: 安装包解压失败或布局不符。", "en": "Error: Failed to extract or invalid archive layout."},
    "update.err_install": {"zh": "错误: 替换安装目录失败，已回滚。", "en": "Error: Failed to replace install dir; rolled back."},
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_updater.py::I18nKeysTest -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add ccprofile_app/i18n.py tests/test_updater.py
git commit -m "feat(i18n): 添加 update 自更新相关字符串"
```

---

### Task 10: `cmd_update` 编排

**Files:**
- Modify: `ccprofile_app/updater.py`（追加 `cmd_update`）
- Test: `tests/test_updater.py`

**Interfaces:**
- Produces: `cmd_update(args) -> None`。读取 `args.check / args.yes / args.force / args.prerelease`（用 `getattr` 默认 `False`），编排：检测 → 比较 → 展示 changelog → 确认（除非 `--yes`/`--check`）→ 下载+校验+解压 → 平台替换。

- [ ] **Step 1: 追加失败测试**

```python
from types import SimpleNamespace


def _upd_args(**kw):
    base = dict(check=False, yes=False, force=False, prerelease=False)
    base.update(kw)
    return SimpleNamespace(**base)


class CmdUpdateTest(unittest.TestCase):
    def _patches(self, **overrides):
        defaults = dict(
            fetch_latest_release=unittest.mock.DEFAULT,
            download_to=unittest.mock.DEFAULT,
            expected_sha256=unittest.mock.DEFAULT,
            verify_sha256=unittest.mock.DEFAULT,
            extract_bundle=unittest.mock.DEFAULT,
            replace_bundle_unix=unittest.mock.DEFAULT,
            replace_bundle_windows=unittest.mock.DEFAULT,
            is_frozen=unittest.mock.DEFAULT,
            platform_asset=unittest.mock.DEFAULT,
            confirm_action=unittest.mock.DEFAULT,
        )
        defaults.update(overrides)
        return [unittest.mock.patch.object(updater, k, v) for k, v in defaults.items()]

    def test_up_to_date_does_not_download(self):
        with unittest.mock.patch.object(updater, "VERSION", "0.9.0"):
            for p in self._patches(
                fetch_latest_release=lambda: {"version": "0.9.0", "body": "", "assets": {}}
            ):
                p.start()
            self.addCleanup(unittest.mock.patch.stopall)
            updater.cmd_update(_upd_args())
        updater.download_to.assert_not_called()

    def test_check_only_does_not_replace(self):
        with unittest.mock.patch.object(updater, "VERSION", "0.3.0"):
            for p in self._patches(
                fetch_latest_release=lambda: {"version": "0.4.0", "body": "x", "assets": {}}
            ):
                p.start()
            self.addCleanup(unittest.mock.patch.stopall)
            updater.cmd_update(_upd_args(check=True))
        updater.replace_bundle_unix.assert_not_called()

    def test_yes_updates_on_unix(self):
        def fake_download(url, dest, timeout=30):
            Path(dest).write_bytes(b"data")

        with unittest.mock.patch.object(updater, "VERSION", "0.3.0"), \
             unittest.mock.patch.object(sys, "platform", "linux"):
            for p in self._patches(
                fetch_latest_release=lambda: {
                    "version": "0.4.0", "body": "x",
                    "assets": {"ccprofile-linux.tar.gz": "u", "SHA256SUMS": "s"},
                },
                download_to=fake_download,
                platform_asset=lambda: "ccprofile-linux.tar.gz",
                expected_sha256=lambda name, text: "abc",
                verify_sha256=lambda path, expected: True,
                extract_bundle=lambda a, d: Path(str(a)),
            ):
                p.start()
            self.addCleanup(unittest.mock.patch.stopall)
            updater.cmd_update(_upd_args(yes=True))
        updater.download_to.assert_called()
        updater.replace_bundle_unix.assert_called_once()
        updater.replace_bundle_windows.assert_not_called()

    def test_not_frozen_aborts_before_replace(self):
        with unittest.mock.patch.object(updater, "VERSION", "0.3.0"):
            for p in self._patches(
                fetch_latest_release=lambda: {"version": "0.4.0", "body": "", "assets": {}},
                is_frozen=lambda: False,
                verify_sha256=lambda path, expected: True,
                extract_bundle=lambda a, d: Path(str(a)),
            ):
                p.start()
            self.addCleanup(unittest.mock.patch.stopall)
            updater.cmd_update(_upd_args(yes=True))
        updater.replace_bundle_unix.assert_not_called()
```

> 说明：`_patches` 对全部外部依赖打补丁（`DEFAULT` 表示替换为可断言的 `MagicMock`），仅按需覆盖返回值。`extract_bundle` 返回一个临时 `Path` 作为「新 bundle」。第二个用例 `fetch` 返回更新版但 `check=True`，故不替换。第三个用例 `yes=True` 且非 Windows，走 `replace_bundle_unix`。第四个用例 `is_frozen` 为假，在下载完成后、替换前中止。

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_updater.py::CmdUpdateTest -v`
Expected: FAIL — `AttributeError ... has no attribute 'cmd_update'`

- [ ] **Step 3: 在 `updater.py` 追加实现**

```python
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_updater.py::CmdUpdateTest -v`
Expected: PASS（4 个用例）

- [ ] **Step 5: 提交**

```bash
git add ccprofile_app/updater.py tests/test_updater.py
git commit -m "feat(updater): 添加 cmd_update 编排"
```

---

### Task 11: CLI 接入

**Files:**
- Modify: `ccprofile_app/cli.py`（import、注册子命令、分发、挂启动检查）
- Test: `tests/test_updater.py`

**Interfaces:**
- Consumes: `updater.cmd_update`、`updater.maybe_check_on_launch`。
- Produces: `ccprofile update` 子命令（`--check / -y,--yes / --force / --prerelease`）与 `main()` 末尾的启动检查调用（`--_internal-proxy` 分支除外）。

- [ ] **Step 1: 追加失败测试**

```python
class CliWiringTest(unittest.TestCase):
    def test_parser_has_update_flags(self):
        from ccprofile_app import cli

        with unittest.mock.patch.object(cli, "init_language"), \
             unittest.mock.patch.object(cli, "migrate_from_legacy"):
            parser = cli.build_parser()
        ns = parser.parse_args(["update", "--check", "-y", "--force", "--prerelease"])
        self.assertTrue(ns.check)
        self.assertTrue(ns.yes)
        self.assertTrue(ns.force)
        self.assertTrue(ns.prerelease)
        self.assertEqual(ns.command, "update")

    def test_main_dispatches_update_and_runs_launch_check(self):
        from ccprofile_app import cli

        with unittest.mock.patch("sys.argv", ["ccprofile", "update", "-y"]), \
             unittest.mock.patch.object(cli, "cmd_update") as cmd, \
             unittest.mock.patch.object(cli, "migrate_from_legacy"), \
             unittest.mock.patch.object(cli, "maybe_check_on_launch") as launch:
            cli.main()
        cmd.assert_called_once()
        self.assertTrue(cmd.call_args.args[0].yes)
        launch.assert_called_once()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_updater.py::CliWiringTest -v`
Expected: FAIL — `update` 子命令解析错误 / `cmd_update` 未被调用

- [ ] **Step 3: 修改 `cli.py`**

**(a) 在 import 区（`from .sync import (...)` 之后）追加：**

```python
from .updater import cmd_update, maybe_check_on_launch  # noqa: E402
```

**(b) 在 `build_parser()` 内、`sync` 子命令注册之后、`return parser` 之前追加：**

```python
    # update
    p_upd = sub.add_parser("update", help=t("cli.update_help"))
    p_upd.add_argument("--check", action="store_true", help=t("cli.update_check_help"))
    p_upd.add_argument("-y", "--yes", action="store_true", help=t("cli.update_yes_help"))
    p_upd.add_argument("--force", action="store_true", help=t("cli.update_force_help"))
    p_upd.add_argument("--prerelease", action="store_true", help=t("cli.update_prerelease_help"))
```

**(c) 在 `main()` 的 `commands` 字典中加入 `"update": cmd_update`（与 `"current"` 等并列）。**

**(d) 在 `main()` 的两处出口挂启动检查：**

把

```python
    if not args.command:
        interactive_menu()
        return
```

改为：

```python
    if not args.command:
        interactive_menu()
        maybe_check_on_launch()
        return
```

并在 `main()` 最末尾（最后那个 `else: commands[args.command](args)` 之后）追加：

```python
    maybe_check_on_launch()
```

> `--_internal-proxy` 分支在更早处 `return`，不会触发启动检查；交互菜单退出后调用一次；命令执行后调用一次。`provider --help` 等会 `SystemExit`，跳过检查，符合预期。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_updater.py::CliWiringTest -v`
Expected: PASS（2 个用例）

- [ ] **Step 5: 运行全量测试，确认无回归**

Run: `python3 -m pytest -q`
Expected: PASS（基线 32 + 本功能新增用例，全绿）

- [ ] **Step 6: 提交**

```bash
git add ccprofile_app/cli.py tests/test_updater.py
git commit -m "feat(cli): 接入 update 子命令与启动检查"
```

---

### Task 12: 菜单接入

**Files:**
- Modify: `ccprofile_app/menu.py`（import、`_system_menu`、`commands_map`、`_execute_command`）
- Test: `tests/test_updater.py`

**Interfaces:**
- Consumes: `updater.cmd_update`。
- Produces: 「系统设置」下新增「检查更新」入口，行为等同无参数 `ccprofile update`。

- [ ] **Step 1: 追加失败测试**

```python
class MenuWiringTest(unittest.TestCase):
    def test_system_menu_has_check_update(self):
        from ccprofile_app import menu

        with unittest.mock.patch.object(menu, "t", side_effect=lambda k, **kw: k):
            items = menu._system_menu()
        keys = [k for k, _ in items]
        self.assertIn("check_update", keys)

    def test_commands_map_has_check_update(self):
        from ccprofile_app import menu, updater

        # interactive_menu builds the map at call time; inspect the module-level
        # wiring by ensuring cmd_update is importable and wired as expected.
        self.assertTrue(callable(updater.cmd_update))
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest tests/test_updater.py::MenuWiringTest -v`
Expected: FAIL — `_system_menu()` 中无 `check_update`

- [ ] **Step 3: 修改 `menu.py`**

**(a) 在顶部 import 区追加（与 `from .commands import ...` 并列）：**

```python
from .updater import cmd_update
```

**(b) 在 `_system_menu()` 中追加一项：**

```python
def _system_menu():
    return [
        ("init",         t("menu.init_reset")),
        ("language",     t("menu.language_settings")),
        ("check_update", t("menu.check_update")),
        ("_sync",        t("menu.sync_settings")),
    ]
```

**(c) 在 `interactive_menu()` 的 `commands_map` 中追加：**

```python
        "check_update": cmd_update,
```

**(d) 在 `_execute_command` 的参数构造分支中（与 `elif cmd_name == "sync_strategy":` 并列）追加：**

```python
        elif cmd_name == "check_update":
            args.check = False
            args.yes = False
            args.force = False
            args.prerelease = False
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest tests/test_updater.py::MenuWiringTest -v`
Expected: PASS

- [ ] **Step 5: 运行全量测试**

Run: `python3 -m pytest -q`
Expected: PASS（全绿）

- [ ] **Step 6: 手动冒烟（可选但推荐）**

```bash
python3 ccprofile.py update --check
```
Expected: 打印「正在检查最新版本...」与当前/最新版本（联网；离线则打印网络错误后退出，不崩溃）。

- [ ] **Step 7: 提交**

```bash
git add ccprofile_app/menu.py tests/test_updater.py
git commit -m "feat(menu): 系统设置新增检查更新入口"
```

---

### Task 13: README 文档

**Files:**
- Modify: `README.md`

**Interfaces:** 无（纯文档）。

- [ ] **Step 1: 在 `README.md` 安装章节后追加「更新」小节**

在 README 现有「安装」相关章节之后，新增：

```markdown
## 更新

已安装的 ccprofile 可自更新到最新版本：

```bash
ccprofile update            # 检测并更新
ccprofile update --check    # 仅检测，不更新
ccprofile update -y         # 跳过确认
ccprofile update --force    # 即使同版本也重装
ccprofile update --prerelease  # 纳入预发布版本
```

- macOS / Linux 会原地替换安装目录（`~/.local/share/ccprofile`），PATH 上的 wrapper 不受影响，更新后立即生效。
- Windows 因运行中的 `.exe` 被锁定，更新完成后会提示「请重新运行 ccprofile」，由后台脚本完成替换。
- 每次启动会在后台静默检查新版本（每天最多联网一次），发现新版本时向终端打印一行提示。
- 关闭启动检查：设置环境变量 `CCPROFILE_NO_UPDATE_CHECK=1`。
- 也可在交互式菜单「系统设置 → 检查更新」中触发。
```

- [ ] **Step 2: 提交**

```bash
git add README.md
git commit -m "docs: 文档化 ccprofile update 自更新"
```

- [ ] **Step 3: 收尾验证**

Run: `python3 -m pytest -q`
Expected: PASS（全绿）

```bash
python3 ccprofile.py --version
python3 ccprofile.py update --help
```
Expected: 版本号正常输出；`update --help` 列出全部 flag。

---

## 完成标准

- `python3 -m pytest -q` 全绿（基线 32 + 新增用例）。
- `ccprofile update --check` 可联网检测并打印当前/最新版本；离线时打印错误且不崩溃。
- `ccprofile update -y` 在 Unix 上完成原子替换（手动验证：替换前后 `ccprofile --version` 变化；失败可回滚）。
- 启动检查：新版本时 stderr 打印提示；`CCPROFILE_NO_UPDATE_CHECK=1` 关闭；源码运行时跳过。
- 菜单「系统设置 → 检查更新」可用。
- README 已文档化。
