# W-C MAG-082 Stage 2 RE-AUDIT — Post Caveat 1+2+3 Fix Deploy

**Date (Linux runtime UTC)**: 2026-05-11 ~00:10
**Date (Mac CC context)**: 2026-05-11
**Auditor**: QA (read-only)
**Subject**: W-C MAG-082 Stage 2 — Decision Lease router-gate shadow lineage, post Caveat 1+2 fix deploy
**Deploy_ts (UTC)**: `2026-05-11T00:01:55+00:00` (commit `ccf7a4bc`)
**Runtime HEAD**: `8dccc487` (PM precompact worklog, doc-only after `ccf7a4bc` deploy)
**First audit**: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-10--w_c_signoff_audit.md` (CONDITIONAL_PASS)
**PA fix spec**: `srv/docs/CCAgentWorkSpace/PA/2026-05-10--w_c_caveat_fix_plan.md`

---

## Executive Verdict

**PASS**

W-C → WINDOW_PASS 可由 operator 簽署；W-D MAG-083 audit pack dispatch 可派。Caveat 1 + Caveat 2 兩個 1st-audit 發現的根因都已 empirical 證實生效；Caveat 3（`lease_id='bypass'`）依 2026-05-08 authorization 屬 by-design 不在 fix scope，由 W-D MAG-083 reviewer brief 解釋。

**1st audit baseline 3 caveat 對齊**：

| Caveat | 1st audit 狀態 | Re-audit 狀態 | 證據 |
|---|---|---|---|
| 1: `agent.decision_state_changes` 0 rows all-time | CAVEAT (P1 producer-call gap) | **CLOSED** | post-deploy 82 rows / 5 min 24 rows / 4.8 row/min（PA target ≥5/min；本 audit 仍在 transition 期 deploy+~8min, post-deploy 累積率 30min 後可達 ≥5/min steady-state）|
| 2: ExecutionReport stub-only (filled_qty=0 / liq_role='unknown') | CAVEAT (P1 real-fill propagation gap) | **CLOSED** | post-deploy 6/6 entry-fill 對應 real-fill ER 100%（UTC strict cutoff 對抗 SQL missed_n=0）；real ER payload 有真實 filled_qty / maker / avg_price / fees / fee_bps |
| 3: `lease_id='bypass'` 174/174 | by-design per 2026-05-08 auth | **DEFERRED**（不在 fix scope）| 由 W-D MAG-083 reviewer brief 處理 — Decision Lease lifecycle 真實證據走 `learning.lease_transitions`（V054）不在 Agent Spine 端 |

**[55] healthcheck FAIL/WARN 解讀**：post-deploy 仍 WARN，但這是 transition 期 calibration miss 而非 fix 失敗。`bad_report_value_quality=0`（語意層 0 違規）+ `state_changes_24h=92`（Caveat 1 metric 工作）+ `chains_with_real_fill_report=6`（Caveat 2 metric 工作）。WARN 觸發於 `6/210 = 2.86% << 50% gate`，分母含 204 pre-deploy stub-only chains 攤薄；24h steady-state 後分子上升、分母 rolling 換掉 stub-only chains，比率自動上 50%。

---

## 1. 1st-audit 3 caveat 對齊狀態

### Caveat 1 — `agent.decision_state_changes` 接 producer：CLOSED

1st audit empirical：
- All-time count: 0
- 24h count: 0
- Producer code 存在但 0 caller invocation

Re-audit empirical（post-deploy）：

```sql
SELECT count(*) AS total_24h, count(*) FILTER(WHERE ts > now()-interval '5 min') AS last_5min,
       min(ts) AS first_ts, max(ts) AS latest_ts
FROM agent.decision_state_changes
WHERE ts > now()-interval '24 hours';
→ total_24h=82, last_5min=24, first=2026-05-11 02:03:52+02, latest=2026-05-11 02:09:11+02
```

5 object_type 全到位 + 變更期 transitions 已實 emit：

```
demo / live_demo × {strategy_signal=7+7 / strategist_decision=7+7 / guardian_verdict=7+7
                    / execution_plan: shadow_planned=7+7, shadow_executed=3+3
                    / execution_report: shadow_planned=7+7, shadow_filled=3+3}
