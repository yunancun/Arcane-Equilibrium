# OpenClaw / Bybit AI Agent Trading System
<!-- Git 日志 — 项目入口。主日志见 CLAUDE.md -->

AI Agent 自动交易系统 — 自主扫描 650+ 交易对，智能部署策略，**Live_Ready ⚠️**（5 项 live gate 全绿才上真实 live，见下文门控表）。

---

## 🖥️ GUI 访问（Tailscale 网络内）

| 地址 | 功能 |
|------|------|
| **[http://trade-core:8000](http://trade-core:8000)** | **统一控制台**（登录后进入 11 Tab 视图） |
| [http://trade-core:3000](http://trade-core:3000) | Grafana 运营监控仪表盘 |
| [https://trade-core.tail358794.ts.net](https://trade-core.tail358794.ts.net) | OpenClaw Gateway |

### 统一控制台 Tab（11 Tab，左→右）

| Tab | 内容 |
|-----|------|
| 📊 系统总览 / Overview | 系统状态 + 章节状态 + Paper Trading 概览 |
| 🟣 实盘交易 / Live | **Live_Ready** — 紫色主题仪表板（余额/PnL/持仓/成交/缩仓监控）+ API key 管理 + 3 槽位（Demo/Live-Demo/Live）|
| 🧪 测试交易 / Test | **子 Tab 包装器**：纸面交易 / Bybit Demo（iframe 独立加载） |
| 📈 K线图表 / Charts | TradingView K线 + 信号标记 + 策略面板 |
| ⚙ 策略中心 / Strategy | 策略部署 + 扫描器 + 品种管理 |
| 🛡 风控止损 / Risk | P0/P1/P2 风控参数 + 止损配置 |
| 🤖 AI 引擎 / AI | Layer2Engine + 模型选择 + 成本追踪 |
| 📖 学习系统 / Learning | Learning Cockpit + 观察统计 + 晋升状态 |
| ⚖ 治理控制 / Governance | GovernanceHub 4 SM + 授权 + 租约 + 对账 |
| 🔍 监控 / Monitor | Grafana 嵌入 + 系统健康 |
| ⚙ 设置 / Settings | 参数配置 + 计划重启（弹窗修复）|

---

## 当前状态 (2026-04-29 · **Live_Ready ⚠️** · 62-finding remediation Batch A-F deployed · 治理文件減肥完成)

**最新更新**：62-finding remediation Batch A-F 全部 fixed/sign-off/PUSHED/Linux deployed（commits `bc3fa70` + `6539e4e` + `5db4e29`，6 batch × 62 findings × Linear NCY-5..10 milestone 對應）；2026-04-29 治理文件減肥 Stage 0-2 完成（TODO.md 817→678 / CLAUDE.md §三 5 個過期 paragraph 歸檔到 archive）；post-deploy healthcheck 大幅改善（fix `cfb1e7d` demo fee cold-boot + `c0902d9` post-restart passive wait grace 後，原 FAIL `[12]+[22]` / WARN `[27]` 已 PASS，僅剩 `[16] strategist_cycle_fresh` 需 RCA）
- 治理 trim 歸檔索引：`docs/archive/2026-04-29--62finding-batch-A-to-F.md` · `docs/archive/2026-04-29--strkusdt-p0-wave.md` · `docs/archive/2026-04-29--wave-A-to-H-narrative.md` · `docs/archive/2026-04-29--claude_md_section3_pre_04_27_detail.md`
- Batch F PM Sign-off：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_f_ml_agent_autonomy_signoff.md`
- 62-finding tracking ledger：`docs/audit/remediation_tracking.md`
- TODO（按 Wave 1-4 + Batch + Backlog 組織）：`TODO.md`

**Runtime（2026-04-29 CEST · ssh verify）**：HEAD `b0ef335` synced（pre-trim） · engine PID **161957** alive · API uvicorn PID **162029** + 4 workers · engine_watchdog PID 3450754 · openclaw-gateway PID 3973441 · watchdog `engine_alive=true` + demo snapshot fresh · API auth enforced（401 unauth）· post-deploy healthcheck FAIL `[16]`（其餘 27 PASS）· Live pipeline 拒啟動是預期 gate（authorization schema v1 vs v2，需 Operator 經 `/api/v1/live/auth/renew` 重簽，不可手寫）

**已驗證的修復事實**：
1. ExecutorAgent shadow_mode hardcoded ✅ 已修（G3-03 Phase B `shadow_mode_provider` live at `program_code/.../executor_agent.py:145-186`，取代 hardcoded `_shadow_mode = True`）
2. edge_estimator_scheduler ✅ 已修（commits `f32629c`+`abc85c0`，2026-04-24；現 187 cells / 59 updated/cycle / mtime <30min）
3. PostOnly demo/live 反向 ✅ 已修（EDGE-DIAG-2 + Wave A-H series）

**下一步主路徑**：(1) `[16] strategist_cycle_fresh` RCA（強 1）→ (2) Live auth renewal（operator 動作）→ (3) G1-04-FUP ~05-02 1w accumulated re-compute → (4) G2-01 PostOnly ~05-07 1-2w 驗收 → (5) Phase C Wave 1 派發（operator gated）→ Live（最早 ~2026-05-23）


```
系统模式:     Live_Ready ⚠️ — LIVE-P0/P1/P2 代码完整，0 真实 live 流量（历史 43k "live" = LiveDemo）
Live 门控:    5 项全绿才上真实 live（LIVE-GUARD-1 + LIVE-GATE-BINDING-1，2026-04-18 ✅）
              Rust 侧 4 项可验证 + Python 侧 1 项 global mode：
              (1) Python live_reserved global mode + Operator auth
              (2) OPENCLAW_ALLOW_MAINNET=1 env var（仅 Mainnet）
              (3) secret slot 有 api_key + api_secret（Mainnet env var fallback 已封闭）
              (4) authorization.json HMAC-SHA256 签名 + 未过期（每 5 min re-verify）
              (5) Python Operator 角色 auth
execution_authority: Rust 端仅为 P0/P1 denylist 字符串常量（claude_teacher/applier.rs:226）
                     非真实授权逻辑，"auto_granted_on_start" 为 Python 概念
测试:         Rust engine lib 2290 passed / 0 failed（Phase 4 + G3-09 Phase A merge 後 baseline，2026-04-27）
              · core 403 · e2e 35 · reconciler_e2e 19
              Python control_api 3117 passed (0 fail · 3 skipped) · ml_training 238 passed
              healthcheck 28 check（19 既有 + STRKUSDT P0 wave [22-29] + EDGE-DIAG-2 [30] + [31]）
API 路由:     209 /api/v1 + 11 non-api（2026-04-16 audit 实测）
代码:         ~62,000 行（Python ~40k + Rust ~22k）
单一引擎:     Rust openclaw_engine = paper / demo / live 三模式唯一引擎
              tick pipeline + IntentProcessor + paper_state + governance + stop_manager
ARCH-RC1:     ✅ 1A → 1C-4 WRAP COMPLETE
              4 IPC 写入面（patch_{risk,learning,budget}_config + update_strategy_params）
              5 engines 热重载 · V014 fail-soft audit · ConfigStore 落盘 ✅
              Guardian = RiskConfig 纯派生视图
Phase 5:      ⏸ PAUSED（2026-04-12 reframe）— PNL-FIX-1/2 揭露活跃策略 gross edge 为负
              cost_gate / DL / JS 机械已接线但需真实正 edge；等策略重做（G-SR-1 / Strategist）
近期里程碑:   ✅ EDGE-P2-2 Phase A OI confluence（`381c542`，E2 FUP #1-#7 全修，2026-04-20）
              ✅ PIPELINE-SLOT-1 Phases 1-4（auth-fail live-only，2026-04-19）
              ✅ E5-FN / FILL-CONTEXT / EXIT-FEATURES / E5-P0/P1/P2 Refactor Waves
              ✅ P1-16 HALT-SESSION cross-symbol price corruption（245× cleaner，2026-04-18）
              ✅ LIVE-GATE-BINDING-1 HMAC authorization.json（2026-04-18）
              ✅ LIVE-GUARD-1 三重 Mainnet 硬锁（2026-04-16）
              ✅ P0-10 SCANNER-GATE / P0-5 PHANTOM-2-FUP / P1-8 / MICRO-PROFIT-FIX-1（2026-04-17）
EDGE-P3-1:    🟡 ONNX loader Phase B #3 ✅（ort backend）+ Lane A CQR ✅；等真 ETL 资料跑首 artifact
Live 准备:    ✅ P0 API key 管理 + tab-live 动态前置条件 + 仪表板框架
              ✅ P1 TradingMode::Live + slot-aware key 读取 + session routes
              ✅ P2 PerEngineRiskStores（paper/demo/live 独立风控）+ GUI per-engine tab
              ✅ P3 Gov-P1 + OPENCLAW_ALLOW_MAINNET 硬锁回补（Rust fail-safe 三重 gate）
              ✅ P4 Live-Demo 虚拟槽 + live/paper metrics 端点 + DB Signal Diamond 规划
              ✅ P5 LIVE-GATE-BINDING-1 Python↔Rust HMAC 签名授权
安全:         ✅ SEC-05 innerHTML XSS 全面修复（safeText→ocEsc + badge fallbacks）
              ✅ LIVE-GUARD-1 OPENCLAW_ALLOW_MAINNET 三重硬锁（2026-04-16 回补）
              ✅ WP-F/AH-06 risk-tab dirty-tracking 防覆盖
              ✅ W19 G-3 IPC HMAC-SHA256 认证 + G-5 Rate Limit 全局覆盖
              ✅ W20 SEC-04/06/13 E3 深度审查 PASS
治理:         GovernanceHub 4 SM (Python) + GovernanceCore (Rust) · fail-closed
              Operator manual governor override（白名单 / 24h cooldown / V014 audit）
              Position Reconciler 30s 真相轮询 + Phase 6 自动降级（6-RC-1~10 ✅）
              策略渐进放权管线（6-01~03 ✅）：5 阶段 + 毕业门槛 + Operator 审批
              Phase 6 验收（6-04~08 ✅）：集成 7 + 压测 9 场景 + sync_commit PASS
Bybit REST:   httpx BybitClient 13 方法（PYO3-ELIMINATE-1 Phase 2 後純 Python，LIVE-GATE-FALLBACK-1 reduce_only 繞引擎直通）
Phase 4:      ✅ CODE-COMPLETE（4-00~4-21 + 4.1）· Claude Teacher consumer loop 已 wire
新闻引擎:     ✅ NewsPipeline + Guardian halt + 60s scheduler（A2 完成）
Layer 2:      L0 确定性 → L1 Ollama 9B/27B → L2 Claude API
5 Agent:      Scout + Strategist + Guardian + Analyst + Executor 全部运行
数据库:       TimescaleDB 2.26.1 · 43 tables · 28 hypertables · 11 Grafana VIEWs
              Signal Diamond Phase 1-4 ✅（归档：docs/references/2026-04-10--signal_diamond_db_todo.md）
Bybit API:    64 REST + 8 WS + 5 Private WS + 8 IPC

下一步（2026-04-29 PM 排序）:
  1) [16] strategist_cycle_fresh RCA（healthcheck 唯一 FAIL，其餘 27 PASS）
  2) Live auth renewal（operator 動作 — `/api/v1/live/auth/renew` 重簽 schema v2）
  3) G1-04-FUP ~05-02：1w accumulated 後 QC re-compute fee drop + R:R baseline
  4) G2-01 PostOnly 1-2w 驗收 ~05-07/08：fee drop ≥60% 或 G2-04 disable 決策
  5) G2-02 ma_crossover counterfactual ~05-03：tool ready，passive 1w demo data 後跑雙軌
  6) Phase C Wave 1 impl（PA RFC `90d1a2e` ready，operator gated）
  7) LG-4/5 Live Gate + 真实 Live：换入 mainnet API key（最早 ~2026-05-23 W24 末）
