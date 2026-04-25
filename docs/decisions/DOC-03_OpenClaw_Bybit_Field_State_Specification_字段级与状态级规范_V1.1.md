# OpenClaw / Bybit 交易 Agent

# 字段级与状态级规范 V1.1

## 0. 文档定位

本文件是 OpenClaw / Bybit 交易 Agent 的 **字段级与状态级规范文件**。

本文件回答以下问题： - 系统中有哪些核心状态对象 - 每类状态对象包含哪些关键字段 - 字段的正式名称、语义、类型、单位、精度、时区、默认值、空值语义是什么 - 字段是原始事实值、推导值还是展示值 - 哪些字段允许被写入，哪些字段只允许读取 - 状态对象的生命周期如何变化 - API、GUI、审计、报表、学习平面应如何对齐这些字段与状态

本文件 **不负责**： - API 路由设计 - GUI 样式与排版 - 数据库索引与物理建表细节 - 策略参数数值 - 风控阈值数值 - 具体模型提示词

如与《项目宪法 / 根原则》或任何正式边界定义文件（DOC-02、EX-01～EX-05）冲突，以它们为上位约束。


## 1. 总体规范原则

### 1.1 单一语义原则

一个字段在全系统中只能有一个正式语义。

禁止出现以下情况： - 同名字段在不同模块里代表不同含义 - 不同字段名实际上表达同一核心事实 - GUI 为了显示方便重新发明内部状态 - 学习平面使用与实盘不同的关键状态语义

### 1.2 原始值 / 推导值 / 展示值三分原则

所有字段必须明确归类为以下三类之一：
- **Raw / Source ****Value（原始值）**
  - 来自交易所、系统采集、操作员动作、控制平面登记等原始事实
  - 不应被任意覆写
- **Derived ****Value（推导值）**
  - 基于原始值按明确规则推导得出
  - 必须能追溯推导来源
- **Display ****Value（展示值）**
  - 仅供 GUI、报表、摘要阅读使用
  - 不得反向写回成为系统真相

### 1.3 真相源优先原则

关键事实字段必须绑定唯一真相源。

至少以下字段组必须明确唯一真相源： - 持仓 - 订单 - 成交 - Lease - 风险模式 - 系统模式 - Agent 运行状态 - 授权级别

### 1.4 机器字段与展示字段分离

面向系统内部判断的字段，与面向 GUI / 人类阅读的字段必须分离。

例如： - lease_status 是机器字段 - lease_status_label_zh 是展示字段

禁止 GUI 直接修改机器字段语义。

### 1.5 空值语义必须显式定义

任何允许为空的字段，必须说明： - null 代表未知 - 还是代表不适用 - 还是代表尚未计算 - 还是代表已失效

禁止把所有空值都视为同一种语义。

### 1.6 时间统一原则

除展示层外，系统内部所有时间字段应统一使用： - **UTC** 作为机器真相时区 - ISO 8601 或 epoch_ms 作为正式交换格式

如需本地时区显示，只能在展示层转换。

### 1.7 精度与单位必须固定

金额、价格、数量、比例、延迟、时间窗、概率等字段，必须在规范中写明： - 单位 - 精度 - 舍入方式 - 是否允许负值


## 2. 字段命名规范

### 2.1 通用命名风格

推荐统一使用： - 小写 snake_case - 枚举字段名以 _status / _mode / _type / _state 结尾 - 布尔字段以 is_ / has_ / can_ 开头 - 时间字段以 _at / _ts / _window 结尾 - 比例字段以 _pct / _ratio 结尾 - 数量字段以 _qty / _count 结尾

### 2.2 推荐命名示例
- system_mode
- agent_run_mode
- lease_status
- market_regime
- data_quality_state
- net_pnl
- expected_slippage_pct
- max_position_notional
- expires_at
- created_at

### 2.3 禁止命名

禁止使用模糊字段名作为核心字段，例如： - status（不带对象前缀） - flag - data1 - value - misc - temp


## 3. 核心状态对象总表

