# 玄衡 TODO — 活躍派工佇列

**版本**：v61（v60 → v61 重構：400 → 250 行 / 過時歸檔 / session·wave·sprint 結構化 / reference ~30 條完整）
**日期**：2026-05-21
**Session**：v5.7 + v5.8 13-module autonomy expansion (44-55w Y1 + 21-32mo 達 95% autonomy)
**v60 完整歷史 archive**：`docs/archive/2026-05-21--todo_v60_archive.md`

---

## §0 摘要

- **Current Sprint Phase**：Sprint 1A-α + Wave 2 + Wave 2.5 + Sprint 1A-β + **Sprint 1A-γ DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED** (PM-signed 2026-05-21；15/15 deliverable 全 land；M8 + V109 sequential final)；Sprint 1A-δ READY-TO-DISPATCH
  - 註：DESIGN-DONE = spec/ADR/runbook 文件 land；IMPL-PENDING = 無對應 IMPL 代碼；RUNTIME-NOT-APPLIED = sql/migrations/ 本地 max=V098 / Linux PG `_sqlx_migrations` max=96 / 10 target table (health_observations / degradation_state / replay_divergence_log / reward_weight_history / decision_lease_lal_tiers / lal_eligibility_log / decay_signals / strategy_lifecycle / earn_movement_log / hypotheses) pg_class 0 hits（per 2026-05-21 acceptance audit）
- **Current Wave**：Sprint 1A-δ READY 派 (M5/M12/M13 stubs)；**新增 Sprint 1A-ζ IMPL Prototype Spike phase**（PM push back 2026-05-21；W8.5-10；驗證 M1 LAL/M3/M11 critical path spec→IMPL 真實可行，避免 Sprint 4 first Live 才發現 spec gap 大幅 rework）— PA spike scope spec 進行中
- **Active P0**：`P0-EDGE-1`（5 strategy alpha-deficient）+ `P0-LG-3`（Wave 2.4 IMPL DISPATCH PENDING SPEC-READY 10d）+ `P0-OPS-1..4`（HTTPS / cred / legal / runbook）— Sprint 4 first Live W18-21 前必 closure
- **Next 24h operator action**：D+1 (2026-05-22) AM ① BB OpenClaw key 發行日 5 min query ② Phase 2a 14d verdict 視窗（clock @ 2026-05-22~23 UTC）30-60 min 三選一決議
- **Runtime**：engine PID 2934602 + API PID 2934665 + watchdog PID 2936560；最後 graceful restart 2026-05-21 13:31 UTC
- **Pending operator decision**：(1) Phase 2a verdict (D+1-D+2) (2) `P0-FUNDING-ARB-DECISION-FORCE` 升等 (3) Watchdog daemon R2 deploy 時機 (4) v5.8 16 CRITICAL 派發後 D+5 Sprint 1A-β readiness sign-off

---

## §1 Session / Wave / Sprint 路線圖

### §1.1 Current Sprint Banner

```
Sprint 1A-α   DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED (W0-1.5, 2026-05-21 PM-signed)  v5.7 12 prefix + PM signoff
Sprint 1A-修補 DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED (D+0~D+5, 2026-05-21)           v5.8 16 CR + Wave 2.5 paperwork
Sprint 1A-β   DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED (2026-05-21 PM-signed)          M1 LAL/M3/M6/M7/M11 DESIGN spec + 5 V### schema spec + 6 runbook (16 artifact / ~12,900+ 行；無 IMPL；V099+ migration 本地不存在；Linux PG max=96)
Sprint 1A-γ   DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED (2026-05-21 PM-signed)          M2/M4/M8/M9/M10 DESIGN spec + V105/V108/V109/V111 schema spec + V103 EXTEND outline + 2 runbook + 3 ADR (M3/M6/M7) (15 artifact / ~12,400+ 行；無 IMPL；V###未 apply)
Sprint 1A-δ   READY-TO-DISPATCH (W5.5-6.5)                                                       M5/M12/M13 interface stubs (ADR-0035/0039/0040 已 Wave 2 land)
Sprint 1A-ε   PENDING (W6.5-8.5)                                                                  integration verify + cross-ADR consistency audit + 45+ open Q audit + docs index 補
Sprint 1A-ζ   PENDING (W8.5-10) — **NEW PHASE 2026-05-21 PM push back**                            IMPL Prototype Spike (M1 LAL + M3 health + M11 replay critical-path 驗證 spec→IMPL 可行；30-50 hr / 1-2 wall-clock week)
```

