# 玄衡 TODO — 活躍派工佇列

版本：v60-zh（v59 + 2026-05-21 v5.7 12 條 CRITICAL prefix DONE + PM signoff + FA/PA verify）
日期：2026-05-21
狀態：路線中立；§1 路線變更區待 operator 拍板後重填；§0.5 v5.7 12 條 prefix DONE PM SIGN-OFF。

## §0 摘要

- **Live deploy 5-gate hard precondition**：`P0-EDGE-1`（net-positive edge）+ `P0-LG-3`（Wave 2.4 IMPL DISPATCH）+ `P0-OPS-1..4`（HTTPS / cred rotation / legal / runbook）
- **當前 Phase 2a 14d observation**：clock @ 2026-05-18 13:50 UTC；verdict 視窗 2026-05-22~23 UTC（明後天）；QA D1 T+72h projection AC-1/2/4 FAIL → PM 須三選一決議
- **Runtime**：engine PID 2934602 + API PID 2934665 + watchdog PID 2936560（Inert probe enabled）；最後 graceful restart 2026-05-21 13:31 UTC
- **待 operator 拍板**：(1) 路線敲定 v4/v5 重填 §1；(2) `P0-FUNDING-ARB-DECISION-FORCE` 升等；(3) Watchdog daemon R2 deploy 時機
- **v5.7 dispatch-safe patch 狀態（2026-05-21）**：14 SubAgent 執行性審核 + PA/FA 匯總 + PM 簽收完成；operator 已批 D1-D5；D6 = 暫不重填 §1 / 不解 V101/V102 Hard precondition，僅於 §0.5 列 12 條 pre-start CRITICAL fix
- **v5.7 12 條 prefix DONE 2026-05-21**：12/12 land（C1-C12）；7 並行 sub-agent + PM hands-on；FA verdict APPROVE-WITH-CAVEAT；PA verdict NEEDS-PM-ARBITRATION（非 NO-GO）；**PM 仲裁 5 條決議全採 FA+PA 推薦**（V### re-number 採 option A / 工時 75-105 hr / V101 字段集路徑 A / Earn §4 條件 A / clippy 軟強制）；BB C6 **PROOF PASS 31,473 rows 推翻 v57 audit Risk 1 BLOCKED claim**；4 ADR draft 0030-0033 land（TW 926 行）；V103/V104 schema spec land（MIT 940 行）；Earn governance spec land（CC 460 行）；V### empirical head=V096 仲裁採 option A：V099/V100=Track v3 / V101/V102=Earn schema
- **operator follow-up（不阻塞）**：(1) OpenClaw key 發行日（Bybit Web API mgmt 查 last edited；5 min；Sprint 1B 派發前必驗）(2) Console tab 歸屬 H2（A3+PA+operator；不阻塞 Sprint 1A）
- **派發前 must-fix（PA+sub-agent 補 2026-05-22 內）**：V103 schema 補 4-5 audit field（lease_id/approval_id/actor_id/bybit_request_payload/rationale；5-8 hr）+ V### re-number search/replace + PG connection 範例補 CLAUDE.md + Earn governance 五角色 cross-ref
- **報告 inventory（2026-05-21）**：`PM/workspace/reports/2026-05-21--v57_pm_signoff.md`（路線敲定主入口）+ `PM/workspace/reports/2026-05-21--v57_12_prefix_pm_signoff.md`（12 條 prefix 驗收）+ `FA/workspace/reports/2026-05-21--v57_12_prefix_business_verify.md` + `PA/workspace/reports/2026-05-21--v57_12_prefix_tech_verify.md` + 12 條 prefix sub-agent reports（C2 TW / C3 MIT / C4-C6 BB / C8 CC / C9 PA）

---

## §0.5 v5.7 Sprint 1A Pre-Start CRITICAL Fix List — DONE 2026-05-21 PM SIGN-OFF

**狀態**：**DONE — 12/12 land + FA APPROVE-WITH-CAVEAT + PA NEEDS-PM-ARBITRATION + PM 仲裁 5 條決議完畢 + Sprint 1A 派發 GO-WITH-CONDITIONS**

