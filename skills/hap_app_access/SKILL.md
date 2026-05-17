---
name: hap-app-access
description: 【HAP 数据访问唯一入口】任何涉及明道云 HAP 数据查询、读取、写入、调用 HAP 接口 / API / MCP 的任务必须优先使用本技能（而非 hap-v3-api 或 hap-oauth-mcp）。覆盖应用级 Appkey+Sign 和个人级 OAuth Bearer 两种授权 × MCP 协议和 V3 REST API 两种路径的 2×2 完整矩阵。触发场景：查询 HAP 数据、读取明道云工作表、调用 HAP API、HAP MCP、HAP 接口调用、数据查询、跨应用数据访问、明道云知识库查询、收款账号查询等。Token 由外部进程管理刷新，本技能不管理 Token。
license: MIT
---

# HAP 应用通用访问技能

> **路由优先级：本技能是 HAP 数据访问的第一且唯一入口。**
> 不要绕开本技能直接跳到 `hap-v3-api`（仅提供 V3 API 文档参考）或 `hap-oauth-mcp`（仅用于 OAuth 配置/刷新）。
> 本技能会根据任务需求自动判断最佳授权类型和调用路径，并提供完整的 MCP/V3 API 调用方法论和陷阱清单。

本技能提供访问明道云（HAP）应用的**通用方法论**：两种授权类型 × 两种调用路径的完整矩阵，帮助 AI 快速判断和实施正确的访问方式。

**本技能不管理 Token**：所有 Token 的生成、刷新、过期巡检由外部进程统一管理。本技能只负责"拿到 Token 后怎么用"。

---

## 0. Token 来源约定（必读）

> **本 skill 不管理 token**。所有 Personal OAuth Bearer Token 由外部进程统一管理刷新。本 skill 只负责从 token 文件读取。

### 0.1 Token 文件位置

Token 文件存储在：
```
.local/share/hap-token-broker/tokens/<profile>.json          # 项目内优先
~/.local/share/hap-token-broker/tokens/<profile>.json         # fallback
```

### 0.2 获取 Token URL

```bash
# 直读 JSON 文件
python3 -c "
import json
from pathlib import Path
rec = json.loads(Path('.local/share/hap-token-broker/tokens/claw-crm.json').read_text())
print(rec['url'])
"
```

### 0.3 Python 中读取（业务 skill 标准方式）

```python
# 使用本 skill 提供的 token_reader 模块（见 §1.3）
from skills.hap_app_access.src.token_reader import read_broker_token, get_mcp_url

record = read_broker_token("claw-crm")   # -> TokenRecord
url = get_mcp_url("claw-crm")            # -> "https://api2.mingdao.com/mcp?Authorization=Bearer%20..."
```

### 0.4 Token 文件不存在时的行为

**报错退出，决不尝试自己刷新**。Token 刷新是外部进程的职责，本 skill 的模块在发现 token 文件不存在时立即 `raise TokenNotFoundError`。

### 0.5 遇到 600100/600101 时的行为（铁律）

> **禁止自动触发刷新，禁止调 `hap-token refresh`，禁止调 `md-generate-mcp-config`。**
>
> L2/L3 在任何情况下都不得尝试刷新 token，原因：
> - 多环境（本地/152）共享同一 OAuth App 的 refresh 链，**业务层触发刷新会踢掉其他环境的 token**
> - 某环境看起来 600100，可能只是自己的缓存过期，其他环境还在正常使用
> - 盲目刷新 → 其他环境立刻 600100 → 形成互踩循环
>
> **正确做法**：报告 token 已过期，提示用户联系管理员或等待 broker 自动巡检恢复。
> 各环境的 broker 会按自己的 `refresh_before_expire_hours` 节奏独立处理，互不干扰。

### 0.6 应用级 Appkey+Sign

应用级凭据不需要刷新，由业务 skill 直接从自己的配置中读取（通过环境变量或安全存储）。详见 §2.1。

