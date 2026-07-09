# PA Report — G8-01-FUP-LOSSES-WIRING (2026-04-28)

**Topic**: Wire `_stats["consecutive_losses"]` from trade outcome callback so `tick_cognitive_modulator` receives a real (non-zero) input. Closes RFC `2026-04-27--g8_01_cognitive_e2e_design.md` §3.1 acknowledged limitation.

**Mode**: PA design + direct E1 impl + sanity tests (3-role合一，per main session authorization). Scope strictly bounded — does NOT touch W2/W3, regret/dream placeholders, or Rust IPC.

---

## §1 Problem Restatement

`tick_cognitive_modulator` reads `agent._stats.get("consecutive_losses", 0)` but pre-FUP **no production code path ever set this key**. Result of W1 commit `aca7ee3`:
- Structurally: `update_count` advances 0 → ≥1 (RFC §3.1 BUG-B closed).
- Behaviorally: modulator inputs all 0 → `_compute_confidence_floor` short-circuits → modulator state stays at ctor base.

Therefore W1 fixed the call cadence but the call itself was a no-op. Without FUP, W2 ≥85% line cov would test dead branch (input=0), and W3 integration ≥5 case would all run "losses=0" scenarios with no modulator adaptation visible.

---

## §2 Architecture / Data-Flow Survey

### §2.1 Existing trade outcome paths in Python (live, surveyed)

| Producer | Consumer | Status |
|---|---|---|
| `MessageType.ROUND_TRIP_COMPLETE` | `AnalystAgent.on_message` | **DEAD** — zero producers in production after `pipeline_bridge.py` deletion (DEAD-PY-2). Audit refs `_emit_round_trip()` in `WIRING_AUDIT_SUMMARY.txt:74` etc. all stale. |
| Rust engine → IPC `analyst_evaluate` (analysis_type=`round_trip`) → `AIService._handle_analyst()` (`ai_service_dispatch.py:478`) → `AnalystAgent.analyze_trade(record)` | AnalystAgent | **LIVE** — single live entry point for trade outcomes reaching Python. Builds `TradeRecord` with `pnl`, `fees_paid` → `record.net_pnl` is the post-fee outcome. |
| `_write_auto_observation` (`strategy_wiring.py:843-880`) | learning_state STORE | dead (PIPELINE_BRIDGE = None means writer never injected). Doc-only relic. |
| `learning.pattern_insights` DB writes via `persist_analyst_feedback` | Strategist Ollama prompt enrichment | live but PnL-aggregated, not per-trade. Wrong granularity for `consecutive_losses`. |

### §2.2 Strategist subscription surface

`MESSAGE_BUS.subscribe(AgentRole.STRATEGIST, STRATEGIST_AGENT.on_message)` exists, and Strategist's `on_message` already handles INTEL_OBJECT / RISK_VERDICT / PATTERN_INSIGHT / SYSTEM_DIRECTIVE. Adding a new MessageType (e.g., TRADE_OUTCOME_PROCESSED) was an option but rejected (§3.2).

### §2.3 CognitiveModulator semantics check

`_compute_confidence_floor` (`local_model_tools/cognitive_modulator.py:112-135`):
- `consec_losses >= 3` → `pos.append(0.02 * min(consec_losses-2, 5))` → at 5 losses, +0.06 increment.
- `consec_losses >= 3` also blocks downward pressure (`neg_net = 0.0`).
- EMA(α=0.3) on base 0.6 → after 1 tick with consec_losses=5: floor → 0.6 + 0.3 × 0.06 = 0.618.
- This is the test acceptance threshold for the end-to-end test.

---

## §3 Design Decision

### §3.1 Wiring choice: Hybrid Option 1 (in-process callback path)

**AnalystAgent gains an optional `set_strategist_loss_callback(Callable[[float], None])` invoked inside `analyze_trade()` after stats updates. StrategistAgent gains `record_trade_outcome(net_pnl)` updating `_stats["consecutive_losses"]`. `strategy_wiring.py` binds the two with a lambda after both singletons are constructed.**

### §3.2 Options matrix

