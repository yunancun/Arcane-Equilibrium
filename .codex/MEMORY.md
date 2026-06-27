# Codex Memory

Last slimmed: 2026-05-16

This file is Codex operating memory for `srv/`. It should stay short: role,
boundaries, workflow, and durable lessons only. Current project state lives in
`TODO.md`; stable project context lives in `README.md`; source routing lives in
`docs/agents/context-loading.md`.

## Startup

Codex starts as `PM`.

Default read route:

1. `AGENTS.md`
2. `CLAUDE.md`
3. `.codex/MEMORY.md`
4. `README.md`
5. `docs/agents/context-loading.md`
6. `TODO.md` for code, deploy, runtime, planning, sign-off, review, or unclear
   continuity
7. `.codex/agents/PM.md`
8. `.codex/AGENT_DISPATCH_PROTOCOL.md`
9. `.codex/SUBAGENT_EXECUTION_RULES.md`

Read on demand:

- `CONTEXT.md` and relevant `docs/adr/*` for domain/architecture work
- `docs/agents/todo-maintenance.md` before editing `TODO.md`
- `AE_INVENTORY_CONSOLIDATED.md` only for deep history, RCA, or old
  design decisions

## Role

Codex is a secondary engineer, reviewer, PM/conductor, and deploy operator when
requested. The default stance is PM-first: clarify success criteria, identify
source of truth, choose local work vs dispatch, and keep boundaries visible.

Operator-facing responses should be Chinese-first. The operator needs judgment,
pushback, and clear uncertainty, not blind execution.

文檔與注釋同樣中文優先：新增或修改的設計文檔、報告、實施筆記、
代碼注釋應默認使用中文；只有在 operator 明確要求英文、文件本身已
鎖定英文格式，或必須保留精確 API / protocol wording 時才使用英文。

## Source Of Truth

- `CLAUDE.md`: shared operating rules and hard boundaries
- `.codex/MEMORY.md`: Codex-specific operating memory
- `README.md`: stable project entry, architecture map, GUI/scripts pointers
- `TODO.md`: active queue, current blockers, runtime evidence, schedule
- `docs/agents/context-loading.md`: where to load each kind of context
- `docs/agents/profit-first-autonomy-loop.md`: stable profit-first autonomous
  trading loop; current tasks still live in `TODO.md`
- `docs/agents/role-profile-memory-standard.md`: role profile / memory split
  and hygiene standard
- `docs/agents/todo-maintenance.md`: TODO lifecycle and formatting standard
- `CONTEXT.md`: domain glossary
- `docs/adr/*`: accepted architecture decisions
- reports/archive: evidence and historical detail

Do not rely on hidden chat memory as the source of truth.

## Runtime Reality

- Mac is the development machine.
- Linux `trade-core` is the active runtime machine.
- Real engine, DB, watchdog, rebuild, deploy, and live checks run on Linux,
  usually through `ssh trade-core`.
- Mac local engine not running is expected.
- New code must stay portable to future Apple Silicon deployment; avoid
  machine-specific absolute paths in production code.

Known paths:

- Mac repo: `/Users/ncyu/Projects/TradeBot/srv`
- Linux repo: `/home/ncyu/BybitOpenClaw/srv`
- remote: `git@github.com:yunancun/BybitOpenClaw.git`
- ssh alias: `trade-core`
- Runtime services are user units. Use `systemctl --user status
  openclaw-trading-api.service openclaw-watchdog.service`; system-level
  `systemctl status openclaw-trading-api.service` is the wrong namespace.
  `openclaw-engine-watchdog.service` is not the current watchdog unit.
- Position reconciler recovery invariant: empty baseline + empty current is a
  clean verification cycle, not a reseed-only cycle. Stale baselines and first
  non-empty current snapshots may reseed, but flat/flat must reach
  `evaluate_actions()` so Guardian recovery can accumulate clean cycles.

## Hard Boundaries

- Bounded Demo proof must be candidate-matched by strategy, symbol, and side.
  Aggregate Demo fills are health/execution-flow evidence only; they must not
  satisfy bounded-probe touchability, Cost Gate, or promotion proof for another
  candidate.

- Bybit is the only exchange target.
- Rust `openclaw_engine` is the trading, risk, config, and execution authority.
- Python/FastAPI is control plane / GUI / bridge / replay / agent host, not the
  trading truth layer.
- GUI-backed Rust RiskConfig is the operator-facing risk parameter source of
  truth. GUI `P1 Risk/Trade=10.0%` maps to Rust/TOML
  `per_trade_risk_pct=0.1`; GUI `0.5%` maps to `0.005`. Do not confuse GUI
  `10.0` with `10 USDT`. The active bounded-probe per-order notional default
  is fail-closed `0.0` until a reviewed GUI/Rust-resolved cap is supplied.
  Resolving a USDT cap also requires an accepted Demo fast-balance equity
  artifact (`demo_account_equity_artifact_v1` wrapping
  `/api/v1/strategy/demo/balance?fast=1` `rust_snapshot_fast` output); a naked
  `account_equity_usdt` number is not auditable cap evidence.