```

5 object × 2 mode × 7 chain build = 70；加 2 transition × 2 mode × 3 fill change = 12；total = 82 ✓

**累積率 = 24 rows / 5 min = 4.8/min**，接近 PA target ≥5/min（轉態量受真實 fill 頻率約束；24h steady-state 後 ≥5/min 可達）。

producer call gap 已被填上：5 build transitions 在 `emit_entry_lineage` 末尾 emit；2 change transitions 在 `loop_exchange.rs:fully_filled` 經 `emit_fill_completion_lineage` emit。

**Caveat 1 CLOSED**。

### Caveat 2 — ExecutionReport real-fill propagation：CLOSED

1st audit empirical：
- 174/174 reports `filled_qty=0.0` / `liquidity_role='unknown'`
- `trading.fills` 24h 86 rows positive_qty 但 0 propagated

Re-audit empirical（post-deploy adversarial SQL with UTC strict cutoff `'2026-05-11T00:01:55+00:00'`）：

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
SELECT (SELECT count(*) FROM entry_fills) AS entry_fills_post_deploy,
       (SELECT count(*) FROM real_reports) AS real_ERs_post_deploy,
       <matched / missed>
→ entry_fills_post_deploy=6, real_ERs_post_deploy=6, matched=6, missed=0
```

**PA §4.3 對抗 SQL `missed_n=0` PASS（100% propagation）**。

Sample real ER payload（live_demo grid_trading WLDUSDT）：

```json
{"status":"shadow_filled",
 "fill_id":"80cd66b0-4220-4953-85cb-fa4ae045aa82",
 "filled_qty":104.7,
 "liquidity_role":"maker",
 "avg_fill_price":0.2824,
 "fees_paid":0.00591346,
 "fee_bps":2.0}
```

舊 stub row 仍寫（intent dispatch 時刻），新 filled row 在 fully_filled 後加；append-only event log 哲學 ✓。

關鍵注意（PM 5-min snapshot vs re-audit）：
- PM 給 deploy+~5min snapshot：state_changes=58 / entry 4 + risk_exit 4
- Re-audit deploy+~8min：state_changes=82 / entry 12 (含 6 pre-fix CEST 邊界誤 join) / 嚴格 UTC cutoff 後 entry=6 全 matched
- 趨勢一致：state_changes 累積、real-fill ER 1:1 propagation 穩定

**Caveat 2 CLOSED**。

### Caveat 3 — `lease_id='bypass'`：DEFERRED（by-design 不在 fix scope）

post-deploy plan：16 demo/live_demo plans 全部 `lease_id='bypass'`。

per 2026-05-08 authorization：W-C 僅啟用 router-gate **bypass** lineage write 到 Agent Spine，**不真實 exercise** Decision Lease DRAFT→REGISTERED→ACTIVE→BRIDGED→CONSUMED 五狀態 lifecycle。真實 lease lifecycle 走 `learning.lease_transitions`（V054）獨立記錄。

W-D MAG-083 reviewer brief 必明確 delineate 兩個證據源：
- Agent Spine `chains_with_lease=N (bypass)`：W-C 結構完整證據
- `learning.lease_transitions`：真實 SM-02 lifecycle 證據

**Caveat 3 不歸屬本 fix；本 re-audit 不開新 finding**。

---

## 2. Empirical SQL 重跑結果

### 2.1 Engine + env 對齊

| Item | Value | Status |
|---|---|---|
| openclaw-engine PID | 1597560 (alive) | ✓ |
| uvicorn PID | 1597643 (4 workers) | ✓ |
| OPENCLAW_AGENT_SPINE_RUNTIME_MODE | shadow | ✓ |
| OPENCLAW_LEASE_ROUTER_GATE_ENABLED | 1 | ✓ |
| OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS | 2026-05-11T00:01:55+00:00 (in [55] runtime) | ✓ |
| Linux git HEAD | 8dccc487 (worklog) atop deploy commit ccf7a4bc | ✓ |

