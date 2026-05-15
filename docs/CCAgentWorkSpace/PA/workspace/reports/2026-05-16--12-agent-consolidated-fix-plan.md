# 12-Agent Consolidated Audit Fix Plan
## PA Technical Verdict — 2026-05-16

---

## Section 1: Finding Verification (P0 / CRITICAL / BLOCKER)

### FA Findings

| ID | Claim | Verdict | Evidence |
|---|---|---|---|
| FA-P0-1 | ONNX `model_manager.rs:108` predict() returns None unconditionally (stub) | **CONFIRMED** | `model_manager.rs:111`: line reads `None` -- TODO comment says "Replace with ort::Session::run()". The `LoadedModel` struct at :34 has no real ort::Session, only `_path` / `feature_dim` / `_version`. Entire module is placeholder. |
| FA-P0-2 | `executor.shadow_mode=true` in ALL 3 TOML configs | **CONFIRMED** | `risk_config_demo.toml:244` shadow_mode=true, `risk_config_paper.toml:226` shadow_mode=true, `risk_config_live.toml:240` shadow_mode=true. This is **by design** -- live shadow_mode flip requires Phase C auth-gated IPC (per :236-238 comment). Not a bug; it is the intended pre-live state. |
| FA-P0-3 | `learning.rl_transitions` + `learning.symbol_clusters` have ZERO writers | **CONFIRMED** | Zero grep hits for INSERT/write to either table across all `.py` and `.rs` files. V068 migration classifies both as "review-only placeholder". These are dead schema from V004. |
| FA-P0-4 | Layer 2 Engine manual-only trigger, no scheduler | **CONFIRMED with context** | Per ADR-0020 (layer2-manual-supervisor-only), this is an explicit architectural decision, not a bug. L2 Claude is supervisor-escalation only. |
| FA-P0-5 | All 5 strategies negative realized edge (P0-EDGE-1) | **CONFIRMED** | Known active P0. CLAUDE.md section 3 explicitly states `[40]` negative realized edge remains active. This is a strategy quality problem, not a code bug. |
| FA-P1-9 | exit_features.est_net_bps 100% NULL | **CONFIRMED with context** | `exit_features` module exists; DUAL-TRACK-EXIT-1 T3/T4 wiring exists in `position_risk_evaluator.rs`. The 100% NULL is because exit feature writers are not yet live-wired to production. Part of Track P maturity gap. |
| FA-P1-11 | LIVE-RECONCILER-STALE-CMD-TX | **CONFIRMED** | `main.rs:435` and `:1290-1296` both carry explicit P1 TODO comments referencing this issue. Reconcilers hold `cmd_tx` by-value, preventing pipeline respawn from reaching them with new channels. |

### AI-E Findings

| ID | Claim | Verdict | Evidence |
|---|---|---|---|
| AI-E-F-04 | ai_service_dispatch.py Strategist IPC path has ZERO record_ai_invocation calls | **CONFIRMED** | `ai_service_dispatch.py:192-308` (_handle_strategist) -- no call to `record_ai_invocation` or `_record_ai_invocation`. Other agents (Guardian, Analyst, Strategist-edge-eval) do call it. The primary Strategist-as-Configurator path is unrecorded. |
| AI-E-F-06 | OPENCLAW_COST_EDGE_ADVISOR env unset | **CONFIRMED by design** | This is env-gated DEFAULT-OFF (`cost_edge_advisor_boot.rs:145`). The advisor daemon is opt-in via `OPENCLAW_COST_EDGE_ADVISOR=1`. Not a bug but a maturity gap (P1-FAKE-3 pattern). |
| AI-E-F-01 | budget_config.toml daily_usd_max=100 (50x DOC-08 $2 cap) | **CONFIRMED** | `budget_config.toml:27` and `settings/risk_control_rules/budget_config.toml:6` both read `daily_usd_max = 100.0`. DOC-08 section 12 KPI says $2/day target. The config has never been tightened. |
| AI-E-F-09 | 27B model available but Rust hardcodes l1_9b | **CONFIRMED** | `strategist_scheduler/evaluate.rs:412` hardcodes `"model_tier": "l1_9b"`. The H3 stats struct tracks both `l1_9b_count` and `l1_27b_count` fields, and pricing.rs references qwen-3.5-9b, but the scheduler always requests 9B. No model_router dynamic selection exists. |