- Current-candidate Decision Lease / Guardian gate evidence must be generated
  from read-only runtime governance IPC evidence schemas. Generic hand-written
  `ACTIVE` lease or `PASS` guardian JSON must not clear admission gates.
  Runtime `governance.get_risk_state` may expose entry constraints under a
  nested `constraints` object; Guardian sizing must apply
  `position_size_multiplier` to the GUI/Rust-resolved cap before admission.
- Current-candidate sizing proposals must revalidate GUI cap lineage locally:
  `cap_source` must be `current_candidate_envelope.cap_resolution.resolved_cap_usdt`,
  GUI percent/fraction fields must match, local/bounded `10 USDT` authority
  flags must be false, admission/Guardian/construction GUI caps must agree, and
  GUI `position_size_max_pct` must be converted to an auditable
  `single_position_budget_usdt`.
  Effective single-order cap is the minimum of GUI per-trade cap,
  GUI max-single-position budget, and Guardian-adjusted cap.
  A reduced sizing proposal is review-only until Decision Lease, Guardian,
  Rust authority, fresh BBO, and audit/reconstructability gates pass.
  Do not use reduced-sizing Guardian evidence to clear a stale larger
  admission order shape; the rounded notional must match.
- Current-candidate no-order Decision Lease validation may only prove the IPC /
  Rust lease state-machine path. If it acquires a lease, it must immediately
  release it before writing the artifact; that released lease cannot clear the
  active Decision Lease admission gate. Runtime direct runs that touch engine
  IPC must carry `OPENCLAW_IPC_SECRET_FILE` (or equivalent secret env) when the
  engine requires `__auth`; missing transport auth is a runtime wiring blocker,
  not a trading permission workaround.
- Current-candidate active Decision Lease gate-window evidence is still no-order
  rehearsal evidence. It may acquire a short Demo lease, read governance while
  the lease is active, evaluate Decision Lease / Guardian gates, and release in
  `finally`; post-run `lease_live_count=0` / `list_leases=[]` must be recorded.
  A passed active-window Decision Lease gate does not persist into final
  admission after release, and Guardian `CAUTIOUS` remains a loss-control
  blocker even when the lease gate passes.
- Current-candidate Guardian reconciler drift diagnosis is read-only evidence.
  It may consume runtime `governance.get_status` / `list_leases` /
  `get_risk_state` snapshots and prove that GUI cap lineage is intact, but a
  `CAUTIOUS` state, drift-after-recovery tail, multiplier below 1.0, or
  `lease_live_count=0` remains a loss-control blocker. Do not force Guardian
  NORMAL, reuse a released validation lease, refresh actual-admission BBO, or
  grant order authority from a diagnosis packet.
- `engine_dead` incident detection is external-watchdog notify-only by design:
  when the engine is dead, in-process Rust C4 senders are unavailable. Do not
  route it through Rust `AllFail`/Defensive without a separately reviewed
  watchdog-side defensive design.
- External OpenClaw Gateway is communication, mobile, supervisor, and proposal
  relay only; it is not order authority or a second GUI.
- True live requires all five gates: Python `live_reserved`, Python Operator
  role auth, `OPENCLAW_ALLOW_MAINNET=1`, valid secret slot, and signed unexpired
  `authorization.json`.
- Signed live auth must be written only through the approved route, never by
  hand.
- LiveDemo is live-grade control flow against a demo endpoint.
- Paper is not active promotion evidence unless an explicit future operator
  decision reopens it.
- Cost Gate bounded Demo probe source readiness can be reviewed, but this is
  not authority: as of 2026-06-23 the near-touch Adapter, reject-path placement
  preview wiring, and `bounded_demo_probe_operator_authorization_v1` contract
  grant no Cost Gate lowering, no active probe authority, and no order
  authority unless a future bounded operator authorization object is explicitly
  supplied and accepted by runtime admission.
- Demo API operator authorization is not live/mainnet authorization. Control
  API POSTs require the existing CSRF double-submit cookie/header pair; use a
  0600 curl config for Bearer auth so tokens do not appear in argv. Demo cleanup
  close fills and unattributed fills are audit/risk-reduction evidence only,
  not bounded-probe, Cost Gate, promotion, or risk-adjusted net PnL proof.
- The operator has granted standing Demo operational authorization for the
  profit-first loop. Treat this as a requirement to build/consume structured,
  runtime-readable Demo authority envelopes with explicit loss controls and
  auditability, not as permission to bypass Rust authority, Decision Lease,
  reconstructability, live gates, or proof rules.