```

**亮点**：ARCH-RC1 统一 Config 4 IPC 写入面 + 5 engines 热重载（端到端 e2e `4780b04`）· Python 风控/纸盘双退场 · Guardian = RiskConfig 纯派生视图 · 单一 Rust 引擎 · V014 audit · L3 12 路审计完成 · EXT-1 Exchange-as-Truth · 5 Agent · Rust tick <100μs · PYO3-ELIMINATE-1 完成（纯 Python httpx Bybit 桥，无 cdylib 跨平台耦合）· Telegram+Webhook 双通道告警

**详细完成度视角**：见 `docs/audits/2026-04-07--phase4_final_signoff_audit.md`（Phase 4 sign-off）+ `TODO.md`（forward plan）。早期 A-J 能力目标 + Batch 9B 缺口表已过期归档至 `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`。

**开发路线图**

| Phase | 内容 | 状态 |
|-------|------|------|
| 0-3 | 业务功能 52%→100% + L1/L2 冻结 | ✅ 完成 |
| R-00~R-06 | Rust 引擎 24 core + 12 engine 模组 + IPC | ✅ 完成 |
| R-07 | 灰度验证（Go/No-Go 4/10） | ✅ 7/7 PASS |
| 0a | PG 8-Schema DDL + Grafana VIEW 桥接 | ✅ 完成 |
| 0b | TimescaleDB + 压缩/retention | ✅ 完成 |
| Session 6 | KNOWN_ISSUES 清理 + OC-1/2 告警 + Shadow docs | ✅ OPEN 8 |
| 1 | 市场数据止血 + FeatureCollector + PSI | ✅ 完成 |
| 2 | 交易链 + Decision Context + LightGBM Scorer + ONNX | ✅ 完成 |
| **3a** | **update_params() 改造（AGT-1）** | **✅ 完成** |
| **3b** | **Optuna TPE + Thompson Sampling + CPCV + 黑天鹅** | **✅ 完成** |
| Session 9 | EXT-1 Exchange-as-Truth + L3 Audit + Risk Config | ✅ 完成 |
| RRC-1 | 风控运行时接线（H0Gate+9 check+Gate 2.7） | ✅ 完成 |
| L3 Audit | 12路全系统审计 + PA 整改计划 | ✅ 63 issues |
| 4 | Claude Teacher + LinUCB + 新闻 Agent + DL-3 | ✅ CODE-COMPLETE（4-00~4-21 + 4.1） |
| ARCH-RC1 | 统一 Config + Python 风控核心退场 | ✅ 1A→1C-4 WRAP COMPLETE + A2 News scheduler |
| **5** | **cost_gate 重写：DL-1/2 + James-Stein + mode-aware gate** | **⏸ PAUSED — PNL-FIX 揭露 gross edge 为负，等策略重做** |
| **Live 准备** | **API key + TradingMode::Live + PerEngineRiskStores** | **✅ P0/P1/P2 全部完成** |
| **安全** | **SEC-05 XSS + WP-F/AH-06 + G-3 IPC 认证 + G-5 Rate Limit + SEC-04/06/13** | **✅ W19+W20 完成** |
| 6 | Reconciler 自动收缩（6-RC-1~10 ✅）+ 渐进放权（6-01~03 ✅）+ 验收（6-04~13 ✅） | ✅ 完成 |
| Live | 21 天 demo + SEC-08/17/21 + Live Gate | ⬜ 等策略重做后启动 |

**详细文件**：`docs/references/2026-04-04--execution_plan_v1.md`（执行计划 V1）

---

## 项目结构

```
srv/
├── CLAUDE.md                      ← ★ 项目完整上下文
├── docs/                          ← 工程文档（20+ 份日志/审核/设计）
├── program_code/
│   ├── exchange_connectors/
│   │   └── bybit_connector/
│   │       └── control_api_v1/    ← FastAPI 126+ 路由 + 3,700+ 测试
│   │           ├── app/
│   │           │   ├── governance_hub.py         ← ★ 治理中枢（4 SM 编排 + 跨 SM 级联）
│   │           │   ├── governance_routes.py      ← 11 治理 API 端点（含 6-01~03 渐进放权）
│   │           │   ├── scout_routes.py          ← 5 Scout REST 端点（OpenClaw 推送入口）
│   │           │   ├── paper_trading_routes.py  ← Paper/Demo/Live session 路由
│   │           │   ├── live_routes.py           ← Live 实盘 API 端点
│   │           │   ├── multi_agent_framework.py ← ScoutAgent + MessageBus + Conductor
│   │           │   ├── ollama_client.py         ← Ollama HTTP 客户端（L1 本地推理）
│   │           │   ├── bybit_demo_connector.py  ← 工具函数（round_price/qty，无交易逻辑）
│   │           │   ├── grafana_data_writer.py   ← Grafana 数据写入
│   │           │   ├── telegram_alerter.py      ← Telegram 告警
│   │           │   └── static/                  ← GUI (login/console/11 Tab)
│   │           └── tests/
│   ├── local_model_tools/         ← 策略工具包（HTTP 路由层，无交易逻辑）
│   │   ├── kline_manager.py       ← K线聚合 + REST 引导
│   │   ├── indicator_engine.py    ← 7 指标协调
│   │   ├── signal_generator.py    ← 8 信号规则
│   │   ├── strategies/base.py    ← StrategyBase ABC（策略由 Rust 引擎实现）
│   │   └── strategy_orchestrator.py ← HTTP 路由层 activate/pause/stop（IPC → Rust）
│   ├── governance/                ← Phase 2 治理状态机（授权/风控/租约/对账/审计）
│   ├── ai_agents/                 ← H1-H5 AI 治理层
│   ├── risk_control/              ← H0 本地判断
│   └── trade_executor/            ← I 决策租约
├── docker_projects/
│   ├── monitoring_services/       ← Grafana + 5 仪表盘
│   └── trading_services/          ← PostgreSQL
├── rust/                          ← ★ Rust 交易引擎（R-00~R-04）
│   ├── Cargo.toml                 ← Workspace: 3 crates（PYO3-ELIMINATE-1 Phase 3 後移除 openclaw_pyo3）
│   ├── openclaw_types/            ← 10 shared types + serde (36 tests)
│   ├── openclaw_core/             ← 24 modules: SM/indicators/signals/risk/backtest (403 tests)
│   ├── openclaw_engine/           ← 12+ modules: tick pipeline/strategies/paper state/canary (116 tests)
│   └── schemas/                   ← Golden JSON schema (10 types)
├── helper_scripts/                ← ★ 详见 helper_scripts/SCRIPT_INDEX.md
│   ├── restart_all.sh             ← 轻量重启（--rebuild 先编译）
│   ├── stop_all.sh                ← 优雅停止 + maintenance flag
│   ├── clean_restart.sh           ← 交易所平仓 + 重启（不动 DB / paper_state）
│   ├── fresh_start.sh             ← ★ 完整 DB 重置重启（PnL/手续费/胜率清零）
│   ├── clean_restart_flatten.py   ← 交易所平仓助手（demo / mainnet，PYO3-ELIMINATE-1 Phase 2 後走 httpx）
│   ├── start_paper_trading.sh     ← Paper Trading 一键启动
│   ├── cron_observer_cycle.sh     ← Observer 自动化
│   ├── cron_daily_report.sh       ← 日报 → Telegram（UTC 0:00）
│   ├── canary/                    ← 灰度验证 + watchdog
│   ├── db/fresh_start_reset.py    ← DB 经验数据清理（保留市场/模型）
│   └── maintenance_scripts/       ← 清理 / 检查脚本
└── docs/
    ├── rust_migration/            ← 8 阶段执行文件（R-00~R-07）
    └── worklogs/                  ← Session 工作日志
