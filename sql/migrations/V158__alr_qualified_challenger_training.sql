-- V158: qualified ALR challenger training persistence (shadow/source only).
--
-- This forward-only schema records a repository-qualified training receipt and
-- one immutable q10/q50/q90 challenger result.  It does not apply itself,
-- create credentials, run a fit, update the legacy registry, expose a model to
-- serving, or grant any trading/exchange authority.
BEGIN;
SET LOCAL search_path = pg_catalog, pg_temp;
-- V158 Guard A: fail before normalizing DDL.  Roles and credentials are an
-- independently gated OPS precondition; this migration only verifies them.
DO $v158_guard_a$
DECLARE
    v_writer pg_roles%ROWTYPE;
    v_caller pg_roles%ROWTYPE;
    v_digest_owner TEXT;
    v_existing_tables INTEGER;
    v_existing_functions INTEGER;
    v_existing_triggers INTEGER;
    v_object TEXT;
    v_schema_owner OID;
    v_spec RECORD;
    v_oid OID;
BEGIN
    IF session_user <> current_user OR NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = current_user AND rolsuper IS TRUE
    ) THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: gated PostgreSQL superuser migration session required';
    END IF;
    IF to_regclass('learning.alr_artifact_nodes') IS NULL THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: learning.alr_artifact_nodes missing; apply V151 first';
    END IF;
    SELECT n.nspowner INTO v_schema_owner
    FROM pg_namespace AS n WHERE n.nspname = 'learning';
    IF NOT FOUND OR pg_get_userbyid(v_schema_owner) <> current_user OR NOT EXISTS (
           SELECT 1 FROM pg_roles
           WHERE oid = v_schema_owner AND rolsuper IS TRUE
       ) OR EXISTS (
           SELECT 1 FROM pg_auth_members WHERE roleid=v_schema_owner
       ) THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: learning schema requires the current trusted superuser owner';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_roles AS r
        WHERE r.rolsuper IS FALSE AND has_schema_privilege(r.rolname, 'learning', 'CREATE')
    ) OR EXISTS (
        SELECT 1 FROM pg_namespace AS n
        CROSS JOIN LATERAL aclexplode(
          COALESCE(n.nspacl, acldefault('n',n.nspowner))
        ) AS a WHERE n.nspname='learning' AND a.grantee=0 AND a.privilege_type='CREATE'
    ) THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: untrusted learning schema CREATE authority';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_class AS c
        WHERE c.oid='learning.alr_artifact_nodes'::regclass
          AND c.relowner=v_schema_owner AND c.relkind='r'
          AND c.relpersistence='p' AND NOT c.relispartition
          AND NOT c.relrowsecurity AND NOT c.relforcerowsecurity
          AND NOT c.relhasrules
    ) OR EXISTS (
        SELECT 1 FROM pg_inherits
        WHERE inhrelid='learning.alr_artifact_nodes'::regclass
           OR inhparent='learning.alr_artifact_nodes'::regclass
    ) OR EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polrelid='learning.alr_artifact_nodes'::regclass
    ) THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: learning_target dependency table is not trusted permanent state';
    END IF;
    IF to_regprocedure('public.digest(bytea,text)') IS NULL OR NOT EXISTS (
        SELECT 1
        FROM pg_proc AS p
        JOIN pg_depend AS d
          ON d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e'
        JOIN pg_extension AS e ON e.oid = d.refobjid
        WHERE p.oid = 'public.digest(bytea,text)'::regprocedure AND e.extname = 'pgcrypto'
    ) THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: exact extension-owned public.digest(bytea,text) missing';
    END IF;
    SELECT pg_get_userbyid(p.proowner)
      INTO v_digest_owner
      FROM pg_proc AS p
     WHERE p.oid = 'public.digest(bytea,text)'::regprocedure;
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = v_digest_owner AND rolsuper IS TRUE
    ) THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: public.digest(bytea,text) owner is not trusted';
    END IF;
    SELECT * INTO v_writer FROM pg_roles
     WHERE rolname = 'alr_challenger_writer';
    IF NOT FOUND OR v_writer.rolcanlogin IS TRUE OR v_writer.rolsuper IS TRUE OR v_writer.rolcreatedb IS TRUE OR v_writer.rolcreaterole IS TRUE OR v_writer.rolinherit IS TRUE OR v_writer.rolreplication IS TRUE OR v_writer.rolbypassrls IS TRUE THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: alr_challenger_writer role posture mismatch';
    END IF;
    SELECT * INTO v_caller FROM pg_roles
     WHERE rolname = 'alr_challenger_trainer_caller';
    IF NOT FOUND OR v_caller.rolcanlogin IS FALSE OR v_caller.rolsuper IS TRUE OR v_caller.rolcreatedb IS TRUE OR v_caller.rolcreaterole IS TRUE OR v_caller.rolinherit IS TRUE OR v_caller.rolreplication IS TRUE OR v_caller.rolbypassrls IS TRUE OR v_caller.rolconnlimit <> 1 THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: alr_challenger_trainer_caller role posture mismatch';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM pg_auth_members AS m
        JOIN pg_roles AS granted ON granted.oid = m.roleid
        JOIN pg_roles AS member_role ON member_role.oid = m.member
        WHERE granted.rolname IN (
                  'alr_challenger_writer', 'alr_challenger_trainer_caller'
              ) OR member_role.rolname IN (
                  'alr_challenger_writer', 'alr_challenger_trainer_caller'
              )
    ) THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: challenger roles must have no memberships';
    END IF;
    IF has_parameter_privilege(
           'alr_challenger_trainer_caller', 'session_replication_role', 'SET'
       ) OR has_parameter_privilege(
           'alr_challenger_writer', 'session_replication_role', 'SET'
       ) THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: challenger roles may not SET session_replication_role';
    END IF;
    SELECT count(*) INTO v_existing_tables
    FROM pg_class AS c
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'learning' AND c.relkind IN ('r', 'p') AND c.relname IN (
          'alr_qualified_training_receipts',
          'alr_challenger_training_runs',
          'alr_challenger_model_artifacts',
          'alr_challenger_registry'
      );
    IF v_existing_tables NOT IN (0, 4) THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: partial V158 table set detected: %/4',
            v_existing_tables;
    END IF;
    SELECT count(*) INTO v_existing_functions
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
    SELECT count(*) INTO v_existing_triggers
    FROM pg_trigger
    WHERE tgisinternal IS FALSE AND tgname IN (
          'alr_challenger_run_complete_ct_v1',
          'alr_challenger_artifact_complete_ct_v1',
          'alr_challenger_registry_complete_ct_v1',
          'alr_v158_immutable_alr_qualified_training_receipts_trg',
          'alr_v158_immutable_alr_challenger_training_runs_trg',
          'alr_v158_immutable_alr_challenger_model_artifacts_trg',
          'alr_v158_immutable_alr_challenger_registry_trg'
      );
    IF (v_existing_tables = 0 AND (
            v_existing_functions <> 0 OR v_existing_triggers <> 0
        )) OR (v_existing_tables = 4 AND (
            v_existing_functions <> 6 OR v_existing_triggers <> 7
        )) THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: partial V158 object set tables=% functions=% triggers=%',
            v_existing_tables, v_existing_functions, v_existing_triggers;
    END IF;
    IF (SELECT count(*) FROM pg_shdepend
        WHERE refclassid='pg_authid'::regclass AND refobjid=v_writer.oid
          AND deptype='o') <> v_existing_functions OR EXISTS (
        SELECT 1 FROM pg_shdepend AS d
        WHERE d.refclassid='pg_authid'::regclass
          AND d.refobjid=v_writer.oid AND d.deptype='o' AND (
            v_existing_functions=0
            OR d.dbid<>(SELECT oid FROM pg_database
                        WHERE datname=current_database())
            OR d.classid<>'pg_proc'::regclass
            OR d.objid NOT IN (
              to_regprocedure('learning.persist_alr_qualified_training_receipt_v1(text,text,text,text,text,text,text,text,text,text,text,text,text,text,text,jsonb)'),
              to_regprocedure('learning.persist_alr_challenger_training_result_v1(text,text,text,text,text,text,text,text,text,text,text,text,integer,text,text,text,timestamp with time zone,timestamp with time zone,text,text,bigint,text,text,bigint,text,text,bigint,text)'),
              to_regprocedure('learning.read_alr_qualified_training_receipt_v1(text,text)'),
              to_regprocedure('learning.read_alr_challenger_training_result_v1(text,text)'),
              to_regprocedure('learning.alr_v158_assert_complete_result()'),
              to_regprocedure('learning.alr_v158_reject_mutation()')
            )
          )
    ) THEN
        RAISE EXCEPTION
            'V158 Guard A FAIL: writer may own only the fixed V158 functions';
    END IF;
    IF v_existing_functions = 6 THEN
        FOR v_spec IN SELECT * FROM (VALUES
          ('learning.persist_alr_qualified_training_receipt_v1(text,text,text,text,text,text,text,text,text,text,text,text,text,text,text,jsonb)', '5edfac9aaf6b5e9e7d2ef492feb06f52', 'jsonb', TRUE),
          ('learning.persist_alr_challenger_training_result_v1(text,text,text,text,text,text,text,text,text,text,text,text,integer,text,text,text,timestamp with time zone,timestamp with time zone,text,text,bigint,text,text,bigint,text,text,bigint,text)', '30b25e486b820477b4a9eeaf3d209e28', 'jsonb', TRUE),
          ('learning.read_alr_qualified_training_receipt_v1(text,text)', '0b5f006cc0cb84a970e057a01c408ea0', 'jsonb', TRUE),
          ('learning.read_alr_challenger_training_result_v1(text,text)', '7b199c1aa74c5258693a4c761586f96b', 'jsonb', TRUE),
          ('learning.alr_v158_assert_complete_result()', '4829c6065049859a85bf49ec6b47e1ec', 'trigger', FALSE),
          ('learning.alr_v158_reject_mutation()', '2258b2692fe7dfbbed3c1ec397b47617', 'trigger', FALSE)
        ) AS x(identity, body_md5, return_type, caller_access) LOOP
            v_oid := to_regprocedure(v_spec.identity);
            IF v_oid IS NULL OR EXISTS (
                SELECT 1 FROM pg_proc AS p WHERE p.oid = v_oid AND (
                  p.proowner <> v_writer.oid OR p.prosecdef IS FALSE OR p.prolang <> (SELECT oid FROM pg_language WHERE lanname='plpgsql') OR p.prorettype <> v_spec.return_type::regtype OR p.proconfig IS DISTINCT FROM
                       ARRAY['search_path=pg_catalog, pg_temp']::TEXT[] OR p.provolatile <> 'v' OR p.proparallel <> 'u' OR p.proleakproof OR p.proisstrict OR p.pronargdefaults <> 0 OR p.provariadic <> 0 OR md5(p.prosrc) <> v_spec.body_md5
                )
            ) OR EXISTS (
                SELECT 1 FROM pg_proc AS p
                CROSS JOIN LATERAL aclexplode(
                  COALESCE(p.proacl, acldefault('f', p.proowner))
                ) AS a
                WHERE p.oid = v_oid AND (
                  a.grantee NOT IN (v_writer.oid, v_caller.oid) OR (a.grantee = v_caller.oid AND (
                    v_spec.caller_access IS FALSE OR a.privilege_type <> 'EXECUTE' OR a.is_grantable
                  ))
                )
            ) OR (SELECT count(*) FROM pg_proc AS p
                  CROSS JOIN LATERAL aclexplode(
                    COALESCE(p.proacl, acldefault('f', p.proowner))
                  ) AS a WHERE p.oid=v_oid AND a.grantee=v_caller.oid)
                 <> CASE WHEN v_spec.caller_access THEN 1 ELSE 0 END THEN
                RAISE EXCEPTION
                    'V158 Guard A FAIL: existing fixed function drift: %',
                    v_spec.identity;
            END IF;
        END LOOP;
    END IF;
    IF v_existing_triggers = 7 THEN
        FOR v_spec IN SELECT * FROM (VALUES
          ('alr_challenger_run_complete_ct_v1','learning.alr_challenger_training_runs','learning.alr_v158_assert_complete_result()',29,TRUE),
          ('alr_challenger_artifact_complete_ct_v1','learning.alr_challenger_model_artifacts','learning.alr_v158_assert_complete_result()',29,TRUE),
          ('alr_challenger_registry_complete_ct_v1','learning.alr_challenger_registry','learning.alr_v158_assert_complete_result()',29,TRUE),
          ('alr_v158_immutable_alr_qualified_training_receipts_trg','learning.alr_qualified_training_receipts','learning.alr_v158_reject_mutation()',27,FALSE),
          ('alr_v158_immutable_alr_challenger_training_runs_trg','learning.alr_challenger_training_runs','learning.alr_v158_reject_mutation()',27,FALSE),
          ('alr_v158_immutable_alr_challenger_model_artifacts_trg','learning.alr_challenger_model_artifacts','learning.alr_v158_reject_mutation()',27,FALSE),
          ('alr_v158_immutable_alr_challenger_registry_trg','learning.alr_challenger_registry','learning.alr_v158_reject_mutation()',27,FALSE)
        ) AS x(name, relation_name, function_name, trigger_type, constrained) LOOP
            IF (SELECT count(*) FROM pg_trigger WHERE tgname=v_spec.name AND tgisinternal IS FALSE) <> 1 OR NOT EXISTS (
                SELECT 1 FROM pg_trigger AS t WHERE t.tgname=v_spec.name AND t.tgrelid=v_spec.relation_name::regclass AND t.tgfoid=v_spec.function_name::regprocedure AND t.tgtype=v_spec.trigger_type AND t.tgenabled='O' AND t.tgnargs=0 AND t.tgqual IS NULL AND t.tgattr::TEXT='' AND t.tgdeferrable=v_spec.constrained AND t.tginitdeferred=v_spec.constrained AND (t.tgconstraint<>0)=v_spec.constrained
            ) THEN
                RAISE EXCEPTION
                    'V158 Guard A FAIL: existing trigger drift: %', v_spec.name;
            END IF;
        END LOOP;
    END IF;
    IF v_existing_tables = 4 THEN
        FOREACH v_object IN ARRAY ARRAY[
            'learning.alr_qualified_training_receipts',
            'learning.alr_challenger_training_runs',
            'learning.alr_challenger_model_artifacts',
            'learning.alr_challenger_registry'
        ] LOOP
            IF NOT EXISTS (
                 SELECT 1 FROM pg_class AS c WHERE c.oid=v_object::regclass
                   AND c.relowner=v_schema_owner AND c.relkind='r'
                   AND c.relpersistence='p' AND NOT c.relispartition
                   AND NOT c.relrowsecurity AND NOT c.relforcerowsecurity
                   AND NOT c.relhasrules
               ) OR EXISTS (
                 SELECT 1 FROM pg_inherits
                 WHERE inhrelid=v_object::regclass
                    OR inhparent=v_object::regclass
               ) OR EXISTS (
                 SELECT 1 FROM pg_policy WHERE polrelid=v_object::regclass
               ) OR EXISTS (
                 SELECT 1 FROM pg_index AS i
                 WHERE i.indrelid=v_object::regclass
                   AND (i.indisunique OR i.indisexclusion)
                   AND i.indisvalid AND i.indisready
                   AND NOT EXISTS (
                     SELECT 1 FROM pg_constraint AS c
                     WHERE c.conrelid=v_object::regclass
                       AND c.conindid=i.indexrelid AND c.contype IN ('p','u')
                   )
               ) OR NOT has_table_privilege(
                    'alr_challenger_writer', v_object, 'SELECT'
               ) OR NOT has_table_privilege(
                    'alr_challenger_writer', v_object, 'INSERT'
               ) OR EXISTS (
                   SELECT 1 FROM pg_class AS c
                   CROSS JOIN LATERAL aclexplode(
                     COALESCE(c.relacl, acldefault('r', c.relowner))
                   ) AS a WHERE c.oid=v_object::regclass AND (
                     a.grantee NOT IN (v_schema_owner, v_writer.oid) OR (a.grantee=v_writer.oid AND (
                       a.privilege_type NOT IN ('SELECT','INSERT') OR a.is_grantable
                     ))
                   )
               ) OR (SELECT count(*) FROM pg_class AS c
                     CROSS JOIN LATERAL aclexplode(
                       COALESCE(c.relacl, acldefault('r', c.relowner))
                     ) AS a WHERE c.oid=v_object::regclass AND a.grantee=v_writer.oid) <> 2 OR EXISTS (
                   SELECT 1 FROM pg_attribute AS a
                   CROSS JOIN LATERAL aclexplode(a.attacl) AS x
                   WHERE a.attrelid=v_object::regclass
               ) THEN
                RAISE EXCEPTION
                    'V158 Guard A FAIL: existing table owner/ACL drift: %',
                    v_object;
            END IF;
        END LOOP;
        IF NOT has_schema_privilege(
             'alr_challenger_writer','learning','USAGE'
           ) OR NOT has_schema_privilege(
             'alr_challenger_writer','public','USAGE'
           ) OR has_schema_privilege(
             'alr_challenger_writer','learning','CREATE'
           ) OR has_schema_privilege(
             'alr_challenger_writer','public','CREATE'
           ) OR NOT has_schema_privilege(
             'alr_challenger_trainer_caller','learning','USAGE'
           ) OR has_schema_privilege(
             'alr_challenger_trainer_caller','learning','CREATE'
           ) OR has_schema_privilege(
             'alr_challenger_trainer_caller','public','CREATE'
           ) OR NOT has_function_privilege(
             'alr_challenger_writer','public.digest(bytea,text)'::regprocedure,
             'EXECUTE'
           ) OR NOT has_table_privilege(
             'alr_challenger_writer','learning.alr_artifact_nodes','SELECT'
           ) OR has_table_privilege(
             'alr_challenger_writer','learning.alr_artifact_nodes',
             'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
           ) OR has_any_column_privilege(
             'alr_challenger_writer','learning.alr_artifact_nodes',
             'INSERT,UPDATE,REFERENCES'
           ) OR (SELECT count(*) FROM pg_proc AS p
                 CROSS JOIN LATERAL aclexplode(
                   COALESCE(p.proacl,acldefault('f',p.proowner))
                 ) AS a WHERE p.oid='public.digest(bytea,text)'::regprocedure
                   AND a.grantee=v_writer.oid)<>1
           OR EXISTS (
             SELECT 1 FROM pg_proc AS p
             CROSS JOIN LATERAL aclexplode(
               COALESCE(p.proacl,acldefault('f',p.proowner))
             ) AS a WHERE p.oid='public.digest(bytea,text)'::regprocedure
               AND a.grantee=v_writer.oid AND (
                 a.privilege_type<>'EXECUTE' OR a.is_grantable
                 OR a.grantor<>p.proowner
               )
           ) OR (SELECT count(*) FROM pg_class AS c
                 CROSS JOIN LATERAL aclexplode(
                   COALESCE(c.relacl,acldefault('r',c.relowner))
                 ) AS a WHERE c.oid='learning.alr_artifact_nodes'::regclass
                   AND a.grantee=v_writer.oid)<>1
           OR EXISTS (
             SELECT 1 FROM pg_class AS c
             CROSS JOIN LATERAL aclexplode(
               COALESCE(c.relacl,acldefault('r',c.relowner))
             ) AS a WHERE c.oid='learning.alr_artifact_nodes'::regclass
               AND a.grantee=v_writer.oid AND (
                 a.privilege_type<>'SELECT' OR a.is_grantable
                 OR a.grantor<>c.relowner
               )
           ) OR EXISTS (
             SELECT 1 FROM pg_attribute AS x
             CROSS JOIN LATERAL aclexplode(x.attacl) AS a
             WHERE x.attrelid='learning.alr_artifact_nodes'::regclass
               AND a.grantee=v_writer.oid
           ) THEN
            RAISE EXCEPTION
                'V158 Guard A FAIL: existing schema/dependency ACL drift';
        END IF;
    END IF;