- Public quote transport diagnostics are evidence-quality tooling only: they
  may record sanitized failure class/reason/errno/stage, but must redact
  secrets, cookies, DSNs, local paths, tracebacks, and non-allowlisted URLs;
  they do not grant repeat exchange calls, runtime-host invocation, order/probe
  authority, Cost Gate relaxation, or promotion proof without the normal
  PM->E3->BB gate.
- Do not fake AI calls, trading activity, lineage, fills, healthchecks, or test
  results.
- Bybit API timeout / nonzero `retCode` fails closed; no hidden trading retry
  paths.
- Alpha promotion evidence is math-primary: bull data is allowed only with
  explicit regime/freshness labels; Bybit market APIs are raw state inputs, not
  prediction; news/X/Reddit agents are secondary corroboration only.
- FlashDip touchability is not promotion evidence. The nf3% shallow-retune
  cells were blocked by adversarial death stress; K6/N2/C3/nf0.5% is only a
  counterfactual survivor-first research candidate and still requires
  QC/MIT/AI-E review before any flag-gated demo parameter change.

## Operating Rules

Unless explicitly overridden:

- Think before coding; state assumptions and ask on uncertainty.
- Prefer the simplest solution that satisfies acceptance criteria.
- Make surgical changes only; do not opportunistically refactor neighbors.
- Define success criteria, then iterate to verified closure.
- Use the model for judgment calls, not deterministic routing/retry/data
  transforms.
- Token budgets are hard guidance: 4,000 per task and 30,000 per session; when
  close, summarize/reset and disclose.
- Surface conflicts; choose the newer or better-tested pattern and mark cleanup
  debt.
- Read exports, direct callers, and shared helpers before writing.
- Tests should verify intent, not just behavior.
- For delegated Rust/Cargo or Linux-runtime work, attach
  `docs/agents/sub-agent-hygiene-sop.md` to the dispatch. Sub-agents do Mac
  cargo/source verification and Linux read-only probes only; Linux cargo or
  restart requires PM/operator-owned atomic deploy handling.
- Checkpoint after significant steps.
- Match codebase conventions even when you disagree; push back explicitly if
  they are harmful.
- Fail loud when tests, steps, or evidence are skipped.

## Claude Code Hooks Mirror

Hints mirrored from the Claude Code side; canonical text lives in the pointed
files, not here.

- Claude Code sessions in this repo run an rtk PreToolUse rewrite layer
  (`.claude/settings.json` + `.claude/hooks/rtk-rewrite.sh`): Bash output in
  shared transcripts/reports may be rtk-compressed. If exit != 0 but the
  summary looks green, read the `[full output:]` tee log or rerun via
  `rtk proxy <cmd>`. Canonical: `CLAUDE.md` §八 + `tools/rtk/README.md`.
- `.claude/skills` descriptions are written as trigger conditions; check for a
  matching skill before hand-rolling a procedure.

## Dispatch Rules

Use bound repo roles, not temporary runtime nicknames.

Forced chains:

- feature / bug: `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`
- compliance / architecture: `PM -> CC -> FA -> PA -> PM`
- quant / ML / data: `PM -> QC -> MIT -> AI-E -> PM`
- security / deploy / runtime: `PM -> E3 -> BB if exchange-facing -> PM`

Every delegated task declares role, Codex type, ownership, task shape, and
expected output. If a role is skipped, state why. E2/E4 are not skipped for
implementation work without explicit risk acceptance.

## Validation

- For sign-off, first decide whether replay or counterfactual replay can verify
  the claim. Use runtime/DB/WS/healthcheck evidence when replay cannot prove it.
- V### migrations with PG reflection, transaction control, or schema assumptions
  need Linux PG empirical dry-run.
- GUI JS changes require `node --check` or stronger verification.
- Edge analysis uses demo data, not paper, unless a task is explicitly about
  paper diagnostics.
- `live_demo` remains live-grade and does not relax controls.
- Funding-cap for funding-harvest / funding-threshold strategies is the
  exchange `instruments-info.upperFundingRate` (SSOT), not the max of a
  funding/history sample window (which always sits inside one regime and
  mis-estimates the cap). 2026-05-31 lesson: a funding_short_v2 audit read the
  +0.0001 IR-baseline floor of a low-premium window as a +10.9% APR structural
  cap and wrongly called the strategy permanently DOA; Bybit real caps are
  +547~2190% APR, so funding_short_v2 is regime-dormant (fires under bull
  premium), not structurally infeasible — see
  `docs/audits/2026-05-31--p0_edge_cost_wall_investigation.md`.

## TODO Rules

Before editing `TODO.md`, read `docs/agents/todo-maintenance.md`.

Keep TODO focused on active queue and current evidence:

- active blockers
- next action
- owner/chain
- acceptance
- timestamped runtime evidence
- report/archive links

