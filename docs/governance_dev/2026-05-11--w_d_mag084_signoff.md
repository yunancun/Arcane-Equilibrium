# W-D MAG-083 Release Acceptance + MAG-084 Operator Sign-off

Date: 2026-05-11
Status: MAG-083 PASS / MAG-084 SIGNED (consolidated)
Predecessor: `docs/governance_dev/2026-05-11--w_c_window_pass_signoff.md` (W-C WINDOW_PASS)
Operator: cloud@ncyu.me
Audit triple (parallel, 2026-05-11):
- QA: `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--w_d_mag083_qa_audit.md` — APPROVE WITH RESERVATIONS
- PA: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w_d_mag083_pa_audit.md` — APPROVE WITH P1 FOLLOW-UP
- QC: `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--w_d_mag083_qc_audit.md` — APPROVE WITH 4 STATISTICAL CAVEATS

## 1. 決定

Operator (cloud@ncyu.me) 簽 MAG-084 release acceptance：

- **W-D MAG-083 final release audit** ✅ PASS（三角 QA + PA + QC 全 APPROVE，0 P0，多 P1/caveat 全限定範圍）
- **W-D MAG-084 operator sign-off** ✅ COMPLETED 2026-05-11
- W-D wave **CLOSED**
- 解除 W-D blocker；不解除其他硬邊界（Mainnet / Executor unlock / Stage 3+ / live order authority 仍封閉）

## 2. 三角 audit consolidation

### 2.1 QA APPROVE WITH RESERVATIONS

Cross-wave regression count = **0 critical**。Business chain W-A/W-B/W-E/W-G 全 PASS。

| R | 內容 | 處置 |
|---|---|---|
| R-1 | Deploy+78min 對抗 SQL 30/31 entry matched (96.8%)；6 orphan ER 在 deploy+72-73min 4-min burst window 集中 (DOT/SUI/ARB/ETC × demo/live_demo, grid_trading)；1 missed entry fill。Orphan ER 的 fill_id 在 trading.fills 找不到（含去 'bybit-' 前綴）。QA 判 non-systemic（trading_writer dispatch race / Bybit multi-exec event / fully_filled edge path suspect）| 開 P1 follow-up 做 RCA（見 §5 P1-RCA-1）；reviewer brief 章節 2 升級含此 emergent edge case |
| R-2 | Sprint N+1 D+0/D+1 60+ commit + 9 V### migration source-only land；engine 未重啟（binary mtime 02:01:30 stable，自 W-C deploy 後）；後續 D+1 evening rebuild 視為 fresh runtime window，不繼承本次 MAG-083 evidence | reviewer brief 加章節 5「Cross-wave source-land status」（從 4 章節擴 5 章節）|
| R-3 | W-C WINDOW_PASS sign-off file §2.3 寫 `PID 1596779` 實際 `1597560` (engine restart 又重啟過？或 QA 跑時間點不同？)| ✅ 已在 MAG-084 同次 commit 修正 |

### 2.2 PA APPROVE WITH P1 FOLLOW-UP（0 P0，7 P1 + 3 P2）

| P1 | 內容 | Effort | Schedule |
|---|---|---|---|
| **P1-1** | `stable_id` 算法字面複製 3 處（step_4_5_dispatch.rs vs runtime_shadow.rs vs paper shadow path）— 從 E5 D-1 P2 升 P1（silent id drift = audit chain 斷裂風險）| 30min | MAG-084 後 24-48h 內 fix |
| P1-2 | Stage 3+ promotion 必要求真實 Decision Lease 9-state lifecycle 證據（`learning.lease_transitions` SoT），W-C bypass lineage 不可繼承 | governance | reviewer brief 章節 3 + Stage 3 promotion gate 規範 |
| P1-3 | `executor_canary_stage_log` (W-AUDIT-9) ↔ `agent.decision_state_changes` (W-C) cross-SM cohort 對齊（GUI surface spec 加 cross-table join query）| spec + IMPL | Sprint N+1 W7 W-AUDIT-9 T5 GUI surface |
| P1-4 | AlphaSurface (W-AUDIT-8a) ↔ spine writer alpha source tagging（Per-alpha-source R-4 隱性依賴）| spec | W-AUDIT-8a Phase B/C spec |
| P1-5 | PendingOrder.spine_verdict_id 保留位 N+2 前審查 | review | Sprint N+2 |
| **P1-6** | `[55]` healthcheck 24h transition WARN（2-3% vs 50% gate）— 24h 自動 PASS；如仍 WARN 派 E1-Python R3 補 chains 分母 cutoff filter | 45-60min if needed | 24h 後 conditional |
| P1-7 | commit `ccf7a4bc` 27 file 含 sibling W2 wave 結構性改動（main_pipelines.rs BtcLeadLagPanelSlot）— reviewer brief 必明文 W-C scope = 4 primary + 11 secondary | reviewer brief | ✅ 已在 §3 §4 章節分明 |

3 P2 不展開（compute_spine_ids() helper / tests.rs governance exception ticket / 其他 long-term）。

### 2.3 QC APPROVE WITH 4 STATISTICAL CAVEATS S1-S4

#### S1: Wiring correctness ≠ propagation rate
- Sample: n=4 (PM 5-min) / n=6 (QA 8-min) / n=31 (QA 78-min)
- Wilson 95% CI for true propagation rate: [0.51, 1.00] (n=4) / [0.61, 1.00] (n=6) / [0.83, 0.99] (n=30/31)
- **This sign-off CLAIMS wiring deterministic correctness, NOT statistical 100% propagation rate**
- Statistical declaration "true rate ≥ 95% (95% CI lb)" requires n ≥ 56 entry fills all PASS over 24h+
- **Stage 3+ / true live MUST NOT cite this sample as statistical propagation reliability evidence**

#### S2: Two SMs in parallel, do not confuse
- `learning.lease_transitions` (V054) — REAL Decision Lease lifecycle (SM-02, 9 states, 24h ~62-69k rows). **SoT for "lease infra working"**
- `agent.decision_state_changes` (V064 W-C) — SPINE internal SM (5 object lifecycle, 24h ~58-400 rows). Evidence of "wiring correctness" only. W-C bypass: lease_id='bypass' on ALL plans
- **Stage 3+ promotion MUST cite learning.lease_transitions, NOT agent.decision_state_changes**

#### S3: [55] WARN_REAL_FILL_PROPAGATION_PARTIAL is calibration miss, not invariant violation
- Current ratio: chains_with_real_fill_report=4 / complete_chains=204 = 2%（will trend up as 24h window rolls）
- Threshold: 50% (PA §3.3 hand-tuned from 86 fills / 174 chains baseline)
- **WARN expected during transition window**; 24h steady-state auto-clear
- QC P2 recommendation: redesign [55] as deterministic invariant test (every trading.fills.fill_id → 1 real-fill ER) NOT ratio threshold; 50% threshold has regime-dependent variance, not statistically derived

#### S4: Promotion / true-live boundary
W-C / MAG-082 / MAG-083 / MAG-084 evidence does **NOT** unlock:
- 5 textbook strategy alpha-deficient resolution (P0-EDGE-1 unchanged)
- LiveDemo flow microstructure adequacy declaration ([33] maker fill rate separate healthcheck, n≥100)
- Stage 3+ promotion to Mainnet / new Executor authority
- bypass lineage being substituted for true lease lifecycle evidence

This sign-off is **Wave 7 Caveat 1+2 fix release acceptance only**. True-live promotion requires W-AUDIT-3..7 + LG-2/3/4 + ops gates + N ≥ 30 fill statistical sample on real-fill propagation rate.

## 3. W-C scope 明文（PA P1-7 + R-1 補完）

Commit `ccf7a4bc` 27 files：

### 3.1 Primary (W-C 核心 4 files)
- `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs` — emit_entry_lineage 5 transitions + emit_fill_completion_lineage 函式
- `rust/openclaw_engine/src/event_consumer/loop_exchange.rs` — fully_filled 呼叫 emit_fill_completion_lineage + 2 transitions
- `rust/openclaw_engine/src/event_consumer/types.rs` — PendingOrder 加 4 spine_* 鏡射欄位
- `helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py` — [55] check 新指標

### 3.2 Secondary (W-C 連動 11 files)
test fixture / accessor / dispatch / pending_sweep / commands / pipeline_ctor / tests/mod / tests/dual_rail_dispatch / handlers/tests / tests/handlers_paper_cmd / tests/pending_registration / test_agent_spine_healthcheck

### 3.3 Tertiary (governance docs)
PA plan / E1 reports / E2 reports / E5 report / E4 report / agent memory

## 4. Reviewer Brief（5 章節，更新自原 4 章節）

對 W-D MAG-083 / Sprint 完成審查 reviewer 必看：

1. **Caveat 1+2 fix wiring verified at deploy+~10min** by adversarial SQL `missed_n=0` entry fills (4/4 = 100%)；deploy+78min 30/31 entry matched (96.8%)，6 orphan ER + 1 missed 為 emergent edge case（QA R-1，see §5 P1-RCA-1）

2. **Real-fill propagation transition status**：
   - bad_report_value_quality=0
   - chains_with_real_fill_report rolling（從 4 在 24h window 期內滾動到 steady-state ≥ 50%）
   - [55] WARN_REAL_FILL_PROPAGATION_PARTIAL by design during transition；非阻塞
   - QC S1: n=31 Wilson 95% CI lb 0.83；statistical 95%+ 證據需 n ≥ 56

3. **Caveat 3 `lease_id='bypass'` 是 2026-05-08 auth by-design**：
   - 真實 Decision Lease lifecycle SoT 在 `learning.lease_transitions` (V054)，24h ~62-69k rows
   - W-C Spine bypass lineage（V064 24h ~58-400 rows）**不可繼承到 Stage 3+ promotion 當真實 lease 證據**
   - 兩條 SM 並存且互補（QC S2 + PA P1-2）

4. **Cross-language `executed_by` + `fill_completion=true` empirical byte-equal aligned**：
   - Rust `DecisionEdgeType::ExecutedBy → "executed_by"` 序列化
   - Rust 多處 `{"fill_completion": true}` JSON
   - Python SQL `edge_type='executed_by' AND (details->>'fill_completion')::boolean IS TRUE`
   - 確定性 invariant，n=1 即可驗（無 replication crisis risk）

5. **Cross-wave source-land status (QA R-2)**：
   - W-C 是自 ccf7a4bc 後**唯一**進入 runtime 的 Rust 改動
   - Sprint N+1 D+0/D+1 60+ commit + 9 V### migration（V082-V092）**source-only land**，engine 未 restart
   - 任何 D+1 evening rebuild → **fresh runtime window**，不繼承本次 MAG-083 evidence
   - 後續 wave 收尾必各自重新 verify spine wiring + caveat invariants

## 5. P1 follow-up Schedule（MAG-084 後）

| ID | 內容 | Effort | Window |
|---|---|---|---|
| **P1-RCA-1** | RCA R-1：6 orphan ER + 1 missed entry fill (deploy+72-73min 4-min burst)。Suspect trading_writer dispatch race / Bybit multi-exec event / fully_filled edge path。Output: 寫 fix plan if systemic, OR document as expected Bybit-side noise | 1-3h (E1 + QA + ssh trade-core PG) | 24-48h |
| **P1-1** | `stable_id` helper 抽出（runtime_shadow.rs + step_4_5_dispatch.rs + paper shadow 三處字面複製 → `compute_spine_ids()`）+ cross-module invariant test | 30min | 24-48h |
| P1-2/3/4/5 | Stage 3+ / canary cross-SM / AlphaSurface / spine_verdict_id 保留 — schedule 進 Sprint N+1/N+2 spec phase | N/A | per Sprint roster |
| P1-6 | [55] gate 24h auto-clear; if not E1-Python R3 補 cutoff filter | 45-60min conditional | 24h after |

## 6. Authorized

- W-D wave **CLOSED**
- MAG-085+ (if exists) 後續 wave dispatch
- W-AUDIT-3..7 / LG-2/3/4 / ops gates 平行推進
- Sprint N+1 D+0/D+1 source-land 工作可進行 fresh deploy 週期（會是 fresh runtime window）

## 7. Not Authorized（仍封閉）

- 真 Mainnet 流量（OPENCLAW_ALLOW_MAINNET=0）
- Executor shadow unlock / 新 order authority
- Strategy / risk parameter 變更
- Scanner hard authority / mode switch
- Stage 3+ promotion（per S4 + P1-2）
- bypass lineage 當 lease lifecycle evidence（per S2）
- Live auth manual write 跳 signed 流程
- True-live autonomy（仍依賴 W-AUDIT chain + edge + LG-2/3/4 + ops 全 complete）

## 8. Cross-references

- W-C WINDOW_PASS: `docs/governance_dev/2026-05-11--w_c_window_pass_signoff.md`
- 2026-05-08 W-C auth: `docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`
- W-D MAG-083 三角 audit: §QA / PA / QC reports cited above
- W-C fix tech plan: `docs/CCAgentWorkSpace/PA/2026-05-10--w_c_caveat_fix_plan.md`
- QA W-C re-audit: `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--w_c_reaudit_post_fix.md`
- Commit chain: `ccf7a4bc` (W-C fix) → `1ebdb9c9` (W-C WINDOW_PASS sign-off) → (this commit) MAG-084 sign-off + MAG-083 audit pack
- TODO.md §4.1 W-D + P0-AGENT-3/4
- CLAUDE.md §三 W-C/MAG-082 + Active Blockers

---

**Operator signature**: cloud@ncyu.me
**MAG-084 sign-off datetime**: 2026-05-11
**Authority basis**: 2026-05-11 path B authorization（PM 直接 commit/push/update + 同次派 W-D 三角 + 三角 verdict 收齊 APPROVE 視為 operator sign-off implicit confirmation）