---

## 1. 共享 Python 模块

本 skill 提供三个共享模块，位于 `skills/hap-app-access/src/`，供 L3 业务 skill 直接 import 使用。

### 1.1 mcp_client.py — MCP JSON-RPC 客户端

```python
from skills.hap_app_access.src.mcp_client import MCPClient

client = MCPClient(mcp_url)
await client.initialize()

# 拉工具列表（参数命名以 schema 为 SSOT，见 §4.1）
tools = await client.list_tools()

# 调用工具
result = await client.call_tool("get_record_list", {
    "appId": "<appId>",
    "worksheet_id": "<worksheetId>",
    "pageSize": 50,
    "ai_description": "query project records",
})
```

特性：
- 自动处理 MCP session 管理（initialize → tools/list → tools/call）
- 自动剥离 MCP content 包装，返回纯 `data`
- 基于 urllib 裸 JSON-RPC POST，不依赖第三方 MCP SDK

> **关键陷阱**：Python MCP SDK 的 `streamablehttp_client` 仅适用于 `get_time` 等简单工具调用。
> 业务工具（`get_org_list`、`get_record_list`、`get_app_worksheets_list` 等）必须使用本模块的 `MCPClient`，
> 否则 `streamablehttp_client` 的 SSE/协议处理不完整，导致 `10001 Http Headers verification failed`。
> 详见 §5.12。

### 1.2 api_client.py — V3 REST API 客户端

```python
from skills.hap_app_access.src.api_client import V3ApiClient

client = V3ApiClient(appkey="...", sign="...", api_base="https://api.mingdao.com")
data = client.get_record_list(worksheet_id="...", page_size=50, filter={...})
```

仅用于应用级 Appkey+Sign 场景。Personal OAuth 场景**强制走 MCP 协议**（见 §2.3）。

### 1.3 token_reader.py — Token 文件读取器

```python
from skills.hap_app_access.src.token_reader import read_broker_token, get_mcp_url

# 读取指定 profile 的 token 记录
record = read_broker_token("claw-crm")
print(record.url)           # 完整 MCP URL
print(record.expires_at)    # 过期时间
print(record.is_expired())  # 是否已过期

# 快捷方法：直接拿 MCP URL
url = get_mcp_url("claw-crm")
```

行为：
- 优先项目内 `.local/share/hap-token-broker/tokens/<profile>.json`，fallback `~/`
- 文件不存在 → `TokenNotFoundError`
- 不尝试自己刷新

---

## 2. 授权类型与调用路径

### 2.1 授权类型总览

HAP 应用有且仅有两种授权类型：

| 维度 | 应用级授权（Appkey+Sign） | 个人级授权（OAuth Bearer） |
|------|--------------------------|---------------------------|
| 身份 | 应用身份（不受人约束） | 个人身份（等同于登录用户） |
| 凭证 | Appkey + Sign（长期有效） | Bearer Token（约 1 天过期） |
| 权限范围 | 应用内 API 开关控制的全部数据 | 当前登录用户在应用中可见的数据 |
| 跨应用 | 只能访问所属应用 | 可跨应用访问用户有权限的所有应用 |
| 适用场景 | 后台定时任务、服务间同步、脚本自动化 | 个人数据查询、以用户视角读写数据 |
| 过期 | 不过期（除非在 HAP 后台重置） | 约 1 天，需要刷新（由外部进程管理） |
| Token 来源 | 配置文件/环境变量（业务 skill 自己管理） | Token 文件（由外部进程管理刷新，§0） |

**选择原则**：
- 需要**无人值守运行** → 应用级（Appkey+Sign）
- 需要**受用户权限约束** → 个人级（OAuth Bearer）
- 需要跨多个应用 → 个人级（一个 token 覆盖多应用）
- 两者都可用 → 优先应用级（无过期风险）

### 2.2 两种调用路径

