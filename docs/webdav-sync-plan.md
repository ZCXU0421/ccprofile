# WebDAV 多端同步方案设计报告

## 1. 背景与动机

ccprofile 当前的所有配置数据（加密的 profile、provider、元信息）仅存储在本地 `~/.ccprofile/` 目录下。用户在多台设备（如办公电脑、家用电脑、笔记本）上使用 Claude Code 时，需要手动在每台设备上重复配置相同的 profile 和 provider，维护成本高且容易不一致。

WebDAV 是一种成熟、广泛支持的文件同步协议，主流网盘服务（坚果云、Nextcloud、Synology WebDAV、TeraCloud 等）均提供 WebDAV 接口。通过 WebDAV 同步，用户可以在任意设备上无缝使用已配置的 profile，且无需自建服务器。

## 2. 需要同步的数据

| 文件 | 内容 | 大小估算 | 同步策略 |
|------|------|----------|----------|
| `profiles.enc` | Fernet 加密后的全部 profile 配置 JSON | < 10 KB | 双向同步 |
| `providers.enc` | Fernet 加密后的全部 provider 配置 JSON | < 5 KB | 双向同步 |
| `profiles_meta.json` | 当前激活的 profile 名称 | < 100 B | 仅上传/不同步 |
| `.profile_key` | Fernet 加密密钥 | 44 B | **不同步** |

### 设计决策：加密密钥不同步

`.profile_key` 是加密配置文件的核心密钥。若通过 WebDAV 传输密钥，即使传输层使用 HTTPS，仍存在以下风险：

- WebDAV 服务端（网盘提供商）可获取明文密钥
- 历史版本可能残留密钥文件
- 用户的 WebDAV 凭据泄露时，密钥同时暴露

因此，**加密密钥需在每台设备上通过 `ccprofile init` 独立生成**，而同步的 `profiles.enc` 和 `providers.enc` 需要在同步时进行密钥转换（re-encrypt）。

### 设计决策：`profiles_meta.json` 仅上传不同步

每台设备的「当前激活 profile」是本地状态，不应被其他设备覆盖。仅上传至远端作为参考备份，拉取时忽略此文件。

## 3. 同步模型

### 3.1 总体架构

```
设备 A                              WebDAV 服务器                           设备 B
┌──────────────┐                   ┌──────────────────┐                  ┌──────────────┐
│ ~/.ccprofile/│                   │ /dav/ccprofile/   │                  │ ~/.ccprofile/│
│ profiles.enc │ ──push──>         │ profiles.enc      │        ──pull──> │ profiles.enc │
│ providers.enc│ ──push──>         │ providers.enc     │        ──pull──> │ providers.enc│
│ profiles_meta│ ──upload──>       │ profiles_meta.json│   (不拉取)        │              │
│ .profile_key │ (不传输)          │ sync_meta.json    │ <──pull───       │ .profile_key │
└──────────────┘                   └──────────────────┘                  └──────────────┘
```

### 3.2 同步元数据 `sync_meta.json`

存储在 WebDAV 端，用于追踪同步状态：

```json
{
  "version": 1,
  "last_modified": "2026-04-22T14:30:00Z",
  "last_modified_by": "office-mac",
  "profiles_enc_md5": "a1b2c3d4...",
  "providers_enc_md5": "e5f6g7h8..."
}
```

每台设备本地也维护一份同步元数据：

```json
{
  "device_name": "office-mac",
  "last_sync_time": "2026-04-22T14:30:00Z",
  "last_push_time": "2026-04-22T14:30:00Z",
  "last_pull_time": "2026-04-22T14:25:00Z",
  "remote_profiles_md5": "a1b2c3d4...",
  "remote_providers_md5": "e5f6g7h8..."
}
```

### 3.3 密钥转换流程

由于每台设备有不同的 Fernet 密钥，同步时需执行密钥转换：

```
远端 profiles.enc（用设备 A 的密钥加密）
    ↓ 下载
    ↓ 用设备 A 的密钥解密 → 明文 JSON
    ↓ 用设备 B 的密钥重新加密
本地 profiles.enc（用设备 B 的密钥加密）
```

这意味着 **push 时需要知道远端数据使用的密钥**，或更准确地说：

- **Push**：本地的加密数据 → 解密为明文 → 用本地密钥重新加密后上传（远端总是存储最后一次 push 设备的密钥加密版本）
- **Pull**：下载远端加密数据 → 由于无法解密（密钥不同），需要一种协商机制

#### 问题：跨设备密钥转换的可行性分析

**方案 A：远端存储明文 JSON（依赖传输层加密）**

