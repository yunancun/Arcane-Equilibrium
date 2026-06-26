# Xuanheng TODO - Active Dispatch Queue

**Version** v567 | **Date** 2026-06-26
**Source/runtime pointer**: v567 source-code checkpoint commit `07050103e35c1acabb251e5743215e0b8af92c75` is on `main`; this TODO lives at current repo HEAD. Linux runtime source and crontab expected-head pins remain `dd22810ee41c353c1d214d9a3217862d7b2bac74`.
**Current posture**: fresh BBO read-only readiness path is `DONE_WITH_CONCERNS`; P0 bounded authorization remains blocked/no-repeat because latest AVAX auth is still review-required/no-authority.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--fresh_bbo_readonly_readiness_path_no_order.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T08:45:12Z`: Linux runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`; user API service `active`, MainPID `2218842`. | Runtime intentionally unchanged by v567. Do not sync/restart unless a separate runtime blocker is opened. |
| Artifact SSOT path | Current cost-gate artifacts are under `trade-core:/tmp/openclaw/cost_gate_learning_lane/`. | Runtime artifact checks must read this path; local `/tmp` only has source-only smokes. |
| Authorization latest | `2026-06-26T08:45:05Z`, sha `d7716a6017c4e8b99428751414d35f89abe981fda96af36ec02f1e91c86ee09f`, status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, candidate `grid_trading\|AVAXUSDT\|Sell`, no authorization object/authority. | This is an artifact delta but not an authorization delta. P0 bounded probe authorization stays blocked/no-repeat. |
| Autonomous proposal latest | `2026-06-26T08:29:20Z`, sha `abe948aa9196f1f5569d1118ba00b735817a1878637d6f30d3f5a2b6dce74a1f`, status `REVIEWABLE_PARAMETER_PROPOSAL_READY`, candidate AVAX, no authority/proof. | Proposal remains review-only; no direct order/risk/live mutation. |
| Friction scorecard latest | `2026-06-26T08:30:47Z`, sha `ed57e0e5c4ce04155450d6dac25e364c0dad2e6324d8a672d68fbf1890f96b71`, status `FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY`. | Ranking/candidate selection is already closed; do not rerun without new ranking/cap evidence. |
| Fresh BBO readiness smoke | `/tmp/openclaw/fresh_bbo_readonly_readiness_path_smoke_20260626T084511Z/fresh_bbo_readonly_readiness_path.json`, sha `c521a821956913200f26b0c76d8e2510192a6ce9bfe1b27be7cd66930bbe11e4`, status `FRESH_BBO_READONLY_READINESS_PATH_READY_NO_AUTHORITY`. | Future quote capture must be public/read-only, exact AVAX, no auth/private/order path, max BBO age `1000ms`, adapter-backed before construction preview. This is not quote capture, order admission, or profit proof. |
| Proof exclusions | Exclude `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale `Working` rows, artifact counts, source-smoke, single-window MM positives, replay-only results, and cross-symbol controls as AVAX proof. | These never count for bounded-probe proof, Cost Gate proof, promotion, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T084511Z_fresh_bbo_readonly_readiness_path_no_order.json` |
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-FRESH-BBO-READONLY-READINESS-PATH-NO-ORDER` |
| `blocker_goal` | Define a source-only fresh BBO/instrument readiness path for the selected AVAX bounded Demo candidate, without exchange capture or authority. |
| `profit_relevance` | Future profitability testing needs fresh bid/ask/spread and Trading instrument filters before construction/order-admission review; stale BBO can create false edge after fees/slippage. |
| `previous_evidence_checked` | v566 TODO; fee schema smoke; remote auth/proposal/friction artifacts; runtime source/service metadata. |
| `new_evidence_delta_required` | Open source-only fresh BBO/instrument readiness path; no real P0 authorization delta. |
| `new_evidence_delta_found` | New source helper, focused/adjacent tests, and smoke artifact `FRESH_BBO_READONLY_READINESS_PATH_READY_NO_AUTHORITY`. |
| `anti_repeat_decision` | Proceeded with distinct source-only blocker; do not rerun P0 authorization, candidate selection, current-cap worksheet, fee schema, or fresh BBO readiness on the same artifacts. |
| `loop_status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` if real auth delta appears; otherwise `P1-AGGRESSIVE-ALPHA-MAKER-FIRST-MICRO-TIER-PLACEMENT-POLICY-NO-ORDER`. |
| `why_not_repeating_current_blocker` | Readiness contract is source-backed, smoke-tested, and adjacent-tested; repeating would add no new evidence. |

## §2 Active Dispatch Queue

| ID | P | Status | Loop decision | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; §0 proof exclusions. | No-repeat unless exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading\|AVAXUSDT\|Sell`. | No-repeat unless fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | `BLOCKED_BY_RUNTIME_AUTHORIZATION` | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid scoped authorization is admitted and E3/BB review passes. | `2026-06-26T08:45:05Z` auth latest sha `d7716a60...`: AVAX-scoped, `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, no authority object/grant. | No read-only repeat. Resume only on real candidate-scoped typed-confirm, standing-auth, or authority artifact delta. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | `WAITING_FOR_AUTHORIZED_OUTCOMES` | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe has candidate-matched outcomes. |
| `P1-AGGRESSIVE-ALPHA-SOURCE-ONLY-CONTROL-IDENTITY-CONTRACT-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Source-only contract defines AVAX proof identity, same-side-cell controls, cross-symbol exclusions, and no-authority answers. | `2026-06-26--source_only_control_identity_contract_no_order.md`; smoke `SOURCE_ONLY_CONTROL_IDENTITY_CONTRACT_READY_NO_AUTHORITY`. | No-repeat unless proof/control identity semantics change. |
| `P1-AGGRESSIVE-ALPHA-CURRENT-CAP-STAIRCASE-RISK-WORKSHEET-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Current-cap tier ladder and risk worksheet exists; no cap/risk mutation, no order admission, no authority/proof claim. | `2026-06-26--current_cap_staircase_risk_worksheet_no_order.md`; smoke `tier_count=8`, BBO refresh required. | No-repeat unless construction preview, cap/risk contract, or auth evidence changes. |
| `P1-AGGRESSIVE-ALPHA-FEE-SLIPPAGE-MAKER-TAKER-SCHEMA-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Actual fee/slippage/maker-taker/lineage/net-PnL reconstruction schema exists; fail-closed no-authority answers; focused + adjacent tests pass. | `2026-06-26--fee_slippage_maker_taker_schema_no_order.md`; smoke `FEE_SLIPPAGE_MAKER_TAKER_SCHEMA_READY_NO_AUTHORITY`. | No-repeat unless future outcome schema/proof requirements change. |
| `P1-AGGRESSIVE-ALPHA-FRESH-BBO-READONLY-READINESS-PATH-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Source-only public quote/readiness handoff contract exists; no quote capture, no order admission, no authority/proof claim. | v567 report; smoke `FRESH_BBO_READONLY_READINESS_PATH_READY_NO_AUTHORITY`; source checkpoint `07050103e35c1acabb251e5743215e0b8af92c75`. | No-repeat unless quote/readiness handoff semantics change. |
| `P1-AGGRESSIVE-ALPHA-MAKER-FIRST-MICRO-TIER-PLACEMENT-POLICY-NO-ORDER` | 1 | READY | `READY_SOURCE_ONLY` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Define maker-first post-only micro-tier placement/skip policy using current cap ladder, fresh BBO contract, and fee/slippage schema; no placement call/order authority. | Fresh BBO readiness report says next source-only safe action is maker-tier policy if no real auth delta. | Run this blocker unless a real P0 auth delta appears first. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Survival/risk | Profit is optimized only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | Demo API permission is not live/mainnet permission. Bounded Demo grant requires candidate-scoped structured auth or exact typed confirm plus E3/BB review. |
| Runtime/order path | Bybit private/trading calls, public quote capture, adapter/writer enablement, plan mutation, order submission, PG write, crontab/env edit, or service restart require reviewed runtime chain. |
| Cost Gate | Global Cost Gate and freshness gate must not be lowered. Proof must be candidate-matched and include fills, actual fees, slippage, lineage, controls, and execution realism. |
| Candidate selection | AVAX remains the P0 bounded candidate. ETH and other symbols remain research-only unless separate cap/evidence review changes this. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Fastest safe test | Authority |
|---|---|---|---|
| Maker-first micro tier placement policy | upside Medium; evidence Medium design-only; realism Low until fills; cost favorable if maker; time Medium; account risk None; governance Medium; autonomy High | Source-only policy using current cap tiers, fresh BBO readiness, and fee/slippage schema; no placement call. | Research only; E3/BB + P0 auth before any order. |
| Reviewed public quote capture envelope | upside Medium-High; evidence Medium; realism Medium after quote; time Fast; account risk None; governance Low-Medium; autonomy Medium | Prepare E3/BB-reviewed public GET capture packet using existing helper; no private/order endpoint. | E3/BB for runtime/public quote capture; no order authority. |
| Spread-aware no-trade skip guard | upside Medium; evidence Medium; realism Medium; cost critical; time Medium; account risk None; governance Low; autonomy High | Add source-only spread/cost-cushion skip rules before any maker order admission. | None for design; bounded auth before order. |

## §5 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--fresh_bbo_readonly_readiness_path_no_order.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T084511Z_fresh_bbo_readonly_readiness_path_no_order.json | sed -n '1,220p'
python3 -m json.tool /tmp/openclaw/fresh_bbo_readonly_readiness_path_smoke_20260626T084511Z/fresh_bbo_readonly_readiness_path.json | sed -n '1,220p'
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_fresh_bbo_readonly_readiness_path.py
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: A next PM can identify the next action in under one minute: real P0 auth delta takes precedence; otherwise run maker-first micro-tier placement policy, not another broad audit or quote capture.