END
$v158_guard_a$;
CREATE TABLE IF NOT EXISTS learning.alr_qualified_training_receipts (
    durable_receipt_hash TEXT NOT NULL,
    source_receipt_hash TEXT NOT NULL,
    source_contract_hash TEXT NOT NULL,
    projection_artifact_hash TEXT NOT NULL,
    selection_binding_hash TEXT NOT NULL,
    proof_input_hash TEXT NOT NULL,
    proof_packet_hash TEXT NOT NULL,
    reward_set_hash TEXT NOT NULL,
    pit_dataset_manifest_hash TEXT NOT NULL,
    after_cost_label_set_hash TEXT NOT NULL,
    evidence_set_hash TEXT NOT NULL,
    training_input_hash TEXT NOT NULL,
    training_key_hash TEXT NOT NULL,
    code_manifest_hash TEXT NOT NULL,
    training_config_hash TEXT NOT NULL,
    receipt_status TEXT NOT NULL,
    canonical_payload JSONB NOT NULL,
    no_authority JSONB NOT NULL,
    authority_counters JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_qualified_receipts_pk
        PRIMARY KEY (durable_receipt_hash) NOT DEFERRABLE,
    CONSTRAINT alr_qualified_receipts_training_key_uniq
        UNIQUE (training_key_hash) NOT DEFERRABLE,
    CONSTRAINT alr_qualified_receipts_receipt_training_uniq
        UNIQUE (durable_receipt_hash, training_key_hash) NOT DEFERRABLE,
    CONSTRAINT alr_qualified_receipts_source_training_uniq
        UNIQUE (source_receipt_hash, training_key_hash) NOT DEFERRABLE,
    CONSTRAINT alr_qualified_receipts_projection_fk
        FOREIGN KEY (projection_artifact_hash)
        REFERENCES learning.alr_artifact_nodes (artifact_hash)
        NOT DEFERRABLE,
    CONSTRAINT alr_qualified_receipts_hashes_check CHECK (
        durable_receipt_hash ~ '^[0-9a-f]{64}$' AND source_receipt_hash ~ '^[0-9a-f]{64}$' AND source_contract_hash ~ '^[0-9a-f]{64}$' AND projection_artifact_hash ~ '^[0-9a-f]{64}$' AND selection_binding_hash ~ '^[0-9a-f]{64}$' AND proof_input_hash ~ '^[0-9a-f]{64}$' AND proof_packet_hash ~ '^[0-9a-f]{64}$' AND reward_set_hash ~ '^[0-9a-f]{64}$' AND pit_dataset_manifest_hash ~ '^[0-9a-f]{64}$' AND after_cost_label_set_hash ~ '^[0-9a-f]{64}$' AND evidence_set_hash ~ '^[0-9a-f]{64}$' AND training_input_hash ~ '^[0-9a-f]{64}$' AND training_key_hash ~ '^[0-9a-f]{64}$' AND code_manifest_hash ~ '^[0-9a-f]{64}$' AND training_config_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT alr_qualified_receipts_status_check CHECK (
        receipt_status = 'QUALIFIED_INPUT_PERSISTED'
    ),
    CONSTRAINT alr_qualified_receipts_payload_check CHECK (
        jsonb_typeof(canonical_payload) = 'object' AND canonical_payload->>'schema_version' IS NOT DISTINCT FROM
            'alr_qualified_training_receipt_v1' AND canonical_payload ?& ARRAY[
            'schema_version', 'durable_receipt_hash', 'source_receipt_hash',
            'source_contract_hash', 'projection_artifact_hash',
            'projection_artifact_kind', 'selection_binding_hash',
            'proof_input_hash', 'proof_packet_hash', 'reward_set_hash',
            'pit_dataset_manifest_hash', 'after_cost_label_set_hash',
            'evidence_set_hash', 'training_input_hash', 'training_key_hash',
            'code_manifest_hash', 'training_config_hash', 'receipt_status',
            'training_allowed', 'model_training_performed',
            'registry_write_allowed', 'runtime_or_exchange_attested',
            'no_authority', 'authority_counters', 'dataset_hash',
            'row_ids_hash', 'split_hash', 'feature_schema_hash',
            'label_schema_hash', 'training_rows'
        ]::TEXT[] AND canonical_payload - ARRAY[
            'schema_version', 'durable_receipt_hash', 'source_receipt_hash',
            'source_contract_hash', 'projection_artifact_hash',
            'projection_artifact_kind', 'selection_binding_hash',
            'proof_input_hash', 'proof_packet_hash', 'reward_set_hash',
            'pit_dataset_manifest_hash', 'after_cost_label_set_hash',
            'evidence_set_hash', 'training_input_hash', 'training_key_hash',
            'code_manifest_hash', 'training_config_hash', 'receipt_status',
            'training_allowed', 'model_training_performed',
            'registry_write_allowed', 'runtime_or_exchange_attested',
            'no_authority', 'authority_counters', 'dataset_hash',
            'row_ids_hash', 'split_hash', 'feature_schema_hash',
            'label_schema_hash', 'training_rows'
        ]::TEXT[] = '{}'::jsonb
    ),
    CONSTRAINT alr_qualified_receipts_no_authority_check CHECK (
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
        }'::jsonb
    ),
    CONSTRAINT alr_qualified_receipts_counters_check CHECK (
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
        }'::jsonb
    )
);
CREATE TABLE IF NOT EXISTS learning.alr_challenger_training_runs (
    training_run_hash TEXT NOT NULL,
    durable_receipt_hash TEXT NOT NULL,
    training_key_hash TEXT NOT NULL,
    source_head TEXT NOT NULL,
    actual_dataset_hash TEXT NOT NULL,
    actual_row_ids_hash TEXT NOT NULL,
    actual_split_hash TEXT NOT NULL,
    actual_code_manifest_hash TEXT NOT NULL,
    actual_training_config_hash TEXT NOT NULL,
    actual_feature_schema_hash TEXT NOT NULL,
    actual_label_schema_hash TEXT NOT NULL,
    model_schema_version TEXT NOT NULL,
    actual_training_rows INTEGER NOT NULL,
    model_artifact_set_hash TEXT NOT NULL,
    metrics_hash TEXT NOT NULL,
    resource_usage_hash TEXT NOT NULL,
    run_status TEXT NOT NULL,
    model_training_performed BOOLEAN NOT NULL,
    canonical_payload JSONB NOT NULL,
    no_authority JSONB NOT NULL,
    authority_counters JSONB NOT NULL,
    fit_started_at TIMESTAMPTZ NOT NULL,
    fit_completed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_challenger_runs_pk
        PRIMARY KEY (training_run_hash) NOT DEFERRABLE,
    CONSTRAINT alr_challenger_runs_training_key_uniq
        UNIQUE (training_key_hash) NOT DEFERRABLE,
    CONSTRAINT alr_challenger_runs_result_lineage_uniq
        UNIQUE (
            training_run_hash, training_key_hash, model_artifact_set_hash
        ) NOT DEFERRABLE,
    CONSTRAINT alr_challenger_runs_artifact_lineage_uniq
        UNIQUE (
            training_run_hash, training_key_hash, model_artifact_set_hash,
            actual_feature_schema_hash, model_schema_version
        ) NOT DEFERRABLE,
    CONSTRAINT alr_challenger_runs_receipt_training_fk
        FOREIGN KEY (durable_receipt_hash, training_key_hash)
        REFERENCES learning.alr_qualified_training_receipts (
            durable_receipt_hash, training_key_hash
        ) NOT DEFERRABLE,
    CONSTRAINT alr_challenger_runs_hashes_check CHECK (
        training_run_hash ~ '^[0-9a-f]{64}$' AND durable_receipt_hash ~ '^[0-9a-f]{64}$' AND training_key_hash ~ '^[0-9a-f]{64}$' AND source_head ~ '^[0-9a-f]{40}$' AND actual_dataset_hash ~ '^[0-9a-f]{64}$' AND actual_row_ids_hash ~ '^[0-9a-f]{64}$' AND actual_split_hash ~ '^[0-9a-f]{64}$' AND actual_code_manifest_hash ~ '^[0-9a-f]{64}$' AND actual_training_config_hash ~ '^[0-9a-f]{64}$' AND actual_feature_schema_hash ~ '^[0-9a-f]{64}$' AND actual_label_schema_hash ~ '^[0-9a-f]{64}$' AND model_artifact_set_hash ~ '^[0-9a-f]{64}$' AND metrics_hash ~ '^[0-9a-f]{64}$' AND resource_usage_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT alr_challenger_runs_model_schema_check CHECK (
        model_schema_version ~ '^[a-z0-9][a-z0-9_.-]{0,127}$'
    ),
    CONSTRAINT alr_challenger_runs_state_check CHECK (
        run_status = 'TRAINING_PERFORMED' AND model_training_performed IS TRUE AND actual_training_rows > 0 AND fit_completed_at >= fit_started_at
    ),
    CONSTRAINT alr_challenger_runs_payload_check CHECK (
        jsonb_typeof(canonical_payload) = 'object' AND canonical_payload->>'schema_version' IS NOT DISTINCT FROM
            'alr_challenger_training_result_v1'
    ),
    CONSTRAINT alr_challenger_runs_no_authority_check CHECK (
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
        }'::jsonb
    ),
    CONSTRAINT alr_challenger_runs_counters_check CHECK (
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
          "model_fit_count": 1
        }'::jsonb
    )
);
CREATE TABLE IF NOT EXISTS learning.alr_challenger_model_artifacts (
    artifact_hash TEXT NOT NULL,
    training_run_hash TEXT NOT NULL,
    training_key_hash TEXT NOT NULL,
    model_artifact_set_hash TEXT NOT NULL,
    quantile TEXT NOT NULL,
    artifact_format TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    artifact_size_bytes BIGINT NOT NULL,
    feature_schema_hash TEXT NOT NULL,
    model_schema_version TEXT NOT NULL,
    symlink_created BOOLEAN NOT NULL,
    serving_visible BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_challenger_artifacts_pk
        PRIMARY KEY (artifact_hash) NOT DEFERRABLE,
    CONSTRAINT alr_challenger_artifacts_run_quantile_uniq
        UNIQUE (training_run_hash, quantile) NOT DEFERRABLE,
    CONSTRAINT alr_challenger_artifacts_run_lineage_fk
        FOREIGN KEY (
            training_run_hash, training_key_hash, model_artifact_set_hash,
            feature_schema_hash, model_schema_version
        ) REFERENCES learning.alr_challenger_training_runs (
            training_run_hash, training_key_hash, model_artifact_set_hash,
            actual_feature_schema_hash, model_schema_version
        ) NOT DEFERRABLE,
    CONSTRAINT alr_challenger_artifacts_hashes_check CHECK (
        artifact_hash ~ '^[0-9a-f]{64}$' AND training_run_hash ~ '^[0-9a-f]{64}$' AND training_key_hash ~ '^[0-9a-f]{64}$' AND model_artifact_set_hash ~ '^[0-9a-f]{64}$' AND feature_schema_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT alr_challenger_artifacts_shape_check CHECK (
        quantile IN ('q10', 'q50', 'q90') AND artifact_format = 'onnx' AND artifact_size_bytes > 0 AND model_schema_version ~ '^[a-z0-9][a-z0-9_.-]{0,127}$' AND artifact_path =
            'runs/' || training_run_hash || '/' || quantile || '.onnx' AND symlink_created IS FALSE AND serving_visible IS FALSE
    )
);
CREATE TABLE IF NOT EXISTS learning.alr_challenger_registry (
    challenger_hash TEXT NOT NULL,
    training_run_hash TEXT NOT NULL,
    training_key_hash TEXT NOT NULL,
    model_artifact_set_hash TEXT NOT NULL,
    registry_status TEXT NOT NULL,
    serving_allowed BOOLEAN NOT NULL,
    promotion_allowed BOOLEAN NOT NULL,
    latest_pointer_allowed BOOLEAN NOT NULL,
    symlink_allowed BOOLEAN NOT NULL,
    canonical_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_challenger_registry_pk
        PRIMARY KEY (challenger_hash) NOT DEFERRABLE,
    CONSTRAINT alr_challenger_registry_run_uniq
        UNIQUE (training_run_hash) NOT DEFERRABLE,
    CONSTRAINT alr_challenger_registry_training_key_uniq
        UNIQUE (training_key_hash) NOT DEFERRABLE,
    CONSTRAINT alr_challenger_registry_run_lineage_fk
        FOREIGN KEY (
            training_run_hash, training_key_hash, model_artifact_set_hash
        ) REFERENCES learning.alr_challenger_training_runs (
            training_run_hash, training_key_hash, model_artifact_set_hash
        ) NOT DEFERRABLE,
    CONSTRAINT alr_challenger_registry_hashes_check CHECK (
        challenger_hash ~ '^[0-9a-f]{64}$' AND training_run_hash ~ '^[0-9a-f]{64}$' AND training_key_hash ~ '^[0-9a-f]{64}$' AND model_artifact_set_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT alr_challenger_registry_state_check CHECK (
        registry_status = 'NOT_SERVING' AND serving_allowed IS FALSE AND promotion_allowed IS FALSE AND latest_pointer_allowed IS FALSE AND symlink_allowed IS FALSE
    ),
    CONSTRAINT alr_challenger_registry_payload_check CHECK (
        jsonb_typeof(canonical_payload) = 'object' AND canonical_payload->>'schema_version' IS NOT DISTINCT FROM
            'alr_challenger_registry_entry_v1'
    )
);
-- Guard B compares each durable CHECK against a freshly parsed PG16 catalog
-- expression.  LIKE copies the exact verified column map but no CHECK clauses.
CREATE TEMP TABLE alr_v158_expected_receipts
  (LIKE learning.alr_qualified_training_receipts) ON COMMIT DROP;
ALTER TABLE alr_v158_expected_receipts
  ADD CONSTRAINT expected_receipt_hashes CHECK (durable_receipt_hash ~ '^[0-9a-f]{64}$' AND source_receipt_hash ~ '^[0-9a-f]{64}$' AND source_contract_hash ~ '^[0-9a-f]{64}$' AND projection_artifact_hash ~ '^[0-9a-f]{64}$' AND selection_binding_hash ~ '^[0-9a-f]{64}$' AND proof_input_hash ~ '^[0-9a-f]{64}$' AND proof_packet_hash ~ '^[0-9a-f]{64}$' AND reward_set_hash ~ '^[0-9a-f]{64}$' AND pit_dataset_manifest_hash ~ '^[0-9a-f]{64}$' AND after_cost_label_set_hash ~ '^[0-9a-f]{64}$' AND evidence_set_hash ~ '^[0-9a-f]{64}$' AND training_input_hash ~ '^[0-9a-f]{64}$' AND training_key_hash ~ '^[0-9a-f]{64}$' AND code_manifest_hash ~ '^[0-9a-f]{64}$' AND training_config_hash ~ '^[0-9a-f]{64}$'),
  ADD CONSTRAINT expected_receipt_status CHECK (receipt_status='QUALIFIED_INPUT_PERSISTED'),
  ADD CONSTRAINT expected_receipt_payload CHECK (
    jsonb_typeof(canonical_payload)='object' AND canonical_payload->>'schema_version' IS NOT DISTINCT FROM 'alr_qualified_training_receipt_v1'
    AND canonical_payload ?& ARRAY['schema_version','durable_receipt_hash','source_receipt_hash','source_contract_hash','projection_artifact_hash','projection_artifact_kind','selection_binding_hash','proof_input_hash','proof_packet_hash','reward_set_hash','pit_dataset_manifest_hash','after_cost_label_set_hash','evidence_set_hash','training_input_hash','training_key_hash','code_manifest_hash','training_config_hash','receipt_status','training_allowed','model_training_performed','registry_write_allowed','runtime_or_exchange_attested','no_authority','authority_counters','dataset_hash','row_ids_hash','split_hash','feature_schema_hash','label_schema_hash','training_rows']::TEXT[]
    AND canonical_payload-ARRAY['schema_version','durable_receipt_hash','source_receipt_hash','source_contract_hash','projection_artifact_hash','projection_artifact_kind','selection_binding_hash','proof_input_hash','proof_packet_hash','reward_set_hash','pit_dataset_manifest_hash','after_cost_label_set_hash','evidence_set_hash','training_input_hash','training_key_hash','code_manifest_hash','training_config_hash','receipt_status','training_allowed','model_training_performed','registry_write_allowed','runtime_or_exchange_attested','no_authority','authority_counters','dataset_hash','row_ids_hash','split_hash','feature_schema_hash','label_schema_hash','training_rows']::TEXT[]='{}'::JSONB),
  ADD CONSTRAINT expected_receipt_no_authority CHECK (no_authority='{"exchange_authority":false,"trading_authority":false,"order_or_probe_authority":false,"decision_lease_authority":false,"cost_gate_authority":false,"proof_authority":false,"serving_authority":false,"promotion_authority":false,"latest_authority":false,"runtime_mutation_authority":false,"database_write_authority":false,"symlink_authority":false}'::JSONB),
  ADD CONSTRAINT expected_receipt_counters CHECK (authority_counters='{"exchange_contact_count":0,"trading_action_count":0,"order_or_probe_count":0,"decision_lease_count":0,"cost_gate_change_count":0,"proof_claim_count":0,"serving_or_promotion_count":0,"runtime_mutation_count":0,"database_write_count":0,"symlink_update_count":0,"model_fit_count":0}'::JSONB);
CREATE TEMP TABLE alr_v158_expected_runs
  (LIKE learning.alr_challenger_training_runs) ON COMMIT DROP;
ALTER TABLE alr_v158_expected_runs
  ADD CONSTRAINT expected_run_hashes CHECK (training_run_hash ~ '^[0-9a-f]{64}$' AND durable_receipt_hash ~ '^[0-9a-f]{64}$' AND training_key_hash ~ '^[0-9a-f]{64}$' AND source_head ~ '^[0-9a-f]{40}$' AND actual_dataset_hash ~ '^[0-9a-f]{64}$' AND actual_row_ids_hash ~ '^[0-9a-f]{64}$' AND actual_split_hash ~ '^[0-9a-f]{64}$' AND actual_code_manifest_hash ~ '^[0-9a-f]{64}$' AND actual_training_config_hash ~ '^[0-9a-f]{64}$' AND actual_feature_schema_hash ~ '^[0-9a-f]{64}$' AND actual_label_schema_hash ~ '^[0-9a-f]{64}$' AND model_artifact_set_hash ~ '^[0-9a-f]{64}$' AND metrics_hash ~ '^[0-9a-f]{64}$' AND resource_usage_hash ~ '^[0-9a-f]{64}$'),
  ADD CONSTRAINT expected_run_model_schema CHECK (model_schema_version ~ '^[a-z0-9][a-z0-9_.-]{0,127}$'),
  ADD CONSTRAINT expected_run_state CHECK (run_status='TRAINING_PERFORMED' AND model_training_performed IS TRUE AND actual_training_rows>0 AND fit_completed_at>=fit_started_at),
  ADD CONSTRAINT expected_run_payload CHECK (jsonb_typeof(canonical_payload)='object' AND canonical_payload->>'schema_version' IS NOT DISTINCT FROM 'alr_challenger_training_result_v1'),
  ADD CONSTRAINT expected_run_no_authority CHECK (no_authority='{"exchange_authority":false,"trading_authority":false,"order_or_probe_authority":false,"decision_lease_authority":false,"cost_gate_authority":false,"proof_authority":false,"serving_authority":false,"promotion_authority":false,"latest_authority":false,"runtime_mutation_authority":false,"database_write_authority":false,"symlink_authority":false}'::JSONB),
  ADD CONSTRAINT expected_run_counters CHECK (authority_counters='{"exchange_contact_count":0,"trading_action_count":0,"order_or_probe_count":0,"decision_lease_count":0,"cost_gate_change_count":0,"proof_claim_count":0,"serving_or_promotion_count":0,"runtime_mutation_count":0,"database_write_count":0,"symlink_update_count":0,"model_fit_count":1}'::JSONB);
CREATE TEMP TABLE alr_v158_expected_artifacts
  (LIKE learning.alr_challenger_model_artifacts) ON COMMIT DROP;
ALTER TABLE alr_v158_expected_artifacts
  ADD CONSTRAINT expected_artifact_hashes CHECK (artifact_hash ~ '^[0-9a-f]{64}$' AND training_run_hash ~ '^[0-9a-f]{64}$' AND training_key_hash ~ '^[0-9a-f]{64}$' AND model_artifact_set_hash ~ '^[0-9a-f]{64}$' AND feature_schema_hash ~ '^[0-9a-f]{64}$'),
  ADD CONSTRAINT expected_artifact_shape CHECK (quantile IN ('q10','q50','q90') AND artifact_format='onnx' AND artifact_size_bytes>0 AND model_schema_version ~ '^[a-z0-9][a-z0-9_.-]{0,127}$' AND artifact_path='runs/'||training_run_hash||'/'||quantile||'.onnx' AND symlink_created IS FALSE AND serving_visible IS FALSE);
CREATE TEMP TABLE alr_v158_expected_registry
  (LIKE learning.alr_challenger_registry) ON COMMIT DROP;
ALTER TABLE alr_v158_expected_registry
  ADD CONSTRAINT expected_registry_hashes CHECK (challenger_hash ~ '^[0-9a-f]{64}$' AND training_run_hash ~ '^[0-9a-f]{64}$' AND training_key_hash ~ '^[0-9a-f]{64}$' AND model_artifact_set_hash ~ '^[0-9a-f]{64}$'),
  ADD CONSTRAINT expected_registry_state CHECK (registry_status='NOT_SERVING' AND serving_allowed IS FALSE AND promotion_allowed IS FALSE AND latest_pointer_allowed IS FALSE AND symlink_allowed IS FALSE),
  ADD CONSTRAINT expected_registry_payload CHECK (jsonb_typeof(canonical_payload)='object' AND canonical_payload->>'schema_version' IS NOT DISTINCT FROM 'alr_challenger_registry_entry_v1');
-- Fixed receipt writer; status and authority fields are database-owned.
CREATE OR REPLACE FUNCTION learning.persist_alr_qualified_training_receipt_v1(
    p_durable_receipt_hash TEXT,
    p_source_receipt_hash TEXT,
    p_source_contract_hash TEXT,
    p_projection_artifact_hash TEXT,
    p_selection_binding_hash TEXT,
    p_proof_input_hash TEXT,
    p_proof_packet_hash TEXT,
    p_reward_set_hash TEXT,
    p_pit_dataset_manifest_hash TEXT,
    p_after_cost_label_set_hash TEXT,
    p_evidence_set_hash TEXT,
    p_training_input_hash TEXT,
    p_training_key_hash TEXT,
    p_code_manifest_hash TEXT,
    p_training_config_hash TEXT,
    p_canonical_payload JSONB
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $v158_receipt_writer$
DECLARE
    v_no_authority CONSTANT JSONB := '{
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
    }'::jsonb;
    v_zero_counters CONSTANT JSONB := '{
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
    }'::jsonb;
    v_inserted TEXT;
    v_existing learning.alr_qualified_training_receipts%ROWTYPE;
    v_status TEXT;
BEGIN
    IF session_user <> 'alr_challenger_trainer_caller' OR current_user <> 'alr_challenger_writer' THEN
        RAISE EXCEPTION 'V158 receipt writer session identity rejected';
    END IF;
    IF current_setting('session_replication_role') <> 'origin' THEN
        RAISE EXCEPTION 'V158 receipt writer requires session_replication_role=origin';
    END IF;
    IF jsonb_typeof(p_canonical_payload) IS DISTINCT FROM 'object' OR p_canonical_payload->>'schema_version' IS DISTINCT FROM
            'alr_qualified_training_receipt_v1' OR p_canonical_payload->>'durable_receipt_hash' IS DISTINCT FROM
            p_durable_receipt_hash OR p_canonical_payload->>'source_receipt_hash' IS DISTINCT FROM
            p_source_receipt_hash OR p_canonical_payload->>'source_contract_hash' IS DISTINCT FROM
            p_source_contract_hash OR p_canonical_payload->>'projection_artifact_hash' IS DISTINCT FROM
            p_projection_artifact_hash OR p_canonical_payload->>'projection_artifact_kind' IS DISTINCT FROM
            'learning_target' OR p_canonical_payload->>'selection_binding_hash' IS DISTINCT FROM
            p_selection_binding_hash OR p_canonical_payload->>'proof_input_hash' IS DISTINCT FROM
            p_proof_input_hash OR p_canonical_payload->>'proof_packet_hash' IS DISTINCT FROM
            p_proof_packet_hash OR p_canonical_payload->>'reward_set_hash' IS DISTINCT FROM
            p_reward_set_hash OR p_canonical_payload->>'pit_dataset_manifest_hash' IS DISTINCT FROM
            p_pit_dataset_manifest_hash OR p_canonical_payload->>'after_cost_label_set_hash' IS DISTINCT FROM
            p_after_cost_label_set_hash OR p_canonical_payload->>'evidence_set_hash' IS DISTINCT FROM
            p_evidence_set_hash OR p_canonical_payload->>'training_input_hash' IS DISTINCT FROM
            p_training_input_hash OR p_canonical_payload->>'training_key_hash' IS DISTINCT FROM
            p_training_key_hash OR p_canonical_payload->>'code_manifest_hash' IS DISTINCT FROM
            p_code_manifest_hash OR p_canonical_payload->>'training_config_hash' IS DISTINCT FROM
            p_training_config_hash OR p_canonical_payload->>'receipt_status' IS DISTINCT FROM
            'QUALIFIED_INPUT_PERSISTED' OR p_canonical_payload->'training_allowed' IS DISTINCT FROM 'false'::jsonb OR p_canonical_payload->'model_training_performed' IS DISTINCT FROM
            'false'::jsonb OR p_canonical_payload->'registry_write_allowed' IS DISTINCT FROM
            'false'::jsonb OR p_canonical_payload->'runtime_or_exchange_attested' IS DISTINCT FROM
            'false'::jsonb OR p_canonical_payload->'no_authority' IS DISTINCT FROM v_no_authority OR p_canonical_payload->'authority_counters' IS DISTINCT FROM
            v_zero_counters OR COALESCE(p_canonical_payload->>'dataset_hash', '') !~
            '^[0-9a-f]{64}$' OR COALESCE(p_canonical_payload->>'row_ids_hash', '') !~
            '^[0-9a-f]{64}$' OR COALESCE(p_canonical_payload->>'split_hash', '') !~
            '^[0-9a-f]{64}$' OR COALESCE(p_canonical_payload->>'feature_schema_hash', '') !~
            '^[0-9a-f]{64}$' OR COALESCE(p_canonical_payload->>'label_schema_hash', '') !~
            '^[0-9a-f]{64}$' OR COALESCE(jsonb_typeof(p_canonical_payload->'training_rows'), '') <>
            'number' OR COALESCE(p_canonical_payload->>'training_rows', '') !~
            '^[1-9][0-9]{0,9}$' OR NOT p_canonical_payload ?& ARRAY[
            'schema_version', 'durable_receipt_hash', 'source_receipt_hash',
            'source_contract_hash', 'projection_artifact_hash',
            'projection_artifact_kind', 'selection_binding_hash',
            'proof_input_hash', 'proof_packet_hash', 'reward_set_hash',
            'pit_dataset_manifest_hash', 'after_cost_label_set_hash',
            'evidence_set_hash', 'training_input_hash', 'training_key_hash',
            'code_manifest_hash', 'training_config_hash', 'receipt_status',
            'training_allowed', 'model_training_performed',
            'registry_write_allowed', 'runtime_or_exchange_attested',
            'no_authority', 'authority_counters', 'dataset_hash',
            'row_ids_hash', 'split_hash', 'feature_schema_hash',
            'label_schema_hash', 'training_rows'
       ]::TEXT[] OR p_canonical_payload - ARRAY[
            'schema_version', 'durable_receipt_hash', 'source_receipt_hash',
            'source_contract_hash', 'projection_artifact_hash',
            'projection_artifact_kind', 'selection_binding_hash',
            'proof_input_hash', 'proof_packet_hash', 'reward_set_hash',
            'pit_dataset_manifest_hash', 'after_cost_label_set_hash',
            'evidence_set_hash', 'training_input_hash', 'training_key_hash',
            'code_manifest_hash', 'training_config_hash', 'receipt_status',
            'training_allowed', 'model_training_performed',
            'registry_write_allowed', 'runtime_or_exchange_attested',
            'no_authority', 'authority_counters', 'dataset_hash',
            'row_ids_hash', 'split_hash', 'feature_schema_hash',
            'label_schema_hash', 'training_rows'
       ]::TEXT[] <> '{}'::jsonb
    THEN
        RAISE EXCEPTION 'V158 receipt canonical payload mismatch';
    END IF;
    IF (p_canonical_payload->>'training_rows')::BIGINT > 2147483647 THEN
        RAISE EXCEPTION 'V158 receipt training_rows exceeds INTEGER range';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM learning.alr_artifact_nodes
        WHERE artifact_hash = p_projection_artifact_hash AND artifact_kind = 'learning_target'
    ) THEN
        RAISE EXCEPTION 'V158 qualified learning_target projection missing';
    END IF;
    INSERT INTO learning.alr_qualified_training_receipts (
        durable_receipt_hash, source_receipt_hash, source_contract_hash,
        projection_artifact_hash, selection_binding_hash, proof_input_hash,
        proof_packet_hash, reward_set_hash, pit_dataset_manifest_hash,
        after_cost_label_set_hash, evidence_set_hash, training_input_hash,
        training_key_hash, code_manifest_hash, training_config_hash,
        receipt_status, canonical_payload, no_authority, authority_counters
    ) VALUES (
        p_durable_receipt_hash, p_source_receipt_hash, p_source_contract_hash,
        p_projection_artifact_hash, p_selection_binding_hash, p_proof_input_hash,
        p_proof_packet_hash, p_reward_set_hash, p_pit_dataset_manifest_hash,
        p_after_cost_label_set_hash, p_evidence_set_hash, p_training_input_hash,
        p_training_key_hash, p_code_manifest_hash, p_training_config_hash,
        'QUALIFIED_INPUT_PERSISTED', p_canonical_payload, v_no_authority,
        v_zero_counters
    )
    ON CONFLICT DO NOTHING
    RETURNING durable_receipt_hash INTO v_inserted;
    v_status := CASE WHEN v_inserted IS NULL THEN 'DUPLICATE' ELSE 'PERSISTED' END;
    SELECT r.* INTO v_existing
    FROM learning.alr_qualified_training_receipts AS r
    WHERE r.durable_receipt_hash = p_durable_receipt_hash OR r.training_key_hash = p_training_key_hash OR (r.source_receipt_hash = p_source_receipt_hash AND r.training_key_hash = p_training_key_hash)
    ORDER BY (r.durable_receipt_hash = p_durable_receipt_hash) DESC
    LIMIT 1;
    IF NOT FOUND OR v_existing.durable_receipt_hash IS DISTINCT FROM p_durable_receipt_hash OR v_existing.source_receipt_hash IS DISTINCT FROM p_source_receipt_hash OR v_existing.source_contract_hash IS DISTINCT FROM p_source_contract_hash OR v_existing.projection_artifact_hash IS DISTINCT FROM p_projection_artifact_hash OR v_existing.selection_binding_hash IS DISTINCT FROM p_selection_binding_hash OR v_existing.proof_input_hash IS DISTINCT FROM p_proof_input_hash OR v_existing.proof_packet_hash IS DISTINCT FROM p_proof_packet_hash OR v_existing.reward_set_hash IS DISTINCT FROM p_reward_set_hash OR v_existing.pit_dataset_manifest_hash IS DISTINCT FROM p_pit_dataset_manifest_hash OR v_existing.after_cost_label_set_hash IS DISTINCT FROM p_after_cost_label_set_hash OR v_existing.evidence_set_hash IS DISTINCT FROM p_evidence_set_hash OR v_existing.training_input_hash IS DISTINCT FROM p_training_input_hash OR v_existing.training_key_hash IS DISTINCT FROM p_training_key_hash OR v_existing.code_manifest_hash IS DISTINCT FROM p_code_manifest_hash OR v_existing.training_config_hash IS DISTINCT FROM p_training_config_hash OR v_existing.receipt_status <> 'QUALIFIED_INPUT_PERSISTED' OR v_existing.canonical_payload IS DISTINCT FROM p_canonical_payload OR v_existing.no_authority IS DISTINCT FROM v_no_authority OR v_existing.authority_counters IS DISTINCT FROM v_zero_counters THEN
        RAISE EXCEPTION 'V158 receipt replay conflict';
    END IF;
    RETURN jsonb_build_object(
        'status', v_status,
        'receipt', to_jsonb(v_existing)
    );