- WebDAV 上存储未加密的 JSON
- 传输层 HTTPS 保证传输安全
- 风险：WebDAV 服务端可直接读取全部配置（含 API Token）
- **不推荐**：API Token 是敏感凭据

**方案 B：使用独立的同步加密密钥（推荐）**

- 引入一个独立于本地 `.profile_key` 的「同步密钥」（sync_key）
- 同步密钥由用户在首次配置同步时设定（一个密码短语）
- 使用 PBKDF2 从密码短语派生 Fernet 密钥
- 远端存储的数据用同步密钥加密，本地数据用本地密钥加密
- Push 时：本地密钥解密 → 明文 → 同步密钥加密 → 上传
- Pull 时：下载 → 同步密钥解密 → 明文 → 本地密钥加密 → 写入本地

```
本地 profiles.enc ──本地密钥解密──> 明文 JSON ──同步密钥加密──> 上传到 WebDAV

WebDAV profiles.enc ──同步密钥解密──> 明文 JSON ──本地密钥加密──> 本地 profiles.enc
```

**方案 C：所有设备共享同一密钥**

- 将 `.profile_key` 通过安全渠道（非 WebDAV）在设备间传递
- 简单但安全性依赖用户手动管理密钥传递
- 适合高安全需求的用户，但体验差

**推荐方案 B**：独立同步密钥，兼顾安全性和易用性。

## 4. 冲突检测与解决

### 4.1 冲突场景

1. **设备 A push 后，设备 B 在未 pull 的情况下修改了本地数据再 push** → 远端被覆盖
2. **设备 A 和设备 B 都 pull 了相同版本，各自修改后同时 push** → 后 push 者覆盖

### 4.2 冲突检测机制

使用 `sync_meta.json` 中的 MD5 哈希值进行检测：

```
Push 前检查：
1. 下载远端 sync_meta.json
2. 比较 remote_profiles_md5 与本地记录的 remote_profiles_md5
3. 若不一致 → 说明远端已被其他设备更新
4. 检查本地数据是否也修改过（对比上次 pull 后的快照）
5. 若两端都修改过 → 冲突
```

### 4.3 冲突解决策略

提供三种策略供用户选择：

| 策略 | 行为 | 适用场景 |
|------|------|----------|
| `local-wins` | 本地版本覆盖远端 | 用户明确知道本地版本是最新的 |
| `remote-wins` | 远端版本覆盖本地 | 用户知道其他设备的修改更重要 |
| `merge` | JSON 级别的字段合并 | 两端修改了不同 profile，自动合并 |

**合并策略详细逻辑**：

```python
def merge_profiles(local_profiles, remote_profiles, base_profiles):
    """
    三方合并：以 base 为基准，分别与 local 和 remote 比较
    - 两端都新增的同名 profile → 冲突，保留 remote 并重命名 local（加后缀）
    - 一端新增一端未改 → 保留新增
    - 一端修改一端未改 → 保留修改
    - 两端都修改同一 profile → 冲突，保留 remote，将 local 保存为冲突副本
    """
    merged = {}
    all_keys = set(local_profiles) | set(remote_profiles) | set(base_profiles)

    for key in all_keys:
        in_base = key in base_profiles
        in_local = key in local_profiles
        in_remote = key in remote_profiles

        if not in_base:
            # 新增：两端都新增了同名 profile
            if in_local and in_remote:
                if local_profiles[key] == remote_profiles[key]:
                    merged[key] = local_profiles[key]
                else:
                    merged[key] = remote_profiles[key]
                    merged[f"{key} (冲突-{device_name})"] = local_profiles[key]
            elif in_local:
                merged[key] = local_profiles[key]
            else:
                merged[key] = remote_profiles[key]
        else:
            # 已存在：检测修改
            local_changed = local_profiles.get(key) != base_profiles.get(key)
            remote_changed = remote_profiles.get(key) != base_profiles.get(key)

            if local_changed and remote_changed:
                if local_profiles[key] == remote_profiles[key]:
                    merged[key] = local_profiles[key]
                else:
                    merged[key] = remote_profiles[key]
                    merged[f"{key} (冲突-{device_name})"] = local_profiles[key]
            elif local_changed:
                merged[key] = local_profiles[key]
            elif remote_changed:
                merged[key] = remote_profiles[key]
            else:
                merged[key] = base_profiles[key]

    return merged
```

为实现三方合并，需要在本地保存上次同步后的快照（base version），存储在 `~/.ccprofile/sync_snapshot/` 目录下。

## 5. CLI 命令设计

