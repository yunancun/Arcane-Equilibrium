# W-D MAG-083 Reviewer Brief（for operator MAG-084 sign-off）

**Date**: 2026-05-11
**Authors**: PM（整合 PA + QC + QA 三角 audit；read-only 整合，不重寫 audit 內容）
**Deploy SoT**: commit `ccf7a4bc0822a9885312f1e8f0eb6678705cebc3`
**Runtime HEAD（PM 整合時）**: `dfb7f1ce`
**Sign-off prerequisite**: W-C MAG-082 Stage 2 WINDOW_PASS 已 sign 2026-05-11（`docs/governance_dev/2026-05-11--w_c_window_pass_signoff.md`）
**Reviewer scope**: W-D MAG-083 final release audit 結果整合 → MAG-084 operator sign-off

---

## Executive Summary

### 三角 audit verdict 概覽

| 角色 | Verdict | Report |
|---|---|---|
| **QA**（端到端整合 / SQL 實測）| **PASS** | `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--w_c_reaudit_post_fix.md` |
| **PA**（架構整合 / 風險識別）| **APPROVE WITH P1 FOLLOW-UP**（0 P0 + 7 P1 + 3 P2）| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w_d_mag083_pa_audit.md` |
| **QC**（統計 / 數學審查）| **APPROVE WITH 4 STATISTICAL CAVEATS (S1-S4)** | `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--w_d_mag083_qc_audit.md` |

### W-C 1st-audit 3 caveat 收口狀態

| Caveat | 1st audit 狀態 | Re-audit 狀態 | 證據 |
|---|---|---|---|
| 1: `agent.decision_state_changes` 0 rows all-time | CAVEAT (P1) | **CLOSED** | post-deploy 82 rows / rate 4.8-14.7 row/min |
| 2: ExecutionReport stub-only（filled_qty=0 / liq_role='unknown'）| CAVEAT (P1) | **CLOSED** | post-deploy 6/6 entry-fill 100% propagation；adversarial SQL `missed_n=0`（UTC strict cutoff `2026-05-11T00:01:55+00:00`）|
| 3: `lease_id='bypass'` 174/174 | by-design per 2026-05-08 auth | **DEFERRED**（不在 fix scope）| W-D §3 處理；真實 lease lifecycle 走 `learning.lease_transitions` (V054) |

### MAG-084 sign-off readiness

- **0 P0 blocker**（PA 0 架構 gap；QA 0 corruption / 0 orphan）
- **7 P1 follow-up**（PA 識別）24-48h 內納入 backlog tracker；不阻 MAG-084 sign-off
- **3 P2** (long-term backlog)：文件大小拆 sibling 等
- **4 statistical caveats S1-S4**（QC 強制）必明文寫進 MAG-084 sign-off file（§6 詳列）
- **硬邊界 5 項全部 0 觸碰**：`live_execution_allowed` / `max_retries=0` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json`（PA §G + QA §6 5 hard gates）
- **DOC-08 §12 9 安全不變量 0 觸碰**（PA §G）
- **16 條根原則 0 違反**；原則 #8（交易可解釋）**strengthened**（PA §G）

**Recommendation**: MAG-084 可由 operator sign。前置條件詳 §7 checklist。

---

## 1. Caveat 1+2 fix wiring 驗證（QA §5 強制章節 #1）

**論述**：Caveat 1+2 fix wiring verified at deploy+~10min by adversarial SQL `missed_n=0`。

### 1.1 Caveat 1 — state_changes wiring verified

`agent.decision_state_changes` (V064) producer call gap 已填上：

- **5 build transitions**（`emit_entry_lineage` 末尾 forloop emit）
- **2 change transitions**（`emit_fill_completion_lineage` 在 `loop_exchange.rs:fully_filled` 經 short-circuit if-let-Some 呼叫 emit）

**Empirical 驗證（QA §1 + §2.2）**：

```sql
SELECT count(*) AS total_24h, count(*) FILTER(WHERE ts > now()-interval '5 min') AS last_5min,
       min(ts) AS first_ts, max(ts) AS latest_ts
FROM agent.decision_state_changes
WHERE ts > now()-interval '24 hours';
→ total_24h=82, last_5min=24, first=2026-05-11 02:03:52+02, latest=2026-05-11 02:09:11+02
```

- **Object × mode 平衡**：5 object × 2 mode × 7 chain build = 70；加 2 transition × 2 mode × 3 fill change = 12；total = 82 ✓
- **Rate**：24 rows / 5 min = **4.8 rows/min**（PA target ≥5/min，transition 期接近目標；24h steady-state 預期 ≥5/min）
- PM 5-min snapshot：58 rows；QA 8-min snapshot：82 rows；[55] runtime ~12 min：92 rows — 趨勢一致累積

**結論**：Caveat 1 CLOSED；producer wiring 真實生效。

### 1.2 Caveat 2 — real-fill ER propagation verified

PA §4.3 對抗 SQL（UTC strict cutoff `'2026-05-11T00:01:55+00:00'`）：