END
$v158_receipt_writer$;
-- Fixed result writer; filesystem durability precedes the database transaction.
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
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $v158_result_writer$
DECLARE
    v_no_authority CONSTANT JSONB := '{
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
    }'::jsonb;
    v_run_counters CONSTANT JSONB := '{
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
      "model_fit_count": 1
    }'::jsonb;
    v_receipt learning.alr_qualified_training_receipts%ROWTYPE;
    v_run learning.alr_challenger_training_runs%ROWTYPE;
    v_registry learning.alr_challenger_registry%ROWTYPE;
    v_inserted TEXT;
    v_set_hash TEXT;
    v_run_payload JSONB;
    v_registry_payload JSONB;
    v_artifacts JSONB;
    v_exact_count INTEGER;
    v_total_count INTEGER;
BEGIN
    IF session_user <> 'alr_challenger_trainer_caller' OR current_user <> 'alr_challenger_writer' THEN
        RAISE EXCEPTION 'V158 result writer session identity rejected';
    END IF;
    IF current_setting('session_replication_role') <> 'origin' THEN
        RAISE EXCEPTION 'V158 result writer requires session_replication_role=origin';
    END IF;
    SELECT r.* INTO v_receipt
    FROM learning.alr_qualified_training_receipts AS r
    WHERE r.durable_receipt_hash = p_durable_receipt_hash AND r.training_key_hash = p_training_key_hash;
    IF NOT FOUND OR v_receipt.code_manifest_hash <> p_actual_code_manifest_hash OR v_receipt.training_config_hash <> p_actual_training_config_hash OR v_receipt.canonical_payload->>'dataset_hash' IS DISTINCT FROM
            p_actual_dataset_hash OR v_receipt.canonical_payload->>'row_ids_hash' IS DISTINCT FROM
            p_actual_row_ids_hash OR v_receipt.canonical_payload->>'split_hash' IS DISTINCT FROM
            p_actual_split_hash OR v_receipt.canonical_payload->>'feature_schema_hash' IS DISTINCT FROM
            p_actual_feature_schema_hash OR v_receipt.canonical_payload->>'label_schema_hash' IS DISTINCT FROM
            p_actual_label_schema_hash OR (v_receipt.canonical_payload->>'training_rows')::INTEGER <>
            p_actual_training_rows THEN
        RAISE EXCEPTION 'V158 exact receipt lineage mismatch';
    END IF;
    IF p_q10_artifact_hash = p_q50_artifact_hash OR p_q10_artifact_hash = p_q90_artifact_hash OR p_q50_artifact_hash = p_q90_artifact_hash THEN
        RAISE EXCEPTION 'V158 artifact hashes must be distinct';
    END IF;
    v_set_hash := pg_catalog.encode(
        public.digest(
            pg_catalog.convert_to(
                pg_catalog.format(
                    E'q10=%s\nq50=%s\nq90=%s\n',
                    p_q10_artifact_hash,
                    p_q50_artifact_hash,
                    p_q90_artifact_hash
                ),
                'UTF8'::pg_catalog.name
            ),
            'sha256'::pg_catalog.text
        ),
        'hex'::pg_catalog.text
    );
    IF v_set_hash IS DISTINCT FROM p_model_artifact_set_hash THEN
        RAISE EXCEPTION 'V158 artifact set hash mismatch';
    END IF;
    IF p_q10_artifact_path <> 'runs/' || p_training_run_hash || '/q10.onnx' OR p_q50_artifact_path <> 'runs/' || p_training_run_hash || '/q50.onnx' OR p_q90_artifact_path <> 'runs/' || p_training_run_hash || '/q90.onnx' THEN
        RAISE EXCEPTION 'V158 immutable artifact path mismatch';
    END IF;
    v_run_payload := jsonb_build_object(
        'schema_version', 'alr_challenger_training_result_v1',
        'training_run_hash', p_training_run_hash,
        'durable_receipt_hash', p_durable_receipt_hash,
        'training_key_hash', p_training_key_hash,
        'source_head', p_source_head,
        'actual_dataset_hash', p_actual_dataset_hash,
        'actual_row_ids_hash', p_actual_row_ids_hash,
        'actual_split_hash', p_actual_split_hash,
        'actual_code_manifest_hash', p_actual_code_manifest_hash,
        'actual_training_config_hash', p_actual_training_config_hash,
        'actual_feature_schema_hash', p_actual_feature_schema_hash,
        'actual_label_schema_hash', p_actual_label_schema_hash,
        'model_schema_version', p_model_schema_version,
        'actual_training_rows', p_actual_training_rows,
        'model_artifact_set_hash', p_model_artifact_set_hash,
        'metrics_hash', p_metrics_hash,
        'resource_usage_hash', p_resource_usage_hash,
        'fit_started_at', pg_catalog.to_char(
            p_fit_started_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
        ),
        'fit_completed_at', pg_catalog.to_char(
            p_fit_completed_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
        ),
        'run_status', 'TRAINING_PERFORMED',
        'model_training_performed', TRUE,
        'no_authority', v_no_authority,
        'authority_counters', v_run_counters
    );
    v_registry_payload := jsonb_build_object(
        'schema_version', 'alr_challenger_registry_entry_v1',
        'challenger_hash', p_challenger_hash,
        'training_run_hash', p_training_run_hash,
        'training_key_hash', p_training_key_hash,
        'model_artifact_set_hash', p_model_artifact_set_hash,
        'registry_status', 'NOT_SERVING',
        'serving_allowed', FALSE,
        'promotion_allowed', FALSE,
        'latest_pointer_allowed', FALSE,
        'symlink_allowed', FALSE
    );
    SET CONSTRAINTS
        learning.alr_challenger_run_complete_ct_v1,
        learning.alr_challenger_artifact_complete_ct_v1,
        learning.alr_challenger_registry_complete_ct_v1
        DEFERRED;
    INSERT INTO learning.alr_challenger_training_runs (
        training_run_hash, durable_receipt_hash, training_key_hash, source_head,
        actual_dataset_hash, actual_row_ids_hash, actual_split_hash,
        actual_code_manifest_hash, actual_training_config_hash,
        actual_feature_schema_hash, actual_label_schema_hash,
        model_schema_version, actual_training_rows, model_artifact_set_hash,
        metrics_hash, resource_usage_hash, run_status,
        model_training_performed, canonical_payload, no_authority,
        authority_counters, fit_started_at, fit_completed_at
    ) VALUES (
        p_training_run_hash, p_durable_receipt_hash, p_training_key_hash,
        p_source_head, p_actual_dataset_hash, p_actual_row_ids_hash,
        p_actual_split_hash, p_actual_code_manifest_hash,
        p_actual_training_config_hash, p_actual_feature_schema_hash,
        p_actual_label_schema_hash, p_model_schema_version,
        p_actual_training_rows, p_model_artifact_set_hash, p_metrics_hash,
        p_resource_usage_hash, 'TRAINING_PERFORMED', TRUE, v_run_payload,
        v_no_authority, v_run_counters, p_fit_started_at, p_fit_completed_at
    )
    ON CONFLICT DO NOTHING
    RETURNING training_run_hash INTO v_inserted;
    IF NOT FOUND OR v_inserted IS NULL THEN
        SELECT r.* INTO v_run
        FROM learning.alr_challenger_training_runs AS r
        WHERE r.training_run_hash = p_training_run_hash OR r.training_key_hash = p_training_key_hash
        ORDER BY (r.training_run_hash = p_training_run_hash) DESC
        LIMIT 1;
        IF NOT FOUND OR v_run.training_run_hash IS DISTINCT FROM p_training_run_hash OR v_run.durable_receipt_hash IS DISTINCT FROM p_durable_receipt_hash OR v_run.training_key_hash IS DISTINCT FROM p_training_key_hash OR v_run.source_head IS DISTINCT FROM p_source_head OR v_run.actual_dataset_hash IS DISTINCT FROM p_actual_dataset_hash OR v_run.actual_row_ids_hash IS DISTINCT FROM p_actual_row_ids_hash OR v_run.actual_split_hash IS DISTINCT FROM p_actual_split_hash OR v_run.actual_code_manifest_hash IS DISTINCT FROM p_actual_code_manifest_hash OR v_run.actual_training_config_hash IS DISTINCT FROM p_actual_training_config_hash OR v_run.actual_feature_schema_hash IS DISTINCT FROM p_actual_feature_schema_hash OR v_run.actual_label_schema_hash IS DISTINCT FROM p_actual_label_schema_hash OR v_run.model_schema_version IS DISTINCT FROM p_model_schema_version OR v_run.actual_training_rows IS DISTINCT FROM p_actual_training_rows OR v_run.model_artifact_set_hash IS DISTINCT FROM p_model_artifact_set_hash OR v_run.metrics_hash IS DISTINCT FROM p_metrics_hash OR v_run.resource_usage_hash IS DISTINCT FROM p_resource_usage_hash OR v_run.run_status <> 'TRAINING_PERFORMED' OR v_run.model_training_performed IS NOT TRUE OR v_run.canonical_payload IS DISTINCT FROM v_run_payload OR v_run.no_authority IS DISTINCT FROM v_no_authority OR v_run.authority_counters IS DISTINCT FROM v_run_counters OR v_run.fit_started_at IS DISTINCT FROM p_fit_started_at OR v_run.fit_completed_at IS DISTINCT FROM p_fit_completed_at THEN
            RAISE EXCEPTION 'V158 result replay conflict';
        END IF;
        SELECT count(*), count(*) FILTER (WHERE
            (quantile = 'q10' AND artifact_hash = p_q10_artifact_hash AND artifact_path = p_q10_artifact_path AND artifact_size_bytes = p_q10_artifact_size_bytes) OR (quantile = 'q50' AND artifact_hash = p_q50_artifact_hash AND artifact_path = p_q50_artifact_path AND artifact_size_bytes = p_q50_artifact_size_bytes) OR (quantile = 'q90' AND artifact_hash = p_q90_artifact_hash AND artifact_path = p_q90_artifact_path AND artifact_size_bytes = p_q90_artifact_size_bytes)
        ) INTO v_total_count, v_exact_count
        FROM learning.alr_challenger_model_artifacts
        WHERE training_run_hash = p_training_run_hash AND training_key_hash = p_training_key_hash AND model_artifact_set_hash = p_model_artifact_set_hash AND feature_schema_hash = p_actual_feature_schema_hash AND model_schema_version = p_model_schema_version AND artifact_format = 'onnx' AND symlink_created IS FALSE AND serving_visible IS FALSE;
        IF v_total_count <> 3 OR v_exact_count <> 3 THEN
            RAISE EXCEPTION 'V158 result replay conflict: artifact bundle mismatch';
        END IF;
        SELECT g.* INTO v_registry
        FROM learning.alr_challenger_registry AS g
        WHERE g.training_run_hash = p_training_run_hash;
        IF NOT FOUND OR v_registry.challenger_hash IS DISTINCT FROM p_challenger_hash OR v_registry.training_key_hash IS DISTINCT FROM p_training_key_hash OR v_registry.model_artifact_set_hash IS DISTINCT FROM p_model_artifact_set_hash OR v_registry.registry_status <> 'NOT_SERVING' OR v_registry.serving_allowed IS NOT FALSE OR v_registry.promotion_allowed IS NOT FALSE OR v_registry.latest_pointer_allowed IS NOT FALSE OR v_registry.symlink_allowed IS NOT FALSE OR v_registry.canonical_payload IS DISTINCT FROM v_registry_payload THEN
            RAISE EXCEPTION 'V158 result replay conflict: registry mismatch';
        END IF;
    ELSE
        INSERT INTO learning.alr_challenger_model_artifacts (
            artifact_hash, training_run_hash, training_key_hash,
            model_artifact_set_hash, quantile, artifact_format, artifact_path,
            artifact_size_bytes, feature_schema_hash, model_schema_version,
            symlink_created, serving_visible
        ) VALUES (
            p_q10_artifact_hash, p_training_run_hash, p_training_key_hash,
            p_model_artifact_set_hash, 'q10', 'onnx', p_q10_artifact_path,
            p_q10_artifact_size_bytes, p_actual_feature_schema_hash,
            p_model_schema_version, FALSE, FALSE
        );
        INSERT INTO learning.alr_challenger_model_artifacts (
            artifact_hash, training_run_hash, training_key_hash,
            model_artifact_set_hash, quantile, artifact_format, artifact_path,
            artifact_size_bytes, feature_schema_hash, model_schema_version,
            symlink_created, serving_visible
        ) VALUES (
            p_q50_artifact_hash, p_training_run_hash, p_training_key_hash,
            p_model_artifact_set_hash, 'q50', 'onnx', p_q50_artifact_path,
            p_q50_artifact_size_bytes, p_actual_feature_schema_hash,
            p_model_schema_version, FALSE, FALSE
        );
        INSERT INTO learning.alr_challenger_model_artifacts (
            artifact_hash, training_run_hash, training_key_hash,
            model_artifact_set_hash, quantile, artifact_format, artifact_path,
            artifact_size_bytes, feature_schema_hash, model_schema_version,
            symlink_created, serving_visible
        ) VALUES (
            p_q90_artifact_hash, p_training_run_hash, p_training_key_hash,
            p_model_artifact_set_hash, 'q90', 'onnx', p_q90_artifact_path,
            p_q90_artifact_size_bytes, p_actual_feature_schema_hash,
            p_model_schema_version, FALSE, FALSE
        );
        INSERT INTO learning.alr_challenger_registry (
            challenger_hash, training_run_hash, training_key_hash,
            model_artifact_set_hash, registry_status, serving_allowed,
            promotion_allowed, latest_pointer_allowed, symlink_allowed,
            canonical_payload
        ) VALUES (
            p_challenger_hash, p_training_run_hash, p_training_key_hash,
            p_model_artifact_set_hash, 'NOT_SERVING', FALSE, FALSE, FALSE,
            FALSE, v_registry_payload
        );
    END IF;
    SET CONSTRAINTS
        learning.alr_challenger_run_complete_ct_v1,
        learning.alr_challenger_artifact_complete_ct_v1,
        learning.alr_challenger_registry_complete_ct_v1
        IMMEDIATE;
    SELECT r.* INTO v_run
    FROM learning.alr_challenger_training_runs AS r
    WHERE r.training_run_hash = p_training_run_hash AND r.training_key_hash = p_training_key_hash;
    SELECT g.* INTO v_registry
    FROM learning.alr_challenger_registry AS g
    WHERE g.training_run_hash = p_training_run_hash;
    SELECT jsonb_agg(to_jsonb(a) ORDER BY CASE quantile
               WHEN 'q10' THEN 1 WHEN 'q50' THEN 2 ELSE 3 END)
      INTO v_artifacts
      FROM learning.alr_challenger_model_artifacts AS a
     WHERE a.training_run_hash = p_training_run_hash;
    RETURN jsonb_build_object(
        'status', CASE WHEN v_inserted IS NULL THEN 'DUPLICATE' ELSE 'PERSISTED' END,
        'run', to_jsonb(v_run),
        'artifacts', v_artifacts,
        'registry', to_jsonb(v_registry)
    );
