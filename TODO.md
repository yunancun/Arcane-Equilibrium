# Xuanheng TODO - Active Dispatch Queue

**Version** v533 | **Date** 2026-06-26
**Source / runtime pointer**: Mac/origin `main` was clean at `5df11b84628bc887005b4888c21792a1cdfff85f` before this source-only CSRF helper checkpoint; Linux runtime remains clean at `d2cd70d092916194043e112eeb402fb92bacb699` with no source sync, rebuild, restart, crontab/env mutation, PG write, or Rust writer/adapter enablement.
**Current mainline**: `P1-RUNTIME-HEALTH-HYGIENE-API-CSRF-CLI-INVOKER` is closed as `DONE_WITH_CONCERNS`; no cleanup POST or exchange mutation was retried. Per operator request, pause after this round. On resume, the next executable blocker is the refreshed `P0` demo residual cleanup action review.
**Evidence links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--api_csrf_cli_invoker_source_patch.md`; prior CSRF blocker report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_action_csrf_block.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source / cron | 2026-06-26T01:50:28Z read-only check: Linux repo clean at `d2cd70d0`; crontab expected-head occurrences `d2cd70d0=11`, new Mac source `5df11b84=0`; adapter flag count `0`; `OPENCLAW_ALLOW_MAINNET=1` count `0`. | No runtime sync/restart/rebuild was done. v533 helper is source-only until a separate runtime/source-sync review. |
| CSRF helper proof | 2026-06-26 source helper `helper_scripts/operator/control_api_csrf_post.py` added. Focused tests `16 passed`, `py_compile` PASS, `git diff --check` PASS. No-route control API probe to `/api/v1/__csrf_probe_no_route` returned expected HTTP `404` with `uses_curl_cookie_engine=true` and `uses_raw_cookie_header=false`; artifact `/tmp/openclaw/control_api_csrf_helper_no_route_probe_final_after_e2.json`. | Cookie delivery path is proven on a non-exchange route only. This does not authorize or execute cleanup. |
| Fresh pre-action Bybit demo inventory | 2026-06-26T01:58:16Z cursor-aware private GET-only inventory: `5` open orders on `ETCUSDT/FILUSDT/ICPUSDT/INJUSDT/NEARUSDT`, estimated open notional `486.24260000 USDT`; `3` nonzero positions on `FILUSDT/ICPUSDT/NEARUSDT`, value `435.14105000 USDT`, uPnL `-18.28692000 USDT`. Artifact on `trade-core`: `/tmp/openclaw/audit/bybit_demo_cleanup_action_pre_inventory/20260626T015816Z_pre_inventory.json`. | Stale for any future action unless refreshed inside the next E3/BB envelope. Inventory evidence is not profit proof. |
| Cleanup action attempt | 2026-06-26T01:59:00Z: one control API POST attempt to `/api/v1/strategy/demo/session/stop` returned HTTP `403` with `csrf_token_mismatch` / missing `oc_csrf` cookie. Response artifact: `/tmp/openclaw/audit/demo_residual_cleanup_action/20260626T015900Z_session_stop_response.json`; meta: `/tmp/openclaw/audit/demo_residual_cleanup_action/20260626T015900Z_session_stop_meta.json`. | Route did not execute; no exchange mutation occurred. Do not retry under the same failed invocation shape. |
| PG reconciliation | 2026-06-26 03:52:27+02 read-only PG: 72h demo fills `83`; missing `order_id=0`, missing `context_id=0`, unattributed/blank strategy `3`. 24h effective Working from `order_state_changes`: `2` linked PostOnly maker entries (`ETCUSDT`, `INJUSDT`). | Unattributed fills remain proof-excluded. Candidate selection stays blocked by exposure and lineage hygiene. |
| Passive healthcheck | 2026-06-26T01:50:53Z passive healthcheck `FAIL`; [68] demo `working_n=2`, resting about `487 USDT`, filled local exposure `0`, divergence `48735.0%`; [74] close-maker reject samples also `FAIL`. | No clean-book posture. Do not select/authorize a bounded Demo candidate yet. |

## §1 Current Dispatch State

| Field | Value |
|---|---|
| Session posture | Paused after v533 per operator request; do not auto-advance in this thread after this checkpoint. |
| Completed this round | `P1-RUNTIME-HEALTH-HYGIENE-API-CSRF-CLI-INVOKER` |
| Status | `DONE_WITH_CONCERNS` |
| Why concerns remain | Helper is source-only and not deployed to Linux runtime; actual cleanup still needs a fresh `PM -> E3 -> BB -> PM` exchange-facing envelope plus fresh pre-action inventory. |
| Next executable blocker on resume | `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-ACTION-E3-BB-REVIEW` |
| Do not repeat | Do not rerun broad audits, demo-order checks, or learning-running checks without source/runtime/PG/artifact/authorization delta. |

## §2 P0 Dispatch Queue

| ID | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY-BYBIT-DEMO-OPEN-ORDER-READ-ONLY-INVENTORY-E3-BB-REVIEW` | DONE_WITH_CONCERNS | PM -> E3 -> BB -> PM | Cursor-aware Bybit demo private GET inventory completed; proof exclusions explicit; no mutation or authority granted. | Report `2026-06-26--bybit_demo_open_order_read_only_inventory.md`; artifact `/tmp/openclaw/audit/bybit_demo_exchange_inventory/20260626T011756Z_inventory.json`. | No-repeat. Do not rerun without source/runtime/PG/artifact or authorization delta. |
| `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-PLAN-E3-BB-REVIEW` | DONE_WITH_CONCERNS | PM -> E3 -> BB -> PM | Residual exposure classified as 2 linked maker entries plus 3 residual positions protected by 3 reduce-only StopLoss conditionals. | Report `2026-06-26--demo_residual_exposure_cleanup_plan.md`; BB artifact `/tmp/openclaw/audit/bybit_demo_exchange_inventory_bb_review/20260626T014016Z_bb_inventory.json`. | No-repeat. Do not reclassify without evidence delta. |
| `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-ACTION-E3-BB-REVIEW` | WAITING | PM -> E3 -> BB -> PM | Create fresh session state; refresh E3/BB approval; collect fresh cursor-aware pre-action inventory; if scope still matches, invoke exactly one demo-only cleanup through CSRF-safe control API path; stop on any auth/CSRF/runtime failure; collect post-inventory. | Previous E3/BB approved shape, but first POST was blocked by `csrf_token_mismatch`; v533 source helper now proves cookie delivery on a non-exchange no-route probe. | After pause: run only this refreshed action envelope. No direct Bybit POST shortcut, no PG write, no runtime sync/restart, no Cost Gate/probe/order/live authority. |
| `P0-PROFIT-CANDIDATE-SELECTION` | BLOCKED | PM -> QC/MIT/BB -> PM | Select exactly one bounded Demo candidate only after clean-book posture or explicitly accepted residual risk; use attributed, fee/slippage-aware evidence only. | Blocked by 5 demo open orders, 3 demo positions, healthcheck [68] FAIL, and 3 proof-excluded unattributed/blank-strategy fills. | Reopen only after cleanup action is `DONE` or `DONE_WITH_CONCERNS` with clean post-inventory or accepted residual posture. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | BLOCKED | PM -> E3 -> BB -> Operator/QC -> PM | Requires completed evidence-quality and candidate-selection blockers plus explicit bounded-probe packet. | No candidate selected; no authority granted. | No action. |
| `P0-PROFIT-OUTCOME-REVIEW` | WAITING | PM -> QC/MIT/BB -> PM | Review candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded probe outcomes exist. | Wait for authorized bounded probe outcomes. |

