# OpenClaw / Bybit Control API + GUI — 部署封板清单（2026-03-26）

## 1. 部署封板检查项

### 1.1 代码完整性

| 检查项 | 状态 | 说明 |
|---|---|---|
| 默认入口统一 | ✅ | `app.main:app`（snapshot-stable） |
| 回滚入口保留 | ✅ | `app.main_legacy:app` |
| 所有 GET 端点可用 | ✅ | 10 个读取端点 |
| 所有 POST 端点可用 | ✅ | 15 个写入/控制端点（含 3 个新增） |
| 产品族配置写接口 | ✅ | 6 个产品族独立配置端点 |
| 经营摘要完整 | ✅ | daily + 历史条目 + 成本分解 |
| PnL 录入端点 | ✅ | realized 累加 + unrealized 快照 |
| GUI 配置台可交互 | ✅ | 产品族控件 + 录入表单 + 设置台 |
| 二次确认弹窗 | ✅ | 所有关键动作有确认保护 |
| Runtime bridge 集成 | ✅ | 可选外部快照叠加 |
| Snapshot identity 稳定 | ✅ | 只读 GET 不变更 snapshot_id |

### 1.2 安全边界

| 检查项 | 状态 | 说明 |
|---|---|---|
| execution_authority = not_granted | ✅ | 任何操作后均不变 |
| mode_switch 阻断 live | ✅ | live_ready 等值被明确拒绝 |
| 未认证请求 401 | ✅ | 无 token → 401 |
| 非白名单路径 400 | ✅ | config-change 白名单外 → 400 |
| connector 角色分离 | ✅ | readonly ≠ execution |

### 1.3 部署基础设施

| 检查项 | 状态 | 说明 |
|---|---|---|
| Dockerfile | ✅ | Python 3.11-slim, port 8710 |
| docker-compose.yml | ✅ | 含全部环境变量 + volume 映射 |
| requirements.txt | ✅ | 5 个依赖全部 pinned |
| .env.example | ✅ | 全部环境变量有中英注释 |
| start_local.sh | ✅ | 一键启动（自动 venv + 安装 + 启动） |
| .gitignore 覆盖 | ✅ | .env / .venv / runtime/ / __pycache__/ |

### 1.4 文档

| 检查项 | 状态 | 说明 |
|---|---|---|
| README.md | ✅ | 完整端点表 + 环境变量 + 启动指南 |
| DEPLOY_README.md（Docker） | ✅ | Docker 部署指南 |
| Worklog 2026-03-25 | ✅ | 初始开发日志 |
| Worklog 2026-03-26 | ✅ | 配置写接口 + 经营数据 + 设置台 |
| 本文件 | ✅ | 部署封板清单 |

### 1.5 测试

| 检查项 | 状态 | 说明 |
|---|---|---|
| 原有合同测试 | ✅ | 3/3 passed |
| 快照稳定性测试 | ✅ | 3/3 passed |
| Runtime bridge 测试 | ✅ | 3/3 passed |
| Runtime 快照生成测试 | ✅ | 3/3 passed |
| Runtime 目录提供器测试 | ✅ | 3/3 passed |
| 产品族/经营/PnL/设置测试 | ✅ | 23/23 passed |
| **总计** | **✅** | **38/38 passed, 0 failures** |

---

## 2. 已知限制（非阻断）

| 限制 | 影响 | 后续计划 |
|---|---|---|
| 经营数据仅 daily 切片 | 无 weekly/monthly | L 章 Net PnL Dashboard |
| Runtime bridge 依赖文件快照 | 非实时 | 后续接 OpenClaw runtime 事件流 |
| 学习系统仅骨架 | 只有空列表 | L 章正式实现 |
| GUI Portal 未整合 | 独立运行 | 后续嵌入 OpenClaw 主 Portal |

---

## 3. 封板结论

Control API v1 + GUI Operator Console v1 达到 **functional closeout** 标准：

- 所有计划端点已实现且通过测试
- GUI 可交互操作全部产品族配置、经营数据录入、系统设置
- 安全边界不可突破
- 部署基础设施完备
- 文档和 worklog 齐全

**建议**：合并本分支后正式进入 L 章（Learning / Self-Observability / Net PnL）。
