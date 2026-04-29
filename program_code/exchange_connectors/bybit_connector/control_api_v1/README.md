# OpenClaw / Bybit Control API + GUI V1 RC2

**FastAPI + 内嵌静态 GUI** 的受保护控制台。
**FastAPI + embedded static GUI** guarded control console.

---

## 当前状态 / Current Status

| 维度 | 状态 |
|---|---|
| API 完成度 | ~95%（18 个端点全部可用） |
| GUI 完成度 | ~95%（配置台 + 录入面板 + 设置台可交互） |
| 执行权限 | `disabled`（未授予，不可变） |
| 默认入口 | `app.main:app`（snapshot-stable） |
| 回滚入口 | `app.main_legacy:app` |
| 分支 | `feature/openclaw-bybit-control-api-gui-v1-rc2` |

---

## 一键启动 / Quick Start

### 本地启动 / Local

```bash
cd program_code/exchange_connectors/bybit_connector/control_api_v1
bash start_local.sh          # 默认端口 8710
bash start_local.sh 8100     # 自定义端口
```

脚本会自动创建 venv、安装依赖、启动 uvicorn。

### 手动启动 / Manual

```bash
cd program_code/exchange_connectors/bybit_connector/control_api_v1
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
mkdir -p .secrets && chmod 700 .secrets
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > .secrets/api_token
chmod 600 .secrets/api_token
export OPENCLAW_API_TOKEN_FILE="$PWD/.secrets/api_token"
uvicorn app.main:app --host 0.0.0.0 --port 8710 --reload
```

### Docker

```bash
cd docker_projects/trading_services/openclaw_bybit_control_api_v1
docker compose up --build
```

### 打开 / Open

| 入口 | 地址 |
|---|---|
| GUI 控制台 | `http://127.0.0.1:8710/` |
| API 文档 | `http://127.0.0.1:8710/docs` |

在 GUI 中输入你生成或从密钥管理器读取的 Token，点"连接"。

---

## 环境变量 / Environment Variables

详见 `.env.example`。关键变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OPENCLAW_API_TOKEN` | 无 | Bearer Token（生产环境必须显式设置，或使用 `OPENCLAW_API_TOKEN_FILE`） |
| `OPENCLAW_API_TOKEN_FILE` | `.secrets/api_token` | Bearer Token 文件路径 |
| `OPENCLAW_STATE_FILE` | `runtime/...state.json` | 控制状态持久化路径 |
| `OPENCLAW_RUNTIME_SNAPSHOT_FILE` | （空） | 外部 runtime 快照路径（可选） |
| `OPENCLAW_READONLY_CONNECTOR_NAME` | `bybit_prod_readonly_main` | 只读连接器名称 |
| `OPENCLAW_EXECUTION_CONNECTOR_NAME` | （空） | 执行连接器（当前阶段留空） |

---

## API 端点总览 / API Endpoints

### 系统信息（只读）/ System Info (Read-Only)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/system/overview` | 系统运行态摘要 |
| GET | `/api/v1/system/chapter-status` | 章节就绪状态 |
| GET | `/api/v1/system/control-plane` | 控制平面全量 |
| GET | `/api/v1/system/capability-matrix` | 能力矩阵 |
| GET | `/api/v1/system/product-families` | 产品族事实与状态 |
| GET | `/api/v1/system/business/daily` | 每日经营指标 |
| GET | `/api/v1/system/business/summary` | **完整经营摘要**（含历史条目 + 成本分解） |
| GET | `/api/v1/system/health` | 健康评分与 gate |
| GET | `/api/v1/system/audit-summary` | 审计动作摘要 |
| GET | `/api/v1/system/source-context` | 连接器角色与连接状态 |

### 学习系统 / Learning

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/learning/overview` | 学习观察摘要 |
| GET | `/api/v1/learning/hypotheses` | 假设与实验记录 |

### 控制动作（需认证）/ Control Actions (Authenticated)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/control/recheck/j-canonical` | J 章 canonical 复核 |
| POST | `/api/v1/control/recheck/k-canonical` | K 章 canonical 复核 |
| POST | `/api/v1/control/recheck/j-closeout` | J 章 closeout 复核 |
| POST | `/api/v1/control/recheck/k-closeout` | K 章 closeout 复核 |
| POST | `/api/v1/control/demo/validate` | Demo 前提验证 |
| POST | `/api/v1/control/demo/arm` | Demo Arm（进入 armed_but_closed） |
| POST | `/api/v1/control/demo/enable` | Demo Enable（受 gate 阻断） |
| POST | `/api/v1/control/demo/relock` | Demo Relock（回锁） |
| POST | `/api/v1/control/safe-recheck-bundle` | 多步安全复核打包 |
| POST | `/api/v1/control/product-family/{family}/config` | **产品族配置写接口** |