> **狀態語言**（per 2026-05-21 acceptance audit）：
> - **DESIGN-DONE**：spec / ADR / runbook / schema spec 文件 land 在 docs/ 並通過 PM signoff
> - **IMPL-PENDING**：對應 Rust / Python / SQL 實作未開始（grep `nightly_replay|cf_quality|replay_divergence|earn_reconcile|lal_audit|decay_signal` in helper_scripts/api/python → 0 hits）
> - **RUNTIME-NOT-APPLIED**：sql/migrations/ 本地 max=V098；Linux runtime DB `_sqlx_migrations` MAX(version)=96 / COUNT=93；10 個 target table pg_class 0 hits

### §1.2 Sprint Progression Table（Sprint 1A → Y3）

| Sprint | Calendar | 主要工作 | 工時 (hr) | Status |
|---|---|---|---|---|
| 1A-α | 2026-05-21 done | v5.7 baseline + 4 follow-up | 75-105 | DESIGN-DONE / IMPL-PENDING |
| 1A-修補 | 2026-05-21 done | 16 CRITICAL + Wave 2.5 paperwork | 1,007-1,453 並行 | DESIGN-DONE / IMPL-PENDING |
| 1A-β | 2026-05-21 done | M1 LAL/M3/M6/M7/M11 DESIGN + V106/V107/V110/V112/V113 schema spec (本地無 .sql 檔；Linux PG 未 apply) + 6 runbook | 310-460 並行 (10 sub-agent + 3 recovery) | DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED |
| 1A-γ | 2026-05-21 done | M2/M4/M8/M9/M10 DESIGN + V105/V108/V109/V111 schema spec + V103 EXTEND outline + 2 runbook + 3 ADR (M3/M6/M7) | 240-360 並行 (6 + 7 recovery + 2 sequential) | DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED |
| 1A-δ | W5.5-6.5 (~2026-05-28 開派) | M5/M12/M13 stubs + ADR-0035/0039/0040 + V114-116 partial | 75-120 | READY-TO-DISPATCH |
| 1A-ε | W6.5-8.5 | integration verify + cross-ADR consistency audit + docs/README index 補 + 45+ open Q audit | 60-100 | ⏳ |
| **1A-ζ** | **W8.5-10 (NEW; PM push back 2026-05-21)** | **IMPL Prototype Spike — Track A M1 LAL + V112 PG apply / Track B M3 health + V106 / Track C M11 replay + V107；驗 Sprint 1B IMPL 開始前 spec 真實可行** | **57-86 (含 buffer)** | **⏳ PENDING — PA spike scope spec 進行中** |
| 1B | W9-12 | v5.7 baseline + C10 Stage 1 Demo + Earn first stake + M3 partial | 165-220 | ⏳ |
| 2 | W12-15 | Alpha Tournament + M4 stage 1 + M10 Tier A + M8 read-only | 280-400 | ⏳ |
| 3 | W15-18 | Top-1 Unlock SHORT build + Stage 0 shadow + M11 nightly + M3 detectors | 280-380 | ⏳ |
| **4** | **W18-21 (~2026-09 初)** | **★ Top-1 LIVE $500 first time ★** + Top-2 + Options Stack 1 + M1 LAL Tier 1 + M9 read-only | 360-490 | ⏳ |
| 5 | W21-24 | Top-2 LIVE + Top-3 + Options Stack 2 + M3 auto-degradation | 305-440 | ⏳ |
| 6 | W24-27 | Top-4 + C13-VRP + Funding short + M12 maker-vs-taker | 305-440 | ⏳ |
| 7 | W27-30 | Top-5 + Advisory Allocator + M1 Tier 2 + M6 Advisory + M9 manual A/B | 280-410 | ⏳ |
| 8 | W30-33 | Decay (M7) IMPL + M4 stage 2 + M3 recovery + M8 alerting | 360-490 | ⏳ |
| 9 | W33-36 | Continue Advisory + Copy Infra build + M12 slicing | 255-360 | ⏳ |
| 10 | W36-44 末 | Y1 Review + Copy Trading Evidence Gate + Overlay verdict + M13 spec | 190-260 | ⏳ |
| **Y1 末** | **W44-55 (~2027 Q1-Q2)** | **autonomy 66%** | – | – |
| Y2 Q1-Q2 | ~21-24 mo | 6mo Advisory + 80% approval → Auto-Allocator activation → autonomy 90% | – | – |
| Y3 Q2 | ~32 mo | M10 Tier C-E / M12 cross-venue / M13 Y3+ / M5 streaming → autonomy 95% | – | – |
| **Y1 Total** | **44-55w** | – | **3,500-5,200 hr** | – |

