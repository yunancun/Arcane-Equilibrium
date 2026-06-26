# Xuanheng TODO - Active Dispatch Queue

**Version** v534 | **Date** 2026-06-26
**Source / runtime pointer**: Mac/origin `main` was clean at `08d660db11211b838d42e21c8a235ff26acc9b46` before this docs checkpoint; Linux runtime remains clean at `d2cd70d092916194043e112eeb402fb92bacb699` with no source sync, rebuild, restart, crontab/env mutation, PG write, or Rust writer/adapter enablement.
**Current mainline**: `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-ACTION-E3-BB-REVIEW` is `BLOCKED_BY_RUNTIME_AUTHORIZATION`: the one reviewed cleanup POST failed HTTP `401 unauthenticated` before route execution; no exchange mutation occurred. Next executable blocker is a narrow control API auth-token path checkpoint.
**Evidence links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_action_unauthenticated_block.md`; prior helper report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--api_csrf_cli_invoker_source_patch.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source / cron | 2026-06-26T02:23:12Z read-only check: Linux repo clean at `d2cd70d0`; crontab expected-head occurrences `d2cd70d0=11`; adapter flag count `0`; `OPENCLAW_ALLOW_MAINNET=1` count `0`. | No runtime sync/restart/rebuild was done. v533/v534 helper remains source-only on Mac/origin. |
| CSRF helper proof | 2026-06-26 source helper `helper_scripts/operator/control_api_csrf_post.py` added. Focused tests `16 passed`, `py_compile` PASS, `git diff --check` PASS. No-route control API probe to `/api/v1/__csrf_probe_no_route` returned expected HTTP `404` with `uses_curl_cookie_engine=true` and `uses_raw_cookie_header=false`; artifact `/tmp/openclaw/control_api_csrf_helper_no_route_probe_final_after_e2.json`. | Cookie delivery path is proven on a non-exchange route only. This does not authorize or execute cleanup. |
| Fresh pre-action Bybit demo inventory | 2026-06-26T02:40:42Z cursor-aware private GET-only inventory: `6` open orders on `ETCUSDT/FILUSDT/ICPUSDT/NEARUSDT/TRXUSDT`, estimated open notional `200.61774000 USDT`; `5` nonzero positions on the same symbols, value `636.52024000 USDT`, uPnL `-12.86180000 USDT`. Artifact on `trade-core`: `/tmp/openclaw/audit/bybit_demo_cleanup_action_pre_inventory/20260626T024042Z_pre_inventory.json`. | Demo exposure is still drifting. Inventory evidence is risk state only, not profit proof. |
| Cleanup action attempt | 2026-06-26T02:41:01Z: exactly one reviewed helper-mediated POST to `/api/v1/strategy/demo/session/stop` returned HTTP `401` with `unauthenticated`. Response artifact `/tmp/openclaw/audit/demo_residual_cleanup_action/20260626T024042Z_session_stop_response.json`; meta `/tmp/openclaw/audit/demo_residual_cleanup_action/20260626T024042Z_session_stop_meta.json`. | Route did not execute; no exchange mutation occurred. Do not retry under the same failed auth envelope. |
| PG reconciliation | 2026-06-26 03:52:27+02 read-only PG: 72h demo fills `83`; missing `order_id=0`, missing `context_id=0`, unattributed/blank strategy `3`. 24h effective Working from `order_state_changes`: `2` linked PostOnly maker entries (`ETCUSDT`, `INJUSDT`). | Unattributed fills remain proof-excluded. Candidate selection stays blocked by exposure and lineage hygiene. |
| Passive healthcheck | 2026-06-26T02:23:28Z passive healthcheck `FAIL`; notable current fails include [12], [56], [74], [82]. [68] was not emitted in quiet output, but direct exchange inventory still shows open orders/positions. | No clean-book posture. Do not select/authorize a bounded Demo candidate yet. |

## §1 Current Dispatch State

| Field | Value |
|---|---|
| Session posture | Active loop; do not repeat cleanup POST under the failed auth envelope. |
| Completed this round | Refreshed E3/BB envelope, fresh cursor-aware pre-inventory, and exactly one reviewed cleanup POST attempt. |
| Status | `BLOCKED_BY_RUNTIME_AUTHORIZATION` |
| Why concerns remain | The control API rejected the Bearer token with `401 unauthenticated` before route execution; local Mac token source does not prove runtime API token alignment. |
| Next executable blocker on resume | `P1-RUNTIME-HEALTH-HYGIENE-CONTROL-API-AUTH-TOKEN-PATH` |
| Do not repeat | Do not rerun broad audits, demo-order checks, or learning-running checks without source/runtime/PG/artifact/authorization delta. |

## §2 P0 Dispatch Queue

| ID | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY-BYBIT-DEMO-OPEN-ORDER-READ-ONLY-INVENTORY-E3-BB-REVIEW` | DONE_WITH_CONCERNS | PM -> E3 -> BB -> PM | Cursor-aware Bybit demo private GET inventory completed; proof exclusions explicit; no mutation or authority granted. | Report `2026-06-26--bybit_demo_open_order_read_only_inventory.md`; artifact `/tmp/openclaw/audit/bybit_demo_exchange_inventory/20260626T011756Z_inventory.json`. | No-repeat. Do not rerun without source/runtime/PG/artifact or authorization delta. |
| `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-PLAN-E3-BB-REVIEW` | DONE_WITH_CONCERNS | PM -> E3 -> BB -> PM | Residual exposure classified as 2 linked maker entries plus 3 residual positions protected by 3 reduce-only StopLoss conditionals. | Report `2026-06-26--demo_residual_exposure_cleanup_plan.md`; BB artifact `/tmp/openclaw/audit/bybit_demo_exchange_inventory_bb_review/20260626T014016Z_bb_inventory.json`. | No-repeat. Do not reclassify without evidence delta. |
| `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-ACTION-E3-BB-REVIEW` | BLOCKED_BY_RUNTIME_AUTHORIZATION | PM -> E3 -> BB -> PM | Execute at most one reviewed demo cleanup POST after fresh inventory; stop on any auth/CSRF/runtime failure; collect response/meta. | E3/BB refreshed approval completed; fresh pre-inventory `20260626T024042Z`; exactly one POST returned HTTP `401 unauthenticated`; report `2026-06-26--demo_residual_cleanup_action_unauthenticated_block.md`. | No-repeat. Open the auth-token path blocker; do not issue a second cleanup POST until new E3/BB envelope and fresh inventory exist. |
| `P0-PROFIT-CANDIDATE-SELECTION` | BLOCKED | PM -> QC/MIT/BB -> PM | Select exactly one bounded Demo candidate only after clean-book posture or explicitly accepted residual risk; use attributed, fee/slippage-aware evidence only. | Blocked by fresh demo exchange exposure: `6` open orders, `5` nonzero positions, HTTP `401` cleanup auth block, and 3 proof-excluded unattributed/blank-strategy fills. | Reopen only after cleanup action is `DONE` or `DONE_WITH_CONCERNS` with clean post-inventory or accepted residual posture. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | BLOCKED | PM -> E3 -> BB -> Operator/QC -> PM | Requires completed evidence-quality and candidate-selection blockers plus explicit bounded-probe packet. | No candidate selected; no authority granted. | No action. |
| `P0-PROFIT-OUTCOME-REVIEW` | WAITING | PM -> QC/MIT/BB -> PM | Review candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded probe outcomes exist. | Wait for authorized bounded probe outcomes. |

