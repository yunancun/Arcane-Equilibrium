# E4 Linux Full Regression — Wave H 3-way active warn cleanup splits + 2 inline fixes

**HEAD**: `0a50c6c` (origin/main, Wave H 6 commits `dbba235..0a50c6c` synced to Linux)
**Date**: 2026-04-28
**Verdict**: **PASS**
**Engine rebuild**: NOT required (Wave H = pure Python refactor + docs, 0 Rust src diff, 0 trade impact)

## 對象 Wave H 6 commits

| Commit | Type | Scope |
|---|---|---|
| `54b9add` | docs(claude-md) | §九 hard cap pre-existing baseline exception clause |
| `6d657c1` | refactor(strategy-wiring) | STRATEGY-WIRING-SPLIT P2 (1060 → 784 + 2 sibling: h_state 133 + scanner 338) |
| `5928576` | refactor(strategist) | STRATEGIST-DELEGATOR-SLIM P3 (933 → 782 + 25 delegators lift + body migration to cognitive/edge_eval siblings) |
| `bd48672` | docs(g3-08-fup) | MAF-SPLIT-CLEANUP (b) docstring + (c) SCOUT_AGENT §九 row registration |
| `eb6f9e2` | docs | cross-agent memory |
| `0a50c6c` | docs(g3-09-fup) | PA-DOCSTRING-CLARIFY P4 (lambda capture comment correction) |

Note: `dbba235` (operator EDGE-DIAG-2) was push 之前 Wave H 落地，含 §三/§十一 + memory + new healthcheck [31] strategy diversity sentinel — orthogonal to Wave H.

## Test Results — Linux Runtime

| Suite | passed | failed | baseline | delta |
|---|---|---|---|---|
| Rust engine lib (release) | **2308** | 0 | 2308 (post-EDGE-DIAG-2) | 0 ✓ |
| Rust daemon test split (3 files) | **11** | 0 | 11 | 0 ✓ |
| - dual_safeguard | 3 | 0 | 3 | 0 ✓ |
| - daemon_proofs | 5 | 0 | 5 | 0 ✓ |
| - spawn_decision | 3 | 0 | 3 | 0 ✓ |
| Rust persistence (Linux real PG) | **2** | 0 | 2 | 0 ✓ |
| HSQ same-session (api_contract + h_state_query) — 1st run | **108** | 0 | 108 (post-Wave-G HSQ-SPLIT) | 0 ✓ |
| HSQ same-session — 2nd run (flaky verify) | **108** | 0 | 108 | 0 ✓ |
| Strategist regression (8 files) | **133** | 0 | 133 | 0 ✓ |
| Scout (integration + audit_wiring) | **46** | 0 | 46 | 0 ✓ |
| Analyst (agent_unit) | **22** | 0 | 22 | 0 ✓ |
| Full control_api_v1 baseline | **3117** | 0 | ≥3117 (post-Wave-G + EDGE-DIAG-2) | 0 ✓ (3 skipped) |
| Healthcheck full sweep | 32 checks | 2 FAIL (pre-existing) | — | OK |

**Critical SINGLETON post-Wave-G HSQ split + Wave H STRATEGY-WIRING split integrity**: HSQ same-session 108/108 reproducible 兩遍 (2.61s + 2.53s, 0 flake) — confirms strategy_wiring split (1060→784 + 2 sibling) does NOT break H state singleton lifecycle.

## Healthcheck Detail (32 checks)

- **30 PASS** including new `[31] edge_diag_2_strategy_diversity` (operator-added pre-Wave-H, demo Approved=108 across 3 strategies)
- **2 FAIL pre-existing** (documented across multiple prior E4 reports: 2026-04-26 g2_06, 2026-04-27 healthcheck_observer, 2026-04-27 p0_wave_combined, 2026-04-28 Wave G):
  - `[12] bb_breakout_post_deadlock_fix` — bb_breakout 7d entries=0 (G2-06 disable + EDGE-DIAG-2 demo override known issue)
  - `[27] intents_counter_freeze` — Rust trading_writer intent INSERT path wedge (parent also FAIL, P1 documented)

Per CLAUDE.md §九 pre-existing baseline exception clause: Wave H 0 Rust diff, 0 trade impact, does NOT introduce these — both pre-date `dbba235`.

## Engine Rebuild Decision

**NOT triggered**. Rust src 0 diff, engine binary mtime unchanged. Wave H is pure Python refactor (split refactors maintain singleton attribute grep stability `app.strategy_wiring.MARKET_SCANNER` / `_H_STATE_INVALIDATOR` etc. via re-export) + docs. LiveDemo runtime unaffected.

## Mock 審查

N/A — Wave H 0 業務邏輯 mock 變動。Strategist split lifts 25 delegators (本身已含 mock pattern from prior waves，已 E2 通過)，Scout/Analyst test suites unchanged, control_api_v1 baseline 全綠。

## 跑兩遍結果 (skill 強制)

- HSQ 1st: 108 passed in 2.61s
- HSQ 2nd: 108 passed in 2.53s
- **Flaky**: NO

## 結論 / Sign-off

**PASS** — Wave H 3-way active warn cleanup splits + 2 inline fixes 全綠：
1. Rust 2308/0 不退（baseline aligned, 0 Rust diff confirmed）
2. 3 daemon test split sum 11/0 不退
3. Linux PG persistence 2/0 不退
4. HSQ same-session 108/108 兩遍 reproducible — STRATEGY-WIRING-SPLIT P2 對 H state singleton 0 影響
5. Strategist 133/133 — STRATEGIST-DELEGATOR-SLIM P3 (933→782 + 25 delegators lift) 不破
6. 全 control_api_v1 3117/0 — 不退 baseline
7. Healthcheck 30 PASS + 2 pre-existing FAIL (bb_breakout/intents_counter_freeze) 已 documented
8. LiveDemo runtime 不退化（0 engine rebuild needed）

無 BLOCKER；無需退回 E1。Push 即可。