### §1.3 5 Strategy × Current Stage Roster

| Strategy | Current Stage | Next Stage | Sprint ETA | Notes |
|---|---|---|---|---|
| C10 funding harvest | Stage 1 Demo（Sprint 1B） | Stage 4 LIVE | Sprint 4 | demo spot leg paper-only Phase 1 |
| Unlock SHORT | Stage 0 DRAFT | Stage 0R Replay Preflight | Sprint 3 W15-18 | Tokenomist signal dep |
| Pairs trading | Stage 0 DRAFT | Stage 0 (Alpha Tournament) | Sprint 2 W12-15 | BTC/ETH cointegration |
| C13 defined-risk | Stage 0 DRAFT | Stage 0 (Alpha Tournament) | Sprint 2-6 | Bybit options demo 待驗 |
| Funding short-only | Stage 0 DRAFT | Stage 0 (Alpha Tournament) | Sprint 2-6 | high-threshold > 30% annualized |

**詳細 Strategy × Stage gate matrix**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_business_consolidation.md` §6

### §1.4 Operator Action Checklist（D+0~D+6 + Sprint 4 first Live ETA）

| 日期 | Action | 預期時間 | 提醒 trigger | 卡進度後果 |
|---|---|---|---|---|
| **D+0 (2026-05-21)** | ✅ **簽 D1-D5 已完成**（v5.8 16 CRITICAL / M1→LAL / 工時上修 / M13 Y3+ / AMD-2026-05-21-01）| 30 min | done | – |
| **D+1 (2026-05-22)** | OpenClaw API key 發行日（Bybit Web UI 查 last edited，5 min）— v5.7 leftover | 5 min | PM ping AM | 阻 Sprint 1B Earn first stake |
| **D+1-D+2** | **Phase 2a 14d verdict 三選一決議**（calibration r2 / accept 35% / Phase 2b LiveDemo）— clock @ 2026-05-22~23 UTC | 30-60 min | clock 觸發 | 阻 P0-EDGE-1 closure → Sprint 4 first Live |
| **D+2-D+3** | review AMD-2026-05-21-01 草案（CC + PM draft 後；protected vs opt-in scope） | 15-30 min | CC + PM ping | 阻 CR-3 + 7 auto-apply module |
| **D+3** | 提供 P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 closure ETA（填 §10 P0 precondition table） | 30 min | PM ping | 阻 Sprint 4 first Live + CR-10 |
| **D+4** | batch review 4 ADR draft（ADR-0034 LAL / 0036 M8 anomaly / 0037 M9 A/B / 0038 M11 replay） | 30-60 min | TW + PM ping | 阻 CR-2/5/7 + V### spec |
| **D+5** | **batch sign-off 12 ADR + 1 AMD**（ADR-0030~0033 + 0034 + 0035~0040 + 0041 + AMD-2026-05-21-01） | 60-90 min | PM ping | 阻 Sprint 1A-β 派發 |
| **D+5** | Console tab 歸屬決策（4 tab × 2-4 sub-section；不擴張 16 tab） | 15-30 min | A3 + PM ping | 阻 CR-11 + Sprint 4 M1 IMPL |
| **D+5** | Bybit Tokenomist trial expiry 確認（M4 dependency）+ 續訂 / fallback vendor | 5-10 min | BB ping | 阻 Sprint 6-7 M4 active |
| **D+5-D+6** | Sprint 1A-β 派發 readiness 12 check + final sign-off | 30 min | PM ping | – |

**Operator 親手時間 D+0~D+6 ≈ 3.5-5 hr**（分散 6 天，平均 30-50 min/day）；PM 每次 operator 進 session 主動 check 當天 action

### §1.5 Sprint 1A-α + Wave 2 + Wave 2.5 closure pointer

**狀態**（per 2026-05-21 acceptance audit）：
- Sprint 1A-α **DESIGN-DONE / IMPL-PENDING**（PM-signed `26ee2f06`；v5.7 12 prefix 為文件級 patch）
- Wave 2 v5.8 16 CR **DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED**（`77d5c54e`；spec/ADR land，無 IMPL，9 V### 為 placeholder spec 非 SQL 檔）
- Wave 2.5 paperwork **DESIGN-DONE**（`957491ee`；ADR-0035/0037 補位 + 反向 ref + README 索引漂移修）
- Sprint 1A-β D+5~D+6 dispatch readiness 12-check **10/12 ✅**（剩 #8 #9 operator-bound）

**重要 caveat**（acceptance audit 揭露）：sql/migrations/ 本地 max=V098；Linux PG `_sqlx_migrations` MAX(version)=96 / COUNT=93；V099+ migration file 尚未產出；V97/V98 file 存在但未 apply。10 個 target table (health_observations / degradation_state / replay_divergence_log / reward_weight_history / decision_lease_lal_tiers / lal_eligibility_log / decay_signals / strategy_lifecycle / earn_movement_log / hypotheses) pg_class 0 hits。所有「DONE」措辭 = 文件 land 級別，不代表 runtime ready。

**完整 12-check 表 + closure narrative + 反向 attack mitigation + commit chain + reference**：`docs/archive/2026-05-21--sprint_1a_alpha_repair_closure.md` §A-§F；Sprint 1A-β PM signoff narrative 在同檔 §G（無獨立 1A-β PM signoff file）

### §1.6 v5.8 Wave 2 16 CRITICAL must-fix closure pointer

**狀態**：16/16 **DESIGN-DONE** 2026-05-21（commit `77d5c54e`，spec/ADR/runbook 文件級 land；無 IMPL 代碼）+ Wave 2.5 paperwork（commit `957491ee`）；CRITICAL 合計 ~1,007-1,453 hr（est. 含未來 IMPL）/ D+0~D+5 並行 5-10 sub-agent（per 2026-05-21 acceptance audit）。

**完整 16 CR 表（Owner / 工時 / ETA）+ 統計**：`docs/archive/2026-05-21--sprint_1a_alpha_repair_closure.md` §B


---

## §2 架構邊界 + 硬不變式（cross-ref CLAUDE.md）

- **產品**：玄衡 · Arcane Equilibrium；交易所目標僅 Bybit（per ADR-0033 amendment：Binance market data only / DEX 不允）
- **權威分工**：Rust `openclaw_engine` = 交易/風控/策略 config/執行；Python = control plane/GUI/bridge/replay/5-Agent host
- **GUI**：FastAPI console `trade-core:8000/console`（Vanilla JS）；外部 OpenClaw Gateway 僅通訊/mobile/supervisor
- **5-Agent runtime**：Scout / Strategist / Guardian / Analyst / Executor；Cloud L2 走 supervisor escalation + budget/model config + `agent.ai_invocations` ledger
- **權威 agent lineage**：StrategySignal → StrategistDecision → GuardianVerdict → ExecutionPlan → Decision Lease/idempotency → ExecutionReport
- **Graduated Canary**（AMD-2026-05-15-01）：Stage 0 shadow → Stage 0R Replay Preflight → Stage 1 Demo micro-canary 7d → Stage 2 demo 14d → Stage 3 demo 21d → Stage 4 LIVE_PENDING
- **5-gate live**：Python `live_reserved` + Operator role auth + `OPENCLAW_ALLOW_MAINNET=1` + secret slot + signed unexpired `authorization.json`
- **DOC-08 §12 9 條安全不變量** + **SM-04 ladder** + **CLAUDE.md §二 16 原則** 強制 binary fail-closed，不被 graduated canary 觸碰
- **新增（v5.8）**：M1 LAL（Layered Approval Lease 0-4 Tier）/ M4 self-supervised DRAFT writeback / M2 overlay state machine — 全部走 5-gate 不繞 governance

---

## §3 Runtime Evidence

- **Phase 2a 14d obs verdict 視窗**：2026-05-22~23 UTC；QA D1 T+72h projection AC-1/2/4 FAIL → operator 三選一決議
- **LG-1 P0 DONE 2026-05-21 PASS WITH 1 KNOWN GAP**：H0 wired 18M+ ticks；fail-closed never fired 5h；衍生 `P2-LG1-DEMO-SLO-CARVEOUT`（已 closure 2026-05-21 commit `aa0780a3`）
- **LG-2 P0 DONE 2026-05-21 PASS WITH 1 CAVEAT**：startup assertion fire；production tick path 0 caller for `fee_source()` BY-DESIGN per spec §2.4
- **v56 P0 HALT cycle CLOSED 2026-05-20**：root cause UNRESOLVED → `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`（passive wait + H4 healthcheck [69] LIVE 2026-05-21）
- **D2 watchdog classifier R2 SOURCE LAND 2026-05-21**：4-gate + AMBIGUOUS_SOURCE_PATTERNS guard；207/207 PASS；deploy 等 operator 決定 daemon 重啟
- **stale signal**：`learning.edge_estimate_snapshots` 14d 內 0 rows（max=2026-05-07）→ 併入 P0-EDGE-1

---

## §4 P0 — True-Live Blockers（active only）

| ID | 狀態 | Owner | Acceptance Criteria | Next Action |
|---|---|---|---|---|
| `P0-EDGE-1` | 🔴 ACTIVE | QC + PA | **AC-A**: 5 textbook 策略 ≥ 3 個 demo 7d avg_net > 5bps（Wilson CI lower > 0），n ≥ 30 per-strategy<br>**AC-B**: portfolio gross daily PnL 7d MA > 0 USDT<br>**AC-C**: 若全策略 7d EV < 0，supervised path = 凍結至 alpha 修補有 demo 證據 | Sprint 2 Alpha Tournament（W12-15）+ 併入 `learning.edge_estimate_snapshots` stale follow-up |
| `P0-LG-3` | ⚠️ SPEC READY 10d, IMPL DISPATCH PENDING | PA spec → E1×7 | **AC-A**: spec v2 §2.4A 加 fee_source tick-time consumer scope<br>**AC-B**: DISPATCH 拍板條件 = operator 路線決議 OR 90d stale-detect 強制 IMPL<br>**AC-C**: V099/V100 migration Linux PG empirical dry-run mandatory | PA refresh dispatch plan；待 operator 拍板 |
| `P0-OPS-1..4` | 🔴 ACTIVE | PA + BB + E3 | **OPS-1**: HTTPS certbot + 4 service binding<br>**OPS-2**: credential rotation TTL + script<br>**OPS-3**: legal+ToS spec（Bybit ToS / KYC / 地理）<br>**OPS-4**: 第一天 30min runbook | 4 子項各自 owner；OPS-1 → OPS-2 序列 |

**Sprint 4 first Live W18-21 必前置條件**：P0-EDGE-1 + P0-LG-3 + P0-OPS-1..4 全 closure（per FA v5.8 §1.4 + PM verdict §六 風險點 #6）

---

## §5 P1 / P2 / P3 — Engineering Queue + Backlog

### §5.1 P1 Active Engineering Queue（v5.7 baseline + v5.8 新增）

| ID | 優先 | 任務 | AC / Next Action |
|---|---:|---|---|
| `P1-EDGE-2` (funding_arb) | 3 | ⚠️ PA D3 建議升 P0-FUNDING-ARB-DECISION-FORCE 待 operator 拍板 | operator 選項 (A) 砍策略 / (B) 增樣本 / (C) 接受 INSUFFICIENT；缺 deadline |
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch — STILL_ACTIVE | source 活躍；7d 共 66 review_live_candidate 全 verdict=defer；建議 90d cadence + 3 not-defer 或 180d 都 defer 觸發 review |
| `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 3 | v56 P0 未解 root cause；H4 healthcheck [69] LIVE → passive-wait 合規 | forensic `halt_audit.log` armed；passive wait + 90d review 2026-08-21 |
| `P1-LEASE-1` | 3 | 升 P1 from P2：清掃 terminal `lease.rs:303` + HashMap leak | 依賴 P0-LG-3 IMPL DISPATCH；工時 ~4-6h |
| `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` | 4 | Phase 1b spec §5.4 完整 dynamic backoff state machine | Phase 2a Demo PASS 後另開 PR；PA 估 ~130 LOC |