**完整 sign-off**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_12_prefix_pm_signoff.md`（PM 驗收主入口）
**FA 業務 verify**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_12_prefix_business_verify.md`
**PA 技術 verify**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_12_prefix_tech_verify.md`

**PM 仲裁 5 條決議**（全採 FA+PA 推薦）：
1. **G5 V### re-number**：option A（V097/V098 catch-up → V099/V100=Track v3 → V101/V102=Earn schema）；30-60 min churn
2. **G3 工時 reconcile**：75-105 hr 中間值（BB C6 推翻僅 §6 部分，不全回滾）
3. **G2 V101 字段集**：路徑 A（v5.7 brief 字段集；廢棄 V101 §3.3.1+§3.3.2）
4. **G7 C8 §4**：條件 A finalize（BB C4 verdict (a) API EXISTS）
5. **G11 Apple CI clippy**：雙軌（hard gate cargo check / 軟強制 clippy + P2-CLIPPY-CLEANUP-1 ticket）

**operator follow-up（不阻塞今日 commit）**：
- G4 OpenClaw key 發行日（5 min query；Sprint 1B 派發前必驗）
- H2 Console tab 歸屬決策（A3+PA+operator 工作會；H 級不阻塞）

**Sprint 1A 派發前 must-fix（PA + sub-agent 補；2026-05-22 內 land）**：
- G6 V103 schema 補 4-5 audit field（PA + MIT；5-8 hr）
- V### re-number search/replace（PA；30-60 min）
- PG connection 範例補 CLAUDE.md / docs/agents/context-loading.md（TW；30 min）
- Earn governance 五角色 cross-ref（FA + E3 + QA + MIT 並行；各 1-2 hr）

**新增 P2 ticket**：`P2-CLIPPY-CLEANUP-1`（既有 17 clippy errors 修；owner E1；4-6 hr；Sprint 1A 進行中並行清；不阻塞 dispatch）

**Sprint 1A 派發 verdict**：GO-WITH-CONDITIONS — D+1（2026-05-22）5 並行 track 可派

| ID | 項目 | Owner | 狀態 | 落地 |
|---|---|---|---|---|
| `v57-C1` | v5.7 主檔搬 `docs/execution_plan/2026-05-20--execution-plan-v5.7.md` + 進 git tree（**§1 不重填 / Hard precondition 不解除** per D6） | PM | ✅ DONE | git rename detected |
| `v57-C2` | ADR 0030/0031/0032 + ADR-0033（ADR-0006 amendment）926 行 | TW | ✅ DONE | `docs/adr/0030-..0033-*.md` |
| `v57-C3` | V103/V104 schema spec（4 表 DDL + Guard A/B/C）940 行 ⚠️ V### search/replace（PM 仲裁 1）+ 補 4-5 audit field（2026-05-22 PA+MIT 5-8 hr）| PA + MIT | ✅ DONE-WITH-FOLLOWUP | `docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md` |
| `v57-C4` | Bybit Earn API endpoint = **(a) API EXISTS 12 endpoint** | BB | ✅ DONE | `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md` |
| `v57-C5` | Earn API key scope = **(a) non-withdraw sufficient** ⚠️ operator 5-min 查 key 發行日（Sprint 1B 派發前必驗）| BB + E3 | ✅ DONE-WITH-OPERATOR-FOLLOWUP | 同上 BB report |
| `v57-C6` | liquidation writer = **(a) PROOF PASS 31,473 rows** 推翻 v57 audit Risk 1 BLOCKED claim | BB + MIT | ✅ DONE-STRONG | 同上 BB report |
| `v57-C7` | Sprint 1B C10 → Stage 0R + Stage 1 Demo（不寫 mainnet live $2,000）；Stage 4 落 Sprint 3-4 | PA + FA | ✅ DONE | `docs/execution_plan/2026-05-21--sprint_1a_dispatch_packet.md` §1 |
| `v57-C8` | Earn governance spec（5-gate / IntentProcessor 復用 / fail-closed / daily reconciliation）460 行 ⚠️ §4 條件 A finalize（PM 仲裁 4）；五角色 cross-ref 預 2026-05-22 land | CC + FA | ✅ DONE-WITH-CROSS-REF-FOLLOWUP | `docs/execution_plan/2026-05-21--earn_governance_spec.md` |
| `v57-C9` | V103/V104 PG empirical dry-run — **head=V096，V101/V102 未 land**；PM 仲裁 1 採 option A：V099/V100=Track v3 / V101/V102=Earn schema | PA | ✅ DONE-STRONG | `docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md` + PA report |
| `v57-C10` | Sprint 1A 60-80 → **75-105 hr**（PM 仲裁 2 中間值）+ Y1 total → **1,275-1,710 hr**；§9 並行 sub-agent 強制 50-60% workload | PM | ✅ DONE | dispatch_packet §2 |
| `v57-C11` | Apple Silicon CI — PM 仲裁 5 雙軌：`cargo check --target aarch64-apple-darwin` hard gate ✅；clippy 軟強制 + P2-CLIPPY-CLEANUP-1 | PA | ✅ DONE | dispatch_packet §3 |
| `v57-C12` | 中文注釋 mandate + SCRIPT_INDEX.md enforce + MODULE_NOTE grep step | PA + TW | ✅ DONE | dispatch_packet §4 |

**5 並行 track 派工 readiness**：1A-gov ✅ / 1A-schema ⚠️ NEEDS-PM-ARBITRATION (V### re-number done) / 1A-sensor ✅ / 1A-earn ✅ / 1A-gui ⚠️ NEEDS-OPERATOR-DECISION (H2 tab 歸屬)

---

## §1 路線變更區（待 operator 拍板）

v4 / v4.1 / v4.2 / v4.3 / v4.4 / v5.0 / v5.2-v5.7 路線提案歸檔於：
- `docs/archive/2026-05-21--todo_v57_5_route_change_purge.md`
- commit `50c7a0a6 docs(planning): 2026-05-20 路線演進 v5.2-v5.7 — Adaptive Strategy Lab final convergence`

operator 拍板後在本區重填 Sprint Milestone Banner + Wave Roster + Sequencing。

---

## §2 架構邊界 + 硬不變式

- 正式產品：`玄衡 · Arcane Equilibrium`；交易所目標僅 Bybit
- Rust `openclaw_engine` = 交易 / 風控 / 策略 config / 執行權威；Python = control plane / GUI / bridge / replay surface / 5-Agent runtime host（**不**是交易事實層）
- 標準 GUI = FastAPI console `trade-core:8000/console`；外部 OpenClaw Gateway 僅做通訊 / mobile / supervisor relay
- 本地 5-Agent runtime（Scout / Strategist / Guardian / Analyst / Executor）；Cloud L2 呼叫須走 supervisor escalation packet + 顯式 budget/model config + durable `agent.ai_invocations` ledger reservation
- Scanner = always-on infra；**不**是交易權威，不可 hard-gate opens/closes/live auth
- 權威 agent promotion 須 typed lineage：StrategySignal → StrategistDecision → GuardianVerdict → ExecutionPlan → Decision Lease / idempotency → ExecutionReport
- Replay = advisory / diagnostic；不能取代 runtime lineage 或授權 live promotion
- **Graduated Canary**（AMD-2026-05-15-01 取代 AMD-2026-05-09-03）：Stage 0 shadow → Stage 0R Replay Preflight（`eligible_for_demo_canary=true/false`）→ Stage 1 Demo micro-canary（1 策略 × 1 symbol × Demo × 7d）→ Stage 2 demo extended ×14d → Stage 3 demo full ×21d → Stage 4 LIVE_PENDING
- **A4-C BTC→Alt Lead-Lag**：archived from promotion；diagnostic-only / no-revive；`panel.btc_lead_lag_panel` + `[57]` 留 diagnostic
- **5-gate live**：Python `live_reserved` + Python Operator role auth + `OPENCLAW_ALLOW_MAINNET=1` + valid secret slot + signed unexpired `authorization.json`
- DOC-08 §12 9 條安全不變量 + SM-04 ladder + §二 16 原則硬不變式 4 範圍**強制 binary fail-closed**，不被 graduated canary 觸碰

---

## §3 當前活躍狀態

- **Phase 2a 14d obs verdict 視窗**：2026-05-22~23 UTC；QA D1 §3.2 T+72h projection **AC-1/2/4 FAIL**（maker_fill=35.71% << 60% gate；fallback=64.29% >> 30% gate；AC-4 cell 4/5）→ PM 須準備三選一決議（calibration r2 / accept 35% baseline / Phase 2b LiveDemo）
- **業務根因**：5 textbook 策略結構性 alpha-deficient（QC 2026-05-11 audit verdict 持續有效；歸檔詳情 §F）
- **LG-1 P0 DONE 2026-05-21 PASS WITH 1 KNOWN GAP**：H0 wired (18M+ ticks)；fail-closed never fired 5h window；衍生 `P2-LG1-DEMO-SLO-CARVEOUT`（platform jitter，非 algorithmic bug，per E5 F1 audit）
- **LG-2 P0 DONE 2026-05-21 PASS WITH 1 CAVEAT**：startup assertion fire 09:57:12 UTC；production tick path 0 caller for `fee_source()` 是 **BY-DESIGN per spec §2.4**（startup assertion + IPC read contract，**不是 tick-time consumer**）→ LG-3 IMPL spec 須包含 tick-time consumer scope（per QA D1 caveat）
- **v56 P0 HALT cycle CLOSED 2026-05-20**：Layer A + Layer B real-event verified；Halt 觸發根因仍 UNRESOLVED → `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`（passive wait）
- **D2 watchdog classifier R2 SOURCE LAND 2026-05-21**：4-gate + AMBIGUOUS_SOURCE_PATTERNS guard 含 PG pool token；207/207 PASS；deploy 等 operator 決定 watchdog daemon 重啟
- **stale signal**：`learning.edge_estimate_snapshots` 14d 內 0 rows（max=2026-05-07）— 對 `[40]` realized_edge_acceptance + cost_gate 上游有影響；併入 `P0-EDGE-1` 範圍處理（per FA G2 §1.4）

---

## §4 P0 — True-Live Blockers（active only）

| ID | 狀態 | Owner | Acceptance Criteria | Next Action |
|---|---|---|---|---|
| `P0-EDGE-1` | 🔴 ACTIVE | QC + PA | **AC-EDGE-1-A**: 5 textbook 策略 ≥ 3 個 demo 7d avg_net > 5bps（Wilson CI lower > 0），n ≥ 30 per-strategy<br>**AC-EDGE-1-B**: portfolio gross daily PnL 7d MA > 0 USDT<br>**AC-EDGE-1-C**: 若全策略 7d EV < 0，supervised path = 凍結至 alpha 修補有 demo 證據（per FA G2 §4.1）| 等 operator 路線敲定後 Track A 或 alpha 替代方案啟動；併入 `learning.edge_estimate_snapshots` stale follow-up |
| `P0-LG-3` | ⚠️ SPEC READY 10d, Wave 2.4 IMPL DISPATCH PENDING | PA spec → E1×7 | **AC-LG-3-A**: spec v2 §2.4A 加 fee_source tick-time consumer scope（per LG-2 QA D1 caveat）<br>**AC-LG-3-B**: DISPATCH 拍板條件 = operator 路線決議 OR 90d stale-detect 強制 IMPL<br>**AC-LG-3-C**: V099/V100 migration Linux PG empirical dry-run mandatory | PA refresh dispatch plan（V### 號 + multi-E1 race-aware 排程）；待 operator 拍板路線後派 |
| `P0-OPS-1..4` | 🔴 ACTIVE | PA + BB + E3 | **OPS-1**: HTTPS certbot config + 4 service binding<br>**OPS-2**: credential rotation TTL + rotation script<br>**OPS-3**: legal+ToS spec（Bybit ToS / KYC / 地理）<br>**OPS-4**: 第一天 30min runbook | 4 子項各自 owner-推進；OPS-1 → OPS-2 序列 |

---

## §5 P1 — 工程佇列（按優先級 sort）

### §5.1 W-AUDIT-4b retained 範圍（invariant 19 — 觀察 only，無迫切派工）

| ID | 物件 | 分類 | 備註 |
|---|---|---|---|
| `P1-WA4B-INSERT-2` | `learning.cost_edge_advisor_log` | retained INSERT | 2026-05-14 runtime 6091 rows；demo `[cost_edge].enabled=false` → rows `Disabled / ratio=NULL` |
| `P1-WA4B-INSERT-3` | `observability.drift_events` | retained INSERT / readiness gated | 依賴 active `feature_baselines` + ADWIN burn-in 30d；不可未經 operator 同意移除 burn-in |
| `P1-WA4B-VIEW-1` | `learning.mlde_edge_training_rows` | companion VIEW | 唯讀投影；ML training healthcheck |
| `P1-WA4B-VIEW-2` | `learning.scorer_training_features` | companion VIEW | bounded/metadata probe；不可 full unbounded count |
| `P1-WA4B-DROP-1` | `learning.scorer_predictions` | dropped | V069 已 drop；無 producer 接線目標 |

### §5.2 P1 active queue

| ID | 優先 | 任務 | AC / Next Action |
|---|---:|---|---|
| `P1-EDGE-2` (funding_arb) | 3 | ⚠️ PA D3 建議升 P0-FUNDING-ARB-DECISION-FORCE 待 operator 拍板 | FA F2 RCA 確認 SL gate 健康（NOT_A_BUG）；funding_arb 整體治理仍開放；operator 拍板選項 (A) 砍策略 / (B) 增樣本 / (C) 接受 INSUFFICIENT；缺 deadline |
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch — STILL_ACTIVE | source 活躍；14d daily fire 4-43 reviews/day；7d 共 66 review_live_candidate 全 verdict=defer 是設計正確訊號；建議 review cadence 90d + exit conditions（3 個 not-defer 或 180d 都 defer 觸發 PA review） |
| `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 3 | v56 P0 closure 未解 root cause；H4 healthcheck [69] LIVE → passive-wait 規則合規 | forensic `halt_audit.log` armed；passive wait next 自然事件；✅ **H4 補 healthcheck `[69] halt_session_root_cause_recurrence` LIVE 2026-05-21**（E1 IMPL + E2 APPROVE + E4 PASS；13 test PASS；commit `296e94b2`）+ 90d review date 2026-08-21 |
| `P1-LEASE-1` | 3 | 升 P1 from P2（2026-05-20）：清掃 terminal `lease.rs:303` `objects` + HashMap leak | 依賴 P0-LG-3 IMPL DISPATCH 完成後排專案；spec 需 5 元素（terminal state / hashmap 同步 / audit-preserve prune / 觸發時機 / Python `_lease_sm` 對等同步）；工時 ~4-6h |
| `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` | 4 | Phase 1b spec §5.4 完整 dynamic backoff state machine IMPL | Phase 1b 初版（commit `27f02a07`）取 per-symbol 5min 固定；Phase 2a Demo PASS 後另開 PR；PA 估 ~130 LOC |