END
$v158_result_writer$;
CREATE OR REPLACE FUNCTION learning.read_alr_qualified_training_receipt_v1(
    p_durable_receipt_hash TEXT,
    p_training_key_hash TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $v158_receipt_reader$
DECLARE
    v_receipt learning.alr_qualified_training_receipts%ROWTYPE;
    v_conflicts INTEGER;
BEGIN
    IF session_user <> 'alr_challenger_trainer_caller' OR current_user <> 'alr_challenger_writer' THEN
        RAISE EXCEPTION 'V158 receipt reader session identity rejected';
    END IF;
    IF current_setting('session_replication_role') <> 'origin' THEN
        RAISE EXCEPTION 'V158 receipt reader requires session_replication_role=origin';
    END IF;
    SELECT r.* INTO v_receipt
    FROM learning.alr_qualified_training_receipts AS r
    WHERE r.durable_receipt_hash = p_durable_receipt_hash AND r.training_key_hash = p_training_key_hash;
    IF FOUND THEN
        RETURN jsonb_build_object('status', 'FOUND', 'receipt', to_jsonb(v_receipt));
    END IF;
    SELECT count(*) INTO v_conflicts
    FROM learning.alr_qualified_training_receipts AS r
    WHERE r.durable_receipt_hash = p_durable_receipt_hash OR r.training_key_hash = p_training_key_hash;
    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION 'V158 receipt PARTIAL_OR_DIVERGENT';
    END IF;
    RETURN jsonb_build_object('status', 'NOT_FOUND', 'receipt', NULL);
END
$v158_receipt_reader$;
CREATE OR REPLACE FUNCTION learning.read_alr_challenger_training_result_v1(
    p_training_run_hash TEXT,
    p_training_key_hash TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $v158_result_reader$
DECLARE
    v_run learning.alr_challenger_training_runs%ROWTYPE;
    v_registry learning.alr_challenger_registry%ROWTYPE;
    v_artifacts JSONB;
    v_artifact_count INTEGER;
    v_registry_count INTEGER;
    v_conflicts INTEGER;
    v_set_hash TEXT;
BEGIN
    IF session_user <> 'alr_challenger_trainer_caller' OR current_user <> 'alr_challenger_writer' THEN
        RAISE EXCEPTION 'V158 result reader session identity rejected';
    END IF;
    IF current_setting('session_replication_role') <> 'origin' THEN
        RAISE EXCEPTION 'V158 result reader requires session_replication_role=origin';
    END IF;
    SELECT r.* INTO v_run
    FROM learning.alr_challenger_training_runs AS r
    WHERE r.training_run_hash = p_training_run_hash AND r.training_key_hash = p_training_key_hash;
    IF NOT FOUND THEN
        SELECT (
            SELECT count(*) FROM learning.alr_challenger_training_runs
             WHERE training_run_hash = p_training_run_hash OR training_key_hash = p_training_key_hash
        ) + (
            SELECT count(*) FROM learning.alr_challenger_model_artifacts
             WHERE training_run_hash = p_training_run_hash OR training_key_hash = p_training_key_hash
        ) + (
            SELECT count(*) FROM learning.alr_challenger_registry
             WHERE training_run_hash = p_training_run_hash OR training_key_hash = p_training_key_hash
        ) INTO v_conflicts;
        IF v_conflicts <> 0 THEN
            RAISE EXCEPTION 'V158 result PARTIAL_OR_DIVERGENT';
        END IF;
        RETURN jsonb_build_object('status', 'NOT_FOUND');
    END IF;
    SELECT count(*),
           jsonb_agg(to_jsonb(a) ORDER BY CASE quantile
               WHEN 'q10' THEN 1 WHEN 'q50' THEN 2 ELSE 3 END),
           pg_catalog.encode(
               public.digest(
                   pg_catalog.convert_to(
                       pg_catalog.format(
                           E'q10=%s\nq50=%s\nq90=%s\n',
                           max(artifact_hash) FILTER (WHERE quantile = 'q10'),
                           max(artifact_hash) FILTER (WHERE quantile = 'q50'),
                           max(artifact_hash) FILTER (WHERE quantile = 'q90')
                       ),
                       'UTF8'::pg_catalog.name
                   ),
                   'sha256'::pg_catalog.text
               ),
               'hex'::pg_catalog.text
           )
      INTO v_artifact_count, v_artifacts, v_set_hash
      FROM learning.alr_challenger_model_artifacts AS a
     WHERE a.training_run_hash = p_training_run_hash AND a.training_key_hash = p_training_key_hash AND a.model_artifact_set_hash = v_run.model_artifact_set_hash AND a.feature_schema_hash = v_run.actual_feature_schema_hash AND a.model_schema_version = v_run.model_schema_version;
    SELECT count(*) INTO v_registry_count
    FROM learning.alr_challenger_registry AS g
    WHERE g.training_run_hash = p_training_run_hash AND g.training_key_hash = p_training_key_hash AND g.model_artifact_set_hash = v_run.model_artifact_set_hash;
    IF v_artifact_count <> 3 OR v_set_hash IS DISTINCT FROM v_run.model_artifact_set_hash OR v_registry_count <> 1 THEN
        RAISE EXCEPTION 'V158 result PARTIAL_OR_DIVERGENT';
    END IF;
    SELECT g.* INTO v_registry
    FROM learning.alr_challenger_registry AS g
    WHERE g.training_run_hash = p_training_run_hash AND g.training_key_hash = p_training_key_hash AND g.model_artifact_set_hash = v_run.model_artifact_set_hash;
    RETURN jsonb_build_object(
        'status', 'FOUND',
        'run', to_jsonb(v_run),
        'artifacts', v_artifacts,
        'registry', to_jsonb(v_registry)
    );
END
$v158_result_reader$;
CREATE OR REPLACE FUNCTION learning.alr_v158_assert_complete_result()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $v158_complete_trigger$
DECLARE
    v_run_hash TEXT;
    v_run learning.alr_challenger_training_runs%ROWTYPE;
    v_artifact_count INTEGER;
    v_quantile_count INTEGER;
    v_hash_count INTEGER;
    v_schema_match_count INTEGER;
    v_registry_count INTEGER;
    v_set_hash TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_run_hash := OLD.training_run_hash;
    ELSE
        v_run_hash := NEW.training_run_hash;
    END IF;
    IF session_user <> 'alr_challenger_trainer_caller' OR current_user <> 'alr_challenger_writer' THEN
        RAISE EXCEPTION 'V158 completeness trigger session identity rejected';
    END IF;
    IF current_setting('session_replication_role') <> 'origin' THEN
        RAISE EXCEPTION 'V158 completeness trigger requires session_replication_role=origin';
    END IF;
    SELECT r.* INTO v_run
    FROM learning.alr_challenger_training_runs AS r
    WHERE r.training_run_hash = v_run_hash;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'V158 complete result invariant: run missing';
    END IF;
    SELECT count(*), count(DISTINCT quantile), count(DISTINCT artifact_hash),
           count(*) FILTER (
               WHERE training_key_hash = v_run.training_key_hash AND model_artifact_set_hash = v_run.model_artifact_set_hash AND feature_schema_hash = v_run.actual_feature_schema_hash AND model_schema_version = v_run.model_schema_version AND artifact_format = 'onnx' AND symlink_created IS FALSE AND serving_visible IS FALSE
           ),
           pg_catalog.encode(
               public.digest(
                   pg_catalog.convert_to(
                       pg_catalog.format(
                           E'q10=%s\nq50=%s\nq90=%s\n',
                           max(artifact_hash) FILTER (WHERE quantile = 'q10'),
                           max(artifact_hash) FILTER (WHERE quantile = 'q50'),
                           max(artifact_hash) FILTER (WHERE quantile = 'q90')
                       ),
                       'UTF8'::pg_catalog.name
                   ),
                   'sha256'::pg_catalog.text
               ),
               'hex'::pg_catalog.text
           )
      INTO v_artifact_count, v_quantile_count, v_hash_count,
           v_schema_match_count, v_set_hash
      FROM learning.alr_challenger_model_artifacts
     WHERE training_run_hash = v_run_hash;
    IF v_artifact_count <> 3 OR v_quantile_count <> 3 OR v_hash_count <> 3 OR v_schema_match_count <> 3 OR v_set_hash IS DISTINCT FROM v_run.model_artifact_set_hash THEN
        RAISE EXCEPTION
            'V158 complete result invariant: exact q10/q50/q90 bundle required';
    END IF;
    SELECT count(*) INTO v_registry_count
    FROM learning.alr_challenger_registry AS g
    WHERE g.training_run_hash = v_run_hash AND g.training_key_hash = v_run.training_key_hash AND g.model_artifact_set_hash = v_run.model_artifact_set_hash AND g.registry_status = 'NOT_SERVING' AND g.serving_allowed IS FALSE AND g.promotion_allowed IS FALSE AND g.latest_pointer_allowed IS FALSE AND g.symlink_allowed IS FALSE;
    IF v_registry_count <> 1 THEN
        RAISE EXCEPTION
            'V158 complete result invariant: exact NOT_SERVING registry row required';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END
$v158_complete_trigger$;
CREATE OR REPLACE FUNCTION learning.alr_v158_reject_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $v158_immutable_trigger$
BEGIN
    IF current_user <> 'alr_challenger_writer' THEN
        RAISE EXCEPTION 'V158 immutable trigger owner mismatch';
    END IF;
    IF current_setting('session_replication_role') <> 'origin' THEN
        RAISE EXCEPTION 'V158 immutable trigger requires session_replication_role=origin';
    END IF;
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        RAISE EXCEPTION 'V158 append-only table rejects %', TG_OP;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END
$v158_immutable_trigger$;
-- Only fixed functions are owned by the membership-free NOLOGIN role.
ALTER FUNCTION learning.persist_alr_qualified_training_receipt_v1(
    TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
    TEXT, TEXT, TEXT, JSONB
) OWNER TO alr_challenger_writer;
ALTER FUNCTION learning.persist_alr_challenger_training_result_v1(
    TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
    INTEGER, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ,
    TEXT, TEXT, BIGINT, TEXT, TEXT, BIGINT, TEXT, TEXT, BIGINT, TEXT
) OWNER TO alr_challenger_writer;
ALTER FUNCTION learning.read_alr_qualified_training_receipt_v1(TEXT, TEXT)
    OWNER TO alr_challenger_writer;
ALTER FUNCTION learning.read_alr_challenger_training_result_v1(TEXT, TEXT)
    OWNER TO alr_challenger_writer;
ALTER FUNCTION learning.alr_v158_assert_complete_result()
    OWNER TO alr_challenger_writer;
ALTER FUNCTION learning.alr_v158_reject_mutation()
    OWNER TO alr_challenger_writer;
-- PG16 constraint triggers are create-if-absent; Guard B rejects drift.
DO $v158_create_triggers$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'learning.alr_challenger_training_runs'::regclass AND tgname = 'alr_challenger_run_complete_ct_v1' AND tgisinternal IS FALSE
    ) THEN
        EXECUTE $trigger$
            CREATE CONSTRAINT TRIGGER alr_challenger_run_complete_ct_v1
            AFTER INSERT OR UPDATE OR DELETE
            ON learning.alr_challenger_training_runs
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION learning.alr_v158_assert_complete_result()
        $trigger$;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'learning.alr_challenger_model_artifacts'::regclass AND tgname = 'alr_challenger_artifact_complete_ct_v1' AND tgisinternal IS FALSE
    ) THEN
        EXECUTE $trigger$
            CREATE CONSTRAINT TRIGGER alr_challenger_artifact_complete_ct_v1
            AFTER INSERT OR UPDATE OR DELETE
            ON learning.alr_challenger_model_artifacts
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION learning.alr_v158_assert_complete_result()
        $trigger$;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'learning.alr_challenger_registry'::regclass AND tgname = 'alr_challenger_registry_complete_ct_v1' AND tgisinternal IS FALSE
    ) THEN
        EXECUTE $trigger$
            CREATE CONSTRAINT TRIGGER alr_challenger_registry_complete_ct_v1
            AFTER INSERT OR UPDATE OR DELETE
            ON learning.alr_challenger_registry
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION learning.alr_v158_assert_complete_result()
        $trigger$;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'learning.alr_qualified_training_receipts'::regclass AND tgname = 'alr_v158_immutable_alr_qualified_training_receipts_trg' AND tgisinternal IS FALSE
    ) THEN
        EXECUTE $trigger$
            CREATE TRIGGER alr_v158_immutable_alr_qualified_training_receipts_trg
            BEFORE UPDATE OR DELETE
            ON learning.alr_qualified_training_receipts
            FOR EACH ROW
            EXECUTE FUNCTION learning.alr_v158_reject_mutation()
        $trigger$;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'learning.alr_challenger_training_runs'::regclass AND tgname = 'alr_v158_immutable_alr_challenger_training_runs_trg' AND tgisinternal IS FALSE
    ) THEN
        EXECUTE $trigger$
            CREATE TRIGGER alr_v158_immutable_alr_challenger_training_runs_trg
            BEFORE UPDATE OR DELETE
            ON learning.alr_challenger_training_runs
            FOR EACH ROW
            EXECUTE FUNCTION learning.alr_v158_reject_mutation()
        $trigger$;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'learning.alr_challenger_model_artifacts'::regclass AND tgname = 'alr_v158_immutable_alr_challenger_model_artifacts_trg' AND tgisinternal IS FALSE
    ) THEN
        EXECUTE $trigger$
            CREATE TRIGGER alr_v158_immutable_alr_challenger_model_artifacts_trg
            BEFORE UPDATE OR DELETE
            ON learning.alr_challenger_model_artifacts
            FOR EACH ROW
            EXECUTE FUNCTION learning.alr_v158_reject_mutation()
        $trigger$;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'learning.alr_challenger_registry'::regclass AND tgname = 'alr_v158_immutable_alr_challenger_registry_trg' AND tgisinternal IS FALSE
    ) THEN
        EXECUTE $trigger$
            CREATE TRIGGER alr_v158_immutable_alr_challenger_registry_trg
            BEFORE UPDATE OR DELETE
            ON learning.alr_challenger_registry
            FOR EACH ROW
            EXECUTE FUNCTION learning.alr_v158_reject_mutation()
        $trigger$;
    END IF;
