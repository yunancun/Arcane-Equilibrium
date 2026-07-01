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

- Bybit remains the only active live execution exchange target. ADR-approved
  non-Bybit exceptions are explicitly scoped: Binance market-data-only per
  ADR-0033/0040, and IBKR `stock_etf_cash` read-only/paper/shadow research per
  ADR-0048 + AMD-2026-06-29-01. IBKR live/tiny-live remains denied.
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
- Legacy crypto Paper is not active promotion evidence unless an explicit
  future operator decision reopens it. The ADR-0048 IBKR `stock_etf_cash`
  paper/shadow lane is separate research evidence and cannot auto-promote to
  tiny-live, live, or durable-alpha proof.
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

## 2026-06-27 Guardian NORMAL Current-Cap Sizing

- Guardian recovered to `NORMAL` with position-size multiplier `1.0`; read-only snapshot `/tmp/openclaw/runtime_guardian_normal_snapshot_20260627T074300Z_contract/runtime_governance_snapshot.json` sha `034132e387c44e5926989a83f41bf122f72668c500548a0ab774e5ffcb289943` has `lease_live_count=0` and `list_leases=[]`.
- Source/runtime `9040c75e92c7b363087c4599ad42059450af9112` changes `current_candidate_guardian_adjusted_sizing_proposal.py` so Guardian-pass/no-active-lease gate evidence can emit a current-cap READY_NO_ORDER proposal without forcing stale `0.7` reduction. It uses `min(original_qty, max_qty_under_effective_cap)` and only requires reduction when original notional exceeds effective cap.
- Runtime sync manifest `/tmp/openclaw/runtime_source_sync_guardian_normal_sizing_20260627T074057Z/runtime_sync_manifest.json` sha `3d72b8ea7281aa9f0746b02399de5f91482b59ede0ec2eb60db16c8688725c99`; runtime crontab pins `9040c75e=11`, old `e4fb5c7f=0`, no restart/rebuild/order. Local and runtime focused related suites passed `36`; py_compile and diff-check passed.
- Runtime current-cap sizing `/tmp/openclaw/runtime_guardian_normal_current_cap_evidence_20260627T074329Z/current_cap_sizing/current_candidate_guardian_adjusted_sizing_proposal.json` sha `59d8e8b75d810d8c5f78a537ca4c36c56c39a9556ea3bb0e97b108e5b2211229` is `READY_NO_ORDER`: GUI cap `955.24342626 USDT`, max-single-position budget `2388.10856564 USDT`, Guardian-adjusted cap `955.24342626 USDT`, proposed `145.7 AVAX / 954.6264 USDT`, and `requires_fresh_bbo_before_admission=true`.
- Final no-order gate `/tmp/openclaw/runtime_guardian_normal_current_cap_evidence_20260627T074329Z/gate_with_current_cap_sizing/current_candidate_decision_lease_guardian_gate_evidence.json` sha `b9e730a3bc1ebc79c632eed7b2e5ec4b5669d2b775ca5e655651a8e9ed6a586b` is `BLOCKED_BY_LOSS_CONTROL` only on `decision_lease_valid`; Guardian gate passes. Session state `/tmp/openclaw/session_loop_state_20260627T0745Z_guardian_normal_current_cap_sizing/session_loop_state.json` sha `e6e5bbf668574b1f5f593c3f2d2d267feeee122d16f8e3da364cf179ccacddb8` is `DONE_WITH_CONCERNS`.
- Do not treat the copied construction input as fresh actual-admission BBO. Next no-order work must recompute fresh current-candidate envelope/BBO, then acquire a fresh bounded Demo Decision Lease and rerun gate evidence inside that final window. No execution/profit proof exists.

## 2026-06-27 Final-Window Guardian CAUTIOUS Blocker

- Operator risk correction remains binding: GUI/Rust RiskConfig is source of truth. Fresh equity `/tmp/openclaw/current_candidate_final_window_fresh_equity_20260627T075301Z/demo_account_equity_artifact.json` sha `72e3cd04b33105ce4df4c216c777d25595f2cfe8751c44eafd1cc4797c65991d` is `9551.58809495`, so GUI P1 `10.0%` resolves to `955.1588095 USDT`; GUI max-single-position `25%` resolves to `2387.89702374 USDT`. Local `10 USDT` cap authority is false.
- Source/runtime `9d9c575b2bfbe0cfab24ec001b866c90c016059c` adds `runtime_governance_ipc_readonly_snapshot.py`; local/runtime focused snapshot/gate/active-window/sizing tests passed `19`, py_compile and diff-check passed. Runtime sync manifest `/tmp/openclaw/runtime_source_sync_readonly_snapshot_helper_20260627T080352Z/runtime_sync_manifest.json` sha `22b69cd574c2f1b54a64b7746e805cf7483f0cd926bd3f72c00d01758e99a482`; crontab pins are `9d9c575b=5`, old `9040c75e=0`, no service/binary restart.
- Final-window no-order chain is fresh and AVAX Sell aligned: envelope sha `bda743baa3aa40aefdc80b13a90f35bbe14f1a9da78fd5909b140f49a6ea29e9`, public quote/construction sha `8606a213ad3d2e3a78d2488e1d411189c18e76659699dd1a2676c041660a9804` with BBO age `478.308ms`, handoff sha `d75e7f88eff848f9346ab5790003dcd5a81174ac3c2349c4754fedc9c1096030`, and admission review sha `5ccd9a239bf9f095dc00ec1c613a01966e333de0eff5830b93bdf02388bb4170`.
- Fresh read-only governance snapshot `/tmp/openclaw/current_candidate_final_window_governance_snapshot_20260627T080216Z/runtime_governance_snapshot.json` sha `4bf3d10b17dd865953398936e6e1048d5013a1ff33d220457c868df394e1d669` shows Guardian `CAUTIOUS`, multiplier `0.7`, `lease_live_count=0`, and `reconciler_drift` after recovery. It only succeeds when runtime IPC is invoked with `OPENCLAW_IPC_SECRET_FILE`; the no-secret run failed closed.
- Reduced sizing `/tmp/openclaw/current_candidate_final_window_guardian_adjusted_sizing_20260627T080248Z/current_candidate_guardian_adjusted_sizing_proposal.json` sha `33e0e97e848f1827e5da535982429a8279f34f5291cbb1c9c08ca9fd949ba412` proposes `101.8 AVAX / 668.1134 USDT` under Guardian-adjusted cap `668.61116665 USDT`, but final gate `/tmp/openclaw/current_candidate_final_window_gate_with_sizing_20260627T080300Z/current_candidate_decision_lease_guardian_gate_evidence.json` sha `c8990418f35621918071f5d0d1b61bd861fd909ad2f0a1bb08e9e5d7d01aa8bd` remains `BLOCKED_BY_LOSS_CONTROL` on `decision_lease_valid` and `guardian_risk_gate_valid` because Guardian is not normal.
- Diagnosis `/tmp/openclaw/current_candidate_final_window_guardian_reconciler_diagnosis_20260627T080325Z/current_candidate_guardian_reconciler_drift_diagnosis.json` sha `edaa2fd9c0d0910d99eab8f014640a3602fdbd12e8630b28f9573b5f8ebb424f` records blockers: active lease missing, Guardian `CAUTIOUS`, multiplier below one, active reconciler drift tail, and drift after recovery. Session state `/tmp/openclaw/session_loop_state_20260627T0804Z_final_window_guardian_cautious_blocked/session_loop_state.json` sha `a0440bfbac73e2da703c042c9326f056b593d8929dfcecfa5426d6358e64a84f` is `BLOCKED_BY_LOSS_CONTROL`.
- Do not acquire active Decision Lease, refresh actual-admission BBO, enable adapter/writer, or execute while Guardian gate is invalid. Next work is a fresh read-only governance snapshot showing Guardian `NORMAL` and no active drift tail; only then reacquire a fresh bounded Demo lease and rerun gate evidence before actual-admission BBO.

## 2026-06-27 Bounded Demo Probe Capture Normalization

- Source/runtime `5aa5fff0b90239d2fee5ca36fff377f833b0fd3c` fixes demo-learning reject normalization so runtime `cost_gate(JS-demo): estimated=-...bps < 0` rejects are recognized by the hot-path adapter. Local/runtime `demo_learning_lane` and `demo_learning_lane_hot_path` tests passed; release rebuild/restart verified engine PID `4164391` and binary sha `fef422953a221c1d81bf434864ba45968454530238455d90db52bd1eb29ceae0`.
- Runtime ledger now increments under the Demo-only soak: line count moved `99196 -> 99235`, non-selected rows emit `SIDE_CELL_NOT_SELECTED`, and selected `grid_trading|AVAXUSDT|Sell` rows appear. Selected rows remain `ADAPTER_DISABLED` / `runtime_adapter_enable_flag_is_false` because `active_order_request` is absent; next blocker is runner-owned final-window Decision Lease acquisition and active order request construction. Do not use fake lease ids, bypass Governance, lower Cost Gate, or claim order/fill/profit proof.

## 2026-06-27 Active Decision Lease Gate Window Guardian NORMAL

- Operator risk correction remains binding: GUI/Rust RiskConfig is source of truth. GUI `P1 Risk/Trade=10.0%` is Rust `per_trade_risk_pct=0.1`, not `10 USDT`; GUI `Max Single Position=25%` resolves from equity as an exposure budget.
- Fresh governance snapshot `/tmp/openclaw/current_candidate_followup_governance_snapshot_20260627T081842Z/runtime_governance_snapshot.json` sha `7ac2439134f73e406fe261a1a2a6c250078c2924c6b85cb4b4d98ddcc6aa8139` shows Guardian `NORMAL`, multiplier `1.0`, `lease_live_count=0`, and latest tail `reconciler_recovery`.
- Fresh normal sizing `/tmp/openclaw/current_candidate_followup_guardian_normal_sizing_20260627T081842Z/current_candidate_guardian_adjusted_sizing_proposal.json` sha `3011fb95827d6c038b5230a58e56977e76ae0b4815fb21b6de0cac5d0861a06b` uses GUI cap `955.1588095 USDT`, max-single-position budget `2387.89702374 USDT`, and proposes `145.5 AVAX / 954.9165 USDT`. Gate with sizing sha `07ba7560ec0d8831a45fd081177cd7dfafd79608a72b05bf725ae61bc249d174` is blocked only on missing Decision Lease.
- Active bounded Demo lease window `/tmp/openclaw/current_candidate_followup_active_lease_gate_window_20260627T081842Z/current_candidate_active_decision_lease_gate_window.json` sha `c562665f41db188d1da3c58b71684dc5aaa45310c61ba7ca95ef6746e4061188` is `DONE_NO_ORDER`; nested active gate `/tmp/openclaw/current_candidate_followup_active_lease_gate_window_20260627T081842Z/active_current_candidate_decision_lease_guardian_gate_evidence.json` sha `a67e25c3f61d8bc2ce7a23ed8357a35328aeac66ddaddd5c8570550b34609d8e` is `READY_NO_ORDER`. Post-window snapshot `/tmp/openclaw/current_candidate_followup_post_active_governance_snapshot_20260627T081843Z/runtime_governance_snapshot.json` sha `71175768a9d400a59ccc680434b5ce92421fcfee3044dc519a276224b1bb5749` confirms `lease_live_count=0`.
- Session state `/tmp/openclaw/session_loop_state_20260627T0819Z_active_decision_lease_gate_window_done/session_loop_state.json` sha `f50cfafdd776bb28b212034fdafe5e7dd6ce1d0f3d6500c2d17e2723e201df26` is `DONE_WITH_CONCERNS`. This proves only active-window gate validity and leaves no persistent runtime admission/order authority. Next no-order blocker: fresh actual-admission BBO/instrument refresh inside a fresh current-candidate Demo Decision Lease window.

## 2026-06-30 IBKR Stock/ETF Risk Policy Contract

- Source checkpoint adds `stock_etf_risk_policy_v1` for ADR-0048 Stock/ETF cash paper/shadow risk policy. It validates the dormant `settings/risk_control_rules/risk_config_stock_etf_paper.toml`, finite ordered notional caps, bounded open-order/open-position limits, cash-only no-margin/no-short/no-options/no-CFD/no-transfer/no-live controls, required stock/ETF/cash universe and denied crypto/CFD kinds, cost-model prerequisites, Rust authority/session/Decision Lease/Guardian/idempotency/reconciliation gates, Bybit-live unchanged proof, and no IBKR contact/connector/secret serialization.
- `stock_etf_risk_policy_v1` is now listed in the Phase 0 manifest contract list, required by lane-scoped paper IPC gates, and required by broker capability paper write plus shadow/scorecard rows. Added blocked template `settings/broker/stock_etf_risk_policy.template.toml` and acceptance tests.
- Verification passed: focused linked openclaw_types tests `28 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `163` integration/acceptance + `0` doc-tests; targeted touched-file `rustfmt --check` passed; `git diff --check` passed.
- Boundary unchanged: no IBKR contact/healthcheck, no secret read/create/serialization, no connector runtime, no paper order, no evidence clock, no scorecard writer, no DB apply, no GUI lane authority, no tiny-live/live, and no Bybit live execution behavior change. First IBKR contact remains blocked until real secret/topology evidence and immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.

## 2026-06-30 IBKR Stock/ETF Reference Data Sources Contract

- Source checkpoint adds `stock_etf_reference_data_sources_v1` for ADR-0048 corporate-action, FX, fee, tax/FTT, and withholding-treatment source-as-of records. It validates source names, as-of timestamps, required hashes, USD v1 currency treatment, evidence-clock freeze, Bybit-live unchanged proof, and no IBKR contact/connector/secret/tiny-live/live authority.
- `stock_etf_reference_data_sources_v1` is now listed in the Phase 0 manifest contract list, required by Phase 3 frozen inputs, and required by broker capability shadow-fill / scorecard rows. Added blocked template `settings/broker/stock_etf_reference_data_sources.template.toml` and acceptance tests.
- Verification passed: focused linked openclaw_types tests `28 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `168` integration/acceptance + `0` doc-tests; targeted touched-file `rustfmt --check` passed.
- Boundary unchanged: no IBKR contact/healthcheck, no secret read/create/serialization, no connector runtime, no reference-data ingestion, no evidence clock, no scorecard writer, no DB apply, no GUI lane authority, no tiny-live/live, and no Bybit live execution behavior change. First IBKR contact remains blocked until real secret/topology evidence and immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.

## 2026-06-30 IBKR Stock/ETF Market-Data Provenance Contract

- Source checkpoint hardens `stock_market_data_provenance_v1` inside the Phase 3 evidence contract surface for lane/broker/environment, vendor/entitlement, payload/source hashes, timestamps, adjustment marker, instrument identity, and calendar session provenance.
- The validator now rejects Bybit-live regression, IBKR contact, connector runtime, serialized secrets, and tiny-live/live authority; broker capability gates require it for market-data read, shadow-fill reconstruction, and scorecard derivation.
- Verification passed: focused linked openclaw_types tests `25 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `171` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, collector, market-data ingestion, evidence clock, scorecard writer, DB apply, GUI lane authority, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF Scorecard Input Contract Hardening

- Source checkpoint hardens Phase 3 scorecard input contracts: cash ledger, cost model, benchmark, shadow fill, and storage capacity now require exact named `contract_id` values and `source_version=1`.
- `StockEtfScorecardInputBundleV1` now requires market-data provenance, reference-data source, and risk-policy contract hashes, preserves Bybit-live unchanged proof, and rejects IBKR contact, connector runtime, broker fill import, scorecard writer, DB apply, evidence-clock start, serialized secrets, and tiny-live/live authority.
- Broker capability registry and lane-scoped IPC now consume shared scorecard contract constants for relevant gates; default-blocked scorecard input template exposes these fields and remains secret-free.
- Verification passed: focused linked openclaw_types tests `30 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `173` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, fill import, scorecard writer, DB apply, evidence clock, GUI lane authority, paper order, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF Evidence-Clock Contract Hardening

