import json
import hashlib
import hmac
import difflib
import io
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import tomllib
import zipfile
from pathlib import Path

from core import db
from core.codex_source import (
    find_running_codex_path,
    find_windowsapps_codex_path,
    find_windowsapps_codex_path_by_package,
    portable_app_needs_update,
    prepare_portable_codex_path,
    read_processes_in_directory,
    request_process_close,
    read_source_signature,
    read_running_codex_commands,
    read_running_codex_processes,
    write_source_signature,
)
from core.config_store import load_config, save_config
from core.constants import DB_PATH, DEFAULT_PROFILE_ROOT, PORTABLE_APP_DIR_NAME
from core.auth_service import auth_kind, auth_tokens, extract_auth
from core.logger import get_logger
from core.oauth_service import login_with_browser
from core.path_utils import check_directory_writable, format_health_status, is_reparse_point, normalize_path_for_match, remove_readonly_path, sanitize_profile_name
from core.profile_service import (
    apply_profile,
    get_active_auth_path,
    get_active_codex_dir,
    get_active_config_path,
    get_auth_credentials_store,
    get_profile_status,
    import_auth_json_profile,
    import_active_profile,
    ensure_profile_config_path,
    prepare_profile_codex_home,
    get_profile_auth_path,
    sync_codex_home_to_profile,
)
from core.instruction_service import (
    delete_instruction_template as delete_instruction_template_service,
    disable_instruction_template as disable_instruction_template_service,
    enable_instruction_template as enable_instruction_template_service,
    ensure_builtin_instruction_templates,
    list_instruction_templates as list_instruction_templates_service,
    save_instruction_template as save_instruction_template_service,
    sync_instruction_template as sync_instruction_template_service,
)
from core.toml_config_service import read_toml_config as read_toml_config_service, save_toml_config as save_toml_config_service
from core.secure_store import protect_bytes, unprotect_bytes
from core.usage_service import (
    get_cached_profile_usage,
    refresh_all_profile_usage as refresh_all_profile_usage_cache,
    refresh_profile_usage as refresh_profile_usage_cache,
    remove_cached_usage,
)
from core.workspace_service import (
    delete_mcp_server as delete_mcp_server_service,
    install_skill as install_skill_service,
    list_sessions as list_sessions_service,
    read_workspace,
    remove_skill as remove_skill_service,
    save_agents as save_agents_service,
    save_mcp_server as save_mcp_server_service,
    set_mcp_enabled as set_mcp_enabled_service,
    set_skill_enabled as set_skill_enabled_service,
)


logger = get_logger(__name__)
SYSTEM_PROFILE_NAME = "__system__"
CODEX_SKIN_PORT_START = 19335
CODEX_SKIN_PORT_COUNT = 100


def ok(data=None):
    """生成统一成功响应，供 Electron 界面稳定解析。"""
    return {"ok": True, "data": data or {}, "error": ""}


def fail(message):
    """生成统一失败响应，避免把异常对象直接泄露给界面。"""
    return {"ok": False, "data": {}, "error": str(message)}


def invoke(command, payload=None):
    """按白名单分发桥接命令。"""
    payload = payload or {}
    commands = {
        "create_profile": create_profile,
        "create_oauth_profile": create_oauth_profile,
        "create_auth_file_profile": create_auth_file_profile,
        "delete_profile": delete_profile,
        "export_profile_backup": export_profile_backup,
        "get_app_state": get_app_state,
        "get_runtime_status": get_runtime_status,
        "get_shell_snapshot": get_shell_snapshot,
        "get_diagnostics": get_diagnostics,
        "get_profile_detail": get_profile_detail,
        "get_profile_health": get_profile_health,
        "get_profile_launch_settings": get_profile_launch_settings,
        "get_usage_history": get_usage_history,
        "get_workspace": get_workspace,
        "get_workspace_snapshot": get_workspace_snapshot,
        "import_profile_backup": import_profile_backup,
        "install_skill": install_skill,
        "list_sessions": list_sessions,
        "list_instruction_templates": list_instruction_templates,
        "save_instruction_template": save_instruction_template,
        "delete_instruction_template": delete_instruction_template,
        "enable_instruction_template": enable_instruction_template,
        "disable_instruction_template": disable_instruction_template,
        "launch_profile": launch_profile,
        "list_profiles": list_profiles,
        "refresh_all_profile_usage": refresh_all_profile_usage,
        "refresh_codex_source": refresh_codex_source,
        "refresh_profile_usage": refresh_profile_usage,
        "read_toml_config": read_toml_config,
        "remove_skill": remove_skill,
        "repair_profile": repair_profile,
        "rename_profile": rename_profile,
        "save_toml_config": save_toml_config,
        "save_agents": save_agents,
        "save_mcp_server": save_mcp_server,
        "save_profile_launch_settings": save_profile_launch_settings,
        "set_mcp_enabled": set_mcp_enabled,
        "set_skill_enabled": set_skill_enabled,
        "sync_toml_keys": sync_toml_keys,
        "delete_mcp_server": delete_mcp_server,
        "compare_toml_configs": compare_toml_configs,
        "set_share_system_config": set_share_system_config,
        "set_launch_mode": set_launch_mode,
        "set_codex_skin_enabled": set_codex_skin_enabled,
        "get_codex_skin_sessions": get_codex_skin_sessions,
        "ensure_codex_skin_sessions": ensure_codex_skin_sessions,
        "set_profile_root": set_profile_root,
        "open_path": open_path,
        "stop_profile": stop_profile,
    }
    handler = commands.get(command)
    if not handler:
        logger.warning("未知命令 命令=%s", command)
        return fail(f"未知命令：{command}")
    try:
        logger.info("命令开始 命令=%s", command)
        result = handler(payload)
        logger.info("命令成功 命令=%s", command)
        return ok(result)
    except Exception as exc:
        logger.exception("命令失败 命令=%s 错误=%s", command, exc)
        return fail(exc)


def get_app_state(_payload=None):
    """读取首页需要的账号切换状态。"""
    config = load_config()
    _normalize_profile_configs(config)
    ensure_builtin_instruction_templates()
    for profile_name in config.get("profiles", []):
        target = _resolve_config_target(config, {"profileName": profile_name})
        ensure_builtin_instruction_templates(_instruction_payload(target))
    running_processes = read_running_codex_processes()
    running_commands = _commands_from_processes(running_processes)
    return _build_app_state(config, running_processes, running_commands)


def get_runtime_status(_payload=None):
    """只读取客户端进程状态，供界面轻量轮询。"""
    config = load_config()
    running_processes = read_running_codex_processes()
    running_commands = _commands_from_processes(running_processes)
    legacy_profile = _get_legacy_system_running_profile(config, running_processes)
    return {
        "runningCount": _running_count_for_mode(config, running_processes, running_commands),
        "profiles": {
            profile_name: _is_profile_running(config, profile_name, running_commands, legacy_profile)
            for profile_name in config.get("profiles", [])
        },
    }


def get_shell_snapshot(_payload=None):
    """一次读取壳层状态和账号摘要，避免重复启动后端与扫描进程。"""
    config = load_config()
    _normalize_profile_configs(config)
    ensure_builtin_instruction_templates()
    for profile_name in config.get("profiles", []):
        target = _resolve_config_target(config, {"profileName": profile_name})
        ensure_builtin_instruction_templates(_instruction_payload(target))
    running_processes = read_running_codex_processes()
    running_commands = _commands_from_processes(running_processes)
    return {
        "appState": _build_app_state(config, running_processes, running_commands),
        "profiles": _build_profile_summaries(config, running_commands, running_processes),
    }


def _build_app_state(config, running_processes, running_commands):
    """用同一份配置和进程快照构造壳层状态。"""
    profiles = config.get("profiles", [])
    profile_root = Path(config.get("profile_root") or DEFAULT_PROFILE_ROOT)
    running_count = _running_count_for_mode(config, running_processes, running_commands)
    return {
        "codexCommandAvailable": _is_codex_command_available(config, running_processes),
        "activeAuthPath": str(get_active_auth_path()),
        "activeAuthExists": get_active_auth_path().exists(),
        "activeConfigPath": str(get_active_config_path()),
        "activeConfigExists": get_active_config_path().exists(),
        "activeProfile": config.get("active_profile", ""),
        "shareSystemConfig": True,
        "launchMode": _get_launch_mode(config),
        "codexSkinEnabled": bool(config.get("codex_skin_enabled")),
        "profileRoot": str(profile_root),
        "profileRootExists": profile_root.exists(),
        "profileCount": len(profiles),
        "runningCount": running_count,
        "authCredentialStore": get_auth_credentials_store(get_active_config_path()),
    }


def list_profiles(_payload=None):
    """读取账号列表和每个账号资料状态。"""
    config = load_config()
    _normalize_profile_configs(config)
    running_processes = read_running_codex_processes()
    running_commands = _commands_from_processes(running_processes)
    return {"profiles": _build_profile_summaries(config, running_commands, running_processes)}


def create_profile(payload):
    """新增账号，把当前默认 Codex 账号资料保存到账号目录。"""
    config = load_config()
    name = _validate_profile_name(config, payload.get("name", ""))
    profiles = config.setdefault("profiles", [])
    profiles.append(name)
    save_config(config)
    profile_dir = _get_profile_dir(config, name)
    logger.info("账号创建开始 名称=%s 目录=%s", name, profile_dir)
    try:
        import_active_profile(profile_dir)
    except Exception:
        _remove_path_if_inside_profile_root(config, profile_dir)
        profiles.remove(name)
        save_config(config)
        raise
    config["active_profile"] = name
    save_config(config)
    logger.info("账号创建成功 名称=%s 目录=%s", name, profile_dir)
    return _build_profile_summary(config, name, read_running_codex_commands())