| 维度 | MCP 协议（SSE/Streamable HTTP） | V3 REST API（HTTP JSON） |
|------|-------------------------------|-------------------------|
| 协议 | MCP（Model Context Protocol） | 标准 HTTPS + JSON |
| 端点 | `https://api.mingdao.com/mcp` | `https://api.mingdao.com/v3/open/...` |
| 鉴权注入 | URL query 参数或 SSE Header | HTTP 请求头 |
| 工具发现 | 自动暴露 40~70 个工具 | 需查 API 文档 |
| 调用方式 | AI 工具原生支持 | 代码中 `fetch`/`requests` 等 |
| 适合谁 | AI 助手直接操作数据 | 开发者在代码中集成 |
| 分页 | `pageSize` 上限 **90** | `pageSize` 上限 **1000** |
| 响应大小 | 单次约 **256KB** 缓冲上限 | 无此限制 |

**选择原则**：
- AI 在对话中直接操作数据 → MCP
- 写代码集成 HAP → V3 REST API
- 两者都能用 → AI 场景用 MCP，代码场景用 V3 API

### 2.3 交叉矩阵：2×2 = 4 种组合

|  | MCP 协议 | V3 REST API（`/v3/open/*`） |
|--|---------|-------------|
| **应用级 Appkey+Sign** | ✅ 最常用 | ✅ 代码集成首选 |
| **个人级 OAuth Bearer** | ✅ **推荐且强制** | ❌ `/v3/open/*` 仅认 Appkey+Sign |

> Personal OAuth 场景下，智能体统一通过 MCP 协议调用工具。即使客户端未集成 MCP，也应用 Python MCP SDK 做运行时直调——**仍然走 MCP 协议**，不要直连任何 REST 端点。

### 2.4 应用级授权：Appkey+Sign

#### 获取凭证

1. 登录 HAP → 进入目标应用 → **应用设置** → **API 开发** → **API 密钥**
2. 复制 `Appkey` 和 `Sign`

#### MCP 路径配置

```json
{
  "mcpServers": {
    "hap-mcp-<应用名>": {
      "url": "https://api.mingdao.com/mcp?HAP-Appkey=<Appkey>&HAP-Sign=<Sign>"
    }
  }
}
```

#### V3 REST API 路径

**请求头**：
```http
Content-Type: application/json
HAP-Appkey: <Appkey>
HAP-Sign: <Sign>
```

**常用端点**：

| 操作 | 方法 | 路径 |
|------|------|------|
| 获取应用信息 | GET | `/v3/app/info` |
| 获取工作表列表 | GET | `/v3/app/worksheets` |
| 获取工作表字段 | GET | `/v3/app/worksheet/getFields` |
| 查询记录 | POST | `/v3/app/worksheets/{id}/rows/list` |
| 获取记录详情 | GET | `/v3/app/worksheets/{id}/rows/{rowId}` |
| 创建记录 | POST | `/v3/app/worksheets/{id}/rows` |
| 更新记录 | PUT | `/v3/app/worksheets/{id}/rows/{rowId}` |
| 删除记录 | DELETE | `/v3/app/worksheets/{id}/rows/{rowId}` |
| 批量创建 | POST | `/v3/app/worksheets/{id}/rows/batch` |
| 批量更新 | PUT | `/v3/app/worksheets/{id}/rows/batch` |
| 批量删除 | DELETE | `/v3/app/worksheets/{id}/rows/batch` |

> 完整 V3 API 规范详见 `hap-v3-api` 技能。

### 2.5 个人级授权：OAuth Bearer

#### Token 来源

Token 由外部进程统一管理刷新（见 §0）。业务 skill 无需关心 Token 的获取和刷新。

#### ⚠️ Claude Code MCP 兼容性（必读）

**Claude Code 内置 MCP 客户端对 Bearer token 鉴权存在已知兼容性问题**：`mcp__HAP-Personal-MCP__get_time` 能正常调用，但业务工具（`get_org_list`、`get_record_list` 等）会返回 `600100 token无效或过期`，即使 token 完全有效。

