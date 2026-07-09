# E4 Regression — Wave 1.5 Track E4 KAMA Fallback Gate (commit 9df44183)

**Auditor**: E4 (Test Engineer)
**Trigger**: PA dispatch — Wave 1.5 / Track E4 — KAMA fallback gate regression + exit path verify
**Subject commit**: `9df44183` fix(ma_crossover): warn + skip entry when KAMA unavailable (W3-6 by-the-way)
**Verify head (Linux trade-core, this run)**: `34aa7086` (E4 new test code commit; 9df44183 in linear history)
**Verify date**: 2026-05-15 (operator local) / 2026-05-16 UTC commit
**Verdict**: **REGRESSION-PASS · deploy READY**

---

## Executive Summary

E1's W3-6 by-the-way fix at commit `9df44183` (KAMA fallback `debug! + fall through` -> `warn! + return vec![]`) PASSES E4 regression with the following verified facts:

- Rust lib full regression: **2893 / 0 / 1 ignored** (baseline 2889 / 0 / 1 -> +4 new from this E4 commit, 0 fail delta).
- ma_crossover focused: **72 / 0** (E1 baseline 68 / 0 -> +4 E4 new tests, all PASS).
- 4 new exit-path corner-case tests written by E4 to empirically verify E1's self-flagged uncertainty: all PASS (no force-exit on KAMA unavailable, no spurious signal across 100 consecutive missing-KAMA ticks, normal recovery after the unavailable window, no entry when no position).
- `stress_ma_crossover_whipsaw_rapid_reversals` PASS in <0.01s (E1 H0 SLA <1ms unaffected by the +1 if-check + early return).
- Cross-language parity not applicable: Python `KAMACrossoverRule` is a `_StubRule` only; ma_crossover entry/exit logic is Rust-SSoT with no dual implementation.
- No mock used in any new E4 test (real `MaCrossover::new()` + real `IndicatorSnapshot` + real `on_tick`).
- Non-flaky: ma_crossover focused 72/72 PASS twice; full lib 2893/0/1 PASS twice (`finished in 0.64s` both runs).
- Pre-existing 2 stress_integration failures (`stress_bb_breakout_valid_squeeze_with_volume` + `stress_bb_reversion_extreme_oversold_bounce`) confirmed unrelated to commit 9df44183 (diff only touches `ma_crossover/strategy_impl.rs`; both were flagged in 2026-05-16 full-scope-testing-audit §1.2).

---

## §1 Baseline comparison (full Rust lib)

| Run | passed | failed | ignored | runtime | source |
|---|---|---|---|---|---|
| 2026-05-16 full-scope audit baseline | 2889 | 0 | 1 | 0.70s | `2026-05-16--full-scope-testing-audit.md` §1.1 |
| Pre-E4-commit on `9df44183` (`72692fe4` synced) | 2889 | 0 | 1 | 0.64s | this run, before push |
| Post-E4-commit `34aa7086` Pass 1 | 2893 | 0 | 1 | 0.64s | this run, after push |
| Post-E4-commit `34aa7086` Pass 2 | 2893 | 0 | 1 | 0.64s | non-flaky verify |

Delta: **+4 new (E4 corner case)**, **0 regression**, ignored count unchanged (LG1-T3 known h0_shadow_mode propagation gap; not Wave 1.5 scope).

CLAUDE.md §九 baseline rule: `passed >= baseline AND failed <= pre-existing` -> SATISFIED (2893 >= 2889, 0 <= 0).

---

## §2 ma_crossover focused suite (E1's 68-test verify)

| Run | passed | failed | ignored | runtime |
|---|---|---|---|---|
| Pre-E4 commit ma_crossover focused | 68 | 0 | 0 | <0.01s |
| Post-E4 commit ma_crossover focused Pass 1 | 72 | 0 | 0 | <0.01s |
| Post-E4 commit ma_crossover focused Pass 2 | 72 | 0 | 0 | <0.01s |

E1's 68/0 reproduced byte-equal pre-E4-commit. After E4 +4 = 72/0. Non-flaky.

Sibling drift check: Mac local on `6b8be386`; Linux trade-core on `34aa7086` (after this run). 9df44183 is in linear history of both heads (`git log 9df44183 --oneline -1` reachable on trade-core). E4 verify is on the **HEAD after** 9df44183, not on the commit itself -- forward-looking confirmation that subsequent commits did not regress this work. Per E4 memory 2026-05-09 W-AUDIT-3b lesson: HEAD-verify > commit-pinned verify.

---

## §3 New exit-path corner-case tests (E4 contribution)

