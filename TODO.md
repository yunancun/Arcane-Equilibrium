# Xuanheng TODO - Active Dispatch Queue

**Version** v535 | **Date** 2026-06-26
**Source / runtime pointer**: Mac/origin `main` was clean at `f42f28fcb369ac702cd8751a20beb8a73b813199` before this docs checkpoint. Linux runtime `trade-core` remains clean at `d2cd70d092916194043e112eeb402fb92bacb699`; no source sync, service restart, rebuild, crontab/env mutation, PG write, Rust writer, or adapter enablement was performed.
**Current posture**: `P1-RUNTIME-HEALTH-HYGIENE-CONTROL-API-AUTH-TOKEN-PATH` is `DONE_WITH_CONCERNS`: runtime-local token file authenticated a read-only GET probe with HTTP `200`. The spent cleanup envelope must not be reused; next executable work is a fresh E3/BB cleanup envelope plus fresh pre-inventory.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--control_api_auth_token_path_probe.md`; prior cleanup block `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_action_unauthenticated_block.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source | `2026-06-26T02:49:46Z` read-only SSH: Linux repo clean at `d2cd70d0`; runtime token file stat `2026-03-26 21:27:31 +0100`, size `44`, mode `600`. | Runtime is not synced to v533/v535 helper source. Do not assume Mac token file matches runtime API token. |
| Auth-token path | `2026-06-26T02:54:05Z` E3-approved runtime-local probe: exactly one `GET /api/v1/backtest/status` with runtime repo token file returned HTTP `200`, curl exit `0`; response keys `last_result_available/source/stub`. Artifacts: `/tmp/openclaw/audit/control_api_auth_token_path/20260626T025405Z_auth_probe_meta.json` and response JSON. | Auth path is proven for read-only runtime-local control API calls. It does not authorize cleanup/order actions. |
| Spent cleanup attempt | `2026-06-26T02:41:01Z` one reviewed helper POST to `/api/v1/strategy/demo/session/stop` from Mac token source returned HTTP `401 unauthenticated`; route did not execute; no exchange mutation occurred. | Do not retry under that envelope. A new E3/BB review and fresh inventory are mandatory. |
| Latest demo exposure | `2026-06-26T02:40:42Z` fresh pre-action inventory: `6` open orders, `5` nonzero positions, open notional `200.61774000 USDT`, position value `636.52024000 USDT`, uPnL `-12.86180000 USDT`. | Candidate selection remains blocked until cleanup succeeds or residual posture is explicitly accepted. |
| Attribution hygiene | `2026-06-26 03:52:27+02` read-only PG: 72h demo fills `83`; missing order/context `0/0`; unattributed or blank strategy `3`. | Unattributed fills remain proof-excluded. |
| Passive health | `2026-06-26T02:23:28Z` passive healthcheck `FAIL`; current notable fails include `[12]`, `[56]`, `[74]`, `[82]`. | No clean-book posture. Do not select a bounded Demo candidate yet. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T024946Z_control_api_auth_token_path.json` |
| `active_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-CONTROL-API-AUTH-TOKEN-PATH` |
| `blocker_goal` | Prove a secret-safe runtime-local authenticated read-only control API path without token leakage or mutation. |
| `profit_relevance` | Clean residual exposure and clean attribution are prerequisites for selecting real risk-adjusted net-PnL candidates. |
| `new_evidence_delta_required` | Prior cleanup failed `401 unauthenticated`; a token-path proof was required before any fresh cleanup envelope. |
| `new_evidence_delta_found` | Runtime-local token file succeeded on authenticated read-only GET with HTTP `200`. |
| `anti_repeat_decision` | `PROCEED_NEW_EVIDENCE_DELTA`, then `DONE_WITH_CONCERNS`. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-CLEANUP-ACTION-REFRESH-E3-BB` |
| `why_not_repeating_current_blocker` | Auth-token proof is complete. Next action is not another auth probe and not the spent cleanup envelope. |