- Source checkpoint hardens `stock_etf_evidence_clock_v1` day evidence: it now requires exact contract id/source version, `stock_etf_cash` / IBKR lane binding, read-only/paper/shadow environment, source artifact hash, market-data provenance contract hash, and scorecard input bundle hash.
- The checker preserves Bybit-live unchanged proof and rejects checker-side IBKR contact, connector runtime, runtime evidence-clock start, scorecard writer, DB apply, serialized secrets, and tiny-live/live authority. `WINDOW_COMPLETE` remains rejected by the source checker alone.
- Broker capability registry, lane-scoped IPC, Phase 0 manifest, exports, and the default-blocked Phase 3 template now use the shared evidence-clock contract constant.
- Verification passed: focused linked openclaw_types tests `33 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `174` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, evidence clock, collector, scorecard writer, DB apply, GUI lane authority, paper order, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF Release/Tiny-Live Contract Hardening

- Source checkpoint hardens `stock_etf_release_packet_v1` and `tiny_live_adr_eligibility_v1`: release packets now require exact `packet_id == stock_etf_release_packet_v1` plus `source_version=1`, and tiny-live ADR eligibility now requires exact `contract_id == tiny_live_adr_eligibility_v1` plus `source_version=1`.
- The Phase 0 manifest validator consumes shared release/tiny-live contract constants; blocked templates expose `source_version=0`; regression tests reject old `_fixture` ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `21 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `176` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, evidence clock, scorecard writer, DB apply, GUI lane authority, paper order, ADR start, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF GUI Lane Contract Hardening

- Source checkpoint hardens `gui_lane_contract_v1`: GUI lane contract artifacts now require exact `contract_id == gui_lane_contract_v1` plus `source_version=1`.
- The Phase 0 manifest validator consumes the shared GUI lane contract constant; the blocked template exposes `source_version=0`; regression tests reject the old `_fixture` id and wrong source versions.
- Verification passed: focused linked openclaw_types tests `14 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `177` integration/acceptance + `0` doc-tests. This grants no GUI runtime authority, IBKR contact, connector runtime, DB apply, evidence clock, paper order, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Asset-Lane Audit Event Hardening

- Source checkpoint hardens `audit.asset_lane_events_v1`: asset-lane event references now require exact `schema_version == audit.asset_lane_events_v1` plus `source_version=1`.
- The Phase 0 manifest validator consumes the shared audit event contract constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like schema ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `15 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `178` integration/acceptance + `0` doc-tests. This grants no audit writer, DB apply, IBKR contact, connector runtime, evidence clock, paper order, GUI authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Broker Capability Registry Hardening

- Source checkpoint hardens `broker_capability_registry_v1`: registry artifacts now require exact `registry_id == broker_capability_registry_v1` plus `source_version=1`.
- The Phase 0 manifest validator and `lane_scoped_ipc_v1` paper/preview gates consume the shared broker registry contract constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like registry ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `22 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `179` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, paper order, evidence clock, scorecard writer, DB apply, GUI authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Lane-Scoped IPC Hardening

- Source checkpoint hardens `lane_scoped_ipc_v1`: IPC contract artifacts now require exact `contract_id == lane_scoped_ipc_v1` plus `source_version=1`.
- The Phase 0 manifest validator and IPC paper-effect self-gates consume the shared lane-scoped IPC contract constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like IPC ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `14 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `180` integration/acceptance + `0` doc-tests. This grants no IPC runtime, IBKR contact, connector runtime, paper order, evidence clock, scorecard writer, DB apply, GUI authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Instrument Identity Hardening

- Source checkpoint hardens `instrument_identity_contract_v1`: instrument identity artifacts now require exact `contract_id == instrument_identity_contract_v1` plus `source_version=1`.
- The Phase 0 manifest validator, broker capability contract-details gate, and `lane_scoped_ipc_v1` paper/preview gates consume the shared instrument identity constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like identity ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `31 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `181` integration/acceptance + `0` doc-tests. This grants no IBKR contract-details call, market-data subscription, connector runtime, IPC runtime, paper order, evidence clock, scorecard writer, DB apply, GUI authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF PIT Universe Hardening

- Source checkpoint hardens `stock_etf_pit_universe_contract_v1`: PIT universe artifacts now require exact `contract_id == stock_etf_pit_universe_contract_v1` plus `source_version=1`.
- The Phase 0 manifest validator, broker capability shadow/scorecard gates, and `lane_scoped_ipc_v1` preview/shadow gates consume the shared PIT universe constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like PIT universe ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `30 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `182` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, market-data collection, IPC runtime, paper order, evidence clock, scorecard writer, DB apply, GUI authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Strategy Hypothesis Hardening

- Source checkpoint hardens `stock_etf_strategy_hypothesis_contract_v1`: strategy hypothesis artifacts now require exact `contract_id == stock_etf_strategy_hypothesis_contract_v1` plus `source_version=1`.
- The Phase 0 manifest validator, broker capability shadow/scorecard gates, and `lane_scoped_ipc_v1` shadow gates consume the shared strategy hypothesis constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like strategy ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `30 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `183` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, market-data collection, IPC runtime, paper order, evidence clock, scorecard writer, DB apply, GUI authority, profitability claim, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Risk Policy Hardening

- Source checkpoint hardens `stock_etf_risk_policy_v1`: risk-policy artifacts now require exact `contract_id == stock_etf_risk_policy_v1` plus `source_version=1`; dormant source-config conversion emits source version 1 while preserving config version.
- The Phase 0 manifest validator consumes the shared risk policy constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like risk-policy ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `31 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `184` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, IPC runtime, paper order, market-data collection, evidence clock, scorecard writer, DB apply, GUI authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF DB Evidence DDL Hardening

- Source checkpoint hardens `stock_etf_db_evidence_ddl_v1`: DB evidence DDL artifacts now require exact `contract_id == stock_etf_db_evidence_ddl_v1` plus `source_version=1`.
- The Phase 0 manifest validator consumes the shared DB evidence DDL contract constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like DB DDL ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `14 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `185` integration/acceptance + `0` doc-tests. This grants no DB apply, PG write, sqlx migration registration, migration authorization, IBKR contact, connector runtime, evidence clock, scorecard writer, GUI authority, paper order, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Disable Cleanup Runbook Hardening

- Source checkpoint hardens `stock_etf_kill_switch_and_disable_cleanup_runbook_v1`: disable/cleanup runbook artifacts now require exact `runbook_id == stock_etf_kill_switch_and_disable_cleanup_runbook_v1` plus `source_version=1`.
- The Phase 0 manifest validator consumes the shared disable/cleanup runbook constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like runbook ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `13 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `186` integration/acceptance + `0` doc-tests. This grants no service stop, DB mutation, destructive cleanup, secret-slot creation, IBKR contact, connector runtime, paper order, evidence clock, GUI authority, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Reference Data Sources Hardening

- Source checkpoint hardens `stock_etf_reference_data_sources_v1`: reference-data artifacts now require exact `contract_id == stock_etf_reference_data_sources_v1` plus `source_version=1`; the blocker is now explicit `SourceVersionMismatch`.
- The Phase 0 manifest validator consumes the shared reference-data contract constant; the blocked template exposes and tests `source_version=0`; regression tests reject fixture-like reference-data ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `12 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `187` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, reference-data ingestion, scorecard writer, DB apply, evidence clock, GUI authority, paper order, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Market Data Provenance Hardening

- Source checkpoint hardens `stock_market_data_provenance_v1`: market-data provenance artifacts now require exact `contract_id == stock_market_data_provenance_v1` plus `source_version=1`.
- The Phase 0 manifest validator consumes the shared market-data provenance contract constant; the blocked template exposes and tests `source_version=0`; regression tests reject fixture-like provenance ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `19 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `188` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, collector start, market-data ingestion, scorecard writer, DB apply, evidence clock, GUI authority, paper order, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Phase2 Contract Constants Hardening

- Source checkpoint converges remaining Phase 0 / Phase 2 named contract ids into shared Rust constants for asset-lane taxonomy, external surface gate, non-Bybit API allowlist, API session topology, session attestation, feature-flag/secret/auth matrix, paper lifecycle, lifecycle event log, paper attestation, and redaction policy.
- Phase 0 manifest, broker capability registry gates, lane-scoped IPC gates, and audit event fixtures now consume shared constants where this does not create reverse module coupling; validation semantics are unchanged.
- Verification passed: focused linked openclaw_types tests `63 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `188` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, collector start, market-data/reference-data ingestion, scorecard writer, DB apply, evidence clock, GUI authority, paper order, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper Lifecycle Hardening

- Source checkpoint hardens paper lifecycle evidence: `BrokerLifecycleEventLogV1` now requires exact `lifecycle_contract_id == ibkr_paper_order_lifecycle_v1`, exact `event_log_contract_id == broker_lifecycle_event_log_v1`, and `source_version=1`.
- The blocked lifecycle template exposes empty ids plus `source_version=0`; regression tests reject fixture-like lifecycle/event-log ids and wrong source versions while preserving state-transition and append-only evidence checks.
- Verification passed: focused linked openclaw_types tests `32 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `189` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, IPC runtime, paper order, fill import, audit writer, DB apply, evidence clock, GUI authority, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Phase 2 Pre-Contact Identity Hardening

- Source checkpoint hardens Phase 2 pre-contact contracts: external-surface gate, API session topology, session attestation, feature-flag/secret/auth matrix, and prerequisite policies now require exact named contract ids plus `source_version=1`.
- Blocked external-surface/runtime/auth templates expose empty ids plus `source_version=0`; policy prerequisite templates carry exact policy ids/source versions but remain non-authorizing source prerequisites, not PASS artifacts.
- Verification passed: focused Phase 2 openclaw_types tests `32 passed`; linked tests `62 passed`; full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` `35` unit/golden + `191` integration/acceptance + `0` doc-tests; `cargo check --manifest-path rust/Cargo.toml --workspace` passed. This grants no IBKR contact, secret-slot creation, connector runtime, paper order, fill import, audit writer, DB apply, evidence clock, GUI authority, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Phase 2 Artifact + Secret Identity Hardening

- Source checkpoint hardens the remaining pre-contact artifact chain: `IbkrPhase2GateArtifactV1` now requires exact `contract_id == phase2_ibkr_external_surface_gate_v1` plus `source_version=1`, and `IbkrSecretSlotContractV1` requires exact `contract_id == ibkr_secret_slot_contract_v1` plus `source_version=1`.
- The blocked gate artifact template now exposes empty ids/source-version 0 for artifact, embedded gate, secret-slot, and topology sections; the blocked runtime contract template also exposes empty secret-slot id/source-version 0.
- Verification passed: focused openclaw_types tests `23 passed`; linked tests `63 passed`; full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` `35` unit/golden + `192` integration/acceptance + `0` doc-tests; `cargo check --manifest-path rust/Cargo.toml --workspace` passed. This grants no IBKR contact, secret inspection, secret-slot creation, connector runtime, paper order, fill import, audit writer, DB apply, evidence clock, GUI authority, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Non-Bybit API Allowlist Hardening

- Source checkpoint adds `NonBybitApiAllowlistV1` in `ibkr_non_bybit_api_allowlist`: exact `contract_id == non_bybit_api_allowlist_v1`, `source_version=1`, and complete read / paper-write / denied coverage for all 23 IBKR non-Bybit API actions.
- The validator ties bucket membership to `classify_non_bybit_api_action`, rejects Client Portal/live/account-write/margin/short/options/CFD/entitlement/contact/secret/Bybit-regression drift, and keeps the blocked external-surface template at empty id plus `source_version=0`.
- Verification passed: focused gate `10 passed`; linked IBKR/Phase0 `65 passed`; full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` `35` unit/golden + `194` integration/acceptance + `0` doc-tests; `cargo check --manifest-path rust/Cargo.toml --workspace` passed. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, audit writer, DB apply, evidence clock, GUI authority, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF IPC Readiness Allowlist Trace

- Phase 1D source/runtime fixture checkpoint makes Stock/ETF engine IPC readiness expose `phase2.api_allowlist` with exact `non_bybit_api_allowlist_v1` id/version, accepted verdict, action counts, no-contact/no-secret flags, and Bybit-live protected proof.
- The external-surface gate remains blocked because there is still no immutable PASS artifact, no real secret/topology evidence, and no first-contact authorization; legacy `submit_paper_order` behavior remains on the existing channel path.
- Verification passed: engine IPC focused `4 passed`; engine `stock_etf` filtered `5 passed`; linked openclaw_types `18 passed`; `cargo check --manifest-path rust/Cargo.toml --workspace` passed. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Readiness Allowlist Gate

- Phase 1D FastAPI checkpoint makes the Stock/ETF readiness route normalize `phase2.api_allowlist` into top-level `api_allowlist` and fail closed on missing/mismatched `non_bybit_api_allowlist_v1` id, source version, action counts, contact/secret flags, or missing Bybit-live protection proof.
- IPC unavailable remains the existing degraded/fail-closed state rather than being reclassified as an IPC payload contract violation; integer contract fields reject boolean values.
- Verification passed: `python3 -m py_compile` for the route/test files and focused FastAPI/no-write pytest `12 passed`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Allowlist Readiness Trace

- Phase 4 display-only GUI checkpoint makes `tab-stock-etf.html` render the normalized `api_allowlist` readiness payload: accepted/blocked status, contract id/source version, action counts, no-contact/no-secret flags, Bybit-live protection proof, and allowlist blockers.
- Allowlist blockers are merged into the existing denied/blocker surface; static tests assert the tab consumes `api_allowlist` while preserving no POST, no paper order method, and no local/session storage authority.
- Verification passed: route test `py_compile`, focused FastAPI/no-write pytest `12 passed`, Node inline-script syntax check `2` scripts, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Static GUI No-Write Guard

- Source-only test checkpoint extends the Stock/ETF IBKR no-write guard to the static GUI tab, requiring `/api/v1/stock-etf/readiness` and rejecting POST/PUT/PATCH/DELETE snippets, `ocPost`, direct `fetch`, forms, browser storage lane authority, IBKR broker-write strings, and Stock/ETF write IPC strings.
- The guard is intentionally scoped to `tab-stock-etf.html` so existing Bybit paper/live GUI surfaces are not reclassified as IBKR violations.
- Verification passed: guard test `py_compile`, focused FastAPI/static no-write pytest `13 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Route Cache Auth Partition

- Phase 4 route/cache/auth checkpoint makes Stock/ETF readiness and tab redirect responses emit no-store/private cache headers plus `Vary: Authorization`.
- Route tests prove query/header supplied lane, paper-ready, and first-contact claims are ignored: the API still calls only `stock_etf.get_readiness` with empty params and trusts the Rust IPC payload.
- Verification passed: route/test `py_compile`, focused FastAPI/static no-write pytest `14 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Route Method Partition

- Source-only Phase 4 route-method checkpoint asserts the Stock/ETF OpenAPI surface exposes only `GET /api/v1/stock-etf/readiness`.
- Runtime negative tests assert `POST`, `PUT`, `PATCH`, and `DELETE` return `405` for both `/api/v1/stock-etf` and `/api/v1/stock-etf/readiness`; the existing static no-write guard remains in force.
- Verification passed: route test `py_compile`, focused FastAPI/static no-write pytest `16 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Lane Status Read-Only Surface