本项目建议至少标准化以下状态对象：
- system_state —— 系统全局状态
- health_state —— 系统健康状态
- market_state —— 市场状态
- account_state —— 账户状态
- risk_state —— 风险状态
- authorization_state —— 授权状态
- candidate_context —— 候选上下文
- h0_decision —— H0 决定
- deliberation_state —— H1-H5 审议结果
- decision_lease —— Lease 正式对象
- execution_state —— 执行状态
- position_state —— 持仓状态
- order_state —— 订单状态
- fill_state —— 成交状态
- audit_event —— 审计事件
- learning_record —— 学习记录

后续文档可以扩展，但不应随意替换上述对象的核心语义。


## 4. system_state 规范

### 4.1 对象语义

system_state 表示系统当前整体控制模式与运行阶段，是系统行为约束的高优先级对象之一。

### 4.2 核心字段

| 字段名 | 类型 | 类别 | 语义 | 单位/格式 | 空值语义 |
|---|---|---|---|---|---|
| system_mode | enum | raw | 系统控制模式 | string enum | 不可为空 |
| runtime_stage | enum | raw | 当前运行阶段 | string enum | 不可为空 |
| operator_mode | enum | raw | 操作员控制模式 | string enum | 不可为空 |
| is_write_enabled | bool | derived | 当前是否允许写动作 | boolean | 不可为空 |
| is_new_risk_allowed | bool | derived | 当前是否允许新风险暴露 | boolean | 不可为空 |
| updated_at | datetime | raw | 最新更新时间 | UTC ISO8601 | 不可为空 |
| source_module | string | raw | 该对象真相源模块名 | string | 不可为空 |

### 4.3 枚举建议

#### system_mode
- shadow
- paper
- supervised_live
- constrained_live
- manual_safe
- halted

#### runtime_stage
- booting
- warming
- ready
- degraded
- frozen
- recovering

#### operator_mode
- normal
- review_required
- manual_override
- manual_only
- emergency_stop


## 5. health_state 规范

### 5.1 对象语义

health_state 表示系统当前健康状况，用于决定系统是否具备继续交易的资格。

### 5.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| health_status | enum | derived | 综合健康状态 |
| data_quality_state | enum | derived | 数据质量状态 |
| ws_health_state | enum | raw/derived | WebSocket 健康 |
| rest_health_state | enum | raw/derived | REST 健康 |
| db_health_state | enum | raw/derived | 数据库健康 |
| reconciliation_state | enum | derived | 对账健康 |
| audit_pipeline_state | enum | derived | 审计链健康 |
| risk_pipeline_state | enum | derived | 风控链健康 |
| last_successful_sync_at | datetime | raw | 最近一次成功同步时间 |
| latency_ms_p50 | number | raw | 延迟 p50 |
| latency_ms_p95 | number | raw | 延迟 p95 |
| packet_loss_pct | number | raw | 丢包率 |
| cpu_usage_pct | number | raw | CPU 使用率 |
| memory_usage_pct | number | raw | 内存使用率 |
| updated_at | datetime | raw | 更新时间 |

### 5.3 枚举建议

#### health_status
- healthy
- cautious
- degraded
- defensive
- critical
- halted

#### data_quality_state
- reliable
- degraded
- unreliable
- missing

#### reconciliation_state
- in_sync
- lagging
- mismatch_detected
- unknown


## 6. market_state 规范

### 6.1 对象语义

market_state 是系统面对市场时使用的标准化世界状态对象，而不是原始行情流本身。

### 6.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| symbol | string | raw | 交易标的 |
| market_regime | enum | derived | 市场大状态 |
| volatility_state | enum | derived | 波动率状态 |
| liquidity_state | enum | derived | 流动性状态 |
| momentum_state | enum | derived | 动量状态 |
| event_state | enum | derived | 事件驱动状态 |
| correlation_state | enum | derived | 跨市场关联状态 |
| trend_bias | enum | derived | 方向偏置 |
| confidence_score | number | derived | 当前状态识别置信度 |
| regime_window | string | raw/derived | 当前状态主要依据的时间窗 |
| snapshot_at | datetime | raw | 快照时间 |
| data_quality_state | enum | derived | 市场状态本身的数据质量 |

### 6.3 枚举建议

#### market_regime
- trend_up
- trend_down
- range
- compression
- event_driven
- unstable
- unknown

#### volatility_state
- compressed
- expanding
- unstable
- calming

#### liquidity_state
- healthy
- thin
- dangerous

#### trend_bias
- bullish
- bearish
- neutral
- mixed