```sql
WITH entry_fills AS (
    SELECT replace(fill_id, 'bybit-', '') AS sf, engine_mode
    FROM trading.fills
    WHERE ts > '2026-05-11T00:01:55+00:00'::timestamptz
      AND engine_mode IN ('demo','live_demo')
      AND order_id LIKE 'oc_%' AND order_id NOT LIKE 'oc_risk_%'),
real_reports AS (
    SELECT payload->>'fill_id' AS fill_id, engine_mode
    FROM agent.decision_objects
    WHERE object_type='execution_report'
      AND (payload->>'filled_qty')::numeric > 0
      AND created_at > '2026-05-11T00:01:55+00:00'::timestamptz)
→ entry_fills_post_deploy=6, real_ERs_post_deploy=6, matched=6, missed=0
```

- **Adversarial SQL `missed_n=0` PASS**（100% wiring propagation）
- ER payload 真實值：`filled_qty / liquidity_role / avg_fill_price / fees_paid / fee_bps` 全完整（QA §2.4 6 row sample）
- 舊 stub row 仍寫（intent dispatch 時刻），新 filled row 在 fully_filled 後加；**append-only event log 哲學 ✓**
- `orphan_real_fill_ERs=0`：每個 real-fill ER 都有 `ExecutedBy` edge + `fill_completion=true`（QA §2.6）

**結論**：Caveat 2 CLOSED；real-fill ER caller wiring 真實生效。

> ⚠️ **重要邊界**（QC Caveat S1）：「100% propagation」是 n=4-6 in-sample 觀察，**不是** statistical claim。Wilson 95% CI 下界 `[0.51, 1.00]` (n=4) / `[0.61, 1.00]` (n=6)。MAG-084 sign-off **DOES NOT** claim "propagation rate = 100%" statistically。詳 §6 Caveat S1。

### 1.3 PA §4.3 短窗論證 QA + QC 雙獨立接受

PA 5 點論證：

| # | PA 論證 | QA 結論 | QC 結論 |
|---|---|---|---|
| 1 | 24h window 證量，51h 已證 | 接受 | 接受 |
| 2 | caveat 修正 = deterministic code wiring，不是 statistical sampling | 接受（QA §3）| 接受（QC §G.3）|
| 3 | 30min sample 證新 producer call 真執行 + 新 ER 真值 | **強化** — deploy+~10min 已 empirical 收斂 | 接受 |
| 4 | 歷史 51h evidence chain 不消失 | 接受（pre_deploy_ERs=537 不變）| 接受 |
| 5 | MAG-083 audit pack 必含 caveat fix delta 章節 | 強化（本 brief 即是）| 強化（4 caveat 必含）|

短窗替代 24h 重等的決策得 empirical + 統計雙重 endorse。

---

## 2. Real-fill propagation transition（QA §5 強制章節 #2）

**論述**：Real-fill propagation transition — `bad_report_value_quality=0` / `chains_with_real_fill_report=6` / 24h steady-state 後分母 rolling 達 ≥ 50% gate。

### 2.1 [55] healthcheck transition 期 WARN 解讀

post-deploy `[55] agent_decision_spine_lineage` 報 `WARN_REAL_FILL_PROPAGATION_PARTIAL`。**WARN 是 calibration miss 而非 fix failure**。分解：

```
STATUS: WARN
MSG: agent decision spine real-fill propagation partial
     MAG-082 readiness=WARN_REAL_FILL_PROPAGATION_PARTIAL
     window=1440m modes=demo,live_demo
     objects=1056/2771  edges=846/2218  idempotency=210/553
     types=strategy_signal=210, strategist_decision=210,
           guardian_verdict=210, execution_plan=210, execution_report=216
     chains=210  chains_with_idempotency=210  chains_with_lease=210
     chains_with_report=210  bad_report_quality=0
     bad_report_value_quality=0          ← Caveat 2 value gate PASS
     chains_with_real_fill_report=6      ← Caveat 2 propagation working
     state_changes_24h=92                ← Caveat 1 metric working
     value_quality_cutoff=2026-05-11T00:01:55+00:00  ← env var roundtripped
```

| Metric | Post-fix value | Status | 證據意義 |
|---|---|---|---|
| `bad_report_quality` | 0 | PASS | keyspace 通過（既有 gate）|
| `bad_report_value_quality` | **0** | **PASS** | value-realism 通過（**新 gate 工作；cutoff filter 真排除 historical stub**）|
| `state_changes_24h` | **92** | **PASS** | Caveat 1 metric 真累積（**不再是 0**）|
| `chains_with_real_fill_report` | **6** | **WARN** | 分子（post-deploy real-fill ER）|
| `chains` (denominator) | 210 | — | 含 204 pre-deploy stub-only chains |
| Ratio | 6/210 = 2.86% | WARN（<<50% gate）| Transition 期 expected |

### 2.2 為何 ratio < 50% 是 transition 預期

