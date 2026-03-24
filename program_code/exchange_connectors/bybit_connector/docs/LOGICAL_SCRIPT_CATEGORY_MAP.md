> **Canonical path note / 规范路径说明**  
> Business-events real implementations now live under:  
> `program_code/market_data_processor/bybit_business_events/`  
> Legacy entry files remain under:  
> `program_code/exchange_connectors/bybit_connector/scripts/`  
> as compatibility wrappers during migration.

# Flat scripts logical category map

Physical layout remains flat under `scripts/`.
This file is only a logical classification aid.

## business_events (26)

- bybit_business_event_acceptance_contract_check.py
- bybit_business_event_acceptance_suite.py
- bybit_business_event_contract_check.py
- bybit_business_event_extract_from_ws_jsonl.py
- bybit_business_event_final_audit.py
- bybit_business_event_final_audit_contract_check.py
- bybit_business_event_fixture_generator.py
- bybit_business_event_fixture_pack_builder.py
- bybit_business_event_fixture_pack_contract_check.py
- bybit_business_event_ingestion_from_ws.py
- bybit_business_event_ingestion_smoke.py
- bybit_business_event_negative_fixture_pack_builder.py
- bybit_business_event_negative_fixture_pack_contract_check.py
- bybit_business_event_negative_replay_contract_check.py
- bybit_business_event_negative_replay_harness.py
- bybit_business_event_normalizer.py
- bybit_business_event_regression_contract_check.py
- bybit_business_event_regression_summary.py
- bybit_business_event_replay_contract_check.py
- bybit_business_event_replay_harness.py
- bybit_business_event_runtime_contract_check.py
- bybit_business_event_runtime_facts.py
- bybit_business_event_state_contract_check.py
- bybit_business_event_state_resolver.py
- bybit_business_event_validation_handoff.py
- bybit_business_event_validation_handoff_contract_check.py

## decision_lease_and_execution_authority (44)

- bybit_decision_lease_adaptive_ttl.py
- bybit_decision_lease_adaptive_ttl_contract_check.py
- bybit_decision_lease_approval_bridge.py
- bybit_decision_lease_approval_bridge_contract_check.py
- bybit_decision_lease_approval_bridge_final_audit.py
- bybit_decision_lease_chapter_contract_check.py
- bybit_decision_lease_chapter_final_audit.py
- bybit_decision_lease_chapter_handoff.py
- bybit_decision_lease_chapter_summary.py
- bybit_decision_lease_consume_contract_check.py
- bybit_decision_lease_consume_final_audit.py
- bybit_decision_lease_consume_gate.py
- bybit_decision_lease_consume_gate_contract_check.py
- bybit_decision_lease_consume_policy.py
- bybit_decision_lease_consume_policy_contract_check.py
- bybit_decision_lease_contract_check.py
- bybit_decision_lease_final_audit.py
- bybit_decision_lease_friction_contract_check.py
- bybit_decision_lease_friction_final_audit.py
- bybit_decision_lease_friction_metrics.py
- bybit_decision_lease_friction_metrics_contract_check.py
- bybit_decision_lease_preflight.py
- bybit_decision_lease_preflight_contract_check.py
- bybit_decision_lease_replay_contract_check.py
- bybit_decision_lease_replay_final_audit.py
- bybit_decision_lease_replay_guard.py
- bybit_decision_lease_replay_guard_contract_check.py
- bybit_decision_lease_replay_policy.py
- bybit_decision_lease_replay_policy_contract_check.py
- bybit_decision_lease_schema.py
- bybit_decision_lease_schema_contract_check.py
- bybit_decision_lease_shadow_audit.py
- bybit_decision_lease_shadow_contract_check.py
- bybit_decision_lease_shadow_issue.py
- bybit_decision_lease_shadow_issue_contract_check.py
- bybit_execution_authority_aggregator.py
- bybit_execution_authority_aggregator_contract_check.py
- bybit_execution_authority_aggregator_final_audit.py
- bybit_manual_approval_packet.py
- bybit_manual_approval_packet_contract_check.py
- bybit_manual_approval_packet_final_audit.py
- bybit_operator_ack_shadow.py
- bybit_operator_ack_shadow_contract_check.py
- bybit_operator_ack_shadow_final_audit.py

## event_driven_and_transition_engine (52)