---

## §6 P2/P3 — 維護 backlog

### §6.1 立刻可派 actionable（不依賴 operator 拍板）— 0 active

**H+I 批 2026-05-21 closure 後本區清空**；新衍生 follow-up 全入 §6.2 deferred 或路線範圍。

**H 批 2026-05-21 closure**：
- ✅ `P3-AUDIT-SCRIPT-STALE-CONST` DONE（E1+E2+E4；tomllib fallback；5/5 PASS；commit `296e94b2`）
- ✅ `P2-DYN-STOP-FLOOR-SENTINEL` DONE（E4 self；3 sentinel；3045 PASS；commit `296e94b2`）
- ✅ `P2-PHYS-LOCK-72-HEALTHCHECK` DONE（PA spec + IMPL slot [68]；E2 APPROVE + E4 PASS；10 test；commit `296e94b2`）
- ✅ `P2-EDGE-EST-SNAPSHOTS-STALE-FOLLOWUP` AUDIT DONE（FA verdict LOW now / MEDIUM future-risk；root cause = cron never installed；Path A operator approve `crontab -e` 5 min ops；維持 P2 綁 W-AUDIT-8a Phase B/C/D 為硬 deadline）

**I 批 2026-05-21 closure**：
- ✅ `P2-LG1-DEMO-SLO-CARVEOUT` DONE（PA spec 429 行 + E1 hot path 接線 + E2 APPROVE + E4 PASS；3272 + 410 + 5/5 integration；Apple Silicon CI 雙 PASS；adversarial real catcher；ML pipeline contamination 守住；commit `aa0780a3`）