- Phase 4 API checkpoint adds display-only `GET /api/v1/stock-etf/lane-status`, calling only Rust IPC `stock_etf.get_lane_status` with empty params and no-store/private cache headers.
- Lane-status normalization fail-closes to default `crypto_perp`, Stock/ETF/IBKR display identity, `display_only` GUI authority, no paper-order entry, no IBKR live, and no first-contact allowance; route tests prove query/header lane/paper/contact claims are ignored.
- Verification passed: route/test `py_compile`, focused FastAPI/static no-write pytest `21 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Lane Status Read-Only Render

- Phase 4 static GUI checkpoint makes `tab-stock-etf.html` consume display-only `GET /api/v1/stock-etf/lane-status` alongside readiness and render lane-status state plus feature flags in the Lane Boundary panel.
- Static guards now require both read-only endpoints while continuing to reject direct `fetch`, POST/PUT/PATCH/DELETE snippets, forms, browser storage lane authority, broker-write strings, and Stock/ETF write IPC strings.
- Verification passed: GUI guard `py_compile`, focused FastAPI/static no-write pytest `21 passed`, Node inline-script syntax check `2` scripts, and `git diff --check`. This grants no login-success lane selector, GUI/lane authority, IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust Lane Status IPC Regression

- Source-only Rust IPC test checkpoint adds direct coverage for `stock_etf.get_lane_status`: phase2 precontact fixture identity, Stock/ETF/IBKR lane binding, mirrored default lane/flag state, typed feature-flag booleans, and safety fields false.
- The test asserts Phase 2 remains blocked, first IBKR contact false, connector disabled, API allowlist identity/version present, no IBKR contact performed, and no secret serialization.
- Verification passed: `rustfmt --edition 2021`, focused lane-status cargo test `1 passed`, filtered `openclaw_engine stock_etf` cargo test `6 passed`, focused FastAPI/static no-write pytest `21 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Redirect Auth Partition

- Phase 4 auth checkpoint makes `GET /api/v1/stock-etf` tab redirect require the same authenticated actor dependency as the Stock/ETF read APIs.
- Added a negative test proving unauthenticated redirect access returns `401`; existing method tests still prove Stock/ETF API routes are GET-only and reject POST/PUT/PATCH/DELETE.
- Verification passed: route/test `py_compile`, focused FastAPI/static no-write pytest `22 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF IPC Method Registry Boundary

- Source-only Rust method-registry checkpoint makes Stock/ETF IPC fixture boundaries explicit: lane-status/readiness/preview/import/shadow methods remain read-only fixtures.
- Stock/ETF submit/cancel/replace paper methods stay visibly non-readonly, require no global IPC slot, do not enter the Bybit live-write token surface, and do not alias legacy paper method names.
- Verification passed: `rustfmt --edition 2021`, focused registry cargo test `1 passed`, filtered `openclaw_engine stock_etf` cargo test `7 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Evidence Status Read-Only Surface

- Phase 4 source-only checkpoint adds Rust IPC read-only fixture `stock_etf.get_evidence_status`, registry/dispatch coverage, and a blocked `phase3_evidence_status_source_fixture` from existing market-data provenance/evidence-clock contracts.
- FastAPI now exposes authenticated no-store `GET /api/v1/stock-etf/evidence-status`, calls only that IPC method with empty params, ignores client-supplied state, fail-closes on IPC errors, and converts Phase 3/contact/secret/order/scorecard/DB/Bybit IPC side-effect signals into contract violations while top-level authority fields remain false.
- `tab-stock-etf.html` renders the Evidence Status panel from the read-only endpoint; static guards require lane-status/readiness/evidence-status and still reject write methods, direct `fetch`, forms, browser storage lane authority, direct IBKR broker writes, and Stock/ETF write IPC strings.
- Verification passed: `rustfmt --edition 2021`, filtered `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf` `8 passed`, route/static `py_compile`, focused pytest `27 passed`, Node inline-script syntax `checked 2 inline scripts`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, evidence clock runtime, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2 start, Phase 3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Storage Capacity Guard

- Source-only contract checkpoint hardens `stock_etf_storage_capacity_v1`: max `1,000` instruments, max `5,000,000` rows/day, max `8,192` MB index budget, max `5,000` ms query SLO, raw payload hash retention at least `365` days, compressed retention not shorter than raw-hash retention and not above `3,650` days, and archive paths restricted to relative `evidence/stock_etf_cash/...`.
- Acceptance tests now reject unbounded volume, slow query SLO, retention-order violations, and unsafe/cross-lane/archive traversal paths; the Phase 0 named contract packet documents the same guard.
- Verification passed: `rustfmt --edition 2021`, scorecard inputs `12 passed`, Phase0 manifest `6 passed`, Phase3 evidence `13 passed`, full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` `35` unit/golden + `181` integration/acceptance + `0` doc-tests, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, evidence clock runtime, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2 start, Phase 3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Contract Endpoint Hardening

- Source-only GUI contract checkpoint updates `gui_lane_contract_v1` to require three exact display-only GET surfaces: `/api/v1/stock-etf/readiness`, `/api/v1/stock-etf/lane-status`, and `/api/v1/stock-etf/evidence-status`.
- Added lane-status/evidence-status constants, GET-only fields, endpoint mismatch blockers, blocked template fields, and acceptance coverage; the Phase 0 named contract packet now documents the three-endpoint GUI surface.
- Verification passed: `rustfmt --edition 2021` on GUI contract source/test, GUI contract `9 passed`, Phase0 manifest `6 passed`, FastAPI/static guard pytest `27 passed`, full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` `35` unit/golden + `182` integration/acceptance + `0` doc-tests, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, evidence clock runtime, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2 start, Phase 3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper Status Read-Only Surface

- Phase 4B source-only checkpoint adds Rust IPC fixture `stock_etf.get_paper_status`, authenticated FastAPI `GET /api/v1/stock-etf/paper-status`, and a GUI `Paper Status` panel showing blocked paper lifecycle/reconstructability state.
- `lane_scoped_ipc_v1` now includes `GetPaperStatus` as display-only/non-effect-capable, and `gui_lane_contract_v1` requires paper-status as an exact GET-only/display-only endpoint alongside readiness/lane/evidence/universe/shadow status.
- Verification passed: engine `stock_etf` filtered `11 passed`; GUI/lane IPC focused `17 passed`; FastAPI/static guard `42 passed`; Node inline scripts `checked 2`; full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` passed; `cargo check --manifest-path rust/Cargo.toml --workspace` passed; `git diff --check` PASS. This grants no IBKR contact, secret access, connector runtime, paper account snapshot, broker paper attestation, paper order, fill import, lifecycle writer, DB apply, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Status Normalizer Split

- Source-only Python refactor splits the overgrown Stock/ETF FastAPI status normalizers out of `stock_etf_routes.py` into shared/common plus readiness, evidence, universe, shadow, and paper normalizer modules; the route file now keeps only authenticated GET handlers, no-store header handling, and IPC query helpers.
- `stock_etf_routes.py` drops from `1550` lines to `257` lines, and every new Stock/ETF status normalizer module is below the `800` review-attention threshold; `test_stock_etf_routes.py` remains `1736` lines and should be fixture-split before the next route-test expansion.
- Verification passed: Stock/ETF route/normalizer/test `py_compile`; focused FastAPI/static no-write pytest `42 passed`; `git diff --check` PASS. This grants no new endpoint, response-contract change, IBKR contact, secret access, connector runtime, paper order, fill import, DB apply, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Route Test Split

- Source-only Python test refactor splits `test_stock_etf_routes.py` into a shared `stock_etf_route_fixtures.py` helper plus endpoint-scoped lane/readiness/evidence/universe/shadow/paper route-test modules; the original route test now covers auth, OpenAPI GET-only shape, redirect, static GUI registration, and display-only checks.
- `test_stock_etf_routes.py` drops from `1736` lines to `144` lines; every Stock/ETF route-test module is now below the `800` review-attention threshold.
- Verification passed: split Stock/ETF route-test `py_compile`; focused FastAPI/static no-write pytest `42 passed`; `git diff --check` PASS. This grants no production-code change, endpoint change, IBKR contact, secret access, connector runtime, paper order, fill import, DB apply, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Reconciliation Status Read-Only Surface

- Phase 4 source-only checkpoint adds Rust IPC read-only fixture `stock_etf.get_reconciliation_status`, dispatch/registry coverage, authenticated FastAPI `GET /api/v1/stock-etf/reconciliation-status`, and a GUI `Reconciliation Status` panel.
- `lane_scoped_ipc_v1` now includes `GetReconciliationStatus` as display-only/non-effect-capable, and `gui_lane_contract_v1` requires reconciliation-status as an exact GET-only/display-only endpoint alongside readiness/lane/evidence/universe/shadow/paper status.
- Verification passed: route/normalizer/test `py_compile`; `rustfmt --check` on changed Rust files except `rust/openclaw_types/src/lib.rs`; `git diff --check` PASS; Node inline scripts `parsed 7`; focused FastAPI/static no-write pytest `47 passed`; engine `stock_etf` filtered `12 passed`; GUI/lane IPC focused `17 passed`. This grants no IBKR contact, secret access, connector runtime, Phase 2/3 start, paper account snapshot, broker paper attestation, paper order, fill import, lifecycle writer, scorecard writer, DB apply, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Account Status Read-Only Surface

- Phase 4 source-only checkpoint adds Rust IPC read-only fixture `stock_etf.get_account_status`, dispatch/registry coverage, authenticated FastAPI `GET /api/v1/stock-etf/account-status`, and a GUI `Account / Connector Status` panel.
- `lane_scoped_ipc_v1` now includes `GetAccountStatus` as display-only/non-effect-capable, and `gui_lane_contract_v1` requires account-status as an exact GET-only/display-only endpoint alongside readiness/lane/evidence/universe/shadow/paper/reconciliation status.
- Verification passed: route/normalizer/test `py_compile`; `rustfmt --check` on changed Rust files except `rust/openclaw_types/src/lib.rs`; `git diff --check` PASS; Node inline script parser PASS; focused FastAPI/static no-write pytest `52 passed`; engine `stock_etf` filtered `13 passed`; GUI/lane IPC focused `17 passed`. This grants no IBKR contact, secret access, connector runtime, Phase 2/3 start, account snapshot, portfolio snapshot, cash ledger retrieval, broker paper attestation, paper order, fill import, lifecycle writer, scorecard writer, DB apply, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Scorecard Verdict Contract

- Phase 3 source-only checkpoint adds `stock_etf_scorecard_verdict_v1`, an exported Rust validator and default-blocked template for the statistical scorecard verdict artifact between scorecard inputs and future `tiny_live_adr_eligibility_v1`.
- Verdict labels now cover `engineering_ready`, `research_promising`, `profitability_feasible`, `insufficient_evidence`, `execution_model_invalid`, and `kill`; positive verdicts require formula/preregistration hashes, sample/window thresholds, paper-vs-shadow divergence, PSR/DSR-style thresholds, after-cost LCBs where applicable, quality labels, and QC/MIT/QA review hashes.
- Negative verdicts can be sealed without positive profitability, while the validator rejects IBKR contact, connector runtime, broker fill import, scorecard writer side effects, DB apply, evidence-clock start, secret serialization, tiny-live/live authority, and Bybit-live regression.
- Verification passed: `rustfmt --check` on new Rust source/test, scorecard verdict `8 passed`, scorecard inputs `12 passed`, tiny-live eligibility `7 passed`, phase0 manifest `6 passed`, full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` `35` unit/golden + `206` integration/acceptance + `0` doc-tests, and `git diff --check`. Runtime was not synced or restarted. This grants no IBKR contact, secret access, connector runtime, evidence clock runtime, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2/3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Scorecard Status Read-Only Surface

- Phase 4 source-only checkpoint adds Rust IPC read-only fixture `stock_etf.get_scorecard_status`, dispatch/registry coverage, authenticated FastAPI `GET /api/v1/stock-etf/scorecard-status`, and a GUI `Scorecard Verdict Status` panel.
- `lane_scoped_ipc_v1` now includes `GetScorecardStatus` as display-only/non-effect-capable, and `gui_lane_contract_v1` requires scorecard-status as an exact GET-only/display-only endpoint alongside readiness/lane/evidence/universe/shadow/paper/reconciliation/account status.
- Verification passed: route/normalizer/test `py_compile`; Rust format check on changed files, with `lib.rs` checked using `skip_children=true` to avoid unrelated module traversal; Node inline parser PASS; focused FastAPI/static pytest `57 passed`; engine `stock_etf` filtered `14 passed`; full `openclaw_types` `35` unit/golden + `206` integration/acceptance + `0` doc-tests; and `git diff --check`. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access, evidence clock, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2/3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Launch Status Read-Only Surface

- Phase 4/5 source-only checkpoint adds Rust IPC read-only fixture `stock_etf.get_launch_status`, registry/dispatch coverage, authenticated FastAPI `GET /api/v1/stock-etf/launch-status`, and a GUI `Launch / Release Status` panel.
- The surface exposes only blocked/default posture from `stock_etf_release_packet_v1`, `stock_etf_kill_switch_and_disable_cleanup_runbook_v1`, and `tiny_live_adr_eligibility_v1`; FastAPI fail-closes IPC errors and converts launch/live/secret/order/DB/Bybit reuse drift into `contract_violation_blocked` while top-level authority fields remain false.
- `lane_scoped_ipc_v1` now includes `GetLaunchStatus` as display-only/non-effect-capable, and `gui_lane_contract_v1` requires launch-status as an exact GET-only/display-only endpoint alongside readiness/lane/evidence/universe/shadow/paper/reconciliation/account/scorecard status.
- Verification passed: route/normalizer/test `py_compile`; Rust format check on changed files, with `lib.rs` checked using `skip_children=true`; Node inline parser PASS (`7` scripts); focused FastAPI/static pytest `58 passed`; engine `stock_etf` filtered `15 passed`; GUI/lane IPC focused `17 passed`; full `openclaw_types` `35` unit/golden + `174` integration/acceptance + `0` doc-tests. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access, evidence clock, scorecard writer, DB apply, paper-shadow launch, paper order, fill import, GUI/lane selector authority, Phase 2/3/5 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Data Foundation Status Read-Only Surface

- Phase 4 source-only checkpoint adds Rust IPC read-only fixture `stock_etf.get_data_foundation_status`, registry/dispatch coverage, authenticated FastAPI `GET /api/v1/stock-etf/data-foundation-status`, and a GUI `Data Foundation Status` panel.
- The surface exposes blocked/default posture from `instrument_identity_contract_v1` and `stock_etf_reference_data_sources_v1`; FastAPI fail-closes IPC errors and converts contract-details/reference collection/market ingestion/contact/secret/connector/DB/Bybit reuse drift into `contract_violation_blocked` while top-level authority fields remain false.
- `lane_scoped_ipc_v1` now includes `GetDataFoundationStatus` as display-only/non-effect-capable, and `gui_lane_contract_v1` requires data-foundation-status as an exact GET-only/display-only endpoint alongside readiness/lane/evidence/universe/shadow/paper/reconciliation/account/scorecard/launch status.
- Verification passed: route/normalizer/test `py_compile`; Rust format check on changed files, with `lib.rs` checked using `skip_children=true`; Node inline parser PASS (`7` scripts); focused FastAPI/static pytest `18 passed`; full Stock/ETF FastAPI/static pytest `67 passed`; engine `stock_etf` filtered `16 passed`; GUI/lane IPC focused `17 passed`; full `openclaw_types` `35` unit/golden + `206` integration/acceptance + `0` doc-tests; `git diff --check` PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access, contract-details request, reference-data collection/ingestion, market-data ingestion, evidence clock, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2/3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Policy Status Read-Only Surface