E1 commit message + E1 self-report: "stress_ma_crossover_whipsaw_rapid_reversals 通過... 但不確定 exit path 持倉中 KAMA disappear 是否會誤平倉". E4 wrote 4 new tests to empirically prove the unverified claim.

All tests added to `rust/openclaw_engine/src/strategies/ma_crossover/tests.rs` (1016 -> 1178 LOC; +162 LOC).

| # | Test name | What it asserts | Result |
|---|---|---|---|
| 1 | `test_kama_unavailable_during_open_position_does_not_force_exit` | self-owned ma_crossover LONG position + `kama: None` + valid ADX -> `on_tick` returns empty `Vec<StrategyAction>` (NOT a Close) | PASS |
| 2 | `test_kama_unavailable_for_consecutive_n_ticks_returns_empty` | self-owned LONG + 100 consecutive ticks of `kama: None` -> all 100 return empty, no panic, no spurious exit, exit_persistence state remains coherent for fresh check | PASS |
| 3 | `test_kama_recovers_after_unavailable_window_resumes_trading` | no position + 10 ticks `kama: None` (all empty) -> tick 11 KAMA back with `kama=101 > sma_20=100` -> emits exactly 1 Open(LONG) intent (no sticky state blocks recovery) | PASS |
| 4 | `test_kama_unavailable_no_entry_when_no_position` | no position + `kama: None` (theoretically valid signal direction) -> empty actions (matches commit's design intent: avoid SMA-vs-SMA degradation polluting ML training data) | PASS |

E4 commit landing `34aa7086`. Push verified `git pull --ff-only` on trade-core succeeded (`72692fe4..34aa7086 Fast-forward`).

### Semantic verification of E1's claim

E1's reasoning: "持倉中 KAMA unavailable -> return vec![] -> exit by stop_manager (trailing/time stop)".

**E4 empirical proof** of the load-bearing piece — `on_tick` itself does not emit Close in this scenario:

- Test #1 directly asserts `actions.is_empty()` with self-owned position + `kama: None`.
- Test #2 stress-tests the invariant across 100 consecutive ticks (no transient spurious exit, no resource leak).
- Old code path semantic equivalence: pre-9df44183, `fast = ind.sma_20.unwrap_or(0.0)` and `slow = ind.sma_20.unwrap_or(0.0)` -> `fast == slow` -> `reverse_signal = None` -> exit branch's `if persisted && reverse_signal.is_some()` fails -> no Close emitted. New path early-returns before reaching exit branch. **Both paths agree on the no-force-exit invariant**; new path additionally avoids polluting downstream confluence/persistence (commit's stated goal).
- E1's claim about stop_manager owning exit is **out of scope for this regression** (stop_manager is a different module); this regression only proves `MaCrossover.on_tick` does not contribute a spurious Close. Stop_manager-driven exit remains intact (no code change to that module).

---

## §4 Cross-language consistency (1e-4 tolerance)

**Not applicable for this commit.**

`grep -rn "ma_crossover\|MaCrossover" program_code/local_model_tools/strategies/` and `signal_generator.py` show:
- `KAMACrossoverRule` in `signal_generator.py:146-151` is a `_StubRule` (stub class with no on_tick logic).
- `program_code/local_model_tools/strategies/base.py` has zero `kama` references in actual strategy logic.
- ma_crossover entry/exit logic is Rust SSoT (per CLAUDE.md §五 + ARCH-RC1); no Python implementation exists to compare against.

The KAMA *indicator* itself (`rust/openclaw_core/src/indicators/trend.rs`) has Python parity in `program_code/local_model_tools/kline_manager.py`'s indicator engine, but that is **not in commit 9df44183 scope** (commit changes strategy fallback behavior, not the KAMA computation). No cross-lang work owed for this commit.

---

## §5 SLA spot check (H0 hot-path <1ms)

`stress_ma_crossover_whipsaw_rapid_reversals` (the stress test E1 mentioned passing in their work):

```
test stress_ma_crossover_whipsaw_rapid_reversals ... ok
test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 34 filtered out; finished in 0.00s
```

`finished in 0.00s` (<10 ms total for whatever sample count the test runs). The +1 `if let None = ind.kama` branch + early `return vec![]` is on the order of 1-2 ns; per-tick overhead is negligible. H0 SLA <1ms unaffected.

No dedicated `ma_crossover_perf` test exists in `--release` integration suite; the stress test is the closest signal. PASS.

---

## §6 Overall verdict for PM

**REGRESSION-PASS** for commit `9df44183` (W3-6 by-the-way KAMA fallback gate).