### QC Findings

| ID | Claim | Verdict | Evidence |
|---|---|---|---|
| QC-P0-1 | Donchian look-ahead bias: trend.rs:190 includes current bar | **CONFIRMED** | `openclaw_core/src/indicators/trend.rs:190`: `let h_window = &high[n - period..n]` -- the window includes the current bar (index n-1). When `high` array is updated with current tick's high before this call, the Donchian upper includes the current bar's high. The test `test_w_audit_6_bb_breakout_5m_hard_gate_uses_prior_donchian` (tests.rs:257) mentions "prior-bar" semantics exist for the 5m runtime path, but the underlying `donchian()` function itself has the look-ahead. The fix is to pass `high[..n-1]` and `low[..n-1]` (prior bar only) or add a `donchian_prior()` variant. |
| QC-P0-2 | funding_arb entry threshold (5 bps) below breakeven (11.33 bps) | **DISPUTED (moot)** | `strategy_params_demo.toml:170`: `funding_threshold = 0.0005` (5 bps) and `total_cost_bps = 34.0`. However, funding_arb is `active = false` across all three environments (demo/paper/live) since 2026-05-03. The strategy directory does not exist in Rust (`src/strategies/funding_arb/` missing -- it was never ported to Rust). This is a known deprecated strategy (ADR-0018, memory `project_funding_arb_v2_deprecation_path`). The mathematical finding is correct but the strategy cannot execute. |
| QC-P1-1 | OU sigma uses raw second moment not residual std | **CONFIRMED** | `grid_helpers.rs:140`: `let sigma = (changes.iter().map(|c| c * c).sum::<f64>() / n_f).sqrt()` -- this computes the sample RMS of changes, not the residual standard deviation from the OU regression. The residual sigma should be `sqrt(sum((dx_i - a - b*x_i)^2) / (n-2))` where a,b are from the OLS. The current formula conflates OU drift with volatility, systematically overestimating sigma when theta is high. |

### E5 Findings

| ID | Claim | Verdict | Evidence |
|---|---|---|---|
| E5-P-1 | step_4_5_dispatch.rs 53 `.clone()` on hot path | **CONFIRMED** | `grep -c ".clone()" step_4_5_dispatch.rs` returns 53. This is the tick-level dispatch hot path. |
| E5-P-2 | state_compiler.py triple deepcopy | **CONFIRMED** | `state_compiler.py:627` deepcopy cache return, `:630` deepcopy input, `:635` deepcopy result. Three `copy.deepcopy()` calls per compile_state() invocation. The B6 dirty-flag cache mitigates frequency but when dirty the triple copy is real. |

### A3 Findings (GUI)

| ID | Claim | Verdict | Evidence |
|---|---|---|---|
| A3-BLOCKER-1 | Emergency Stop is one-click inside modal | **CONFIRMED** | `tab-live.html:556`: `<button class="btn-emergency" onclick="doEmergencyStop()">` -- single click inside a simple dialog. No typed-phrase confirmation. The dialog shows warnings but the action button is a single click. |
| A3-BLOCKER-2 | Close All Live one-click | **CONFIRMED** | `tab-live.html:572`: `<button onclick="doLiveCloseAll()">` -- same pattern, single click inside modal. |
| A3-MAJOR-1 | Start Live no confirmation at all | **CONFIRMED** | `tab-live.html:318/1563`: `liveStart()` directly calls `ocPost('/api/v1/live/session/start', {})` with no dialog, no confirmation, no typed phrase. One click starts live trading with real money. |

### E3 Findings (Security)

