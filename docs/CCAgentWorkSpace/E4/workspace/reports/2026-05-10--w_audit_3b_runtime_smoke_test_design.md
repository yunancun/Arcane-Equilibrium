# W-AUDIT-3b Runtime Smoke Test Design (Sprint N+1 W4 預跑)

- 日期: 2026-05-10
- Agent: E4
- 任務性質: design + spec only (no IMPL)
- Dispatch ref: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md` §3.4 W4
- Status: DESIGN PASS (W4 sub-agent 可直接接 IMPL phase)

## 1. W-AUDIT-3b 既有 IMPL summary

W-AUDIT-3b 在 N+0 Sprint 已 land，分散在多個 commit (Sprint 3 Track H/I `dbcf845b` / `0ad79f67` 是 Decision Lease retrofit Path A 的源頭，AMD-2026-05-02-01 Track E)。Runtime live：W-C 於 2026-05-08 經 operator 授權啟用 `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`。

| 路徑 | 檔案 | 內容 |
|---|---|---|
| Rust router gate (Gate 1.4) | `rust/openclaw_engine/src/intent_processor/router.rs:80-122` (`acquire_lease_for_gate_1_4`) + `:218-226` (RouterLeaseGuard 包裹 + flag gating) | 30s TTL；Production fail-closed on AuthNotEffective；Exploration/Validation 短路 LeaseId::Bypass |
| Lease guard RAII | `router.rs:22-71` (RouterLeaseGuard + Drop 釋放 Cancelled) | rejection path 自動 release，避免 leak |
| Event consumer release | `rust/openclaw_engine/src/event_consumer/mod.rs:91-100` | 成功路徑 fill consumer 釋放 Consumed |
| Python execution plan lease | `program_code/.../control_api_v1/app/executor_plan_v2.py` (build / acquire / prepare / require) | 5 個既有 fail-closed 邊界 |
| Lineage writer | `rust/openclaw_engine/src/database/lease_transition_writer.rs` | 把 lease/bypass lineage 寫入 `agent.execution_plan` rows (lease_id 欄位) |

既有 pytest coverage (3 個檔，共 9 個 fail-closed test case)：
- `test_executor_plan_v2.py` 5 case：`rejected_guardian_verdict` / `scope_mismatch` / `lease_acquisition_failure` / `missing_lease_request_fields` / `real_submit_without_governance_or_lease`
- `test_executor_agent_unit.py` 3 case：`no_engine_missing_provider` / `no_engine_provider_failure` / `shadow_provider_raises`
- `test_executor_shadow_to_live_e2e.py` 1 case：`pre_init_ipc_failure_stays_fail_closed`

Rust 端：`intent_processor/tests.rs:892-1335` 已涵蓋 `acquire_lease(Production)` AuthNotEffective + Validation profile 短路 Bypass 兩條真路徑。

## 2. [55] healthcheck IMPL summary

- 檔案: `helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py`
- Function: `check_55_agent_decision_spine_lineage(cur)` (line 211)
- Window 默認: 24h (`OPENCLAW_AGENT_SPINE_HEALTH_WINDOW_MINUTES`)
- Modes 默認: `demo,live_demo`
- 核心 SQL CTE: `_complete_chain_counts` (line 109-208) 跑 `strategy_signal → strategist_decision → guardian_verdict → execution_plan` 4-hop JOIN，再 LEFT JOIN `execution_idempotency_keys` + `execution_report`，5 個指標：
  - `complete_chains` (4-hop chain 完整數)
  - `chains_with_idempotency` (帶 idem key)
  - `chains_with_lease` (`plan.lease_id IS NOT NULL AND lease_id <> ''`)
  - `chains_with_report` (有 `executed_by` edge + execution_report)
  - `bad_report_quality` (報告缺 quality_metrics/requested_qty/filled_qty/liquidity_role)
- 阻塞層級: `BLOCKED_SCHEMA_MISSING` → `BLOCKED_ENABLED_EMPTY` → `BLOCKED_NO_RECENT_LINEAGE` → `BLOCKED_INCOMPLETE` → `BLOCKED_IDEMPOTENCY` → `BLOCKED_REPORTS_PENDING` → `BLOCKED_REPORT_QUALITY` → PASS
- 2026-05-08 22:09 UTC 直查 baseline：`chains=101, chains_with_lease=76, chains_with_report=101, bad_report_quality=0`，`LINEAGE_READY_NOT_WINDOW_PASS window=1440m` (Stage 2 evidence 已收，等 24h window PASS)

## 3. pytest design — 評估 = **不建議新寫**，改 review + 補一條 TTL/Drop 路徑

W-AUDIT-3b 既有 9 case 已涵蓋 dispatch v3.4 §3.4 acceptance 「≥ 1 fail-closed test case」。重複新寫 `test_executor_fail_closed.py` 是 fake coverage。建議 W4 IMPL phase 改為：

**(A) Coverage gap review (read-only, 不寫新 case)**：跑既有 9 case 確認 PASS，列已覆蓋與未覆蓋 scenario matrix。

**(B) 補 1 條 Rust 路徑** (對應 dispatch §3.4 acceptance)：在 `rust/openclaw_engine/src/intent_processor/tests.rs` 加 `test_router_gate_1_4_lease_drop_releases_on_rejection` — 驗 RouterLeaseGuard Drop 在 reject 路徑下真的呼 release(Cancelled)，補既有 test 對 Drop 的 assertion gap。預估 ~40 LOC。

| Scenario | 既有 case | Gap |
|---|---|---|
| AuthNotEffective Production | Rust `acquire_lease()` test (tests.rs:898) | OK |
| Validation profile bypass | Rust tests.rs:1330 | OK |
| Lease acquisition None | Python `test_lease_acquisition_failure_fails_closed` | OK |
| Missing lease scope (real_submit) | Python `test_missing_lease_request_fields_fail_closed_for_real_submit` | OK |
| **Lease Drop release on reject** | 無 | **W4 補 1 條 Rust unit test** |
| Real submit no lease | Python `test_real_submit_without_governance_or_lease_fails_closed` | OK |

**Assertion list (新 Rust test)**：
1. Build `OrderIntent` + flag ON + Production profile + auth effective → `acquire_lease_for_gate_1_4` 成功回 `LeaseId::Active`
2. 構造一個會在後續 gate 被 reject 的 intent (例：non-reducing + risk_governor_emergency)
3. `process_with_features()` 回 `IntentResult::rejected`
4. `governance.lease_manager.snapshot()` assert lease 已 release(Cancelled) (lease state ≠ Active)

## 4. Runtime smoke test script design

落 `srv/helper_scripts/test_w_audit_3b_runtime_smoke.sh` (W4 IMPL phase 寫，~80 LOC)。Pseudo-code：

```bash
#!/usr/bin/env bash
# W-AUDIT-3b runtime smoke (Sprint N+1 W4)
# 用法: bash helper_scripts/test_w_audit_3b_runtime_smoke.sh
set -euo pipefail
T_START=$(date -u +%s)