### 6.4 数值字段建议

如后续加入数值型市场摘要，建议使用： - atr_pct - spread_bps - book_imbalance_ratio - volume_zscore - oi_change_pct - funding_rate

这些字段需在扩展版本中单独固定单位与计算口径。


## 7. account_state 规范

### 7.1 对象语义

account_state 表示账户层面的资金、保证金、权益与 PnL 状态。

### 7.2 核心字段

| 字段名 | 类型 | 类别 | 语义 | 单位 |
|---|---|---|---|---|
| account_id | string | raw | 账户标识 | string |
| venue | string | raw | 交易场所 | string |
| account_equity | number | raw | 当前账户权益 | quote_ccy |
| available_balance | number | raw | 可用余额 | quote_ccy |
| margin_used | number | raw | 已用保证金 | quote_ccy |
| unrealized_pnl | number | raw | 未实现盈亏 | quote_ccy |
| realized_pnl | number | raw | 已实现盈亏 | quote_ccy |
| gross_pnl | number | derived | 名义盈亏 | quote_ccy |
| net_pnl | number | derived | 真实净盈亏 | quote_ccy |
| fee_cost | number | raw/derived | 手续费成本 | quote_ccy |
| slippage_cost | number | derived | 滑点成本 | quote_ccy |
| ai_cost | number | derived | AI 决策成本 | quote_ccy |
| operating_cost_allocated | number | derived | 分摊经营成本 | quote_ccy |
| effective_leverage | number | derived | 实际杠杆 | x |
| updated_at | datetime | raw | 更新时间 | UTC |

### 7.3 空值语义
- operating_cost_allocated = null：表示当前对象尚未做经营层成本分摊，不代表 0
- ai_cost = 0：表示本次周期明确未计入 AI 决策成本


## 8. risk_state 规范

### 8.1 对象语义

risk_state 表示系统当前风险位置、风险预算占用与风险模式。

### 8.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| risk_mode | enum | derived | 当前风险模式 |
| account_risk_state | enum | derived | 账户风险状态 |
| daily_loss_pct | number | derived | 当日亏损占权益比例 |
| weekly_loss_pct | number | derived | 当周亏损占权益比例 |
| drawdown_pct | number | derived | 当前回撤比例 |
| risk_budget_used_pct | number | derived | 已使用风险预算比例 |
| new_risk_allowed | bool | derived | 是否允许新增风险 |
| reduce_only_required | bool | derived | 是否只允许减仓 |
| circuit_breaker_active | bool | raw/derived | 熔断是否生效 |
| updated_at | datetime | raw | 更新时间 |

### 8.3 枚举建议

#### risk_mode
- normal
- cautious
- reduced
- defensive
- circuit_breaker
- manual_review

#### account_risk_state
- normal
- elevated
- critical


## 9. authorization_state 规范

### 9.1 对象语义

authorization_state 表示某对象或当前系统在授权矩阵中的允许范围。

### 9.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| authorization_level | enum | raw | 授权级别 |
| allowed_venues | array[string] | raw | 允许交易场所 |
| allowed_symbols | array[string] / selector | raw | 允许标的范围 |
| allowed_strategy_families | array[string] | raw | 允许策略簇 |
| max_position_notional | number | raw | 最大名义仓位 |
| max_new_risk_pct | number | raw | 最大新增风险比例 |
| allow_short | bool | raw | 是否允许做空 |
| allow_new_orders | bool | raw | 是否允许新订单 |
| allow_modify_orders | bool | raw | 是否允许改单 |
| allow_reduce_only | bool | raw | 是否仅允许减仓 |
| effective_from | datetime | raw | 生效时间 |
| expires_at | datetime | raw | 到期时间 |
| approved_by | string | raw | 批准人/批准来源 |

### 9.3 枚举建议

#### authorization_level
- none
- observe_only
- shadow_only
- paper_only
- supervised_live_limited
- constrained_live
- manual_only

#### authorization_status

授权对象的生命周期状态（与 authorization_level 不同，level 定义权限范围，status 定义生命周期阶段）。完整迁移规则见 SM-01。
- draft
- pending_approval
- active
- restricted
- frozen
- revoked
- expired
- rejected


## 10. candidate_context 规范

### 10.1 对象语义

