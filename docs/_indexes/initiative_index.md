# Initiative Index

> **ROUTER ONLY**
>
> 本索引用来帮助 agent 找到正确证据入口，不是 active queue。当前工作状态、
> owner、gate、runtime evidence 和 next action 仍以根目录 `TODO.md` 为准。

## Active Routing

| 需要 | 先读 |
|---|---|
| 当前 blocker / next action | `TODO.md` |
| 稳定项目入口 | `README.md` |
| agent 启动路由 | `docs/agents/context-loading.md` |
| TODO 维护规则 | `docs/agents/todo-maintenance.md` |
| 版本增量历史 | `docs/CLAUDE_CHANGELOG.md` |
| 深历史 / RCA | `AE_INVENTORY_CONSOLIDATED.md`（按需） |

## Initiatives

| Initiative | 当前入口 | 设计 / 证据 |
|---|---|---|
| IBKR Stock/ETF paper + shadow lane | Phase 0 ADR/AMD + named contract packet 已落地；Phase 1 source foundation 已新增 closed type/config/IPC fixture/source-only DDL + denial tests。下一步仍需 Phase 2 external-surface gate PASS；不允許 IBKR API/secret/connector/runtime/evidence clock | `docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md`; `docs/governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md`; `docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.md`; `docs/execution_plan/specs/2026-06-29--stock_etf_db_evidence_ddl_v1.source_only.sql`; `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`; `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round3_pm_launch_certification.md`; `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_phase1_source_foundation_checkpoint.md` |
| L2 Advisory Mesh | `TODO.md` row `P1-L2-ADVISORY-MESH-TAILS`; `L2_TODO.md` 仅作专题 ledger/reference | `docs/execution_plan/2026-06-05--l2-advisory-mesh-execution-plan.md`; `docs/execution_plan/2026-06-05--l2-copilot-design-session-consolidated.md`; `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-12--l2_root_todo_tail_triage.md` |
| AEG / Alpha-Edge | `TODO.md` `P0-EDGE-1` / `AEG-S3-CANDIDATE-DIRECT-ROWS` | `docs/adr/0047-alpha-edge-regime-evidence-governance.md`; `docs/governance_dev/amendments/2026-05-31--AMD-2026-05-31-01-alpha-edge-evidence-governance.md`; `docs/execution_plan/2026-05-31--aeg_s0_contracts.md`; `docs/execution_plan/2026-06-01--aeg_s1_foundation_unblock_packet.md` |
| Cost Gate demo-learning lane | `TODO.md` Latest active marker / operator actions; active authority remains PM + operator approval | `docs/runbooks/2026-06-21--cost_gate_learning_lane_runtime_activation.md`; `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-22--shadow_placement_impact_alpha_ingestion.md`; `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-22--bounded_probe_shadow_placement_impact.md`; `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-22--bounded_probe_placement_repair_plan.md`; `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-22--bounded_probe_touchability_preflight.md`; `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-22--demo_order_to_fill_gap_touchability_audit.md`; `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-22--cost_gate_data_flow_packet_refresh_cron.md`; `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-21--cost_gate_learning_scorecard_refresh_chain.md`; latest PM reports under `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-22--*_cost_gate*` / `2026-06-22--bounded_probe_*` / `2026-06-22--demo_order_to_fill_gap_*` |
| Gate-B listing fade | `TODO.md` `AEG-S3-CANDIDATE-DIRECT-ROWS` and operator action `S2 Gate-B 24h 真捕捉 run` | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-12--aeg_s3_gate_b_preflight_command_guard.md`; `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-12--aeg_s3_gate_b_watch_preflight_bridge.md` |
| P5-SM IPC convergence | `TODO.md` row `P5-SM-OPTION2-CONVERGENCE` | Latest closure: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-13--p5_sm_82_clean_closure.md`; infra compliance: `docs/CCAgentWorkSpace/CC/workspace/reports/2026-06-11--p5sm_soak_infra_compliance.md`; active next action still in `TODO.md` |
| OPS-2 cutover | `TODO.md` rows `P1-OPS-2-PHASE-2-CUTOVER` / operator actions | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-10--ops2_phase2_cutover_pm_signoff.md`; `docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-10--ops2_phase2_cutover_bb_signoff.md` |
| Incident-policy dispatch trigger | `TODO.md` row `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-12--incident_policy_dispatch_trigger_pm_source_closure.md`; `docs/CCAgentWorkSpace/E4/workspace/reports/2026-06-12--incident_policy_dispatch_trigger_e4_regression.md`; `docs/CCAgentWorkSpace/QA/workspace/reports/2026-06-12--incident_policy_dispatch_trigger_qa_acceptance.md` |
| Multi-Agent Rework historical MAG ledger | `TODO.md` if reopened; otherwise reference only | `docs/architecture/multi_agent_rework_2026-05-05/AgentTodo.md`; `docs/architecture/multi_agent_rework_2026-05-05/ENGINEERING_PLAN.md`; current OpenClaw position in `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md` |

## Reference Routers

| Area | 先读 | 不要误读成 |
|---|---|---|
| Runbooks / OPS | `docs/runbooks/README.md`; active operator action still in `TODO.md` §6 | Runbook approval or current runtime state |
| Architecture | `docs/architecture/README.md`; current queue still in `TODO.md` | Active implementation ticket |
| Execution plans | `docs/execution_plan/README.md`; current queue still in `TODO.md` | Current sprint authority when the file is legacy |
| Audit evidence | `docs/_indexes/audit_index.md` | GitHub Issues or active blocker list |
| Agent reports | `docs/CCAgentWorkSpace/README.md`; latest relevant `workspace/reports/` | A single merged source of truth; reports are evidence |
| Archive | `docs/archive/README.md` | Backlog or current active state |
| Healthcheck docs | `docs/healthchecks/README.md` | Current health result |
| Known issue references | `docs/known_issues/README.md`; root `docs/KNOWN_ISSUES.md` snapshot banner | Current blocker queue |

## Legacy / Reference High-Risk Topics

| Topic | Reference path | Current authority |
|---|---|---|
| v5.7 / v5.8 autonomy thesis | `docs/execution_plan/2026-05-20--execution-plan-v5.7.md`; `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` | `TODO.md` v5.9 thesis-shift / AEG mainline |
| M1/M5/M10 module specs | `docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md`; `docs/execution_plan/2026-05-21--m5_online_learning_design_spec.md`; `docs/execution_plan/2026-05-21--m10_discovery_tier_design_spec.md` | `TODO.md` and latest PM/role reports |
| funding_short_v2 | `docs/execution_plan/2026-05-25--alpha_candidate_1_funding_short_v2_spec.md`; `memory/project_2026_05_31_funding_short_structural_doa.md` | Bybit `instruments-info.upperFundingRate`; current AEG/funding rows in `TODO.md` |
| Old Layer 2 plan | `docs/references/2026-03-27--layer2_ai_reasoning_engine_implementation_plan.md` | `TODO.md` row `P1-L2-ADVISORY-MESH-TAILS`; 2026-06-05 L2 execution plan |
| Paper Replay / REF-20 | `docs/references/2026-05-02--paper_replay_learning_surface_design.md`; REF-20 execution plans | `CLAUDE.md` Paper boundary; AMD-2026-05-15-01; ADR-0047; `TODO.md` |
| 3E-ARCH | `docs/references/2026-04-11--three_engine_parallel_arch_plan.md` | `CLAUDE.md`, `.codex/MEMORY.md`, `TODO.md`, ADR/AMD and latest reports |

## Audit Folders

| Folder | Meaning |
|---|---|
| `docs/audit/` | Legacy 62-finding audit bundle and working ledgers. Do not treat as current issue tracker. |
| `docs/audits/` | General dated audit and verdict reports. |
| `docs/governance_dev/audits/` | Governance-development audit evidence. |