# Step 1: ssh trade-core 確認 engine alive + flag ON
ssh trade-core "pgrep -af openclaw_engine >/dev/null" \
  || { echo "FAIL: engine not running pre-restart"; exit 1; }
ssh trade-core "env | grep -q OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1" \
  || { echo "FAIL: router gate flag OFF"; exit 1; }

# Step 2: ssh restart_all --keep-auth (W4 不重 build, 只 restart 觀察 5min window)
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --keep-auth" \
  || { echo "FAIL: restart_all failed"; exit 2; }

# Step 3: poll engine watchdog 直到 alive (max 60s)
for i in $(seq 1 12); do
  alive=$(ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --status 2>&1 \
    | grep -c 'engine_alive: true'" || echo 0)
  [[ "$alive" == "1" ]] && break
  sleep 5
done
[[ "$alive" == "1" ]] || { echo "FAIL: engine_alive=false after 60s"; exit 3; }

# Step 4: 等 5min window 累 lineage (signal→decision→verdict→plan 4-hop)
echo "Waiting 5min for lineage accumulation..."
sleep 300

# Step 5: 直查 [55] SQL — 從 checks_agent_spine.py 抽 SQL pattern
RESULT=$(ssh trade-core "cd ~/BybitOpenClaw/srv && \
  PGPASSWORD=\$PG_PASS psql -U trader -d openclaw -h trade-core -t -c \"
  -- 同 _complete_chain_counts CTE 但縮 5min window
  WITH chains AS (
    SELECT DISTINCT plan.object_id AS plan_object_id, plan.lease_id, plan.engine_mode
    FROM agent.decision_objects sig
    JOIN agent.decision_edges sig_edge ON sig_edge.from_object_id=sig.object_id AND sig_edge.edge_type='signal_for'
    JOIN agent.decision_objects dec ON dec.object_id=sig_edge.to_object_id AND dec.object_type='strategist_decision'
    JOIN agent.decision_edges verdict_edge ON verdict_edge.from_object_id=dec.object_id AND verdict_edge.edge_type IN ('reviewed_by','modified_by')
    JOIN agent.decision_objects verdict ON verdict.object_id=verdict_edge.to_object_id AND verdict.object_type='guardian_verdict'
    JOIN agent.decision_edges plan_edge ON plan_edge.from_object_id=verdict.object_id AND plan_edge.edge_type='planned_by'
    JOIN agent.decision_objects plan ON plan.object_id=plan_edge.to_object_id AND plan.object_type='execution_plan'
    WHERE sig.engine_mode=ANY(ARRAY['demo','live_demo'])
      AND sig.created_at > now() - interval '5 minutes'
  )
  SELECT count(DISTINCT plan_object_id) FILTER (WHERE lease_id IS NOT NULL AND lease_id<>'') AS chains_with_lease
  FROM chains;\"")

CHAINS_WITH_LEASE=$(echo "$RESULT" | tr -d ' ')
[[ "$CHAINS_WITH_LEASE" -ge 1 ]] \
  || { echo "FAIL: chains_with_lease=$CHAINS_WITH_LEASE < 1 in 5min window"; exit 4; }

# Step 6: Sanity — bad_report_quality must be 0
# (擴 query 加 chains_with_report + bad_report_quality)
echo "PASS: chains_with_lease=$CHAINS_WITH_LEASE elapsed=$(($(date -u +%s)-T_START))s"
```

**Acceptance gate (script return)**：
- exit 0 = PASS (chains_with_lease ≥ 1 in 5min)
- exit 1-4 = FAIL with stage label

## 5. Acceptance criteria refinement (建議 update dispatch v3.4 §3.4)

**現行 v3.4 §3.4**：「pytest PASS（≥ 1 test case 涵蓋 fail-closed path）」+ 「[55] chains_with_lease ≥ 1 經 restart 後 5min 內」

**E4 建議補強 (向 PA push back)**：
1. pytest 規格改寫：「既有 9 fail-closed test case 全 PASS + 補 1 條 Rust `RouterLeaseGuard` Drop release test (確認 reject path 不 leak lease)」— 避免 W4 sub-agent 重寫 fake coverage
2. Smoke test gate 加 4 條 invariant：
   - `chains_with_lease ≥ 1` (現)
   - `bad_report_quality = 0` (lineage quality 不退化，與 [55] PASS 條件對齊)
   - `chains_with_report ≥ 1` (確認 fill consumer 也活)
   - `engine_alive=true` 在 restart 後 60s 內回穩 (engine 沒崩)
3. 5min window 是必要下限但不夠：建議 W4 sub-agent 跑 2 次（restart 後立刻 + 5min 後）做 baseline-vs-window 對比，避免「pre-restart 累積數混入」假 PASS

## 6. Test order

1. **Pytest first** (fast, isolated, dev env)
   - `cd srv && python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_plan_v2.py -q -k "fail_closed or lease"`
   - `cd srv && python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_agent_unit.py -q -k "fail_closed"`
   - `cd srv/rust && cargo test --release -p openclaw_engine --lib -- intent_processor::tests::` (含新加 Drop release test)
   - 全 PASS 才進 step 2
2. **Runtime smoke** (slow, prod-like, ssh trade-core)
   - `bash helper_scripts/test_w_audit_3b_runtime_smoke.sh` (~6min: 60s restart wait + 300s window + ~20s SQL query)
   - exit 0 才能 sign-off W4

順序硬約束：pytest FAIL → 不跑 runtime smoke (省 6min)；runtime smoke FAIL → 退回 E1 不接 sign-off。

## 7. W4 IMPL phase 預估

| Sub-task | LOC | 時間 |
|---|---|---|
| W4-1a Run existing pytest baseline (9 case) | 0 (read-only) | 10min |
| W4-1b Add 1 Rust test (`test_router_gate_1_4_lease_drop_releases_on_rejection`) | ~40 LOC | 1h |
| W4-2 Write `test_w_audit_3b_runtime_smoke.sh` | ~80 LOC | 1.5h |
| W4-3 Run smoke + write report | 0 (script-driven) | 30min (含 5min window wait) |
| **總計** | **~120 LOC** | **~3.5h (符合 dispatch v3.4 「1 day」上限)** |

## E4 sign-off

DESIGN PASS — W4 sub-agent IMPL phase 可直接接。

關鍵檔案 (W4 IMPL 必讀)：
- `srv/rust/openclaw_engine/src/intent_processor/router.rs` (lines 22-122, 218-226)
- `srv/rust/openclaw_engine/src/intent_processor/tests.rs` (lines 892-1335 既有 lease test pattern)
- `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_plan_v2.py` (既有 5 fail-closed case)
- `srv/helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py` (lines 109-340 [55] SQL 來源)
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md` §3.4 W4 spec
