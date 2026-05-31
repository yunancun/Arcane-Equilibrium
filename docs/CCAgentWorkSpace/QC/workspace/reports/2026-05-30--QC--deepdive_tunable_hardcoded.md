# QC Deep-Dive — Tunable vs Hardcoded (audit direction #4, Phase 5) — 2026-05-30

> AUTHORSHIP: QC(default). Written directly by QC.
> Baseline: frozen `187704f6`; HEAD `3f805a61` (docs-only `[skip ci]` ahead);
> Rust/Python source byte-identical to baseline per sibling reports + `git status`
> (only `docs/CCAgentWorkSpace/*/memory.md` dirty). READ-ONLY run.
> RUN NOTE: harness tool-output outage flapped during the run (recovered via the
> background-task persisted-output path + retries). ALL five categories were
> ultimately captured WITH evidence, including the Bybit REST/WS client. Every
> finding below is backed by a grep/read that returned non-empty this run.

## DEEPER VERDICT: CONFIRMED-MOSTLY-CONFIG (+ small NEW-HARDCODED-FINDINGS, all P3)

The tunable surface is broad and disciplined: ~30 TOML config blocks across all 5
risk-config envs, almost every one with a `validate()` range-guard cited in-comment
and a documented "defaults mirror the old hardcoded constant" migration lineage
(G7-01..G7-07, W-AUDIT-6, etc.). Categories 1/2/3/5 are SUBSTANTIALLY config-driven
and sane. The one prior P2 (confluence DB-load gap) is **re-confirmed**. THREE
NEW hardcoded-but-arguably-tunable clusters found (all P3, exec/exchange
microstructure; NONE defeats a risk control). Category 4 (Bybit client) IS now
swept — its connection/rate-limit constants are the most material new item.

## Sweep table

| # | param | location (file:line) | value | in-config? | should-be-tunable? | sev if hardcoded |
|---|---|---|---|---|---|---|
| 1 | confluence weight sum guard | `strategies/confluence.rs:80-90` | `==65`, construction-time only | DB row exists; **no load-time guard** | guard SHOULD run on DB-load | **P2** (re-confirm) |
| 2 | confluence default weights/thresholds | `strategies/confluence.rs:57-113` + `strategy_params.rs:163-181,226-246` | 25/20/12/8; thr 45/52/58 | **serde(default=fn)** → TOML-overridable schema | already tunable via params | N/A (config-backed) |
| 3 | Risk [limits] (all envs) | `risk_config_{demo,live,...}.toml [limits]` | demo lev50/pos25/dd25/daily15; live lev15/pos15/dd12/daily7 | **CONFIG** | yes — is | N/A |
| 4 | drawdown_halt_ttl_ms | `risk_config_*.toml [limits]` | `0` sticky (validate rejects >0) | CONFIG + hard-guard | structurally must=0 | N/A (correct) |
| 5 | cascade drawdown ladder | `risk_config_*.toml [cascade]` | demo 8/15/20/22; live 2.5/5/8/10 | CONFIG | yes — is | N/A |
| 6 | AI daily/monthly cap | `budget_config.toml [caps]` | daily 2.0 / monthly 60.0 / cooldown 60m | CONFIG (claims `==layer2_types.py:60`) | yes — is | N/A (cross-lang claim UNVERIFIED) |
| 7 | cost_edge_max_ratio / min_profit | `budget_config.toml [attention_tax]` | 0.2 / 0.3 | CONFIG | yes — is | N/A |
| 8 | cost_edge trigger_threshold | `risk_config_*.toml [cost_edge]` | demo -0.5 / live -0.3 | CONFIG | yes — is | N/A |
| 9 | slippage tiers + cost_gate knobs | `[slippage]` / `[cost_gate]` | tiers 1-30bps; floor .3; safety 1.3; min_n 15 | CONFIG | yes — is | N/A |
| 10 | feature windows / TTLs | `[ewma_vol]`,`[hurst]`,`[grid_ou]`,`[correlation]`,`[dynamic_sizing]`,`[pricing]`,`[cusum]` | lambda .97; corr win 45m; pricing 60/1440m; etc | CONFIG (+validate) | yes — is | N/A |
| 11 | funding_arb cost/threshold/hold consts | `strategies/funding_arb.rs:33-41` | total_cost 34bps; thr 5bps; max_hold 72h; maker_timeout 45s | `const` defaults of `FundingArbParams` w/ `apply()`+snapshot (l.158-190) → **runtime-overridable** | already tunable via params | N/A (config-backed) |
| 12 | **close-maker backoff/cascade consts** | `strategies/maker_rejection.rs:39-51` | initial 1s / max 60s / reset 300s / cascade 10 symbols/60s / pause 300s | **HARDCODED** (`pub(crate) const`, no params/TOML path) | **borderline** — exec rate-limit safety; tuning would help live calibration | **P3** |
| 13 | funding_arb maker offset/buffer-ticks | `strategies/funding_arb.rs:39-40` | offset 1.0bps / buffer 1 tick | **HARDCODED** const (NOT in the overridable params struct) | minor exec tuning knob | **P3** |
| 14 | **Bybit REST recv_window** | `bybit_rest_client.rs:1004` | `"5000"` (ms) | **HARDCODED** (struct init, no config/param) | yes — recv_window is a per-deployment latency knob | **P3** |
| 15 | **Bybit REST HTTP timeout** | `bybit_rest_client.rs:995` | `from_secs(10)` | **HARDCODED** | borderline — fixed 10s request timeout | **P3** |
| 16 | Bybit REST rate-limit/latency windows | `bybit_rest_client.rs:399..580` `REST_LATENCY_WINDOW_SECS` / `RET_CODE_WINDOW_SECS`; `GLOBAL_THRESHOLD` | `const` | **HARDCODED** consts | mostly observ.; thresholds borderline | **P3** |
| 17 | Bybit WS reconnect/ping/RTT windows | `bybit_private_ws.rs:30-36,93` via `ws_backoff::BackoffConfig::ws_private_default()` (3s/60s/x2); `WS_RTT_WINDOW_SECS`, ping 20s | `const` / shared BackoffConfig default | partially abstracted (BackoffConfig) but values fixed in code | observ. + reconnect; low impact | **P3** |

