# Xuanheng TODO - Active Dispatch Queue

**Version** v536 | **Date** 2026-06-26
**Source / runtime pointer**: Mac/origin `main` was clean at `30c7ce1cf32ad91e130dbcecccdcc745b4bf64f4` before this docs checkpoint. Linux runtime `trade-core` remains clean at `d2cd70d092916194043e112eeb402fb92bacb699`; no source sync, service restart, rebuild, crontab/env mutation, PG write, Rust writer, or adapter enablement was performed.
**Current posture**: `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-CLEANUP-ACTION-REFRESH-E3-BB` is `DONE_WITH_CONCERNS`: one E3/BB-reviewed runtime-local demo cleanup POST executed, and independent post-action Bybit full-scan inventory is clean. Next executable blocker is `P0-PROFIT-CANDIDATE-SELECTION`.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; prior auth report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--control_api_auth_token_path_probe.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source | `2026-06-26T02:59:35Z` read-only SSH: Linux repo clean at `d2cd70d0`; v535 helper/full-scan source is not present on runtime. | Cleanup used a one-time E3/BB-approved inline GET-only full-scan inventory, not source sync. |
| Fresh pre-inventory | `2026-06-26T03:09:10Z` inline runtime-local private GET-only Bybit demo full scan: 5 open orders, all reduce-only `Untriggered` market conditionals on `ETCUSDT/FILUSDT/ICPUSDT/NEARUSDT/TRXUSDT`; 5 nonzero positions; position value `440.14150000 USDT`; uPnL `-7.83110000 USDT`; caps passed. Artifact `/tmp/openclaw/audit/bybit_demo_cleanup_refresh_pre_inventory/20260626T030910Z_pre_inventory.json`. | Fresh scope was within E3/BB reviewed one-shot cleanup envelope. |
| Cleanup action | `2026-06-26T03:09:49Z` exactly one runtime-local CSRF/Bearer control API POST to `/api/v1/strategy/demo/session/stop`: HTTP `200`, `closed_all=true`, `partial_failure=false`, `cancel_orders.found=5`, `cancel_orders.cancelled=5`, `orphan_sweep.found=4`, `orphan_sweep.swept=4`, `verify.clean=true`. Meta `/tmp/openclaw/audit/demo_residual_cleanup_refresh_action/20260626T030949Z_session_stop_meta.json`. | Exchange-facing cleanup executed through reviewed control-plane route only; no direct Bybit POST by PM. |
| Post-action exchange truth | `2026-06-26T03:10:31Z` independent inline runtime-local private GET-only Bybit demo full scan: open orders `0`, nonzero positions `0`, parse errors `0`. Artifact `/tmp/openclaw/audit/bybit_demo_cleanup_refresh_post_inventory/20260626T031031Z_post_inventory.json`. | Demo exchange book is clean. |
| PG / proof exclusions | `2026-06-26 05:10:50+02` read-only PG: 72h demo fills `106`; missing order/context/blank strategy `0/0/0`; strategy counts include `flash_dip_buy=88`, `risk_close:ipc_close_symbol=6`, `unattributed:bybit_auto=4`. | Cleanup/risk-close/unattributed rows remain proof-excluded; do not count them in candidate proof or PnL. |
| Passive health | `2026-06-26T03:10:50Z` passive healthcheck still `FAIL`; [68] now fails from local lineage (`working_n=4`, `resting=398`, `filled=0`, divergence critical) despite exchange full-scan clean. Latest local `Working` rows are `oc_close_mf_fb_dm_1782442166742_135`, `oc_risk_dm_1782442146668_133`, `oc_risk_dm_1782440967557_121`, `oc_close_mf_fb_dm_1782440965566_120`, all with NULL details. | [68] is now a local lineage hygiene residual, not exchange open exposure. Candidate selection must not use those rows as proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T030115Z_demo_residual_cleanup_refresh.json` |
| `active_blocker_id` | `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-CLEANUP-ACTION-REFRESH-E3-BB` |
| `blocker_goal` | Execute at most one reviewed demo cleanup action after auth proof and fresh inventory. |
| `profit_relevance` | Clean exchange book removes a major contamination source before real risk-adjusted net-PnL candidate selection. |
| `new_evidence_delta_required` | Auth proof plus runtime/PG/artifact delta after prior spent 401 envelope. |
| `new_evidence_delta_found` | Runtime-local auth proof, fresh Bybit full-scan pre/post inventory, one successful cleanup POST, updated PG/health evidence. |
| `anti_repeat_decision` | `PROCEED_NEW_EVIDENCE_DELTA`, then `DONE_WITH_CONCERNS`. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-PROFIT-CANDIDATE-SELECTION` |
| `why_not_repeating_current_blocker` | Cleanup already executed once and post-action exchange full scan is clean. Repeating cleanup would violate the one-shot envelope and add no evidence. |

