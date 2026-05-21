# 玄衡 TODO — 活躍派工佇列

**版本**：v61（v60 → v61 重構：400 → 250 行 / 過時歸檔 / session·wave·sprint 結構化 / reference ~30 條完整）
**日期**：2026-05-21
**Session**：v5.7 + v5.8 13-module autonomy expansion (44-55w Y1 + 21-32mo 達 95% autonomy)
**v60 完整歷史 archive**：`docs/archive/2026-05-21--todo_v60_archive.md`

---

## §0 摘要

- **Current Sprint Phase**：Sprint 1A-α DONE（v5.7 12 prefix sign-off 2026-05-21）+ Wave 2 v5.8 修補 D+0~D+5 STAGING
- **Current Wave**：Wave 2 = v5.8 16 CRITICAL must-fix 修補（D+0 完 1/16；剩 15 條 D+1~D+5 並行）
- **Active P0**：`P0-EDGE-1`（5 strategy alpha-deficient）+ `P0-LG-3`（Wave 2.4 IMPL DISPATCH PENDING SPEC-READY 10d）+ `P0-OPS-1..4`（HTTPS / cred / legal / runbook）— Sprint 4 first Live W18-21 前必 closure
- **Next 24h operator action**：D+1 (2026-05-22) AM ① BB OpenClaw key 發行日 5 min query ② Phase 2a 14d verdict 視窗（clock @ 2026-05-22~23 UTC）30-60 min 三選一決議
- **Runtime**：engine PID 2934602 + API PID 2934665 + watchdog PID 2936560；最後 graceful restart 2026-05-21 13:31 UTC
- **Pending operator decision**：(1) Phase 2a verdict (D+1-D+2) (2) `P0-FUNDING-ARB-DECISION-FORCE` 升等 (3) Watchdog daemon R2 deploy 時機 (4) v5.8 16 CRITICAL 派發後 D+5 Sprint 1A-β readiness sign-off

---

## §1 Session / Wave / Sprint 路線圖

### §1.1 Current Sprint Banner

```
Sprint 1A-α  ✅ DONE (W0-1.5, 2026-05-21)            v5.7 12 prefix + PM signoff
Sprint 1A-修補 🟡 ACTIVE (D+0~D+5, 2026-05-21~26)     v5.8 16 CRITICAL must-fix
Sprint 1A-β  ⏳ PENDING (W1.5-3.5, ~2026-05-27 開派)   M1 LAL/M3/M6/M7/M11 DESIGN
Sprint 1A-γ  ⏳ PENDING (W3.5-5.5)                    M2/M4/M8/M9/M10 DESIGN
Sprint 1A-δ  ⏳ PENDING (W5.5-6.5)                    M5/M12/M13 interface stubs
Sprint 1A-ε  ⏳ PENDING (W6.5-9)                      integration verify + Monthly Review Wizard
```

### §1.2 Sprint Progression Table（Sprint 1A → Y3）

| Sprint | Calendar | 主要工作 | 工時 (hr) | Status |
|---|---|---|---|---|
| 1A-α | 2026-05-21 done | v5.7 baseline + 4 follow-up | 75-105 | ✅ DONE |
| 1A-修補 | D+0~D+5 (2026-05-21~26) | 16 CRITICAL must-fix | 1,007-1,453 並行 | 🟡 ACTIVE |
| 1A-β | W1.5-3.5 | M1 LAL/M3/M6/M7/M11 + ADR-0034/36/37/38 + V105/V106/V107/V112/V113 spec | 310-460 | ⏳ |
| 1A-γ | W3.5-5.5 | M2/M4/M8/M9/M10 DESIGN + V108/V109/V111 + 4 runbook | 220-340 | ⏳ |
| 1A-δ | W5.5-6.5 | M5/M12/M13 stubs + ADR-0035/0039/0040 + V114-116 partial | 75-120 | ⏳ |
| 1A-ε | W6.5-9 | integration verify + cross-ADR + Monthly Review Wizard + docs/README index | 60-100 | ⏳ |
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

### §1.5 Sprint 1A-β Dispatch Readiness Checklist（12 條，D+5~D+6 必達）