- WARN 觸發於 `6/210 = 2.86% << 50% gate`
- **分母**含 204 pre-deploy stub-only chains（W-C 51h baseline；append-only event log 無法 retroactively 補 real-fill ER）
- **分子**（post-deploy real-fill ER）僅 6 條（deploy+~10min 起累積）
- 24h steady-state 後分子上升、分母 rolling 換掉 stub-only chains，比率自動 ≥ 50%
- **預期 24h auto-clear 時間**：deploy+24h ≈ **2026-05-12 ~00:02 UTC**（QA §7 Medium-term）

### 2.3 處理選項（QA §4 三選一評估）

| 選 | 描述 | QA verdict |
|---|---|---|
| **A** | 接受 transition 期 WARN，24h steady-state 自動轉 PASS | **推薦** — Empirical 已證 fix correctness；分母 transition 是預期 |
| B | E1-Python round 3 補 cutoff filter 到分子 + 分母（chains 計數加 `WHERE c.created_at > cutoff`） | 不推薦 — 多 ~45-60min critical path；不破 fix correctness |
| **C** | reviewer brief 含 transition 章節說明 | **推薦並行** — 與 A 共行 |

**PM 採納 A + C**：本 brief §2 即為 C 章節。如 operator 要 strict B，可派 E1-Python round 3（不阻 MAG-084 sign-off；P1-6 follow-up §5）。

### 2.4 QC alternative (P2 backlog) — [55] WARN 改 invariant test

QC §C.4 強烈推薦 P2 backlog（**不阻 release**）：

> 棄 50% gate，改 invariant test：每個 `trading.fills.fill_id` 必對應 1 個 real-fill ER。理由：(1) Wiring correctness 是 deterministic invariant，不是 statistical threshold；(2) Invariant test 不受 regime dependency 影響；(3) 對 reviewer「100% mapping」比「ratio ≥ 50%」更 audit-friendly。

PM 接受 P2 backlog 安排；不阻 MAG-084。

---

## 3. Caveat 3 lease_id='bypass' 邊界（QA §5 強制章節 #3）

**論述**：Caveat 3 `lease_id='bypass'` per 2026-05-08 auth 不在 fix scope；真實 lease lifecycle SoT 走 `learning.lease_transitions` (V054)。

### 3.1 By-design 事實

post-deploy plan：16 demo/live_demo plans 全部 `lease_id='bypass'`。

per **2026-05-08 authorization**（`docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`）：

- W-C 僅啟用 router-gate **bypass evidence mode**（`OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` + `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`）
- **bypass = router gate 沒走真實 lease acquire/release lifecycle**，只在 `ExecutionPlan.payload` 標 `lease_id="bypass"` 作 lineage hint
- W-C scope = 證 Spine 結構完整（5 object lineage chain），**不證 lease lifecycle**

### 3.2 兩條 SM log 並存（mandatory wording — QC Caveat S2）

| SM | SoT 表 | 寫入路徑 | 24h 量 | W-D 是否評證據 | Stage 3+ 用途 |
|---|---|---|---|---|---|
| **真實 Decision Lease lifecycle** (SM-02 9-state) | `learning.lease_transitions` (V054) | `governance_hub.py` 直 writer | ~62k row | ✅ 真實 lease 證據 SoT | **YES** — Stage 3+ promotion 必引此表 |
| **Agent Spine SM**（5 object lifecycle）| `agent.decision_state_changes` (V064) | `runtime_shadow.rs` + `loop_exchange.rs` 經 mpsc | 82-92 row（post-fix）| ✅ W-C MAG-082 wiring 證據 | **NO** — bypass only，**不可作 lease lifecycle 證據** |
| Spine bypass evidence | `agent.decision_objects.execution_plan.payload.lease_id = "bypass"` | `runtime_shadow.rs:emit_entry_lineage` | 174→210 row（post-fix 累積）| ⚠️ **W-D 看到此值不可作真實 lease 證據** | **N/A** |

**架構真實**：Spine bypass lineage 與 `learning.lease_transitions` 真實 lifecycle 是**兩條完全獨立的 SM log**。W-C MAG-082 是「Spine 自己的 lineage 完整性」evidence，**不是 Decision Lease lifecycle 真實 exercise 證據**。

### 3.3 Stage 3+ promotion 對 lease 真實證據的要求

Per AMD-2026-05-09-03 §3.5 + DOC-01 §5.5 / §5.6（PA §B.2/B.3）：

Stage 3+ promotion **必須要求**真實 Decision Lease 9-state lifecycle 證據：

- DRAFT → REGISTERED → ACTIVE → BRIDGED → CONSUMED 5 state transitions（happy path）
- DRAFT → REGISTERED → REVOKED（revocation path）
- DRAFT → REGISTERED → EXPIRED（TTL path）
- DRAFT → REGISTERED → REJECTED（Guardian deny path）

**證據 SoT**：`learning.lease_transitions` (V054)，**不是** `agent.decision_objects.execution_plan.payload.lease_id`。

