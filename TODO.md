# Xuanheng TODO - Active Dispatch Queue

**Version** v566 | **Date** 2026-06-26
**Source/runtime pointer**: v566 source-code checkpoint commit `73ae76a88492a8b9ad51eadbd7412984398116d5` is on `main`; this TODO lives at current repo HEAD. Linux runtime source and crontab expected-head pins remain `dd22810ee41c353c1d214d9a3217862d7b2bac74`.
**Current posture**: fee/slippage/maker-taker schema contract is `DONE_WITH_CONCERNS`; P0 bounded authorization remains blocked/no-repeat because latest AVAX auth is still review-required/defer/no-authority. Operator requested pause after this round.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--fee_slippage_maker_taker_schema_no_order.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T08:37:45Z`: Linux runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`; user API service `active`, MainPID `2218842`. | Runtime intentionally unchanged by v566. Do not sync/restart unless a separate runtime blocker is opened. |
| Artifact SSOT path | Current cost-gate artifacts are under `trade-core:/tmp/openclaw/cost_gate_learning_lane/`. | Runtime artifact checks must read this path; local `/tmp` only has source-only smokes. |
| Authorization latest | `2026-06-26T08:30:47Z`, sha `c75fb61d70596f62d04bf47855f64e0964178455d405d0c87314cadf67db94ed`, status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, candidate `grid_trading\|AVAXUSDT\|Sell`, no authorization object/authority. | This is an artifact delta but not an authorization delta. P0 bounded probe authorization stays blocked/no-repeat. |
| Autonomous proposal latest | `2026-06-26T08:29:20Z`, sha `abe948aa9196f1f5569d1118ba00b735817a1878637d6f30d3f5a2b6dce74a1f`, status `REVIEWABLE_PARAMETER_PROPOSAL_READY`, candidate AVAX, no authority/proof. | Proposal remains review-only; no direct order/risk/live mutation. |
| Friction scorecard latest | `2026-06-26T08:30:47Z`, sha `ed57e0e5c4ce04155450d6dac25e364c0dad2e6324d8a672d68fbf1890f96b71`, status `FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY`. | Ranking/candidate selection is already closed; do not rerun without new ranking/cap evidence. |
| Fee/slippage schema smoke | `/tmp/openclaw/fee_slippage_maker_taker_schema_smoke_20260626T083106Z/fee_slippage_maker_taker_schema.json`, sha `a08b23bf3ed649a899ea1fc37c174fda4d4dcd13a8762c169d77316ca04d1878`, status `FEE_SLIPPAGE_MAKER_TAKER_SCHEMA_READY_NO_AUTHORITY`. | Future proof rows require actual fee, slippage, maker/taker label, lineage, and reconstructable net PnL; this is not order admission or profit proof. |
| Proof exclusions | Exclude `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale `Working` rows, artifact counts, source-smoke, single-window MM positives, replay-only results, and cross-symbol controls as AVAX proof. | These never count for bounded-probe proof, Cost Gate proof, promotion, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T083106Z_fee_slippage_maker_taker_schema_no_order.json` |
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-FEE-SLIPPAGE-MAKER-TAKER-SCHEMA-NO-ORDER` |
| `blocker_goal` | Define a source-only fee/slippage/maker-taker schema contract for future AVAX bounded Demo outcomes and matched controls. |
| `profit_relevance` | Future profitability proof must be real risk-adjusted net PnL after actual fees/slippage, with maker/taker role and lineage; modeled cost-only rows cannot support promotion. |
| `previous_evidence_checked` | v565 TODO; current-cap worksheet; remote auth/proposal/friction artifacts; runtime source/service metadata. |
| `new_evidence_delta_required` | Open fee/slippage/maker-taker proof-quality schema gap; no real P0 authorization delta. |
| `new_evidence_delta_found` | New source helper, focused tests, and smoke artifact `FEE_SLIPPAGE_MAKER_TAKER_SCHEMA_READY_NO_AUTHORITY`. |
| `anti_repeat_decision` | Proceeded with distinct source-only blocker; do not rerun P0 authorization, candidate selection, control identity, current-cap worksheet, or fee schema on the same artifacts. |
| `loop_status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` if real auth delta appears; otherwise after pause, `P1-AGGRESSIVE-ALPHA-FRESH-BBO-READONLY-READINESS-PATH-NO-ORDER`. |
| `why_not_repeating_current_blocker` | Fee schema is source-backed and smoke-tested; repeating would add no new evidence. |

## §2 Active Dispatch Queue

| ID | P | Status | Loop decision | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; §0 proof exclusions. | No-repeat unless exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading\|AVAXUSDT\|Sell`. | No-repeat unless fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | `BLOCKED_BY_RUNTIME_AUTHORIZATION` | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid scoped authorization is admitted and E3/BB review passes. | `2026-06-26T08:30:47Z` auth latest sha `c75fb61d...`: AVAX-scoped, `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, no authority object/grant. | No read-only repeat. Resume only on real candidate-scoped typed-confirm, standing-auth, or authority artifact delta. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | `WAITING_FOR_AUTHORIZED_OUTCOMES` | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe has candidate-matched outcomes. |
| `P1-AGGRESSIVE-ALPHA-SOURCE-ONLY-CONTROL-IDENTITY-CONTRACT-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Source-only contract defines AVAX proof identity, same-side-cell controls, cross-symbol exclusions, and no-authority answers. | `2026-06-26--source_only_control_identity_contract_no_order.md`; smoke `SOURCE_ONLY_CONTROL_IDENTITY_CONTRACT_READY_NO_AUTHORITY`. | No-repeat unless proof/control identity semantics change. |
| `P1-AGGRESSIVE-ALPHA-CURRENT-CAP-STAIRCASE-RISK-WORKSHEET-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Current-cap tier ladder and risk worksheet exists; no cap/risk mutation, no order admission, no authority/proof claim. | `2026-06-26--current_cap_staircase_risk_worksheet_no_order.md`; smoke `tier_count=8`, BBO refresh required. | No-repeat unless construction preview, cap/risk contract, or auth evidence changes. |
| `P1-AGGRESSIVE-ALPHA-FEE-SLIPPAGE-MAKER-TAKER-SCHEMA-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Actual fee/slippage/maker-taker/lineage/net-PnL reconstruction schema exists; fail-closed no-authority answers; focused + adjacent tests pass. | v566 report; smoke `FEE_SLIPPAGE_MAKER_TAKER_SCHEMA_READY_NO_AUTHORITY`; source checkpoint `73ae76a88492a8b9ad51eadbd7412984398116d5`. | No-repeat unless future outcome schema/proof requirements change. |
| `P1-AGGRESSIVE-ALPHA-FRESH-BBO-READONLY-READINESS-PATH-NO-ORDER` | 1 | WAITING | `READY_SOURCE_ONLY_AFTER_OPERATOR_PAUSE` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Define a no-order fresh BBO/instrument readiness path that can feed later construction/order-admission review without private/order authority. | Current-cap and fee-schema contracts both point to fresh BBO as next safe source-only path when no real auth delta exists. | Paused by operator request. On resume, run this specific blocker unless real P0 auth delta appears first. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Survival/risk | Profit is optimized only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | Demo API permission is not live/mainnet permission. Bounded Demo grant requires candidate-scoped structured auth or exact typed confirm plus E3/BB review. |
| Runtime/order path | Bybit private/trading calls, adapter/writer enablement, plan mutation, order submission, PG write, crontab/env edit, or service restart require reviewed runtime chain. |
| Cost Gate | Global Cost Gate must not be lowered. Proof must be candidate-matched and include fills, actual fees, slippage, lineage, controls, and execution realism. |
| Candidate selection | AVAX remains the P0 bounded candidate. ETH and other symbols remain research-only unless separate cap/evidence review changes this. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Fastest safe test | Authority |
|---|---|---|---|
| Fresh BBO read-only readiness path | upside Medium-High; evidence Medium; realism Medium after quote; cost critical; time Fast; account risk None; governance Low-Medium; autonomy High | Source-only/read-only public quote readiness design with exact candidate/BBO/instrument provenance; no order admission. | None for source-only design; E3/BB if runtime/public quote capture is used; P0 auth before any order. |
| Maker-first micro tier placement policy | upside Medium; evidence Low-Medium; realism Low until fills; cost favorable only if maker; time Medium; account risk None now; governance Medium; autonomy Medium | Source-only policy using current cap tiers plus future fee/slippage schema; no placement call. | Research only; E3/BB + P0 auth before any order. |
| Execution realism failure review | upside Medium; evidence Medium design-only; realism High once fills exist; cost after fees critical; time Fast; account risk None; governance Low; autonomy High | Keep future outcome review proof-eligible only when fee/slippage/maker-taker/lineage schema passes. | None for design; bounded outcomes required later. |

## §5 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--fee_slippage_maker_taker_schema_no_order.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T083106Z_fee_slippage_maker_taker_schema_no_order.json | sed -n '1,220p'
python3 -m json.tool /tmp/openclaw/fee_slippage_maker_taker_schema_smoke_20260626T083106Z/fee_slippage_maker_taker_schema.json | sed -n '1,220p'
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_fee_slippage_maker_taker_schema_contract.py
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: A next PM can identify the next action in under one minute: pause now; on resume, real P0 auth delta takes precedence, otherwise run fresh BBO read-only readiness path, not another broad audit.