| ID | Claim | Verdict | Evidence |
|---|---|---|---|
| E3-MED-2 | start_local.sh:86 + beta_quickstart.sh:78 bind 0.0.0.0 | **CONFIRMED** | `start_local.sh:86` has `--host 0.0.0.0`, `beta_quickstart.sh:78` has `--host 0.0.0.0`. These scripts bind to all interfaces. Per memory `feedback_restart_bind_host_default`, production `restart_all.sh` was already fixed to use Tailscale IPv4 auto-detect, but these two scripts remain unfixed. |
| E3-LOW-1 | CSP unsafe-inline | **CONFIRMED** | `main_legacy.py:340`: `script-src 'self' 'unsafe-inline'` and `:341` `style-src 'self' 'unsafe-inline'`. Known trade-off documented in comments at :318-320. |

### MIT Findings

| ID | Claim | Verdict | Evidence |
|---|---|---|---|
| MIT-P0-1 | PG work_mem=4MB, shared_buffers=128MB | **CANNOT VERIFY from Mac** | No postgresql.conf in repo; these are runtime PG settings on trade-core. Cannot dispute or confirm from source code alone. Likely accurate given default PG install. |
| MIT-P1-1 | Walk-forward purge missing in edge_estimate_validation.py:113-148 | **CONFIRMED** | `_walk_forward_oos_values()` at :138-147 does train/test window splitting but has zero purge/embargo between train and test windows. Train ends at `train_end`, test starts immediately at `train_end` -- no gap for position settlement or look-ahead buffer. |

### R4 Findings

| ID | Claim | Verdict | Evidence |
|---|---|---|---|
| R4-CRITICAL-1 | CLAUDE.md says "14 ADR" but actually 22 | **CONFIRMED** | `ls docs/adr/ | wc -l` returns 22. CLAUDE.md section 1 says "14 条 ADR". |
| R4-CRITICAL-2 | CLAUDE.md says "13-tab" but actually 16 tab files | **CONFIRMED** | `ls static/tab-*.html | wc -l` returns 16. CLAUDE.md section 5 says "13-tab". |

### BB Findings

| ID | Claim | Verdict | Evidence |
|---|---|---|---|
| BB-M-1 | backtest_routes.py:107 hardcodes mainnet URL | **CONFIRMED** | `backtest_routes.py:107`: `_BYBIT_BASE_URL = "https://api.bybit.com"` -- hardcoded mainnet. Should use env var or config. |
| BB-A-1 | retCode 110017 not in BybitRetCode enum | **CONFIRMED** | `bybit_rest_client.rs:297-356` enum BybitRetCode has 14 variants; 110017 (ReduceOnlyReject) is absent. |

### CC Findings

| ID | Claim | Verdict | Evidence |
|---|---|---|---|
| CC-F-1 | Decision Lease shadow-bypass-only | **CONFIRMED by design** | CLAUDE.md section 4 states `decision_lease_emitted = "shadow_bypass_lineage_only"`. This is the intended pre-live state, not a compliance failure. |

---

## Section 2: Prioritized Work Packages

### WP-01: GUI Safety Gates (A3 BLOCKERs + MAJORs)
**Priority: P0-BLOCKER** | **Risk: HIGH** | **Effort: 1 session**

| Finding | Fix |
|---|---|
| A3-BLOCKER-1 Emergency Stop one-click | Add typed-phrase confirmation ("EMERGENCY STOP" required) |
| A3-BLOCKER-2 Close All Live one-click | Add typed-phrase confirmation ("CLOSE ALL" required) |
| A3-MAJOR-1 Start Live no confirmation | Add confirmation dialog with session-start acknowledgement |
| A3-MAJOR-2 4 different modal patterns | Unify to single reusable `oc-confirm-dialog` component |
| A3-MAJOR-3 LinUCB 2 dead buttons | Remove dead buttons or wire to real endpoints |
| A3-MAJOR-4 Learning tab English-only labels | Translate 6 metric labels to Chinese |

**Files touched**: `tab-live.html`, `tab-learning.html`, possibly shared JS dialog helper.
**No cross-module side effects** -- pure GUI layer.

