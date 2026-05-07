# REF-21 C5 Acceptance And Runtime Sign-Off

**Date:** 2026-05-07  
**Owner:** PM  
**Commit scope:** C2-C5 continuation after `0eda6005`  
**PM sign-off:** CONDITIONAL

---

## 1. Parallelization Decision

C2-C5 was reviewed for parallel execution.

- C2 recorder preflight can be built independently of report analytics.
- C3 report analytics depends on C2 trust fields and replay report shape.
- C4 ML/Dream advisory ranking depends on C3 analytics.
- C5 runbook/sign-off depends on the final C2-C4 behavior.

Decision: execute C2 -> C3 -> C4 -> C5 sequentially for integration quality.
This avoided producing advisory ranking or operator guidance against fields that
were not yet stable.

---

## 2. Completed Checkpoints

| Wave | Commit | Result |
|---|---|---|
| C2 | `9ba6ebc6` | Added `/api/v1/replay/full-chain/coverage` preflight and GUI trust cells for BBO/orderbook/funding/OI/tick-size/edge/execution samples. |
| C3 | `925d3017` | Added replay report analytics overlay: fee-net bps, miss/reject counts, fee/slippage summary, and sandbox verdict. |
| C4 | `0eda6005` | Added read-only `/api/v1/replay/advisory/rank` for ML/Dream advisory ranking; no applier or mutation path. |
| C5 | pending this checkpoint | Adds operator runbook, wave reset update, TODO/CLAUDE status sync, and runtime verification. |

---

## 3. 16 Root-Principle Check

| # | Principle | Status | Evidence |
|---|---|---|---|
| 1 | Single write entry | Pass | Replay still spawns dedicated `replay_runner`; advisory route has no order path. |
| 2 | Read/write separation | Pass | Coverage and advisory are read-only; C4 sets `mutation_allowed=false`. |
| 3 | AI output is not a command | Pass | ML/Dream endpoint is advisory only; no demo/live handoff. |
| 4 | Strategy cannot bypass risk | Pass | Strategy/risk execution remains in isolated replay adapter path. |
| 5 | Survival over profit | Conditional | Replay cannot promote live risk; S1 promotion still requires separate gates. |
| 6 | Fail conservative | Pass | Missing data lowers fidelity tier; no fabricated microstructure. |
| 7 | Learning does not rewrite live | Pass | C4 cannot mutate parameters or invoke an applier. |
| 8 | Explainable trading | Pass | Reports expose warnings, coverage, miss/reject counts, and fee-net result. |
| 9 | Disaster protection | N/A | Replay never submits orders. |
| 10 | Cognitive honesty | Pass | Runbook and UI distinguish S2/S2+/S1-limited/S1-calibrated. |
| 11 | Agent autonomy inside boundaries | Pass | Replay adds advisory evidence without reducing runtime agent capability. |
| 12 | Continuous evolution | Pass | Replay can now feed read-only advisory ranking. |
| 13 | AI cost awareness | Conditional | Advisory endpoint has K cap/rate limit; no cost model extension in this wave. |
| 14 | Zero external cost operation | Pass | Replay runtime does not require paid external APIs beyond existing Bybit public data. |
| 15 | Multi-agent collaboration | Pass | ML/Dream use is advisory and compatible with the existing 5-agent model. |
| 16 | Portfolio risk awareness | Conditional | Multi-symbol replay exists, but correlation/portfolio kill thresholds remain outside C2-C5. |

Hard-boundary result: no live auth, `authorization.json`, `OPENCLAW_ALLOW_MAINNET`,
Decision Lease, or live execution boundary was changed.

---

## 4. PM Acceptance

Approved statements:

- REF-21 replay is usable as a one-click full-chain development sandbox.
- Replay can compress strategy iteration time by replaying a selected historical
  window instead of waiting for demo/live_demo accumulation.
- Fee-aware report analytics and recorder coverage preflight are available in
  the operator workflow.
- ML/Dream can consume replay summaries only as read-only advisory rankings.

Rejected statements:

- "Replay is a fully calibrated live-grade backtest for every historical
  window."
- "Replay can approve demo/live parameter changes."
- "Old windows can be reconstructed with historical orderbook data if no local
  recorder rows exist."

---

## 5. Remaining S1 Calibration Work

These are the next quality wave, not current runtime blockers:

1. deterministic partial-fill modeling from event-aligned orderbook depth,
2. latency q50/q90 model from order/fill state transitions,
3. baseline-vs-candidate comparison workflow,
4. balance-curve and stationary block-bootstrap run bands,
5. recorder retention/storage policy and longer data maturity.

---

## 6. Verification Result

Mac verification:

- `python3 -m py_compile` for the C2-C4 modules and `app/main.py`: passed.
- Targeted replay route/report/static pytest suite: 59 passed.
- `git diff --check`: passed.

Linux `trade-core` verification:

- `python3 -m py_compile` for the same modules: passed.
- Targeted replay route/report/static pytest suite: 59 passed.
- Final source sync: `59f5634a`.
- Final API reload: `bash helper_scripts/restart_all.sh --api-only --keep-auth`
  restarted API parent PID `2467902`.
- Final route probes at `59f5634a`:
  - `GET /api/v1/replay/full-chain/coverage` -> 405,
  - `GET /api/v1/replay/advisory/rank` -> 405,
  - `GET /api/v1/replay/report/example` -> 401.

Warnings: pytest still reports pre-existing Pydantic v1 `@validator`
deprecation warnings in replay modules. This is already tracked as a P3
migration item and is not a C5 blocker.
