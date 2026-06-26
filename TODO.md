# Xuanheng TODO - Active Dispatch Queue

**Version** v537 | **Date** 2026-06-26
**Source / runtime pointer**: Mac/origin `main` was clean at `5f50f1de2a903115f2378b07fcbd468eb1bd5987` before this docs checkpoint. Linux runtime `trade-core` remains clean at `d2cd70d092916194043e112eeb402fb92bacb699`; no source sync, service restart, rebuild, crontab/env mutation, PG write, Rust writer, or adapter enablement was performed.
**Current posture**: `P0-PROFIT-CANDIDATE-SELECTION` is `DONE_WITH_CONCERNS`: exactly one review-only bounded Demo candidate was selected, `grid_trading|AVAXUSDT|Sell`. This session is paused after the v537 checkpoint per operator request. Next executable blocker is `P0-BOUNDED-PROBE-AUTHORIZATION`, with max safe first action limited to source/read-only first-attempt touchability bootstrap; no probe/order/live authority is granted.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--profit_candidate_selection_avax_review_packet.md`; cleanup report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source | `2026-06-26T02:59:35Z` read-only SSH: Linux repo clean at `d2cd70d0`; v535 helper/full-scan source is not present on runtime. | No runtime source sync/restart was done in the candidate-selection checkpoint. |
| Exchange cleanup | Report `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`: one reviewed runtime-local cleanup POST returned HTTP `200`; independent post-action full scan showed open orders `0`, nonzero positions `0`, parse errors `0`. | Demo exchange book is clean enough to select a candidate, but cleanup rows are risk hygiene only. |
| PG / proof exclusions | `2026-06-26 05:10:50+02` read-only PG: 72h demo fills `106`; missing order/context/blank strategy `0/0/0`; strategy counts include `flash_dip_buy=88`, `risk_close:ipc_close_symbol=6`, `unattributed:bybit_auto=4`. | Cleanup/risk-close/unattributed rows remain proof-excluded; do not count them in candidate proof or PnL. |
| Passive health | `2026-06-26T03:10:50Z` passive healthcheck still `FAIL`; [68] now fails from local lineage (`working_n=4`, `resting=398`, `filled=0`, divergence critical) despite exchange full-scan clean. Latest local `Working` rows are `oc_close_mf_fb_dm_1782442166742_135`, `oc_risk_dm_1782442146668_133`, `oc_risk_dm_1782440967557_121`, `oc_close_mf_fb_dm_1782440965566_120`, all with NULL details. | [68] is now a local lineage hygiene residual, not exchange open exposure. Candidate selection must not use those rows as proof. |
| Candidate selection | `2026-06-26T03:23Z` PM/QC/MIT/BB review packet selected `grid_trading|AVAXUSDT|Sell` only. Evidence: avg net `73.5511bps`, `48/48` net-positive 60m outcomes, cap `10 USDT`, min notional `5 USDT`, no authority. Report `2026-06-26--profit_candidate_selection_avax_review_packet.md`. | Candidate selection is closed with concerns; active probe/order remains blocked by missing candidate-matched touchability. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T032000Z_profit_candidate_selection.json` |
| `active_blocker_id` | `P0-PROFIT-CANDIDATE-SELECTION` |
| `blocker_goal` | Select exactly one bounded Demo candidate from false-negative, sealed horizon, MM current-fee, or clean attributed demo evidence; output review packet only. |
| `profit_relevance` | Converts cleaned demo state into the fastest candidate-specific path toward real risk-adjusted net-PnL evidence after fees/slippage. |
| `new_evidence_delta_required` | Clean exchange book plus proof-exclusion policy after the residual cleanup blocker. |
| `new_evidence_delta_found` | Clean exchange-book report, candidate evidence inventory, and QC/MIT/BB read-only review all support selecting one review-only AVAX candidate. |
| `anti_repeat_decision` | `PROCEED_NEW_EVIDENCE_DELTA`, then `DONE_WITH_CONCERNS`. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` |
| `why_not_repeating_current_blocker` | Exactly one review-only candidate is selected. Repeating selection without a new candidate/cap/fee/touchability delta would add no evidence. |

## §2 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE_WITH_CONCERNS | PM -> QC/MIT/BB -> PM | Exactly one candidate selected; review-only packet; no probe/order/live authority; proof exclusions recorded. | Report `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading|AVAXUSDT|Sell`; QC/MIT/BB all approve review-only with concerns. | No-repeat unless new candidate/cap/fee/touchability evidence appears. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | ACTIVE | PM -> E3 -> BB -> Operator/QC -> PM | Candidate-specific bounded-probe authorization packet for `grid_trading|AVAXUSDT|Sell`; no global Cost Gate lowering; no live promotion; no order/probe authority outside a reviewed envelope. | Candidate selected, but candidate-matched touchability is missing: `candidate_reviewed_orders=0`, `candidate_fill_rows=0`, `CANDIDATE_TOUCHABILITY_DATA_REQUIRED`. | After this pause, first executable step is source/read-only first-attempt touchability bootstrap design; do not submit orders. |
| `P0-BOUNDED-PROBE-FIRST-ATTEMPT-TOUCHABILITY-BOOTSTRAP-SOURCE-ONLY` | 0 | WAITING | PM -> PA/E1 -> E2/E4 -> PM | No-authority near-touch-or-skip design contract for exact side-cell `grid_trading|AVAXUSDT|Sell`, requiring fresh BBO/cap checks and candidate-matched order/fill/fee/slippage lineage before any E3/BB/order path. | MIT/BB both identify candidate touchability as the hard blocker. | Resume here only after the requested pause. |
| `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-CLEANUP-ACTION-REFRESH-E3-BB` | 0 | DONE_WITH_CONCERNS | PM -> E3 -> BB -> PM | Fresh session state; E3/BB review; fresh pre-inventory; at most one reviewed cleanup POST; post-action inventory clean. | Report `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; post-action full scan open orders `0`, nonzero positions `0`. | No-repeat. Reopen only if future Bybit full-scan inventory shows new residual exposure. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Review candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait for authorized bounded-probe outcomes. |
| `P1-RUNTIME-HEALTH-HYGIENE-LOCAL-LINEAGE-68-STALE-WORKING` | 1 | WAITING | PM -> E3/BB -> PM | Determine whether health [68] should ignore exchange-clean local close/risk stale `Working` rows or whether a reconciler/source fix is needed. | Exchange post-scan clean but [68] FAIL from 4 local stale `Working` rows with NULL details. | Defer unless [68] blocks the first-attempt touchability/bootstrap or authorization packet. |
| `P1-RUNTIME-HEALTH-HYGIENE-CONTROL-API-AUTH-TOKEN-PATH` | 1 | DONE_WITH_CONCERNS | PM -> E3 -> PM | Secret-safe runtime-local authenticated read-only probe completed; no token material recorded; no mutation. | HTTP `200` probe artifacts under `/tmp/openclaw/audit/control_api_auth_token_path/20260626T025405Z_*`. | No-repeat unless a later cleanup action returns new auth failure evidence. |
| `P1-RUNTIME-HEALTH-HYGIENE-API-CSRF-CLI-INVOKER` | 1 | DONE_WITH_CONCERNS | PM -> PA/E2/E4 -> PM | Reviewed helper exists for CSRF-protected POSTs in source; token from env/file only; curl cookie engine; sensitive path gates. | Report `2026-06-26--api_csrf_cli_invoker_source_patch.md`; helper is not synced to runtime. | Consider source-sync only if future runtime workflows need the helper. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | WAITING | PM -> PA/CC -> PM | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | Current checkpoint did not change learning authority. | Resume after the AVAX touchability/bootstrap or bounded-probe authorization checkpoint. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | WAITING | PM -> PA/E1 -> E2 -> E4 -> PM | Learning output may become a reviewable proposal only; it must not mutate order/risk/live state. | Proposal helpers remain review-only. | Resume after the AVAX touchability/bootstrap or bounded-probe authorization checkpoint. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | WAITING | PM -> E3 -> BB -> PM | Reconcile runtime drift without unreviewed restart/rebuild/env mutation. | Linux checkout still `d2cd70d0`; v533/v536 helpers are not synced to runtime. | Consider runtime source-sync review only if the AVAX bootstrap/auth path needs runtime helper propagation. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | DEFERRED | PM -> BB/E2/E4 -> PM | Production full-scan pagination adoption path recorded and reviewed. | Mac source has full-scan helper; Linux runtime lacks it because no source sync. | Carry into runtime source-sync review only if future exchange inventory/reconciler work needs it. |