**根因**：Claude Code MCP HTTP 传输层与 `api.mingdao.com` Bearer token 校验存在细微不兼容。同一 URL、同一 token、同一参数，Python `urllib` 直连正常，Claude Code 内置 MCP 不行。

**永久规则（不可绕过）**：

> Personal MCP 业务工具调用**必须走 MCPClient 直连，禁止使用 `mcp__HAP-Personal-MCP__*` 工具（`get_time` 除外）。**
>
> 使用项目根目录的桥接脚本：
> ```bash
> python3 hap_personal_mcp.py <tool_name> '<json_args>'
> ```
>
> 该脚本自动从 token 文件读取 token，完成 MCP 握手，走 `urllib` 直连调用。

#### MCP 路径配置（AI 工具）

```json
{
  "mcpServers": {
    "HAP-Personal-MCP": {
      "url": "https://api.mingdao.com/mcp?Authorization=Bearer%20<Token>"
    }
  }
}
```

可用工具约 60~70 个，涵盖应用级全部工具 + `get_org_list`（组织列表）、跨应用数据访问等，受用户权限约束。

#### MCP 调用必填参数

Personal MCP 的**每次工具调用**必须额外提供：

```json
{
  "appId": "<目标应用的 AppID>",
  "ai_description": "<本次调用的用途描述>"
}
```

- `appId`：必填，标识访问哪个应用，否则返回 401
- `ai_description`：必填，HAP 服务端用于审计和鉴权校验
- 元数据工具（`get_org_list` 等）不需要 `appId`
- 应用级 MCP 不需要这两个参数——Appkey+Sign 已经绑定了应用

#### 获取应用 AppID

| 方式 | 说明 |
|------|------|
| 浏览器 URL | 打开目标应用，URL 格式 `https://app.mingdao.com/app/<AppID>/...` |
| MCP 发现序列 | `get_org_list()` → `get_app_list(org_id)` → 按名称匹配 |
| V3 API `GET /v3/app/info` | 使用 Appkey+Sign 请求，返回 `data.appId` |

> `get_app_list` 的参数是 **`org_id`**，不是 `appId`。必须先调 `get_org_list()` 拿到组织 ID。

#### 标准发现序列（5 步）

```
1. get_org_list()                                 → 拿所有可见组织 org_id
2. get_app_list(org_id)                           → 按名称定位目标应用 appId
3. get_app_worksheets_list(appId)                 → 列出应用所有工作表
4. get_worksheet_structure(worksheet_id, appId, responseFormat="md") → 查字段与选项 key
5. get_record_list(worksheet_id, appId, filter, fields) → 按条件取数据
```

关键点：
- `get_app_list` 参数是 **`org_id`**；工作表相关工具用 **`worksheet_id`**（snake_case）
- 每次调用必填 `ai_description`
- `get_worksheet_structure` 建议传 `responseFormat="md"`，输出紧凑且含选项 key

#### OAuth scope 限制

Personal OAuth token 的可见范围 = 用户在 OAuth 同意页勾选的应用。对于**明道云官方内置应用**（知识库、任务、审批等），普通用户通常不在 token scope 里，此时 `get_org_list` / `get_app_list` 可能返回空或 10001。

**解法**：跳过发现序列，用浏览器 URL 法直接取 `appId`。

#### 官方应用访问

**明道云官方应用**（CRM2025、知识库等）的应用管理员为明道官方团队，外部用户**无法获取 Appkey+Sign**，只能走 Personal OAuth。

---

## 3. API Host（产品线）

| 产品线 | API Host | MCP URL 示例 |
|--------|----------|-------------|
| 明道云 HAP | `https://api.mingdao.com` | `https://api.mingdao.com/mcp?...` |
| Nocoly HAP | `https://www.nocoly.com` | `https://www.nocoly.com/mcp?...` |
| 私有部署 | `https://<域名>/api` | `https://<域名>/mcp?...` |

