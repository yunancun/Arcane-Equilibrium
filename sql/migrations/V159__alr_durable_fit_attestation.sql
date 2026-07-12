-- V159: durable externally authenticated ALR challenger fit attestation.
--
-- Source-only forward migration.  It verifies pre-provisioned identities,
-- closes over an exact empty V158 result surface, and adds only durable
-- attestation/lineage state.  It never creates a role or credential, contacts
-- a runtime or broker, runs a fit, exposes a model, or grants trading authority.
BEGIN;
SET LOCAL search_path = pg_catalog, pg_temp;

-- One transaction-local validator is used for the frozen V158 entry state,
-- the fully applied V159 replay state, and the final postflight state.
CREATE OR REPLACE FUNCTION pg_temp.alr_v159_assert_catalog(p_mode TEXT)
RETURNS VOID LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp
AS $v159_catalog_validator$
DECLARE
    v_schema_owner OID; v_writer OID; v_caller OID; v_attestor OID; v_attestor_caller OID;
    v_spec RECORD; v_actual RECORD; v_expr RECORD; v_definition TEXT; v_expected_rel REGCLASS;
    v_count INTEGER; v_writer_owned INTEGER; v_attestor_owned INTEGER; v_oid OID;
BEGIN
    IF p_mode IS NULL OR p_mode NOT IN ('legacy','replay','final') THEN RAISE EXCEPTION 'V159 catalog FAIL: invalid mode %',p_mode; END IF;
    SELECT nspowner INTO v_schema_owner FROM pg_namespace WHERE nspname='learning';
    SELECT oid INTO v_writer FROM pg_roles WHERE rolname='alr_challenger_writer';
    SELECT oid INTO v_caller FROM pg_roles WHERE rolname='alr_challenger_trainer_caller';
    SELECT oid INTO v_attestor FROM pg_roles WHERE rolname='alr_challenger_fit_attestor';
    SELECT oid INTO v_attestor_caller FROM pg_roles WHERE rolname='alr_challenger_fit_attestor_caller';
    IF v_schema_owner IS NULL OR v_writer IS NULL OR v_caller IS NULL OR v_attestor IS NULL OR v_attestor_caller IS NULL THEN RAISE EXCEPTION 'V159 catalog FAIL: required role/schema identity missing'; END IF;
    IF session_user<>current_user OR NOT EXISTS(SELECT 1 FROM pg_roles r WHERE r.oid=v_schema_owner AND r.rolsuper) OR EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.roleid=v_schema_owner) THEN RAISE EXCEPTION 'V159 catalog FAIL: trusted learning owner'; END IF;

    FOR v_spec IN SELECT * FROM (VALUES
      ('learning.alr_qualified_training_receipts','1:durable_receipt_hash:text:true:false:-:-:-|2:source_receipt_hash:text:true:false:-:-:-|3:source_contract_hash:text:true:false:-:-:-|4:projection_artifact_hash:text:true:false:-:-:-|5:selection_binding_hash:text:true:false:-:-:-|6:proof_input_hash:text:true:false:-:-:-|7:proof_packet_hash:text:true:false:-:-:-|8:reward_set_hash:text:true:false:-:-:-|9:pit_dataset_manifest_hash:text:true:false:-:-:-|10:after_cost_label_set_hash:text:true:false:-:-:-|11:evidence_set_hash:text:true:false:-:-:-|12:training_input_hash:text:true:false:-:-:-|13:training_key_hash:text:true:false:-:-:-|14:code_manifest_hash:text:true:false:-:-:-|15:training_config_hash:text:true:false:-:-:-|16:receipt_status:text:true:false:-:-:-|17:canonical_payload:jsonb:true:false:-:-:-|18:no_authority:jsonb:true:false:-:-:-|19:authority_counters:jsonb:true:false:-:-:-|20:created_at:timestamp with time zone:true:true:-:-:CURRENT_TIMESTAMP',NULL::TEXT),
      ('learning.alr_challenger_training_runs','1:training_run_hash:text:true:false:-:-:-|2:durable_receipt_hash:text:true:false:-:-:-|3:training_key_hash:text:true:false:-:-:-|4:source_head:text:true:false:-:-:-|5:actual_dataset_hash:text:true:false:-:-:-|6:actual_row_ids_hash:text:true:false:-:-:-|7:actual_split_hash:text:true:false:-:-:-|8:actual_code_manifest_hash:text:true:false:-:-:-|9:actual_training_config_hash:text:true:false:-:-:-|10:actual_feature_schema_hash:text:true:false:-:-:-|11:actual_label_schema_hash:text:true:false:-:-:-|12:model_schema_version:text:true:false:-:-:-|13:actual_training_rows:integer:true:false:-:-:-|14:model_artifact_set_hash:text:true:false:-:-:-|15:metrics_hash:text:true:false:-:-:-|16:resource_usage_hash:text:true:false:-:-:-|17:run_status:text:true:false:-:-:-|18:model_training_performed:boolean:true:false:-:-:-|19:canonical_payload:jsonb:true:false:-:-:-|20:no_authority:jsonb:true:false:-:-:-|21:authority_counters:jsonb:true:false:-:-:-|22:fit_started_at:timestamp with time zone:true:false:-:-:-|23:fit_completed_at:timestamp with time zone:true:false:-:-:-|24:created_at:timestamp with time zone:true:true:-:-:CURRENT_TIMESTAMP','1:training_run_hash:text:true:false:-:-:-|2:durable_receipt_hash:text:true:false:-:-:-|3:training_key_hash:text:true:false:-:-:-|4:source_head:text:true:false:-:-:-|5:actual_dataset_hash:text:true:false:-:-:-|6:actual_row_ids_hash:text:true:false:-:-:-|7:actual_split_hash:text:true:false:-:-:-|8:actual_code_manifest_hash:text:true:false:-:-:-|9:actual_training_config_hash:text:true:false:-:-:-|10:actual_feature_schema_hash:text:true:false:-:-:-|11:actual_label_schema_hash:text:true:false:-:-:-|12:model_schema_version:text:true:false:-:-:-|13:actual_training_rows:integer:true:false:-:-:-|14:model_artifact_set_hash:text:true:false:-:-:-|15:metrics_hash:text:true:false:-:-:-|16:resource_usage_hash:text:true:false:-:-:-|17:run_status:text:true:false:-:-:-|18:model_training_performed:boolean:true:false:-:-:-|19:canonical_payload:jsonb:true:false:-:-:-|20:no_authority:jsonb:true:false:-:-:-|21:authority_counters:jsonb:true:false:-:-:-|22:fit_started_at:timestamp with time zone:true:false:-:-:-|23:fit_completed_at:timestamp with time zone:true:false:-:-:-|24:created_at:timestamp with time zone:true:true:-:-:CURRENT_TIMESTAMP|25:durable_attestation_hash:text:true:false:-:-:-|26:durable_training_run_hash:text:true:false:-:-:-|27:attestation_bound_at:timestamp with time zone:true:false:-:-:-|28:attestation_verified_at:timestamp with time zone:true:false:-:-:-|29:attestation_expires_at:timestamp with time zone:true:false:-:-:-'),
      ('learning.alr_challenger_model_artifacts','1:artifact_hash:text:true:false:-:-:-|2:training_run_hash:text:true:false:-:-:-|3:training_key_hash:text:true:false:-:-:-|4:model_artifact_set_hash:text:true:false:-:-:-|5:quantile:text:true:false:-:-:-|6:artifact_format:text:true:false:-:-:-|7:artifact_path:text:true:false:-:-:-|8:artifact_size_bytes:bigint:true:false:-:-:-|9:feature_schema_hash:text:true:false:-:-:-|10:model_schema_version:text:true:false:-:-:-|11:symlink_created:boolean:true:false:-:-:-|12:serving_visible:boolean:true:false:-:-:-|13:created_at:timestamp with time zone:true:true:-:-:CURRENT_TIMESTAMP','1:artifact_hash:text:true:false:-:-:-|2:training_run_hash:text:true:false:-:-:-|3:training_key_hash:text:true:false:-:-:-|4:model_artifact_set_hash:text:true:false:-:-:-|5:quantile:text:true:false:-:-:-|6:artifact_format:text:true:false:-:-:-|7:artifact_path:text:true:false:-:-:-|8:artifact_size_bytes:bigint:true:false:-:-:-|9:feature_schema_hash:text:true:false:-:-:-|10:model_schema_version:text:true:false:-:-:-|11:symlink_created:boolean:true:false:-:-:-|12:serving_visible:boolean:true:false:-:-:-|13:created_at:timestamp with time zone:true:true:-:-:CURRENT_TIMESTAMP|14:durable_attestation_hash:text:true:false:-:-:-|15:durable_training_run_hash:text:true:false:-:-:-'),
      ('learning.alr_challenger_registry','1:challenger_hash:text:true:false:-:-:-|2:training_run_hash:text:true:false:-:-:-|3:training_key_hash:text:true:false:-:-:-|4:model_artifact_set_hash:text:true:false:-:-:-|5:registry_status:text:true:false:-:-:-|6:serving_allowed:boolean:true:false:-:-:-|7:promotion_allowed:boolean:true:false:-:-:-|8:latest_pointer_allowed:boolean:true:false:-:-:-|9:symlink_allowed:boolean:true:false:-:-:-|10:canonical_payload:jsonb:true:false:-:-:-|11:created_at:timestamp with time zone:true:true:-:-:CURRENT_TIMESTAMP','1:challenger_hash:text:true:false:-:-:-|2:training_run_hash:text:true:false:-:-:-|3:training_key_hash:text:true:false:-:-:-|4:model_artifact_set_hash:text:true:false:-:-:-|5:registry_status:text:true:false:-:-:-|6:serving_allowed:boolean:true:false:-:-:-|7:promotion_allowed:boolean:true:false:-:-:-|8:latest_pointer_allowed:boolean:true:false:-:-:-|9:symlink_allowed:boolean:true:false:-:-:-|10:canonical_payload:jsonb:true:false:-:-:-|11:created_at:timestamp with time zone:true:true:-:-:CURRENT_TIMESTAMP|12:durable_attestation_hash:text:true:false:-:-:-|13:durable_training_run_hash:text:true:false:-:-:-|14:durable_challenger_hash:text:true:false:-:-:-|15:attestation_bound_at:timestamp with time zone:true:false:-:-:-'),
      ('learning.alr_challenger_fit_attestations',NULL::TEXT,'1:durable_attestation_hash:text:true:false:-:-:-|2:external_receipt_digest:text:true:false:-:-:-|3:signed_receipt_bytes:bytea:true:false:-:-:-|4:receipt_projection:jsonb:true:false:-:-:-|5:evidence_tier:text:true:false:-:-:-|6:claim_kind:text:true:false:-:-:-|7:authentication_status:text:true:false:-:-:-|8:durable_receipt_hash:text:true:false:-:-:-|9:training_key_hash:text:true:false:-:-:-|10:structural_result_hash:text:true:false:-:-:-|11:structural_fit_capture_hash:text:true:false:-:-:-|12:structural_candidate_hash:text:true:false:-:-:-|13:structural_training_run_hash:text:true:false:-:-:-|14:structural_challenger_hash:text:true:false:-:-:-|15:runner_identity_hash:text:true:false:-:-:-|16:actual_input_material_set_hash:text:true:false:-:-:-|17:ordered_artifact_set_hash:text:true:false:-:-:-|18:issuer_id:text:true:false:-:-:-|19:trust_policy_id:text:true:false:-:-:-|20:signature_key_id:text:true:false:-:-:-|21:signature_algorithm:text:true:false:-:-:-|22:verified_at:timestamp with time zone:true:false:-:-:-|23:expires_at:timestamp with time zone:true:false:-:-:-|24:no_authority:jsonb:true:false:-:-:-|25:authority_counters:jsonb:true:false:-:-:-|26:created_at:timestamp with time zone:true:true:-:-:CURRENT_TIMESTAMP')
    ) AS x(table_name,legacy_signature,final_signature) LOOP
        v_definition:=CASE WHEN p_mode='legacy' THEN v_spec.legacy_signature ELSE COALESCE(v_spec.final_signature,v_spec.legacy_signature) END;
        IF v_definition IS NULL THEN IF to_regclass(v_spec.table_name) IS NOT NULL THEN RAISE EXCEPTION 'V159 catalog FAIL: legacy forward table present: %',v_spec.table_name; END IF; CONTINUE; END IF;
        IF to_regclass(v_spec.table_name) IS NULL THEN RAISE EXCEPTION 'V159 catalog FAIL: table missing: %',v_spec.table_name; END IF;
        IF NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=v_spec.table_name::regclass AND n.nspname='learning' AND c.relowner=v_schema_owner AND c.relkind='r' AND c.relpersistence='p' AND c.relispartition IS FALSE AND c.relrowsecurity IS FALSE AND c.relforcerowsecurity IS FALSE AND c.relhasrules IS FALSE AND c.relreplident='d' AND c.reloftype=0 AND c.reloptions IS NULL AND c.reltablespace=0 AND c.relam=(SELECT oid FROM pg_am WHERE amname='heap')) OR EXISTS(SELECT 1 FROM pg_inherits WHERE inhrelid=v_spec.table_name::regclass OR inhparent=v_spec.table_name::regclass) OR EXISTS(SELECT 1 FROM pg_policy WHERE polrelid=v_spec.table_name::regclass) THEN RAISE EXCEPTION 'V159 catalog FAIL: table posture: %',v_spec.table_name; END IF;
        SELECT string_agg(a.attnum::TEXT||':'||a.attname||':'||format_type(a.atttypid,a.atttypmod)||':'||a.attnotnull::TEXT||':'||a.atthasdef::TEXT||':'||COALESCE(NULLIF(a.attgenerated::TEXT,''),'-')||':'||COALESCE(NULLIF(a.attidentity::TEXT,''),'-')||':'||COALESCE(pg_get_expr(d.adbin,d.adrelid,FALSE),'-'),'|' ORDER BY a.attnum) INTO v_actual FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE a.attrelid=v_spec.table_name::regclass AND a.attnum>0 AND NOT a.attisdropped;
        IF v_actual.string_agg IS DISTINCT FROM v_definition OR EXISTS(SELECT 1 FROM pg_attribute a WHERE a.attrelid=v_spec.table_name::regclass AND a.attnum>0 AND NOT a.attisdropped AND (a.attndims<>0 OR a.attcollation IS DISTINCT FROM CASE WHEN a.atttypid='text'::regtype THEN 'default'::regcollation::OID ELSE 0::OID END)) THEN RAISE EXCEPTION 'V159 catalog FAIL: exact column signature: %',v_spec.table_name; END IF;
    END LOOP;

    EXECUTE 'DROP TABLE IF EXISTS alr_v159_expected_receipts,alr_v159_expected_runs,alr_v159_expected_artifacts,alr_v159_expected_registry,alr_v159_expected_attestations';
    EXECUTE 'CREATE TEMP TABLE alr_v159_expected_receipts (LIKE learning.alr_qualified_training_receipts) ON COMMIT DROP';
    EXECUTE 'CREATE TEMP TABLE alr_v159_expected_runs (LIKE learning.alr_challenger_training_runs) ON COMMIT DROP';
    EXECUTE 'CREATE TEMP TABLE alr_v159_expected_artifacts (LIKE learning.alr_challenger_model_artifacts) ON COMMIT DROP';
    EXECUTE 'CREATE TEMP TABLE alr_v159_expected_registry (LIKE learning.alr_challenger_registry) ON COMMIT DROP';
    EXECUTE $ddl$ALTER TABLE alr_v159_expected_receipts ADD CONSTRAINT alr_qualified_receipts_hashes_check CHECK(durable_receipt_hash~'^[0-9a-f]{64}$' AND source_receipt_hash~'^[0-9a-f]{64}$' AND source_contract_hash~'^[0-9a-f]{64}$' AND projection_artifact_hash~'^[0-9a-f]{64}$' AND selection_binding_hash~'^[0-9a-f]{64}$' AND proof_input_hash~'^[0-9a-f]{64}$' AND proof_packet_hash~'^[0-9a-f]{64}$' AND reward_set_hash~'^[0-9a-f]{64}$' AND pit_dataset_manifest_hash~'^[0-9a-f]{64}$' AND after_cost_label_set_hash~'^[0-9a-f]{64}$' AND evidence_set_hash~'^[0-9a-f]{64}$' AND training_input_hash~'^[0-9a-f]{64}$' AND training_key_hash~'^[0-9a-f]{64}$' AND code_manifest_hash~'^[0-9a-f]{64}$' AND training_config_hash~'^[0-9a-f]{64}$'),ADD CONSTRAINT alr_qualified_receipts_status_check CHECK(receipt_status='QUALIFIED_INPUT_PERSISTED'),ADD CONSTRAINT alr_qualified_receipts_payload_check CHECK(jsonb_typeof(canonical_payload)='object' AND canonical_payload->>'schema_version' IS NOT DISTINCT FROM 'alr_qualified_training_receipt_v1' AND canonical_payload?&ARRAY['schema_version','durable_receipt_hash','source_receipt_hash','source_contract_hash','projection_artifact_hash','projection_artifact_kind','selection_binding_hash','proof_input_hash','proof_packet_hash','reward_set_hash','pit_dataset_manifest_hash','after_cost_label_set_hash','evidence_set_hash','training_input_hash','training_key_hash','code_manifest_hash','training_config_hash','receipt_status','training_allowed','model_training_performed','registry_write_allowed','runtime_or_exchange_attested','no_authority','authority_counters','dataset_hash','row_ids_hash','split_hash','feature_schema_hash','label_schema_hash','training_rows']::TEXT[] AND canonical_payload-ARRAY['schema_version','durable_receipt_hash','source_receipt_hash','source_contract_hash','projection_artifact_hash','projection_artifact_kind','selection_binding_hash','proof_input_hash','proof_packet_hash','reward_set_hash','pit_dataset_manifest_hash','after_cost_label_set_hash','evidence_set_hash','training_input_hash','training_key_hash','code_manifest_hash','training_config_hash','receipt_status','training_allowed','model_training_performed','registry_write_allowed','runtime_or_exchange_attested','no_authority','authority_counters','dataset_hash','row_ids_hash','split_hash','feature_schema_hash','label_schema_hash','training_rows']::TEXT[]='{}'::JSONB),ADD CONSTRAINT alr_qualified_receipts_no_authority_check CHECK(no_authority='{"exchange_authority":false,"trading_authority":false,"order_or_probe_authority":false,"decision_lease_authority":false,"cost_gate_authority":false,"proof_authority":false,"serving_authority":false,"promotion_authority":false,"latest_authority":false,"runtime_mutation_authority":false,"database_write_authority":false,"symlink_authority":false}'::JSONB),ADD CONSTRAINT alr_qualified_receipts_counters_check CHECK(authority_counters='{"exchange_contact_count":0,"trading_action_count":0,"order_or_probe_count":0,"decision_lease_count":0,"cost_gate_change_count":0,"proof_claim_count":0,"serving_or_promotion_count":0,"runtime_mutation_count":0,"database_write_count":0,"symlink_update_count":0,"model_fit_count":0}'::JSONB)$ddl$;
    EXECUTE $ddl$ALTER TABLE alr_v159_expected_runs ADD CONSTRAINT alr_challenger_runs_hashes_check CHECK(training_run_hash~'^[0-9a-f]{64}$' AND durable_receipt_hash~'^[0-9a-f]{64}$' AND training_key_hash~'^[0-9a-f]{64}$' AND source_head~'^[0-9a-f]{40}$' AND actual_dataset_hash~'^[0-9a-f]{64}$' AND actual_row_ids_hash~'^[0-9a-f]{64}$' AND actual_split_hash~'^[0-9a-f]{64}$' AND actual_code_manifest_hash~'^[0-9a-f]{64}$' AND actual_training_config_hash~'^[0-9a-f]{64}$' AND actual_feature_schema_hash~'^[0-9a-f]{64}$' AND actual_label_schema_hash~'^[0-9a-f]{64}$' AND model_artifact_set_hash~'^[0-9a-f]{64}$' AND metrics_hash~'^[0-9a-f]{64}$' AND resource_usage_hash~'^[0-9a-f]{64}$'),ADD CONSTRAINT alr_challenger_runs_model_schema_check CHECK(model_schema_version~'^[a-z0-9][a-z0-9_.-]{0,127}$'),ADD CONSTRAINT alr_challenger_runs_state_check CHECK(run_status='TRAINING_PERFORMED' AND model_training_performed IS TRUE AND actual_training_rows>0 AND fit_completed_at>=fit_started_at),ADD CONSTRAINT alr_challenger_runs_no_authority_check CHECK(no_authority='{"exchange_authority":false,"trading_authority":false,"order_or_probe_authority":false,"decision_lease_authority":false,"cost_gate_authority":false,"proof_authority":false,"serving_authority":false,"promotion_authority":false,"latest_authority":false,"runtime_mutation_authority":false,"database_write_authority":false,"symlink_authority":false}'::JSONB)$ddl$;
    EXECUTE $ddl$ALTER TABLE alr_v159_expected_artifacts ADD CONSTRAINT alr_challenger_artifacts_hashes_check CHECK(artifact_hash~'^[0-9a-f]{64}$' AND training_run_hash~'^[0-9a-f]{64}$' AND training_key_hash~'^[0-9a-f]{64}$' AND model_artifact_set_hash~'^[0-9a-f]{64}$' AND feature_schema_hash~'^[0-9a-f]{64}$')$ddl$;
    EXECUTE $ddl$ALTER TABLE alr_v159_expected_registry ADD CONSTRAINT alr_challenger_registry_hashes_check CHECK(challenger_hash~'^[0-9a-f]{64}$' AND training_run_hash~'^[0-9a-f]{64}$' AND training_key_hash~'^[0-9a-f]{64}$' AND model_artifact_set_hash~'^[0-9a-f]{64}$'),ADD CONSTRAINT alr_challenger_registry_state_check CHECK(registry_status='NOT_SERVING' AND serving_allowed IS FALSE AND promotion_allowed IS FALSE AND latest_pointer_allowed IS FALSE AND symlink_allowed IS FALSE)$ddl$;
    IF p_mode='legacy' THEN
        EXECUTE $ddl$ALTER TABLE alr_v159_expected_runs ADD CONSTRAINT alr_challenger_runs_payload_check CHECK(jsonb_typeof(canonical_payload)='object' AND canonical_payload->>'schema_version' IS NOT DISTINCT FROM 'alr_challenger_training_result_v1'),ADD CONSTRAINT alr_challenger_runs_counters_check CHECK(authority_counters='{"exchange_contact_count":0,"trading_action_count":0,"order_or_probe_count":0,"decision_lease_count":0,"cost_gate_change_count":0,"proof_claim_count":0,"serving_or_promotion_count":0,"runtime_mutation_count":0,"database_write_count":0,"symlink_update_count":0,"model_fit_count":1}'::JSONB)$ddl$;
        EXECUTE $ddl$ALTER TABLE alr_v159_expected_artifacts ADD CONSTRAINT alr_challenger_artifacts_shape_check CHECK(quantile IN('q10','q50','q90') AND artifact_format='onnx' AND artifact_size_bytes>0 AND model_schema_version~'^[a-z0-9][a-z0-9_.-]{0,127}$' AND artifact_path='runs/'||training_run_hash||'/'||quantile||'.onnx' AND symlink_created IS FALSE AND serving_visible IS FALSE)$ddl$;
        EXECUTE $ddl$ALTER TABLE alr_v159_expected_registry ADD CONSTRAINT alr_challenger_registry_payload_check CHECK(jsonb_typeof(canonical_payload)='object' AND canonical_payload->>'schema_version' IS NOT DISTINCT FROM 'alr_challenger_registry_entry_v1')$ddl$;
    ELSE
        EXECUTE $ddl$ALTER TABLE alr_v159_expected_runs ADD CONSTRAINT alr_challenger_runs_payload_check CHECK(jsonb_typeof(canonical_payload)='object' AND canonical_payload->>'schema_version' IS NOT DISTINCT FROM 'alr_challenger_training_result_v2'),ADD CONSTRAINT alr_challenger_runs_counters_check CHECK(authority_counters='{"exchange_contact_count":0,"trading_action_count":0,"order_or_probe_count":0,"decision_lease_count":0,"cost_gate_change_count":0,"proof_claim_count":0,"serving_or_promotion_count":0,"runtime_mutation_count":0,"database_write_count":0,"symlink_update_count":0,"model_fit_count":0}'::JSONB),ADD CONSTRAINT alr_challenger_runs_v159_hashes_check CHECK(durable_attestation_hash~'^[0-9a-f]{64}$' AND durable_training_run_hash~'^[0-9a-f]{64}$'),ADD CONSTRAINT alr_challenger_runs_v159_time_check CHECK(fit_completed_at<=attestation_verified_at AND attestation_verified_at<=attestation_bound_at AND attestation_bound_at<attestation_expires_at)$ddl$;
        EXECUTE $ddl$ALTER TABLE alr_v159_expected_artifacts ADD CONSTRAINT alr_challenger_artifacts_shape_check CHECK(quantile IN('q10','q50','q90') AND artifact_format='onnx' AND artifact_size_bytes>0 AND model_schema_version~'^[a-z0-9][a-z0-9_.-]{0,127}$' AND artifact_path='runs/structural/'||training_run_hash||'/'||quantile||'.onnx' AND symlink_created IS FALSE AND serving_visible IS FALSE),ADD CONSTRAINT alr_challenger_artifacts_v159_hashes_check CHECK(durable_attestation_hash~'^[0-9a-f]{64}$' AND durable_training_run_hash~'^[0-9a-f]{64}$')$ddl$;
        EXECUTE $ddl$ALTER TABLE alr_v159_expected_registry ADD CONSTRAINT alr_challenger_registry_payload_check CHECK(jsonb_typeof(canonical_payload)='object' AND canonical_payload->>'schema_version' IS NOT DISTINCT FROM 'alr_challenger_registry_entry_v2'),ADD CONSTRAINT alr_challenger_registry_v159_hashes_check CHECK(durable_attestation_hash~'^[0-9a-f]{64}$' AND durable_training_run_hash~'^[0-9a-f]{64}$' AND durable_challenger_hash~'^[0-9a-f]{64}$')$ddl$;
        EXECUTE 'CREATE TEMP TABLE alr_v159_expected_attestations (LIKE learning.alr_challenger_fit_attestations) ON COMMIT DROP';
        EXECUTE $ddl$ALTER TABLE alr_v159_expected_attestations ADD CONSTRAINT alr_fit_attestations_hashes_check CHECK(durable_attestation_hash~'^[0-9a-f]{64}$' AND external_receipt_digest~'^[0-9a-f]{64}$' AND durable_receipt_hash~'^[0-9a-f]{64}$' AND training_key_hash~'^[0-9a-f]{64}$' AND structural_result_hash~'^[0-9a-f]{64}$' AND structural_fit_capture_hash~'^[0-9a-f]{64}$' AND structural_candidate_hash~'^[0-9a-f]{64}$' AND structural_training_run_hash~'^[0-9a-f]{64}$' AND structural_challenger_hash~'^[0-9a-f]{64}$' AND runner_identity_hash~'^[0-9a-f]{64}$' AND actual_input_material_set_hash~'^[0-9a-f]{64}$' AND ordered_artifact_set_hash~'^[0-9a-f]{64}$'),ADD CONSTRAINT alr_fit_attestations_signed_bytes_check CHECK(octet_length(signed_receipt_bytes) BETWEEN 2 AND 1048576 AND external_receipt_digest=encode(public.digest(signed_receipt_bytes,'sha256'::TEXT),'hex'::TEXT) AND signed_receipt_bytes=convert_to(receipt_projection::TEXT,'UTF8'::NAME)),ADD CONSTRAINT alr_fit_attestations_time_check CHECK(isfinite(verified_at) AND isfinite(expires_at) AND verified_at<expires_at),ADD CONSTRAINT alr_fit_attestations_no_authority_check CHECK(no_authority='{"exchange_authority":false,"trading_authority":false,"order_or_probe_authority":false,"decision_lease_authority":false,"cost_gate_authority":false,"proof_authority":false,"serving_authority":false,"promotion_authority":false,"latest_authority":false,"runtime_mutation_authority":false,"database_write_authority":false,"symlink_authority":false}'::JSONB AND receipt_projection->'no_authority'=no_authority),ADD CONSTRAINT alr_fit_attestations_counters_check CHECK(authority_counters='{"exchange_contact_count":0,"trading_action_count":0,"order_or_probe_count":0,"decision_lease_count":0,"cost_gate_change_count":0,"proof_claim_count":0,"serving_or_promotion_count":0,"runtime_mutation_count":0,"database_write_count":0,"symlink_update_count":0,"model_fit_count":0}'::JSONB AND receipt_projection->'authority_counters'=authority_counters)$ddl$;
        EXECUTE $ddl$ALTER TABLE alr_v159_expected_attestations ADD CONSTRAINT alr_fit_attestations_evidence_check CHECK(evidence_tier='PLATFORM_OR_EXTERNAL_ATTESTED' AND claim_kind='ALR_FIT_EXECUTION_ATTESTATION_V1' AND authentication_status='SIGNATURE_VERIFIED_BY_TRUST_POLICY' AND issuer_id~'^[a-z0-9][a-z0-9_.:-]{0,127}$' AND trust_policy_id~'^[a-z0-9][a-z0-9_.:-]{0,127}$' AND signature_key_id~'^[a-z0-9][a-z0-9_.:-]{0,127}$' AND signature_algorithm IN('ed25519','ecdsa-p256-sha256') AND jsonb_typeof(receipt_projection)='object' AND receipt_projection?&ARRAY['schema_version','evidence_tier','claim_kind','authentication_status','subject','claims','result_observation','authentication','verified_at','expires_at','no_authority','authority_counters']::TEXT[] AND receipt_projection-ARRAY['schema_version','evidence_tier','claim_kind','authentication_status','subject','claims','result_observation','authentication','verified_at','expires_at','no_authority','authority_counters']::TEXT[]='{}'::JSONB AND receipt_projection->>'schema_version' IS NOT DISTINCT FROM 'alr_fit_execution_signed_receipt_v1' AND receipt_projection->>'evidence_tier' IS NOT DISTINCT FROM evidence_tier AND receipt_projection->>'claim_kind' IS NOT DISTINCT FROM claim_kind AND receipt_projection->>'authentication_status' IS NOT DISTINCT FROM authentication_status AND jsonb_typeof(receipt_projection->'schema_version') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection->'evidence_tier') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection->'claim_kind') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection->'authentication_status') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection->'subject')='object' AND receipt_projection->'subject'?&ARRAY['durable_receipt_hash','training_key_hash','result_hash','fit_capture_hash','candidate_attestation_hash','training_run_hash','challenger_hash','runner_identity_hash','actual_input_material_set_hash','ordered_artifact_set_hash']::TEXT[] AND (receipt_projection->'subject')-ARRAY['durable_receipt_hash','training_key_hash','result_hash','fit_capture_hash','candidate_attestation_hash','training_run_hash','challenger_hash','runner_identity_hash','actual_input_material_set_hash','ordered_artifact_set_hash']::TEXT[]='{}'::JSONB AND receipt_projection#>>'{subject,durable_receipt_hash}' IS NOT DISTINCT FROM durable_receipt_hash AND receipt_projection#>>'{subject,training_key_hash}' IS NOT DISTINCT FROM training_key_hash AND receipt_projection#>>'{subject,result_hash}' IS NOT DISTINCT FROM structural_result_hash AND receipt_projection#>>'{subject,fit_capture_hash}' IS NOT DISTINCT FROM structural_fit_capture_hash AND receipt_projection#>>'{subject,candidate_attestation_hash}' IS NOT DISTINCT FROM structural_candidate_hash AND receipt_projection#>>'{subject,training_run_hash}' IS NOT DISTINCT FROM structural_training_run_hash AND receipt_projection#>>'{subject,challenger_hash}' IS NOT DISTINCT FROM structural_challenger_hash AND receipt_projection#>>'{subject,runner_identity_hash}' IS NOT DISTINCT FROM runner_identity_hash AND receipt_projection#>>'{subject,actual_input_material_set_hash}' IS NOT DISTINCT FROM actual_input_material_set_hash AND receipt_projection#>>'{subject,ordered_artifact_set_hash}' IS NOT DISTINCT FROM ordered_artifact_set_hash AND jsonb_typeof(receipt_projection#>'{subject,durable_receipt_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{subject,training_key_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{subject,result_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{subject,fit_capture_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{subject,candidate_attestation_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{subject,training_run_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{subject,challenger_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{subject,runner_identity_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{subject,actual_input_material_set_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{subject,ordered_artifact_set_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection->'claims')='object' AND receipt_projection->'claims'?&ARRAY['actual_inputs_consumed','actual_fit_executed','model_training_performed','artifact_readback_completed','onnx_semantic_validation_passed']::TEXT[] AND (receipt_projection->'claims')-ARRAY['actual_inputs_consumed','actual_fit_executed','model_training_performed','artifact_readback_completed','onnx_semantic_validation_passed']::TEXT[]='{}'::JSONB AND receipt_projection#>'{claims,actual_inputs_consumed}'='true'::JSONB AND receipt_projection#>'{claims,actual_fit_executed}'='true'::JSONB AND receipt_projection#>'{claims,model_training_performed}'='true'::JSONB AND receipt_projection#>'{claims,artifact_readback_completed}'='true'::JSONB AND receipt_projection#>'{claims,onnx_semantic_validation_passed}'='true'::JSONB AND jsonb_typeof(receipt_projection->'result_observation')='object' AND receipt_projection->'result_observation'?&ARRAY['source_head','actual_inputs','model','fit_started_at','fit_completed_at','artifacts']::TEXT[] AND (receipt_projection->'result_observation')-ARRAY['source_head','actual_inputs','model','fit_started_at','fit_completed_at','artifacts']::TEXT[]='{}'::JSONB AND jsonb_typeof(receipt_projection#>'{result_observation,source_head}') IS NOT DISTINCT FROM 'string' AND COALESCE(receipt_projection#>>'{result_observation,source_head}','')~'^[0-9a-f]{40}$' AND jsonb_typeof(receipt_projection#>'{result_observation,fit_started_at}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{result_observation,fit_completed_at}') IS NOT DISTINCT FROM 'string' AND COALESCE(receipt_projection#>>'{result_observation,fit_started_at}','')~'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$' AND COALESCE(receipt_projection#>>'{result_observation,fit_completed_at}','')~'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$' AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs}')='object' AND receipt_projection#>'{result_observation,actual_inputs}'?&ARRAY['dataset_hash','row_ids_hash','split_hash','code_manifest_hash','training_config_hash','feature_schema_hash','label_schema_hash','training_rows']::TEXT[] AND (receipt_projection#>'{result_observation,actual_inputs}')-ARRAY['dataset_hash','row_ids_hash','split_hash','code_manifest_hash','training_config_hash','feature_schema_hash','label_schema_hash','training_rows']::TEXT[]='{}'::JSONB AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,dataset_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,row_ids_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,split_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,code_manifest_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,training_config_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,feature_schema_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,label_schema_hash}') IS NOT DISTINCT FROM 'string' AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,dataset_hash}','')~'^[0-9a-f]{64}$' AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,row_ids_hash}','')~'^[0-9a-f]{64}$' AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,split_hash}','')~'^[0-9a-f]{64}$' AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,code_manifest_hash}','')~'^[0-9a-f]{64}$' AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,training_config_hash}','')~'^[0-9a-f]{64}$' AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,feature_schema_hash}','')~'^[0-9a-f]{64}$' AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,label_schema_hash}','')~'^[0-9a-f]{64}$' AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,training_rows}') IS NOT DISTINCT FROM 'number' AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,training_rows}','')~'^[1-9][0-9]{0,9}$' AND (receipt_projection#>>'{result_observation,actual_inputs,training_rows}')::NUMERIC BETWEEN 1 AND 2147483647 AND jsonb_typeof(receipt_projection#>'{result_observation,model}')='object' AND receipt_projection#>'{result_observation,model}'?&ARRAY['model_schema_version','metrics_hash','resource_usage_hash']::TEXT[] AND (receipt_projection#>'{result_observation,model}')-ARRAY['model_schema_version','metrics_hash','resource_usage_hash']::TEXT[]='{}'::JSONB AND jsonb_typeof(receipt_projection#>'{result_observation,model,model_schema_version}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{result_observation,model,metrics_hash}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{result_observation,model,resource_usage_hash}') IS NOT DISTINCT FROM 'string' AND COALESCE(receipt_projection#>>'{result_observation,model,model_schema_version}','')~'^[a-z0-9][a-z0-9_.-]{0,127}$' AND COALESCE(receipt_projection#>>'{result_observation,model,metrics_hash}','')~'^[0-9a-f]{64}$' AND COALESCE(receipt_projection#>>'{result_observation,model,resource_usage_hash}','')~'^[0-9a-f]{64}$' AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts}')='object' AND receipt_projection#>'{result_observation,artifacts}'?&ARRAY['q10','q50','q90']::TEXT[] AND (receipt_projection#>'{result_observation,artifacts}')-ARRAY['q10','q50','q90']::TEXT[]='{}'::JSONB AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q10}')='object' AND receipt_projection#>'{result_observation,artifacts,q10}'?&ARRAY['artifact_hash','artifact_size_bytes']::TEXT[] AND (receipt_projection#>'{result_observation,artifacts,q10}')-ARRAY['artifact_hash','artifact_size_bytes']::TEXT[]='{}'::JSONB AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q10,artifact_hash}') IS NOT DISTINCT FROM 'string' AND COALESCE(receipt_projection#>>'{result_observation,artifacts,q10,artifact_hash}','')~'^[0-9a-f]{64}$' AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q10,artifact_size_bytes}') IS NOT DISTINCT FROM 'number' AND COALESCE(receipt_projection#>>'{result_observation,artifacts,q10,artifact_size_bytes}','')~'^[1-9][0-9]{0,18}$' AND (receipt_projection#>>'{result_observation,artifacts,q10,artifact_size_bytes}')::NUMERIC BETWEEN 1 AND 9223372036854775807 AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q50}')='object' AND receipt_projection#>'{result_observation,artifacts,q50}'?&ARRAY['artifact_hash','artifact_size_bytes']::TEXT[] AND (receipt_projection#>'{result_observation,artifacts,q50}')-ARRAY['artifact_hash','artifact_size_bytes']::TEXT[]='{}'::JSONB AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q50,artifact_hash}') IS NOT DISTINCT FROM 'string' AND COALESCE(receipt_projection#>>'{result_observation,artifacts,q50,artifact_hash}','')~'^[0-9a-f]{64}$' AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q50,artifact_size_bytes}') IS NOT DISTINCT FROM 'number' AND COALESCE(receipt_projection#>>'{result_observation,artifacts,q50,artifact_size_bytes}','')~'^[1-9][0-9]{0,18}$' AND (receipt_projection#>>'{result_observation,artifacts,q50,artifact_size_bytes}')::NUMERIC BETWEEN 1 AND 9223372036854775807 AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q90}')='object' AND receipt_projection#>'{result_observation,artifacts,q90}'?&ARRAY['artifact_hash','artifact_size_bytes']::TEXT[] AND (receipt_projection#>'{result_observation,artifacts,q90}')-ARRAY['artifact_hash','artifact_size_bytes']::TEXT[]='{}'::JSONB AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q90,artifact_hash}') IS NOT DISTINCT FROM 'string' AND COALESCE(receipt_projection#>>'{result_observation,artifacts,q90,artifact_hash}','')~'^[0-9a-f]{64}$' AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q90,artifact_size_bytes}') IS NOT DISTINCT FROM 'number' AND COALESCE(receipt_projection#>>'{result_observation,artifacts,q90,artifact_size_bytes}','')~'^[1-9][0-9]{0,18}$' AND (receipt_projection#>>'{result_observation,artifacts,q90,artifact_size_bytes}')::NUMERIC BETWEEN 1 AND 9223372036854775807 AND receipt_projection#>>'{result_observation,artifacts,q10,artifact_hash}'<>receipt_projection#>>'{result_observation,artifacts,q50,artifact_hash}' AND receipt_projection#>>'{result_observation,artifacts,q10,artifact_hash}'<>receipt_projection#>>'{result_observation,artifacts,q90,artifact_hash}' AND receipt_projection#>>'{result_observation,artifacts,q50,artifact_hash}'<>receipt_projection#>>'{result_observation,artifacts,q90,artifact_hash}' AND encode(public.digest(convert_to(format(E'q10=%s\nq50=%s\nq90=%s\n',receipt_projection#>>'{result_observation,artifacts,q10,artifact_hash}',receipt_projection#>>'{result_observation,artifacts,q50,artifact_hash}',receipt_projection#>>'{result_observation,artifacts,q90,artifact_hash}'),'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT)=ordered_artifact_set_hash AND jsonb_typeof(receipt_projection->'authentication')='object' AND receipt_projection->'authentication'?&ARRAY['issuer_id','trust_policy_id','signature_key_id','signature_algorithm','signature']::TEXT[] AND (receipt_projection->'authentication')-ARRAY['issuer_id','trust_policy_id','signature_key_id','signature_algorithm','signature']::TEXT[]='{}'::JSONB AND receipt_projection#>>'{authentication,issuer_id}' IS NOT DISTINCT FROM issuer_id AND receipt_projection#>>'{authentication,trust_policy_id}' IS NOT DISTINCT FROM trust_policy_id AND receipt_projection#>>'{authentication,signature_key_id}' IS NOT DISTINCT FROM signature_key_id AND receipt_projection#>>'{authentication,signature_algorithm}' IS NOT DISTINCT FROM signature_algorithm AND jsonb_typeof(receipt_projection#>'{authentication,issuer_id}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{authentication,trust_policy_id}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{authentication,signature_key_id}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{authentication,signature_algorithm}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection#>'{authentication,signature}') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection->'verified_at') IS NOT DISTINCT FROM 'string' AND jsonb_typeof(receipt_projection->'expires_at') IS NOT DISTINCT FROM 'string' AND receipt_projection->>'verified_at'=to_char(verified_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AND receipt_projection->>'expires_at'=to_char(expires_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AND (receipt_projection#>>'{result_observation,fit_started_at}')::TIMESTAMPTZ<=(receipt_projection#>>'{result_observation,fit_completed_at}')::TIMESTAMPTZ AND (receipt_projection#>>'{result_observation,fit_completed_at}')::TIMESTAMPTZ<=verified_at AND COALESCE(receipt_projection#>>'{authentication,signature}','')~'^[A-Za-z0-9_-]{43,512}={0,2}$')$ddl$;
    END IF;
    FOR v_spec IN SELECT * FROM (VALUES
      ('learning.alr_qualified_training_receipts','pg_temp.alr_v159_expected_receipts',10,TRUE),('learning.alr_challenger_training_runs','pg_temp.alr_v159_expected_runs',CASE WHEN p_mode='legacy' THEN 11 ELSE 18 END,TRUE),('learning.alr_challenger_model_artifacts','pg_temp.alr_v159_expected_artifacts',CASE WHEN p_mode='legacy' THEN 5 ELSE 7 END,TRUE),('learning.alr_challenger_registry','pg_temp.alr_v159_expected_registry',CASE WHEN p_mode='legacy' THEN 7 ELSE 10 END,TRUE),('learning.alr_challenger_fit_attestations','pg_temp.alr_v159_expected_attestations',17,p_mode<>'legacy')
    ) AS x(relation_name,expected_relation,constraint_count,required) LOOP
        IF NOT v_spec.required THEN CONTINUE; END IF; v_expected_rel:=v_spec.expected_relation::regclass;
        SELECT count(*) INTO v_count FROM pg_constraint c WHERE c.conrelid=v_spec.relation_name::regclass AND c.contype IN('p','u','f','c');
        IF v_count<>v_spec.constraint_count OR (SELECT count(*) FROM pg_constraint WHERE conrelid=v_spec.relation_name::regclass AND contype='c')<>(SELECT count(*) FROM pg_constraint WHERE conrelid=v_expected_rel AND contype='c') THEN RAISE EXCEPTION 'V159 catalog FAIL: constraint set/count: %',v_spec.relation_name; END IF;
        FOR v_actual IN SELECT conname FROM pg_constraint WHERE conrelid=v_expected_rel AND contype='c' LOOP
            SELECT pg_get_expr(a.conbin,a.conrelid,FALSE) actual_expr,pg_get_expr(e.conbin,e.conrelid,FALSE) expected_expr INTO v_expr FROM pg_constraint a JOIN pg_constraint e ON e.conrelid=v_expected_rel AND e.conname=v_actual.conname WHERE a.conrelid=v_spec.relation_name::regclass AND a.conname=v_actual.conname AND a.contype='c' AND a.convalidated AND NOT a.connoinherit AND a.conislocal AND a.coninhcount=0 AND a.conparentid=0 AND NOT a.condeferrable AND NOT a.condeferred;
            IF NOT FOUND OR v_expr.actual_expr IS DISTINCT FROM v_expr.expected_expr THEN RAISE EXCEPTION 'V159 catalog FAIL: exact CHECK: %.%',v_spec.relation_name,v_actual.conname; END IF;
        END LOOP;
    END LOOP;

    FOR v_spec IN SELECT * FROM (VALUES
      ('both','alr_qualified_receipts_pk','learning.alr_qualified_training_receipts','p','durable_receipt_hash',NULL::TEXT,NULL::TEXT),('both','alr_qualified_receipts_training_key_uniq','learning.alr_qualified_training_receipts','u','training_key_hash',NULL,NULL),('both','alr_qualified_receipts_receipt_training_uniq','learning.alr_qualified_training_receipts','u','durable_receipt_hash,training_key_hash',NULL,NULL),('both','alr_qualified_receipts_source_training_uniq','learning.alr_qualified_training_receipts','u','source_receipt_hash,training_key_hash',NULL,NULL),('both','alr_qualified_receipts_projection_fk','learning.alr_qualified_training_receipts','f','projection_artifact_hash','learning.alr_artifact_nodes','artifact_hash'),
      ('both','alr_challenger_runs_pk','learning.alr_challenger_training_runs','p','training_run_hash',NULL,NULL),('both','alr_challenger_runs_training_key_uniq','learning.alr_challenger_training_runs','u','training_key_hash',NULL,NULL),('both','alr_challenger_runs_result_lineage_uniq','learning.alr_challenger_training_runs','u','training_run_hash,training_key_hash,model_artifact_set_hash',NULL,NULL),('both','alr_challenger_runs_artifact_lineage_uniq','learning.alr_challenger_training_runs','u','training_run_hash,training_key_hash,model_artifact_set_hash,actual_feature_schema_hash,model_schema_version',NULL,NULL),('both','alr_challenger_runs_receipt_training_fk','learning.alr_challenger_training_runs','f','durable_receipt_hash,training_key_hash','learning.alr_qualified_training_receipts','durable_receipt_hash,training_key_hash'),
      ('both','alr_challenger_artifacts_pk','learning.alr_challenger_model_artifacts','p','artifact_hash',NULL,NULL),('both','alr_challenger_artifacts_run_quantile_uniq','learning.alr_challenger_model_artifacts','u','training_run_hash,quantile',NULL,NULL),('both','alr_challenger_artifacts_run_lineage_fk','learning.alr_challenger_model_artifacts','f','training_run_hash,training_key_hash,model_artifact_set_hash,feature_schema_hash,model_schema_version','learning.alr_challenger_training_runs','training_run_hash,training_key_hash,model_artifact_set_hash,actual_feature_schema_hash,model_schema_version'),
      ('both','alr_challenger_registry_pk','learning.alr_challenger_registry','p','challenger_hash',NULL,NULL),('both','alr_challenger_registry_run_uniq','learning.alr_challenger_registry','u','training_run_hash',NULL,NULL),('both','alr_challenger_registry_training_key_uniq','learning.alr_challenger_registry','u','training_key_hash',NULL,NULL),('both','alr_challenger_registry_run_lineage_fk','learning.alr_challenger_registry','f','training_run_hash,training_key_hash,model_artifact_set_hash','learning.alr_challenger_training_runs','training_run_hash,training_key_hash,model_artifact_set_hash'),
      ('final','alr_fit_attestations_pk','learning.alr_challenger_fit_attestations','p','durable_attestation_hash',NULL,NULL),('final','alr_fit_attestations_receipt_digest_uniq','learning.alr_challenger_fit_attestations','u','external_receipt_digest',NULL,NULL),('final','alr_fit_attestations_receipt_training_uniq','learning.alr_challenger_fit_attestations','u','durable_receipt_hash,training_key_hash',NULL,NULL),('final','alr_fit_attestations_structural_result_uniq','learning.alr_challenger_fit_attestations','u','structural_result_hash',NULL,NULL),('final','alr_fit_attestations_structural_fit_capture_uniq','learning.alr_challenger_fit_attestations','u','structural_fit_capture_hash',NULL,NULL),('final','alr_fit_attestations_structural_candidate_uniq','learning.alr_challenger_fit_attestations','u','structural_candidate_hash',NULL,NULL),('final','alr_fit_attestations_structural_training_run_uniq','learning.alr_challenger_fit_attestations','u','structural_training_run_hash',NULL,NULL),('final','alr_fit_attestations_structural_challenger_uniq','learning.alr_challenger_fit_attestations','u','structural_challenger_hash',NULL,NULL),('final','alr_fit_attestations_ordered_artifact_set_uniq','learning.alr_challenger_fit_attestations','u','ordered_artifact_set_hash',NULL,NULL),('final','alr_fit_attestations_lineage_uniq','learning.alr_challenger_fit_attestations','u','durable_attestation_hash,durable_receipt_hash,training_key_hash,structural_training_run_hash,ordered_artifact_set_hash',NULL,NULL),('final','alr_fit_attestations_qualified_receipt_fk','learning.alr_challenger_fit_attestations','f','durable_receipt_hash,training_key_hash','learning.alr_qualified_training_receipts','durable_receipt_hash,training_key_hash'),
      ('final','alr_challenger_runs_v159_attestation_fk','learning.alr_challenger_training_runs','f','durable_attestation_hash,durable_receipt_hash,training_key_hash,training_run_hash,model_artifact_set_hash','learning.alr_challenger_fit_attestations','durable_attestation_hash,durable_receipt_hash,training_key_hash,structural_training_run_hash,ordered_artifact_set_hash'),('final','alr_challenger_runs_v159_attestation_uniq','learning.alr_challenger_training_runs','u','durable_attestation_hash',NULL,NULL),('final','alr_challenger_runs_v159_durable_run_uniq','learning.alr_challenger_training_runs','u','durable_training_run_hash',NULL,NULL),('final','alr_challenger_runs_v159_artifact_lineage_uniq','learning.alr_challenger_training_runs','u','training_run_hash,durable_training_run_hash,durable_attestation_hash,training_key_hash,model_artifact_set_hash,actual_feature_schema_hash,model_schema_version',NULL,NULL),('final','alr_challenger_runs_v159_registry_lineage_uniq','learning.alr_challenger_training_runs','u','training_run_hash,durable_training_run_hash,durable_attestation_hash,training_key_hash,model_artifact_set_hash',NULL,NULL),
      ('final','alr_challenger_artifacts_v159_lineage_fk','learning.alr_challenger_model_artifacts','f','training_run_hash,durable_training_run_hash,durable_attestation_hash,training_key_hash,model_artifact_set_hash,feature_schema_hash,model_schema_version','learning.alr_challenger_training_runs','training_run_hash,durable_training_run_hash,durable_attestation_hash,training_key_hash,model_artifact_set_hash,actual_feature_schema_hash,model_schema_version'),('final','alr_challenger_registry_v159_lineage_fk','learning.alr_challenger_registry','f','training_run_hash,durable_training_run_hash,durable_attestation_hash,training_key_hash,model_artifact_set_hash','learning.alr_challenger_training_runs','training_run_hash,durable_training_run_hash,durable_attestation_hash,training_key_hash,model_artifact_set_hash'),('final','alr_challenger_registry_v159_durable_challenger_uniq','learning.alr_challenger_registry','u','durable_challenger_hash',NULL,NULL)
    ) AS x(state,name,relation_name,constraint_type,key_columns,foreign_relation,foreign_columns) WHERE state='both' OR p_mode<>'legacy' LOOP
        SELECT c.oid,c.contype,c.conindid,c.confrelid,c.conkey,c.confkey,(SELECT string_agg(a.attname,',' ORDER BY k.ordinality) FROM unnest(c.conkey) WITH ORDINALITY k(attnum,ordinality) JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.attnum) key_columns,CASE WHEN c.confrelid=0 THEN NULL ELSE c.confrelid::regclass::TEXT END foreign_relation,(SELECT string_agg(a.attname,',' ORDER BY k.ordinality) FROM unnest(c.confkey) WITH ORDINALITY k(attnum,ordinality) JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.attnum) foreign_columns INTO v_actual FROM pg_constraint c WHERE c.conrelid=v_spec.relation_name::regclass AND c.conname=v_spec.name AND c.contype=v_spec.constraint_type::"char" AND c.convalidated AND c.connoinherit AND c.conislocal AND c.coninhcount=0 AND c.conparentid=0 AND NOT c.condeferrable AND NOT c.condeferred AND ((c.contype='f' AND c.confupdtype='a' AND c.confdeltype='a' AND c.confmatchtype='s') OR c.contype IN('p','u'));
        IF NOT FOUND OR v_actual.key_columns IS DISTINCT FROM v_spec.key_columns OR v_actual.foreign_relation IS DISTINCT FROM v_spec.foreign_relation OR v_actual.foreign_columns IS DISTINCT FROM v_spec.foreign_columns THEN RAISE EXCEPTION 'V159 catalog FAIL: key/FK manifest: %',v_spec.name; END IF;
        IF v_spec.constraint_type IN('p','u') AND NOT EXISTS(SELECT 1 FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid JOIN pg_am am ON am.oid=ic.relam JOIN pg_constraint c ON c.oid=v_actual.oid WHERE i.indexrelid=v_actual.conindid AND ic.relname=v_spec.name AND ic.relowner=v_schema_owner AND ic.relkind='i' AND ic.relpersistence='p' AND ic.reloptions IS NULL AND ic.reltablespace=0 AND am.amname='btree' AND i.indisunique AND i.indisprimary=(v_spec.constraint_type='p') AND NOT i.indisexclusion AND i.indimmediate AND i.indisvalid AND i.indisready AND i.indislive AND NOT i.indisclustered AND NOT i.indisreplident AND NOT i.indcheckxmin AND NOT i.indnullsnotdistinct AND i.indnkeyatts=i.indnatts AND i.indexprs IS NULL AND i.indpred IS NULL AND ARRAY(SELECT k FROM unnest(i.indkey) WITH ORDINALITY x(k,o) ORDER BY o)=c.conkey AND ARRAY(SELECT k FROM unnest(i.indclass) WITH ORDINALITY x(k,o) ORDER BY o)=ARRAY(SELECT opc.oid FROM unnest(c.conkey) WITH ORDINALITY x(attnum,o) JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=x.attnum JOIN pg_opclass opc ON opc.opcmethod=ic.relam AND opc.opcintype=a.atttypid AND opc.opcdefault ORDER BY o) AND ARRAY(SELECT k FROM unnest(i.indcollation) WITH ORDINALITY x(k,o) ORDER BY o)=ARRAY(SELECT a.attcollation FROM unnest(c.conkey) WITH ORDINALITY x(attnum,o) JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=x.attnum ORDER BY o) AND ARRAY(SELECT k FROM unnest(i.indoption) WITH ORDINALITY x(k,o) ORDER BY o)=array_fill(0::SMALLINT,ARRAY[cardinality(c.conkey)])) THEN RAISE EXCEPTION 'V159 catalog FAIL: exact index: %',v_spec.name; END IF;
    END LOOP;
    SELECT count(*) INTO v_count FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='learning' AND (c.relname IN('alr_qualified_training_receipts','alr_challenger_training_runs','alr_challenger_model_artifacts','alr_challenger_registry') OR (p_mode<>'legacy' AND c.relname='alr_challenger_fit_attestations'));
    IF v_count<>(CASE WHEN p_mode='legacy' THEN 13 ELSE 28 END) THEN RAISE EXCEPTION 'V159 catalog FAIL: extra/missing index %',v_count; END IF;

    SELECT count(*) INTO v_count FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='learning' AND NOT t.tgisinternal AND (c.relname IN('alr_qualified_training_receipts','alr_challenger_training_runs','alr_challenger_model_artifacts','alr_challenger_registry') OR (p_mode<>'legacy' AND c.relname='alr_challenger_fit_attestations'));
    IF v_count<>(CASE WHEN p_mode='legacy' THEN 7 ELSE 11 END) THEN RAISE EXCEPTION 'V159 catalog FAIL: trigger count %',v_count; END IF;
    FOR v_spec IN SELECT * FROM (VALUES
      ('both','alr_challenger_run_complete_ct_v1','learning.alr_challenger_training_runs','learning.alr_v158_assert_complete_result()',29,TRUE),('both','alr_challenger_artifact_complete_ct_v1','learning.alr_challenger_model_artifacts','learning.alr_v158_assert_complete_result()',29,TRUE),('both','alr_challenger_registry_complete_ct_v1','learning.alr_challenger_registry','learning.alr_v158_assert_complete_result()',29,TRUE),('both','alr_v158_immutable_alr_qualified_training_receipts_trg','learning.alr_qualified_training_receipts','learning.alr_v158_reject_mutation()',27,FALSE),('both','alr_v158_immutable_alr_challenger_training_runs_trg','learning.alr_challenger_training_runs','learning.alr_v158_reject_mutation()',27,FALSE),('both','alr_v158_immutable_alr_challenger_model_artifacts_trg','learning.alr_challenger_model_artifacts','learning.alr_v158_reject_mutation()',27,FALSE),('both','alr_v158_immutable_alr_challenger_registry_trg','learning.alr_challenger_registry','learning.alr_v158_reject_mutation()',27,FALSE),
      ('final','alr_v159_immutable_fit_attestations_trg','learning.alr_challenger_fit_attestations','learning.alr_v159_reject_attestation_mutation()',27,FALSE),('final','alr_v159_run_complete_ct_v1','learning.alr_challenger_training_runs','learning.alr_v159_assert_attested_bundle()',29,TRUE),('final','alr_v159_artifact_complete_ct_v1','learning.alr_challenger_model_artifacts','learning.alr_v159_assert_attested_bundle()',29,TRUE),('final','alr_v159_registry_complete_ct_v1','learning.alr_challenger_registry','learning.alr_v159_assert_attested_bundle()',29,TRUE)
    ) AS x(state,name,relation_name,function_name,trigger_type,constrained) WHERE state='both' OR p_mode<>'legacy' LOOP
        IF NOT EXISTS(SELECT 1 FROM pg_trigger t WHERE NOT t.tgisinternal AND t.tgname=v_spec.name AND t.tgrelid=v_spec.relation_name::regclass AND t.tgfoid=v_spec.function_name::regprocedure AND t.tgtype=v_spec.trigger_type AND t.tgenabled='O' AND t.tgnargs=0 AND t.tgqual IS NULL AND t.tgattr::TEXT='' AND t.tgdeferrable=v_spec.constrained AND t.tginitdeferred=v_spec.constrained AND (t.tgconstraint<>0)=v_spec.constrained AND t.tgparentid=0 AND t.tgoldtable IS NULL AND t.tgnewtable IS NULL AND (NOT v_spec.constrained OR EXISTS(SELECT 1 FROM pg_constraint c WHERE c.oid=t.tgconstraint AND c.conname=v_spec.name AND c.conrelid=t.tgrelid AND c.contype='t' AND c.convalidated AND c.conislocal AND c.coninhcount=0 AND c.conparentid=0 AND c.condeferrable AND c.condeferred))) THEN RAISE EXCEPTION 'V159 catalog FAIL: trigger manifest %',v_spec.name; END IF;
    END LOOP;

    SELECT count(*) INTO v_count FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='learning' AND p.proname IN('persist_alr_qualified_training_receipt_v1','persist_alr_challenger_training_result_v1','read_alr_qualified_training_receipt_v1','read_alr_challenger_training_result_v1','alr_v158_assert_complete_result','alr_v158_reject_mutation','persist_alr_challenger_fit_attestation_v1','persist_alr_challenger_training_result_v2','read_alr_challenger_training_result_v2','alr_v159_reject_attestation_mutation','alr_v159_assert_attested_bundle');
    IF v_count<>(CASE WHEN p_mode='legacy' THEN 6 ELSE 11 END) THEN RAISE EXCEPTION 'V159 catalog FAIL: function/overload count %',v_count; END IF;
    FOR v_spec IN SELECT * FROM (VALUES
      ('both','learning.persist_alr_qualified_training_receipt_v1(text,text,text,text,text,text,text,text,text,text,text,text,text,text,text,jsonb)','5edfac9aaf6b5e9e7d2ef492feb06f52','writer','trainer'),('both','learning.persist_alr_challenger_training_result_v1(text,text,text,text,text,text,text,text,text,text,text,text,integer,text,text,text,timestamp with time zone,timestamp with time zone,text,text,bigint,text,text,bigint,text,text,bigint,text)',NULL,'writer','legacy_trainer'),('both','learning.read_alr_qualified_training_receipt_v1(text,text)','0b5f006cc0cb84a970e057a01c408ea0','writer','trainer'),('both','learning.read_alr_challenger_training_result_v1(text,text)',NULL,'writer','legacy_trainer'),('both','learning.alr_v158_assert_complete_result()','4829c6065049859a85bf49ec6b47e1ec','writer',NULL),('both','learning.alr_v158_reject_mutation()','2258b2692fe7dfbbed3c1ec397b47617','writer',NULL),
      ('final','learning.persist_alr_challenger_fit_attestation_v1(bytea,jsonb,text,text,text,text,text,text,text,text,text,text,text,text,text,text,timestamp with time zone,timestamp with time zone)','5e6e564637a0c7fb62bd7853da662073','attestor','attestor_caller'),('final','learning.persist_alr_challenger_training_result_v2(text,text,text,text,text,text,text,text,text,text,integer,text,text,timestamp with time zone,timestamp with time zone,text,bigint,text,bigint,text,bigint)','fcdbf0ddf9c991d151f3bc7e7f91db6c','writer','trainer'),('final','learning.read_alr_challenger_training_result_v2(text,text)','dfb767fc22f251b4663d9b3d0a7b4347','writer','trainer'),('final','learning.alr_v159_reject_attestation_mutation()','c0fe988ce64bea1b1f92a1732b2ea09b','attestor',NULL),('final','learning.alr_v159_assert_attested_bundle()','35c0d60952f47797006601f4ddfa37ed','writer',NULL)
    ) AS x(state,identity,body_md5,owner_kind,caller_kind) WHERE state='both' OR p_mode<>'legacy' LOOP
        v_oid:=to_regprocedure(v_spec.identity); IF v_spec.identity='learning.persist_alr_challenger_training_result_v1(text,text,text,text,text,text,text,text,text,text,text,text,integer,text,text,text,timestamp with time zone,timestamp with time zone,text,text,bigint,text,text,bigint,text,text,bigint,text)' THEN v_spec.body_md5:=CASE WHEN p_mode='legacy' THEN '30b25e486b820477b4a9eeaf3d209e28' ELSE 'd4eafeccebddd383e4e5b9543ba21ccf' END; ELSIF v_spec.identity='learning.read_alr_challenger_training_result_v1(text,text)' THEN v_spec.body_md5:=CASE WHEN p_mode='legacy' THEN '7b199c1aa74c5258693a4c761586f96b' ELSE '71da623028a4ed44c78452b501b8daeb' END; END IF;
        IF v_oid IS NULL OR NOT EXISTS(SELECT 1 FROM pg_proc p WHERE p.oid=v_oid AND p.proowner=CASE v_spec.owner_kind WHEN 'writer' THEN v_writer ELSE v_attestor END AND p.prolang=(SELECT oid FROM pg_language WHERE lanname='plpgsql') AND p.prokind='f' AND p.prorettype=CASE WHEN v_spec.identity IN('learning.alr_v158_assert_complete_result()','learning.alr_v158_reject_mutation()','learning.alr_v159_reject_attestation_mutation()','learning.alr_v159_assert_attested_bundle()') THEN 'trigger'::regtype ELSE 'jsonb'::regtype END AND p.prosecdef AND p.proconfig IS NOT DISTINCT FROM ARRAY['search_path=pg_catalog, pg_temp']::TEXT[] AND p.provolatile='v' AND p.proparallel='u' AND NOT p.proleakproof AND NOT p.proisstrict AND p.pronargdefaults=0 AND p.provariadic=0 AND md5(p.prosrc)=v_spec.body_md5) OR EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) privilege WHERE p.oid=v_oid AND (privilege.grantor<>p.proowner OR privilege.is_grantable OR privilege.privilege_type<>'EXECUTE' OR privilege.grantee NOT IN(p.proowner,CASE v_spec.caller_kind WHEN 'trainer' THEN v_caller WHEN 'legacy_trainer' THEN CASE WHEN p_mode='legacy' THEN v_caller ELSE p.proowner END WHEN 'attestor_caller' THEN v_attestor_caller ELSE p.proowner END))) OR (SELECT count(*) FROM pg_proc p CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) privilege WHERE p.oid=v_oid)<>(CASE WHEN v_spec.caller_kind IN('trainer','attestor_caller') OR (v_spec.caller_kind='legacy_trainer' AND p_mode='legacy') THEN 2 ELSE 1 END) THEN RAISE EXCEPTION 'V159 catalog FAIL: function definition/ACL %',v_spec.identity; END IF;
    END LOOP;
    SELECT count(*) INTO v_writer_owned FROM pg_shdepend WHERE refclassid='pg_authid'::regclass AND refobjid=v_writer AND deptype='o'; SELECT count(*) INTO v_attestor_owned FROM pg_shdepend WHERE refclassid='pg_authid'::regclass AND refobjid=v_attestor AND deptype='o';
    IF v_writer_owned<>(CASE p_mode WHEN 'legacy' THEN 6 ELSE 9 END) OR v_attestor_owned<>(CASE p_mode WHEN 'legacy' THEN 0 ELSE 2 END) OR EXISTS(SELECT 1 FROM pg_shdepend d LEFT JOIN pg_proc p ON d.classid='pg_proc'::regclass AND p.oid=d.objid LEFT JOIN pg_namespace n ON n.oid=p.pronamespace WHERE d.refclassid='pg_authid'::regclass AND d.deptype='o' AND d.refobjid IN(v_writer,v_attestor) AND (d.dbid<>(SELECT oid FROM pg_database WHERE datname=current_database()) OR d.classid<>'pg_proc'::regclass OR n.nspname<>'learning' OR p.proowner<>d.refobjid OR p.proname NOT IN('persist_alr_qualified_training_receipt_v1','persist_alr_challenger_training_result_v1','read_alr_qualified_training_receipt_v1','read_alr_challenger_training_result_v1','alr_v158_assert_complete_result','alr_v158_reject_mutation','persist_alr_challenger_fit_attestation_v1','persist_alr_challenger_training_result_v2','read_alr_challenger_training_result_v2','alr_v159_reject_attestation_mutation','alr_v159_assert_attested_bundle'))) THEN RAISE EXCEPTION 'V159 catalog FAIL: function ownership inventory'; END IF;
    IF NOT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_depend d ON d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e' JOIN pg_extension e ON e.oid=d.refobjid AND e.extname='pgcrypto' JOIN pg_roles r ON r.oid=e.extowner WHERE p.oid='public.digest(bytea,text)'::regprocedure AND p.proowner=e.extowner AND r.rolsuper AND NOT EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.roleid=e.extowner) AND p.prorettype='bytea'::regtype AND p.proargtypes='17 25'::oidvector AND p.prolang=(SELECT oid FROM pg_language WHERE lanname='c') AND p.prosrc='pg_digest' AND p.probin='$libdir/pgcrypto' AND p.provolatile='i' AND p.proisstrict AND p.proparallel='s' AND NOT p.prosecdef AND NOT p.proleakproof AND p.proconfig IS NULL AND p.pronargdefaults=0 AND p.provariadic=0) OR NOT has_function_privilege('alr_challenger_writer','public.digest(bytea,text)'::regprocedure,'EXECUTE') OR (p_mode<>'legacy' AND NOT has_function_privilege('alr_challenger_fit_attestor','public.digest(bytea,text)'::regprocedure,'EXECUTE')) THEN RAISE EXCEPTION 'V159 catalog FAIL: trusted public.digest'; END IF;
    FOR v_spec IN SELECT * FROM (VALUES
      ('learning.alr_qualified_training_receipts',TRUE,TRUE,p_mode<>'legacy',FALSE,TRUE),('learning.alr_challenger_training_runs',TRUE,TRUE,FALSE,FALSE,TRUE),('learning.alr_challenger_model_artifacts',TRUE,TRUE,FALSE,FALSE,TRUE),('learning.alr_challenger_registry',TRUE,TRUE,FALSE,FALSE,TRUE),('learning.alr_challenger_fit_attestations',p_mode<>'legacy',FALSE,p_mode<>'legacy',p_mode<>'legacy',p_mode<>'legacy')
    ) AS x(relation_name,writer_select,writer_insert,attestor_select,attestor_insert,required) LOOP
        IF NOT v_spec.required THEN CONTINUE; END IF;
        IF EXISTS(SELECT 1 FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) privilege WHERE c.oid=v_spec.relation_name::regclass AND (NOT(privilege.grantor=v_schema_owner) OR privilege.is_grantable OR privilege.grantee NOT IN(v_schema_owner,v_writer,v_attestor) OR (privilege.grantee=v_schema_owner AND privilege.privilege_type NOT IN('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER')) OR (privilege.grantee=v_writer AND privilege.privilege_type NOT IN('SELECT',CASE WHEN v_spec.writer_insert THEN 'INSERT' ELSE 'SELECT' END)) OR (privilege.grantee=v_attestor AND privilege.privilege_type NOT IN(CASE WHEN v_spec.attestor_select THEN 'SELECT' ELSE 'NONE' END,CASE WHEN v_spec.attestor_insert THEN 'INSERT' ELSE 'NONE' END)))) OR (SELECT count(*) FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) privilege WHERE c.oid=v_spec.relation_name::regclass AND privilege.grantee=v_schema_owner)<>7 OR (SELECT count(*) FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) privilege WHERE c.oid=v_spec.relation_name::regclass AND privilege.grantee=v_writer)<>(CASE WHEN v_spec.writer_insert THEN 2 WHEN v_spec.writer_select THEN 1 ELSE 0 END) OR (SELECT count(*) FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) privilege WHERE c.oid=v_spec.relation_name::regclass AND privilege.grantee=v_attestor)<>(CASE WHEN v_spec.attestor_insert THEN 2 WHEN v_spec.attestor_select THEN 1 ELSE 0 END) THEN RAISE EXCEPTION 'V159 catalog FAIL: exact table ACL %',v_spec.relation_name; END IF;
        IF (v_spec.writer_select AND NOT has_table_privilege('alr_challenger_writer',v_spec.relation_name,'SELECT')) OR (v_spec.writer_insert AND NOT has_table_privilege('alr_challenger_writer',v_spec.relation_name,'INSERT')) OR has_table_privilege('alr_challenger_writer',v_spec.relation_name,'UPDATE') OR has_table_privilege('alr_challenger_writer',v_spec.relation_name,'DELETE') OR has_table_privilege('alr_challenger_writer',v_spec.relation_name,'TRUNCATE') OR has_table_privilege('alr_challenger_writer',v_spec.relation_name,'REFERENCES') OR has_table_privilege('alr_challenger_writer',v_spec.relation_name,'TRIGGER') OR (v_spec.attestor_select AND NOT has_table_privilege('alr_challenger_fit_attestor',v_spec.relation_name,'SELECT')) OR (v_spec.attestor_insert AND NOT has_table_privilege('alr_challenger_fit_attestor',v_spec.relation_name,'INSERT')) OR has_table_privilege('alr_challenger_trainer_caller',v_spec.relation_name,'SELECT') OR has_table_privilege('alr_challenger_trainer_caller',v_spec.relation_name,'INSERT') OR has_table_privilege('alr_challenger_fit_attestor_caller',v_spec.relation_name,'SELECT') OR has_table_privilege('alr_challenger_fit_attestor_caller',v_spec.relation_name,'INSERT') THEN RAISE EXCEPTION 'V159 catalog FAIL: effective table ACL %',v_spec.relation_name; END IF;
    END LOOP;
    IF NOT EXISTS(SELECT 1 FROM pg_class c WHERE c.oid='learning.alr_artifact_nodes'::regclass AND c.relowner=v_schema_owner AND c.relkind='r' AND c.relpersistence='p' AND c.relispartition IS FALSE AND c.relrowsecurity IS FALSE AND c.relforcerowsecurity IS FALSE AND c.relhasrules IS FALSE AND c.reloftype=0 AND c.relam=(SELECT oid FROM pg_am WHERE amname='heap')) OR EXISTS(SELECT 1 FROM pg_inherits WHERE inhrelid='learning.alr_artifact_nodes'::regclass OR inhparent='learning.alr_artifact_nodes'::regclass) OR EXISTS(SELECT 1 FROM pg_policy WHERE polrelid='learning.alr_artifact_nodes'::regclass) OR NOT has_table_privilege('alr_challenger_writer','learning.alr_artifact_nodes','SELECT') OR has_table_privilege('alr_challenger_writer','learning.alr_artifact_nodes','INSERT') OR has_table_privilege('alr_challenger_writer','learning.alr_artifact_nodes','UPDATE') OR has_table_privilege('alr_challenger_writer','learning.alr_artifact_nodes','DELETE') OR has_table_privilege('alr_challenger_writer','learning.alr_artifact_nodes','TRUNCATE') OR has_table_privilege('alr_challenger_writer','learning.alr_artifact_nodes','REFERENCES') OR has_table_privilege('alr_challenger_writer','learning.alr_artifact_nodes','TRIGGER') OR (SELECT count(*) FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) privilege WHERE c.oid='learning.alr_artifact_nodes'::regclass AND privilege.grantee=v_writer)<>1 OR EXISTS(SELECT 1 FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) privilege WHERE c.oid='learning.alr_artifact_nodes'::regclass AND privilege.grantee=v_writer AND (privilege.privilege_type<>'SELECT' OR privilege.grantor<>c.relowner OR privilege.is_grantable)) OR EXISTS(SELECT 1 FROM pg_attribute a CROSS JOIN LATERAL aclexplode(a.attacl) privilege WHERE a.attrelid='learning.alr_artifact_nodes'::regclass AND privilege.grantee=v_writer) THEN RAISE EXCEPTION 'V159 catalog FAIL: projection-read ACL/posture'; END IF;
    IF EXISTS(SELECT 1 FROM pg_attribute a WHERE a.attrelid IN(SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='learning' AND c.relname IN('alr_qualified_training_receipts','alr_challenger_training_runs','alr_challenger_model_artifacts','alr_challenger_registry','alr_challenger_fit_attestations')) AND a.attacl IS NOT NULL) OR EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.roleid IN(v_writer,v_caller,v_attestor,v_attestor_caller) OR m.member IN(v_writer,v_caller,v_attestor,v_attestor_caller)) THEN RAISE EXCEPTION 'V159 catalog FAIL: column ACL or role membership'; END IF;
    IF NOT has_schema_privilege('alr_challenger_writer','learning','USAGE') OR NOT has_schema_privilege('alr_challenger_trainer_caller','learning','USAGE') OR (p_mode<>'legacy' AND (NOT has_schema_privilege('alr_challenger_fit_attestor','learning','USAGE') OR NOT has_schema_privilege('alr_challenger_fit_attestor_caller','learning','USAGE'))) OR NOT has_schema_privilege('alr_challenger_writer','public','USAGE') OR (p_mode<>'legacy' AND NOT has_schema_privilege('alr_challenger_fit_attestor','public','USAGE')) OR has_schema_privilege('alr_challenger_writer','learning','CREATE') OR has_schema_privilege('alr_challenger_writer','public','CREATE') OR has_schema_privilege('alr_challenger_trainer_caller','learning','CREATE') OR has_schema_privilege('alr_challenger_trainer_caller','public','CREATE') OR has_schema_privilege('alr_challenger_fit_attestor','learning','CREATE') OR has_schema_privilege('alr_challenger_fit_attestor','public','CREATE') OR has_schema_privilege('alr_challenger_fit_attestor_caller','learning','CREATE') OR has_schema_privilege('alr_challenger_fit_attestor_caller','public','CREATE') OR NOT EXISTS(SELECT 1 FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) privilege WHERE n.nspname='public' AND privilege.grantee=v_writer AND privilege.privilege_type='USAGE' AND privilege.grantor=n.nspowner AND NOT privilege.is_grantable) OR (p_mode<>'legacy' AND NOT EXISTS(SELECT 1 FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) privilege WHERE n.nspname='public' AND privilege.grantee=v_attestor AND privilege.privilege_type='USAGE' AND privilege.grantor=n.nspowner AND NOT privilege.is_grantable)) THEN RAISE EXCEPTION 'V159 catalog FAIL: schema USAGE/CREATE posture'; END IF;
    IF EXISTS(SELECT 1 FROM pg_roles r WHERE NOT r.rolsuper AND has_schema_privilege(r.rolname,'learning','CREATE')) OR EXISTS(SELECT 1 FROM pg_namespace n CROSS JOIN LATERAL aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) privilege WHERE n.nspname='learning' AND privilege.grantee=0 AND privilege.privilege_type='CREATE') THEN RAISE EXCEPTION 'V159 catalog FAIL: generic learning CREATE reachability'; END IF;
    IF p_mode<>'legacy' THEN
        IF EXISTS(SELECT 1 FROM pg_roles generic WHERE NOT generic.rolsuper AND left(generic.rolname,3)<>'pg_' AND generic.oid NOT IN(v_writer,v_caller,v_attestor,v_attestor_caller) AND (has_table_privilege(generic.rolname,'learning.alr_challenger_fit_attestations','SELECT') OR has_table_privilege(generic.rolname,'learning.alr_challenger_fit_attestations','INSERT') OR has_table_privilege(generic.rolname,'learning.alr_challenger_training_runs','SELECT') OR has_table_privilege(generic.rolname,'learning.alr_challenger_model_artifacts','SELECT') OR has_table_privilege(generic.rolname,'learning.alr_challenger_registry','SELECT') OR has_function_privilege(generic.rolname,to_regprocedure('learning.persist_alr_challenger_fit_attestation_v1(bytea,jsonb,text,text,text,text,text,text,text,text,text,text,text,text,text,text,timestamp with time zone,timestamp with time zone)'),'EXECUTE') OR has_function_privilege(generic.rolname,to_regprocedure('learning.persist_alr_challenger_training_result_v2(text,text,text,text,text,text,text,text,text,text,integer,text,text,timestamp with time zone,timestamp with time zone,text,bigint,text,bigint,text,bigint)'),'EXECUTE') OR has_function_privilege(generic.rolname,to_regprocedure('learning.read_alr_challenger_training_result_v2(text,text)'),'EXECUTE'))) THEN RAISE EXCEPTION 'V159 catalog FAIL: generic role reachability'; END IF;
    END IF;