candidate_context 表示某次候选交易行为在进入 H0 前后的结构化上下文，是 H0 与 H1-H5 的共同基础对象之一。

### 10.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| candidate_id | string | raw | 候选唯一标识 |
| symbol | string | raw | 标的 |
| direction_hint | enum | raw/derived | 初步方向提示 |
| trigger_source | string | raw | 触发来源 |
| trigger_reason | string | raw/display | 触发原因摘要 |
| candidate_created_at | datetime | raw | 候选创建时间 |
| market_state_ref | string | raw | 市场状态引用 |
| account_state_ref | string | raw | 账户状态引用 |
| risk_state_ref | string | raw | 风险状态引用 |
| authorization_state_ref | string | raw | 授权状态引用 |
| health_state_ref | string | raw | 健康状态引用 |
| candidate_status | enum | derived | 候选当前状态 |

### 10.3 枚举建议

#### direction_hint
- long_bias
- short_bias
- flat_bias
- unknown

#### candidate_status
- created
- screening
- h0_rejected
- passed_to_h
- under_deliberation
- closed


## 11. h0_decision 规范

### 11.1 对象语义

h0_decision 表示 H0 对某候选上下文做出的正式本地决定。

### 11.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| h0_decision_id | string | raw | H0 决定唯一标识 |
| candidate_id | string | raw | 对应候选 |
| h0_result | enum | raw | H0 决定结果 |
| h0_reason_codes | array[string] | raw | 原因代码 |
| h0_reason_text | string | display | 可读摘要 |
| h0_rule_version | string | raw | 所用规则版本 |
| decided_at | datetime | raw | 决定时间 |
| decided_by_module | string | raw | 决定模块 |

### 11.3 枚举建议

#### h0_result
- reject
- defer
- downgrade
- pass_to_h
- passive_only


## 12. deliberation_state 规范

### 12.1 对象语义

deliberation_state 表示 H1-H5 对某候选进行审议后的综合状态，不等于 Lease 正式对象。

### 12.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| deliberation_id | string | raw | 审议唯一标识 |
| candidate_id | string | raw | 对应候选 |
| h1_summary | string | raw/display | 市场解释摘要 |
| h2_counter_evidence | array[string] | raw/display | 反证摘要 |
| h3_cost_review | string | raw/display | 成本审查摘要 |
| h4_risk_review | string | raw/display | 风险审查摘要 |
| h5_synthesis | string | raw/display | 综合结论 |
| deliberation_result | enum | raw | 审议结果 |
| requires_manual_review | bool | raw | 是否建议人工审查 |
| lease_draft_ref | string | raw | Lease 草案引用 |
| deliberated_at | datetime | raw | 审议完成时间 |

### 12.3 枚举建议

#### deliberation_result
- recommend_reject
- recommend_defer
- recommend_passive
- lease_draft
- review_required


## 13. decision_lease 规范

### 13.1 对象语义

decision_lease 是受条件、时效与生命周期约束的正式控制对象；它不是订单，也不是最终执行批准。

### 13.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| lease_id | string | raw | Lease 唯一标识 |
| candidate_id | string | raw | 对应候选 |
| source_deliberation_id | string | raw | 来源审议对象 |
| lease_status | enum | raw/derived | Lease 状态 |
| direction | enum | raw | 方向倾向 |
| symbol | string | raw | 标的 |
| lease_type | enum | raw | Lease 类型 |
| valid_from | datetime | raw | 生效起点 |
| expires_at | datetime | raw | 过期时间 |
| invalidation_conditions | array[string] | raw | 失效条件 |
| suggested_max_position_pct | number | raw | 建议最大仓位比例 |
| suggested_execution_style | enum | raw | 建议执行风格 |
| risk_tags | array[string] | raw | 风险标签 |
| lease_reason_chain | array[string] | raw/display | 理由链 |
| created_at | datetime | raw | 创建时间 |
| updated_at | datetime | raw | 更新时间 |

### 13.3 枚举建议

#### lease_status
- draft
- registered
- active
- bridged
- expired
- revoked
- frozen
- rejected
- consumed

#### direction
- long
- short
- flat
- observe

#### lease_type
- entry_candidate
- adjustment_candidate
- exit_candidate
- observe_only
- risk_response