| Gate | Status |
|---|---|
| Full Rust lib regression no drift | PASS (2889 -> 2893, +4 new, 0 fail) |
| ma_crossover focused 68/0 verify | PASS (E1's claim reproduced byte-equal pre-commit) |
| Exit-path corner case empirical proof (E1 self-flagged) | PASS (4/4 new tests) |
| Cross-language consistency | N/A (no Python dual implementation) |
| SLA hot-path spot check | PASS (stress_ma_crossover_whipsaw <0.01s) |
| Mock audit (no business logic mocked) | PASS (0 mocks in new tests) |
| Non-flaky double-run | PASS (Pass 1 = Pass 2, both lib 2893/0 and ma_crossover 72/0) |
| Sibling pre-existing fails accounted | PASS (2 stress_integration fails unrelated to 9df44183 diff) |

Deploy READY. No rebuild blocker introduced by 9df44183 + 34aa7086. trade-core engine PID can be left as-is (test-only commits do not require rebuild).

---

## §7 Push back to E1

**None.** No new failures, no business logic regression, no SLA concern.

E4 observation worth noting (not a blocker, FYI for E1 / future audits):

1. **Test-design lesson for E1**: the moment E1 self-flags "uncertain about exit path", that is exactly the moment to sub-task an E4 corner-case test before claiming IMPL-DONE — not after. E1 self-report 68 PASS but admitted unverified scope; in the strong work chain, E4 corner-case write should be in scope of the same wave, not a separate dispatch. The 4 new tests in this report would have taken E1 ~30 min to write inline. (This is a minor flow optimization, not a blocking ask.)
2. **Code comment quality is good**: the new comment block in `strategy_impl.rs:149-156` correctly notes the dual-path consequence (`fast` is also used by exit path, and `reverse_signal` degrades to None). Good defensive documentation.
3. **Pre-existing baseline has 1 long-standing ignored test** (`LG1-T3 h0_shadow_mode propagation gap`) — not Wave 1.5 scope; carry-over.

---

## Appendix A — Full test output snippets

### A.1 Pre-E4-commit baseline ma_crossover (Linux, on `9df44183` + later docs commits)

```
test result: ok. 68 passed; 0 failed; 0 ignored; 0 measured; 2822 filtered out; finished in 0.00s
```

### A.2 Post-E4-commit ma_crossover (Linux, on `34aa7086`)

```
test strategies::ma_crossover::tests::test_kama_recovers_after_unavailable_window_resumes_trading ... ok
test strategies::ma_crossover::tests::test_kama_unavailable_during_open_position_does_not_force_exit ... ok
test strategies::ma_crossover::tests::test_kama_unavailable_for_consecutive_n_ticks_returns_empty ... ok
test strategies::ma_crossover::tests::test_kama_unavailable_no_entry_when_no_position ... ok

test result: ok. 72 passed; 0 failed; 0 ignored; 0 measured; 2822 filtered out; finished in 0.00s
```

### A.3 Full Rust lib post-E4 (run 1 + run 2)

```
test result: ok. 2893 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.64s   # Run 1
test result: ok. 2893 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.64s   # Run 2
```

### A.4 stress_ma_crossover_whipsaw_rapid_reversals

```
test stress_ma_crossover_whipsaw_rapid_reversals ... ok
test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 34 filtered out; finished in 0.00s
```

---

## Appendix B — Ssh / git operations record

| Step | Command (abridged) | Result |
|---|---|---|
| 1 | `ssh trade-core "git log -1"` | trade-core HEAD `2e7a1b2f` -> later `72692fe4` |
| 2 | `ssh trade-core "git log 9df44183 --oneline -1"` | reachable in linear history |
| 3 | local edit `tests.rs` +162 LOC | +4 tests, 0 mocks |
| 4 | `git commit --only rust/.../ma_crossover/tests.rs -m "test(ma_crossover): ..." && git push origin main` | `34aa7086` pushed |
| 5 | `ssh trade-core "git pull --ff-only origin main"` | `72692fe4..34aa7086 Fast-forward` |
| 6 | Linux cargo test ma_crossover x2 | 72/0 both runs |
| 7 | Linux cargo test --lib full x2 | 2893/0/1 both runs |
| 8 | Linux cargo test stress_ma_crossover_whipsaw | PASS <0.01s |
| 9 | Linux cargo test --test stress_integration full | 33/2 (2 = pre-existing bb_breakout + bb_reversion fails, unrelated) |

---

E4 REGRESSION DONE: PASS · report path: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-15--kama_fallback_gate_e4_regression.md`