### WP-02: Donchian Look-Ahead Bias Fix (QC P0)
**Priority: P0** | **Risk: HIGH** | **Effort: 1 session**

| Finding | Fix |
|---|---|
| QC-P0-1 Donchian look-ahead | Add `donchian_prior()` in `openclaw_core/src/indicators/trend.rs` that takes `high[..n-1]` and `low[..n-1]`, or add a `prior_bar: bool` parameter. Wire bb_breakout to call the prior-bar variant. |

**Files touched**: `openclaw_core/src/indicators/trend.rs`, `bb_breakout/mod.rs` (verify ctx already passes prior bar data for 5m, extend to 1m), bb_breakout tests.
**Side effects**: Changes indicator output. All bb_breakout tests must be updated. Replay results will differ. Engine rebuild required.

### WP-03: OU Sigma Estimation Fix (QC P1)
**Priority: P1** | **Risk: MEDIUM** | **Effort: 0.5 session**

| Finding | Fix |
|---|---|
| QC-P1-1 OU sigma raw second moment | Replace `grid_helpers.rs:140` with residual std: `sigma = sqrt(sum((dx_i - (a + b*x_i))^2) / (n-2))` using the already-computed regression coefficients. |

**Files touched**: `strategies/grid_helpers.rs`, grid_helpers tests.
**Side effects**: Grid spacing will change (likely narrower when theta is high). Affects grid_trading strategy behavior. Need regression test comparison.

### WP-04: AI Observability + Budget (AI-E findings)
**Priority: P1** | **Risk: LOW** | **Effort: 1 session**

| Finding | Fix |
|---|---|
| AI-E-F-04 Strategist IPC no record_ai_invocation | Add `self._record_ai_invocation()` call in `_handle_strategist()` after Ollama response |
| AI-E-F-01 daily_usd_max=100 vs DOC-08 $2 | Reduce `budget_config.toml` daily_usd_max to 2.0 (or justified higher value with DOC-08 amendment) |
| AI-E-F-09 Hardcoded l1_9b | Add `model_tier` to strategist scheduler config (TOML param) instead of hardcoding. Wire model_router logic for 9B vs 27B selection. |

**Files touched**: `ai_service_dispatch.py`, `budget_config.toml` (x2), `strategist_scheduler/evaluate.rs`, config TOML.
**Side effects**: F-09 model_tier change is Rust + needs rebuild. F-04 and F-01 are Python/config only.

### WP-05: Security Hardening (E3 findings)
**Priority: P1** | **Risk: MEDIUM** | **Effort: 0.5 session**

| Finding | Fix |
|---|---|
| E3-MED-2 bind 0.0.0.0 | Replace `--host 0.0.0.0` with `--host 127.0.0.1` (or Tailscale auto-detect) in start_local.sh and beta_quickstart.sh |
| E3-MED-4 API error leaks str(exc) | Add exception sanitizer middleware / wrap error responses |
| E3-LOW-1 CSP unsafe-inline | P2 backlog -- requires refactoring all inline JS/CSS to external files |

**Files touched**: `start_local.sh`, `beta_quickstart.sh`, error handling middleware in `main_legacy.py`.
**Side effects**: bind address change could break dev workflows -- need to document.

### WP-06: Performance Hot Path (E5 findings)
**Priority: P1** | **Risk: MEDIUM** | **Effort: 1-2 sessions**

| Finding | Fix |
|---|---|
| E5-P-1 53 .clone() in step_4_5_dispatch.rs | Audit each clone: replace String fields with Arc<str>, pass references where ownership not needed. Target 50% reduction. |
| E5-P-14 OrderIntent String fields | Convert OrderIntent symbol/strategy/side fields to Arc<str> or interned strings. |
| E5-P-2 state_compiler triple deepcopy | Eliminate input deepcopy (caller contract), use structural sharing for output. Target: 1 deepcopy max. |
| E5-P-3 298 inline time calls | Centralize to now_ms() utility. Dedup 4 definitions. |
| E5-P-4 orjson migration | Continue incremental migration from stdlib json to orjson. |