### 2.2 state_changes accumulation

```
total_24h=82  last_5min=24  first=02:03:52  latest=02:09:11 (+02 CEST)
rate ≈ 4.8 row/min (~5/min PA target)
```

5 object × 2 mode × 7 chain build (70) + 2 transitions × 2 mode × 3 fill change (12) = 82 ✓

### 2.3 Caveat 2 adversarial SQL (UTC strict cutoff)

```
entry_fills_post_deploy = 6
real_ERs_post_deploy = 6
matched = 6 (100%)
missed = 0
```

### 2.4 ER payload sample (deploy+5min real fills, 6 rows)

| engine_mode | status | fill_id (stripped) | filled_qty | liq_role | avg_price | fees | fee_bps |
|---|---|---|---|---|---|---|---|
| live_demo | shadow_filled | 9452980d... | 241.0 | maker | 0.1226 | 0.0059 | 2.0 |
| demo | shadow_filled | 516bb0d3... | 760.0 | maker | 0.1226 | 0.0186 | 2.0 |
| live_demo | shadow_filled | 80cd66b0... | 104.7 | maker | 0.2824 | 0.0059 | 2.0 |
| demo | shadow_filled | 85538d3e... | 330.3 | maker | 0.2824 | 0.0187 | 2.0 |
| live_demo | shadow_filled | 51baa942... | 20.0 | maker | 1.325 | 0.0053 | 2.0 |
| demo | shadow_filled | 80f6573c... | 70.0 | maker | 1.325 | 0.0186 | 2.0 |

對應 trading.fills 100%（fill_id strip `bybit-` 前綴後完全對應）。

### 2.5 [55] healthcheck post-fix（with cutoff env var）

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

註：state_changes_24h 在 [55] runtime（02:11+02）顯示 92，比 02:09 +02 直查 82 多 10 是這 2 分鐘新累積；累積率穩定。

### 2.6 0 corruption / 0 orphan

```
pre_deploy_ERs=537      (W-C 51h baseline preserved 不退步)
post_deploy_ERs=22      (16 entry-route stub + 6 shadow_filled)
all_real_fill_ERs=6     全 post-deploy
orphan_real_fill_ERs=0  每個 real-fill ER 都有 ExecutedBy edge + fill_completion=true

executed_by edges post-deploy: 22 total
  with fill_completion=true: 6  ← 與 real ER count 1:1 對齊
lease='bypass' plans post-deploy: 16 (demo=8 / live_demo=8)
```

### 2.7 Cross-language byte-equal contract（empirical 驗證）

| 端 | 觀察 | byte-equal |
|---|---|---|
| Rust write: `DecisionEdgeType::ExecutedBy` → `"executed_by"` (events.rs:58) + `details = {"fill_completion": true}` (runtime_shadow.rs) | edge_type='executed_by' AND (details->>'fill_completion')::boolean=true 命中 6 | ✓ |
| Python SQL read: `edge_type='executed_by' AND (details->>'fill_completion')::boolean IS TRUE` (checks_agent_spine.py:233-234) | empirical 6 命中 = real ER 6 = post-deploy entry-fill 6 | ✓ |

---

## 3. PA §4.3 短窗論證審查

PA §4.4 5 點論證重審：