1. ☐ v5.7 4 leftover land（CR-1：V103 audit field / V### re-number / PG conn / Earn 五角色 cross-ref）
2. ☐ ADR-0030~0033（v5.7）+ ADR-0034 LAL（CR-2）sign-off
3. ☐ AMD-2026-05-21-01 autonomy-vs-human-final-review sign-off（CR-3）
4. ☐ ADR-0040 multi-venue gate（CR-4）sign-off
5. ☐ ADR-0036 + ADR-0037 + ADR-0038 sign-off
6. ☐ M10 Tier D 黑名單 hardening + M8 GARCH 替換（CR-5）
7. ☐ V105-V113 9 個 schema spec doc land（CR-8，90-140 MIT-hr）
8. ☐ §10 P0 precondition table + operator closure ETA（CR-10）
9. ☐ GUI 工時 +261-374 hr + Console tab 4 sub-section + A3 sign-off invariants（CR-11）
10. ☐ TW 工時 +450-640 hr 寫入 §3/§4/§8/§9/§12（CR-12）
11. ☐ §3/§4/§14 工時統一上修（CR-13：543-797→670-1,015 hr / 2,780-3,930→3,500-5,200 hr / 37-44w→44-55w）
12. ☐ docs/README.md index 補（v5.7+v5.8 主檔 + 14 audit + dispatch packet + V103/V104 spec 等 ~11 條）+ TODO v61 finalize

### §1.6 v5.8 16 CRITICAL must-fix（D+0~D+5 並行修補）

| ID | Item | Owner | 工時 | ETA |
|---|---|---|---|---|
| `v58-CR-1` | v5.7 4 follow-up | PA+MIT+TW+FA+E3+QA | 8-12 hr | D+1 |
| `v58-CR-2` | M1→LAL + ADR-0034 5 細節 | PA+CC+QA | 12-18 hr | D+2 |
| `v58-CR-3` | AMD-2026-05-21-01 autonomy-vs-human-final-review | PM+CC | 4-8 hr | D+2 |
| `v58-CR-4` | ADR-0040 multi-venue gate（M13→Y3+ 措辭 + 5-gate venue schema） | TW+BB+E3 | 6-10 hr | D+3 |
| `v58-CR-5` | M10 Tier D HMM 黑名單 + M8 GARCH 替換（ATR-vol regime + funding state）| TW+MIT+QC | 4-6 hr | D+2 |
| `v58-CR-6` | M4 minimum bar + leakage protocol（6 attribute + shift(1) leak-free）| MIT+PA | 5-8 hr | D+3 |
| `v58-CR-7` | M11 threshold statistical derivation + M7 dedup（M11→M7 input；M7 single authority）| MIT+QC | 4-6 hr | D+3 |
| `v58-CR-8` | 9 個 V### schema spec doc（V105-V113）仿 v103_v104 範式 | MIT+PA+E5 | 90-140 hr | D+5 |
| `v58-CR-9` | PG dry-run mandatory + cross-V### dependency graph | PA+E5 | 3-5 hr | D+3 |
| `v58-CR-10` | §10 P0 precondition table + §12 operator decision 5 | PM | 2-4 hr | D+3 |
| `v58-CR-11` | GUI 工時 +261-374 hr + Console tab + A3 sign-off invariants | PM+A3 | 3-5 hr | D+4 |
| `v58-CR-12` | TW 工時 +450-640 hr | PM+TW | 2-3 hr | D+4 |
| `v58-CR-13` | §3/§4/§14 工時統一上修 | PM | 1 hr | D+4 |
| `v58-CR-14` | M12 maker_fill_rate + M11 PG `market.liquidations` source | BB+TW | 3-5 hr | D+3 |
| `v58-CR-15` | 5-gate auto path inheritance 明文 + M4 DRAFT Decision Lease | TW+E3+CC | 4-6 hr | D+4 |
| `v58-CR-16` | ADR-0041 ContextDistiller v4 + DOC-08 月 cap 重估 | AI-E+TW+PM | 6-10 hr | D+5 |

**CRITICAL 合計**：~157-246 hr core + 90-140 hr MIT spec + 450-640 hr TW + 261-374 hr GUI + 48-53 hr A3 ≈ **1,007-1,453 hr**；並行 5-10 sub-agent wall-clock D+0~D+5

### §1.6.1 16 CRITICAL closure status — DONE 2026-05-21 主會話