**Files touched**: `step_4_5_dispatch.rs`, order intent types, `state_compiler.py`, time utilities.
**Side effects**: Rust changes need extensive testing. state_compiler change needs thread-safety review.

### WP-07: Dead Code + Schema Cleanup (FA P0-3, P1-1)
**Priority: P2** | **Risk: LOW** | **Effort: 0.5 session**

| Finding | Fix |
|---|---|
| FA-P0-3 rl_transitions + symbol_clusters zero writers | Promote V068 "review-only" to "deprecated-pending-drop". Add P2 ticket for DROP after 30d notice. |
| FA-P1-1 openclaw_core 9 dead modules | Identify which modules have zero callers. Create cleanup plan. |
| FA-P1-2 PerceptionPlane validate_for_decision 0 callers | Wire to production or mark deprecated |
| FA-P1-3 H0_GATE Python singleton 0 production calls | Python H0Gate is a read-only view layer; verify Rust H0 gate is the real enforcement. Mark Python as display-only. |

**Files touched**: SQL migrations (new V-next for comments/drops), openclaw_core modules.
**Side effects**: DROP TABLE migrations must be guarded. Core module removal needs import analysis.

### WP-08: ML Pipeline Maturity (MIT findings)
**Priority: P1** | **Risk: MEDIUM** | **Effort: 2 sessions**

| Finding | Fix |
|---|---|
| MIT-P0-1 PG work_mem / shared_buffers | Linux runtime: tune postgresql.conf (work_mem=64MB, shared_buffers=2GB for 128GB system). Requires PG restart. |
| MIT-P0-2 6/12 ML cron scripts not installed | Install missing crontab entries on trade-core. Scripts exist in `helper_scripts/cron/` but are not in crontab. |
| MIT-P1-1 Drift chain broken | Install feature_baseline_writer cron (partially done per P1-WA4B-INSERT-1). Verify drift_events populate. |
| MIT-P1-2 Walk-forward purge missing | Add `purge_days` parameter to `_walk_forward_oos_values()`. Default gap = wf_test_days between train end and test start. |
| MIT-P1-3 decision_features 10.22M rows no prune | V075 created `prune_old_plain_tables()` function. Ensure cron calls it. |
| MIT-DB-6 Training uses only "demo" | Fix training SQL queries to include `WHERE engine_mode IN ('demo', 'live_demo')` per memory `project_engine_mode_tag_live_demo`. |

**Files touched**: Linux PG config (runtime), crontab (runtime), `edge_estimate_validation.py`, ML training scripts.
**Side effects**: PG restart impacts all services. Cron installation is Linux-only operation.

### WP-09: Documentation + Index Sync (R4 + TW findings)
**Priority: P2** | **Risk: LOW** | **Effort: 0.5 session**

| Finding | Fix |
|---|---|
| R4-CRITICAL-1 "14 ADR" should be 22 | Update CLAUDE.md section 1 to "22 ADR" |
| R4-CRITICAL-2 "13-tab" should be 16 | Update CLAUDE.md section 5 to "16-tab" |
| R4-HIGH-1 README missing 97 files | Add 2026-05-11+ files to docs/README.md index |
| TW-P1 KNOWN_ISSUES.md 33 days stale | Update KNOWN_ISSUES.md with current state |
| TW-P1 6 superseded files lack headers | Add SUPERSEDED headers |

**Files touched**: CLAUDE.md, docs/README.md, KNOWN_ISSUES.md, various docs.
**No code side effects**.

### WP-10: Bybit Integration (BB findings)
**Priority: P1** | **Risk: LOW-MEDIUM** | **Effort: 0.5 session**

| Finding | Fix |
|---|---|
| BB-M-1 backtest_routes.py mainnet URL | Replace hardcoded URL with env var / config lookup |
| BB-A-1 110017 not in BybitRetCode | Add `ReduceOnlyReject = 110017` variant with correct classification |