| Option | Verdict | Rationale |
|---|---|---|
| **1. Direct callback (CHOSEN)** | ✅ | Fail-open at every layer (analyst try/except + strategist try/except); zero new event types; tightest causality (per-trade); easiest to test in-process; no MessageBus subscription churn. |
| 2. New `MessageType.TRADE_OUTCOME_PROCESSED` + Analyst broadcasts + Strategist subscribes | ❌ | Extra event type expands ALLOWED_FLOWS matrix (`multi_agent_framework.py:258-275`); Strategist `on_message` dispatch grows; no benefit over Option 1 since both paths reach the same Strategist instance in-process. |
| 3. Rust engine writes a new IPC stat field, Python polls | ❌ | Touches Rust IPC schema (forbidden by P2 prep-gate scope per task); violates Python-as-SSOT-for-Strategist-stats principle; adds round-trip latency. |
| 4. Subscribe Strategist to dead `ROUND_TRIP_COMPLETE` | ❌ | No producer exists post-DEAD-PY-2; Strategist would still see zero events. |

### §3.3 Loss / win semantics

| net_pnl | Action | Reason |
|---|---|---|
| `> 0` | reset `consecutive_losses = 0` | True profit after fees; modulator should release pressure. |
| `<= 0` | increment by 1 | Includes breakeven (`net_pnl == 0`, fee-eaten) per Principle #5 (生存 > 利潤) + #13 (cost-edge awareness): a fee-eaten trade drained capital with zero edge — exactly the scenario CognitiveModulator should react to. Tested explicitly. |

### §3.4 Idempotency

Intentionally NOT deduped on `trade_id` — caller upstream (Rust IPC) is the dedup authority. Simplifies the counter ingress; no per-trade memory needed.

### §3.5 Out-of-scope (deferred)

- `regret_data` / `dream_data` placeholders (RFC §3.1 deeper FUP — needs OpportunityTracker / DreamEngine production wiring).
- Persisting `consecutive_losses` across uvicorn restarts (current: in-memory, resets on restart — consistent with `_stats` dict pattern).
- A WebSocket / GUI exposure for live monitoring of `consecutive_losses` (not requested, would touch routes).

---

## §4 Implementation Summary

### §4.1 Files modified (3 files, +194 LOC business code)

| File | LOC change | Description |
|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/analyst_agent.py` | +70 | Adds `_strategist_loss_callback` attr, `set_strategist_loss_callback()` setter, fail-open invocation inside `analyze_trade()` after stats update + before `compute_strategy_metrics`. |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py` | +79 | Adds `_stats["consecutive_losses"]` + `_stats["trade_outcomes_observed"]` to ctor stats dict; adds `record_trade_outcome(net_pnl)` method (thread-safe under `self._lock`, fail-open). |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py` | +45 | After Batch-10 Analyst (re)init block, binds `ANALYST_AGENT.set_strategist_loss_callback(lambda net_pnl: STRATEGIST_AGENT.record_trade_outcome(net_pnl))`. Fail-open with explicit warning logs covering both "agent missing" and "wire raised". |

### §4.2 New tests (1 file, 8 test cases, ~330 LOC test)

`program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_g8_01_fup_losses_wiring.py`:

1. **TestRecordTradeOutcomeCounterSemantics** (3 tests)
   - `test_loss_increments_consecutive_losses` — net_pnl<0 → +1
   - `test_win_resets_consecutive_losses_to_zero` — net_pnl>0 → reset; new loss starts from 1
   - `test_breakeven_treated_as_loss` — net_pnl==0 → +1 (Principle #5/#13)

2. **TestAnalystToStrategistCallbackWiring** (3 tests)
   - `test_analyze_trade_invokes_strategist_callback_with_net_pnl` — full round-trip incl. fees
   - `test_callback_failure_is_fail_open_and_does_not_break_analyst` — RuntimeError in callback → analyst stats still advance, errors=0
   - `test_no_callback_wired_is_safe_noop` — backward-compat (callback=None)

3. **TestEndToEndModulatorAdvancesUnderLossStreak** (2 tests)
   - `test_modulator_state_actually_advances_after_loss_streak` — 5 losses + tick → `confidence_floor > base` (proves RFC §3.1 limitation closed end-to-end)
   - `test_win_streak_does_not_advance_floor_above_base` — control: 5 wins + tick → `confidence_floor ≤ base + 1e-9`

---

## §5 Verification

### §5.1 New tests
```
python3 -m pytest .../tests/test_g8_01_fup_losses_wiring.py -v
8 passed in 0.03s
```

### §5.2 W1 sanity tests (regression check)
```
python3 -m pytest .../tests/test_strategist_cognitive_w1_fix.py -v
6 passed in 0.03s
```

### §5.3 Strategist + Analyst + Executor + audit_wiring full sweep
```
python3 -m pytest .../{test_strategist_agent,test_strategist_cognitive_w1_fix,
                       test_analyst_agent_unit,test_analyst_agent_registry,
                       test_batch9_perception_analyst_integration,
                       test_executor_agent_unit,test_strategist_audit_wiring,
                       test_g8_01_fup_losses_wiring}.py
