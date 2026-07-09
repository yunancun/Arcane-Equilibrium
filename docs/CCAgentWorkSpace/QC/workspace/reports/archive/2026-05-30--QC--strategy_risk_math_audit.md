# QC Strategy/Risk/Math Audit — 2026-05-30 (cold audit RE-RUN, Phase 2)

> PERSISTENCE NOTE (PM): QC(default) ran with a read-only toolset (no Write/Edit/Bash) and returned the full report inline; PM(default) persisted it verbatim. Authorship = QC(default); persistence = PM(default).

**Baseline reconciliation [FACT]:** PM froze `187704f6`; sibling reports confirm HEAD advanced (docs-only `[skip ci]`), Rust/Python source byte-identical to baseline. Audited source = baseline source.

## Counts: P0=0 · P1=0 · P2=1 · P3=2 (all NEW low-severity; prior P1/P2/P3 remediation HELD)

### P0/P1: none.

### P2-1 — Confluence weight-sum invariant has no runtime-config guard; dirty DB param (`73≠65`) can persist undetected
- Label: FACT · Severity: P2
- Path+line: `rust/openclaw_engine/src/strategies/confluence.rs:80-90` `ConfluenceConfig::validate()` enforces sum==65, but it is a **construction-time** check on code defaults (adx25+regime20+vol12+mom8=65 ✓; reversion 15+30+10+10=65 ✓). The TODO `[16]` dirty `ma_crossover` confluence weight sum `73≠65` lives in a **strategist DB row**, surfaced only as a `[16] strategist_cycle_fresh` healthcheck FAIL.
- Impact: No fail-closed gate rejects a malformed DB-sourced weight set at load → a bad weight set would silently skew confluence scoring (alpha distortion, not safety). Strategist is advisory (non-trading-critical), so P2.
- Why real, not FP: validate() exists but is not invoked on the DB-load path; the dirty `73` value is observed in runtime healthcheck.
- Fix direction: validate()-on-DB-load + reject/fallback to code default. Fix owner: E1+MIT; verifier: QC+E2.

### Deep-dive verdicts (the 6 flagged areas):

**#6 Replay/Demo evidence — CLEAN [FACT].** Paper isolation intact: `engine_mode IN ('live','live_demo')` filter; `edge_estimates_paper.json` vs `edge_estimates.json` split (prior QC cleared); Stage 0R = offline replay / Stage 1 = Demo-only (I9). basis_panel `source_tier='bybit_v5_ws_tickers'`, no engine_mode column (correct: shared market plane). No paper→promotion leak.

**P0-EDGE-1 honesty — VERDICT: HONESTLY REPRESENTED [FACT].** TODO §1 states 0/3 AC paths satisfied, 4/4 textbook `insufficient_total_samples` with runtime_bps −11~−42, live_demo 7d net −1.99 USDT. No cherry-picked positive edge. funding_arb retirement per AMD-2026-05-26-01 justified (G-2 n=13 0% win −36.76bps; delta-neutral structurally unviable on Bybit demo = no spot lending). A2 LCS-fade correctly held REVISE/HOLD (avg_net −2.45bps, 0/3 evidence). Textbook-honest negative-edge reporting.

**ADR-0046 basis observation/execution split — NOT LANDED; cannot audit as shipped [FACT].** ADR-0046 file does not exist (Glob 0 hits); AMD-2026-05-26-01:14 confirms "ADR-0046 (Proposed) funding_arb.rs IMPL + V117 migration spec" — a future-redesign DRAFT (TODO §3 workflow B, IMPL-not-started, V117 not V115). What landed is the separate `P2-BASIS-PANEL-INFRA` (V115 basis_panel writer). **PM task prompt conflated the two.** Basis math in the landed writer is SOUND: `basis_pct=(perp_last/index−1)*100` signed, perp=last_price (not mark), strategy-parity test-locked. No execution path in basis_panel (offline-replay-only, no IPC slot, no order writes) — observation/execution separation structurally satisfied by write-only-to-PG.

**BasisAggregator look-ahead — VERDICT: NO LOOK-AHEAD [FACT].** `basis.rs:141-211` flush is a pure point-in-time snapshot: no `rolling(N)`, no window, no `.shift()`, no future bar. Latest-value cache holds only last-known (last_price, index_price) as-of flush; sparse-index frames preserve prior index (never future). ON CONFLICT DO UPDATE idempotent. As-of correctness (`snapshot_ts_ms <= signal_ts_ms` LATERAL) is the A1 runner's responsibility (not yet landed — B-4). Fail-closed: index≤0 → no row (double-guarded). Does NOT trip Donchian/rolling-max blacklist. CLEAN.

**#4 Tunable-vs-hardcoded — RiskConfig sane [FACT].** demo TOML: per_trade_risk_pct=0.1, position_size_max_pct=25, leverage_max=50, correlated_exposure=65, drawdown ladder 8/15/20/22 — all SSOT-config'd, sane. Kelly tier section config-driven (prior QC cleared kellysizer via KellyConfig/RiskConfig). Guardian scoring constants closed → P2-09 named-const + lock-tests (archive). drawdown_halt_ttl_ms=0 sticky (correct, structural).

### NEW P3-1 (re-flag of sibling BB P2): 110009 mislabeled `PositionNotFound` (official = stop-order-limit). Exchange semantics → BB owns; currently harmless (SL/TP path doesn't route through NoOp table per BB trace). Cross-role.
### NEW P3-2: get_positions(None) single-page pagination (BB P3) — not strategy/risk math; cross-ref only.

### Blockers / cross-role:
- **None block promotion.** P0-EDGE-1 remains the structural gate (no alpha-bearing candidate ready) — needs A1 basis-panel forward-accumulation (~2026-06-13) OR new candidate; **operator decision** on tournament timeline, not a code fix.
- P2-1 (confluence DB guard) → E1+MIT.
- P3-1 (110009) → BB/cross-role (exchange semantics).

### Did prior remediation hold? **YES.** Prior QC-SRMA P1/P2/P3 (cost-gate freshness, trading-stop tick, retry policy, guardian consts, DSR power, OU comments) all source-landed + DEPLOYED per closure archive + TODO v84; source byte-identical to baseline confirms no regression. Donchian look-ahead stays cleared (`donchian_prior`). No blacklist method (HMM/GARCH/VPIN/vol-mean-rev/naked-Donchian) reintroduced.