## §2 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-CLEANUP-ACTION-REFRESH-E3-BB` | 0 | ACTIVE | PM -> E3 -> BB -> PM | Fresh session state; E3/BB approve a new cleanup envelope after auth proof; fresh cursor-aware demo inventory immediately before action; at most one reviewed cleanup POST through runtime-local authenticated path; stop on any auth/CSRF/runtime/exchange failure; post-action inventory only if route executes. | Auth path report `2026-06-26--control_api_auth_token_path_probe.md`; prior spent envelope report `2026-06-26--demo_residual_cleanup_action_unauthenticated_block.md`. | Build the refreshed E3/BB packet. Do not run cleanup until that review and fresh inventory are complete. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | BLOCKED | PM -> QC/MIT/BB -> PM | Select exactly one bounded Demo candidate from Cost Gate false-negative, sealed horizon, MM current-fee, or clean attributed demo fills. | Blocked by demo exposure plus 3 proof-excluded unattributed/blank-strategy fills. | Reopen only after cleanup is `DONE`/`DONE_WITH_CONCERNS` with clean post-inventory or accepted residual posture. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> Operator/QC -> PM | Candidate-specific bounded-probe packet; no global Cost Gate lowering; no live promotion; no order/probe authority outside approved envelope. | No candidate selected; no authority granted. | No action. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Review candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait for authorized bounded-probe outcomes. |
| `P1-RUNTIME-HEALTH-HYGIENE-CONTROL-API-AUTH-TOKEN-PATH` | 1 | DONE_WITH_CONCERNS | PM -> E3 -> PM | Secret-safe runtime-local authenticated read-only probe completed; no token material recorded; no mutation. | HTTP `200` probe artifacts under `/tmp/openclaw/audit/control_api_auth_token_path/20260626T025405Z_*`. | No-repeat unless a later cleanup action returns new auth failure evidence. |
| `P1-RUNTIME-HEALTH-HYGIENE-API-CSRF-CLI-INVOKER` | 1 | DONE_WITH_CONCERNS | PM -> PA/E2/E4 -> PM | Reviewed helper exists for CSRF-protected POSTs; token from env/file only; curl cookie engine; sensitive path gates. | Report `2026-06-26--api_csrf_cli_invoker_source_patch.md`; tests `16 passed`; no-route probe HTTP `404`. | No-repeat unless deploying/syncing helper or a new CSRF failure appears. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | WAITING | PM -> PA/CC -> PM | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | Current checkpoint did not change learning authority. | Resume after P0 cleanup unblocks candidate selection. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | WAITING | PM -> PA/E1 -> E2 -> E4 -> PM | Learning output may become a reviewable proposal only; it must not mutate order/risk/live state. | Proposal helpers remain review-only. | Resume after P0 cleanup and candidate selection. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | WAITING | PM -> E3 -> BB -> PM | Reconcile runtime drift without unreviewed restart/rebuild/env mutation. | Linux checkout still `d2cd70d0`; v533 helper source not synced to runtime. | Consider runtime source-sync review only if fresh cleanup envelope needs it. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | DEFERRED | PM -> BB/E2/E4 -> PM | Production full-scan pagination adoption path recorded and reviewed. | Mac source has full-scan helper; Linux runtime lacks it because no source sync. | Carry into a runtime source-sync review only after P0 cleanup is resolved. |

## §3 Hard Gates

| Gate | Trigger | Rule |
|---|---|---|
| Demo cleanup | Any successful cancel/modify/close/order-affecting action for residual demo exposure. | Requires fresh E3/BB envelope, fresh pre-inventory, and one reviewed control-plane path. No direct Bybit POST shortcut. |
| Runtime source sync | Deploying helper/full-scan source to Linux runtime. | Requires separate runtime/source-sync review; no service restart by default. |
| Bounded Demo probe | Candidate selected and clean-book or accepted residual posture exists. | Requires explicit candidate packet; no live promotion. |
| Live/mainnet | Any mainnet key/order/path. | Out of scope; no live authority. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Do not lower global Cost Gate, widen caps/freshness gates, fake freshness, or bypass Guardian/risk/Decision Lease/Rust authority.
- `flash_dip_buy` demo fills, cleanup/risk-close fills, unattributed fills, artifact counts, source-smoke, single-window MM positives, and replay-only results cannot count as Cost Gate, bounded-probe, promotion, or risk-adjusted net-PnL proof.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.

## §5 Aggressive Alpha Backlog

| Hypothesis | Upside | Evidence | Fast safe test | Authority |
|---|---:|---:|---|---|
| Runtime-local authenticated cleanup path | High | Medium | Fresh E3/BB cleanup packet plus fresh inventory; one reviewed runtime-local cleanup POST only if approved. | E3/BB for exchange-facing cleanup. |
| Maker-path after clean exposure | Medium | Low-Medium | Post-clean maker-ratio packet with fee/slippage and adverse-selection controls. | Research/proposal until candidate authorization. |
| False-negative high-edge subset | High | Low-Medium | After cleanup, rank false negatives by current-fee net edge, fill attribution, and touchability friction; select one bounded candidate. | Candidate review only. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch && git rev-parse HEAD"
ssh trade-core "python3 -m json.tool /tmp/openclaw/audit/control_api_auth_token_path/20260626T025405Z_auth_probe_meta.json"
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
