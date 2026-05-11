---
name: hap-skill-creator
description: L3 HAP 业务技能脚手架工具。当用户说"创建新的 HAP 业务技能"、"新建 L3 skill"、"生成 HAP 技能骨架"、"创建一个新技能"等时触发。引导用户填写技能元信息，自动生成标准目录结构和 SKILL.md 骨架，遵循 L3 开发规范。
version: 1.0.0
---

# HAP L3 业务技能脚手架

帮助 AI 快速生成符合 [L3 开发规范](../../docs/l3-development.md) 的 HAP 业务技能骨架。

## 1. 触发条件

- "创建新的 HAP 业务技能"
- "新建 L3 skill"
- "生成 HAP 技能骨架"
- "帮我创建一个技能 / 帮我搭一个技能框架"
- "我要开发一个 HAP 技能"

## 2. 信息收集

按以下顺序向用户收集信息，每轮 1-2 个问题，不要一次性全部抛出：

### 2.1 技能标识

| 字段 | 说明 | 示例 |
|------|------|------|
| 技能名 | 英文 snake_case，建议 `hap_skill_<name>` 格式 | `crm_project_review` |
| 分发 repo 名 | GitHub repo 名，建议 `<descriptive-name>` 格式（不必加 hap-skill 前缀） | `crm-project-review`、`crm_leads_sync` |
| 一句话描述 | 含触发场景关键词 | "基于明道云知识库对 CRM 项目做结构化评审" |

### 2.2 HAP 应用信息

| 字段 | 说明 | 默认值/如何获取 |
|------|------|---------------|
| 目标 appId | HAP 应用 ID（UUID） | 浏览器 URL 或 `get_org_list → get_app_list` |
| 授权类型 | Appkey+Sign 或 OAuth Bearer | 按 L2 决策流程判断 |
| Token profile | 仅 OAuth 模式需要，Broker 中的 profile 名 | 如 `claw-crm` |

### 2.3 业务配置

| 字段 | 说明 | 如何获取 |
|------|------|---------|
| 知识库 ID | 若有知识库检索需求 | `get_app_knowledge_list(appId)` |
| 工作表 ID | 主要操作的工作表 | `get_app_worksheets_list(appId)` |
| 关键字段 | 需要读写的字段名和控制 ID | `get_worksheet_structure(worksheet_id, appId)` |

### 2.4 脚本需求

- 是否需要 Python 辅助脚本？（是/否）
- 脚本参数有哪些？（如 `--project`、`--row-id`）

## 3. 生成骨架

收集完信息后，按以下结构生成文件：

### 3.1 目录结构

```
skills/<skill-name>/
├── SKILL.md
└── src/
    └── <script>.py          # 仅当用户需要脚本时
```

### 3.2 SKILL.md 模板