#### suggested_execution_style
- passive_limit
- aggressive_limit
- market_if_required
- split_execution
- reduce_only

### 13.4 空值语义
- expires_at = null：禁止；Lease 必须有生命周期上限或显式永久禁用语义，不允许无界模糊存在
- invalidation_conditions = []：不推荐；如允许，必须由上位文档明示该类 Lease 可无失效条件


## 14. execution_state 规范

### 14.1 对象语义

execution_state 表示某次受控桥接后的执行过程状态，不代表订单最终事实本身。

### 14.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| execution_id | string | raw | 执行对象唯一标识 |
| lease_id | string | raw | 来源 Lease |
| execution_status | enum | raw/derived | 执行状态 |
| execution_intent_type | enum | raw | 执行意图类型 |
| execution_style | enum | raw | 实际执行风格 |
| expected_slippage_pct | number | raw/derived | 预估滑点 |
| actual_slippage_pct | number | derived | 实际滑点 |
| reduce_only | bool | raw | 是否只减仓 |
| execution_started_at | datetime | raw | 开始时间 |
| execution_finished_at | datetime | raw | 结束时间 |
| execution_error_code | string | raw | 错误代码 |

### 14.3 枚举建议

#### execution_status
- pending
- approved
- submitted
- partially_filled
- filled
- cancel_requested
- cancelled
- failed
- reconciling
- completed
- aborted

#### execution_intent_type
- new_entry
- add_position
- reduce_position
- full_exit
- cancel_order
- modify_order
- protective_action


## 15. position_state 规范

### 15.1 对象语义

position_state 是某标的持仓事实的标准化状态对象。

### 15.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| position_id | string | raw | 持仓唯一标识 |
| symbol | string | raw | 标的 |
| side | enum | raw | 多空方向 |
| qty | number | raw | 持仓数量 |
| entry_price | number | raw | 均价 |
| mark_price | number | raw | 标记价 |
| notional_value | number | derived | 名义价值 |
| unrealized_pnl | number | raw/derived | 未实现盈亏 |
| realized_pnl | number | derived | 与该持仓关联已实现盈亏 |
| position_status | enum | derived | 持仓状态 |
| opened_at | datetime | raw | 开仓时间 |
| updated_at | datetime | raw | 更新时间 |

### 15.3 枚举建议

#### side
- long
- short
- flat

#### position_status
- opening
- open
- reducing
- closing
- closed
- unknown


## 16. order_state 规范

### 16.1 对象语义

order_state 表示订单在系统中的标准化状态对象。

### 16.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| order_id | string | raw | 系统订单标识 |
| venue_order_id | string | raw | 交易所订单标识 |
| execution_id | string | raw | 来源执行对象 |
| symbol | string | raw | 标的 |
| order_type | enum | raw | 订单类型 |
| order_side | enum | raw | 买卖方向 |
| price | number | raw | 委托价 |
| qty | number | raw | 委托数量 |
| filled_qty | number | derived/raw | 已成交数量 |
| remaining_qty | number | derived | 剩余数量 |
| order_status | enum | raw/derived | 订单状态 |
| tif | enum | raw | Time in Force |
| reduce_only | bool | raw | 是否只减仓 |
| post_only | bool | raw | 是否仅挂单 |
| submitted_at | datetime | raw | 提交时间 |
| updated_at | datetime | raw | 更新时间 |

### 16.3 枚举建议

#### order_type
- market
- limit
- stop_limit
- stop_market
- take_profit
- other

#### order_side
- buy
- sell

#### order_status
- created
- submitted
- acknowledged
- partially_filled
- filled
- cancel_requested
- cancelled
- rejected
- expired
- unknown

#### tif
- gtc
- ioc
- fok
- post_only


## 17. fill_state 规范

### 17.1 对象语义

fill_state 表示成交事实对象。

### 17.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| fill_id | string | raw | 成交唯一标识 |
| order_id | string | raw | 来源订单 |
| symbol | string | raw | 标的 |
| fill_price | number | raw | 成交价 |
| fill_qty | number | raw | 成交量 |
| fill_notional | number | derived | 成交名义价值 |
| fee_paid | number | raw | 实际手续费 |
| liquidity_flag | enum | raw | maker/taker 标识 |
| fill_at | datetime | raw | 成交时间 |