157 passed, 5 warnings in 0.17s
```

### §5.4 Wider Strategist/Executor/Batch-7/11 sweep
```
77 passed, 7 skipped, 8 failed
```
The 8 failures are **pre-existing in baseline (HEAD `82347a5` origin/main)** — confirmed by `git stash` + rerun yielding identical 8/8 failures. They belong to `test_executor_shadow_to_live_e2e.py` and are tracked in `TODO.md` HEALTHCHECK-PRE-EXISTING P2 backlog. **Zero new regressions.**

3 collection errors (`test_executor_shadow_toggle_api.py`, `test_strategist_history_routes.py`, `test_strategist_promote_api.py`) are due to `fastapi` not installed on Mac dev env (expected per `feedback_dev_runtime_split` Mac dev-only mode). Should pass on Linux CI.

---

## §6 Hard Boundary Compliance (CLAUDE.md §四 + 16 Root Principles)

| Boundary | Status | Note |
|---|---|---|
| `live_execution_allowed` / `decision_lease_emitted` / `max_retries=0` | ✅ untouched | Pure stats wiring, no execution path. |
| Rust IPC schema | ✅ untouched | Pure Python in-process callback. |
| `OPENCLAW_ALLOW_MAINNET` / `authorization.json` | ✅ untouched | No live-gate proximity. |
| Principle #1 (single write entry) | ✅ | No order writes. |
| Principle #3 (AI ≠ command) | ✅ | Modulator is a **threshold tightener**, never a writer; remains fail-open. |
| Principle #4 (策略不繞風控) | ✅ | Modulator only **raises** confidence_floor, cannot lower it; consistent with cap behavior. |
| Principle #5 (生存 > 利潤) | ✅ enforced | Breakeven counted as loss → tightens posture under fee-drag. |
| Principle #6 (失敗默認收縮) | ✅ enforced | Callback fail-open at 3 layers: Analyst try/except, Strategist try/except, wiring try/except. Failure leaves modulator on legacy 0-input path (no regression). |
| Principle #11 (Agent 自主) | ✅ | Modulator does not gain new capability; gains correct input data per design. |
| §九 file-size discipline | ✅ | analyst 874→944 lines, strategist 854→933 lines (under 1200 hard cap; **strategist now 933 > 800 warning** — flagged below). |

⚠️ `strategist_agent.py` post-FUP = 933 lines (was 854). Under 1200 hard cap but over 800 warning. PA assessment: do NOT split as part of this FUP — `record_trade_outcome` is a 60-line public method tightly coupled to ctor stats dict; extracting to a 4th sibling would expand surface for marginal gain. Schedule split as part of a future G3-08 Phase 5 if file grows further.

---

## §7 E2 Review Focus (3 highest-risk points)

1. **Lambda closure semantics in `strategy_wiring.py`** — closure captures `STRATEGIST_AGENT` singleton. If a future refactor reassigns `STRATEGIST_AGENT` post-wiring, callback would still call the old instance. Mitigated by docstring + the fact that no reassignment exists today; but E2 should grep for any future `STRATEGIST_AGENT =` reassignments to confirm.

2. **Breakeven-as-loss policy** — explicit decision to treat `net_pnl == 0` as loss. Argued from Principle #5/#13. E2 should validate with PM/FA whether this matches their semantic intent. If they prefer "strict loss only" (`net_pnl < 0`), single-line fix in `record_trade_outcome` (`if net_pnl > 0` → `if net_pnl >= 0`).

3. **Thread-safety of `record_trade_outcome`** — uses `self._lock` (Strategist's existing lock). AnalystAgent's `analyze_trade` runs under its own `self._lock`. Two locks acquired in nested order: Analyst lock → Strategist lock (via callback). PA verified: Strategist's `_lock` is never acquired while Analyst's `_lock` is held in any reverse path (no Strategist code path calls back into Analyst inside its own lock), so no deadlock. E2 should sanity-check by grepping `STRATEGIST_AGENT.` callsites within Analyst module.

---

## §8 Status

- ✅ Design + impl + tests complete in worktree `agent-aded82fa990c915c2` (base HEAD `82347a5`)
- ✅ 8/8 new tests + 6/6 W1 sanity + 157/157 related Strategist/Analyst/Executor regression — all green on Mac
- ✅ Zero hard-boundary touches, zero Rust IPC schema touches, zero new event types
- ⏸️ NOT committed in worktree (per task instruction "返主會話統一 commit + push")
- ⏸️ Linux full regression deferred to E4 in main session
