#!/usr/bin/env python3
"""advise_visit.py — ClawCRM 客户拜访建议数据采集管道。

用法:
    python3 advise_visit.py --project "XYZ客户" [--scene "方案演示"]
    python3 advise_visit.py --row-id <ROW_ID>

输出: stdout 一个 JSON bundle，结构:
    {
      "project": {
        "rowId": "...", "title": "...",
        "fields": { ...normalized record... },
        "followUpLogs": [ {text, time, source} ... ]
      },
      "visitHits": [ {chunkId, content, score, query, knowledgeName} ... ],
      "projectHits": [ {chunkId, content, score, query, knowledgeName} ... ],
      "scene": "方案演示",
      "diagnostics": [...]
    }

Agent 拿到 JSON 后，按 SKILL.md §5 模板生成拜访建议报告，\
然后调用 --writeback-file 写回「拜访准备」字段。
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Any

# L2 共享模块路径注入
_SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent  # skills/
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))

from hap_app_access.src.mcp_client import MCPClient  # noqa: E402
from hap_app_access.src.app_config import get_app_auth  # noqa: E402


def diag(msg: str) -> None:
    print(f"[diag] {msg}", file=sys.stderr, flush=True)


def ai_desc(s: str) -> str:
    return s[:180]


def _row_title(r: dict) -> str:
    return str(r.get("title") or r.get("name") or "")


# ── 常量 ──────────────────────────────────────────────
CLAWCRM_APP_ID = "3028926b11966404"
KB_VISIT = "6a047c8820ab7dc22d1131d6"   # 客户拜访技术
KB_PROJECT = "69ca75132970faa5ac6ce728"  # 项目管理知识库
PROJECT_WS_ID = "69ca1fb1d128aadb0c749d49"
WRITEBACK_FIELD_ID = "6a048e4e104f63109c08aa67"  # 拜访准备 (Text/富文本)


def build_app_mcp_url(app_id: str) -> str | None:
    """从 apps.toml 读取 ClawCRM 的 AppKey+Sign，构造 App MCP URL。"""
    cfg = get_app_auth(app_id)
    if not cfg or not cfg.is_appkey:
        diag(f"apps.toml 中未找到 {app_id} 的 AppKey+Sign 配置")
        return None
    return f"https://api.mingdao.com/mcp?HAP-Appkey={cfg.appkey}&HAP-Sign={cfg.sign}"


def build_queries(record: dict, logs: list[dict], scene: str | None) -> dict[str, str]:
    """基于日志和场景构造检索词。"""
    log_blob = " ".join((l.get("text") or "") for l in logs)[-1500:]
    customer = str(record.get("title") or record.get("name") or "")

    # 拜访前：准备关键词
    prep_words = []
    for kw in ("准备", "方案", "案例", "异议", "目标", "信息", "关键人", "八大件"):
        if kw in log_blob:
            prep_words.append(kw)
    if scene:
        prep_words.insert(0, scene)
    query_prep = "拜访前准备 " + " ".join(prep_words) if prep_words else "拜访前 准备 目标 信息搜集"

    # 拜访中：执行关键词
    exec_words = []
    for kw in ("开场", "探询", "呈现", "演示", "方案", "POC", "总结"):
        if kw in log_blob:
            exec_words.append(kw)
    query_exec = "拜访中执行 " + " ".join(exec_words) if exec_words else "拜访中 开场 探询 呈现"

    # 拜访后
    follow_words = []
    for kw in ("复盘", "CRM", "反馈", "邮件", "日清", "跟进"):
        if kw in log_blob:
            follow_words.append(kw)
    query_follow = "拜访后行动 " + " ".join(follow_words) if follow_words else "拜访后 复盘 CRM 反馈"

    # 项目管理 KB 辅助检索
    stage_words = []
    for kw in ("演示", "POC", "报价", "签约", "交付", "选型"):
        if kw in log_blob:
            stage_words.append(kw)
    query_stage = "销售阶段 " + " ".join(stage_words) if stage_words else "销售阶段 ICP"

    return {
        "query_prep": query_prep,
        "query_exec": query_exec,
        "query_follow": query_follow,
        "query_stage": query_stage,
    }


def search_kb(cli: MCPClient, kb_ids: list[str], query: str, app_id: str, topk: int = 6) -> list[dict]:
    """单次 knowledge_search，返回 chunks 列表。"""
    r = cli.call("knowledge_search", {
        "appId": app_id,
        "knowledgeIds": kb_ids,
        "query": query,
        "searchMode": "hybrid",
        "topK": topk,
        "ai_description": ai_desc(f"Search KB for visit advice: {query[:80]}"),
    })
    chunks: list[dict] = []
    if isinstance(r, dict):
        chunks = r.get("chunks") or []
    elif isinstance(r, list):
        for it in r:
            if isinstance(it, dict):
                chunks += it.get("chunks") or []
    return chunks


def extract_logs(record: dict, cli: MCPClient, app_id: str, ws_id: str, all_ws: list[dict]) -> list[dict]:
    """从项目记录中提取跟进日志（主表内嵌 + 独立工作表）。"""
    # 形态 A：主表内嵌「日志」字段
    logs: list[dict] = []
    for k, v in record.items():
        if "日志" in str(k):
            if isinstance(v, str) and v.strip():
                logs.append({"text": v[:2000], "time": None, "source": f"主表.{k}"})
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        txt = item.get("name") or item.get("text") or ""
                        logs.append({"text": str(txt)[:2000], "time": item.get("createTime"), "source": f"主表.{k}"})

    # 形态 B：独立工作表「项目日志」
    row_id = record.get("rowId") or record.get("rowid") or record.get("_id")
    if not logs and row_id:
        log_ws = next((w for w in all_ws if "项目日志" in w.get("worksheetName", "")), None)
        if log_ws:
            lwid = log_ws.get("worksheetId")
            r = cli.call("get_record_list", {
                "worksheet_id": lwid,
                "pageSize": 50,
                "pageIndex": 1,
                "appId": app_id,
                "ai_description": ai_desc("Fetch project logs for visit advice"),
            })
            rows: list[dict] = []
            if isinstance(r, dict):
                rows = r.get("rows") or r.get("data") or []
            elif isinstance(r, list):
                rows = [x for x in r if isinstance(x, dict)]
            for row in rows:
                proj = row.get("project")
                if isinstance(proj, list):
                    for p in proj:
                        if isinstance(p, dict) and p.get("sid") == row_id:
                            content = str(row.get("content") or row.get("log_title") or "")
                            logs.append({
                                "text": content[:2000],
                                "time": row.get("_createdAt") or row.get("createTime"),
                                "source": f"项目日志.{row.get('rowId','?')}",
                            })
                            break
    return logs


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--project", help="项目名")
    p.add_argument("--row-id", help="项目 rowId（优先）")
    p.add_argument("--scene", help="拜访场景：初次拜访/方案演示/POC验证/高层拜访/复盘拜访")
    p.add_argument("--app-id", default=CLAWCRM_APP_ID)
    p.add_argument("--topk", type=int, default=6)
    p.add_argument("--writeback-file",
                   help="写回模式：读取该文件的 Markdown 内容写回「拜访准备」字段。必须配合 --row-id。")
    p.add_argument("--writeback-field-id", default=WRITEBACK_FIELD_ID,
                   help="拜访准备字段的 controlId")
    args = p.parse_args()

    # ========== 写回模式 ==========
    if args.writeback_file:
        if not args.row_id:
            print("ERROR: 写回模式必须同时提供 --row-id", file=sys.stderr)
            return 2
        try:
            with open(args.writeback_file, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            print(f"ERROR: 读取 writeback-file 失败: {e}", file=sys.stderr)
            return 2
        if not content.strip():
            print("ERROR: writeback-file 内容为空，拒绝写回", file=sys.stderr)
            return 2

        mcp_url = build_app_mcp_url(args.app_id)
        if not mcp_url:
            return 2
        cli = MCPClient(mcp_url, mode="app_mcp", app_id=args.app_id)
        cli.ensure_initialized()

        # 核对字段存在
        struct = cli.call("get_worksheet_structure", {
            "worksheet_id": PROJECT_WS_ID,
            "appId": args.app_id,
            "responseFormat": "json",
            "ai_description": ai_desc("Verify visit preparation field before writeback"),
        })
        fields = struct.get("fields", []) if isinstance(struct, dict) else []
        match = None
        for f in fields:
            fid = f.get("id") or f.get("controlId")
            if fid == args.writeback_field_id:
                match = f
                break
        if not match:
            print(json.dumps({
                "ok": False,
                "reason": "「拜访准备」字段未在工作表结构中命中",
                "tried_field_id": args.writeback_field_id,
            }, ensure_ascii=False, indent=2))
            return 1

        resolved_id = match.get("id") or match.get("controlId") or args.writeback_field_id

        upd = cli.call("update_record", {
            "worksheet_id": PROJECT_WS_ID,
            "row_id": args.row_id,
            "appId": args.app_id,
            "fields": [{"id": resolved_id, "value": content}],
            "ai_description": ai_desc(
                f"Write visit advice report into 拜访准备 field for record {args.row_id}"),
        })

        ok = (isinstance(upd, str) and upd == args.row_id) or \
             (isinstance(upd, dict) and upd.get("success") is not False)
        print(json.dumps({
            "ok": ok,
            "worksheetId": PROJECT_WS_ID,
            "rowId": args.row_id,
            "fieldId": resolved_id,
            "fieldName": match.get("name"),
            "charsWritten": len(content),
        }, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    # ========== 写回模式结束 ==========

    if not (args.project or args.row_id):
        print("ERROR: 必须提供 --project 或 --row-id", file=sys.stderr)
        return 2

    # S1: 构造 App MCP URL
    mcp_url = build_app_mcp_url(args.app_id)
    if not mcp_url:
        return 2
    diag(f"S1 mcp_url via apps.toml for appId={args.app_id}")

    cli = MCPClient(mcp_url, mode="app_mcp", app_id=args.app_id)
    cli.ensure_initialized()
    tl = cli.list_tool_names()
    diag(f"S2 tools: {', '.join(tl[:10])}...")

    # S3: 获取项目上下文
    ws_list = cli.call("get_app_worksheets_list", {"appId": args.app_id})

    def _walk_ws(o):
        if isinstance(o, dict):
            nm = o.get("worksheetName") or o.get("name") or ""
            wid = o.get("worksheetId") or o.get("id")
            if wid and nm:
                yield {"worksheetId": wid, "worksheetName": nm}
            for v in o.values():
                yield from _walk_ws(v)
        elif isinstance(o, list):
            for v in o:
                yield from _walk_ws(v)

    all_ws = list(_walk_ws(ws_list))
    proj_ws = next((w for w in all_ws if w["worksheetId"] == PROJECT_WS_ID), None)
    if not proj_ws:
        proj_ws = next((w for w in all_ws if "项目" in w["worksheetName"] and "日志" not in w["worksheetName"]), None)
    if not proj_ws:
        print(json.dumps({"error": "WORKSPACE_NOT_FOUND", "message": "未找到项目管理工作表"}, ensure_ascii=False))
        return 3

    ws_id = proj_ws["worksheetId"]

    # 定位项目记录
    record: dict = {}
    record_title = ""
    row_id = args.row_id

    if row_id:
        detail = cli.call("get_record_details", {
            "worksheet_id": ws_id, "row_id": row_id, "appId": args.app_id,
            "ai_description": ai_desc("Fetch project record for visit advice"),
        })
        if isinstance(detail, dict):
            record = detail
            record_title = str(detail.get("title") or detail.get("name") or "")
    else:
        r = cli.call("get_record_list", {
            "worksheet_id": ws_id, "pageSize": 20, "pageIndex": 1,
            "search": args.project, "appId": args.app_id,
            "ai_description": ai_desc(f"Search project '{args.project}' for visit advice"),
        })
        rows: list[dict] = []
        if isinstance(r, dict):
            rows = r.get("rows") or r.get("data") or []
        elif isinstance(r, list):
            rows = [x for x in r if isinstance(x, dict)]

        if not rows:
            print(json.dumps({
                "error": "PROJECT_NOT_FOUND",
                "message": f"项目「{args.project}」在项目管理表中未找到",
            }, ensure_ascii=False, indent=2))
            return 3

        # 精确匹配
        best = next((x for x in rows if _row_title(x) == args.project), None)
        if not best:
            best = next((x for x in rows if args.project in _row_title(x) or _row_title(x) in args.project), None)
        if not best:
            best = rows[0]

        record = best
        row_id = best.get("rowId") or best.get("rowid") or best.get("id")
        record_title = _row_title(best)

        # 拉完整详情
        if row_id:
            detail = cli.call("get_record_details", {
                "worksheet_id": ws_id, "row_id": row_id, "appId": args.app_id,
                "ai_description": ai_desc("Fetch full project record for visit advice"),
            })
            if isinstance(detail, dict):
                record = {**record, **detail}

    diag(f"S3 project: rowId={row_id} title={record_title!r}")

    # 提取日志
    logs = extract_logs(record, cli, args.app_id, ws_id, all_ws)
    diag(f"S3 logs: {len(logs)} entries")

    # S4+S5: 检索知识库
    queries = build_queries(record, logs, args.scene)
    diag(f"S4 queries: {json.dumps(queries, ensure_ascii=False)}")

    # 客户拜访技术 KB (主检索)
    visit_hits: list[dict] = []
    seen_chunks: set[str] = set()
    for qname in ("query_prep", "query_exec", "query_follow"):
        chunks = search_kb(cli, [KB_VISIT], queries[qname], args.app_id, args.topk)
        for h in chunks:
            cid = h.get("chunkId")
            if cid and cid not in seen_chunks:
                seen_chunks.add(cid)
                h["_query"] = qname
                visit_hits.append(h)
    visit_hits.sort(key=lambda x: x.get("score", 0), reverse=True)
    visit_hits = visit_hits[: args.topk * 2]
    diag(f"S4 visitHits: {len(visit_hits)} chunks")

    # 项目管理 KB (辅助)
    project_hits: list[dict] = []
    p_seen: set[str] = set()
    chunks = search_kb(cli, [KB_PROJECT], queries["query_stage"], args.app_id, args.topk)
    for h in chunks:
        cid = h.get("chunkId")
        if cid and cid not in p_seen:
            p_seen.add(cid)
            h["_query"] = "query_stage"
            project_hits.append(h)
    project_hits.sort(key=lambda x: x.get("score", 0), reverse=True)
    project_hits = project_hits[: args.topk]
    diag(f"S5 projectHits: {len(project_hits)} chunks")

    # S6: 输出
    clean_diags = [d for d in cli.diagnostics if "error_code=1" not in d]
    bundle = {
        "project": {
            "rowId": row_id,
            "title": record_title,
            "fields": record,
            "followUpLogs": logs,
        },
        "visitHits": visit_hits,
        "projectHits": project_hits,
        "scene": args.scene,
        "diagnostics": clean_diags,
    }
    print(json.dumps(bundle, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
