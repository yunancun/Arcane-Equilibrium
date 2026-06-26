# Xuanheng TODO - Active Dispatch Queue

**Version** v565 | **Date** 2026-06-26
**Source/runtime pointer**: v565 source-code checkpoint commit `c28d5cf6e0259f911796a46c732e78fc45746b1f` is on `main` / `origin/main`; this TODO lives at current repo HEAD. Linux runtime source and crontab expected-head pins remain `dd22810ee41c353c1d214d9a3217862d7b2bac74`.
**Current posture**: current-cap staircase/risk worksheet is `DONE_WITH_CONCERNS`; AVAX is constructible under current `10 USDT` cap, but BBO is stale and P0 authorization remains blocked/no-repeat unless a real candidate-scoped auth delta appears.
**Links**: latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--current_cap_staircase_risk_worksheet_no_order.md`; changelog `docs/CLAUDE_CHANGELOG.md`; TODO standard `docs/agents/todo-maintenance.md`.

---

## §0 Current Runtime Facts

| Area | Latest verified fact | Dispatch impact |
|---|---|---|
| Runtime source/services | `2026-06-26T08:20:31Z`: Linux runtime source clean at `dd22810ee41c353c1d214d9a3217862d7b2bac74`; API service `active/running`, MainPID `2218842`. | Runtime is intentionally not changed by v565. Do not sync/restart unless a separate runtime blocker is opened. |
| Artifact SSOT path | Current cost-gate artifacts are under `/tmp/openclaw/cost_gate_learning_lane/` on `trade-core`. | Read-only checks must use this subdirectory. |
| Authorization latest | `2026-06-26T08:15:05Z`, sha `4a0aa283...`, status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, candidate `grid_trading\|AVAXUSDT\|Sell`, decision defer/no authorization id/object. | This is a fresh artifact delta but not an authorization delta. P0 bounded probe authorization stays blocked/no-repeat. |
| Current-cap worksheet smoke | `/tmp/openclaw/current_cap_staircase_risk_worksheet_smoke_20260626T082031Z/current_cap_staircase_risk_worksheet.json`: `CURRENT_CAP_STAIRCASE_RISK_WORKSHEET_READY_NO_AUTHORITY`, `tier_count=8`, min tier `0.9 AVAX / 5.4576 USDT`, max tier `1.6 AVAX / 9.7024 USDT`, cap/risk mutation false, order admission false, BBO refresh required true. | Cap/risk design is closed; do not rerun on same construction/auth artifacts. |
| Control identity contract smoke | `/tmp/openclaw/source_only_control_identity_contract_smoke_20260626T081124Z/control_identity_contract.json`: `SOURCE_ONLY_CONTROL_IDENTITY_CONTRACT_READY_NO_AUTHORITY`, same-side-cell controls required, cross-symbol controls not proof, authority/proof false. | Control identity is closed. |
| AVAX bounded candidate | Selected bounded Demo candidate remains `grid_trading\|AVAXUSDT\|Sell`, 60m, current-cap feasible, modeled `73.5511bps`, `48/48` positive. | Candidate selection is closed. Do not replace AVAX without fresh ranking/cap-feasibility evidence. |
| Proof exclusions | Exclude `flash_dip_buy`, cleanup/risk-close fills, unattributed fills, local stale `Working` rows, artifact counts, source-smoke, single-window MM positives, replay-only results, and cross-symbol controls as AVAX proof. | These never count for bounded-probe proof, Cost Gate proof, promotion, or risk-adjusted net PnL proof. |

## §1 Active State Machine

| Field | Value |
|---|---|
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260626T082031Z_current_cap_staircase_risk_worksheet_no_order.json` |
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-CURRENT-CAP-STAIRCASE-RISK-WORKSHEET-NO-ORDER` |
| `blocker_goal` | Define a source-only current-cap AVAX executable tier ladder and portfolio/survival risk worksheet without cap/risk/runtime/order mutation or authority. |
| `profit_relevance` | Determines whether the selected AVAX candidate can be sized inside the existing `10 USDT` cap and bounded portfolio exposure before any real risk-adjusted net PnL proof after fees/slippage is attempted. |
| `previous_evidence_checked` | v564 TODO; control identity report; no-order AVAX construction preview; runtime auth/proposal/scorecard mtimes. |
| `new_evidence_delta_required` | Completed control identity contract plus open cap staircase and portfolio risk gaps; no real P0 authorization delta. |
| `new_evidence_delta_found` | Runtime auth refreshed at `2026-06-26T08:15:05Z` but remains defer/no-authority; current-cap worksheet smoke is ready/no-authority. |
| `anti_repeat_decision` | Proceeded with a distinct source-only helper; do not rerun P0 auth or worksheet on the same artifacts. |
| `loop_status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` if real auth delta appears; otherwise `P1-AGGRESSIVE-ALPHA-FEE-SLIPPAGE-MAKER-TAKER-SCHEMA-NO-ORDER`. |
| `why_not_repeating_current_blocker` | Cap/risk worksheet is source-backed and smoke-tested; repeating would add no evidence. |

## §2 Active Dispatch Queue

| ID | P | Status | Loop decision | Owner chain | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|---|---|
| `P0-PROFIT-EVIDENCE-QUALITY` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> E3/BB/QC -> PM | Demo overhang classified; stale/unattributed/proof-exclusion rules recorded; no unreviewed cancel/modify. | `2026-06-26--demo_residual_cleanup_refresh_action_clean_exchange.md`; §0 proof exclusions. | No-repeat unless exchange inventory, fill attribution, or proof-quality evidence changes. |
| `P0-PROFIT-CANDIDATE-SELECTION` | 0 | DONE | `DONE_WITH_CONCERNS` | PM -> QC/MIT/BB -> PM | Exactly one review-only candidate selected; no probe/order/live authority. | `2026-06-26--profit_candidate_selection_avax_review_packet.md`; selected `grid_trading\|AVAXUSDT\|Sell`. | No-repeat unless fresh evidence invalidates AVAX cap feasibility or ranking. |
| `P0-BOUNDED-PROBE-AUTHORIZATION` | 0 | BLOCKED | `BLOCKED_BY_RUNTIME_AUTHORIZATION` | PM -> E3 -> BB -> PM | Candidate-specific bounded Demo auth only; no global Cost Gate lowering; no live; no runtime/order/probe authority unless valid scoped authorization is admitted and E3/BB review passes. | `2026-06-26T08:15:05Z` auth latest sha `4a0aa283...`: AVAX-scoped, `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, defer/no authority. | No read-only repeat. Resume only on candidate-scoped typed-confirm, standing-auth, or authority artifact delta. |
| `P0-PROFIT-OUTCOME-REVIEW` | 0 | WAITING | `WAITING_FOR_AUTHORIZED_OUTCOMES` | PM -> QC/MIT/BB -> PM | Candidate-matched fills, net PnL after fees/slippage, matched controls, execution realism, repeat/OOS path. | No authorized bounded-probe outcomes exist. | Run only after an authorized bounded Demo probe has candidate-matched outcomes. |
| `P1-AGGRESSIVE-ALPHA-SOURCE-ONLY-CONTROL-IDENTITY-CONTRACT-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Machine-checkable source-only contract defines AVAX proof identity, same-side-cell matched control identity, research-control exclusions, and no-authority answers. | `2026-06-26--source_only_control_identity_contract_no_order.md`; smoke `SOURCE_ONLY_CONTROL_IDENTITY_CONTRACT_READY_NO_AUTHORITY`. | No-repeat unless gap-closure contract or proof/control source semantics change. |
| `P1-AGGRESSIVE-ALPHA-CURRENT-CAP-STAIRCASE-RISK-WORKSHEET-NO-ORDER` | 1 | DONE | `DONE_WITH_CONCERNS` | PM -> PA/E1 -> E2 -> E4 -> QA/PM | Machine-checkable current-cap tier ladder and risk worksheet exists; no cap/risk mutation, no order admission, no authority/proof claim. | `2026-06-26--current_cap_staircase_risk_worksheet_no_order.md`; smoke `tier_count=8`, cap/risk mutation false, BBO refresh required. | No-repeat unless construction preview, cap/risk contract, or auth evidence changes. |
| `P1-AGGRESSIVE-ALPHA-FEE-SLIPPAGE-MAKER-TAKER-SCHEMA-NO-ORDER` | 1 | READY | `READY_SOURCE_ONLY` | PM -> QC/MIT -> PM | Define future fill/outcome schema requirements for actual fees, slippage, maker/taker label, orderLinkId/exchange/fill lineage, and proof-exclusion enforcement. | Current-cap worksheet says next safe action is fee/slippage/maker-taker schema unless real auth delta appears. | If no real P0 auth delta appears, implement this specific source-only schema contract. |

## §3 Hard Gates

| Gate | Rule |
|---|---|
| Survival/risk | Profit is optimized only inside survival, Guardian/risk, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| Authorization | Demo API permission is not live/mainnet permission. Bounded Demo grant requires candidate-scoped structured auth or exact typed confirm plus E3/BB review. |
| Runtime/order path | Bybit private/trading calls, adapter/writer enablement, plan mutation, order submission, PG write, crontab/env edit, or service restart require reviewed runtime chain. |
| Cost Gate | Global Cost Gate must not be lowered. Proof must be candidate-matched and include fills, fees, slippage, lineage, controls, and execution realism. |
| Candidate selection | AVAX remains the P0 bounded candidate. ETH is research-only until separate cap-envelope review. |
| Live/mainnet | Out of scope; no live/mainnet authority. |

## §4 Aggressive Alpha Backlog

| Hypothesis | Score snapshot | Fastest safe test | Authority |
|---|---|---|---|
| Fee/slippage/maker-taker evidence schema | upside Medium-High; evidence Medium design-only; realism Low until fills; cost critical; time Fast; account risk None; governance Low; autonomy High | Source-only schema contract for future result review and proof-exclusion checks. | None for schema; bounded auth before any fill path. |
| Fresh BBO read-only readiness path | upside Medium; evidence Medium; realism Medium after fresh snapshot; cost modeled favorable; time Fast with reviewed read-only path; account risk None; governance Low-Medium; autonomy Medium | Reviewed read-only BBO/instrument snapshot capture only. | PM->E3 for runtime read if needed; no order authority. |
| Micro tier selection for maker placement | upside Medium; evidence Low-Medium; realism Low until fills; cost favorable only if maker; time Medium; account risk None now; governance Medium; autonomy Medium | Source-only tier policy proposal using current ladder and future fee/slippage schema. | Research only; E3/BB + auth before any order. |

## §5 Handoff Commands

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/TODO.md
sed -n '1,220p' /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--current_cap_staircase_risk_worksheet_no_order.md
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T082031Z_current_cap_staircase_risk_worksheet_no_order.json | sed -n '1,220p'
python3 -m json.tool /tmp/openclaw/current_cap_staircase_risk_worksheet_smoke_20260626T082031Z/current_cap_staircase_risk_worksheet.json | sed -n '1,180p'
ssh trade-core 'python3 -m json.tool /tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json | sed -n "1,120p"'
```

**Maintenance contract**: `TODO.md` is the active dispatch queue only. Long evidence and version narratives belong in reports/archive/changelog.
**Self-check**: A next PM can identify the next action in under one minute: real P0 auth delta takes precedence; otherwise implement fee/slippage/maker-taker schema, not another cap/risk worksheet.