## P2 (re-confirm, NOT new) — Confluence weight-sum guard is construction-time only
- FACT · P2 · `confluence.rs:80-90`. `validate()` enforces sum `==65` only at
  construction on code defaults (verified: 25+20+12+8=65; reversion 15+30+10+10=65).
  Dirty `ma_crossover` DB-row sum `73≠65` surfaces only via `[16]
  strategist_cycle_fresh` healthcheck FAIL — no validate()-on-DB-load gate. Impact:
  malformed DB weight set skews scoring (alpha distortion, not safety; strategist
  advisory) → P2. Fix: validate() on DB-load, reject/fallback to code default.
  Owner E1+MIT; verifier QC+E2. SAME as first-pass P2-1.

## NEW P3-A — close-maker rate-limit constants are fully hardcoded
- INFERENCE→FACT · P3 · `strategies/maker_rejection.rs:39-51`
- `CLOSE_MAKER_BACKOFF_INITIAL_MS=1_000`, `_MAX_MS=60_000`, `_RESET_AFTER_MS=300_000`,
  `_GLOBAL_CASCADE_WINDOW_MS=60_000`, `_GLOBAL_CASCADE_SYMBOLS=10`, `_GLOBAL_PAUSE_MS=300_000`.
  These govern the PostOnly close-path backoff + global cascade pause. No params
  struct / TOML / IPC override path (grep shows only the `const` defs + direct use
  at l.422/438/744/756/765). Evidence: grep `maker_rejection.rs` (this run).
- Why real not FP: these are live-behavior knobs (how aggressively the close path
  retries maker orders, when a market-wide pause trips) that operators may want to
  tune per liquidity regime, yet only a Rust rebuild can change them. Contrast with
  the deliberate config-isation of the parallel `[slippage]`/`fast_track` paths.
- Why only P3: it is a self-protective rate-limiter (fail-safe direction), does not
  defeat any risk control, and use_maker_close has a market fallback. Tuning is a
  calibration convenience, not a safety fix.
- Fix direction: lift to a `[close_maker]` RiskConfig section mirroring the G7-07
  slippage-tier pattern (defaults bit-identical). Owner E1; verifier E2+QC.