## §3 P1/P2 Engineering Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P1-RUNTIME-HEALTH-HYGIENE-API-CSRF-CLI-INVOKER` | 1 | DONE_WITH_CONCERNS | PM -> PA/E2/E4 -> PM | Provide a reviewed, secret-safe way to invoke CSRF-protected control API POSTs from CLI without granting mutation authority. | v533 helper uses 0600 curl config, token from env/file only, curl cookie engine, approved API base allowlist, path normalization guards, reviewed-write/reviewed-mutation gates; tests `16 passed`; non-exchange no-route probe passed. | No-repeat unless helper is being deployed/synced or a new CSRF failure appears. |
| `P1-RUNTIME-HEALTH-HYGIENE-CONTROL-API-AUTH-TOKEN-PATH` | 1 | ACTIVE | PM -> E3 -> PM | Establish a secret-safe authenticated CLI/control-plane invocation path using the runtime API token source without printing or exfiltrating token material. | Cleanup POST returned `401 unauthenticated`; source inspection shows `current_actor` compares Bearer/cookie token against runtime process `settings.api_token`; Mac and runtime token-file mtimes differ. | Source/read-only runtime auth-token path review. Do not retry cleanup in this blocker. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | WAITING | PM -> PA/CC -> PM | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | Current checkpoint did not change learning authority. | Source/doc decision only after P0 cleanup unblocks candidate selection. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | WAITING | PM -> PA/E1 -> E2 -> E4 -> PM | Learned candidate may become a reviewable proposal; it must not mutate order/risk/live state. | Proposal helpers are review-only; no direct authority. | Revisit after P0 cleanup and candidate selection. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | WAITING | PM -> E3 -> BB -> PM | Reconcile runtime drift without unreviewed restart/rebuild/env mutation. | Linux checkout clean at `d2cd70d0`; v533 helper is not on runtime; 2026-06-26T02:23:28Z healthcheck still FAIL. | Consider runtime source-sync review only after cleanup action checkpoint defines the exact need. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | DEFERRED | PM -> BB/E2/E4 -> PM | Full-scan pagination guard reviewed and production adoption path recorded. | Mac source has full-scan helper; Linux runtime lacks it because no source sync. | Carry into runtime source-sync review only after P0 cleanup is resolved. |

## §4 Operator / Runtime Gates

| Gate | Trigger | Rule |
|---|---|---|
| Exchange cleanup | Any successful cancel/modify/close/order-affecting action for demo residual exposure. | Current envelope is spent and blocked by 401. A second cleanup attempt requires auth-token path resolution, new E3/BB envelope, and fresh pre-inventory. No direct Bybit POST shortcut. |
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
| Runtime-local authenticated cleanup path | Removing residual exposure and proof-excluded fills prevents contaminated PnL selection, but the Mac token path failed auth. | Resolve runtime API token-source path without secret leakage, then refresh E3/BB and run a new fresh-inventory cleanup envelope. | E3 for auth path; E3/BB for any second cleanup attempt. |
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
