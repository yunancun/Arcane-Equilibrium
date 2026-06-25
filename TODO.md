# 玄衡 TODO — 主動派工佇列

**版本** v521 ｜ **日期** 2026-06-25 ｜ **Repo posture**：one E3/BB-approved AVAX public quote attempt succeeded as a timestamped no-order artifact; Linux runtime checkout + cron expected-head pins still remain `e0c2a0e1`; no runtime sync, restart, crontab edit, PG write, `_latest` overwrite, or order action occurred in v521.
**當前主線 / 下一閘**：`P0-BOUNDED-PROBE-AVAX-FRESH-REROUTE-CHAIN-REFRESH-DEMO-ONLY`. The fresh quote path is proven, but the combined quote->adapter->construction-preview chain is blocked until the reroute-review input chain is refreshed inside the preview helper's 24h artifact-age gate.
**硬邊界**：No Cost Gate lowering/cap widening, no live/mainnet promotion, no private/auth Bybit endpoint, no order/cancel/modify, no PG write, no `_latest` runtime artifact overwrite, no service/env/crontab mutation, no Rust writer/adapter enablement, no probe/order/live authority, no promotion proof.
**證據入口**：latest PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-25--avax_public_quote_ready_reroute_stale_block.md`; source patch report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-25--avax_ca_safe_public_quote_route_source_patch.md`; previous SSL fail-closed report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-25--avax_public_quote_refresh_ssl_failed_no_order.md`; history log `docs/CLAUDE_CHANGELOG.md`.

---

## §0 Runtime 快照

| 區域 | 當前狀態 | 下一步 |
|---|---|---|
| Source / runtime | Local source has the verified-TLS public quote helper patch. Runtime Linux checkout and cron pins still point to `e0c2a0e1`; v521 was not runtime-synced. | Do not runtime-sync unless a later checkpoint explicitly selects that path through E3/runtime review. |
| Profit-first loop | Selected fallback remains `grid_trading|AVAXUSDT|Sell`. v521 quote artifact `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_public_quote_capture_avax_sell_20260625T223840Z.json` is `PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER`, sha `fe36f2dd...`, bid/ask `6.199/6.2`, effective age `531.382ms`. | Refresh the AVAX reroute-review input chain before any second quote->adapter->preview run. Do not reuse the now-stale quote as construction proof. |
| Verification | E3/BB approved one quote; PM ran exactly one public quote helper invocation. E3 approved a corrected combined chain command, but BB blocked execution because `bounded_probe_lower_price_reroute_review_latest.json` generated `2026-06-24T17:32:23Z` is stale for preview's 24h gate. | Generate fresh no-authority reroute-review input first; do not widen artifact-age/freshness gates. |
| TODO hygiene | `TODO.md` is now a compact dispatch queue. Version narratives belong in `docs/CLAUDE_CHANGELOG.md`; long evidence belongs in reports/archive. | Preserve active rows; do not paste report bodies or completed ledgers back into TODO. |

## §1 P0 主動阻塞項

| ID | 狀態 | Owner chain | 驗收／閘門 | 最新證據 | 下一步 |
|---|---|---|---|---|---|
| `P0-PROFIT-DEMO-LEARNING-LOOP` | ACTIVE / no-order / quote-ready, construction-preview blocked | PM -> E3 -> BB -> PM | Next construction proof must be candidate-matched, no-order, no authority, and built from fresh reroute-review + fresh BBO inside the helper gates. | v521 READY quote artifact sha `fe36f2dd...`; BB stale-input block; v520 source patch report. | Start `P0-BOUNDED-PROBE-AVAX-FRESH-REROUTE-CHAIN-REFRESH-DEMO-ONLY`; no second quote until fresh reroute-review input exists and E3/BB approve the combined chain. |
| `P0-EDGE-1` | ACTIVE | PM -> PA/QC/MIT/BB -> E1 after gate | Close only with >=3 alpha candidates satisfying net/cost/stat gates, or another accepted P0 edge path. Bull-only, stale, survivor-only, narrative-only, replay-only, or artifact-count positives are not promotion proof. | AEG reports under `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-*`; Gate-B watch and alpha discovery evidence summarized in `docs/CLAUDE_CHANGELOG.md`. | Wait for fresh Gate-B actionable window or continue source-only candidate research that improves execution realism/cost after fees. |
| `P0-LG-3` | ACTIVE / source integrated / runtime undeployed | PM -> E2 -> E4 -> QA -> operator deploy gate | Deploy/rebuild only after review chain and migration/checksum discipline; runtime proof required before closure. | Integrated commits `deb3f3af..0802d52b`; historical runtime notes in changelog. | Re-run review chain before any deploy/rebuild. |
| `P0-OPS` | ACTIVE / operator-gated tails | Operator + PM/E1/MIT as needed | Restore drill, system-level units, live-auth update, replay manifest feeding, and close-maker max-pending evidence must be explicitly recorded. | Operator rows in §3 and historical changelog. | Wait for named operator windows; no silent runtime mutation. |

## §2 Active P1/P2 Engineering Queue

| ID | P | Status | Acceptance | Latest evidence | Next action |
|---|---:|---|---|---|---|
| `P1-COST-GATE-SEALED-HORIZON-REVIEW` | 1 | ACTIVE / review-only | `ma_crossover|BTCUSDT|Sell` 240m sealed evidence may become a bounded proposal only after operator review, production learning lane proof, execution-realism review, and separate Rust-authority probe approval. | Scorecard/preflight artifacts summarized in changelog v500-series. | Build/review bounded proposal contract; do not grant probe/order authority. |
| `P1-L2-ADVISORY-MESH-TAILS` | 1 | ACTIVE / tails remain | First non-empty material day, E2E true distillation/model-call evidence, or B3 shadow runtime evidence before closure. | Reports `2026-06-13--l2_v140_pipeline_activation.md`, `--l2_embedding_backfill_activation.md`, `--l2_b3_recall_wiring.md`; 2026-06-19 watch still no non-empty material day. | Run only when new material/shadow evidence exists; otherwise keep as passive wait with trigger. |
| `AEG-S3-CANDIDATE-DIRECT-ROWS` | 1 | ACTIVE / non-promotable | Candidate rows must satisfy regime, breadth, freshness, survivorship, execution-realism, DSR/PBO, and matched-sample gates. | Gate-B / alpha discovery reports listed in changelog; current discovery `ready_for_probe=0`, `ready_for_aeg_chain=0`. | On fresh Gate-B `ACTIONABLE_*`, run preflight and follow probe hints only if operator-recommended. |
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | ACTIVE / source done, formal review open | Full-scan pagination guard reviewed by BB/E2/E4 and production event proof recorded. | PM report `2026-06-19--reconciler_pagination_focused_review.md`; focused Rust tests passed. | Carry with LG-3/reconciler batch review; no runtime action from this row alone. |
| `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` | 3 | ACTIVE / source done, event proof missing | Formal E2/E4 closure plus production `reconcile_ghost_converge` event proof. | PM report `2026-06-19--d2_audit_removed_semantics_focused_review.md`; Linux read-only DB had 0 production events as of 2026-06-19 01:22Z. | Recheck only after real event or reconciler batch review. |
| `P1-A1A2-STAGE0R-RUNNER-IMPL` | 2 | ACTIVE / trusted promotion packet not opened | Full CI/Linux E4/QC-MIT-QA signoff and trusted packet evidence; current wrappers are report-auth/denominator verified but not promotion proof. | PM reports `2026-06-19--stage0r_8c_denominator_and_pm_runtime_verification.md` and `--stage0r_current_head_wrapper_true_pg_rerun.md`; E4 denominator report. | Continue only if Stage0R candidate/gate evidence changes. |
| `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` | 2 | ACTIVE / operator + runtime blocked | OP-1/2/3, review/deploy/restart, and first real stake evidence. | PM report `2026-06-19--earn_first_stake_capability_routing_focused_review.md`; source wiring tests passed. | Wait for OP-1 key update and Earn variant/stake decision. |
| `P1-OPS-2-DRY-RUN` | 1 | WAITING | Use OP-1 as first OPS-2 SOP dry-run and record timing/failure modes. | OPS-2 runbook evidence in changelog. | Trigger after OP-1. |
| `P0-OPS-4-GAP-B-D-OPERATOR-DEPLOY` | 1 | WAITING / operator-gated | First restore drill and system-level units completed with evidence. | Historical OPS rows in changelog. | Operator schedules restore/system unit window. |
| `P1-WAVE5-TOTP-BACKEND` | 1 | WAITING / operator-gated | Runtime TOTP registration and formal Level 2 promotion gate. | Wave 5 governance rows in changelog and §7. | Resume only at formal autonomy promotion gate. |
| `P1-OP1-BYBIT-ENDPOINT-FILE-MISCONFIG` | 1 | WAITING / OP-1 | During live-slot key update, endpoint file changes from `demo` to `mainnet` with explicit operator evidence. | OP-1 row in §3. | Handle during OP-1, not before. |

## §3 Operator Actions And Passive Waits

| Action | Trigger / evidence | Impact / next step |
|---|---|---|
| Demo-learning AVAX follow-up | v520 source patch report and v519 SSL fail-closed report. | Next action is E3/BB-reviewed one-shot public quote attempt; still no order/probe/live authority. |
| S2 Gate-B 24h real capture | `[GATE-B-WATCH]` fresh Pre-Market/PreLaunch/conversion alert, or latest artifact changes to `ACTIONABLE_START_NOW` / `ACTIONABLE_SCHEDULE`. | Run `aeg_s3_gate_b_preflight.harness` first; full-chain command must be `operator_recommended=true`. |
| OP-1 Bybit mainnet key update | Operator availability. | Blocks Earn Wave C, live-auth update, OPS-2 dry-run, and endpoint-file correction. |
| OP-2/OP-3 Earn variant + first Flexible stake | After OP-1. | Establish first `learning.earn_movement_log` evidence; no action before OP-1. |
| Restore drill / system-level service units | Operator low-trading 4h window and sudo availability. | Closes OPS protection gaps beyond user-level watchdog. |
| P5-SM step-iii CUTOVER sign-off | Operator decides to enter cutover after prior soak/V138/V139/V140/L2 facts. | Requires sign-off + CC/E2/BB/E4 review; this row does not authorize deploy/rebuild/restart. |

## §4 Safety Invariants And Proof Exclusions

- Profit is optimized only inside survival, Guardian/risk gates, Decision Lease, Rust authority, authorization gates, auditability, and reconstructability.
- Unattributed fills never count toward promotion or bounded-probe proof.
- `flash_dip_buy` demo fill, Paper archive, artifact counts, source smoke, replay-only result, or single-window MM positive cannot prove profitability.
- Any proof must be candidate-matched, reconstructable, fee/slippage-aware, and net risk-adjusted after costs.
- Learning output may become a reviewable proposal only; it must not directly mutate order/risk/live state.

## §5 Aggressive Alpha Expansion Backlog

| Hypothesis path | Why it might make money | Fastest safe test | Authority |
|---|---|---|---|
| Fresh AVAX reroute-review chain -> immediate quote/preview | Keeps the cap-feasible false-negative candidate moving toward a realistic demo probe without changing risk caps or freshness gates. | First refresh no-authority reroute-review inputs; then E3/BB-reviewed one-shot quote->adapter->preview chain. | Public Bybit market-data review required only for the quote step; no order authority. |
| Maker/MM repeat-window filter | Could find fee-aware microstructure cells that survive current fees through maker ratio and adverse-selection control. | Wait for MM sample >=30 and repeat-window confirmation; source-only scorecard hardening is allowed. | No exchange/order authority unless later bounded probe is reviewed. |
| Regime-specific false-negative subset | Current broad strategy family may be structurally negative, while narrow regimes/horizons survive fees. | Build source-only candidate rows with matched controls and execution realism; no runtime mutation. | Research/source-only until proposal review. |

## §6 Deferred / Conditional Rows

| ID | Trigger |
|---|---|
| `P2-LIVE-AUTHZ-RUST-DIRECT-SOCKET-FUTURE` | Future architecture decision to move live authz context into Rust. |
| `P1-COST-GATE-DOUBLE-DEDUCT-TRIGGER` | Activate only if a positive cell or forward PnL proof is released. |
| `P2-AC19-ALT-BUCKET-FINAL-VERDICT-FOLLOWUP` | Reopen only if PA/QC/operator selects alpha/beta/C follow-up path. |
| `P2-COLD-AUDIT-P2P3-BATCH-FOLLOWUP` | Reopen only for explicit cost-edge, AI-pricing SSOT, BB-doc, or PERF-1 1m follow-up decision. |
| `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` | Recheck on green Stage0R preflight + operator demo-canary approval, first real AEG-S3 candidate rows, residual flag-on first run, or high-funding A1 regime. Backstop date: 2026-06-27. |
| `P2-AST-SIGNALSPEC-CONFORMANCE` | Resume only after formal SignalSpec schema freeze and PA/PM GO. |
| `P2-PACKET-C-C5-GUI-BANNER-ACK-ROLE` | After Packet C4 / `failsafe_ack_role` config freeze. |
| OPS-2 Sprint 4 runbook debt | Sprint bandwidth / OPS-2 operator context. |
| `P1-LG-5`, `P1-LEASE-1`, `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP`, `P1-INTENTYPE-FIELD-VISIBILITY-DEFER`, `P3-OPS-4-PG-DUMP-EVENT-EXTEND` | Condition-triggered only; see changelog for archived context. |
| `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` | 2026-06-27 sample-size/retire-or-extend decision. |
| `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` / `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 2026-08-21 or earlier if healthcheck regresses. |
| `P2-WP05-CSP-UNSAFE-INLINE` | First Live D-14 / Wave B security scope; not a quick PM-local fix. |
| Sprint 4 first Live $500 | W18-21 (~2026-09) after P0-EDGE-1, LG-3, and OPS gates close. |
| `P3-AE-RUNTIME-RENAME` | Mandatory at Apple Silicon migration start; until then, do not introduce new `AE_*`/`ae_*` runtime prefixes. |