**Files touched**: `backtest_routes.py`, `bybit_rest_client.rs`.
**Side effects**: Rust enum change needs rebuild. RetCode classification determines fail-closed vs retry behavior.

### WP-11: Test Infrastructure (E4 findings)
**Priority: P2** | **Risk: LOW** | **Effort: 2-3 sessions (phased)**

| Finding | Fix |
|---|---|
| E4-HIGH-1 104/342 Rust files 0 coverage | Triage: identify 20 highest-risk uncovered files, add basic smoke tests |
| E4-HIGH-2 107/196 Python modules no test | Same triage approach |
| E4-HIGH-3 4 test files import errors | Fix import paths |
| E4-HIGH-5 test_v072 assertion string | Update expected assertion string |
| E4-HIGH-6 2 Rust integration test failures | Fix bb_breakout/bb_reversion test drift |
| E4-HIGH-7 39 Python tests no assertions | Add meaningful assertions |
| E4-HIGH-8 Zero DB connection loss tests | Add connection pool resilience tests |

**Files touched**: Spread across test directories.
**Side effects**: None (test-only changes).

### WP-12: ONNX Model Manager (FA-P0-1)
**Priority: P2 (deferred -- not blocking any runtime path)** | **Risk: LOW** | **Effort: 1 session**

The ONNX model_manager is a known stub. It returns None, which triggers rule-based fallback by design. The `ort` crate integration is a planned future enhancement, not a current regression. This is correctly classified as a P2 maturity gap, not a P0 runtime issue despite FA's classification.

### WP-13: Reconciler Stale cmd_tx (FA-P1-11)
**Priority: P1** | **Risk: HIGH** | **Effort: 1 session**

| Finding | Fix |
|---|---|
| FA-P1-11 LIVE-RECONCILER-STALE-CMD-TX | Refactor reconciler to receive cmd_tx via Arc<Mutex<>> or use a channel-renewal pattern through the spawner closure |

**Files touched**: `main.rs`, reconciler modules.
**Side effects**: Touches live pipeline respawn logic. High risk. Needs extensive testing.

---

## Section 3: Agent Assignment

| WP | Implement | Review | Sub-agent OK? | Session Strategy |
|---|---|---|---|---|
| WP-01 GUI Safety | E1a (frontend) | A3 + E2 | Yes, single E1a | 1 session; all tab-live.html changes atomic |
| WP-02 Donchian Fix | E1 (Rust) | QC + E2 + E4 | Yes, single E1 | 1 session; trend.rs + bb_breakout mod.rs + tests |
| WP-03 OU Sigma | E1 (Rust) | QC + E2 | Yes, can parallel with WP-02 (different files) | 0.5 session |
| WP-04 AI Observability | E1 (Python) + E1 (Rust) | AI-E + E2 | Split: E1-py (F-04, F-01) + E1-rs (F-09) | 1 session, 2 parallel E1 |
| WP-05 Security | E1 (mixed) | E3 + E2 | Yes, single E1 | 0.5 session |
| WP-06 Performance | E1 (Rust) + E1 (Python) | E5 + E2 | Split: E1-rs (P-1, P-14) + E1-py (P-2, P-3) | 2 sessions, can parallel |
| WP-07 Dead Code | E1 | FA + E2 | Yes, single E1 | 0.5 session |
| WP-08 ML Pipeline | MIT + E1 (Python) | MIT + E2 | Split: MIT (PG tuning, cron) + E1 (code fixes) | 2 sessions, sequential (PG first) |
| WP-09 Documentation | TW + R4 | PM | Yes, single TW | 0.5 session |
| WP-10 Bybit | E1 (mixed) | BB + E2 | Yes, single E1 | 0.5 session |
| WP-11 Test Infra | E4 + E1 | E2 | Phased over multiple sessions | 3 sessions total |
| WP-12 ONNX Stub | E1 (Rust) | E2 + FA | Deferred | Future sprint |
| WP-13 Reconciler | E1 (Rust) | E2 + E4 | Single E1, needs focused session | 1 session |