### 3.4 Stage 3+ 之前的補強路徑（PA §B.3）

| Stage | 補強路徑 | Owner |
|---|---|---|
| Stage 2 (W-C) | 接受 bypass lineage 作 Spine 結構完整 evidence，**明確不作 lease lifecycle 證據** | W-D 已執行（本 brief 即為） |
| Stage 3 promotion 前 | (1) `learning.lease_transitions` (V054) 真實 5 state happy-path transitions ≥ N samples per (env, strategy, symbol) cohort；(2) `agent.decision_state_changes.object_type` 擴充 `'decision_lease'` enum（CHECK constraint 升級 V### migration）；(3) Spine `emit_entry_lineage` 寫入真實 lease_id（替代 'bypass'）| W-AUDIT-9 T6（manual promote Decision Lease）IMPL 後 |
| Stage 4 promotion 前 | 跨 30d 觀察期累積 ≥ 1000 真實 lease transitions（哈希分布 + state 跳轉 timing 驗 SM correctness）| Sprint N+2/N+3 |

**結論**：**MAG-083 PASS 不解除 Stage 3 promotion blocker**。W-AUDIT-9 T6 「manual promote Decision Lease」spec 尚未 IMPL；Stage 3 promotion 是 alpha-bearing pathway gate。

---

## 4. Cross-language byte-equal（QA §5 強制章節 #4）

**論述**：Cross-language `executed_by` + `fill_completion=true` empirical byte-equal aligned。

### 4.1 兩端 contract

| 端 | 觀察 | byte-equal |
|---|---|---|
| **Rust write** | `DecisionEdgeType::ExecutedBy` → `"executed_by"` (events.rs:58) + `details = {"fill_completion": true}` (runtime_shadow.rs) | ✓ |
| **Python SQL read** | `edge_type='executed_by' AND (details->>'fill_completion')::boolean IS TRUE` (checks_agent_spine.py:233-234) | ✓ |

### 4.2 Empirical 驗證（QA §2.6 + §2.7）

```
executed_by edges post-deploy: 22 total
  with fill_completion=true: 6  ← 與 real ER count 1:1 對齊
real_ER count = 6
post-deploy entry-fill count = 6
```

**3 個獨立 query 三向對齊**：edges with fill_completion=true (6) = real ER count (6) = post-deploy entry-fill count (6)。Cross-language contract empirical byte-aligned。

### 4.3 Replication crisis risk 評估（QC §D.2）

| Test | Risk |
|---|---|
| Cross-language byte-equal | **deterministic invariant，n=1 即可驗，No risk** |
| Caveat 1+2 deterministic wiring | code path 接線 deterministic，No risk |
| Propagation rate as statistical claim | **MEDIUM** if 後續用 n=4 declare 100% 推到 promotion criteria（已被 Caveat S1 明確 push back）|

---

## 5. 7 P1 follow-up backlog（PA 識別，不阻 MAG-084 sign-off）

PA 識別 7 個 P1 follow-up，24-48h 內納入 backlog tracker；全部不阻 MAG-084 operator sign-off。

| # | 風險 | 影響 | Owner | ETA | Mitigation 路徑 |
|---|---|---|---|---|---|
| **P1-1** | `stable_id` 算法字面複製 3 處（`step_4_5_dispatch.rs:623-645` exchange path + `:1178?` paper shadow path + `runtime_shadow.rs:72-80`）| 未來改 stable_id 算法漏改 = sub-architectural silent id drift = audit chain 斷裂 | PA + E5 | MAG-084 後 24-48h | 抽 `pub(crate) fn compute_spine_ids(em, signal_id, verdict_id) -> (decision_id, plan_id, stub_report_id)` helper 到 `agent_spine/events.rs`。30min effort。E5 D-1 P2 升 P1 |
| **P1-2** | Stage 3+ promotion 與真實 Decision Lease 9-state lifecycle 證據：W-C bypass lineage 不可繼承 | Stage 3 promotion 前如以 W-C evidence 直接升 = governance fraud | PA | W-AUDIT-9 T6 IMPL 後 | 本 brief §3 即為強烈 push back；reviewer brief Caveat 3 章節 mandatory（QA §5 第 3 點 + PA §B.3 Stage 3 補強路徑）|
| **P1-3** | `executor_canary_stage_log` (W-AUDIT-9) 與 `agent.decision_state_changes` (W-C) 跨 SM 對齊：trace_id / cohort_id 跨表 join | W-AUDIT-9 IMPL 後 operator review GUI 無法 drill-down 從 cohort 到 chain | PA + E1-G | W-AUDIT-9 T5 GUI surface IMPL 前 | W-AUDIT-9 T5 GUI surface spec 加 cross-table join query；同 commit 加 P2 schema cross-ref ticket |
| **P1-4** | AlphaSurface (W-AUDIT-8a) 與 spine writer alpha source tagging 接線：`strategy_signal.payload` 加 `alpha_source` 字段 | Per-alpha-source live promotion gate (R-4) blocker；W-AUDIT-8e/8f/8g IMPL 隱性依賴 | PA | W-AUDIT-8a Phase B 啟動前 | W-AUDIT-8a Phase B spec 啟動前在 PA 端設計 alpha source tag schema migration spec |
| **P1-5** | `PendingOrder.spine_verdict_id` 保留位：4 spine_* 欄位中 verdict_id 未被 `emit_fill_completion_lineage` 使用 | N+2 sprint 前如無使用點 = dead struct field 累積，違反 §九 結構約定文化 | E1 + PA | N+2 sprint 前 | N+2 sprint 前 audit dead field；如無使用點移除（或 partial-fill metadata 擴展真實使用 verdict_id）|
| **P1-6** | `[55]` healthcheck 24h transition window：post-deploy WARN_REAL_FILL_PROPAGATION_PARTIAL（2.86% << 50% gate）| 24h steady-state 自動 PASS 是 calibration miss；如未滾過 24h cliff = silent FAIL 漂移源 | E1-Python | MAG-084 sign-off 後 24h 內 operator check | optional：E1-Python R3 補 chains 分母 cutoff filter（45-60min effort）；或接受 24h 自然 roll-over（**PM 採納後者 + 本 §2 章節說明**）|
| **P1-7** | commit `ccf7a4bc` 27 file 含 sibling W2 wave 結構性改動（`main_pipelines.rs` BtcLeadLagPanelSlot 等）| W-C 純度不 100%；reviewer 看 27 file diff 時需區分 W-C vs sibling | PM | 本 brief 內收口 | 本 brief §5.1 即明文 W-C scope vs sibling W2 wave separate authority |