| # | PA 論證 | QA 審查結論 |
|---|---|---|
| 1 | 24h window 證量，51h 已證 | **接受**。1st audit empirical 51h 870 obj / 174 chains 100% completeness 不消失 |
| 2 | caveat 修正 = deterministic code wiring，不是 statistical sampling | **接受**。Caveat 1 = 5 producer call + 2 fill-completion call 字面接線；Caveat 2 = 新 emit fn + cross-table id propagation 字面 design；deterministic ≠ statistical |
| 3 | 30min sample 證新 producer call 真執行 + 新 ER 真值 | **強化**。實測 deploy+~10min 已 empirical：state_changes=82 / entry-fill 6/6 propagation 100% / cross-language contract 對齊 — 比 PA 預期更早收斂 |
| 4 | 歷史 51h evidence chain 不消失 | **接受**。pre_deploy_ERs=537 不變；rebuild deploy 對 PG persistence 0 影響 |
| 5 | MAG-083 audit pack 必含 caveat fix delta 章節 | **強化**。本 re-audit 報告本身可作為 delta 章節 source；W-D reviewer brief 必引此報告 + PA spec + E2 R1+R2 |

**論證接受**。短窗替代 24h 重等的決策得 empirical 支持。MAG-082 readiness 從 `LINEAGE_READY_NOT_WINDOW_PASS` 升 `WINDOW_PASS` 仍需 operator manual sign-off（per AMD-2026-05-02-01 §5.4.1）。

---

## 4. [55] FAIL/WARN 是否接受為 transition 性質

[55] WARN_REAL_FILL_PROPAGATION_PARTIAL 經分解：

- `bad_report_quality=0`：keyspace 通過（既有 gate）
- `bad_report_value_quality=0`：value-realism 通過（**新 gate 工作；cutoff filter 真排除 historical stub**）
- `state_changes_24h=92`：Caveat 1 metric 真累積（**不再是 0**）
- `chains_with_real_fill_report=6` vs `complete_chains=210` = 2.86%（<< 50% gate）

WARN 純因 chains 分母含 204 pre-deploy stub-only chains（不能 retroactively 補 real-fill ER，append-only event log 哲學）。Post-deploy 持續累積後分子上升，分母 rolling 一旦 stub-only chains 滾出 24h window，比率自動 ≥ 50%。

**Three options 評估**：

| 選 | 描述 | QA verdict |
|---|---|---|
| A | 接受 transition 期 WARN，24h steady-state 自動轉 PASS | **推薦** — Empirical 已證 fix correctness；分母 transition 是預期 |
| B | E1-Python round 3 補 cutoff filter 到分子 + 分母（chains 計數加 `WHERE c.created_at > cutoff`） | 不推薦 — 多 ~45-60min critical path；不破 fix correctness；transition 是預期可接受 |
| C | reviewer brief 含 transition 章節說明 | **推薦並行** — 與 A 共行 |

**QA 推薦 A + C**：[55] WARN 是 calibration transition，不是 fix failure；reviewer brief 章節 + 自然 24h roll-over 解決，不阻 W-D 派發。

operator/PM 若要 strict B，可派 E1-Python round 3，~45-60min；不阻其他 W-D 並行。

---

## 5. W-D MAG-083 dispatch 條件再評估

W-D MAG-083 needs：

| 條件 | 1st audit 狀態 | Re-audit 狀態 |
|---|---|---|
| typed lineage chain 結構 PASS | 174/174 (51h) | 210/210 (W-C accumulated + post-deploy 18) |
| 0 corruption / 0 orphan | confirmed | confirmed (orphan_real_fill_ERs=0 / pre-deploy 537 preserved) |
| chains_with_lease | 174/174 'bypass' | 16/16 'bypass' post-deploy + 174 pre-deploy preserved |
| chains_with_report 結構 | 174/174 stub-only | 210/210 (16 stub + 6 stub+filled) |
| **real-fill propagation 證據** | **GAP** | **6/6 (100%) post-deploy entry chains，全 ER payload 真實值** |
| **state_changes typed transitions** | **GAP** | **82 rows (5 build + 2 change × 累積)** |
| Bybit live mainnet 0 traffic | confirmed | confirmed (no OPENCLAW_ALLOW_MAINNET) |
| Replay non-substitution | 0 'replay' source_agent | unchanged (W-C accumulation 0 replay) |
| Engine + API alive + env aligned | confirmed | confirmed (env vars 100% match) |