---

## Section 4: Parallel Execution Map

### Wave 1 (Immediate -- can start simultaneously)
```
WP-01 (GUI Safety)     [E1a]  ----  no dependency
WP-02 (Donchian)       [E1]   ----  no dependency
WP-05 (Security)       [E1]   ----  no dependency
WP-09 (Documentation)  [TW]   ----  no dependency
```
All four touch completely non-overlapping files. Maximum parallelism.

### Wave 2 (After Wave 1 Donchian fix lands, or independently)
```
WP-03 (OU Sigma)       [E1]   ----  after WP-02 if same E1, else independent
WP-04 (AI Observability) [E1-py + E1-rs]  ----  independent
WP-10 (Bybit)          [E1]   ----  independent
WP-07 (Dead Code)      [E1]   ----  independent
```

### Wave 3 (Requires Linux access or sequential dependency)
```
WP-08 (ML Pipeline)    [MIT + E1]  ----  PG tuning needs Linux; cron needs Linux
WP-06 (Performance)    [E1-rs + E1-py]  ----  large scope, after Wave 1/2 stabilize
WP-13 (Reconciler)     [E1-rs]  ----  high risk, needs focused attention
```

### Wave 4 (Background / Phased)
```
WP-11 (Test Infra)     [E4 + E1]  ----  ongoing, lowest priority
WP-12 (ONNX Stub)      [E1-rs]  ----  deferred to future sprint
```

### Dependency Graph
```
WP-01 ─────────────────────────────────> E2 review
WP-02 ──> WP-03 (same indicator area) ─> E2 + QC review
WP-05 ─────────────────────────────────> E2 + E3 review
WP-09 ─────────────────────────────────> PM review
WP-04 ─────────────────────────────────> E2 + AI-E review
WP-10 ─────────────────────────────────> E2 + BB review
WP-07 ─────────────────────────────────> E2 + FA review
WP-08 ──> (PG restart first) ──────────> MIT + E2 review
WP-06 ──> (after stability) ───────────> E5 + E2 review
WP-13 ──> (focused session) ───────────> E2 + E4 review
WP-11 ──> (phased) ───────────────────> E4 review
```

---

## Section 5: Cross-Audit Deduplication

### Cluster A: Negative Edge (3 agents)
- FA-P0-5, CC-F-2, QC ma_crossover negative Kelly
- **Root issue**: P0-EDGE-1. All 5 textbook strategies are alpha-deficient.
- **Consolidation**: Single P0 tracking item. Not fixable by code change -- requires new alpha hypothesis (W-AUDIT-8b funding skew, OI-confirmed 5m, etc.)
- **Action**: WP-02 (Donchian fix) may partially improve bb_breakout edge, but P0-EDGE-1 closure requires Phase B/C/D alpha candidates.

### Cluster B: ONNX / ML Stub (2 agents)
- FA-P0-1 (ONNX predict returns None), MIT (ML maturity 40%)
- **Root issue**: ML pipeline immaturity. ONNX is a stub, 6/12 crons not installed, drift chain broken.
- **Consolidation**: WP-08 (ML Pipeline) + WP-12 (ONNX). Sequential: get crons working first, ONNX integration later.

### Cluster C: Shadow Mode / Lease (3 agents)
- FA-P0-2 (shadow_mode=true everywhere), CC-F-1 (lease shadow-bypass-only), AI-E-F-06 (cost_edge_advisor unset)
- **Root issue**: Pre-live state. All three are **by design** -- the system is in shadow/demo mode before true-live promotion.
- **Consolidation**: NOT a fix target. These will change when operator authorizes Phase C live flip. No WP needed. Re-classify from P0 to KNOWN-STATE.

### Cluster D: Documentation Drift (2 agents)
- R4 (README gaps, CLAUDE.md counts wrong), TW (stale docs)
- **Root issue**: Documentation not synced after rapid 2026-05-11 sprint.
- **Consolidation**: WP-09.