### 5.1 新增命令

```bash
# 配置 WebDAV 连接
ccprofile sync config

# 自动同步（自动判断 push/pull/merge，默认行为）
ccprofile sync

# 设置冲突解决策略
ccprofile sync strategy [local-wins|remote-wins|merge]

# 查看同步状态
ccprofile sync status

# 清除本地同步配置
ccprofile sync reset
```

### 5.2 `sync config` 交互流程

```
$ ccprofile sync config

  WebDAV 同步配置
  ───────────────

  WebDAV 服务器地址: https://dav.jianguoyun.com/dav/
  用户名: user@example.com
  密码: ****
  远端目录 [/ccprofile]: /ccprofile

  ✓ 连接测试成功

  设置同步密码（用于加密远端数据）:
  同步密码: ****
  确认密码: ****

  设备名称 (用于冲突标识) [mac-office]: mac-office

  ✓ 同步配置已保存
```

### 5.3 `sync` 自动同步流程

```
1. 读取本地同步配置
2. 连接 WebDAV，获取远端 sync_meta.json
3. 比较远端 MD5 与本地记录
4. 若远端无变化且本地无变化 → "已是最新" 提示
5. 若仅远端有变化 → 执行 pull
6. 若仅本地有变化 → 执行 push
7. 若两端都有变化 → 根据策略解决冲突后同步
```

## 6. 新增模块设计

### 6.1 文件结构

```
ccprofile_app/
  sync.py            # 同步核心逻辑（新增）
  webdav.py          # WebDAV 客户端封装（新增）
```

### 6.2 `webdav.py` — WebDAV 客户端

职责：封装 WebDAV 协议操作，不涉及 ccprofile 业务逻辑。

```python
class WebDAVClient:
    """轻量级 WebDAV 客户端，仅实现 ccprofile 同步所需的最小操作集"""

    def __init__(self, base_url: str, username: str, password: str):
        """
        base_url: WebDAV 服务根路径，如 https://dav.jianguoyun.com/dav/
        所有远端路径相对于 base_url 解析
        """

    def test_connection(self) -> bool:
        """验证连接和凭据是否有效（PROPFIND 请求）"""

    def exists(self, remote_path: str) -> bool:
        """检查远端文件是否存在（HEAD 请求）"""

    def download(self, remote_path: str) -> bytes:
        """下载远端文件内容（GET 请求）"""

    def upload(self, remote_path: str, data: bytes) -> None:
        """上传文件到远端（PUT 请求）"""

    def delete(self, remote_path: str) -> None:
        """删除远端文件（DELETE 请求）"""

    def get_etag(self, remote_path: str) -> str | None:
        """获取远端文件的 ETag（HEAD 请求），用于条件上传"""

    def ensure_directory(self, remote_path: str) -> None:
        """确保远端目录存在（MKCOL 请求，忽略 405/301 错误）"""

    def list_files(self, remote_path: str) -> list[str]:
        """列出远端目录下的文件（PROPFIND depth=1）"""
```

实现细节：
- 使用 `urllib.request`（标准库），不引入 `requests` 依赖
- Basic Auth 通过 `urllib.request.HTTPBasicAuthHandler` 处理
- 所有请求验证 HTTPS 证书（默认）
- 超时设置：连接 10 秒，读取 30 秒
- 自动处理重定向（301/302）

### 6.3 `sync.py` — 同步核心逻辑

职责：协调本地数据、WebDAV 客户端、密钥转换和冲突解决。

```python
def cmd_sync_config(args):
    """交互式配置 WebDAV 连接"""

def cmd_sync(args):
    """执行自动同步（push/pull/merge 由变更检测自动决定）"""

def cmd_sync_status(args):
    """显示同步状态（上次同步时间、远端对比等）"""

def cmd_sync_strategy(args):
    """设置冲突解决策略"""

def cmd_sync_reset(args):
    """清除本地同步配置"""

# 内部函数
def _get_sync_config() -> dict | None:
    """读取本地同步配置"""

def _save_sync_config(config: dict) -> None:
    """保存同步配置到 ~/.ccprofile/sync_config.json"""

def _derive_sync_key(passphrase: str) -> bytes:
    """从用户密码短语派生 Fernet 密钥（PBKDF2 + SHA256）"""

def _re_encrypt(data: bytes, old_key: bytes, new_key: bytes) -> bytes:
    """用 old_key 解密数据，用 new_key 重新加密"""

def _detect_sync_action(local_snapshot, local_current, remote_meta) -> str:
    """检测需要的同步动作：'push', 'pull', 'conflict', 'up-to-date'"""

def _merge_data(local, remote, base, device_name) -> tuple[dict, list[str]]:
    """三方合并，返回 (merged_data, conflict_warnings)"""

def _save_snapshot(profiles, providers) -> None:
    """保存同步快照到 ~/.ccprofile/sync_snapshot/"""
```