### §5.1.1 v5.8 24 H 級 ticket（按 module 分組；派發後 Sprint 1A-β-ε 期間並行補）

- **M2 Stage gate**：H-1 對齊 AMD-2026-05-15-01 / H-2 M6 Bayesian spec / H-3 M7 baseline calibration
- **M4-M8-M11**：H-4 M8 autoencoder Y2 spec / H-5 M9 variant Stage 路徑 / H-17 M9 framework validation + M4 leakage scan
- **M10-M12-M13**：H-6 M10 AUM trigger 數據源 / H-7 M5/M12/M13 trait slot
- **mutex**：H-8 M3/M8/M11 trigger mutual exclusion contract
- **missing module**：H-9 M14/M15/M16 處置（已決議 §5.2）
- **threshold**：H-10 M1/M3/M11 量化 threshold
- **forgetfulness attack**：H-11 §11 反向 attack 6 條
- **灰度事件**：H-12 嚴重度對照表
- **IPC + state machine test**：H-13 Rust IPC message type / H-14 state machine 4 SM proptest
- **migration + SLA**：H-15 V### dry-run / H-16 SLA stress 5 hot path
- **cross-language + sibling file**：H-18 1e-4 fixture harness / H-19 13 module sibling file structure
- **CI + secret slot**：H-20 Apple Silicon CI 13 module / H-21 external secret slot policy
- **docs + tokenomist**：H-22 docs/README.md index 補 / H-23 TODO §0.5 refactor 已 done v61 / H-24 M4 Tokenomist trial expiry