### 5.1 P1-7 commit `ccf7a4bc` 純度說明（PM 收口）

PA §F.2 識別：commit `ccf7a4bc` 27 files / +3964 -17 LOC，包含：

- **W-C primary**：4 file（`runtime_shadow.rs` / `loop_exchange.rs` / `types.rs` / `checks_agent_spine.py`）
- **W-C secondary**：11 file（test fixture + accessor + dispatch + dual_rail + `tests/mod.rs` 等）
- **Sibling W2 wave 結構性 commit**：`main_pipelines.rs` BtcLeadLagPanelSlot 連動（per E4 §F.2 + E1 R2 §6 C-Round2-2）

**Mitigation**：
- E4 §A 雙 profile 一致 2776/0/0 PASS — 證 commit 整體 build + test 健全
- Linux deploy cargo build 32.99s clean + engine PID 1596779 healthy（per sign-off §2.3）
- **Reviewer 看 27 file diff 時必區分**：W-C scope = 4 primary + 11 secondary file；sibling W2 wave 在同 commit 但**屬 separate wave authority**

### 5.2 P2 long-term backlog（PA §G + QC §C.4）

| # | 風險 | Owner | Path |
|---|---|---|---|
| P2-1 | `tests.rs` 1063 LOC > 800 警告（W-C +361）拆 sibling 仿 G5-09 | E5 | 拆 4-5 sibling（runtime_shadow_lineage / channel_store / contracts / signal_adapter）|
| P2-2 | `step_4_5_dispatch.rs` 1557 LOC > 800 警告（pre-existing）拆 sibling | E5 | 拆 exchange_path / paper_path / spine_id_compute |
| P2-3 | `runtime_shadow.rs` 657 LOC trending toward 800；`emit_entry_lineage` 單 fn 接近 IMP 上界 | E5 | 抽 build_transitions helper |
| P2-4（QC §C.4）| [55] WARN 改 deterministic invariant test 取代 ratio threshold | E1-Python + PA | 棄 50% gate；每個 `trading.fills.fill_id` 必對應 1 個 real-fill ER（QC §C 推薦 C 方案）|

---

## 6. 4 statistical caveats S1-S4（QC 強制必含）

QC §300 強制 4 條 caveat 必明文寫進 MAG-084 sign-off file。每條附完整 push back 條件 + 量化建議。

### 6.1 Caveat S1 — Wiring correctness ≠ propagation rate（最關鍵）

```
Sample: n=4 entry fills (PM 5-min snapshot) / n=6 (QA 8-min snapshot) post-deploy
Observation: 100% propagation to real-fill ER (4/4 or 6/6)
Wilson 95% CI for true propagation rate:
  - n=4: [0.51, 1.00]
  - n=6: [0.61, 1.00]

This sign-off CLAIMS wiring deterministic correctness (caller is wired).
This sign-off DOES NOT CLAIM "propagation rate = 100%" statistically.

Statistical declaration "true rate ≥ 95% (95% CI lb)" requires n ≥ 56 entry fills all PASS over 24h+ window.
Statistical declaration "true rate ≥ 99% (95% CI lb)" requires n ≥ 296 entry fills all PASS over ~6 days.

Stage 3+ / true live promotion MUST NOT cite this sample as statistical propagation reliability evidence.
```

**Push back 條件**（QC §B.5）：

