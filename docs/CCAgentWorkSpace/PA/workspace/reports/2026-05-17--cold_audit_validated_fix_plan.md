# PA Cold Audit Validated Fix Plan

Date prefix: `2026-05-17` per operator request.  
Actual PA synthesis time: 2026-05-29 Europe/Madrid.  
Repo root: `/Users/ncyu/Projects/TradeBot/srv`.  
Role: PA(default).  
Mutation scope: this report file only.

## Scope

Read and synthesized all required reports:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--cold_audit_baseline_freeze.md`
- `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-17--index_integrity_audit.md`
- `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-17--doc_inventory_dedup_audit.md`
- `docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-17--root_principle_compliance_audit.md`
- `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-17--full_chain_functional_gap_dead_code_audit.md`
- `docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-17--security_gate_secret_audit.md`
- `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-17--bybit_api_compatibility_audit.md`
- `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-17--strategy_risk_math_audit.md`
- `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-17--db_ml_foundation_audit.md`
- `docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-17--ai_usage_effectiveness_audit.md`
- `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-17--full_chain_test_audit.md`
- `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-17--optimization_readability_performance_audit.md`
- `docs/CCAgentWorkSpace/A3/workspace/reports/2026-05-17--gui_usability_dead_button_audit.md`

PA rechecked current source/runtime state with read-only commands only:

```bash
git rev-parse HEAD && git status --porcelain=v1 -b
rg ... program_code rust settings docs helper_scripts
nl -ba <source files> | sed -n <ranges>
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD && git status --porcelain=v1 -b && crontab -l | grep -E "m11|ac19|pg_dump|attribution_daily"'
ssh trade-core 'psql ... SELECT-only reflection for close_maker_audit, model_registry, drift/model_performance, replay tables'
```

Current local and Linux source HEAD rechecked during PA synthesis:

- Local: `575a0a94e5501539c992281ea4d79382109d534e`, `## main...origin/main`
- Linux `trade-core`: `575a0a94e5501539c992281ea4d79382109d534e`, `## main...origin/main`

## Summary

Confirmed merged findings:

| Severity | Count |
|---|---:|
| P0 | 0 |
| P1 | 17 |
| P2 | 17 |
| P3 | 7 |

Rejected / downgraded / unproven raw findings: 10.

No confirmed P0 exists in the submitted reports or PA recheck. The dominant P1 clusters are live authorization/session truthfulness, exchange-mutating retry/stop semantics, stale evidence gates, AI/ML cost and promotion lineage, and governance source-of-truth drift.

## P0/P1 Recheck Record

Every P1 below has PA local recheck, cross-role confirmation, or both.

| Final ID | Recheck / confirmation |
|---|---|
| P1-01 | PA source recheck `executor_routes.py:180-420`; cross-confirmed by E3-SG-001. |
| P1-02 | PA source recheck `live_session_endpoints.py:135-224,407-493`; cross-confirmed by A3-GUI-002 and E3-SG-002. |
| P1-03 | PA source recheck `live_session_routes.py:686-710` and `bybit_rest_client.py:681-715`; cross-confirmed by CC-RP-001. |
| P1-04 | PA source recheck `tab-live.js:1068-1118`, `live_session_endpoints.py:354-372`, `live_session_account_routes.py:687-714`; cross-confirmed by A3-GUI-003. |
| P1-05 | PA source recheck `control_ops.py:164-224,329-396`; cross-confirmed by A3-GUI-004. |
| P1-06 | PA source recheck `position_manager.rs:226-260`; cross-confirmed by BB-API-002 and QC-SRMA-002. |
| P1-07 | PA source recheck `dispatch.rs:28-46,201-235,352-423,638-668` and tests `dispatch_tests.rs:371-525`; cross-confirmed by BB-API-003, QC-SRMA-003, E4-FCT-001. |
| P1-08 | PA source recheck `bybit_rest_client.rs:139-143,901-955`; cross-confirmed by BB-API-001. |
| P1-09 | PA source recheck `edge_estimates.rs:80-124,162-187,232-239`, `gates.rs:240-260`, `edge_estimates.json:3-10`; cross-confirmed by QC-SRMA-001. |
| P1-10 | PA source recheck `promotion_pipeline.py:1-25,100-109,454-525`, route `governance_promotion_routes.py:191-250`, test `test_promotion_pipeline.py:125-144`; cross-confirmed by E4-FCT-002. |
| P1-11 | PA runtime SELECT `to_regclass('learning.close_maker_audit') = MISSING`; cross-confirmed by CC-RP-002 and QA evidence referenced by CC. |
| P1-12 | PA source recheck policy enum and route binding mismatch; cross-confirmed by AI-E-001 and AI-E-002. |
| P1-13 | PA source recheck provider-native AI write path and durable ledgers; cross-confirmed by AI-E-003. |
| P1-14 | PA runtime SELECT `model_registry count=3 max=2026-04-24 production/promoting=0`; cross-confirmed by MIT-DBML-001. |
| P1-15 | PA source recheck register paths and PA/Operator mirror diff; cross-confirmed by R4-IDX-001, TW-DOC-01, CC-RP-004. |
| P1-16 | PA source/runtime recheck Alpha/M11 status drift and scaffold script; cross-confirmed by FA-FC-001/002/003. |
| P1-17 | PA source recheck `control_ops.py:504-529`; cross-confirmed by A3-GUI-001. |