END
$v159_catalog_validator$;

-- Guard A accepts either the exact frozen V158 legacy shape or the exact
-- schema-only V159 replay shape.  Partial forward state always fails before
-- any normalizing DDL.
DO $v159_guard_a$
DECLARE
    v_schema_owner OID;
    v_old_writer pg_roles%ROWTYPE;
    v_old_caller pg_roles%ROWTYPE;
    v_attestor pg_roles%ROWTYPE;
    v_attestor_caller pg_roles%ROWTYPE;
    v_attestation_relation BOOLEAN;
    v_lineage_columns INTEGER;
    v_v159_constraints INTEGER;
    v_internal_functions INTEGER;
    v_internal_triggers INTEGER;
    v_public_functions INTEGER;
    v_exact_v159 BOOLEAN;
    v_columns TEXT[];
    v_expected TEXT[];
    v_object TEXT;
    v_spec RECORD;
    v_oid OID;
    v_count INTEGER;
BEGIN
    IF session_user <> current_user OR NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = current_user AND rolsuper IS TRUE
    ) THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: direct PostgreSQL superuser session required';
    END IF;

    SELECT n.nspowner INTO v_schema_owner
    FROM pg_namespace AS n
    WHERE n.nspname = 'learning';
    IF NOT FOUND OR pg_get_userbyid(v_schema_owner) <> current_user OR NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE oid = v_schema_owner AND rolsuper IS TRUE
    ) OR EXISTS (
        SELECT 1 FROM pg_auth_members WHERE roleid = v_schema_owner
    ) THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: learning schema trusted owner mismatch';
    END IF;
    IF to_regprocedure('public.digest(bytea,text)') IS NULL OR NOT EXISTS (
        SELECT 1
        FROM pg_proc AS p
        JOIN pg_depend AS d
          ON d.classid = 'pg_proc'::regclass
         AND d.objid = p.oid
         AND d.deptype = 'e'
        JOIN pg_extension AS e ON e.oid = d.refobjid
        WHERE p.oid = 'public.digest(bytea,text)'::regprocedure
          AND e.extname = 'pgcrypto'
    ) THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: exact pgcrypto digest(bytea,text) missing';
    END IF;

    SELECT * INTO v_old_writer FROM pg_roles
    WHERE rolname = 'alr_challenger_writer';
    IF NOT FOUND OR v_old_writer.rolcanlogin OR v_old_writer.rolsuper
       OR v_old_writer.rolcreatedb OR v_old_writer.rolcreaterole
       OR v_old_writer.rolinherit OR v_old_writer.rolreplication
       OR v_old_writer.rolbypassrls OR v_old_writer.rolconnlimit <> -1 THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: alr_challenger_writer posture mismatch';
    END IF;
    SELECT * INTO v_old_caller FROM pg_roles
    WHERE rolname = 'alr_challenger_trainer_caller';
    IF NOT FOUND OR NOT v_old_caller.rolcanlogin OR v_old_caller.rolsuper
       OR v_old_caller.rolcreatedb OR v_old_caller.rolcreaterole
       OR v_old_caller.rolinherit OR v_old_caller.rolreplication
       OR v_old_caller.rolbypassrls OR v_old_caller.rolconnlimit <> 1 THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: alr_challenger_trainer_caller posture mismatch';
    END IF;
    SELECT * INTO v_attestor FROM pg_roles
    WHERE rolname = 'alr_challenger_fit_attestor';
    IF NOT FOUND OR v_attestor.rolcanlogin OR v_attestor.rolsuper
       OR v_attestor.rolcreatedb OR v_attestor.rolcreaterole
       OR v_attestor.rolinherit OR v_attestor.rolreplication
       OR v_attestor.rolbypassrls OR v_attestor.rolconnlimit <> -1 THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: alr_challenger_fit_attestor posture mismatch';
    END IF;
    SELECT * INTO v_attestor_caller FROM pg_roles
    WHERE rolname = 'alr_challenger_fit_attestor_caller';
    IF NOT FOUND OR NOT v_attestor_caller.rolcanlogin
       OR v_attestor_caller.rolsuper OR v_attestor_caller.rolcreatedb
       OR v_attestor_caller.rolcreaterole OR v_attestor_caller.rolinherit
       OR v_attestor_caller.rolreplication OR v_attestor_caller.rolbypassrls
       OR v_attestor_caller.rolconnlimit <> 1 THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: alr_challenger_fit_attestor_caller posture mismatch';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM pg_auth_members AS membership
        WHERE membership.roleid IN (
            v_old_writer.oid, v_old_caller.oid,
            v_attestor.oid, v_attestor_caller.oid
        ) OR membership.member IN (
            v_old_writer.oid, v_old_caller.oid,
            v_attestor.oid, v_attestor_caller.oid
        )
    ) THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: challenger roles must be membership-free';
    END IF;
    FOREACH v_object IN ARRAY ARRAY[
        'alr_challenger_writer',
        'alr_challenger_trainer_caller',
        'alr_challenger_fit_attestor',
        'alr_challenger_fit_attestor_caller'
    ] LOOP
        IF has_parameter_privilege(
            v_object, 'session_replication_role', 'SET'
        ) OR EXISTS (
            SELECT 1
            FROM pg_parameter_acl AS parameter_acl
            CROSS JOIN LATERAL aclexplode(parameter_acl.paracl) AS privilege
            JOIN pg_roles AS grantee ON grantee.oid = privilege.grantee
            WHERE parameter_acl.parname = 'session_replication_role'
              AND grantee.rolname = v_object
              AND privilege.privilege_type = 'SET'
        ) THEN
            RAISE EXCEPTION
                'V159 Guard A FAIL: % may SET session_replication_role',
                v_object;
        END IF;
    END LOOP;

    -- The four V158 relations must be ordinary, permanent, trusted-owner
    -- tables without RLS, rules, inheritance, or unexpected table owners.
    FOREACH v_object IN ARRAY ARRAY[
        'learning.alr_qualified_training_receipts',
        'learning.alr_challenger_training_runs',
        'learning.alr_challenger_model_artifacts',
        'learning.alr_challenger_registry'
    ] LOOP
        IF to_regclass(v_object) IS NULL OR NOT EXISTS (
            SELECT 1 FROM pg_class AS c
            WHERE c.oid = v_object::regclass
              AND c.relkind = 'r'
              AND c.relpersistence = 'p'
              AND c.relowner = v_schema_owner
              AND NOT c.relispartition
              AND NOT c.relrowsecurity
              AND NOT c.relforcerowsecurity
              AND NOT c.relhasrules
        ) OR EXISTS (
            SELECT 1 FROM pg_inherits
            WHERE inhrelid = v_object::regclass
               OR inhparent = v_object::regclass
        ) OR EXISTS (
            SELECT 1 FROM pg_policy
            WHERE polrelid = v_object::regclass
        ) THEN
            RAISE EXCEPTION
                'V159 Guard A FAIL: V158 table posture mismatch: %', v_object;
        END IF;
    END LOOP;

    SELECT to_regclass('learning.alr_challenger_fit_attestations') IS NOT NULL
      INTO v_attestation_relation;
    SELECT count(*) INTO v_lineage_columns
    FROM pg_attribute AS a
    JOIN pg_class AS c ON c.oid = a.attrelid
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'learning'
      AND a.attnum > 0
      AND NOT a.attisdropped
      AND (
        (c.relname = 'alr_challenger_training_runs' AND a.attname IN (
            'durable_attestation_hash', 'durable_training_run_hash',
            'attestation_bound_at', 'attestation_verified_at',
            'attestation_expires_at'
        )) OR
        (c.relname = 'alr_challenger_model_artifacts' AND a.attname IN (
            'durable_attestation_hash', 'durable_training_run_hash'
        )) OR
        (c.relname = 'alr_challenger_registry' AND a.attname IN (
            'durable_attestation_hash', 'durable_training_run_hash',
            'durable_challenger_hash', 'attestation_bound_at'
        ))
      );
    SELECT count(*) INTO v_v159_constraints
    FROM pg_constraint
    WHERE conname IN (
        'alr_fit_attestations_pk',
        'alr_fit_attestations_receipt_digest_uniq',
        'alr_fit_attestations_receipt_training_uniq',
        'alr_fit_attestations_structural_result_uniq',
        'alr_fit_attestations_structural_fit_capture_uniq',
        'alr_fit_attestations_structural_candidate_uniq',
        'alr_fit_attestations_structural_training_run_uniq',
        'alr_fit_attestations_structural_challenger_uniq',
        'alr_fit_attestations_ordered_artifact_set_uniq',
        'alr_fit_attestations_lineage_uniq',
        'alr_fit_attestations_qualified_receipt_fk',
        'alr_fit_attestations_hashes_check',
        'alr_fit_attestations_signed_bytes_check',
        'alr_fit_attestations_evidence_check',
        'alr_fit_attestations_time_check',
        'alr_fit_attestations_no_authority_check',
        'alr_fit_attestations_counters_check',
        'alr_challenger_runs_v159_attestation_fk',
        'alr_challenger_runs_v159_attestation_uniq',
        'alr_challenger_runs_v159_durable_run_uniq',
        'alr_challenger_runs_v159_artifact_lineage_uniq',
        'alr_challenger_runs_v159_registry_lineage_uniq',
        'alr_challenger_runs_v159_hashes_check',
        'alr_challenger_runs_v159_time_check',
        'alr_challenger_artifacts_v159_lineage_fk',
        'alr_challenger_artifacts_v159_hashes_check',
        'alr_challenger_registry_v159_lineage_fk',
        'alr_challenger_registry_v159_durable_challenger_uniq',
        'alr_challenger_registry_v159_hashes_check'
    );
    IF (NOT v_attestation_relation AND v_lineage_columns = 0
        AND v_v159_constraints = 0) THEN
        v_exact_v159 := FALSE;
    ELSIF (v_attestation_relation AND v_lineage_columns = 11
           AND v_v159_constraints = 29) THEN
        v_exact_v159 := TRUE;
    ELSE
        RAISE EXCEPTION
            'V159 Guard A FAIL: partial V159 state table=% columns=% constraints=%',
            v_attestation_relation, v_lineage_columns, v_v159_constraints;
    END IF;

    SELECT count(*) INTO v_internal_functions
    FROM pg_proc AS p
    JOIN pg_namespace AS n ON n.oid=p.pronamespace
    WHERE n.nspname='learning' AND p.proname IN (
        'alr_v159_reject_attestation_mutation',
        'alr_v159_assert_attested_bundle'
    );
    SELECT count(*) INTO v_internal_triggers
    FROM pg_trigger AS t
    WHERE NOT t.tgisinternal AND t.tgname IN (
        'alr_v159_immutable_fit_attestations_trg',
        'alr_v159_run_complete_ct_v1',
        'alr_v159_artifact_complete_ct_v1',
        'alr_v159_registry_complete_ct_v1'
    );
    SELECT count(*) INTO v_public_functions
    FROM pg_proc AS p
    JOIN pg_namespace AS n ON n.oid=p.pronamespace
    WHERE n.nspname='learning' AND p.proname IN (
        'persist_alr_challenger_fit_attestation_v1',
        'persist_alr_challenger_training_result_v2',
        'read_alr_challenger_training_result_v2'
    );
    IF NOT v_exact_v159 AND (
        v_internal_functions<>0 OR v_internal_triggers<>0
        OR v_public_functions<>0
    ) THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: forward function/trigger state is nonempty';
    ELSIF v_exact_v159 AND (
        v_internal_functions<>2 OR v_internal_triggers<>4
        OR v_public_functions<>3
    ) THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: replay functions internal=% triggers=% public=%',
            v_internal_functions, v_internal_triggers, v_public_functions;
    END IF;

    IF v_exact_v159 THEN
        IF NOT EXISTS (
            WITH expected(attnum, attname, data_type, not_null, has_default) AS (
                VALUES
                  (1,'durable_attestation_hash','text',TRUE,FALSE),
                  (2,'external_receipt_digest','text',TRUE,FALSE),
                  (3,'signed_receipt_bytes','bytea',TRUE,FALSE),
                  (4,'receipt_projection','jsonb',TRUE,FALSE),
                  (5,'evidence_tier','text',TRUE,FALSE),
                  (6,'claim_kind','text',TRUE,FALSE),
                  (7,'authentication_status','text',TRUE,FALSE),
                  (8,'durable_receipt_hash','text',TRUE,FALSE),
                  (9,'training_key_hash','text',TRUE,FALSE),
                  (10,'structural_result_hash','text',TRUE,FALSE),
                  (11,'structural_fit_capture_hash','text',TRUE,FALSE),
                  (12,'structural_candidate_hash','text',TRUE,FALSE),
                  (13,'structural_training_run_hash','text',TRUE,FALSE),
                  (14,'structural_challenger_hash','text',TRUE,FALSE),
                  (15,'runner_identity_hash','text',TRUE,FALSE),
                  (16,'actual_input_material_set_hash','text',TRUE,FALSE),
                  (17,'ordered_artifact_set_hash','text',TRUE,FALSE),
                  (18,'issuer_id','text',TRUE,FALSE),
                  (19,'trust_policy_id','text',TRUE,FALSE),
                  (20,'signature_key_id','text',TRUE,FALSE),
                  (21,'signature_algorithm','text',TRUE,FALSE),
                  (22,'verified_at','timestamp with time zone',TRUE,FALSE),
                  (23,'expires_at','timestamp with time zone',TRUE,FALSE),
                  (24,'no_authority','jsonb',TRUE,FALSE),
                  (25,'authority_counters','jsonb',TRUE,FALSE),
                  (26,'created_at','timestamp with time zone',TRUE,TRUE)
            ), actual AS (
                SELECT a.attnum, a.attname,
                       format_type(a.atttypid,a.atttypmod) AS data_type,
                       a.attnotnull AS not_null, a.atthasdef AS has_default
                FROM pg_attribute AS a
                WHERE a.attrelid=
                    'learning.alr_challenger_fit_attestations'::regclass
                  AND a.attnum>0 AND NOT a.attisdropped
            )
            SELECT 1
            FROM expected AS e
            FULL JOIN actual AS a USING (attnum)
            GROUP BY TRUE
            HAVING count(*)=26
               AND bool_and(e.attname IS NOT DISTINCT FROM a.attname)
               AND bool_and(e.data_type IS NOT DISTINCT FROM a.data_type)
               AND bool_and(e.not_null IS NOT DISTINCT FROM a.not_null)
               AND bool_and(e.has_default IS NOT DISTINCT FROM a.has_default)
        ) OR NOT EXISTS (
            SELECT 1 FROM pg_class AS c
            WHERE c.oid='learning.alr_challenger_fit_attestations'::regclass
              AND c.relkind='r' AND c.relpersistence='p'
              AND c.relowner=v_schema_owner AND NOT c.relispartition
              AND NOT c.relrowsecurity AND NOT c.relforcerowsecurity
              AND NOT c.relhasrules
        ) THEN
            RAISE EXCEPTION
                'V159 Guard A FAIL: exact attestation relation map drift';
        END IF;

        FOR v_spec IN SELECT * FROM (VALUES
          ('alr_fit_attestations_pk','learning.alr_challenger_fit_attestations','p'),
          ('alr_fit_attestations_receipt_digest_uniq','learning.alr_challenger_fit_attestations','u'),
          ('alr_fit_attestations_receipt_training_uniq','learning.alr_challenger_fit_attestations','u'),
          ('alr_fit_attestations_structural_result_uniq','learning.alr_challenger_fit_attestations','u'),
          ('alr_fit_attestations_structural_fit_capture_uniq','learning.alr_challenger_fit_attestations','u'),
          ('alr_fit_attestations_structural_candidate_uniq','learning.alr_challenger_fit_attestations','u'),
          ('alr_fit_attestations_structural_training_run_uniq','learning.alr_challenger_fit_attestations','u'),
          ('alr_fit_attestations_structural_challenger_uniq','learning.alr_challenger_fit_attestations','u'),
          ('alr_fit_attestations_ordered_artifact_set_uniq','learning.alr_challenger_fit_attestations','u'),
          ('alr_fit_attestations_lineage_uniq','learning.alr_challenger_fit_attestations','u'),
          ('alr_fit_attestations_qualified_receipt_fk','learning.alr_challenger_fit_attestations','f'),
          ('alr_fit_attestations_hashes_check','learning.alr_challenger_fit_attestations','c'),
          ('alr_fit_attestations_signed_bytes_check','learning.alr_challenger_fit_attestations','c'),
          ('alr_fit_attestations_evidence_check','learning.alr_challenger_fit_attestations','c'),
          ('alr_fit_attestations_time_check','learning.alr_challenger_fit_attestations','c'),
          ('alr_fit_attestations_no_authority_check','learning.alr_challenger_fit_attestations','c'),
          ('alr_fit_attestations_counters_check','learning.alr_challenger_fit_attestations','c'),
          ('alr_challenger_runs_v159_attestation_fk','learning.alr_challenger_training_runs','f'),
          ('alr_challenger_runs_v159_attestation_uniq','learning.alr_challenger_training_runs','u'),
          ('alr_challenger_runs_v159_durable_run_uniq','learning.alr_challenger_training_runs','u'),
          ('alr_challenger_runs_v159_artifact_lineage_uniq','learning.alr_challenger_training_runs','u'),
          ('alr_challenger_runs_v159_registry_lineage_uniq','learning.alr_challenger_training_runs','u'),
          ('alr_challenger_runs_v159_hashes_check','learning.alr_challenger_training_runs','c'),
          ('alr_challenger_runs_v159_time_check','learning.alr_challenger_training_runs','c'),
          ('alr_challenger_artifacts_v159_lineage_fk','learning.alr_challenger_model_artifacts','f'),
          ('alr_challenger_artifacts_v159_hashes_check','learning.alr_challenger_model_artifacts','c'),
          ('alr_challenger_registry_v159_lineage_fk','learning.alr_challenger_registry','f'),
          ('alr_challenger_registry_v159_durable_challenger_uniq','learning.alr_challenger_registry','u'),
          ('alr_challenger_registry_v159_hashes_check','learning.alr_challenger_registry','c')
        ) AS x(name, relation_name, constraint_type) LOOP
            IF (SELECT count(*) FROM pg_constraint AS c
                WHERE c.conname=v_spec.name)<>1 OR NOT EXISTS (
                SELECT 1 FROM pg_constraint AS c
                WHERE c.conname=v_spec.name
                  AND c.conrelid=v_spec.relation_name::regclass
                  AND c.contype=v_spec.constraint_type::"char"
                  AND c.convalidated AND NOT c.condeferrable
            ) THEN
                RAISE EXCEPTION
                    'V159 Guard A FAIL: constraint placement drift: %',
                    v_spec.name;
            END IF;
        END LOOP;
    END IF;

    -- Exact ordered column inventories bite extra, missing, renamed, or
    -- reordered legacy state.  V159 columns are append-only and have no
    -- defaults, so exact replay has one deterministic extension per table.
    SELECT array_agg(a.attname ORDER BY a.attnum) INTO v_columns
    FROM pg_attribute AS a
    WHERE a.attrelid = 'learning.alr_qualified_training_receipts'::regclass
      AND a.attnum > 0 AND NOT a.attisdropped;
    v_expected := ARRAY[
        'durable_receipt_hash','source_receipt_hash','source_contract_hash',
        'projection_artifact_hash','selection_binding_hash','proof_input_hash',
        'proof_packet_hash','reward_set_hash','pit_dataset_manifest_hash',
        'after_cost_label_set_hash','evidence_set_hash','training_input_hash',
        'training_key_hash','code_manifest_hash','training_config_hash',
        'receipt_status','canonical_payload','no_authority',
        'authority_counters','created_at'
    ];
    IF v_columns IS DISTINCT FROM v_expected THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: V158 receipt column inventory drift';
    END IF;

    SELECT array_agg(a.attname ORDER BY a.attnum) INTO v_columns
    FROM pg_attribute AS a
    WHERE a.attrelid = 'learning.alr_challenger_training_runs'::regclass
      AND a.attnum > 0 AND NOT a.attisdropped;
    v_expected := ARRAY[
        'training_run_hash','durable_receipt_hash','training_key_hash',
        'source_head','actual_dataset_hash','actual_row_ids_hash',
        'actual_split_hash','actual_code_manifest_hash',
        'actual_training_config_hash','actual_feature_schema_hash',
        'actual_label_schema_hash','model_schema_version',
        'actual_training_rows','model_artifact_set_hash','metrics_hash',
        'resource_usage_hash','run_status','model_training_performed',
        'canonical_payload','no_authority','authority_counters',
        'fit_started_at','fit_completed_at','created_at'
    ];
    IF v_exact_v159 THEN
        v_expected := v_expected || ARRAY[
            'durable_attestation_hash','durable_training_run_hash',
            'attestation_bound_at','attestation_verified_at',
            'attestation_expires_at'
        ];
    END IF;
    IF v_columns IS DISTINCT FROM v_expected THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: challenger run column inventory drift';
    END IF;

    SELECT array_agg(a.attname ORDER BY a.attnum) INTO v_columns
    FROM pg_attribute AS a
    WHERE a.attrelid = 'learning.alr_challenger_model_artifacts'::regclass
      AND a.attnum > 0 AND NOT a.attisdropped;
    v_expected := ARRAY[
        'artifact_hash','training_run_hash','training_key_hash',
        'model_artifact_set_hash','quantile','artifact_format','artifact_path',
        'artifact_size_bytes','feature_schema_hash','model_schema_version',
        'symlink_created','serving_visible','created_at'
    ];
    IF v_exact_v159 THEN
        v_expected := v_expected || ARRAY[
            'durable_attestation_hash','durable_training_run_hash'
        ];
    END IF;
    IF v_columns IS DISTINCT FROM v_expected THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: challenger artifact column inventory drift';
    END IF;

    SELECT array_agg(a.attname ORDER BY a.attnum) INTO v_columns
    FROM pg_attribute AS a
    WHERE a.attrelid = 'learning.alr_challenger_registry'::regclass
      AND a.attnum > 0 AND NOT a.attisdropped;
    v_expected := ARRAY[
        'challenger_hash','training_run_hash','training_key_hash',
        'model_artifact_set_hash','registry_status','serving_allowed',
        'promotion_allowed','latest_pointer_allowed','symlink_allowed',
        'canonical_payload','created_at'
    ];
    IF v_exact_v159 THEN
        v_expected := v_expected || ARRAY[
            'durable_attestation_hash','durable_training_run_hash',
            'durable_challenger_hash','attestation_bound_at'
        ];
    END IF;
    IF v_columns IS DISTINCT FROM v_expected THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: challenger registry column inventory drift';
    END IF;

    IF v_exact_v159 AND EXISTS (
        SELECT 1 FROM pg_attribute AS a
        WHERE a.attrelid IN (
            'learning.alr_challenger_training_runs'::regclass,
            'learning.alr_challenger_model_artifacts'::regclass,
            'learning.alr_challenger_registry'::regclass
        ) AND a.attname IN (
            'durable_attestation_hash','durable_training_run_hash',
            'durable_challenger_hash','attestation_bound_at',
            'attestation_verified_at','attestation_expires_at'
        ) AND (NOT a.attnotnull OR a.atthasdef
               OR a.attgenerated <> '' OR a.attidentity <> '')
    ) THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: V159 lineage column null/default drift';
    END IF;

    -- Every V158 v1 overload and internal trigger helper is inventoried by
    -- exact identity and body.  Extra same-name overloads fail closed.
    SELECT count(*) INTO v_count
    FROM pg_proc AS p
    JOIN pg_namespace AS n ON n.oid = p.pronamespace
    WHERE n.nspname = 'learning' AND p.proname IN (
        'persist_alr_qualified_training_receipt_v1',
        'persist_alr_challenger_training_result_v1',
        'read_alr_qualified_training_receipt_v1',
        'read_alr_challenger_training_result_v1',
        'alr_v158_assert_complete_result',
        'alr_v158_reject_mutation'
    );
    IF v_count <> 6 THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: unexpected V158 function overload set: %/6',
            v_count;
    END IF;
    FOR v_spec IN SELECT * FROM (VALUES
        ('learning.persist_alr_qualified_training_receipt_v1(text,text,text,text,text,text,text,text,text,text,text,text,text,text,text,jsonb)', '5edfac9aaf6b5e9e7d2ef492feb06f52', NULL::TEXT, 'jsonb'),
        ('learning.persist_alr_challenger_training_result_v1(text,text,text,text,text,text,text,text,text,text,text,text,integer,text,text,text,timestamp with time zone,timestamp with time zone,text,text,bigint,text,text,bigint,text,text,bigint,text)', '30b25e486b820477b4a9eeaf3d209e28', 'd4eafeccebddd383e4e5b9543ba21ccf', 'jsonb'),
        ('learning.read_alr_qualified_training_receipt_v1(text,text)', '0b5f006cc0cb84a970e057a01c408ea0', NULL::TEXT, 'jsonb'),
        ('learning.read_alr_challenger_training_result_v1(text,text)', '7b199c1aa74c5258693a4c761586f96b', '71da623028a4ed44c78452b501b8daeb', 'jsonb'),
        ('learning.alr_v158_assert_complete_result()', '4829c6065049859a85bf49ec6b47e1ec', NULL::TEXT, 'trigger'),
        ('learning.alr_v158_reject_mutation()', '2258b2692fe7dfbbed3c1ec397b47617', NULL::TEXT, 'trigger')
    ) AS x(identity, legacy_body_md5, closed_body_md5, return_type) LOOP
        v_oid := to_regprocedure(v_spec.identity);
        IF v_oid IS NULL OR NOT EXISTS (
            SELECT 1 FROM pg_proc AS p
            WHERE p.oid = v_oid
              AND p.proowner = v_old_writer.oid
              AND p.prosecdef
              AND p.prolang = (SELECT oid FROM pg_language WHERE lanname='plpgsql')
              AND p.prorettype = v_spec.return_type::regtype
              AND p.proconfig IS NOT DISTINCT FROM
                  ARRAY['search_path=pg_catalog, pg_temp']::TEXT[]
              AND p.provolatile = 'v' AND p.proparallel = 'u'
              AND NOT p.proleakproof AND NOT p.proisstrict
              AND p.pronargdefaults = 0 AND p.provariadic = 0
              AND (
                  (v_spec.closed_body_md5 IS NULL
                   AND md5(p.prosrc)=v_spec.legacy_body_md5)
                  OR (v_spec.closed_body_md5 IS NOT NULL
                      AND v_public_functions=0
                      AND md5(p.prosrc)=v_spec.legacy_body_md5)
                  OR (v_spec.closed_body_md5 IS NOT NULL
                      AND v_public_functions=3
                      AND md5(p.prosrc)=v_spec.closed_body_md5)
              )
        ) THEN
            RAISE EXCEPTION
                'V159 Guard A FAIL: exact V158 function drift: %',
                v_spec.identity;
        END IF;
    END LOOP;

    IF v_exact_v159 THEN
        IF v_public_functions=3 THEN
            FOR v_spec IN SELECT * FROM (VALUES
              ('learning.persist_alr_challenger_fit_attestation_v1(bytea,jsonb,text,text,text,text,text,text,text,text,text,text,text,text,text,text,timestamp with time zone,timestamp with time zone)','5e6e564637a0c7fb62bd7853da662073','attestor','attestor_caller'),
              ('learning.persist_alr_challenger_training_result_v2(text,text,text,text,text,text,text,text,text,text,integer,text,text,timestamp with time zone,timestamp with time zone,text,bigint,text,bigint,text,bigint)','fcdbf0ddf9c991d151f3bc7e7f91db6c','writer','trainer_caller'),
              ('learning.read_alr_challenger_training_result_v2(text,text)','dfb767fc22f251b4663d9b3d0a7b4347','writer','trainer_caller')
            ) AS x(identity,body_md5,owner_kind,caller_kind) LOOP
                v_oid:=to_regprocedure(v_spec.identity);
                IF v_oid IS NULL OR NOT EXISTS(
                    SELECT 1 FROM pg_proc p WHERE p.oid=v_oid
                      AND p.proowner=CASE v_spec.owner_kind WHEN 'attestor' THEN v_attestor.oid ELSE v_old_writer.oid END
                      AND p.prosecdef AND p.prorettype='jsonb'::regtype
                      AND p.prolang=(SELECT oid FROM pg_language WHERE lanname='plpgsql')
                      AND p.proconfig IS NOT DISTINCT FROM ARRAY['search_path=pg_catalog, pg_temp']::TEXT[]
                      AND p.provolatile='v' AND p.proparallel='u' AND NOT p.proleakproof AND NOT p.proisstrict
                      AND p.pronargdefaults=0 AND p.provariadic=0 AND md5(p.prosrc)=v_spec.body_md5
                ) OR NOT has_function_privilege(CASE v_spec.caller_kind WHEN 'attestor_caller' THEN v_attestor_caller.rolname ELSE v_old_caller.rolname END,v_oid,'EXECUTE') OR EXISTS(
                    SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) privilege
                    WHERE p.oid=v_oid AND privilege.grantee NOT IN (p.proowner,CASE v_spec.caller_kind WHEN 'attestor_caller' THEN v_attestor_caller.oid ELSE v_old_caller.oid END)
                ) THEN RAISE EXCEPTION 'V159 Guard A FAIL: public function drift: %',v_spec.identity; END IF;
            END LOOP;
        END IF;
        FOR v_spec IN SELECT * FROM (VALUES
          ('learning.alr_v159_reject_attestation_mutation()','c0fe988ce64bea1b1f92a1732b2ea09b','attestor'),
          ('learning.alr_v159_assert_attested_bundle()','35c0d60952f47797006601f4ddfa37ed','writer')
        ) AS x(identity, body_md5, owner_kind) LOOP
            v_oid:=to_regprocedure(v_spec.identity);
            IF v_oid IS NULL OR NOT EXISTS (
                SELECT 1 FROM pg_proc AS p
                WHERE p.oid=v_oid AND p.proowner=CASE v_spec.owner_kind
                    WHEN 'attestor' THEN v_attestor.oid ELSE v_old_writer.oid END
                  AND p.prosecdef
                  AND p.prolang=(SELECT oid FROM pg_language WHERE lanname='plpgsql')
                  AND p.prorettype='trigger'::regtype
                  AND p.proconfig IS NOT DISTINCT FROM
                      ARRAY['search_path=pg_catalog, pg_temp']::TEXT[]
                  AND p.provolatile='v' AND p.proparallel='u'
                  AND NOT p.proleakproof AND NOT p.proisstrict
                  AND p.pronargs=0 AND p.pronargdefaults=0
                  AND p.provariadic=0 AND md5(p.prosrc)=v_spec.body_md5
            ) OR EXISTS (
                SELECT 1 FROM pg_proc AS p
                CROSS JOIN LATERAL aclexplode(
                    COALESCE(p.proacl,acldefault('f',p.proowner))
                ) AS privilege
                WHERE p.oid=v_oid AND privilege.grantee<>CASE v_spec.owner_kind
                    WHEN 'attestor' THEN v_attestor.oid ELSE v_old_writer.oid END
            ) THEN
                RAISE EXCEPTION
                    'V159 Guard A FAIL: internal function drift: %',
                    v_spec.identity;
            END IF;
        END LOOP;
        FOR v_spec IN SELECT * FROM (VALUES
          ('alr_v159_immutable_fit_attestations_trg','learning.alr_challenger_fit_attestations','learning.alr_v159_reject_attestation_mutation()',27,FALSE),
          ('alr_v159_run_complete_ct_v1','learning.alr_challenger_training_runs','learning.alr_v159_assert_attested_bundle()',29,TRUE),
          ('alr_v159_artifact_complete_ct_v1','learning.alr_challenger_model_artifacts','learning.alr_v159_assert_attested_bundle()',29,TRUE),
          ('alr_v159_registry_complete_ct_v1','learning.alr_challenger_registry','learning.alr_v159_assert_attested_bundle()',29,TRUE)
        ) AS x(name, relation_name, function_name, trigger_type, constrained) LOOP
            IF (SELECT count(*) FROM pg_trigger AS t
                WHERE t.tgname=v_spec.name AND NOT t.tgisinternal)<>1
               OR NOT EXISTS (
                SELECT 1 FROM pg_trigger AS t
                WHERE t.tgname=v_spec.name
                  AND t.tgrelid=v_spec.relation_name::regclass
                  AND t.tgfoid=v_spec.function_name::regprocedure
                  AND t.tgtype=v_spec.trigger_type
                  AND t.tgenabled='O' AND t.tgnargs=0
                  AND t.tgqual IS NULL AND t.tgattr::TEXT=''
                  AND t.tgdeferrable=v_spec.constrained
                  AND t.tginitdeferred=v_spec.constrained
                  AND (t.tgconstraint<>0)=v_spec.constrained
            ) THEN
                RAISE EXCEPTION
                    'V159 Guard A FAIL: internal trigger drift: %', v_spec.name;
            END IF;
        END LOOP;
    END IF;

    SELECT count(*) INTO v_count
    FROM pg_trigger AS t
    WHERE NOT t.tgisinternal AND t.tgname IN (
        'alr_challenger_run_complete_ct_v1',
        'alr_challenger_artifact_complete_ct_v1',
        'alr_challenger_registry_complete_ct_v1',
        'alr_v158_immutable_alr_qualified_training_receipts_trg',
        'alr_v158_immutable_alr_challenger_training_runs_trg',
        'alr_v158_immutable_alr_challenger_model_artifacts_trg',
        'alr_v158_immutable_alr_challenger_registry_trg'
    );
    IF v_count <> 7 THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: exact V158 trigger inventory drift: %/7',
            v_count;
    END IF;

    -- Legacy/replay constraint posture is distinguished by the structural
    -- path and zero-counter upgrades.  Any third expression is drift.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint AS c
        WHERE c.conrelid = 'learning.alr_challenger_model_artifacts'::regclass
          AND c.conname = 'alr_challenger_artifacts_shape_check'
          AND pg_get_constraintdef(c.oid, FALSE) LIKE CASE WHEN v_exact_v159
              THEN '%runs/structural/%'
              ELSE '%runs/%training_run_hash%'
          END
    ) THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: structural artifact path constraint drift';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint AS c
        WHERE c.conrelid = 'learning.alr_challenger_training_runs'::regclass
          AND c.conname = 'alr_challenger_runs_counters_check'
          AND pg_get_constraintdef(c.oid, FALSE) LIKE CASE WHEN v_exact_v159
              THEN '%"model_fit_count": 0%'
              ELSE '%"model_fit_count": 1%'
          END
    ) THEN
        RAISE EXCEPTION
            'V159 Guard A FAIL: run zero-counter constraint drift';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM pg_constraint c WHERE c.conrelid='learning.alr_challenger_training_runs'::regclass AND c.conname='alr_challenger_runs_payload_check' AND pg_get_constraintdef(c.oid,FALSE) LIKE CASE WHEN v_exact_v159 THEN '%alr_challenger_training_result_v2%' ELSE '%alr_challenger_training_result_v1%' END)
       OR NOT EXISTS(SELECT 1 FROM pg_constraint c WHERE c.conrelid='learning.alr_challenger_registry'::regclass AND c.conname='alr_challenger_registry_payload_check' AND pg_get_constraintdef(c.oid,FALSE) LIKE CASE WHEN v_exact_v159 THEN '%alr_challenger_registry_entry_v2%' ELSE '%alr_challenger_registry_entry_v1%' END) THEN
        IF v_exact_v159 THEN RAISE EXCEPTION 'V159 Guard A FAIL: v2 payload expression drift'; ELSE RAISE EXCEPTION 'V159 Guard A FAIL: legacy payload expression drift'; END IF;
    END IF;
    PERFORM pg_temp.alr_v159_assert_catalog(CASE WHEN v_exact_v159 THEN 'replay' ELSE 'legacy' END);