- Phase 4 source-only checkpoint adds Rust IPC read-only fixture `stock_etf.get_policy_status`, registry/dispatch coverage, authenticated FastAPI `GET /api/v1/stock-etf/policy-status`, and a GUI `Policy / Capability Status` panel plus `Policy Gate` metric.
- The surface exposes blocked/default posture from `stock_etf_risk_policy_v1` and `broker_capability_registry_v1`; FastAPI fail-closes IPC errors and converts risk/capability/contact/secret/order/DB/Bybit reuse drift into `contract_violation_blocked` while top-level authority fields remain false.
- `lane_scoped_ipc_v1` now includes `GetPolicyStatus` as display-only/non-effect-capable, and `gui_lane_contract_v1` requires policy-status as an exact GET-only/display-only endpoint alongside readiness/lane/data-foundation/evidence/universe/shadow/paper/reconciliation/account/scorecard/launch status.
- Verification passed: route/normalizer/test `py_compile`; Rust format check on changed files, with `lib.rs` checked using `skip_children=true`; Node inline parser PASS (`2` scripts); focused FastAPI/static pytest `18 passed`; full Stock/ETF FastAPI/static pytest `72 passed`; engine `stock_etf` filtered `17 passed`; GUI/lane IPC focused `17 passed`; full `openclaw_types` `35` unit/golden + `206` integration/acceptance + `0` doc-tests. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access, contract-details request, account snapshot, risk runtime, paper-order rehearsal/submit, paper fill import, evidence clock, scorecard writer, DB apply, GUI/lane selector authority, Phase 2/3/5 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Authorization Status Read-Only Surface

- Phase 4 source-only checkpoint adds Rust IPC read-only fixture `stock_etf.get_authorization_status`, registry/dispatch coverage, authenticated FastAPI `GET /api/v1/stock-etf/authorization-status`, and a GUI `Authorization Status` panel plus `Authorization Gate` metric.
- The surface exposes blocked/default posture from `feature_flag_secret_auth_matrix_v1`, `ibkr_secret_slot_contract_v1`, `phase2_ibkr_external_surface_gate_v1`, `ibkr_session_attestation_v1`, and the authorization envelope; FastAPI fail-closes IPC errors and converts authorization/contact/secret/session/order/DB/Bybit reuse drift into `contract_violation_blocked` while top-level authority fields remain false.
- `lane_scoped_ipc_v1` now includes `GetAuthorizationStatus` as display-only/non-effect-capable, and `gui_lane_contract_v1` requires authorization-status as an exact GET-only/display-only endpoint alongside readiness/lane/data-foundation/policy/evidence/universe/shadow/paper/reconciliation/account/scorecard/launch status.
- Verification passed: route/normalizer/test `py_compile`; Rust format check on changed files, with `lib.rs` checked using `skip_children=true`; Node inline parser PASS (`7` scripts); full Stock/ETF FastAPI/static pytest `77 passed`; engine `stock_etf` filtered `18 passed`; GUI/lane IPC focused `17 passed`; full `openclaw_types` `35` unit/golden + `206` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access/creation, contract-details request, account snapshot, risk runtime, paper-order rehearsal/submit, paper fill import, evidence clock, scorecard writer, DB apply, GUI/lane selector authority, Phase 2/3/5 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Split Hygiene

- Pure GUI hygiene checkpoint splits the accumulated Stock/ETF tab JavaScript out of `tab-stock-etf.html` into `/static/tab-stock-etf.js` after the HTML reached `2225` lines and exceeded the repo 2000-line hard cap.
- Post-split line counts are `tab-stock-etf.html` `341` lines and `tab-stock-etf.js` `1883` lines; static no-write guards now scan the HTML+JS bundle while still checking forbidden write snippets per file.
- Verification passed: changed tests `py_compile`, `node --check tab-stock-etf.js`, HTML inline parser PASS (`1` script), full Stock/ETF FastAPI/static pytest `77 passed`, and `git diff --check` PASS. This grants no new endpoint, IPC/contract change, IBKR contact, secret access, connector runtime, paper order, DB apply, Linux runtime sync/restart, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Disable Cleanup Status Read-Only Surface

- Phase 4/5 source-only checkpoint adds Rust IPC read-only fixture `stock_etf.get_disable_cleanup_status`, registry/dispatch coverage, authenticated FastAPI `GET /api/v1/stock-etf/disable-cleanup-status`, and a GUI `Disable / Cleanup Status` panel plus `Disable Cleanup` metric.
- The surface exposes only `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` source-ready runbook shape with top-level runtime cleanup/launch fields blocked false; FastAPI fail-closes IPC errors and converts contact/secret/order/destructive cleanup/DB/Bybit reuse drift into `contract_violation_blocked`.
- `lane_scoped_ipc_v1` now includes `GetDisableCleanupStatus` as display-only/non-effect-capable, and `gui_lane_contract_v1` requires disable-cleanup-status as an exact GET-only/display-only endpoint. GUI render logic lives in `/static/tab-stock-etf-disable-cleanup.js` so `tab-stock-etf.js` stays below the 2000-line cap.
- Verification passed: route/normalizer/test `py_compile`; full Stock/ETF FastAPI/static pytest `81 passed`; `node --check` for both Stock/ETF JS files; HTML inline parser PASS (`1` script); line caps `359/1895/132`; openclaw_engine `stock_etf` filtered `19 passed`; openclaw_types `stock_etf` filter PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access/creation, collector stop, GUI hide, evidence archive, DB cleanup/apply, paper-shadow launch, paper order, fill import, evidence clock, scorecard writer, GUI/lane selector authority, Phase 2/3/5 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Release Packet Status Read-Only Surface

- Phase 4/5 source-only checkpoint adds Rust IPC read-only fixture `stock_etf.get_release_packet_status`, registry/dispatch coverage, authenticated FastAPI `GET /api/v1/stock-etf/release-packet-status`, and a GUI `Release Packet Status` panel plus `Release Packet` metric.
- The surface exposes only `stock_etf_release_packet_v1` source fixture plus disable-cleanup proof summary while top-level Phase 3/5, paper-shadow launch, connector, scorecard writer, DB, evidence clock, order, secret, IBKR contact, and Bybit reuse fields remain false; FastAPI converts drift into `contract_violation_blocked`.
- `lane_scoped_ipc_v1` now includes `GetReleasePacketStatus` as display-only/non-effect-capable, and `gui_lane_contract_v1` requires release-packet-status as an exact GET-only/display-only endpoint. GUI render logic lives in `/static/tab-stock-etf-release-packet.js` so `tab-stock-etf.js` stays below the 2000-line cap.
- Verification passed: route/normalizer/test `py_compile`; full Stock/ETF FastAPI/static pytest `85 passed`; `node --check` for all Stock/ETF JS files; HTML inline parser PASS (`1` script); openclaw_engine `stock_etf` filtered `20 passed`; full openclaw_types PASS; workspace `cargo check` PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access/creation, release packet materialization, paper-shadow launch, paper order, fill import, evidence clock, scorecard writer, DB apply, GUI/lane selector authority, Phase 2/3/5 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Phase 0 Packet Status Read-Only Surface

- Phase 0/4 source-only checkpoint adds Rust IPC read-only fixture `stock_etf.get_phase0_status`, registry/dispatch coverage, authenticated FastAPI `GET /api/v1/stock-etf/phase0-status`, and a GUI `Phase 0 Packet Status` panel plus `Phase 0 Packet` metric.
- The surface exposes only the accepted `stock_etf_phase0_contract_packet_manifest_v1` source manifest, contract count, API baseline, global denials, and phase-unlock posture while top-level Phase 1/2/3/4/5 runtime, paper-shadow launch, connector, scorecard writer, DB, evidence clock, order, secret, IBKR contact, and Bybit reuse fields remain false; FastAPI converts manifest/runtime drift into `contract_violation_blocked`.
- `lane_scoped_ipc_v1` now includes `GetPhase0Status` as display-only/non-effect-capable, and `gui_lane_contract_v1` requires phase0-status as an exact GET-only/display-only endpoint. GUI render logic lives in `/static/tab-stock-etf-phase0.js` so `tab-stock-etf.js` stays below the 2000-line cap.
- Verification passed: route/normalizer/test `py_compile`; full Stock/ETF FastAPI/static pytest `89 passed`; `node --check` for all Stock/ETF JS files; HTML inline parser PASS (`1` script); Rust format checks PASS; openclaw_engine `stock_etf` filtered `21 passed`; full openclaw_types `35` unit/golden + `206` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access/creation, Phase 1/2/3/4/5 runtime start, release packet materialization, paper-shadow launch, paper order, fill import, evidence clock, scorecard writer, DB apply, GUI/lane selector authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF DB Evidence DDL Source Audit

- Phase 1C source-only checkpoint adds exported Rust auditor `audit_stock_etf_db_evidence_source_sql` for `stock_etf_db_evidence_ddl_v1.source_only.sql`.
- The auditor machine-checks the source-only banner, migration/apply denial, destructive statement denial, required schemas/tables, Guard A, key table column declarations, natural keys, stock/IBKR/paper checks, live denial, synthetic shadow fill separation, raw artifact hash requirements, append-only audit event table/comment, and hot-path indexes.
- Acceptance coverage now runs the real source SQL and rejects contract drift or migration promotion, including missing required column declarations, missing synthetic shadow fill checks, and appended destructive SQL.
- Verification passed: Rust format checks on changed files with `lib.rs` checked using `skip_children=true`; focused source SQL audit `2 passed`; full DB evidence DDL acceptance `9 passed`; full openclaw_types `35` unit/golden + `207` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS. Linux runtime was not synced/restarted. This grants no DB migration/apply, PG dry-run, IBKR contact, connector runtime, secret access/creation, Phase 1 runtime start, paper order, fill import, evidence clock, scorecard writer, GUI/lane selector authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF DB Evidence DDL Source Contract Hardening

- Phase 1C source-only checkpoint strengthens `stock_etf_db_evidence_ddl_v1.source_only.sql` with Guard B type checks, Guard C hot-path index drift checks, source-level foreign keys for instrument/order/fill/commission/shadow lineage, and scorecard lineage columns for cost model, market-data provenance, corporate actions, FX/cash ledger, and paper-vs-shadow reconciliation hashes.
- The source draft now carries a TimescaleDB hypertable/retention promotion plan without executing it; it explicitly blocks V### promotion until every promoted table is redesigned so all primary/unique constraints include the partition column.
- The Rust auditor now rejects missing Guard B/C, missing migration dry-run plan, missing required FKs, missing scorecard lineage columns, and missing hypertable/retention plan; acceptance coverage is now `10` DB DDL tests.
- Verification passed: Rust format checks with `lib.rs` checked using `skip_children=true`; DB evidence DDL acceptance `10 passed`; full openclaw_types `35` unit/golden + `208` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS. Linux runtime was not synced/restarted. This grants no DB migration/apply, PG dry-run, sqlx registration, IBKR contact, connector runtime, secret access/creation, Phase 1 runtime start, paper order, fill import, evidence clock, scorecard writer, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper IPC Request Shape Hardening

- Phase 1D source-only checkpoint hardens `lane_scoped_ipc_v1` by splitting paper order request fields for `PreviewPaperOrder`, `SubmitPaperOrder`, `CancelPaperOrder`, and `ReplacePaperOrder`; submit/cancel/replace no longer share one generic paper-effect field set.
- Submit now pins account fingerprint hash, instrument identity, symbol, instrument kind, side, order type, quantity, `limit_price_policy`, time in force, `order_local_id`, and idempotency key. Cancel now pins `order_local_id`, `broker_order_id`, `cancel_reason`, and idempotency. Replace now pins `order_local_id`, `broker_order_id`, instrument identity, symbol, side, replacement idempotency/quantity/limit-price-policy/time-in-force, and `replace_reason`.
- Acceptance coverage now proves the three effect-capable method request shapes are distinct and rejects submit/cancel/replace cross-wiring with `CommandRequestFieldMissing`.
- Verification passed: Rust format checks; focused lane IPC `9 passed`; lane IPC + Phase0 manifest `15 passed`; full openclaw_types `35` unit/golden + `209` integration/acceptance + `0` doc-tests; openclaw_engine `stock_etf` filter `21 passed`; workspace `cargo check` PASS; `git diff --check` PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access/creation, Phase 1 runtime start, paper order, cancel, replace, fill import, DB apply, evidence clock, scorecard writer, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper Request Envelope Contract

- Phase 1D source-only checkpoint adds `stock_etf_paper_order_request_v1`, a typed Rust request envelope between `lane_scoped_ipc_v1` and `ibkr_paper_order_lifecycle_v1`.
- The envelope validates preview/submit/cancel/replace semantics with exact lane/broker/paper environment, IPC method/operation/scope/effect alignment, normalized symbol, stock/ETF instrument kind, buy/sell side, market/limit order type, positive decimal quantity, explicit limit-price policy, day/GTC time-in-force rules, local/broker/idempotency ids, replacement fields, and lifecycle/capability/audit lineage.
- It rejects IBKR contact, connector runtime, serialized secrets, routed orders, Bybit path reuse, live/tiny-live authority, margin/short/options/CFD requests, Python direct broker writes, cancel requests polluted by submit order-shape fields, and replace requests polluted by original mutable fields. Phase0 manifest now includes 29 contracts.
- Verification passed: new paper request acceptance `8 passed`; paper request + Phase0 manifest `14 passed`; lane IPC `9 passed`; FastAPI Phase0/StockETF route focused `14 passed`; openclaw_engine `stock_etf` filter `21 passed`; full openclaw_types `35` unit/golden + `217` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS; rustfmt/diff checks PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access/creation, Phase 1 runtime start, paper order/cancel/replace, fill import, DB apply, evidence clock, scorecard writer, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper Lifecycle State Machine

- Phase 1D source-only checkpoint hardens `ibkr_paper_order_lifecycle_v1` / `broker_lifecycle_event_log_v1` so lifecycle events require append-only sequencing/hash chaining, request-envelope hash linkage to `stock_etf_paper_order_request_v1`, exact paper environment, and explicit stale-state policy.
- Operation-to-transition validation now separates submit/cancel/replace/fill-import state changes; denied events cannot advance active broker state, and `STATE_UNKNOWN` manual-review vs terminal reconciliation is machine-checked.
- Verification passed: lifecycle acceptance `12 passed`; linked acceptance `12 + 8 + 9 + 6 passed`; engine Stock/ETF `21 passed`; full openclaw_types `35` unit/golden + `221` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, lifecycle writer, connector runtime, paper order/cancel/replace, fill import, DB apply, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper Status Lifecycle Surface Hardening

- Phase 1D/4 source-only checkpoint propagates the hardened paper lifecycle state-machine fields through Rust `stock_etf.get_paper_status`, FastAPI paper-status normalization, test fixtures, and the Stock/ETF GUI paper lifecycle panel.
- The read-only status surface now exposes request contract id, event sequence/genesis flags, hash-chain readiness, request-envelope linkage, and stale-state policy posture while preserving the blocked/default paper status.
- FastAPI now rejects stale lifecycle payload shapes and pre-gate claims for event-chain/request-envelope/stale-policy readiness as `contract_violation_blocked`; fallback paths remain display-only and order routing stays false.
- Verification passed: Python compile PASS; focused paper-status pytest `6 passed`; wider Stock/ETF FastAPI/static pytest `19 passed`; JS syntax PASS; Rust format check PASS; engine `stock_etf_paper_status` focused PASS; engine `stock_etf` filter `21 passed`; workspace `cargo check` PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, lifecycle writer, connector runtime, paper order/cancel/replace, fill import, DB apply, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper IPC Request Envelope Binding

- Phase 1D source-only checkpoint binds Rust IPC paper methods `stock_etf.preview/submit/cancel/replace_paper_order` to the typed `stock_etf_paper_order_request_v1` envelope validator before any future paper runtime can exist.
- The handler now returns a `request_envelope` verdict with parse status, contract id, expected/request method, IPC method-match result, validator blockers, authority/effect posture, lineage field presence, and boundary flags while preserving `ibkr_call_performed=false`, `secret_slot_touched=false`, `order_routed=false`, and `bybit_ipc_reused=false`.
- Regression coverage proves stale/minimal params fail envelope parsing without requiring the Bybit paper channel, a valid preview envelope can validate without runtime authority, and a submit envelope cannot be accepted under the cancel IPC method even if the envelope itself is valid.
- Verification passed: Rust format check PASS; engine `stock_etf` filter `23 passed`; openclaw_types paper request acceptance `8 passed`; workspace `cargo check` PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access/creation, lifecycle writer, paper order/cancel/replace, fill import, DB apply, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper Fill Import Request Contract