```markdown
---
name: <skill-name>
description: <一句话描述，含触发场景关键词>
version: 1.0.0
---

# <技能标题>

<一句话介绍技能用途>

## 1. 触发条件

触发短语（中文优先）：
- "<触发短语 1>"
- "<触发短语 2>"

## 2. 前置条件

| 项目 | 默认值 | 缺失时如何获取 |
|---|---|---|
| Token | 由外部进程管理。通过 `token_reader.get_mcp_url("<profile>")` 读取。 | token 文件不存在时联系管理员刷新 |
| appId | `<appId>` | 固定默认值 |
| 知识库 ID | `<knowledgeId>` | 调用 `get_app_knowledge_list(appId)` |
| 工作表 ID | `<worksheetId>` | 固定锚点 |

### 三层架构中的位置

本 skill 位于 L3（业务技能层），依赖关系：
- **L1 外部服务**：提供 Token（不在本仓库）
- **L2 hap-app-access**：提供访问方法论 + 共享 Python 模块
  - `token_reader.py`：读取 token 文件
  - `mcp_client.py`：MCP JSON-RPC 客户端

## 3. 铁律

继承 [hap-app-access §4.1](../hap_app_access/SKILL.md)：

- **每次会话先调 `tools/list`**，严格遵循 `inputSchema`
- 所有 record 相关工具必须传 `ai_description`
- 错误码 `10001` 几乎总是参数名错误或缺少 `ai_description`

### 3.1 数据源纪律

<在此定义本技能的数据源限制和硬停止条件>

## 4. 端到端流程

```
- [ ] S1 通过 token_reader.get_mcp_url("<profile>") 读取 MCP URL
- [ ] S2 initialize + tools/list
- [ ] S3 <步骤 3>
- [ ] S4 <步骤 4>
```

### 4.1 硬停止分支

| exit | error 字段 | 触发条件 | Agent 应答模板 |
|---|---|---|---|
| 2 | Token 不可用 | Token 文件不存在或已过期 | "Token 不可用，请检查 token 文件或联系管理员刷新" |
| 3 | <自定义> | <条件> | <应答> |

**禁止的降级路径**：
- <列出本技能不允许的降级行为>

## 5. <业务逻辑章节>

<在此定义核心业务逻辑：评分标准、处理规则、输出格式等>

## 6. 常见陷阱

| 现象 | 根因 | 解法 |
|---|---|---|
| | | |

## 7. Related

- L2 `skills/hap_app_access/` — HAP 通用访问方法论 + 共享模块
- L3 开发规范 `docs/l3-development.md`

---

**技能版本**：v1.0.0
**适用范围**：明道云 HAP（SaaS）

**v1.0.0 变更**：
- 初始版本
```

### 3.3 Python 脚本模板（可选）

```python
#!/usr/bin/env python3
"""<技能名> CLI 入口。"""

import argparse
import json
import sys

from skills.hap_app_access.src.token_reader import get_mcp_url
from skills.hap_app_access.src.mcp_client import MCPClient


async def main():
    parser = argparse.ArgumentParser(description="<描述>")
    parser.add_argument("--profile", default="<默认 profile>")
    # TODO: 添加业务参数
    args = parser.parse_args()

    # 1. 读取 token
    try:
        url = get_mcp_url(args.profile)
    except Exception as e:
        print(json.dumps({"error": f"Token 不可用: {e}"}))
        sys.exit(2)

    # 2. 初始化 MCP 客户端
    client = MCPClient(url)
    await client.initialize()

    # 3. TODO: 业务逻辑
    result = await client.call_tool("<tool_name>", {
        "appId": "<appId>",
        "ai_description": "<用途描述>",
        # ...
    })

    print(json.dumps({"data": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## 4. 创建独立分发 repo

生成骨架后，引导用户创建独立 GitHub repo：

```bash
# 1. 复制技能目录
mkdir ~/hap-skill-<name>
cp skills/<skill-name>/SKILL.md ~/hap-skill-<name>/
cp -r skills/<skill-name>/src/ ~/hap-skill-<name>/

# 2. 初始化并推送
cd ~/hap-skill-<name>
git init
git add -A
git commit -m "feat: initial release v1.0.0"
git tag v1.0.0
git remote add origin https://github.com/topmachinegun/<repo-name>.git
git push -u origin main --tags
```

告知用户：平台（OpenClaw 等）通过 `https://github.com/topmachinegun/<repo-name>` 引用此技能。

## 5. 注意事项

- 生成的 SKILL.md 中 `<...>` 占位符必须全部替换为实际值
- 如果用户无法立即提供 appId/worksheetId，标注为「待补充」并给出获取方法
- 硬停止分支是 L3 技能的**强制要求**，不可省略
- 提醒用户阅读 [docs/l3-development.md](../../docs/l3-development.md) 了解完整规范

---

**技能版本**：v1.0.0
**适用范围**：hap-skill-claw-lite monorepo 内使用

**v1.0.0 变更**：
- 初始版本：L3 业务技能脚手架生成