END
$v159_guard_a$;

-- Lock order is normative.  No count is inspected before all three tables
-- are held ACCESS EXCLUSIVE, so a concurrent V158 writer cannot race the
-- forward empty-table requirement.
LOCK TABLE learning.alr_challenger_training_runs
    IN ACCESS EXCLUSIVE MODE;
LOCK TABLE learning.alr_challenger_model_artifacts
    IN ACCESS EXCLUSIVE MODE;
LOCK TABLE learning.alr_challenger_registry
    IN ACCESS EXCLUSIVE MODE;

DO $v159_zero_rows$
BEGIN
    IF (SELECT count(*) FROM learning.alr_challenger_training_runs) <> 0 THEN
        RAISE EXCEPTION
            'V159 zero-row guard FAIL: challenger training runs are nonempty';
    END IF;
    IF (SELECT count(*) FROM learning.alr_challenger_model_artifacts) <> 0 THEN
        RAISE EXCEPTION
            'V159 zero-row guard FAIL: challenger artifacts are nonempty';
    END IF;
    IF (SELECT count(*) FROM learning.alr_challenger_registry) <> 0 THEN
        RAISE EXCEPTION
            'V159 zero-row guard FAIL: challenger registry is nonempty';
    END IF;
END
$v159_zero_rows$;