### §5.2 3 missing module 處置（PM 仲裁，operator D1 採納）

| ID | 描述 | 處置 |
|---|---|---|
| **M14** | strategy hot-swap（不重啟 engine） | **defer v5.9**（Sprint 4 後 90d 才需）|
| **M15** | capacity-aware sizing（depth/liquidity 感知） | **擴 M6 acceptance 第 4 條**「orderbook depth bounds」，不新建 module |
| **M16** | cross-strategy correlation re-sizing | **擴 M1/LAL acceptance**「correlation-adjusted weight」，不新建 module |

### §5.3 W-AUDIT-4b retained invariant 19 — observe only

5 項 observe-only retained INSERT/VIEW/DROP；詳見 archive §B：`docs/archive/2026-05-21--todo_v60_archive.md`

### §5.4 P2/P3 Deferred / Passive Wait

| ID | 狀態 | 觸發 / Deadline |
|---|---|---|
| `P1-OBS-PLACEMENT-BBO-V094` | DEFER | Phase 1b 14d freeze 後（~2026-06-01）|
| `P1-SWEEP-A-AXIS-PRUNE` | DEFER | 下輪 sweep（Phase 2a verdict 後）|
| `P1-WATCHDOG-NETOUTAGE-SPARSE-LOG-OQ` | DEFER | 觀察 canary NETWORK_OUTAGE event 頻率 |
| `P2-CLIPPY-CLEANUP-1` | ACTIVE | Sprint 1A 進行中並行清；E1 4-6 hr |
| `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` | PASSIVE WAIT | 2026-08-21（ADR-0028 90d cadence）|
| `P2-AUDIT-DEAD-CODE` | DORMANT | D-16；Sprint N+6+ |
| `P2-WP05-CSP-UNSAFE-INLINE` | DEFER | live-gate 前升 P1 |
| `P2-CANARY-FILE-SIZE-REFACTOR` | P5 DEFER | 等 800 LOC bulk wave |
| `P3-H0GATE-FILE-SPLIT` | DEFER | 獨立 wave；h0_gate.rs 1243 行 > 800 |
| `P3-H0-LATENCY-1H-RESET-INTEGRATION-TEST` | LOW NTH | 既有 unit test 覆蓋 reset；缺 1h cadence integration |

