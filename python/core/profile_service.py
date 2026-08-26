import json
import os
import re
import shutil
import time
import tomllib
import uuid
from pathlib import Path

from core.constants import DEFAULT_CODEX_ENV_PATH


def get_active_codex_dir():
    """返回默认 Codex 当前用户配置目录。"""
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".codex"


def get_active_auth_path():
    """返回当前生效的 Codex 认证文件路径。"""
    return get_active_codex_dir() / "auth.json"


def get_active_config_path():
    """返回当前生效的 Codex 配置文件路径。"""
    return get_active_codex_dir() / "config.toml"


def import_active_profile(profile_dir, share_system_config=False):
    """把当前生效的 Codex 账号资料保存为启动器账号资料。"""
    active_auth_path = get_active_auth_path()
    if not active_auth_path.exists():
        raise FileNotFoundError("当前 Codex 认证文件不存在，请先用默认 Codex 完成登录")

    profile_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(active_auth_path, profile_dir / "auth.json")
    ensure_profile_config_path(profile_dir)


def import_auth_json_profile(profile_dir, auth_json, share_system_config=False):
    """把指定授权内容保存为启动器账号资料，不改动当前默认 Codex。"""
    profile_dir.mkdir(parents=True, exist_ok=True)
    write_profile_auth_json(profile_dir / "auth.json", auth_json)
    ensure_profile_config_path(profile_dir)