CREATE TABLE IF NOT EXISTS learning.alr_challenger_fit_attestations (
    durable_attestation_hash TEXT NOT NULL,
    external_receipt_digest TEXT NOT NULL,
    signed_receipt_bytes BYTEA NOT NULL,
    receipt_projection JSONB NOT NULL,
    evidence_tier TEXT NOT NULL,
    claim_kind TEXT NOT NULL,
    authentication_status TEXT NOT NULL,
    durable_receipt_hash TEXT NOT NULL,
    training_key_hash TEXT NOT NULL,
    structural_result_hash TEXT NOT NULL,
    structural_fit_capture_hash TEXT NOT NULL,
    structural_candidate_hash TEXT NOT NULL,
    structural_training_run_hash TEXT NOT NULL,
    structural_challenger_hash TEXT NOT NULL,
    runner_identity_hash TEXT NOT NULL,
    actual_input_material_set_hash TEXT NOT NULL,
    ordered_artifact_set_hash TEXT NOT NULL,
    issuer_id TEXT NOT NULL,
    trust_policy_id TEXT NOT NULL,
    signature_key_id TEXT NOT NULL,
    signature_algorithm TEXT NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    no_authority JSONB NOT NULL,
    authority_counters JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_fit_attestations_pk
        PRIMARY KEY (durable_attestation_hash) NOT DEFERRABLE,
    CONSTRAINT alr_fit_attestations_receipt_digest_uniq
        UNIQUE (external_receipt_digest) NOT DEFERRABLE,
    CONSTRAINT alr_fit_attestations_receipt_training_uniq
        UNIQUE (durable_receipt_hash, training_key_hash) NOT DEFERRABLE,
    CONSTRAINT alr_fit_attestations_structural_result_uniq
        UNIQUE (structural_result_hash) NOT DEFERRABLE,
    CONSTRAINT alr_fit_attestations_structural_fit_capture_uniq
        UNIQUE (structural_fit_capture_hash) NOT DEFERRABLE,
    CONSTRAINT alr_fit_attestations_structural_candidate_uniq
        UNIQUE (structural_candidate_hash) NOT DEFERRABLE,
    CONSTRAINT alr_fit_attestations_structural_training_run_uniq
        UNIQUE (structural_training_run_hash) NOT DEFERRABLE,
    CONSTRAINT alr_fit_attestations_structural_challenger_uniq
        UNIQUE (structural_challenger_hash) NOT DEFERRABLE,
    CONSTRAINT alr_fit_attestations_ordered_artifact_set_uniq
        UNIQUE (ordered_artifact_set_hash) NOT DEFERRABLE,
    CONSTRAINT alr_fit_attestations_lineage_uniq
        UNIQUE (
            durable_attestation_hash, durable_receipt_hash,
            training_key_hash, structural_training_run_hash,
            ordered_artifact_set_hash
        ) NOT DEFERRABLE,
    CONSTRAINT alr_fit_attestations_qualified_receipt_fk
        FOREIGN KEY (durable_receipt_hash, training_key_hash)
        REFERENCES learning.alr_qualified_training_receipts (
            durable_receipt_hash, training_key_hash
        ) NOT DEFERRABLE,
    CONSTRAINT alr_fit_attestations_hashes_check CHECK (
        durable_attestation_hash ~ '^[0-9a-f]{64}$'
        AND external_receipt_digest ~ '^[0-9a-f]{64}$'
        AND durable_receipt_hash ~ '^[0-9a-f]{64}$'
        AND training_key_hash ~ '^[0-9a-f]{64}$'
        AND structural_result_hash ~ '^[0-9a-f]{64}$'
        AND structural_fit_capture_hash ~ '^[0-9a-f]{64}$'
        AND structural_candidate_hash ~ '^[0-9a-f]{64}$'
        AND structural_training_run_hash ~ '^[0-9a-f]{64}$'
        AND structural_challenger_hash ~ '^[0-9a-f]{64}$'
        AND runner_identity_hash ~ '^[0-9a-f]{64}$'
        AND actual_input_material_set_hash ~ '^[0-9a-f]{64}$'
        AND ordered_artifact_set_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT alr_fit_attestations_signed_bytes_check CHECK (
        octet_length(signed_receipt_bytes) BETWEEN 2 AND 1048576
        AND external_receipt_digest = encode(
            public.digest(signed_receipt_bytes, 'sha256'::TEXT), 'hex'::TEXT
        )
        AND signed_receipt_bytes = convert_to(
            receipt_projection::TEXT, 'UTF8'::NAME
        )
    ),
    CONSTRAINT alr_fit_attestations_evidence_check CHECK (
        evidence_tier = 'PLATFORM_OR_EXTERNAL_ATTESTED'
        AND claim_kind = 'ALR_FIT_EXECUTION_ATTESTATION_V1'
        AND authentication_status = 'SIGNATURE_VERIFIED_BY_TRUST_POLICY'
        AND issuer_id ~ '^[a-z0-9][a-z0-9_.:-]{0,127}$'
        AND trust_policy_id ~ '^[a-z0-9][a-z0-9_.:-]{0,127}$'
        AND signature_key_id ~ '^[a-z0-9][a-z0-9_.:-]{0,127}$'
        AND signature_algorithm IN ('ed25519', 'ecdsa-p256-sha256')
        AND jsonb_typeof(receipt_projection) = 'object'
        AND receipt_projection ?& ARRAY[
            'schema_version','evidence_tier','claim_kind',
            'authentication_status','subject','claims','result_observation',
            'authentication','verified_at','expires_at','no_authority',
            'authority_counters'
        ]::TEXT[]
        AND receipt_projection - ARRAY[
            'schema_version','evidence_tier','claim_kind',
            'authentication_status','subject','claims','result_observation',
            'authentication','verified_at','expires_at','no_authority',
            'authority_counters'
        ]::TEXT[] = '{}'::JSONB
        AND receipt_projection->>'schema_version'
            IS NOT DISTINCT FROM 'alr_fit_execution_signed_receipt_v1'
        AND receipt_projection->>'evidence_tier'
            IS NOT DISTINCT FROM evidence_tier
        AND receipt_projection->>'claim_kind'
            IS NOT DISTINCT FROM claim_kind
        AND receipt_projection->>'authentication_status'
            IS NOT DISTINCT FROM authentication_status
        AND jsonb_typeof(receipt_projection->'schema_version') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection->'evidence_tier') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection->'claim_kind') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection->'authentication_status') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection->'subject') = 'object'
        AND receipt_projection->'subject' ?& ARRAY[
            'durable_receipt_hash','training_key_hash','result_hash',
            'fit_capture_hash','candidate_attestation_hash',
            'training_run_hash','challenger_hash','runner_identity_hash',
            'actual_input_material_set_hash','ordered_artifact_set_hash'
        ]::TEXT[]
        AND (receipt_projection->'subject') - ARRAY[
            'durable_receipt_hash','training_key_hash','result_hash',
            'fit_capture_hash','candidate_attestation_hash',
            'training_run_hash','challenger_hash','runner_identity_hash',
            'actual_input_material_set_hash','ordered_artifact_set_hash'
        ]::TEXT[] = '{}'::JSONB
        AND receipt_projection#>>'{subject,durable_receipt_hash}'
            IS NOT DISTINCT FROM durable_receipt_hash
        AND receipt_projection#>>'{subject,training_key_hash}'
            IS NOT DISTINCT FROM training_key_hash
        AND receipt_projection#>>'{subject,result_hash}'
            IS NOT DISTINCT FROM structural_result_hash
        AND receipt_projection#>>'{subject,fit_capture_hash}'
            IS NOT DISTINCT FROM structural_fit_capture_hash
        AND receipt_projection#>>'{subject,candidate_attestation_hash}'
            IS NOT DISTINCT FROM structural_candidate_hash
        AND receipt_projection#>>'{subject,training_run_hash}'
            IS NOT DISTINCT FROM structural_training_run_hash
        AND receipt_projection#>>'{subject,challenger_hash}'
            IS NOT DISTINCT FROM structural_challenger_hash
        AND receipt_projection#>>'{subject,runner_identity_hash}'
            IS NOT DISTINCT FROM runner_identity_hash
        AND receipt_projection#>>'{subject,actual_input_material_set_hash}'
            IS NOT DISTINCT FROM actual_input_material_set_hash
        AND receipt_projection#>>'{subject,ordered_artifact_set_hash}'
            IS NOT DISTINCT FROM ordered_artifact_set_hash
        AND jsonb_typeof(receipt_projection#>'{subject,durable_receipt_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{subject,training_key_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{subject,result_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{subject,fit_capture_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{subject,candidate_attestation_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{subject,training_run_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{subject,challenger_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{subject,runner_identity_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{subject,actual_input_material_set_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{subject,ordered_artifact_set_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection->'claims') = 'object'
        AND receipt_projection->'claims' ?& ARRAY[
            'actual_inputs_consumed','actual_fit_executed',
            'model_training_performed','artifact_readback_completed',
            'onnx_semantic_validation_passed'
        ]::TEXT[]
        AND (receipt_projection->'claims') - ARRAY[
            'actual_inputs_consumed','actual_fit_executed',
            'model_training_performed','artifact_readback_completed',
            'onnx_semantic_validation_passed'
        ]::TEXT[] = '{}'::JSONB
        AND receipt_projection#>'{claims,actual_inputs_consumed}' = 'true'::JSONB
        AND receipt_projection#>'{claims,actual_fit_executed}' = 'true'::JSONB
        AND receipt_projection#>'{claims,model_training_performed}' = 'true'::JSONB
        AND receipt_projection#>'{claims,artifact_readback_completed}' = 'true'::JSONB
        AND receipt_projection#>'{claims,onnx_semantic_validation_passed}' = 'true'::JSONB
        AND jsonb_typeof(receipt_projection->'result_observation')='object'
        AND receipt_projection->'result_observation' ?& ARRAY['source_head','actual_inputs','model','fit_started_at','fit_completed_at','artifacts']::TEXT[]
        AND (receipt_projection->'result_observation')-ARRAY['source_head','actual_inputs','model','fit_started_at','fit_completed_at','artifacts']::TEXT[]='{}'::JSONB
        AND jsonb_typeof(receipt_projection#>'{result_observation,source_head}') IS NOT DISTINCT FROM 'string'
        AND COALESCE(receipt_projection#>>'{result_observation,source_head}','')~'^[0-9a-f]{40}$'
        AND jsonb_typeof(receipt_projection#>'{result_observation,fit_started_at}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{result_observation,fit_completed_at}') IS NOT DISTINCT FROM 'string'
        AND COALESCE(receipt_projection#>>'{result_observation,fit_started_at}','')~'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$'
        AND COALESCE(receipt_projection#>>'{result_observation,fit_completed_at}','')~'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$'
        AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs}')='object'
        AND receipt_projection#>'{result_observation,actual_inputs}' ?& ARRAY['dataset_hash','row_ids_hash','split_hash','code_manifest_hash','training_config_hash','feature_schema_hash','label_schema_hash','training_rows']::TEXT[]
        AND (receipt_projection#>'{result_observation,actual_inputs}')-ARRAY['dataset_hash','row_ids_hash','split_hash','code_manifest_hash','training_config_hash','feature_schema_hash','label_schema_hash','training_rows']::TEXT[]='{}'::JSONB
        AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,dataset_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,row_ids_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,split_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,code_manifest_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,training_config_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,feature_schema_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,label_schema_hash}') IS NOT DISTINCT FROM 'string'
        AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,dataset_hash}','')~'^[0-9a-f]{64}$'
        AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,row_ids_hash}','')~'^[0-9a-f]{64}$'
        AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,split_hash}','')~'^[0-9a-f]{64}$'
        AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,code_manifest_hash}','')~'^[0-9a-f]{64}$'
        AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,training_config_hash}','')~'^[0-9a-f]{64}$'
        AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,feature_schema_hash}','')~'^[0-9a-f]{64}$'
        AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,label_schema_hash}','')~'^[0-9a-f]{64}$'
        AND jsonb_typeof(receipt_projection#>'{result_observation,actual_inputs,training_rows}') IS NOT DISTINCT FROM 'number'
        AND COALESCE(receipt_projection#>>'{result_observation,actual_inputs,training_rows}','')~'^[1-9][0-9]{0,9}$'
        AND (receipt_projection#>>'{result_observation,actual_inputs,training_rows}')::NUMERIC BETWEEN 1 AND 2147483647
        AND jsonb_typeof(receipt_projection#>'{result_observation,model}')='object'
        AND receipt_projection#>'{result_observation,model}' ?& ARRAY['model_schema_version','metrics_hash','resource_usage_hash']::TEXT[]
        AND (receipt_projection#>'{result_observation,model}')-ARRAY['model_schema_version','metrics_hash','resource_usage_hash']::TEXT[]='{}'::JSONB
        AND jsonb_typeof(receipt_projection#>'{result_observation,model,model_schema_version}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{result_observation,model,metrics_hash}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{result_observation,model,resource_usage_hash}') IS NOT DISTINCT FROM 'string'
        AND COALESCE(receipt_projection#>>'{result_observation,model,model_schema_version}','')~'^[a-z0-9][a-z0-9_.-]{0,127}$'
        AND COALESCE(receipt_projection#>>'{result_observation,model,metrics_hash}','')~'^[0-9a-f]{64}$'
        AND COALESCE(receipt_projection#>>'{result_observation,model,resource_usage_hash}','')~'^[0-9a-f]{64}$'
        AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts}')='object'
        AND receipt_projection#>'{result_observation,artifacts}' ?& ARRAY['q10','q50','q90']::TEXT[]
        AND (receipt_projection#>'{result_observation,artifacts}')-ARRAY['q10','q50','q90']::TEXT[]='{}'::JSONB
        AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q10}')='object' AND receipt_projection#>'{result_observation,artifacts,q10}' ?& ARRAY['artifact_hash','artifact_size_bytes']::TEXT[] AND (receipt_projection#>'{result_observation,artifacts,q10}')-ARRAY['artifact_hash','artifact_size_bytes']::TEXT[]='{}'::JSONB AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q10,artifact_hash}') IS NOT DISTINCT FROM 'string' AND COALESCE(receipt_projection#>>'{result_observation,artifacts,q10,artifact_hash}','')~'^[0-9a-f]{64}$' AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q10,artifact_size_bytes}') IS NOT DISTINCT FROM 'number' AND COALESCE(receipt_projection#>>'{result_observation,artifacts,q10,artifact_size_bytes}','')~'^[1-9][0-9]{0,18}$' AND (receipt_projection#>>'{result_observation,artifacts,q10,artifact_size_bytes}')::NUMERIC BETWEEN 1 AND 9223372036854775807
        AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q50}')='object' AND receipt_projection#>'{result_observation,artifacts,q50}' ?& ARRAY['artifact_hash','artifact_size_bytes']::TEXT[] AND (receipt_projection#>'{result_observation,artifacts,q50}')-ARRAY['artifact_hash','artifact_size_bytes']::TEXT[]='{}'::JSONB AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q50,artifact_hash}') IS NOT DISTINCT FROM 'string' AND COALESCE(receipt_projection#>>'{result_observation,artifacts,q50,artifact_hash}','')~'^[0-9a-f]{64}$' AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q50,artifact_size_bytes}') IS NOT DISTINCT FROM 'number' AND COALESCE(receipt_projection#>>'{result_observation,artifacts,q50,artifact_size_bytes}','')~'^[1-9][0-9]{0,18}$' AND (receipt_projection#>>'{result_observation,artifacts,q50,artifact_size_bytes}')::NUMERIC BETWEEN 1 AND 9223372036854775807
        AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q90}')='object' AND receipt_projection#>'{result_observation,artifacts,q90}' ?& ARRAY['artifact_hash','artifact_size_bytes']::TEXT[] AND (receipt_projection#>'{result_observation,artifacts,q90}')-ARRAY['artifact_hash','artifact_size_bytes']::TEXT[]='{}'::JSONB AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q90,artifact_hash}') IS NOT DISTINCT FROM 'string' AND COALESCE(receipt_projection#>>'{result_observation,artifacts,q90,artifact_hash}','')~'^[0-9a-f]{64}$' AND jsonb_typeof(receipt_projection#>'{result_observation,artifacts,q90,artifact_size_bytes}') IS NOT DISTINCT FROM 'number' AND COALESCE(receipt_projection#>>'{result_observation,artifacts,q90,artifact_size_bytes}','')~'^[1-9][0-9]{0,18}$' AND (receipt_projection#>>'{result_observation,artifacts,q90,artifact_size_bytes}')::NUMERIC BETWEEN 1 AND 9223372036854775807
        AND receipt_projection#>>'{result_observation,artifacts,q10,artifact_hash}'<>receipt_projection#>>'{result_observation,artifacts,q50,artifact_hash}'
        AND receipt_projection#>>'{result_observation,artifacts,q10,artifact_hash}'<>receipt_projection#>>'{result_observation,artifacts,q90,artifact_hash}'
        AND receipt_projection#>>'{result_observation,artifacts,q50,artifact_hash}'<>receipt_projection#>>'{result_observation,artifacts,q90,artifact_hash}'
        AND encode(public.digest(convert_to(format(
            E'q10=%s\nq50=%s\nq90=%s\n',
            receipt_projection#>>'{result_observation,artifacts,q10,artifact_hash}',
            receipt_projection#>>'{result_observation,artifacts,q50,artifact_hash}',
            receipt_projection#>>'{result_observation,artifacts,q90,artifact_hash}'
        ),'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT)=ordered_artifact_set_hash
        AND jsonb_typeof(receipt_projection->'authentication') = 'object'
        AND receipt_projection->'authentication' ?& ARRAY[
            'issuer_id','trust_policy_id','signature_key_id',
            'signature_algorithm','signature'
        ]::TEXT[]
        AND (receipt_projection->'authentication') - ARRAY[
            'issuer_id','trust_policy_id','signature_key_id',
            'signature_algorithm','signature'
        ]::TEXT[] = '{}'::JSONB
        AND receipt_projection#>>'{authentication,issuer_id}'
            IS NOT DISTINCT FROM issuer_id
        AND receipt_projection#>>'{authentication,trust_policy_id}'
            IS NOT DISTINCT FROM trust_policy_id
        AND receipt_projection#>>'{authentication,signature_key_id}'
            IS NOT DISTINCT FROM signature_key_id
        AND receipt_projection#>>'{authentication,signature_algorithm}'
            IS NOT DISTINCT FROM signature_algorithm
        AND jsonb_typeof(receipt_projection#>'{authentication,issuer_id}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{authentication,trust_policy_id}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{authentication,signature_key_id}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{authentication,signature_algorithm}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection#>'{authentication,signature}') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection->'verified_at') IS NOT DISTINCT FROM 'string'
        AND jsonb_typeof(receipt_projection->'expires_at') IS NOT DISTINCT FROM 'string'
        AND receipt_projection->>'verified_at'=to_char(verified_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
        AND receipt_projection->>'expires_at'=to_char(expires_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
        AND (receipt_projection#>>'{result_observation,fit_started_at}')::TIMESTAMPTZ<=(receipt_projection#>>'{result_observation,fit_completed_at}')::TIMESTAMPTZ
        AND (receipt_projection#>>'{result_observation,fit_completed_at}')::TIMESTAMPTZ<=verified_at
        AND COALESCE(receipt_projection#>>'{authentication,signature}', '')
            ~ '^[A-Za-z0-9_-]{43,512}={0,2}$'
    ),
    CONSTRAINT alr_fit_attestations_time_check CHECK (
        isfinite(verified_at) AND isfinite(expires_at)
        AND verified_at < expires_at
    ),
    CONSTRAINT alr_fit_attestations_no_authority_check CHECK (
        no_authority = '{
          "exchange_authority": false,
          "trading_authority": false,
          "order_or_probe_authority": false,
          "decision_lease_authority": false,
          "cost_gate_authority": false,
          "proof_authority": false,
          "serving_authority": false,
          "promotion_authority": false,
          "latest_authority": false,
          "runtime_mutation_authority": false,
          "database_write_authority": false,
          "symlink_authority": false
        }'::JSONB
        AND receipt_projection->'no_authority' = no_authority
    ),
    CONSTRAINT alr_fit_attestations_counters_check CHECK (
        authority_counters = '{
          "exchange_contact_count": 0,
          "trading_action_count": 0,
          "order_or_probe_count": 0,
          "decision_lease_count": 0,
          "cost_gate_change_count": 0,
          "proof_claim_count": 0,
          "serving_or_promotion_count": 0,
          "runtime_mutation_count": 0,
          "database_write_count": 0,
          "symlink_update_count": 0,
          "model_fit_count": 0
        }'::JSONB
        AND receipt_projection->'authority_counters' = authority_counters
    )
);

ALTER TABLE learning.alr_challenger_training_runs
    ADD COLUMN IF NOT EXISTS durable_attestation_hash TEXT NOT NULL,
    ADD COLUMN IF NOT EXISTS durable_training_run_hash TEXT NOT NULL,
    ADD COLUMN IF NOT EXISTS attestation_bound_at TIMESTAMPTZ NOT NULL,
    ADD COLUMN IF NOT EXISTS attestation_verified_at TIMESTAMPTZ NOT NULL,
    ADD COLUMN IF NOT EXISTS attestation_expires_at TIMESTAMPTZ NOT NULL;
ALTER TABLE learning.alr_challenger_model_artifacts
    ADD COLUMN IF NOT EXISTS durable_attestation_hash TEXT NOT NULL,
    ADD COLUMN IF NOT EXISTS durable_training_run_hash TEXT NOT NULL;
ALTER TABLE learning.alr_challenger_registry
    ADD COLUMN IF NOT EXISTS durable_attestation_hash TEXT NOT NULL,
    ADD COLUMN IF NOT EXISTS durable_training_run_hash TEXT NOT NULL,
    ADD COLUMN IF NOT EXISTS durable_challenger_hash TEXT NOT NULL,
    ADD COLUMN IF NOT EXISTS attestation_bound_at TIMESTAMPTZ NOT NULL;

DO $v159_lineage_constraints$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='alr_challenger_runs_v159_attestation_fk' AND conrelid='learning.alr_challenger_training_runs'::regclass) THEN
        ALTER TABLE learning.alr_challenger_training_runs
          ADD CONSTRAINT alr_challenger_runs_v159_attestation_fk
          FOREIGN KEY (
              durable_attestation_hash, durable_receipt_hash,
              training_key_hash, training_run_hash,
              model_artifact_set_hash
          ) REFERENCES learning.alr_challenger_fit_attestations (
              durable_attestation_hash, durable_receipt_hash,
              training_key_hash, structural_training_run_hash,
              ordered_artifact_set_hash
          )
          NOT DEFERRABLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='alr_challenger_runs_v159_attestation_uniq' AND conrelid='learning.alr_challenger_training_runs'::regclass) THEN
        ALTER TABLE learning.alr_challenger_training_runs
          ADD CONSTRAINT alr_challenger_runs_v159_attestation_uniq
          UNIQUE (durable_attestation_hash) NOT DEFERRABLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='alr_challenger_runs_v159_durable_run_uniq' AND conrelid='learning.alr_challenger_training_runs'::regclass) THEN
        ALTER TABLE learning.alr_challenger_training_runs
          ADD CONSTRAINT alr_challenger_runs_v159_durable_run_uniq
          UNIQUE (durable_training_run_hash) NOT DEFERRABLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='alr_challenger_runs_v159_artifact_lineage_uniq' AND conrelid='learning.alr_challenger_training_runs'::regclass) THEN
        ALTER TABLE learning.alr_challenger_training_runs
          ADD CONSTRAINT alr_challenger_runs_v159_artifact_lineage_uniq
          UNIQUE (
              training_run_hash, durable_training_run_hash,
              durable_attestation_hash, training_key_hash,
              model_artifact_set_hash, actual_feature_schema_hash,
              model_schema_version
          ) NOT DEFERRABLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='alr_challenger_runs_v159_registry_lineage_uniq' AND conrelid='learning.alr_challenger_training_runs'::regclass) THEN
        ALTER TABLE learning.alr_challenger_training_runs
          ADD CONSTRAINT alr_challenger_runs_v159_registry_lineage_uniq
          UNIQUE (
              training_run_hash, durable_training_run_hash,
              durable_attestation_hash, training_key_hash,
              model_artifact_set_hash
          ) NOT DEFERRABLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='alr_challenger_runs_v159_hashes_check' AND conrelid='learning.alr_challenger_training_runs'::regclass) THEN
        ALTER TABLE learning.alr_challenger_training_runs
          ADD CONSTRAINT alr_challenger_runs_v159_hashes_check CHECK (
              durable_attestation_hash ~ '^[0-9a-f]{64}$'
              AND durable_training_run_hash ~ '^[0-9a-f]{64}$'
          );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='alr_challenger_runs_v159_time_check' AND conrelid='learning.alr_challenger_training_runs'::regclass) THEN
        ALTER TABLE learning.alr_challenger_training_runs
          ADD CONSTRAINT alr_challenger_runs_v159_time_check CHECK (
              fit_completed_at <= attestation_verified_at
              AND attestation_verified_at <= attestation_bound_at
              AND attestation_bound_at < attestation_expires_at
          );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='alr_challenger_artifacts_v159_lineage_fk' AND conrelid='learning.alr_challenger_model_artifacts'::regclass) THEN
        ALTER TABLE learning.alr_challenger_model_artifacts
          ADD CONSTRAINT alr_challenger_artifacts_v159_lineage_fk
          FOREIGN KEY (
              training_run_hash, durable_training_run_hash,
              durable_attestation_hash, training_key_hash,
              model_artifact_set_hash, feature_schema_hash,
              model_schema_version
          ) REFERENCES learning.alr_challenger_training_runs (
              training_run_hash, durable_training_run_hash,
              durable_attestation_hash, training_key_hash,
              model_artifact_set_hash, actual_feature_schema_hash,
              model_schema_version
          ) NOT DEFERRABLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='alr_challenger_artifacts_v159_hashes_check' AND conrelid='learning.alr_challenger_model_artifacts'::regclass) THEN
        ALTER TABLE learning.alr_challenger_model_artifacts
          ADD CONSTRAINT alr_challenger_artifacts_v159_hashes_check CHECK (
              durable_attestation_hash ~ '^[0-9a-f]{64}$'
              AND durable_training_run_hash ~ '^[0-9a-f]{64}$'
          );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='alr_challenger_registry_v159_lineage_fk' AND conrelid='learning.alr_challenger_registry'::regclass) THEN
        ALTER TABLE learning.alr_challenger_registry
          ADD CONSTRAINT alr_challenger_registry_v159_lineage_fk
          FOREIGN KEY (
              training_run_hash, durable_training_run_hash,
              durable_attestation_hash, training_key_hash,
              model_artifact_set_hash
          ) REFERENCES learning.alr_challenger_training_runs (
              training_run_hash, durable_training_run_hash,
              durable_attestation_hash, training_key_hash,
              model_artifact_set_hash
          ) NOT DEFERRABLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='alr_challenger_registry_v159_durable_challenger_uniq' AND conrelid='learning.alr_challenger_registry'::regclass) THEN
        ALTER TABLE learning.alr_challenger_registry
          ADD CONSTRAINT alr_challenger_registry_v159_durable_challenger_uniq
          UNIQUE (durable_challenger_hash) NOT DEFERRABLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='alr_challenger_registry_v159_hashes_check' AND conrelid='learning.alr_challenger_registry'::regclass) THEN
        ALTER TABLE learning.alr_challenger_registry
          ADD CONSTRAINT alr_challenger_registry_v159_hashes_check CHECK (
              durable_attestation_hash ~ '^[0-9a-f]{64}$'
              AND durable_training_run_hash ~ '^[0-9a-f]{64}$'
              AND durable_challenger_hash ~ '^[0-9a-f]{64}$'
          );
    END IF;
