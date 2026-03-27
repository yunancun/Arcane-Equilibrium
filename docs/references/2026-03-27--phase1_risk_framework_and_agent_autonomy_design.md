# Phase 1 完整设计文档：全品类风控框架 + Agent 自主交易 + AI 注意力税 + 对抗性止损
# Phase 1 Full Design: All-Category Risk Framework + Agent Autonomous Trading + AI Attention Tax + Adversarial Stop Logic

**日期：** 2026-03-27
**状态：** 设计完成，待编码
**前置文档：** `2026-03-27--local_trading_logic_audit_and_strategy_plan.md`（审查报告）

---

## 一、设计动机

### 审查发现的问题
1. 本地层零交易策略 — H0 只做门控，不产生信号
2. Paper Engine 只支持 market/limit 两种订单 — Bybit V5 支持 10+ 种
3. 无止损止盈 — 单笔亏损无上限
4. edge_threshold (5bps) < 成本底线 (21bps) — 系统在亏本基础上交易
5. 无 max drawdown 熔断

### 用户需求
- Agent 拥有充分自主权：自主选择交易品种、策略、参数、时机
- 用户只在 global 层面设置止盈止损等上限
- 风控必须覆盖 Bybit V5 API 支持的全部交易品类
- 需要对抗高频做市商和 AI 交易机器人的止损猎杀
- 持仓成本需包含 AI 注意力消耗

---

## 二、Bybit V5 全量交易能力（Agent 操作空间）

### 6 大产品品类

| 品类 | API category | 杠杆 | Funding | 到期 | 爆仓 | 风控特殊性 |
|------|-------------|------|---------|------|------|-----------|
| Spot 现货 | spot | 无 | 无 | 无 | 无 | 最安全，亏损有限于本金 |
| Spot Margin 现货保证金 | spot | 有 | 无 | 无 | 有 | 有借贷利息 |
| Linear Perpetual USDT/USDC 永续 | linear | 1-125x | 每 8h | 无 | 有 | 主战场，流动性最好 |
| Inverse Perpetual 反向永续 | inverse | 有 | 每 8h | 无 | 有 | 以币结算，币价波动双重风险 |
| Linear/Inverse Futures 期货 | linear/inverse | 有 | 无 | 有 | 有 | 到期日前需平仓或滚动 |
| Options 期权 | option | N/A | 无 | 有 | N/A | 买方亏损有限，卖方风险无限 |

### 10+ 种订单类型

| 订单类型 | Bybit API | 说明 |
|----------|-----------|------|
| Market | orderType=Market | 市价即时成交 |
| Limit | orderType=Limit | 限价挂单 |
| Conditional/Stop | triggerPrice + orderType | 价格触发后执行 |
| TP/SL (order-level) | takeProfit/stopLoss params | 订单附带止盈止损 |
| TP/SL (position-level) | /v5/position/trading-stop | 持仓级别止盈止损 |
| Trailing Stop | trailingStop param | 动态跟踪止损 |
| Reduce Only | reduceOnly=true | 只减仓不加仓 |
| Post Only | timeInForce=PostOnly | 保证 maker fee |
| Iceberg | 拆单执行 | 隐藏大单意图 |
| TWAP | 时间加权 | 均匀分布执行 |
| Batch | /v5/order/batch-create | 1-10 单批量 |

### Time In Force
- GTC (Good-Till-Cancelled)
- IOC (Immediate-or-Cancel)
- FOK (Fill-or-Kill)
- PostOnly (保证不吃单)

### 保证金模式
- Cross（共享全账户余额）
- Isolated（每仓独立）
- Portfolio（组合保证金）

### 持仓模式
- One-way（单向）
- Hedge（双向对冲）

---

## 三、三层优先级风控架构