Do not paste long reports or stable architecture into TODO.

## Git And Sync

- There may be unrelated WIP. Never revert changes you did not make.
- For meta-doc work in a dirty tree, use narrow staging / `git commit --only`
  when committing.
- Every commit needs subject plus body. Use `[skip ci]` for non-CI-relevant docs
  or governance updates when appropriate.
- Operator shorthand `三端同步` means: push the intended commit to `main`, then
  pull `main` on Linux `trade-core` (`/home/ncyu/BybitOpenClaw/srv`).
- Unless the operator explicitly asks for CI, `push main` means use a
  non-CI-triggering commit subject/body (`[skip ci]`) where GitHub honors it.
- Do not accumulate independent green batches in one dirty tree.
- Every push report includes branch, commit SHA, and short description.
- Do not use destructive git commands unless explicitly requested.

## External Tools

- Git in `srv/` is source of truth.
- GitHub Issues is active.
- Linear is historical/passive unless reopened.
- Notion is frozen; Drive is passive; Coupler, MotherDuck, and Slack are
  declined unless reopened.
- Do not publish secrets or sensitive runtime state externally.

## Maintenance

- Keep this file near operating-memory size; target around 300 lines, not a hard
  cap.
- Move active state to `TODO.md`.
- Move stable overview to `README.md`.
- Move long evidence to reports/archive.
- Update `docs/agents/context-loading.md` when source routing changes.

## 2026-06-25 AVAX Touchability Bootstrap Source Patch

- `P0-BOUNDED-PROBE-AVAX-CANDIDATE-TOUCHABILITY-BOOTSTRAP-SOURCE-ONLY` is `DONE`: zero candidate-matched AVAX orders can now produce `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED` only as a review-only/no-authority/no-proof first-attempt near-touch-or-skip contract.
- Touchability now requires candidate identity alignment before reviewability; placement maps the bootstrap to `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW` with `active=false`, separate authorization required, fresh-BBO/skip constraints, and `first_attempt_bootstrap_is_proof=false`.
- Recursive authority contamination scanning was broadened to reject runtime order authority, config/env/runtime mutations, order modify/cancel aliases, review-granted runtime authority, Cost Gate mutation, authority enum strings/object payloads, promotion/proof, writer/adapter/service mutation vocabulary.
- Verification: focused touchability+placement `30 passed`; adjacent bounded-probe suite `106 passed`; changed-helper py_compile PASS; `git diff --check` PASS. Boundary unchanged: no Bybit call/order/cancel/modify, no PG write, no `_latest` overwrite, no runtime/env/service/crontab mutation, no Cost Gate lowering, no Rust writer/adapter enablement, no probe/order/live authority, no promotion proof.
- Next blocker: `P0-BOUNDED-PROBE-AVAX-AUTHORITY-PATH-READINESS-SOURCE-ONLY`.

## 2026-06-26 AVAX Authority Path Source Readiness

- `P0-BOUNDED-PROBE-AVAX-AUTHORITY-PATH-READINESS-SOURCE-ONLY` is `DONE`: source scan now reports `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW` for the AVAX first-attempt placement input, while runtime/order authority answers remain false.
- Fixed a scanner false negative for `order_intent_limit_tif_surface` by structurally checking `OrderIntent.limit_price`, `OrderIntent.time_in_force`, and `TimeInForce.PostOnly`; added regression so unrelated `PostOnly` code cannot satisfy the seam.
- Verification: focused authority readiness `36 passed`; adjacent bounded-probe `107 passed`; E4 bounded-probe family `215 passed` twice; py_compile and diff-check PASS; PA/E2/E4 PASS. Boundary unchanged: no Bybit call/order/cancel/modify, no PG write, no `_latest` overwrite, no runtime/env/service/crontab mutation, no Cost Gate lowering, no Rust writer/adapter enablement, no probe/order/live authority, no promotion proof.
- Next blocker: `P0-BOUNDED-PROBE-AVAX-RUNTIME-ADMISSION-E3-BB-REVIEW-DEMO-ONLY`.

## 2026-06-26 AVAX Runtime Admission E3/BB Review + TODO Hygiene

- `P0-BOUNDED-PROBE-AVAX-RUNTIME-ADMISSION-E3-BB-REVIEW-DEMO-ONLY` is `DONE_WITH_CONCERNS`: E3 and BB passed only opening the next separate runtime source-sync/post-restart reconciliation/adapter-enablement review checkpoint.
- Runtime blockers remain explicit: `runtime_source_sync_not_verified`, `post_restart_pending_order_reconciliation_not_proven`, and `runtime_adapter_enablement_not_performed_source_only_packet`; review approval is not runtime mutation, adapter enablement, probe/order authority, or Bybit order permission.
- `TODO.md` v527 was compressed back to active dispatch format: completed AVAX ladder rows are a compact no-repeat marker, `P0-PROFIT-DEMO-LEARNING-LOOP` is posture rather than an active row, and the next blocker is WAITING per operator pause request.