def create_oauth_profile(payload):
    """通过浏览器授权新增账号，不覆盖当前默认 Codex 账号资料。"""
    config = load_config()
    name = _validate_profile_name(config, payload.get("name", ""))
    logger.info("浏览器授权账号创建开始 名称=%s", name)
    auth_json = login_with_browser()
    profiles = config.setdefault("profiles", [])
    profiles.append(name)
    save_config(config)
    profile_dir = _get_profile_dir(config, name)
    try:
        import_auth_json_profile(profile_dir, auth_json)
    except Exception:
        _remove_path_if_inside_profile_root(config, profile_dir)
        profiles.remove(name)
        save_config(config)
        raise
    save_config(config)
    logger.info("浏览器授权账号创建成功 名称=%s 目录=%s", name, profile_dir)
    return _build_profile_summary(config, name, read_running_codex_commands())


def create_auth_file_profile(payload):
    """通过本地 auth.json 文件新增账号，不覆盖当前默认 Codex 账号资料。"""
    config = load_config()
    name = _validate_profile_name(config, payload.get("name", ""))
    auth_path = Path(payload.get("authJsonPath", ""))
    logger.info("本地认证文件账号创建开始 名称=%s 认证文件=%s", name, auth_path)
    if not auth_path.is_file() or auth_path.name.lower() != "auth.json":
        raise ValueError("请选择有效的 auth.json 文件")
    try:
        auth_json = json.loads(auth_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("auth.json 内容不是有效的 JSON") from exc
    if not auth_kind(auth_json):
        raise ValueError("auth.json 内容不是有效的 Codex 或 API Key 登录信息")
    profiles = config.setdefault("profiles", [])
    profiles.append(name)
    save_config(config)
    profile_dir = _get_profile_dir(config, name)
    try:
        import_auth_json_profile(profile_dir, auth_json)
    except Exception:
        _remove_path_if_inside_profile_root(config, profile_dir)
        profiles.remove(name)
        save_config(config)
        raise
    logger.info("本地认证文件账号创建成功 名称=%s 目录=%s", name, profile_dir)
    return _build_profile_summary(config, name, read_running_codex_commands())


def rename_profile(payload):
    """修改账号名称，并移动对应资料目录。"""
    old_name = payload.get("oldName", "")
    config = load_config()
    if old_name not in config.get("profiles", []):
        raise ValueError("账号不存在")
    new_name = _validate_profile_name(config, payload.get("newName", ""), exclude_name=old_name)
    logger.info("账号重命名开始 原名称=%s 新名称=%s", old_name, new_name)
    if _is_profile_running(config, old_name):
        raise RuntimeError("该账号正在运行，请先关闭后再改名")
    profiles = config.setdefault("profiles", [])
    profiles[profiles.index(old_name)] = new_name
    if config.get("active_profile") == old_name:
        config["active_profile"] = new_name
    db.rename_profile(old_name, new_name)
    save_config(config)
    logger.info("账号重命名成功 原名称=%s 新名称=%s", old_name, new_name)
    return _build_profile_summary(config, new_name, read_running_codex_commands())


def delete_profile(payload):
    """删除账号配置和账号资料目录。"""
    name = payload.get("name", "")
    config = load_config()
    profiles = config.setdefault("profiles", [])
    if name not in profiles:
        raise ValueError("账号不存在")
    if _is_profile_running(config, name):
        raise RuntimeError("该账号可能正在使用中，请先关闭 Codex")
    profile_dir = _get_profile_dir(config, name)
    logger.info("账号删除开始 名称=%s 目录=%s", name, profile_dir)
    if profile_dir.exists():
        shutil.rmtree(profile_dir, onerror=remove_readonly_path)
    profiles.remove(name)
    if config.get("active_profile") == name:
        config["active_profile"] = ""
    remove_cached_usage(name)
    save_config(config)
    logger.info("账号删除成功 名称=%s", name)
    return {"name": name}


def get_profile_detail(payload):
    """读取账号详情，只返回可展示的认证元数据，不泄露原始令牌。"""
    name = payload.get("name", "")
    config = load_config()
    if name not in config.get("profiles", []):
        raise ValueError("账号不存在")
    summary = _build_profile_summary(config, name, read_running_codex_commands())
    auth_meta = _read_profile_auth_meta(Path(summary["authPath"]))
    return {**summary, "auth": auth_meta}


def get_usage_history(payload):
    name = str(payload.get("name") or "").strip()
    config = load_config()
    if name not in config.get("profiles", []):
        raise ValueError("账号不存在")
    items = db.load_usage_history(name, payload.get("days", 7), payload.get("limit", 500))
    remaining = [
        item["oneWeek"]["remainingPercent"]
        for item in items
        if isinstance(item, dict) and isinstance(item.get("oneWeek"), dict)
    ]
    pace_per_day = None
    if len(items) >= 2 and len(remaining) >= 2:
        elapsed = float(items[-1]["fetchedAt"]) - float(items[0]["fetchedAt"])
        if elapsed > 0:
            pace_per_day = round((remaining[0] - remaining[-1]) / elapsed * 86400, 2)
    return {"name": name, "items": items, "pacePerDay": pace_per_day}


def get_profile_health(payload):
    name = str(payload.get("name") or "").strip()
    config = load_config()
    if name not in config.get("profiles", []):
        raise ValueError("账号不存在")
    summary = _build_profile_summary(config, name, read_running_codex_commands())
    auth = _read_profile_auth_meta(Path(summary["authPath"]))
    checks = []

    def add(key, ok_value, message, severity="error", action=None):
        checks.append({"key": key, "ok": bool(ok_value), "message": message, "severity": "ok" if ok_value else severity, "action": None if ok_value else action})

    add("profile-directory", summary["profileDirExists"], "账号资料目录可用" if summary["profileDirExists"] else "账号资料目录不存在")
    add("auth", summary["authExists"], "auth.json 已就绪" if summary["authExists"] else "缺少 auth.json")
    if summary["authExists"]:
        add("auth-readable", not auth.get("error"), "认证文件可读取" if not auth.get("error") else f"认证文件异常：{auth.get('error')}")
        if auth.get("kind") != "api":
            add("refresh-token", auth.get("hasRefreshToken"), "刷新令牌已就绪" if auth.get("hasRefreshToken") else "缺少 refresh_token，额度刷新或发送消息可能失败", "warning")
    config_path = Path(summary["configPath"])
    add("config", config_path.is_file(), "config.toml 已就绪" if config_path.is_file() else "缺少 config.toml", "warning", "ensure-config")
    if config_path.is_file():
        try:
            tomllib.loads(config_path.read_text(encoding="utf-8"))
            add("config-syntax", True, "config.toml 语法正确")
        except (OSError, tomllib.TOMLDecodeError) as exc:
            add("config-syntax", False, f"config.toml 无法解析：{exc}")
    if _get_launch_mode(config) == "multi":
        add("portable-client", summary["portableCodexExists"], "共享客户端已就绪" if summary["portableCodexExists"] else "共享客户端将在首次启动时创建", "warning")
    usage = summary.get("usage") or {}
    add("usage", not usage.get("error"), "额度状态正常" if not usage.get("error") else str(usage.get("error")), "warning", "refresh-usage")
    return {"name": name, "healthy": all(item["ok"] for item in checks), "checks": checks}


def repair_profile(payload):
    name = _require_profile_name(payload)
    action = str(payload.get("action") or "")
    config = load_config()
    profile_dir = _get_profile_dir(config, name)
    if action == "ensure-config":
        path = ensure_profile_config_path(profile_dir)
        return {"name": name, "action": action, "path": str(path)}
    if action == "refresh-usage":
        return refresh_profile_usage({"name": name})
    if action == "prepare-runtime":
        prepare_profile_codex_home(profile_dir)
        return {"name": name, "action": action}
    raise ValueError("不支持的修复操作")


def get_profile_launch_settings(payload):
    name = _require_profile_name(payload)
    value = db.load_profile_launch_settings(name)
    return {"name": name, "workingDir": value.get("workingDir", ""), "args": value.get("args", []), "env": value.get("env", {})}


def save_profile_launch_settings(payload):
    name = _require_profile_name(payload)
    working_dir = str(payload.get("workingDir") or "").strip()
    if working_dir and not Path(working_dir).is_dir():
        raise ValueError("默认项目目录不存在")
    args = [str(value).strip() for value in payload.get("args", []) if str(value).strip()]
    env = {
        str(key).strip(): str(value)
        for key, value in dict(payload.get("env") or {}).items()
        if str(key).strip()
    }
    if any("=" in key or "\x00" in key for key in env):
        raise ValueError("环境变量名称不合法")
    blocked = {"APPDATA", "LOCALAPPDATA", "CODEX_HOME", "CODEX_MULTI_PROFILE"}
    if any(key.upper() in blocked for key in env):
        raise ValueError("隔离环境变量由 Codex Forge 管理，不能在账号启动环境中覆盖")
    value = {"workingDir": working_dir, "args": args, "env": env}
    db.save_profile_launch_settings(name, value)
    return {"name": name, **value}


def get_workspace(payload):
    target = _workspace_target(payload)
    return read_workspace(target["codex_home"])


def get_workspace_snapshot(payload):
    """一次读取环境工作台所需数据，减少打包后端的重复启动。"""
    name = _require_profile_name(payload)
    workspace_payload = {"profileName": payload.get("profileName")} if payload.get("profileName") else {}
    readers = {
        "history": (get_usage_history, {"name": name, "days": payload.get("days", 30)}),
        "health": (get_profile_health, {"name": name}),
        "workspace": (get_workspace, workspace_payload),
        "sessions": (list_sessions, {**workspace_payload, "limit": payload.get("limit", 300)}),
        "launchSettings": (get_profile_launch_settings, {"name": name}),
    }
    requested_sections = payload.get("sections")
    if isinstance(requested_sections, list):
        sections = {str(section) for section in requested_sections}
        readers = {key: value for key, value in readers.items() if key in sections}
        if not readers:
            raise ValueError("环境工作台读取范围无效")
    results = {}
    errors = {}

    def read_item(key, reader, reader_payload):
        try:
            results[key] = reader(reader_payload)
        except Exception as exc:
            errors[key] = exc

    threads = [
        threading.Thread(target=read_item, args=(key, reader, reader_payload))
        for key, (reader, reader_payload) in readers.items()
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        raise next(iter(errors.values()))
    return {key: results[key] for key in readers}


def save_agents(payload):
    target = _workspace_target(payload)
    return save_agents_service(target["codex_home"], payload.get("content", ""))


def save_mcp_server(payload):
    target = _workspace_target(payload)
    return save_mcp_server_service(target["path"], payload.get("server") or {})


def delete_mcp_server(payload):
    target = _workspace_target(payload)
    return delete_mcp_server_service(target["path"], payload.get("name"))


def set_mcp_enabled(payload):
    target = _workspace_target(payload)
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("MCP 启用状态无效")
    return set_mcp_enabled_service(target["path"], payload.get("name"), enabled)


def set_skill_enabled(payload):
    target = _workspace_target(payload)
    return set_skill_enabled_service(target["codex_home"], payload.get("name"), bool(payload.get("enabled")))


def install_skill(payload):
    target = _workspace_target(payload)
    return install_skill_service(target["codex_home"], payload.get("sourcePath"))


def remove_skill(payload):
    target = _workspace_target(payload)
    return remove_skill_service(target["codex_home"], payload.get("name"))


def list_sessions(payload):
    target = _workspace_target(payload)
    return {"items": list_sessions_service(target["codex_home"], payload.get("limit", 200))}


def compare_toml_configs(payload):
    source = _resolve_config_target(load_config(), {"profileName": payload.get("sourceProfile")})
    target = _resolve_config_target(load_config(), {"profileName": payload.get("targetProfile")})
    source_text = Path(source["path"]).read_text(encoding="utf-8") if Path(source["path"]).is_file() else ""
    target_text = Path(target["path"]).read_text(encoding="utf-8") if Path(target["path"]).is_file() else ""
    diff = "".join(
        difflib.unified_diff(
            source_text.splitlines(keepends=True),
            target_text.splitlines(keepends=True),
            fromfile=str(source["path"]),
            tofile=str(target["path"]),
        )
    )
    source_data = tomllib.loads(source_text) if source_text.strip() else {}
    return {"sourcePath": str(source["path"]), "targetPath": str(target["path"]), "identical": source_text == target_text, "diff": diff, "sourceKeys": sorted(source_data)}


def sync_toml_keys(payload):
    keys = [str(value) for value in payload.get("keys", [])]
    if not keys:
        raise ValueError("请选择要同步的配置项")
    config = load_config()
    source = _resolve_config_target(config, {"profileName": payload.get("sourceProfile")})
    target = _resolve_config_target(config, {"profileName": payload.get("targetProfile")})
    source_text = Path(source["path"]).read_text(encoding="utf-8") if Path(source["path"]).is_file() else ""
    target_text = Path(target["path"]).read_text(encoding="utf-8") if Path(target["path"]).is_file() else ""
    source_data = tomllib.loads(source_text) if source_text.strip() else {}
    missing = [key for key in keys if key not in source_data]
    if missing:
        raise ValueError(f"源配置中不存在：{', '.join(missing)}")
    merged = target_text
    additions = []
    for key in keys:
        merged = _remove_toml_root(merged, key)
        block = _extract_toml_root(source_text, key)
        if block:
            additions.append(block.strip())
    merged = merged.rstrip()
    if additions:
        merged += ("\n\n" if merged else "") + "\n\n".join(additions) + "\n"
    result = save_toml_config_service({"path": str(target["path"]), "content": merged})
    return {**result, "keys": keys}


def _extract_toml_root(content, root_key):
    output = []
    current_root = None
    assignment = re.compile(rf"^\s*{re.escape(root_key)}\s*=")
    for line in content.splitlines():
        header = re.match(r"^\s*\[+\s*([A-Za-z0-9_-]+)(?:\.|\]|\s)", line)
        if header:
            current_root = header.group(1)
        if (current_root is None and assignment.match(line)) or current_root == root_key:
            output.append(line)
    return "\n".join(output)


def _remove_toml_root(content, root_key):
    output = []
    current_root = None
    assignment = re.compile(rf"^\s*{re.escape(root_key)}\s*=")
    for line in content.splitlines():
        header = re.match(r"^\s*\[+\s*([A-Za-z0-9_-]+)(?:\.|\]|\s)", line)
        if header:
            current_root = header.group(1)
        if (current_root is None and assignment.match(line)) or current_root == root_key:
            continue
        output.append(line)
    return "\n".join(output).strip()


def _workspace_target(payload):
    config = load_config()
    if _get_launch_mode(config) == "multi":
        return _resolve_config_target(config, {"profileName": payload.get("profileName")})
    return {"path": get_active_config_path(), "codex_home": get_active_codex_dir()}


def _require_profile_name(payload):
    name = str(payload.get("name") or "").strip()
    if name not in load_config().get("profiles", []):
        raise ValueError("账号不存在")
    return name


def export_profile_backup(payload):
    """导出单个账号资料；敏感备份使用当前 Windows 用户的 DPAPI 加密。"""
    name = payload.get("name", "")
    target_dir = Path(payload.get("targetDir", ""))
    config = load_config()
    if name not in config.get("profiles", []):
        raise ValueError("账号不存在")
    if not target_dir:
        raise ValueError("请选择导出目录")
    target_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = _get_profile_dir(config, name)
    if not profile_dir.exists():
        raise FileNotFoundError("账号资料目录不存在")

    secure = bool(payload.get("secure"))
    include_auth = secure or bool(payload.get("includeAuth"))
    suffix = ".forgebackup" if secure else ".zip"
    backup_path = target_dir / f"{sanitize_profile_name(name)}-backup-{time.strftime('%Y%m%d-%H%M%S')}{suffix}"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "codex-forge-profile.json",
            json.dumps(
                {"name": name, "formatVersion": 3, "containsSensitiveAuth": include_auth, "encrypted": secure},
                ensure_ascii=False,
                indent=2,
            ),
        )
        included_files = list(_iter_profile_backup_files(profile_dir, include_auth=include_auth))
        for file_path in included_files:
            archive.write(file_path, file_path.relative_to(profile_dir).as_posix())
    backup_path.write_bytes(protect_bytes(buffer.getvalue()) if secure else buffer.getvalue())
    return {
        "name": name,
        "backupPath": str(backup_path),
        "includedFileCount": len(included_files),
        "containsSensitiveAuth": include_auth,
        "encrypted": secure,
    }


def _iter_profile_backup_files(profile_dir, include_auth=True):
    """只备份可恢复账号所需文件，排除会话、日志、缓存和客户端副本。"""
    profile_dir = Path(profile_dir)
    direct_files = (
        profile_dir / "CodexHome" / "config.toml",
        profile_dir / "CodexHome" / ".env",
    )
    if include_auth:
        direct_files = (profile_dir / "auth.json", *direct_files)
    seen = set()
    for file_path in direct_files:
        if file_path.is_file() and not is_reparse_point(file_path):
            seen.add(file_path.resolve())
            yield file_path

    template_dir = profile_dir / "instruction_templates"
    if template_dir.is_dir() and not is_reparse_point(template_dir):
        for file_path in template_dir.rglob("*.md"):
            if file_path.is_file() and not is_reparse_point(file_path) and file_path.resolve() not in seen:
                seen.add(file_path.resolve())
                yield file_path

    codex_home = profile_dir / "CodexHome"
    if codex_home.is_dir() and not is_reparse_point(codex_home):
        for file_path in codex_home.glob("*.md"):
            if file_path.is_file() and not is_reparse_point(file_path) and file_path.resolve() not in seen:
                seen.add(file_path.resolve())
                yield file_path


def import_profile_backup(payload):
    """从普通 zip 或当前 Windows 用户加密的备份恢复账号资料。"""
    backup_path = Path(payload.get("backupPath", ""))
    config = load_config()
    if not backup_path.is_file() or backup_path.suffix.lower() not in (".zip", ".forgebackup"):
        raise ValueError("请选择有效的账号备份文件")
    raw = backup_path.read_bytes()
    if backup_path.suffix.lower() == ".forgebackup":
        raw = unprotect_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
        meta = _read_backup_meta(archive)
        name = _validate_profile_name(config, payload.get("name") or meta.get("name") or backup_path.stem)
        profiles = config.setdefault("profiles", [])
        profiles.append(name)
        save_config(config)
        profile_dir = _get_profile_dir(config, name)
        profile_root = Path(config.get("profile_root") or DEFAULT_PROFILE_ROOT).resolve()
        profile_dir_resolved = profile_dir.resolve()
        try:
            profile_dir_resolved.relative_to(profile_root)
        except ValueError as exc:
            raise ValueError("备份恢复目标不在账号根目录内") from exc
        profile_dir.mkdir(parents=True, exist_ok=False)
        try:
            archive.extractall(profile_dir)
        except Exception:
            shutil.rmtree(profile_dir, onerror=remove_readonly_path)
            profiles.remove(name)
            save_config(config)
            raise
    (profile_dir / "codex-forge-profile.json").unlink(missing_ok=True)
    ensure_profile_config_path(profile_dir)
    save_config(config)
    return _build_profile_summary(config, name, read_running_codex_commands())


def launch_profile(payload):
    """切换到指定账号资料，并启动默认安装的 Codex。"""
    name = payload.get("name", "")
    stop_running_first = bool(payload.get("stopRunningFirst"))
    config = load_config()
    if name not in config.get("profiles", []):
        raise ValueError("账号不存在")
    if _get_launch_mode(config) == "multi":
        return _launch_profile_multi(config, name)

    logger.info("账号启动开始 名称=%s 是否先关闭运行中实例=%s", name, stop_running_first)
    if _running_codex_count() > 0:
        if not stop_running_first:
            raise RuntimeError("检测到 Codex 正在运行，请先关闭后再切换账号")
        _stop_running_codex_processes()

    profile_dir = _get_profile_dir(config, name)
    apply_profile(
        profile_dir,
        share_system_config=True,
    )
    config["active_profile"] = name
    save_config(config)
    skin_port = _allocate_codex_skin_port() if config.get("codex_skin_enabled") else None
    launch_result = _launch_default_codex(name, skin_port=skin_port)
    logger.info("账号启动成功 名称=%s 目录=%s", name, profile_dir)
    result = {"name": name, "activeAuthPath": str(get_active_auth_path()), "activeConfigPath": str(get_active_config_path())}
    if launch_result.get("skinSession"):
        result["skinSession"] = launch_result["skinSession"]
    return result


def stop_profile(_payload):
    """关闭当前运行的 Codex 进程。"""
    config = load_config()
    if _get_launch_mode(config) == "multi":
        return _stop_profile_multi(config, _payload or {})
    return _stop_running_codex_processes()


def _launch_profile_multi(config, name, reserved_skin_ports=None):
    """按账号隔离环境启动 Codex 桌面端。"""
    profile_dir = _get_profile_dir(config, name)
    running_commands = read_running_codex_commands()
    if _is_profile_running(config, name, running_commands):
        logger.info("多开账号已在运行 名称=%s", name)
        return {"name": name, "alreadyRunning": True}

    codex_path = _resolve_codex_app_source_path(config)
    appdata_dir = profile_dir / "AppData" / "Roaming"
    localappdata_dir = profile_dir / "AppData" / "Local"
    codex_home_dir = profile_dir / "CodexHome"
    user_data_dir = _get_user_data_dir(config, name)
    for directory in (appdata_dir, localappdata_dir, codex_home_dir, user_data_dir):
        directory.mkdir(parents=True, exist_ok=True)

    prepare_profile_codex_home(profile_dir)
    _cleanup_orphaned_portable_processes(config, codex_path)
    portable_codex_path = prepare_portable_codex_path(
        codex_path,
        _get_shared_app_root(config),
        progress_callback=lambda percent, copied, total: _emit_backend_progress(
            {
                "operation": "portable-client-copy",
                "profileName": name,
                "percent": percent,
                "copiedBytes": copied,
                "totalBytes": total,
            }
        ),
    )

    env = os.environ.copy()
    env["APPDATA"] = str(appdata_dir)
    env["LOCALAPPDATA"] = str(localappdata_dir)
    env["CODEX_HOME"] = str(codex_home_dir)
    env["CODEX_MULTI_PROFILE"] = name
    launch_settings = db.load_profile_launch_settings(name)
    managed_env = {"APPDATA", "LOCALAPPDATA", "CODEX_HOME", "CODEX_MULTI_PROFILE"}
    env.update(
        {
            str(key): str(value)
            for key, value in dict(launch_settings.get("env") or {}).items()
            if str(key).upper() not in managed_env
        }
    )
    extra_args = [str(value) for value in launch_settings.get("args", [])]
    skin_port = None
    if config.get("codex_skin_enabled"):
        skin_port = _allocate_codex_skin_port(reserved_skin_ports)
        extra_args = _append_codex_skin_args(extra_args, skin_port)
    working_dir = str(launch_settings.get("workingDir") or Path(portable_codex_path).parent)

    logger.info("多开账号启动开始 名称=%s 程序=%s CODEX_HOME=%s", name, portable_codex_path, codex_home_dir)
    process = subprocess.Popen(
        [portable_codex_path, f"--user-data-dir={user_data_dir}", *extra_args],
        cwd=working_dir,
        env=env,
        close_fds=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    config["active_profile"] = name
    save_config(config)
    logger.info("多开账号启动成功 名称=%s 目录=%s", name, profile_dir)
    result = {
        "name": name,
        "activeAuthPath": str(codex_home_dir / "auth.json"),
        "activeConfigPath": str(codex_home_dir / "config.toml"),
    }
    if skin_port is not None:
        result["skinSession"] = {"profileName": name, "port": skin_port, "processId": process.pid}
    return result


def _append_codex_skin_args(extra_args, port):
    """追加由 Forge 管理的 CDP 参数，避免与账号自定义参数产生歧义。"""
    blocked_prefixes = ("--remote-debugging-address", "--remote-debugging-port")
    if any(str(value).lower().startswith(blocked_prefixes) for value in extra_args):
        raise ValueError("启用 Codex 皮肤时，账号启动参数不能包含 remote-debugging 参数")
    return [
        *extra_args,
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port}",
    ]


def _allocate_codex_skin_port(reserved_ports=None):
    """从 Forge 专用范围选择当前可用的回环端口。"""
    reserved_ports = reserved_ports or set()
    for port in range(CODEX_SKIN_PORT_START, CODEX_SKIN_PORT_START + CODEX_SKIN_PORT_COUNT):
        if port in reserved_ports:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise RuntimeError("没有可用的 Codex 皮肤调试端口")


def get_codex_skin_sessions(_payload=None):
    """从 Forge 启动的受管客户端恢复皮肤 CDP 会话。"""
    config = load_config()
    if not config.get("codex_skin_enabled"):
        return {"skinSessions": []}
    shared_root = _get_shared_app_root(config).resolve()
    launch_mode = _get_launch_mode(config)
    sessions = []
    for process in read_running_codex_processes():
        command_line = str(process.get("command_line") or "")
        normalized_command = normalize_path_for_match(command_line)
        port_match = re.search(r"(?:^|\s)--remote-debugging-port(?:=|\s+)(\d+)(?:\s|$)", command_line, re.IGNORECASE)
        if not port_match or "--remote-debugging-address=127.0.0.1" not in command_line.lower():
            continue
        port = int(port_match.group(1))
        if not CODEX_SKIN_PORT_START <= port < CODEX_SKIN_PORT_START + CODEX_SKIN_PORT_COUNT:
            continue
        try:
            Path(process.get("executable_path") or "").resolve().relative_to(shared_root)
        except (OSError, ValueError):
            continue
        profile_name = str(config.get("active_profile") or SYSTEM_PROFILE_NAME)
        if launch_mode == "multi":
            profile_name = next(
                (
                    name
                    for name in config.get("profiles", [])
                    if any(target in normalized_command for target in _get_profile_running_match_targets(config, name))
                ),
                "",
            )
            if not profile_name:
                continue
        sessions.append(
            {
                "profileName": profile_name,
                "port": port,
                "processId": int(process.get("pid") or 0),
            }
        )
    return {"skinSessions": sessions}


def ensure_codex_skin_sessions(_payload=None):
    """确保当前运行实例由 Forge 以皮肤 CDP 参数启动。"""
    recovered = get_codex_skin_sessions()
    if recovered["skinSessions"]:
        return recovered
    config = load_config()
    if not config.get("codex_skin_enabled"):
        return {"skinSessions": []}
    launch_mode = _get_launch_mode(config)
    if launch_mode == "multi":
        running_profiles = _running_multi_profile_names(config)
        if not running_profiles:
            return {"skinSessions": []}
        sessions = []
        reserved_ports = set()
        for profile_name in running_profiles:
            _stop_profile_multi(config, {"name": profile_name})
            session = _launch_profile_multi(config, profile_name, reserved_ports).get("skinSession")
            if session:
                sessions.append(session)
                reserved_ports.add(session["port"])
        return {"skinSessions": sessions}
    if _running_codex_count() == 0:
        return {"skinSessions": []}
    active_profile = str(config.get("active_profile") or "")
    _sync_active_auth_to_profile(config, active_profile)
    _stop_running_codex_processes()
    launch_result = _launch_default_codex(active_profile, skin_port=_allocate_codex_skin_port())
    session = launch_result.get("skinSession")
    return {"skinSessions": [session] if session else []}


def _stop_profile_multi(config, payload):
    """关闭指定账号对应的 Codex 进程。"""
    name = payload.get("name", "")
    if not name:
        stopped = 0
        for profile_name in _running_multi_profile_names(config):
            stopped += _stop_profile_multi(config, {"name": profile_name}).get("stopped", 0)
        return {"stopped": stopped}
    if name not in config.get("profiles", []):
        raise ValueError("账号不存在")
    match_targets = _get_profile_running_match_targets(config, name)
    matched_processes = [
        process
        for process in read_running_codex_processes()
        if any(target in normalize_path_for_match(process["command_line"]) for target in match_targets)
    ]
    if _get_legacy_system_running_profile(config) == name:
        matched_processes.extend(_get_unisolated_codex_processes(config))
    logger.info("多开账号关闭开始 名称=%s 匹配进程=%s", name, len(matched_processes))
    stopped = _stop_client_processes(matched_processes)
    sync_codex_home_to_profile(_get_profile_dir(config, name))
    logger.info("多开账号关闭成功 名称=%s 已关闭=%s", name, stopped)
    return {"name": name, "stopped": stopped}


def _stop_running_codex_processes():
    """关闭当前运行的 Codex 客户端主进程。"""
    processes = read_running_codex_processes()
    logger.info("关闭 Codex 进程开始 数量=%s", len(processes))
    stopped = _stop_client_processes(processes)
    logger.info("关闭 Codex 进程成功 已关闭=%s", stopped)
    return {"stopped": stopped}


def _stop_client_processes(processes):
    """先请求客户端正常退出，超时后再强制结束。"""
    pids = {process.get("pid") for process in processes if process.get("pid")}
    for pid in pids:
        request_process_close(pid)

    deadline = time.monotonic() + 5
    remaining = pids
    while remaining and time.monotonic() < deadline:
        time.sleep(0.25)
        running_pids = {process.get("pid") for process in read_running_codex_processes()}
        remaining &= running_pids

    for pid in remaining:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    return len(pids)


def _emit_backend_progress(payload):
    """通过桥接进程 stderr 向 Electron 壳发送结构化进度。"""
    print(
        f"CODEX_FORGE_PROGRESS:{json.dumps(payload, ensure_ascii=False)}",
        file=sys.stderr,
        flush=True,
    )


def refresh_codex_source(_payload=None):
    """刷新可启动的 Codex 程序来源，兼容无命令行别名的安装方式。"""
    config = load_config()
    launch_spec = _resolve_codex_launch_spec(config, refresh_store_source=True)
    logger.info("刷新 Codex 来源成功 类型=%s 显示=%s", launch_spec["kind"], launch_spec["display"])
    return {
        "codexCommandAvailable": True,
        "codexLaunchPath": launch_spec["display"],
    }


def read_toml_config(payload=None):
    """按当前启动模式读取系统或账号级 config.toml。"""
    config = load_config()
    target = _resolve_config_target(config, payload or {})
    return read_toml_config_service({"path": str(target["path"])})


def save_toml_config(payload):
    """按当前启动模式保存系统、单账号或全部账号 config.toml。"""
    config = load_config()
    payload = payload or {}
    if _get_launch_mode(config) == "multi" and payload.get("scope") == "all":
        profile_names = config.get("profiles", [])
        if not profile_names:
            raise ValueError("暂无账号可同步")
        result = None
        for profile_name in profile_names:
            target = _resolve_config_target(config, {"profileName": profile_name})
            result = save_toml_config_service({"path": str(target["path"]), "content": payload.get("content", "")})
        return {**(result or {}), "syncedCount": len(profile_names)}
    target = _resolve_config_target(config, payload)
    return save_toml_config_service({"path": str(target["path"]), "content": payload.get("content", "")})


def list_instruction_templates(payload=None):
    """按当前启动模式读取模板启用状态。"""
    config = load_config()
    target = _resolve_config_target(config, payload or {})
    return list_instruction_templates_service(_instruction_payload(target))


def save_instruction_template(payload):
    """按当前启动模式保存模板；multi 下保存到账号目录。"""
    config = load_config()
    payload = payload or {}
    target = _resolve_config_target(config, payload)
    return save_instruction_template_service({**payload, **_instruction_payload(target)})


def delete_instruction_template(payload):
    """按当前启动模式删除模板；multi 下删除账号目录内模板。"""
    config = load_config()
    payload = payload or {}
    target = _resolve_config_target(config, payload)
    return delete_instruction_template_service({**payload, **_instruction_payload(target)})


def enable_instruction_template(payload):
    """按当前启动模式启用模板；scope=all/profile 只同步模板文件。"""
    config = load_config()
    payload = payload or {}
    if _get_launch_mode(config) == "multi" and payload.get("scope") == "profile":
        target_profile_name = str(payload.get("targetProfileName") or "").strip()
        if target_profile_name not in config.get("profiles", []):
            raise ValueError("请选择有效目标账号")
        source_target = _resolve_config_target(config, payload)
        target = _resolve_config_target(config, {"profileName": target_profile_name})
        sync_payload = {
            "id": payload.get("id"),
            "targetTemplateDir": str(target["template_dir"]),
        }
        if source_target.get("template_dir"):
            sync_payload["templateDir"] = str(source_target["template_dir"])
        return sync_instruction_template_service(sync_payload)
    if _get_launch_mode(config) == "multi" and payload.get("scope") == "all":
        profile_names = config.get("profiles", [])
        if not profile_names:
            raise ValueError("暂无账号可同步")
        result = None
        source_target = _resolve_config_target(config, payload)
        for profile_name in profile_names:
            target = _resolve_config_target(config, {"profileName": profile_name})
            sync_payload = {
                "id": payload.get("id"),
                "targetTemplateDir": str(target["template_dir"]),
            }
            if source_target.get("template_dir"):
                sync_payload["templateDir"] = str(source_target["template_dir"])
            result = sync_instruction_template_service(sync_payload)
        return {**(result or {}), "syncedCount": len(profile_names)}
    target = _resolve_config_target(config, payload)
    return enable_instruction_template_service({
        "id": payload.get("id"),
        **_instruction_payload(target),
    })


def disable_instruction_template(payload=None):
    """按当前启动模式禁用模板。"""
    config = load_config()
    payload = payload or {}
    if _get_launch_mode(config) == "multi" and payload.get("scope") == "all":
        profile_names = config.get("profiles", [])
        if not profile_names:
            raise ValueError("暂无账号可同步")
        result = None
        for profile_name in profile_names:
            target = _resolve_config_target(config, {"profileName": profile_name})
            result = disable_instruction_template_service(_instruction_payload(target))
        return {**(result or {}), "syncedCount": len(profile_names)}
    target = _resolve_config_target(config, payload)
    return disable_instruction_template_service(_instruction_payload(target))


def refresh_profile_usage(payload):
    """刷新单个账号的额度快照。"""
    name = payload.get("name", "")
    config = load_config()
    if name not in config.get("profiles", []):
        raise ValueError("账号不存在")
    use_codex_home = _get_launch_mode(config) == "multi"
    if not use_codex_home:
        _sync_active_auth_to_profile(config, name)
    usage = refresh_profile_usage_cache(
        name,
        _get_profile_dir(config, name),
        share_system_config=not use_codex_home,
        use_codex_home_auth=use_codex_home,
    )
    return {"name": name, "usage": usage}


def refresh_all_profile_usage(_payload=None):
    """刷新全部账号的额度快照。"""
    config = load_config()
    use_codex_home = _get_launch_mode(config) == "multi"
    if not use_codex_home:
        _sync_active_auth_to_profile(config, config.get("active_profile", ""))
    profile_dirs = {
        profile_name: str(_get_profile_dir(config, profile_name))
        for profile_name in config.get("profiles", [])
    }
    return {
        "profiles": refresh_all_profile_usage_cache(
            profile_dirs,
            share_system_config=not use_codex_home,
            use_codex_home_auth=use_codex_home,
        )
    }


def set_share_system_config(payload):
    """兼容旧前端命令；账号切换模式固定使用系统 config.toml。"""
    config = load_config()
    config["share_system_config"] = True
    save_config(config)
    return {"shareSystemConfig": True}


def set_launch_mode(payload):
    """保存 Codex 启动模式。"""
    mode = str(payload.get("mode") or "").strip()
    if mode not in ("switch", "multi"):
        raise ValueError("启动模式无效")
    config = load_config()
    if mode == "switch" and _running_multi_profile_names(config):
        raise RuntimeError("请先关闭所有多开隔离模式下运行的 Codex，再切回账号切换模式")
    if mode == "multi" and _get_launch_mode(config) == "switch":
        _sync_active_auth_to_profile(config, config.get("active_profile", ""))
    config["launch_mode"] = mode
    save_config(config)
    logger.info("启动模式已切换 模式=%s", mode)
    return {"launchMode": mode}


def set_codex_skin_enabled(payload):
    """保存 Codex 皮肤开关，并安全重启当前运行实例以切换 CDP 状态。"""
    config = load_config()
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("Codex 皮肤开关无效")
    previous_enabled = bool(config.get("codex_skin_enabled"))
    launch_mode = _get_launch_mode(config)
    running_profiles = _running_multi_profile_names(config) if launch_mode == "multi" else []
    switch_running = launch_mode == "switch" and _running_codex_count() > 0
    active_profile = config.get("active_profile", "")
    if enabled == previous_enabled:
        return {"codexSkinEnabled": enabled, "skinSessions": []}
    if switch_running:
        _sync_active_auth_to_profile(config, active_profile)
        _stop_running_codex_processes()
    config["codex_skin_enabled"] = enabled
    save_config(config)
    skin_sessions = []
    reserved_skin_ports = set()
    for profile_name in running_profiles:
        _stop_profile_multi(config, {"name": profile_name})
        session = _launch_profile_multi(config, profile_name, reserved_skin_ports).get("skinSession")
        if session:
            skin_sessions.append(session)
            reserved_skin_ports.add(session["port"])
    if switch_running:
        skin_port = _allocate_codex_skin_port() if enabled else None
        launch_result = _launch_default_codex(active_profile, skin_port=skin_port)
        if launch_result.get("skinSession"):
            skin_sessions.append(launch_result["skinSession"])
    logger.info("Codex 皮肤设置已更新 启用=%s", enabled)
    return {"codexSkinEnabled": enabled, "skinSessions": skin_sessions}


def _sync_active_auth_to_profile(config, profile_name):
    """当前账号刷新额度前，把 Codex 刚续期的认证回写到账号目录。"""
    if not profile_name or profile_name != config.get("active_profile"):
        return
    profile_dir = _get_profile_dir(config, profile_name)
    profile_auth_path = get_profile_auth_path(profile_dir)
    active_auth_path = get_active_auth_path()
    if not active_auth_path.exists() or not profile_auth_path.exists():
        return
    try:
        active_auth = json.loads(active_auth_path.read_text(encoding="utf-8"))
        profile_auth = json.loads(profile_auth_path.read_text(encoding="utf-8"))
        if not _is_same_auth_account(active_auth, profile_auth):
            logger.warning("跳过当前账号认证同步 原因=账号身份不一致 名称=%s", profile_name)
            return
        import_active_profile(profile_dir)
        logger.info("当前账号认证已同步 名称=%s 来源=%s 目标=%s", profile_name, active_auth_path, profile_auth_path)
    except Exception as exc:
        logger.warning("当前账号认证同步失败 名称=%s 错误=%s", profile_name, exc)


def _is_same_auth_account(left_auth, right_auth):
    """确认两个 auth.json 属于同一登录用户，避免同一 Team 账号下串号。"""
    left_kind = auth_kind(left_auth)
    right_kind = auth_kind(right_auth)
    if left_kind != right_kind or not left_kind:
        return False
    if left_kind == "api":
        left_key = str(left_auth.get("OPENAI_API_KEY") or "").strip()
        right_key = str(right_auth.get("OPENAI_API_KEY") or "").strip()
        left_digest = hashlib.sha256(left_key.encode("utf-8")).digest()
        right_digest = hashlib.sha256(right_key.encode("utf-8")).digest()
        return bool(left_key and right_key and hmac.compare_digest(left_digest, right_digest))

    left = extract_auth(left_auth) or {}
    right = extract_auth(right_auth) or {}
    left_claims_value = left.get("claims")
    right_claims_value = right.get("claims")
    left_claims = left_claims_value if isinstance(left_claims_value, dict) else {}
    right_claims = right_claims_value if isinstance(right_claims_value, dict) else {}
    for key in ("sub", "email"):
        left_value = left_claims.get(key) or left.get(key)
        right_value = right_claims.get(key) or right.get(key)
        if left_value or right_value:
            return bool(left_value and right_value and left_value == right_value)
    return bool(left.get("accountId") and left.get("accountId") == right.get("accountId"))


def set_profile_root(payload):
    """迁移整个账号资料根目录并保存新位置。"""
    new_root = Path(payload.get("profileRoot", ""))
    if not new_root:
        raise ValueError("账号根目录不能为空")
    if payload.get("asStorageLocation") and new_root.name.lower() != DEFAULT_PROFILE_ROOT.name.lower():
        new_root = new_root / DEFAULT_PROFILE_ROOT.name
    config = load_config()
    old_root = Path(config.get("profile_root") or DEFAULT_PROFILE_ROOT)
    old_root_resolved = old_root.resolve()
    new_root_parent = new_root.parent.resolve()
    new_root_resolved = new_root_parent / new_root.name

    if old_root_resolved == new_root_resolved:
        config["profile_root"] = str(new_root_resolved)
        save_config(config)
        logger.info("账号根目录未变化 路径=%s", new_root_resolved)
        return {"profileRoot": str(new_root_resolved), "migrated": False}
    if old_root_resolved in new_root_resolved.parents:
        raise ValueError("新位置不能放在当前账号目录内部")
    if new_root_resolved in old_root_resolved.parents:
        raise ValueError("新位置不能是当前账号目录的上级目录")

    new_root_parent.mkdir(parents=True, exist_ok=True)
    if not check_directory_writable(new_root_parent):
        raise PermissionError("账号根目录不可写")
    if new_root_resolved.exists() and any(new_root_resolved.iterdir()):
        raise FileExistsError("目标账号根目录已存在且不为空")

    if old_root_resolved.exists():
        logger.info("账号根目录迁移开始 原路径=%s 新路径=%s", old_root_resolved, new_root_resolved)
        _copy_directory(old_root_resolved, new_root_resolved)
        shutil.rmtree(old_root_resolved, onerror=remove_readonly_path)
    else:
        new_root_resolved.mkdir(parents=True, exist_ok=True)

    config["profile_root"] = str(new_root_resolved)
    save_config(config)
    logger.info("账号根目录设置成功 原路径=%s 新路径=%s", old_root_resolved, new_root_resolved)
    return {"profileRoot": str(new_root_resolved), "migrated": True}


def open_path(payload):
    """打开白名单命令传入的本地路径。"""
    path = Path(payload.get("path", ""))
    if not path.exists():
        raise FileNotFoundError(path)
    if payload.get("reveal") and path.is_file():
        subprocess.Popen(["explorer.exe", "/select,", str(path)], creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        os.startfile(str(path))
    return {"path": str(path)}


def get_diagnostics(_payload=None):
    """生成结构化诊断数据。"""
    config = load_config()
    _normalize_profile_configs(config)
    profiles = config.get("profiles", [])
    profile_root = Path(config.get("profile_root") or DEFAULT_PROFILE_ROOT)
    profile_records = db.list_profile_records()
    expected_dirs = {str((profile_root / item["dir_name"]).resolve()) for item in profile_records}
    expected_dirs.add(str(_get_shared_app_root(config).resolve()))
    actual_dirs = (
        {str(path.resolve()) for path in profile_root.iterdir() if path.is_dir()}
        if profile_root.is_dir()
        else set()
    )
    running_commands = read_running_codex_commands()
    profile_items = []
    for profile_name in profiles:
        summary = _build_profile_summary(config, profile_name, running_commands)
        disk_usage_bytes = _get_directory_size(_get_profile_dir(config, profile_name))
        health = {
            "running": summary["running"],
            "errors": summary["errors"],
            "warnings": summary["warnings"],
        }
        status_text, _ = format_health_status(health)
        summary.update(
            {
                "statusText": status_text,
                "errors": health["errors"],
                "warnings": health["warnings"],
                "diskUsageBytes": disk_usage_bytes,
                "diskUsageText": _format_bytes(disk_usage_bytes),
            }
        )
        profile_items.append(summary)
    return {
        "basic": {
            "configPath": str(DB_PATH),
            "configExists": DB_PATH.exists(),
            "lastGoodBackupExists": False,
            "previousGoodBackupExists": False,
            "profileRoot": str(profile_root),
            "profileRootWritable": check_directory_writable(profile_root),
            "activeAuthPath": str(get_active_auth_path()),
            "activeAuthExists": get_active_auth_path().exists(),
            "activeConfigPath": str(get_active_config_path()),
            "activeConfigExists": get_active_config_path().exists(),
            "codexCommandAvailable": _is_codex_command_available(),
            "runningCodexCount": _running_codex_count(),
            "activeProfile": config.get("active_profile", ""),
            "shareSystemConfig": True,
            "profileCount": len(profiles),
            "missingProfileDirs": sorted(expected_dirs - actual_dirs),
            "orphanProfileDirs": sorted(actual_dirs - expected_dirs),
        },
        "profiles": profile_items,
    }


def _read_profile_auth_meta(auth_path):
    """提取账号认证元数据，令牌只返回状态和过期时间。"""
    result = {
        "exists": auth_path.exists(),
        "authMode": "",
        "email": "",
        "accountId": "",
        "planType": "",
        "accessTokenExpiresAt": None,
        "hasRefreshToken": False,
        "error": "",
    }
    if not auth_path.exists():
        return result
    try:
        auth_json = json.loads(auth_path.read_text(encoding="utf-8"))
        mode = auth_kind(auth_json)
        result["authMode"] = mode
        if mode == "api":
            return result
        auth = extract_auth(auth_json)
        tokens = auth_tokens(auth_json) or {}
        result.update(
            {
                "email": auth.get("email") or "",
                "accountId": auth.get("accountId") or "",
                "planType": auth.get("planType") or "",
                "accessTokenExpiresAt": _jwt_expiration(tokens.get("access_token")),
                "hasRefreshToken": bool(tokens.get("refresh_token")),
            }
        )
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _read_backup_meta(archive):
    """读取备份元数据，并拒绝危险 zip 路径。"""
    for member in archive.infolist():
        path = Path(member.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("备份文件包含不安全路径")
    try:
        with archive.open("codex-forge-profile.json") as meta_file:
            meta = json.loads(meta_file.read().decode("utf-8"))
            return meta if isinstance(meta, dict) else {}
    except KeyError:
        return {}


def _jwt_expiration(token):
    if not isinstance(token, str) or not token:
        return None
    parts = token.split(".")
    if len(parts) < 2:
        return None
    import base64

    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        claims = json.loads(decoded)
    except Exception:
        return None
    exp = claims.get("exp") if isinstance(claims, dict) else None
    return int(exp) if isinstance(exp, (int, float)) else None


def _commands_from_processes(processes):
    return normalize_path_for_match("\n".join(process["command_line"] for process in processes))


def _build_profile_summaries(config, running_commands, running_processes):
    profile_records = {record["display_name"]: record for record in db.list_profile_records()}
    usage_cache = db.load_usage_cache()
    legacy_profile = _get_legacy_system_running_profile(config, running_processes)
    return [
        _build_profile_summary(
            config,
            profile_name,
            running_commands,
            profile_record=profile_records.get(profile_name),
            usage_cache=usage_cache,
            legacy_profile=legacy_profile,
        )
        for profile_name in config.get("profiles", [])
    ]


def _build_profile_summary(
    config,
    profile_name,
    running_commands,
    profile_record=None,
    usage_cache=None,
    legacy_profile=None,
):
    """构造账号列表项。"""
    if profile_record is None:
        profile_record = db.get_profile(profile_name)
    usage = usage_cache.get(profile_name) if usage_cache is not None else get_cached_profile_usage(profile_name)
    profile_dir = _get_profile_dir(config, profile_name)
    status = get_profile_status(
        profile_dir,
    )
    active_profile = config.get("active_profile", "")
    running = _is_profile_running(config, profile_name, running_commands, legacy_profile)
    target_app_dir = _get_shared_app_root(config) / PORTABLE_APP_DIR_NAME
    portable_client_path = target_app_dir / "ChatGPT.exe"
    if not portable_client_path.exists():
        portable_client_path = target_app_dir / "Codex.exe"
    source_signature = read_source_signature(target_app_dir)
    portable_codex_size = source_signature.get("directory_size")
    if not isinstance(portable_codex_size, int):
        portable_codex_size = _get_directory_size(target_app_dir)
        if source_signature:
            source_signature["directory_size"] = portable_codex_size
            write_source_signature(target_app_dir, source_signature)
    return {
        "id": profile_record["id"] if profile_record else "",
        "name": profile_name,
        "storageKey": profile_record["dir_name"] if profile_record else profile_dir.name,
        "running": running,
        "active": profile_name == active_profile,
        "profileDir": str(profile_dir),
        "profileDirExists": profile_dir.exists(),
        "authPath": status["authPath"],
        "authExists": status["authExists"],
        "configPath": status["configPath"],
        "configExists": status["configExists"],
        "codexHome": str(profile_dir / "CodexHome"),
        "codexHomeExists": (profile_dir / "CodexHome").exists(),
        "portableCodexPath": str(portable_client_path),
        "portableCodexExists": portable_client_path.exists(),
        "portableCodexSizeBytes": portable_codex_size,
        "portableCodexSizeText": _format_bytes(portable_codex_size),
        "errors": status["errors"],
        "warnings": status["warnings"],
        "usage": usage,
    }


def _get_profile_dir(config, profile_name):
    """通过不可变存储键计算账号目录。"""
    profile_root = Path(config.get("profile_root") or DEFAULT_PROFILE_ROOT)
    profile = db.get_profile(profile_name)
    if not profile:
        raise ValueError("账号不存在")
    return profile_root / profile["dir_name"]


def _get_shared_app_root(config):
    """返回所有多开账号共用的客户端存储目录。"""
    profile_root = Path(config.get("profile_root") or DEFAULT_PROFILE_ROOT)
    return profile_root / ".shared"


def _normalize_profile_configs(config):
    """开发期直接收敛账号配置：删除外层 config.toml，只保留 CodexHome/config.toml。"""
    for profile_name in config.get("profiles", []):
        ensure_profile_config_path(_get_profile_dir(config, profile_name))


def _resolve_config_target(config, payload):
    """switch 使用系统配置；multi 使用指定账号 CodexHome 配置。"""
    if _get_launch_mode(config) != "multi":
        return {"path": get_active_config_path(), "codex_home": get_active_codex_dir(), "template_dir": None, "profileName": ""}

    profile_name = str(payload.get("profileName") or config.get("active_profile") or "").strip()
    if profile_name == SYSTEM_PROFILE_NAME:
        return {"path": get_active_config_path(), "codex_home": get_active_codex_dir(), "template_dir": None, "profileName": SYSTEM_PROFILE_NAME}
    if not profile_name and config.get("profiles"):
        profile_name = config["profiles"][0]
    if profile_name not in config.get("profiles", []):
        raise ValueError("请选择有效账号")
    profile_dir = _get_profile_dir(config, profile_name)
    config_path = ensure_profile_config_path(profile_dir)
    return {
        "path": config_path,
        "codex_home": profile_dir / "CodexHome",
        "template_dir": profile_dir / "instruction_templates",
        "profileName": profile_name,
    }


def _instruction_payload(target):
    payload = {"codexHome": str(target["codex_home"]), "configPath": str(target["path"])}
    if target.get("template_dir"):
        payload["templateDir"] = str(target["template_dir"])
    return payload


def _remove_path_if_inside_profile_root(config, path):
    """仅清理账号根目录内的临时目标，防止异常路径被误删。"""
    profile_root = Path(config.get("profile_root") or DEFAULT_PROFILE_ROOT).resolve()
    target_path = Path(path).resolve()
    try:
        target_path.relative_to(profile_root)
    except ValueError:
        return
    if target_path.exists():
        shutil.rmtree(target_path, onerror=remove_readonly_path)


def _validate_profile_name(config, profile_name, exclude_name=None):
    """校验账号名称和对应目录是否可用。"""
    profile_name = str(profile_name or "").strip()
    if not profile_name:
        raise ValueError("账号名称不能为空")
    profiles = config.setdefault("profiles", [])
    if profile_name in profiles and profile_name != exclude_name:
        raise ValueError("已存在同名账号")
    return profile_name


def _get_launch_mode(config):
    """读取启动模式，异常值回退到稳定的账号切换模式。"""
    return "multi" if config.get("launch_mode") == "multi" else "switch"


def _is_profile_running(config, profile_name, running_commands=None, legacy_profile=None):
    """判断指定账号是否为当前正在运行的账号。"""
    if _get_launch_mode(config) == "multi":
        running_commands = running_commands if running_commands is not None else read_running_codex_commands()
        if any(target in running_commands for target in _get_profile_running_match_targets(config, profile_name)):
            return True
        if legacy_profile is None:
            legacy_profile = _get_legacy_system_running_profile(config)
        return legacy_profile == profile_name
    if running_commands is None:
        running_commands = read_running_codex_commands()
    return profile_name == config.get("active_profile", "") and bool(running_commands)


def _running_count_for_mode(config, running_processes=None, running_commands=None):
    """按当前启动模式统计运行账号数。"""
    running_processes = running_processes if running_processes is not None else read_running_codex_processes()
    if _get_launch_mode(config) != "multi":
        return 1 if running_processes else 0
    running_commands = running_commands if running_commands is not None else _commands_from_processes(running_processes)
    legacy_profile = _get_legacy_system_running_profile(config, running_processes)
    return sum(
        1
        for profile_name in config.get("profiles", [])
        if _is_profile_running(config, profile_name, running_commands, legacy_profile)
    )


def _running_multi_profile_names(config):
    """列出当前仍在多开隔离环境中运行的账号。"""
    running_commands = read_running_codex_commands()
    running_profiles = [
        profile_name
        for profile_name in config.get("profiles", [])
        if any(target in running_commands for target in _get_profile_running_match_targets(config, profile_name))
    ]
    legacy_profile = _get_legacy_system_running_profile(config)
    if legacy_profile and legacy_profile not in running_profiles:
        running_profiles.append(legacy_profile)
    return running_profiles


def _get_unisolated_codex_processes(config, running_processes=None):
    """返回不属于任何账号隔离目录的系统客户端主进程。"""
    profile_targets = [
        target
        for profile_name in config.get("profiles", [])
        for target in _get_profile_running_match_targets(config, profile_name)
    ]
    return [
        process
        for process in (running_processes if running_processes is not None else read_running_codex_processes())
        if not any(target in normalize_path_for_match(process["command_line"]) for target in profile_targets)
    ]


def _get_legacy_system_running_profile(config, running_processes=None):
    """识别从账号切换模式直接带入多开模式的系统客户端。"""
    if _get_launch_mode(config) != "multi" or not _get_unisolated_codex_processes(config, running_processes):
        return ""
    active_auth_path = get_active_auth_path()
    if not active_auth_path.exists():
        return ""
    try:
        active_auth = json.loads(active_auth_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    matching_profiles = []
    for profile_name in config.get("profiles", []):
        profile_auth_path = get_profile_auth_path(_get_profile_dir(config, profile_name))
        if not profile_auth_path.exists():
            continue
        try:
            profile_auth = json.loads(profile_auth_path.read_text(encoding="utf-8"))
            if _is_same_auth_account(active_auth, profile_auth):
                matching_profiles.append(profile_name)
        except Exception:
            continue
    return matching_profiles[0] if len(matching_profiles) == 1 else ""


def _get_user_data_dir(config, profile_name):
    """计算 Codex 网页容器的独立用户数据目录。"""
    return _get_profile_dir(config, profile_name) / "AppData" / "Roaming" / "Codex" / "web" / "Codex"


def _get_profile_running_match_targets(config, profile_name):
    """构造用于识别账号运行进程的命令行路径特征。"""
    profile_dir = _get_profile_dir(config, profile_name)
    return [
        normalize_path_for_match(profile_dir),
        normalize_path_for_match(_get_user_data_dir(config, profile_name)),
    ]


def _running_codex_count():
    """统计当前运行中的 Codex 相关进程数量。"""
    return len(read_running_codex_processes())


def _is_codex_command_available(config=None, running_processes=None):
    """检查当前环境是否能找到可启动的 Codex 程序。"""
    if running_processes:
        return True
    try:
        _resolve_codex_launch_spec(config or load_config())
        return True
    except Exception:
        return False


def _resolve_codex_launch_spec(config, *, refresh_store_source=False):
    """优先使用桌面程序，其次使用微软商店应用标识。"""
    configured_path = str(config.get("codex_path") or "").strip()
    configured_app_path = _resolve_configured_codex_app_path(configured_path)
    if refresh_store_source:
        configured_app_path = _prefer_latest_installed_store_path(configured_app_path)
    if configured_app_path:
        if str(configured_app_path) != configured_path:
            config["codex_path"] = str(configured_app_path)
            save_config(config)
        logger.info("Codex 启动来源已识别 来源=已配置桌面程序 路径=%s", configured_app_path)
        return _build_app_launch_spec(configured_app_path)

    detected_path = find_windowsapps_codex_path() or find_running_codex_path()
    if detected_path:
        config["codex_path"] = detected_path
        save_config(config)
        logger.info("Codex 启动来源已识别 来源=自动识别桌面程序 路径=%s", detected_path)
        return _build_app_launch_spec(detected_path)

    store_app_id = _find_windows_store_codex_app_id()
    if store_app_id:
        logger.info("Codex 启动来源已识别 来源=微软商店 应用标识=%s", store_app_id)
        return {
            "kind": "store",
            "command": ["explorer.exe", f"shell:AppsFolder\\{store_app_id}"],
            "display": store_app_id,
        }

    raise FileNotFoundError("未找到 Codex 桌面客户端，请在设置中重新识别或确认已安装")


def _resolve_codex_app_source_path(config):
    """定位用于复制共享客户端副本的 Codex 安装源。"""
    configured_path = str(config.get("codex_path") or "").strip()
    configured_app_path = _resolve_configured_codex_app_path(configured_path)
    configured_app_path = _prefer_latest_installed_store_path(configured_app_path)
    if configured_app_path:
        if str(configured_app_path) != configured_path:
            config["codex_path"] = str(configured_app_path)
            save_config(config)
        return configured_app_path

    detected_path = find_windowsapps_codex_path() or find_running_codex_path()
    if detected_path and Path(detected_path).exists():
        config["codex_path"] = detected_path
        save_config(config)
        return Path(detected_path)

    raise FileNotFoundError("多开隔离模式需要可识别的 Codex 桌面客户端，请先刷新来源或安装客户端")


def _prefer_latest_installed_store_path(configured_app_path):
    """商店安装路径会随升级变化，已配置商店版时优先使用当前最新安装包。"""
    if not configured_app_path or not _is_windows_store_codex_path(configured_app_path):
        return configured_app_path
    try:
        detected_path = find_windowsapps_codex_path_by_package()
    except Exception as exc:
        logger.warning("重新识别 Codex 商店安装包失败，继续使用已配置路径 错误=%s", exc)
        return configured_app_path
    latest_path = Path(detected_path) if detected_path else None
    if latest_path and latest_path.is_file():
        return latest_path
    return configured_app_path


def _cleanup_orphaned_portable_processes(config, source_codex_path):
    """更新共享副本前清理已无主窗口的残留辅助进程。"""
    target_app_dir = _get_shared_app_root(config) / PORTABLE_APP_DIR_NAME
    if not target_app_dir.exists() or not portable_app_needs_update(source_codex_path, target_app_dir):
        return
    processes = read_processes_in_directory(target_app_dir)
    if not processes:
        return
    main_processes = [
        process
        for process in processes
        if str(process.get("name") or "").lower() in ("chatgpt.exe", "codex.exe")
        and "--type=" not in str(process.get("command_line") or "").lower()
        and " app-server" not in str(process.get("command_line") or "").lower()
    ]
    if main_processes:
        raise RuntimeError("Codex 客户端需要更新，请先关闭所有正在运行的 Codex 实例后重试")

    pids = {int(process.get("pid") or 0) for process in processes if process.get("pid")}
    logger.info("清理旧版 Codex 残留辅助进程 数量=%s", len(pids))
    for pid in pids:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    deadline = time.monotonic() + 5
    remaining = read_processes_in_directory(target_app_dir)
    while remaining and time.monotonic() < deadline:
        time.sleep(0.25)
        remaining = read_processes_in_directory(target_app_dir)
    if remaining:
        raise RuntimeError("旧版 Codex 后台进程未能完全退出，请在任务管理器结束后重试")


def _resolve_configured_codex_app_path(configured_path):
    """把用户保存的文件或目录解析为客户端主程序。"""
    if not configured_path:
        return None
    path = Path(configured_path)
    if path.is_file() and path.name.lower() in ("chatgpt.exe", "codex.exe", "codex desktop.exe"):
        for chatgpt_path in (path.with_name("ChatGPT.exe"), path.parent.parent / "ChatGPT.exe"):
            if chatgpt_path.exists():
                return chatgpt_path
        return None if path.parent.name.lower() == "resources" else path
    if not path.is_dir():
        return None
    for candidate_dir in (path, path / "current", path / "app", path / "Application"):
        for file_name in ("ChatGPT.exe", "Codex.exe", "Codex Desktop.exe"):
            candidate = candidate_dir / file_name
            if candidate.exists():
                return candidate
    return None


def _build_app_launch_spec(codex_path):
    """把桌面程序路径转换为启动说明，微软商店版改走应用标识。"""
    path = Path(codex_path)
    if _is_windows_store_codex_path(path):
        store_app_id = _find_windows_store_codex_app_id()
        if store_app_id:
            return {
                "kind": "store",
                "command": ["explorer.exe", f"shell:AppsFolder\\{store_app_id}"],
                "display": str(path),
            }
    return {
        "kind": "app",
        "command": [str(path)],
        "display": str(path),
        "cwd": str(path.parent),
    }


def _is_windows_store_codex_path(path):
    """判断路径是否指向微软商店版客户端安装目录。"""
    normalized = normalize_path_for_match(path)
    return any(
        marker in normalized
        for marker in ("\\windowsapps\\openai.codex_", "\\windowsapps\\openai.chatgpt_")
    )


def _find_windows_store_codex_app_id():
    """读取微软商店版 Codex 的应用启动标识。"""
    if os.name != "nt":
        return ""
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$pattern = '^OpenAI\.(Codex|ChatGPT)_[^!]+![^!]+$'
$matches = @()
$matches += Get-StartApps | Where-Object { $_.AppID -match $pattern } | Select-Object -ExpandProperty AppID
foreach ($packageName in @('OpenAI.Codex', 'OpenAI.ChatGPT')) {
  $pkg = Get-AppxPackage -Name $packageName | Select-Object -First 1
  if ($null -ne $pkg) {
    $manifest = $pkg | Get-AppxPackageManifest
    foreach ($app in @($manifest.Package.Applications.Application)) {
      if ($null -ne $app -and $app.Id) {
        $matches += ('{0}!{1}' -f $pkg.PackageFamilyName, $app.Id)
      }
    }
  }
}
$matches | Where-Object { $_ -match $pattern } | Sort-Object @{Expression = { $_ -notmatch '!App$' }}, @{Expression = { $_ }} | Select-Object -First 1
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")


def _launch_default_codex(profile_name="", skin_port=None):
    """启动默认安装的 Codex 桌面端。"""
    config = load_config()
    if skin_port is not None:
        codex_path = Path(_resolve_codex_app_source_path(config))
        if _is_windows_store_codex_path(codex_path):
            _cleanup_orphaned_portable_processes(config, codex_path)
            codex_path = Path(
                prepare_portable_codex_path(
                    codex_path,
                    _get_shared_app_root(config),
                    progress_callback=lambda percent, copied, total: _emit_backend_progress(
                        {
                            "operation": "portable-client-copy",
                            "profileName": profile_name,
                            "percent": percent,
                            "copiedBytes": copied,
                            "totalBytes": total,
                        }
                    ),
                )
            )
        launch_spec = {
            "kind": "app",
            "command": [str(codex_path)],
            "display": str(codex_path),
            "cwd": str(codex_path.parent),
        }
    else:
        launch_spec = _resolve_codex_launch_spec(config)
    launch_settings = db.load_profile_launch_settings(profile_name) if profile_name else {}
    extra_args = [str(value) for value in launch_settings.get("args", [])] if launch_spec["kind"] == "app" else []
    if skin_port is not None:
        extra_args = _append_codex_skin_args(extra_args, skin_port)
    command = [*launch_spec["command"], *extra_args]
    env = os.environ.copy()
    env.update({str(key): str(value) for key, value in dict(launch_settings.get("env") or {}).items()})
    working_dir = str(launch_settings.get("workingDir") or launch_spec.get("cwd") or "") or None
    logger.info("Codex 启动开始 类型=%s 显示=%s", launch_spec["kind"], launch_spec["display"])
    try:
        process = subprocess.Popen(
            command,
            cwd=working_dir,
            env=env,
            close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        logger.info("Codex 启动成功 类型=%s 显示=%s", launch_spec["kind"], launch_spec["display"])
        if skin_port is not None:
            return {
                "processId": process.pid,
                "skinSession": {
                    "profileName": profile_name or SYSTEM_PROFILE_NAME,
                    "port": skin_port,
                    "processId": process.pid,
                },
            }
        return {"processId": process.pid}
    except FileNotFoundError as exc:
        logger.exception("Codex 启动失败 显示=%s 错误=%s", launch_spec["display"], exc)
        raise FileNotFoundError("未找到 Codex 桌面客户端，请在设置中重新识别或确认已安装") from exc


def _get_directory_size(directory):
    """统计账号资料目录实际占用的文件字节数，跳过链接目录避免循环扫描。"""
    if not directory.exists():
        return 0
    total_size = 0
    for root, dirs, files in os.walk(directory):
        root_path = Path(root)
        kept_dirs = []
        for directory_name in dirs:
            source_child = root_path / directory_name
            if is_reparse_point(source_child):
                continue
            kept_dirs.append(directory_name)
        dirs[:] = kept_dirs
        for file_name in files:
            file_path = root_path / file_name
            if is_reparse_point(file_path):
                continue
            try:
                total_size += file_path.stat().st_size
            except OSError:
                continue
    return total_size


def _format_bytes(size):
    """把字节数转成界面可读的磁盘占用文本。"""
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024


def _copy_directory(source_dir, target_dir):
    """复制账号资料根目录，跳过 junction 等特殊目录。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(source_dir):
        root_path = Path(root)
        relative_root = root_path.relative_to(source_dir)
        target_root = target_dir / relative_root
        target_root.mkdir(parents=True, exist_ok=True)
        kept_dirs = []
        for directory_name in dirs:
            source_child = root_path / directory_name
            if is_reparse_point(source_child):
                continue
            kept_dirs.append(directory_name)
            (target_root / directory_name).mkdir(parents=True, exist_ok=True)
        dirs[:] = kept_dirs
        for file_name in files:
            source_file = root_path / file_name
            if is_reparse_point(source_file):
                continue
            shutil.copy2(source_file, target_root / file_name)
        try:
            shutil.copystat(root_path, target_root)
        except OSError:
            pass
