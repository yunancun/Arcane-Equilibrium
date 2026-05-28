# Paper Trading Engine 完整工程日志
# Paper Trading Engine — Full Engineering Log

日期：2026-03-26
阶段：模拟交易系统 Phase 2 + Phase 4（引擎核心 + GUI 集成）
状态：**MVP 完成，139 测试全通过**

---

## 一、背景与目标 / Context & Goal

L 章全部完成（自动学习管线 + 安全加固，96 测试通过）后，用户决定：**先搭建完整的模拟交易系统进入 beta 运行，用实际产生的数据精修后再开始 M 章（Supervised Live Gate）**。

系统约束不变：`system_mode = read_only`，`execution_state = disabled`，`execution_authority = not_granted`。Paper trading 系统在此约束内运行，仅使用内部 paper state，**绝不发送真实订单到 Bybit**。

---

## 二、架构决策 / Architecture Decisions

### 独立模块模式

`main_legacy.py` 已有 4600+ 行，不再继续扩展。Paper trading engine 作为独立模块：

```
app/paper_trading_engine.py    ← 核心引擎（~500 行）
app/paper_trading_routes.py    ← API 路由（~280 行）
app/main.py                    ← 注册 paper_router（新增 3 行）
```

### Paper State 隔离

- 使用 `OPENCLAW_PAPER_STATE_FILE` 环境变量指向独立 JSON 文件
- 复用 `JsonStateStore` 模式但完全隔离于主控制状态
- 文件权限 `0o600`（仅 owner 可读写）

### 基于 K 章骨架设计

纸上交易引擎直接实现了 K 章定义的：
- **7 状态生命周期**（paper_order_created → submitted → working → partially_filled → filled/canceled/rejected）
- **8 条状态转换边**（完全遵循 K 章 `state_edges` 定义）
- **5 个投影函数**（project_position_after_fill, project_balance_after_fill, project_fee_and_cash_impact, update_unrealized_pnl, reconcile — 前 4 个已实现，第 5 个预留）
- **6 个适配器接口**（submit, cancel, sync_positions, sync_balance, risk_check, audit_trail — 全部实现）

---

## 三、新建文件清单 / New Files

### 3.1 `app/paper_trading_engine.py`（~500 行）

**核心引擎，包含：**

| 组件 | 说明 |
|------|------|
| `PaperStateStore` | 独立状态存储，隔离于主状态文件 |
| `build_default_paper_state()` | 默认状态 schema（session + orders + positions + fills + pnl + audit） |
| `create_paper_order()` | 订单创建（验证 symbol/side/type/qty/price） |
| `_transition_order()` | 状态机转换（严格验证合法转换路径） |
| `compute_fill_price()` | 成交价计算（market: 含滑点；limit: 限价成交） |
| `compute_fee()` | 手续费计算（taker 0.055% / maker 0.02%，Bybit 永续线性默认值） |
| `should_fill_limit_order()` | 限价单成交判断（buy: price ≤ limit; sell: price ≥ limit） |
| `execute_fill()` | 成交执行（更新 filled_qty/remaining_qty/avg_fill_price/state） |
| `project_position_after_fill()` | 持仓投影（新开/加仓/减仓/平仓/翻转） |
| `project_balance_after_fill()` | 余额投影（扣除手续费） |
| `update_unrealized_pnl()` | 未实现盈亏更新 |
| `PaperTradingEngine` | 顶层管理器（session 管理 + 订单管理 + tick 模拟 + PnL 计算 + 导出） |

**中英双语注释覆盖：** MODULE_NOTE 双语、所有 section header 双语、所有函数 docstring 双语、常量注释双语。

### 3.2 `app/paper_trading_routes.py`（~280 行）

**14 条 API 路由：**

| Method | Route | 说明 |
|--------|-------|------|
| POST | `/api/v1/paper/session/start` | 开始纸上交易 session |
| POST | `/api/v1/paper/session/pause` | 暂停 session |
| POST | `/api/v1/paper/session/resume` | 恢复 session |
| POST | `/api/v1/paper/session/stop` | 结束 session，结算 PnL |
| GET | `/api/v1/paper/session/status` | 获取 session 状态 |
| POST | `/api/v1/paper/order/submit` | 提交纸上订单 |
| POST | `/api/v1/paper/order/cancel` | 取消 working 订单 |
| GET | `/api/v1/paper/orders` | 订单列表（可按状态过滤） |
| GET | `/api/v1/paper/positions` | 当前纸上持仓 |
| GET | `/api/v1/paper/fills` | 成交历史 |
| GET | `/api/v1/paper/pnl` | Paper PnL 汇总 |
| POST | `/api/v1/paper/tick` | 手动触发成交模拟 tick |
| GET | `/api/v1/paper/audit-trail` | 审计记录 |
| GET | `/api/v1/paper/export` | 完整 session 数据导出 |

### 3.3 `tests/test_paper_trading.py`（43 个测试）

| 测试类 | 测试数 | 覆盖范围 |
|--------|--------|----------|
| `TestPaperStateStore` | 2 | 状态存储创建和隔离 |
| `TestSessionLifecycle` | 7 | Session 状态机完整路径 |
| `TestOrderLifecycle` | 10 | 7 状态 8 条边全覆盖 + 安全标记 |
| `TestPositionProjection` | 7 | 开仓/加仓/减仓/平仓/翻转/未实现盈亏/余额扣费 |
| `TestPnLComputation` | 3 | 手续费追踪/净值计算/盈利往返 |
| `TestAuditTrail` | 2 | Session 和订单审计记录 |
| `TestDataExport` | 1 | 导出字段完整性 |
| `TestPaperTradingAPI` | 11 | 全部 API 路由集成测试 + 认证 |

