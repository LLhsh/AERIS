import re


LEGACY_API_PATHS = {"/generate/api/chat", "/gemerate/api/chat"}


def normalize_api_path(api_path, default_path="/v1/chat/completion"):
    """规范化 API 路径，保证以 / 开头。"""
    path = (api_path or default_path).strip()
    if not path:
        path = default_path
    if not path.startswith("/"):
        path = "/" + path
    return path


def build_api_url(proxy_host, proxy_port, api_path, scheme="http"):
    """基于主机、端口和路径拼接完整 URL。"""
    host = (proxy_host or "127.0.0.1").strip()
    port = str(proxy_port or "7870").strip()
    path = normalize_api_path(api_path)
    return f"{scheme}://{host}:{port}{path}"


def normalize_connection_defaults(proxy_host, proxy_port, api_path):
    """兼容旧版本默认配置，必要时迁移到 v1/chat/completion。"""
    host = (proxy_host or "").strip()
    port = str(proxy_port or "").strip()
    path = normalize_api_path(api_path)

    migrated = False
    if path in LEGACY_API_PATHS:
        path = "/v1/chat/completion"
        migrated = True

    if not host:
        host = "127.0.0.1"
        migrated = True

    if not port:
        port = "7870"
        migrated = True

    # 若仍是历史默认联调地址，自动切换到当前内网默认地址
    if host in {"127.0.0.1", "localhost"} and port in {"9090", "80"}:
        host = "127.0.0.1"
        port = "7870"
        migrated = True

    return host, port, path, migrated


def normalize_model_name(model_name):
    """兼容误粘贴的模型串，仅提取第一个合法模型名。"""
    value = (model_name or "").strip()
    if not value:
        return "deepseek-r1:70b"

    # 支持多模型误粘贴场景，例如: a\tb\nc 或 a|b;c
    tokens = re.split(r"[\t\r\n,;|\\]+", value)
    for token in tokens:
        item = token.strip()
        if item:
            return item

    return "deepseek-r1:70b"


def mask_secret(secret):
    """对敏感信息做掩码，仅保留前后少量字符。"""
    value = (secret or "").strip()
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def build_authorization_value(api_key, auth_mode="auto"):
    """构造 Authorization 头值。

    返回 (header_value, effective_mode)。
    header_value 为 None 表示不发送 Authorization。
    """
    key = (api_key or "").strip()
    mode = (auth_mode or "auto").strip().lower()

    if mode in ("none", "off") or not key:
        return None, "none"

    bearer_prefix = re.compile(r"^bearer\s+", re.IGNORECASE)

    if mode == "raw":
        return key, "raw"

    if mode == "bearer":
        token = bearer_prefix.sub("", key).strip()
        return f"Bearer {token}", "bearer"

    # auto: 已含 Bearer 前缀则直接使用；否则默认补 Bearer
    if bearer_prefix.match(key):
        return key, "auto(bearer-as-is)"

    # 如用户输入了其它完整认证方案（如 "Token xxx"），则按原值透传
    first_space = key.find(" ")
    if first_space > 0 and key[:first_space].isalpha():
        return key, "auto(raw-scheme)"

    return f"Bearer {key}", "auto(bearer-added)"
