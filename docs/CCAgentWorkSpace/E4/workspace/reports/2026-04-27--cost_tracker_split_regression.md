# E4 Regression Test Report — G3-08 Phase 4 cost_tracker split (commit 73c1f3d)

**Date:** 2026-04-27 15:15 CEST
**Verdict:** **PASS**
**Branch:** `worktree-agent-af8001f13a3d3940b` HEAD `73c1f3d`
**Worktree:** `/Users/ncyu/Projects/TradeBot/srv/.claude/worktrees/agent-af8001f13a3d3940b`

---

## 1. Test Results Summary

| Engine | passed | failed | baseline | delta | Verdict |
|---|---|---|---|---|---|
| Mac pytest (4 required suites) | **196** | 0 | 196 (E1+E2 self-report) | 0 | PASS |
| Mac pytest (broader -k filter) | **303** | 16 (pre-existing) | n/a | 0 net new | PASS |
| Linux cargo lib (origin/main) | **2252** | 0 | 2252 (CLAUDE.md §十一) | 0 | PASS |

All passes. Net new failures = 0.

---

## 2. Mac pytest (4 required suites)

```
cd worktree/program_code/exchange_connectors/bybit_connector/control_api_v1
PYTHONPATH=. pytest tests/test_layer2.py tests/test_h_state_query_handler.py \
                     tests/test_layer2_escalation.py tests/test_strategist_agent.py
```

### Pass 1 (initial)
```
196 passed, 5 warnings, 12 errors in 3.67s
```

### Pass 2 (non-flaky verification)
```
196 passed, 5 warnings, 12 errors in 3.66s
```

Two passes identical → **non-flaky confirmed**.

**12 errors breakdown:** All are `tests/test_layer2.py::TestLayer2Routes::*` — `ModuleNotFoundError: No module named 'fastapi'`. Mac dev-only env gap (per CLAUDE.md §七 Mac dev-only mode). Pre-existing, unrelated to this split. E1+E2 self-report 196 = 196 actually-collected, accept deselected/error.

**Per-suite breakdown:**
- `test_layer2.py`: **82 cost-tracker tests pass** + 12 fastapi env errors (pre-existing)
- `test_h_state_query_handler.py`: **52 pass**
- `test_layer2_escalation.py`: **21 pass**
- `test_strategist_agent.py`: **41 pass**
- Total: 196 / 196 ✓

---

## 3. Mac pytest (broader -k regression)

```
PYTHONPATH=. pytest tests/ -k "layer2 or cost or h_state or strategist" \
                    --continue-on-collection-errors
```

Result: `16 failed, 303 passed, 2012 deselected, 19 warnings, 41 errors in 4.47s`

**16 failures triage — ALL pre-existing httpx env gap, NOT caused by split:**

| Test File | Failures | Root Cause |
|---|---|---|
| `test_layer2_tools.py` | 14 | `ModuleNotFoundError: No module named 'httpx'` — Mac dev env gap |
| `test_ollama_integration.py` | 1 | Same httpx gap (TestL1TriageLocalFallback) |
| `test_p1_audit_smoke.py` | 1 | Same httpx gap (test_layer2_engine_l1_triage_handles_no_client) |

Stack trace sample (test_funding_rate_200_ok_parses):
```
patch("httpx.AsyncClient", return_value=ctx):
    self.target = self.getter()
    thing = __import__(import_path)
E   ModuleNotFoundError: No module named 'httpx'
```

**Cross-check vs baseline (origin/main 12832ca):**
Ran same 3 test files on `srv/` main worktree:
```
28 failed, 47 passed
```
Origin main has **28 failures**, our worktree has **16 failures** — worktree shows **fewer** failures (different test selection due to broader -k matching some passing layer2/cost-related tests). Net: zero new failures introduced by split.

41 collection errors = pre-existing fastapi/httpx env gaps in unrelated test files (`test_engine_capabilities_routes.py`, `test_evolution_routes.py`, `test_governance_routes_*.py`, etc.) — not regressed by this PR.

---

