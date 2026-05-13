---
name: crm_visit_advisor
description: 基于「客户拜访技术」知识库，为 ClawCRM 项目生成结构化的客户拜访建议，涵盖访前准备、访中执行、访后跟进全流程。当用户说"准备拜访 X"、"拜访前要准备什么"、"帮我准备客户拜访"、"visit preparation"、"客户拜访建议"、"怎么去拜访"时触发。
---

# ClawCRM 客户拜访建议

基于项目上下文（阶段、客户信息、最近动态），检索「客户拜访技术」知识库，生成访前/访中/访后三阶段结构化建议。

> **本技能为 L3 业务技能**。独立 repo 分发，开发时在 hap-skill-claw-lite monorepo 中迭代。

## 1. 触发条件

触发短语（中文优先）：
- "准备拜访 X / X 项目怎么拜访 / 拜访前要准备什么"
- "帮我准备客户拜访 / 客户拜访建议 / 拜访指引"
- "visit preparation / prepare visit for X"

用户通常提供**项目名**，可选提供**拜访场景**（初次拜访 / 方案演示 / POC 验证 / 高层拜访）。

## 2. 前置条件

| 项目 | 默认值 | 缺失时如何获取 |
|---|---|---|
| 认证 | AppKey+Sign（ClawCRM 走 app_mcp 模式） | 从 `hap_app_access/apps.toml` 读取 |
| ClawCRM appId | `3028926b11966404` | 可由 `--app-id` 覆盖 |
| 项目管理 KB | `69ca75132970faa5ac6ce728` | 辅助检索销售阶段和 ICP |
| 客户拜访技术 KB | `6a047c8820ab7dc22d1131d6` | 主检索源 |
| 项目工作表 | `69ca1fb1d128aadb0c749d49`（项目管理） | 固定锚点 |
| 访问模式 | `app_mcp`（无需 Bearer token，无过期问题） | 脚本直接构造 URL |

### 三层架构中的位置

- **L1 Token Broker**：本项目不依赖（走 AppKey+Sign 直接鉴权）
- **L2 hap-app-access**：提供 `app_config.py`（读 apps.toml）、`mcp_client.py`（MCP 客户端）

## 3. 端到端流程

```
- [ ] S1 从 apps.toml 读取 ClawCRM 的 AppKey+Sign，构造 MCP URL
- [ ] S2 initialize + tools/list
- [ ] S3 获取项目上下文：基本信息 + 最近跟进日志
- [ ] S4 构造 3 路检索词，并行查询「客户拜访技术」KB
- [ ] S5 辅助检索「项目管理知识库」KB（阶段、ICP）
- [ ] S6 结合项目上下文 + KB 命中，生成拜访建议 JSON
- [ ] S7 Agent 按 §5 模板呈现建议
```

### 便捷方式

```bash
python3 skills/crm_visit_advisor/src/advise_visit.py \
  --project "XYZ有限公司"

# 可选场景
python3 skills/crm_visit_advisor/src/advise_visit.py \
  --project "XYZ有限公司" --scene "方案演示"
```

## 4. 拜访场景指导（智能体使用）

根据检索结果中的 KB 命中内容，智能体应判断当前所处的拜访阶段，并输出相应指导。

| 场景 | 识别关键词 | KB 重点关注 |
|---|---|---|
| **初次拜访** | 新线索、首次、刚注册、初访 | 明确拜访目标、搜集客户信息、八大件准备、开场话术 |
| **方案演示** | 演示、Demo、产品、方案 | 定制化方案准备、标杆案例、Q&A 预设、呈现要点 |
| **POC 验证** | POC、测试、验证、试用 | 选取案例场景、对齐期望、POC 汇报结构 |
| **高层拜访** | 老板、VP、决策、批复 | 锁定关键人、了解决策链、商务条款准备 |
| **复盘拜访** | 复盘、总结、回顾 | 故事线梳理、Q&A 整理、后续计划 |

## 5. 输出模板

```markdown
# 客户拜访建议：{{项目名}}

- 项目阶段：{{stage}}
- 客户信息：{{customer_snapshot}}
- 最近动态：{{recent_log_summary}}
- 知识依据：客户拜访技术 KB（`6a047c8820ab7dc22d1131d6`）

## 拜访前准备

| 准备项 | 内容 | KB 依据 |
|---|---|---|
| 拜访目标 | {{goal}} | chunk `{{chunkId}}` |
| 客户信息搜集 | {{info_gap}} | chunk `{{chunkId}}` |
| 关键人锁定 | {{key_persons}} | chunk `{{chunkId}}` |
| 定制化方案 | {{solution_prep}} | chunk `{{chunkId}}` |
| 预设异议 | {{expected_objections}} | chunk `{{chunkId}}` |
| 八大件检查 | 电脑 / 转接头 / U盘 / 翻页笔 / 名片 / 宣传册 / 笔记本 / 签字笔 | chunk `{{chunkId}}` |

## 拜访中执行

| 步骤 | 要点 | KB 依据 |
|---|---|---|
| 开场 | {{opening_hint}} | chunk `{{chunkId}}` |
| 探询 | {{inquiry_hint}} | chunk `{{chunkId}}` |
| 呈现 | {{presentation_hint}} | chunk `{{chunkId}}` |
| 总结 | {{closing_hint}} | chunk `{{chunkId}}` |

## 拜访后行动

| 行动 | 说明 | KB 依据 |
|---|---|---|
| CRM 日清 | {{crm_note}} | chunk `{{chunkId}}` |
| 复盘会议 | {{review_plan}} | chunk `{{chunkId}}` |
| 后续反馈 | {{follow_up}} | chunk `{{chunkId}}` |

---
*生成时间：{{ts}}  |  主要知识库：「客户拜访技术」*
```

## 6. 知识库检索策略

1. 从日志提取关键动词和场景词
2. 构造 3 路检索（全部针对客户拜访技术 KB）：
   - `query_prep`：拜访前 准备 目标 信息搜集 异议
   - `query_exec`：拜访中 开场 探询 呈现 总结
   - `query_follow`：拜访后 复盘 CRM 反馈
3. 辅助检索项目管理 KB：`query_stage`（销售阶段 + ICP）
4. 按 chunkId 去重，按 score 保留前 8 条

## 7. 输出 JSON 结构

```json
{
  "project": { "rowId": "...", "title": "...", "stage": "...", "logs": [...] },
  "visitHits": [{ "chunkId": "...", "content": "...", "score": 0.9, "query": "..." }],
  "projectHits": [{ "chunkId": "...", "content": "...", "score": 0.8, "query": "..." }],
  "scene": "初次拜访",
  "diagnostics": [...]
}
```

Agent 基于此 JSON 按 §5 模板生成报告。

---
**技能版本**：v1.0.0