- 任何後續報告引用「100% real-fill propagation」作 statistical claim → **拒絕 + 要求加 CI 標註**
- 任何 Stage 3+ promotion 直接引此 n=4-6 sample 作 propagation reliability → **governance violation**

**量化建議（QC §B.4）**：

| Declare | n | demo 等多久 |
|---|---|---|
| true rate ≥ 50% (Wilson lb) | n ≥ 4 ✓ | 5 min |
| true rate ≥ 80% | n ≥ 12 all-PASS | ~1h |
| true rate ≥ 95% | n ≥ 56 all-PASS | ~24h |
| true rate ≥ 99% | n ≥ 296 all-PASS | ~6 days |

### 6.2 Caveat S2 — Two SMs in parallel, do not confuse

```
Two SMs in parallel — DO NOT CONFUSE:

1. learning.lease_transitions (V054) — REAL Decision Lease lifecycle (SM-02)
   - 9 states: DRAFT → REGISTERED → ACTIVE → BRIDGED → CONSUMED → ...
   - 24h count ~62k rows (real lease lifecycle)
   - SoT for "true-live lease infra working" claim
   - Stage 3+ promotion MUST cite this table

2. agent.decision_state_changes (V064, W-C lineage) — SPINE internal SM
   - 5 object types: strategy_signal, strategist_decision, guardian_verdict, execution_plan, execution_report
   - 24h count ~58-92 rows (Spine lineage chain build + state change)
   - Evidence of "wiring correctness", NOT lease lifecycle
   - W-C bypass mode: lease_id='bypass' on ALL plans
   - Stage 3+ promotion MUST NOT cite this table as lease evidence
```

**Push back 條件**（QC §E.3）：

- 任何 reviewer / operator 看 Spine state_changes 92 rows 以為「Decision Lease lifecycle 92 次運轉」→ **嚴重 misread，立即更正**
- 任何 Stage 3+ promotion documentation 引 `agent.decision_state_changes` 當 lease evidence → **governance violation**

**量化建議（PA §B.3 補強）**：

- Stage 3 promotion 前：`learning.lease_transitions` (V054) 真實 5 state happy-path transitions ≥ N samples per (env, strategy, symbol) cohort
- Stage 4 promotion 前：跨 30d 觀察期累積 ≥ 1000 真實 lease transitions

### 6.3 Caveat S3 — [55] WARN is calibration miss, not invariant violation

```
Current ratio: chains_with_real_fill_report=6 / complete_chains=210 = 2.86%.
Threshold: 50% (PA §3.3 hand-tuned from 86 fills / 174 chains baseline).

WARN expected during transition (denominator inflated by 204 pre-deploy stub-only chains;
append-only event log cannot retroactively add real-fill ER).

Steady-state 24h post-deploy: WARN should auto-clear as denominator rolls over.
Expected auto-clear time: deploy+24h ≈ 2026-05-12 ~00:02 UTC

QC recommendation (P2 backlog, NOT release blocker):
- E1-Python R3 add cutoff filter to denominator (PA optional follow-up)
- OR redesign [55] WARN as deterministic invariant test:
  - Every trading.fills fill_id → exactly 1 real-fill ER
  - NOT ratio threshold
- 50% threshold has regime-dependent variance and is NOT statistically derived
```

**Push back 條件**（QC §C.4）：

- 如 24h 後 [55] 仍 WARN → 派 E1-Python R3 補 cutoff filter（不阻 MAG-084，但作 follow-up）
- 任何試圖將 50% 作 "statistically derived threshold" 引用 → **拒絕**（hand-tuned，非 derived）

**量化建議（QC §C.4 推薦 C 方案）**：

- P2 backlog redesign [55] gate：每個 `trading.fills.fill_id` 必對應 1 個 real-fill ER（deterministic invariant test）
- 不受 regime dependency 影響；audit-friendly

### 6.4 Caveat S4 — Promotion / true-live boundary

```
W-C / MAG-082 / MAG-083 / MAG-084 evidence does NOT unlock:

1. 5 textbook strategy alpha-deficient resolution (P0-EDGE-1 unchanged)
2. LiveDemo flow microstructure adequacy declaration ([33] maker fill rate remains separate)
3. Stage 3+ promotion to Mainnet / new Executor authority
4. bypass lineage being substituted for true lease lifecycle evidence

This sign-off is Wave 7 Caveat 1+2 fix release acceptance only.

True-live promotion requires:
- W-AUDIT-3..7 (runtime/fake-live alignment + security + edge + ops)
- LG-2/3/4 (Live Gate foundation)
- ops gates (HTTPS / credential rotation / legal / first-day runbook)
- N ≥ 30 fill statistical sample on real-fill propagation rate
- operator explicit sign-off
```

**Push back 條件**（QC §D.1）：

- 任何試圖將 W-C/MAG-082/083/084 evidence 推到上 4 條 unlock → **拒絕 + governance violation**
- 任何引用此 release evidence 作 5 textbook 策略 alpha-deficient 結論已解決 → **cross-contamination risk MEDIUM**