### 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│  Priority 0 — 品类专属风控 (Category-Specific)                │
│  用户按品类单独设置，覆盖 P1 默认值（只能更严格）               │
│  例：options max_position=5%，linear max_leverage=10x          │
├──────────────────────────────────────────────────────────────┤
│  Priority 1 — 全局风控 (Global)                               │
│  用户设置的全局上限，适用于所有品类（除非被 P0 覆盖）            │
│  例：max_drawdown=15%，max_single_position=10%                 │
├──────────────────────────────────────────────────────────────┤
│  Priority 2 — Agent 自适应风控 (Agent Adaptive)                │
│  Agent 在 P0/P1 有效上限内自主调整                              │
│  例：Agent 认为高波动 → 收紧 stop_loss 到 1.5%                 │
└──────────────────────────────────────────────────────────────┘
```

### 合并规则

```
effective_cap = min(P0_value ?? P1_value, P1_value)
  → P0 只能比 P1 更严格，不能更宽松

effective_value = min(P2_agent_value, effective_cap)
  → Agent 只能在 effective_cap 内收紧
```

### P1 GlobalRiskConfig（用户全局上限）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| max_stop_loss_pct | 5.0% | 单仓最大止损 |
| max_take_profit_pct | 20.0% | 单仓最大止盈 |
| max_single_position_pct | 10.0% | 单仓占余额上限 |
| max_total_exposure_pct | 50.0% | 总敞口占余额上限 |
| max_correlated_exposure_pct | 30.0% | 同方向最大敞口 |
| max_leverage | 20.0x | 全局最大杠杆 |
| max_session_drawdown_pct | 15.0% | session 回撤熔断 |
| max_daily_loss_pct | 5.0% | 日内最大亏损 |
| consecutive_loss_cooldown_count | 3 | 连亏触发冷却 |
| consecutive_loss_cooldown_minutes | 30 | 冷却时长 |
| max_holding_hours | 72.0h | 最大持仓时间 |
| allowed_categories | spot,linear,inverse | 允许的品类白名单 |
| preferred_margin_mode | isolated | 保证金模式偏好 |
| preferred_position_mode | one_way | 持仓模式偏好 |
| max_cost_edge_ratio | 0.8 | 持仓成本/预期边际 比率上限 |

### P0 CategoryRiskConfig（品类专属）

每个品类可独立设置的覆盖参数 + 品类特有参数：

| 品类 | 特有参数 |
|------|---------|
| Spot | spot_allow_margin (默认 false) |
| Linear/Inverse Perp | perp_max_funding_rate_abs (0.03%), perp_auto_deleverage_threshold (0.8) |
| Options | option_max_premium_pct (5%), option_max_delta_exposure (0.5), option_allowed_strategies (默认不允许裸卖) |

### P2 AgentRiskParams（Agent 自适应）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| effective_stop_loss_pct | 2.0% | 实际止损（在 cap 内） |
| effective_take_profit_pct | 4.0% | 实际止盈 |
| trailing_stop_enabled | false | 追踪止损开关 |
| trailing_stop_activation_pct | 1.0% | 盈利达此才激活 |
| trailing_stop_distance_pct | 0.8% | 回撤距离 |
| position_size_multiplier | 1.0 | 仓位乘数 0.1-1.0 |
| category_preference_weights | {spot:0.3, linear:0.5, inverse:0.2} | 品类偏好 |
| prefer_limit_over_market | true | 优先限价单 |
| use_reduce_only_for_close | true | 平仓用 reduce_only |

---

## 四、AI 注意力税（AI Attention Tax）

### 核心概念

每个持仓都在无声消耗 AI 预算。持仓的真实成本 = 金融成本 + AI 注意力成本。

```
金融成本（可精确计算）：
  开仓手续费 + 预估平仓手续费 + 滑点 + Funding Rate + 保证金机会成本

AI 注意力成本（草算）：
  持仓存在一天 → AI 多监控一天 → 消耗预算
  波动越大 → 监控频率越高 → AI 成本越高
  接近 SL/TP → 注意力升级 → AI 成本飙升
  触发 L2 深度分析 → $0.50-$4.00 一次
