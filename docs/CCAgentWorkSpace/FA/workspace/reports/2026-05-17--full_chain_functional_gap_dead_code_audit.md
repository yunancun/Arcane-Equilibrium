# FA Full-Chain Functional Gap and Dead-Code Audit

Date executed: 2026-05-29
Requested report date prefix: 2026-05-17
Role: FA
Repo root: `/Users/ncyu/Projects/TradeBot/srv`
Mode: read-only audit, except this report file.

## Executive Summary

P0 findings: 0.
P1 findings: 3.
P2 findings: 2.
P3 findings: 1.

No P0/P1 direct live-trading bypass, auth bypass, or order-authority violation was found in the inspected chain. The P1s are functional truth-state blockers: active planning documents and helper indexes now disagree with source/runtime state for Sprint 2 Alpha Tournament and M11 replay scheduling, and one advertised Alpha Tournament daily evidence entrypoint still behaves as a scaffold.

## Audit Envelope

Startup and authority documents inspected:

- `AGENTS.md`
- `CLAUDE.md`
- `TODO.md`
- `.codex/MEMORY.md`
- `.codex/agents/INDEX.md`
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `.codex/SUBAGENT_EXECUTION_RULES.md`
- `.codex/agents/FA.md`
- `.claude/agents/FA.md`
- `docs/CCAgentWorkSpace/FA/profile.md`
- `docs/CCAgentWorkSpace/FA/memory.md`
- `.claude/skills/spec-compliance/SKILL.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--cold_audit_baseline_freeze.md`
- `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-17--index_integrity_audit.md`
- `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-17--doc_inventory_dedup_audit.md`

Additional functional sources inspected:

- `CONTEXT.md`
- `README.md`
- `docs/governance_dev/SPECIFICATION_REGISTER.md`
- `docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md`
- `docs/execution_plan/specs/2026-05-28--alpha_tournament_activation_protocol.md`
- `helper_scripts/SCRIPT_INDEX.md`
- `helper_scripts/alpha_tournament/attribution_daily.py`
- `helper_scripts/alpha_tournament/tournament_orchestrator.py`
- `helper_scripts/cron/m11_replay_runner_daily_cron.sh`
- `helper_scripts/cron/install_m11_replay_runner_cron.sh`
- `helper_scripts/cron/ac19_alt_bucket_daily_cron.sh`
- `program_code/local_model_tools/backtest_engine.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py`
- `rust/openclaw_core/src/lib.rs`
- `rust/openclaw_core/src/backtest.rs`
- `rust/openclaw_core/src/portfolio.rs`
- `rust/openclaw_engine/src/strategies/*`

Runtime checks were limited to read-only SSH, `crontab -l`, `ps`, `tail`, and `psql SELECT`. No code, runtime config, auth, deployment, migration, restart, or trading state was mutated.

## Source vs Runtime Drift

FACT: Current source heads are aligned at audit time.

Evidence command:

```bash
git rev-parse HEAD && git branch --show-current && git status --porcelain=v1 -b && git ls-remote --heads origin main
ssh trade-core "cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD && git branch --show-current && git status --porcelain=v1 -b"
```

Observed:

- local HEAD: `5097bd0670277e24516460f6914a85acf9969d87`
- origin/main: `5097bd0670277e24516460f6914a85acf9969d87`
- Linux `trade-core` HEAD: `5097bd0670277e24516460f6914a85acf9969d87`
- Linux worktree: clean relative to origin/main
- local worktree contains pre-existing dirty/untracked role-memory/report/migration changes outside this FA report path.

INFERENCE: PM baseline source-vs-runtime HEAD drift from the cold freeze report has been closed by the time of this FA audit. Functional drift remains in TODO/spec/index state and in the distinction between source-landed code, runtime cron fire, and claimed feature completion.

## Findings

### FA-FC-001 - Alpha Tournament implementation state is contradictory across active SSOT, TODO, and source

Classification: FACT
Severity: P1

Affected paths and lines:

- `docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md:5` says `SPEC-FINAL / IMPL-PENDING`.
- `docs/governance_dev/SPECIFICATION_REGISTER.md:123` says `Alpha Tournament SSOT` is active and `IMPL-PENDING`.
- `TODO.md:29` says business Sprint 2 Alpha Tournament is `SSOT SPEC-FINAL / IMPL NOT STARTED`.
- `TODO.md:187` says the major correction is that Sprint 2 is mostly done and W2-B Rust IMPL landed.
- `rust/openclaw_engine/src/strategies/tests.rs:118` through `rust/openclaw_engine/src/strategies/tests.rs:125` assert the factory includes the two new Sprint 2 strategies.
- `rust/openclaw_engine/src/strategies/tests.rs:138` through `rust/openclaw_engine/src/strategies/tests.rs:143` assert `funding_short_v2` and `liquidation_cascade_fade` are present.
- `rust/openclaw_engine/src/strategies/registry.rs:278` through `rust/openclaw_engine/src/strategies/registry.rs:320` wire both candidates from strategy params.
- `rust/openclaw_engine/src/strategies/params.rs:163` through `rust/openclaw_engine/src/strategies/params.rs:167` keep both candidates fail-closed by default with `active=false`.

Evidence command / inspection method:

```bash
nl -ba docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md | sed -n '1,90p'
nl -ba docs/governance_dev/SPECIFICATION_REGISTER.md | sed -n '118,162p'
nl -ba TODO.md | sed -n '1,80p'
nl -ba TODO.md | sed -n '180,192p'
rg -n "funding_short_v2|liquidation_cascade_fade|StrategyKind::" rust/openclaw_engine/src/strategies rust/openclaw_engine/src -g'*.rs'
```

Impact:

Agents using the active SSOT/register banner will conclude the Alpha Tournament implementation has not started, even though the W2-B candidate code, params, registry wiring, and tests are already present. This can cause duplicate implementation dispatch, stale PA/E1 scoping, and missed verification of the real remaining work: Stage 0R sanity, evidence accumulation, M11 scheduling, and activation readiness.

Why real, not false positive:

The contradiction is in active sources, not archive files. The same active TODO file says both `IMPL NOT STARTED` at line 29 and `Sprint 2 大半已 DONE` at line 187. Source confirms the two candidate strategies are not just planned: modules, registry wiring, params, and tests exist. The candidates are intentionally inactive by default, so this finding does not claim they have trading authority.

Suggested fix direction:

Split status into explicit phases:

- `candidate scaffold/source IMPL DONE`
- `active=false / no trading authority`
- `Stage 0R runtime evidence pending`
- `Alpha Tournament activation framework future / Sprint 4-5`

Update the Alpha SSOT header, `SPECIFICATION_REGISTER.md`, and TODO phase banner to remove `IMPL NOT STARTED` while preserving fail-closed governance language.

Fix owner role: PM + TW, with PA confirming phase semantics.
Verification owner role: FA + R4, with E4 if test status is restated.

### FA-FC-002 - M11 replay scheduling docs are stale, while runtime cron is installed and only partial M11 output is proven

Classification: FACT
Severity: P1

Affected paths and lines:

- `TODO.md:15` lists `M11 cron install` as a residual item.
- `TODO.md:48` says `replay_runner` has `0 cron + 0 systemd schedule`.
- `TODO.md:53` says replay evidence remains an operator/runtime hand-action.
- `TODO.md:186` says E1 install is pending.
- `TODO.md:187` repeats M11 cron install as true residual work.
- `CONTEXT.md:86` claims M11 nightly continuous validation outputs `learning.replay_divergence_log`.
- `helper_scripts/SCRIPT_INDEX.md:20` now documents the M11 daily cron wrapper and heartbeat.

Evidence command / inspection method:

```bash
ssh trade-core "crontab -l | grep -E 'm11_replay_runner_daily|ac19_alt_bucket_daily|pg_dump|alpha_tournament|attribution_daily' || true"
ssh trade-core "tail -n 25 /tmp/openclaw/logs/m11_replay_runner_daily_cron.cron.log 2>/dev/null || true; ls -l /tmp/openclaw/cron_heartbeat/m11_replay_runner_daily.last_fire 2>/dev/null || true"
ssh trade-core "set -a; . /home/ncyu/BybitOpenClaw/secrets/compose_env/trading_services.env; set +a; PGPASSWORD=\$POSTGRES_PASSWORD psql -h 127.0.0.1 -U \${POSTGRES_USER:-trading_admin} -d \${POSTGRES_DB:-trading_ai} -Atc \"SELECT 'replay_experiments', count(*), max(created_at) FROM replay.experiments; SELECT 'replay_divergence_log', count(*), max(created_at) FROM learning.replay_divergence_log; SELECT 'earn_movement_log', count(*), max(event_ts) FROM learning.earn_movement_log;\""
```