### Cluster E: Funding Arb (2 agents)
- QC-P0-2 (threshold below breakeven), FA (negative edge)
- **Root issue**: Deprecated strategy. `active=false` everywhere, not in Rust.
- **Consolidation**: No fix needed. Strategy is already deprecated per ADR-0018. Close these findings as WONTFIX/MOOT.

### Cluster F: Test Gaps (2 agents)
- E4 (104 Rust / 107 Python files zero coverage), FA P1-1 (dead modules)
- **Root issue**: Coverage gaps correlate with dead/legacy code.
- **Consolidation**: WP-07 (dead code cleanup) reduces the denominator; WP-11 (test infra) increases numerator. Address in parallel.

---

## PA Risk Assessment Summary

| Category | Total Findings | Confirmed | Disputed/Moot | By Design |
|---|---|---|---|---|
| P0/CRITICAL/BLOCKER | 14 | 9 | 2 (QC-P0-2 moot, MIT-P0-1 unverifiable) | 3 (FA-P0-2, FA-P0-4, CC-F-1) |
| P1/HIGH/MAJOR | ~25 | 20+ | 0 | 0 |
| P2/MEDIUM/LOW | ~30 | verified subset | 0 | 0 |

### True P0 Items (require action before any live promotion)
1. **WP-01 A3-BLOCKER-1/2**: Emergency Stop / Close All must have typed-phrase confirmation
2. **WP-02 QC-P0-1**: Donchian look-ahead bias corrupts bb_breakout signal quality
3. **P0-EDGE-1**: Negative realized edge (structural, not code-fixable in one sprint)

### Items Falsely Elevated to P0
1. **FA-P0-1 ONNX stub**: By-design graceful degradation. Reclassify P2.
2. **FA-P0-2 shadow_mode=true**: By-design pre-live state. Reclassify KNOWN-STATE.
3. **FA-P0-4 Layer 2 no scheduler**: By-design per ADR-0020. Reclassify KNOWN-STATE.
4. **QC-P0-2 funding_arb threshold**: Strategy is deprecated and inactive. Reclassify MOOT.

### E2 Must-Review Points (top 3 for each wave)
**Wave 1**:
1. WP-01: Typed-phrase confirmation cannot be bypassed by browser console manipulation
2. WP-02: Donchian prior-bar semantics consistent across 1m and 5m timeframes
3. WP-05: bind address change does not break Tailscale remote access

**Wave 2**:
1. WP-03: OU sigma residual formula numerically stable (denominator n-2 != 0 guard)
2. WP-04 F-09: model_tier TOML param does not break existing IPC contract
3. WP-10 BB-A-1: 110017 classification (retryable vs terminal) is correct per Bybit docs

**Wave 3**:
1. WP-08: PG shared_buffers=2GB does not exceed 128GB system available memory
2. WP-06: Arc<str> migration does not break serialization (serde/IPC)
3. WP-13: Reconciler channel renewal is deadlock-free

---

## Appendix: Disposition of All Agent Findings Not Covered Above

### FA Remaining
- FA-P1-1 (openclaw_core dead modules): WP-07
- FA-P1-2 (PerceptionPlane): WP-07 (wire or deprecate)
- FA-P1-3 (H0_GATE Python): WP-07 (mark display-only)
- FA-P1-9 (exit_features NULL): Track P maturity, not blocking

### E4 Remaining
- E4-HIGH-4 (zero proptest/hypothesis): WP-11 Phase 2
- E4-baseline outdated ("2555/17" vs 7400): WP-09 (doc update)

### CC Remaining
- CC-F-3 (portfolio correlation): P2 backlog, requires new runtime module
- CC-F-4 (audit_migrations.py Mac path): WP-05 or WP-09

### BB Remaining
- BB-A-2/A-3 (ToS cert + IP preflight): WP-10 or P2 backlog
- BB-M-2 (replay hardcode mainnet): WP-10

---

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--12-agent-consolidated-fix-plan.md