```

---

## Phase 2 治理模組 (T2.01–T2.23)

21 个治理模组全部实现，覆盖 4 个核心状态机 + 17 个扩展模组：

| 类别 | 模组 | 规格 |
|------|------|------|
| 核心状态机 | T2.01 授权状态机、T2.02 风控状态机、T2.03 决策租约、T2.04 对账引擎 | SM-01/SM-02/SM-04/EX-04 |
| 扩展模组 | T2.05–T2.23（OMS、审计持久化、Scout Agent、组合风控、事件模型、感知数据面、学习门控等） | EX-01/EX-02/EX-05/EX-06/DOC-01/DOC-06 |

**关键指标：** ~5,300 测试通过（Py 2898 + ml_training 182 + Rs engine lib 1335 + core 380 + e2e 35 + reconciler_e2e 19）· ~65,000 行代码（Py+Rs）· 100% 双语注释 · fail-closed 设计 · 线程安全（Py）/ 零锁 single-owner（Rs）

**详细报告：** `docs/governance_dev/phase2_execution/`（执行总览 + PM 品质审核 + TW 注释审核 + 23 份变更日志）

---

## 16 条根原则（DOC-01 项目宪法 §5.1–§5.16，不可违背）

**V1 原版（§5.1–§5.10）：**

1. **单一写入口** — 所有订单/执行动作通过唯一受控入口，禁止研究/GUI/脚本直接写入交易所
2. **读写分离** — 研究/推理/学习/GUI/报告：只读或建议。写入权限极度受限、可审计、可锁定
3. **AI 输出 ≠ 即时命令** — AI 输出为建议/租约/解释，必须经 Decision Lease（带时效、可撤销）→ 本地复核 → 执行
4. **策略不能绕过风控** — 所有交易意图必须经 Guardian 审批
5. **生存 > 利润** — 先判断"不会螺旋崩溃"，再判断"能否盈利"
6. **失败默认收缩** — 不确定时默认保守：不开新仓、降频率、降风险、reduce-only
7. **学习 ≠ 改写 Live** — 学习平面与 Live 平面隔离，结果只能产出假设/证据/候选参数/变更提案
8. **交易可解释** — 每笔交易必须可重建：为什么、何时、风控审批、授权、执行、结果
9. **交易所灾难保护** — 本地止损 + 交易所条件单双重防线（DOC-01 §5.9）
10. **认知诚实** — 所有结论必须区分：事实 / 推断 / 假设。外部数据（新闻/情绪）默认推断级

**V2 新增（§5.11–§5.16）：**

11. **Agent 最大自主权** — P0/P1 硬边界内，Agent 完全自主决定：币种、策略、参数、时机。Operator 只设硬边界
12. **持续进化** — 系统必须从交易行为中自动学习（当前 live 阶段：Paper/Live 双轨验证→参数进化，渐进放权框架在 Phase 6 实施）
13. **AI 资源成本感知** — 每次 AI 调用计费。cost_edge_ratio ≥ 0.8 → 建议关仓
14. **零外部成本可运行** — 基础运营仅需 L0+L1（Ollama + 免费搜索），云端 AI = 增强层
15. **多 Agent 协作** — 5 Agent（Scout/Strategist/Guardian/Analyst/Executor）+ Conductor 编排，正式对象通信
16. **组合级风险意识** — 监控关联曝险、策略重叠持仓、资金分配合理性、大盘下行时总曝险收缩

**优先级序：** 账户生存 > 风控治理 > 系统健康 > 审计可追溯 > 人类终审 > 真实 Net PnL > 自主能力进化

**实施准则：** 认知调制 ≠ 能力限制 — Agent 压力下更审慎的方式是提高决策门槛，不是关闭能力。虚拟稀缺性被明确否决。（衍生自原则 #11）

---

## 治理架构总览

```
[H0 本地门控]     零成本确定性判断（健康/资格/风险包络）— 永远第一道
[SM-01 授权]      8 状态 · 16 转换 · fail-closed · 终态不可回流
[SM-04 风控]      6 级风险（NORMAL→CIRCUIT_BREAK）· 升级自动/降级需审批
[SM-02 决策租约]   9 状态 · TTL 自动到期 · AI→Lease→复核→执行
[EX-04 对账引擎]   5 类结果（MATCH/MISMATCH/MISSING）· 触发风控升级（Rust event_consumer 直写 DB）
[EX-06 多Agent]    OpenClaw Conductor + Scout/Strategist/Guardian/Analyst/Executor
[EX-05 学习]       L1→L5 五级门控 · 逐级解锁能力 · L5 需 Operator 审批
[EX-07 感知面]     FACT/INFERENCE/HYPOTHESIS 认知标记 · 新鲜度追踪
[DOC-07 审计]      append-only JSONL · 不可修改不可删除 · 自动轮转
```

---

## 治理合规矩阵

22 份治理 SPEC 接入率 **20/22 = 91%**（SM-01 / SM-02 / SM-03 / SM-04 / EX-01 / EX-02 / EX-04 / EX-05 / EX-06 / DOC-07 全部 ✅）。
未接入：`scout_routes.py`（独立运行时）。`paper_live_gate.py` 在 1C-3-F 后随 Python paper engine 一同退场。

> 详细完成度 / 工程目标 vs 实现矩阵已归档至 `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`（含早期 A-J 表 + Batch 9B 缺口列表，因 ARCH-RC1 后大幅过期）。当前 forward 计划见 `TODO.md`。

---

## OpenClaw 集成

> OpenClaw 定位：通信+运维层，不碰交易决策。Python 本地 = 交易 Agent 核心。

### 当前集成架构

```
┌─────────────┐                    ┌─────────────────────┐
│  OpenClaw   │ ── REST POST ──▶  │  scout_routes.py    │
│  (中枢)     │   /scout/market-  │  (5 端点 · Token 认证)│
│  Gateway    │   signal + alert  │         ▼            │
│  :18789     │                    │  ScoutAgent+MessageBus│
└─────────────┘                    │         ▼            │
┌─────────────┐                    │  PipelineBridge     │
│  Bybit API  │ ── WebSocket ──▶  │  (on_tick 本地扫描)   │
└─────────────┘                    └─────────────────────┘
```

### 后续整合计划（非紧急）

| ID | 内容 | 优先级 |
|----|------|--------|
| OC-1 | Webhook 告警通道（异常→OpenClaw→Telegram） | 高 |
| OC-2 | Telegram 通道配置 | 高 |
| OC-3 | 多通道分级告警（P0→紧急群 / P1→常规群） | 中 |
| OC-4 | MCP PostgreSQL 接入（自然语言查交易数据） | 中 |
| OC-5 | Cron 精细化健康心跳（待 OpenClaw --exec flag） | 低 |
| OC-6 | Sub-agent 异步回测（周频 Evolution 网格搜索） | 低 |
| WS-1 | FastAPI WebSocket/SSE 实时推送（替代 30s 轮询） | 中 |

详细方案见 `TODO.md` "OpenClaw 深度整合" 章节

---

## 硬边界（永远不可违背）

```python
# ── Live_Ready 状态（2026-04-18 LIVE-GATE-BINDING-1 ✅ 后更新）────────────
# LIVE-P0/P1/P2 代码完整，0 真实 live 流量。真实 live 门控 = 5 项全绿：
#   1. Python live_reserved global mode + Operator 角色 auth
#   2. OPENCLAW_ALLOW_MAINNET=1 env var（Rust 侧，LIVE-GUARD-1，仅 Mainnet）
#   3. secret slot 有 api_key+api_secret（Mainnet env var fallback 已封闭）
#   4. authorization.json HMAC-SHA256 签名 + 未过期 + env_allowed 匹配
#      路径：$OPENCLAW_SECRETS_DIR/live/authorization.json
#      检查点：build_exchange_pipeline 启动 + main.rs 每 5 min re-verify
#      失效 → engine 优雅 shutdown；涵盖 LiveDemo + Mainnet
#   5. Python Operator 角色 auth
# execution_authority：Rust 侧仅为 P0/P1 denylist 字符串常量
#                     （claude_teacher/applier.rs:226），非真实授权逻辑
decision_lease_emitted  = False
max_retries             = 0                          # Bybit API timeout → fail-closed，不重试