- Phase 1D source-only checkpoint adds `stock_etf_paper_fill_import_request_v1`, a typed request contract for future `stock_etf.import_paper_fills` evidence ingestion before lifecycle reconstruction or DB persistence.
- The contract pins exact Stock/ETF/IBKR/paper identity, `ImportPaperFills` IPC method, `PaperOrderFillImport` operation, read-only authority, session/lifecycle/event-log/redaction/source hashes, reconciliation run id, broker order/execution/commission ids, import idempotency, observed order state, stale-state policy, raw/redacted artifact hashes, and no side effects.
- Validation rejects duplicate imports, stale unknown state without policy, IBKR contact, connector runtime, serialized secrets, fill import side effects, DB apply, routed orders, Bybit path reuse, live/tiny-live authority, margin/short/options/CFD requests, and Python direct broker writes. Phase0 manifest and FastAPI Phase0 contract count now include 30 contracts.
- Verification passed: new fill import acceptance `6 passed`; Phase0 manifest acceptance `6 passed`; FastAPI Phase0/StockETF focused `14 passed`; full openclaw_types `35` unit/golden + `227` integration/acceptance + `0` doc-tests; engine `stock_etf` filter `23 passed`; workspace `cargo check` PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access/creation, lifecycle writer, fill import, DB apply, paper order/cancel/replace, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper Fill Import IPC Binding

- Phase 1D source-only checkpoint binds Rust IPC `stock_etf.import_paper_fills` to `stock_etf_paper_fill_import_request_v1` validation before any future fill importer can exist.
- The handler returns a `fill_import_request` verdict with parse status, expected/request method, IPC method-match result, validator blockers, read-only authority posture, lineage field presence, and boundary flags; `allowed` now also requires fill-import accepted-for-IPC.
- Regression coverage proves a valid fill-import request validates without runtime authority and stale/minimal params fail closed as `fill_import_request_parse_failed`, while IBKR/secret/routing/Bybit side-effect fields remain false.
- Verification passed: Rust format check PASS; engine fill-import IPC focused `2 passed`; openclaw_types fill-import acceptance `6 passed`; engine `stock_etf` filter `25 passed`; workspace `cargo check` PASS; `git diff --check` PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access/creation, lifecycle writer, fill import, DB apply, paper order/cancel/replace, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Shadow Signal Request Contract + IPC Binding

- Phase 1D/3 source-only checkpoint adds `stock_etf_shadow_signal_request_v1`, a typed request contract for future `stock_etf.evaluate_shadow_signal` before any shadow collector, signal emitter, or scorecard path can exist.
- The validator pins exact Stock/ETF/IBKR/shadow identity, `EvaluateShadowSignal` method, `ShadowSignalEmit` operation, shadow-only authority, signal/evaluation ids, evidence clock/PIT universe/strategy hypothesis/instrument identity/market-data provenance/cost model/asset-lane event/source hashes, and no side effects.
- Rust IPC now returns a `shadow_signal_request` verdict for `stock_etf.evaluate_shadow_signal`, and top-level `allowed` also requires `shadow_signal_request_accepted_for_ipc`. Minimal/stale params fail closed as `shadow_signal_request_parse_failed`.
- Phase0 manifest source, repository manifest JSON, FastAPI Phase0 count, route fixtures/tests, settings README, and Phase0 packet spec now include 31 contracts.
- Verification passed: shadow request acceptance `5 passed`; Phase0 manifest `6 passed`; FastAPI Phase0 route `4 passed`; FastAPI StockETF focused `14 passed`; engine shadow IPC focused `2 passed`; engine `stock_etf` filter `27 passed`; workspace `cargo check` PASS; scoped rustfmt check PASS; `git diff --check` PASS. This grants no IBKR contact, connector runtime, secret access/creation, shadow collector, shadow signal emission, shadow fill generation, scorecard writer, DB apply, paper order/cancel/replace, fill import, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper-Shadow Reconciliation Contract

- Phase 3 source-only checkpoint adds `stock_etf_paper_shadow_reconciliation_v1`, a typed contract linking paper lifecycle/fill facts, synthetic shadow-fill facts, frozen divergence threshold, and zero unmatched-fill checks before any reconciliation writer can exist.
- Phase0 manifest source, repository manifest JSON, FastAPI Phase0 count, reconciliation normalizers/tests, settings README, and Phase0 packet spec now include 32 contracts.
- Verification passed: reconciliation acceptance `5 passed`; Phase0 manifest `6 passed`; FastAPI Phase0/reconciliation focused `9 passed`; engine reconciliation focused `1 passed`; engine `stock_etf` filter `27 passed`; workspace `cargo check` PASS; scoped rustfmt check PASS; `git diff --check` PASS. This grants no IBKR contact, connector runtime, secret access/creation, fill import, shadow fill generation, reconciliation/scorecard writer, DB apply, paper order/cancel/replace, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Reconciliation GUI Contract Display

- Display-only checkpoint splits Stock/ETF reconciliation rendering into `tab-stock-etf-reconciliation.js`, keeping main `tab-stock-etf.js` at 1847 lines and under the hard cap.
- The Reconciliation panel now renders `stock_etf_paper_shadow_reconciliation_v1` id/acceptance/blockers, paper-shadow link hash, imported/synthetic markers, and side-effect flags; the new JS is included in route/static and no-write guards.
- Verification passed: Node syntax PASS, GUI line counts PASS, focused route/static/no-write `13 passed`, full Stock/ETF Python route/static `90 passed`. This grants no IBKR contact, connector runtime, fill import, shadow fill generation, reconciliation/scorecard writer, DB apply, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Scorecard Reconciliation Lineage Gate

- Phase 3 source/status/display-only checkpoint adds `paper_shadow_reconciliation_hash` to `stock_etf_scorecard_verdict_v1`, with a dedicated `PaperShadowReconciliationHashInvalid` blocker.
- Rust `stock_etf.get_scorecard_status`, FastAPI normalization, fixtures/tests, and the Stock/ETF GUI now expose `paper_shadow_reconciliation_hash_present=false`; pre-gate truthy claims are blocked as contract violations.
- Verification passed: scorecard verdict acceptance `8 passed`; focused FastAPI/static `15 passed`; full Stock/ETF FastAPI/static `90 passed`; engine `stock_etf` filter `27 passed`; full openclaw_types `35` unit/golden + `236` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS; rustfmt and Node syntax checks PASS. This grants no IBKR contact, connector runtime, secret access/creation, fill import, shadow fill generation, reconciliation writer, scorecard writer, DB apply, evidence clock, paper order/cancel/replace, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Scorecard Derivation Contract

- Phase 3 source/status/display-only checkpoint adds `stock_etf_scorecard_derivation_v1`, a derived artifact lineage contract between scorecard inputs/reconciliation and the scorecard verdict/writer boundary.
- Rust `stock_etf.get_scorecard_status`, FastAPI normalization, fixtures/tests, and the Stock/ETF GUI now expose a blocked `scorecard_derivation` block; pre-gate truthy derivation claims are blocked as contract violations.
- Verification passed: derivation acceptance `5 passed`; Python compile PASS; focused FastAPI/static `15 passed`; full Stock/ETF FastAPI/static `90 passed`; engine scorecard focused `1 passed`; engine `stock_etf` filter `27 passed`; full openclaw_types `35` unit/golden + `241` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS; rustfmt and Node syntax checks PASS. This grants no IBKR contact, connector runtime, secret access/creation, fill import, shadow fill generation, reconciliation writer, scorecard writer, DB apply, evidence clock, paper order/cancel/replace, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Tiny-Live Eligibility Lineage Gate

- Phase 5 ADR-discussion source/status/display-only checkpoint hardens `tiny_live_adr_eligibility_v1` with scorecard derivation/verdict/manifest hashes, paper-shadow reconciliation hash, DQ/statistical preregistration hashes, and QC/MIT/QA review gates.
- Rust `stock_etf.get_launch_status`, FastAPI normalization, fixtures/tests, and the Stock/ETF GUI now expose blocked lineage-present booleans; pre-gate truthy derivation/verdict/reconciliation/QA claims are blocked as contract violations.
- Verification passed: tiny-live eligibility `7 passed`; Python compile PASS; focused FastAPI/static `15 passed`; full Stock/ETF FastAPI/static `90 passed`; engine launch-status focused `1 passed`; engine `stock_etf` filter `27 passed`; full openclaw_types `35` unit/golden + `241` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS; rustfmt, Node syntax, and diff checks PASS. This grants no IBKR contact, connector runtime, secret access/creation, fill import, shadow fill generation, reconciliation writer, scorecard writer, DB apply, evidence clock, paper order/cancel/replace, ADR approval, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Read-Only Connector Skeleton Boundary

- Source-only checkpoint adds inert `program_code/broker_connectors/ibkr_connector/` outside the Bybit connector tree, with typed blocked readiness/previews and no IBKR SDK import, network contact, secret access, order methods, fill side effects, or DB writes.
- The existing Stock/ETF Python no-write static guard now scans the real connector skeleton, and dedicated skeleton tests assert the package stays blocked/source-only.
- Verification passed: Python compile PASS; connector skeleton + no-write static guard `7 passed`; full Stock/ETF FastAPI/static `94 passed`. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, scorecard writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF ADR/Register Lineage Catch-up

- Governance checkpoint updates `SPECIFICATION_REGISTER.md`, ADR-0048, and AMD-2026-06-29-01 so governance docs now record the scorecard derivation/verdict/reconciliation/tiny-live lineage gates and the inert IBKR connector skeleton boundary.
- Verification passed: register/ADR/AMD `rg` check PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, scorecard writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Connector Skeleton Readiness Gate

- Display-only checkpoint exposes a fail-closed `connector_skeleton` block through the Stock/ETF readiness normalizer and GUI, without importing the connector package or adding endpoints/actions.
- Pre-gate truthy claims for skeleton acceptance, non-blocked status, network contact, secret loading, paper/live channel exposure, write method presence, or Bybit path reuse now become readiness contract violations.
- Verification passed: Python compile PASS; focused readiness/no-write `9 passed`; full Stock/ETF FastAPI/static `94 passed`; Node syntax PASS; diff check PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, scorecard writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Source Posture Header Catch-up

- Governance/status text now says Phase 0 ADR/AMD/named contracts exist in source and Phase 1-5 source/status/display hardening is in progress; runtime launch remains blocked.
- Verification passed: `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, scorecard writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust Connector Skeleton Readiness Source

- Source/status-only checkpoint makes Rust IPC `stock_etf.get_readiness` emit the fail-closed `connector_skeleton` block now consumed by FastAPI and the Stock/ETF GUI, keeping the skeleton boundary sourced from Rust readiness rather than only Python fallback.
- The IPC fixture pins `ibkr_stock_etf_readonly_connector_skeleton_v1` to `accepted=false`, `status=blocked_source_only`, `phase2_gate_not_accepted`, and all contact/secret/paper/live/write/Bybit-reuse flags false.
- Verification passed: `rustfmt`, focused engine readiness `1 passed`, engine `stock_etf` filter `27 passed`, Python compile PASS, focused readiness/skeleton/no-write `13 passed`, full Stock/ETF FastAPI/static `94 passed`, Node syntax PASS, workspace `cargo check` PASS, and `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, scorecard writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Read-Only Probe Request Contract

- Phase 2 pre-contact source-only checkpoint adds `stock_etf_ibkr_readonly_probe_request_v1`, a typed request envelope for future IBKR health/account/contract-details/market-data read probes before any first contact can be considered.
- The validator requires Stock/ETF IBKR readonly identity, allowlisted read action to broker-operation mapping, Phase 2 gate artifact, allowlist, secret-slot, topology, session-attestation, redaction, rate-limit, and audit-policy lineage hashes, plus side-effect denials for contact/runtime/secret/order/DB/evidence/Bybit/live/account-write/entitlement/client-portal/Python-write paths.
- Phase0 manifest source, repository manifest JSON, FastAPI Phase0 count/fixtures/tests, settings template/README, ADR-0048, AMD-2026-06-29-01, specification register, and Phase0 packet spec now include 33 named contracts. Verification passed: readonly-probe acceptance `6 passed`; Phase0 manifest `6 passed`; Phase0 FastAPI route `4 passed`; full Stock/ETF FastAPI/static `94 passed`; full openclaw_types `35` unit/golden + `247` integration/acceptance + `0` doc-tests; engine `stock_etf` filter `27 passed`; workspace `cargo check` PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Read-Only Probe Readiness Gate

- Source/status/display-only checkpoint makes Rust IPC `stock_etf.get_readiness` expose a blocked `phase2.readonly_probe_request` block for `stock_etf_ibkr_readonly_probe_request_v1`, keeping the future first-contact read probe envelope visible but unavailable.
- FastAPI normalizes the block into top-level readiness and treats pre-gate truthy claims for request artifact presence, validation, accepted-for-contact, IBKR contact, connector runtime, secret serialization, order/paper order, DB apply, evidence clock, Bybit reuse, or live/tiny-live as contract violations.
- The Stock/ETF GUI now renders the readonly-probe request id/version/status/accepted flag and its guard flags/blockers; this adds no endpoint, connector import, broker SDK path, runtime action, or write surface.
- Verification passed: engine `stock_etf` filter `27 passed`; full Stock/ETF FastAPI/static `94 passed`; Node syntax PASS; workspace `cargo check` PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Read-Only Probe IPC Binding

- Phase 2 source-only checkpoint adds `stock_etf.preview_readonly_probe` as a Rust IPC validation fixture for `stock_etf_ibkr_readonly_probe_request_v1`; it parses/validates the envelope and returns `readonly_probe_request` plus `readonly_probe_request_accepted_for_ipc`.
- `lane_scoped_ipc_v1`, method registry, and dispatch now include the method as readonly/slot-none with Phase 2 gate, API allowlist, secret-slot/topology/session, redaction, rate-limit, and audit-policy lineage requirements.
- A valid readonly-probe request can validate as typed/read-only but top-level `allowed` remains false under default flags/gates; minimal params fail closed as `readonly_probe_request_parse_failed`.
- Verification passed: `rustfmt`; lane-scoped IPC acceptance `9 passed`; readonly-probe IPC focused `2 passed`; registry boundary focused `1 passed`; full openclaw_types `35` unit/golden + `247` integration/acceptance + `0` doc-tests; engine `stock_etf` filter `29 passed`; workspace `cargo check` PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Broker Read Capability Probe Gate

- Source-only checkpoint hardens `broker_capability_registry_v1`: `health_read`, `account_snapshot_read`, `market_data_read`, and `contract_details_read` now require `lane_scoped_ipc_v1` and `stock_etf_ibkr_readonly_probe_request_v1` in addition to their existing per-operation gates before any read capability row can validate.
- Validator/tests reject read rows missing the typed IPC and readonly-probe request gates; paper-write rows now consume the shared lane-scoped IPC contract constant instead of a hard-coded id.
- Phase0 packet spec, broker settings README, and the blocked broker capability template now document the same read-row prerequisite.
- Verification passed: `rustfmt`; broker capability acceptance `10 passed`; full openclaw_types `35` unit/golden + `248` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Policy Status Read-Row Gate Display