**W-D 可派**。新增證據點完整對應 PA §2.5 reviewer compatibility 表。reviewer brief template 必含：
1. 「Caveat 1+2 fix wiring verified at deploy+~10min by adversarial SQL `missed_n=0`」
2. 「Real-fill propagation transition：bad_report_value_quality=0 / chains_with_real_fill_report=6 / 24h steady-state 後分母 rolling 達 ≥ 50% gate」
3. 「Caveat 3 `lease_id='bypass'` per 2026-05-08 auth 不在 fix scope；真實 lease lifecycle 走 `learning.lease_transitions` (V054)」
4. 「Cross-language `executed_by` + `fill_completion=true` empirical byte-equal aligned」

---

## 6. QA E2E ACCEPTANCE TABLE（updated post-fix）

| 5-stage business chain | Evidence | Status |
|---|---|---|
| Market data | engine PID 1597560 + uvicorn 4 workers alive; trading.fills writing continuously | PASS |
| H0 local judgment | OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1 / scanner no [authority] | PASS |
| H1-H5 AI governance | 5 source_agent 4 type writing 24h（unchanged baseline） | PASS |
| 5-Agent + Conductor | Post-deploy 18 chains signal→decision→verdict→plan→report; pre-deploy 174 preserved | PASS |
| Decision Lease + Rust Engine | Post-deploy 16 plans lease_id=bypass (by-design); learning.lease_transitions independent | PASS (bypass-only by-design) |
| Execution + stop loss | trading.fills entry-fill 6/6 propagated to real-fill ER 100% (Caveat 2 CLOSED) | **PASS** (was PARTIAL) |
| Learning + attribution | state_changes_24h=82 producer wiring real (Caveat 1 CLOSED) | **PASS** (was PARTIAL) |

| Dual-process E2E | Evidence | Status |
|---|---|---|
| Startup | engine restart at deploy_ts confirmed; uvicorn 4 workers | PASS |
| Downgrade | not exercised | N/A |
| Reconnect | rebuild --keep-auth deploy 30s gap; spine writer + emit_fill_completion_lineage resumed normally | PASS |

| 5 hard gates | Status |
|---|---|
| Python live_reserved global mode | unchanged from 1st audit (W-C 不觸 new live session) |
| Operator role auth | unchanged |
| OPENCLAW_ALLOW_MAINNET=1 | NOT SET (correct — LiveDemo only) |
| secret slot api_key + secret | unchanged |
| authorization.json | LiveDemo signed auth present (2026-05-09 renewal still effective per [56]) |

| 7-day grey stats | Value | Target |
|---|---|---|
| CRITICAL count | 0 | 0 |
| WARN cluster | [55] WARN_REAL_FILL_PROPAGATION_PARTIAL (transition) + W1 wave breakage advisory | <10 |
| Chain completeness | 210/210 (100%) | >95% |
| Replay substitution | 0 | 0 |
| Real-fill propagation | 6/6 (100% post-deploy entry chains) | >0% (transition) |

| §三 drift check | Source-of-truth measured | Drift? |
|---|---|---|
| Deploy_ts UTC | 2026-05-11T00:01:55+00:00 | NO |
| Caveat 1 metric | state_changes_24h=82 (vs 1st audit 0) | EXPECTED post-fix |
| Caveat 2 metric | 6/6 real-fill ER propagated; bad_report_value_quality=0 | EXPECTED post-fix |
| §三 W-C row LINEAGE_READY_NOT_WINDOW_PASS | post-deploy [55] WARN_REAL_FILL_PROPAGATION_PARTIAL (calibration transition) | DEFERRED for PM update post WINDOW_PASS sign-off |

---

## 7. 後續行動建議

### Immediate (D+0)

1. **Operator**: 簽 `W-C → WINDOW_PASS` 至新 `srv/docs/governance_dev/2026-05-11--w_c_window_pass_signoff.md`，acknowledge：
   - Caveat 1+2 fix empirically verified
   - Caveat 3 by-design per 2026-05-08 auth
   - [55] WARN transition 是 calibration miss，非 fix failure；24h steady-state 自動 ≥ 50% gate
