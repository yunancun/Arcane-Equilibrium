# Xuanheng TODO - Active Dispatch Queue

**Version** v538 | **Date** 2026-06-26
**Source / runtime pointer**: Mac/origin `main` was clean at `ebc3a3979c7294a14f679a4756a72a9887dcf6c8` before this docs checkpoint. Linux runtime `trade-core` remains clean at `d2cd70d092916194043e112eeb402fb92bacb699`; no source sync, service restart, rebuild, crontab/env mutation, PG write, Rust writer, adapter enablement, Bybit order/cancel/modify, Cost Gate change, or live action was performed.
**Current posture**: `P0-BOUNDED-PROBE-AUTHORIZATION` is paused at a no-authority review checkpoint. The selected candidate is still exactly `grid_trading|AVAXUSDT|Sell`. The old first-attempt touchability/bootstrap source blocker is already done and must not be repeated. A fresh defer-only authorization packet is ready for review, but actual bounded Demo grant is blocked until a machine-checkable structured standing Demo authorization or exact typed confirmation is present.
**Links**: latest report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--avax_authorization_review_ready_no_authority.md`; candidate report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--profit_candidate_selection_avax_review_packet.md`; TODO standard `docs/agents/todo-maintenance.md`; changelog `docs/CLAUDE_CHANGELOG.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source | TODO v537 and this docs-only checkpoint: Linux repo clean at `d2cd70d0`; current Mac/origin head before docs is `ebc3a3979c7294a14f679a4756a72a9887dcf6c8`. | No runtime mutation occurred in v538; runtime/admission state is unchanged. |
| Selected candidate | v537 selected exactly one review-only candidate: `grid_trading|AVAXUSDT|Sell`, 60m, avg modeled net `73.5511bps`, `48/48` net-positive, cap `10 USDT`, min notional `5 USDT`. | Candidate selection is closed. Do not reselect without new candidate/cap/fee/touchability evidence. |
| Touchability bootstrap | Prior report `2026-06-25--avax_touchability_bootstrap_source_patch.md` and existing helpers already emit `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED` / `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`. | `P0-BOUNDED-PROBE-FIRST-ATTEMPT-TOUCHABILITY-BOOTSTRAP-SOURCE-ONLY` is `NO-OP_ALREADY_DONE`; repeating it adds no evidence. |
| Authorization review | Fresh artifacts under `/tmp/openclaw/avax_bounded_probe_authorization_review_20260626T032857Z/`: authority readiness status `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`; operator packet status `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, decision `defer`, blocking gates `[]`, typed confirm missing, no auth object. | Review packet is ready but grants no active probe/order authority. |
| E3/BB verdict | E3 and BB both returned `DONE_WITH_CONCERNS`: artifact-only local/non-admitted candidate-scoped Demo authorization is acceptable only if it remains no-runtime/no-order/no-live/no-Cost-Gate mutation; execution stays blocked. | Broad chat authorization is not a machine-checkable grant. Actual order path needs exact bounded Demo authorization plus fresh E3/BB order-envelope/runtime checks. |
| PG / proof exclusions | v537 read-only PG: 72h demo fills `106`; missing order/context/blank strategy `0/0/0`; proof-excluded rows include `flash_dip_buy`, risk-close cleanup, and `unattributed:bybit_auto`. | These rows cannot count toward bounded-probe proof, Cost Gate proof, promotion evidence, or risk-adjusted net-PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T032857Z_avax_touchability_bootstrap_source_only.json` |
| `active_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` |
| `blocker_goal` | Convert the selected AVAX candidate into a no-authority bounded Demo authorization review checkpoint, while preserving Cost Gate, Guardian/risk, Decision Lease, Rust authority, auditability, and reconstructability boundaries. |
| `profit_relevance` | This is the shortest safe bridge from a high-upside false-negative candidate to candidate-matched execution evidence after fees/slippage. |
| `new_evidence_delta_required` | Candidate selection done; prior touchability/bootstrap and source readiness must be checked before considering any authorization packet. |
| `new_evidence_delta_found` | Prior bootstrap is already done; fresh authority-readiness and defer-only authorization artifacts are aligned for `grid_trading|AVAXUSDT|Sell`; E3/BB reviewed artifact-only boundaries. |
| `anti_repeat_decision` | `P0-BOUNDED-PROBE-FIRST-ATTEMPT-TOUCHABILITY-BOOTSTRAP-SOURCE-ONLY` -> `NO-OP_ALREADY_DONE`; `P0-BOUNDED-PROBE-AUTHORIZATION` -> source/read-only review proceeded; actual grant -> `BLOCKED_BY_OPERATOR_ACTION` until exact machine-checkable authorization input exists. |
| `status` | `BLOCKED_BY_OPERATOR_ACTION` for actual grant; no-authority review packet is `DONE_WITH_CONCERNS`. |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION-STRUCTURED-STANDING-OR-TYPED-CONFIRM` if the operator wants to grant a bounded Demo probe; otherwise resume source-only `P1-LEARNING-LOOP-CLOSURE`. |
| `why_not_repeating_current_blocker` | Repeating bootstrap or broad-authorization review would only restate existing evidence. The next state change requires either a valid structured standing Demo authorization object, the exact typed confirm phrase, or a deliberate switch to source-only P1 work. |