### 17.3 枚举建议

#### liquidity_flag
- maker
- taker
- unknown


## 18. audit_event 规范

### 18.1 对象语义

audit_event 是系统的正式审计事件对象，不是普通日志行。

### 18.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| audit_event_id | string | raw | 审计事件唯一标识 |
| event_type | enum | raw | 事件类型 |
| object_type | string | raw | 关联对象类型 |
| object_id | string | raw | 关联对象 ID |
| actor_type | enum | raw | 行为体类型 |
| actor_id | string | raw | 行为体 ID |
| event_result | enum | raw | 结果 |
| reason_codes | array[string] | raw | 原因代码 |
| event_payload_ref | string | raw | 事件载荷引用 |
| event_at | datetime | raw | 事件时间 |

### 18.3 枚举建议

#### event_type
- candidate_created
- h0_decided
- deliberation_completed
- lease_registered
- lease_revoked
- risk_rejected
- execution_submitted
- execution_failed
- operator_override
- system_mode_changed
- circuit_breaker_triggered

#### actor_type
- system
- module
- operator
- automation

#### event_result
- success
- rejected
- failed
- cancelled
- noop


## 19. learning_record 规范

### 19.1 对象语义

learning_record 用于学习与复盘平面记录某笔决策/交易/策略行为的归因与改进建议。

### 19.2 核心字段

| 字段名 | 类型 | 类别 | 语义 |
|---|---|---|---|
| learning_record_id | string | raw | 学习记录唯一标识 |
| related_candidate_id | string | raw | 关联候选 |
| related_lease_id | string | raw | 关联 Lease |
| related_execution_id | string | raw | 关联执行 |
| outcome_type | enum | derived | 结果分类 |
| error_family | enum | derived | 错误族 |
| regime_tag | string | derived | 所处市场标签 |
| hypothesis_review | string | raw/display | 假设复盘 |
| suggested_change_type | enum | raw/derived | 建议变更类型 |
| requires_approval | bool | raw | 是否需审批 |
| created_at | datetime | raw | 创建时间 |

### 19.3 枚举建议

#### outcome_type
- good_judgment_good_execution
- good_judgment_bad_execution
- bad_judgment_good_execution
- bad_judgment_bad_execution
- no_trade_correct
- no_trade_missed_opportunity

#### error_family
- alpha_error
- timing_error
- sizing_error
- execution_error
- risk_error
- cost_error
- state_misread

#### suggested_change_type
- parameter_tuning
- threshold_adjustment
- strategy_weight_update
- new_guard_rule
- manual_review_only
- no_change


## 20. 空值、默认值、零值规范

### 20.1 通用规则
- null：表示未知 / 不适用 / 尚未生成，必须在字段级明确区分
- 0：表示该数值明确为零，不得与未知混用
- []：表示已知为空集合，不得与未知混用
- ""：不推荐用于核心字段；优先使用 null

### 20.2 关键对象建议
- 核心状态枚举字段：**不得为空**
- ID 字段：**不得为空**
- created_at / updated_at：**不得为空**
- 成本类字段：允许为 0，但 null 需区分“尚未计入”
- 规则版本字段：不得为空


## 21. 数值字段单位与精度建议

### 21.1 金额类
- 类型：decimal / high precision number
- 单位：quote currency
- 不允许使用浮点无约束比较

### 21.2 比例类
- 统一使用小数或百分比之一，不能混用
- 如采用 _pct，建议明确使用百分比值（例如 12.5 表示 12.5%）
- 如采用 _ratio，建议使用 0-1 或可超 1 的比值，并在字段级写明

### 21.3 时间类
- _at：UTC datetime
- _ts：epoch_ms 或 epoch_s，必须固定一种
- _window：推荐 ISO 8601 duration 或结构化秒数

### 21.4 价格与数量
- 精度必须服从交易所最小 tick / lot 规则
- 内部可保留高精度，但执行前必须合法归整


## 22. 写权限与只读权限总原则

### 22.1 原则

每个核心对象必须定义： - 真相源模块 - 允许写入模块 - 允许读取模块 - 是否允许人工覆盖 - 是否允许学习平面建议但不直接写入