---

## 4. 通用调用规范

### 4.1 参数命名：以 `tools/list` 为 SSOT

HAP 工具参数命名**混用 camelCase 和 snake_case**。根因是 Personal MCP 底层每个 Action 由 integration 作者各自定义。

| 命名风格 | 代表参数 |
|---------|---------|
| camelCase | `pageSize`、`pageIndex`、`useFieldIdAsKey`、`appId`、`responseFormat`、`knowledgeIds`、`searchMode`、`topK` |
| snake_case | `org_id`、`worksheet_id`、`row_id`、`view_id`（资源 ID 类）；`ai_description` |

**铁律**：调用任何工具前，**先执行 `tools/list` 取目标工具的 `inputSchema`，严格以 schema 声明的 key 名传参**。

```python
# ❌ 错误：用驼峰
get_worksheet_structure(worksheetId=..., appId=...)  # 10001

# ✅ 正确：用 snake_case
get_worksheet_structure(worksheet_id=..., appId=...)
```

### 4.2 返回值字段名 ≠ 入参字段名

同一个资源 ID，在列表返回值中用驼峰，但作为详情工具的入参时必须改下划线：

| 上游工具 | 返回字段名 | 作为下游入参时要改成 |
|---------|-----------|---------------------|
| `get_app_worksheets_list` | `worksheetId` | `worksheet_id` |
| `get_org_list` | `orgId` | `org_id` |
| `get_record_list` | `rowid` | `row_id` |

**规则**：用上游返回值填下游参数时，**取值不取 key**；key 名以下游工具的 schema 为准。

### 4.3 Filter 结构

```json
{
  "filter": {
    "type": "group",
    "logic": "AND",
    "children": [
      {
        "type": "condition",
        "field": "<fieldId 或 alias>",
        "operator": "eq",
        "value": ["<值>"]
      }
    ]
  }
}
```

规则：顶层必须是 `group`；最多两层嵌套：`group → group → condition`。

### 4.4 分页

| 路径 | pageSize 上限 | 推荐值 | 说明 |
|------|-------------|--------|------|
| MCP `get_record_list` | **90** | 50 | 单次响应 ~256KB 缓冲上限 |
| V3 API `rows/list` | **1000** | 100~500 | 无缓冲限制 |

必须翻页获取全部记录，**不可用单页数据做全局统计**。

### 4.5 字段 ID vs 别名

| 场景 | 用什么 |
|------|--------|
| Filter 的 `field` | fieldId（UUID）或 alias 均可 |
| 写入（create/update）的 key | fieldId 或 alias 均可 |
| `get_record_list(useFieldIdAsKey=True)` 返回的 key | **强制替换为 fieldId（UUID）** |

---

## 5. 通用陷阱清单

### 5.1 选项字段写入必须用 key

写入 SingleSelect / MultipleSelect 字段时，value 必须传 **option key（UUID）** 的数组，不能传显示文本。即使是单选，也要用数组 `["key"]`。

### 5.2 关联字段 get_record_list 可能丢失

部分 Relation 字段可能返回空字符串 `""`。**解法**：额外调 `get_record_details(rowId)` 补全。

### 5.3 _owner 字段响应为空但 filter 有效

`_owner` 字段在记录列表中永远返回 `""`，但 `filter.ownerid` 筛选仍然有效。

### 5.4 caid 服务端 filter 的 in 操作不稳定

**解法**：客户端过滤——先拉全量再按 `_createdBy.accountId` 在客户端筛选。

### 5.5 OAuth Bearer 域名白名单

OAuth App 的 Bearer Token 只对**创建该 App 时配置的域名**有效：

| OAuth App 类型 | 域名白名单 | 典型场景 |
|---------------|----------|---------|
| **明道云官方过渡期集成 App** | `api2.mingdao.com` | 使用 `hap-oauth-mcp` 技能获取 token |
| **自建 OAuth App（默认配置）** | `api.mingdao.com` | 企业自主集成 |

