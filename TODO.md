# Xuanheng TODO - Active Dispatch Queue

**Version** v568 | **Date** 2026-06-26
**Source/runtime pointer**: v568 source-code checkpoint commit `7d620f08ca5863f85d5965866d7b87c39f9a76c7` is on `main`; this TODO lives at current repo HEAD. Linux runtime source and crontab expected-head pins remain `dd22810ee41c353c1d214d9a3217862d7b2bac74`.
**Current posture**: maker-first micro-tier placement policy is `DONE_WITH_CONCERNS`; per operator request, pause after this round. P0 bounded authorization remains blocked/no-repeat because latest AVAX auth is still review-required/no-authority.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--maker_first_micro_tier_policy_no_order.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T08:56:29Z`: Linux runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`; user API service `active`, MainPID `2218842`. | Runtime intentionally unchanged by v568. Do not sync/restart unless a separate runtime blocker is opened. |
| Artifact SSOT path | Current cost-gate artifacts are under `trade-core:/tmp/openclaw/cost_gate_learning_lane/`. | Runtime artifact checks must read this path; local `/tmp` only has source-only smokes. |
| Authorization latest | `2026-06-26T08:45:05Z`, sha `d7716a6017c4e8b99428751414d35f89abe981fda96af36ec02f1e91c86ee09f`, status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, candidate `grid_trading\|AVAXUSDT\|Sell`, no authorization object/authority. | This is an artifact delta but not an authorization delta. P0 bounded probe authorization stays blocked/no-repeat. |
| Autonomous proposal latest | `2026-06-26T08:29:20Z`, sha `abe948aa9196f1f5569d1118ba00b735817a1878637d6f30d3f5a2b6dce74a1f`, status `REVIEWABLE_PARAMETER_PROPOSAL_READY`, candidate AVAX, no authority/proof. | Proposal remains review-only; no direct order/risk/live mutation. |
| Friction scorecard latest | `2026-06-26T08:30:47Z`, sha `ed57e0e5c4ce04155450d6dac25e364c0dad2e6324d8a672d68fbf1890f96b71`, status `FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY`. | Ranking/candidate selection is already closed; do not rerun without new ranking/cap evidence. |
| Maker policy smoke | `/tmp/openclaw/maker_first_micro_tier_policy_smoke_20260626T085600Z/maker_first_micro_tier_policy.json`, sha `fa5fdbb91e09601dc49c63a2464f5c796b71b622bf3eed9e641e714eb33ba306`, status `MAKER_FIRST_MICRO_TIER_POLICY_READY_NO_AUTHORITY`. | Primary review tier is `0.9 AVAX / 5.4576 USDT`; policy is post-only maker-first limit-or-skip and does not permit quote capture, placement, order admission, or proof. |
| Proof exclusions | Exclude `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale `Working` rows, artifact counts, source-smoke, single-window MM positives, replay-only results, and cross-symbol controls as AVAX proof. | These never count for bounded-probe proof, Cost Gate proof, promotion, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T085600Z_maker_first_micro_tier_policy_no_order.json` |
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-MAKER-FIRST-MICRO-TIER-PLACEMENT-POLICY-NO-ORDER` |
| `blocker_goal` | Define a source-only maker-first post-only micro-tier placement/skip policy for the selected AVAX bounded Demo candidate, without quote capture, placement calls, order admission, runtime mutation, or authority. |
| `profit_relevance` | Future AVAX profitability testing needs maker economics, cap-respecting small tiers, spread/cost skip rules, and taker-fallback fail-closed semantics before any bounded Demo order review. |
| `previous_evidence_checked` | v567 TODO; current-cap worksheet smoke; fee/slippage schema smoke; fresh BBO readiness smoke; remote auth/proposal/friction artifacts; runtime source/service metadata. |
| `new_evidence_delta_required` | Completed fresh BBO readiness contract plus open maker-first tier/placement/skip policy; no real P0 authorization delta. |
| `new_evidence_delta_found` | New source helper, focused/adjacent tests, and smoke artifact `MAKER_FIRST_MICRO_TIER_POLICY_READY_NO_AUTHORITY`. |
| `anti_repeat_decision` | Proceeded with distinct source-only blocker; do not rerun P0 authorization, candidate selection, current-cap worksheet, fee schema, fresh BBO readiness, or maker policy on the same artifacts. |
| `loop_status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` if real auth delta appears; otherwise `P1-AGGRESSIVE-ALPHA-REVIEWED-PUBLIC-QUOTE-CAPTURE-PACKET-NO-CAPTURE` after operator resumes. |
| `why_not_repeating_current_blocker` | Policy is source-backed, smoke-tested, and adjacent-tested; repeating would add no new evidence. |
| `operator_action_required` | Pause requested by operator after this round; resume only when operator asks to continue or provides a real auth/runtime evidence delta. |

## §2 Active Dispatch Queue

| ID | P | Status | Loop decision | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; §0 proof exclusions. | No-repeat unless exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading\|AVAXUSDT\|Sell`. | No-repeat unless fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | `BLOCKED_BY_RUNTIME_AUTHORIZATION` | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid scoped authorization is admitted and E3/BB review passes. | `2026-06-26T08:45:05Z` auth latest sha `d7716a60...`: AVAX-scoped, `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, no authority object/grant. | No read-only repeat. Resume only on real candidate-scoped typed-confirm, standing-auth, or authority artifact delta. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | `WAITING_FOR_AUTHORIZED_OUTCOMES` | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe has candidate-matched outcomes. |
| `P1-AGGRESSIVE-ALPHA-SOURCE-ONLY-CONTROL-IDENTITY-CONTRACT-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Source-only contract defines AVAX proof identity, same-side-cell controls, cross-symbol exclusions, and no-authority answers. | `2026-06-26--source_only_control_identity_contract_no_order.md`; smoke `SOURCE_ONLY_CONTROL_IDENTITY_CONTRACT_READY_NO_AUTHORITY`. | No-repeat unless proof/control identity semantics change. |
| `P1-AGGRESSIVE-ALPHA-CURRENT-CAP-STAIRCASE-RISK-WORKSHEET-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Current-cap tier ladder and risk worksheet exists; no cap/risk mutation, no order admission, no authority/proof claim. | `2026-06-26--current_cap_staircase_risk_worksheet_no_order.md`; smoke `tier_count=8`, BBO refresh required. | No-repeat unless construction preview, cap/risk contract, or auth evidence changes. |
| `P1-AGGRESSIVE-ALPHA-FEE-SLIPPAGE-MAKER-TAKER-SCHEMA-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Actual fee/slippage/maker-taker/lineage/net-PnL reconstruction schema exists; fail-closed no-authority answers. | `2026-06-26--fee_slippage_maker_taker_schema_no_order.md`; smoke `FEE_SLIPPAGE_MAKER_TAKER_SCHEMA_READY_NO_AUTHORITY`. | No-repeat unless future outcome schema/proof requirements change. |
| `P1-AGGRESSIVE-ALPHA-FRESH-BBO-READONLY-READINESS-PATH-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Source-only public quote/readiness handoff contract exists; no quote capture, no order admission, no authority/proof claim. | `2026-06-26--fresh_bbo_readonly_readiness_path_no_order.md`; smoke `FRESH_BBO_READONLY_READINESS_PATH_READY_NO_AUTHORITY`. | No-repeat unless quote/readiness handoff semantics change. |
| `P1-AGGRESSIVE-ALPHA-MAKER-FIRST-MICRO-TIER-PLACEMENT-POLICY-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Maker-first post-only micro-tier placement/skip policy exists; no quote capture, placement call, order admission, authority, or proof claim. | v568 report; smoke `MAKER_FIRST_MICRO_TIER_POLICY_READY_NO_AUTHORITY`; source checkpoint `7d620f08ca5863f85d5965866d7b87c39f9a76c7`. | No-repeat unless tier/placement/cost-skip semantics change. |
| `P1-AGGRESSIVE-ALPHA-REVIEWED-PUBLIC-QUOTE-CAPTURE-PACKET-NO-CAPTURE` | 1 | DEFERRED | `WAITING_FOR_OPERATOR_RESUME_OR_AUTH_DELTA` | PM -> E3 -> BB -> PM | Produce a reviewed public quote capture packet only; no capture, no private/order endpoint, no auth headers, no runtime mutation, no order authority. | Maker policy max safe next action; fresh BBO readiness contract. | Do not start now. On resume, first check for real P0 auth delta; if none, prepare no-capture review packet. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Survival/risk | Profit is optimized only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | Broad Demo API permission is not automatic bounded-probe/order authority. Bounded Demo grant requires candidate-scoped structured auth or exact typed confirm plus E3/BB review. |
| Runtime/order path | Bybit private/trading calls, public quote capture, adapter/writer enablement, plan mutation, order submission, PG write, crontab/env edit, or service restart require reviewed runtime chain. |
| Cost Gate | Global Cost Gate and freshness gate must not be lowered. Proof must be candidate-matched and include fills, actual fees, slippage, lineage, controls, and execution realism. |
| Candidate selection | AVAX remains the P0 bounded candidate. ETH and other symbols remain research-only unless separate cap/evidence review changes this. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Fastest safe test | Authority |
|---|---|---|---|
| Reviewed public quote capture packet | upside Medium-High; evidence Medium design; realism Medium after capture; time Fast; account risk None; governance Low-Medium; autonomy High | Prepare an E3/BB-reviewed packet for public GET-only AVAX quote capture, but do not capture. | None for packet; E3/BB review before any runtime quote capture. |
| Maker-first micro-tier bounded probe | upside Medium; evidence Medium design-only; realism Low until fills; cost favorable if maker; time Medium; account risk Low bounded later; governance Medium; autonomy High | Already source-designed; next empirical step would require fresh quote, construction review, and candidate-scoped bounded authorization. | E3/BB + candidate-scoped bounded auth before any order. |
| Spread-aware no-trade skip guard | upside Medium; evidence Medium; realism Medium after fresh BBO; cost critical; time Fast; account risk None; governance Low; autonomy High | Carry v568 skip formula into reviewed quote/construction packet. | None for design; runtime quote/order path requires review/auth. |

## §5 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--maker_first_micro_tier_policy_no_order.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T085600Z_maker_first_micro_tier_policy_no_order.json | sed -n '1,220p'
python3 -m json.tool /tmp/openclaw/maker_first_micro_tier_policy_smoke_20260626T085600Z/maker_first_micro_tier_policy.json | sed -n '1,220p'
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_maker_first_micro_tier_policy.py
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: A next PM can identify the next action in under one minute: stop now per operator; on resume, real P0 auth delta takes precedence, otherwise prepare reviewed public quote capture packet with no capture.