END
$v158_create_triggers$;
REVOKE ALL ON TABLE
    learning.alr_qualified_training_receipts,
    learning.alr_challenger_training_runs,
    learning.alr_challenger_model_artifacts,
    learning.alr_challenger_registry
FROM PUBLIC, alr_challenger_trainer_caller, alr_challenger_writer;
GRANT SELECT, INSERT ON TABLE
    learning.alr_qualified_training_receipts,
    learning.alr_challenger_training_runs,
    learning.alr_challenger_model_artifacts,
    learning.alr_challenger_registry
TO alr_challenger_writer;
GRANT SELECT ON TABLE learning.alr_artifact_nodes TO alr_challenger_writer;
REVOKE ALL ON FUNCTION
    learning.persist_alr_qualified_training_receipt_v1(
        TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
        TEXT, TEXT, TEXT, TEXT, JSONB
    ),
    learning.persist_alr_challenger_training_result_v1(
        TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
        TEXT, INTEGER, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ,
        TEXT, TEXT, BIGINT, TEXT, TEXT, BIGINT, TEXT, TEXT, BIGINT, TEXT
    ),
    learning.read_alr_qualified_training_receipt_v1(TEXT, TEXT),
    learning.read_alr_challenger_training_result_v1(TEXT, TEXT),
    learning.alr_v158_assert_complete_result(),
    learning.alr_v158_reject_mutation()