**衍生 P3 follow-up**（per E2 R1 LOW NTH，入 backlog）：
- `P3-H0GATE-FILE-SPLIT`（h0_gate.rs 1243 行 > 800 警告；獨立 wave 處理，per E5 file-size pattern）
- `P3-H0-LATENCY-1H-RESET-INTEGRATION-TEST`（E2 R1 LOW NTH；既有 unit test 覆蓋 reset 邏輯，但缺 1h cadence integration test）

### §6.2 Deferred / Passive Wait

| ID | 狀態 | 觸發 / Deadline |
|---|---|---|
| `P1-OBS-PLACEMENT-BBO-V094` | DEFER | Phase 1b 14d freeze 後（~2026-06-01）|
| `P1-SWEEP-A-AXIS-PRUNE` | DEFER | 下輪 sweep（Phase 2a verdict 後）|
| `P1-WATCHDOG-NETOUTAGE-SPARSE-LOG-OQ` | DEFER | 觀察 canary NETWORK_OUTAGE event 頻率後決定（per E1 D2 R2 push back）|
| `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` | PASSIVE WAIT | 2026-08-21（ADR-0028 90d cadence）|
| `P2-AUDIT-DEAD-CODE` | DORMANT | D-16；Sprint N+6+；ADR-0015 觀察期未跑完 |
| `P2-WP05-CSP-UNSAFE-INLINE` | DEFER | live-gate 前升 P1；HTTP 環境下 nonce-based CSP 無實效 |
| `P2-CANARY-FILE-SIZE-REFACTOR` | P5 DEFER | 等 800 LOC bulk wave；PA F4 評估 11h cost vs 機會成本不經濟 |

