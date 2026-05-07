"""Token Broker 文件读取器。

从 Token Broker 中控服务（L1）生成的 token JSON 文件中读取 MCP URL。
不依赖 hap-config.local.json、不调 md-generate-mcp-config、不尝试自己刷新。

用法:
    from skills.hap_app_access.src.token_reader import read_broker_token, get_mcp_url

    record = read_broker_token("claw-crm")
    url = get_mcp_url("claw-crm")
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


TOKEN_DIR = Path.home() / ".local" / "share" / "hap-token-broker" / "tokens"


class TokenNotFoundError(RuntimeError):
    """Broker token 文件不存在或 daemon 未运行。"""


@dataclass
class TokenRecord:
    """从 Broker token JSON 文件解析出的记录。"""
    profile: str
    url: str
    fetched_at: datetime
    expires_at: datetime
    account_redacted: str
    oauth_app_id: str
    last_refresh_duration_ms: int | None = None

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return now >= self.expires_at

    def seconds_until_expiry(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        return (self.expires_at - now).total_seconds()


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def token_path(profile: str) -> Path:
    return TOKEN_DIR / f"{profile}.json"


def read_broker_token(profile: str) -> TokenRecord:
    """读取指定 profile 的 Broker token 记录。

    Raises:
        TokenNotFoundError: token 文件不存在（Broker 未运行或未初始化）
    """
    p = token_path(profile)
    if not p.exists():
        raise TokenNotFoundError(
            f"Broker token 文件不存在: {p}\n"
            f"  请确认 hap-token-broker 已安装并运行:\n"
            f"    sudo systemctl status hap-token-broker\n"
            f"  或手动触发刷新:\n"
            f"    hap-token refresh {profile}"
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise TokenNotFoundError(f"Broker token 文件损坏 ({p}): {e}") from e

    try:
        return TokenRecord(
            profile=data["profile"],
            url=data["url"],
            fetched_at=_parse_iso(data["fetched_at"]),
            expires_at=_parse_iso(data["expires_at"]),
            account_redacted=data.get("account_redacted", ""),
            oauth_app_id=data.get("oauth_app_id", ""),
            last_refresh_duration_ms=data.get("last_refresh_duration_ms"),
        )
    except KeyError as e:
        raise TokenNotFoundError(f"Broker token 文件缺少字段 {e} ({p})") from e


def get_mcp_url(profile: str, check_expiry: bool = False) -> str:
    """快捷方法：读取指定 profile 的 MCP URL。

    Args:
        profile: Broker profile 名称（如 "claw-crm"）
        check_expiry: 若为 True，过期时抛出 TokenNotFoundError

    Raises:
        TokenNotFoundError: token 不存在或（check_expiry=True 时）已过期
    """
    rec = read_broker_token(profile)
    if check_expiry and rec.is_expired():
        raise TokenNotFoundError(
            f"Broker token 已过期: profile={profile}, expires_at={rec.expires_at.isoformat()}\n"
            f"  请手动触发刷新: hap-token refresh {profile}"
        )
    return rec.url