## Confirmed P1 Findings

| ID | Finding |
|---|---|
| P1-01 | **Executor live authorization verifier uses IPC secret domain.** Affected: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_routes.py:368`, contrasted with `live_trust_routes.py:58-78,253-284` and `rust/openclaw_engine/src/live_authorization.rs:393-399`. Evidence: `nl -ba ...executor_routes.py | sed -n '180,420p'`. Impact: valid live-auth-key signed authorization can be rejected while IPC-signed authorization can satisfy Python live-write surfaces. Real because `_verify_authorization_json_or_raise` computes HMAC with `OPENCLAW_IPC_SECRET` while signer/Rust prefer `OPENCLAW_LIVE_AUTH_SIGNING_KEY`. Fix: centralize/reuse live-auth signing-key verifier; add split-key tests. Owner: E1 + CC. Verify: E3 + E2 + E4. |
| P1-02 | **Live session start/resume/grant can mark `active`/`granted` without full live gate/readback.** Affected: `live_session_endpoints.py:135-224,407-493`. Evidence: `nl -ba ...live_session_endpoints.py | sed -n '120,230p;400,500p'`. Impact: UI/control state can claim live readiness beyond actual Rust authorization posture. Real because start checks role + `live_reserved`, sets authority, swallows IPC resume failure, and does not call the signed auth verifier; resume uses substring `"live"`. Fix: one full live-preflight helper plus mandatory IPC success/readback before `active`; exact `live_reserved`. Owner: PA + E1 + E3. Verify: E3 + E2 + A3 + E4. |
| P1-03 | **Python live Stop performs direct Bybit cancel-all write.** Affected: `live_session_routes.py:686-710`, `bybit_rest_client.py:681-715`. Evidence: PA source recheck. Impact: risk-reducing but still exchange-mutating Python REST write outside Rust execution authority, violating root principles 1/2 unless formally excepted. Real because code calls `_sweep_orphan_orders(rc, "live", errors)` and `_post("/v5/order/cancel-all")`. Fix: move cancel-all behind Rust authority or ratify narrow emergency exception with ADR/audit/5-gate. Owner: PA + CC then E1. Verify: CC + E2 + BB. |
| P1-04 | **Live emergency/close-all GUI can show success on partial failure.** Affected: `static/tab-live.js:1082-1112`, `live_session_endpoints.py:354-372`, `live_session_account_routes.py:687-714`. Evidence: PA source recheck. Impact: operator can see success while residual live positions/orders remain. Real because backend returns top-level `partial_failure`, `closed_all=false`, `errors`, but frontend ignores/looks at wrong nested field. Fix: red/blocking UI state for any partial failure; consider 409/424 for incomplete live risk-reduction. Owner: E1 + PA. Verify: A3 + E2 + BB + E4. |
| P1-05 | **Safe recheck / demo validate stamp readiness instead of proving it.** Affected: `control_ops.py:164-224,329-396`, `static/tab-settings.html:666-683`. Evidence: PA source recheck. Impact: readiness gates can be marked passed with no runtime/replay/IPC evidence. Real because mutators write `passed`/`success` directly and return success. Fix: rename to manual mark or replace with real evidence executors; do not let stamped states satisfy readiness. Owner: PA + E1. Verify: A3 + E2 + QA. |
| P1-06 | **Exchange-side trading-stop prices bypass tick rounding.** Affected: `position_manager.rs:226-260`, `exchange_stop_sync.rs:80-107`, `bootstrap.rs:757-768`, `step_4_5_dispatch.rs:1302-1310`. Evidence: PA source recheck plus BB/QC cross-confirmation. Impact: Bybit can reject conditional stop, weakening dual-rail protection. Real because raw `format!("{}", value)` is sent to `/v5/position/trading-stop` while create order has instrument rounding. Fix: shared trading-stop normalizer with side-aware conservative rounding and fail-closed missing instrument spec. Owner: PA + E1. Verify: BB + QC + E4. |
| P1-07 | **Mutating order-create retry policy conflicts with fail-closed boundary.** Affected: `dispatch.rs:28-46,201-235,352-423,638-668`; tests `dispatch_tests.rs:371-525`. Evidence: PA source recheck and three-role confirmation. Impact: ambiguous transport/parse/timeout/nonzero retCode can trigger another exchange-mutating create; idempotency may mitigate but policy is not ratified against hard boundary. Real because production `order_mgr.place_order` is wrapped by `run_dispatch_retry`, and tests lock retries. Fix: operator/PA/CC choose strict reconcile-before-retry or documented idempotent exception with Bybit proof and reconciliation. Owner: PA + CC + E1. Verify: BB + E2 + E4. |
| P1-08 | **LiveDemo live secret slot can be overridden by process env credentials.** Affected: `bybit_rest_client.rs:139-143,901-955`. Evidence: PA source recheck. Impact: live-grade LiveDemo can bypass operator-managed live slot provenance/audit through process env keys. Real because LiveDemo maps to `live` slot but env fallback is disabled only when `is_mainnet`. Fix: disable env fallback whenever `env.secret_slot() == "live"`. Owner: E1. Verify: BB + E3. |
| P1-09 | **Live/demo cost gate accepts stale/legacy/unvalidated edge snapshots.** Affected: `edge_estimates.rs:80-124,162-187,232-239`, `intent_processor/gates.rs:240-260`, `event_consumer/handlers/edge_estimates.rs:103-114`, `settings/edge_estimates.json:3-10`. Evidence: PA source recheck. Impact: positive stale legacy `shrunk_bps` can pass live/demo cost gating without `runtime_bps`, validation, or TTL. Current snapshot is negative, but gate defect is real. Fix: require fresh `_meta.updated_at`, `runtime_bps`, and `validation_passed=true` for positive production edge; fail/defer otherwise. Owner: E1 + MIT. Verify: QC + E4. |
| P1-10 | **Paper-based demo promotion path remains active despite paper lane freeze.** Affected: `promotion_pipeline.py:1-25,100-109,454-525`, `governance_promotion_routes.py:191-250`, `test_promotion_pipeline.py:125-144`, boundary `CLAUDE.md:96`. Evidence: PA source recheck. Impact: Operator route/tests still allow paper metrics to promote into demo, contradicting Stage 0R/Demo-only evidence discipline. Real because active route and happy-path test exercise `PAPER_SHADOW -> DEMO_ACTIVE`. Fix: freeze/deprecate route transition or require explicit future operator reopen; add regression that paper cannot promote demo. Owner: PA + E1. Verify: E4 + QA. |
| P1-11 | **`learning.close_maker_audit` evidence table is missing.** Affected: `TODO.md:209` plus runtime DB. Evidence: `ssh trade-core 'psql ... SELECT to_regclass('learning.close_maker_audit')'` returned `MISSING`. Impact: close-maker adverse-selection monitoring lacks the specified audit lane. Real because live PG lacks the table and CC/QA evidence agrees. Fix: deploy migration + writer + healthcheck, or amend spec to make another source canonical. Owner: PA + E1 + MIT. Verify: MIT + QA + CC. |
| P1-12 | **Provider-native AI call chain can decide `should_call_ai=true` then not bind/invoke.** Affected: `bybit_thought_gate_policy_builder.py:332`, `policy_contract_check.py:37-40`, `bybit_ai_route_selector_builder.py:303,331,436-457`, `bybit_bind_active_route_env.sh:87-103`. Evidence: PA source recheck. Impact: standard and route C paths can fail before provider binding despite upstream call decision. Real because enum `policy_ready_standard_allowed` is emitted/allowed but selector expects `policy_ready_standard`; route C emits `route_c_escalated_standard` but binder does not accept it. Fix: normalize enum/route names and add end-to-end route fixtures. Owner: E1. Verify: AI-E + E4. |
| P1-13 | **Provider-native AI calls are not connected to durable cost/invocation ledgers.** Affected: `bybit_ai_invocation_attempt_builder.py:385-515`, `bybit_ai_cost_log.py:201`, durable writers `agent_event_store.py:216`, `usage_io.rs:61`. Evidence: PA source recheck. Impact: paid provider calls can be undercounted in DB cost/ROI ledgers. Real because H1-F writes JSON latest/dated files, not `agent.ai_invocations` or `learning.ai_usage_log`. Fix: pre/post durable DB ledger write for paid calls; fail closed if ledger write fails per Rust budget contract. Owner: E1 + MIT. Verify: AI-E + MIT. |
| P1-14 | **Fresh shadow models are not registered for canary promotion.** Affected: `model_registry.py:17-24,139-203,332-338`, `canary_promoter.py:617-624`. Evidence: runtime SELECT: `learning.model_registry count=3`, max `2026-04-24`, `production/promoting=0`; MIT cross-confirmed status `model_registry_skipped`. Impact: current artifacts have no DB candidate lineage for canary/promoter review. Real because registry writes can return `None` and current table is stale. Fix: require registry persistence for non-`no_ship` live-readiness artifacts or fail loudly. Owner: PA + E1. Verify: MIT + E4. |
| P1-15 | **Governance/source-of-truth drift remains in active authority surfaces.** Affected: `SPECIFICATION_REGISTER.md:133-138`, `Operator/2026-05-09--full_loss...md:259`, corrected PA copy `PA/...full_loss...md:262`. Evidence: PA path check and line diff; R4/TW/CC cross-confirm. Impact: future roles can load dead ADR paths or stale liquidation-pulse requirements. Real because registered ADR filenames do not exist while same-number ADR files do, and Operator mirror lacks correction block. Fix: path-existence patch plus mirror-as-stub policy. Owner: TW + PM, PA if ADR naming intent changes. Verify: R4 + CC. |
| P1-16 | **Alpha Tournament/M11 truth-state drift and scaffold evidence entrypoint.** Affected: `alpha_tournament_ssot_spec.md:5`, `SPECIFICATION_REGISTER.md:123`, `TODO.md:29,48,186-187`, `SCRIPT_INDEX.md:61`, `attribution_daily.py:277-299`, `tournament_orchestrator.py:1-14`. Runtime: crontab has M11 daily 04:00 UTC and AC-19 08:00 UTC; `replay.experiments=24`, `learning.replay_divergence_log=0`. Evidence: PA source/runtime recheck. Impact: duplicate/stale dispatch risk and possible false evidence if scaffold exits 0 with zero candidate data. Real because active docs simultaneously say IMPL-pending and mostly done; runtime proves M11 smoke cron installed but full divergence output absent. Fix: split statuses into source-scaffold done, active=false, Stage 0R evidence pending, M11 Stage A smoke installed, Stage B divergence pending; mark `attribution_daily.py` scaffold or wire it. Owner: PM + TW + PA + E1. Verify: FA + E4 + MIT. |
| P1-17 | **Global mode switch returns success after Rust sync failure.** Affected: `control_ops.py:504-529`, `static/tab-system.html:723-728`. Evidence: PA source recheck. Impact: GUI can show `live_reserved` success while Rust remains in prior mode. Real because `sync_ipc_call("set_system_mode")` exception is swallowed and function returns `"success"`. Fix: fail closed or return `partial_failure/rust_synced=false`; require Rust readback for live modes. Owner: PA + E1. Verify: A3 + E2 + E4. |

## Confirmed P2 Findings

| ID | Finding / required fields |
|---|---|
| P2-01 | **Backtest API route uses Python stub, not Rust backtest.** Affected: `program_code/local_model_tools/backtest_engine.py:1-8,56-76`, `backtest_routes.py:57,195-222,296,335`, `rust/openclaw_core/src/backtest.rs:103-129`. Evidence: FA source inspection; PA accepted via source/cross-role. Impact: API backtest cannot be treated as real evidence. Real because Python module returns zero/stub. Fix: label as stub or bridge to Rust/replay path; block evidence injection from stub. Owner: PA + E1 + TW. Verify: FA + E4. |
| P2-02 | **Bybit amend order falls back to raw qty/price when instrument cache misses.** Affected: `order_manager.rs:536-543,551-552`. Evidence: PA source recheck. Impact: amend can send off-step/off-tick fields unlike create path. Real because `.unwrap_or(q/p)` is explicit. Fix: reuse create validation or fail closed on missing spec. Owner: E1. Verify: BB + E4. |
| P2-03 | **Rate-limit preflight is not path/group aware.** Affected: `bybit_rest_client.rs:1105,1165,1267-1327` per BB report. Evidence: BB cross-confirmed; PA source search confirmed group tracking exists. Impact: avoidable 10006 on mutating paths. Fix: `wait_if_rate_limited(path)` with per-group reset state. Owner: E1. Verify: BB + E4. |
| P2-04 | **Bybit reference doc drift on fake pre-check and demo `dcp`.** Affected: `docs/references/2026-04-04--bybit_api_reference.md:823-826,1119-1122,1333`, source contrast `platform_client.rs:355-359`, `bybit_rest_client.rs:119-128`. Evidence: BB report plus PA source contrast. Impact: future exchange work can reintroduce unsafe fake pre-check or bad demo WS topics. Real because source and reference contradict. Fix: TW/BB doc patch to match source/current endpoint policy. Owner: TW + BB. Verify: BB + R4. |
| P2-05 | **Scheduled supervised/quantile ML training is demo-only while live_demo evidence exists.** Affected: `ml_training_maintenance.py:57-58`, `parquet_etl.py:104,439`; runtime has live_demo fills/outcomes per MIT. Evidence: MIT runtime/source, PA accepted cross-role. Impact: insufficient live-grade ML readiness evidence. Fix: PA stage policy: keep demo-only intentionally or add isolated live_demo widened training lane. Owner: PA + E1. Verify: MIT + QC. |
| P2-06 | **Drift/model-performance evidence tables are empty.** Affected: `feature_baseline_writer_cron.sh:101`, `canary_promoter.py:81,617`; runtime SELECT `observability.drift_events=0`, `observability.model_performance=0`. Impact: model promotion cannot rely on empirical drift/performance. Real via SELECT. Fix: enable evaluator/writer after burn-in and gate live packets on non-empty mode-scoped evidence. Owner: E1 + MIT. Verify: MIT + E4. |
| P2-07 | **Replay foundation is smoke/incomplete for ML promotion.** Affected: `m11_replay_runner_daily_cron.sh:20-24,81`; runtime `replay.experiments=24`, `completed=0`, `replay_divergence_log=0`. Impact: M11 smoke is not promotion-grade replay evidence. Real via script comments and SELECT. Fix: Stage B cohort replay with completion/veto materialization. Owner: PA + E1. Verify: MIT + QC. |
| P2-08 | **AI cost/budget path is structurally advisory in parts.** Affected: `bybit_ai_cost_log.py:76-160`, `bybit_query_budget_gate.py:113`, `bybit_query_budget_runtime.py:223-292`, route A allowlist/binder. Evidence: AI-E report and PA source recheck. Impact: "recorded" can mean unpriced and daily spend is not actually metered; route A is paid cloud by default. Real because branches set warning not block. Fix: block unpriced paid calls or write explicit unpriced ledger; read cumulative daily spend; decide route A semantics. Owner: PA + E1 + MIT. Verify: AI-E. |
| P2-09 | **Guardian scoring constants are not externally tunable.** Affected: `rust/openclaw_core/src/guardian.rs:26-32,121-177`. Evidence: QC source inspection. Impact: risk calibration cannot be validated from runtime policy. Real because literals are inside review path. Fix: move to validated risk config or document as invariant constants with tests. Owner: PA + E1. Verify: QC + E2. |
| P2-10 | **Full-chain tests mock PG/subprocess runtime and lack duplicate concurrency coverage.** Affected: `replay_full_chain_routes.py:1661-1930`, tests `test_replay_full_chain_run_routes.py:235-315`. Evidence: E4 source inspection. Impact: Mac tests can pass while Linux PG/subprocess path is broken or duplicate-spawns. Real because tests monkeypatch register/run helpers. Fix: add local concurrency test and separate Linux read-only evidence gate. Owner: E1 + MIT + PM. Verify: E4 + QA. |
| P2-11 | **Large-route and hot-path source files exceed hard-cap/readability threshold.** Affected: `strategy_ai_routes.py:1` has 2536 lines; `step_4_5_dispatch.rs:1` has 2020 lines; `intent_processor/tests.rs` has 2005 lines. Evidence: `wc -l ...`. Impact: review risk and hard-cap drift; production logic in `step_4_5_dispatch.rs` itself is under cap once tests move, so final severity P2 not P1. Fix: behavior-preserving splits. Owner: PA + E1. Verify: E2 + E4. |
| P2-12 | **Async GUI routes call blocking Bybit client and some PG reads miss statement timeout.** Affected: `strategy_ai_routes.py:765,1068,1119,1617,1764,1832,1921-1922,2243`, missing timeouts `1205-1210,1352-1354`, contrast `2187`. Evidence: PA `rg`/source. Impact: event-loop/thread/DB latency risk. Real because `bybit_rest_client.py` uses blocking `httpx.Client`. Fix: `asyncio.to_thread` or sync route handlers; shared GUI read timeout helper. Owner: E1. Verify: E4 + MIT where PG behavior matters. |
| P2-13 | **Stage 0R 8-D sweep recomputes expensive per-cell metrics.** Affected: `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_metrics.py:1616-1685`. Evidence: E5 source inspection. Impact: offline preflight latency/iteration risk. Real because 11,664 grid cells call expensive scans/bootstrap. Fix: PA exact-vs-fast contract, cache row-derived features, short-circuit deterministic failures. Owner: PA + E1. Verify: MIT + E4. |
| P2-14 | **GUI dead/hostile controls remain.** Affected: scheduled restart UI `tab-settings.html:159,610`, disabled route `control_legacy_routes.py:89-116`; governance refresh `tab-governance.html:245` calls undefined `loadGovernance()` while `governance-tab.js:1780` defines `loadAll()`. Evidence: A3 report and PA `rg`. Impact: operator UX failure; no direct trading mutation. Fix: hide/disable dead restart flow; alias or change refresh to `loadAll()`. Owner: E1. Verify: A3. |
| P2-15 | **Paper/demo stop paths can return success envelopes with residual errors.** Affected: `paper_trading_routes.py:399-531`, `paper_trading_response.py:8`, `tab-paper.html:392-398`. Evidence: A3 source inspection. Impact: Stage/demo evidence trust erosion. Fix: map non-empty errors to partial_failure and GUI warning/error. Owner: E1. Verify: A3 + E2. |
| P2-16 | **Bybit-only wording is ambiguous against approved Binance read-only stubs.** Affected: `CLAUDE.md:27`, `README.md:9`, `docs/adr/0033-adr-0006-bybit-binance-amendment.md`, `asset_venue.rs:64-75`, `order_router.rs:375`. Evidence: CC source inspection. Impact: governance ambiguity, not active Binance trading. Fix: clarify "Bybit-only execution; ADR-approved non-Bybit read-only data exceptions". Owner: PA + CC + TW. Verify: R4 + BB + CC. |
| P2-17 | **Docs/script indexes have confirmed discoverability drift beyond the P1 register issue.** Affected examples: missing `TODO` v65 archive path, `docs/README.md` active/archived M13/V116 rows, `helper_scripts/SCRIPT_INDEX.md` omissions/wrong path, Operator exact mirrors. Evidence: R4/TW reports; PA accepted lower severity pending PM index policy. Impact: discovery drift and stale action surfaces. Fix: PM decides literal-vs-generated index policy; TW patch concrete wrong links and mirror policy. Owner: PM + TW. Verify: R4. |

## Confirmed P3 Findings

| ID | Finding / required fields |
|---|---|
| P3-01 | **DSR component can say promote with tiny samples.** Affected: `promotion_evidence.py:126-170`, `dsr_gate.py:394-466`, `promotion_gate.py:113-126`. Evidence: QC source. Impact: misleading component report; final promotion protected by PBO. Fix: DSR min-observation/defer semantics. Owner: MIT + PA. Verify: QC. |
| P3-02 | **Grid OU residual-sigma comments stale.** Affected: `grid_helpers.rs:140-158,184-216`. Evidence: QC source. Impact: reviewer confusion. Fix: update comments/tests. Owner: TW + E1. Verify: QC + R4. |
| P3-03 | **Synthetic replay accepted in demo-applier evidence allowlist.** Affected: `mlde_demo_applier_evidence_filter.py:51,60,181`. Evidence: MIT source/runtime. Impact: low current blast radius; can blur evidence quality. Fix: separate/downweight/opt-in synthetic bucket. Owner: PA + MIT. Verify: MIT. |
| P3-04 | **Residual `openclaw_core` backtest/portfolio exports are not production-called by engine.** Affected: `openclaw_core/src/lib.rs:18,48`, `backtest.rs:103`, `portfolio.rs:90-100`. Evidence: FA `rg`. Impact: maintenance ambiguity. Fix: PA retain-vs-sunset decision. Owner: PA + E1. Verify: E2 + E4. |
| P3-05 | **Notification failsafe helper duplication and generic watcher drift.** Affected: `notification_failsafe/dispatchers/slack.rs:169`, `email.rs:368`, `console_banner.rs:87`, generic watcher `notification_failsafe/mod.rs:580`, shared watcher `providers/single_watcher.rs:219-245`. Evidence: E5 source. Impact: low runtime risk, security-adjacent drift. Fix: helper extraction or mark generic watcher test-only. Owner: PA + E1. Verify: E2 + E4. |
| P3-06 | **Autonomy posture exposes operator-hostile jargon.** Affected: `autonomy-posture.js:8,35,79`, `tab-governance.html:527-629`. Evidence: A3 source. Impact: operator comprehension risk, not fake success. Fix: plain-language enum/stat mapping and collapsible details. Owner: PA + E1. Verify: A3. |
| P3-07 | **Agent reports/archive indexing is not systematic.** Affected: `docs/README.md:1250,1278` and high-volume report/archive dirs. Evidence: R4 inventory. Impact: search dependency and incomplete historical lookup. Fix: generated per-role/archive manifests or explicit directory-convention policy. Owner: PM + TW. Verify: R4. |

## Duplicate Merge Table

| Final ID | Merged source findings |
|---|---|
| P1-01 | E3-SG-001; strategist live apply inherits same verifier. |
| P1-02 | E3-SG-002; A3-GUI-002. |
| P1-03 | CC-RP-001; A3 live stop context. |
| P1-04 | A3-GUI-003; related live close-all partial contract. |
| P1-05 | A3-GUI-004. |
| P1-06 | BB-API-002; QC-SRMA-002. |
| P1-07 | BB-API-003; QC-SRMA-003; E4-FCT-001. |
| P1-08 | BB-API-001. |
| P1-09 | QC-SRMA-001. |
| P1-10 | E4-FCT-002. |
| P1-11 | CC-RP-002; TODO `P1-LEARNING-CLOSE-MAKER-AUDIT-TABLE-MISSING`. |
| P1-12 | AI-E-001; AI-E-002. |
| P1-13 | AI-E-003; overlaps AI-E-004/005 for cost path integrity. |
| P1-14 | MIT-DBML-001. |
| P1-15 | R4-IDX-001; TW-DOC-01; CC-RP-004; FA-FC-005 downgraded into same cluster. |
| P1-16 | FA-FC-001; FA-FC-002; FA-FC-003; MIT-DBML-004 partially. |
| P1-17 | A3-GUI-001. |
| P2-01 | FA-FC-004. |
| P2-02 | BB-API-004. |
| P2-03 | BB-API-005. |
| P2-04 | BB-DOC-006; BB-DOC-007. |
| P2-05 | MIT-DBML-002. |
| P2-06 | MIT-DBML-003. |
| P2-07 | MIT-DBML-004 not included in P1-16. |
| P2-08 | AI-E-004; AI-E-005; AI-E-006. |
| P2-09 | QC-SRMA-004. |
| P2-10 | E5-OPT-001; E5-OPT-002; E5-OPT-009. |
| P2-11 | E5-OPT-004; E5-OPT-005; E5-OPT-010. |
| P2-12 | E5-OPT-003. |
| P2-13 | A3-GUI-006; A3-GUI-007. |
| P2-14 | A3-GUI-005. |
| P2-15 | CC-RP-003. |
| P2-16 | R4-IDX-002/003/005/006/008; TW-DOC-02/03/04/05/06. |
| P3-01 | QC-SRMA-005. |
| P3-02 | QC-SRMA-006. |
| P3-03 | MIT-DBML-005. |
| P3-04 | FA-FC-006. |
| P3-05 | E5-OPT-006; E5-OPT-007. |
| P3-06 | A3-GUI-008. |
| P3-07 | R4-IDX-004/009/010 after PA downgrade pending PM index-policy decision. |

## Rejected / Downgraded / Unproven

| Raw claim | PA disposition |
|---|---|
| PM baseline local/origin/Linux HEAD drift | Rejected as stale for current plan. PA recheck: local and Linux both `575a0a94e5501539c992281ea4d79382109d534e`. |
| "M11 cron install pending / 0 cron" as current runtime fact | Rejected as stale. Runtime crontab has `0 4 * * * ... m11_replay_runner_daily_cron.sh`; full M11 divergence remains confirmed separately. |
| R4/TW literal complete-index counts as P1/P2 blockers | Downgraded. Concrete broken links/mirrors are confirmed, but "every report/archive must be literal in docs/README" needs PM policy decision. |
| E5 generic `FailsafeWatcher` as active runtime risk | Downgraded to P3. `rg` indicates current production surface is `SharedFailsafeWatcher`; generic watcher is mostly test/local API drift. |
| FA residual `openclaw_core` backtest/portfolio as dead code requiring removal | Downgraded to P3. No production caller found, but retained future/test role is not disproven. |
| AI-E H3 "model router" as functional provider-selection blocker | Downgraded/unproven. Confirmed naming debt, but provider binding failures are already captured by P1-12. |
| A3 autonomy-posture wording as P2 fake-success/usability blocker | Downgraded to P3. Source confirms jargon; not a fake-success or dead-button defect. |
| BB official-doc freshness beyond local reference/source contradiction | Not independently re-browsed by PA in this report. Local source/reference contradictions remain confirmed by BB cross-role evidence. |
| Docs exact Operator mirror duplicates as all individually dangerous | Downgraded. Exact duplicates are not themselves false; material drift instance is P1-15 and mirror policy debt is P2-17. |
| Any P0 live-order bypass | Rejected. No report plus PA recheck found a direct current path that bypasses Rust live authorization and places new live orders. |

Rejected/unproven raw-count: 10.

## Parallelizable Fix Sections

These can run in parallel after PA/PM dispatch because file scopes are mostly independent:

1. **Auth/session/GUI truthfulness package**: P1-01, P1-02, P1-04, P1-05, P1-17.
2. **Bybit exchange semantics package**: P1-06, P1-08, P2-02, P2-03, P2-04.
3. **Evidence and promotion package**: P1-09, P1-10, P1-11, P1-16, P2-01, P2-05, P2-06, P2-07.
4. **AI/ML ledger and routing package**: P1-12, P1-13, P1-14, P2-08.
5. **Docs/source-of-truth package**: P1-15, P2-15, P2-17, P3-07.
6. **Performance/readability/UX cleanup package**: P2-10 through P2-14, P3-05, P3-06.

## Serialized Fix Sections

These require decisions before implementation:

1. P1-07 order retry policy: PA/CC/operator must choose strict fail-closed/reconcile-before-retry vs documented idempotent retry exception.
2. P1-03 live cancel-all authority: PA/CC/operator must choose Rust-only authority vs formal emergency exception.
3. P1-02/P1-17 live state contracts: PA must define whether Python control-plane state is advisory or gate-authoritative before E1 patches responses/tests.
4. P1-10 promotion semantics: PM/operator must confirm paper lane remains frozen and Stage 0R/Demo-only is the only current path.
5. P1-11 migration work: MIT Linux PG dry-run required before any schema migration apply.
6. P1-16 Alpha/M11 state: PM/TW should patch active SSOT only after preserving the exact Stage A smoke vs Stage B divergence distinction.
7. P1-14 ML registry: PA/MIT must define which shadow artifacts require registry persistence before E1 changes scheduled jobs.

## Recommended Session Split

To avoid compact risk, split into six sessions:

1. **Session A: Live gates and fake-success**  
   Scope: `executor_routes.py`, `live_trust_routes.py`, `live_session_endpoints.py`, `live_session_routes.py`, `live_session_account_routes.py`, `control_ops.py`, `tab-live.js`, `tab-system.html`, `tab-settings.html`, tests.  
   Tests: targeted FastAPI live gate tests, `test_executor_shadow_toggle_api.py`, live session route tests, GUI `node --check` for touched JS/HTML-embedded JS.  
   Acceptance: split-key auth passes/fails correctly; no live `active/granted/success` without full gate/readback; partial failures render red/warn.

2. **Session B: Exchange write semantics**  
   Scope: `position_manager.rs`, `exchange_stop_sync.rs`, `bootstrap.rs`, `step_4_5_dispatch.rs`, `bybit_rest_client.rs`, `order_manager.rs`, Bybit reference docs.  
   Tests: targeted cargo tests for trading-stop normalization, LiveDemo credential fallback, amend fail-closed, rate limit grouping; BB review.  
   Acceptance: trading-stop/amend use instrument precision or fail closed; LiveDemo ignores env creds for live slot; docs match source.

3. **Session C: Dispatch retry policy**  
   Scope: `event_consumer/dispatch.rs`, `dispatch_tests.rs`, ADR/CLAUDE amendment only if exception retained.  
   Tests: cargo dispatch tests plus new timeout/retCode one-attempt or idempotency/reconcile tests.  
   Acceptance: implementation and hard-boundary wording agree.

4. **Session D: Evidence gates and promotion state**  
   Scope: `edge_estimates.rs`, `intent_processor/gates.rs`, `promotion_pipeline.py`, `governance_promotion_routes.py`, `attribution_daily.py`, Alpha/M11 docs/index, close-maker migration spec.  
   Tests: cargo intent-processor edge tests, FastAPI promotion tests, script dry-run tests, MIT dry-run for migration.  
   Acceptance: stale/unvalidated edge cannot pass production gate; paper cannot promote demo; Alpha/M11 docs and scripts do not claim scaffold success as evidence.

5. **Session E: AI/ML lineage**  
   Scope: thought-gate route selector/binder, invocation/cost log, durable DB writers, model registry training jobs.  
   Tests: AI route end-to-end fixture; DB ledger contract tests; MIT SELECT proof after non-mutating or staged run.  
   Acceptance: `should_call_ai=true` reaches provider binding or blocks honestly; paid calls require durable cost/invocation ledger; fresh artifacts become registry candidates or jobs fail loudly.

6. **Session F: Docs/performance/UX cleanup**  
   Scope: SPEC register paths, Operator mirror stubs, docs/script indexes, route/file splits, GUI dead controls, Stage 0R sweep optimization.  
   Tests: path-existence script, markdown link checks, route regression, JS syntax checks, targeted performance/equivalence tests.  
   Acceptance: no dead ADR paths; material Operator mirrors point to canonical reports; large files below cap or documented exception; dead buttons removed/fixed.

## Operator Decision Items

1. Order-create retry policy: strict fail-closed/reconcile-before-retry or explicit idempotent retry exception.
2. Python live cancel-all: Rust-only move or formally ratified emergency exception.
3. Paper promotion lane: confirm still frozen; no `PAPER_SHADOW -> DEMO_ACTIVE`.
4. Alpha Tournament daily evidence: wire `attribution_daily.py` now or mark disabled/scaffold until Sprint 3.
5. M11 acceptance: Stage A smoke heartbeat sufficient only for `[48]` liveness, not M11 divergence/promotion evidence.
6. LiveDemo credential policy: approve no env fallback for `live` secret slot.
7. AI provider-native policy: paid calls fail closed on missing ledger/pricing, or remain advisory and cannot satisfy cost-cap gates.
8. Docs index policy: literal complete index vs generated per-area manifests.

## Linux Runtime Read-Only Evidence Needed

Before sign-off for related packages, collect only read-only evidence:

- `git rev-parse HEAD`, dirty status, release binary hashes for `openclaw-engine` and `replay_runner`.
- `crontab -l`, M11/AC-19/pg_dump log tail, heartbeat mtimes.
- SELECT-only counts/ages for `learning.close_maker_audit`, `replay.experiments`, `replay.runs`, `learning.replay_divergence_log`, `learning.model_registry`, `observability.model_performance`, `observability.drift_events`.
- Auth state by stat/parse only: `authorization.json` presence/expiry/domain; do not renew.
- Bybit-facing logs by grep/tail only for timeout/retCode/retry behavior; do not provoke trading calls.
- Passive healthcheck output only if the script is known read-only; do not run scripts that register replay runs unless explicitly approved.

## Forbidden Without Approval

Do not perform any of the following under this fix plan without explicit operator approval:

- deploy, rebuild, restart, stop/start services, or run atomic restart scripts
- apply migrations or mutate DB schema/data
- renew or hand-edit `authorization.json`
- edit secrets, rotate keys, or print secret contents
- edit live/demo/paper/risk/strategy TOML
- start paper/demo/live trading, call mutating Bybit endpoints, or run full-chain `/run` routes that register rows/spawn subprocesses
- modify `TODO.md`, memory files, or other docs outside the approved patch/session scope

PA VALIDATED FIX PLAN DONE.
