# OpenClaw / Bybit — 系统参考手册
# OpenClaw / Bybit — System Reference Handbook

**来源 / Source**: 从 CLAUDE.md 移出的参考性内容（非核心指令）
**用途 / Purpose**: Claude 需要查阅详细规格时参考。CLAUDE.md 中保留了指向本文件的指针。
**最后更新 / Last updated**: 2026-03-27

---

## 一、核心能力目标（完整版）

**A. 自主交易执行（在严格门控下）**
- 能自动完成下单、撤单、改单、持仓管理
- 必须先通过本地 H0 判断 → AI 治理 → Decision Lease → 执行门
- 不能跳过任何门，不能因为"行情来了就直接下"

**B. 成本与收益感知**
- 必须追踪 net PnL，不能只看 gross PnL
- 必须纳入：AI API 调用成本、Bybit 手续费、滑点估算、设备折旧、电费、基础设施成本
- 每一笔决策都要能问：扣完所有真实成本后，这笔还有没有正期望？

**C. 计算路径智能分级**
- 纯本地确定性计算（H0，最低延迟，零成本）
- 本地小模型推理（中等复杂度，低延迟）
- 云端 API 大模型（高价值判断，有预算限制）
- 每次调用都有成本记账，纳入 net PnL 计算

**D. 自我感知能力（Self-Observability）**
- 硬件感知：CPU 使用率、内存压力、磁盘 I/O
- 网络感知：REST 延迟、WebSocket 稳定性、公网出口 IP、丢包率
- 软件感知：哪个模块在拖慢整体、数据库查询延迟、脚本执行时间
- 能判断"当前系统状态是否适合交易"——系统不健康时主动降级或暂停

**E. 持续学习能力（越做越好）**
- 记录每次决策的完整上下文：市场状态 + 判断理由 + 执行结果
- 对结果做归因：是策略问题、时机问题、执行问题、还是成本问题
- 生成可检验的假设 → 提出实验方案 → 学习结果沉淀为可复用经验
- **严格边界：学习 ≠ 自作主张**

**F. 日/周/月经营报告**
- 分解：哪些交易赚钱 / 哪些亏钱 / 哪些成本可以优化
- 错误归因 + 可优化建议

**G. Agent 自主交易能力（在风控框架下）**
- Agent 自主决定：品种 / 策略 / 时机 / 仓位 / 参数
- 支持 Bybit V5 API 全 6 品类 + 10+ 订单类型
- 三层优先级风控：P0 > P1 > P2
- Agent 不可以：突破用户上限、自行开启未授权品类、关闭硬止损、修改 system_mode

**H. 对抗性市场意识（Anti-Adversarial Trading）**
- 止损分两层：硬止损（绝对防线）+ 软止损（Agent 评估后决定）
- 止损隐身：永远不在交易所放 stop order，本地 tick() 检查触发
- 反猎杀：ATR + 随机偏移 + 假突破识别 + 流动性感知平仓

**I. AI 注意力税（AI Attention Tax）**
- 持仓真实成本 = 金融成本 + AI 注意力成本
- cost_edge_ratio 超阈值 → 建议平仓
- Agent 自然偏好低维护策略

**J. GUI Operator Console + Learning Cockpit**
- 运营驾驶舱：状态总览 / 控制中心 / 经营收益 / 审计记录 / 学习驾驶舱
- GUI → Control API → Agent 逻辑

---

## 二、Control API 详细状态

### 代码位置
`program_code/exchange_connectors/bybit_connector/control_api_v1/`

### 已可用 GET 接口（31+ 条）
`/system/overview` / `chapter-status` / `control-plane` / `capability-matrix` / `product-families` / `business/daily` / `business/summary` / `health` / `audit-summary` / `source-context` / `learning/overview` / `learning/hypotheses` / `learning/feed` / `learning/experiments` / `learning/net-pnl` / `learning/review-queue` / `paper/session/status` / `paper/orders` / `paper/positions` / `paper/fills` / `paper/pnl` / `paper/audit-trail` / `paper/export` / `paper/shadow/history` / `paper/shadow/decisions` / `paper/metrics` / `paper/ai-cost` / `paper/market-feed/status` / `console`