# 永不允许（LIVE-GATE-BINDING-1 后硬边界）：
# - 绕过 live_reserved global mode 直接启动 live session
# - 自动修改 engine trading_mode 为 live（需 operator 显式配置）
# - Bybit API retCode != 0 → fail-closed，不重试
# - Mainnet 下无 OPENCLAW_ALLOW_MAINNET=1 env var（LIVE-GUARD-1）
# - Mainnet 下试图用 BYBIT_API_KEY/SECRET env var 作为唯一凭证来源
# - Live（含 LiveDemo）下没有有效 authorization.json 即 spawn pipeline
# - 不经 Python _write_signed_live_authorization() 手动写 authorization.json
# - 伪造 AI 调用或交易活动
# - 缩仓监控：回撤 ≥15% → 自动撤销 execution_authority + 平仓 + 冻结 GovernanceHub
```

---

## 部署

**跨平台**：项目必须随时可部署至 macOS（路径不硬编码 / LLM 抽象 / systemd→launchd 可迁移 / 无 Linux-only 依赖）。详见 CLAUDE.md §七。

```bash
# API 服务器（Linux: systemd，开机自启；macOS: launchd 可迁移）
systemctl --user status openclaw-trading-api    # 端口 8000
systemctl --user status openclaw-gateway        # OpenClaw + Tailscale HTTPS
systemctl --user status openclaw-watchdog       # 引擎存活监控 + 自动重启