### 6.4 配置存储

新增文件 `~/.ccprofile/sync_config.json`：

```json
{
  "webdav_url": "https://dav.jianguoyun.com/dav/",
  "username": "user@example.com",
  "password_encrypted": "gAAAAABh...",  // 用本地 .profile_key 加密存储
  "remote_dir": "/ccprofile",
  "sync_key_salt": "base64...",          // PBKDF2 盐值
  "device_name": "mac-office",
  "strategy": "merge",
  "last_sync_time": "2026-04-22T14:30:00Z",
  "remote_profiles_md5": "a1b2c3d4...",
  "remote_providers_md5": "e5f6g7h8..."
}
```

**密码安全**：WebDAV 密码使用本地 `.profile_key` 加密后存储，避免明文落盘。

新增目录 `~/.ccprofile/sync_snapshot/`，存储上次成功同步后的本地快照（用于三方合并）：
- `sync_snapshot/profiles.json` — 使用本地 `.profile_key` 加密后的 JSON
- `sync_snapshot/providers.json` — 使用本地 `.profile_key` 加密后的 JSON

## 7. 与现有架构的集成

### 7.1 依赖关系

```
cli.py
  └─> sync.py (新增)
        └─> webdav.py (新增)
        └─> storage.py (load/save profiles, providers)
        └─> crypto.py (re-encrypt, derive key)
        └─> constants.py (新增同步相关路径)
```

不引入新的反向依赖，符合现有架构方向。

### 7.2 `constants.py` 变更

```python
# 新增
SYNC_CONFIG_FILE = CCPROFILE_DIR / "sync_config.json"
SYNC_SNAPSHOT_DIR = CCPROFILE_DIR / "sync_snapshot"
SYNC_SNAPSHOT_PROFILES = SYNC_SNAPSHOT_DIR / "profiles.json"
SYNC_SNAPSHOT_PROVIDERS = SYNC_SNAPSHOT_DIR / "providers.json"
```

### 7.3 `cli.py` 变更

```python
# build_parser() 中新增子命令
sync_sub = subparsers.add_parser('sync', help=t('sync_help'))
sync_sub.add_argument('action', nargs='?', default='auto',
                      choices=['config', 'status', 'strategy', 'reset'],
                      help=t('sync_action_help'))
sync_sub.add_argument('strategy_arg', nargs='?', default=None,
                      help=t('sync_strategy_help'))
```

### 7.4 `i18n.py` 变更

新增同步相关的中英文翻译条目（约 30 条），涵盖所有同步命令的提示文本。

### 7.5 `menu.py` 变更

在系统子菜单中新增「同步管理」选项：

```
系统设置
  ├── 语言设置
  ├── 同步管理        ← 新增
  └── 退出
```

### 7.6 `commands.py` 变更

在 `cmd_add`、`cmd_edit`、`cmd_delete` 等修改数据的命令末尾，标记本地数据已变更：

```python
# 在修改 profile/provider 的命令末尾添加
_sync_mark_dirty()
```

`_sync_mark_dirty()` 仅更新本地元数据中的 `local_dirty` 标志，不触发自动同步。下次执行 `sync` 时会检测到此标志。

## 8. WebDAV 兼容性考量

| 服务商 | 基础 URL | 注意事项 |
|--------|----------|----------|
| 坚果云 | `https://dav.jianguoyun.com/dav/` | 需使用应用专用密码，非登录密码 |
| Nextcloud | `https://cloud.example.com/remote.php/dav/files/USER/` | 标准兼容 |
| Synology | `https://nas.example.com:5006/` | 需启用 WebDAV 服务 |
| TeraCloud | `https://ena.teracloud.jp/dav/` | 标准兼容 |
| Box | `https://dav.box.com/dav/` | 需使用应用密码 |
| 自建（Nginx/Radicale） | 自定义 | 需配置 HTTPS |

### 兼容性处理

- **路径拼接**：统一使用 `/` 分隔，处理末尾/开头斜杠不一致
- **MKCOL 冲突**：目录已存在时返回 405，视为成功
- **Etag 格式**：不同服务商 ETag 格式不同（有无引号），统一去除引号后比较
- **字符编码**：所有 PUT/GET 使用 UTF-8 编码
- **HTTPS 证书**：部分自建服务可能使用自签证书，提供 `--no-verify-ssl` 选项（仅在 `sync config` 中设置，非每次命令参数）