- Source/status/display-only checkpoint exposes broker read-row probe gates through Rust `stock_etf.get_policy_status`, FastAPI normalization/fallback, and the Stock/ETF policy GUI panel.
- Policy status now carries `lane_scoped_ipc_contract_id`, `readonly_probe_request_contract_id`, `read_rows_require_lane_scoped_ipc`, and `read_rows_require_readonly_probe_request` under `broker_capability_registry`.
- FastAPI treats an accepted broker capability registry that omits or mismatches those read-row gate claims as `contract_violation_blocked`.
- Verification passed: Python compile PASS; Node syntax PASS; focused policy/static `15 passed`; focused engine policy-status `1 passed`; full Stock/ETF FastAPI/static `94 passed`; engine `stock_etf` filter `29 passed`; workspace `cargo check` PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Read-Only Probe Request Operation Binding

- Source-only IPC checkpoint makes `stock_etf.preview_readonly_probe` derive the top-level broker decision operation from an accepted `stock_etf_ibkr_readonly_probe_request_v1` envelope instead of always using method fallback `health_read`.
- Invalid or parse-failed readonly-probe payloads are not trusted for operation selection and still fall back to the method-level `HealthRead` fixture boundary.
- Added a market-data readonly-probe IPC test proving a valid `market_data_snapshot` request yields top-level `decision.operation=market_data_read` while remaining `allowed=false` with no contact or routing side effects.
- Verification passed: `rustfmt`; readonly-probe IPC focused `3 passed`; engine `stock_etf` filter `30 passed`; workspace `cargo check` PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Plan Timeline Checkpoint Guard

- PM normalized the main IBKR development arrangement so PM session checkpoints are now linear and unique from 14 through 74, aligned to the PM memory / Operator source timeline.
- Added a structure test that reads the main plan Markdown and fails if PM session checkpoint numbers become duplicated, skipped, or out of order.
- Verification passed: focused IBKR timeline structure test `1 passed`; section-body compare against `HEAD` PASS; `git diff --check` PASS. The full structure test file still has pre-existing docs README index drift failures unrelated to this guard. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF PM Memory Traceability Backfill

- PM backfilled main-plan and Operator trace titles for PM memory checkpoints: `Source Posture Header Catch-up`, `Rust Connector Skeleton Readiness Source`, `Read-Only Probe Request Contract`, and `Read-Only Probe Readiness Gate`.
- Added a structure guard requiring those PM memory trace titles to appear in both the main IBKR plan and Operator summary.
- Verification passed: focused IBKR timeline + traceability structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Python Connector Network Static Guard

- PM hardened the Stock/ETF / IBKR Python no-write static guard so the source-only connector skeleton cannot import socket/HTTP/WebSocket client modules or dynamically import IBKR SDK / network modules.
- The guard now covers `socket`, `http.client`, `requests`, `httpx`, `urllib`, `urllib3`, `aiohttp`, `websocket`, and `websockets`, while keeping the scan scoped to Stock/ETF / IBKR Python surfaces rather than existing Bybit connector modules.
- Verification passed: Python no-write static guard `4 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Endpoint Template Consistency Guard

- PM added a FastAPI/GUI contract consistency guard requiring Stock/ETF OpenAPI GET endpoints to match `settings/broker/stock_etf_gui_lane_contract.template.toml` endpoint declarations, excluding the authenticated root redirect.
- The parser covers numeric endpoint keys such as `phase0_status_endpoint`; the guard prevents future route/template drift without adding endpoints or runtime authority.
- Verification passed: Stock/ETF route tests `11 passed`; full Stock/ETF FastAPI/static `96 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Static Endpoint Template Consistency Guard

- PM added a source-only static GUI guard requiring the Stock/ETF GUI bundle endpoint set to match `settings/broker/stock_etf_gui_lane_contract.template.toml` endpoint declarations exactly.
- The guard scans static `tab-stock-etf*` sources for `/api/v1/stock-etf...` strings, preventing future GUI/template drift or accidental extra Stock/ETF API surfaces.
- Verification passed: Python no-write static guard `5 passed`; full Stock/ETF FastAPI/static `97 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Route Auth Coverage Guard

- PM added a route-level auth coverage guard that derives every Stock/ETF GET path from OpenAPI, adds the authenticated root redirect, and verifies each route returns `401` without `current_actor`.
- This prevents future display-only Stock/ETF endpoints from being added without auth while preserving the existing GET-only, no-write route boundary.
- Verification passed: Stock/ETF route tests `12 passed`; full Stock/ETF FastAPI/static `98 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Route Cache Header Coverage Guard

- PM added a route-level cache/header guard that derives every Stock/ETF GET path from OpenAPI, adds the root redirect, and verifies `Cache-Control` is private/no-store with `Pragma: no-cache`, `Expires: 0`, and `Vary: Authorization`.
- This prevents future display-only Stock/ETF endpoints from bypassing auth/cache partitioning or leaking lane-specific status via stale shared caches.
- Verification passed: Stock/ETF route tests `13 passed`; full Stock/ETF FastAPI/static `99 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI IPC Empty Params Guard

- PM added an AST guard proving every `stock_etf_routes.py` IPC status read uses a literal `params={}`, so query/header/client lane claims cannot be forwarded into Rust IPC.
- The guard counts the Stock/ETF IPC calls and fails if any call omits `params` or passes non-empty/non-literal params.
- Verification passed: Python no-write static guard `6 passed`; full Stock/ETF FastAPI/static `100 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Handler Client-State Guard

- PM added an AST guard proving every `@stock_etf_router.get` handler accepts only `response` and/or authenticated `actor`, with `actor` wired through `Depends(base.current_actor)`.
- The guard blocks future route handlers from accepting Request/Header/Query/Body/Cookie/Form-style client state before Rust IPC/status normalization.
- Verification passed: Python no-write static guard `7 passed`; full Stock/ETF FastAPI/static `101 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI IPC Method Allowlist Guard

- PM added an AST guard proving `stock_etf_routes.py` IPC calls use named method constants whose resolved values are exactly the readonly Stock/ETF status/readiness method allowlist.
- The guard blocks future FastAPI GET/status surfaces from calling paper preview/submit/cancel/replace, fill import, shadow evaluation, readonly-probe preview, or any other non-status IPC method.
- Verification passed: Python no-write static guard `8 passed`; full Stock/ETF FastAPI/static `102 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Python Persistence Static Guard

- PM added a source-only AST guard proving Stock/ETF / IBKR Python surfaces do not import persistence, DB, object-store, or local evidence-writer modules.
- The guard also blocks dynamic persistence imports and explicit file-writer calls such as write_text/write_bytes/open-write/os.replace in the scoped Stock/ETF/IBKR Python surface.
- Verification passed: Python no-write static guard `9 passed`; full Stock/ETF FastAPI/static `103 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF OpenAPI Client Input Surface Guard

- PM added a route/OpenAPI guard proving Stock/ETF GET operations expose no request body and no client-state parameters beyond the optional `Authorization` header from existing auth.
- The guard blocks future query/path/header/cookie/body inputs from appearing in the public Stock/ETF OpenAPI contract.
- Verification passed: Stock/ETF route tests `14 passed`; full Stock/ETF FastAPI/static `104 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust Status IPC Untrusted Params Guard

- PM added a Rust IPC regression proving every Stock/ETF status/readiness method returns exactly the same result for `{}` params and malicious non-empty params claiming live, Bybit, paper submit, IBKR contact, secret touch, order routing, and Bybit IPC reuse.
- This extends the client-state-untrusted boundary below FastAPI so direct IPC callers cannot influence status/readiness fixture output through params.
- Verification passed: `rustfmt`; focused engine test `1 passed`; engine `stock_etf` filter `31 passed`; full Stock/ETF FastAPI/static `104 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust Dispatch Registry Routing Guard

- PM moved Rust dispatch for Stock/ETF fixture methods from a duplicated hand-written match arm list to registry-driven `is_stock_etf_fixture_method`.
- The registry helper requires a `stock_etf.` registered method with `slot=None`, keeping Stock/ETF IPC routing tied to the same source of truth that already records readonly/write-fixture metadata and live-token exclusion.
- Verification passed: `rustfmt`; engine `stock_etf` filter `31 passed`; full Stock/ETF FastAPI/static `104 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Data/Policy Fallback Split Guard

- PM split the large Data Foundation / Policy fallback payloads out of the main Stock/ETF GUI bundle into `tab-stock-etf-data-policy.js`, reducing `tab-stock-etf.js` from `1976` to `1805` lines and keeping every Stock/ETF GUI bundle file below the 2000-line governance cap.
- The static no-write guard now scans the new data/policy JS file and includes a line-cap regression for the Stock/ETF GUI bundle; the HTML loads the split before the main loader so existing display-only rendering semantics stay unchanged.
- Verification passed: Stock/ETF JS `node --check`; Python no-write/static guard `10 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust IPC Test Split Guard

- PM split the tail Stock/ETF Rust IPC status fixture tests into `rust/openclaw_engine/src/ipc_server/tests/stock_etf/status_fixtures.rs`, reducing the parent `stock_etf.rs` from `2532` lines to `1852` lines while keeping the child at `685` lines.
- Added a structure guard requiring the Stock/ETF Rust IPC parent and child fixture test files to stay below the 2000-line governance cap, with source-only checks for the moved status fixture methods and forbidden network/IBKR SDK tokens.
- Verification passed: `rustfmt`; engine `stock_etf` filter `31 passed`; Rust IPC split static guard `2 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust IPC Handler Split Guard

- PM split tail Stock/ETF Rust IPC status summary builders from `rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs` into `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries.rs`, reducing the parent handler from `2217` lines to `1292` lines while keeping the child at `934` lines.
- Added a structure guard requiring the Stock/ETF Rust IPC handler parent and child files to stay below the 2000-line governance cap, with source-only checks for the moved status builder functions and forbidden IBKR SDK / network client tokens.
- Verification passed: `rustfmt`; engine `stock_etf` filter `31 passed`; Rust IPC handler/test split static guards `4 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Route Fixture Split Guard

- PM split the oversized Stock/ETF FastAPI route fixture helper into a same-name `stock_etf_route_fixtures/` package with `app.py`, `phase2_payloads.py`, `phase3_payloads.py`, and `phase5_payloads.py`, preserving the existing `from stock_etf_route_fixtures import ...` test import surface.
- The old 1525-line fixture file is replaced by package modules of `57`, `63`, `482`, `629`, and `364` lines, all below the 800-line review-attention threshold.
- Added a route fixture split structure guard requiring the legacy flat helper to stay removed, the package module/export set to remain stable, and payload fixture modules to avoid network/IBKR SDK/file-write tokens.
- Verification passed: route fixture `py_compile`; route fixture split static guard `3 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust IPC Request Contract Test Split Guard

- PM split Stock/ETF Rust IPC paper/fill/shadow/readonly-probe request contract tests from `rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs` into `rust/openclaw_engine/src/ipc_server/tests/stock_etf/request_contracts.rs`.
- The Rust IPC test parent is reduced from `1852` to `1110` lines; `request_contracts.rs` is `745` lines and `status_fixtures.rs` remains `685` lines.
- The Rust IPC split structure guard now requires exactly `request_contracts.rs` and `status_fixtures.rs`, caps each parent/child test file at `1200` lines, and keeps both child modules free of network/IBKR SDK tokens.
- Verification passed: `rustfmt`; engine `stock_etf` filter `31 passed`; Rust IPC test split static guard `3 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust IPC Handler Request Summary Split Guard

- PM split Stock/ETF Rust IPC request parsing and source-only paper/fill/shadow/readonly-probe summary helpers from `rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs` into `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/request_summaries.rs`.
- The production handler parent is reduced from `1292` to `823` lines; `request_summaries.rs` is `477` lines and `status_summaries.rs` remains `934` lines.
- The handler split structure guard now requires exactly `request_summaries.rs` and `status_summaries.rs`, caps parent/child handler files at `1200` lines, and keeps both child modules free of network/IBKR SDK tokens.
- Verification passed: `rustfmt --check`; engine `stock_etf` filter `31 passed`; Rust IPC handler/test split static guards `6 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, dispatch route, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Route IPC Query Helper Guard

- PM collapsed 16 duplicated `stock_etf_routes.py` IPC status query helpers into one central `_query_stock_etf_status(ipc, method)` helper while preserving every endpoint, method constant, normalizer, response envelope, and auth/no-store behavior.
- `stock_etf_routes.py` is reduced from `587` to `393` lines; the Python no-write static guard now proves there is exactly one `ipc.call(method, params={})` site and that all 16 route handlers invoke it only with allowlisted readonly Stock/ETF method constants.
- Verification passed: route/no-write focused tests `24 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, client input, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI Fallback Payload Split Guard

- PM split the remaining large display-only fallback payload builders out of `tab-stock-etf.js` into `tab-stock-etf-fallbacks.js`: authorization, account, evidence, universe, shadow, paper, scorecard, and launch.
- The main Stock/ETF GUI bundle is reduced from `1805` to `1244` lines; the new fallback module is `563` lines, loaded before the main loader, and all endpoint/rendering semantics remain display-only.
- The static no-write guard now scans the new fallback module and proves the large fallback builders stay out of the main bundle, with `tab-stock-etf.js <= 1400` and `tab-stock-etf-fallbacks.js <= 800`.
- Verification passed: Stock/ETF JS `node --check`; route/no-write focused tests `25 passed`; full Stock/ETF FastAPI/static `106 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, client input, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI Data/Policy Renderer Split Guard

- PM moved the Data Foundation and Policy panel renderers from `tab-stock-etf.js` into the existing `tab-stock-etf-data-policy.js` display-only module, keeping the fallback payloads and renderers together.
- The main Stock/ETF GUI bundle is reduced from `1244` to `985` lines; `tab-stock-etf-data-policy.js` grows from `170` to `469` lines with local UI helpers consistent with the other split Stock/ETF modules.
- The static no-write guard now proves `renderDataFoundationStatus` and `renderPolicyStatus` stay out of the main bundle, with `tab-stock-etf.js <= 1100` and `tab-stock-etf-data-policy.js <= 700`.
- Verification passed: Stock/ETF JS `node --check`; route/no-write focused tests `26 passed`; full Stock/ETF FastAPI/static `107 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, client input, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI Authorization/Account Renderer Split Guard

- PM moved the Authorization and Account panel renderers from `tab-stock-etf.js` into new display-only module `tab-stock-etf-auth-account.js`.
- The main Stock/ETF GUI bundle is reduced from `985` to `798` lines; `tab-stock-etf-auth-account.js` is `235` lines and exposes `window.renderAuthorizationStatus` / `window.renderAccountStatus` for the main loader.
- The static no-write guard now scans the auth/account module and proves `renderAuthorizationStatus` and `renderAccountStatus` stay out of the main bundle, with `tab-stock-etf.js <= 900` and `tab-stock-etf-auth-account.js <= 400`.
- Verification passed: Stock/ETF JS `node --check`; route/no-write focused tests `27 passed`; full Stock/ETF FastAPI/static `108 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, client input, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI Evidence/Paper Renderer Split Guard

- PM moved the Evidence, Universe, Shadow, and Paper panel renderers from `tab-stock-etf.js` into new display-only module `tab-stock-etf-evidence-paper.js`.
- The main Stock/ETF GUI bundle is reduced from `798` to `583` lines; `tab-stock-etf-evidence-paper.js` is `265` lines and exposes `window.renderEvidenceStatus` / `window.renderUniverseStatus` / `window.renderShadowStatus` / `window.renderPaperStatus` for the main loader.
- The static no-write guard now scans the evidence/paper module and proves those renderers stay out of the main bundle, with `tab-stock-etf.js <= 650` and `tab-stock-etf-evidence-paper.js <= 500`.
- Verification passed: Stock/ETF JS `node --check`; route/no-write focused tests `28 passed`; full Stock/ETF FastAPI/static `109 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, client input, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI Scorecard/Launch Renderer Split Guard

- PM moved the Scorecard and Launch panel renderers from `tab-stock-etf.js` into new display-only module `tab-stock-etf-scorecard-launch.js`.
- The main Stock/ETF GUI bundle is reduced from `583` to `350` lines; `tab-stock-etf-scorecard-launch.js` is `281` lines and exposes `window.renderScorecardStatus` / `window.renderLaunchStatus` for the main loader.
- The static no-write guard now scans the scorecard/launch module and proves those renderers stay out of the main bundle, with `tab-stock-etf.js <= 400` and `tab-stock-etf-scorecard-launch.js <= 500`.
- Verification passed: Stock/ETF JS `node --check`; route/no-write focused tests `29 passed`; full Stock/ETF FastAPI/static `110 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, client input, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI Readiness Renderer Split Guard

