"""Internationalization support."""

from pathlib import Path

LANG_FILE = Path.home() / ".ccprofile" / "language"
LANGUAGES = ("zh", "en")
_current_lang = "zh"

STRINGS = {
    # ── Language settings (for menu integration by Implementor B) ──
    "menu.language_settings": {
        "zh": "语言设置",
        "en": "Language Settings",
    },
    "menu.language_changed": {
        "zh": "语言已切换为中文。",
        "en": "Language switched to English.",
    },
    "menu.select_language": {
        "zh": "选择语言",
        "en": "Select Language",
    },
    "menu.lang_zh": {
        "zh": "中文",
        "en": "Chinese",
    },
    "menu.lang_en": {
        "zh": "English",
        "en": "English",
    },

    # ── menu.py ──
    "menu.switch_profile": {"zh": "切换配置", "en": "Switch Profile"},
    "menu.manage_profiles": {"zh": "管理配置", "en": "Manage Profiles"},
    "menu.provider_mgmt": {"zh": "提供商管理", "en": "Provider Management"},
    "menu.system_settings": {"zh": "系统设置", "en": "System Settings"},
    "menu.exit": {"zh": "退出", "en": "Exit"},
    "menu.list_profiles": {"zh": "列出所有配置", "en": "List All Profiles"},
    "menu.show_current": {"zh": "显示当前活动配置", "en": "Show Active Profile"},
    "menu.show_profile": {"zh": "显示配置详情", "en": "Show Profile Details"},
    "menu.view_profiles": {"zh": "查看配置", "en": "View Profiles"},
    "menu.add_profile": {"zh": "添加配置", "en": "Add Profile"},
    "menu.edit_profile": {"zh": "编辑配置", "en": "Edit Profile"},
    "menu.switch_teams": {"zh": "切换 Teams 模式", "en": "Switch Teams Mode"},
    "menu.delete_profile": {"zh": "删除配置", "en": "Delete Profile"},
    "menu.init_reset": {"zh": "初始化 / 重置密钥", "en": "Init / Reset Key"},
    "menu.add_provider": {"zh": "添加提供商", "en": "Add Provider"},
    "menu.list_providers": {"zh": "列出所有提供商", "en": "List All Providers"},
    "menu.show_provider": {"zh": "显示提供商详情", "en": "Show Provider Details"},
    "menu.edit_provider": {"zh": "编辑提供商", "en": "Edit Provider"},
    "menu.delete_provider": {"zh": "删除提供商", "en": "Delete Provider"},
    "menu.profile_name_prompt": {"zh": "配置名称", "en": "Profile Name"},
    "menu.canceled": {"zh": "已取消。", "en": "Canceled."},
    "menu.single_mode_desc": {
        "zh": "单一模式 — 一个提供商对应所有模型",
        "en": "Single Mode — One provider for all models",
    },
    "menu.mixed_mode_desc": {
        "zh": "混合模式 — 不同模型使用不同提供商",
        "en": "Mixed Mode — Different providers for different models",
    },
    "menu.select_mode": {"zh": "选择配置模式", "en": "Select Profile Mode"},
    "menu.provider_name_prompt": {"zh": "提供商名称", "en": "Provider Name"},
    "menu.op_canceled": {"zh": "操作已取消。", "en": "Operation canceled."},
    "menu.not_initialized": {
        "zh": "系统尚未初始化，请先进入「系统设置」→「初始化」",
        "en": "System not initialized. Go to System Settings → Init first.",
    },
    "menu.current_profile": {"zh": "当前配置", "en": "Current Profile"},
    "menu.select_op": {"zh": "请选择操作", "en": "Select an operation"},
    "menu.goodbye": {"zh": "再见！", "en": "Goodbye!"},
    "menu.banner": {
        "zh": "ccprofile — Claude Code 配置管理",
        "en": "ccprofile — Claude Code Configuration Manager",
    },

    # ── commands.py ──
    "cmd.init_exists_warn": {
        "zh": "密钥文件已存在。重新生成将导致现有配置不可读！继续？",
        "en": "Key file exists. Regenerating will make existing profiles unreadable! Continue?",
    },
    "cmd.init_provider_warn": {
        "zh": "重新初始化将删除现有提供商配置 providers.enc。确认？",
        "en": "Re-initializing will delete existing provider config providers.enc. Confirm?",
    },
    "cmd.canceled": {"zh": "已取消。", "en": "Canceled."},
    "cmd.init_done": {"zh": "初始化完成。密钥已生成", "en": "Initialization complete. Key generated"},
    "cmd.add_exists": {
        "zh": "错误: 配置 '{name}' 已存在。请使用 edit 命令修改。",
        "en": "Error: Profile '{name}' already exists. Use edit to modify.",
    },
    "cmd.add_mixed_intro": {
        "zh": "添加混合配置 '{name}'。按回车使用默认值。",
        "en": "Adding mixed profile '{name}'. Press Enter for defaults.",
    },
    "cmd.add_noninteractive_error": {
        "zh": "错误: 非交互模式需要 -t, -u, -m 参数。",
        "en": "Error: Non-interactive mode requires -t, -u, -m arguments.",
    },
    "cmd.add_single_intro": {
        "zh": "添加配置 '{name}'。按回车使用默认值。",
        "en": "Adding profile '{name}'. Press Enter for defaults.",
    },
    "cmd.add_done": {"zh": "配置 '{name}' 已添加。", "en": "Profile '{name}' added."},
    "cmd.switch_not_found": {
        "zh": "错误: 配置 '{name}' 不存在。",
        "en": "Error: Profile '{name}' does not exist.",
    },
    "cmd.switch_pick": {"zh": "选择要切换的配置", "en": "Select profile to switch to"},
    "cmd.switch_no_provider": {
        "zh": "错误: 暂无可用提供商。请先使用 'ccprofile provider add' 添加提供商。",
        "en": "Error: No providers available. Use 'ccprofile provider add' first.",
    },
    "cmd.switch_provider_not_found": {
        "zh": "错误: 提供商 '{name}' 不存在。",
        "en": "Error: Provider '{name}' does not exist.",
    },
    "cmd.switch_stop_proxy_warn": {
        "zh": "警告: 停止旧代理失败，将继续尝试启动新代理。",
        "en": "Warning: Failed to stop old proxy, will try to start new one.",
    },
    "cmd.switch_start_proxy_error": {
        "zh": "错误: 启动代理失败。",
        "en": "Error: Failed to start proxy.",
    },
    "cmd.switch_stop_proxy_warn2": {
        "zh": "警告: 停止代理失败，但将继续切换配置。",
        "en": "Warning: Failed to stop proxy, but will continue switching profile.",
    },
    "cmd.switch_done": {
        "zh": "已切换到配置 '{name}' ({mode})。",
        "en": "Switched to profile '{name}' ({mode}).",
    },
    "cmd.mode_single": {"zh": "单一模式", "en": "Single Mode"},
    "cmd.mode_mixed": {"zh": "混合模式", "en": "Mixed Mode"},
    "cmd.list_empty": {"zh": "暂无配置。", "en": "No profiles yet."},
    "cmd.list_total": {"zh": "共 {n} 个", "en": "{n} total"},
    "cmd.show_pick": {"zh": "选择要查看的配置", "en": "Select profile to view"},
    "cmd.show_not_found": {
        "zh": "错误: 配置 '{name}' 不存在。",
        "en": "Error: Profile '{name}' does not exist.",
    },
    "cmd.edit_pick": {"zh": "选择要编辑的配置", "en": "Select profile to edit"},
    "cmd.edit_not_found": {
        "zh": "错误: 配置 '{name}' 不存在。",
        "en": "Error: Profile '{name}' does not exist.",
    },
    "cmd.edit_intro": {
        "zh": "编辑配置 '{name}'。按回车保留当前值。",
        "en": "Editing profile '{name}'. Press Enter to keep current value.",
    },
    "cmd.edit_teams_conflict": {
        "zh": "错误: 不能同时指定 --enable-teams 和 --disable-teams。",
        "en": "Error: Cannot specify both --enable-teams and --disable-teams.",
    },
    "cmd.edit_done": {"zh": "配置 '{name}' 已更新。", "en": "Profile '{name}' updated."},
    "cmd.delete_pick": {"zh": "选择要删除的配置", "en": "Select profile to delete"},
    "cmd.delete_not_found": {
        "zh": "错误: 配置 '{name}' 不存在。",
        "en": "Error: Profile '{name}' does not exist.",
    },
    "cmd.delete_active_warn": {
        "zh": "警告: '{name}' 是当前活动配置。",
        "en": "Warning: '{name}' is the current active profile.",
    },
    "cmd.delete_confirm": {
        "zh": "确认删除配置 '{name}'？",
        "en": "Confirm deleting profile '{name}'?",
    },
    "cmd.delete_done": {"zh": "配置 '{name}' 已删除。", "en": "Profile '{name}' deleted."},
    "cmd.current_none": {"zh": "当前无活动配置。", "en": "No active profile."},
    "cmd.current_missing": {
        "zh": "活动配置 '{name}' 不存在（可能已被删除）。",
        "en": "Active profile '{name}' not found (may have been deleted).",
    },
    "cmd.teams_no_active": {
        "zh": "错误: 当前无活动配置。请先使用 'switch' 切换到某个配置。",
        "en": "Error: No active profile. Use 'switch' to select one first.",
    },
    "cmd.teams_missing": {
        "zh": "错误: 活动配置 '{active}' 不存在。",
        "en": "Error: Active profile '{active}' does not exist.",
    },
    "cmd.teams_done": {
        "zh": "配置 '{name}' 的 Agent Teams 模式{status}。",
        "en": "Agent Teams mode {status} for profile '{name}'.",
    },
    "cmd.teams_enabled": {"zh": "已启用", "en": "enabled"},
    "cmd.teams_disabled": {"zh": "已禁用", "en": "disabled"},
    "cmd.proxy_running": {"zh": "代理状态: 运行中", "en": "Proxy status: running"},
    "cmd.proxy_pid": {"zh": "PID", "en": "PID"},
    "cmd.proxy_port": {"zh": "端口", "en": "Port"},
    "cmd.proxy_mapping": {"zh": "模型映射", "en": "Model mapping"},
    "cmd.proxy_stopped": {"zh": "代理状态: 未运行", "en": "Proxy status: not running"},
    "cmd.proxy_config_port": {"zh": "配置端口", "en": "Config port"},

    # ── prompts.py ──
    "prompt.select_label": {"zh": "选择{label}", "en": "Select {label}"},
    "prompt.disable_options": {"zh": "禁用选项", "en": "Disable Options"},
    "prompt.enable_options": {"zh": "启用选项", "en": "Enable Options"},
    "prompt.disable_flag": {"zh": "禁用: {desc}", "en": "Disable: {desc}"},
    "prompt.enable_flag": {"zh": "启用: {desc}", "en": "Enable: {desc}"},
    "prompt.hooks_config": {
        "zh": "推送通知配置 (留空跳过)",
        "en": "Push notification config (skip if empty)",
    },
    "prompt.bark_key": {"zh": "Bark Key", "en": "Bark Key"},
    "prompt.host_label": {"zh": "主机名标签", "en": "Host Label"},
    "prompt.notify_sound": {"zh": "通知铃声", "en": "Notification Sound"},
    "prompt.required_field": {
        "zh": "错误: {label} 为必填项。",
        "en": "Error: {label} is required.",
    },

    # ── constants.py — FIELDS labels ──
    "fields.auth_token": {"zh": "API 密钥", "en": "API Key"},
    "fields.base_url": {"zh": "API 基础地址", "en": "API Base URL"},
    "fields.model": {"zh": "模型 (opus/sonnet/haiku)", "en": "Model (opus/sonnet/haiku)"},
    "fields.effort_level": {
        "zh": "努力等级 (low/medium/high)",
        "en": "Effort Level (low/medium/high)",
    },
    "fields.default_model": {"zh": "默认模型", "en": "Default Model"},
    "fields.haiku_override": {"zh": "Haiku 模型覆盖", "en": "Haiku Model Override"},
    "fields.sonnet_override": {"zh": "Sonnet 模型覆盖", "en": "Sonnet Model Override"},
    "fields.opus_override": {"zh": "Opus 模型覆盖", "en": "Opus Model Override"},

    # ── constants.py — DISABLE_FLAGS labels ──
    "disable.telemetry": {"zh": "禁用遥测", "en": "Disable Telemetry"},
    "disable.autoupdater": {"zh": "禁用自动更新", "en": "Disable Auto-updater"},
    "disable.experimental": {
        "zh": "禁用实验性功能",
        "en": "Disable Experimental Features",
    },
    "disable.nonessential": {
        "zh": "禁用非必要流量",
        "en": "Disable Non-essential Traffic",
    },

    # ── constants.py — HOOKS_FIELDS labels ──
    "hooks.bark_key": {"zh": "Bark Key", "en": "Bark Key"},
    "hooks.host_label": {"zh": "主机名标签", "en": "Host Label"},
    "hooks.sound": {"zh": "通知铃声", "en": "Notification Sound"},

    # ── constants.py — PROVIDER_FIELDS labels ──
    "provider.base_url": {
        "zh": "API 基础地址或 /v1/messages 端点",
        "en": "API Base URL or /v1/messages endpoint",
    },
    "provider.api_key": {"zh": "API 密钥", "en": "API Key"},
    "provider.models": {"zh": "可用模型 (逗号分隔)", "en": "Available Models (comma-separated)"},

    # ── constants.py — panel titles (used by display.py, referenced here for i18n) ──
    "panel.profile_list": {"zh": "配置列表", "en": "Profile List"},
    "panel.provider_list": {"zh": "提供商列表", "en": "Provider List"},
    "panel.provider": {"zh": "提供商", "en": "Provider"},

    # ── cli.py — argparse help strings ──
    "cli.description": {
        "zh": "Claude Code API 配置管理工具",
        "en": "Claude Code API Configuration Manager",
    },
    "cli.init_help": {"zh": "初始化：生成加密密钥", "en": "Initialize: generate encryption key"},
    "cli.add_help": {"zh": "添加配置", "en": "Add profile"},
    "cli.add_name_help": {"zh": "配置名称", "en": "Profile name"},
    "cli.add_mode_help": {
        "zh": "配置模式 (single/mixed)",
        "en": "Profile mode (single/mixed)",
    },
    "cli.add_token_help": {"zh": "API 密钥", "en": "API key"},
    "cli.add_url_help": {"zh": "API 基础地址", "en": "API base URL"},
    "cli.add_model_help": {"zh": "模型 (opus/sonnet/haiku)", "en": "Model (opus/sonnet/haiku)"},
    "cli.add_effort_help": {"zh": "努力等级", "en": "Effort level"},
    "cli.add_anthropic_model_help": {"zh": "默认模型", "en": "Default model"},
    "cli.add_haiku_model_help": {"zh": "Haiku 模型覆盖", "en": "Haiku model override"},
    "cli.add_sonnet_model_help": {"zh": "Sonnet 模型覆盖", "en": "Sonnet model override"},
    "cli.add_opus_model_help": {"zh": "Opus 模型覆盖", "en": "Opus model override"},
    "cli.add_disable_all_help": {
        "zh": "启用所有禁用标志",
        "en": "Enable all disable flags",
    },
    "cli.add_enable_teams_help": {
        "zh": "启用 Agent Teams 模式",
        "en": "Enable Agent Teams mode",
    },
    "cli.add_bark_key_help": {"zh": "Bark 推送 Key", "en": "Bark push key"},
    "cli.add_host_label_help": {"zh": "主机名标签", "en": "Host label"},
    "cli.add_notify_sound_help": {"zh": "通知铃声", "en": "Notification sound"},
    "cli.add_hooks_json_help": {
        "zh": "自定义 hooks JSON 配置",
        "en": "Custom hooks JSON config",
    },
    "cli.switch_help": {"zh": "切换配置", "en": "Switch profile"},
    "cli.switch_name_help": {
        "zh": "配置名称（省略则弹出选择）",
        "en": "Profile name (omit to pick interactively)",
    },
    "cli.list_help": {"zh": "列出所有配置", "en": "List all profiles"},
    "cli.show_help": {"zh": "显示配置详情", "en": "Show profile details"},
    "cli.show_name_help": {
        "zh": "配置名称（省略则弹出选择）",
        "en": "Profile name (omit to pick interactively)",
    },
    "cli.edit_help": {"zh": "编辑配置", "en": "Edit profile"},
    "cli.edit_name_help": {
        "zh": "配置名称（省略则弹出选择）",
        "en": "Profile name (omit to pick interactively)",
    },
    "cli.edit_enable_teams_help": {
        "zh": "启用 Agent Teams 模式",
        "en": "Enable Agent Teams mode",
    },
    "cli.edit_disable_teams_help": {
        "zh": "禁用 Agent Teams 模式",
        "en": "Disable Agent Teams mode",
    },
    "cli.delete_help": {"zh": "删除配置", "en": "Delete profile"},
    "cli.delete_name_help": {
        "zh": "配置名称（省略则弹出选择）",
        "en": "Profile name (omit to pick interactively)",
    },
    "cli.current_help": {
        "zh": "显示当前活动配置",
        "en": "Show active profile",
    },
    "cli.teams_help": {
        "zh": "切换 Agent Teams 模式",
        "en": "Switch Agent Teams mode",
    },
    "cli.teams_action_help": {
        "zh": "操作 (on/off/toggle，默认 toggle)",
        "en": "Action (on/off/toggle, default toggle)",
    },
    "cli.teams_apply_help": {
        "zh": "同时更新 settings.json 使变更立即生效",
        "en": "Also update settings.json to apply changes immediately",
    },
    "cli.provider_help": {"zh": "提供商管理", "en": "Provider management"},
    "cli.provider_add_help": {"zh": "添加提供商", "en": "Add provider"},
    "cli.provider_name_help": {"zh": "提供商名称", "en": "Provider name"},
    "cli.provider_url_help": {
        "zh": "API 基础地址或 /v1/messages 端点",
        "en": "API base URL or /v1/messages endpoint",
    },
    "cli.provider_key_help": {"zh": "API 密钥", "en": "API key"},
    "cli.provider_models_help": {
        "zh": "可用模型 (逗号分隔)",
        "en": "Available models (comma-separated)",
    },
    "cli.provider_list_help": {
        "zh": "列出所有提供商",
        "en": "List all providers",
    },
    "cli.provider_show_help": {
        "zh": "显示提供商详情",
        "en": "Show provider details",
    },
    "cli.provider_show_name_help": {
        "zh": "提供商名称（省略则弹出选择）",
        "en": "Provider name (omit to pick interactively)",
    },
    "cli.provider_edit_help": {"zh": "编辑提供商", "en": "Edit provider"},
    "cli.provider_edit_name_help": {
        "zh": "提供商名称（省略则弹出选择）",
        "en": "Provider name (omit to pick interactively)",
    },
    "cli.provider_delete_help": {"zh": "删除提供商", "en": "Delete provider"},
    "cli.provider_delete_name_help": {
        "zh": "提供商名称（省略则弹出选择）",
        "en": "Provider name (omit to pick interactively)",
    },
    "cli.proxy_help": {"zh": "代理管理", "en": "Proxy management"},
    "cli.proxy_status_help": {"zh": "显示代理状态", "en": "Show proxy status"},
    "cli.proxy_stop_help": {"zh": "停止代理", "en": "Stop proxy"},
    "cli.proxy_logs_help": {"zh": "显示代理日志", "en": "Show proxy logs"},
    "cli.proxy_logs_lines_help": {
        "zh": "显示最后 N 行 (默认 50)",
        "en": "Show last N lines (default 50)",
    },

    # ── storage.py ──
    "storage.migration_done": {
        "zh": "已将旧配置迁移到 {dir}：{files}",
        "en": "Migrated legacy config to {dir}: {files}",
    },

    # ── terminal.py ──
    "term.select_prompt": {"zh": "请选择", "en": "Select"},
    "term.select_hint": {
        "zh": "↑↓ 选择 · Enter 确认 · Esc 取消",
        "en": "↑↓ Select · Enter Confirm · Esc Cancel",
    },
    "term.yes": {"zh": "是", "en": "Yes"},
    "term.no": {"zh": "否", "en": "No"},
    "term.cancelled": {"zh": "已取消", "en": "Canceled"},

    # ── cmd_show display labels ──
    "cmd.show.model": {"zh": "模型", "en": "Model"},
    "cmd.show.effort": {"zh": "努力等级", "en": "Effort Level"},
    "cmd.show.teams_mode": {"zh": "Teams 模式", "en": "Teams Mode"},
    "cmd.show.teams_enabled": {"zh": "✓ 已启用", "en": "✓ Enabled"},
    "cmd.show.teams_disabled": {"zh": "未启用", "en": "Not Enabled"},
    "cmd.show.connection": {"zh": "连接", "en": "Connection"},
    "cmd.show.model_override": {"zh": "模型覆盖", "en": "Model Override"},
    "cmd.show.flags": {"zh": "标志", "en": "Flags"},
    "cmd.show.flags_disabled": {"zh": "禁用", "en": "Disabled"},
    "cmd.show.flags_enabled": {"zh": "启用", "en": "Enabled"},
    "cmd.show.push_notification": {"zh": "推送通知", "en": "Push Notification"},
    "cmd.show.custom_hooks": {"zh": "自定义 hooks 配置", "en": "Custom Hooks Config"},
    "cmd.show.not_configured": {"zh": "未配置", "en": "Not Configured"},
    "cmd.show.proxy_port": {"zh": "代理端口", "en": "Proxy Port"},
    "cmd.show.model_mapping": {"zh": "模型映射", "en": "Model Mapping"},
    "cmd.show.bark": {"zh": "Bark", "en": "Bark"},

    # ── cmd_show proxy status ──
    "cmd.proxy_pid": {"zh": "PID", "en": "PID"},
    "cmd.proxy_port": {"zh": "端口", "en": "Port"},
    "cmd.proxy_config_port": {"zh": "配置端口", "en": "Config Port"},
    "cmd.proxy_model_mapping": {"zh": "模型映射", "en": "Model Mapping"},

    # ── additional display labels ──
    "cmd.show.default_model": {"zh": "默认模型", "en": "Default Model"},

    # ── commands.py ──
    "cmd.hooks_json_error": {
        "zh": "错误: --hooks-json 不是有效的 JSON: {error}",
        "en": "Error: --hooks-json is not valid JSON: {error}",
    },

    # ── prompts.py ──
    "prompt.no_provider_error": {
        "zh": "错误: 暂无可用提供商。请先使用 'ccprofile provider add' 添加提供商。",
        "en": "Error: No providers available. Use 'ccprofile provider add' first.",
    },
    "prompt.configure_slot": {
        "zh": "配置 {slot} 槽位",
        "en": "Configure {slot} slot",
    },
    "prompt.skip_slot": {
        "zh": "跳过此槽位",
        "en": "Skip this slot",
    },
    "prompt.select_provider_for_slot": {
        "zh": "选择 {slot} 槽位的提供商",
        "en": "Select provider for {slot} slot",
    },
    "prompt.provider_no_models": {
        "zh": "错误: 提供商 '{name}' 没有可用模型，跳过此槽位。",
        "en": "Error: Provider '{name}' has no available models, skipping slot.",
    },
    "prompt.select_model": {
        "zh": "选择模型 ({provider})",
        "en": "Select model ({provider})",
    },
    "prompt.mixed_min_one": {
        "zh": "错误: 混合配置至少需要配置一个模型槽位。",
        "en": "Error: Mixed profile requires at least one model slot configured.",
    },
    "prompt.select_default_model": {
        "zh": "选择默认模型",
        "en": "Select default model",
    },
    "prompt.select_effort": {
        "zh": "选择努力等级",
        "en": "Select effort level",
    },
    "prompt.hooks_config_skip": {
        "zh": "推送通知配置 (留空跳过)",
        "en": "Push notification config (skip if empty)",
    },

    # ── provider.py ──
    "prov.url_scheme_error": {
        "zh": "错误: API 地址必须以 http:// 或 https:// 开头。",
        "en": "Error: API address must start with http:// or https://.",
    },
    "prov.url_format_error": {
        "zh": "错误: API 地址格式无效。",
        "en": "Error: Invalid API address format.",
    },
    "prov.models_empty_error": {
        "zh": "错误: --models 包含空模型名，请检查逗号分隔格式。",
        "en": "Error: --models contains empty model name, check comma separation.",
    },
    "prov.models_whitespace_error": {
        "zh": "错误: 模型名 '{model}' 不能包含空白字符。",
        "en": "Error: Model name '{model}' cannot contain whitespace.",
    },
    "prov.models_duplicate_error": {
        "zh": "错误: --models 中模型名重复: {model}",
        "en": "Error: duplicate model name in --models: {model}",
    },
    "prov.add_exists": {
        "zh": "错误: 提供商 '{name}' 已存在。请使用 edit 命令修改。",
        "en": "Error: Provider '{name}' already exists. Use edit to modify.",
    },
    "prov.add_noninteractive_all_required": {
        "zh": "错误: 非交互添加提供商时必须同时提供 --url、--key 和 --models。缺少: {missing}",
        "en": "Error: Non-interactive provider add requires --url, --key and --models. Missing: {missing}",
    },
    "prov.add_intro": {
        "zh": "添加提供商 '{name}'。按回车使用默认值。",
        "en": "Adding provider '{name}'. Press Enter for defaults.",
    },
    "prov.add_empty_error": {
        "zh": "错误: --url、--key 和 --models 不能为空。",
        "en": "Error: --url, --key and --models cannot be empty.",
    },
    "prov.add_done": {
        "zh": "提供商 '{name}' 已添加。",
        "en": "Provider '{name}' added.",
    },
    "prov.list_empty": {
        "zh": "暂无提供商。",
        "en": "No providers yet.",
    },
    "prov.list_total": {"zh": "共 {n} 个", "en": "{n} total"},
    "prov.list_models": {"zh": "模型", "en": "Models"},
    "prov.show_pick": {"zh": "选择要查看的提供商", "en": "Select provider to view"},
    "prov.show_not_found": {
        "zh": "错误: 提供商 '{name}' 不存在。",
        "en": "Error: Provider '{name}' does not exist.",
    },
    "prov.edit_pick": {"zh": "选择要编辑的提供商", "en": "Select provider to edit"},
    "prov.edit_not_found": {
        "zh": "错误: 提供商 '{name}' 不存在。",
        "en": "Error: Provider '{name}' does not exist.",
    },
    "prov.edit_intro": {
        "zh": "编辑提供商 '{name}'。按回车保留当前值。",
        "en": "Editing provider '{name}'. Press Enter to keep current value.",
    },
    "prov.edit_done": {
        "zh": "提供商 '{name}' 已更新。",
        "en": "Provider '{name}' updated.",
    },
    "prov.delete_pick": {"zh": "选择要删除的提供商", "en": "Select provider to delete"},
    "prov.delete_not_found": {
        "zh": "错误: 提供商 '{name}' 不存在。",
        "en": "Error: Provider '{name}' does not exist.",
    },
    "prov.delete_in_use": {
        "zh": "错误: 提供商 '{name}' 正被以下配置使用: {profiles}",
        "en": "Error: Provider '{name}' is in use by the following profiles: {profiles}",
    },
    "prov.delete_in_use_hint": {
        "zh": "请先删除或修改这些配置后再删除提供商。",
        "en": "Delete or modify these profiles first before deleting the provider.",
    },
    "prov.delete_confirm": {
        "zh": "确认删除提供商 '{name}'？",
        "en": "Confirm deleting provider '{name}'?",
    },
    "prov.delete_done": {
        "zh": "提供商 '{name}' 已删除。",
        "en": "Provider '{name}' deleted.",
    },
    "prov.panel_title": {"zh": "提供商列表", "en": "Provider List"},
    "prov.panel_provider": {"zh": "提供商", "en": "Provider"},
    "prov.api_address": {"zh": "API 地址", "en": "API Address"},
    "prov.api_key": {"zh": "API 密钥", "en": "API Key"},
    "prov.available_models": {"zh": "可用模型", "en": "Available Models"},

    # ── terminal.py ──
    "term.select_numbered": {
        "zh": "请选择 [1-{total}] (默认 {default})",
        "en": "Select [1-{total}] (default {default})",
    },

    # ── picker.py ──
    "picker.select_profile": {"zh": "选择配置", "en": "Select Profile"},
    "picker.no_profiles_init": {"zh": "暂无配置。请先 init 并 add。", "en": "No profiles yet. Run init and add first."},
    "picker.no_profiles_add": {"zh": "暂无配置。请先添加。", "en": "No profiles yet. Add one first."},
    "picker.select_provider": {"zh": "选择提供商", "en": "Select Provider"},
    "picker.no_providers": {"zh": "暂无提供商。请先添加。", "en": "No providers yet. Add one first."},
    "picker.cancel": {"zh": "取消", "en": "Cancel"},

    # ── display.py ──
    "display.proxy_running": {"zh": "运行中", "en": "Running"},
    "display.proxy_stopped": {"zh": "已停止", "en": "Stopped"},

    # ── proxy_process.py ──
    "proxy.already_running": {"zh": "代理已在运行中 (PID: {pid})", "en": "Proxy already running (PID: {pid})"},
    "proxy.started": {"zh": "代理已启动 (PID: {pid}), 端口: {port}", "en": "Proxy started (PID: {pid}), port: {port}"},
    "proxy.start_timeout": {"zh": "错误: 代理启动超时，未收到子进程就绪信号 (端口: {port})", "en": "Error: Proxy start timed out, no ready signal (port: {port})"},
    "proxy.start_exit": {"zh": "错误: 代理子进程已退出 (退出码: {code})，端口 {port} 可能已被占用", "en": "Error: Proxy subprocess exited (code: {code}), port {port} may be in use"},
    "proxy.start_failed": {"zh": "错误: 启动代理失败: {error}", "en": "Error: Failed to start proxy: {error}"},
    "proxy.not_running": {"zh": "代理未运行", "en": "Proxy not running"},
    "proxy.pid_not_running": {"zh": "代理进程 (PID: {pid}) 未运行，清理 PID 文件", "en": "Proxy (PID: {pid}) not running, cleaned PID file"},
    "proxy.pid_stale": {"zh": "代理 PID 文件已过期或不匹配 (PID: {pid})，已清理", "en": "Proxy PID file stale or mismatched (PID: {pid}), cleaned"},
    "proxy.stopped": {"zh": "代理已停止 (PID: {pid})", "en": "Proxy stopped (PID: {pid})"},
    "proxy.stop_failed": {"zh": "错误: 停止代理失败: {error}", "en": "Error: Failed to stop proxy: {error}"},
    "proxy.log_title": {"zh": "代理日志 ({path}) - 最后 {n} 行:", "en": "Proxy log ({path}) - last {n} lines:"},
    "proxy.log_missing": {"zh": "代理日志文件不存在。", "en": "Proxy log file does not exist."},
    "proxy.log_total": {"zh": "共 {n} 行日志。", "en": "{n} total log lines."},
    "proxy.log_read_error": {"zh": "错误: 读取日志文件失败: {error}", "en": "Error: Failed to read log file: {error}"},
    "proxy.lines_invalid": {"zh": "行数必须大于等于 1。", "en": "Line count must be at least 1."},

    # ── crypto.py ──
    "crypto.not_initialized": {"zh": "错误: 未初始化。请先运行: {hint}", "en": "Error: Not initialized. Run first: {hint}"},
    "crypto.decrypt_failed": {"zh": "错误: 解密失败，密钥可能不匹配或数据已损坏。请尝试重新初始化。", "en": "Error: Decryption failed. Key mismatch or corrupted data. Try re-initializing."},
}

