import base64
import calendar
import json
import time
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_OAUTH_ISSUER = "https://auth.openai.com"
REQUEST_TIMEOUT_SECONDS = 30
REFRESH_LEAD_SECONDS = 10 * 60
KEEPALIVE_LAST_REFRESH_BASE_AGE_SECONDS = 7 * 24 * 60 * 60
KEEPALIVE_LAST_REFRESH_JITTER_SECONDS = 24 * 60 * 60


def extract_auth(auth_json):
    """从 Codex auth.json 提取额度接口和令牌刷新需要的身份信息。"""
    tokens = auth_tokens(auth_json)
    if not tokens:
        if auth_kind(auth_json) == "api":
            raise ValueError("API Key 账号不提供 ChatGPT 套餐额度")
        mode = str(auth_json.get("auth_mode") or "").lower() if isinstance(auth_json, dict) else ""
        if mode and mode not in ("chatgpt", "chatgpt_auth_tokens"):
            raise ValueError("当前账号不是 ChatGPT 登录模式，无法读取额度")
        raise ValueError("登录信息缺少 ChatGPT 令牌，请重新授权")

    access_token = clean_string(tokens.get("access_token"))
    id_token = clean_string(tokens.get("id_token"))
    refresh_token = clean_string(tokens.get("refresh_token"))
    account_id = clean_string(tokens.get("account_id") or tokens.get("chatgpt_account_id"))
    if not access_token:
        raise ValueError("登录信息缺少 access_token，无法读取额度")
    if not id_token:
        raise ValueError("登录信息缺少 id_token，无法识别账号额度")

    claims = decode_jwt_payload(id_token)
    auth_claim = claims.get("https://api.openai.com/auth") if isinstance(claims, dict) else None
    auth_claim = auth_claim if isinstance(auth_claim, dict) else {}
    if not account_id:
        account_id = clean_string(auth_claim.get("chatgpt_account_id"))
    if not account_id:
        raise ValueError("无法从登录信息识别 ChatGPT 账号编号")

    return {
        "accessToken": access_token,
        "idToken": id_token,
        "refreshToken": refresh_token,
        "accountId": account_id,
        "planType": clean_string(auth_claim.get("chatgpt_plan_type")),
        "email": clean_string(claims.get("email")) if isinstance(claims, dict) else None,
        "claims": claims,
    }


def auth_tokens(auth_json):
    """兼容新旧 auth.json 结构，优先读取 tokens 节点。"""
    if not isinstance(auth_json, dict):
        return None
    tokens = auth_json.get("tokens")
    if isinstance(tokens, dict):
        return tokens
    if "access_token" in auth_json and "id_token" in auth_json:
        return auth_json
    return None


def auth_kind(auth_json):
    """识别 Forge 支持的 ChatGPT 或 API Key 认证。"""
    if auth_tokens(auth_json):
        return "chatgpt"
    if isinstance(auth_json, dict) and clean_string(auth_json.get("OPENAI_API_KEY")):
        return "api"
    return ""


def ensure_fresh_auth(auth_json, force=False):
    """必要时刷新登录令牌，并返回新的 auth.json 与是否刷新。"""
    if not force and not auth_needs_keepalive_refresh(auth_json):
        return auth_json, False
    return refresh_chatgpt_auth_tokens(auth_json), True


def auth_needs_keepalive_refresh(auth_json):
    """判断是否需要主动保活，参考 Codex Tools 的保守刷新策略。"""
    if auth_tokens_expire_within(auth_json, REFRESH_LEAD_SECONDS):
        return True

    tokens = auth_tokens(auth_json)
    if not tokens:
        return False
    root = auth_json if isinstance(auth_json, dict) else {}
    last_refresh = parse_last_refresh(root.get("last_refresh"))
    if last_refresh is None:
        return True

    account_key = ""
    try:
        auth = extract_auth(auth_json)
        account_key = f"{auth.get('email') or ''}|{auth['accountId']}"
    except Exception:
        pass
    max_age = keepalive_max_last_refresh_age_seconds(account_key)
    return int(time.time()) - last_refresh >= max_age


def auth_tokens_expire_within(auth_json, lead_seconds):
    """只用 access_token 判断刷新窗口，避免因 id_token 过期过早刷新。"""
    tokens = auth_tokens(auth_json)
    if not tokens:
        return False
    access_token = clean_string(tokens.get("access_token"))
    expires_at = jwt_expiration(access_token)
    if expires_at is None:
        return False
    return expires_at <= int(time.time()) + max(0, int(lead_seconds))