- PM moved the lane/readiness boundary renderer and its local UI helpers from `tab-stock-etf.js` into new display-only module `tab-stock-etf-readiness.js`.
- The main Stock/ETF GUI bundle is reduced from `350` to `197` lines; `tab-stock-etf-readiness.js` is `159` lines and exposes `window.renderReadiness` for the main loader/fallback path.
- The static no-write guard now scans the readiness module and proves `renderReadiness` plus shared helper definitions stay out of the main bundle, with `tab-stock-etf.js <= 250` and `tab-stock-etf-readiness.js <= 250`.
- Verification passed: Stock/ETF JS `node --check`; route/no-write focused tests `30 passed`; full Stock/ETF FastAPI/static `111 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, client input, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-07-01 Fresh Invocation-Window Source Preflight Blocked

- PM established session loop state sha `e6724c79a45b187e1c020065cf6c445950bafcf01daf923e9e73e94afbad7a2d` for `P0-CURRENT-CANDIDATE-FRESH-INVOCATION-WINDOW-LEASE-BBO-ORDER-SHAPE-GATE` and ran only the corrected dry-run with `PYTHONPATH=helper_scripts/research`.
- Dry-run sha `148deaecd3e7423d1ecf207c5d8f715e48f6773e95f676500e1e05299237e6b6` is `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_SOURCE_NOT_READY`; source blockers are stale current-candidate envelope plus missing/mismatched pre-active sizing-aware gate evidence.
- E3 returned `BLOCKED`; BB accepted public Bybit market-data GET scope in principle but also blocked `--run` until source inputs dry-run ready. Boundary: no lease, public quote, Bybit call, order/cancel/modify, PG access, runtime mutation, service restart, Cost Gate change, live/mainnet, fill/PnL, or proof.
- TODO v688 active blocker is `P0-CURRENT-CANDIDATE-FRESH-INVOCATION-WINDOW-SOURCE-INPUT-REFRESH-GATE`.

## 2026-07-01 IBKR Stock/ETF Python Secret/Env Access Static Guard

- PM added a source-only AST guard proving Stock/ETF / IBKR Python surfaces do not import env/secret helper modules or read secret/environment material.
- The guard blocks `os` imports, `dotenv`/`getpass`/`keyring`, `os.environ`, `getenv`/`os.getenv`, `Path.home`, `expanduser`, `read_text`, `read_bytes`, and any `open()` call in the scoped surface while preserving display-only secret-slot schema normalization.
- Verification passed: Python no-write static guard `17 passed`; route/no-write focused tests `31 passed`; full Stock/ETF FastAPI/static `112 passed`; IBKR timeline + trace-title guard `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, client input, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Rust IPC Secret/Env Material Static Guard

- PM added Rust split structure guards proving Stock/ETF IPC handler/test files do not introduce direct `std::env`/`env::var`, secret-file/material readers, network/socket clients, or direct IBKR SDK tokens.
- The handler guard explicitly preserves exactly one typed `StockEtfFeatureFlags::from_env()` path in the parent handler while forbidding bypass reads in `stock_etf.rs`, `request_summaries.rs`, and `status_summaries.rs`.
- Verification passed: Rust IPC split static guards `8 passed`; docs trace guard `2 passed`; full Stock/ETF FastAPI/static `112 passed`; `git diff --check` PASS. This grants no Rust runtime behavior change, no endpoint/IPC method change, no IBKR contact, no SDK import, no socket/HTTP, no secret access, no read probe execution, no paper order, no DB/evidence writer, no tiny-live/live, and no Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Rust Feature Flag Env Allowlist Guard

- PM added a Rust acceptance regression proving `StockEtfFeatureFlags::from_lookup` queries exactly five non-secret feature flag keys and falls back to default-off posture when all keys are absent.
- The allowed keys are lane enabled, IBKR readonly enabled, IBKR paper enabled, asset-lane default, and stock/ETF shadow-only; the test rejects secret/token/password/account/key-bearing names.
- Verification passed: file `rustfmt --check`; `stock_etf_lane_acceptance` `9 passed`; docs trace guard `2 passed`; full Stock/ETF FastAPI/static `112 passed`; `git diff --check` PASS. Workspace-wide `cargo fmt --all -- --check` remains blocked by pre-existing unrelated Rust formatting drift outside this IBKR slice.

## 2026-07-01 IBKR Stock/ETF Connector Preview Payload Guard

- PM made `IbkrReadOnlyClient.connection_plan()` explicitly fail closed with `surface_id`, `accepted=false`, `status=blocked_source_only`, `phase2_gate_not_accepted`, and `connection_plan_blocked`.
- PM added an exact payload-shape regression for the inert IBKR connector skeleton covering connection plan, readiness, account snapshot, market data, contract details, paper lifecycle, fill import, and static fixture previews.
- The guard fixes all preview payloads to secret-free/no-network/no-paper-channel/no-live/no-write/no-Bybit-reuse posture while preserving the existing source-only connector boundary.
- Verification passed: connector skeleton tests `5 passed`; Python no-write static guard `17 passed`; full Stock/ETF FastAPI/static `113 passed`; docs trace guard `2 passed`; `git diff --check` PASS. This grants no endpoint, IPC method, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order, fill import, DB/evidence writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Connector Bybit Import Separation Guard

- PM added an AST guard proving the inert IBKR connector skeleton does not import Bybit connector, control-api `app`, or `program_code.exchange_connectors.bybit_connector` modules.
- The guard scans direct imports and literal dynamic imports via `__import__` / `importlib.import_module` across `program_code/broker_connectors/ibkr_connector/*.py`.
- This keeps the IBKR skeleton isolated under `program_code/broker_connectors/ibkr_connector/` and prevents accidental reuse of Bybit runtime/control-api code while preserving the existing `bybit_path_reused=false` payload field.
- Verification passed: connector skeleton tests `6 passed`; Python no-write static guard `17 passed`; full Stock/ETF FastAPI/static `114 passed`; docs trace guard `2 passed`; `git diff --check` PASS. This grants no endpoint, IPC method, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order, fill import, DB/evidence writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF FastAPI IBKR Connector Runtime Wiring Guard

- PM added a production-surface AST guard proving Stock/ETF/control-api Python files do not import the inert IBKR connector skeleton before runtime approval.
- The guard scans `control_api_v1/app` Stock/ETF/IBKR files only, while allowing dedicated skeleton tests to import the package.
- Literal dynamic imports are also checked through the shared dynamic import helper, including `importlib.import_module`.
- Verification passed: Python no-write static guard `18 passed`; connector skeleton tests `6 passed`; full Stock/ETF FastAPI/static `115 passed`; docs trace guard `2 passed`; `git diff --check` PASS. This grants no endpoint, IPC method, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order, fill import, DB/evidence writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Rust IPC Bybit Runtime Separation Guard

- PM added Rust split structure guards proving Stock/ETF IPC handler/test source does not import or call Bybit REST/WS/Earn clients, order manager/router, paper state, bounded-probe active-order module, legacy paper submit handler, or direct order method call tokens.
- The handler guard scans `stock_etf.rs`, `request_summaries.rs`, and `status_summaries.rs`; the fixture guard scans parent `stock_etf.rs`, `request_contracts.rs`, and `status_fixtures.rs`.
- Contract-level negative posture fields such as `bybit_ipc_reused=false`, `bybit_path_reused=false`, and legacy Bybit channel regression text remain allowed; the guard blocks runtime code-path coupling.
- Verification passed: Rust IPC split static guards `10 passed`; full Stock/ETF FastAPI/static `115 passed`; docs trace guard `2 passed`; `git diff --check` PASS. This grants no Rust runtime behavior change, endpoint/IPC method change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order/cancel/replace, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Connector Public API Freeze Guard

- PM added exact package/class public-surface guards for the inert IBKR connector skeleton.
- The package `__all__` is frozen to the source-only surface id, read-only client, paper boundary client, endpoint config, and surface status; the read-only client public surface is limited to config/readiness/preview methods; the paper boundary public surface is limited to lifecycle and fill-import readiness descriptors.
- This supplements the existing forbidden write-method guard by preventing future runtime-start, order-write, secret/network, or Bybit-reuse entrypoints from appearing under alternative public method names.
- Verification passed: connector skeleton tests `8 passed`; Python no-write static guard `18 passed`; full Stock/ETF FastAPI/static `117 passed`; docs trace guard `2 passed`; `git diff --check` PASS. This grants no endpoint/IPC method change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order/cancel/replace, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Python Runtime Side-Effect Static Guard

- PM added an AST guard proving the scoped Stock/ETF / IBKR Python surface does not import clock/concurrency/subprocess modules or call timing/background-work primitives.
- The guard bans `time`, `datetime`, `asyncio`, `threading`, `multiprocessing`, `subprocess`, and `concurrent` imports plus `sleep`, `time`, `monotonic`, `perf_counter`, `now`, `utcnow`, `fromtimestamp`, `Thread`, `Process`, `Popen`, `run`, `create_task`, and `to_thread` calls in the scoped surface.
- Scope remains only Stock/ETF FastAPI routes/normalizers and the inert IBKR connector skeleton, preserving existing Bybit runtime modules.
- Verification passed: Python no-write static guard `19 passed`; connector skeleton tests `8 passed`; full Stock/ETF FastAPI/static `118 passed`; docs trace guard `2 passed`; `git diff --check` PASS. This grants no endpoint/IPC method change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order/cancel/replace, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Rust IPC Runtime Side-Effect Static Guard

- PM added Rust split structure guards proving Stock/ETF IPC handler/test source does not import or call clock/thread/task/process side-effect primitives.
- The guard bans `std::time`, `SystemTime`, `Instant`, `chrono`, `Utc::now`, `Local::now`, `std::thread`, `thread::spawn`, `tokio::spawn`, `tokio::task`, `tokio::time`, `sleep(`, `std::process`, `process::Command`, `Command::new`, and `.spawn(` in scoped handler/test files.
- Scope remains only Stock/ETF IPC handler parent/children and Stock/ETF IPC fixture test parent/children.
- Verification passed: Rust IPC split static guards `12 passed`; full Stock/ETF FastAPI/static `118 passed`; docs trace guard `2 passed`; `git diff --check` PASS. This grants no Rust runtime behavior change, endpoint/IPC method change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order/cancel/replace, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI Background Work Static Guard

- PM added a static GUI guard proving Stock/ETF display files do not introduce polling, push channels, workers, XHR/sendBeacon, or high-frequency timing primitives.
- The guard scans `tab-stock-etf*.js` and `tab-stock-etf.html`, blocking `setInterval`, `setTimeout`, animation/idle callbacks, WebSocket, EventSource, Worker/SharedWorker, BroadcastChannel, XMLHttpRequest, sendBeacon, `performance.now`, and `Date.now`.
- Existing one-shot authenticated GET loading remains allowed; `new Date().toLocaleTimeString()` remains display-only and does not start background work.
- Verification passed: Python no-write static guard `20 passed`; full Stock/ETF FastAPI/static `119 passed`; docs trace guard `2 passed`; `git diff --check` PASS. This grants no endpoint/IPC method change, client input change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order/cancel/replace, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI One-Shot Fanout Budget Guard

- PM added a static GUI guard proving `tab-stock-etf.js` keeps exactly one one-shot load path: one `Promise.all`, one `waitForServerUp(loadReadiness)`, and 16 `ocApi` calls.
- Every Stock/ETF GUI `ocApi` call must be GET-only with `timeoutMs: 5000` and `toastOnError: false`.
- This prevents future display-only GUI drift into extra API fanout, longer timeout budgets, or repeated loaders before runtime approval.
- Verification passed: Python no-write static guard `21 passed`; full Stock/ETF FastAPI/static `120 passed`; docs trace guard `2 passed`; `git diff --check` PASS. This grants no endpoint/IPC method change, client input change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order/cancel/replace, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Collector Run Contract

- PM added source-only `stock_etf_collector_run_v1` and raised the Phase0 named contract count to 34, tying future collector evidence to 5 green trading sessions plus PIT universe, market-data provenance, reference-data, storage-capacity, gap, DQ, replay, and source-artifact hashes.
- Existing `stock_etf.get_evidence_status`, FastAPI normalization/fallback, and the GUI evidence panel now expose a default-blocked `collector_run` block without adding endpoints, IPC methods, GUI fanout, or runtime/background work.
- Verification passed: Python compile, Stock/ETF JS `node --check`, scoped Rust `rustfmt`, full Stock/ETF FastAPI/static `120 passed`, full `openclaw_types` `287` tests, engine Stock/ETF focused `31 passed`, docs trace guard `2 passed`, and `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, collector start, market-data ingestion, paper order/cancel/replace, fill import, DB/evidence/scorecard writer, evidence clock, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF DQ Manifest Contract

- PM added source-only `stock_etf_dq_manifest_v1` and raised the Phase0 named contract count to 35, tying future daily DQ evidence to exact contract id/source version, Stock/ETF IBKR paper/shadow identity, collector run id, market-data provenance lineage, source artifact hash, coverage/completeness/latency/quality fields, and Bybit-live unchanged proof.
- Existing `stock_etf.get_evidence_status`, FastAPI normalization/fallback, and the GUI evidence panel now expose default-blocked `dq_manifest` contract status without adding endpoints, IPC methods, GUI fanout, runtime/background work, or a DQ writer.
- Verification passed: Python compile, Stock/ETF JS `node --check`, scoped Rust `rustfmt`, Phase3 evidence acceptance `19 passed`, Phase0 manifest acceptance `6 passed`, focused Phase0/Evidence/Route pytest `22 passed`, full Stock/ETF FastAPI/static `120 passed`, full `openclaw_types` PASS, engine Stock/ETF focused `31 passed`, docs trace guard `2 passed`, and `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, collector start, market-data ingestion, DQ writer, paper order/cancel/replace, fill import, DB/evidence/scorecard writer, evidence clock, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Evidence Clock Lineage Guard

- PM hardened source-only `stock_etf_evidence_clock_v1` so evidence-clock day artifacts carry collector-run and DQ-manifest contract id/hash lineage.
- Existing evidence-status IPC/FastAPI/GUI surfaces now expose default-blocked evidence-clock collector/DQ/source/provenance/scorecard input hash presence without adding endpoints, IPC methods, GUI fanout, runtime work, or an evidence clock.
- Verification passed: Python compile, JS syntax, scoped Rust format, Phase3 evidence acceptance `19 passed`, Phase0 manifest acceptance `6 passed`, and focused evidence-status pytest `4 passed`.
- Boundary unchanged: no IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, collector start, market-data ingestion, DQ writer, paper order/cancel/replace, fill import, DB/evidence/scorecard writer, evidence clock, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Phase3 Evidence Module Split Guard

- PM split Phase3 market-data provenance and frozen-input contracts into `stock_etf_phase3_evidence/market_data.rs` while preserving the parent module public re-export surface.
- `stock_etf_phase3_evidence.rs` dropped from 982 to 742 lines; the new child module is 254 lines.
- Verification passed: scoped Rust format, Phase3 evidence acceptance `19 passed`, Phase0 manifest acceptance `6 passed`, full Stock/ETF FastAPI/static `120 passed`, full `openclaw_types` PASS, engine Stock/ETF focused PASS, docs trace `2 passed`, and `git diff --check` PASS.
- Boundary unchanged: no contract behavior, endpoint, IPC, GUI payload, IBKR contact, runtime, order, DB/evidence writer, evidence clock, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Connector Attestation Preview Guard

