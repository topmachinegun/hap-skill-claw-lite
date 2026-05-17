# L3 业务技能开发规范

L3 是 HAP 技能体系的业务层。每个 L3 技能解决一个具体业务问题（如项目评审、客户分析等），通过 L2 `hap_app_access` 提供的共享模块访问 HAP 数据。

## 1. 标准目录结构

每个 L3 技能必须遵循以下结构：

```
hap-skill-<name>/
├── SKILL.md              # 技能定义文件（必需）
├── src/                  # Python 源码（可选，有脚本时必需）
│   └── <script>.py
└── README.md             # 独立 repo 的说明文件（分发用）
```

## 2. SKILL.md 规范

### 2.1 Frontmatter（必需）

```yaml
---
name: <skill-name>              # 技能标识，建议 hap-skill-<name> 格式
description: <一句话描述>        # 含触发场景关键词
version: <x.y.z>                # SemVer
---
```

参考示例：
```yaml
---
name: crm_project_review
description: 基于明道云项目管理知识库，对 ClawCRM 项目记录进行结构化评审...当用户说"评估项目"、"项目跟进评审"等时触发。
version: 3.1.0
---
```

### 2.2 必需章节

| 章节 | 说明 |
|------|------|
| 触发条件 | 明确列出触发短语（中英文），让 AI 知道何时加载 |
| 前置条件 | Token 来源、HAP 应用 ID、知识库 ID、工作表 ID 等硬编码默认值 |
| 三层架构位置 | 声明依赖 L2 `hap_app_access` 的哪些模块 |
| 铁律 | 参数命名规则、数据源纪律、硬停止条件 |
| 端到端流程 | 逐步执行清单 |
| 硬停止分支 | exit code、触发条件、Agent 应答模板 |
| 常见陷阱 | 现象 → 根因 → 解法 |
| 版本信息 | 版本号、适用范围、变更记录 |

### 2.3 依赖声明模板

```markdown
### 三层架构中的位置

本 skill 位于 L3（业务技能层），依赖关系：
- **L1 外部服务**：提供 Token（不在本仓库）
- **L2 hap-app-access**：提供访问方法论 + 共享 Python 模块
  - `token_reader.py`：读取 token 文件
  - `mcp_client.py`：MCP JSON-RPC 客户端
```

## 3. 共享模块使用规范

### 3.1 Token 读取

**唯一方式**：通过 L2 的 `token_reader` 模块。

```python
from skills.hap_app_access.src.token_reader import read_broker_token, get_mcp_url

# 读取指定 profile 的 token
record = read_broker_token("<profile-name>")
url = get_mcp_url("<profile-name>")
```

**禁止**：自行管理 token、硬编码 MCP URL、直连 OAuth 端点。

### 3.2 MCP 调用

**唯一方式**：通过 L2 的 `MCPClient`。

```python
from skills.hap_app_access.src.mcp_client import MCPClient

client = MCPClient(mcp_url)
await client.initialize()
tools = await client.list_tools()
result = await client.call_tool("get_record_list", {
    "appId": "<appId>",
    "worksheet_id": "<worksheetId>",
    "pageSize": 50,
    "ai_description": "<用途描述>",
})
```

**禁止**：直接使用 Python MCP SDK 的 `streamablehttp_client`（业务工具不兼容）。

### 3.3 应用级 API 调用

仅当使用 Appkey+Sign 时，可使用 L2 的 `V3ApiClient`：

```python
from skills.hap_app_access.src.api_client import V3ApiClient

client = V3ApiClient(appkey="...", sign="...", api_base="https://api.mingdao.com")
data = client.get_record_list(worksheet_id="...", page_size=50)
```

## 4. 参数命名铁律

继承 L2 hap_app_access 的铁律：

1. **每次会话先调 `tools/list`**，以返回的 `inputSchema` 为 SSOT
2. 参数混用 camelCase 和 snake_case，严格按 schema 传参
3. 上游返回值字段名（驼峰） ≠ 下游入参字段名（下划线）