## 2026-06-26 AVAX Runtime Source + Cron Expected-Head Sync

- PM synced Linux `/home/ncyu/BybitOpenClaw/srv` cleanly from `e0c2a0e1` to `d2cd70d0` with no restart/rebuild, after E3 allowed ff-only source checkout sync and BB failed only the adapter/order path.
- E3 approved exactly 11 crontab expected-head SHA replacements; post-check line count stayed `70`, old SHA count `0`, new `d2cd70d0` count `11`, and adapter/mainnet/probe-record forbidden counts stayed `0`.
- Engine PID `2432529` and API MainPID `2218842` remained unchanged. Adapter/order path remains blocked by passive healthcheck FAIL, especially demo resting exposure `working_n=6` / about `691 USDT`.

## 2026-06-24 Runtime Adapter No-Order BTC Checkpoint

- `P0-BOUNDED-PROBE-RUNTIME-ADAPTER-ENABLEMENT-DEMO-ONLY-E3-BB-REVIEW` is `DONE_WITH_CONCERNS`: E3/BB found no safe current production flag for actual demo order submission; Rust writer still hard-codes `adapter_enabled=false`.
- PM generated only timestamped runtime artifacts. Temporary non-ledger plan copy + `runtime_adapter.py --adapter-enabled` reached `ADMIT_DEMO_LEARNING_PROBE`, but no-order placement construction failed closed: BTCUSDT local BBO age `1652ms` > 1000ms gate, and `qty_step=0.001` at limit `60040.2` makes min positive notional `60.0402 USDT`, above the historical bounded-local 10 USDT/order cap at that checkpoint.
- Canonical plan sha `624a62d5...` and ledger sha `84624226...` unchanged. No Bybit call/order, no PG write, no ledger append, no canonical plan mutation, no runtime/env/cron/service mutation, no writer, no Cost Gate lowering, no live/mainnet, no promotion proof. Next blocker: `P0-BOUNDED-PROBE-CAP-AND-ORDER-CONSTRUCTION-REPAIR-DEMO-ONLY-SOURCE-PROPOSAL`.

## 2026-06-24 Bounded Probe Order-Construction Repair

- `P0-BOUNDED-PROBE-CAP-AND-ORDER-CONSTRUCTION-REPAIR-DEMO-ONLY-SOURCE-PROPOSAL` is `DONE_WITH_CONCERNS`: BTC remained not executable under the historical bounded-local 10 USDT/order cap, but the source-only repair packet was reviewed and reconstructable.
- Added `bounded_probe_order_construction_repair.py` and tests. It emits `bounded_demo_probe_order_construction_repair_v1`, fails closed on authority/proof/mutation contamination including non-boolean truthy values, non-empty placement blockers, stale/schema-mismatched candidate universe artifacts, CLI bare-array universe bypass, and non-Trading instruments. CLI records input path/sha.
- Runtime read-only PG screen found 9 false-negative candidates fitting the existing cap; top is `grid_trading|AVAXUSDT|Sell`, rank 1, avg net `73.5511bps`, 48/48 net-positive 60m outcomes, min executable notional `5.0 USDT`.
- Latest repair artifact `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_order_construction_repair_latest.json` sha `5a5940cf...`, status `ORDER_CONSTRUCTION_REPAIR_REQUIRED`: BTC cap repair remains review-only, lower-price reroute is available. PA/E1 PASS; E2/E4 PASS; focused helper `11 passed`, adjacent bounded-probe suite `42 passed`, py_compile and diff-check passed.
- Boundary unchanged: no Bybit order/cancel/modify, no PG write, no canonical plan/ledger mutation, no runtime/env/crontab/service mutation, no Rust writer, no Cost Gate lowering, no live/mainnet, no promotion proof. Next blocker: `P0-BOUNDED-PROBE-LOWER-PRICE-CANDIDATE-REROUTE-REVIEW-DEMO-ONLY`.

## 2026-06-24 Bounded Probe Lower-Price Reroute Review