```

### 注意力税率表（草算 bounds）

| 注意力等级 | tick 间隔 | 估算 AI 成本/小时 | 场景 |
|-----------|----------|------------------|------|
| dormant | 60s | $0.000 | 无仓位 |
| low | 10s | $0.003 | 有仓但安全 |
| medium | 3s | $0.010 | 有持仓 |
| high | 500ms | $0.050 | 接近触发 |
| critical | 实时 | $0.100 | 高波动 |

### AI 成本归因

- **直接归因：** L2 session 分析特定 symbol → 成本归到该 position
- **按比例归因：** L1 triage / 通用监控 → 按仓位名义价值比例分摊
- **固定开销：** 系统级 AI 成本 → 均摊到所有 open positions

### 持仓成本追踪

每个 position 新增：
```json
{
  "holding_cost": {
    "financial_cost_usd": 0.0,
    "ai_cost_attributed_usd": 0.0,
    "total_holding_cost_usd": 0.0,
    "estimated_remaining_edge_usd": 0.0,
    "cost_edge_ratio": 0.0,
    "cost_efficiency_grade": "A",
    "hourly_ai_burn_rate_usd": 0.003,
    "projected_break_even_hours": null
  }
}
```

### 效率等级

| 等级 | cost_edge_ratio | 含义 |
|------|----------------|------|
| A | < 0.2 | 成本可忽略 |
| B | < 0.4 | 健康 |
| C | < 0.6 | 需要关注 |
| D | < 0.8 | 建议减仓或平仓 |
| F | ≥ 0.8 | 持有已不划算，应平仓 |

### 自然衰减压力

```
position_remaining_edge = initial_expected_edge - accumulated_total_cost

当 remaining_edge ≤ 0 → 持有本身在亏钱 → 系统建议平仓
```

效果：
- 赚钱的仓位也有"保质期"
- Agent 自然偏好低维护策略（Grid、Funding Rate 套利）
- AI 预算紧张时仓位自然收缩

### 开仓前成本预估

```
预估 AI 成本 = 预估持仓时间 × 每小时 AI 税率
预估总成本 = 预估 AI 成本 + 预估金融成本
预估净边际 = 预估边际 - 预估总成本