详见 [hap_app_access/SKILL.md](../skills/hap_app_access/SKILL.md) §4。

## 5. 硬停止规范

L3 技能必须在遇到不可恢复状态时硬停止，禁止降级兜底。

必须定义的硬停止至少包括：

| exit | 条件 | Agent 行为 |
|------|------|-----------|
| Token 不可用 | token 文件不存在或过期 | 报错退出，联系管理员 |
| 数据源为空 | 目标记录不存在或日志为空 | 原样返回，请用户补数据 |

**禁止的降级路径**：
- 用其他数据源替代
- 用知识库内容假设项目状态
- 用行业常识生成结论

## 6. 脚本规范

### 6.1 入口脚本

如果提供 Python 脚本，放在 `src/<script>.py`，遵循：

```python
#!/usr/bin/env python3
"""<技能名> CLI 入口。"""

import argparse
import json
import sys

# 标准 L2 导入
from skills.hap_app_access.src.token_reader import get_mcp_url
from skills.hap_app_access.src.mcp_client import MCPClient

async def main():
    parser = argparse.ArgumentParser(description="<描述>")
    parser.add_argument("--profile", default="<默认 profile>")
    # ... 业务参数
    args = parser.parse_args()

    # 1. 读取 token
    try:
        url = get_mcp_url(args.profile)
    except Exception as e:
        print(json.dumps({"error": f"Token 不可用: {e}"}))
        sys.exit(2)

    # 2. 初始化 MCP
    client = MCPClient(url)
    await client.initialize()

    # 3. 业务逻辑
    # ...

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### 6.2 输出格式

脚本输出统一为 JSON，便于 AI 消费：

```json
{
  "project": "<标识>",
  "data": { ... },
  "knowledgeHits": [ ... ],
  "tools": [ ... ]
}
```

## 7. 版本管理

### 7.1 版本号

遵循 SemVer（`MAJOR.MINOR.PATCH`）：

- **MAJOR**：不兼容的 API 变更（如数据源替换、评分标准重构）
- **MINOR**：向后兼容的功能新增（如新评审维度、新检索策略）
- **PATCH**：修复、文档更新、参数调整

### 7.2 版本记录

在 SKILL.md 末尾维护变更记录：

```markdown
**技能版本**：v1.0.0
**适用范围**：明道云 HAP（SaaS）

**v1.0.0 变更**：
- 初始版本
```

### 7.3 Git 发布

```bash
git tag v1.0.0
git push origin v1.0.0
```

平台（如 OpenClaw）通过 Git tag 确定拉取哪个版本。

## 8. 分发流程

### 8.1 创建独立 repo

在 GitHub 上创建 `hap-skill-<name>` 仓库：

```bash
# 初始化
mkdir hap-skill-<name>
cd hap-skill-<name>
git init

# 添加文件
cp /path/to/hap-skill-claw-lite/skills/<name>/SKILL.md .
cp -r /path/to/hap-skill-claw-lite/skills/<name>/src/ .

# 首次发布
git add -A
git commit -m "feat: initial release v1.0.0"
git tag v1.0.0
git remote add origin https://github.com/topmachinegun/<repo-name>.git
git push -u origin main --tags
```

### 8.2 平台引用

OpenClaw 等平台通过 GitHub URL 引用技能：

```
https://github.com/topmachinegun/<repo-name>
```

已有 L3 技能示例：`crm-project-review`。

### 8.3 本仓库中的参考示例

`skills/crm_project_review/` 作为 L3 参考示例留在本仓库，供开发新 L3 技能时参考。其分发版在独立 repo `crm-project-review`。

## 9. 参考实现

- [skills/crm_project_review/](../skills/crm_project_review/) — 完整的 L3 业务技能参考实现
- [skills/hap_app_access/](../skills/hap_app_access/) — L2 基础技能，所有 L3 技能的依赖