END
$v159_lineage_constraints$;

-- Upgrade only the four V158 checks whose semantics necessarily change:
-- paths remain acyclic by using the structural c64 run identity, and result
-- rows do not self-assert a fit through an authority counter.
DO $v159_upgrade_checks$
DECLARE
    v_artifact_expr TEXT;
    v_counter_expr TEXT;
    v_run_payload_expr TEXT;
    v_registry_payload_expr TEXT;
BEGIN
    SELECT pg_get_constraintdef(c.oid, FALSE) INTO v_artifact_expr
    FROM pg_constraint AS c
    WHERE c.conrelid='learning.alr_challenger_model_artifacts'::regclass
      AND c.conname='alr_challenger_artifacts_shape_check';
    IF v_artifact_expr LIKE '%runs/structural/%' THEN
        NULL;
    ELSIF v_artifact_expr LIKE '%runs/%training_run_hash%' THEN
        ALTER TABLE learning.alr_challenger_model_artifacts
          DROP CONSTRAINT alr_challenger_artifacts_shape_check;
        ALTER TABLE learning.alr_challenger_model_artifacts
          ADD CONSTRAINT alr_challenger_artifacts_shape_check CHECK (
              quantile IN ('q10','q50','q90')
              AND artifact_format='onnx'
              AND artifact_size_bytes>0
              AND model_schema_version ~ '^[a-z0-9][a-z0-9_.-]{0,127}$'
              AND artifact_path='runs/structural/'||training_run_hash||'/'||quantile||'.onnx'
              AND symlink_created IS FALSE
              AND serving_visible IS FALSE
          );
    ELSE
        RAISE EXCEPTION
            'V159 check upgrade FAIL: artifact path expression drift';
    END IF;

    SELECT pg_get_constraintdef(c.oid, FALSE) INTO v_counter_expr
    FROM pg_constraint AS c
    WHERE c.conrelid='learning.alr_challenger_training_runs'::regclass
      AND c.conname='alr_challenger_runs_counters_check';
    IF v_counter_expr LIKE '%"model_fit_count": 0%' THEN
        NULL;
    ELSIF v_counter_expr LIKE '%"model_fit_count": 1%' THEN
        ALTER TABLE learning.alr_challenger_training_runs
          DROP CONSTRAINT alr_challenger_runs_counters_check;
        ALTER TABLE learning.alr_challenger_training_runs
          ADD CONSTRAINT alr_challenger_runs_counters_check CHECK (
              authority_counters = '{
                "exchange_contact_count": 0,
                "trading_action_count": 0,
                "order_or_probe_count": 0,
                "decision_lease_count": 0,
                "cost_gate_change_count": 0,
                "proof_claim_count": 0,
                "serving_or_promotion_count": 0,
                "runtime_mutation_count": 0,
                "database_write_count": 0,
                "symlink_update_count": 0,
                "model_fit_count": 0
              }'::JSONB
          );
    ELSE
        RAISE EXCEPTION
            'V159 check upgrade FAIL: run counter expression drift';
    END IF;
    SELECT pg_get_constraintdef(c.oid,FALSE) INTO v_run_payload_expr FROM pg_constraint c WHERE c.conrelid='learning.alr_challenger_training_runs'::regclass AND c.conname='alr_challenger_runs_payload_check';
    IF v_run_payload_expr LIKE '%alr_challenger_training_result_v2%' THEN NULL;
    ELSIF v_run_payload_expr LIKE '%alr_challenger_training_result_v1%' THEN
        ALTER TABLE learning.alr_challenger_training_runs DROP CONSTRAINT alr_challenger_runs_payload_check;
        ALTER TABLE learning.alr_challenger_training_runs ADD CONSTRAINT alr_challenger_runs_payload_check CHECK(jsonb_typeof(canonical_payload)='object' AND canonical_payload->>'schema_version' IS NOT DISTINCT FROM 'alr_challenger_training_result_v2');
    ELSE RAISE EXCEPTION 'V159 check upgrade FAIL: legacy payload expression drift'; END IF;
    SELECT pg_get_constraintdef(c.oid,FALSE) INTO v_registry_payload_expr FROM pg_constraint c WHERE c.conrelid='learning.alr_challenger_registry'::regclass AND c.conname='alr_challenger_registry_payload_check';
    IF v_registry_payload_expr LIKE '%alr_challenger_registry_entry_v2%' THEN NULL;
    ELSIF v_registry_payload_expr LIKE '%alr_challenger_registry_entry_v1%' THEN
        ALTER TABLE learning.alr_challenger_registry DROP CONSTRAINT alr_challenger_registry_payload_check;
        ALTER TABLE learning.alr_challenger_registry ADD CONSTRAINT alr_challenger_registry_payload_check CHECK(jsonb_typeof(canonical_payload)='object' AND canonical_payload->>'schema_version' IS NOT DISTINCT FROM 'alr_challenger_registry_entry_v2');
    ELSE RAISE EXCEPTION 'V159 check upgrade FAIL: v2 payload expression drift'; END IF;