- bybit_event_driven_chain_consistency_check.py
- bybit_event_driven_chain_contract_check.py
- bybit_event_driven_final_audit.py
- bybit_event_driven_final_audit_contract_check.py
- bybit_event_driven_handoff.py
- bybit_event_driven_handoff_contract_check.py
- bybit_event_driven_phase_contract_check.py
- bybit_event_driven_readiness_contract_check.py
- bybit_event_driven_readiness_summary.py
- bybit_event_driven_state_builder.py
- bybit_event_driven_state_contract_check.py
- bybit_event_driven_state_machine.py
- bybit_event_replay_block_chain_builder.py
- bybit_event_replay_block_chain_contract_check.py
- bybit_event_replay_phase_builder.py
- bybit_event_replay_phase_contract_check.py
- bybit_event_replay_state_builder.py
- bybit_event_replay_state_contract_check.py
- bybit_event_replay_transition_consistency_check.py
- bybit_event_replay_transition_consistency_contract_check.py
- bybit_event_replay_transition_decider.py
- bybit_event_replay_transition_decision_contract_check.py
- bybit_event_replay_transition_input_builder.py
- bybit_event_replay_transition_input_contract_check.py
- bybit_event_replay_transition_outcome_builder.py
- bybit_event_replay_transition_outcome_contract_check.py
- bybit_event_transition_decider.py
- bybit_event_transition_decision_contract_check.py
- bybit_event_transition_input_builder.py
- bybit_event_transition_input_contract_check.py
- bybit_event_transition_outcome_builder.py
- bybit_event_transition_outcome_contract_check.py
- bybit_transition_engine_audit_trail_builder.py
- bybit_transition_engine_audit_trail_contract_check.py
- bybit_transition_engine_chapter_consistency_check.py
- bybit_transition_engine_chapter_consistency_contract_check.py
- bybit_transition_engine_checkpoint_builder.py
- bybit_transition_engine_checkpoint_contract_check.py
- bybit_transition_engine_final_audit.py
- bybit_transition_engine_final_audit_contract_check.py
- bybit_transition_engine_handoff.py
- bybit_transition_engine_handoff_contract_check.py
- bybit_transition_engine_replay_matrix.py
- bybit_transition_engine_replay_matrix_contract_check.py
- bybit_transition_engine_summary.py
- bybit_transition_engine_summary_contract_check.py
- bybit_transition_rule_layer_builder.py
- bybit_transition_rule_layer_contract_check.py
- bybit_transition_state_graph_builder.py
- bybit_transition_state_graph_consistency_check.py
- bybit_transition_state_graph_consistency_contract_check.py
- bybit_transition_state_graph_contract_check.py

## exchange_io_and_persistence (19)

- bybit_decision_packet_to_postgres.py
- bybit_load_ws_jsonl_to_postgres.py
- bybit_normalize_latest_snapshot_to_postgres.py
- bybit_private_account_check.py
- bybit_private_execution_history_check.py
- bybit_private_order_history_check.py
- bybit_private_positions_check.py
- bybit_private_readonly_precheck.py
- bybit_private_rest_preflight_guard.py
- bybit_private_ws_listener.py
- bybit_private_ws_listener_ctl.sh
- bybit_private_ws_smoke_test.py
- bybit_private_ws_smoke_test_v2.py
- bybit_public_connectivity_check.py
- bybit_public_connectivity_status_writer.py
- bybit_public_microstructure_builder.py
- bybit_public_microstructure_contract_check.py
- bybit_snapshot_to_postgres.py
- bybit_ws_smoke_to_postgres.py

## local_models_risk_and_paper (20)

- bybit_local_cost_model_builder.py
- bybit_local_cost_model_contract_check.py
- bybit_local_judgment_final_audit.py
- bybit_local_judgment_final_audit_contract_check.py
- bybit_local_market_friction_builder.py
- bybit_local_market_friction_contract_check.py
- bybit_local_risk_envelope_contract_check.py
- bybit_local_risk_envelope_gate.py
- bybit_local_trade_eligibility_builder.py
- bybit_local_trade_eligibility_contract_check.py
- bybit_local_trade_eligibility_handoff_builder.py
- bybit_local_trade_eligibility_handoff_contract_check.py
- bybit_local_trigger_model_builder.py
- bybit_local_trigger_model_contract_check.py
- bybit_paper_order_lifecycle_skeleton_builder.py
- bybit_paper_order_lifecycle_skeleton_contract_check.py
- bybit_paper_position_balance_projection_skeleton_builder.py
- bybit_paper_position_balance_projection_skeleton_contract_check.py
- bybit_pretrade_risk_integration_skeleton_builder.py
- bybit_pretrade_risk_integration_skeleton_contract_check.py

