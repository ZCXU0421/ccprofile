# `ccprofile update` 自更新功能设计

- **日期**: 2026-06-29
- **状态**: 已通过设计评审，待实现
- **方案**: 方案一（原生自更新器）

## 1. 目标与背景

### 1.1 目标

为 ccprofile 增加「检测新版本并更新」的能力，取代当前手动去 GitHub Releases 下载的升级方式。

- **手动更新**：`ccprofile update` 检测最新版本，展示变更说明，确认后自动完成升级。
- **启动自动检查**：每次启动在后台静默检查，若发现新版本则打印一行提示；每天最多联网一次。
- **全平台自更新**：macOS / Linux / Windows 均支持原地自更新。

### 1.2 非目标

- 不做强制自动升级（仅提示，更新由用户显式触发）。
- 不引入除 `cryptography` 外的新运行时依赖。
- 不改动现有 CI（复用已发布的 release 资产与 `SHA256SUMS`）。
- 不支持回滚到任意历史版本（仅保留本次替换前的临时备份用于失败回滚）。

### 1.3 背景与约束

**分发模型**：ccprofile 以 PyInstaller onedir 二进制分发，资产为：

| 平台 | 资产 |
|------|------|
| macOS arm64 | `ccprofile-macos-arm64.tar.gz` |
| Linux | `ccprofile-linux.tar.gz` |
| Windows | `ccprofile-windows.zip` |

每个 release 附带 `SHA256SUMS` 校验文件。`releases/latest/download/<asset>` 指向最新版资产。版本号硬编码于 `ccprofile_app/constants.py`（当前 `VERSION = "0.3.0"`），git tag 形如 `v0.3.0`。Intel Mac 已不支持。

**安装布局**（由安装脚本生成）：