---

## §6 Dormant + Passive Wait

| ID | 描述 | 原因 | 最早重啟 |
|---|---|---|---|
| `D-13` | Cognitive Modulator | 3-Tier 數據源未接齊 + alpha 無依賴 | Sprint N+8+ |
| `D-14` | DreamEngine 完整自主進化 | Foundation Model + L4 跨策略 meta-learning 未 ready | long-tail |
| `D-15` | OpportunityTracker 全 Agent 注入 | 不影響 supervised live | Sprint N+5 可選 |
| `D-16` | openclaw_core 9 模組 sunset cleanup | 7 已清；餘 2 待 PA | Sprint N+6+ |
| `D-17` | Layer 2 自主推理循環自動觸發 | **PERMANENT DORMANT** by ADR-0020 manual+supervisor-only | **不解** |
| `D-02` | Layer 2 手動 7d 試運行 SOP | Operator 自執行 | operator 觸發 |

**FA constraint**：靜默漏寫 = 6 個月後 lobby 重新 review；explicit 標 dormant + reason + earliest reactivate

---

## §7 排程 + Milestone

| 日期 / Sprint | 工作 | Gate |
|---|---|---|
| **D+0 ~ D+5 (2026-05-21~26)** | v5.8 16 CRITICAL 並行修補 | Sprint 1A-β readiness 12-check |
| **D+5~D+6 (2026-05-26~27)** | Sprint 1A-β 派發 PA + 5-7 並行 sub-agent | 12-check ✓ |
| **2026-05-22~23 UTC** | Phase 2a 14d verdict 視窗 | operator 三選一 |
| 2026-06-01 | `P1-OBS-PLACEMENT-BBO-V094` + `P1-SWEEP-A-AXIS-PRUNE` 可啟動 | Phase 2a freeze |
| 2026-06-09 | `P1-CONDITIONAL-WATCH` TONUSDT 30d evidence freeze | QC 2026-05-11 zero-cost action #4 |
| **W18-21 (~2026-09 初)** | **Sprint 4 first Live $500** | P0-EDGE-1 + LG-3 + OPS-1..4 全 closure |
| 2026-08-21 | `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` + `P1-HALT-TRIGGER` review | 90d cadence |
| **W44-55 (~2027 Q1-Q2)** | **Y1 末 — autonomy 66%** | Copy Trading evidence gate / Overlay verdict |
| **~21-24 mo** | **Y2 Q2 Auto-Allocator activation — autonomy 90%** | 6mo Advisory + >80% approval |
| **~32 mo** | **Y3 Q2 — autonomy 95%** | M10 Tier C-E / M12 / M13 Y3+ |

