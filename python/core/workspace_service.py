import json
import re
import shutil
import time
import tomllib
from pathlib import Path


def read_workspace(codex_home):
    codex_home = Path(codex_home)
    config_path = codex_home / "config.toml"
    config_error = ""
    try:
        config = _read_toml(config_path)
    except ValueError as exc:
        config = {}
        config_error = str(exc)
    mcp_servers = config.get("mcp_servers") if isinstance(config, dict) else {}
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
    return {
        "codexHome": str(codex_home),
        "configError": config_error,
        "agentsPath": str(codex_home / "AGENTS.md"),
        "agentsContent": _read_text(codex_home / "AGENTS.md"),
        "mcpServers": [
            {**value, "name": name, "enabled": value.get("enabled") is not False}
            for name, value in sorted(mcp_servers.items())
            if isinstance(value, dict)
        ],
        "skills": _list_skills(codex_home),
    }


def save_agents(codex_home, content):
    path = Path(codex_home) / "AGENTS.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = _backup_file(path)
    path.write_text(str(content or ""), encoding="utf-8")
    return {"path": str(path), "content": path.read_text(encoding="utf-8"), "backupPath": str(backup_path) if backup_path else ""}


def save_mcp_server(config_path, server):
    name = _validate_name(server.get("name"), "MCP 名称")
    command = str(server.get("command") or "").strip()
    if not command:
        raise ValueError("MCP 命令不能为空")
    args = [str(value) for value in server.get("args", []) if str(value).strip()]
    env = {
        str(key).strip(): str(value)
        for key, value in dict(server.get("env") or {}).items()
        if str(key).strip()
    }
    enabled = server.get("enabled") is not False
    config_path = Path(config_path)
    content = _read_text(config_path)
    content = _remove_mcp_section(content, name).rstrip()
    section = [f"[mcp_servers.{name}]", f"command = {_toml_string(command)}"]
    if args:
        section.append("args = [" + ", ".join(_toml_string(value) for value in args) + "]")
    if not enabled:
        section.append("enabled = false")
    if env:
        section.extend(["", f"[mcp_servers.{name}.env]"])
        section.extend(f"{_toml_key(key)} = {_toml_string(value)}" for key, value in sorted(env.items()))
    next_content = (content + "\n\n" if content else "") + "\n".join(section) + "\n"
    tomllib.loads(next_content)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    _backup_file(config_path)
    config_path.write_text(next_content, encoding="utf-8")
    return {"name": name}


def delete_mcp_server(config_path, name):
    config_path = Path(config_path)
    name = _validate_name(name, "MCP 名称")
    content = _remove_mcp_section(_read_text(config_path), name).rstrip()
    if content:
        tomllib.loads(content)
    _backup_file(config_path)
    config_path.write_text(content + ("\n" if content else ""), encoding="utf-8")
    return {"name": name}


def set_mcp_enabled(config_path, name, enabled):
    config_path = Path(config_path)
    name = _validate_name(name, "MCP 名称")
    content = _read_text(config_path)
    config = _read_toml(config_path)
    servers = config.get("mcp_servers") if isinstance(config, dict) else None
    if not isinstance(servers, dict) or not isinstance(servers.get(name), dict):
        raise FileNotFoundError("MCP 服务不存在")

    header = re.search(rf"(?m)^\[mcp_servers\.{re.escape(name)}\]\s*$", content)
    if not header:
        raise ValueError("无法定位 MCP 服务配置")
    next_header = re.search(r"(?m)^\[[^\]]+\]\s*$", content[header.end() :])
    section_end = header.end() + next_header.start() if next_header else len(content)
    section = content[header.end() : section_end]
    enabled_line = f"enabled = {'true' if enabled else 'false'}"
    if re.search(r"(?m)^enabled\s*=.*$", section):
        section = re.sub(r"(?m)^enabled\s*=.*$", enabled_line, section, count=1)
    else:
        section = f"\n{enabled_line}{section}"
    next_content = content[: header.end()] + section + content[section_end:]
    tomllib.loads(next_content)
    _backup_file(config_path)
    config_path.write_text(next_content, encoding="utf-8")
    return {"name": name, "enabled": bool(enabled)}


def set_skill_enabled(codex_home, name, enabled):
    codex_home = Path(codex_home)
    name = _validate_name(name, "Skill 名称")
    skills_dir = codex_home / "skills"
    disabled_dir = codex_home / ".disabled-skills"
    source = disabled_dir / name if enabled else skills_dir / name
    target = skills_dir / name if enabled else disabled_dir / name
    if not source.is_dir():
        raise FileNotFoundError("Skill 不存在")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError("目标 Skill 已存在")
    shutil.move(str(source), str(target))
    return {"name": name, "enabled": bool(enabled)}