---

## §7 Dormant + Passive Wait

| ID | 描述 | 原因 | 最早重啟 / Review |
|---|---|---|---|
| `D-13` | Cognitive Modulator | 3-Tier 數據源未接齊 + alpha 無依賴 | Sprint N+8+ |
| `D-14` | DreamEngine 完整自主進化 | Foundation Model + L4 跨策略 meta-learning 未 ready | long-tail |
| `D-15` | OpportunityTracker 全 Agent 注入 | 不影響 supervised live | Sprint N+5 可選 |
| `D-16` | openclaw_core 9 模組 sunset cleanup | ADR-0015 permanent sunset candidates；7 模組已被 P2-DEAD-RUST-CLEANUP-1 (commit `449f628b`) 清；餘 2 待 PA 下 sprint 確認 | Sprint N+6+ |
| `D-17` | Layer 2 自主推理循環自動觸發 | **PERMANENT DORMANT** by ADR-0020 manual+supervisor-only design | **不解** |
| `D-02` | Layer 2 手動 7d 試運行 SOP | Operator 自執行；歸檔 SOP `docs/archive/2026-05-21--todo_v58_layout_refactor_archive.md` §E | operator 觸發 |

**FA constraint**：靜默漏寫 = 6 個月後 lobby 重新 review；explicit 標 dormant + reason + earliest reactivate = 防 strategy drift。