---

## §8 跨 Wave 衝突仲裁

| # | 衝突 | 解 |
|---|---|---|
| 1 | LG-3 IMPL DISPATCH ↔ P0-FUNDING-ARB-DECISION-FORCE | 若 operator 選 (A) 砍 funding_arb，LG-3 cohort 4；**operator 拍板前 LG-3 IMPL DISPATCH 不可派** |
| 2 | Phase 2a engine STOPPED ↔ verdict 視窗 累積 | 每暫停 1h 失 ~0.4 rows；後續禁無預警 stop |
| 3 | W-AUDIT-9 graduated canary path ↔ ExecutorAgent shadow_mode | per AMD-2026-05-15-01：Stage 0R replay preflight + Stage 1 demo；ExecutorAgent shadow=true 至 Stage 0R PASS |
| 4 | A 群策略候選 ↔ Stage 1 Demo cohort | RESOLVED 2026-05-16：Stage 1 為 Demo-only；A4-C tombstoned 不可作 cohort 來源 |
| 5 | v5.8 Sprint 1A-β/γ/δ 順序 dispatch ↔ cross-V### dependency | per `v58-CR-9` PG dry-run + cross-V### dependency graph；β/γ 不能無條件並行 |

---

## §9 派工規則 + Handoff SOP

詳見 `docs/agents/todo-maintenance.md` + `CLAUDE.md` §八。簡明條款：

- **實作鏈**：`PM → PA → E1/E1a → E2 → E4 → QA → PM`
- **安全 / 部署 / runtime**：`PM → E3 → BB（若涉交易所）→ PM`
- **量化 / 資料**：`PM → QC → MIT → AI-E（若涉模型成本）→ PM`
- **Sign-off SOP**：`cargo test -p openclaw_engine --release`（覆蓋 tests/ integration crate）
- **GUI JS 變動**：sign-off 強制 `node --check`
- **V### migration**：Linux PG empirical dry-run mandatory before IMPL sign-off
- **Meta-doc 改動**：dirty trees 用 `git commit --only <files>` 隔離 race
- **每 green checkpoint**：commit subject + body，push origin，再 ssh trade-core fast-forward；doc-only commits 加 `[skip ci]`

```bash
# Handoff 檢查
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

## §10 References（active only）

### v5.7 + v5.8 主檔 + dispatch
- v5.7 主檔：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md`
- v5.8 主檔：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- v5.7 Sprint 1A dispatch packet：`docs/execution_plan/2026-05-21--sprint_1a_dispatch_packet.md`
- V103/V104 schema spec：`docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- V103/V104 PG dry-run：`docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md`
- Earn governance spec：`docs/execution_plan/2026-05-21--earn_governance_spec.md`

### v5.7 + v5.8 整合 + verdict
- PM 最終 verdict v5.8 主入口：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`
- PM autonomy verdict v5.7：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_autonomy_verdict.md`
- PM v5.7 12-prefix signoff：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_12_prefix_pm_signoff.md`
- PA v5.7+v5.8 dispatch consolidation：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`（562 行）
- PA v5.7 dispatch consolidation：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_dispatch_consolidation.md`
- PA v5.7 12-prefix tech verify：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_12_prefix_tech_verify.md`
- FA v5.7 business consolidation（含 5 strategy×Stage matrix §6 + 資金路徑流圖 §7）：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_business_consolidation.md`
- FA v5.8 executability audit（含 13-module business acceptance §0.6）：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v58_executability_audit.md`
- FA v5.7 12-prefix business verify：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_12_prefix_business_verify.md`

### v5.8 14 multi-agent audit
- A3 / AI-E / BB / CC / E2 / E3 / E4 / E5 / FA / MIT / QA / QC / R4 / TW：`docs/CCAgentWorkSpace/{ROLE}/workspace/reports/2026-05-21--v58_executability_audit.md`