**對抗性樣本建議（W-D 後 / Stage 3 前必跑，QC §D.3）**：

| Case | 期望 | Fail risk |
|---|---|---|
| Partial fill | 不寫 transition (by-design); real-fill ER 寫一條 | state_changes 漏接 partial event |
| Network 中斷 mid-chain (engine restart 30s gap) | Append-only; restart 後新 intent 開始 | Orphan plan rows |
| mpsc channel full → put_state_transition try_send drop | warn log; 下一 emit 正常 | state_changes_24h 短暫 drop |

W-D operator 可選不跑這 3 個對抗 case 就簽 MAG-084，但要在 sign-off file 明寫「Stage 3 promotion 前 must run」。

---

## 7. MAG-084 operator sign-off checklist

PM 給 operator 的 sign-off 前置條件 + 簽署要點清單。

### 7.1 Hard pre-condition（必要條件）

| # | 條件 | 狀態 | 證據 |
|---|---|---|---|
| 1 | W-C MAG-082 Stage 2 WINDOW_PASS sign-off | ✅ DONE 2026-05-11 | `docs/governance_dev/2026-05-11--w_c_window_pass_signoff.md`（cloud@ncyu.me 簽）|
| 2 | QA E2E audit PASS | ✅ DONE | `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--w_c_reaudit_post_fix.md`（Caveat 1+2 CLOSED / Caveat 3 DEFERRED）|
| 3 | PA architecture audit verdict | ✅ APPROVE WITH P1 FOLLOW-UP | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w_d_mag083_pa_audit.md`（0 P0 + 7 P1 + 3 P2）|
| 4 | QC statistical audit verdict | ✅ APPROVE WITH 4 CAVEATS | `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--w_d_mag083_qc_audit.md`（S1-S4）|
| 5 | Reviewer brief 4 章節 必含 | ✅ 本 brief §1-§4 完整 | 本檔 §1-§4 |
| 6 | 硬邊界 5 項 0 觸碰 | ✅ Confirmed | PA §G + QA §6 + 本 brief §7.4 |
| 7 | DOC-08 §12 9 安全不變量 0 觸碰 | ✅ Confirmed | PA §G |
| 8 | 16 條根原則 0 違反；原則 #8 strengthened | ✅ Confirmed | PA §G |

### 7.2 簽署要點（operator 確認）

簽 MAG-084 時 operator 必明確 acknowledge：

1. ✅ **Caveat 1+2 修復鏈 empirically verified**：post-deploy adversarial SQL `missed_n=0`；state_changes_24h=82-92；real-fill ER 6/6 propagation
2. ✅ **Caveat 3 lease_id='bypass' by-design**：W-C bypass evidence mode per 2026-05-08 auth；真實 lease lifecycle SoT 走 `learning.lease_transitions` (V054)；Stage 3+ promotion MUST NOT cite W-C as lease evidence
3. ✅ **4 statistical caveats S1-S4 寫進 sign-off file**（§6 全文）：
   - S1 Wiring correctness ≠ propagation rate（n=4-6 Wilson 95% CI lb 51-61%）
   - S2 Two SMs in parallel — do not confuse（V054 vs V064 SoT 區分）
   - S3 [55] WARN is calibration miss not invariant violation
   - S4 Promotion / true-live boundary 不解鎖（W-AUDIT-3..7 + LG-2/3/4 + ops + N≥30 真實樣本）
4. ✅ **7 P1 follow-up 24-48h 進 backlog**（§5 列）；3 P2 long-term
5. ✅ **commit `ccf7a4bc` 純度說明**：W-C scope = 4 primary + 11 secondary file；sibling W2 wave 在同 commit 但 separate wave authority（§5.1）
6. ✅ **[55] WARN 24h auto-clear 預期**：deploy+24h ≈ 2026-05-12 ~00:02 UTC；如 24h 後仍 WARN → 派 E1-Python R3 補 cutoff filter（不阻 MAG-084）
7. ❌ **不解除任何硬邊界**：Mainnet / Executor 解鎖 / Stage 3+ / live order authority 仍封閉
8. ❌ **不解除 P0-EDGE-1** / **不認可 5 textbook 策略 alpha-deficient 已解決**（QC Caveat S4 push back）

### 7.3 PA 不建議的 pre-condition（PM 明確拒絕作 sign-off blocker）

PA §5 明列 4 條**不建議**作 MAG-084 sign-off blocker：

- ❌ 不要求 P1-2 Stage 3+ lease lifecycle 證據先 land（屬 W-AUDIT-9 T6 + 後續 sprint）
- ❌ 不要求 P1-3 cross-SM trace_id join 先 land（屬 W-AUDIT-9 T5 GUI surface）
- ❌ 不要求 P1-4 AlphaSurface alpha source tagging 先 land（屬 W-AUDIT-8a Phase B）
- ❌ 不要求 P2-1/-2/-3 文件拆 sibling 先 land（governance exception 接受）

### 7.4 硬邊界檢查 final 確認

| 項 | 狀態 | 證據 |
|---|---|---|
| `live_execution_allowed` | ✅ 0 觸碰 | PA §G + E1 R1 §7.4 |
| `max_retries = 0` | ✅ 0 觸碰 | PA §G + E1 R1 §7.4 |
| `OPENCLAW_ALLOW_MAINNET` | ✅ 0 觸碰（NOT SET correct — LiveDemo only）| QA §6 + PA §G |
| `live_reserved` | ✅ 0 觸碰 | PA §G + sign-off §5 |
| `authorization.json` | ✅ 0 寫入（只讀 by [56]）| QA §2 + E4 §B |
| `decision_lease_emitted = "shadow_bypass_lineage_only"` | ✅ 保持 W-C 授權範圍 | sign-off §1 + 2026-05-08 auth |
| `executor_canary_stage` | ✅ Stage 0 default 不變 | AMD-2026-05-09-03 |
| 16 原則 #1 單一寫入口 | ✅ 不影響（IntentProcessor 不動）| E1 R1 §7.4 |
| 16 原則 #3 AI ≠ 命令 | ✅ 不影響（emit lineage 不下單）| E1 R1 §7.4 |
| 16 原則 #4 不繞風控 | ✅ 不影響（Guardian 不動）| E1 R1 §7.4 |
| 16 原則 #7 學習 ≠ 改寫 Live | ✅ 強化（更完整的 audit log）| PA spec §7 |
| 16 原則 #8 交易可解釋 | ✅ **強化**（state_changes 補齊 + real-fill ER 補齊）| E1 R1 §7.4 + sign-off §2.4 |
| DOC-08 §12 9 安全不變量 | ✅ 0 觸碰 | PA §G + E1 R1 §7.4 |
| §三 W-C row 一致性 | ✅ sign-off + commit chain 對齊 | sign-off §2.3 |

---

## 8. Cross-references

### 8.1 三 audit reports

- **QA re-audit (PASS)**: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--w_c_reaudit_post_fix.md`
- **PA audit (APPROVE WITH P1 FOLLOW-UP)**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w_d_mag083_pa_audit.md`
- **QC audit (APPROVE WITH 4 CAVEATS)**: `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--w_d_mag083_qc_audit.md`

### 8.2 W-C 修復鏈工件

- **PA Caveat 1+2 fix plan**: `srv/docs/CCAgentWorkSpace/PA/2026-05-10--w_c_caveat_fix_plan.md`
- **E1 Rust R1 IMPL**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w_c_fix_rust_impl.md`
- **E1 Rust R2 IMPL**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w_c_fix_rust_impl_round2.md`
- **E1 Python IMPL**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w_c_fix_python_impl.md`
- **E2 R1 review**: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-10--w_c_fix_e2_review.md` (APPROVE WITH CONDITIONS)
- **E2 R2 review**: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w_c_fix_e2_review_round2.md` (APPROVE)
- **E5 perf review**: `srv/docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-10--w_c_fix_e5_perf_review.md` (APPROVE WITH 3 P2)
- **E4 regression**: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_c_fix_e4_regression.md` (READY)

### 8.3 Governance / authorization

- **W-C WINDOW_PASS sign-off**: `srv/docs/governance_dev/2026-05-11--w_c_window_pass_signoff.md`
- **W-C lease router authorization**: `srv/docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`
- **SM-02 R04 retrofit Path A**: `srv/docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`
- **AMD-2026-05-09-03 graduated canary default**: `srv/docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md`

### 8.4 Deploy / runtime

- **W-C deploy commit**: `ccf7a4bc0822a9885312f1e8f0eb6678705cebc3`
- **Deploy_ts (UTC)**: `2026-05-11T00:01:55+00:00`
- **Engine PID (post-deploy)**: 1596779 → 1597560（subsequent restart verified by QA）
- **Runtime HEAD (at PM brief integration)**: `dfb7f1ce`

---

## Final Verdict

**W-D MAG-083 三角 audit consensus**:

- **QA**: PASS — Caveat 1+2 empirically CLOSED；Caveat 3 DEFERRED；[55] WARN transition 自然 24h auto-clear
- **PA**: APPROVE WITH P1 FOLLOW-UP — 0 P0 架構 gap；7 P1 + 3 P2 backlog
- **QC**: APPROVE WITH 4 STATISTICAL CAVEATS — S1-S4 必明文寫進 MAG-084 sign-off file

**MAG-084 operator sign-off READY**。Pre-condition §7.1 全部達成；簽署要點 §7.2 全部明列；硬邊界 §7.4 全部 0 觸碰。

Operator 簽 MAG-084 即可 unlock W-AUDIT-3..7 + LG-2/3/4 + ops gates 下一波 dispatch；**不解除** Stage 3+ / Mainnet / Executor / live order authority。

---

**Report path**: `srv/docs/governance_dev/2026-05-11--w_d_mag083_reviewer_brief.md`

**PM REVIEWER BRIEF DONE**