- `P0-BOUNDED-PROBE-LOWER-PRICE-CANDIDATE-REROUTE-REVIEW-DEMO-ONLY` is `DONE`: exactly one cap-feasible lower-price candidate is selected for the next no-order construction review, `grid_trading|AVAXUSDT|Sell`.
- Added `bounded_probe_lower_price_reroute_review.py` and tests. It emits `bounded_demo_probe_lower_price_reroute_review_v1`, requires fresh/schema-valid/aligned repair + false-negative/preflight/placement/auth-readiness/touchability artifacts, exact integer horizon, complete candidate identity, `instrument_status=Trading`, explicit side-cell when multiple candidates fit, recursive no-authority/proof/mutation preservation, and input artifact hashes.
- Runtime latest `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_lower_price_reroute_review_latest.json` sha `fcd7f925...`, status `LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW`, blocking gates `0`, rank `1`, avg net `73.5511bps`, 48/48 net-positive outcomes, min executable notional `5.0 USDT`.
- PA/E1 PASS; E2/E4 PASS after fixes for horizon rounding, identity completeness, non-Trading feasibility, and row-order auto-selection. Focused helper `11 passed`, adjacent bounded-probe suite `70 passed`, py_compile and diff-check passed.
- Boundary unchanged: no Bybit order/cancel/modify, no PG write, no canonical plan/ledger mutation, no runtime/env/crontab/service mutation, no Rust writer, no Cost Gate lowering, no live/mainnet, no promotion proof. Next blocker: `P0-BOUNDED-PROBE-REROUTE-CANDIDATE-CONSTRUCTION-PREFLIGHT-DEMO-ONLY`.

## 2026-06-24 Bounded Probe Candidate Construction Preview

- `P0-BOUNDED-PROBE-REROUTE-CANDIDATE-CONSTRUCTION-PREFLIGHT-DEMO-ONLY` is `DONE_WITH_CONCERNS`: AVAXUSDT Sell was constructible under raw instrument filters and the historical bounded-local 10 USDT/order cap, but demo order admission remained blocked by BBO freshness.
- Added `bounded_probe_candidate_construction_preview.py` and tests. It emits `bounded_demo_probe_candidate_construction_preview_v1`, consumes a ready lower-price reroute review plus a read-only PG market snapshot, uses raw ticker/instrument fields as construction SSOT, requires read-only source, exact candidate/ticker/instrument symbol match, raw/derived consistency, effective BBO age from raw `ticker.ts`, `instrument.status=Trading`, passive near-touch placement, cap/min-notional feasibility, and no-authority/proof/mutation preservation.
- Runtime latest `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_candidate_construction_preview_avax_sell_latest.json` sha `3d652a3a5f28433adf33944e1dcf63d6a7a05ab176f161efaba3569611237600`, status `CANDIDATE_CONSTRUCTION_BBO_STALE`, only blocking gate `bbo_freshness`. Construction math: limit `6.045`, qty `1.6`, notional `9.672 USDT`, min positive qty notional `0.6045 USDT`, cap `10.0 USDT`; effective BBO age `1229558.906ms` > `1000ms`.
- PA/E1 PASS and E2/E4 PASS after fixes for nested market identity, effective BBO age, authority danger keys, stale-BBO precedence, raw/derived contradictions, and malformed derived numeric fields. Focused helper `15 passed`, adjacent bounded-probe suite `85 passed`, py_compile and diff-check passed.
- Boundary unchanged: no Bybit order/cancel/modify, no PG write, no canonical plan/ledger mutation, no runtime/env/crontab/service mutation, no Rust writer, no Cost Gate lowering, no live/mainnet, no promotion proof. Next blocker: `P0-BOUNDED-PROBE-REROUTE-FRESH-BBO-CONSTRUCTION-REFRESH-DEMO-ONLY`.

## 2026-06-24 Bounded Probe BBO Freshness Refresh / Diagnosis / Proposal

- `P0-BOUNDED-PROBE-REROUTE-FRESH-BBO-CONSTRUCTION-REFRESH-DEMO-ONLY` is `DONE_WITH_CONCERNS`: fresh read-only AVAX market snapshot and preview artifacts were produced, but BBO freshness still failed.
- Fresh-BBO market snapshot `/tmp/openclaw/cost_gate_learning_lane/candidate_market_snapshot_avax_sell_fresh_bbo_latest.json` sha `0212b7452ad383b33b856d7ebe360d5ebacbca5be78af92f97ef5fd77d8f7e8d`; fresh-BBO preview `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_candidate_construction_preview_avax_sell_fresh_bbo_latest.json` sha `cf5acebf01ff4a4fe32cdbf9f3ca8fd396cd09599fa47f11fa4868f855b51cf6`, status `CANDIDATE_CONSTRUCTION_BBO_STALE`, effective BBO age `4935.735ms`, limit `6.064`, qty `1.6`, notional `9.7024 USDT`.
- `P0-BOUNDED-PROBE-BBO-FRESHNESS-DIAGNOSIS-DEMO-ONLY` is `DONE_WITH_CONCERNS`: read-only PG diagnosis `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_diagnosis_avax_sell_latest.json` sha `9b32d64fc1b6e3076fd32835c8b947ae31a038235008b0a7683ea5f5d4706e9e`, status `BBO_FRESHNESS_DIAGNOSIS_TRANSIENT_STALE`; latest AVAX lag `2088.428ms`, 15m gap p50 `900ms`, sampled latest symbols `0 <=1000ms` and `164 >1000ms`.
- `P0-BOUNDED-PROBE-BBO-FRESHNESS-REPAIR-PROPOSAL-DEMO-ONLY` is `DONE`: proposal `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_repair_proposal_avax_sell_latest.json` sha `6a6149719db6f1454eddb1379cea2222b564984187e31080abcd5b6aa7487ca8`, status `BBO_FRESHNESS_REPAIR_PROPOSAL_READY_NO_AUTHORITY`. Rank-1 next path is source-only co-located read-only PG snapshot+preview runner; direct public quote capture is rank-2 and requires PM->E3->BB before any exchange-facing call; freshness-gate change is not recommended.
- Boundary unchanged: read-only PG + `/tmp/openclaw` artifacts + docs only; no Bybit call/order/cancel/modify, no PG write, no canonical plan/ledger mutation, no runtime/env/crontab/service mutation, no Rust writer, no Cost Gate lowering, no live/mainnet, no promotion proof. Next blocker: `P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-SOURCE-DESIGN-DEMO-ONLY`.