FROM PUBLIC, alr_challenger_trainer_caller;
GRANT EXECUTE ON FUNCTION
    learning.persist_alr_qualified_training_receipt_v1(
        TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
        TEXT, TEXT, TEXT, TEXT, JSONB
    ),
    learning.persist_alr_challenger_training_result_v1(
        TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
        TEXT, INTEGER, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ,
        TEXT, TEXT, BIGINT, TEXT, TEXT, BIGINT, TEXT, TEXT, BIGINT, TEXT
    ),
    learning.read_alr_qualified_training_receipt_v1(TEXT, TEXT),
    learning.read_alr_challenger_training_result_v1(TEXT, TEXT)
TO alr_challenger_trainer_caller;
REVOKE CREATE ON SCHEMA learning
FROM PUBLIC, alr_challenger_writer, alr_challenger_trainer_caller;
REVOKE CREATE ON SCHEMA public
FROM alr_challenger_writer, alr_challenger_trainer_caller;
GRANT USAGE ON SCHEMA learning TO alr_challenger_trainer_caller;
GRANT USAGE ON SCHEMA learning TO alr_challenger_writer;
GRANT USAGE ON SCHEMA public TO alr_challenger_writer;
GRANT EXECUTE ON FUNCTION public.digest(bytea, text) TO alr_challenger_writer;
-- Generic identities receive no V158 table or function privilege.
DO $v158_generic_acl$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'REVOKE ALL ON TABLE learning.alr_qualified_training_receipts, learning.alr_challenger_training_runs, learning.alr_challenger_model_artifacts, learning.alr_challenger_registry FROM trading_ai';
        EXECUTE 'REVOKE ALL ON FUNCTION learning.persist_alr_qualified_training_receipt_v1(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,JSONB), learning.persist_alr_challenger_training_result_v1(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,TEXT,BIGINT,TEXT,TEXT,BIGINT,TEXT,TEXT,BIGINT,TEXT), learning.read_alr_qualified_training_receipt_v1(TEXT,TEXT), learning.read_alr_challenger_training_result_v1(TEXT,TEXT), learning.alr_v158_assert_complete_result(), learning.alr_v158_reject_mutation() FROM trading_ai';
        EXECUTE 'REVOKE CREATE ON SCHEMA learning FROM trading_ai';
        EXECUTE 'REVOKE SET ON PARAMETER session_replication_role FROM trading_ai';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'alr_shadow') THEN
        EXECUTE 'REVOKE ALL ON TABLE learning.alr_qualified_training_receipts, learning.alr_challenger_training_runs, learning.alr_challenger_model_artifacts, learning.alr_challenger_registry FROM alr_shadow';
        EXECUTE 'REVOKE ALL ON FUNCTION learning.persist_alr_qualified_training_receipt_v1(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,JSONB), learning.persist_alr_challenger_training_result_v1(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,TEXT,BIGINT,TEXT,TEXT,BIGINT,TEXT,TEXT,BIGINT,TEXT), learning.read_alr_qualified_training_receipt_v1(TEXT,TEXT), learning.read_alr_challenger_training_result_v1(TEXT,TEXT), learning.alr_v158_assert_complete_result(), learning.alr_v158_reject_mutation() FROM alr_shadow';
        EXECUTE 'REVOKE CREATE ON SCHEMA learning FROM alr_shadow';
        EXECUTE 'REVOKE SET ON PARAMETER session_replication_role FROM alr_shadow';
    END IF;
END
$v158_generic_acl$;
-- V158 Guard B: exact schema, replay arbiters, functions, owners, and triggers.
DO $v158_guard_b$
DECLARE
    v_spec RECORD;
    v_actual RECORD;
    v_oid OID;
    v_definition TEXT;
    v_count INTEGER;