def write_profile_auth_json(auth_path, auth_json):
    """原子写入账号 auth.json，避免刷新令牌时留下半截文件。"""
    auth_path = Path(auth_path)
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = auth_path.with_name(f".{auth_path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(
        json.dumps(auth_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(auth_path)


def ensure_profile_env_file(codex_home_dir):
    """确保账号 CodexHome 里有默认 .env；已有账号专属配置时不覆盖。"""
    target_env_path = Path(codex_home_dir) / ".env"
    if target_env_path.exists() or not DEFAULT_CODEX_ENV_PATH.exists():
        return
    target_env_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DEFAULT_CODEX_ENV_PATH, target_env_path)


def prepare_profile_codex_home(profile_dir, share_system_config=False):
    """把账号资料同步到多开模式使用的 CodexHome。"""
    profile_dir = Path(profile_dir)
    source_auth_path = get_profile_auth_path(profile_dir)
    if not source_auth_path.exists():
        raise FileNotFoundError("账号认证文件不存在，无法启动")

    codex_home_dir = profile_dir / "CodexHome"
    codex_home_dir.mkdir(parents=True, exist_ok=True)
    runtime_auth_path = codex_home_dir / "auth.json"
    if (
        runtime_auth_path.exists()
        and runtime_auth_path.stat().st_mtime_ns > source_auth_path.stat().st_mtime_ns
    ):
        sync_codex_home_to_profile(profile_dir)
    config_path = ensure_profile_config_path(profile_dir)
    sanitize_profile_config_file(config_path)
    require_file_auth_store(config_path)
    ensure_profile_env_file(codex_home_dir)
    shutil.copy2(source_auth_path, runtime_auth_path)


def sync_codex_home_to_profile(profile_dir, share_system_config=False):
    """多开实例关闭后，把 CodexHome 中刷新过的认证回写到账号根目录。"""
    profile_dir = Path(profile_dir)
    codex_home_dir = profile_dir / "CodexHome"
    auth_path = codex_home_dir / "auth.json"
    if auth_path.exists():
        try:
            auth_json = json.loads(auth_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("运行时 auth.json 内容不是有效的 JSON") from exc
        write_profile_auth_json(get_profile_auth_path(profile_dir), auth_json)


def ensure_profile_config_path(profile_dir):
    """确保账号级配置只存在于 CodexHome/config.toml。"""
    profile_dir = Path(profile_dir)
    config_path = resolve_profile_config_path(profile_dir)
    if config_path.exists():
        return config_path
    active_config_path = get_active_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if active_config_path.exists():
        config_path.write_text(
            sanitize_profile_config_text(active_config_path.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
    else:
        config_path.write_text('cli_auth_credentials_store = "file"\n', encoding="utf-8")
    return config_path


def sanitize_profile_config_file(config_path):
    """移除不能跨 Codex 实例复制的动态配置。"""
    config_path = Path(config_path)
    current = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    sanitized = sanitize_profile_config_text(current)
    if sanitized != current:
        config_path.write_text(sanitized, encoding="utf-8")


def sanitize_profile_config_text(text):
    """保留用户配置，同时过滤应用生成的管道、缓存和运行时路径。"""
    dynamic_sections = (
        "mcp_servers.node_repl",
        "marketplaces.openai-bundled",
        "hooks.state",
    )
    output = []
    skip_section = False
    section_name = ""
    credential_store_pattern = re.compile(r"^\s*cli_auth_credentials_store\s*=")
    notify_pattern = re.compile(r"^\s*notify\s*=")

    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section_name = stripped.strip("[]").replace('"', "").replace("'", "")
            skip_section = any(
                section_name == prefix or section_name.startswith(f"{prefix}.")
                for prefix in dynamic_sections
            )
        if skip_section:
            continue
        if not section_name and credential_store_pattern.match(line):
            continue
        if not section_name and notify_pattern.match(line):
            normalized = line.lower().replace("/", "\\")
            if "\\openai\\codex\\runtimes\\" in normalized or "codex-computer-use" in normalized:
                continue
        output.append(line)

    while output and not output[-1].strip():
        output.pop()
    return 'cli_auth_credentials_store = "file"\n' + "\n".join(output).lstrip() + "\n"


def apply_profile(profile_dir, share_system_config=False):
    """把指定账号资料写入当前 Codex 活动配置。"""
    source_auth_path = get_profile_auth_path(profile_dir)
    if not source_auth_path.exists():
        raise FileNotFoundError("账号认证文件不存在，无法切换")

    active_dir = get_active_codex_dir()
    active_dir.mkdir(parents=True, exist_ok=True)
    require_file_auth_store(get_active_config_path())
    backup_active_files(active_dir)
    shutil.copy2(source_auth_path, get_active_auth_path())


def get_auth_credentials_store(config_path):
    """读取认证缓存位置；未配置时保持现有 auth.json 行为。"""
    config_path = Path(config_path)
    if not config_path.exists():
        return "file"
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"config.toml 语法错误：{exc}") from exc
    value = str(config.get("cli_auth_credentials_store") or "file").strip().lower()
    return value if value in ("file", "keyring", "auto") else "file"


def require_file_auth_store(config_path):
    """Forge 通过 auth.json 切换账号，拒绝可能忽略该文件的凭据库模式。"""
    store = get_auth_credentials_store(config_path)
    if store != "file":
        raise RuntimeError(
            f"当前认证存储为 {store}，账号切换需要在 config.toml 中设置 "
            'cli_auth_credentials_store = "file"'
        )


def backup_active_files(active_dir):
    """切换前备份当前活动认证和配置，便于误操作恢复。"""
    backup_dir = active_dir / "account-switcher-backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    for file_name in ("auth.json", "config.toml"):
        source_path = active_dir / file_name
        if source_path.exists():
            shutil.copy2(source_path, backup_dir / f"{file_name}.{timestamp}.bak")


def get_profile_status(profile_dir, share_system_config=False):
    """检查账号资料是否完整。"""
    auth_path = get_profile_auth_path(profile_dir)
    config_path = resolve_profile_config_path(profile_dir)
    errors = []
    warnings = []
    if not profile_dir.exists():
        errors.append("账号资料目录不存在")
    if not auth_path.exists():
        errors.append("账号认证文件不存在")
    if not config_path.exists():
        warnings.append("多开配置文件不存在，启动多开时会自动创建")
    return {
        "authPath": str(auth_path),
        "authExists": auth_path.exists(),
        "configPath": str(config_path),
        "configExists": config_path.exists(),
        "errors": errors,
        "warnings": warnings,
    }


def get_profile_auth_path(profile_dir):
    """返回账号唯一持久认证文件。"""
    return Path(profile_dir) / "auth.json"


def resolve_profile_config_path(profile_dir):
    """返回 multi 模式唯一账号级配置文件。"""
    profile_dir = Path(profile_dir)
    return profile_dir / "CodexHome" / "config.toml"