## §3 P1/P2 Engineering Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P1-RUNTIME-HEALTH-HYGIENE-API-CSRF-CLI-INVOKER` | 1 | DONE_WITH_CONCERNS | PM -> PA/E2/E4 -> PM | Provide a reviewed, secret-safe way to invoke CSRF-protected control API POSTs from CLI without granting mutation authority. | v533 helper uses 0600 curl config, token from env/file only, curl cookie engine, approved API base allowlist, path normalization guards, reviewed-write/reviewed-mutation gates; tests `16 passed`; non-exchange no-route probe passed. | No-repeat unless helper is being deployed/synced or a new CSRF failure appears. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | WAITING | PM -> PA/CC -> PM | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | Current checkpoint did not change learning authority. | Source/doc decision only after P0 cleanup unblocks candidate selection. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | WAITING | PM -> PA/E1 -> E2 -> E4 -> PM | Learned candidate may become a reviewable proposal; it must not mutate order/risk/live state. | Proposal helpers are review-only; no direct authority. | Revisit after P0 cleanup and candidate selection. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | WAITING | PM -> E3 -> BB -> PM | Reconcile runtime drift without unreviewed restart/rebuild/env mutation. | Linux checkout clean at `d2cd70d0`; v533 helper is not on runtime; healthcheck [68], [74], [82] still FAIL. | Consider runtime source-sync review only after cleanup action checkpoint defines the exact need. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | DEFERRED | PM -> BB/E2/E4 -> PM | Full-scan pagination guard reviewed and production adoption path recorded. | Mac source has full-scan helper; Linux runtime lacks it because no source sync. | Carry into runtime source-sync review only after P0 cleanup is resolved. |