---

## 四、修改文件清单 / Modified Files

| 文件 | 修改内容 |
|------|----------|
| `app/main.py` | 新增 3 行：import paper_router + include_router |
| `app/main_legacy.py` | 新增 2 个 auth scope：`paper:read`、`paper:trade` |
| `app/static/index.html` | 新增 Paper Trading GUI 区块（~50 行 HTML） |
| `app/static/app.js` | 新增 Paper Trading GUI 函数（~150 行 JS）+ loadDashboard 集成 |
| `app/static/styles.css` | 新增 Paper Trading 样式（~100 行 CSS，蓝色边框视觉风格） |

---

## 五、GUI Paper Trading 界面 / GUI Paper Trading Dashboard

### 界面组成

1. **警告横幅** — "所有数据均为模拟，不影响真实账户" — 蓝色底，始终可见
2. **Session 控制按钮** — Start / Pause / Resume / Stop（根据 session 状态自动 enable/disable）
3. **Session 状态徽章** — 未启动 / 运行中 / 已暂停 / 已结束
4. **Paper PnL 卡片** — 已实现 / 未实现 / 手续费 / 净值（绿色正值 / 红色负值）
5. **持仓表格** — symbol / side / qty / entry_price / unrealized_pnl
6. **订单提交表单** — Symbol / Side / Type / Qty / Price + Submit 按钮
7. **订单列表** — 最近 20 条，按状态着色（蓝=working, 绿=filled, 灰=canceled）
8. **成交历史**（折叠） — symbol / side / qty @ price / fee
9. **审计记录**（折叠） — JSON 格式

### 视觉设计

- Paper Trading 区块使用**蓝色左边框**（`border-left: 4px solid #3b82f6`），与主控制台区块区分
- PnL 正值绿色 `#10b981`，负值红色 `#ef4444`
- Session 按钮颜色区分：Start 蓝、Pause 黄、Resume 绿、Stop 红
- 响应式：移动端时 PnL/持仓 两栏变单栏

---

## 六、安全保证 / Safety Guarantees

| 保证项 | 实现方式 |
|--------|----------|
| Paper state 隔离 | 独立 JSON 文件，独立 `PaperStateStore` 实例 |
| 模拟标记 | 所有响应携带 `is_simulated: true` + `data_category: "paper_simulated"` |
| 不碰真实 API | `paper_trading_engine.py` 不 import 任何 Bybit API client |
| 系统状态不变 | `system_mode` / `execution_state` / `execution_authority` 全程不变 |
| 认证保护 | 所有路由需要 Bearer Token 认证 |
| 文件权限 | Paper state 文件 `chmod 0o600` |

---

## 七、测试结果 / Test Results

```
139 passed in 7.33s

原有测试：96 个全部通过（零回归）
新增测试：43 个全部通过

路由总数：46（主系统）+ 14（纸上交易）= 60 条
```

---

## 八、成交模拟规则 / Fill Simulation Rules

| 订单类型 | 成交规则 | 手续费 |
|----------|----------|--------|
| Market order | 立即以 `lastPrice * (1 ± slippage)` 成交 | Taker: 0.055% |
| Limit buy | 当 `lastPrice ≤ limit_price` 时成交 | Maker: 0.02% |
| Limit sell | 当 `lastPrice ≥ limit_price` 时成交 | Maker: 0.02% |
| 默认滑点 | 0.05%（可配置） | — |

---

## 九、PnL 计算逻辑 / PnL Computation

```
realized_pnl = 已平仓盈亏（含部分平仓、完全平仓、翻转平仓）
unrealized_pnl = 当前持仓的未实现盈亏（按最新市场价计算）
total_fees_paid = 所有成交的手续费累计
net_paper_pnl = realized_pnl + unrealized_pnl - total_fees_paid - total_ai_cost

current_balance = initial_balance + realized_pnl - total_fees_paid
```

---

## 十、后续可推进方向 / Next Steps

| 阶段 | 内容 | 依赖 |
|------|------|------|
| Phase 1 | 真实数据接入（observer → runtime snapshot 自动桥接，Bybit PnL → Net PnL 自动计算） | observer pipeline |
| Phase 3 | 影子决策管线（H chain AI 咨询 → shadow decision → paper order） | H1-H5 chain |
| Phase 5 | Beta 就绪（performance metrics, market comparison, data export for M 章分析） | Phase 2+3 |

---

## 十一、文件路径汇总 / File Path Summary

```
program_code/exchange_connectors/bybit_connector/control_api_v1/
├── app/
│   ├── main.py                    ← 注册 paper_router（已修改）
│   ├── main_legacy.py             ← 新增 paper scopes（已修改）
│   ├── paper_trading_engine.py    ← NEW: 核心引擎（~500 行）
│   ├── paper_trading_routes.py    ← NEW: 14 条 API 路由（~280 行）
│   └── static/
│       ├── index.html             ← 新增 Paper Trading 区块（已修改）
│       ├── app.js                 ← 新增 Paper Trading 交互（已修改）
│       └── styles.css             ← 新增 Paper Trading 样式（已修改）
└── tests/
    └── test_paper_trading.py      ← NEW: 43 个测试（~430 行）
```
