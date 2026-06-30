# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ccprofile** — A Python CLI tool that manages multiple encrypted API provider configurations for Claude Code, enabling quick switching between providers (e.g., PocoAI proxy, Anthropic official) via command line.

## Running

```bash
pip install cryptography          # Only dependency
python ccprofile.py init          # First-time setup
python ccprofile.py add <name>    # Add a profile
python ccprofile.py switch <name> # Switch active profile
```

No build system, no linter configured. **Tests exist** in `tests/`(121 tests, `python3 -m pytest`)。

## Architecture

`ccprofile.py` is a thin entry point that delegates to `ccprofile_app.cli:main()`. The package is organized by responsibility:

| Module | Responsibility |
|--------|---------------|
| `cli.py` | argparse definitions, `main()`, `build_parser()` |
| `commands.py` | `cmd_init`, `cmd_add`, `cmd_switch`, `cmd_list`, `cmd_show`, `cmd_edit`, `cmd_delete`, `cmd_current` |
| `provider.py` | Provider CRUD(`provider` 子命令) |
| `proxy.py` / `proxy_process.py` | 内置 HTTP 代理服务器,把 Claude Code 请求路由到不同 provider;`proxy` 子命令管理该进程 |
| `sync.py` / `webdav.py` | WebDAV 远程同步(`sync` 子命令) |
| `updater.py` | 自更新(`update` 子命令):检测、下载、校验并替换 ccprofile 包 |
| `storage.py` | profiles / meta / settings 文件读写与备份 |
| `crypto.py` | Fernet 密钥加载 / 保存、加解密 |
| `constants.py` | 路径、字段、hooks 模板、版本号(`VERSION`) |
| `hooks.py` | hooks 生成与 Bark key 脱敏 |
| `formatting.py` | 脱敏与输出格式工具 |
| `prompts.py` | profile 字段交互输入 |
| `menu.py` | 交互式菜单主循环 |
| `terminal.py` | 终端按键读取、列表选择、VT mode 支持 |
| `picker.py` | `pick_profile()` / `pick_provider()` 共享选择器 |
| `display.py` | 终端 UI 面板(非 TTY 时降级为纯文本) |
| `filelock.py` | 跨平台文件锁(flock / msvcrt) |
| `i18n.py` | 国际化(zh / en) |

**Dependency direction**: `cli` -> `commands` / `menu` -> `storage` / `prompts` / `hooks` / `formatting` -> `crypto` / `constants`。反向依赖不存在。

**Data flow**: Profiles are stored as a single JSON blob, encrypted with Fernet, and written to `~/.claude/profiles.enc`. The encryption key lives in `~/.claude/.profile_key`. The `switch` command reads a profile, backs up `~/.claude/settings.json` to `settings.json.bak`, merges the profile's `env` keys into the existing settings (preserving unrecognized fields), and writes the result.

**Key paths** (all under `~/.claude/`):
- `.profile_key` — Fernet encryption key (hidden on Windows)
- `profiles.enc` — Encrypted profile storage
- `profiles_meta.json` — Tracks which profile is active
- `settings.json` — Claude Code settings (modified by `switch`)
- `settings.json.bak` — Auto-backup before each switch

**Security**: API tokens are masked in display (first 8 + last 4 chars). Key file gets hidden attribute on Windows and restricted permissions via `os.chmod`. `settings.local.json` is never modified.

## CLI Commands

顶层子命令: `init`, `add`, `switch`, `list`, `show`, `edit`, `delete`, `current`(profile 管理);`provider {add,list,show,edit,delete}`(provider CRUD);`proxy {status,stop,logs}`;`sync {config,status,strategy,reset}`(WebDAV 同步);`teams`(Teams 集成);`update [--check] [-y] [--force] [--prerelease]`(自更新)。详见 README.md。

## 发布流程 (Release)

**发布新版本时,「升版本号 + 合并」只是开始——必须同时打 tag 和发 GitHub Release,缺一不可。** 完整步骤:

1. **升版本号**:改 `ccprofile_app/constants.py` 的 `VERSION`(版本号唯一来源),确认 `PYTHONPATH="$PWD" python3 -m pytest` 全绿。
2. **提交并合并**:新建分支 → 提交 → 推送 → 开 PR → 合并到 `main`。
   - `main` 受分支保护(要求 review,且作者无法自审)。以 owner 身份合并:`gh pr merge <PR号> --admin --merge --delete-branch`。
3. **打 tag**:在 `main` 上打**带注释**标签,版本号须与 `VERSION` 一致:`git tag -a vX.Y.Z -m "release vX.Y.Z"` → `git push origin vX.Y.Z`。
4. **发 GitHub Release**:`gh release create vX.Y.Z --target main --title "vX.Y.Z" --notes "..."`(notes 概述本次修复/特性,引用 PR)。

环境备忘:远端走 HTTPS + `gh` 凭据(本机 SSH 22 端口超时)。如需切回 SSH:`git remote set-url origin git@github.com:ZCXU0421/ccprofile.git`。

## Language

User-facing output and README are in Chinese (中文). Code comments and identifiers are in English.
