# README.md stale extract — archived 2026-05-06

Archived from `srv/README.md`. The content below was 4 days stale (HEAD `a7b93d5` snapshot, pre-REF-20 closure, pre-Decision-Lease retrofit) and contradicted current state in `srv/CLAUDE.md` §三 + memory. Source README HEAD at archive time: `67b95808`.

Live state lives in `srv/CLAUDE.md` §三 and `srv/memory/MEMORY.md`.

---

## "当前状态 (2026-05-02 · Live_Ready ⚠️)" — verbatim extract

**HEAD**: `a7b93d5`（Mac/Linux/origin 同步）· **Engine deployed**: `eaf0c7e`（PRE-LIVE-3，Mac 领先 6 commit 待下次 deploy 一次性 promote）

**运行事实**：engine、API、watchdog、gateway 均在线；watchdog `engine_alive=true`，demo + live_demo snapshots fresh，paper inactive by design。最新 passive healthcheck 总结为 **WARN**（多项真实 WARN）。

### 5 策略 7d gross PnL（demo + live_demo · PA 直查 trading_ai DB · 2026-05-02）

| 策略 | demo fills | demo PnL | live_demo fills | live_demo PnL | 结论 |
|---|---:|---:|---:|---:|---|
| `grid_trading` | 642 | **+4.98** | 520 | **+0.79** | 唯一 net positive |
| `ma_crossover` | 378 | -5.09 | 257 | -1.60 | net negative，ATR-SNR 后仍未转正 |
| `funding_arb` | 99 | -5.96 | 0 | 0 | V2 弃策略路径（commit `a19797d`）；demo 收 EDGE-DIAG-2 样本至 2026-05-16 |
| `bb_breakout` | 34 (14d) | -0.75 | 0 | 0 | live_demo **14d 0 fires**（FIX-26-DEADLOCK-1 修了 demo） |
| `bb_reversion` | 7 | -0.16 | 0 | 0 | live_demo dormant |
| **合计 7d gross** | | **-6.98** | | **-0.81** | 5 策略合计 net negative |

### 当前主问题
- **Edge 仍负**：5 策略 7d gross net **-6.98 USDT**；grid 唯一 +5.77，其它 4 个合计 -11.96。等 ~05-15 P0-3 决策（A 翻正/B 仍负/C 部分改善）。
- **`[33]` maker fill rate live_demo 7d=36.6%** < 40% PASS 线（healthcheck 假绿，drift 待修）
- **`[40]` 24h slippage live_demo -92 bps**（BUSDT 110017 reject loop，funding_arb V2 弃策略残仓）
- **Decision Lease 在 Rust 热路径 0 触发** — R-04 last-mile 漏做（PA + FA archaeology 确认；非 spec design）；路径 A retrofit 待开（P0-GOV-1）

### 已部署但仍需观察
- Strategy edge models：MA/BB/grid maker buffer、grid `blocked_symbols`、reject cooldown、`min_grid_step_bps`、`cost_floor_multiplier`、scanner posterior LCB routing、MA `min_trend_snr` 已进入 runtime
- Dust residual prevention：Bybit full-close primary path 使用 `qty=0 + reduceOnly + closeOnTrigger`；2026-04-30 已真实 Demo/LiveDemo `qty=0` close fills 验证
- MLDE demo autonomy：`[35]` / `[36]` / `[37]` PASS。Demo 可自动受限调参；live/live_demo 自动改参仍必须走 GovernanceHub + Decision Lease + 5 live gates
- LG-5 W3 FUP-1 reviewer 接线：sibling CC commit `463890d` 已 land；待下次 `restart_all.sh --keep-auth` 启动 reviewer scheduler，验证 24h `governance_audit_log` 累积

### 18 Live Blocker（PA + FA cold panorama 整合，按重要性排序）

详细见 `CLAUDE.md` §三。前 5 大：
1. 5 策略 7d gross net negative — P0-3 ~05-15 决策
2. LG-2 H0 blocking IMPL（RFC only，0 行 IMPL）
3. LG-3 provider pricing binding IMPL
4. LG-4 supervised live IMPL（state machine 0 行）
5. **Decision Lease 在 Rust 热路径 0 触发** — 路径 A retrofit（1.5-2 E1）

### 下一步主路径

`post-deploy edge observation + LG-5 reviewer activation → G2-02/G2-01 结论 → P0-3 edge decision (~05-15) → LG-2/3/4 IMPL + Decision Lease retrofit + Live infra (HTTPS / credential rotation / runbook) → true live`

**Live target**：~05-23 乐观 / ~05-30 中位 / ~06-15 悲观为规划带。**panorama 评估悲观更可能**（5 LG IMPL + Decision Lease retrofit + 18 blocker）。

**Active queue**：见 `TODO.md` P0/P1/P2 三层工作流程。完整上下文和硬边界见 `CLAUDE.md`。

**已关闭并归档**：62-finding remediation Batch A-F、STRKUSDT P0 wave、Wave A-H、旧 Wave 1-3 叙事、4-day codex audit closure 不再是 active mainline。归档：
- `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md`
- `docs/archive/2026-05-02--TODO-pre-trim-snapshot.md`
- `docs/archive/2026-04-30--{CLAUDE,TODO,README}-pre-cleanup-snapshot.md`

---

## "治理合规矩阵" — verbatim extract

22 份治理 SPEC 接入率 **20/22 = 91%**（SM-01 / SM-02 / SM-03 / SM-04 / EX-01 / EX-02 / EX-04 / EX-05 / EX-06 / DOC-07 全部 ✅）。
未接入：`scout_routes.py`（独立运行时）；`paper_live_gate.py` 在 1C-3-F 后随 Python paper engine 一同退场。

> 详细完成度 / 工程目标 vs 实现矩阵已归档至 `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`（含早期 A-J 表 + Batch 9B 缺口列表，因 ARCH-RC1 后大幅过期）。当前 forward 计划见 `TODO.md`。

**Why archived**: "20/22 = 91%" 數字未經 Sprint 1+2+3+4 + Decision Lease retrofit 後重新校驗；現行治理覆蓋率以 `srv/docs/governance_dev/SPECIFICATION_REGISTER.md` 為準（README 原寫 `docs/SPECIFICATION_REGISTER.md` 不存在，路徑錯）。

---

## "OpenClaw 集成" + 后续整合计划 OC-1..OC-6 / WS-1 — verbatim extract

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

### 后续整合计划（非紧急，TODO P2-COND backlog）

| ID | 内容 | 优先级 |
|----|------|--------|
| OC-1 | Webhook 告警通道（异常→OpenClaw→Telegram） | 高 |
| OC-2 | Telegram 通道配置 | 高 |
| OC-3 | 多通道分级告警（P0→紧急群 / P1→常规群） | 中 |
| OC-4 | MCP PostgreSQL 接入（自然语言查交易数据） | 中 |
| OC-5 | Cron 精细化健康心跳（待 OpenClaw --exec flag） | 低 |
| OC-6 | Sub-agent 异步回测（周频 Evolution 网格搜索） | 低 |
| WS-1 | FastAPI WebSocket/SSE 实时推送（替代 30s 轮询） | 中 |

**Why archived**: OC-1..6 / WS-1 是 Phase-2 era backlog，與 CLAUDE.md §十一「Linear-only active / Slack DECLINED / Notion FROZEN / Coupler+MotherDuck DECLINED」直接衝突 — README 此表 reintroduces 已被 declined 的工具為「高/中」優先。當前外部工具策略以 CLAUDE.md §十一 為準。
