# 本地交易逻辑审查报告与策略补齐计划
# Local Trading Logic Audit Report & Strategy Enhancement Plan

**日期：** 2026-03-27
**状态：** 审查完成，计划待实施
**审查范围：** H0 链（5 模块）+ Paper Trading Engine + Shadow Decision Builder + Layer 2 Engine + H2 Trigger Model

---

## 一、安全性审查

### 结论：安全，有改进空间

**安全优点：**
- H0 链全程 fail-closed，任何输入缺失/不一致都会 block
- Paper Trading Engine 完全不 import Bybit API 客户端
- 所有数据标记 `is_simulated=True` + `lease_mode=shadow_only`
- `execution_authority=not_granted` 作为硬不变量
- Kill switch + cooldown + position/order count 限制全覆盖
- 状态文件每次写入后 `chmod 0o600`
- PaperStateStore 使用 `threading.RLock()` 保证并发安全

**需修复的问题：**

| # | 问题 | 位置 | 严重度 | 修复方案 |
|---|------|------|--------|----------|
| S1 | Paper engine margin check 只检查 fee 够不够，没检查 notional margin | `paper_trading_engine.py:637` | 中 | 添加 notional/leverage margin 检查 |
| S2 | Limit order 一次全量成交，无部分成交模拟 | `paper_trading_engine.py:753` | 中 | 添加基于深度的部分成交概率模拟 |
| S3 | 没有 max drawdown 自动熔断 | Paper Trading Engine 整体 | 中 | 添加 session 级别回撤熔断 |
| S4 | edge_threshold (5bps) 远低于实际成本底线 (21bps) | `shadow_decision_builder.py:73` | 高 | 提高默认门槛至成本底线以上 |
| S5 | ShadowDecisionConsumer 直接访问 engine 私有方法 `_read()` | `shadow_decision_builder.py:224` | 低 | 改用公共方法 |

---

## 二、本地覆盖审查

### 核心发现：本地层没有任何交易策略逻辑

现状：
- H0 链 = 纯门控（只判断"能不能走到 AI 审查"，不产生信号）
- H2 = 纯分诊（只判断"值不值得调 AI"，不产生信号）
- 所有交易信号 100% 来自 AI（Layer 2 或 H-chain governed observation）
- Paper Trading Engine = 纯执行（收到订单就执行，没有自己的判断）

缺失的本地能力：
- 止损/止盈/追踪止损
- 基于技术指标的本地信号（MA、RSI、Bollinger、MACD）
- Funding rate 套利检测
- 网格交易
- 仓位大小自适应（根据波动率/置信度）
- 最大回撤熔断
- 持仓时间限制

---

## 三、交易风险与盈利可能性评估

### 成本结构

```
taker 手续费：     0.055% × 2（开平）= 0.11%（11 bps）
模拟滑点：         0.05% × 2         = 0.10%（10 bps）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
单笔往返成本底线：                       0.21%（21 bps）
```

### 结构性问题
- 无止损 → 单笔亏损无上限
- 固定 2% 仓位 → 不根据信号强度/波动率调整
- 无持仓时间限制 → 占用资金无限期
- 无最大回撤熔断 → 连续亏损不会自动停止
- 无相关性检查 → 多币种同方向风险集中
- edge_threshold (5bps) < 成本底线 (21bps) → 系统在亏本基础上交易

### 盈利可能性
- 短线频繁交易：几乎不可能盈利（21bps 成本 + AI 延迟）
- 中线波段：有条件盈利（需止损止盈 + 仓位管理 + AI 方向正确率 >55%）
- 趋势跟踪：有一定空间（需 regime 识别 + 追踪止损）

---

## 四、策略补齐计划

### 设计原则

**用户角色：** 只在 global 层面设置止盈止损上限和风险包络
**Agent 角色：** 自主决定交易什么、用哪种策略、参数如何设置、数据是否充足、何时启停

### 策略 A：自动风控层（Auto Risk Control Layer）

```
优先级：最高（所有策略的基础）
风险等级：极低（纯风控）

功能：
- 每个持仓自动附加 stop_loss / take_profit / trailing_stop
- 默认值由用户 global 设置提供上限，Agent 可在上限内自主调整
- max_holding_time 超时自动平仓
- session 级别 max_drawdown 熔断
- 单币种最大敞口限制
- 多币种总敞口限制
- 连续亏损自动冷却（N 次连亏后暂停 M 分钟）

Agent 自主能力：
- 根据波动率动态收紧/放宽止损
- 根据近期胜率调整仓位大小
- 根据市场状态决定是否启用追踪止损
```

### 策略 B：Funding Rate 套利信号器

```
优先级：高
风险等级：低

功能：
- 每 8h 读取 Bybit funding rate
- 极端 funding rate → 本地产生反向信号
- 纯确定性逻辑，零 AI 成本

Agent 自主能力：
- 判断 funding rate 数据是否积累足够（至少 3 天）
- 动态调整极端阈值（根据历史分布）
- 决定何时启用/停用
```

### 策略 C：Bollinger Band 均值回归

```
优先级：中
风险等级：中低

功能：
- 本地维护 K 线数据 → 计算 BB + RSI
- 触及上/下轨 + RSI 超买/超卖 → 信号
- 趋势市自动禁用

Agent 自主能力：
- 判断 K 线数据是否积累足够（至少 20 周期）
- 自适应参数（BB 周期、标准差倍数、RSI 阈值）
- 结合 H2 市场质量分过滤
```

### 策略 D：Grid Trading（网格交易）

```
优先级：中
风险等级：低（适合震荡市）

功能：
- 围绕当前价格设置 N 档价格网格
- 每档下挂限价单对（买+卖）
- 成交后自动补挂
- 纯机械执行

Agent 自主能力：
- 判断当前市场是否适合网格（波动率在 moderate 范围）
- 自适应网格间距和档数
- 趋势突破时自动停止
```

---

## 五、实施顺序

```
Phase 1: 安全修复 + 风控基础
  ├── 修复 S1-S5 安全问题
  ├── 策略 A：自动风控层
  └── Agent 风控自主性框架（global caps + agent-adjustable params）

Phase 2: 本地策略信号器
  ├── 本地技术指标计算引擎（K 线聚合 + MA/RSI/BB/MACD）
  ├── 策略 B：Funding Rate 信号器
  └── 策略 C：Bollinger Band 均值回归

Phase 3: 机械策略 + Agent 策略调度器
  ├── 策略 D：Grid Trading
  ├── Agent Strategy Orchestrator（Agent 自主选择/组合/启停策略）
  └── 策略间冲突检测 + 总敞口协调

Phase 4: 回测验证 + 性能基准
  ├── 历史数据回测框架
  ├── 策略表现基准线（Sharpe / Sortino / 最大回撤 / 胜率）
  └── 优化反馈闭环
```

---

## 六、安全不变量（不因策略扩展而改变）

```
system_mode             = read_only        不变
execution_state         = disabled         不变
execution_authority     = not_granted      不变
is_simulated            = true             所有交易
lease_mode              = shadow_only      所有决策
daily_hard_cap          = $15              AI 成本硬上限
user_global_stop_loss   = 绝对上限         Agent 不可突破
user_global_take_profit = 绝对上限         Agent 不可参考但可提前止盈
max_drawdown_circuit    = 绝对上限         Agent 不可突破
```
