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

## 当前状态 (2026-04-30 21:10 CEST · **Live_Ready ⚠️**)

**运行事实**：Mac/Linux source HEAD `a9fce24`（code-bearing runtime checkpoint）；engine、API、watchdog、gateway 均在线；watchdog `engine_alive=true`，demo/live snapshots fresh，paper inactive by design。最新 passive healthcheck 总结为 **WARN** exit 0（WARN `[4]`/`[11]`/`[33]`/`[38]`/`[40]`，无 pipeline-dead FAIL）。

**当前主问题**：post-reload maker 执行质量接近目标（post-2026-04-29 reload slice maker_like **73.23%** / fee_drop **59.32%**），但 7d rolling 仍低（25.6%，diluted by pre-reload samples）；grid lifecycle drift 是真实信号（`[38]` live_demo p50 1.7min vs demo 4.8min），grid_levels 10→7 + blocked_symbols 11 个已于 2026-04-29 部署，观察中。主指标是 post-fee `net_bps_after_fee`，PnL / win-rate 仅作辅助。

**已关闭并归档**：62-finding remediation Batch A-F、STRKUSDT P0 wave、Wave A-H、旧 Wave 1-3 叙事不再是 active mainline。清理前快照保存在：
- `docs/archive/2026-04-30--README-pre-cleanup-snapshot.md`
- `docs/archive/2026-04-30--TODO-pre-cleanup-snapshot.md`
- `docs/archive/2026-04-30--CLAUDE-pre-cleanup-snapshot.md`

**已部署但仍需观察**：
- Strategy edge models：MA/BB/grid maker buffer、grid `blocked_symbols`、reject cooldown、`min_grid_step_bps`、`cost_floor_multiplier`、scanner posterior LCB routing、MA `min_trend_snr` 已进入 runtime。
- Dust residual prevention：Bybit full-close primary path 使用 `qty=0 + reduceOnly + closeOnTrigger`；仍需一笔真实 Demo/Live close-path 证明 exchange-side 残留处理有效。
- MLDE demo autonomy：`[35]` / `[36]` / `[37]` PASS。Demo 可自动受限调参；live/live_demo 自动改参仍必须走 GovernanceHub + Decision Lease + 5 live gates。

**下一步主路径**：G2-02 ma_crossover counterfactual replay（~2026-05-03）→ G2-01 PostOnly settlement（~2026-05-07/08）→ P0-3 edge decision（~2026-05-15）→ LG-2/3/4/5 Live gates → true live。

**Active queue**：见 `TODO.md`。完整上下文和硬边界见 `CLAUDE.md`。

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

**关键指标：** ~6,200 测试通过（Py 2898 + ml_training 182 + Rs engine lib **2381** + core 380 + e2e 35 + reconciler_e2e 19）· ~65,000 行代码（Py+Rs）· 100% 双语注释 · fail-closed 设计 · 线程安全（Py）/ 零锁 single-owner（Rs）

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

当前 OpenClaw/Scout 后续只保留在 `TODO.md` active queue；旧深度整合叙事已归档。

---

## 硬边界（永远不可违背）

README 只保留入口级摘要；完整硬边界以 `CLAUDE.md` §四为准。

- 真实 live 必须同时满足 Python live_reserved、Operator 角色认证、`OPENCLAW_ALLOW_MAINNET=1`、secret slot、signed `authorization.json` 五项 gate。
- `execution_authority` 在 Rust 侧仅是 P0/P1 denylist 字符串常量，不是真实授权逻辑。
- LiveDemo 走 live-grade 控制流；demo endpoint 不放宽 authorization、TTL 或 risk gate。
- 禁止手写 `authorization.json`、绕过 Operator auth、自动切 live、伪造 AI/交易活动，或在 Bybit `retCode != 0` 后重试成交路径。

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