---

## §8 排程

| 日期 | 工作 | Gate |
|---|---|---|
| **2026-05-22~23 UTC** | **Phase 2a 14d observation verdict 視窗**（T+96-120h from 2026-05-18 13:50 UTC clock reset）；QA D1 T+72h projection AC-1/2/4 FAIL → PM 須三選一決議（calibration r2 / accept 35% baseline / Phase 2b LiveDemo）| Phase 1b 14d observation closure |
| 2026-06-01 | `P1-OBS-PLACEMENT-BBO-V094` + `P1-SWEEP-A-AXIS-PRUNE` 可啟動 | Phase 2a 14d freeze 結束 |
| 2026-06-09 | `P1-CONDITIONAL-WATCH` TONUSDT 30d evidence freeze 決議 | per QC 2026-05-11 zero-cost action #4 |
| 2026-06-15 | Supervised live 樂觀帶（業務鏈 75%+）| conditional on P0-EDGE-1 + LG-3 + OPS-1..4 |
| 2026-06-30 | Supervised live 中位帶（80%+）| ~40% probability per FA |
| 2026-07-15 | Supervised live 悲觀帶（85%+）| ~25% probability per FA |
| 2026-08-21 | `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` + `P1-HALT-TRIGGER` review date | 90d cadence |

**Incident marker 2026-05-21**：
- 09:58 UTC engine + watchdog SIGTERM graceful stop（操作 race 可能 Ctrl+C interrupt）；13:31 UTC PM restart_all.sh --keep-auth 恢復；engine PID 2934602 / API PID 2934665 / watchdog PID 2936560；Phase 2a sample velocity gap ~3.5h ≈ 失 1.4 rows；verdict 視窗影響 low