## §2 Active Dispatch Queue

| ID | P | Status | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE_WITH_CONCERNS | PM -> QC/MIT/BB -> PM | Exactly one candidate selected; review-only packet; no probe/order/live authority; proof exclusions recorded. | Report `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading|AVAXUSDT|Sell`. | No-repeat unless new candidate/cap/fee/touchability evidence appears. |
| `P0-BOUNDED-PROBE-FIRST-ATTEMPT-TOUCHABILITY-BOOTSTRAP-SOURCE-ONLY` | 0 | DONE / NO-OP_ALREADY_DONE | PM -> PA/E1 -> E2/E4 -> PM | Source-only near-touch-or-skip bootstrap contract exists for exact AVAX side-cell; no authority; candidate-matched lineage required before proof. | Report `2026-06-25--avax_touchability_bootstrap_source_patch.md`; placement repair plan status `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`. | Do not rerun unless source, candidate, cap, fee, or touchability artifacts materially change. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | PM -> E3 -> BB -> Operator/QC -> PM | Candidate-specific bounded Demo authorization packet only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless exact bounded authorization is admitted and later reviewed by E3/BB. | Report `2026-06-26--avax_authorization_review_ready_no_authority.md`; defer packet `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, blocking gates `[]`, no auth object, typed confirm missing. | Paused. To grant: provide/admit valid `standing_demo_operator_authorization_v1` or exact typed confirm for `grid_trading|AVAXUSDT|Sell`, max `1`, TTL `<=4h`; then run fresh E3/BB order-envelope/runtime-source/reconciliation review before any order. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Wait for an authorized bounded Demo probe with candidate-matched outcomes. |
| `P1-LEARNING-LOOP-CLOSURE` | 1 | WAITING | PM -> PA/CC -> PM | Decide durable learning SSOT: artifact ledger vs PG-backed Cost Gate learning ledger. | Current checkpoint did not mutate learning authority or ledgers. | If bounded authorization remains blocked, resume here as the next source-only autonomy improvement. |
| `P1-AUTONOMOUS-PARAMETER-PROPOSAL` | 1 | WAITING | PM -> PA/E1 -> E2 -> E4 -> PM | Learning output may become a reviewable proposal only; it must not mutate order/risk/live state. | Proposal helpers remain review-only. | Resume after either bounded authorization or P1 learning SSOT checkpoint. |
| `P1-RUNTIME-HEALTH-HYGIENE-LOCAL-LINEAGE-68-STALE-WORKING` | 1 | WAITING | PM -> E3/BB -> PM | Determine whether health [68] should ignore exchange-clean local close/risk stale `Working` rows or whether a reconciler/source fix is needed. | v537: exchange book clean; [68] still FAILs from 4 local stale `Working` rows with NULL details. | Defer unless [68] blocks authorization/admission review. |
| `P1-RUNTIME-HEALTH-HYGIENE` | 1 | WAITING | PM -> E3 -> BB -> PM | Reconcile runtime drift without unreviewed restart/rebuild/env mutation. | Linux checkout still `d2cd70d0`; no v538 sync/restart. | Consider only if a future bounded authorization/admission packet needs runtime propagation. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | DEFERRED | PM -> BB/E2/E4 -> PM | Production full-scan pagination adoption path recorded and reviewed. | Mac source has full-scan helper; runtime source may still lack it depending on sync point. | Carry into runtime source-sync review only if future exchange inventory/reconciler work needs it. |

## §3 Hard Gates

| Gate | Trigger | Rule |
|---|---|---|
| Authorization object | Any move from defer/review packet to granted bounded Demo probe. | Requires exact typed confirm or valid structured standing Demo authorization object scoped to `grid_trading|AVAXUSDT|Sell`, max `1`, TTL `<=4h`, demo only. Broad chat authorization is insufficient for machine-checkable authority. |
| Runtime/order path | Any public/private Bybit call, adapter/writer enablement, plan mutation, or order submission. | Requires fresh PM -> E3 -> BB -> PM order-envelope/runtime-source/reconciliation review. No current authority exists. |
| Cost Gate | Any attempt to reduce global Cost Gate or treat a row as proof. | Global Cost Gate must not be lowered. Proof must be candidate-matched and include fills, fees, slippage, lineage, controls, and execution realism. |
| Live/mainnet | Any mainnet key/order/path. | Out of scope; no live authority. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Do not lower global Cost Gate, widen caps/freshness gates, fake freshness, or bypass Guardian/risk/Decision Lease/Rust authority.
- `flash_dip_buy` demo fills, cleanup/risk-close fills, unattributed fills, local stale Working rows, artifact counts, source-smoke, single-window MM positives, and replay-only results cannot count as Cost Gate, bounded-probe, promotion, or risk-adjusted net-PnL proof.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.

## §5 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Why it might make money | Fastest safe test | Required data | Failure condition | Authority |
|---|---|---|---|---|---|---|
| AVAX false-negative near-touch bounded Demo | upside High; evidence Medium; realism Medium; cost Good; time Fast; account risk Low if capped; governance risk Medium; autonomy High | Historic blocked outcomes clear current modeled cost by wide margin; near-touch-or-skip may convert false-negative edge into real candidate-matched fills. | Exact no-authority authorization packet first; after valid grant, one capped Demo post-only near-touch-or-skip attempt with fresh BBO and full lineage. | Valid authorization object, fresh BBO, cap/min-notional, order/fill/fee/slippage lineage, matched blocked controls. | No touch, taker fill, stale BBO, missing lineage, net after fees/slippage <= 0, or control underperforms. | Structured bounded Demo authorization + E3/BB order-envelope review required. |
| AVAX regime filter before probe | upside Medium-High; evidence Medium; realism Medium; cost Good; time Medium; account risk None source-only; governance Low | AVAX false-negative edge may concentrate in spread/volatility/liquidity regimes, reducing wasted probes. | Source-only scorecard over existing blocked outcomes; output reviewable filter proposal only. | Blocked outcomes, L1/spread/volatility features, fee model, regime labels. | Filter loses net cushion, overfits one window, or reduces sample below floor. | Research/proposal only. |
| Current-fee maker/MM repeat-window branch | upside Medium; evidence Low; realism Low-Medium; cost Tight; time Medium; account risk None source-only; governance Low | If repeated current-fee-positive maker windows exist, it may become a lower-capital execution path. | Accumulate independent windows and maker-realism score without claiming proof. | Recent maker/taker fees, fills, queue position proxies, spread/markout, distinct dates. | Single-window only, net cushion below fees/slippage, or maker ratio cannot be achieved. | Research/proposal only. |

## §6 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--avax_authorization_review_ready_no_authority.md
python3 -m json.tool /tmp/openclaw/avax_bounded_probe_authorization_review_20260626T032857Z/operator_authorization_review_defer_avax_sell_20260626T032857Z.json | sed -n '1,220p'
python3 -m json.tool /tmp/openclaw/avax_bounded_probe_authorization_review_20260626T032857Z/authority_path_readiness_avax_sell_20260626T032857Z.json | sed -n '1,160p'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog.