### 已可用 POST 接口（44+ 条）
`demo/validate` / `demo/arm` / `demo/enable` / `demo/relock` / `safe-recheck-bundle` / `recheck/j-canonical` / `recheck/k-canonical` / `recheck/j-closeout` / `recheck/k-closeout` / `input/config-change` / `input/cost` / `input/event` / `input/manual-note` / `input/observation` / `input/lesson` / `input/hypothesis` / `input/experiment` / `input/pnl-entry` / `input/pnl-period-snapshot` / `learning/hypothesis/{id}/verdict` / `learning/experiment/{id}/approve` / `learning/experiment/{id}/complete` / `learning/auto/scan-observations` / `learning/auto/scan-lessons` / `learning/auto/scan-hypotheses` / `learning/review/{id}/decide` / `learning/review/{id}/ai-consult` / `control/product-family/{family}/config` / `paper/session/start` / `paper/session/pause` / `paper/session/resume` / `paper/session/stop` / `paper/order/submit` / `paper/order/cancel` / `paper/tick` / `paper/shadow/feed` / `paper/market-feed/start` / `paper/market-feed/stop` / `paper/market-feed/add-symbol` / `paper/market-feed/remove-symbol`

### Phase 2 策略路由（11 条）
GET: `strategy/klines/{symbol}/{timeframe}` / `strategy/indicators/{symbol}/{timeframe}` / `strategy/signals` / `strategy/signals/{symbol}/summary` / `strategy/list` / `strategy/{name}/status` / `strategy/intents` / `strategy/status`
POST: `strategy/{name}/activate` / `strategy/{name}/pause` / `strategy/{name}/stop`

### 安全加固
- API Token：自动生成 + 文件保存 + 重置指南
- Token 比较：`hmac.compare_digest()` 常数时间
- 状态文件权限：`chmod 0o600`
- CORS：`OPENCLAW_CORS_ORIGINS` 配置
- 速率限制：slowapi 120/min/IP（`OPENCLAW_RATE_LIMIT`）
- 文本长度限制：title ≤200 / detail ≤2000 / reason ≤500
- 幂等缓存 TTL：24h + 500 条上限

### API 合同版本
`openclaw_bybit_control_api_v1_rc2@v1`
`openclaw_bybit_state_dictionary@v1`

---

## 三、Paper Trading Engine 详细

- 独立模块：`app/paper_trading_engine.py` + `app/paper_trading_routes.py`
- 独立状态文件：`OPENCLAW_PAPER_STATE_FILE`
- 7 状态生命周期：created → submitted → working → partially_filled → filled/canceled/rejected
- 成交模拟：market order（含滑点 0.05%）+ limit order（价格穿越）
- 手续费：taker 0.055% / maker 0.02%
- PnL：realized + unrealized - fees - ai_cost = net_paper_pnl
- 影子决策管线：`shadow_decision_builder.py`
- 性能指标：`paper_trading_metrics.py`（胜率 / 最大回撤 / Sharpe）
- 实时行情：`bybit_public_ws_listener.py` + `market_data_dispatcher.py`
- 自动桥接：`auto_bridge_observer_to_runtime_snapshot.py`

---

## 四、GUI Operator Console 详细

- 真实调用 API（非静态 mock），并发 fetch 10+ 端点
- 主控制台区块：连接区、summary、运行模式控制、经营摘要、来源上下文、健康摘要、产品族配置、快捷动作、审计
- Learning Cockpit 5 标签：Observation / Lesson / Hypothesis / Experiment / Review Queue
- Net PnL Dashboard：日度 PnL / 成本分解 / 周期趋势
- Paper Trading Dashboard：Session 控制 + PnL 卡片 + 持仓/订单/成交/审计
- 统一控制台 `/console`：Trading Dashboard + OpenClaw + AI Cost

### GUI 关键文档
```
docs/handoffs/2026-03-25_api_gui_handoff/
  API_GUI_FULL_ENGINEERING_REPORT_2026-03-26.md
  API_GUI_LIGHT_CLOSEOUT_2026-03-26.md
  API_GUI_STAGE_COMPLETION_README_2026-03-26.md
  API_GUI_STAGE_CLOSEOUT_CHECKLIST_2026-03-26.md
  GUI_OPENCLAW_PORTAL_PRELAYOUT_2026-03-26.md
  LONG_TERM_SWITCHES_PRESET_2026-03-26.md
```