## NEW P3-B — funding_arb maker offset / buffer-ticks hardcoded (lesser)
- FACT · P3 · `strategies/funding_arb.rs:39-41`: `FUNDING_ARB_MAKER_OFFSET_BPS=1.0`,
  `FUNDING_ARB_MAKER_BUFFER_TICKS=1`, `_TIMEOUT_MS=45_000`. Unlike the cost/threshold
  consts (l.33-38, which ARE wired into the overridable `FundingArbParams` via
  `apply()` l.158-170 + snapshot l.183-190), these maker-execution consts have no
  params field. funding_arb is RETIRED (AMD-2026-05-26-01, active=false), so impact
  is dormant → P3, informational.
  Fix: fold into FundingArbParams if/when strategy revived. Owner E1; verifier QC.

## NEW P3-C — Bybit REST/WS client connection constants are hardcoded (Category 4)
- FACT · P3 · `bybit_rest_client.rs`
- `recv_window: "5000"` (l.1004, struct init), HTTP `.timeout(from_secs(10))`
  (l.995), and rate-limit/latency window consts `REST_LATENCY_WINDOW_SECS` /
  `RET_CODE_WINDOW_SECS` / `GLOBAL_THRESHOLD` (used l.399..580, 1331). WS side:
  reconnect backoff via `ws_backoff::BackoffConfig::ws_private_default()` (3s base /
  60s cap / x2, l.30-36) + ping 20s + `WS_RTT_WINDOW_SECS`/`WS_DROPOUT_WINDOW_SECS`.
  None config/IPC-overridable. Evidence: grep `bybit_rest_client.rs` +
  `bybit_private_ws.rs` (this run).
- Why real not FP: `recv_window` and request timeout directly affect live order
  reliability (too-small recv_window → signed-request rejects under clock skew /
  latency; fixed 10s timeout interacts with the fail-closed-on-timeout rule in
  CLAUDE.md §四). These are legitimate per-deployment knobs (mainnet vs demo
  latency profiles differ) yet require a rebuild to change.
- Why only P3: current values are reasonable Bybit-spec defaults (5000ms is Bybit's
  documented recv_window default; 10s timeout is generous); the rate-limit windows
  are observability/pacing, not risk gates. NONE defeats a risk control — the
  fail-closed timeout path is preserved (a hardcoded-but-present timeout is SAFER
  than none). So this is a tunability-debt item, not a safety bug.
- IMPORTANT non-finding: NO hardcoded `min_notional` / `tick_size` / `lot_size`
  *values* — those are resolved at runtime via `InstrumentInfoCache` + `spec.
  round_price/round_qty` (l.704-840), i.e. fetched from the exchange, NOT magic
  numbers. That is the correct pattern. retCode classification (is_retryable /
  is_exchange_backoff / PriceTickInvalid=110049) is semantic, not a tunable.
- Fix direction: optionally lift recv_window + http_timeout into a `[bybit_client]`
  config block (defaults bit-identical). Low priority. Owner E1/BB; verifier BB+QC.

## Counts
- Config params swept WITH evidence: **~30 TOML blocks** (cats 1/2/3/5, all 5 envs).
- Rust constant families examined WITH evidence: **5** — confluence (config-backed
  via serde), funding_arb cost/thr (config-backed via params), maker_rejection
  consts (hardcoded → P3-A), funding_arb maker consts (hardcoded → P3-B), Bybit
  REST/WS client consts (hardcoded → P3-C).
- NEW findings: **3 (all P3)**: P3-A close-maker rate-limit, P3-B funding_arb maker
  exec consts (dormant), P3-C Bybit client recv_window/timeout/windows.
- Re-confirmed: **1 (P2 confluence DB-load gap)**.
- ALL 5 categories complete with evidence.

## Recommendation to PM
Sweep is COMPLETE. No re-dispatch needed for coverage. Optional low-priority
follow-ups: (a) the one remaining unverified claim is the in-comment assertion that
`budget_config.toml daily_usd_max=2.0 ↔ layer2_types.py:60 DEFAULT_DAILY_HARD_CAP_USD`
— a 1-line cross-check would close it (not done this run; Python side not read);
(b) bundle P3-A/P3-C into a single "exec-constants → config" cleanup ticket if/when
the close-maker or exchange-latency path needs live calibration. **No promotion
blocker introduced; no hardcoded value defeats a risk control; structural gate
remains P0-EDGE-1 (operator decision), unchanged.**