# ── Field key → i18n key mappings (used by prompts.py and commands.py) ──

FIELD_I18N_KEYS = {
    "ANTHROPIC_AUTH_TOKEN": "fields.auth_token",
    "ANTHROPIC_BASE_URL": "fields.base_url",
    "model": "fields.model",
    "effortLevel": "fields.effort_level",
    "ANTHROPIC_MODEL": "fields.default_model",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "fields.haiku_override",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "fields.sonnet_override",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "fields.opus_override",
}

DISABLE_FLAG_I18N_KEYS = {
    "DISABLE_TELEMETRY": "disable.telemetry",
    "DISABLE_AUTOUPDATER": "disable.autoupdater",
    "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "disable.experimental",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "disable.nonessential",
}

HOOKS_FIELD_I18N_KEYS = {
    "bark_key": "hooks.bark_key",
    "host_label": "hooks.host_label",
    "sound": "hooks.sound",
}

PROVIDER_FIELD_I18N_KEYS = {
    "base_url": "provider.base_url",
    "api_key": "provider.api_key",
    "models": "provider.models",
}


def init_language():
    global _current_lang
    if LANG_FILE.exists():
        val = LANG_FILE.read_text().strip()
        if val in LANGUAGES:
            _current_lang = val


def get_language():
    return _current_lang


def set_language(lang):
    global _current_lang
    _current_lang = lang
    LANG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LANG_FILE.write_text(lang)


def t(key, **kwargs):
    entry = STRINGS.get(key, {})
    text = entry.get(_current_lang, entry.get("zh", key))
    if kwargs:
        return text.format(**kwargs)
    return text