### 22.2 当前阶段总规则
- system_state：仅控制平面/治理模块可写
- health_state：健康监控链可写，其他模块只读
- market_state：市场状态引擎可写，其他模块只读
- risk_state：风险链可写，其他模块只读
- authorization_state：授权治理链/人工批准路径可写
- h0_decision：H0 模块可写
- deliberation_state：H1-H5 审议链可写
- decision_lease：I 控制平面可写状态迁移，不重写来源事实
- execution_state：执行治理链可写
- position_state / order_state / fill_state：对账+交易所事实同步链可写
- learning_record：学习平面可写，但不得反向直接改 live 真相对象

详细所有权矩阵将在后续《Truth Source & Ownership Matrix》中展开。


## 23. 生命周期要求

### 23.1 Candidate → H0 → H → Lease → Execution 主链

推荐生命周期：

candidate_created → h0_decided → under_deliberation → lease_draft → lease_registered → lease_active → lease_bridged → execution_submitted → order/fill progression → position update → learning_record created

### 23.2 生命周期禁止事项

禁止出现： - 无来源 candidate 的 Lease - 无 Lease 直接出现的 execution - 无 execution 来源的系统订单对象 - 无审计事件的关键状态跳变


## 24. API / GUI / Audit / Learning 对齐要求

### 24.1 API
- API 字段名必须遵循本规范
- API 不得把展示字段冒充机器字段
- 所有状态枚举应在 API 文档中与本规范一致

### 24.2 GUI
- GUI 可以做本地 label 映射
- GUI 不得自行发明核心状态
- GUI 不得将“摘要解释”回写为“系统真相”

### 24.3 Audit
- 审计事件必须引用正式对象 ID
- 审计事件中的状态值必须与本规范一致

### 24.4 Learning
- 学习平面可组合多个对象做分析
- 学习平面输出的建议必须与本规范中的对象建立正式引用
- 学习建议不得直接替代正式对象写入


## 25. 版本化要求

本文件修改时必须： - 标记版本号 - 标记新增 / 删除 / 弃用字段 - 说明兼容性影响 - 说明是否需要数据迁移 - 说明是否影响 API / GUI / 审计 / 历史回放

核心对象字段不得无版本直接改语义。


## 26. 附录：动作与结果类正式对象

除上述 16 个核心状态对象外，系统中还存在以下 4 个动作/结果类正式对象，其完整字段模板已在对应边界定义文件中给出，此处列出其核心语义与归属：

### 26.1 risk_decision

语义：Risk Governor 对某个 Lease、执行申请或持仓调整做出的正式风控裁决结果。真相源：Risk Governor。主写入方：Risk Governor。完整字段模板见 EX-01 §16。

### 26.2 reconciliation_result

语义：Reconciliation 对本地视图与外部事实的一致性校验结果。真相源：Reconciliation Pipeline。主写入方：Reconciliation。完整字段模板见 EX-04 §18。

### 26.3 learning_suggestion

语义：Learning Plane 生成的候选变更建议对象。真相源：Learning Plane。主写入方：Learning Plane。完整字段模板见 EX-05 §6。禁止写入方：GUI、H0、H1-H5、I、Execution。

### 26.4 operator_action

语义：操作员通过 Control Plane 发起的正式治理动作对象。真相源：Control Plane。主写入方：Control Plane / Operator Console。完整字段模板见 EX-03 §18。禁止写入方：H0、H1-H5、I、Learning。

### 26.5 change_request

语义：进入正式变更治理流程的变更请求对象。真相源：Change Control Pipeline。主写入方：Change Control Pipeline（接受来自 Operator、Learning、Audit、Engineering 的变更提议）。完整字段模板见 DOC-06 §9。禁止写入方：GUI 直接伪造、H0、H1-H5、I 直接生成。

### 26.6 incident_record

语义：事故的正式记录对象，含严重等级、影响范围、根因分类、围堵状态与恢复审批。真相源：Incident Pipeline。主写入方：Incident Pipeline + Operator。完整字段模板见 DOC-07 §8。禁止写入方：GUI 直接伪造、Learning 直接改写、H0/H1-H5/I。


## 27. 一句话总纲

**字段级与状态级规范的目标，是把系统的设计理念压缩成统一、可追溯、可审计、可实现的工程真相，使任何模块都不能各自发明“自己的真相版本”。**