### 数据录入（需认证）/ Data Input (Authenticated)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/input/cost` | 录入费用条目 |
| POST | `/api/v1/input/event` | 录入业务事件 |
| POST | `/api/v1/input/manual-note` | 录入手动备注 |
| POST | `/api/v1/input/config-change` | 白名单路径配置变更 |
| POST | `/api/v1/input/pnl-entry` | **PnL 盈亏录入** |

### 产品族配置端点详细说明

`POST /api/v1/control/product-family/{family}/config`

支持的 `{family}` 值：`spot` / `margin` / `perp_linear` / `perp_inverse` / `options` / `other_derivatives_reserved`

payload 支持字段：
```json
{
  "enabled_switch": true,
  "visibility_switch": true,
  "mode_switch": "shadow_only",
  "action_permissions": {
    "new_order": false,
    "cancel": true,
    "amend": false,
    "reduce_only": false,
    "increase_position": false,
    "close_position": false
  }
}
```

安全限制：`mode_switch` 只允许 `disabled` / `observe_only` / `shadow_only`。

---

## GUI 功能区 / GUI Sections

| 区域 | 功能 |
|---|---|
| 运行态摘要 | 全局模式、执行权限、Demo 状态、快照绑定 |
| 运行模式控制 | Demo Reserved / Arm / Validate 等 guarded 动作 |
| 经营与收益摘要 | 每日 PnL + 成本 + 历史条目 + 成本分解 |
| 产品族配置（只读） | 各族启用/可见/模式/能力快照 |
| 产品族配置设置台 | **可交互修改** enabled/visible/mode + 动作权限 |
| 长期开关预留 | 未来开关位（当前锁定/预留） |
| 收益与成本录入 | 费用录入表单 + PnL 录入表单 + 历史列表 |
| 系统设置台 | 风险策略 / Demo Ack / 学习审批开关 |
| 来源上下文 | 连接状态与角色分离 |
| 健康摘要 | 健康评分与 gate 状态 |
| 产品族事实表 | 全产品族事实/控制/能力一览表 |
| 快捷动作 | 一键执行 guarded 操作 |
| 调试原文 | 折叠式原始 JSON（审计用） |

---

## Runtime 快照桥接 / Runtime Snapshot Bridge

设置 `OPENCLAW_RUNTIME_SNAPSHOT_FILE` 指向外部 JSON 快照文件后：

- `source_context` 优先读取外部连接状态
- `global_runtime.facts` 优先读取外部事实
- `product_family_status.*.facts` 优先读取外部产品族事实
- 响应 `snapshot_id` 绑定 state + runtime 快照

推荐 JSON 结构见 `examples/runtime_snapshot.example.json`。

---

## 测试 / Tests

```bash
cd program_code/exchange_connectors/bybit_connector/control_api_v1
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

当前：38 个测试全部通过。

---

## 安全边界 / Safety Boundaries

以下条件**始终**成立，任何 GUI/API 操作均无法突破：

```
global_execution_mode_switch  = disabled
execution_state               = disabled
execution_authority           = not_granted
runtime_still_protected       = true
```

- `mode_switch` 尝试设置 `live_ready` 等值会被明确拒绝
- 即使所有产品族全部启用 + 开启所有动作权限，execution authority 仍为 `disabled`
- 未认证请求返回 401

---

## 文件结构 / File Structure

```
control_api_v1/
├── app/
│   ├── main.py                 # 默认入口（snapshot-stable）
│   ├── main_legacy.py          # 核心实现（模型 + 逻辑 + 路由）
│   ├── runtime_bridge.py       # Runtime 快照桥接层
│   └── static/
│       ├── index.html          # GUI HTML
│       ├── app.js              # GUI JavaScript（配置台 + 录入 + 设置台）
│       └── styles.css          # GUI 样式
├── tests/                      # 集成测试（38 个用例）
├── scripts/                    # Runtime 快照生成 / 验证工具
├── examples/                   # 示例 JSON 快照文件
├── docs/                       # 技术文档
├── runtime/                    # 运行时状态存储（.gitignore）
├── Dockerfile                  # Docker 构建文件
├── requirements.txt            # Python 依赖
├── start_local.sh              # 本地一键启动脚本
├── .env.example                # 环境变量参考
└── README.md                   # 本文件
```
