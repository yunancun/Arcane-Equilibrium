# Phase 1 风控框架实现工程日志
# Phase 1 Risk Framework Implementation Engineering Log

**日期：** 2026-03-27
**工作范围：** 安全修复 S1-S5 + 三层优先级风控框架 + 对抗性止损 + AI 注意力税基础 + 8 条新路由
**结果：** 369 测试全通过（327 旧 + 42 新），路由 84 → 92

---

## 一、工作背景

本轮工作起源于对本地交易逻辑的全面审查（同日完成），发现 5 个安全问题和本地层零交易策略覆盖。用户进一步提出三个关键需求：
1. Agent 需要充分自主权（用户只设全局上限，Agent 自主交易）
2. 风控必须覆盖 Bybit V5 API 全部 6 大品类 + 10+ 种订单类型
3. 止损逻辑需要考虑对抗高频做市商和 AI 交易机器人的猎杀

在此基础上又追加了两个概念：
4. AI 注意力税：持仓真实成本 = 金融成本 + AI 监控成本
5. 对抗性止损：软止损（Agent 评估）+ 硬止损（绝对防线）+ 止损隐身

---

## 二、实施过程（7 步）

### Step 1: S4 + S5 安全修复

**S4: edge_threshold 从 5 提升到 25 bps**
- 文件：`app/shadow_decision_builder.py:73`
- 原因：往返成本底线约 21 bps（taker 5.5×2 + slippage 5×2），旧阈值 5 bps 意味着系统在亏本基础上交易
- 影响：7 个 shadow decision 测试因 edge 值低于新阈值而失败
- 修复：测试中 `_make_governed_observation` 默认 edge 从 15→30，显式 edge 从 20→30

**S5: get_state() 公共方法**
- 文件：`app/paper_trading_engine.py` — 新增 `get_state()` 方法
- 原因：4 个外部模块直接访问 `_read()` 私有方法，耦合过紧
- 修改 4 处：`shadow_decision_builder.py` / `paper_trading_routes.py`(2处) / `market_data_dispatcher.py`
- 内部 `self._read()` 保持不变（仅影响外部调用）

**验证：** 327 测试全通过

### Step 2: S1 margin check + S3 peak balance tracking

**S1: margin check 修复**
- 文件：`app/paper_trading_engine.py:639-651`
- 旧逻辑：`balance < estimated_fee`（几乎永远 False，fee 极小）
- 新逻辑：`balance < required_margin + estimated_fee`（检查 notional/leverage + 手续费）
- `required_margin = notional / leverage`（变量原本已存在但未使用）
- reject_reason 从 `insufficient_balance` 改为 `insufficient_margin`

**S3: peak balance + session halt**
- `build_default_paper_state()` 新增 3 个字段：
  - `peak_balance_usdt`：峰值余额（用于回撤计算）
  - `session_halted`：session 是否被熔断
  - `session_halt_reason`：熔断原因
- `_recompute_pnl()` 末尾新增 peak balance 跟踪逻辑
- `submit_order()` mutator 内新增 `session_halted` 检查，熔断时拒绝下单

**测试适配：** `test_reject_insufficient_balance` → `test_reject_insufficient_margin`

**验证：** 327 测试全通过

### Step 3: S2 限价单部分成交模拟

**新增函数：** `compute_partial_fill_qty(order, market_price, rng=None)`
- 深穿越（>0.5%）→ 100% 成交
- 中等穿越（0.1-0.5%）→ 50-100% 随机
- 浅穿越（<0.1%）→ 30-70% 随机
- 最小成交量 = remaining × 10%（避免 dust）
- `rng` 参数：可传入 `random.Random(seed)` 用于测试确定性

**集成：** `tick()` 中 `fill_qty = order["remaining_qty"]` → `fill_qty = compute_partial_fill_qty(order, mp, rng=self._partial_fill_rng)`

**`PaperTradingEngine.__init__` 新增：** `partial_fill_rng` 可选参数

**测试适配：** `test_limit_order_filled_via_dispatch` 改用深穿越价格（86500 × 0.994 ≈ 86000）保证全量成交

**已有限价单测试天然深穿越（2%+），无需修改**

**验证：** 327 测试全通过