# Grafana
cd docker_projects/monitoring_services && docker compose up -d   # 端口 3000

# 一键启动 Paper Trading
bash helper_scripts/start_paper_trading.sh
```

### Mac dev-only 模式（开发环境，不参与交易）

**使用场景**：Mac 端只做开发（编辑 / build / test / commit / auto-push），Linux trade-core 是唯一 OMS。两端共用同一个 Bybit demo API key —— Mac 跑 engine 会与 Linux 撞单（违反根原则 #1「单一写入口」）。

**启用 dev-only**（重命名 secret slot 让 engine 找不到 credentials → fail-closed）：
```bash
cd "$OPENCLAW_SECRETS_DIR" && for s in demo live read_only; do
  [[ -d "$s" ]] && mv "$s" "$s.dev_disabled_$(date +%Y%m%d)"
done
rm -f "$OPENCLAW_SECRETS_DIR/live/authorization.json"   # 顺便撤 live 签章
```

**还原**（未来想 Mac 跑测试 / 回到 deploy 模式）：
```bash
# 用实际后缀替换 SUFFIX（例如 .dev_disabled_20260421）
cd "$OPENCLAW_SECRETS_DIR" && for s in demo live read_only; do
  [[ -d "$s.dev_disabled_"* ]] && mv "$s.dev_disabled_"* "$s"
