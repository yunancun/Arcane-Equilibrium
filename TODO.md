# OpenClaw TODO — active queue (v4)

Authoritative active-state file. Historical wave narratives and completed batch detail are archived under `docs/archive/`.

## Current Truth (2026-04-30 21:10 CEST)

- **Repo**: Mac/Linux source at `5ba9b1c` (`Track Scout heartbeat wiring P3 follow-up`). Mac worktree has unrelated dirty GUI static files; do not stage them for docs-only work.
- **Runtime**: Linux `trade-core` rebuilt from current source. Engine PID `1529433`, API PID `1554832`, watchdog alive, gateway alive. Watchdog reports `engine_alive=true`, demo/live snapshots fresh; paper is inactive by design.
- **Healthcheck**: latest cron summary is `FAIL` because `[38] grid_trading_lifecycle_drift` is a real strategy drift signal, not a dead pipeline. Current notable gates: WARN `[4]`, `[11]`, `[33]`, `[40]`; PASS `[35]`, `[36]`, `[37]`, `[39]`.
- **Live boundary**: LiveDemo/live pipeline is authorized and running under the live-grade gates. True autonomous live trading and live parameter mutation still require GovernanceHub + Decision Lease + the 5 live gates.
- **Primary active problem**: edge quality remains negative after fees. Judge strategy work by post-fee `net_bps_after_fee`; PnL/win-rate are secondary.

## Current Checkpoints

1. **Strategy edge model batch deployed** (`1644701`, runtime rebuilt): TOML-to-runtime wiring for MA/BB/grid maker buffers, grid `blocked_symbols`, reject cooldown, `min_grid_step_bps`, `cost_floor_multiplier`; scanner posterior LCB routing; MA `min_trend_snr`. Observe `[33]`, `[38]`, `[40]` using a post-deploy cutoff; rolling windows still contain old fills.
2. **Dust residual prevention deployed** (`8efe71b` + `b1cd9a8`, runtime rebuilt): primary exchange full-close uses Bybit `qty=0 + reduceOnly + closeOnTrigger`; normal zero-qty orders still fail closed; fast-track partial reduce skips when it would leave below-minNotional residue; `DUST_FROZEN`/`orphan_frozen` stay visible. Runtime efficacy still needs one real Demo/Live full-close observation.
3. **MLDE demo autonomy active**: `[35]` learning contract, `[36]` advisory/live lease boundary, `[37]` demo applier audit all PASS. Rust active LinUCB arm-space remains `v1_15`; richer `mlde_arm_id` is shadow/advisory until a separate migration.
4. **62-finding remediation closed**: Batch A-F fixed, signed off, deployed, and archived. Do not reopen as the current mainline unless a new regression is found.

## Now Actionable

| Priority | Item | Owner chain | Gate / evidence |
|---|---|---|---|
| P0 | Post-deploy edge observation | `PM -> QC -> MIT -> E4 -> PM` | `[33]` maker fee-drop, `[38]` grid lifecycle, `[40]` realized edge. Use post-deploy cutoff; do not conclude from mixed rolling windows alone. |
| P0 | Dust residual runtime proof | `PM -> E4 -> QA -> PM` | Wait for or safely inspect one real Demo/Live full-close path using `qty=0 reduceOnly closeOnTrigger`; verify no new below-minNotional residual. No manual live action without operator approval. |
| P1 | G1-04 final compute | `PM -> QC -> FA -> PM` | Due around 2026-05-01/02 after 1w post-G7-09 data. Recompute fee mix and R:R by strategy. |
| P1 | G2-02 ma_crossover dual-track | `PM -> QC -> FA -> E2 -> PM` | Due around 2026-05-03. Run counterfactual tool on post-fix demo data; result triggers or blocks G2-03 caller wiring. |
| P1 | G2-01 PostOnly settlement | `PM -> QC -> FA -> PM` | Due 2026-05-07/08. If maker fee-drop remains below target, schedule G2-04 strategy adjustment / disable decision. |
| P1 | G2-03 caller wire | `PM -> PA -> E1 -> E2 -> E4 -> PM` | Only after G2-02 conclusion. Current schema/helpers are staged; production caller still must be wired if approved. |
| P2 | ML training data hygiene | `PM -> MIT -> E1 -> E2 -> E4 -> PM` | Quantify historical `learning.exit_features` dust-noise rows; backfill only if material. |
| P2 | EDGE-P1b calibrator flow | `PM -> QC -> E1 -> E2 -> E4 -> QA -> PM` | Wait for per-strategy sample sufficiency; IPC `exit_stale_peak_ms` is closed, `shadow_enabled` remains TOML-only. |
| P3 | Scout heartbeat production wiring | `PM -> PA -> E1 -> E2 -> E4 -> PM` | Contract exists, but `ScoutAgent.record_scan()` still needs canonical production caller wiring if not already closed in the next code wave. |
| P3 | Refactor cleanup | `PM -> PA/E5 -> E1 -> E2 -> E4 -> PM` | `G3-08-FUP-MAF-SPLIT-CLEANUP`, analyst split, H-state query split, minor memory/doc nits. |