BEGIN
    FOR v_spec IN SELECT * FROM (VALUES
      ('learning.alr_qualified_training_receipts',
       '1:durable_receipt_hash:text:true:-|2:source_receipt_hash:text:true:-|3:source_contract_hash:text:true:-|4:projection_artifact_hash:text:true:-|5:selection_binding_hash:text:true:-|6:proof_input_hash:text:true:-|7:proof_packet_hash:text:true:-|8:reward_set_hash:text:true:-|9:pit_dataset_manifest_hash:text:true:-|10:after_cost_label_set_hash:text:true:-|11:evidence_set_hash:text:true:-|12:training_input_hash:text:true:-|13:training_key_hash:text:true:-|14:code_manifest_hash:text:true:-|15:training_config_hash:text:true:-|16:receipt_status:text:true:-|17:canonical_payload:jsonb:true:-|18:no_authority:jsonb:true:-|19:authority_counters:jsonb:true:-|20:created_at:timestamp with time zone:true:CURRENT_TIMESTAMP'),
      ('learning.alr_challenger_training_runs',
       '1:training_run_hash:text:true:-|2:durable_receipt_hash:text:true:-|3:training_key_hash:text:true:-|4:source_head:text:true:-|5:actual_dataset_hash:text:true:-|6:actual_row_ids_hash:text:true:-|7:actual_split_hash:text:true:-|8:actual_code_manifest_hash:text:true:-|9:actual_training_config_hash:text:true:-|10:actual_feature_schema_hash:text:true:-|11:actual_label_schema_hash:text:true:-|12:model_schema_version:text:true:-|13:actual_training_rows:integer:true:-|14:model_artifact_set_hash:text:true:-|15:metrics_hash:text:true:-|16:resource_usage_hash:text:true:-|17:run_status:text:true:-|18:model_training_performed:boolean:true:-|19:canonical_payload:jsonb:true:-|20:no_authority:jsonb:true:-|21:authority_counters:jsonb:true:-|22:fit_started_at:timestamp with time zone:true:-|23:fit_completed_at:timestamp with time zone:true:-|24:created_at:timestamp with time zone:true:CURRENT_TIMESTAMP'),
      ('learning.alr_challenger_model_artifacts',
       '1:artifact_hash:text:true:-|2:training_run_hash:text:true:-|3:training_key_hash:text:true:-|4:model_artifact_set_hash:text:true:-|5:quantile:text:true:-|6:artifact_format:text:true:-|7:artifact_path:text:true:-|8:artifact_size_bytes:bigint:true:-|9:feature_schema_hash:text:true:-|10:model_schema_version:text:true:-|11:symlink_created:boolean:true:-|12:serving_visible:boolean:true:-|13:created_at:timestamp with time zone:true:CURRENT_TIMESTAMP'),
      ('learning.alr_challenger_registry',
       '1:challenger_hash:text:true:-|2:training_run_hash:text:true:-|3:training_key_hash:text:true:-|4:model_artifact_set_hash:text:true:-|5:registry_status:text:true:-|6:serving_allowed:boolean:true:-|7:promotion_allowed:boolean:true:-|8:latest_pointer_allowed:boolean:true:-|9:symlink_allowed:boolean:true:-|10:canonical_payload:jsonb:true:-|11:created_at:timestamp with time zone:true:CURRENT_TIMESTAMP')
    ) AS x(table_name,column_signature) LOOP
        IF NOT EXISTS (
          SELECT 1 FROM pg_class AS c JOIN pg_namespace AS n
            ON n.nspname='learning' AND c.relowner=n.nspowner
          WHERE c.oid=v_spec.table_name::regclass
            AND pg_get_userbyid(c.relowner)=current_user
            AND c.relkind='r' AND c.relpersistence='p'
            AND NOT c.relispartition AND NOT c.relrowsecurity
            AND NOT c.relforcerowsecurity AND NOT c.relhasrules
        ) OR EXISTS (
          SELECT 1 FROM pg_inherits
          WHERE inhrelid=v_spec.table_name::regclass
             OR inhparent=v_spec.table_name::regclass
        ) OR EXISTS (
          SELECT 1 FROM pg_policy WHERE polrelid=v_spec.table_name::regclass
        ) OR EXISTS (
          SELECT 1 FROM pg_index AS i
          WHERE i.indrelid=v_spec.table_name::regclass
            AND (i.indisunique OR i.indisexclusion)
            AND i.indisvalid AND i.indisready
            AND NOT EXISTS (
              SELECT 1 FROM pg_constraint AS c
              WHERE c.conrelid=v_spec.table_name::regclass
                AND c.conindid=i.indexrelid AND c.contype IN ('p','u')
            )
        ) THEN
            RAISE EXCEPTION
                'V158 Guard B FAIL: durable table posture mismatch: %',
                v_spec.table_name;
        END IF;
        SELECT string_agg(
          a.attnum::TEXT||':'||a.attname||':'||format_type(a.atttypid,a.atttypmod)
          ||':'||a.attnotnull::TEXT||':'||COALESCE(
            pg_get_expr(d.adbin,d.adrelid),'-'
          ), '|' ORDER BY a.attnum
        ) INTO v_definition
        FROM pg_attribute AS a LEFT JOIN pg_attrdef AS d
          ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE a.attrelid=v_spec.table_name::regclass AND a.attnum>0 AND NOT a.attisdropped;
        IF v_definition IS DISTINCT FROM v_spec.column_signature THEN
            RAISE EXCEPTION
                'V158 Guard B FAIL: exact column schema mismatch: %',
                v_spec.table_name;
        END IF;
    END LOOP;
    FOR v_spec IN
        SELECT * FROM (VALUES
            ('learning.alr_qualified_training_receipts', 10),
            ('learning.alr_challenger_training_runs', 11),
            ('learning.alr_challenger_model_artifacts', 5),
            ('learning.alr_challenger_registry', 7)
        ) AS expected(table_name, constraint_count)
    LOOP
        SELECT count(*) INTO v_count
        FROM pg_constraint
        WHERE conrelid = v_spec.table_name::regclass AND contype IN ('p', 'u', 'f', 'c');
        IF v_count <> v_spec.constraint_count THEN
            RAISE EXCEPTION
                'V158 Guard B FAIL: % constraint count % expected %',
                v_spec.table_name, v_count, v_spec.constraint_count;
        END IF;
    END LOOP;
    FOR v_spec IN SELECT * FROM (VALUES
      ('alr_qualified_receipts_hashes_check','learning.alr_qualified_training_receipts','expected_receipt_hashes','pg_temp.alr_v158_expected_receipts'),
      ('alr_qualified_receipts_status_check','learning.alr_qualified_training_receipts','expected_receipt_status','pg_temp.alr_v158_expected_receipts'),
      ('alr_qualified_receipts_payload_check','learning.alr_qualified_training_receipts','expected_receipt_payload','pg_temp.alr_v158_expected_receipts'),
      ('alr_qualified_receipts_no_authority_check','learning.alr_qualified_training_receipts','expected_receipt_no_authority','pg_temp.alr_v158_expected_receipts'),
      ('alr_qualified_receipts_counters_check','learning.alr_qualified_training_receipts','expected_receipt_counters','pg_temp.alr_v158_expected_receipts'),
      ('alr_challenger_runs_hashes_check','learning.alr_challenger_training_runs','expected_run_hashes','pg_temp.alr_v158_expected_runs'),
      ('alr_challenger_runs_model_schema_check','learning.alr_challenger_training_runs','expected_run_model_schema','pg_temp.alr_v158_expected_runs'),
      ('alr_challenger_runs_state_check','learning.alr_challenger_training_runs','expected_run_state','pg_temp.alr_v158_expected_runs'),
      ('alr_challenger_runs_payload_check','learning.alr_challenger_training_runs','expected_run_payload','pg_temp.alr_v158_expected_runs'),
      ('alr_challenger_runs_no_authority_check','learning.alr_challenger_training_runs','expected_run_no_authority','pg_temp.alr_v158_expected_runs'),
      ('alr_challenger_runs_counters_check','learning.alr_challenger_training_runs','expected_run_counters','pg_temp.alr_v158_expected_runs'),
      ('alr_challenger_artifacts_hashes_check','learning.alr_challenger_model_artifacts','expected_artifact_hashes','pg_temp.alr_v158_expected_artifacts'),
      ('alr_challenger_artifacts_shape_check','learning.alr_challenger_model_artifacts','expected_artifact_shape','pg_temp.alr_v158_expected_artifacts'),
      ('alr_challenger_registry_hashes_check','learning.alr_challenger_registry','expected_registry_hashes','pg_temp.alr_v158_expected_registry'),
      ('alr_challenger_registry_state_check','learning.alr_challenger_registry','expected_registry_state','pg_temp.alr_v158_expected_registry'),
      ('alr_challenger_registry_payload_check','learning.alr_challenger_registry','expected_registry_payload','pg_temp.alr_v158_expected_registry')
    ) AS x(name,relation_name,expected_name,expected_relation) LOOP
        SELECT pg_get_expr(a.conbin,a.conrelid,FALSE) AS actual_expr,
               pg_get_expr(e.conbin,e.conrelid,FALSE) AS expected_expr
          INTO v_actual
          FROM pg_constraint AS a JOIN pg_constraint AS e
            ON e.conname=v_spec.expected_name
           AND e.conrelid=v_spec.expected_relation::regclass
         WHERE a.conname=v_spec.name
           AND a.conrelid=v_spec.relation_name::regclass;
        IF NOT FOUND OR (SELECT count(*) FROM pg_constraint
             WHERE conname=v_spec.name)<>1
           OR v_actual.actual_expr IS DISTINCT FROM v_actual.expected_expr
           OR NOT EXISTS (
             SELECT 1 FROM pg_constraint AS c
             WHERE c.conname=v_spec.name
               AND c.conrelid=v_spec.relation_name::regclass
               AND c.contype='c' AND c.convalidated
               AND NOT c.connoinherit AND c.conislocal AND c.coninhcount=0
               AND c.conparentid=0 AND NOT c.condeferrable
               AND NOT c.condeferred
           ) THEN
            RAISE EXCEPTION
                'V158 Guard B FAIL: exact CHECK drift: %', v_spec.name;
        END IF;
    END LOOP;
    FOR v_spec IN SELECT * FROM (VALUES
      ('alr_qualified_receipts_pk','learning.alr_qualified_training_receipts','p','durable_receipt_hash',NULL,NULL),
      ('alr_qualified_receipts_training_key_uniq','learning.alr_qualified_training_receipts','u','training_key_hash',NULL,NULL),
      ('alr_qualified_receipts_receipt_training_uniq','learning.alr_qualified_training_receipts','u','durable_receipt_hash,training_key_hash',NULL,NULL),
      ('alr_qualified_receipts_source_training_uniq','learning.alr_qualified_training_receipts','u','source_receipt_hash,training_key_hash',NULL,NULL),
      ('alr_qualified_receipts_projection_fk','learning.alr_qualified_training_receipts','f','projection_artifact_hash','learning.alr_artifact_nodes','artifact_hash'),
      ('alr_challenger_runs_pk','learning.alr_challenger_training_runs','p','training_run_hash',NULL,NULL),
      ('alr_challenger_runs_training_key_uniq','learning.alr_challenger_training_runs','u','training_key_hash',NULL,NULL),
      ('alr_challenger_runs_result_lineage_uniq','learning.alr_challenger_training_runs','u','training_run_hash,training_key_hash,model_artifact_set_hash',NULL,NULL),
      ('alr_challenger_runs_artifact_lineage_uniq','learning.alr_challenger_training_runs','u','training_run_hash,training_key_hash,model_artifact_set_hash,actual_feature_schema_hash,model_schema_version',NULL,NULL),
      ('alr_challenger_runs_receipt_training_fk','learning.alr_challenger_training_runs','f','durable_receipt_hash,training_key_hash','learning.alr_qualified_training_receipts','durable_receipt_hash,training_key_hash'),
      ('alr_challenger_artifacts_pk','learning.alr_challenger_model_artifacts','p','artifact_hash',NULL,NULL),
      ('alr_challenger_artifacts_run_quantile_uniq','learning.alr_challenger_model_artifacts','u','training_run_hash,quantile',NULL,NULL),
      ('alr_challenger_artifacts_run_lineage_fk','learning.alr_challenger_model_artifacts','f','training_run_hash,training_key_hash,model_artifact_set_hash,feature_schema_hash,model_schema_version','learning.alr_challenger_training_runs','training_run_hash,training_key_hash,model_artifact_set_hash,actual_feature_schema_hash,model_schema_version'),
      ('alr_challenger_registry_pk','learning.alr_challenger_registry','p','challenger_hash',NULL,NULL),
      ('alr_challenger_registry_run_uniq','learning.alr_challenger_registry','u','training_run_hash',NULL,NULL),
      ('alr_challenger_registry_training_key_uniq','learning.alr_challenger_registry','u','training_key_hash',NULL,NULL),
      ('alr_challenger_registry_run_lineage_fk','learning.alr_challenger_registry','f','training_run_hash,training_key_hash,model_artifact_set_hash','learning.alr_challenger_training_runs','training_run_hash,training_key_hash,model_artifact_set_hash')
    ) AS x(name,relation_name,constraint_type,key_columns,foreign_relation,foreign_columns) LOOP
        SELECT c.contype, c.condeferrable, c.condeferred, c.convalidated,
               c.connoinherit, c.conislocal, c.coninhcount, c.conparentid,
               c.conindid, c.confupdtype, c.confdeltype, c.confmatchtype,
               (SELECT string_agg(a.attname,',' ORDER BY k.ordinality)
                FROM unnest(c.conkey) WITH ORDINALITY AS k(attnum,ordinality)
                JOIN pg_attribute AS a ON a.attrelid=c.conrelid AND a.attnum=k.attnum) AS key_columns,
               CASE WHEN c.confrelid=0 THEN NULL
                    ELSE c.confrelid::regclass::TEXT END AS foreign_relation,
               (SELECT string_agg(a.attname,',' ORDER BY k.ordinality)
                FROM unnest(c.confkey) WITH ORDINALITY AS k(attnum,ordinality)
                JOIN pg_attribute AS a ON a.attrelid=c.confrelid AND a.attnum=k.attnum) AS foreign_columns
          INTO v_actual FROM pg_constraint AS c
         WHERE c.conname=v_spec.name AND c.conrelid=v_spec.relation_name::regclass;
        IF NOT FOUND OR (SELECT count(*) FROM pg_constraint
             WHERE conname=v_spec.name)<>1 OR v_actual.contype::TEXT<>v_spec.constraint_type OR v_actual.key_columns IS DISTINCT FROM v_spec.key_columns OR v_actual.foreign_relation IS DISTINCT FROM v_spec.foreign_relation OR v_actual.foreign_columns IS DISTINCT FROM v_spec.foreign_columns OR v_actual.condeferrable OR v_actual.condeferred OR NOT v_actual.convalidated OR NOT v_actual.connoinherit OR NOT v_actual.conislocal OR v_actual.coninhcount<>0 OR v_actual.conparentid<>0 OR (v_spec.constraint_type='f' AND (
             v_actual.confupdtype<>'a' OR v_actual.confdeltype<>'a' OR v_actual.confmatchtype<>'s'
           )) THEN
            RAISE EXCEPTION
                'V158 Guard B FAIL: constraint posture mismatch: %',
                v_spec.name;
        END IF;
        IF v_spec.constraint_type IN ('p', 'u') AND NOT EXISTS (
            SELECT 1 FROM pg_index
            WHERE indexrelid = v_actual.conindid AND indisunique IS TRUE AND indimmediate IS TRUE AND indisvalid IS TRUE AND indisready IS TRUE
        ) THEN
            RAISE EXCEPTION
                'V158 Guard B FAIL: non-immediate replay arbiter: %',
                v_spec.name;
        END IF;
    END LOOP;
    FOR v_spec IN SELECT * FROM (VALUES
      ('persist_alr_qualified_training_receipt_v1','learning.persist_alr_qualified_training_receipt_v1(text,text,text,text,text,text,text,text,text,text,text,text,text,text,text,jsonb)',16,'jsonb','5edfac9aaf6b5e9e7d2ef492feb06f52'),
      ('persist_alr_challenger_training_result_v1','learning.persist_alr_challenger_training_result_v1(text,text,text,text,text,text,text,text,text,text,text,text,integer,text,text,text,timestamp with time zone,timestamp with time zone,text,text,bigint,text,text,bigint,text,text,bigint,text)',28,'jsonb','30b25e486b820477b4a9eeaf3d209e28'),
      ('read_alr_qualified_training_receipt_v1','learning.read_alr_qualified_training_receipt_v1(text,text)',2,'jsonb','0b5f006cc0cb84a970e057a01c408ea0'),
      ('read_alr_challenger_training_result_v1','learning.read_alr_challenger_training_result_v1(text,text)',2,'jsonb','7b199c1aa74c5258693a4c761586f96b'),
      ('alr_v158_assert_complete_result','learning.alr_v158_assert_complete_result()',0,'trigger','4829c6065049859a85bf49ec6b47e1ec'),
      ('alr_v158_reject_mutation','learning.alr_v158_reject_mutation()',0,'trigger','2258b2692fe7dfbbed3c1ec397b47617')
    ) AS x(function_name,identity,arg_count,return_type,body_md5) LOOP
        v_oid := to_regprocedure(v_spec.identity);
        IF v_oid IS NULL OR EXISTS (
            SELECT 1 FROM pg_proc AS p WHERE p.oid=v_oid AND (
              pg_get_userbyid(p.proowner)<>'alr_challenger_writer' OR p.prosecdef IS FALSE OR p.pronargs<>v_spec.arg_count OR p.prolang<>(SELECT oid FROM pg_language WHERE lanname='plpgsql') OR p.prorettype<>v_spec.return_type::regtype OR p.proconfig IS DISTINCT FROM
                   ARRAY['search_path=pg_catalog, pg_temp']::TEXT[] OR p.provolatile<>'v' OR p.proparallel<>'u' OR p.proleakproof OR p.proisstrict OR p.pronargdefaults<>0 OR p.provariadic<>0 OR md5(p.prosrc)<>v_spec.body_md5
            )
        ) THEN
            RAISE EXCEPTION
                'V158 Guard B FAIL: exact function definition mismatch: %',
                v_spec.function_name;
        END IF;
        SELECT count(*) INTO v_count
        FROM pg_proc AS p
        JOIN pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = 'learning' AND p.proname = v_spec.function_name;
        IF v_count <> 1 THEN
            RAISE EXCEPTION
                'V158 Guard B FAIL: unexpected function overload: %',
                v_spec.function_name;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM pg_trigger WHERE tgisinternal IS FALSE AND tgrelid IN (
          'learning.alr_qualified_training_receipts'::regclass,
          'learning.alr_challenger_training_runs'::regclass,
          'learning.alr_challenger_model_artifacts'::regclass,
          'learning.alr_challenger_registry'::regclass
        )) <> 7 THEN
        RAISE EXCEPTION 'V158 Guard B FAIL: unexpected trigger set';
    END IF;
    FOR v_spec IN SELECT * FROM (VALUES
      ('alr_challenger_run_complete_ct_v1','learning.alr_challenger_training_runs','learning.alr_v158_assert_complete_result()',29,TRUE),
      ('alr_challenger_artifact_complete_ct_v1','learning.alr_challenger_model_artifacts','learning.alr_v158_assert_complete_result()',29,TRUE),
      ('alr_challenger_registry_complete_ct_v1','learning.alr_challenger_registry','learning.alr_v158_assert_complete_result()',29,TRUE),
      ('alr_v158_immutable_alr_qualified_training_receipts_trg','learning.alr_qualified_training_receipts','learning.alr_v158_reject_mutation()',27,FALSE),
      ('alr_v158_immutable_alr_challenger_training_runs_trg','learning.alr_challenger_training_runs','learning.alr_v158_reject_mutation()',27,FALSE),
      ('alr_v158_immutable_alr_challenger_model_artifacts_trg','learning.alr_challenger_model_artifacts','learning.alr_v158_reject_mutation()',27,FALSE),
      ('alr_v158_immutable_alr_challenger_registry_trg','learning.alr_challenger_registry','learning.alr_v158_reject_mutation()',27,FALSE)
    ) AS x(name,relation_name,function_name,trigger_type,constrained) LOOP
        IF (SELECT count(*) FROM pg_trigger WHERE tgname=v_spec.name AND tgisinternal IS FALSE)<>1 OR NOT EXISTS (
            SELECT 1 FROM pg_trigger AS t WHERE t.tgname=v_spec.name AND t.tgrelid=v_spec.relation_name::regclass AND t.tgfoid=v_spec.function_name::regprocedure AND t.tgtype=v_spec.trigger_type AND t.tgenabled='O' AND t.tgnargs=0 AND t.tgqual IS NULL AND t.tgattr::TEXT='' AND t.tgdeferrable=v_spec.constrained AND t.tginitdeferred=v_spec.constrained AND (t.tgconstraint<>0)=v_spec.constrained
        ) THEN
            RAISE EXCEPTION
                'V158 Guard B FAIL: trigger posture mismatch: %',
                v_spec.name;
        END IF;
    END LOOP;