done
# authorization.json 需透过 GUI /api/v1/live/auth/renew 重簽（HMAC 与本机 IPC_SECRET 绑定，不能从 Linux copy）
```

效果：Mac engine 即使被误启也无 credentials 可连 Bybit → 0 订单冲突；Linux trade-core 文件分属不同主机，完全不受影响。

---

## 常用脚本 (Common Scripts)

完整清单见 [`helper_scripts/SCRIPT_INDEX.md`](helper_scripts/SCRIPT_INDEX.md)。

### 生命周期 (Lifecycle)

| 脚本 | 用途 | 何时用 |
|------|------|--------|
| `restart_all.sh` | 停+启 Rust 引擎 + API（**不动数据**）。`--rebuild` 先编译 engine binary（PYO3-ELIMINATE-1 Phase 3 後唯一建構產物）。 | 日常：改代码后部署、unstick 卡住的进程 |
| `stop_all.sh` | 优雅停止 + 建 `engine_maintenance.flag`（watchdog 不会自动拉起）。`rm flag` 或 `restart_all.sh` 恢复。 | 停机维护、手工 debug |
| `clean_restart.sh` | 停 → 交易所平仓（demo 强制，`--include-live` 可选 mainnet）→ 归档 runtime → 编译检查 → 重启 → watchdog 验证。**保留 paper_state 与 DB**。 | 清空交易所持仓、解决 runtime snapshot 污染 |
| `fresh_start.sh` ★ | `clean_restart` 全部动作 + **清空 DB 经验数据**（fills/intents/orders/outcomes/signals/agent/learning 状态）。**保留**：市场数据、已训练模型、LinUCB archive。 | 开发阶段结束、需要从零历史冷启动验证 |
| `start_paper_trading.sh` | API 就绪后自动启 Paper Trading 会话（供 systemd/cron 调用）。 | 开机自动化（已接 systemd） |

### 灰度 / 监控 (Canary & Monitor)

| 脚本 | 用途 |
|------|------|
| `canary/engine_watchdog.py` | 引擎存活检查。`--status` 打 JSON（`engine_alive` + 各 pipeline age）；`--stale-threshold` 设过期秒数。已包装为 `openclaw-watchdog.service` user unit。 |
| `canary/replay_runner.py` | 灰度回放：读 canary JSONL 与 Python 基线比对。 |

### 数据库 (Database)

| 脚本 | 用途 |
|------|------|
| `db/fresh_start_reset.py` | DB 经验数据清理核心。`--report-only`（默认）/`--dry-run`/`--execute --confirm "FRESH_START_YYYY_MM_DD"`。通常透过 `fresh_start.sh` 调用（会一并停引擎）。 |

### 定时任务 (Cron)

| 脚本 | 用途 |
|------|------|
| `cron_daily_report.sh` | 每日 UTC 0:00 采集 Paper 指标 + Telegram 推送。 |
| `cron_observer_cycle.sh` | 每 5 分钟 Observer 循环 + runtime snapshot 桥接。 |

### 快速对照：选哪个重启？

```
改了代码需部署              → restart_all.sh --rebuild
只想清交易所持仓             → clean_restart.sh --yes
开发告一段落要清 PnL/勝率    → fresh_start.sh --yes
临时停机 debug              → stop_all.sh
```

---

## 参考文件

| 类别 | 位置 |
|------|------|
| 完整项目指令 | `CLAUDE.md` |
| 当前工作计划 | `TODO.md` |
| 审计报告 | `docs/governance_dev/audits/` |
| QC 量化审查 | `docs/CCAgentWorkSpace/QC/workspace/reports/` |
| 工作日志 | `docs/worklogs/` |
| 变更历史 | `docs/CLAUDE_CHANGELOG.md` |
| 治理文件（SPEC 源） | Cowork `01_source_documents/` |
| Phase 2/3 执行记录 | `docs/governance_dev/phase2_execution/` / `phase3_integration/` |

GitHub: [yunancun/BybitOpenClaw](https://github.com/yunancun/BybitOpenClaw)
