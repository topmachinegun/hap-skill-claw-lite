"""读取应用认证配置 (~/.config/hap-skill-claw-lite/apps.toml)

决策逻辑（§7）：
  apps.toml 有 appkey → Appkey+Sign（优先，权限更大）
  apps.toml 无 appkey → OAuth MCP（走 Broker）
  apps.toml 无记录  → 看 Broker 是否运行
"""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

if sys.version_info < (3, 11):
    import tomli as tomllib  # type: ignore

CONFIG_PATH = Path.home() / ".config" / "hap-skill-claw-lite" / "apps.toml"


@dataclass
class AppAuthConfig:
    """单个应用的认证配置。"""
    app_id: str
    name: str
    auth_type: str          # "appkey" | "oauth"
    appkey: Optional[str] = None
    sign: Optional[str] = None

    @property
    def is_appkey(self) -> bool:
        return self.auth_type == "appkey"


def load_apps_config() -> dict[str, AppAuthConfig]:
    """加载 apps.toml，返回 {appId: AppAuthConfig}。文件不存在返回空 dict。"""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)
    result: dict[str, AppAuthConfig] = {}
    for app_id, cfg in raw.get("apps", {}).items():
        has_appkey = bool(cfg.get("appkey"))
        result[app_id] = AppAuthConfig(
            app_id=app_id,
            name=cfg.get("name", ""),
            auth_type="appkey" if has_appkey else "oauth",
            appkey=cfg.get("appkey"),
            sign=cfg.get("sign"),
        )
    return result


def get_app_auth(app_id: str) -> Optional[AppAuthConfig]:
    """查单个应用的认证配置，无记录返回 None。"""
    return load_apps_config().get(app_id)


def list_app_ids() -> list[str]:
    """列出所有已配置的 appId。"""
    return list(load_apps_config().keys())