## Time-Driven Gates

| Gate | Target | Status | Healthcheck |
|---|---:|---|---|
| P0-2 21d demo clock | 2026-05-07 | still a live promotion prerequisite | watchdog + `[22]` / `[27]` / `[32]` |
| G1-04 final fee/R:R compute | 2026-05-01/02 | due next | `[33]` plus strategy R:R query |
| G2-02 ma_crossover replay | 2026-05-03 | tool ready, data-driven | targeted replay |
| G2-01 PostOnly acceptance | 2026-05-07/08 | maker quality still below target | `[33]` |
| GRID-LIFECYCLE-DRIFT observation | 2026-05-06 | active real signal | `[38]` |
| EDGE-P1b calibrator | ~2026-05-10 | wait for per-strategy rows | `[14]` |
| P0-3 edge decision | ~2026-05-15 | requires G1/G2/MLDE inputs | PM + FA + PA + QC decision |

## Background Threads

- **Fee-refresh RCA**: `[22]` remains PASS after periodic reseed fix. Keep watching hourly refresh logs only if `[22]` regresses.
- **bb_breakout**: `[12]` is PASS and producing limited demo samples. Do not switch runtime timeframe without a new PA/QC RFC.
- **Strategy-name attribution**: `[39]` is PASS after W1-T2 close attribution work; old “W1-T2 deferred” text is historical and archived.
- **Live auth**: current runtime is authorized. Historical schema-v1 startup block is no longer current status.
- **Linear posture**: Linear is an active mirror only; git remains source of truth. Do not publish secrets or detailed runtime PID/fill-rate internals externally.

## Healthcheck Map

Runtime registry includes numbered `[1]`-`[40]` except retired/unused `[17]`, plus `[Xa]` and `[Xb]`.

| Group | IDs | Meaning |
|---|---|---|
| Core trading flow | `[1]`-`[7]`, `[10]`, `[22]`-`[28]` | fills, labels, exit features, phys lock, edge estimates, intents/orders/signals freshness, dust/phantom checks |
| Passive edge gates | `[11]`-`[15]`, `[31]`-`[34]`, `[38]`-`[40]` | clean-window growth, bb_breakout, scheduler freshness, exit-feature sufficiency, shadow agreement, maker intent/fill/attribution, lifecycle and realized edge |
| Runtime/governance | `[16]`, `[18]`-`[21]`, `[29]`, `[30]`, `[Xa]`, `[Xb]` | strategist cycle, disabled strategy inventory, observer, H-state gateway, dust inventory, reconciler placeholder, cost-edge advisor, leader lock, pipeline triangulation |
| MLDE | `[35]`, `[36]`, `[37]` | learning data contract, advisory/live lease boundary, demo applier audit/live boundary |

Any passive wait with three consecutive relevant FAILs stops being passive and returns to PM triage.

## Archive Index

- Pre-cleanup snapshots: `docs/archive/2026-04-30--TODO-pre-cleanup-snapshot.md`, `docs/archive/2026-04-30--CLAUDE-pre-cleanup-snapshot.md`, `docs/archive/2026-04-30--README-pre-cleanup-snapshot.md`
- Active docs cleanup summary: `docs/archive/2026-04-30--active_docs_cleanup_archive.md`
- 62-finding Batch A-F: `docs/archive/2026-04-29--62finding-batch-A-to-F.md`
- STRKUSDT P0 Wave: `docs/archive/2026-04-29--strkusdt-p0-wave.md`
- Wave A-H narrative: `docs/archive/2026-04-29--wave-A-to-H-narrative.md`
- 2026-04-22~24 runtime/detail archive: `docs/archive/2026-04-29--claude_md_section3_pre_04_27_detail.md`
- Older TODO versions: `docs/archive/2026-04-24--todo_v2_dual_axis_snapshot.md`, `docs/archive/2026-04-24--todo_v1_refactor_snapshot.md`, `docs/archive/2026-04-24--todo_snapshot_pre_refactor.md`

## Workflow Quick Reference

```bash
# Mac source state
git status --short --branch && git log --oneline -5

# Linux source and runtime state
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch && git log --oneline -5"
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status"
ssh trade-core "tail -120 /tmp/openclaw/passive_wait_healthcheck_cron.log"
```

Implementation chain: `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`.
Compliance/architecture chain: `PM -> CC -> FA -> PA -> PM`.
Quant/ML/data chain: `PM -> QC -> MIT -> AI-E -> PM`.
Security/deploy/runtime chain: `PM -> E3 -> BB if exchange-facing -> PM`.

Deployment commands remain operator-gated when they affect live runtime:

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild --keep-auth"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/stop_all.sh"
```
