# hap-skill-claw-lite

明道云 HAP 应用集成工具包，三层架构，统一 Token 管理。

## 三层架构

```
L1: token-broker/       独立部署的 Token 中控服务（systemd 守护进程）
         │
         │ 提供 token URL（文件接口）
         ▼
L2: skills/hap_app_access/   基础技能 — HAP 通用访问方法论 + 共享代码
         │
         │ 提供 MCP/V3 API 调用能力
         ▼
L3: skills/crm_project_review/  业务技能 — CRM 项目评审
    skills/...                   未来业务技能横向扩展
```

| 层 | 职责 | 不做什么 |
|---|---|---|
| L1 Token Broker | 服务器级 token 刷新、多 profile 管理、过期巡检 | 不涉及业务逻辑、不知道 HAP 应用结构 |
| L2 hap_app_access | HAP 应用访问方法论、MCP/V3 API 调用、错误码/陷阱清单、共享 Python 模块 | 不管理 token 生成/刷新、不包含业务逻辑 |
| L3 业务技能 | 具体业务逻辑、知识库检索、数据加工 | 不直接处理 MCP JSON-RPC、不管理凭据 |

## 快速开始

### 1. 部署 Token Broker（152 服务器）

```bash
cd token-broker
sudo bash install.sh
sudo -e /root/.config/hap-token-broker/config.toml   # 填入真实凭据
sudo bash install.sh --restart
hap-token status
```

### 2. 加载技能到 AI 工具

将 `skills/` 下的技能目录复制到对应 AI 工具的 skills 路径：

```bash
# Qoder
cp -r skills/hap_app_access ~/.qoder/skills/
cp -r skills/crm_project_review ~/.qoder/skills/

# 其他遵循 Agent Skills 约定的客户端同理
```

### 3. 运行业务脚本

```bash
# CRM 项目评审
python3 skills/crm_project_review/src/review_project.py \
  --project "XYZ有限公司"
```

## 仓库结构

```
hap-skill-claw-lite/
├── token-broker/           # L1: Token 中控服务（独立部署）
│   ├── src/                # Python 源码
│   ├── systemd/            # systemd unit 模板
│   ├── config.example.toml # 配置模板
│   └── install.sh          # 一键部署脚本
├── skills/                 # 技能目录（加载到 AI 工具）
│   ├── hap_app_access/     # L2: 基础技能
│   │   ├── SKILL.md
│   │   └── src/
│   ├── crm_project_review/ # L3: 业务技能
│   │   ├── SKILL.md
│   │   └── src/
│   └── ...                 # 未来业务技能
└── docs/                   # 架构文档
```

## 相关技能

本仓库不包含但依赖以下独立技能：

| 技能 | 用途 | 关系 |
|------|------|------|
| `hap-oauth-mcp` | OAuth 授权 + Token 生成 | Token Broker 的刷新后端 |
| `hap-v3-api` | V3 REST API 完整规范 | hap-app-access 通过引用补充 |
| `hap-mcp-usage` | MCP 配置自动化安装 | 独立使用 |

## License

MIT
