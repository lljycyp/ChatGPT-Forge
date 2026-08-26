import contextlib
import os
import time
from pathlib import Path

from core import db
from core.app_server_service import read_account_and_rate_limits
from core.constants import DB_PATH
from core.profile_service import get_active_config_path, get_profile_auth_path, sync_codex_home_to_profile


def load_usage_cache():
    """从 SQLite 读取额度缓存。"""
    return db.load_usage_cache()


def save_usage_cache(cache):
    """把额度缓存写入 SQLite。"""
    db.save_usage_cache(cache)


def get_cached_profile_usage(profile_name):
    """读取单个账号的额度快照。"""
    usage = load_usage_cache().get(profile_name)
    return usage if isinstance(usage, dict) else None


def refresh_profile_usage(profile_name, profile_dir, share_system_config=False, use_codex_home_auth=False):
    """刷新单个账号额度并写入缓存。"""
    started_at = time.time()
    usage = _build_profile_usage(
        profile_dir,
        share_system_config=share_system_config,
        use_codex_home_auth=use_codex_home_auth,
    )
    cache = _merge_usage_results({profile_name: usage}, started_at)
    return cache.get(profile_name, usage)


def refresh_all_profile_usage(profile_dirs, share_system_config=False, use_codex_home_auth=False):
    """串行刷新全部账号额度，避免同时启动多个 App Server。"""
    started_at = time.time()
    if not profile_dirs:
        cache = load_usage_cache()
        save_usage_cache(cache)
        return {}

    results = {}
    for profile_name, profile_dir in profile_dirs.items():
        try:
            results[profile_name] = _build_profile_usage(
                Path(profile_dir),
                share_system_config=share_system_config,
                use_codex_home_auth=use_codex_home_auth,
            )
        except Exception as exc:
            results[profile_name] = _usage_error(f"额度读取失败：{exc}")

    cache = _merge_usage_results(results, started_at)
    return {name: cache.get(name) for name in profile_dirs}


def _merge_usage_results(results, started_at):
    """合并刷新结果，避免较早请求覆盖较新的成功快照。"""
    with _file_lock(DB_PATH.with_name(f".{DB_PATH.name}.usage.lock")):
        cache = load_usage_cache()
        for profile_name, usage in results.items():
            current = cache.get(profile_name)
            current_fetched_at = current.get("fetchedAt") if isinstance(current, dict) else None
            if isinstance(current_fetched_at, (int, float)) and current_fetched_at > started_at:
                continue
            if _should_keep_current_usage(current, usage):
                continue
            cache[profile_name] = usage
        save_usage_cache(cache)
        return cache


def rename_cached_usage(old_name, new_name):
    """账号改名时同步迁移额度缓存。"""
    cache = load_usage_cache()
    if old_name in cache:
        cache[new_name] = cache.pop(old_name)
        save_usage_cache(cache)


def remove_cached_usage(profile_name):
    """账号删除时清理额度缓存。"""
    cache = load_usage_cache()
    if profile_name in cache:
        cache.pop(profile_name, None)
        save_usage_cache(cache)


def _build_profile_usage(profile_dir, share_system_config=False, use_codex_home_auth=False):
    """通过官方 App Server 读取账号和 Codex 额度。"""
    profile_dir = Path(profile_dir)
    auth_path = _resolve_usage_auth_path(profile_dir, use_codex_home_auth)
    if not auth_path.exists():
        return _usage_error("未找到登录信息，请先保存当前账号资料")
    config_path = _resolve_usage_config_path(profile_dir, share_system_config, use_codex_home_auth)

    try:
        account, rate_limits = read_account_and_rate_limits(profile_dir, auth_path, config_path)
        usage = _map_app_server_usage(account, rate_limits)
        _sync_usage_auth_to_profile(profile_dir, auth_path, use_codex_home_auth)
        return usage
    except Exception as exc:
        return _usage_error(_normalize_usage_error(str(exc)))


def _resolve_usage_auth_path(profile_dir, use_codex_home_auth=False):
    """多开模式使用运行副本，其余场景使用账号唯一持久认证。"""
    profile_dir = Path(profile_dir)
    codex_home_auth_path = profile_dir / "CodexHome" / "auth.json"
    if use_codex_home_auth and codex_home_auth_path.exists():
        return codex_home_auth_path
    return get_profile_auth_path(profile_dir)


def _resolve_usage_config_path(profile_dir, share_system_config=False, use_codex_home_auth=False):
    """switch 使用系统配置，multi 使用账号 CodexHome 配置。"""
    profile_dir = Path(profile_dir)
    if use_codex_home_auth:
        return profile_dir / "CodexHome" / "config.toml"
    return get_active_config_path()