## §4 Operator / Runtime Gates

| Gate | Trigger | Rule |
|---|---|---|
| Exchange cleanup | Any successful cancel/modify/close/order-affecting action for demo residual exposure. | Must use refreshed `PM -> E3 -> BB -> PM` envelope after pause, with fresh pre-inventory. Use control API helper shape; no direct Bybit POST shortcut. |
| Runtime source sync | Deploying v533 CSRF helper or full-scan helper to Linux checkout. | Requires separate runtime/source-sync review; no service restart by default. |
| Bounded Demo probe | Candidate selected and clean-book posture accepted. | Requires explicit bounded-probe authorization; no live promotion. |
| Live/mainnet | Any mainnet key/order/path. | Not in scope; no live authority. |

## §5 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Do not lower global Cost Gate, widen caps/freshness gates, or fake freshness by editing/copying stale artifacts.
- Bybit inventory, healthcheck, source smoke, replay-only results, artifact counts, and single-window positives are not profitability proof.
- `flash_dip_buy` demo rows/fills, cleanup/risk-close rows, and unattributed fills cannot count toward bounded Cost Gate proof, bounded-probe proof, promotion, or risk-adjusted net PnL.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.

## §6 Aggressive Alpha Backlog

| Hypothesis path | Why it might make money | Fastest safe test | Authority |
|---|---|---|---|
| Clean-book unlock for one bounded candidate | Removing residual exposure and proof-excluded fills prevents contaminated PnL selection. | Resume at the refreshed cleanup action envelope, then rerun post-clean inventory/health/PG read-only and select exactly one candidate packet. | E3/BB for cleanup; no probe authority now. |
| Maker-path after exposure cleanup | Linked PostOnly entries show passive placement can rest, but edge is unusable until exposure is clean and fills are attributed. | Post-clean maker-ratio candidate packet with fee/slippage and adverse-selection controls. | Candidate review only; bounded probe later. |
| False-negative high-edge subset | Cost Gate false negatives may contain high net-edge cells, but only a clean, attributed book can make the comparison defensible. | After cleanup, rank false-negative candidates by current-fee net edge, fill attribution, and touchability friction; select one bounded demo candidate. | Research/proposal only until candidate authorization. |

## §7 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch && git rev-parse HEAD"
python3 /Users/ncyu/Projects/TradeBot/srv/helper_scripts/operator/control_api_csrf_post.py --api-base http://100.91.109.86:8000 --path /api/v1/__csrf_probe_no_route --token-file /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/.secrets/api_token --output /tmp/openclaw/control_api_csrf_helper_no_route_probe.json --expect-http 404
ssh trade-core "cd ~/BybitOpenClaw/srv && PGHOST=localhost PGUSER=trading_admin PGDATABASE=trading_ai bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