END
$v159_upgrade_checks$;

-- Internal trigger functions only.  They are not application interfaces and
-- receive no caller EXECUTE grant.
CREATE OR REPLACE FUNCTION learning.alr_v159_reject_attestation_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $v159_immutable_trigger$
BEGIN
    IF current_user <> 'alr_challenger_fit_attestor' THEN
        RAISE EXCEPTION
            'V159 immutable trigger owner identity rejected';
    END IF;
    IF current_setting('session_replication_role') <> 'origin' THEN
        RAISE EXCEPTION
            'V159 immutable trigger requires session_replication_role=origin';
    END IF;
    RAISE EXCEPTION
        'V159 durable fit attestations are append-only: % rejected', TG_OP;
END
$v159_immutable_trigger$;

CREATE OR REPLACE FUNCTION learning.alr_v159_assert_attested_bundle()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $v159_complete_trigger$
DECLARE
    v_structural_run_hash TEXT;
    v_run learning.alr_challenger_training_runs%ROWTYPE;
    v_attestation learning.alr_challenger_fit_attestations%ROWTYPE;
    v_registry learning.alr_challenger_registry%ROWTYPE;
    v_artifact_count INTEGER;
    v_quantile_count INTEGER;
    v_registry_count INTEGER;
    v_exact_artifacts INTEGER;
    v_set_hash TEXT;
BEGIN
    IF session_user <> 'alr_challenger_trainer_caller'
       OR current_user <> 'alr_challenger_writer' THEN
        RAISE EXCEPTION
            'V159 completeness trigger session identity rejected';
    END IF;
    IF current_setting('session_replication_role') <> 'origin' THEN
        RAISE EXCEPTION
            'V159 completeness trigger requires session_replication_role=origin';
    END IF;
    IF TG_OP='DELETE' THEN
        v_structural_run_hash := OLD.training_run_hash;
    ELSE
        v_structural_run_hash := NEW.training_run_hash;
    END IF;

    SELECT r.* INTO v_run
    FROM learning.alr_challenger_training_runs AS r
    WHERE r.training_run_hash=v_structural_run_hash;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'V159 complete bundle invariant: exact attested run required';
    END IF;
    SELECT a.* INTO v_attestation
    FROM learning.alr_challenger_fit_attestations AS a
    WHERE a.durable_attestation_hash=v_run.durable_attestation_hash;
    IF NOT FOUND
       OR v_attestation.durable_receipt_hash
            IS DISTINCT FROM v_run.durable_receipt_hash
       OR v_attestation.training_key_hash
            IS DISTINCT FROM v_run.training_key_hash
       OR v_attestation.structural_training_run_hash
            IS DISTINCT FROM v_run.training_run_hash
       OR v_attestation.ordered_artifact_set_hash
            IS DISTINCT FROM v_run.model_artifact_set_hash
       OR v_attestation.verified_at
            IS DISTINCT FROM v_run.attestation_verified_at
       OR v_attestation.expires_at
            IS DISTINCT FROM v_run.attestation_expires_at
       OR v_run.attestation_bound_at < v_attestation.verified_at
       OR v_run.attestation_bound_at >= v_attestation.expires_at THEN
        RAISE EXCEPTION
            'V159 complete bundle invariant: attestation lineage mismatch';
    END IF;

    SELECT count(*), count(DISTINCT m.quantile), count(*) FILTER (WHERE
               m.durable_attestation_hash=v_run.durable_attestation_hash
           AND m.durable_training_run_hash=v_run.durable_training_run_hash
           AND m.training_key_hash=v_run.training_key_hash
           AND m.model_artifact_set_hash=v_run.model_artifact_set_hash
           AND m.feature_schema_hash=v_run.actual_feature_schema_hash
           AND m.model_schema_version=v_run.model_schema_version
           AND m.artifact_format='onnx'
           AND m.artifact_path=
               'runs/structural/'||v_run.training_run_hash||'/'||m.quantile||'.onnx'
           AND m.symlink_created IS FALSE
           AND m.serving_visible IS FALSE
       ), encode(
           public.digest(
               convert_to(format(
                   E'q10=%s\nq50=%s\nq90=%s\n',
                   max(m.artifact_hash) FILTER (WHERE m.quantile='q10'),
                   max(m.artifact_hash) FILTER (WHERE m.quantile='q50'),
                   max(m.artifact_hash) FILTER (WHERE m.quantile='q90')
               ), 'UTF8'::NAME),
               'sha256'::TEXT
           ), 'hex'::TEXT
       )
      INTO v_artifact_count, v_quantile_count, v_exact_artifacts, v_set_hash
    FROM learning.alr_challenger_model_artifacts AS m
    WHERE m.training_run_hash=v_run.training_run_hash;
    IF v_artifact_count<>3 OR v_quantile_count<>3 OR v_exact_artifacts<>3
       OR v_set_hash IS DISTINCT FROM v_run.model_artifact_set_hash THEN
        RAISE EXCEPTION
            'V159 complete bundle invariant: exact ordered q10/q50/q90 required';
    END IF;

    SELECT count(*) INTO v_registry_count
    FROM learning.alr_challenger_registry AS g
    WHERE g.training_run_hash=v_run.training_run_hash;
    SELECT g.* INTO v_registry
    FROM learning.alr_challenger_registry AS g
    WHERE g.training_run_hash=v_run.training_run_hash
      AND g.durable_training_run_hash=v_run.durable_training_run_hash
      AND g.durable_attestation_hash=v_run.durable_attestation_hash
      AND g.training_key_hash=v_run.training_key_hash
      AND g.model_artifact_set_hash=v_run.model_artifact_set_hash;
    IF v_registry_count<>1 OR NOT FOUND
       OR v_registry.challenger_hash
            IS DISTINCT FROM v_attestation.structural_challenger_hash
       OR v_registry.attestation_bound_at
            IS DISTINCT FROM v_run.attestation_bound_at
       OR v_registry.registry_status<>'NOT_SERVING'
       OR v_registry.serving_allowed IS NOT FALSE
       OR v_registry.promotion_allowed IS NOT FALSE
       OR v_registry.latest_pointer_allowed IS NOT FALSE
       OR v_registry.symlink_allowed IS NOT FALSE THEN
        RAISE EXCEPTION
            'V159 complete bundle invariant: exact NOT_SERVING registry required';
    END IF;
    RETURN NULL;
END
$v159_complete_trigger$;

ALTER FUNCTION learning.alr_v159_reject_attestation_mutation()
    OWNER TO alr_challenger_fit_attestor;
ALTER FUNCTION learning.alr_v159_assert_attested_bundle()
    OWNER TO alr_challenger_writer;
REVOKE ALL ON FUNCTION
    learning.alr_v159_reject_attestation_mutation(),
    learning.alr_v159_assert_attested_bundle()
FROM PUBLIC, alr_challenger_trainer_caller,
     alr_challenger_fit_attestor_caller;

-- Minimal dependency reads for the internal SECURITY DEFINER trigger only;
-- INSERT and public-interface EXECUTE remain closed until the next increment.
GRANT SELECT ON TABLE
    learning.alr_challenger_fit_attestations,
    learning.alr_challenger_training_runs,
    learning.alr_challenger_model_artifacts,
    learning.alr_challenger_registry
TO alr_challenger_fit_attestor;
GRANT SELECT ON TABLE learning.alr_challenger_fit_attestations
TO alr_challenger_writer;
GRANT EXECUTE ON FUNCTION public.digest(bytea, text)
TO alr_challenger_fit_attestor;

DO $v159_internal_triggers$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid='learning.alr_challenger_fit_attestations'::regclass
          AND tgname='alr_v159_immutable_fit_attestations_trg'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER alr_v159_immutable_fit_attestations_trg
        BEFORE UPDATE OR DELETE
        ON learning.alr_challenger_fit_attestations
        FOR EACH ROW
        EXECUTE FUNCTION learning.alr_v159_reject_attestation_mutation();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid='learning.alr_challenger_training_runs'::regclass
          AND tgname='alr_v159_run_complete_ct_v1'
          AND NOT tgisinternal
    ) THEN
        CREATE CONSTRAINT TRIGGER alr_v159_run_complete_ct_v1
        AFTER INSERT OR UPDATE OR DELETE
        ON learning.alr_challenger_training_runs
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION learning.alr_v159_assert_attested_bundle();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid='learning.alr_challenger_model_artifacts'::regclass
          AND tgname='alr_v159_artifact_complete_ct_v1'
          AND NOT tgisinternal
    ) THEN
        CREATE CONSTRAINT TRIGGER alr_v159_artifact_complete_ct_v1
        AFTER INSERT OR UPDATE OR DELETE
        ON learning.alr_challenger_model_artifacts
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION learning.alr_v159_assert_attested_bundle();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid='learning.alr_challenger_registry'::regclass
          AND tgname='alr_v159_registry_complete_ct_v1'
          AND NOT tgisinternal
    ) THEN
        CREATE CONSTRAINT TRIGGER alr_v159_registry_complete_ct_v1
        AFTER INSERT OR UPDATE OR DELETE
        ON learning.alr_challenger_registry
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION learning.alr_v159_assert_attested_bundle();
    END IF;
END
$v159_internal_triggers$;