## §2 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | ACTIVE | PM -> QC/MIT/BB -> PM | Select exactly one bounded Demo candidate from Cost Gate false-negative, sealed horizon, MM current-fee, or clean attributed demo fills. Output an operator-review packet only; no probe/order/live authority. Must exclude cleanup/risk-close/unattributed/local-stale rows and include fee/slippage/current-cost controls. | Exchange book clean at post-inventory `20260626T031031Z`; proof-excluded rows still present in PG; health [68] local-lineage residual remains. | Build a candidate-selection packet; do not grant authority. |
| `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-CLEANUP-ACTION-REFRESH-E3-BB` | 0 | DONE_WITH_CONCERNS | PM -> E3 -> BB -> PM | Fresh session state; E3/BB review; fresh pre-inventory; at most one reviewed cleanup POST; post-action inventory clean. | Report `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; post-action full scan open orders `0`, nonzero positions `0`. | No-repeat. Reopen only if future Bybit full-scan inventory shows new residual exposure. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> Operator/QC -> PM | Candidate-specific bounded-probe packet; no global Cost Gate lowering; no live promotion; no order/probe authority outside approved envelope. | No candidate selected in v536; no authority granted. | Wait for candidate-selection packet. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Review candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait for authorized bounded-probe outcomes. |
| `P1-RUNTIME-HEALTH-HYGIENE-LOCAL-LINEAGE-68-STALE-WORKING` | 1 | WAITING | PM -> E3/BB -> PM | Determine whether health [68] should ignore exchange-clean local close/risk stale `Working` rows or whether a reconciler/source fix is needed. | Exchange post-scan clean but [68] FAIL from 4 local stale `Working` rows with NULL details. | Defer until after candidate packet unless [68] blocks packet construction. |
| `P1-RUNTIME-HEALTH-HYGIENE-CONTROL-API-AUTH-TOKEN-PATH` | 1 | DONE_WITH_CONCERNS | PM -> E3 -> PM | Secret-safe runtime-local authenticated read-only probe completed; no token material recorded; no mutation. | HTTP `200` probe artifacts under `/tmp/openclaw/audit/control_api_auth_token_path/20260626T025405Z_*`. | No-repeat unless a later cleanup action returns new auth failure evidence. |
| `P1-RUNTIME-HEALTH-HYGIENE-API-CSRF-CLI-INVOKER` | 1 | DONE_WITH_CONCERNS | PM -> PA/E2/E4 -> PM | Reviewed helper exists for CSRF-protected POSTs in source; token from env/file only; curl cookie engine; sensitive path gates. | Report `2026-06-26--api_csrf_cli_invoker_source_patch.md`; helper is not synced to runtime. | Consider source-sync only if future runtime workflows need the helper. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | WAITING | PM -> PA/CC -> PM | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | Current checkpoint did not change learning authority. | Resume after candidate selection. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | WAITING | PM -> PA/E1 -> E2 -> E4 -> PM | Learning output may become a reviewable proposal only; it must not mutate order/risk/live state. | Proposal helpers remain review-only. | Resume after candidate selection. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | WAITING | PM -> E3 -> BB -> PM | Reconcile runtime drift without unreviewed restart/rebuild/env mutation. | Linux checkout still `d2cd70d0`; v533/v536 helpers are not synced to runtime. | Consider runtime source-sync review after P0 candidate packet if needed. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | DEFERRED | PM -> BB/E2/E4 -> PM | Production full-scan pagination adoption path recorded and reviewed. | Mac source has full-scan helper; Linux runtime lacks it because no source sync. | Carry into a runtime source-sync review after P0 candidate packet if needed. |

## §3 Hard Gates

| Gate | Trigger | Rule |
|---|---|---|
| Candidate selection | Any claim that a side-cell is ready for bounded Demo review. | Must be candidate-matched, attributed, fee/slippage-aware, and exclude cleanup/risk-close/unattributed/local-stale rows. |
| Bounded Demo probe | Candidate selected and packet reviewed. | Requires explicit candidate packet; no live promotion and no global Cost Gate lowering. |
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
| False-negative high-edge subset after clean exchange book | High | Medium | Rank false-negative candidates by current-fee net edge, sealed horizon, attribution quality, and touchability friction; select exactly one review packet. | Candidate review only. |
| Maker-path after cleanup | Medium | Low-Medium | Build maker-ratio candidate packet with current fee tier, adverse-selection controls, and candidate-matched attributed fills only. | Research/proposal until candidate authorization. |
| Local lineage [68] repair | Medium | Medium | Source-only healthcheck/reconciler patch so exchange-clean close/risk stale rows do not block candidate selection. | Source-only review; no runtime mutation by default. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "python3 -m json.tool /tmp/openclaw/audit/bybit_demo_cleanup_refresh_post_inventory/20260626T031031Z_post_inventory.json | head -120"
ssh trade-core "python3 -m json.tool /tmp/openclaw/audit/demo_residual_cleanup_refresh_action/20260626T030949Z_session_stop_meta.json"
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