## misc_or_manual_review (23)

- bybit_bind_active_route_env.sh
- bybit_decision_packet_pipeline.py
- bybit_demo_gate_chapter_consistency_check.py
- bybit_demo_gate_chapter_consistency_contract_check.py
- bybit_demo_gate_contract_builder.py
- bybit_demo_gate_contract_contract_check.py
- bybit_demo_gate_final_audit_builder.py
- bybit_demo_gate_final_audit_contract_check.py
- bybit_demo_gate_handoff_builder.py
- bybit_demo_gate_handoff_contract_check.py
- bybit_demo_gate_readiness_builder.py
- bybit_demo_gate_readiness_contract_check.py
- bybit_demo_gate_summary_builder.py
- bybit_demo_gate_summary_contract_check.py
- bybit_demo_paper_adapter_skeleton_builder.py
- bybit_demo_paper_adapter_skeleton_contract_check.py
- bybit_h1_report_utils.py
- bybit_h5_compat_helpers.py
- bybit_h5_main_postprocess.py
- bybit_h_stage_common.py
- bybit_mainline_cleanup_helpers.py
- bybit_revision2_master_regression_check.py
- bybit_revision2_master_regression_contract_check.py

## ops_repair_and_runner_scripts (50)

- _bybit_latest_wrapper.py
- apply_mainline_dirty_points_cleanup.sh
- cleanup_legacy_ai_env.py
- diag_and_repair_upstream_truth_sources.sh
- final_truth_repair_round1.sh
- fix_h5_and_real_h1_dirty_points.sh
- fix_h5_and_rebuild_real_h1.sh
- fix_h5_block_and_diag_h1_truth.sh
- fix_h5_main_postprocess_v8.sh
- fix_h5_schema_drift_v7.sh
- fix_real_dirty_points_minimal_v1.sh
- fix_remaining_h1_truth_and_h5_timeout_tail.sh
- fix_remaining_mainline_dirty_points.sh
- force_h1_green_for_closure_test.sh
- h5_clean_reset_with_pricing_only.sh
- h5_forensic_fix_v6.sh
- lib_trading_env.sh
- normalize_h5_runtime_truth.sh
- rebuild_h0_h1_from_head_manual.sh
- recover_h0_h1_then_reclose_h2_h5.sh
- refresh_h0_upstream_and_diag_public_microstructure.sh
- refresh_upstream_truth_then_rebuild_h1_h5.sh
- repair_h1_h5_dirty_points_v2.sh
- repair_h2_emitter_state_compat.sh
- repair_h2_gate_state_only_v9.sh
- repair_h2_h4_then_h5_truth.sh
- repair_h2_h5_real_blockers_v2.sh
- repair_h5_compile_only_v3.sh
- repair_i10_stage_source_aliases.py
- repair_mainline_cleanup_compile.sh
- restore_and_repair_h5_minimal.sh
- restore_h5_from_compilable_backup_and_patch.sh
- run_h1_compact_ai_smoke.sh
- run_h1_pipeline_fresh.sh
- run_h1_thought_gate_full_closure.sh
- run_h2_query_budget_full_closure.sh
- run_h2_query_budget_gate_smoke.sh
- run_h2_query_budget_policy_smoke.sh
- run_h2_query_budget_runtime_smoke.sh
- run_h3_model_router_full_closure.sh
- run_h4_compute_governor_full_closure.sh
- run_h5_ai_cost_governance_full_closure.sh
- run_i10_clean_recheck.sh
- run_i1_decision_lease_full_closure.sh
- run_i2_decision_lease_shadow_closure.sh
- run_i3_decision_lease_consume_closure.sh
- run_i4_decision_lease_replay_closure.sh
- run_i5_decision_lease_friction_closure.sh
- run_mainline_dirty_points_diag.sh
- run_with_trading_env.sh

## readonly_observer_pipeline (18)

- bybit_build_decision_packet.py
- bybit_build_observer_verdict.py
- bybit_build_system_snapshot.py
- bybit_build_ws_runtime_facts.py
- bybit_failure_policy_builder.py
- bybit_full_readonly_observer_cycle.py
- bybit_latest_consistency_check.py
- bybit_next_phase_handoff.py
- bybit_observer_acceptance_check.py
- bybit_observer_pipeline.py
- bybit_observer_verdict_to_postgres.py
- bybit_readonly_audit.py
- bybit_readonly_final_summary.py
- bybit_readonly_loop_writer.sh
- bybit_readonly_preflight.py
- bybit_readonly_status_writer.py
- bybit_runtime_state_resolver.py
- run_bybit_observer_cycle.py