- macOS/Linux：PATH 上的 wrapper `~/.local/bin/ccprofile`（`exec "$APP_DIR/ccprofile" "$@"`）→ 真实 bundle `~/.local/share/ccprofile/`（含二进制 + `_internal/`）。
- Windows：wrapper `%USERPROFILE%\bin\ccprofile.bat`（`"!APP_DIR!\ccprofile.exe" %*`）→ 真实 bundle `%LOCALAPPDATA%\ccprofile\`。

**核心难点**：自更新需替换「当前正在运行的二进制」所在的 bundle。

- **Unix**：可安全替换运行中的文件——内核保留已打开的 inode。因此可解压到临时目录校验后原子地交换 bundle 目录。
- **Windows**：运行中的 `ccprofile.exe` 及 `_internal/*.dll`/`*.pyd` 被锁定，无法覆盖。需由脱机辅助进程在当前进程退出后再替换。

在 PyInstaller onedir 构建中，`sys.executable` 即真实二进制路径，故 **bundle 目录 = `Path(sys.executable).parent`**。PATH 上的 wrapper 不受影响——它只是 exec 新二进制。

## 2. 用户可见行为

### 2.1 命令面

```
ccprofile update              # 检测 → 有新版则展示 changelog → 确认 → 更新
ccprofile update --check      # 仅检测并报告，不更新（dry-run）
ccprofile update -y/--yes     # 跳过确认直接更新
ccprofile update --force      # 即使同版本也重装
ccprofile update --prerelease # 纳入预发布版本
```

### 2.2 输出示例

已是最新：

```
正在检查最新版本...
当前版本: 0.3.0
最新版本: 0.3.0
已是最新版本。
```

发现新版本：

```
正在检查最新版本...
当前版本: 0.3.0
最新版本: 0.4.0  ← 有新版本可用

更新内容:
  - 新增 X
  - 修复 Y
  ...

是否更新到 0.4.0？[Y/n]
正在下载 ccprofile-macos-arm64.tar.gz ... 完成
正在校验 SHA256 ... 通过
正在安装 ... 完成
更新成功！当前版本: 0.4.0
```

Windows 末尾：

```
更新成功！请重新运行 ccprofile 以使用新版本。
```

### 2.3 启动自动检查

- 在 `main()` 正常流程结束后（用户命令执行完 / 菜单退出后）追加一次检查；**不**对 `--_internal-proxy`（代理子进程）分支运行。
- **节流**：距上次联网检查 < 24 小时则只读本地缓存，不联网。
- **静默规则**：仅当发现新版本时向 **stderr** 打印一行提示，例如：

  ```
  [ccprofile] 发现新版本 0.4.0，运行 `ccprofile update` 更新。
  ```

  版本相同或检查失败时完全静默（不污染正常输出与脚本管道）。
- **可关闭**：环境变量 `CCPROFILE_NO_UPDATE_CHECK=1` 跳过启动检查。
- **源码运行**：`sys.frozen` 为假时自动跳过（提示用 `git pull` 或安装正式版）。
- **菜单入口**：在「系统设置」下新增「检查更新」，行为等同无参数的 `ccprofile update`（检测 → 展示 → 确认 → 更新）。

## 3. 架构

新增模块 `ccprofile_app/updater.py`，遵循现有依赖方向（`cli → updater → constants/i18n/display`，不反向依赖）。

### 3.1 模块职责

| 函数 | 职责 | 可测性 |
|------|------|--------|
| `parse_version(s) -> tuple` | 解析 `MAJOR.MINOR.PATCH`，去前导 `v`，识别 prerelease | 纯函数 |
| `is_newer(latest, current, include_prerelease) -> bool` | 版本比较 | 纯函数 |
| `platform_asset() -> str` | 当前平台对应的资产文件名 | 纯函数 |
| `expected_sha256(asset_name, sha256sums_text) -> str \| None` | 从 `SHA256SUMS` 文本中取对应哈希 | 纯函数 |
| `should_check_now(cache) -> bool` | 节流判断（距上次联网 ≥ 24h） | 纯函数 |
| `fetch_latest_release() -> dict` | 调 GitHub Releases API（带 UA、超时、限流降级） | IO |
| `download_to(url, dest) -> None` | 流式下载到文件 | IO |
| `verify_sha256(path, expected) -> bool` | 计算并比对 SHA256 | IO |
| `extract_bundle(archive, dest) -> Path` | 解压并校验布局 | IO |
| `replace_bundle_unix(new_dir) -> None` | Unix 原子交换 + 失败回滚 | IO |
| `replace_bundle_windows(new_dir) -> None` | Windows 脱机 `.bat` 替换 | IO |
| `cmd_update(args) -> None` | 命令入口：编排上述步骤 | 编排 |
| `maybe_check_on_launch() -> None` | 启动自动检查（节流 + 静默） | 编排 |

### 3.2 数据流

```
cmd_update
  └─ fetch_latest_release() ── API ──┐
        (限流降级: HEAD releases/latest 读 Location tag)
        ├─ is_newer(latest, current) ?
        │     no  → "已是最新"
        │     yes → 展示 changelog → 确认
        └─ download_to(asset) + download_to(SHA256SUMS)
              └─ verify_sha256(asset, expected_sha256(...))
                    └─ extract_bundle(asset, tmp)
                          └─ sys.frozen?
                                no  → "源码运行，请 git pull"
                                yes → Unix: replace_bundle_unix
                                       Win : replace_bundle_windows（脱机）
```

启动自动检查走虚线分支：`fetch_latest_release → is_newer`，命中则写缓存 + 打印提示。

### 3.3 持久化

新增缓存文件 `~/.ccprofile/update_check.json`（与现有 `~/.ccprofile/` 数据目录一致）：

```json
{
  "last_check_ts": 1774800000,
  "latest_known": "0.4.0"
}
```

## 4. 详细算法

### 4.1 版本检测

- 主路径：`GET https://api.github.com/repos/ZCXU0421/ccprofile/releases/latest`，请求头设 `User-Agent: ccprofile/<VERSION>`。解析 JSON：`tag_name`（去 `v`）、`body`（changelog，截断展示）、`assets[].browser_download_url`。
- **限流降级**：返回 403 时回退到 `HEAD https://github.com/ZCXU0421/ccprofile/releases/latest`，读 `Location` 响应头最后一段（如 `.../tag/v0.4.0`）得到 tag——无需鉴权、无限流。此降级仅得版本号，无 changelog（展示时省略变更说明）。
- 网络/解析失败：自动检查静默；显式 `update` 打印简短错误后正常退出（非零退出码）。
- 超时：显式 `update` 用 ~10s；启动检查用 ~3s，避免拖慢正常命令。
- 仅用 stdlib `urllib`；TLS 显式用 `ssl.create_default_context(cafile=certifi.where())`（打包已 `--collect-data certifi`，CA 可用）。

### 4.2 节流（启动检查）

- 读取 `update_check.json` 的 `last_check_ts`。
- `now - last_check_ts >= 86400` 才联网；否则用缓存的 `latest_known` 直接判断是否提示。
- 联网成功后更新 `last_check_ts` 与 `latest_known`。

### 4.3 下载与校验

1. 由 `platform_asset()` 选资产；Intel Mac → 报错退出（与安装脚本一致）。
2. 下载该资产 + 同一 release 的 `SHA256SUMS`（优先用 API 返回的精确资产 URL；降级时用 `releases/latest/download/SHA256SUMS`）。
3. **强制校验**：`expected = expected_sha256(asset_name, sha256sums_text)`；找不到 → 报错中止。比对资产实际 SHA256，不匹配 → 删除临时文件、中止、报错（完全镜像 `verify_checksum`）。
4. 解压：Unix `tarfile`、Windows `zipfile`，预期布局 `ccprofile/ccprofile` 或 `ccprofile\ccprofile.exe`；布局不符 → 报错。

### 4.4 Unix 替换（运行中可替换）

```
backup = bundle_dir.parent / "ccprofile.old"
shutil.move(bundle_dir, backup)        # 运行中二进制的 inode 仍被映射
try:
    os.replace(new_extracted_dir, bundle_dir)   # 原子
except Exception:
    shutil.rmtree(bundle_dir, ignore_errors=True)
    shutil.move(backup, bundle_dir)     # 回滚
    raise
shutil.rmtree(backup, ignore_errors=True)
```

PATH wrapper 不动，下次 exec 即新二进制。

### 4.5 Windows 替换（脱机辅助脚本）

1. 解压校验到暂存 `%TEMP%\ccprofile-update-<pid>\ccprofile`。
2. 生成 `%TEMP%\ccprofile-update-<pid>.bat`，逻辑：

   ```bat
   :wait
   tasklist /FI "PID eq <PID>" | find "<PID>" >nul && (timeout /t 1 >nul & goto wait)
   rmdir /s /q "<bundle_dir>"            （带最多 3 次重试）
   move /y "<staging>\ccprofile" "<bundle_dir>"
   rmdir /s /q "<staging_parent>"
   del "%~f0"
   ```

3. `subprocess.Popen(["cmd","/c","start","/b",bat], creationflags=DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP)` 启动后立即返回。
4. 父进程打印「更新成功！请重新运行 ccprofile」并退出；辅助脚本随后完成替换。
5. 持久失败（如重试用尽）则保留暂存目录并提示用户手动处理。

## 5. 安全

- **仅 HTTPS**：硬编码官方仓库；`CCPROFILE_RELEASES_URL` 可覆盖（镜像/测试），但强制 HTTPS 校验（同安装脚本的 `require_https_url`）。
- **替换前必校验**：SHA256 不匹配一律中止，绝不落盘未校验的二进制。
- **最小执行面**：除已校验的平台二进制外，不执行任何远端代码（Windows 辅助 `.bat` 由本地生成，非远端）。
- **不修改用户数据**：`~/.claude/` 配置、profile 加密数据等一律不动。

## 6. i18n

新增 zh/en 字符串（键名前缀 `update.` / `cli.update_*`），示例：

| 键 | zh | en |
|----|----|----|
| `cli.update_help` | 检测并更新到最新版本 | Check for and update to the latest version |
| `cli.update_check_help` | 仅检测，不更新 | Check only, do not update |
| `cli.update_yes_help` | 跳过确认 | Skip confirmation |
| `cli.update_force_help` | 即使同版本也重装 | Reinstall even if same version |
| `cli.update_prerelease_help` | 纳入预发布版本 | Include pre-release versions |
| `menu.check_update` | 检查更新 | Check for Updates |
| `update.checking` | 正在检查最新版本... | Checking for the latest version... |
| `update.current` | 当前版本 | Current version |
| `update.latest` | 最新版本 | Latest version |
| `update.up_to_date` | 已是最新版本。 | Already up to date. |
| `update.new_available` | 有新版本可用 | A new version is available |
| `update.changelog` | 更新内容 | Release notes |
| `update.confirm` | 是否更新到 {version}？ | Update to {version}? |
| `update.canceled` | 已取消。 | Canceled. |
| `update.downloading` | 正在下载 {asset} | Downloading {asset} |
| `update.verifying` | 正在校验 SHA256 | Verifying SHA256 |
| `update.extracting` | 正在安装 | Installing |
| `update.success_unix` | 更新成功！当前版本: {version} | Updated! Now at version {version} |
| `update.success_windows` | 更新成功！请重新运行 ccprofile。 | Updated! Please re-run ccprofile. |
| `update.launch_hint` | [ccprofile] 发现新版本 {version}，运行 `ccprofile update` 更新。 | [ccprofile] New version {version} available. Run `ccprofile update`. |
| `update.err_network` | 错误: 无法连接到 GitHub，请检查网络。 | Error: Cannot reach GitHub. Check your network. |
| `update.err_rate_limited` | 错误: GitHub API 限流，请稍后再试。 | Error: GitHub API rate-limited. Try again later. |
| `update.err_checksum` | 错误: SHA256 校验失败，已中止。 | Error: SHA256 verification failed. Aborted. |
| `update.err_checksum_missing` | 错误: 未找到该资产的校验值。 | Error: No checksum found for the asset. |
| `update.err_not_frozen` | 源码运行模式无法自更新。请用 git pull 或安装正式版。 | Running from source; use git pull or install a release. |
| `update.err_unsupported` | 错误: 不支持的平台（Intel Mac 已停止支持）。 | Error: Unsupported platform (Intel Mac is no longer supported). |

版本信息卡片复用 `display.py` 的 `panel` / `kv`。

## 7. 文件改动

| 文件 | 改动 |
|------|------|
| `ccprofile_app/updater.py` | **新增**：全部逻辑 + `cmd_update` + `maybe_check_on_launch` |
| `ccprofile_app/cli.py` | 注册 `update` 子命令与参数；分发；`main()` 末尾调用 `maybe_check_on_launch()` |
| `ccprofile_app/constants.py` | 新增 `GITHUB_REPO = "ZCXU0421/ccprofile"`、`UPDATE_CHECK_FILE = PROFILE_DIR / "update_check.json"`、`UPDATE_CHECK_INTERVAL = 86400` |
| `ccprofile_app/i18n.py` | 新增上表字符串 |
| `ccprofile_app/menu.py` | 「系统设置」下新增「检查更新」入口 |
| `README.md` | 文档化 `ccprofile update` 与启动检查 |
| `tests/test_updater.py` | **新增**：纯逻辑单测 |

**不改动** `.github/workflows/build.yml`、安装脚本。

## 8. 边界与错误处理

- 源码运行（`sys.frozen` 假）→ 友好提示，不替换。
- Intel Mac → 报错（与安装脚本一致）。
- `expected_sha256` 找不到行、下载中断、校验失败、解压布局不符 → 删除临时文件、中止、清晰报错。
- GitHub 限流 → 显式命令提示稍后重试；启动检查静默。
- Windows 替换重试用尽 → 保留暂存、提示用户。
- bundle 目录不可写 → 提前检测权限，报错而非半途崩溃。
- 启动检查任何异常都被捕获，绝不影响主命令。

## 9. 测试策略

纯逻辑函数（无 IO）单元测试，覆盖：

- `parse_version`：`0.3.0` / `v0.3.0` / `0.4.0-rc1` / 非法输入。
- `is_newer`：各方向、prerelease 开关。
- `platform_asset`：mock `sys.platform`/`platform.machine()` 覆盖三平台 + Intel Mac 报错。
- `expected_sha256`：标准 `SHA256SUMS` 文本、缺失项返回 `None`。
- `should_check_now`：刚检查过、超过 24h、无缓存。

IO 层（网络/替换）保持薄；对 `fetch_latest_release` 用 mock HTTP 验证成功路径与限流降级分支。

## 10. 未来扩展（非本期）

- `ccprofile update --version <x.y.z>` 安装指定版本。
- 从 release body 解析结构化 changelog。
- 数字签名校验（cosign/sigstore）替代/补充 SHA256。
- 滚动保留 N 个历史版本以便一键回滚。
