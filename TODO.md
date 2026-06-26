# Xuanheng TODO - Active Dispatch Queue

**Version** v569 | **Date** 2026-06-26
**Source/runtime pointer**: v569 source-code checkpoint commit `d2d97b96df9a82982bbb02325821b9aa7001560f` is on `main`; this TODO lives at current repo HEAD. Linux runtime source and crontab expected-head pins remain `dd22810ee41c353c1d214d9a3217862d7b2bac74`.
**Current posture**: reviewed public quote capture packet is `DONE_WITH_CONCERNS`; P0 bounded authorization remains blocked/no-repeat because latest AVAX auth is still review-required/no-authority.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--reviewed_public_quote_capture_packet_no_capture.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T09:12:05Z`: Linux runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`; user API service `active`, MainPID `2218842`. | Runtime intentionally unchanged by v569. Do not sync/restart unless a separate runtime blocker is opened. |
| Artifact SSOT path | Current cost-gate artifacts are under `trade-core:/tmp/openclaw/cost_gate_learning_lane/`. | Runtime artifact checks must read this path; local `/tmp` only has source-only smokes. |
| Authorization latest | `2026-06-26T09:00:04Z`, sha `85c92d10f07f776ee70547bd3fa362856f3f447fcc52e8ac5dbf043d83ea7bda`, status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, decision `defer`, candidate `grid_trading\|AVAXUSDT\|Sell`, no authorization object/authority. | This is an artifact delta but not an authorization delta. P0 bounded probe authorization stays blocked/no-repeat. |
| Autonomous proposal latest | `2026-06-26T08:29:20Z`, sha `abe948aa9196f1f5569d1118ba00b735817a1878637d6f30d3f5a2b6dce74a1f`, status `REVIEWABLE_PARAMETER_PROPOSAL_READY`, candidate AVAX, no authority/proof. | Proposal remains review-only; no direct order/risk/live mutation. |
| Friction scorecard latest | `2026-06-26T08:30:47Z`, sha `ed57e0e5c4ce04155450d6dac25e364c0dad2e6324d8a672d68fbf1890f96b71`, status `FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY`. | Ranking/candidate selection is already closed; do not rerun without new ranking/cap evidence. |
| Reviewed public quote packet smoke | `/tmp/openclaw/reviewed_public_quote_capture_packet_smoke_20260626T091205Z/reviewed_public_quote_capture_packet.json`, sha `dc9536ff502a565a3df7568d7d6bc11c215373158839d141b827432b286d0b34`, status `REVIEWED_PUBLIC_QUOTE_CAPTURE_PACKET_READY_NO_CAPTURE_NO_AUTHORITY`. | Future capture is fixed to public GET-only request envelope and PM->E3->BB review; this is not capture, order admission, authority, or proof. |
| Proof exclusions | Exclude `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale `Working` rows, artifact counts, source-smoke, single-window MM positives, replay-only results, and cross-symbol controls as AVAX proof. | These never count for bounded-probe proof, Cost Gate proof, promotion, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T091205Z_reviewed_public_quote_capture_packet_no_capture.json` |
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-REVIEWED-PUBLIC-QUOTE-CAPTURE-PACKET-NO-CAPTURE` |
| `blocker_goal` | Produce a source-only reviewed public quote capture packet for the selected AVAX candidate, without quote capture, Bybit call, runtime mutation, order admission, or authority. |
| `profit_relevance` | Future AVAX profitability testing needs reconstructable fresh BBO/spread and instrument filters before maker-first construction can be economically reviewed. |
| `previous_evidence_checked` | v568 TODO; maker-first policy smoke; fresh BBO readiness smoke; remote auth/proposal/friction artifacts; runtime source/service metadata. |
| `new_evidence_delta_required` | Completed maker-first policy plus open no-capture quote packet design; no real P0 authorization delta. |
| `new_evidence_delta_found` | New source helper, focused/adjacent tests, and smoke artifact `REVIEWED_PUBLIC_QUOTE_CAPTURE_PACKET_READY_NO_CAPTURE_NO_AUTHORITY`. |
| `anti_repeat_decision` | Proceeded with distinct source-only no-capture blocker; do not rerun P0 authorization or no-capture packet on the same artifacts. |
| `loop_status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-AGGRESSIVE-ALPHA-PUBLIC-QUOTE-CAPTURE-RUNTIME-REVIEW` unless real P0 auth delta appears first. |
| `why_not_repeating_current_blocker` | Packet is source-backed, smoke-tested, and adjacent-tested; repeating would add no new evidence. |
| `operator_action_required` | False for source-only work; any runtime public quote capture must first open a fresh session state and use PM->E3->BB review. |

## §2 Active Dispatch Queue

| ID | P | Status | Loop decision | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; §0 proof exclusions. | No-repeat unless exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading\|AVAXUSDT\|Sell`. | No-repeat unless fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | `BLOCKED_BY_RUNTIME_AUTHORIZATION` | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid scoped authorization is admitted and E3/BB review passes. | `2026-06-26T09:00:04Z` auth latest sha `85c92d10...`: AVAX-scoped, `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, no authority object/grant. | No read-only repeat. Resume only on real candidate-scoped typed-confirm, standing-auth, or authority artifact delta. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | `WAITING_FOR_AUTHORIZED_OUTCOMES` | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe has candidate-matched outcomes. |
| `P1-AGGRESSIVE-ALPHA-CURRENT-CAP-STAIRCASE-RISK-WORKSHEET-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Current-cap tier ladder and risk worksheet exists; no cap/risk mutation, no order admission, no authority/proof claim. | `2026-06-26--current_cap_staircase_risk_worksheet_no_order.md`; smoke `tier_count=8`, BBO refresh required. | No-repeat unless construction preview, cap/risk contract, or auth evidence changes. |
| `P1-AGGRESSIVE-ALPHA-FEE-SLIPPAGE-MAKER-TAKER-SCHEMA-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Actual fee/slippage/maker-taker/lineage/net-PnL reconstruction schema exists; fail-closed no-authority answers. | `2026-06-26--fee_slippage_maker_taker_schema_no_order.md`; smoke `FEE_SLIPPAGE_MAKER_TAKER_SCHEMA_READY_NO_AUTHORITY`. | No-repeat unless future outcome schema/proof requirements change. |
| `P1-AGGRESSIVE-ALPHA-FRESH-BBO-READONLY-READINESS-PATH-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Source-only public quote/readiness handoff contract exists; no quote capture, no order admission, no authority/proof claim. | `2026-06-26--fresh_bbo_readonly_readiness_path_no_order.md`; smoke `FRESH_BBO_READONLY_READINESS_PATH_READY_NO_AUTHORITY`. | No-repeat unless quote/readiness handoff semantics change. |
| `P1-AGGRESSIVE-ALPHA-MAKER-FIRST-MICRO-TIER-PLACEMENT-POLICY-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Maker-first post-only micro-tier placement/skip policy exists; no quote capture, placement call, order admission, authority, or proof claim. | `2026-06-26--maker_first_micro_tier_policy_no_order.md`; smoke `MAKER_FIRST_MICRO_TIER_POLICY_READY_NO_AUTHORITY`. | No-repeat unless tier/placement/cost-skip semantics change. |
| `P1-AGGRESSIVE-ALPHA-REVIEWED-PUBLIC-QUOTE-CAPTURE-PACKET-NO-CAPTURE` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | No-capture review packet exists; no network/Bybit call, no capture, no runtime mutation, no order admission, no authority/proof claim. | v569 report; smoke `REVIEWED_PUBLIC_QUOTE_CAPTURE_PACKET_READY_NO_CAPTURE_NO_AUTHORITY`; source checkpoint `d2d97b96df9a82982bbb02325821b9aa7001560f`. | No-repeat unless quote capture review envelope semantics change. |
| `P1-AGGRESSIVE-ALPHA-PUBLIC-QUOTE-CAPTURE-RUNTIME-REVIEW` | 1 | READY | `READY_RUNTIME_REVIEW` | PM -> E3 -> BB -> PM | Review and, only if gates pass, perform one public/read-only AVAX quote capture artifact; no private/order endpoint, no auth headers, no order/probe/live authority. | v569 no-capture packet and fresh BBO readiness contract. | Open a new session_loop_state; verify no P0 auth delta first; then run PM->E3->BB review before any capture. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Survival/risk | Profit is optimized only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | Broad Demo API permission is not automatic bounded-probe/order authority. Bounded Demo grant requires candidate-scoped structured auth or exact typed confirm plus E3/BB review. |
| Runtime/order path | Bybit private/trading calls, adapter/writer enablement, plan mutation, order submission, PG write, crontab/env edit, or service restart require reviewed runtime chain. Public quote capture is read-only but still exchange-facing and must use PM->E3->BB review. |
| Cost Gate | Global Cost Gate and freshness gate must not be lowered. Proof must be candidate-matched and include fills, actual fees, slippage, lineage, controls, and execution realism. |
| Candidate selection | AVAX remains the P0 bounded candidate. ETH and other symbols remain research-only unless separate cap/evidence review changes this. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Fastest safe test | Authority |
|---|---|---|---|
| Public quote runtime capture | upside Medium-High; evidence Medium; realism Medium after capture; time Fast; account risk None; governance Medium; autonomy High | PM->E3->BB-reviewed public GET-only AVAX quote capture artifact. | E3/BB before capture; no order authority. |
| Adapter-backed construction preview refresh | upside Medium; evidence Medium after quote; realism Medium; cost important; time Medium; account risk None; governance Low-Medium; autonomy High | Convert reviewed quote to candidate market snapshot, then construction preview. | After reviewed capture; no order authority. |
| Maker spread skip calibration | upside Medium; evidence Medium after quote; realism Medium; cost critical; time Fast; account risk None; governance Low; autonomy High | Evaluate v568/v569 spread-cost skip formula from captured spread only. | Analysis only after reviewed capture; order path still needs bounded auth. |

## §5 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--reviewed_public_quote_capture_packet_no_capture.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T091205Z_reviewed_public_quote_capture_packet_no_capture.json | sed -n '1,220p'
python3 -m json.tool /tmp/openclaw/reviewed_public_quote_capture_packet_smoke_20260626T091205Z/reviewed_public_quote_capture_packet.json | sed -n '1,220p'
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_reviewed_public_quote_capture_packet.py
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: A next PM can identify the next action in under one minute: real P0 auth delta takes precedence; otherwise open public quote capture runtime review with PM->E3->BB, not another no-capture/source audit.