## 2026-06-24 BBO Freshness Co-Located Runner Source Design

- `P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-SOURCE-DESIGN-DEMO-ONLY` is `DONE_WITH_CONCERNS`: source-only helper is implemented and reviewed, but runtime `--pg-readonly` execution still requires a separate PM->E3 runtime review/sync checkpoint.
- Added `bbo_freshness_colocated_runner.py` and tests. It emits `bounded_probe_bbo_freshness_colocated_runner_v1`, consumes a ready no-authority repair proposal, the AVAX reroute review, and either supplied market snapshot or explicit `--pg-readonly`, then reuses `build_candidate_construction_preview`. Supplied-market mode cannot close the co-located PG gate; `COLOCATED_RUNNER_READY_NO_ORDER` requires `pg_readonly_mode=True`.
- CLI uses required mutually exclusive `--market-snapshot-json` vs `--pg-readonly`; PG mode requires `--market-snapshot-output` for reconstructability. Both runner and construction preview now reject enum authority fields and explicit mutation aliases including `order_cancel_modify_performed` and `runtime_env_mutation_performed`.
- Runtime supplied-mode smoke `/tmp/openclaw/cost_gate_learning_lane/co_located_bbo_snapshot_preview_runner_design_latest.json` sha `f520ce1eb6862236eee83862e8a0f30cd46f077232fa2b26378c2ebc31d065a5`, status `COLOCATED_RUNNER_BBO_STALE_NO_ORDER`, mode `supplied_market_snapshot`, next blocker `P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-RUNTIME-REVIEW-DEMO-ONLY`.
- PA/E1 PASS; E2/E4 PASS after fixes for authority aliases, supplied-mode gate closure, CLI ambiguity, and PG output reconstructability. Verification：focused runner+preview `30 passed`, adjacent bounded-probe suite `100 passed`, py_compile and diff-check passed.
- Boundary unchanged: source/test/docs + supplied-mode `/tmp/openclaw` smoke only; no runtime source sync, no live runtime PG read via new helper, no Bybit call/order/cancel/modify, no PG write, no canonical plan/ledger mutation, no runtime/env/crontab/service mutation, no Rust writer, no Cost Gate lowering, no live/mainnet, no promotion proof. Next blocker: `P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-RUNTIME-REVIEW-DEMO-ONLY`.

## 2026-06-24 BBO Freshness Runtime Co-Located Runner Review

- `P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-RUNTIME-REVIEW-DEMO-ONLY` is `DONE_WITH_CONCERNS`: E3 approved a bounded PM-only runtime path; runtime fast-forwarded `bdc1e156 -> 8e7bc890`, focused runner+preview tests passed, and the helper ran on trade-core in explicit `--pg-readonly` mode.
- Runtime runner `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_colocated_runner_avax_sell_pg_readonly_20260624T185436Z.json` sha `8a204584715c13f53852a0107de263893e1ba55d804f5c73873fac2889645568` is `COLOCATED_RUNNER_BBO_STALE_NO_ORDER`; effective BBO age `2476.128ms` still exceeds the `1000ms` gate, so no order admission follows.
- Boundary unchanged: ff-only source sync + read-only PG SELECT + `/tmp/openclaw` artifacts + docs/index only; no Bybit call/order/cancel/modify, no PG write, no canonical plan/ledger mutation, no service/env/crontab mutation, no Rust writer, no Cost Gate/freshness-gate lowering, no live/mainnet, no promotion proof. Next blocker: `P0-BOUNDED-PROBE-BBO-FRESHNESS-PUBLIC-QUOTE-CAPTURE-E3-BB-REVIEW-DEMO-ONLY`.

## 2026-06-24 BBO Freshness Public Quote Capture