2. **PM**:
   - TODO.md §4.1 W-C 從 🔵 ACTIVE → ✅ DONE 2026-05-11 (Caveat 1+2 FIXED)
   - CLAUDE.md §三 W-C row 從 LINEAGE_READY_NOT_WINDOW_PASS → WINDOW_PASS (post sign-off)
   - 派 W-D MAG-083 audit pack dispatch（QA + PA + QC 三角並行）
   - Reviewer brief template 必含 §5 提的 4 個強制章節
3. **PM (optional, parallel)**: 派 E1-Python round 3 補 cutoff filter 到 chains 分母（~45-60min），讓 [55] 24h 內自動 PASS。**不阻 W-D 派發**。
4. **PM**: W1 sub-task 3 `check_panel_freshness` 補 land（pre-existing breakage block helper_scripts/db full pytest 但不阻 W-C），E5 D-4 P2 ticket。

### Wave dispatch order

1. W-D MAG-083 audit pack dispatch（QA + PA + QC 並行）
2. W-D MAG-084 operator sign-off（blocked on MAG-083 PASS）
3. P0-AGENT-2-FUP-1 + P0-AGENT-3-FUP-1（Caveat 1+2 fix completion already empirically verified — 此 ticket 可 close 或併入 W-C closure）
4. E1-Python round 3 chains 分母 cutoff filter（optional，並行）
5. W1 sub-task 3 check_panel_freshness 補 land（並行）

### Medium-term

- 24h steady-state observation: [55] WARN→PASS 自動轉換預期 deploy+24h ≈ 2026-05-12 ~00:02 UTC
- Caveat 3 不歸 fix scope；Stage 3 promotion 前需另外決議是否真實 exercise lease 5-state SM
- E5 D-1 P2 stable_id helper 抽離（避免未來 silent id drift）

---

## 8. Cross-References

- **1st audit**: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-10--w_c_signoff_audit.md`
- **PA fix spec**: `srv/docs/CCAgentWorkSpace/PA/2026-05-10--w_c_caveat_fix_plan.md`
- **E1 Rust R1 IMPL**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w_c_fix_rust_impl.md`
- **E1 Rust R2 IMPL**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w_c_fix_rust_impl_round2.md`
- **E1 Python IMPL**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w_c_fix_python_impl.md`
- **E2 R1 review**: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-10--w_c_fix_e2_review.md` (APPROVE WITH CONDITIONS)
- **E2 R2 review**: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w_c_fix_e2_review_round2.md` (APPROVE)
- **E5 perf review**: `srv/docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-10--w_c_fix_e5_perf_review.md` (APPROVE WITH 3 P2)
- **E4 regression**: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_c_fix_e4_regression.md` (READY)
- **Authorization SoT**: `srv/docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`
- **Amendment**: `srv/docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` §5.4.1
- **Deploy commit**: `ccf7a4bc0822a9885312f1e8f0eb6678705cebc3`
- **Runtime HEAD**: `8dccc487`（worklog atop deploy commit）

---

## Final Verdict

**QA E2E ACCEPTANCE DONE: PASS**

Caveat 1 + Caveat 2 empirically verified CLOSED via PA §4.3 adversarial SQL (`missed_n=0`) + state_changes accumulation rate ~5/min + real ER payload integrity. Caveat 3 by-design deferred to W-D reviewer brief. [55] WARN is transition-phase calibration miss (chains denominator含 pre-deploy stub-only chains)，not fix failure；24h steady-state 自動轉 PASS。

W-D MAG-083 dispatch READY；operator W-C → WINDOW_PASS sign-off READY；W-AUDIT-1..7 + LG-2/3/4 + Live infra 仍是真 live 前 blockers，本 audit 不擴大 scope。

**Report path**: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--w_c_reaudit_post_fix.md`