如果 预估净边际 ≤ 0 → 不开仓（"养不起 AI"）
```

---

## 五、对抗性止损逻辑（Adversarial Stop Logic）

### 市场对手

1. **高频做市商 (HFT Market Makers)：** 微秒级执行，看得到 order book 上的止损单
2. **量化基金 AI Bot：** ML 模型预测散户止损位置
3. **止损猎杀策略：** 推价格刺穿止损区 → 触发连锁清算 → 反向获利

### 软止损 + 硬止损范式

```
┌─────────────────────────────────────────────┐
│  硬止损 Hard Stop（P1 全局上限，绝对防线）     │
│  ─ 价格到了就关，零讨论                       │
│  ─ 永远不放在交易所 order book 上              │
│  ─ 本地 tick() 检查触发，市价平仓              │
│  ─ 占止损触发的 ~20%                          │
├─────────────────────────────────────────────┤
│  软止损 Soft Stop（Agent 评估后决定）          │
│  ─ 价格进入止损区域 → Agent L1 快速评估：      │
│    · 渐进下跌 vs 瞬间刺穿？                   │
│    · Order book 深度正常 vs 异常薄？            │
│    · 相关资产同步异动 vs 孤立异动？             │
│    · 是否在高猎杀概率时段？                    │
│  ─ Agent 决定：平仓 / 持有 / 收紧 / 放宽      │
│  ─ 占止损触发的 ~80%                          │
│  ─ 止损对外界完全不可见                        │
└─────────────────────────────────────────────┘
```

### 具体反猎杀措施

**1. 止损价格反预测**
- 避免：整数位、标准百分比（-2.00%）、明显支撑阻力
- 采用：ATR 基础 + 随机偏移（±0.1-0.3%）+ 非整数
- 例：不是 -2.0% 而是 -2.17%（1.5×ATR + random offset）

**2. 止损隐身（Stealth Stops）**
- 永远不在交易所下 stop order
- 本地 tick() 监控，触发时发市价单
- 对做市商来说我们的止损不存在

**3. 假突破识别**
- 突然尖刺 + 极薄 order book = 疑似猎杀
- 多品种同步异动 = 真实行情
- 单品种孤立异动 = 疑似操纵
- 疑似猎杀 → soft stop 不触发，hard stop 仍生效

**4. 流动性感知平仓**
- 深度充足 → 市价平仓
- 深度不足 → 限价 + TWAP 拆分
- 避免在最差流动性时被迫最差价格平仓

**5. 时间感知**
- 高猎杀概率时段（session 交接、周日晚）→ soft stop 阈值放宽
- Hard stop 永远不变

**6. 对抗性仓位管理**
- 入场不用标准仓位大小，用 ATR 调整
- 分批入场/出场
- 大单用 iceberg/TWAP
- 变化持仓时间避免模式被预测

### 我们的结构性优势

| HFT Bot | 我们的 Agent |
|---------|-------------|
| 快但不聪明（规则驱动） | 慢但能推理（AI 驱动） |
| 看到 -2% → 猎杀 -2% 止损 | 看到 -2% → 分析为什么 → 决定跑还是留 |
| 止损在 order book 上可见 | 止损本地隐形 |
| 固定止损位可预测 | 动态止损 + 随机偏移不可预测 |

---

## 六、Agent 自主性框架

### Agent 可以自主决定的事

| 领域 | Agent 自主范围 | 硬约束 |
|------|--------------|--------|
| **交易什么** | 任何 allowed_categories 内的品种 | 品类白名单由用户控制 |
| **用哪种策略** | Funding Rate / Bollinger / Grid / AI-driven | 自由选择和组合 |
| **何时开仓** | 自主判断时机和数据充分性 | 必须通过 pre-order risk check |
| **何时平仓** | 主动平仓 + 止损止盈 | 硬止损不可突破 |
| **仓位大小** | 在 max_single_position_pct 内自由调整 | P0/P1 上限 |
| **杠杆倍数** | 在 max_leverage 内自由选择 | P0/P1 上限 |
| **订单类型** | 市价/限价/条件/TP_SL/追踪/冰山/TWAP | 全部可用 |
| **风控参数** | 在 P0/P1 内自由调整止损止盈追踪等 | 只能收紧不能放宽 |
| **品类偏好** | 动态分配各品类仓位权重 | 总敞口受限 |
| **策略启停** | 判断数据是否充分，自主启停策略 | 无，完全自主 |

### Agent 不能做的事（硬约束）
- 不能突破用户 P1 全局上限
- 不能自行开启用户未允许的品类
- 不能关闭硬止损
- 不能修改 system_mode / execution_authority
- 不能突破 daily AI hard cap
- 不能在 session_halted 状态下继续交易（需人工解除）

---

## 七、实施概览

### 新增文件
| 文件 | 行数估算 | 职责 |
|------|---------|------|
| `app/risk_manager.py` | ~600 | 三层风控 + 对抗性止损 + AI attention tax |
| `app/risk_routes.py` | ~250 | 8 条 API 路由 |
| `tests/test_risk_manager.py` | ~500 | ~50 个测试用例 |

### 修改文件
| 文件 | 改动 |
|------|------|
| `app/paper_trading_engine.py` | S1-S3,S5 修复 + 订单类型扩展 + 接入 risk_manager |
| `app/shadow_decision_builder.py` | S4 edge 5→25bps + S5 |
| `app/paper_trading_routes.py` | S5 + 实例化 RiskManager |
| `app/market_data_dispatcher.py` | S5 |
| `app/main.py` | 注册 risk_router |

### 路由变更
系统总路由 84 → 92（新增 8 条 `/api/v1/paper/risk/*`）

### 安全不变量
```
system_mode=read_only, execution_state=disabled, execution_authority=not_granted — 不变
is_simulated=True — 所有交易
P0 只能比 P1 更严格 — 架构保证
Agent P2 只能在 effective_cap 内收紧 — 架构保证
硬止损不可突破 — 用户全局上限
allowed_categories — 用户白名单
options 裸卖 — 默认禁止
daily AI hard cap $15 — 不可突破
```
