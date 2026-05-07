"""MCP JSON-RPC 客户端：Personal OAuth / App MCP 共用。

两种模式的差异收敛在 URL 构造与参数注入：
  - Personal MCP: URL 含 Authorization=Bearer <token>；业务工具调用注入 appId + ai_description
  - App MCP:      URL 含 HAP-Appkey + HAP-Sign；无需额外注入

Token 管理完全委托给 L1 Token Broker，本模块通过 token_reader 直读 Broker token 文件。

用法:
    # Personal MCP（从 Broker 读 token）
    from skills.hap_app_access.src.token_reader import get_mcp_url
    from skills.hap_app_access.src.mcp_client import MCPClient

    url = get_mcp_url("claw-crm")
    client = MCPClient(url, mode="personal_mcp", app_id="...", ai_description="...")

    # App MCP（从 Appkey+Sign 拼 URL）
    client = MCPClient("https://api.mingdao.com/mcp?HAP-Appkey=...&HAP-Sign=...", mode="app_mcp")
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
import uuid
from typing import Any


class MCPClientError(RuntimeError):
    """MCP 调用失败。"""


class MCPClient:
    """MCP JSON-RPC 客户端。

    Args:
        url: 完整 MCP URL（包含鉴权参数）
        mode: "personal_mcp" 或 "app_mcp"
        app_id: Personal MCP 场景下注入的 appId（可选，可在 call() 时覆盖）
        ai_description: Personal MCP 场景下注入的 ai_description（可选，可在 call() 时覆盖）
    """

    def __init__(
        self,
        url: str,
        mode: str = "personal_mcp",
        app_id: str | None = None,
        ai_description: str | None = None,
    ):
        if mode not in ("personal_mcp", "app_mcp"):
            raise ValueError(f"mode 必须是 personal_mcp 或 app_mcp，收到: {mode}")
        self.url = url
        self.mode = mode
        self.app_id = app_id
        self.ai_description = ai_description
        self.diagnostics: list[str] = []
        self._initialized = False

    def rpc(self, method: str, params: dict | None = None) -> dict:
        """发 JSON-RPC 请求，自动处理 SSE 响应。"""
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method}
        if params is not None:
            body["params"] = params
        req = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")

        # SSE 兼容
        if raw.startswith("event:") or "data:" in raw[:40]:
            for line in raw.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
        return json.loads(raw)

    def ensure_initialized(self) -> None:
        """初始化 MCP session（幂等）。"""
        if self._initialized:
            return
        self.rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "hap-app-access", "version": "3.0.0"},
        })
        try:
            self.rpc("notifications/initialized")
        except Exception:
            pass
        self._initialized = True

    def list_tools(self) -> list[dict]:
        """返回完整工具列表（含 name + inputSchema），用于 schema 校验。"""
        self.ensure_initialized()
        resp = self.rpc("tools/list")
        return resp.get("result", {}).get("tools", []) or []

    def list_tool_names(self) -> list[str]:
        """返回工具名列表（便捷方法）。"""
        return [t.get("name", "") for t in self.list_tools() if t.get("name")]

    def call(self, tool: str, args: dict) -> Any:
        """调业务工具，自动注入 mode 所需的鉴权上下文。

        Personal MCP：自动注入 appId + ai_description（若构造时提供且 args 未覆盖）
        App MCP：不注入额外参数
        """
        self.ensure_initialized()
        merged = dict(args)
        if self.mode == "personal_mcp":
            if self.app_id:
                merged.setdefault("appId", self.app_id)
            if self.ai_description:
                merged.setdefault("ai_description", self.ai_description)

        resp = self.rpc("tools/call", {"name": tool, "arguments": merged})
        content = resp.get("result", {}).get("content", [])
        parsed: list[Any] = []
        for c in content:
            if c.get("type") == "text":
                t = c.get("text", "")
                try:
                    parsed.append(json.loads(t))
                except Exception:
                    parsed.append(t)
            else:
                parsed.append(c)

        # 明道云每条返回包一层 data/error_code
        for item in parsed:
            if isinstance(item, dict):
                ec = item.get("error_code")
                if item.get("success") is False or (ec is not None and ec != 0):
                    self.diagnostics.append(
                        f"[{tool}] error_code={ec} msg={item.get('error_msg') or item.get('error')}"
                    )
                if "data" in item:
                    return item["data"]
        return parsed
