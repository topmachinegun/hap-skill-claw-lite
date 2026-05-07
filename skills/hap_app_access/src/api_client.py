"""HAP V3 REST API 客户端（仅限 Appkey+Sign 场景）。

endpoint: {api_base}/v3/open/<module>/<action>
auth: HTTP header `HAP-Appkey` + `HAP-Sign`

Personal OAuth 场景不走此路径——请用 mcp_client.py。

用法:
    from skills.hap_app_access.src.api_client import V3ApiClient

    client = V3ApiClient(
        appkey="<Appkey>",
        sign="<Sign>",
        api_base="https://api.mingdao.com",
    )
    data = client.get_record_list(worksheet_id="...", page_size=50)
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


# MCP 工具名 → V3 REST (path, payload_builder) 映射
def _editrow_payload(a: dict) -> dict:
    controls = []
    for f in a.get("fields") or a.get("controls") or []:
        controls.append({
            "controlId": f.get("controlId") or f.get("id"),
            "value": f.get("value"),
        })
    return {
        "worksheetId": a.get("worksheetId") or a.get("worksheet_id"),
        "rowId": a.get("rowId") or a.get("row_id"),
        "controls": controls,
    }


def _getfilterrows_payload(a: dict) -> dict:
    return {
        "worksheetId": a.get("worksheetId") or a.get("worksheet_id"),
        "filters": a.get("filters") or [],
        "pageSize": a.get("pageSize") or a.get("page_size") or 50,
        "pageIndex": a.get("pageIndex") or a.get("page_index") or 1,
    }


def _create_row_payload(a: dict) -> dict:
    controls = []
    for f in a.get("fields") or a.get("controls") or []:
        controls.append({
            "controlId": f.get("controlId") or f.get("id"),
            "value": f.get("value"),
        })
    return {
        "worksheetId": a.get("worksheetId") or a.get("worksheet_id"),
        "controls": controls,
    }


TOOL_TO_ENDPOINT: dict[str, tuple[str, Any]] = {
    "update_record": ("worksheet/editRow", _editrow_payload),
    "editRow": ("worksheet/editRow", _editrow_payload),
    "get_record_list": ("worksheet/getFilterRows", _getfilterrows_payload),
    "getFilterRows": ("worksheet/getFilterRows", _getfilterrows_payload),
    "create_record": ("worksheet/addRow", _create_row_payload),
    "addRow": ("worksheet/addRow", _create_row_payload),
}


class UnsupportedTool(RuntimeError):
    """V3 API 不支持该工具。"""


class V3ApiClient:
    """HAP V3 REST API 客户端。

    Args:
        appkey: 应用 AppKey
        sign: 应用 Sign
        api_base: API 基础 URL（默认 https://api.mingdao.com）
    """

    def __init__(self, appkey: str, sign: str, api_base: str = "https://api.mingdao.com"):
        self.base = api_base.rstrip("/")
        self.appkey = appkey
        self.sign = sign
        self.diagnostics: list[str] = []

    def _post(self, path: str, payload: dict) -> Any:
        url = f"{self.base}/v3/open/{path.lstrip('/')}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "HAP-Appkey": self.appkey,
                "HAP-Sign": self.sign,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            self.diagnostics.append(f"[{path}] HTTP {e.code}: {body[:300]}")
            raise
        try:
            obj = json.loads(raw)
        except ValueError:
            self.diagnostics.append(f"[{path}] non-JSON response: {raw[:200]}")
            return raw
        if isinstance(obj, dict):
            if obj.get("success") is False or obj.get("error_code") not in (None, 0):
                self.diagnostics.append(
                    f"[{path}] error_code={obj.get('error_code')} msg={obj.get('error_msg')}"
                )
            return obj.get("data", obj)
        return obj

    def list_tools(self) -> list[str]:
        """返回 V3 API 支持的工具名列表。"""
        return sorted(TOOL_TO_ENDPOINT.keys())

    def call(self, tool: str, args: dict) -> Any:
        """调 V3 API 工具。

        Raises:
            UnsupportedTool: 工具不在映射表中
        """
        entry = TOOL_TO_ENDPOINT.get(tool)
        if entry is None:
            raise UnsupportedTool(
                f"工具 '{tool}' 在 V3 API 下无端点映射。\n"
                f"  支持的工具：{', '.join(sorted(TOOL_TO_ENDPOINT))}\n"
                f"  若需调用其他工具，请改用 Personal MCP（mcp_client.py）"
            )
        path, builder = entry
        return self._post(path, builder(args))