---

## §9 跨 Wave 衝突仲裁

| # | 衝突 | 範圍 | 解 |
|---|---|---|---|
| 1 | LG-3 IMPL DISPATCH ↔ P0-FUNDING-ARB-DECISION-FORCE | LG-3 spec v2 §3 「5 textbook 策略」cohort | 若 operator 選 (A) 砍 funding_arb，LG-3 cohort collapse 到 4；**operator 拍板 P0-FUNDING-ARB 前 LG-3 IMPL DISPATCH 不可派** |
| 2 | Phase 2a engine STOPPED ↔ verdict 視窗 累積 | 09:58 UTC ~3.5h gap | 每暫停 1h 失 ~0.4 rows；當前已 restart；後續禁無預警 stop 操作 |
| 3 | W-AUDIT-9 graduated canary path ↔ ExecutorAgent shadow_mode 接線 | `executor_config_cache.py` / `executor_agent.py` | per AMD-2026-05-15-01：Stage 0R replay preflight + Stage 1 demo micro-canary；ExecutorAgent shadow=true 至 Stage 0R PASS |
| 4 | A 群策略候選 ↔ Stage 1 Demo cohort 選擇 | governance/canary | RESOLVED 2026-05-16：Stage 1 為 Demo-only；A4-C tombstoned 不可作 cohort 來源 |

---

## §10 派工規則 + Handoff SOP

詳見 `docs/agents/todo-maintenance.md` + `CLAUDE.md` §八。簡明條款：

- **實作鏈**：`PM → PA → E1/E1a → E2 → E4 → QA → PM`（跳過角色須 explicit justify）
- **安全 / 部署 / runtime**：`PM → E3 → BB（若涉交易所）→ PM`
- **量化 / 資料**：`PM → QC → MIT → AI-E（若涉模型成本）→ PM`
- **Sign-off SOP**：`cargo test -p openclaw_engine --release`（no --lib，覆蓋 tests/ integration crate）
- **W-AUDIT-6d 砍 6 子項**：E2 必 grep blacklist；命中即 reject merge
- **GUI JS 變動**：sign-off 強制 `node --check`
- **V### migration**：Linux PG empirical dry-run mandatory before IMPL sign-off
- **Meta-doc 改動**：dirty trees 用 `git commit --only <files>` 隔離 race
- **每 green checkpoint**：commit subject + body，push origin，再 ssh trade-core fast-forward；doc-only / governance-only commits 加 `[skip ci]`

### Handoff 檢查

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

## §11 References（active only）

### Active spec / AMD
- LG-3 spec v2 final：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md`
- EDGE-P2-3 Phase 1b spec v1.4：`docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`
- V094 hybrid schema migration spec：`docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- AMD-2026-05-15-01（Canary Rebase Replay Preflight + Demo Micro-Canary）
- AMD-2026-05-15-02 v0.7（EDGE-P2-3 Phase 1b + Runtime Activation Layer + W-AUDIT-8b tombstone）

### Active ADR
- ADR-0015 openclaw_core sunset
- ADR-0017 scanner authority retirement
- ADR-0018 funding_arb retire
- ADR-0020 Layer 2 manual+supervisor-only
- ADR-0022 strategist cap
- ADR-0023 SourceAvailability schema
- ADR-0028 close-maker-fallback dead enum reservation（90d audit 2026-08-21）
- ADR-0029 market.public_trades + orderbook_l2_snapshot storage policy（Proposed，待 MIT calibration）

### Bybit / API
- `docs/references/2026-04-04--bybit_api_reference.md`
- `docs/audits/2026-04-04--bybit_api_infra_audit.md`