Observed:

- Runtime crontab contains `0 4 * * * ... m11_replay_runner_daily_cron.sh`.
- Runtime log shows failures first, then an OK run at `2026-05-28T16:53:53Z` with experiment id `c0ba0553-5cba-4024-934d-82f0ef81468c` and run id `6532fc38338f4bf299846c0c55f880c5`.
- Heartbeat exists at `/tmp/openclaw/cron_heartbeat/m11_replay_runner_daily.last_fire`.
- `replay.experiments` count is `24`, max `created_at` is `2026-05-28 18:53:51.78058+02`.
- `learning.replay_divergence_log` count is `0`.
- `learning.earn_movement_log` count is `0`.

Impact:

The active TODO state is stale in one direction and the functional M11 claim is incomplete in the other direction. PM/E1 may dispatch a cron install that already exists, while FA/PA/QC may incorrectly treat the first successful smoke replay as full M11 nightly divergence validation. This also affects passive healthcheck interpretation for `[48] replay_manifest_registry_growth`.

Why real, not false positive:

Runtime crontab and log prove the Stage A smoke cron exists and fired successfully. The database proves a new replay experiment was registered. The same database also proves no divergence rows exist, so the broader M11 output claim in `CONTEXT.md` is not yet functionally satisfied.

Suggested fix direction:

Update TODO and healthcheck notes to say:

- M11 Stage A smoke cron installed and first runtime fire succeeded.
- `[48]` should be re-evaluated against the passive healthcheck rule after the 24h window.
- Full M11 divergence pipeline remains pending until `learning.replay_divergence_log` receives expected rows from a real nightly validation path.

Fix owner role: PM + TW for source-of-truth text; E1 if a fuller replay-divergence writer remains unwired.
Verification owner role: FA + E4; MIT if DB/cron semantics are promoted into governance gates.

### FA-FC-003 - Advertised Alpha Tournament daily evidence entrypoint is still a scaffold and is not the runtime cron path

Classification: FACT
Severity: P1

Affected paths and lines:

- `helper_scripts/SCRIPT_INDEX.md:61` says `alpha_tournament/attribution_daily.py` is the Sprint 2 daily cron at `02:30 UTC`.
- `helper_scripts/alpha_tournament/attribution_daily.py:277` through `helper_scripts/alpha_tournament/attribution_daily.py:286` says the real PG path is still pending W2-F PA wire-up.
- `helper_scripts/alpha_tournament/attribution_daily.py:288` through `helper_scripts/alpha_tournament/attribution_daily.py:299` returns zero candidate data with status `wire_up_pending_w2f_pa` and exit code 0.
- `helper_scripts/alpha_tournament/tournament_orchestrator.py:14` says the orchestrator is a stub returning 0 and writes no PG/file output.
- Runtime crontab has `ac19_alt_bucket_daily_cron.sh` at `08:00 UTC`, but no `alpha_tournament/attribution_daily.py` or `02:30 UTC` entry.

Evidence command / inspection method:

```bash
nl -ba helper_scripts/SCRIPT_INDEX.md | sed -n '52,72p'
nl -ba helper_scripts/alpha_tournament/attribution_daily.py | sed -n '250,315p'
nl -ba helper_scripts/alpha_tournament/tournament_orchestrator.py | sed -n '1,90p'
rg -n "alpha_tournament|attribution_daily|ac19_alt_bucket_daily_cron|m11_replay_runner_daily" helper_scripts/cron helper_scripts/alpha_tournament helper_scripts/SCRIPT_INDEX.md
ssh trade-core "crontab -l | grep -E 'm11_replay_runner_daily|ac19_alt_bucket_daily|pg_dump|alpha_tournament|attribution_daily' || true"
```