def install_skill(codex_home, source_path):
    source = Path(source_path).resolve()
    if not source.is_dir() or not (source / "SKILL.md").is_file():
        raise ValueError("请选择包含 SKILL.md 的 Skill 目录")
    name = _validate_name(source.name, "Skill 名称")
    target = Path(codex_home) / "skills" / name
    if target.exists():
        raise FileExistsError("同名 Skill 已存在")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    return {"name": name, "path": str(target)}


def remove_skill(codex_home, name):
    codex_home = Path(codex_home)
    name = _validate_name(name, "Skill 名称")
    source = next((path for path in (codex_home / "skills" / name, codex_home / ".disabled-skills" / name) if path.is_dir()), None)
    if source is None:
        raise FileNotFoundError("Skill 不存在")
    backup = codex_home / ".skill-backups" / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1_000_000_000:09d}-{name}"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(backup))
    return {"name": name, "backupPath": str(backup)}


def list_sessions(codex_home, limit=200):
    session_root = Path(codex_home) / "sessions"
    if not session_root.is_dir():
        return []
    files = sorted(session_root.rglob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [_read_session_summary(path) for path in files[: max(1, min(int(limit), 1000))]]


def _read_session_summary(path):
    summary = {
        "id": path.stem,
        "title": "",
        "projectPath": "",
        "path": str(path),
        "updatedAt": path.stat().st_mtime,
        "sizeBytes": path.stat().st_size,
    }
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                if index >= 120:
                    break
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = event.get("payload") if isinstance(event, dict) else None
                if event.get("type") == "session_meta" and isinstance(payload, dict):
                    summary["id"] = str(payload.get("id") or summary["id"])
                    summary["projectPath"] = str(payload.get("cwd") or payload.get("workspace") or "")
                if event.get("type") == "turn_context" and isinstance(payload, dict) and not summary["projectPath"]:
                    summary["projectPath"] = str(payload.get("cwd") or "")
                text = _user_text(event)
                if text and not summary["title"]:
                    summary["title"] = text[:120]
    except OSError:
        pass
    summary["title"] = summary["title"] or path.stem
    return summary


def _user_text(event):
    if not isinstance(event, dict) or event.get("type") != "response_item":
        return ""
    payload = event.get("payload")
    if not isinstance(payload, dict) or payload.get("role") != "user":
        return ""
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    return " ".join(
        str(item.get("text") or "").strip()
        for item in content
        if isinstance(item, dict) and item.get("type") in ("input_text", "text")
    ).strip()


def _list_skills(codex_home):
    result = []
    for enabled, directory in ((True, Path(codex_home) / "skills"), (False, Path(codex_home) / ".disabled-skills")):
        if not directory.is_dir():
            continue
        for child in sorted(directory.iterdir(), key=lambda path: path.name.lower()):
            if child.is_dir():
                result.append(
                    {
                        "name": child.name,
                        "enabled": enabled,
                        "path": str(child),
                        "hasManifest": (child / "SKILL.md").is_file(),
                    }
                )
    return result


def _remove_mcp_section(content, name):
    escaped = re.escape(name)
    pattern = re.compile(
        rf"(?ms)^\[mcp_servers\.{escaped}(?:\.[^\]]+)?\]\s*\n.*?(?=^\[(?!mcp_servers\.{escaped}(?:\.|\]))[^\]]+\]\s*$|\Z)"
    )
    previous = None
    while previous != content:
        previous = content
        content = pattern.sub("", content)
    return re.sub(r"\n{3,}", "\n\n", content)


def _read_toml(path):
    if not Path(path).is_file():
        return {}
    try:
        return tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"config.toml 语法错误：{exc}") from exc


def _read_text(path):
    return Path(path).read_text(encoding="utf-8") if Path(path).is_file() else ""


def _validate_name(value, label):
    value = str(value or "").strip()
    if not value or not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise ValueError(f"{label}只能包含字母、数字、点、下划线和短横线")
    return value


def _toml_string(value):
    return json.dumps(str(value), ensure_ascii=False)


def _toml_key(value):
    return value if re.fullmatch(r"[A-Za-z0-9_-]+", value) else _toml_string(value)


def _backup_file(path):
    path = Path(path)
    if not path.is_file():
        return None
    backup_dir = path.parent / ".forge-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{path.stem}-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1_000_000_000:09d}{path.suffix}"
    shutil.copy2(path, backup_path)
    return backup_path