- PM added inert Python connector skeleton session and paper attestation preview payloads plus blocked fixtures, preserving source-only/no-network/no-secret/no-Bybit posture.
- `IbkrReadOnlyClient.session_attestation_preview()` and `IbkrPaperClientBoundary.paper_attestation_preview()` now return typed blocked dicts for future Phase 2 gate wiring.
- Verification passed: Python compile, connector skeleton focused test `8 passed`, full Stock/ETF FastAPI/static `120 passed`, docs trace `2 passed`, and `git diff --check` PASS.
- Boundary unchanged: no endpoint, IPC, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe, paper order, fill import, DB/evidence writer, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Read-Only Probe Result Import Request Contract

- PM added source-only `stock_etf_ibkr_readonly_probe_result_import_request_v1` to bind future sanitized read-only probe outputs back to the pre-contact request, session attestation, allowlist, redaction/audit policy, result payload, raw/redacted/source artifacts, as-of/import-request timestamps, idempotency, and one downstream evidence family.
- Probe kind-specific lineage now covers health snapshot, `broker_account_portfolio_cash_ledger_v1`, `stock_market_data_provenance_v1`, `instrument_identity_contract_v1`, and `broker_lifecycle_event_log_v1`.
- Phase0 manifest/JSON now moves from 35 to 36 named contracts, and broker capability `scorecard_derive` now requires readonly probe result import request lineage before scorecard facts can be considered complete.
- Verification passed: scoped Rust format; result import request acceptance `6 passed`; Phase0 manifest acceptance `6 passed`; broker capability registry acceptance `10 passed`; full `cargo test -p openclaw_types` PASS; full Stock/ETF FastAPI/static pytest `120 passed`; focused docs trace `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, result import, collector, market-data ingestion, DQ writer, paper order/cancel/replace, fill import, DB/evidence writer, evidence clock, scorecard writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Lane-Scoped IPC Source Static Guard

- PM added a source-only structure guard for `stock_etf_lane_scoped_ipc.rs`, keeping the lane-scoped IPC contract below 800 lines while proving the 20-method matrix, denied sentinels, and lane/auth/Phase2/session/non-Bybit/secret-topology/broker-registry/asset-lane contract tokens remain present.
- The guard bans env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens in the contract source, preventing source drift into runtime authority.
- Verification passed: new guard `3 passed`; lane-scoped IPC acceptance `9 passed`; full `cargo test -p openclaw_types` PASS. This grants no IPC runtime, IBKR contact, connector runtime, secret access, read probe, result import, paper order/cancel/replace, fill import, DB/evidence/scorecard writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Lane Source Static Guard

- PM added a source-only structure guard for `stock_etf_lane.rs`, keeping the lane taxonomy, broker/env/instrument/authority surfaces, 15 broker operations, 20 denial variants, 13 gate fields, and live/margin/options/CFD/account-write typed denials pinned.
- The guard allows only the existing `StockEtfFeatureFlags::from_env()` single `std::env::var(key).ok()` path over five non-secret feature flag keys, and rejects fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime plus secret/account material tokens.
- Verification passed: new guard `4 passed`; Stock/ETF lane acceptance `9 passed`; full `cargo test -p openclaw_types` PASS. This grants no feature enablement, IBKR contact, connector runtime, secret access, read probe, result import, paper order/cancel/replace, DB/evidence/scorecard writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 IBKR Phase2 Gate Source Static Guard

- PM added a source-only structure guard for `ibkr_phase2_gate.rs`, pinning ADR/AMD, external-surface gate, session attestation, paper/live port constants, gate fields/blockers, session attestation fields/blockers, and loopback/paper-port/live-port/env-fallback/staleness checks.
- The guard rejects env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens plus secret material access tokens, keeping Phase 2 gate source as data validation only.
- Verification passed: new guard `4 passed`; Phase2 gate acceptance `11 passed`; full `cargo test -p openclaw_types` PASS. This grants no external-surface PASS, session runtime, IBKR contact, connector runtime, secret access, read probe, result import, paper order, DB/evidence/scorecard writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 IBKR Phase2 Runtime Source Static Guard

- PM added a source-only structure guard for `ibkr_phase2_runtime.rs`, pinning secret-slot and API-session-topology contract IDs, secret posture/gateway mode/verdict/blocker types, hashed paper slot, absent live slot, owner-only permission, env fallback denial, and loopback paper gateway topology.
- The guard rejects env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens plus secret material access tokens, keeping the file as evidence-shape validation rather than a secret reader or gateway starter.
- Verification passed: new guard `4 passed`; Phase2 runtime acceptance `7 passed`; full `cargo test -p openclaw_types` PASS. This grants no secret read, gateway/TWS start, API topology probe, IBKR contact, connector runtime, paper order, DB/evidence/scorecard writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 IBKR Phase2 Artifact Source Static Guard

- PM added a source-only structure guard for `ibkr_phase2_artifact.rs`, pinning artifact fields, blocker/verdict surface, PM/Operator reviewer checks, policy-flag cross-checks, secret-slot/API-topology runtime contract cross-checks, fail-closed defaults, and retroactive call denial.
- The guard rejects env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens plus secret material access tokens, keeping the file as a PASS-artifact validator rather than artifact materialization or IBKR contact.
- Verification passed: new guard `4 passed`; Phase2 artifact acceptance `8 passed`; full `cargo test -p openclaw_types` PASS. This grants no external-surface PASS, artifact seal, IBKR contact, connector runtime, secret access, paper order, DB/evidence/scorecard writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 IBKR Feature Flag Secret Auth Source Static Guard

- PM added a source-only structure guard for `ibkr_feature_flag_secret_auth.rs`, pinning the feature flag, secret-slot contract, Phase2 artifact, session attestation, and authorization envelope decision matrix.
- The guard requires fail-closed defaults, live/account-write denial, paper flag and shadow-only checks, secret/artifact/session validation, envelope scope/hash/expiry checks, and secret/account fingerprint consistency across secret/artifact/session contracts.
- Verification passed: new guard `5 passed`; feature-flag/secret auth acceptance `8 passed`; full `cargo test -p openclaw_types` PASS. This grants no feature enablement, secret read, IBKR contact, connector runtime, paper order authorization, DB/evidence/scorecard writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 IBKR Non-Bybit API Allowlist Source Static Guard

- PM added a source-only structure guard for `ibkr_non_bybit_api_allowlist.rs`, pinning the IBKR non-Bybit API action allowlist/deny matrix.
- The guard requires 10 read actions, 3 paper-write actions, 10 denied actions, 10 typed denial reasons, paper-write gate/session/order-gate requirements, live/account/client-portal typed denials, action missing/duplicated/wrong-bucket detection, retroactive contact denial, secret serialization denial, and Bybit live execution protection.
- Verification passed: new guard `5 passed`; Phase2 gate/allowlist acceptance `11 passed`; full `cargo test -p openclaw_types` PASS. This grants no external-surface PASS, IBKR client construction, read probe, paper order submission/cancel/replace, secret access, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Broker Capability Registry Source Static Guard

- PM added a source-only structure guard for `stock_etf_broker_capability_registry.rs`, pinning the Stock/ETF IBKR broker operation capability matrix.
- The guard requires 15 operations, audit fields, fail-closed defaults, StockEtfCash/IBKR accepted fixture boundaries, read-only gates, paper-write PaperRehearsal/Rust-owned gates, shadow/scorecard lineage gates, live/margin/options/CFD/account-write denied scopes and typed denials, plus no runtime/secret/order/Bybit client tokens.
- Verification passed: new guard `5 passed`; broker capability registry acceptance `10 passed`; full `cargo test -p openclaw_types` PASS. This grants no broker registry activation, IBKR contact, read probe, paper order authorization, secret access, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Risk Policy Source Static Guard

- PM added a source-only structure guard for `stock_etf_risk_policy.rs`, pinning the dormant Stock/ETF cash risk-policy contract and source config shape.
- The guard requires fail-closed defaults, StockEtfCash/IBKR Paper accepted fixture with `enabled=false` and `shadow_only=true`, cash-only instrument controls, cap ordering and open-order/position limits, universe/identity/market-session gates, cost-model gates, paper-order authority/session/lease/guardian/idempotency/reconciliation gates, and no runtime/secret/order/Bybit client tokens.
- Verification passed: new guard `5 passed`; risk policy acceptance `8 passed`; full `cargo test -p openclaw_types` PASS. This grants no risk policy runtime enablement, IBKR contact, connector start, paper order authorization, secret access, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Paper Order Request Source Static Guard

- PM added a semantic source-only structure guard for `stock_etf_paper_order_request.rs` and its validation module, beyond the existing split guard.
- The guard requires fail-closed defaults, preview ReadOnly/effect=false, submit/cancel/replace PaperRehearsal/effect=true, request/hash/decision-lease/audit requirements, Stock/ETF-only normalized order intent, price/TIF compatibility, method-specific pollution blockers, and no runtime/secret/order/Bybit client tokens.
- Verification passed: new guard `5 passed`; split+semantic paper-order structure guards `8 passed`; paper order request acceptance `8 passed`; full `cargo test -p openclaw_types` PASS. This grants no IPC runtime, IBKR contact, connector start, paper order route, secret access, tiny-live/live, or Bybit behavior change.

## 2026-07-01 IBKR Paper Lifecycle Source Static Guard

- PM added a source-only structure guard for `ibkr_paper_lifecycle.rs`, pinning the paper order lifecycle and append-only event-log contract.
- The guard requires contract ids, event fields, fail-closed default, accepted ack lineage, genesis/hash rules, StockEtfCash/IBKR/Paper checks, live denial, paper lifecycle operation and transition gating, StateUnknown recovery rules, denied-event semantics, stale-state policy matching, restart recovery fail-closed classification, and no runtime/secret/order/Bybit client tokens.
- Verification passed: new guard `6 passed`; paper lifecycle acceptance `12 passed`; full `cargo test -p openclaw_types` PASS. This grants no IBKR contact, connector construction, paper order route, lifecycle writer, secret access, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Paper Fill Import Request Source Static Guard

- PM added a source-only structure guard for `stock_etf_paper_fill_import_request.rs`, pinning the paper fill import request envelope after paper lifecycle events.
- The guard requires fail-closed defaults, accepted ReadOnly/effect=false shape, lifecycle/event-log/redaction/session/source hashes, reconciliation/broker/execution/commission/idempotency identifiers, stale StateUnknown policy handling, duplicate-import denial, no-side-effect boundary flags, and no runtime/secret/order/Bybit client tokens.
- Verification passed: new guard `6 passed`; paper fill import request acceptance `6 passed`; full `cargo test -p openclaw_types` PASS. This grants no IBKR contact, connector construction, fill import execution, DB apply, paper order route, secret access, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Paper Shadow Reconciliation Source Static Guard

- PM added a source-only structure guard for `stock_etf_paper_shadow_reconciliation.rs`, pinning the paper fill to synthetic shadow fill reconciliation envelope.
- The guard requires fail-closed defaults, accepted ReadOnly/effect=false paper_shadow shape, lineage hashes, append-only event readiness, imported paper-fill and synthetic shadow-fill separation, divergence threshold checks, unmatched-fill denial, no writer/DB/order/runtime flags, and no runtime/secret/order/Bybit client tokens.
- Verification passed: new guard `7 passed`; paper shadow reconciliation acceptance `5 passed`; full `cargo test -p openclaw_types` PASS. This grants no IBKR contact, connector construction, fill import, shadow-fill generation, reconciliation/scorecard writer, DB apply, paper order route, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Shadow Signal Request Source Static Guard

- PM added a source-only structure guard for `stock_etf_shadow_signal_request.rs`, pinning the shadow signal request envelope before paper-shadow reconciliation.
- The guard requires fail-closed defaults, accepted StockEtfCash/IBKR/Shadow `EvaluateShadowSignal` shape, ShadowOnly/effect=false authority, evidence clock/PIT universe/strategy/instrument/market-data/cost/asset-lane/source lineage hashes, no shadow emission/writer/order/runtime flags, and no runtime/secret/order/Bybit client tokens.
- Verification passed: new guard `6 passed`; shadow signal request acceptance `5 passed`; full `cargo test -p openclaw_types` PASS. This grants no IBKR contact, connector construction, shadow signal emission, shadow-fill generation, scorecard writer, DB apply, paper order route, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Scorecard Inputs Source Static Guard

- PM added a source-only structure guard for the split `stock_etf_scorecard_inputs` parent/components/bundle modules.
- The guard requires scorecard input contract ids, storage capacity caps, cash ledger Paper/ReadOnly checks, cost/benchmark/shadow-fill validators, synthetic shadow fill separation, storage retention/archive/query-SLO gates, derived-only bundle posture, cross-contract hashes, Bybit-live protection, no evidence clock/writer/DB/runtime flags, and no runtime/secret/order/Bybit client tokens.
- Verification passed: new guard `7 passed`; scorecard inputs acceptance `12 passed`; full `cargo test -p openclaw_types` PASS. This grants no IBKR contact, broker fill import, scorecard derivation/writer, evidence clock, DB apply, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Scorecard Derivation Source Static Guard

- PM added a source-only structure guard for `stock_etf_scorecard_derivation.rs`, pinning sealed derived scorecard artifact lineage.
- The guard requires fail-closed defaults, accepted StockEtfCash/IBKR/Paper sealed shape, id/run/as-of lineage, scorecard input/evidence clock/DQ/reconciliation/formula/preregistration/manifest/verdict/source/code/output/review hashes, atomic-facts-only and idempotent replay proof, paper-shadow separation, Bybit-live protection, no writer/DB/evidence-clock/runtime flags, and no runtime/secret/order/Bybit client tokens.
- Verification passed: new guard `6 passed`; scorecard derivation acceptance `5 passed`; full `cargo test -p openclaw_types` PASS. This grants no IBKR contact, broker fill import, shadow-fill generation, reconciliation/scorecard writer, evidence clock, DB apply, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Scorecard Verdict Source Static Guard

- PM added a source-only structure guard for `stock_etf_scorecard_verdict.rs`, pinning the statistical scorecard verdict before any future tiny-live ADR discussion.
- The guard requires fail-closed defaults, profitability-feasible fixture statistics, verdict label dispatch, formula/preregistration/reconciliation/hash lineage, window and independent-observation thresholds, divergence/PSR/DSR/LCB gates, quality labels, execution-model-invalid failure evidence, QC/MIT/QA review gates, no writer/DB/evidence-clock/tiny-live/runtime flags, and no runtime/secret/order/Bybit client tokens.
- Verification passed: new guard `7 passed`; scorecard verdict acceptance `8 passed`; full `cargo test -p openclaw_types` PASS. This grants no IBKR contact, scorecard writer, evidence clock, DB apply, tiny-live/live authorization, gate lowering, or Bybit behavior change.

## 2026-07-01 Stock/ETF Tiny-Live Eligibility Source Static Guard

- PM added a source-only structure guard for `stock_etf_tiny_live_eligibility.rs`, pinning the future ADR discussion-only gate.
- The guard requires release ADR/AMD/spec paths, fail-closed default NotEligible posture, accepted AdrDiscussionOnly fixture, phase5/scorecard/reconciliation/DQ/preregistration/review hashes, paper-shadow window/statistics/review gates, explicit TinyLiveAuthorized and LiveAuthorized rejection, secret serialization denial, sealed requirement, and no runtime/secret/order/Bybit client tokens.
- Verification passed: new guard `6 passed`; tiny-live eligibility acceptance `7 passed`; full `cargo test -p openclaw_types` PASS. This grants no tiny-live/live authorization, IBKR contact, secret access, connector runtime, evidence clock, Bybit gate lowering, or Bybit behavior change.