### Step 4-5: risk_manager.py（核心风控模块）

**新建文件：** `app/risk_manager.py`（~455 行）

**三层配置数据结构：**

| 层 | 类 | 职责 |
|---|---|---|
| P1 | `GlobalRiskConfig` | 用户全局上限（15 个参数） |
| P0 | `CategoryRiskConfig` | 品类专属覆盖（通用 + spot/perp/option 特有参数） |
| P2 | `AgentRiskParams` | Agent 可调参数（10 个参数） |

**合并函数：** `resolve_effective_limit(param_name, global, category)` → `min(P0 ?? P1, P1)`

**RiskManager 类核心方法：**

| 方法 | 职责 |
|------|------|
| `check_order_allowed()` | 下单前检查：session halt / cooldown / 品类白名单 / 杠杆 / 仓位大小 / 总敞口 / 相关性敞口 |
| `check_positions_on_tick()` | tick 时检查：硬止损 / 软止损 / 止盈 / 追踪止损 / 持仓超时 / session 回撤 |
| `agent_adjust()` | Agent 调参（clamp 到有效上限） |
| `record_fill_result()` | 连续亏损计数 + 冷却触发 |
| `get_risk_state_for_persistence()` / `load_risk_state()` | 持久化/恢复 |

**追踪止损 Bug 修复（实现过程中发现并修复）：**
- Bug 1：首次进入激活区时 peak 未初始化（`pnl > peak` 对 `pnl == peak` 为 False）
- Bug 2：价格回落到激活阈值以下时追踪止损检查被跳过
- 修复：分离"初始化"和"检查"逻辑，一旦激活则始终检查

**集成到 PaperTradingEngine：**
- `__init__` 新增 `risk_manager` 可选参数
- `submit_order()` mutator 内：在 margin check 之前调用 `check_order_allowed()`
- `tick()` mutator 内：在 unrealized PnL 更新后调用 `check_positions_on_tick()` → 自动生成平仓单 → 更新 PnL → 检查 session 回撤熔断 → 持久化 risk state

### Step 6: risk_routes.py + 路由注册

**新建文件：** `app/risk_routes.py`（~230 行）

**8 条新路由（prefix `/api/v1/paper/risk/`）：**

| 方法 | 路由 | 功能 |
|------|------|------|
| GET | `/config` | 全量风控配置（三层合并后） |
| POST | `/config/global` | 更新 P1 全局配置 |
| GET | `/config/category/{cat}` | 获取 P0 品类配置 |
| POST | `/config/category/{cat}` | 更新 P0 品类配置 |
| GET | `/status` | 风控状态（冷却/追踪止损/回撤/熔断） |
| POST | `/agent-adjust` | Agent 调 P2 参数 |
| POST | `/reset-cooldown` | 手动清冷却 |
| POST | `/unhalt-session` | 手动解熔断 |

**Pydantic 请求模型：** `GlobalConfigUpdate` / `CategoryConfigUpdate` / `AgentAdjustRequest`

**路由注册：** `app/main.py` 新增 2 行

**paper_trading_routes.py 修改：**
- 新增 `RISK_MANAGER = RiskManager()` 实例化
- `ENGINE = PaperTradingEngine(PAPER_STORE, risk_manager=RISK_MANAGER)`

### Step 7: 全量测试

**新建文件：** `tests/test_risk_manager.py`（~350 行，42 个测试用例）

**测试覆盖：**

| 类 | 测试数 | 覆盖内容 |
|---|--------|---------|
| TestGlobalRiskConfig | 3 | 默认值 / 序列化往返 / 忽略未知字段 |
| TestCategoryRiskConfig | 2 | 默认值 / 序列化往返 |
| TestAgentRiskParams | 2 | 默认值 / 序列化往返 |
| TestResolveEffectiveLimit | 4 | 仅全局 / P0 更严 / P0 更松被 clamp / P0 为 None |
| TestAgentAdjust | 4 | 收紧止损 / 不可超上限 / multiplier clamp / 追踪止损开关 |
| TestPreOrderChecks | 6 | 允许 / 品类禁止 / 杠杆超限 / 仓位超限 / session 熔断 / 冷却中 |
| TestTickChecks | 5 | 止损触发 / 止盈触发 / 限内不触发 / 追踪止损 / 回撤熔断 |
| TestConsecutiveLossCooldown | 3 | 连亏触发 / 盈利重置 / 手动重置 |
| TestPersistence | 1 | 全状态序列化往返 |
| TestCostEfficiencyGrade | 1 | A-F 等级映射 |
| TestRiskIntegration | 3 | 风控拒单 / 风控放行 / tick 自动平仓 |
| TestRiskRoutes | 8 | 全部 8 条路由 |