END
$v158_guard_b$;
-- V158 Guard C: effective least privilege and ownership, not merely ACL text.
DO $v158_guard_c$
DECLARE
    v_table TEXT;
    v_oid OID;
    v_function TEXT;
    v_schema_owner OID;
    v_writer_oid OID;
    v_caller_oid OID;
BEGIN
    SELECT nspowner INTO v_schema_owner
    FROM pg_namespace WHERE nspname='learning';
    SELECT oid INTO v_writer_oid FROM pg_roles
    WHERE rolname='alr_challenger_writer';
    SELECT oid INTO v_caller_oid FROM pg_roles
    WHERE rolname='alr_challenger_trainer_caller';
    FOREACH v_table IN ARRAY ARRAY[
        'learning.alr_qualified_training_receipts',
        'learning.alr_challenger_training_runs',
        'learning.alr_challenger_model_artifacts',
        'learning.alr_challenger_registry'
    ] LOOP
        IF NOT has_table_privilege('alr_challenger_writer', v_table, 'SELECT') OR NOT has_table_privilege('alr_challenger_writer', v_table, 'INSERT') OR has_table_privilege('alr_challenger_writer', v_table, 'UPDATE') OR has_table_privilege('alr_challenger_writer', v_table, 'DELETE') OR has_table_privilege('alr_challenger_writer', v_table, 'TRUNCATE') OR has_table_privilege('alr_challenger_writer', v_table, 'REFERENCES') OR has_table_privilege('alr_challenger_writer', v_table, 'TRIGGER') THEN
            RAISE EXCEPTION
                'V158 Guard C FAIL: writer table ACL mismatch: %', v_table;
        END IF;
        IF has_any_column_privilege(
            'alr_challenger_writer', v_table, 'UPDATE,REFERENCES'
        ) OR has_any_column_privilege(
            'alr_challenger_trainer_caller', v_table,
            'SELECT,INSERT,UPDATE,REFERENCES'
        ) THEN
            RAISE EXCEPTION
                'V158 Guard C FAIL: unexpected column authority: %', v_table;
        END IF;
        IF EXISTS (
            SELECT 1 FROM pg_class AS c
            CROSS JOIN LATERAL aclexplode(
              COALESCE(c.relacl, acldefault('r', c.relowner))
            ) AS a WHERE c.oid=v_table::regclass AND (
              a.grantee NOT IN (v_schema_owner, v_writer_oid) OR (a.grantee=v_writer_oid AND (
                a.privilege_type NOT IN ('SELECT','INSERT') OR a.is_grantable
              ))
            )
        ) OR (SELECT count(*) FROM pg_class AS c
              CROSS JOIN LATERAL aclexplode(
                COALESCE(c.relacl, acldefault('r',c.relowner))
              ) AS a WHERE c.oid=v_table::regclass AND a.grantee=v_writer_oid) <> 2 OR EXISTS (
              SELECT 1 FROM pg_attribute AS a
              CROSS JOIN LATERAL aclexplode(a.attacl) AS x
              WHERE a.attrelid=v_table::regclass
          ) THEN
            RAISE EXCEPTION
                'V158 Guard C FAIL: unexpected table/column ACL: %', v_table;
        END IF;
        IF (SELECT relowner FROM pg_class WHERE oid=v_table::regclass)
              <> v_schema_owner THEN
            RAISE EXCEPTION
                'V158 Guard C FAIL: unexpected table owner: %', v_table;
        END IF;
    END LOOP;
    FOREACH v_function IN ARRAY ARRAY[
        'learning.persist_alr_qualified_training_receipt_v1(text,text,text,text,text,text,text,text,text,text,text,text,text,text,text,jsonb)',
        'learning.persist_alr_challenger_training_result_v1(text,text,text,text,text,text,text,text,text,text,text,text,integer,text,text,text,timestamp with time zone,timestamp with time zone,text,text,bigint,text,text,bigint,text,text,bigint,text)',
        'learning.read_alr_qualified_training_receipt_v1(text,text)',
        'learning.read_alr_challenger_training_result_v1(text,text)'
    ] LOOP
        v_oid := to_regprocedure(v_function);
        IF v_oid IS NULL OR NOT has_function_privilege(
               'alr_challenger_trainer_caller', v_oid, 'EXECUTE'
           ) THEN
            RAISE EXCEPTION
                'V158 Guard C FAIL: caller fixed-function ACL mismatch: %',
                v_function;
        END IF;
        IF EXISTS (
            SELECT 1 FROM pg_proc AS p
            CROSS JOIN LATERAL aclexplode(
              COALESCE(p.proacl, acldefault('f',p.proowner))
            ) AS a WHERE p.oid=v_oid AND (
              a.grantee NOT IN (v_writer_oid,v_caller_oid) OR (a.grantee=v_caller_oid AND (
                a.privilege_type<>'EXECUTE' OR a.is_grantable
              ))
            )
        ) OR (SELECT count(*) FROM pg_proc AS p
              CROSS JOIN LATERAL aclexplode(
                COALESCE(p.proacl, acldefault('f',p.proowner))
              ) AS a WHERE p.oid=v_oid AND a.grantee=v_caller_oid) <> 1 THEN
            RAISE EXCEPTION
                'V158 Guard C FAIL: unexpected fixed-function ACL: %',
                v_function;
        END IF;
    END LOOP;
    FOREACH v_function IN ARRAY ARRAY[
        'learning.alr_v158_assert_complete_result()',
        'learning.alr_v158_reject_mutation()'
    ] LOOP
        v_oid := to_regprocedure(v_function);
        IF v_oid IS NULL OR has_function_privilege(
               'alr_challenger_trainer_caller', v_oid, 'EXECUTE'
           ) THEN
            RAISE EXCEPTION
                'V158 Guard C FAIL: caller trigger-function authority: %',
                v_function;
        END IF;
        IF EXISTS (
            SELECT 1 FROM pg_proc AS p
            CROSS JOIN LATERAL aclexplode(
              COALESCE(p.proacl, acldefault('f',p.proowner))
            ) AS a WHERE p.oid=v_oid AND a.grantee<>v_writer_oid
        ) THEN
            RAISE EXCEPTION
                'V158 Guard C FAIL: unexpected trigger-function ACL: %',
                v_function;
        END IF;
    END LOOP;
    IF NOT has_schema_privilege(
            'alr_challenger_writer', 'learning', 'USAGE'
       ) OR NOT has_schema_privilege(
            'alr_challenger_writer', 'public', 'USAGE'
       ) OR has_schema_privilege(
            'alr_challenger_writer', 'learning', 'CREATE'
       ) OR has_schema_privilege(
            'alr_challenger_writer', 'public', 'CREATE'
       ) OR NOT has_schema_privilege(
            'alr_challenger_trainer_caller', 'learning', 'USAGE'
       ) OR has_schema_privilege(
            'alr_challenger_trainer_caller', 'learning', 'CREATE'
       ) OR has_schema_privilege(
            'alr_challenger_trainer_caller', 'public', 'CREATE'
    ) THEN
        RAISE EXCEPTION 'V158 Guard C FAIL: schema ACL posture mismatch';
    END IF;
    IF session_user<>current_user
       OR pg_get_userbyid(v_schema_owner) <> current_user OR NOT EXISTS (
          SELECT 1 FROM pg_roles WHERE oid=v_schema_owner AND rolsuper
       ) OR EXISTS (
          SELECT 1 FROM pg_auth_members WHERE roleid=v_schema_owner
       ) OR EXISTS (
          SELECT 1 FROM pg_roles AS r WHERE r.rolsuper IS FALSE AND has_schema_privilege(r.rolname,'learning','CREATE')
       ) OR EXISTS (
          SELECT 1 FROM pg_namespace AS n
          CROSS JOIN LATERAL aclexplode(
            COALESCE(n.nspacl,acldefault('n',n.nspowner))
          ) AS a WHERE n.nspname='learning' AND a.grantee=0 AND a.privilege_type='CREATE'
       ) THEN
        RAISE EXCEPTION
            'V158 Guard C FAIL: schema owner/CREATE authority mismatch';
    END IF;
    IF NOT has_function_privilege(
        'alr_challenger_writer', 'public.digest(bytea,text)'::regprocedure,
        'EXECUTE'
    ) OR (SELECT count(*) FROM pg_proc AS p
          CROSS JOIN LATERAL aclexplode(
            COALESCE(p.proacl,acldefault('f',p.proowner))
          ) AS a WHERE p.oid='public.digest(bytea,text)'::regprocedure
            AND a.grantee=v_writer_oid)<>1 OR EXISTS (
          SELECT 1 FROM pg_proc AS p
          CROSS JOIN LATERAL aclexplode(
            COALESCE(p.proacl,acldefault('f',p.proowner))
          ) AS a WHERE p.oid='public.digest(bytea,text)'::regprocedure
            AND a.grantee=v_writer_oid AND (
              a.privilege_type<>'EXECUTE' OR a.is_grantable
              OR a.grantor<>p.proowner
            )
    ) THEN
        RAISE EXCEPTION
            'V158 Guard C FAIL: writer cannot execute exact public.digest';
    END IF;
    IF (SELECT relowner FROM pg_class
        WHERE oid='learning.alr_artifact_nodes'::regclass)<>v_schema_owner
       OR NOT has_table_privilege(
           'alr_challenger_writer', 'learning.alr_artifact_nodes', 'SELECT'
       ) OR has_table_privilege(
           'alr_challenger_writer', 'learning.alr_artifact_nodes',
           'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
       ) OR has_any_column_privilege(
           'alr_challenger_writer', 'learning.alr_artifact_nodes',
           'INSERT,UPDATE,REFERENCES'
       ) OR (SELECT count(*) FROM pg_class AS c
             CROSS JOIN LATERAL aclexplode(
               COALESCE(c.relacl,acldefault('r',c.relowner))
             ) AS a WHERE c.oid='learning.alr_artifact_nodes'::regclass
               AND a.grantee=v_writer_oid)<>1 OR EXISTS (
             SELECT 1 FROM pg_class AS c
             CROSS JOIN LATERAL aclexplode(
               COALESCE(c.relacl,acldefault('r',c.relowner))
             ) AS a WHERE c.oid='learning.alr_artifact_nodes'::regclass
               AND a.grantee=v_writer_oid AND (
                 a.privilege_type<>'SELECT' OR a.is_grantable
                 OR a.grantor<>c.relowner
               )
       ) OR EXISTS (
             SELECT 1 FROM pg_attribute AS x
             CROSS JOIN LATERAL aclexplode(x.attacl) AS a
             WHERE x.attrelid='learning.alr_artifact_nodes'::regclass
               AND a.grantee=v_writer_oid
       ) THEN
        RAISE EXCEPTION
            'V158 Guard C FAIL: writer projection-read ACL mismatch';
    END IF;
    IF has_parameter_privilege(
           'alr_challenger_writer', 'session_replication_role', 'SET'
       ) OR has_parameter_privilege(
           'alr_challenger_trainer_caller', 'session_replication_role', 'SET'
       ) OR EXISTS (
           SELECT 1
           FROM pg_parameter_acl AS p
           CROSS JOIN LATERAL aclexplode(p.paracl) AS acl
           JOIN pg_roles AS r ON r.oid = acl.grantee
           WHERE p.parname = 'session_replication_role' AND r.rolname IN (
                 'alr_challenger_writer', 'alr_challenger_trainer_caller'
             ) AND acl.privilege_type = 'SET'
       ) THEN
        RAISE EXCEPTION
            'V158 Guard C FAIL: session_replication_role SET authority present';
    END IF;
    IF EXISTS (
           SELECT 1
           FROM pg_roles AS r
           WHERE r.rolname IN ('trading_ai', 'alr_shadow')
             AND has_parameter_privilege(
                   r.rolname, 'session_replication_role', 'SET'
                 )
       ) OR EXISTS (
           SELECT 1
           FROM pg_parameter_acl AS p
           CROSS JOIN LATERAL aclexplode(p.paracl) AS acl
           JOIN pg_roles AS r ON r.oid = acl.grantee
           WHERE p.parname = 'session_replication_role'
             AND r.rolname IN ('trading_ai', 'alr_shadow')
             AND acl.privilege_type = 'SET'
       ) OR EXISTS (
           SELECT 1 FROM pg_roles AS generic
           CROSS JOIN pg_roles AS reachable
           WHERE generic.rolname IN ('trading_ai', 'alr_shadow')
             AND generic.oid <> reachable.oid
             AND pg_has_role(generic.oid, reachable.oid, 'SET')
             AND has_parameter_privilege(
                   reachable.rolname, 'session_replication_role', 'SET'
                 )
       ) THEN
        RAISE EXCEPTION
            'V158 Guard C FAIL: generic role has session_replication_role SET authority';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM pg_auth_members AS m
        JOIN pg_roles AS granted ON granted.oid = m.roleid
        JOIN pg_roles AS member_role ON member_role.oid = m.member
        WHERE granted.rolname IN (
                  'alr_challenger_writer', 'alr_challenger_trainer_caller'
              ) OR member_role.rolname IN (
                  'alr_challenger_writer', 'alr_challenger_trainer_caller'
              )
    ) THEN
        RAISE EXCEPTION 'V158 Guard C FAIL: challenger role membership present';
    END IF;
    IF (SELECT count(*) FROM pg_shdepend
        WHERE refclassid='pg_authid'::regclass AND refobjid=v_writer_oid
          AND deptype='o')<>6 OR EXISTS (
        SELECT 1 FROM pg_shdepend AS d
        WHERE d.refclassid='pg_authid'::regclass
          AND d.refobjid=v_writer_oid AND d.deptype='o' AND (
            d.dbid<>(SELECT oid FROM pg_database
                     WHERE datname=current_database())
            OR d.classid<>'pg_proc'::regclass OR d.objid NOT IN (
              'learning.persist_alr_qualified_training_receipt_v1(text,text,text,text,text,text,text,text,text,text,text,text,text,text,text,jsonb)'::regprocedure,
              'learning.persist_alr_challenger_training_result_v1(text,text,text,text,text,text,text,text,text,text,text,text,integer,text,text,text,timestamp with time zone,timestamp with time zone,text,text,bigint,text,text,bigint,text,text,bigint,text)'::regprocedure,
              'learning.read_alr_qualified_training_receipt_v1(text,text)'::regprocedure,
              'learning.read_alr_challenger_training_result_v1(text,text)'::regprocedure,
              'learning.alr_v158_assert_complete_result()'::regprocedure,
              'learning.alr_v158_reject_mutation()'::regprocedure
            )
          )
    ) THEN
        RAISE EXCEPTION
            'V158 Guard C FAIL: writer owns objects beyond six fixed functions';
    END IF;
END
$v158_guard_c$;
COMMIT;