- 调错域名 → `error_code: 10001`
- 两个域名**不可互换**

### 5.6 MCP 单次响应 256KB 上限

超出抛 `Exceeded limit on max bytes to buffer`。**解法**：降低 `pageSize`（大表推荐 50），或改用 V3 REST API。

### 5.7 数值字段读写类型不一致

- 写入：传数字类型 `1000000.50`
- 读取：返回字符串 `"1000000.50"`

### 5.8 日期过滤时区偏移

日期字段可能因服务端时区设置偏移 ±1 天。**解法**：放宽过滤窗口 + 客户端二次过滤。

### 5.9 triggerWorkflow 参数

| 场景 | 值 |
|------|---|
| 正常业务操作 | `true`（默认） |
| 数据迁移 / 批量同步 | `false` |

### 5.10 knowledge_search 返回「账号未登录」

排查顺序：
1. 先查 schema：`tools/list` 核对 `knowledge_search` 参数名（`knowledgeIds`、`searchMode`、`topK` 等）
2. 再查必填参数：`appId` + `ai_description`
3. 最后才考虑 token 权限

**兜底方案**：走常规查询 `get_app_worksheets_list` → `get_record_list` → `get_record_details`。

### 5.12 Python MCP SDK 的 streamablehttp_client 不适用于业务工具

Python `mcp` 包提供的 `streamablehttp_client` 只实现了基本的 SSE 握手，对需要完整 JSON-RPC 响应解析的业务工具支持不完整。

- `get_time` 等简单工具 → `streamablehttp_client` 可用
- 业务工具（`get_org_list`、`get_app_list`、`get_record_list`、`get_worksheet_structure` 等）→ **必须使用本 skill 的 `MCPClient`**（`skills/hap_app_access/src/mcp_client.py`）

误用 `streamablehttp_client` 调业务工具 → `10001 Http Headers verification failed`。根因是 SSE stream 的 JSON-RPC 响应解析不完整，导致 HAP 服务端收到的请求 headers 残缺。

### 5.11 MDAccountLogin「服务异常」≠ 服务端故障

这是明道云反刷库的**统一脱敏响应**。真实原因概率降序：
1. 账号不存在 / 拼错
2. 密码错
3. 账号被风控
4. OAuth App 被撤销
5. 服务端真挂（罕见）

**正确诊断顺序**：先查 env 中的账号拼写 → 手工登录验证 → 最后才怀疑服务端。

---

## 6. 错误码速查

| 错误码 | 含义 | 典型原因 | 解法 |
|--------|------|---------|------|
| `1` | 成功 | — | — |
| `-1` | 通用失败 | 查看 `error_msg` | 按 error_msg 排查 |
| `4` | 权限不足 | 当前身份无该操作权限 | 检查授权类型和用户权限 |
| `10` | 参数错误 | 参数缺失或格式错误 | 核对参数名和值格式 |
| `10001` | HTTP Headers 验证失败 | 域名不在白名单 / 参数缺失或错误 / **误用 streamablehttp_client** | 确认域名匹配；核对参数名与 schema；**业务工具必须用 MCPClient（§5.12）** |
| `600101` | 授权已失效 | Bearer token 过期 | **禁止业务层刷新**。报告过期，等待 broker 自动恢复或联系管理员 |
| `600100` | token 无效/缺失 | token 为空或格式错误 | **禁止业务层刷新**。检查 token 文件是否存在，等待 broker 自动恢复 |

### 10001 排错三步走（强制顺序）

| 顺序 | 检查项 | 阅读 |
|------|--------|------|
| **1** | 参数名与 schema 是否一致（snake_case vs camelCase） | §4.1 / §4.2 |
| **2** | OAuth token 域名白名单是否匹配 | §5.5 |
| **3** | Token / 权限问题（极少见） | §6 |

---

## 7. 快速决策流程