| ID | 狀態 | Artifact / 收口位置 |
|---|---|---|
| `v58-CR-1` | ✅ DONE | V103 spec §14 audit field EXTEND（5 field）+ CLAUDE.md §Data PG conn ref + docs/agents/context-loading.md PG examples + Earn governance §12 五角色 cross-ref 委派 + v5.8 §9 V### re-number consistent note |
| `v58-CR-2` | ✅ DONE | `docs/adr/0034-decision-lease-layered-approval-lal.md` (~200 行；5 細節 + LAL↔Stage 矩陣) |
| `v58-CR-3` | ✅ DONE | `docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md` (254 行；protected 6 / opt-in 8 / 反向 attack 6) |
| `v58-CR-4` | ✅ DONE | `docs/adr/0040-multi-venue-gate-spec.md` (257 行；M13 Y2→Y3+ + Venue enum hardcode + 6 trade gate criteria) |
| `v58-CR-5` | ✅ DONE | `docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md` (268 行；HMM/Markov/GARCH 黑名單 + ATR-vol+funding 雙 axis) |
| `v58-CR-6` | ✅ DONE | `docs/execution_plan/2026-05-21--m4_minimum_bar_and_leakage_protocol.md` (839 行；6 attribute + shift(1) 三語言 + V103 EXTEND 6 字段 + leakage scan) |
| `v58-CR-7` | ✅ DONE | `docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md` (321 行；3 threshold + M7 single decay authority + DECAY_ENFORCED rename) |
| `v58-CR-8` | ✅ DONE | V105-V113 9 個 placeholder spec doc 1,970 行（`docs/execution_plan/2026-05-21--v###_*_schema_spec.md`）；full DDL Sprint 1A-β/γ 推進 |
| `v58-CR-9` | ✅ DONE | v5.8 §3.5.5 cross-V### dependency graph + PG dry-run mandate；CLAUDE.md §Data ref |
| `v58-CR-10` | ✅ DONE | v5.8 §10.5 P0 precondition table（P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 + 5-gate） + §12 decision 5 三選一 |
| `v58-CR-11` | ✅ DONE | v5.8 §3.5.2 GUI 工時 +261-374 hr + §4 reflect + §12 A3 sign-off invariants 48-53 hr Y1 |
| `v58-CR-12` | ✅ DONE | v5.8 §3.5.2 TW 工時 +450-640 hr + §4 reflect + §12 並行 dispatch with PA-MIT-CC parallel tracks |
| `v58-CR-13` | ✅ DONE | v5.8 §3.5.1 Sprint 1A 543-797→670-1,015 hr + §4 Y1 2,780-3,930→3,500-5,200 hr + 37-44w→44-55w + 5.5w buffer |
| `v58-CR-14` | ✅ DONE | `docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md` (308 行) + `docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md` (255 行；self-hosted PG market.liquidations 非 Bybit API) |
| `v58-CR-15` | ✅ DONE | v5.8 §11.5 5-gate auto path inheritance 7 條 + M4 DRAFT writeback Decision Lease + 6 反向 attack mitigation |
| `v58-CR-16` | ✅ DONE | `docs/adr/0041-context-distiller-v4-and-ai-cost-cap-amendment.md` (272 行；800 token hard cap + DOC-08 §4 Y2 opt-in $150-200 + M4 hybrid + M11 daily L1 vs CRITICAL L2) |

**16/16 ✅ DONE 2026-05-21** — 主會話統一 dispatch + sub-agent 並行 + 主會話收口；Sprint 1A-β D+5~D+10 內 PA dispatch packet → 5-7 並行 sub-agent → 真實 DESIGN 開始。

**新增 artifact 統計**：
- **6 ADR**：0034 (LAL) / 0036 (M8+M10 blacklist) / 0038 (M11 replay) / 0039 (M12 + maker fill rate) / 0040 (multi-venue Y3+) / 0041 (ContextDistiller v4)
- **1 AMD**：AMD-2026-05-21-01 autonomy-vs-human-final-review
- **2 spec docs**：M4 leakage protocol / M11+M7 dedup + DECAY_ENFORCED rename
- **9 V### placeholder spec docs**：V105-V113
- **6 v5.8 主檔 patches**：§3.5 / §4 / §9 / §10.5 / §11.5 / §12 / §14
- **4 主文件 patches**：CLAUDE.md §Data + docs/agents/context-loading.md PG examples + Earn governance §12 五角色 cross-ref + V103 spec §14 audit field EXTEND
- **總計**：~21 個新文件 + ~8 個現有文件 patches；~5,500+ 行新增

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
- **ADR-0034 M1 LAL（Layered Approval Lease，v5.8 NEW）— TW draft pending D+5**
- **ADR-0035-0040 v5.8 7 ADR — TW draft pending D+4-D+5**
- **ADR-0041 ContextDistiller v4 — AI-E draft pending D+5**
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

- **2026-05-21 closure summary**：v5.7 12 prefix DONE PM SIGN-OFF（archive §A）/ v5.8 13-module audit 14 agent + PA + PM verdict / TODO v60 → v61 重構（本檔）+ H+I 批 P2/P3 closure（archive §C）/ 過去 14d 9 批 closure narrative（archive §D）
- **Incident marker 2026-05-21**：09:58 UTC engine + watchdog SIGTERM graceful stop；13:31 UTC PM restart_all.sh --keep-auth 恢復；Phase 2a sample velocity gap ~3.5h；verdict 視窗影響 low

**詳細歷史**：`docs/archive/2026-05-21--todo_v60_archive.md`（§A-§F 完整 narrative）

---

**Maintenance contract**：依 `docs/agents/todo-maintenance.md` 將本檔保持為活躍派工佇列。穩定專案脈絡走 `README.md`；agent 操作規則走 `CLAUDE.md`；歷史 closure 走 `docs/archive/`。