def refresh_chatgpt_auth_tokens(auth_json):
    """使用 refresh_token 刷新 ChatGPT 登录令牌，并返回新的 auth.json。"""
    auth = extract_auth(auth_json)
    refresh_token = auth.get("refreshToken")
    if not refresh_token:
        raise ValueError("登录信息缺少 refresh_token，无法自动刷新，请重新授权")

    claims_value = auth.get("claims")
    claims = claims_value if isinstance(claims_value, dict) else {}
    issuer = clean_string(claims.get("iss")) or DEFAULT_OAUTH_ISSUER
    token_url = f"{issuer.rstrip('/')}/oauth/token"
    form = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    client_id = extract_client_id_from_claims(claims)
    if client_id:
        form["client_id"] = client_id

    request = urllib.request.Request(
        token_url,
        data=urllib.parse.urlencode(form).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "CodexForge/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"刷新登录令牌失败：{exc.code} {truncate(body)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"刷新登录令牌失败：{exc}") from exc

    return apply_refreshed_tokens(auth_json, payload)


def apply_refreshed_tokens(auth_json, payload):
    """把刷新接口返回的新令牌合并回 auth.json。"""
    access_token = clean_string(payload.get("access_token"))
    id_token = clean_string(payload.get("id_token"))
    if not access_token or not id_token:
        raise RuntimeError("刷新登录令牌响应缺少 access_token 或 id_token")

    updated = dict(auth_json) if isinstance(auth_json, dict) else {}
    updated.setdefault("OPENAI_API_KEY", None)
    updated["auth_mode"] = updated.get("auth_mode") or "chatgpt"
    raw_tokens = updated.get("tokens")
    tokens: dict[str, object] = raw_tokens.copy() if isinstance(raw_tokens, dict) else {}
    tokens["access_token"] = access_token
    tokens["id_token"] = id_token
    if clean_string(payload.get("refresh_token")):
        tokens["refresh_token"] = clean_string(payload.get("refresh_token"))
    if not clean_string(tokens.get("account_id")):
        account_id = extract_account_id_from_id_token(id_token)
        if account_id:
            tokens["account_id"] = account_id
    updated["tokens"] = tokens
    updated["last_refresh"] = rfc3339_now()
    return updated


def extract_account_id_from_id_token(id_token):
    """从 id_token 里读取 ChatGPT 账号编号。"""
    claims = decode_jwt_payload(id_token)
    auth_claim = claims.get("https://api.openai.com/auth") if isinstance(claims, dict) else None
    if isinstance(auth_claim, dict):
        return clean_string(auth_claim.get("chatgpt_account_id"))
    return None


def extract_client_id_from_claims(claims):
    """从 id_token 的受众字段中提取刷新接口需要的客户端编号。"""
    aud = claims.get("aud") if isinstance(claims, dict) else None
    if isinstance(aud, str):
        return clean_string(aud)
    if isinstance(aud, list):
        for item in aud:
            value = clean_string(item)
            if value:
                return value
    return None


def decode_jwt_payload(token):
    """解析 JWT 第二段载荷，仅读取声明，不验证签名。"""
    if not token:
        return {}
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        claims = json.loads(decoded)
        return claims if isinstance(claims, dict) else {}
    except Exception:
        return {}


def jwt_expiration(token):
    """读取 JWT 过期时间戳。"""
    claims = decode_jwt_payload(token)
    exp = claims.get("exp") if isinstance(claims, dict) else None
    return int(exp) if isinstance(exp, (int, float)) else None


def parse_last_refresh(value):
    """兼容秒、毫秒和常见 UTC 时间文本。"""
    if isinstance(value, (int, float)):
        return normalize_timestamp(int(value))
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return normalize_timestamp(int(text))
    except ValueError:
        pass
    for pattern in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return int(calendar.timegm(time.strptime(text, pattern)))
        except ValueError:
            continue
    return None


def normalize_timestamp(value):
    """把毫秒时间戳归一为秒。"""
    return value // 1000 if abs(value) >= 1_000_000_000_000 else value


def keepalive_max_last_refresh_age_seconds(account_key):
    """给每个账号稳定增加保活抖动，避免同一时间集中刷新。"""
    hash_value = 0xCBF29CE484222325
    for byte in account_key.encode("utf-8", errors="ignore"):
        hash_value = (hash_value ^ byte) * 0x100000001B3
        hash_value &= 0xFFFFFFFFFFFFFFFF
    return KEEPALIVE_LAST_REFRESH_BASE_AGE_SECONDS + (
        hash_value % KEEPALIVE_LAST_REFRESH_JITTER_SECONDS
    )


def rfc3339_now():
    """生成 Codex auth.json 使用的 UTC 时间文本。"""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clean_string(value):
    """清理可选字符串字段。"""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def truncate(value, limit=140):
    """截断接口错误正文，避免过长内容进入界面。"""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."