Impact:

The script index advertises `attribution_daily.py` as the production daily Alpha Tournament evidence cron, but invoking it without `--dry-run` still returns a scaffold summary with zero fills and success exit. The actual runtime evidence path is the separate AC-19 ALT bucket cron. This can mislead operators or agents into treating a placeholder success as real candidate evidence, or into looking for the wrong cron name/time.

Why real, not false positive:

The script itself explicitly says the real PG query path is pending and populates `wire_up_pending_w2f_pa`. Runtime crontab proves the advertised Alpha Tournament entrypoint is not installed. The AC-19 cron exists, but it is a separate script and should not make `attribution_daily.py` appear production-wired.

Suggested fix direction:

Either wire `attribution_daily.py` to the real PG/cron path, or mark it explicitly as a scaffold in `SCRIPT_INDEX.md` and require `--dry-run` for zero-data success. Document `ac19_alt_bucket_daily_cron.sh` as the current runtime evidence collector for Sprint 2 until the Alpha Tournament module is actually wired.

Fix owner role: E1 for script behavior; TW for index wording; PA for evidence-path boundary.
Verification owner role: E4 + FA.

### FA-FC-004 - Backtest REST/API path uses a Python stub while the Rust backtest engine is not wired to that path

Classification: FACT
Severity: P2

Affected paths and lines:

- `README.md:102` describes `openclaw_core` as containing risk/backtest functionality.
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py:57` imports `BacktestEngine` from Python `local_model_tools.backtest_engine`.
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py:195` through `program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py:222` creates the Python engine singleton.
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py:296` and `program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py:335` call that singleton for `/api/v1/backtest/run`.
- `program_code/local_model_tools/backtest_engine.py:1` through `program_code/local_model_tools/backtest_engine.py:8` declares the Python engine a stub and says Rust is authoritative.
- `program_code/local_model_tools/backtest_engine.py:56` through `program_code/local_model_tools/backtest_engine.py:64` returns a zero-filled result with warning.
- `program_code/local_model_tools/backtest_engine.py:71` through `program_code/local_model_tools/backtest_engine.py:76` reports `stub: True`.
- `rust/openclaw_core/src/backtest.rs:103` through `rust/openclaw_core/src/backtest.rs:129` contains a Rust `BacktestEngine` implementation, but it is not used by the API route above.

Evidence command / inspection method:

```bash
nl -ba program_code/local_model_tools/backtest_engine.py | sed -n '1,220p'
nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py | sed -n '45,235p'
nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py | sed -n '285,435p'
nl -ba rust/openclaw_core/src/backtest.rs | sed -n '1,180p'
rg -n "from .*backtest_engine|BacktestEngine\\(|backtest_engine" program_code . -g'*.py'
```

Impact:

Backtest API responses, evolution code, and any TruthSourceRegistry injection using this route cannot be treated as real historical backtest evidence. They are deterministic no-ops unless another path bypasses the route. This matters for functional claims around research/evolution/backtest evidence, but does not directly grant live trading authority.

Why real, not false positive:

The Python file intentionally labels itself `STUB`, returns zero-filled results, and exposes `stub: True`. The route imports and calls that Python stub. The Rust implementation exists but `rg` found only crate exports/tests, not a route binding from the FastAPI path to `openclaw_core::backtest`.

Suggested fix direction:

Keep the endpoint if needed, but label it as diagnostic/stub in API/docs/UI unless and until it calls the Rust backtest or a replay-backed evidence path. If the endpoint is meant to drive learning, block TruthSourceRegistry injection from stub output or require a non-stub provenance flag.

Fix owner role: PA for contract; E1 for bridge/removal; TW for docs/API label.
Verification owner role: FA + E4.

### FA-FC-005 - Active ADR register rows for ADR-0036 through ADR-0041 point to missing filenames

Classification: FACT
Severity: P2

Affected paths and lines:

- `docs/governance_dev/SPECIFICATION_REGISTER.md:133` through `docs/governance_dev/SPECIFICATION_REGISTER.md:138`

Evidence command / inspection method:

```bash
nl -ba docs/governance_dev/SPECIFICATION_REGISTER.md | sed -n '125,142p'
rg --files docs/adr | sort | sed -n '30,50p'
```

Observed actual files include:

- `docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`
- `docs/adr/0037-m9-ab-framework-and-statistical-methodology.md`
- `docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`
- `docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md`
- `docs/adr/0040-multi-venue-gate-spec.md`
- `docs/adr/0041-context-distiller-v4-and-ai-cost-cap-amendment.md`

Impact:

Agents following the register cannot open several active ADRs that define M8/M9/M10/M11/M12/M13 and ContextDistiller governance. This is a functional spec-loading risk: downstream FA/PA/E1 work can miss required constraints even though the files exist.

Why real, not false positive:

This is not a stale archive pointer. The rows are in the active specification register and the listed filenames do not match the files on disk. R4 independently flagged the same register integrity issue as P1 in `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-17--index_integrity_audit.md`; FA severity is P2 because the immediate issue is spec discoverability, not runtime behavior.

Suggested fix direction:

Update only the path cells in `SPECIFICATION_REGISTER.md` for ADR-0036 through ADR-0041 to match actual filenames. Then run an index/path validation pass.

Fix owner role: TW.
Verification owner role: R4 + FA.

### FA-FC-006 - Residual `openclaw_core` backtest/portfolio modules are exported and tested but not production-called by the engine

Classification: FACT
Severity: P3

Affected paths and lines:

- `rust/openclaw_core/src/lib.rs:18` exports `backtest`.
- `rust/openclaw_core/src/lib.rs:48` exports `portfolio`.
- `rust/openclaw_core/src/backtest.rs:103` defines `BacktestEngine`.
- `rust/openclaw_core/src/portfolio.rs:90` through `rust/openclaw_core/src/portfolio.rs:100` defines `check_portfolio_risk`.
- `TODO.md:368` tracks the known D-16 `openclaw_core` sunset tail as 7 cleared and 2 pending PA.

Evidence command / inspection method:

```bash
nl -ba rust/openclaw_core/src/lib.rs | sed -n '1,140p'
nl -ba rust/openclaw_core/src/backtest.rs | sed -n '1,180p'
nl -ba rust/openclaw_core/src/portfolio.rs | sed -n '1,180p'
rg -n "openclaw_core::(backtest|portfolio)|crate::(backtest|portfolio)|use openclaw_core::(backtest|portfolio)|mod (backtest|portfolio)" rust -g'*.rs'
```

Observed:

`rg` found the modules exported from `openclaw_core` and used by `rust/openclaw_core/tests/golden_extreme.rs`, but no production caller in `openclaw_engine`.

Impact:

These modules add maintenance and semantic ambiguity around where real portfolio/backtest authority lives. The practical issue is lower severity because TODO already tracks D-16 as dormant, and the current Python API backtest stub is separately covered in FA-FC-004.

Why real, not false positive:

The modules compile and have tests, but production engine call sites were not found by symbol search. This matches the existing TODO D-16 dormant-tail note rather than contradicting it.

Suggested fix direction:

PA should decide whether these are future-use retained modules, test fixtures, or sunset candidates. If retained, document the non-authoritative status and expected future binding. If sunset, remove exports/code under the existing D-16 workflow after E2/E4 review.

Fix owner role: PA + E1.
Verification owner role: E2 + E4 + FA.

## Non-Findings / Confirmed Boundaries

- FACT: Current local, origin/main, and Linux source heads are aligned at `5097bd0670277e24516460f6914a85acf9969d87`.
- FACT: The active engine process exists on Linux as `rust/target/release/openclaw-engine`, but this audit did not rebuild, restart, or mutate runtime.
- FACT: The new Alpha Tournament candidates are source-wired but default inactive; this audit found no evidence that they currently bypass Decision Lease, Guardian, or the five live gates.
- FACT: The M11 Stage A smoke cron being installed does not prove full M11 nightly divergence validation because `learning.replay_divergence_log` has zero rows.

## Blockers

Audit blockers: none.

Functional blockers found:

- P1 Alpha Tournament status drift across active SSOT/register/TODO/source.
- P1 M11 schedule state drift and incomplete divergence output.
- P1 Alpha Tournament daily evidence entrypoint scaffold vs advertised cron behavior.
