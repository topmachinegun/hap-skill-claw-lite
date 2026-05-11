# hap-skill-claw-lite

明道云 HAP 技能的基础开发环境。维护 L1 Token Broker 源码与 L2 通用访问技能，同时为 L3 业务技能提供开发规范与脚手架工具。

## 定位

本仓库是 **HAP 技能体系的开发中枢**，不直接参与线上部署或分发：

| 组件 | 本仓库角色 | 分发方式 |
|------|-----------|---------|
| L1 token-broker | 源码开发与维护 | 手动同步到独立 repo `hap-token-broker` 分发 |
| L2 hap_app_access | 源码开发与维护，随本仓库版本发布 | 本仓库直接分发 |
| L3 业务技能 | 提供开发规范 + 脚手架 skill；含 `crm_project_review` 参考示例 | 各 L3 技能独立 GitHub repo 分发 |

## 三层架构

```
L1: token-broker/               Token 中控服务（源码在此，独立 repo 分发）
         │
         │ 提供 token URL（文件接口）
         ▼
L2: skills/hap_app_access/     基础技能 — HAP 通用访问方法论 + 共享代码
         │
         │ 提供 MCP/V3 API 调用能力
         ▼
L3: 独立 GitHub repo            业务技能（各自独立开发、独立分发）
    skills/crm_project_review/  参考示例（本仓库内，不做直接分发）
    skills/hap-skill-creator/   脚手架 skill — 快速生成新 L3 技能
```

| 层 | 职责 | 不做什么 |
|---|---|---|
| L1 Token Broker | 服务器级 token 刷新、多 profile 管理、过期巡检 | 不涉及业务逻辑、不知道 HAP 应用结构 |
| L2 hap_app_access | HAP 应用访问方法论、MCP/V3 API 调用、错误码/陷阱清单、共享 Python 模块 | 不管理 token 生成/刷新、不包含业务逻辑 |
| L3 业务技能 | 具体业务逻辑、知识库检索、数据加工 | 不直接处理 MCP JSON-RPC、不管理凭据 |

## 快速开始

### 1. 加载 L2 基础技能到 AI 工具

```bash
# Qoder
cp -r skills/hap_app_access ~/.qoder/skills/

# 其他遵循 Agent Skills 约定的客户端同理
```

### 2. 加载 L3 脚手架（可选，用于创建新业务技能）

```bash
cp -r skills/hap-skill-creator ~/.qoder/skills/
```

### 3. 在本地运行业务脚本（开发调试）

```bash
# 参考示例：CRM 项目评审
python3 skills/crm_project_review/src/review_project.py \
  --project "XYZ有限公司"
```

> Token 由外部 Broker 进程管理，脚本通过 `token_reader` 自动读取。详见 [hap_app_access/SKILL.md](skills/hap_app_access/SKILL.md) §0。

## 仓库结构

```
hap-skill-claw-lite/
├── token-broker/              # L1: Token 中控服务源码
│   ├── src/                   # Python 源码
│   ├── bin/                   # CLI 入口
│   ├── systemd/               # systemd unit 模板
│   ├── config.example.toml    # 配置模板
│   └── install.sh             # 部署脚本
├── skills/                    # 技能目录
│   ├── hap_app_access/        # L2: HAP 通用访问技能（核心资产）
│   │   ├── SKILL.md
│   │   └── src/
│   ├── crm_project_review/    # L3: 参考示例
│   │   ├── SKILL.md
│   │   └── src/
│   └── hap-skill-creator/     # L3: 脚手架 skill
│       └── SKILL.md
├── docs/                      # 开发文档
│   └── l3-development.md      # L3 业务技能开发规范
└── config/
    └── apps.example.toml      # 应用认证配置模板
```

## 版本管理

| 组件 | 版本方式 | 权威源 |
|------|---------|--------|
| L1 token-broker | 独立 repo 独立版本 | 本仓库（开发）→ `hap-token-broker` repo（分发，手动同步） |
| L2 hap_app_access | SKILL.md frontmatter `version` | 本仓库 |
| L3 业务技能 | 各独立 repo 的 Git tag | 各自独立 repo |
| 整体 monorepo | Git tag（如 `v1.0.0`） | 本仓库 |

## L3 业务技能开发

- 开发规范：[docs/l3-development.md](docs/l3-development.md)
- 脚手架工具：加载 `skills/hap-skill-creator` 后，AI 可自动生成新 L3 技能骨架
- 参考示例：`skills/crm_project_review/`（分发版在独立 repo `crm-project-review`）
- 分发：每个 L3 技能独立建 GitHub repo，平台（如 OpenClaw）直接通过 GitHub 拉取

## 相关技能

| 技能 | 用途 | 与本仓库关系 |
|------|------|-------------|
| `hap-oauth-mcp` | OAuth 授权 + Token 生成 | Token Broker 的刷新后端 |
| `hap-v3-api` | V3 REST API 完整规范 | hap-app-access 通过引用补充 |
| `hap-mcp-usage` | MCP 配置自动化安装 | 独立使用 |
| `hap-token-broker` | L1 独立分发 repo | 从本仓库 `token-broker/` 手动同步 |
| `crm-project-review` | crm_project_review 分发版 | 从本仓库参考示例衍生 |

## License

MIT