CREATE OR REPLACE FUNCTION learning.persist_alr_challenger_fit_attestation_v1(
    p_signed_receipt_bytes BYTEA, p_receipt_projection JSONB,
    p_durable_receipt_hash TEXT, p_training_key_hash TEXT,
    p_structural_result_hash TEXT, p_structural_fit_capture_hash TEXT,
    p_structural_candidate_hash TEXT, p_structural_training_run_hash TEXT,
    p_structural_challenger_hash TEXT, p_runner_identity_hash TEXT,
    p_actual_input_material_set_hash TEXT, p_ordered_artifact_set_hash TEXT,
    p_issuer_id TEXT, p_trust_policy_id TEXT, p_signature_key_id TEXT,
    p_signature_algorithm TEXT, p_verified_at TIMESTAMPTZ,
    p_expires_at TIMESTAMPTZ
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $v159_attestation_writer$
DECLARE
    v_now TIMESTAMPTZ; v_digest TEXT; v_hash TEXT; v_inserted TEXT;
    v_row learning.alr_challenger_fit_attestations%ROWTYPE;
    v_receipt learning.alr_qualified_training_receipts%ROWTYPE;
    v_obs JSONB; v_obs_set TEXT;
    v_q10 TEXT; v_q50 TEXT; v_q90 TEXT; v_lock_key BIGINT;
    v_no JSONB := '{"exchange_authority":false,"trading_authority":false,"order_or_probe_authority":false,"decision_lease_authority":false,"cost_gate_authority":false,"proof_authority":false,"serving_authority":false,"promotion_authority":false,"latest_authority":false,"runtime_mutation_authority":false,"database_write_authority":false,"symlink_authority":false}'::JSONB;
    v_zero JSONB := '{"exchange_contact_count":0,"trading_action_count":0,"order_or_probe_count":0,"decision_lease_count":0,"cost_gate_change_count":0,"proof_claim_count":0,"serving_or_promotion_count":0,"runtime_mutation_count":0,"database_write_count":0,"symlink_update_count":0,"model_fit_count":0}'::JSONB;
BEGIN
    IF session_user<>'alr_challenger_fit_attestor_caller' OR current_user<>'alr_challenger_fit_attestor' THEN RAISE EXCEPTION 'V159 attestation writer session identity rejected'; END IF;
    IF current_setting('session_replication_role')<>'origin' THEN RAISE EXCEPTION 'V159 attestation writer requires session_replication_role=origin'; END IF;
    v_digest:=encode(public.digest(p_signed_receipt_bytes,'sha256'::TEXT),'hex'::TEXT);
    IF octet_length(p_signed_receipt_bytes) NOT BETWEEN 2 AND 1048576 OR p_signed_receipt_bytes IS DISTINCT FROM convert_to(p_receipt_projection::TEXT,'UTF8'::NAME)
       OR jsonb_typeof(p_receipt_projection) IS DISTINCT FROM 'object'
       OR p_receipt_projection->>'evidence_tier' IS DISTINCT FROM 'PLATFORM_OR_EXTERNAL_ATTESTED'
       OR p_receipt_projection->>'claim_kind' IS DISTINCT FROM 'ALR_FIT_EXECUTION_ATTESTATION_V1'
       OR p_receipt_projection->>'authentication_status' IS DISTINCT FROM 'SIGNATURE_VERIFIED_BY_TRUST_POLICY'
       OR p_receipt_projection#>'{claims,actual_inputs_consumed}' IS DISTINCT FROM 'true'::JSONB
       OR p_receipt_projection#>'{claims,actual_fit_executed}' IS DISTINCT FROM 'true'::JSONB
       OR p_receipt_projection#>'{claims,model_training_performed}' IS DISTINCT FROM 'true'::JSONB
       OR p_receipt_projection#>'{claims,artifact_readback_completed}' IS DISTINCT FROM 'true'::JSONB
       OR p_receipt_projection#>'{claims,onnx_semantic_validation_passed}' IS DISTINCT FROM 'true'::JSONB
       OR p_receipt_projection#>>'{subject,durable_receipt_hash}' IS DISTINCT FROM p_durable_receipt_hash
       OR p_receipt_projection#>>'{subject,training_key_hash}' IS DISTINCT FROM p_training_key_hash
       OR p_receipt_projection#>>'{subject,result_hash}' IS DISTINCT FROM p_structural_result_hash
       OR p_receipt_projection#>>'{subject,fit_capture_hash}' IS DISTINCT FROM p_structural_fit_capture_hash
       OR p_receipt_projection#>>'{subject,candidate_attestation_hash}' IS DISTINCT FROM p_structural_candidate_hash
       OR p_receipt_projection#>>'{subject,training_run_hash}' IS DISTINCT FROM p_structural_training_run_hash
       OR p_receipt_projection#>>'{subject,challenger_hash}' IS DISTINCT FROM p_structural_challenger_hash
       OR p_receipt_projection#>>'{subject,runner_identity_hash}' IS DISTINCT FROM p_runner_identity_hash
       OR p_receipt_projection#>>'{subject,actual_input_material_set_hash}' IS DISTINCT FROM p_actual_input_material_set_hash
       OR p_receipt_projection#>>'{subject,ordered_artifact_set_hash}' IS DISTINCT FROM p_ordered_artifact_set_hash
       OR p_receipt_projection#>>'{authentication,issuer_id}' IS DISTINCT FROM p_issuer_id
       OR p_receipt_projection#>>'{authentication,trust_policy_id}' IS DISTINCT FROM p_trust_policy_id
       OR p_receipt_projection#>>'{authentication,signature_key_id}' IS DISTINCT FROM p_signature_key_id
       OR p_receipt_projection#>>'{authentication,signature_algorithm}' IS DISTINCT FROM p_signature_algorithm
       OR p_receipt_projection->>'verified_at' IS DISTINCT FROM to_char(p_verified_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
       OR p_receipt_projection->>'expires_at' IS DISTINCT FROM to_char(p_expires_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
       OR p_receipt_projection->'no_authority' IS DISTINCT FROM v_no OR p_receipt_projection->'authority_counters' IS DISTINCT FROM v_zero THEN
        RAISE EXCEPTION 'V159 signed receipt bytes/projection/claim mismatch';
    END IF;
    v_obs:=p_receipt_projection->'result_observation';
    IF jsonb_typeof(v_obs->'actual_inputs')<>'object' OR NOT v_obs->'actual_inputs' ?& ARRAY['dataset_hash','row_ids_hash','split_hash','code_manifest_hash','training_config_hash','feature_schema_hash','label_schema_hash','training_rows']::TEXT[] OR (v_obs->'actual_inputs')-ARRAY['dataset_hash','row_ids_hash','split_hash','code_manifest_hash','training_config_hash','feature_schema_hash','label_schema_hash','training_rows']::TEXT[]<>'{}'::JSONB THEN RAISE EXCEPTION 'V159 actual_input fields/type mismatch'; END IF;
    IF jsonb_typeof(v_obs->'model')<>'object' OR NOT v_obs->'model' ?& ARRAY['model_schema_version','metrics_hash','resource_usage_hash']::TEXT[] OR (v_obs->'model')-ARRAY['model_schema_version','metrics_hash','resource_usage_hash']::TEXT[]<>'{}'::JSONB THEN RAISE EXCEPTION 'V159 model observation fields/type mismatch'; END IF;
    IF jsonb_typeof(v_obs->'artifacts')<>'object' OR NOT v_obs->'artifacts' ?& ARRAY['q10','q50','q90']::TEXT[] OR (v_obs->'artifacts')-ARRAY['q10','q50','q90']::TEXT[]<>'{}'::JSONB OR v_obs#>>'{artifacts,q10,artifact_hash}' IN(v_obs#>>'{artifacts,q50,artifact_hash}',v_obs#>>'{artifacts,q90,artifact_hash}') OR v_obs#>>'{artifacts,q50,artifact_hash}'=v_obs#>>'{artifacts,q90,artifact_hash}' THEN RAISE EXCEPTION 'V159 artifact observation fields/type mismatch'; END IF;
    v_q10:=v_obs#>>'{artifacts,q10,artifact_hash}'; v_q50:=v_obs#>>'{artifacts,q50,artifact_hash}'; v_q90:=v_obs#>>'{artifacts,q90,artifact_hash}';
    IF (v_obs->>'fit_started_at')::TIMESTAMPTZ>(v_obs->>'fit_completed_at')::TIMESTAMPTZ OR (v_obs->>'fit_completed_at')::TIMESTAMPTZ>p_verified_at THEN RAISE EXCEPTION 'V159 fit observation ordering mismatch'; END IF;
    SELECT * INTO v_receipt FROM learning.alr_qualified_training_receipts WHERE durable_receipt_hash=p_durable_receipt_hash AND training_key_hash=p_training_key_hash;
    IF NOT FOUND THEN RAISE EXCEPTION 'V159 qualified receipt lineage missing'; END IF;
    IF v_obs#>>'{actual_inputs,dataset_hash}' IS DISTINCT FROM v_receipt.canonical_payload->>'dataset_hash' OR v_obs#>>'{actual_inputs,row_ids_hash}' IS DISTINCT FROM v_receipt.canonical_payload->>'row_ids_hash' OR v_obs#>>'{actual_inputs,split_hash}' IS DISTINCT FROM v_receipt.canonical_payload->>'split_hash' OR v_obs#>>'{actual_inputs,code_manifest_hash}' IS DISTINCT FROM v_receipt.code_manifest_hash OR v_obs#>>'{actual_inputs,training_config_hash}' IS DISTINCT FROM v_receipt.training_config_hash OR v_obs#>>'{actual_inputs,feature_schema_hash}' IS DISTINCT FROM v_receipt.canonical_payload->>'feature_schema_hash' OR v_obs#>>'{actual_inputs,label_schema_hash}' IS DISTINCT FROM v_receipt.canonical_payload->>'label_schema_hash' OR (v_obs#>>'{actual_inputs,training_rows}')::INTEGER IS DISTINCT FROM (v_receipt.canonical_payload->>'training_rows')::INTEGER THEN RAISE EXCEPTION 'V159 signed observation differs from qualified receipt'; END IF;
    v_obs_set:=encode(public.digest(convert_to(format(E'q10=%s\nq50=%s\nq90=%s\n',v_obs#>>'{artifacts,q10,artifact_hash}',v_obs#>>'{artifacts,q50,artifact_hash}',v_obs#>>'{artifacts,q90,artifact_hash}'),'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT);
    IF v_obs_set<>p_ordered_artifact_set_hash THEN RAISE EXCEPTION 'V159 signed observation artifact set mismatch'; END IF;
    v_hash:=encode(public.digest(convert_to(format(E'alr_durable_fit_attestation_v1\nreceipt=%s\ndurable_receipt=%s\ntraining_key=%s\nresult=%s\nfit_capture=%s\ncandidate=%s\nrun=%s\nchallenger=%s\nrunner=%s\nmaterials=%s\nartifacts=%s\nissuer=%s\npolicy=%s\nkey=%s\nverified=%s\nexpires=%s\n',v_digest,p_durable_receipt_hash,p_training_key_hash,p_structural_result_hash,p_structural_fit_capture_hash,p_structural_candidate_hash,p_structural_training_run_hash,p_structural_challenger_hash,p_runner_identity_hash,p_actual_input_material_set_hash,p_ordered_artifact_set_hash,p_issuer_id,p_trust_policy_id,p_signature_key_id,to_char(p_verified_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),to_char(p_expires_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')),'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT);
    FOR v_lock_key IN SELECT DISTINCT hashtextextended('v159:artifact:'||artifact_hash,0) AS lock_key FROM unnest(ARRAY[v_q10,v_q50,v_q90]) artifact_hash ORDER BY lock_key LOOP
        PERFORM pg_advisory_xact_lock(v_lock_key);
    END LOOP;
    SELECT * INTO v_row FROM learning.alr_challenger_fit_attestations WHERE durable_attestation_hash=v_hash OR external_receipt_digest=v_digest OR (durable_receipt_hash=p_durable_receipt_hash AND training_key_hash=p_training_key_hash) OR structural_result_hash=p_structural_result_hash OR structural_fit_capture_hash=p_structural_fit_capture_hash OR structural_candidate_hash=p_structural_candidate_hash OR structural_training_run_hash=p_structural_training_run_hash OR structural_challenger_hash=p_structural_challenger_hash OR ordered_artifact_set_hash=p_ordered_artifact_set_hash ORDER BY (durable_attestation_hash=v_hash) DESC LIMIT 1;
    IF FOUND THEN
        IF ROW(v_row.durable_attestation_hash,v_row.external_receipt_digest,v_row.signed_receipt_bytes,v_row.receipt_projection,v_row.durable_receipt_hash,v_row.training_key_hash,v_row.structural_result_hash,v_row.structural_fit_capture_hash,v_row.structural_candidate_hash,v_row.structural_training_run_hash,v_row.structural_challenger_hash,v_row.runner_identity_hash,v_row.actual_input_material_set_hash,v_row.ordered_artifact_set_hash,v_row.issuer_id,v_row.trust_policy_id,v_row.signature_key_id,v_row.signature_algorithm,v_row.verified_at,v_row.expires_at,v_row.no_authority,v_row.authority_counters) IS DISTINCT FROM ROW(v_hash,v_digest,p_signed_receipt_bytes,p_receipt_projection,p_durable_receipt_hash,p_training_key_hash,p_structural_result_hash,p_structural_fit_capture_hash,p_structural_candidate_hash,p_structural_training_run_hash,p_structural_challenger_hash,p_runner_identity_hash,p_actual_input_material_set_hash,p_ordered_artifact_set_hash,p_issuer_id,p_trust_policy_id,p_signature_key_id,p_signature_algorithm,p_verified_at,p_expires_at,v_no,v_zero) THEN RAISE EXCEPTION 'V159 attestation replay conflict'; END IF;
        RETURN jsonb_build_object('status','DUPLICATE','durable_attestation_hash',v_hash,'external_receipt_digest',v_digest,'verified_at',p_verified_at,'expires_at',p_expires_at);
    END IF;
    IF EXISTS(SELECT 1 FROM learning.alr_challenger_fit_attestations e WHERE e.durable_attestation_hash<>v_hash AND ARRAY[e.receipt_projection#>>'{result_observation,artifacts,q10,artifact_hash}',e.receipt_projection#>>'{result_observation,artifacts,q50,artifact_hash}',e.receipt_projection#>>'{result_observation,artifacts,q90,artifact_hash}']::TEXT[] && ARRAY[v_q10,v_q50,v_q90]::TEXT[]) THEN RAISE EXCEPTION 'V159 attestation replay conflict'; END IF;
    v_now:=clock_timestamp();
    IF p_verified_at>v_now OR v_now>=p_expires_at OR p_verified_at>=p_expires_at THEN RAISE EXCEPTION 'V159 attestation future-dated or expired'; END IF;
    INSERT INTO learning.alr_challenger_fit_attestations VALUES (v_hash,v_digest,p_signed_receipt_bytes,p_receipt_projection,'PLATFORM_OR_EXTERNAL_ATTESTED','ALR_FIT_EXECUTION_ATTESTATION_V1','SIGNATURE_VERIFIED_BY_TRUST_POLICY',p_durable_receipt_hash,p_training_key_hash,p_structural_result_hash,p_structural_fit_capture_hash,p_structural_candidate_hash,p_structural_training_run_hash,p_structural_challenger_hash,p_runner_identity_hash,p_actual_input_material_set_hash,p_ordered_artifact_set_hash,p_issuer_id,p_trust_policy_id,p_signature_key_id,p_signature_algorithm,p_verified_at,p_expires_at,v_no,v_zero,DEFAULT) ON CONFLICT DO NOTHING RETURNING durable_attestation_hash INTO v_inserted;
    IF v_inserted IS NOT NULL AND clock_timestamp()>=p_expires_at THEN RAISE EXCEPTION 'V159 attestation future-dated or expired'; END IF;
    SELECT * INTO v_row FROM learning.alr_challenger_fit_attestations WHERE durable_attestation_hash=v_hash OR external_receipt_digest=v_digest OR (durable_receipt_hash=p_durable_receipt_hash AND training_key_hash=p_training_key_hash) OR structural_result_hash=p_structural_result_hash OR structural_fit_capture_hash=p_structural_fit_capture_hash OR structural_candidate_hash=p_structural_candidate_hash OR structural_training_run_hash=p_structural_training_run_hash OR structural_challenger_hash=p_structural_challenger_hash OR ordered_artifact_set_hash=p_ordered_artifact_set_hash ORDER BY (durable_attestation_hash=v_hash) DESC LIMIT 1;
    IF NOT FOUND OR ROW(v_row.external_receipt_digest,v_row.signed_receipt_bytes,v_row.receipt_projection,v_row.durable_receipt_hash,v_row.training_key_hash,v_row.structural_result_hash,v_row.structural_fit_capture_hash,v_row.structural_candidate_hash,v_row.structural_training_run_hash,v_row.structural_challenger_hash,v_row.runner_identity_hash,v_row.actual_input_material_set_hash,v_row.ordered_artifact_set_hash,v_row.issuer_id,v_row.trust_policy_id,v_row.signature_key_id,v_row.signature_algorithm,v_row.verified_at,v_row.expires_at,v_row.no_authority,v_row.authority_counters) IS DISTINCT FROM ROW(v_digest,p_signed_receipt_bytes,p_receipt_projection,p_durable_receipt_hash,p_training_key_hash,p_structural_result_hash,p_structural_fit_capture_hash,p_structural_candidate_hash,p_structural_training_run_hash,p_structural_challenger_hash,p_runner_identity_hash,p_actual_input_material_set_hash,p_ordered_artifact_set_hash,p_issuer_id,p_trust_policy_id,p_signature_key_id,p_signature_algorithm,p_verified_at,p_expires_at,v_no,v_zero) THEN RAISE EXCEPTION 'V159 attestation replay conflict'; END IF;
    RETURN jsonb_build_object('status',CASE WHEN v_inserted IS NULL THEN 'DUPLICATE' ELSE 'PERSISTED' END,'durable_attestation_hash',v_hash,'external_receipt_digest',v_digest,'verified_at',p_verified_at,'expires_at',p_expires_at);
END $v159_attestation_writer$;

CREATE OR REPLACE FUNCTION learning.persist_alr_challenger_training_result_v2(
    p_durable_attestation_hash TEXT,p_source_head TEXT,
    p_actual_dataset_hash TEXT,p_actual_row_ids_hash TEXT,p_actual_split_hash TEXT,
    p_actual_code_manifest_hash TEXT,p_actual_training_config_hash TEXT,
    p_actual_feature_schema_hash TEXT,p_actual_label_schema_hash TEXT,
    p_model_schema_version TEXT,p_actual_training_rows INTEGER,
    p_metrics_hash TEXT,p_resource_usage_hash TEXT,
    p_fit_started_at TIMESTAMPTZ,p_fit_completed_at TIMESTAMPTZ,
    p_q10_hash TEXT,p_q10_size BIGINT,p_q50_hash TEXT,p_q50_size BIGINT,
    p_q90_hash TEXT,p_q90_size BIGINT
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $v159_result_writer$
DECLARE
    a learning.alr_challenger_fit_attestations%ROWTYPE;
    r learning.alr_challenger_training_runs%ROWTYPE;
    g learning.alr_challenger_registry%ROWTYPE;
    v_bound TIMESTAMPTZ; v_set TEXT; v_drun TEXT; v_dchallenger TEXT;
    v_digest TEXT; v_att_hash TEXT; v_run_payload JSONB; v_reg_payload JSONB;
    v_artifacts JSONB; v_runs INTEGER; v_arts INTEGER; v_regs INTEGER;
    v_exact INTEGER; v_existing BOOLEAN:=FALSE; v_registry_found BOOLEAN; v_lock_key BIGINT;
    v_no JSONB:='{"exchange_authority":false,"trading_authority":false,"order_or_probe_authority":false,"decision_lease_authority":false,"cost_gate_authority":false,"proof_authority":false,"serving_authority":false,"promotion_authority":false,"latest_authority":false,"runtime_mutation_authority":false,"database_write_authority":false,"symlink_authority":false}'::JSONB;
    v_zero JSONB:='{"exchange_contact_count":0,"trading_action_count":0,"order_or_probe_count":0,"decision_lease_count":0,"cost_gate_change_count":0,"proof_claim_count":0,"serving_or_promotion_count":0,"runtime_mutation_count":0,"database_write_count":0,"symlink_update_count":0,"model_fit_count":0}'::JSONB;
BEGIN
    IF session_user<>'alr_challenger_trainer_caller' OR current_user<>'alr_challenger_writer' THEN RAISE EXCEPTION 'V159 result v2 writer session identity rejected'; END IF;
    IF current_setting('session_replication_role')<>'origin' THEN RAISE EXCEPTION 'V159 result v2 writer requires session_replication_role=origin'; END IF;
    SELECT * INTO a FROM learning.alr_challenger_fit_attestations WHERE durable_attestation_hash=p_durable_attestation_hash;
    IF NOT FOUND THEN RAISE EXCEPTION 'V159 durable attestation not found'; END IF;
    FOR v_lock_key IN SELECT DISTINCT hashtextextended(lock_material,0) AS lock_key FROM unnest(ARRAY['v159:attestation:'||p_durable_attestation_hash,'v159:run:'||a.structural_training_run_hash,'v159:challenger:'||a.structural_challenger_hash,'v159:artifact:'||p_q10_hash,'v159:artifact:'||p_q50_hash,'v159:artifact:'||p_q90_hash]::TEXT[]) lock_material ORDER BY lock_key LOOP
        PERFORM pg_advisory_xact_lock(v_lock_key);
    END LOOP;
    v_digest:=encode(public.digest(a.signed_receipt_bytes,'sha256'::TEXT),'hex'::TEXT);
    v_att_hash:=encode(public.digest(convert_to(format(E'alr_durable_fit_attestation_v1\nreceipt=%s\ndurable_receipt=%s\ntraining_key=%s\nresult=%s\nfit_capture=%s\ncandidate=%s\nrun=%s\nchallenger=%s\nrunner=%s\nmaterials=%s\nartifacts=%s\nissuer=%s\npolicy=%s\nkey=%s\nverified=%s\nexpires=%s\n',v_digest,a.durable_receipt_hash,a.training_key_hash,a.structural_result_hash,a.structural_fit_capture_hash,a.structural_candidate_hash,a.structural_training_run_hash,a.structural_challenger_hash,a.runner_identity_hash,a.actual_input_material_set_hash,a.ordered_artifact_set_hash,a.issuer_id,a.trust_policy_id,a.signature_key_id,to_char(a.verified_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),to_char(a.expires_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')),'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT);
    IF v_digest<>a.external_receipt_digest OR v_att_hash<>a.durable_attestation_hash OR a.evidence_tier<>'PLATFORM_OR_EXTERNAL_ATTESTED' OR a.claim_kind<>'ALR_FIT_EXECUTION_ATTESTATION_V1' THEN RAISE EXCEPTION 'V159 stored attestation integrity mismatch'; END IF;
    v_set:=encode(public.digest(convert_to(format(E'q10=%s\nq50=%s\nq90=%s\n',p_q10_hash,p_q50_hash,p_q90_hash),'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT);
    IF v_set<>a.ordered_artifact_set_hash OR p_q10_hash IN(p_q50_hash,p_q90_hash) OR p_q50_hash=p_q90_hash OR LEAST(p_q10_size,p_q50_size,p_q90_size)<=0 OR p_fit_completed_at<p_fit_started_at OR p_fit_completed_at>a.verified_at THEN RAISE EXCEPTION 'V159 result v2 artifact/fit mismatch'; END IF;
    IF NOT EXISTS(SELECT 1 FROM learning.alr_qualified_training_receipts q WHERE q.durable_receipt_hash=a.durable_receipt_hash AND q.training_key_hash=a.training_key_hash AND q.code_manifest_hash=p_actual_code_manifest_hash AND q.training_config_hash=p_actual_training_config_hash AND q.canonical_payload->>'dataset_hash'=p_actual_dataset_hash AND q.canonical_payload->>'row_ids_hash'=p_actual_row_ids_hash AND q.canonical_payload->>'split_hash'=p_actual_split_hash AND q.canonical_payload->>'feature_schema_hash'=p_actual_feature_schema_hash AND q.canonical_payload->>'label_schema_hash'=p_actual_label_schema_hash AND (q.canonical_payload->>'training_rows')::INTEGER=p_actual_training_rows) THEN RAISE EXCEPTION 'V159 exact qualified receipt lineage mismatch'; END IF;
    IF a.receipt_projection#>>'{result_observation,source_head}' IS DISTINCT FROM p_source_head OR a.receipt_projection#>>'{result_observation,actual_inputs,dataset_hash}' IS DISTINCT FROM p_actual_dataset_hash OR a.receipt_projection#>>'{result_observation,actual_inputs,row_ids_hash}' IS DISTINCT FROM p_actual_row_ids_hash OR a.receipt_projection#>>'{result_observation,actual_inputs,split_hash}' IS DISTINCT FROM p_actual_split_hash OR a.receipt_projection#>>'{result_observation,actual_inputs,code_manifest_hash}' IS DISTINCT FROM p_actual_code_manifest_hash OR a.receipt_projection#>>'{result_observation,actual_inputs,training_config_hash}' IS DISTINCT FROM p_actual_training_config_hash OR a.receipt_projection#>>'{result_observation,actual_inputs,feature_schema_hash}' IS DISTINCT FROM p_actual_feature_schema_hash OR a.receipt_projection#>>'{result_observation,actual_inputs,label_schema_hash}' IS DISTINCT FROM p_actual_label_schema_hash OR (a.receipt_projection#>>'{result_observation,actual_inputs,training_rows}')::INTEGER IS DISTINCT FROM p_actual_training_rows OR a.receipt_projection#>>'{result_observation,model,model_schema_version}' IS DISTINCT FROM p_model_schema_version OR a.receipt_projection#>>'{result_observation,model,metrics_hash}' IS DISTINCT FROM p_metrics_hash OR a.receipt_projection#>>'{result_observation,model,resource_usage_hash}' IS DISTINCT FROM p_resource_usage_hash OR (a.receipt_projection#>>'{result_observation,fit_started_at}')::TIMESTAMPTZ IS DISTINCT FROM p_fit_started_at OR (a.receipt_projection#>>'{result_observation,fit_completed_at}')::TIMESTAMPTZ IS DISTINCT FROM p_fit_completed_at OR a.receipt_projection#>>'{result_observation,artifacts,q10,artifact_hash}' IS DISTINCT FROM p_q10_hash OR (a.receipt_projection#>>'{result_observation,artifacts,q10,artifact_size_bytes}')::BIGINT IS DISTINCT FROM p_q10_size OR a.receipt_projection#>>'{result_observation,artifacts,q50,artifact_hash}' IS DISTINCT FROM p_q50_hash OR (a.receipt_projection#>>'{result_observation,artifacts,q50,artifact_size_bytes}')::BIGINT IS DISTINCT FROM p_q50_size OR a.receipt_projection#>>'{result_observation,artifacts,q90,artifact_hash}' IS DISTINCT FROM p_q90_hash OR (a.receipt_projection#>>'{result_observation,artifacts,q90,artifact_size_bytes}')::BIGINT IS DISTINCT FROM p_q90_size THEN RAISE EXCEPTION 'V159 caller result differs from signed observation'; END IF;
    SELECT count(*) INTO v_runs FROM learning.alr_challenger_training_runs WHERE durable_attestation_hash=a.durable_attestation_hash OR training_run_hash=a.structural_training_run_hash;
    SELECT count(*) INTO v_arts FROM learning.alr_challenger_model_artifacts WHERE durable_attestation_hash=a.durable_attestation_hash OR training_run_hash=a.structural_training_run_hash OR artifact_hash IN(p_q10_hash,p_q50_hash,p_q90_hash);
    SELECT count(*) INTO v_regs FROM learning.alr_challenger_registry WHERE durable_attestation_hash=a.durable_attestation_hash OR training_run_hash=a.structural_training_run_hash OR challenger_hash=a.structural_challenger_hash;
    IF v_runs=1 THEN SELECT * INTO r FROM learning.alr_challenger_training_runs WHERE durable_attestation_hash=a.durable_attestation_hash OR training_run_hash=a.structural_training_run_hash; v_existing:=TRUE; v_bound:=r.attestation_bound_at;
    ELSIF v_runs=0 AND v_arts=0 AND v_regs=0 THEN v_bound:=clock_timestamp(); IF a.verified_at>v_bound OR v_bound>=a.expires_at THEN RAISE EXCEPTION 'V159 expired or future attestation cannot bind'; END IF;
    ELSE RAISE EXCEPTION 'V159 result v2 PARTIAL_OR_DIVERGENT'; END IF;
    IF p_fit_completed_at>v_bound THEN RAISE EXCEPTION 'V159 fit completed after bind time'; END IF;
    v_drun:=encode(public.digest(convert_to(format(E'alr_durable_training_run_v1\nattestation=%s\nstructural_run=%s\nsource=%s\ndataset=%s\nrows=%s\nsplit=%s\ncode=%s\nconfig=%s\nfeature=%s\nlabel=%s\nmodel=%s\ntraining_rows=%s\nartifacts=%s\nmetrics=%s\nresources=%s\nfit_start=%s\nfit_end=%s\nbound=%s\n',a.durable_attestation_hash,a.structural_training_run_hash,p_source_head,p_actual_dataset_hash,p_actual_row_ids_hash,p_actual_split_hash,p_actual_code_manifest_hash,p_actual_training_config_hash,p_actual_feature_schema_hash,p_actual_label_schema_hash,p_model_schema_version,p_actual_training_rows,v_set,p_metrics_hash,p_resource_usage_hash,to_char(p_fit_started_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),to_char(p_fit_completed_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),to_char(v_bound AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')),'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT);
    v_dchallenger:=encode(public.digest(convert_to(format(E'alr_durable_challenger_v1\nattestation=%s\ndurable_run=%s\nstructural_challenger=%s\nartifacts=%s\n',a.durable_attestation_hash,v_drun,a.structural_challenger_hash,v_set),'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT);
    v_run_payload:=jsonb_build_object('schema_version','alr_challenger_training_result_v2','structural_training_run_hash',a.structural_training_run_hash,'durable_training_run_hash',v_drun,'durable_attestation_hash',a.durable_attestation_hash,'structural_result_hash',a.structural_result_hash,'structural_fit_capture_hash',a.structural_fit_capture_hash,'structural_candidate_hash',a.structural_candidate_hash,'run_status','TRAINING_PERFORMED','model_training_performed',TRUE,'attestation_bound_at',v_bound,'no_authority',v_no,'authority_counters',v_zero);
    v_reg_payload:=jsonb_build_object('schema_version','alr_challenger_registry_entry_v2','structural_challenger_hash',a.structural_challenger_hash,'durable_challenger_hash',v_dchallenger,'durable_training_run_hash',v_drun,'durable_attestation_hash',a.durable_attestation_hash,'registry_status','NOT_SERVING','serving_allowed',FALSE,'promotion_allowed',FALSE,'latest_pointer_allowed',FALSE,'symlink_allowed',FALSE);
    IF v_existing THEN
        SELECT * INTO g FROM learning.alr_challenger_registry WHERE training_run_hash=a.structural_training_run_hash; v_registry_found:=FOUND;
        SELECT count(*) FILTER(WHERE (quantile='q10' AND artifact_hash=p_q10_hash AND artifact_size_bytes=p_q10_size AND artifact_path='runs/structural/'||a.structural_training_run_hash||'/q10.onnx') OR (quantile='q50' AND artifact_hash=p_q50_hash AND artifact_size_bytes=p_q50_size AND artifact_path='runs/structural/'||a.structural_training_run_hash||'/q50.onnx') OR (quantile='q90' AND artifact_hash=p_q90_hash AND artifact_size_bytes=p_q90_size AND artifact_path='runs/structural/'||a.structural_training_run_hash||'/q90.onnx')) INTO v_exact FROM learning.alr_challenger_model_artifacts WHERE training_run_hash=a.structural_training_run_hash AND durable_training_run_hash=v_drun AND durable_attestation_hash=a.durable_attestation_hash AND training_key_hash=a.training_key_hash AND model_artifact_set_hash=v_set AND feature_schema_hash=p_actual_feature_schema_hash AND model_schema_version=p_model_schema_version AND artifact_format='onnx' AND symlink_created IS FALSE AND serving_visible IS FALSE;
        IF v_arts<>3 OR v_regs<>1 OR v_exact<>3 OR NOT v_registry_found OR ROW(r.durable_training_run_hash,r.durable_receipt_hash,r.training_key_hash,r.source_head,r.actual_dataset_hash,r.actual_row_ids_hash,r.actual_split_hash,r.actual_code_manifest_hash,r.actual_training_config_hash,r.actual_feature_schema_hash,r.actual_label_schema_hash,r.model_schema_version,r.actual_training_rows,r.model_artifact_set_hash,r.metrics_hash,r.resource_usage_hash,r.fit_started_at,r.fit_completed_at,r.canonical_payload,r.no_authority,r.authority_counters,r.attestation_verified_at,r.attestation_expires_at) IS DISTINCT FROM ROW(v_drun,a.durable_receipt_hash,a.training_key_hash,p_source_head,p_actual_dataset_hash,p_actual_row_ids_hash,p_actual_split_hash,p_actual_code_manifest_hash,p_actual_training_config_hash,p_actual_feature_schema_hash,p_actual_label_schema_hash,p_model_schema_version,p_actual_training_rows,v_set,p_metrics_hash,p_resource_usage_hash,p_fit_started_at,p_fit_completed_at,v_run_payload,v_no,v_zero,a.verified_at,a.expires_at) OR ROW(g.challenger_hash,g.durable_training_run_hash,g.durable_attestation_hash,g.training_key_hash,g.model_artifact_set_hash,g.durable_challenger_hash,g.attestation_bound_at,g.registry_status,g.serving_allowed,g.promotion_allowed,g.latest_pointer_allowed,g.symlink_allowed,g.canonical_payload) IS DISTINCT FROM ROW(a.structural_challenger_hash,v_drun,a.durable_attestation_hash,a.training_key_hash,v_set,v_dchallenger,v_bound,'NOT_SERVING',FALSE,FALSE,FALSE,FALSE,v_reg_payload) THEN RAISE EXCEPTION 'V159 result v2 replay conflict'; END IF;
    ELSE
        SET CONSTRAINTS learning.alr_challenger_run_complete_ct_v1,learning.alr_challenger_artifact_complete_ct_v1,learning.alr_challenger_registry_complete_ct_v1,learning.alr_v159_run_complete_ct_v1,learning.alr_v159_artifact_complete_ct_v1,learning.alr_v159_registry_complete_ct_v1 DEFERRED;
        INSERT INTO learning.alr_challenger_training_runs(training_run_hash,durable_receipt_hash,training_key_hash,source_head,actual_dataset_hash,actual_row_ids_hash,actual_split_hash,actual_code_manifest_hash,actual_training_config_hash,actual_feature_schema_hash,actual_label_schema_hash,model_schema_version,actual_training_rows,model_artifact_set_hash,metrics_hash,resource_usage_hash,run_status,model_training_performed,canonical_payload,no_authority,authority_counters,fit_started_at,fit_completed_at,durable_attestation_hash,durable_training_run_hash,attestation_bound_at,attestation_verified_at,attestation_expires_at) VALUES(a.structural_training_run_hash,a.durable_receipt_hash,a.training_key_hash,p_source_head,p_actual_dataset_hash,p_actual_row_ids_hash,p_actual_split_hash,p_actual_code_manifest_hash,p_actual_training_config_hash,p_actual_feature_schema_hash,p_actual_label_schema_hash,p_model_schema_version,p_actual_training_rows,v_set,p_metrics_hash,p_resource_usage_hash,'TRAINING_PERFORMED',TRUE,v_run_payload,v_no,v_zero,p_fit_started_at,p_fit_completed_at,a.durable_attestation_hash,v_drun,v_bound,a.verified_at,a.expires_at);
        INSERT INTO learning.alr_challenger_model_artifacts(artifact_hash,training_run_hash,training_key_hash,model_artifact_set_hash,quantile,artifact_format,artifact_path,artifact_size_bytes,feature_schema_hash,model_schema_version,symlink_created,serving_visible,durable_attestation_hash,durable_training_run_hash) VALUES(p_q10_hash,a.structural_training_run_hash,a.training_key_hash,v_set,'q10','onnx','runs/structural/'||a.structural_training_run_hash||'/q10.onnx',p_q10_size,p_actual_feature_schema_hash,p_model_schema_version,FALSE,FALSE,a.durable_attestation_hash,v_drun),(p_q50_hash,a.structural_training_run_hash,a.training_key_hash,v_set,'q50','onnx','runs/structural/'||a.structural_training_run_hash||'/q50.onnx',p_q50_size,p_actual_feature_schema_hash,p_model_schema_version,FALSE,FALSE,a.durable_attestation_hash,v_drun),(p_q90_hash,a.structural_training_run_hash,a.training_key_hash,v_set,'q90','onnx','runs/structural/'||a.structural_training_run_hash||'/q90.onnx',p_q90_size,p_actual_feature_schema_hash,p_model_schema_version,FALSE,FALSE,a.durable_attestation_hash,v_drun);
        INSERT INTO learning.alr_challenger_registry(challenger_hash,training_run_hash,training_key_hash,model_artifact_set_hash,registry_status,serving_allowed,promotion_allowed,latest_pointer_allowed,symlink_allowed,canonical_payload,durable_attestation_hash,durable_training_run_hash,durable_challenger_hash,attestation_bound_at) VALUES(a.structural_challenger_hash,a.structural_training_run_hash,a.training_key_hash,v_set,'NOT_SERVING',FALSE,FALSE,FALSE,FALSE,v_reg_payload,a.durable_attestation_hash,v_drun,v_dchallenger,v_bound);
        SET CONSTRAINTS learning.alr_challenger_run_complete_ct_v1,learning.alr_challenger_artifact_complete_ct_v1,learning.alr_challenger_registry_complete_ct_v1,learning.alr_v159_run_complete_ct_v1,learning.alr_v159_artifact_complete_ct_v1,learning.alr_v159_registry_complete_ct_v1 IMMEDIATE;
    END IF;
    SELECT jsonb_agg(to_jsonb(m) ORDER BY CASE m.quantile WHEN 'q10' THEN 1 WHEN 'q50' THEN 2 ELSE 3 END) INTO v_artifacts FROM learning.alr_challenger_model_artifacts m WHERE m.training_run_hash=a.structural_training_run_hash;
    RETURN jsonb_build_object('status',CASE WHEN v_existing THEN 'DUPLICATE' ELSE 'PERSISTED' END,'state','BOUND_COMPLETE','durable_attestation_hash',a.durable_attestation_hash,'structural_training_run_hash',a.structural_training_run_hash,'durable_training_run_hash',v_drun,'structural_challenger_hash',a.structural_challenger_hash,'durable_challenger_hash',v_dchallenger,'attestation_bound_at',v_bound,'artifacts',v_artifacts);
EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION 'V159 result v2 identity collision' USING ERRCODE='P0001';
END $v159_result_writer$;

ALTER FUNCTION learning.persist_alr_challenger_training_result_v2(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,BIGINT,TEXT,BIGINT,TEXT,BIGINT)
    OWNER TO alr_challenger_writer;
REVOKE ALL ON FUNCTION learning.persist_alr_challenger_training_result_v2(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,BIGINT,TEXT,BIGINT,TEXT,BIGINT)
FROM PUBLIC;

CREATE OR REPLACE FUNCTION learning.read_alr_challenger_training_result_v2(
    p_durable_attestation_hash TEXT,p_structural_training_run_hash TEXT
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $v159_result_reader$
DECLARE
    a learning.alr_challenger_fit_attestations%ROWTYPE;
    r learning.alr_challenger_training_runs%ROWTYPE;
    g learning.alr_challenger_registry%ROWTYPE;
    v_artifacts JSONB; v_rows INTEGER; v_exact INTEGER; v_quantiles INTEGER;
    v_regs INTEGER; v_set TEXT;
BEGIN
    IF session_user<>'alr_challenger_trainer_caller' OR current_user<>'alr_challenger_writer' THEN RAISE EXCEPTION 'V159 result v2 reader session identity rejected'; END IF;
    IF current_setting('session_replication_role')<>'origin' THEN RAISE EXCEPTION 'V159 result v2 reader requires session_replication_role=origin'; END IF;
    SELECT * INTO a FROM learning.alr_challenger_fit_attestations WHERE durable_attestation_hash=p_durable_attestation_hash AND structural_training_run_hash=p_structural_training_run_hash;
    IF NOT FOUND THEN
        SELECT (SELECT count(*) FROM learning.alr_challenger_fit_attestations WHERE durable_attestation_hash=p_durable_attestation_hash OR structural_training_run_hash=p_structural_training_run_hash)+(SELECT count(*) FROM learning.alr_challenger_training_runs WHERE durable_attestation_hash=p_durable_attestation_hash OR training_run_hash=p_structural_training_run_hash)+(SELECT count(*) FROM learning.alr_challenger_model_artifacts WHERE durable_attestation_hash=p_durable_attestation_hash OR training_run_hash=p_structural_training_run_hash)+(SELECT count(*) FROM learning.alr_challenger_registry WHERE durable_attestation_hash=p_durable_attestation_hash OR training_run_hash=p_structural_training_run_hash) INTO v_rows;
        IF v_rows<>0 THEN RAISE EXCEPTION 'V159 result v2 PARTIAL_OR_DIVERGENT'; END IF;
        RETURN jsonb_build_object('status','NOT_FOUND','state','NOT_FOUND');
    END IF;
    SELECT * INTO r FROM learning.alr_challenger_training_runs WHERE durable_attestation_hash=a.durable_attestation_hash AND training_run_hash=a.structural_training_run_hash;
    IF NOT FOUND THEN
        SELECT (SELECT count(*) FROM learning.alr_challenger_model_artifacts WHERE durable_attestation_hash=a.durable_attestation_hash OR training_run_hash=a.structural_training_run_hash)+(SELECT count(*) FROM learning.alr_challenger_registry WHERE durable_attestation_hash=a.durable_attestation_hash OR training_run_hash=a.structural_training_run_hash) INTO v_rows;
        IF v_rows<>0 THEN RAISE EXCEPTION 'V159 result v2 PARTIAL_OR_DIVERGENT'; END IF;
        RETURN jsonb_build_object('status','FOUND','state','ATTESTED_UNBOUND','durable_attestation_hash',a.durable_attestation_hash,'external_receipt_digest',a.external_receipt_digest,'receipt_bytes_encoding','base64','signed_receipt_bytes_base64',replace(encode(a.signed_receipt_bytes,'base64'::TEXT),E'\n',''),'receipt_projection',a.receipt_projection,'structural_result_hash',a.structural_result_hash,'structural_fit_capture_hash',a.structural_fit_capture_hash,'structural_candidate_hash',a.structural_candidate_hash,'structural_training_run_hash',a.structural_training_run_hash,'structural_challenger_hash',a.structural_challenger_hash,'verified_at',a.verified_at,'expires_at',a.expires_at);
    END IF;
    SELECT count(*),count(DISTINCT m.quantile),count(*) FILTER(WHERE m.durable_training_run_hash=r.durable_training_run_hash AND m.durable_attestation_hash=r.durable_attestation_hash AND m.training_key_hash=r.training_key_hash AND m.model_artifact_set_hash=r.model_artifact_set_hash AND m.feature_schema_hash=r.actual_feature_schema_hash AND m.model_schema_version=r.model_schema_version AND m.artifact_format='onnx' AND m.artifact_path='runs/structural/'||r.training_run_hash||'/'||m.quantile||'.onnx' AND m.symlink_created IS FALSE AND m.serving_visible IS FALSE),jsonb_agg(to_jsonb(m) ORDER BY CASE m.quantile WHEN 'q10' THEN 1 WHEN 'q50' THEN 2 ELSE 3 END),encode(public.digest(convert_to(format(E'q10=%s\nq50=%s\nq90=%s\n',max(m.artifact_hash) FILTER(WHERE m.quantile='q10'),max(m.artifact_hash) FILTER(WHERE m.quantile='q50'),max(m.artifact_hash) FILTER(WHERE m.quantile='q90')),'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT) INTO v_rows,v_quantiles,v_exact,v_artifacts,v_set FROM learning.alr_challenger_model_artifacts m WHERE m.training_run_hash=r.training_run_hash;
    SELECT count(*) INTO v_regs FROM learning.alr_challenger_registry WHERE training_run_hash=r.training_run_hash;
    SELECT * INTO g FROM learning.alr_challenger_registry WHERE training_run_hash=r.training_run_hash AND durable_training_run_hash=r.durable_training_run_hash AND durable_attestation_hash=r.durable_attestation_hash AND training_key_hash=r.training_key_hash AND model_artifact_set_hash=r.model_artifact_set_hash;
    IF r.durable_receipt_hash<>a.durable_receipt_hash OR r.training_key_hash<>a.training_key_hash OR r.model_artifact_set_hash<>a.ordered_artifact_set_hash OR r.attestation_verified_at<>a.verified_at OR r.attestation_expires_at<>a.expires_at OR r.attestation_bound_at<a.verified_at OR r.attestation_bound_at>=a.expires_at OR v_rows<>3 OR v_quantiles<>3 OR v_exact<>3 OR v_set<>r.model_artifact_set_hash OR v_regs<>1 OR NOT FOUND OR g.challenger_hash<>a.structural_challenger_hash OR g.durable_training_run_hash<>r.durable_training_run_hash OR g.durable_attestation_hash<>r.durable_attestation_hash OR g.attestation_bound_at<>r.attestation_bound_at OR g.registry_status<>'NOT_SERVING' OR g.serving_allowed OR g.promotion_allowed OR g.latest_pointer_allowed OR g.symlink_allowed THEN RAISE EXCEPTION 'V159 result v2 PARTIAL_OR_DIVERGENT'; END IF;
    RETURN jsonb_build_object('status','FOUND','state','BOUND_COMPLETE','durable_attestation_hash',a.durable_attestation_hash,'external_receipt_digest',a.external_receipt_digest,'receipt_bytes_encoding','base64','signed_receipt_bytes_base64',replace(encode(a.signed_receipt_bytes,'base64'::TEXT),E'\n',''),'receipt_projection',a.receipt_projection,'structural_result_hash',a.structural_result_hash,'structural_fit_capture_hash',a.structural_fit_capture_hash,'structural_candidate_hash',a.structural_candidate_hash,'structural_training_run_hash',r.training_run_hash,'durable_training_run_hash',r.durable_training_run_hash,'structural_challenger_hash',g.challenger_hash,'durable_challenger_hash',g.durable_challenger_hash,'attestation_bound_at',r.attestation_bound_at,'run',to_jsonb(r),'artifacts',v_artifacts,'registry',to_jsonb(g));
END $v159_result_reader$;

ALTER FUNCTION learning.read_alr_challenger_training_result_v2(TEXT,TEXT)
    OWNER TO alr_challenger_writer;
REVOKE ALL ON FUNCTION learning.read_alr_challenger_training_result_v2(TEXT,TEXT)
FROM PUBLIC;

-- All V158 result overloads were inventoried in Guard A.  Their first and
-- only executable action is now an unconditional hard failure.
CREATE OR REPLACE FUNCTION learning.persist_alr_challenger_training_result_v1(
    p_training_run_hash TEXT,
    p_durable_receipt_hash TEXT,
    p_training_key_hash TEXT,
    p_source_head TEXT,
    p_actual_dataset_hash TEXT,
    p_actual_row_ids_hash TEXT,
    p_actual_split_hash TEXT,
    p_actual_code_manifest_hash TEXT,
    p_actual_training_config_hash TEXT,
    p_actual_feature_schema_hash TEXT,
    p_actual_label_schema_hash TEXT,
    p_model_schema_version TEXT,
    p_actual_training_rows INTEGER,
    p_model_artifact_set_hash TEXT,
    p_metrics_hash TEXT,
    p_resource_usage_hash TEXT,
    p_fit_started_at TIMESTAMPTZ,
    p_fit_completed_at TIMESTAMPTZ,
    p_q10_artifact_hash TEXT,
    p_q10_artifact_path TEXT,
    p_q10_artifact_size_bytes BIGINT,
    p_q50_artifact_hash TEXT,
    p_q50_artifact_path TEXT,
    p_q50_artifact_size_bytes BIGINT,
    p_q90_artifact_hash TEXT,
    p_q90_artifact_path TEXT,
    p_q90_artifact_size_bytes BIGINT,
    p_challenger_hash TEXT
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $v159_closed_writer$ BEGIN RAISE EXCEPTION 'V159 closed V158 result writer: durable fit attestation v2 required'; END $v159_closed_writer$;
CREATE OR REPLACE FUNCTION learning.read_alr_challenger_training_result_v1(
    p_training_run_hash TEXT,
    p_training_key_hash TEXT
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $v159_closed_reader$ BEGIN RAISE EXCEPTION 'V159 closed V158 result reader: durable fit attestation v2 required'; END $v159_closed_reader$;

ALTER FUNCTION learning.persist_alr_challenger_fit_attestation_v1(BYTEA,JSONB,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ)
    OWNER TO alr_challenger_fit_attestor;

REVOKE ALL ON TABLE learning.alr_challenger_fit_attestations,learning.alr_challenger_training_runs,learning.alr_challenger_model_artifacts,learning.alr_challenger_registry FROM PUBLIC,alr_challenger_writer,alr_challenger_trainer_caller,alr_challenger_fit_attestor,alr_challenger_fit_attestor_caller;
GRANT SELECT,INSERT ON TABLE learning.alr_challenger_fit_attestations TO alr_challenger_fit_attestor;
GRANT SELECT ON TABLE learning.alr_qualified_training_receipts TO alr_challenger_fit_attestor;
GRANT SELECT ON TABLE learning.alr_qualified_training_receipts,learning.alr_challenger_fit_attestations TO alr_challenger_writer;
GRANT SELECT,INSERT ON TABLE learning.alr_challenger_training_runs,learning.alr_challenger_model_artifacts,learning.alr_challenger_registry TO alr_challenger_writer;
GRANT EXECUTE ON FUNCTION public.digest(bytea,text) TO alr_challenger_fit_attestor,alr_challenger_writer;
REVOKE ALL ON FUNCTION learning.persist_alr_challenger_fit_attestation_v1(BYTEA,JSONB,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ),learning.persist_alr_challenger_training_result_v2(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,BIGINT,TEXT,BIGINT,TEXT,BIGINT),learning.read_alr_challenger_training_result_v2(TEXT,TEXT),learning.persist_alr_challenger_training_result_v1(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,TEXT,BIGINT,TEXT,TEXT,BIGINT,TEXT,TEXT,BIGINT,TEXT),learning.read_alr_challenger_training_result_v1(TEXT,TEXT) FROM PUBLIC,alr_challenger_trainer_caller,alr_challenger_fit_attestor_caller;
GRANT EXECUTE ON FUNCTION learning.persist_alr_challenger_fit_attestation_v1(BYTEA,JSONB,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ) TO alr_challenger_fit_attestor_caller;
GRANT EXECUTE ON FUNCTION learning.persist_alr_challenger_training_result_v2(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,BIGINT,TEXT,BIGINT,TEXT,BIGINT),learning.read_alr_challenger_training_result_v2(TEXT,TEXT) TO alr_challenger_trainer_caller;
GRANT USAGE ON SCHEMA learning TO alr_challenger_fit_attestor,alr_challenger_fit_attestor_caller;
GRANT USAGE ON SCHEMA public TO alr_challenger_fit_attestor;
REVOKE CREATE ON SCHEMA learning,public FROM alr_challenger_writer,alr_challenger_trainer_caller,alr_challenger_fit_attestor,alr_challenger_fit_attestor_caller;
DO $v159_generic_revoke$ BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='trading_ai') THEN EXECUTE 'REVOKE ALL ON TABLE learning.alr_challenger_fit_attestations,learning.alr_challenger_training_runs,learning.alr_challenger_model_artifacts,learning.alr_challenger_registry FROM trading_ai'; EXECUTE 'REVOKE ALL ON FUNCTION learning.persist_alr_challenger_fit_attestation_v1(BYTEA,JSONB,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ),learning.persist_alr_challenger_training_result_v2(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,BIGINT,TEXT,BIGINT,TEXT,BIGINT),learning.read_alr_challenger_training_result_v2(TEXT,TEXT),learning.persist_alr_challenger_training_result_v1(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,TEXT,BIGINT,TEXT,TEXT,BIGINT,TEXT,TEXT,BIGINT,TEXT),learning.read_alr_challenger_training_result_v1(TEXT,TEXT) FROM trading_ai'; END IF;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='alr_shadow') THEN EXECUTE 'REVOKE ALL ON TABLE learning.alr_challenger_fit_attestations,learning.alr_challenger_training_runs,learning.alr_challenger_model_artifacts,learning.alr_challenger_registry FROM alr_shadow'; EXECUTE 'REVOKE ALL ON FUNCTION learning.persist_alr_challenger_fit_attestation_v1(BYTEA,JSONB,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ),learning.persist_alr_challenger_training_result_v2(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,BIGINT,TEXT,BIGINT,TEXT,BIGINT),learning.read_alr_challenger_training_result_v2(TEXT,TEXT),learning.persist_alr_challenger_training_result_v1(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,TEXT,BIGINT,TEXT,TEXT,BIGINT,TEXT,TEXT,BIGINT,TEXT),learning.read_alr_challenger_training_result_v1(TEXT,TEXT) FROM alr_shadow'; END IF;
END $v159_generic_revoke$;

DROP TABLE IF EXISTS pg_temp.alr_v159_expected_receipts,pg_temp.alr_v159_expected_runs,pg_temp.alr_v159_expected_artifacts,pg_temp.alr_v159_expected_registry,pg_temp.alr_v159_expected_attestations;

-- Guard C proves the final exact function, trigger, table, and ACL surface.
DO $v159_schema_postflight$
DECLARE
    v_count INTEGER;
    v_attestor_oid OID;
    v_writer_oid OID;
    v_attestor_caller_oid OID;
    v_trainer_caller_oid OID;
    v_spec RECORD;
    v_oid OID;
    v_object TEXT;
BEGIN
    IF to_regclass('learning.alr_challenger_fit_attestations') IS NULL THEN
        RAISE EXCEPTION
            'V159 schema postflight FAIL: attestation relation missing';
    END IF;
    SELECT oid INTO v_attestor_oid FROM pg_roles
    WHERE rolname='alr_challenger_fit_attestor';
    SELECT oid INTO v_writer_oid FROM pg_roles
    WHERE rolname='alr_challenger_writer';
    SELECT oid INTO v_attestor_caller_oid FROM pg_roles
    WHERE rolname='alr_challenger_fit_attestor_caller';
    SELECT oid INTO v_trainer_caller_oid FROM pg_roles
    WHERE rolname='alr_challenger_trainer_caller';
    SELECT count(*) INTO v_count
    FROM pg_attribute AS a
    WHERE a.attrelid='learning.alr_challenger_fit_attestations'::regclass
      AND a.attnum>0 AND NOT a.attisdropped;
    IF v_count<>26 THEN
        RAISE EXCEPTION
            'V159 schema postflight FAIL: attestation columns %/26', v_count;
    END IF;
    SELECT count(*) INTO v_count
    FROM pg_constraint AS c
    WHERE c.conname IN (
        'alr_fit_attestations_pk','alr_fit_attestations_receipt_digest_uniq',
        'alr_fit_attestations_receipt_training_uniq',
        'alr_fit_attestations_structural_result_uniq',
        'alr_fit_attestations_structural_fit_capture_uniq',
        'alr_fit_attestations_structural_candidate_uniq',
        'alr_fit_attestations_structural_training_run_uniq',
        'alr_fit_attestations_structural_challenger_uniq',
        'alr_fit_attestations_ordered_artifact_set_uniq',
        'alr_fit_attestations_lineage_uniq',
        'alr_fit_attestations_qualified_receipt_fk',
        'alr_fit_attestations_hashes_check',
        'alr_fit_attestations_signed_bytes_check',
        'alr_fit_attestations_evidence_check',
        'alr_fit_attestations_time_check',
        'alr_fit_attestations_no_authority_check',
        'alr_fit_attestations_counters_check',
        'alr_challenger_runs_v159_attestation_fk',
        'alr_challenger_runs_v159_attestation_uniq',
        'alr_challenger_runs_v159_durable_run_uniq',
        'alr_challenger_runs_v159_artifact_lineage_uniq',
        'alr_challenger_runs_v159_registry_lineage_uniq',
        'alr_challenger_runs_v159_hashes_check',
        'alr_challenger_runs_v159_time_check',
        'alr_challenger_artifacts_v159_lineage_fk',
        'alr_challenger_artifacts_v159_hashes_check',
        'alr_challenger_registry_v159_lineage_fk',
        'alr_challenger_registry_v159_durable_challenger_uniq',
        'alr_challenger_registry_v159_hashes_check'
    );
    IF v_count<>29 THEN
        RAISE EXCEPTION
            'V159 schema postflight FAIL: V159 constraints %/29', v_count;
    END IF;
    SELECT count(*) INTO v_count
    FROM pg_attribute AS a
    WHERE a.attrelid IN (
        'learning.alr_challenger_training_runs'::regclass,
        'learning.alr_challenger_model_artifacts'::regclass,
        'learning.alr_challenger_registry'::regclass
    ) AND a.attname IN (
        'durable_attestation_hash','durable_training_run_hash',
        'durable_challenger_hash','attestation_bound_at',
        'attestation_verified_at','attestation_expires_at'
    ) AND a.attnum > 0 AND NOT a.attisdropped
      AND a.attnotnull AND NOT a.atthasdef
      AND a.attgenerated = '' AND a.attidentity = '';
    IF v_count <> 11 THEN
        RAISE EXCEPTION
            'V159 schema postflight FAIL: exact no-default lineage columns %/11',
            v_count;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint AS c
        WHERE c.conrelid='learning.alr_challenger_model_artifacts'::regclass
          AND c.conname='alr_challenger_artifacts_shape_check'
          AND pg_get_constraintdef(c.oid,FALSE) LIKE '%runs/structural/%'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_constraint AS c
        WHERE c.conrelid='learning.alr_challenger_training_runs'::regclass
          AND c.conname='alr_challenger_runs_counters_check'
          AND pg_get_constraintdef(c.oid,FALSE) LIKE '%"model_fit_count": 0%'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_constraint c WHERE c.conrelid='learning.alr_challenger_training_runs'::regclass AND c.conname='alr_challenger_runs_payload_check' AND pg_get_constraintdef(c.oid,FALSE) LIKE '%alr_challenger_training_result_v2%'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_constraint c WHERE c.conrelid='learning.alr_challenger_registry'::regclass AND c.conname='alr_challenger_registry_payload_check' AND pg_get_constraintdef(c.oid,FALSE) LIKE '%alr_challenger_registry_entry_v2%'
    ) THEN
        RAISE EXCEPTION
            'V159 schema postflight FAIL: structural path/counter/payload upgrade';
    END IF;
    SELECT count(*) INTO v_count
    FROM pg_proc AS p
    JOIN pg_namespace AS n ON n.oid=p.pronamespace
    WHERE n.nspname='learning'
      AND p.proname IN (
          'alr_v159_reject_attestation_mutation',
          'alr_v159_assert_attested_bundle'
      ) AND p.proowner=CASE p.proname
          WHEN 'alr_v159_reject_attestation_mutation' THEN v_attestor_oid
          ELSE v_writer_oid END AND p.prosecdef
      AND p.prorettype='trigger'::regtype;
    IF v_count<>2 OR (
        SELECT count(*) FROM pg_trigger AS t
        WHERE NOT t.tgisinternal AND t.tgname IN (
            'alr_v159_immutable_fit_attestations_trg',
            'alr_v159_run_complete_ct_v1',
            'alr_v159_artifact_complete_ct_v1',
            'alr_v159_registry_complete_ct_v1'
        )
    )<>4 THEN
        RAISE EXCEPTION
            'V159 schema postflight FAIL: internal functions/triggers';
    END IF;
    SELECT count(*) INTO v_count FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='learning' AND p.proname IN('persist_alr_challenger_fit_attestation_v1','persist_alr_challenger_training_result_v2','read_alr_challenger_training_result_v2');
    IF v_count<>3 THEN RAISE EXCEPTION 'V159 Guard C FAIL: public overload inventory %/3',v_count; END IF;
    FOR v_spec IN SELECT * FROM (VALUES
      ('learning.persist_alr_challenger_fit_attestation_v1(bytea,jsonb,text,text,text,text,text,text,text,text,text,text,text,text,text,text,timestamp with time zone,timestamp with time zone)','5e6e564637a0c7fb62bd7853da662073','attestor','attestor_caller'),
      ('learning.persist_alr_challenger_training_result_v2(text,text,text,text,text,text,text,text,text,text,integer,text,text,timestamp with time zone,timestamp with time zone,text,bigint,text,bigint,text,bigint)','fcdbf0ddf9c991d151f3bc7e7f91db6c','writer','trainer_caller'),
      ('learning.read_alr_challenger_training_result_v2(text,text)','dfb767fc22f251b4663d9b3d0a7b4347','writer','trainer_caller')
    ) AS x(identity,body_md5,owner_kind,caller_kind) LOOP
        v_oid:=to_regprocedure(v_spec.identity);
        IF v_oid IS NULL OR NOT EXISTS(SELECT 1 FROM pg_proc p WHERE p.oid=v_oid AND p.proowner=CASE v_spec.owner_kind WHEN 'attestor' THEN v_attestor_oid ELSE v_writer_oid END AND p.prosecdef AND p.prorettype='jsonb'::regtype AND p.proconfig IS NOT DISTINCT FROM ARRAY['search_path=pg_catalog, pg_temp']::TEXT[] AND p.pronargdefaults=0 AND p.provariadic=0 AND md5(p.prosrc)=v_spec.body_md5)
           OR NOT has_function_privilege(CASE v_spec.caller_kind WHEN 'attestor_caller' THEN 'alr_challenger_fit_attestor_caller' ELSE 'alr_challenger_trainer_caller' END,v_oid,'EXECUTE')
           OR EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) privilege WHERE p.oid=v_oid AND privilege.grantee NOT IN(p.proowner,CASE v_spec.caller_kind WHEN 'attestor_caller' THEN v_attestor_caller_oid ELSE v_trainer_caller_oid END)) THEN RAISE EXCEPTION 'V159 Guard C FAIL: public function drift: %',v_spec.identity; END IF;
    END LOOP;
    IF md5((SELECT prosrc FROM pg_proc WHERE oid='learning.persist_alr_challenger_training_result_v1(text,text,text,text,text,text,text,text,text,text,text,text,integer,text,text,text,timestamp with time zone,timestamp with time zone,text,text,bigint,text,text,bigint,text,text,bigint,text)'::regprocedure))<>'d4eafeccebddd383e4e5b9543ba21ccf'
       OR md5((SELECT prosrc FROM pg_proc WHERE oid='learning.read_alr_challenger_training_result_v1(text,text)'::regprocedure))<>'71da623028a4ed44c78452b501b8daeb'
       OR has_function_privilege('alr_challenger_trainer_caller','learning.persist_alr_challenger_training_result_v1(text,text,text,text,text,text,text,text,text,text,text,text,integer,text,text,text,timestamp with time zone,timestamp with time zone,text,text,bigint,text,text,bigint,text,text,bigint,text)'::regprocedure,'EXECUTE')
       OR has_function_privilege('alr_challenger_trainer_caller','learning.read_alr_challenger_training_result_v1(text,text)'::regprocedure,'EXECUTE')
       OR EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) privilege WHERE p.oid IN('learning.persist_alr_challenger_training_result_v1(text,text,text,text,text,text,text,text,text,text,text,text,integer,text,text,text,timestamp with time zone,timestamp with time zone,text,text,bigint,text,text,bigint,text,text,bigint,text)'::regprocedure,'learning.read_alr_challenger_training_result_v1(text,text)'::regprocedure) AND privilege.grantee<>p.proowner) THEN RAISE EXCEPTION 'V159 Guard C FAIL: V158 result v1 closure drift'; END IF;
    IF NOT has_table_privilege('alr_challenger_fit_attestor','learning.alr_challenger_fit_attestations','SELECT,INSERT') OR has_table_privilege('alr_challenger_fit_attestor','learning.alr_challenger_fit_attestations','UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_table_privilege('alr_challenger_fit_attestor','learning.alr_challenger_training_runs','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
       OR NOT has_table_privilege('alr_challenger_writer','learning.alr_challenger_fit_attestations','SELECT') OR has_table_privilege('alr_challenger_writer','learning.alr_challenger_fit_attestations','INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') THEN RAISE EXCEPTION 'V159 Guard C FAIL: owner seam table ACL drift'; END IF;
    FOREACH v_object IN ARRAY ARRAY['learning.alr_challenger_training_runs','learning.alr_challenger_model_artifacts','learning.alr_challenger_registry'] LOOP
        IF NOT has_table_privilege('alr_challenger_writer',v_object,'SELECT,INSERT') OR has_table_privilege('alr_challenger_writer',v_object,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_table_privilege('alr_challenger_fit_attestor',v_object,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_table_privilege('alr_challenger_trainer_caller',v_object,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_table_privilege('alr_challenger_fit_attestor_caller',v_object,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') THEN RAISE EXCEPTION 'V159 Guard C FAIL: result table ACL drift: %',v_object; END IF;
    END LOOP;
    IF has_table_privilege('alr_challenger_trainer_caller','learning.alr_challenger_fit_attestations','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_table_privilege('alr_challenger_fit_attestor_caller','learning.alr_challenger_fit_attestations','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR EXISTS(SELECT 1 FROM pg_attribute a WHERE a.attrelid IN('learning.alr_challenger_fit_attestations'::regclass,'learning.alr_challenger_training_runs'::regclass,'learning.alr_challenger_model_artifacts'::regclass,'learning.alr_challenger_registry'::regclass) AND a.attacl IS NOT NULL) THEN RAISE EXCEPTION 'V159 Guard C FAIL: caller/column ACL drift'; END IF;
    IF has_schema_privilege('alr_challenger_writer','learning','CREATE') OR has_schema_privilege('alr_challenger_trainer_caller','learning','CREATE') OR has_schema_privilege('alr_challenger_fit_attestor','learning','CREATE') OR has_schema_privilege('alr_challenger_fit_attestor_caller','learning','CREATE') OR EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.roleid IN(v_writer_oid,v_trainer_caller_oid,v_attestor_oid,v_attestor_caller_oid) OR m.member IN(v_writer_oid,v_trainer_caller_oid,v_attestor_oid,v_attestor_caller_oid)) THEN RAISE EXCEPTION 'V159 Guard C FAIL: role reachability drift'; END IF;
    FOREACH v_object IN ARRAY ARRAY['trading_ai','alr_shadow'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=v_object) THEN
            IF has_table_privilege(v_object,'learning.alr_challenger_fit_attestations','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_table_privilege(v_object,'learning.alr_challenger_training_runs','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_function_privilege(v_object,'learning.persist_alr_challenger_fit_attestation_v1(bytea,jsonb,text,text,text,text,text,text,text,text,text,text,text,text,text,text,timestamp with time zone,timestamp with time zone)'::regprocedure,'EXECUTE') OR has_function_privilege(v_object,'learning.persist_alr_challenger_training_result_v2(text,text,text,text,text,text,text,text,text,text,integer,text,text,timestamp with time zone,timestamp with time zone,text,bigint,text,bigint,text,bigint)'::regprocedure,'EXECUTE') OR has_function_privilege(v_object,'learning.read_alr_challenger_training_result_v2(text,text)'::regprocedure,'EXECUTE') THEN RAISE EXCEPTION 'V159 Guard C FAIL: generic role reachability: %',v_object; END IF;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM learning.alr_challenger_training_runs)<>0 OR (SELECT count(*) FROM learning.alr_challenger_model_artifacts)<>0 OR (SELECT count(*) FROM learning.alr_challenger_registry)<>0 THEN RAISE EXCEPTION 'V159 Guard C FAIL: result tables became nonzero'; END IF;
    PERFORM pg_temp.alr_v159_assert_catalog('final');
END
$v159_schema_postflight$;

COMMIT;