---

## 五、产品族与能力层

### 产品族
```
spot               现货（无杠杆、无爆仓、最安全）
margin             现货保证金（有杠杆、有借贷利息、有爆仓）
perp_linear        线性永续 USDT/USDC（杠杆 1-125x、funding rate、主战场）
perp_inverse       反向永续（以币结算、杠杆、funding rate）
options            期权（买方亏损有限、卖方风险无限、Greeks 风险）
other_derivatives_reserved  其他衍生品 / 期货（有到期日、预留）
```

### Bybit V5 API 全量订单类型
```
market / limit / conditional / tp_sl_order / tp_sl_position / trailing_stop
reduce_only / post_only / iceberg / twap / batch
```

### 保证金模式
`cross` / `isolated` / `portfolio`

### 持仓模式
`one_way` / `hedge`

### 三层优先级风控
```
P0 品类专属 > P1 全局 > P2 Agent 自适应
合并：effective = min(P0 ?? P1, P1)，Agent P2 在 effective 内收紧
```

### 对抗性止损设计
```
硬止损：P1 全局上限，绝对防线，永远不放交易所 order book，本地 tick() 触发
软止损：Agent 评估（渐进下跌 vs 瞬间刺穿？相关资产联动？）
反猎杀：ATR + 随机偏移 + 假突破识别 + 流动性感知 + 非标仓位
```

### AI 注意力税
```
cost_edge_ratio = total_holding_cost / initial_expected_edge
  A (<0.2) / B (<0.4) / C (<0.6) / D (<0.8) / F (≥0.8)
```

### OpenClaw 能力层
`unsupported` / `observe_only` / `shadow_ready` / `demo_ready` / `live_guarded_ready` / `live_ready`

### 执行动作权限
`new_order` / `cancel` / `amend` / `reduce_only` / `increase_position` / `close_position` / `leverage_change` / `borrow` / `transfer`

---

## 六、OpenClaw 融合

- 统一控制台：`/console`（Trading Dashboard + OpenClaw Gateway 状态 + AI 成本侧边栏）
- OpenClaw 定位：通信层（消息推送 / 成本追踪 / 定时任务），非 Agent 大脑
- Canvas 对接：`~/.openclaw/canvas/index.html` → iframe 指向统一控制台

---

## 七、部署与服务化

- systemd 用户服务：`openclaw-trading-api.service`（开机自启 + 崩溃重启）
- 绑定 `127.0.0.1:8000`（仅本地），远程访问通过 SSH 隧道
- 管理：`systemctl --user {status|restart|stop} openclaw-trading-api`
- OpenClaw Gateway：端口 18789

---

## 八、近期关键设计文档索引

```
docs/references/
  2026-03-27--phase1_risk_framework_and_agent_autonomy_design.md
    → ★★ 全品类风控框架完整设计
  2026-03-27--phase2_strict_audit_report.md
    → ★ Phase 2 严格审核报告
  2026-03-27--phase2_audit_fix_roadmap.md
    → Phase 2 修复路线图
  2026-03-27--local_trading_logic_audit_and_strategy_plan.md
    → 本地交易逻辑审查报告
  2026-03-27--layer2_ai_reasoning_engine_implementation_plan.md
    → Layer 2 实现计划

docs/worklogs/control_api_gui/
  2026-03-27--phase2_local_strategy_toolkit_engineering_log.md
    → Phase 2 完整工程日志
  2026-03-27--phase1_final_audited_engineering_log.md
    → Phase 1 最终审核版工程日志
```

---

## 九、历史编号映射（防混淆）

| 历史临时编号 | 正式章节 |
|---|---|
| D21 readonly observer hardened | D |
| D22 business-event classification | E |
| D23 event-driven scaffold | F |
| 临时 G1/G2/G3 | G |
| 临时 G4.x | J |
| 临时 G5/G6 | K |

J/K 内部旧 G4.x/G5.x 命名是历史 debt，已完成 functional closeout，不再继续深挖。