### Recent 2026-05-21 audit reports
- QA D1: `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-21--lg1_lg2_7d_closure_phase2a_t72h_verify.md`
- PA D3: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--p1_data_lg5_edge_status_reverify.md`
- E5 F1: `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md`
- FA F2: inline closure（NOT_A_BUG）
- PA F4: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--todo_reorganize_proposal.md`
- FA G2: `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--todo_business_chain_audit.md`

### Archive index
- v55 翻譯歸檔：`docs/archive/2026-05-19--todo_v55_translation_archive.md`
- v57.3 closure cleanup：`docs/archive/2026-05-20--todo_v57_3_closure_cleanup_archive.md`
- v57.5 route change purge：`docs/archive/2026-05-21--todo_v57_5_route_change_purge.md`
- v58 layout refactor：`docs/archive/2026-05-21--todo_v58_layout_refactor_archive.md`（**本檔 PA G1 + FA G2 audit 結論**）

---

## §-1 歷史 closure 一段話留底（最近 14d）

- **2026-05-08~16** v55 4 軌道 closure（watchdog RCA / entry-path RCA / tab-live extract / stress fails）→ archive §A
- **2026-05-19** v56 P0-ENGINE-HALTSESSION-STUCK-FIX incident → 2026-05-20 02:15 UTC Layer A+B LIVE + real-event verified → §C 歸檔
- **2026-05-20** P2 sweep 6 項 closure（QA-TEMPLATE / STRUCT-2 / AUDIT-VERIFY-3 / ENTRY-CLOSE-MAKER / STRESS-BB / SIM-QUEUE-AWARE）→ §I 歸檔
- **2026-05-21 A+B+C+D+E+F+G+H+I 九批 closure**：
  - A: TODO 縮 70 行（v57.3 cleanup）
  - B: 13 governance + 9 planning 入 git
  - C: 8 P2 sweep follow-up（含 healthcheck [66] / ADR-0028/0029 / spec v1.4 AC-20 / FA A-axis verdict / FA phys-lock audit）
  - D: QA D1 LG-1/2 P0 closure + PA D3 P1 reverify + watchdog R2 source land
  - E: TODO 路線變更 purge → `docs/archive/2026-05-21--todo_v57_5_route_change_purge.md`
  - F: 4 actionable attack — F1 E5 P1-LG1-DEMO-SLA → P2-LG1-DEMO-SLO-CARVEOUT / F2 FA P1-FUNDING-ARB-SL NOT_A_BUG / F3 E1→E2→E4 P2-OBS-WILSON 88/88 PASS / F4 PA P2-CANARY-FILE-SIZE DEFER
  - G: TODO layout refactor v58 → v59
  - **H**: 5 backlog actionable closure（commit `296e94b2`）— H1 audit script polish / H2 dyn-stop sentinel 3 test / H3 phys-lock healthcheck [68] / H4 halt-trigger healthcheck [69] / H5 edge-est-snapshots audit；E1+E4+PA+FA → E2 → E4 全 chain PASS；Python 116 + Rust 3045 + adversarial 4/4 真實 catcher
  - **I**: P2-LG1-DEMO-SLO-CARVEOUT 完整 closure（commit `aa0780a3`）— I1 PA spec 429 行 + Rust skeleton 8 unit test + Cargo hdrhistogram=7.5.4 + Grafana JSON 5 panels；I2 E1 hot path 接線 5 plumbing steps + 5 integration test；I3 E2 review APPROVE（3 push back + 2 注意全 ACCEPT；0 BLOCKER）；I4 E4 regression PASS（3272 engine + 410 core + Apple Silicon CI 雙 PASS + adversarial real catcher byte-restore + ML contamination 守住）；衍生 P3-H0GATE-FILE-SPLIT + P3-H0-LATENCY-1H-RESET-INTEGRATION-TEST 入 §6.1 follow-up

歸檔詳情走 `docs/archive/2026-05-21--todo_v58_layout_refactor_archive.md`。

---

**Maintenance contract**：依 `docs/agents/todo-maintenance.md` 將本檔保持為活躍派工佇列。穩定專案脈絡走 `README.md`；agent 操作規則走 `CLAUDE.md`；歷史 closure 走 `docs/archive/`。