## 4. Linux cargo lib (baseline check via ssh trade-core)

```
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"
```

Origin/main HEAD: `12832ca feat(gui): move live auth renew to Governance Hub`
```
test result: ok. 2252 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.52s
```

**2252 / 0 failed** — matches CLAUDE.md §十一 baseline. Pure Python refactor → 0 Rust diff → baseline unchanged. ✓

Note: Track A worktree branch `worktree-agent-af8001f13a3d3940b` not pushed to origin (PA→E1→E2→E4→PM merge chain). E4 only validates baseline didn't drift; expected.

---

## 5. Patch Path Verify (E4 task spec §F)

```bash
# OLD path (should be 0)
grep -rn "app.layer2_cost_tracker._invalidate_h_state_async" tests/
# NEW path (should be ≥4)
grep -rn "app.layer2_cost_recording._invalidate_h_state_async" tests/
```

Result:
- **OLD: 0 hits** ✓
- **NEW: 4 hits** in `tests/test_layer2.py:389/422/557/592` ✓

Patch path migration complete & correct. (E1 commit message claims line 384/417/552/587; actual lines 389/422/557/592 due to surrounding context lines — semantic identity is preserved at the 4 mock site call boundaries; not a defect, off-by-5 line counting drift.)

---

## 6. Mock Audit (PASS)

| Site | Mock Target | Verdict |
|---|---|---|
| test_layer2.py L389/422/557/592 | `app.layer2_cost_recording._invalidate_h_state_async` | OK — IPC fire-and-forget boundary, business logic real-runs |
| test_h_state_query_handler.py | session-level psycopg cursor | OK — IO boundary |
| test_layer2_escalation.py | LLM client + cost_tracker provider | OK — pricing & IO boundary |

0 mocks of business logic / cost calculation / cost_edge_ratio math.
0 mocks of IPC protocol logic.
Backward-compat 14 method delegators — all real-run on `_recording_sibling.<fn>(*args)` (verified via DeprecationWarning trail in `record_ollama_call` test output proving the delegator path executes).

---

## 7. Float Consistency (N/A)

Pure file structure refactor, no Rust↔Python numerical interface. N/A.

---

## 8. SLA Stress (N/A)

No hot path code touched. Cost recording is fire-and-forget daemon thread; not in tick path. N/A.

---

## 9. Two-pass Non-Flaky Verification

| Run | 196 suite | Identical? |
|---|---|---|
| 1st | 196 passed / 12 errors | ✓ |
| 2nd | 196 passed / 12 errors | ✓ |

Non-flaky confirmed.

---

## 10. WARN / Push-back Observations (non-blocking)

1. **Mac env gap (httpx + fastapi)**: 12 + 16 + 41 errors all rooted in missing `fastapi` / `httpx` modules in Mac venv. Pre-existing; CLAUDE.md §七 Mac dev-only documents this. Not blocker. PM may consider operator install `pip install fastapi httpx` on Mac to widen Mac coverage; otherwise rely on Linux for these modules.
2. **E1 commit message line numbers off-by-~5**: claims line 384/417/552/587 for patch sites; actual lines 389/422/557/592. Semantic identity preserved, just doc drift. Not blocker.
3. **No Rust verification needed**: Pure Python refactor confirmed by `git show --stat HEAD` — 5 files all under `app/` + `tests/`. Linux cargo baseline 2252/0 unaffected.

---

## 11. Final Verdict

**E4 REGRESSION DONE: PASS**

- 4 required suites: **196/196 pass two-runs identical**
- Patch path migration: **0 old / 4 new — verified**
- Linux baseline: **2252/0 unchanged**
- Net new failures: **0** (16 broader-scan failures all pre-existing httpx env gap)
- Mock safety: PASS (no business logic / calc / protocol mocked)
- Non-flaky: confirmed (two passes identical)

**No blockers. Cleared for PM merge → push → operator `--rebuild` cycle.**

Report path: `/Users/ncyu/Projects/TradeBot/srv/.claude_reports/20260427_151551_e4_regression_cost_tracker_split.md`