## §3 Hard Gates

| Gate | Trigger | Rule |
|---|---|---|
| Candidate selection | Any claim that a side-cell is ready for bounded Demo review. | v537 selected only `grid_trading|AVAXUSDT|Sell`; no-repeat without new evidence. |
| Bounded Demo probe | Any attempt to move from review packet to active probe/order. | Requires candidate-matched touchability bootstrap, E3/BB runtime/exchange review, exact authorization packet, no live promotion, and no global Cost Gate lowering. |
| Runtime source sync | Deploying helper/full-scan source to Linux runtime. | Requires separate runtime/source-sync review; no service restart by default. |
| Live/mainnet | Any mainnet key/order/path. | Out of scope; no live authority. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Do not lower global Cost Gate, widen caps/freshness gates, fake freshness, or bypass Guardian/risk/Decision Lease/Rust authority.
- `flash_dip_buy` demo fills, cleanup/risk-close fills, unattributed fills, local stale Working rows, artifact counts, source-smoke, single-window MM positives, and replay-only results cannot count as Cost Gate, bounded-probe, promotion, or risk-adjusted net-PnL proof.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.

## §5 Aggressive Alpha Backlog

| Hypothesis | Upside | Evidence | Fast safe test | Authority |
|---|---:|---:|---|---|
| AVAX false-negative first-attempt touchability bootstrap | High | Medium | Source-only near-touch-or-skip design contract for `grid_trading|AVAXUSDT|Sell`; require fresh BBO/cap and candidate-matched lineage. | Source/review only. |
| AVAX regime filter before probe | Medium-High | Medium | Source-only filter proposal over blocked-outcome rows; no Cost Gate lowering. | Research/proposal only. |
| MM current-fee repeat-window branch | Medium | Low | Accumulate independent windows for the same current-fee-positive SOXL cell before review. | Research/proposal only. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--profit_candidate_selection_avax_review_packet.md
python3 -m json.tool /tmp/openclaw/local_chain_smoke_20260625T232303Z/inputs/cap_feasible_candidate_selection_avax_sell_20260625T214943Z.json | head -120
python3 -m json.tool /tmp/openclaw/local_chain_smoke_20260625T232303Z/outputs/bounded_probe_touchability_preflight_avax_sell_20260625T232303Z.json | head -120
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