```
需要访问 HAP 应用数据
│
├─ 1. 查 hap_app_access/apps.toml（与 SKILL.md 同目录）
│   ├─ 有 appId 且配置了 appkey → Appkey+Sign（优先，权限更大）
│   │   ├─ AI 对话操作 → MCP
│   │   └─ 代码集成   → V3 API
│   │
│   └─ 有 appId 但无 appkey → OAuth MCP（走 §0 token 文件）
│
└─ 2. apps.toml 无记录
    ├─ token 文件存在 → OAuth MCP（走发现序列定位 appId）
    └─ token 文件不存在 → 报告：需提供 appId + Appkey/Sign，或先配置 token
```

> **核心原则**：Appkey+Sign 权限更大、不过期、可走 V3 API（pageSize 上限 1000），因此优先。OAuth MCP 是通用兜底方案。

配置格式见 [apps.example.toml](apps.example.toml)（同目录），Python 读取见 [app_config.py](src/app_config.py)。

---

## 8. 相关技能

| 技能 | 用途 | 层级 |
|------|------|------|
| `hap-oauth-mcp` | OAuth 授权流程 + Token 刷新后端 | 独立 skill |
| `hap-mcp-usage` | MCP 配置的自动化安装（9 种 AI 工具平台） | 独立 skill |
| `hap-v3-api` | V3 REST API 完整使用规范 | 独立 skill |
| `hap-frontend-project` | 使用 HAP 作为后端搭建独立网站 | 独立 skill |
| `hap-view-plugin` | 开发 HAP 自定义视图插件 | 独立 skill |

---

## 9. 三层架构约定

```
L1: token-broker/                Token 中控服务（源码在本仓库，独立 repo 分发）
         │
         │ 提供 token URL（文件接口）
         ▼
L2: skills/hap-app-access/ 本技能 — HAP 通用访问方法论 + 共享代码
         │
         │ 提供 MCP/V3 API 调用能力
         ▼
L3: 独立 GitHub repo             业务技能（各自独立开发、独立分发）
    skills/crm_project_review/   参考示例（本仓库内，分发版在独立 repo）
```

| 层 | 职责 | 不做什么 |
|---|---|---|
| L1 Token Broker | 服务器级 token 刷新、过期巡检（源码在 `token-broker/`，运行时由外部进程管理） | 不涉及业务逻辑、不知道 HAP 应用结构 |
| L2 hap-app-access | HAP 应用访问方法论、MCP/V3 API 调用、错误码/陷阱清单、共享 Python 模块 | 不管理 token 生成/刷新、不包含业务逻辑 |
| L3 业务技能 | 具体业务逻辑、知识库检索、数据加工 | 不直接处理 MCP JSON-RPC、不管理凭据 |

---

**技能版本**：v3.3.0
**适用范围**：明道云 HAP（SaaS / Nocoly / 私有部署）

**v3.3.0 变更**：
- 新增 §0.5「遇到 600100/600101 时的行为（铁律）」：禁止 L2/L3 业务层触发 token 刷新，防止多环境互踩
- §6 错误码表更新：600100/600101 解法明确标注「禁止业务层刷新」

**v3.2.0 变更**：
- 三层架构更新：L1 源码回归本仓库 `token-broker/`（运行时仍由外部进程管理），L3 改为独立 repo 分发
- 添加 L3 开发规范与脚手架技能引用

**v3.1.0 变更**：
- Token 管理全面剥离，交由外部进程管理。本仓库不再包含 Token 刷新源码
- L1 Token Broker 源码移出本仓库，三层架构中 L1 改为外部服务
- `token_reader.py` 路径和 API 不变

**v3.0.0 变更**：
- CLI `hap-access` 模式移除，替换为共享 Python 模块（`mcp_client` / `api_client` / `token_reader`）
- 新增 §0「Token 来源约定」、§1「共享 Python 模块」、§9「三层架构约定」
- 保留核心内容：授权类型、MCP 协议、错误码、陷阱清单