### Active ADR / AMD
- ADR-0006 (Bybit-only) + ADR-0033 (Binance amendment)
- ADR-0015 openclaw_core sunset
- ADR-0017 scanner authority retirement / ADR-0018 funding_arb retire
- ADR-0020 Layer 2 manual+supervisor-only
- ADR-0022 strategist cap / ADR-0023 SourceAvailability schema / ADR-0024 Cowork operator-assistant
- ADR-0028 close-maker-fallback dead enum reservation（90d audit 2026-08-21）
- ADR-0029 market.public_trades + orderbook_l2_snapshot storage policy（Proposed）
- ADR-0030 Bybit Earn governance / ADR-0031 Macro counterfactual / ADR-0032 On-chain counterfactual
- ADR-0034 M1 LAL（Layered Approval Lease，v5.8 NEW）✅ DONE 2026-05-21
- ADR-0035 M5 online learning interface reserved (Y3+) ✅ DONE 2026-05-21
- ADR-0036 M8 anomaly detection + M10 Tier D blacklist ✅ DONE 2026-05-21
- ADR-0037 M9 A/B framework + statistical methodology ✅ DONE 2026-05-21
- ADR-0038 M11 continuous counterfactual replay ✅ DONE 2026-05-21
- ADR-0039 M12 order router trait + maker fill rate ✅ DONE 2026-05-21
- ADR-0040 multi-venue gate spec ✅ DONE 2026-05-21
- ADR-0041 ContextDistiller v4 + AI cost cap amendment ✅ DONE 2026-05-21
- AMD-2026-05-15-01（Canary Rebase Replay Preflight + Demo Micro-Canary）
- AMD-2026-05-15-02 v0.7（EDGE-P2-3 Phase 1b + Runtime Activation Layer）
- **AMD-2026-05-21-01-autonomy-vs-human-final-review — CC+PM draft pending D+2**

### Active spec
- LG-3 spec v2 final：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md`
- EDGE-P2-3 Phase 1b spec v1.4：`docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`
- V094 hybrid schema migration spec：`docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`

### Bybit / API
- `docs/references/2026-04-04--bybit_api_reference.md`
- `docs/audits/2026-04-04--bybit_api_infra_audit.md`
- BB v57 C4/C5/C6 verdict：`docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md`

### Recent 2026-05-21 audit reports (active)
- QA D1: `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-21--lg1_lg2_7d_closure_phase2a_t72h_verify.md`
- PA D3: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--p1_data_lg5_edge_status_reverify.md`
- E5 F1: `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md`
- FA G2: `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--todo_business_chain_audit.md`
- PA v61 restructure proposal：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--todo_v61_restructure_proposal.md`
- FA v61 restructure proposal：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--todo_v61_restructure_proposal.md`

### Archive index
- v55 翻譯歸檔：`docs/archive/2026-05-19--todo_v55_translation_archive.md`
- v57.3 closure cleanup：`docs/archive/2026-05-20--todo_v57_3_closure_cleanup_archive.md`
- v57.5 route change purge：`docs/archive/2026-05-21--todo_v57_5_route_change_purge.md`
- v58 layout refactor：`docs/archive/2026-05-21--todo_v58_layout_refactor_archive.md`
- **v60 重構歸檔（v5.7 12 prefix DONE + W-AUDIT-4b + H+I 批 closure + 9 批 narrative）**：`docs/archive/2026-05-21--todo_v60_archive.md`

### Operator commit
- v5.8 主檔 + 14 audit + PA consolidation + PM verdict + TODO §0.6：commit `f37cb62b` (2026-05-21)

---

## §-1 歷史 closure 摘要（≤ 14d）

- **2026-05-21 closure summary**：v5.7 12 prefix **DESIGN-DONE / IMPL-PENDING** PM SIGN-OFF（archive §A）/ v5.8 13-module audit 14 agent + PA + PM verdict（DESIGN-only）/ Sprint 1A-β 16 artifact **DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED**（archive §G）/ TODO v60 → v61 重構（本檔）+ H+I 批 P2/P3 closure（archive §C）/ 過去 14d 9 批 closure narrative（archive §D）— per 2026-05-21 acceptance audit (Linux PG max_version=96, 10 target tables pg_class 0 hits, V099+ migration .sql 本地不存在)
- **Incident marker 2026-05-21**：09:58 UTC engine + watchdog SIGTERM graceful stop；13:31 UTC PM restart_all.sh --keep-auth 恢復；Phase 2a sample velocity gap ~3.5h；verdict 視窗影響 low

**詳細歷史**：`docs/archive/2026-05-21--todo_v60_archive.md`（§A-§F 完整 narrative）

---

**Maintenance contract**：依 `docs/agents/todo-maintenance.md` 將本檔保持為活躍派工佇列。穩定專案脈絡走 `README.md`；agent 操作規則走 `CLAUDE.md`；歷史 closure 走 `docs/archive/`。