def _sync_usage_auth_to_profile(profile_dir, auth_path, use_codex_home_auth=False):
    """把 App Server 刷新后的多开认证同步回账号主资料。"""
    if not use_codex_home_auth:
        return
    sync_codex_home_to_profile(profile_dir)


def _map_app_server_usage(account, payload):
    """把 account/rateLimits/read 转换成前端稳定结构。"""
    rate_limits = payload.get("rateLimits") if isinstance(payload, dict) else None
    rate_limits = rate_limits if isinstance(rate_limits, dict) else {}
    windows = [
        window
        for key in ("primary", "secondary")
        for window in (rate_limits.get(key),)
        if isinstance(window, dict)
    ]
    reset_credits = payload.get("rateLimitResetCredits") or {}
    reset_credit_items = reset_credits.get("credits") or []
    credits = rate_limits.get("credits") or {}
    return {
        "fetchedAt": time.time(),
        "planType": _clean_string(rate_limits.get("planType") or account.get("planType")),
        "oneWeek": _to_usage_window(_find_window(windows, 7 * 24 * 60 * 60)),
        "resetCredits": _optional_int(reset_credits.get("availableCount")),
        "resetCreditExpiresAt": _available_credit_expiries(reset_credit_items),
        "hasCredits": bool(credits.get("hasCredits")),
        "creditsUnlimited": bool(credits.get("unlimited")),
        "spendControlReached": bool(rate_limits.get("rateLimitReachedType")),
        "rateLimitReachedType": _clean_string(rate_limits.get("rateLimitReachedType")),
        "error": None,
    }


def _find_window(windows, target_seconds):
    """按真实时长查找额度窗口。"""
    target_minutes = target_seconds / 60
    return next(
        (
            window
            for window in windows
            if window.get("windowDurationMins") == target_minutes
            and isinstance(window.get("usedPercent"), (int, float))
        ),
        None,
    )


def _to_usage_window(window):
    """把 App Server 窗口字段转换为前端字段。"""
    if not window:
        return None
    used_percent = _clamp_percent(float(window.get("usedPercent", 0)))
    return {
        "usedPercent": used_percent,
        "remainingPercent": _clamp_percent(100 - used_percent),
        "windowSeconds": int(window.get("windowDurationMins", 0) * 60),
        "resetAt": int(window["resetsAt"]) if isinstance(window.get("resetsAt"), (int, float)) else None,
    }


def _usage_error(message, plan_type=None):
    """生成失败快照，让前端展示明确原因。"""
    return {
        "fetchedAt": time.time(),
        "planType": plan_type,
        "oneWeek": None,
        "resetCredits": None,
        "resetCreditExpiresAt": [],
        "hasCredits": False,
        "creditsUnlimited": False,
        "spendControlReached": False,
        "rateLimitReachedType": None,
        "error": message,
    }


def _optional_int(value):
    return int(value) if isinstance(value, (int, float)) else None


def _available_credit_expiries(credits):
    expires_at_values = []
    for credit in credits:
        if not isinstance(credit, dict) or credit.get("status") != "available":
            continue
        value = credit.get("expiresAt")
        if isinstance(value, (int, float)):
            expires_at_values.append(int(value))
    return sorted(expires_at_values)


def _normalize_usage_error(message):
    """把 App Server 常见错误转成用户可理解的提示。"""
    lowered = message.lower()
    if "api key" in lowered or "apikey" in lowered:
        return "API Key 账号不提供 Codex 套餐额度"
    if "unauthorized" in lowered or "not logged" in lowered or "expired" in lowered:
        return "登录令牌已过期，请重新授权后再刷新额度"
    if message.startswith("未找到 Codex 内置 Codex App Server"):
        return message
    return f"额度读取失败：{message}"


def _should_keep_current_usage(current, usage):
    """临时网络失败不覆盖已有成功额度。"""
    if not isinstance(current, dict) or current.get("error"):
        return False
    if not isinstance(usage, dict):
        return False
    error = usage.get("error")
    return isinstance(error, str) and _is_transient_usage_error(error)


def _is_transient_usage_error(message):
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "超时",
            "timeout",
            "timed out",
            "connection reset",
            "connection aborted",
            "temporarily unavailable",
            "unexpected_eof",
            "ssl",
        )
    )


def _clean_string(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _clamp_percent(value):
    return max(0, min(100, value))


@contextlib.contextmanager
def _file_lock(lock_path, timeout_seconds=30):
    """用独占锁文件串行化跨进程缓存读写。"""
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout_seconds
    file_handle = None
    while True:
        try:
            file_handle = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(file_handle, str(os.getpid()).encode("utf-8"))
            break
        except FileExistsError:
            if time.time() >= deadline:
                raise TimeoutError(f"等待文件锁超时：{lock_path}")
            time.sleep(0.08)
    try:
        yield
    finally:
        if file_handle is not None:
            os.close(file_handle)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