## §7 Governance Pointers

| Area | Current pointer |
|---|---|
| AEG SSOT | ADR `docs/adr/0047-alpha-edge-regime-evidence-governance.md` + amendment `docs/governance_dev/amendments/2026-05-31--AMD-2026-05-31-01-alpha-edge-evidence-governance.md`. |
| ADR-0046 | Basis observation/execution split remains a live proposal path; coordinate with AEG endpoint/storage decisions. |
| SQL / migrations | Production SQL head fact last recorded as V145 on 2026-06-19; later source migrations require normal deploy/migration gate. |
| L2 memory | Schema/seed/V140/cron/embedding/B3 source wiring closed; first non-empty material day and B3 shadow evidence still open. |

## §8 Handoff Rules

- Function/bug chain: `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`.
- Quant/data chain: `PM -> QC -> MIT -> AI-E -> PM`.
- Runtime/exchange/security chain: `PM -> E3 -> BB if exchange-facing -> PM`.
- V### migration: Linux PG empirical dry-run before sign-off.
- GUI JS: `node --check`.
- Meta-doc updates: commit with subject/body, push origin, and keep Linux source sync as a separate reviewed runtime action.

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && PGHOST=localhost PGUSER=trading_admin PGDATABASE=trading_ai bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

**維護契約**：`TODO.md` is the active dispatch queue only. Long evidence, completed ledgers, and version narratives belong in reports/archive/changelog. See `docs/agents/todo-maintenance.md`.