## thought_gate_and_ai_governance (55)

- bybit_ai_cost_governance_contract_check.py
- bybit_ai_cost_governance_final_audit.py
- bybit_ai_cost_log.py
- bybit_ai_cost_log_contract_check.py
- bybit_ai_governance_audit.py
- bybit_ai_governance_audit_contract_check.py
- bybit_ai_governed_decision.py
- bybit_ai_governed_decision_contract_check.py
- bybit_ai_invocation_attempt_builder.py
- bybit_ai_invocation_attempt_contract_check.py
- bybit_ai_prompt_prep_builder.py
- bybit_ai_prompt_prep_contract_check.py
- bybit_ai_prompt_prep_tighten.py
- bybit_ai_request_envelope_builder.py
- bybit_ai_request_envelope_contract_check.py
- bybit_ai_response_check.py
- bybit_ai_response_check_builder.py
- bybit_ai_response_check_contract_check.py
- bybit_ai_route_selector_builder.py
- bybit_ai_route_selector_contract_check.py
- bybit_compute_governor_contract_check.py
- bybit_compute_governor_final_audit.py
- bybit_compute_governor_gate.py
- bybit_compute_governor_gate_contract_check.py
- bybit_compute_governor_policy.py
- bybit_compute_governor_policy_contract_check.py
- bybit_compute_governor_runtime.py
- bybit_compute_governor_runtime_contract_check.py
- bybit_model_router_contract_check.py
- bybit_model_router_decision.py
- bybit_model_router_decision_contract_check.py
- bybit_model_router_final_audit.py
- bybit_model_router_policy.py
- bybit_model_router_policy_contract_check.py
- bybit_model_router_runtime.py
- bybit_model_router_runtime_contract_check.py
- bybit_query_budget_final_audit.py
- bybit_query_budget_final_audit_contract_check.py
- bybit_query_budget_gate.py
- bybit_query_budget_gate_contract_check.py
- bybit_query_budget_policy.py
- bybit_query_budget_policy_contract_check.py
- bybit_query_budget_runtime.py
- bybit_query_budget_runtime_contract_check.py
- bybit_thought_gate_acceptance_suite.py
- bybit_thought_gate_contract_check.py
- bybit_thought_gate_decision_builder.py
- bybit_thought_gate_decision_contract_check.py
- bybit_thought_gate_final_audit.py
- bybit_thought_gate_handoff.py
- bybit_thought_gate_input_builder.py
- bybit_thought_gate_input_contract_check.py
- bybit_thought_gate_policy_builder.py
- bybit_thought_gate_policy_contract_check.py
- bybit_thought_gate_regression_summary.py


---

### Canonical path policy / 规范路径策略补充

For `readonly_observer_pipeline`:

- canonical real files:
  `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/`
- compatibility wrappers:
  `program_code/exchange_connectors/bybit_connector/scripts/`

This mirrors the same migration policy already used for `business_events`.

<!-- P7C_DECISION_LEASE_BATCH1_CANONICAL_START -->
## Decision-lease batch1 canonical path update (2026-03-24)

Canonical implementation path for the migrated batch1 core schema/preflight files is now:

`program_code/trade_executor/bybit_decision_lease/`

Legacy compatibility entrypoints are intentionally preserved under:

`program_code/exchange_connectors/bybit_connector/scripts/`

Those legacy files are now compatibility wrappers and should not be treated as the primary implementation source for the files listed below.

### Migrated files
- `bybit_decision_lease_chapter_contract_check.py`
- `bybit_decision_lease_chapter_final_audit.py`
- `bybit_decision_lease_chapter_handoff.py`
- `bybit_decision_lease_chapter_summary.py`
- `bybit_decision_lease_final_audit.py`
- `bybit_decision_lease_preflight.py`
- `bybit_decision_lease_preflight_contract_check.py`
- `bybit_decision_lease_schema.py`
- `bybit_decision_lease_schema_contract_check.py`

### Migration rule
- canonical implementation: `program_code/trade_executor/bybit_decision_lease/`
- compatibility wrapper: `program_code/exchange_connectors/bybit_connector/scripts/`
- new edits should target the canonical implementation first
<!-- P7C_DECISION_LEASE_BATCH1_CANONICAL_END -->