- `P0-BOUNDED-PROBE-BBO-FRESHNESS-PUBLIC-QUOTE-CAPTURE-E3-BB-REVIEW-DEMO-ONLY` is `DONE`: E3/BB approved a bounded public-market-data-only envelope for `/v5/market/time`, `/v5/market/tickers?category=linear&symbol=AVAXUSDT`, and optional `/v5/market/instruments-info?category=linear&symbol=AVAXUSDT`; no private/auth/order path, no PG/runtime mutation, and no order/probe/live authority.
- Source commit `b66715be` adds `bbo_freshness_public_quote_capture.py` and focused tests. The helper emits `bounded_probe_bbo_freshness_public_quote_capture_v1`, records request envelope/timing/hash/provenance fields, uses conservative server-time/local-duration freshness, and stays separate from PG market snapshots. PG construction preview still rejects `bybit_call_performed=true` and cannot consume the public quote artifact.
- PA/E1, E2, and E4 PASS. Verification: public quote focused `11 passed`, public quote + co-located runner + construction preview `41 passed`, py_compile, diff-check. Commit `b66715be` pushed to `origin/main`; runtime trade-core was not synced.
- `P0-BOUNDED-PROBE-PUBLIC-QUOTE-ONE-SHOT-RUNTIME-REVIEW-DEMO-ONLY` is `DONE_WITH_CONCERNS`: PM ran exactly one reviewed public quote capture from local source. Artifact `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_public_quote_capture_avax_sell_20260624T192038Z.json` sha `6857deffd44a1e0fbaa4b370b5c8f4222c76886584a4c691750d52653cb2ce65`, markdown sha `4a0d21334d273d11579c6ca32ad7bd45194d05ed01bc073cd67e409343439fcc`.
- One-shot result is `PUBLIC_QUOTE_CAPTURE_SOURCE_FAILURE_NO_ORDER`: all three public GETs failed closed with `transport_error:URLError`, no HTTP status/retCode/raw response hash, no bid/ask, no effective BBO age. Answers preserve `bybit_public_market_data_call_performed=true`, `bybit_private_call_performed=false`, `auth_headers_present=false`, `pg_write_performed=false`, `order_submission_performed=false`, Cost Gate `NONE`, and no probe/order/live/promotion authority.
- Boundary unchanged: source/test/docs + one public-market-data artifact attempt only; no Bybit private/order/cancel/modify, no PG write/schema/query, no canonical plan/ledger mutation, no service/env/crontab/runtime mutation, no Rust writer, no Cost Gate/freshness-gate lowering, no live/mainnet, no promotion proof. Next blocker: `P0-BOUNDED-PROBE-PUBLIC-QUOTE-RUNTIME-ROUTE-E3-BB-REVIEW-DEMO-ONLY`.

## 2026-06-27 GUI Percent Cap Semantics Guard

- Operator correction is binding: all risk parameters follow GUI-backed Rust RiskConfig. GUI `P1 Risk/Trade=10.0%` is Rust `per_trade_risk_pct=0.1`, not `10 USDT`; GUI `Max Single Position=25%` is `position_size_max_pct=25.0`.
- Current accepted Demo equity is `9552.43426257`; GUI per-trade cap is `955.24342626 USDT`; GUI max-single-position budget is `2388.10856564 USDT`. Effective single-order cap remains `min(gui_per_trade_cap_usdt, gui_max_single_position_budget_usdt, Guardian-adjusted cap)`, currently `668.67039838 USDT` under Guardian multiplier `0.7`.
- Source/runtime `e4fb5c7f4087d55ed1a8330174234bdb3f00aa3e` adds machine-checkable fields to `current_cap_staircase_risk_worksheet.py` (`risk_source_of_truth`, `gui_percent_semantics`, and false local-10-USDT authority flags) plus a regression proving legacy `source_construction_cap_usdt=10.0` resolves to GUI cap `955.24342626` under current Demo equity.
- Runtime `trade-core` is synced to `e4fb5c7f`; crontab expected-head pins are `e4fb5c7f=11`, old `efa92a88=0`, line count `70`, no service restart. Runtime sync manifest `/tmp/openclaw/runtime_source_sync_gui_percent_cap_guard_20260627T0723Z/runtime_sync_manifest.json` sha `a6af92acbc6af17e365b3752a6f1abd1ce472332a041812d5b11d0b34b3224e7`.
- Session state `/tmp/openclaw/session_loop_state_20260627T0728Z_gui_percent_cap_semantics_guard.json` sha `5b1612164c48afa37a31d3d133335b296ebb053935ea511612e285e08e623225` is `DONE_WITH_CONCERNS`: cap semantics and runtime source are guarded, but runtime admission remains blocked by Guardian `CAUTIOUS` / reconciler drift and requires a fresh active Decision Lease plus actual-admission BBO later.