## 9. 实现计划

### Phase 1：基础框架（约 3-4 天）

1. 实现 `webdav.py`：WebDAV 客户端核心操作
2. 实现 `sync.py`：配置管理 + 密钥派生 + re-encrypt
3. 在 `cli.py` 中注册 `sync` 子命令
4. 在 `menu.py` 中添加同步入口
5. 单向同步验证：push 功能可用

### Phase 2：双向同步（约 2-3 天）

1. 实现变更检测逻辑
2. 实现 pull 功能
3. 实现自动同步模式（push/pull/merge 自动判断）
4. 本地快照管理

### Phase 3：冲突处理（约 2 天）

1. 实现三方合并算法
2. 实现冲突提示和策略选择
3. 冲突副本保存和恢复

### Phase 4：集成与优化（约 2 天）

1. i18n 翻译条目补充
2. 错误处理和重试机制
3. 多服务商兼容性测试
4. 在修改类命令中标记 dirty 状态

**总计约 9-11 天。**

## 10. 安全性总结

| 安全措施 | 说明 |
|----------|------|
| 传输加密 | HTTPS 强制使用，不支持 HTTP |
| 远端数据加密 | 使用 PBKDF2 派生的同步密钥加密，WebDAV 服务端无法读取明文 |
| 本地密码加密 | WebDAV 凭据使用本地 `.profile_key` 加密存储 |
| 密钥隔离 | 同步密钥与本地加密密钥完全独立，互不影响 |
| API Token 保护 | 即使远端数据被获取，没有同步密码也无法解密获得 API Token |
| 文件权限 | 新增的 sync_config.json 和快照文件设置与现有文件一致的权限 |

## 11. 用户体验示例

### 首次配置（设备 A）

```
$ ccprofile sync config

  ╔══════════════════════════════════╗
  ║       WebDAV 同步配置             ║
  ╚══════════════════════════════════╝

  WebDAV 地址: https://dav.jianguoyun.com/dav/
  用户名: user@example.com
  应用密码: ********

  ✓ 连接测试成功

  远端目录 [/ccprofile]:
  同步密码: ********
  确认同步密码: ********
  设备名称 [mac-office]:

  ✓ 同步配置已保存
  ℹ 使用 ccprofile sync 开始同步
```

### 日常同步

```
$ ccprofile sync

  同步检测中...
  ┌─────────────────────────────────┐
  │ 远端有 2 项更新                  │
  │ 本地有 1 项更新                  │
  │                                 │
  │ 执行合并同步...                  │
  │ ✓ 合并成功，无冲突               │
  │ ✓ 已推送到远端 (3 profiles)      │
  │ ✓ 已拉取到本地 (3 profiles)      │
  │                                 │
  │ 上次同步: 2026-04-22 14:30      │
  └─────────────────────────────────┘
```

### 冲突场景

```
$ ccprofile sync

  同步检测中...
  ┌─────────────────────────────────┐
  │ ⚠ 检测到冲突                    │
  │                                 │
  │ Profile "work" 在远端和本地      │
  │ 都被修改                        │
  │                                 │
  │ 冲突策略: merge                  │
  │ ✓ 保留远端版本 "work"            │
  │ ✓ 本地版本保存为 "work (冲突)"   │
  │ ✓ 同步完成                      │
  └─────────────────────────────────┘
```

## 12. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| WebDAV 服务不可用 | 无法同步 | 本地功能不受影响，提供清晰的错误提示 |
| 用户忘记同步密码 | 无法解密远端数据 | 提示重新配置同步，远端数据可覆盖 |
| 网络中断导致上传不完整 | 远端数据损坏 | 使用原子上传（先传临时文件名，再 RENAME；不支持则传完整后验证 MD5） |
| 大量 profile 导致合并复杂 | 合并逻辑错误 | 实际场景 profile 数量很少（< 20），复杂度可控 |
| 坚果云 API 限频 | 同步失败 | 同步操作仅在用户主动触发时执行，不自动轮询 |

## 13. 未来扩展

- **自动同步**：在 `cmd_switch`/`cmd_add` 等命令后自动触发同步（需用户在配置中启用）
- **同步历史**：保留最近 N 次同步的变更记录，支持回滚
- **多端同步状态**：在 `sync status` 中显示所有已知设备的最后同步时间
- **端到端加密增强**：使用 X25519 + AES-256-GCM 替代 Fernet，提供更强的安全性