**全量回归结果：** 369 测试全通过（327 旧 + 42 新），0 失败

---

## 三、文件变更清单

### 新建文件（3 个）
| 文件 | 行数 | 职责 |
|------|------|------|
| `app/risk_manager.py` | ~455 | 三层风控框架核心 |
| `app/risk_routes.py` | ~230 | 8 条风控 API 路由 |
| `tests/test_risk_manager.py` | ~350 | 42 个风控测试 |

### 修改文件（8 个）
| 文件 | 改动摘要 |
|------|---------|
| `app/paper_trading_engine.py` | S1 margin / S2 partial fill / S3 peak+halt / S5 get_state() / risk_manager 集成 |
| `app/shadow_decision_builder.py` | S4 edge 5→25bps / S5 get_state() |
| `app/paper_trading_routes.py` | S5 get_state() / RISK_MANAGER 实例化 |
| `app/market_data_dispatcher.py` | S5 get_state() |
| `app/main.py` | 注册 risk_router（+2 行） |
| `tests/test_shadow_decision.py` | edge 值适配新阈值 |
| `tests/test_paper_trading.py` | insufficient_balance→insufficient_margin |
| `tests/test_market_data.py` | limit fill 用深穿越价格 |

---

## 四、数量变化

| 指标 | 变更前 | 变更后 | 变化 |
|------|--------|--------|------|
| 测试用例 | 327 | 369 | +42 |
| API 路由 | 84 | 92 | +8 |
| 安全问题 | S1-S5 | 全部修复 | -5 |

---

## 五、实现过程中发现并修复的 Bug

| Bug | 位置 | 原因 | 修复 |
|-----|------|------|------|
| 追踪止损 peak 未初始化 | `risk_manager.py` | `pnl > peak` 对 `pnl == peak` 为 False | 分离初始化和检查逻辑 |
| 追踪止损激活区外跳过检查 | `risk_manager.py` | 价格回落到 activation_pct 以下时追踪止损被整体跳过 | 一旦 peak 已设置则始终检查 |

---

## 六、安全不变量确认

```
system_mode             = read_only       ✅ 不变
execution_state         = disabled        ✅ 不变
execution_authority     = not_granted     ✅ 不变
is_simulated            = true            ✅ 所有订单
P0 只能比 P1 更严格                        ✅ resolve_effective_limit 保证
Agent P2 只能在 effective cap 内收紧       ✅ agent_adjust clamp 保证
硬止损不可突破                             ✅ 始终在 soft stop 之前检查
session 熔断需人工解除                     ✅ unhalt-session 路由
```

---

## 七、后续待完成

本轮完成了风控框架的核心实现，以下是设计文档中已规划但本轮未编码的部分：

1. **Paper Engine 订单类型扩展** — conditional / TP-SL / trailing stop / reduce_only / PostOnly / iceberg / TWAP 订单类型（当前仍为 market + limit）
2. **AI 注意力税完整集成** — 持仓成本追踪结构已定义（`holding_cost` 字段），尚未写入 position 和 tick 流程
3. **对抗性止损完整集成** — 假突破识别 / 流动性感知平仓 / 时间感知（当前软止损逻辑为直接比较，未接入 L1 评估）
4. **本地策略补齐（Phase 2）** — 技术指标引擎 / Funding Rate / Bollinger / Grid / Strategy Orchestrator
5. **GUI 风控面板** — Risk Control 仪表盘（三层配置可视化 + 风控状态实时展示）

**设计文档：** `docs/references/2026-03-27--phase1_risk_framework_and_agent_autonomy_design.md`
**审查报告：** `docs/references/2026-03-27--local_trading_logic_audit_and_strategy_plan.md`
