-- V160: atomic durable ALR fit consumption.
--
-- This forward migration installs one six-action coordinator over the frozen
-- V158/V159 relations.  It creates no role or credential and performs no fit,
-- model, serving, promotion, broker, or runtime action by itself.
BEGIN;
SET LOCAL search_path = pg_catalog, pg_temp;
SET LOCAL lock_timeout = '15s';
SET LOCAL statement_timeout = '120s';

-- Canonical CHECK parse trees are built independently in pg_temp and compared
-- with both the replay catalog and the final catalog.  The manifest below is
-- the single exact inventory for all 23 V160 constraints.
CREATE TEMP TABLE pg_temp.alr_v160_expected_requests (
    request_hash TEXT,durable_receipt_hash TEXT,training_key_hash TEXT,
    nonce_digest TEXT,request_bytes BYTEA,request_projection JSONB,
    verification_receipt_bytes BYTEA,verification_receipt_hash TEXT,
    verification_receipt JSONB,request_generation BIGINT,issuer_id TEXT,
    accept_by TIMESTAMPTZ,complete_by TIMESTAMPTZ,
    CONSTRAINT expected_requests_hashes CHECK (
        request_hash~'^[0-9a-f]{64}$'
        AND durable_receipt_hash~'^[0-9a-f]{64}$'
        AND training_key_hash~'^[0-9a-f]{64}$'
        AND nonce_digest~'^[0-9a-f]{64}$'),
    CONSTRAINT expected_requests_shape CHECK (
        octet_length(request_bytes) BETWEEN 2 AND 1048576
        AND jsonb_typeof(request_projection)='object'
        AND octet_length(verification_receipt_bytes) BETWEEN 2 AND 1048576
        AND verification_receipt_hash~'^[0-9a-f]{64}$'
        AND verification_receipt_hash=encode(
            public.digest(verification_receipt_bytes,'sha256'::TEXT),'hex'::TEXT)
        AND convert_from(verification_receipt_bytes,'UTF8'::NAME)::JSONB=verification_receipt
        AND jsonb_typeof(verification_receipt)='object'
        AND request_generation>0
        AND issuer_id~'^[a-z0-9][a-z0-9_.:-]{0,127}$'
        AND accept_by<complete_by)
) ON COMMIT DROP;
CREATE TEMP TABLE pg_temp.alr_v160_expected_claims (
    claim_bytes BYTEA,claim_projection JSONB,verification_receipt_bytes BYTEA,
    verification_receipt_hash TEXT,verification_receipt JSONB,
    CONSTRAINT expected_claims_shape CHECK (
        octet_length(claim_bytes) BETWEEN 2 AND 1048576
        AND jsonb_typeof(claim_projection)='object'
        AND octet_length(verification_receipt_bytes) BETWEEN 2 AND 1048576
        AND verification_receipt_hash~'^[0-9a-f]{64}$'
        AND verification_receipt_hash=encode(
            public.digest(verification_receipt_bytes,'sha256'::TEXT),'hex'::TEXT)
        AND convert_from(verification_receipt_bytes,'UTF8'::NAME)::JSONB=verification_receipt
        AND jsonb_typeof(verification_receipt)='object')
) ON COMMIT DROP;
CREATE TEMP TABLE pg_temp.alr_v160_expected_statuses (
    status_generation BIGINT,response_hash TEXT,response_bytes BYTEA,
    response_projection JSONB,verification_receipt_bytes BYTEA,
    verification_receipt_hash TEXT,verification_receipt JSONB,
    status_issued_at TIMESTAMPTZ,status_expires_at TIMESTAMPTZ,
    CONSTRAINT expected_statuses_shape CHECK (
        status_generation>0 AND response_hash~'^[0-9a-f]{64}$'
        AND octet_length(response_bytes) BETWEEN 2 AND 2097152
        AND jsonb_typeof(response_projection)='object'
        AND octet_length(verification_receipt_bytes) BETWEEN 2 AND 1048576
        AND verification_receipt_hash~'^[0-9a-f]{64}$'
        AND verification_receipt_hash=encode(
            public.digest(verification_receipt_bytes,'sha256'::TEXT),'hex'::TEXT)
        AND convert_from(verification_receipt_bytes,'UTF8'::NAME)::JSONB=verification_receipt
        AND jsonb_typeof(verification_receipt)='object'
        AND status_issued_at<status_expires_at)
) ON COMMIT DROP;
CREATE TEMP TABLE pg_temp.alr_v160_expected_verifier_evidence (
    verifier_receipt_hash TEXT,action TEXT,declared_phase TEXT,
    verification_receipt_bytes BYTEA,verification_receipt JSONB,
    CONSTRAINT expected_verifier_evidence_shape CHECK (
        verifier_receipt_hash~'^[0-9a-f]{64}$'
        AND action IN ('REGISTER_REQUEST','CLAIM_REQUEST','RECORD_STATUS',
                       'CONSUME_TERMINAL','MARK_RECONCILE_REQUIRED')
        AND declared_phase IN ('REQUEST_ONLY','SIGNED_STATUS',
                               'TERMINAL_SUCCESS','TERMINAL_NO_INNER')
        AND octet_length(verification_receipt_bytes) BETWEEN 2 AND 1048576
        AND verifier_receipt_hash=encode(
            public.digest(verification_receipt_bytes,'sha256'::TEXT),'hex'::TEXT)
        AND convert_from(verification_receipt_bytes,'UTF8'::NAME)::JSONB=verification_receipt
        AND jsonb_typeof(verification_receipt)='object')
) ON COMMIT DROP;
CREATE TEMP TABLE pg_temp.alr_v160_expected_terminals (
    terminal_hash TEXT,outcome TEXT,terminal_bytes BYTEA,
    terminal_projection JSONB,inner_receipt_bytes BYTEA,
    verification_receipt_bytes BYTEA,verification_receipt_hash TEXT,
    verification_receipt JSONB,
    CONSTRAINT expected_terminals_shape CHECK (
        terminal_hash~'^[0-9a-f]{64}$'
        AND outcome IN ('SUCCEEDED','REJECTED_PRE_FIT',
                        'FAILED_AFTER_START','EXPIRED_UNCLAIMED')
        AND octet_length(terminal_bytes) BETWEEN 2 AND 2097152
        AND jsonb_typeof(terminal_projection)='object'
        AND ((outcome='SUCCEEDED' AND inner_receipt_bytes IS NOT NULL
              AND verification_receipt_bytes IS NOT NULL
              AND verification_receipt_hash IS NOT NULL
              AND verification_receipt IS NOT NULL)
          OR (outcome IN ('REJECTED_PRE_FIT','FAILED_AFTER_START')
              AND inner_receipt_bytes IS NULL
              AND verification_receipt_bytes IS NOT NULL
              AND verification_receipt_hash IS NOT NULL
              AND verification_receipt IS NOT NULL)
          OR (outcome='EXPIRED_UNCLAIMED' AND inner_receipt_bytes IS NULL
              AND verification_receipt_bytes IS NULL
              AND verification_receipt_hash IS NULL
              AND verification_receipt IS NULL))
        AND (verification_receipt_bytes IS NULL OR (
            octet_length(verification_receipt_bytes) BETWEEN 2 AND 1048576
            AND verification_receipt_hash~'^[0-9a-f]{64}$'
            AND verification_receipt_hash=encode(
                public.digest(verification_receipt_bytes,'sha256'::TEXT),'hex'::TEXT)
            AND convert_from(verification_receipt_bytes,'UTF8'::NAME)::JSONB=verification_receipt
            AND jsonb_typeof(verification_receipt)='object')))
) ON COMMIT DROP;
CREATE TEMP TABLE pg_temp.alr_v160_expected_reconciliation (
    reconciliation_hash TEXT,reason TEXT,event_bytes BYTEA,event_projection JSONB,
    verification_receipt_bytes BYTEA,verification_receipt_hash TEXT,
    verification_receipt JSONB,
    CONSTRAINT expected_reconciliation_shape CHECK (
        reconciliation_hash~'^[0-9a-f]{64}$'
        AND reason IN ('AMBIGUOUS_RESPONSE','FAILED_AFTER_START')
        AND octet_length(event_bytes) BETWEEN 2 AND 2097152
        AND jsonb_typeof(event_projection)='object'
        AND ((verification_receipt_bytes IS NULL
              AND verification_receipt_hash IS NULL
              AND verification_receipt IS NULL)
          OR (octet_length(verification_receipt_bytes) BETWEEN 2 AND 1048576
              AND verification_receipt_hash~'^[0-9a-f]{64}$'
              AND verification_receipt_hash=encode(
                  public.digest(verification_receipt_bytes,'sha256'::TEXT),'hex'::TEXT)
              AND convert_from(verification_receipt_bytes,
                  'UTF8'::NAME)::JSONB=verification_receipt
              AND jsonb_typeof(verification_receipt)='object')))
) ON COMMIT DROP;

CREATE TEMP TABLE pg_temp.alr_v160_expected_constraints (
    relation_name TEXT NOT NULL,name TEXT NOT NULL,constraint_type TEXT NOT NULL,
    key_columns TEXT,foreign_relation TEXT,foreign_columns TEXT,
    expected_check_name TEXT,expected_check_relation TEXT
) ON COMMIT DROP;
INSERT INTO pg_temp.alr_v160_expected_constraints VALUES
 ('learning.alr_challenger_consumption_requests','alr_consumption_requests_pk','p','request_hash',NULL,NULL,NULL,NULL),
 ('learning.alr_challenger_consumption_requests','alr_consumption_requests_admission_generation_uniq','u','durable_receipt_hash,training_key_hash,request_generation',NULL,NULL,NULL,NULL),
 ('learning.alr_challenger_consumption_requests','alr_consumption_requests_issuer_nonce_uniq','u','issuer_id,nonce_digest',NULL,NULL,NULL,NULL),
 ('learning.alr_challenger_consumption_requests','alr_consumption_requests_hashes_check','c',NULL,NULL,NULL,'expected_requests_hashes','pg_temp.alr_v160_expected_requests'),
 ('learning.alr_challenger_consumption_requests','alr_consumption_requests_shape_check','c',NULL,NULL,NULL,'expected_requests_shape','pg_temp.alr_v160_expected_requests'),
 ('learning.alr_challenger_consumption_claims','alr_consumption_claims_pk','p','request_hash',NULL,NULL,NULL,NULL),
 ('learning.alr_challenger_consumption_claims','alr_consumption_claims_request_fk','f','request_hash','learning.alr_challenger_consumption_requests','request_hash',NULL,NULL),
 ('learning.alr_challenger_consumption_claims','alr_consumption_claims_shape_check','c',NULL,NULL,NULL,'expected_claims_shape','pg_temp.alr_v160_expected_claims'),
 ('learning.alr_challenger_consumption_statuses','alr_consumption_statuses_pk','p','request_hash,status_generation',NULL,NULL,NULL,NULL),
 ('learning.alr_challenger_consumption_statuses','alr_consumption_statuses_response_uniq','u','response_hash',NULL,NULL,NULL,NULL),
 ('learning.alr_challenger_consumption_statuses','alr_consumption_statuses_request_fk','f','request_hash','learning.alr_challenger_consumption_requests','request_hash',NULL,NULL),
 ('learning.alr_challenger_consumption_statuses','alr_consumption_statuses_shape_check','c',NULL,NULL,NULL,'expected_statuses_shape','pg_temp.alr_v160_expected_statuses'),
 ('learning.alr_challenger_consumption_verifier_evidence','alr_consumption_verifier_evidence_pk','p','request_hash,action,verifier_receipt_hash',NULL,NULL,NULL,NULL),
 ('learning.alr_challenger_consumption_verifier_evidence','alr_consumption_verifier_evidence_request_fk','f','request_hash','learning.alr_challenger_consumption_requests','request_hash',NULL,NULL),
 ('learning.alr_challenger_consumption_verifier_evidence','alr_consumption_verifier_evidence_shape_check','c',NULL,NULL,NULL,'expected_verifier_evidence_shape','pg_temp.alr_v160_expected_verifier_evidence'),
 ('learning.alr_challenger_consumption_terminals','alr_consumption_terminals_pk','p','request_hash',NULL,NULL,NULL,NULL),
 ('learning.alr_challenger_consumption_terminals','alr_consumption_terminals_hash_uniq','u','terminal_hash',NULL,NULL,NULL,NULL),
 ('learning.alr_challenger_consumption_terminals','alr_consumption_terminals_request_fk','f','request_hash','learning.alr_challenger_consumption_requests','request_hash',NULL,NULL),
 ('learning.alr_challenger_consumption_terminals','alr_consumption_terminals_shape_check','c',NULL,NULL,NULL,'expected_terminals_shape','pg_temp.alr_v160_expected_terminals'),
 ('learning.alr_challenger_consumption_reconciliation_audit','alr_consumption_reconciliation_pk','p','reconciliation_hash',NULL,NULL,NULL,NULL),
 ('learning.alr_challenger_consumption_reconciliation_audit','alr_consumption_reconciliation_identity_uniq','u','request_hash,reconciliation_hash',NULL,NULL,NULL,NULL),
 ('learning.alr_challenger_consumption_reconciliation_audit','alr_consumption_reconciliation_request_fk','f','request_hash','learning.alr_challenger_consumption_requests','request_hash',NULL,NULL),
 ('learning.alr_challenger_consumption_reconciliation_audit','alr_consumption_reconciliation_shape_check','c',NULL,NULL,NULL,'expected_reconciliation_shape','pg_temp.alr_v160_expected_reconciliation');

DO $v160_preflight$
DECLARE
    v_coordinator OID;
    v_caller OID;
    v_writer OID;
    v_trainer_caller OID;
    v_attestor OID;
    v_attestor_caller OID;
    v_schema_owner OID;
    v_v160_relations INTEGER;
    v_spec RECORD;
    v_constraint RECORD;
    v_oid OID;
    v_actual TEXT;
BEGIN
    SELECT oid INTO v_coordinator FROM pg_roles
    WHERE rolname='alr_challenger_consumption_coordinator';
    SELECT oid INTO v_caller FROM pg_roles
    WHERE rolname='alr_challenger_consumption_caller';
    SELECT oid INTO v_writer FROM pg_roles WHERE rolname='alr_challenger_writer';
    SELECT oid INTO v_trainer_caller FROM pg_roles
    WHERE rolname='alr_challenger_trainer_caller';
    SELECT oid INTO v_attestor FROM pg_roles WHERE rolname='alr_challenger_fit_attestor';
    SELECT oid INTO v_attestor_caller FROM pg_roles
    WHERE rolname='alr_challenger_fit_attestor_caller';
    SELECT nspowner INTO v_schema_owner FROM pg_namespace WHERE nspname='learning';
    IF v_coordinator IS NULL OR v_caller IS NULL OR v_writer IS NULL
       OR v_trainer_caller IS NULL OR v_attestor IS NULL
       OR v_attestor_caller IS NULL OR v_schema_owner IS NULL THEN
        RAISE EXCEPTION 'V160 required pre-provisioned roles are missing';
    END IF;
    IF session_user<>current_user
       OR current_user<>pg_get_userbyid(v_schema_owner)
       OR NOT EXISTS (SELECT 1 FROM pg_roles
                      WHERE oid=v_schema_owner AND rolsuper)
       OR EXISTS (SELECT 1 FROM pg_auth_members
                  WHERE roleid=v_schema_owner OR member=v_schema_owner) THEN
        RAISE EXCEPTION 'V160 trusted learning schema owner drift';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE oid=v_coordinator AND NOT rolcanlogin AND NOT rolinherit
          AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
          AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=-1
          AND rolvaliduntil IS NULL AND rolconfig IS NULL
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE oid=v_caller AND rolcanlogin AND NOT rolinherit
          AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
          AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=1
          AND rolvaliduntil IS NULL AND rolconfig IS NULL
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE oid=v_writer AND NOT rolcanlogin AND NOT rolinherit
          AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
          AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=-1
          AND rolvaliduntil IS NULL AND rolconfig IS NULL
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE oid=v_trainer_caller AND rolcanlogin AND NOT rolinherit
          AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
          AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=1
          AND rolvaliduntil IS NULL AND rolconfig IS NULL
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE oid=v_attestor AND NOT rolcanlogin AND NOT rolinherit
          AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
          AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=-1
          AND rolvaliduntil IS NULL AND rolconfig IS NULL
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE oid=v_attestor_caller AND rolcanlogin AND NOT rolinherit
          AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
          AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=1
          AND rolvaliduntil IS NULL AND rolconfig IS NULL
    ) OR EXISTS (
        SELECT 1 FROM pg_auth_members
        WHERE roleid IN (v_coordinator,v_caller,v_writer,v_trainer_caller,
                         v_attestor,v_attestor_caller)
           OR member IN (v_coordinator,v_caller,v_writer,v_trainer_caller,
                         v_attestor,v_attestor_caller)
    ) THEN
        RAISE EXCEPTION 'V160 role posture or membership drift';
    END IF;
    IF to_regclass('learning.alr_qualified_training_receipts') IS NULL
       OR to_regclass('learning.alr_challenger_fit_attestations') IS NULL
       OR to_regclass('learning.alr_challenger_training_runs') IS NULL
       OR to_regclass('learning.alr_challenger_model_artifacts') IS NULL
       OR to_regclass('learning.alr_challenger_registry') IS NULL THEN
        RAISE EXCEPTION 'V160 requires the complete V158/V159 schema';
    END IF;
    FOR v_spec IN SELECT * FROM (VALUES
      ('alr_challenger_run_complete_ct_v1','learning.alr_challenger_training_runs','learning.alr_v158_assert_complete_result()',29,TRUE),
      ('alr_challenger_artifact_complete_ct_v1','learning.alr_challenger_model_artifacts','learning.alr_v158_assert_complete_result()',29,TRUE),
      ('alr_challenger_registry_complete_ct_v1','learning.alr_challenger_registry','learning.alr_v158_assert_complete_result()',29,TRUE),
      ('alr_v158_immutable_alr_qualified_training_receipts_trg','learning.alr_qualified_training_receipts','learning.alr_v158_reject_mutation()',27,FALSE),
      ('alr_v158_immutable_alr_challenger_training_runs_trg','learning.alr_challenger_training_runs','learning.alr_v158_reject_mutation()',27,FALSE),
      ('alr_v158_immutable_alr_challenger_model_artifacts_trg','learning.alr_challenger_model_artifacts','learning.alr_v158_reject_mutation()',27,FALSE),
      ('alr_v158_immutable_alr_challenger_registry_trg','learning.alr_challenger_registry','learning.alr_v158_reject_mutation()',27,FALSE),
      ('alr_v159_immutable_fit_attestations_trg','learning.alr_challenger_fit_attestations','learning.alr_v159_reject_attestation_mutation()',27,FALSE),
      ('alr_v159_run_complete_ct_v1','learning.alr_challenger_training_runs','learning.alr_v159_assert_attested_bundle()',29,TRUE),
      ('alr_v159_artifact_complete_ct_v1','learning.alr_challenger_model_artifacts','learning.alr_v159_assert_attested_bundle()',29,TRUE),
      ('alr_v159_registry_complete_ct_v1','learning.alr_challenger_registry','learning.alr_v159_assert_attested_bundle()',29,TRUE)
    ) AS x(name,relation_name,function_name,trigger_type,constrained) LOOP
        IF (SELECT count(*) FROM pg_trigger t
            WHERE t.tgname=v_spec.name AND NOT t.tgisinternal)<>1
           OR NOT EXISTS (SELECT 1 FROM pg_trigger t
              WHERE t.tgname=v_spec.name
                AND t.tgrelid=v_spec.relation_name::regclass
                AND t.tgfoid=v_spec.function_name::regprocedure
                AND t.tgtype=v_spec.trigger_type AND t.tgenabled='O'
                AND t.tgnargs=0 AND t.tgqual IS NULL AND t.tgattr::TEXT=''
                AND t.tgdeferrable=v_spec.constrained
                AND t.tginitdeferred=v_spec.constrained
                AND (t.tgconstraint<>0)=v_spec.constrained
                AND (NOT v_spec.constrained OR EXISTS (
                    SELECT 1 FROM pg_constraint c
                    WHERE c.oid=t.tgconstraint AND c.contype='t'
                      AND c.conrelid=t.tgrelid AND c.conname=t.tgname))) THEN
            RAISE EXCEPTION 'V160 exact preflight V158/V159 trigger drift: %',
                            v_spec.name;
        END IF;
    END LOOP;
    SELECT count(*) INTO v_v160_relations FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='learning' AND c.relname IN (
        'alr_challenger_consumption_requests',
        'alr_challenger_consumption_claims',
        'alr_challenger_consumption_statuses',
        'alr_challenger_consumption_verifier_evidence',
        'alr_challenger_consumption_terminals',
        'alr_challenger_consumption_reconciliation_audit'
    ) AND c.relkind='r';
    IF v_v160_relations NOT IN (0,6) THEN
        RAISE EXCEPTION 'V160 partial relation inventory rejected: %/6',v_v160_relations;
    END IF;
    IF v_v160_relations=0 THEN
        FOR v_spec IN SELECT * FROM (VALUES
          ('learning.persist_alr_qualified_training_receipt_v1(text,text,text,text,text,text,text,text,text,text,text,text,text,text,text,jsonb)',
           '5edfac9aaf6b5e9e7d2ef492feb06f52','writer'),
          ('learning.read_alr_qualified_training_receipt_v1(text,text)',
           '0b5f006cc0cb84a970e057a01c408ea0','writer'),
          ('learning.alr_v158_assert_complete_result()',
           '4829c6065049859a85bf49ec6b47e1ec','writer'),
          ('learning.alr_v158_reject_mutation()',
           '2258b2692fe7dfbbed3c1ec397b47617','writer'),
          ('learning.persist_alr_challenger_fit_attestation_v1(bytea,jsonb,text,text,text,text,text,text,text,text,text,text,text,text,text,text,timestamp with time zone,timestamp with time zone)',
           '5e6e564637a0c7fb62bd7853da662073','attestor'),
          ('learning.persist_alr_challenger_training_result_v2(text,text,text,text,text,text,text,text,text,text,integer,text,text,timestamp with time zone,timestamp with time zone,text,bigint,text,bigint,text,bigint)',
           'fcdbf0ddf9c991d151f3bc7e7f91db6c','writer'),
          ('learning.read_alr_challenger_training_result_v2(text,text)',
           'dfb767fc22f251b4663d9b3d0a7b4347','writer'),
          ('learning.alr_v159_reject_attestation_mutation()',
           'c0fe988ce64bea1b1f92a1732b2ea09b','attestor'),
          ('learning.alr_v159_assert_attested_bundle()',
           '35c0d60952f47797006601f4ddfa37ed','writer')
        ) AS x(identity,body_md5,owner_kind) LOOP
            v_oid:=to_regprocedure(v_spec.identity);
            IF v_oid IS NULL OR NOT EXISTS(SELECT 1 FROM pg_proc p
                WHERE p.oid=v_oid AND p.proowner=CASE v_spec.owner_kind
                    WHEN 'attestor' THEN v_attestor ELSE v_writer END
                  AND p.prosecdef
                  AND p.proconfig IS NOT DISTINCT FROM
                      ARRAY['search_path=pg_catalog, pg_temp']::TEXT[]
                  AND md5(p.prosrc)=v_spec.body_md5) THEN
                RAISE EXCEPTION 'V160 frozen V158/V159 baseline drift: %',
                                v_spec.identity;
            END IF;
        END LOOP;
    END IF;
    IF v_v160_relations=6 AND (
        to_regprocedure('learning.coordinate_alr_challenger_consumption_v1(text,jsonb)') IS NULL
        OR to_regprocedure('learning.read_alr_challenger_consumption_v1(text)') IS NULL
        OR to_regprocedure('learning.alr_v160_reject_consumption_mutation()') IS NULL
        OR (SELECT count(*) FROM pg_trigger t WHERE NOT t.tgisinternal
            AND t.tgname IN (
              'alr_v160_immutable_requests_trg','alr_v160_immutable_claims_trg',
              'alr_v160_immutable_statuses_trg','alr_v160_immutable_verifier_evidence_trg',
              'alr_v160_immutable_terminals_trg','alr_v160_immutable_reconciliation_trg'
            ))<>6
    ) THEN
        RAISE EXCEPTION 'V160 mixed or incomplete final catalog rejected';
    END IF;
    IF v_v160_relations=6 THEN
        FOR v_spec IN SELECT * FROM (VALUES
          ('learning.alr_challenger_consumption_requests',
           'request_hash:text|request_bytes:bytea|request_projection:jsonb|verification_receipt_bytes:bytea|verification_receipt_hash:text|verification_receipt:jsonb|durable_receipt_hash:text|training_key_hash:text|request_generation:bigint|issuer_id:text|nonce_digest:text|accept_by:timestamp with time zone|complete_by:timestamp with time zone|registered_at:timestamp with time zone',5),
          ('learning.alr_challenger_consumption_claims',
           'request_hash:text|claim_bytes:bytea|claim_projection:jsonb|verification_receipt_bytes:bytea|verification_receipt_hash:text|verification_receipt:jsonb|claimed_at:timestamp with time zone',3),
          ('learning.alr_challenger_consumption_statuses',
           'request_hash:text|status_generation:bigint|response_hash:text|response_bytes:bytea|response_projection:jsonb|verification_receipt_bytes:bytea|verification_receipt_hash:text|verification_receipt:jsonb|status_issued_at:timestamp with time zone|status_expires_at:timestamp with time zone|recorded_at:timestamp with time zone',4),
          ('learning.alr_challenger_consumption_verifier_evidence',
           'verifier_receipt_hash:text|request_hash:text|action:text|declared_phase:text|verification_receipt_bytes:bytea|verification_receipt:jsonb|recorded_at:timestamp with time zone',3),
          ('learning.alr_challenger_consumption_terminals',
           'request_hash:text|terminal_hash:text|outcome:text|terminal_bytes:bytea|terminal_projection:jsonb|inner_receipt_bytes:bytea|verification_receipt_bytes:bytea|verification_receipt_hash:text|verification_receipt:jsonb|consumed_at:timestamp with time zone',4),
          ('learning.alr_challenger_consumption_reconciliation_audit',
           'reconciliation_hash:text|request_hash:text|reason:text|event_bytes:bytea|event_projection:jsonb|verification_receipt_bytes:bytea|verification_receipt_hash:text|verification_receipt:jsonb|recorded_at:timestamp with time zone',4)
        ) AS x(relation_name,column_signature,constraint_count) LOOP
            SELECT string_agg(a.attname||':'||format_type(a.atttypid,a.atttypmod),
                              '|' ORDER BY a.attnum) INTO v_actual
            FROM pg_attribute a
            WHERE a.attrelid=v_spec.relation_name::regclass
              AND a.attnum>0 AND NOT a.attisdropped;
            IF v_actual IS DISTINCT FROM v_spec.column_signature
               OR (SELECT count(*) FROM pg_constraint c
                   WHERE c.conrelid=v_spec.relation_name::regclass)
                    <>v_spec.constraint_count
               OR NOT EXISTS(SELECT 1 FROM pg_class c
                   WHERE c.oid=v_spec.relation_name::regclass
                     AND c.relowner=v_coordinator
                     AND c.relkind='r' AND c.relpersistence='p'
                     AND NOT c.relrowsecurity AND NOT c.relforcerowsecurity
                     AND NOT c.relhasrules AND c.relreplident='d')
               OR NOT has_table_privilege(
                    'alr_challenger_consumption_coordinator',
                    v_spec.relation_name,'SELECT,INSERT')
               OR has_table_privilege(
                    'alr_challenger_consumption_caller',v_spec.relation_name,
                    'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
               OR EXISTS(SELECT 1 FROM pg_class c
                  CROSS JOIN LATERAL aclexplode(
                    COALESCE(c.relacl,acldefault('r',c.relowner))) privilege
                  WHERE c.oid=v_spec.relation_name::regclass
                    AND privilege.grantee<>c.relowner)
               OR (SELECT count(*) FROM pg_class c
                  CROSS JOIN LATERAL aclexplode(
                    COALESCE(c.relacl,acldefault('r',c.relowner))) privilege
                  WHERE c.oid=v_spec.relation_name::regclass
                    AND privilege.grantee=c.relowner
                    AND privilege.is_grantable
                    AND privilege.privilege_type IN (
                      'SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'))<>7 THEN
                RAISE EXCEPTION 'V160 exact replay catalog drift: %',
                                v_spec.relation_name;
            END IF;
        END LOOP;
        IF (SELECT count(*) FROM pg_temp.alr_v160_expected_constraints)<>23
           OR (SELECT count(*) FROM pg_constraint c
               WHERE c.conrelid IN (
                 'learning.alr_challenger_consumption_requests'::regclass,
                 'learning.alr_challenger_consumption_claims'::regclass,
                 'learning.alr_challenger_consumption_statuses'::regclass,
                 'learning.alr_challenger_consumption_verifier_evidence'::regclass,
                 'learning.alr_challenger_consumption_terminals'::regclass,
                 'learning.alr_challenger_consumption_reconciliation_audit'::regclass)
                 AND c.contype IN ('p','u','f','c'))<>23 THEN
            RAISE EXCEPTION 'V160 exact replay constraint inventory drift';
        END IF;
        FOR v_spec IN SELECT * FROM pg_temp.alr_v160_expected_constraints
                      ORDER BY relation_name,name LOOP
            SELECT c.oid,c.conkey,c.contype,c.condeferrable,c.condeferred,c.convalidated,
                   c.connoinherit,c.conislocal,c.coninhcount,c.conparentid,
                   c.conindid,c.confupdtype,c.confdeltype,c.confmatchtype,
                   (SELECT string_agg(a.attname,',' ORDER BY k.ordinality)
                    FROM unnest(c.conkey) WITH ORDINALITY k(attnum,ordinality)
                    JOIN pg_attribute a ON a.attrelid=c.conrelid
                                       AND a.attnum=k.attnum) AS key_columns,
                   CASE WHEN c.confrelid=0 THEN NULL
                        ELSE c.confrelid::regclass::TEXT END AS foreign_relation,
                   (SELECT string_agg(a.attname,',' ORDER BY k.ordinality)
                    FROM unnest(c.confkey) WITH ORDINALITY k(attnum,ordinality)
                    JOIN pg_attribute a ON a.attrelid=c.confrelid
                                       AND a.attnum=k.attnum) AS foreign_columns,
                   CASE WHEN c.contype='c'
                        THEN pg_get_expr(c.conbin,c.conrelid,FALSE) END AS check_expr
              INTO v_constraint
              FROM pg_constraint c
             WHERE c.conrelid=v_spec.relation_name::regclass
               AND c.conname=v_spec.name;
            IF NOT FOUND
               OR (SELECT count(*) FROM pg_constraint c
                   WHERE c.conrelid=v_spec.relation_name::regclass
                     AND c.conname=v_spec.name)<>1
               OR v_constraint.contype::TEXT<>v_spec.constraint_type
               OR v_constraint.condeferrable OR v_constraint.condeferred
               OR NOT v_constraint.convalidated OR NOT v_constraint.conislocal
               OR v_constraint.coninhcount<>0 OR v_constraint.conparentid<>0
               OR v_constraint.connoinherit<>(v_spec.constraint_type<>'c') THEN
                RAISE EXCEPTION 'V160 exact replay constraint posture drift: %',
                                v_spec.name;
            END IF;
            IF v_spec.constraint_type='c' THEN
                IF v_constraint.check_expr IS DISTINCT FROM (
                    SELECT pg_get_expr(c.conbin,c.conrelid,FALSE)
                    FROM pg_constraint c
                    WHERE c.conrelid=v_spec.expected_check_relation::regclass
                      AND c.conname=v_spec.expected_check_name) THEN
                    RAISE EXCEPTION 'V160 exact replay CHECK definition drift: %',
                                    v_spec.name;
                END IF;
            ELSIF v_constraint.key_columns IS DISTINCT FROM v_spec.key_columns
               OR v_constraint.foreign_relation IS DISTINCT FROM v_spec.foreign_relation
               OR v_constraint.foreign_columns IS DISTINCT FROM v_spec.foreign_columns
               OR (v_spec.constraint_type='f' AND (
                    v_constraint.confupdtype<>'a' OR v_constraint.confdeltype<>'a'
                    OR v_constraint.confmatchtype<>'s')) THEN
                RAISE EXCEPTION 'V160 exact replay key/FK definition drift: %',
                                v_spec.name;
            ELSIF v_spec.constraint_type IN ('p','u') AND NOT EXISTS (
                SELECT 1 FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid
                JOIN pg_am am ON am.oid=ic.relam
                WHERE i.indexrelid=v_constraint.conindid
                  AND ic.relname=v_spec.name AND ic.relowner=v_coordinator
                  AND ic.relkind='i' AND ic.relpersistence='p'
                  AND ic.reloptions IS NULL AND ic.reltablespace=0
                  AND am.amname='btree' AND i.indisunique
                  AND i.indisprimary=(v_spec.constraint_type='p')
                  AND NOT i.indisexclusion AND i.indimmediate
                  AND i.indisvalid AND i.indisready AND i.indislive
                  AND NOT i.indisclustered AND NOT i.indisreplident
                  AND NOT i.indcheckxmin AND NOT i.indnullsnotdistinct
                  AND i.indnkeyatts=i.indnatts
                  AND i.indnkeyatts=cardinality(v_constraint.conkey)
                  AND i.indexprs IS NULL AND i.indpred IS NULL
                  AND ARRAY(SELECT k FROM unnest(i.indkey)
                            WITH ORDINALITY x(k,o) ORDER BY o)=
                      v_constraint.conkey) THEN
                RAISE EXCEPTION 'V160 exact replay PK/UNIQUE index drift: %',
                                v_spec.name;
            END IF;
        END LOOP;
        FOR v_spec IN SELECT * FROM (VALUES
          ('learning.alr_challenger_fit_attestations'),
          ('learning.alr_challenger_training_runs'),
          ('learning.alr_challenger_model_artifacts'),
          ('learning.alr_challenger_registry')
        ) AS x(relation_name) LOOP
            IF NOT EXISTS (SELECT 1 FROM pg_class c
                           WHERE c.oid=v_spec.relation_name::regclass
                             AND c.relowner=v_coordinator)
               OR has_table_privilege('alr_challenger_writer',
                                      v_spec.relation_name,
                                      'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
               OR has_table_privilege('alr_challenger_fit_attestor',
                                      v_spec.relation_name,
                                      'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
               OR has_table_privilege('alr_challenger_trainer_caller',
                                      v_spec.relation_name,
                                      'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
               OR has_table_privilege('alr_challenger_fit_attestor_caller',
                                      v_spec.relation_name,
                                      'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
               OR EXISTS(SELECT 1 FROM pg_class c
                  CROSS JOIN LATERAL aclexplode(
                    COALESCE(c.relacl,acldefault('r',c.relowner))) privilege
                  WHERE c.oid=v_spec.relation_name::regclass
                    AND privilege.grantee<>c.relowner)
               OR (SELECT count(*) FROM pg_class c
                  CROSS JOIN LATERAL aclexplode(
                    COALESCE(c.relacl,acldefault('r',c.relowner))) privilege
                  WHERE c.oid=v_spec.relation_name::regclass
                    AND privilege.grantee=c.relowner
                    AND privilege.is_grantable
                    AND privilege.privilege_type IN (
                      'SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'))<>7 THEN
                RAISE EXCEPTION 'V160 exact replay V159 owner/closure drift: %',
                                v_spec.relation_name;
            END IF;
        END LOOP;
        FOR v_spec IN SELECT * FROM (VALUES
          ('alr_v160_immutable_requests_trg','learning.alr_challenger_consumption_requests'),
          ('alr_v160_immutable_claims_trg','learning.alr_challenger_consumption_claims'),
          ('alr_v160_immutable_statuses_trg','learning.alr_challenger_consumption_statuses'),
          ('alr_v160_immutable_verifier_evidence_trg','learning.alr_challenger_consumption_verifier_evidence'),
          ('alr_v160_immutable_terminals_trg','learning.alr_challenger_consumption_terminals'),
          ('alr_v160_immutable_reconciliation_trg','learning.alr_challenger_consumption_reconciliation_audit')
        ) AS x(name,relation_name) LOOP
            IF (SELECT count(*) FROM pg_trigger t
                WHERE t.tgname=v_spec.name AND NOT t.tgisinternal)<>1
               OR NOT EXISTS (SELECT 1 FROM pg_trigger t
                  WHERE t.tgname=v_spec.name
                    AND t.tgrelid=v_spec.relation_name::regclass
                    AND t.tgfoid='learning.alr_v160_reject_consumption_mutation()'::regprocedure
                    AND t.tgtype=27 AND t.tgenabled='O' AND t.tgnargs=0
                    AND t.tgqual IS NULL AND t.tgattr::TEXT=''
                    AND NOT t.tgdeferrable AND NOT t.tginitdeferred
                    AND t.tgconstraint=0) THEN
                RAISE EXCEPTION 'V160 exact replay trigger drift: %',v_spec.name;
            END IF;
        END LOOP;
        FOR v_spec IN SELECT * FROM (VALUES
          ('learning.alr_v160_reject_consumption_mutation()',
           'e8562a1e280b36a92c7a9110bcfe3bfc','coordinator'),
          ('learning.alr_v158_assert_complete_result()',
           '5bc309e618dd18c926d758cb7a606204','coordinator'),
          ('learning.alr_v159_assert_attested_bundle()',
           '5c7e7216a1e429a08557d33bb6d9701e','coordinator'),
          ('learning.persist_alr_challenger_fit_attestation_v1(bytea,jsonb,text,text,text,text,text,text,text,text,text,text,text,text,text,text,timestamp with time zone,timestamp with time zone)',
           '6046c06c3c1d9474915a2bcfa8eeea63','attestor'),
          ('learning.persist_alr_challenger_training_result_v2(text,text,text,text,text,text,text,text,text,text,integer,text,text,timestamp with time zone,timestamp with time zone,text,bigint,text,bigint,text,bigint)',
           '3aef68c2429a9b973f4a4ee983f5993b','writer'),
          ('learning.read_alr_challenger_training_result_v2(text,text)',
           '282f6d341ed9c8e4f51facc7b341097d','writer'),
          ('learning.coordinate_alr_challenger_consumption_v1(text,jsonb)',
           'f733ebd97a6a42f3da7fa5af15f072a8','coordinator'),
          ('learning.read_alr_challenger_consumption_v1(text)',
           '27679331a7c07211a70f862d39c3d1ff','coordinator')
        ) AS x(identity,body_md5,owner_kind) LOOP
            v_oid:=to_regprocedure(v_spec.identity);
            IF v_oid IS NULL OR NOT EXISTS(SELECT 1 FROM pg_proc p
                WHERE p.oid=v_oid
                  AND p.proowner=CASE v_spec.owner_kind
                    WHEN 'coordinator' THEN v_coordinator
                    WHEN 'attestor' THEN v_attestor ELSE v_writer END
                  AND p.prosecdef
                  AND p.proconfig IS NOT DISTINCT FROM CASE
                      WHEN v_spec.identity=
                        'learning.coordinate_alr_challenger_consumption_v1(text,jsonb)'
                      THEN ARRAY['search_path=pg_catalog, pg_temp',
                                 'lock_timeout=15s',
                                 'statement_timeout=120s']::TEXT[]
                      ELSE ARRAY['search_path=pg_catalog, pg_temp']::TEXT[] END
                  AND md5(p.prosrc)=v_spec.body_md5)
               OR EXISTS(SELECT 1 FROM pg_proc p
                  CROSS JOIN LATERAL aclexplode(COALESCE(
                    p.proacl,acldefault('f',p.proowner))) privilege
                  WHERE p.oid=v_oid AND privilege.grantee<>p.proowner
                    AND NOT (v_spec.identity IN (
                      'learning.coordinate_alr_challenger_consumption_v1(text,jsonb)',
                      'learning.read_alr_challenger_consumption_v1(text)')
                      AND privilege.grantee=v_caller)) THEN
                RAISE EXCEPTION 'V160 exact replay function drift: %',v_spec.identity;
            END IF;
        END LOOP;
        IF NOT has_function_privilege('alr_challenger_consumption_caller',
             'learning.coordinate_alr_challenger_consumption_v1(text,jsonb)'::regprocedure,
             'EXECUTE')
           OR NOT has_function_privilege('alr_challenger_consumption_caller',
             'learning.read_alr_challenger_consumption_v1(text)'::regprocedure,
             'EXECUTE')
           OR has_function_privilege('alr_challenger_fit_attestor_caller',
             'learning.persist_alr_challenger_fit_attestation_v1(bytea,jsonb,text,text,text,text,text,text,text,text,text,text,text,text,text,text,timestamp with time zone,timestamp with time zone)'::regprocedure,
             'EXECUTE')
           OR has_function_privilege('alr_challenger_trainer_caller',
             'learning.persist_alr_challenger_training_result_v2(text,text,text,text,text,text,text,text,text,text,integer,text,text,timestamp with time zone,timestamp with time zone,text,bigint,text,bigint,text,bigint)'::regprocedure,
             'EXECUTE')
           OR has_function_privilege('alr_challenger_trainer_caller',
             'learning.read_alr_challenger_training_result_v2(text,text)'::regprocedure,
             'EXECUTE')
           OR has_schema_privilege('alr_challenger_consumption_caller',
                                   'learning','CREATE')
           OR has_parameter_privilege('alr_challenger_consumption_caller',
                                      'session_replication_role','SET')
           OR has_parameter_privilege('alr_challenger_writer',
                                      'session_replication_role','SET')
           OR has_parameter_privilege('alr_challenger_trainer_caller',
                                      'session_replication_role','SET')
           OR has_parameter_privilege('alr_challenger_fit_attestor',
                                      'session_replication_role','SET')
           OR has_parameter_privilege('alr_challenger_fit_attestor_caller',
                                      'session_replication_role','SET') THEN
            RAISE EXCEPTION 'V160 exact replay reachability drift';
        END IF;
    END IF;
END
$v160_preflight$;

-- Old V159 attest-only or partial rows were caller-claimed before atomic
-- consumption existed and are never promoted in place.  Lock the complete
-- surface in one fixed order before deciding the zero legacy state.
LOCK TABLE learning.alr_challenger_fit_attestations IN ACCESS EXCLUSIVE MODE;
LOCK TABLE learning.alr_challenger_training_runs IN ACCESS EXCLUSIVE MODE;
LOCK TABLE learning.alr_challenger_model_artifacts IN ACCESS EXCLUSIVE MODE;
LOCK TABLE learning.alr_challenger_registry IN ACCESS EXCLUSIVE MODE;
DO $v160_zero_legacy_rows$
BEGIN
    IF (SELECT count(*) FROM learning.alr_challenger_fit_attestations)<>0
       OR (SELECT count(*) FROM learning.alr_challenger_training_runs)<>0
       OR (SELECT count(*) FROM learning.alr_challenger_model_artifacts)<>0
       OR (SELECT count(*) FROM learning.alr_challenger_registry)<>0 THEN
        RAISE EXCEPTION 'V160 refuses pre-atomic V159 rows; explicit reconciliation required';
    END IF;
END
$v160_zero_legacy_rows$;

CREATE TABLE IF NOT EXISTS learning.alr_challenger_consumption_requests (
    request_hash TEXT NOT NULL,
    request_bytes BYTEA NOT NULL,
    request_projection JSONB NOT NULL,
    verification_receipt_bytes BYTEA NOT NULL,
    verification_receipt_hash TEXT NOT NULL,
    verification_receipt JSONB NOT NULL,
    durable_receipt_hash TEXT NOT NULL,
    training_key_hash TEXT NOT NULL,
    request_generation BIGINT NOT NULL,
    issuer_id TEXT NOT NULL,
    nonce_digest TEXT NOT NULL,
    accept_by TIMESTAMPTZ NOT NULL,
    complete_by TIMESTAMPTZ NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_consumption_requests_pk PRIMARY KEY (request_hash),
    CONSTRAINT alr_consumption_requests_admission_generation_uniq
        UNIQUE (durable_receipt_hash,training_key_hash,request_generation),
    CONSTRAINT alr_consumption_requests_issuer_nonce_uniq
        UNIQUE (issuer_id,nonce_digest),
    CONSTRAINT alr_consumption_requests_hashes_check CHECK (
        request_hash~'^[0-9a-f]{64}$'
        AND durable_receipt_hash~'^[0-9a-f]{64}$'
        AND training_key_hash~'^[0-9a-f]{64}$'
        AND nonce_digest~'^[0-9a-f]{64}$'
    ),
    CONSTRAINT alr_consumption_requests_shape_check CHECK (
        octet_length(request_bytes) BETWEEN 2 AND 1048576
        AND jsonb_typeof(request_projection)='object'
        AND octet_length(verification_receipt_bytes) BETWEEN 2 AND 1048576
        AND verification_receipt_hash~'^[0-9a-f]{64}$'
        AND verification_receipt_hash=encode(
            public.digest(verification_receipt_bytes,'sha256'::TEXT),'hex'::TEXT)
        AND convert_from(verification_receipt_bytes,'UTF8'::NAME)::JSONB=verification_receipt
        AND jsonb_typeof(verification_receipt)='object'
        AND request_generation>0
        AND issuer_id~'^[a-z0-9][a-z0-9_.:-]{0,127}$'
        AND accept_by<complete_by
    )
);

CREATE TABLE IF NOT EXISTS learning.alr_challenger_consumption_claims (
    request_hash TEXT NOT NULL,
    claim_bytes BYTEA NOT NULL,
    claim_projection JSONB NOT NULL,
    verification_receipt_bytes BYTEA NOT NULL,
    verification_receipt_hash TEXT NOT NULL,
    verification_receipt JSONB NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_consumption_claims_pk PRIMARY KEY (request_hash),
    CONSTRAINT alr_consumption_claims_request_fk FOREIGN KEY (request_hash)
        REFERENCES learning.alr_challenger_consumption_requests(request_hash),
    CONSTRAINT alr_consumption_claims_shape_check CHECK (
        octet_length(claim_bytes) BETWEEN 2 AND 1048576
        AND jsonb_typeof(claim_projection)='object'
        AND octet_length(verification_receipt_bytes) BETWEEN 2 AND 1048576
        AND verification_receipt_hash~'^[0-9a-f]{64}$'
        AND verification_receipt_hash=encode(
            public.digest(verification_receipt_bytes,'sha256'::TEXT),'hex'::TEXT)
        AND convert_from(verification_receipt_bytes,'UTF8'::NAME)::JSONB=verification_receipt
        AND jsonb_typeof(verification_receipt)='object'
    )
);

CREATE TABLE IF NOT EXISTS learning.alr_challenger_consumption_statuses (
    request_hash TEXT NOT NULL,
    status_generation BIGINT NOT NULL,
    response_hash TEXT NOT NULL,
    response_bytes BYTEA NOT NULL,
    response_projection JSONB NOT NULL,
    verification_receipt_bytes BYTEA NOT NULL,
    verification_receipt_hash TEXT NOT NULL,
    verification_receipt JSONB NOT NULL,
    status_issued_at TIMESTAMPTZ NOT NULL,
    status_expires_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_consumption_statuses_pk
        PRIMARY KEY (request_hash,status_generation),
    CONSTRAINT alr_consumption_statuses_response_uniq UNIQUE (response_hash),
    CONSTRAINT alr_consumption_statuses_request_fk FOREIGN KEY (request_hash)
        REFERENCES learning.alr_challenger_consumption_requests(request_hash),
    CONSTRAINT alr_consumption_statuses_shape_check CHECK (
        status_generation>0 AND response_hash~'^[0-9a-f]{64}$'
        AND octet_length(response_bytes) BETWEEN 2 AND 2097152
        AND jsonb_typeof(response_projection)='object'
        AND octet_length(verification_receipt_bytes) BETWEEN 2 AND 1048576
        AND verification_receipt_hash~'^[0-9a-f]{64}$'
        AND verification_receipt_hash=encode(
            public.digest(verification_receipt_bytes,'sha256'::TEXT),'hex'::TEXT)
        AND convert_from(verification_receipt_bytes,'UTF8'::NAME)::JSONB=verification_receipt
        AND jsonb_typeof(verification_receipt)='object'
        AND status_issued_at<status_expires_at
    )
);

CREATE TABLE IF NOT EXISTS learning.alr_challenger_consumption_verifier_evidence (
    verifier_receipt_hash TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    action TEXT NOT NULL,
    declared_phase TEXT NOT NULL,
    verification_receipt_bytes BYTEA NOT NULL,
    verification_receipt JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_consumption_verifier_evidence_pk
        PRIMARY KEY (request_hash,action,verifier_receipt_hash),
    CONSTRAINT alr_consumption_verifier_evidence_request_fk
        FOREIGN KEY (request_hash) REFERENCES
        learning.alr_challenger_consumption_requests(request_hash),
    CONSTRAINT alr_consumption_verifier_evidence_shape_check CHECK (
        verifier_receipt_hash~'^[0-9a-f]{64}$'
        AND action IN ('REGISTER_REQUEST','CLAIM_REQUEST','RECORD_STATUS',
                       'CONSUME_TERMINAL','MARK_RECONCILE_REQUIRED')
        AND declared_phase IN ('REQUEST_ONLY','SIGNED_STATUS',
                               'TERMINAL_SUCCESS','TERMINAL_NO_INNER')
        AND octet_length(verification_receipt_bytes) BETWEEN 2 AND 1048576
        AND verifier_receipt_hash=encode(
            public.digest(verification_receipt_bytes,'sha256'::TEXT),'hex'::TEXT)
        AND convert_from(verification_receipt_bytes,'UTF8'::NAME)::JSONB=verification_receipt
        AND jsonb_typeof(verification_receipt)='object'
    )
);

CREATE TABLE IF NOT EXISTS learning.alr_challenger_consumption_terminals (
    request_hash TEXT NOT NULL,
    terminal_hash TEXT NOT NULL,
    outcome TEXT NOT NULL,
    terminal_bytes BYTEA NOT NULL,
    terminal_projection JSONB NOT NULL,
    inner_receipt_bytes BYTEA,
    verification_receipt_bytes BYTEA,
    verification_receipt_hash TEXT,
    verification_receipt JSONB,
    consumed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_consumption_terminals_pk PRIMARY KEY (request_hash),
    CONSTRAINT alr_consumption_terminals_hash_uniq UNIQUE (terminal_hash),
    CONSTRAINT alr_consumption_terminals_request_fk FOREIGN KEY (request_hash)
        REFERENCES learning.alr_challenger_consumption_requests(request_hash),
    CONSTRAINT alr_consumption_terminals_shape_check CHECK (
        terminal_hash~'^[0-9a-f]{64}$'
        AND outcome IN ('SUCCEEDED','REJECTED_PRE_FIT',
                        'FAILED_AFTER_START','EXPIRED_UNCLAIMED')
        AND octet_length(terminal_bytes) BETWEEN 2 AND 2097152
        AND jsonb_typeof(terminal_projection)='object'
        AND ((outcome='SUCCEEDED' AND inner_receipt_bytes IS NOT NULL
              AND verification_receipt_bytes IS NOT NULL
              AND verification_receipt_hash IS NOT NULL
              AND verification_receipt IS NOT NULL)
          OR (outcome IN ('REJECTED_PRE_FIT','FAILED_AFTER_START')
              AND inner_receipt_bytes IS NULL
              AND verification_receipt_bytes IS NOT NULL
              AND verification_receipt_hash IS NOT NULL
              AND verification_receipt IS NOT NULL)
          OR (outcome='EXPIRED_UNCLAIMED' AND inner_receipt_bytes IS NULL
              AND verification_receipt_bytes IS NULL
              AND verification_receipt_hash IS NULL
              AND verification_receipt IS NULL))
        AND (verification_receipt_bytes IS NULL OR (
            octet_length(verification_receipt_bytes) BETWEEN 2 AND 1048576
            AND verification_receipt_hash~'^[0-9a-f]{64}$'
            AND verification_receipt_hash=encode(
                public.digest(verification_receipt_bytes,'sha256'::TEXT),'hex'::TEXT)
            AND convert_from(verification_receipt_bytes,'UTF8'::NAME)::JSONB=verification_receipt
            AND jsonb_typeof(verification_receipt)='object'))
    )
);

CREATE TABLE IF NOT EXISTS learning.alr_challenger_consumption_reconciliation_audit (
    reconciliation_hash TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    reason TEXT NOT NULL,
    event_bytes BYTEA NOT NULL,
    event_projection JSONB NOT NULL,
    verification_receipt_bytes BYTEA,
    verification_receipt_hash TEXT,
    verification_receipt JSONB,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT alr_consumption_reconciliation_pk
        PRIMARY KEY (reconciliation_hash),
    CONSTRAINT alr_consumption_reconciliation_identity_uniq
        UNIQUE (request_hash,reconciliation_hash),
    CONSTRAINT alr_consumption_reconciliation_request_fk FOREIGN KEY (request_hash)
        REFERENCES learning.alr_challenger_consumption_requests(request_hash),
    CONSTRAINT alr_consumption_reconciliation_shape_check CHECK (
        reconciliation_hash~'^[0-9a-f]{64}$'
        AND reason IN ('AMBIGUOUS_RESPONSE','FAILED_AFTER_START')
        AND octet_length(event_bytes) BETWEEN 2 AND 2097152
        AND jsonb_typeof(event_projection)='object'
        AND ((verification_receipt_bytes IS NULL
              AND verification_receipt_hash IS NULL
              AND verification_receipt IS NULL)
          OR (octet_length(verification_receipt_bytes) BETWEEN 2 AND 1048576
              AND verification_receipt_hash~'^[0-9a-f]{64}$'
              AND verification_receipt_hash=encode(
                  public.digest(verification_receipt_bytes,'sha256'::TEXT),'hex'::TEXT)
              AND convert_from(verification_receipt_bytes,
                  'UTF8'::NAME)::JSONB=verification_receipt
              AND jsonb_typeof(verification_receipt)='object'))
    )
);

-- Every relation writable by the atomic coordinator is owned by its NOLOGIN,
-- membership-free execution role.  V158 admission remains on its frozen owner.
ALTER TABLE learning.alr_challenger_fit_attestations
    OWNER TO alr_challenger_consumption_coordinator;
ALTER TABLE learning.alr_challenger_training_runs
    OWNER TO alr_challenger_consumption_coordinator;
ALTER TABLE learning.alr_challenger_model_artifacts
    OWNER TO alr_challenger_consumption_coordinator;
ALTER TABLE learning.alr_challenger_registry
    OWNER TO alr_challenger_consumption_coordinator;
ALTER TABLE learning.alr_challenger_consumption_requests
    OWNER TO alr_challenger_consumption_coordinator;
ALTER TABLE learning.alr_challenger_consumption_claims
    OWNER TO alr_challenger_consumption_coordinator;
ALTER TABLE learning.alr_challenger_consumption_statuses
    OWNER TO alr_challenger_consumption_coordinator;
ALTER TABLE learning.alr_challenger_consumption_verifier_evidence
    OWNER TO alr_challenger_consumption_coordinator;
ALTER TABLE learning.alr_challenger_consumption_terminals
    OWNER TO alr_challenger_consumption_coordinator;
ALTER TABLE learning.alr_challenger_consumption_reconciliation_audit
    OWNER TO alr_challenger_consumption_coordinator;

CREATE OR REPLACE FUNCTION learning.alr_v160_reject_consumption_mutation()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $v160_immutable$
BEGIN
    IF current_user<>'alr_challenger_consumption_coordinator' THEN
        RAISE EXCEPTION 'V160 immutable trigger owner identity rejected';
    END IF;
    IF current_setting('session_replication_role')<>'origin' THEN
        RAISE EXCEPTION 'V160 immutable trigger requires session_replication_role=origin';
    END IF;
    RAISE EXCEPTION 'V160 append-only relation rejects %',TG_OP;
END
$v160_immutable$;
ALTER FUNCTION learning.alr_v160_reject_consumption_mutation()
    OWNER TO alr_challenger_consumption_coordinator;
REVOKE ALL ON FUNCTION learning.alr_v160_reject_consumption_mutation()
FROM PUBLIC;

DO $v160_append_only_triggers$
DECLARE
    v_relation TEXT;
    v_trigger TEXT;
BEGIN
    FOR v_relation,v_trigger IN SELECT * FROM (VALUES
      ('learning.alr_challenger_consumption_requests','alr_v160_immutable_requests_trg'),
      ('learning.alr_challenger_consumption_claims','alr_v160_immutable_claims_trg'),
      ('learning.alr_challenger_consumption_statuses','alr_v160_immutable_statuses_trg'),
      ('learning.alr_challenger_consumption_verifier_evidence','alr_v160_immutable_verifier_evidence_trg'),
      ('learning.alr_challenger_consumption_terminals','alr_v160_immutable_terminals_trg'),
      ('learning.alr_challenger_consumption_reconciliation_audit','alr_v160_immutable_reconciliation_trg')
    ) AS x(relation_name,trigger_name) LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_trigger
            WHERE tgrelid=v_relation::regclass AND tgname=v_trigger
              AND NOT tgisinternal) THEN
            EXECUTE format(
                'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %s '
                'FOR EACH ROW EXECUTE FUNCTION '
                'learning.alr_v160_reject_consumption_mutation()',
                v_trigger,v_relation
            );
        END IF;
    END LOOP;
END
$v160_append_only_triggers$;

-- V158 and V159 both installed deferred completeness triggers.  The V160
-- coordinator inserts the same complete bundle in one transaction, so both
-- trigger identities are rebound without calling either application wrapper.
CREATE OR REPLACE FUNCTION learning.alr_v158_assert_complete_result()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $v160_v158_complete_trigger$
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
    IF session_user<>'alr_challenger_consumption_caller'
       OR current_user<>'alr_challenger_consumption_coordinator' THEN
        RAISE EXCEPTION 'V160 V158 completeness trigger session identity rejected';
    END IF;
    IF current_setting('session_replication_role')<>'origin' THEN
        RAISE EXCEPTION 'V160 V158 completeness trigger requires session_replication_role=origin';
    END IF;
    v_run_hash:=CASE WHEN TG_OP='DELETE' THEN OLD.training_run_hash
                     ELSE NEW.training_run_hash END;
    SELECT r.* INTO v_run FROM learning.alr_challenger_training_runs r
    WHERE r.training_run_hash=v_run_hash;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'V160 complete result invariant: run missing';
    END IF;
    SELECT count(*),count(DISTINCT quantile),count(DISTINCT artifact_hash),
           count(*) FILTER (WHERE training_key_hash=v_run.training_key_hash
             AND model_artifact_set_hash=v_run.model_artifact_set_hash
             AND feature_schema_hash=v_run.actual_feature_schema_hash
             AND model_schema_version=v_run.model_schema_version
             AND artifact_format='onnx' AND symlink_created IS FALSE
             AND serving_visible IS FALSE),
           encode(public.digest(convert_to(format(
             E'q10=%s\nq50=%s\nq90=%s\n',
             max(artifact_hash) FILTER (WHERE quantile='q10'),
             max(artifact_hash) FILTER (WHERE quantile='q50'),
             max(artifact_hash) FILTER (WHERE quantile='q90')),
             'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT)
      INTO v_artifact_count,v_quantile_count,v_hash_count,
           v_schema_match_count,v_set_hash
    FROM learning.alr_challenger_model_artifacts
    WHERE training_run_hash=v_run_hash;
    IF v_artifact_count<>3 OR v_quantile_count<>3 OR v_hash_count<>3
       OR v_schema_match_count<>3
       OR v_set_hash IS DISTINCT FROM v_run.model_artifact_set_hash THEN
        RAISE EXCEPTION 'V160 complete result invariant: exact q10/q50/q90 required';
    END IF;
    SELECT count(*) INTO v_registry_count
    FROM learning.alr_challenger_registry g
    WHERE g.training_run_hash=v_run_hash
      AND g.training_key_hash=v_run.training_key_hash
      AND g.model_artifact_set_hash=v_run.model_artifact_set_hash
      AND g.registry_status='NOT_SERVING'
      AND g.serving_allowed IS FALSE AND g.promotion_allowed IS FALSE
      AND g.latest_pointer_allowed IS FALSE AND g.symlink_allowed IS FALSE;
    IF v_registry_count<>1 THEN
        RAISE EXCEPTION 'V160 complete result invariant: exact NOT_SERVING registry required';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END
$v160_v158_complete_trigger$;
ALTER FUNCTION learning.alr_v158_assert_complete_result()
    OWNER TO alr_challenger_consumption_coordinator;
REVOKE ALL ON FUNCTION learning.alr_v158_assert_complete_result() FROM PUBLIC;
REVOKE ALL ON FUNCTION learning.alr_v158_assert_complete_result() FROM
    alr_challenger_writer,alr_challenger_trainer_caller,
    alr_challenger_fit_attestor,alr_challenger_fit_attestor_caller,
    alr_challenger_consumption_caller;

CREATE OR REPLACE FUNCTION learning.alr_v159_assert_attested_bundle()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $v160_v159_complete_trigger$
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
    IF session_user<>'alr_challenger_consumption_caller'
       OR current_user<>'alr_challenger_consumption_coordinator' THEN
        RAISE EXCEPTION 'V160 V159 completeness trigger session identity rejected';
    END IF;
    IF current_setting('session_replication_role')<>'origin' THEN
        RAISE EXCEPTION 'V160 V159 completeness trigger requires session_replication_role=origin';
    END IF;
    v_structural_run_hash:=CASE WHEN TG_OP='DELETE' THEN OLD.training_run_hash
                                ELSE NEW.training_run_hash END;
    SELECT r.* INTO v_run FROM learning.alr_challenger_training_runs r
    WHERE r.training_run_hash=v_structural_run_hash;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'V160 complete bundle invariant: exact attested run required';
    END IF;
    SELECT a.* INTO v_attestation
    FROM learning.alr_challenger_fit_attestations a
    WHERE a.durable_attestation_hash=v_run.durable_attestation_hash;
    IF NOT FOUND
       OR v_attestation.durable_receipt_hash IS DISTINCT FROM v_run.durable_receipt_hash
       OR v_attestation.training_key_hash IS DISTINCT FROM v_run.training_key_hash
       OR v_attestation.structural_training_run_hash IS DISTINCT FROM v_run.training_run_hash
       OR v_attestation.ordered_artifact_set_hash IS DISTINCT FROM v_run.model_artifact_set_hash
       OR v_attestation.verified_at IS DISTINCT FROM v_run.attestation_verified_at
       OR v_attestation.expires_at IS DISTINCT FROM v_run.attestation_expires_at
       OR v_run.attestation_bound_at<v_attestation.verified_at
       OR v_run.attestation_bound_at>=v_attestation.expires_at THEN
        RAISE EXCEPTION 'V160 complete bundle invariant: attestation lineage mismatch';
    END IF;
    SELECT count(*),count(DISTINCT m.quantile),count(*) FILTER (WHERE
               m.durable_attestation_hash=v_run.durable_attestation_hash
           AND m.durable_training_run_hash=v_run.durable_training_run_hash
           AND m.training_key_hash=v_run.training_key_hash
           AND m.model_artifact_set_hash=v_run.model_artifact_set_hash
           AND m.feature_schema_hash=v_run.actual_feature_schema_hash
           AND m.model_schema_version=v_run.model_schema_version
           AND m.artifact_format='onnx'
           AND m.artifact_path='runs/structural/'||v_run.training_run_hash||'/'||m.quantile||'.onnx'
           AND m.symlink_created IS FALSE AND m.serving_visible IS FALSE),
           encode(public.digest(convert_to(format(
               E'q10=%s\nq50=%s\nq90=%s\n',
               max(m.artifact_hash) FILTER (WHERE m.quantile='q10'),
               max(m.artifact_hash) FILTER (WHERE m.quantile='q50'),
               max(m.artifact_hash) FILTER (WHERE m.quantile='q90')),
               'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT)
      INTO v_artifact_count,v_quantile_count,v_exact_artifacts,v_set_hash
    FROM learning.alr_challenger_model_artifacts m
    WHERE m.training_run_hash=v_run.training_run_hash;
    IF v_artifact_count<>3 OR v_quantile_count<>3 OR v_exact_artifacts<>3
       OR v_set_hash IS DISTINCT FROM v_run.model_artifact_set_hash THEN
        RAISE EXCEPTION 'V160 complete bundle invariant: exact ordered q10/q50/q90 required';
    END IF;
    SELECT count(*) INTO v_registry_count
    FROM learning.alr_challenger_registry g
    WHERE g.training_run_hash=v_run.training_run_hash;
    SELECT g.* INTO v_registry FROM learning.alr_challenger_registry g
    WHERE g.training_run_hash=v_run.training_run_hash
      AND g.durable_training_run_hash=v_run.durable_training_run_hash
      AND g.durable_attestation_hash=v_run.durable_attestation_hash
      AND g.training_key_hash=v_run.training_key_hash
      AND g.model_artifact_set_hash=v_run.model_artifact_set_hash;
    IF v_registry_count<>1 OR NOT FOUND
       OR v_registry.challenger_hash IS DISTINCT FROM v_attestation.structural_challenger_hash
       OR v_registry.attestation_bound_at IS DISTINCT FROM v_run.attestation_bound_at
       OR v_registry.registry_status<>'NOT_SERVING'
       OR v_registry.serving_allowed IS NOT FALSE
       OR v_registry.promotion_allowed IS NOT FALSE
       OR v_registry.latest_pointer_allowed IS NOT FALSE
       OR v_registry.symlink_allowed IS NOT FALSE THEN
        RAISE EXCEPTION 'V160 complete bundle invariant: exact NOT_SERVING registry required';
    END IF;
    RETURN NULL;
END
$v160_v159_complete_trigger$;
ALTER FUNCTION learning.alr_v159_assert_attested_bundle()
    OWNER TO alr_challenger_consumption_coordinator;
REVOKE ALL ON FUNCTION learning.alr_v159_assert_attested_bundle() FROM PUBLIC;
REVOKE ALL ON FUNCTION learning.alr_v159_assert_attested_bundle() FROM
    alr_challenger_writer,alr_challenger_trainer_caller,
    alr_challenger_fit_attestor,alr_challenger_fit_attestor_caller,
    alr_challenger_consumption_caller;

-- Old V159 application paths are executable hard failures even if a future
-- ACL accidentally reopens one.  V158 qualified-receipt persist/read functions
-- are intentionally not replaced or re-granted here.
CREATE OR REPLACE FUNCTION learning.persist_alr_challenger_fit_attestation_v1(
    p_signed_receipt_bytes BYTEA,p_receipt_projection JSONB,
    p_durable_receipt_hash TEXT,p_training_key_hash TEXT,
    p_structural_result_hash TEXT,p_structural_fit_capture_hash TEXT,
    p_structural_candidate_hash TEXT,p_structural_training_run_hash TEXT,
    p_structural_challenger_hash TEXT,p_runner_identity_hash TEXT,
    p_actual_input_material_set_hash TEXT,p_ordered_artifact_set_hash TEXT,
    p_issuer_id TEXT,p_trust_policy_id TEXT,p_signature_key_id TEXT,
    p_signature_algorithm TEXT,p_verified_at TIMESTAMPTZ,p_expires_at TIMESTAMPTZ
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $v160_closed_v159_attestation$
BEGIN
    RAISE EXCEPTION 'V160 closed V159 attestation wrapper: atomic coordinator required';
END
$v160_closed_v159_attestation$;

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
SET search_path=pg_catalog,pg_temp AS $v160_closed_v159_result$
BEGIN
    RAISE EXCEPTION 'V160 closed V159 result wrapper: atomic coordinator required';
END
$v160_closed_v159_result$;

CREATE OR REPLACE FUNCTION learning.read_alr_challenger_training_result_v2(
    p_durable_attestation_hash TEXT,p_structural_training_run_hash TEXT
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $v160_closed_v159_reader$
BEGIN
    RAISE EXCEPTION 'V160 closed V159 result reader: fixed consumption read required';
END
$v160_closed_v159_reader$;

CREATE OR REPLACE FUNCTION learning.coordinate_alr_challenger_consumption_v1(
    p_action TEXT,p_payload JSONB
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp
SET lock_timeout='15s'
SET statement_timeout='120s'
AS $v160_coordinator$
DECLARE
    v_request learning.alr_challenger_consumption_requests%ROWTYPE;
    v_claim learning.alr_challenger_consumption_claims%ROWTYPE;
    v_status learning.alr_challenger_consumption_statuses%ROWTYPE;
    v_terminal learning.alr_challenger_consumption_terminals%ROWTYPE;
    v_request_bytes BYTEA;
    v_event_bytes BYTEA;
    v_verifier_bytes BYTEA;
    v_inner_bytes BYTEA;
    v_projection JSONB;
    v_verifier JSONB;
    v_inner JSONB;
    v_request_hash TEXT;
    v_verifier_hash TEXT;
    v_event_hash TEXT;
    v_phase TEXT;
    v_outcome TEXT;
    v_now TIMESTAMPTZ;
    v_lock_key BIGINT;
    v_generation BIGINT;
    v_previous_generation BIGINT;
    v_previous_status_generation BIGINT;
    v_previous_status_issued TIMESTAMPTZ;
    v_durable_receipt_hash TEXT;
    v_training_key_hash TEXT;
    v_issuer_id TEXT;
    v_nonce_digest TEXT;
    v_accept_by TIMESTAMPTZ;
    v_complete_by TIMESTAMPTZ;
    v_q10_hash TEXT;
    v_q50_hash TEXT;
    v_q90_hash TEXT;
    v_q10_size BIGINT;
    v_q50_size BIGINT;
    v_q90_size BIGINT;
    v_set_hash TEXT;
    v_external_digest TEXT;
    v_attestation_hash TEXT;
    v_durable_run_hash TEXT;
    v_durable_challenger_hash TEXT;
    v_structural_result_hash TEXT;
    v_structural_fit_capture_hash TEXT;
    v_structural_candidate_hash TEXT;
    v_structural_run_hash TEXT;
    v_structural_challenger_hash TEXT;
    v_runner_identity_hash TEXT;
    v_material_set_hash TEXT;
    v_verified_at TIMESTAMPTZ;
    v_expires_at TIMESTAMPTZ;
    v_bound_at TIMESTAMPTZ;
    v_observation JSONB;
    v_run_payload JSONB;
    v_registry_payload JSONB;
    v_reconciliation_hash TEXT;
    v_no_authority JSONB := '{"exchange_authority":false,"trading_authority":false,"order_or_probe_authority":false,"decision_lease_authority":false,"cost_gate_authority":false,"proof_authority":false,"serving_authority":false,"promotion_authority":false,"latest_authority":false,"runtime_mutation_authority":false,"database_write_authority":false,"symlink_authority":false}'::JSONB;
    v_zero_counters JSONB := '{"exchange_contact_count":0,"trading_action_count":0,"order_or_probe_count":0,"decision_lease_count":0,"cost_gate_change_count":0,"proof_claim_count":0,"serving_or_promotion_count":0,"runtime_mutation_count":0,"database_write_count":0,"symlink_update_count":0,"model_fit_count":0}'::JSONB;
BEGIN
    IF session_user<>'alr_challenger_consumption_caller'
       OR current_user<>'alr_challenger_consumption_coordinator' THEN
        RAISE EXCEPTION 'V160 coordinator session identity rejected';
    END IF;
    IF current_setting('session_replication_role')<>'origin' THEN
        RAISE EXCEPTION 'V160 coordinator requires session_replication_role=origin';
    END IF;
    IF p_action IS NULL OR p_action NOT IN (
        'REGISTER_REQUEST','CLAIM_REQUEST','RECORD_STATUS','CONSUME_TERMINAL',
        'EXPIRE_UNCLAIMED','MARK_RECONCILE_REQUIRED'
    ) OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'V160 closed action or payload rejected';
    END IF;

    IF p_action='REGISTER_REQUEST' THEN
        IF NOT p_payload?&ARRAY['request_bytes_hex','request_projection',
              'verification_receipt_bytes_hex','verification_receipt']::TEXT[]
           OR p_payload-ARRAY['request_bytes_hex','request_projection',
              'verification_receipt_bytes_hex','verification_receipt']::TEXT[]<>'{}'::JSONB THEN
            RAISE EXCEPTION 'V160 REGISTER_REQUEST payload fields rejected';
        END IF;
        v_request_bytes:=decode(p_payload->>'request_bytes_hex','hex');
        v_projection:=p_payload->'request_projection';
        v_verifier_bytes:=decode(p_payload->>'verification_receipt_bytes_hex','hex');
        v_verifier:=p_payload->'verification_receipt';
        IF convert_from(v_request_bytes,'UTF8'::NAME)::JSONB IS DISTINCT FROM v_projection
           OR convert_from(v_verifier_bytes,'UTF8'::NAME)::JSONB IS DISTINCT FROM v_verifier THEN
            RAISE EXCEPTION 'V160 REGISTER_REQUEST byte projection mismatch';
        END IF;
        v_request_hash:=v_projection->>'request_hash';
        v_durable_receipt_hash:=v_projection#>>'{signed_payload,admission,durable_receipt_hash}';
        v_training_key_hash:=v_projection#>>'{signed_payload,admission,training_key_hash}';
        v_generation:=(v_projection#>>'{signed_payload,request_generation}')::BIGINT;
        v_issuer_id:=v_projection#>>'{signed_payload,issuer_id}';
        v_nonce_digest:=v_projection#>>'{signed_payload,nonce_digest}';
        v_accept_by:=(v_projection#>>'{signed_payload,accept_by}')::TIMESTAMPTZ;
        v_complete_by:=(v_projection#>>'{signed_payload,complete_by}')::TIMESTAMPTZ;
        v_phase:='REQUEST_ONLY';
    ELSIF p_action IN ('CLAIM_REQUEST','RECORD_STATUS','CONSUME_TERMINAL',
                        'MARK_RECONCILE_REQUIRED') THEN
        v_request_hash:=p_payload->>'request_hash';
        SELECT * INTO v_request FROM learning.alr_challenger_consumption_requests
        WHERE request_hash=v_request_hash;
        IF NOT FOUND THEN RAISE EXCEPTION 'V160 registered request not found'; END IF;
        v_durable_receipt_hash:=v_request.durable_receipt_hash;
        v_training_key_hash:=v_request.training_key_hash;
        v_generation:=v_request.request_generation;
        v_issuer_id:=v_request.issuer_id;
        v_nonce_digest:=v_request.nonce_digest;
        v_accept_by:=v_request.accept_by;
        v_complete_by:=v_request.complete_by;
        IF p_action='CLAIM_REQUEST' THEN
            IF NOT p_payload?&ARRAY['request_hash','claim_bytes_hex','claim_projection',
                  'verification_receipt_bytes_hex','verification_receipt']::TEXT[]
               OR p_payload-ARRAY['request_hash','claim_bytes_hex','claim_projection',
                  'verification_receipt_bytes_hex','verification_receipt']::TEXT[]<>'{}'::JSONB THEN
                RAISE EXCEPTION 'V160 CLAIM_REQUEST payload fields rejected';
            END IF;
            v_event_bytes:=decode(p_payload->>'claim_bytes_hex','hex');
            v_projection:=p_payload->'claim_projection';
            v_phase:='REQUEST_ONLY';
        ELSIF p_action='RECORD_STATUS' THEN
            IF NOT p_payload?&ARRAY['request_hash','response_bytes_hex','response_projection',
                  'verification_receipt_bytes_hex','verification_receipt']::TEXT[]
               OR p_payload-ARRAY['request_hash','response_bytes_hex','response_projection',
                  'verification_receipt_bytes_hex','verification_receipt']::TEXT[]<>'{}'::JSONB THEN
                RAISE EXCEPTION 'V160 RECORD_STATUS payload fields rejected';
            END IF;
            v_event_bytes:=decode(p_payload->>'response_bytes_hex','hex');
            v_projection:=p_payload->'response_projection';
            v_phase:='SIGNED_STATUS';
        ELSIF p_action='CONSUME_TERMINAL' THEN
            IF NOT p_payload?&ARRAY['request_hash','response_bytes_hex','response_projection',
                  'inner_receipt_bytes_hex','verification_receipt_bytes_hex',
                  'verification_receipt']::TEXT[]
               OR p_payload-ARRAY['request_hash','response_bytes_hex','response_projection',
                  'inner_receipt_bytes_hex','verification_receipt_bytes_hex',
                  'verification_receipt']::TEXT[]<>'{}'::JSONB THEN
                RAISE EXCEPTION 'V160 CONSUME_TERMINAL payload fields rejected';
            END IF;
            v_event_bytes:=decode(p_payload->>'response_bytes_hex','hex');
            v_projection:=p_payload->'response_projection';
            v_outcome:=v_projection->>'outcome';
            v_phase:=CASE WHEN v_outcome='SUCCEEDED' THEN 'TERMINAL_SUCCESS'
                          ELSE 'TERMINAL_NO_INNER' END;
            IF v_outcome='SUCCEEDED' THEN
                v_inner_bytes:=decode(p_payload->>'inner_receipt_bytes_hex','hex');
                v_inner:=convert_from(v_inner_bytes,'UTF8'::NAME)::JSONB;
            ELSIF p_payload->'inner_receipt_bytes_hex'<>'null'::JSONB THEN
                RAISE EXCEPTION 'V160 non-success terminal forbids inner receipt';
            END IF;
        ELSE
            IF NOT p_payload?&ARRAY['request_hash','event_bytes_hex','event_projection',
                  'verification_receipt_bytes_hex','verification_receipt']::TEXT[]
               OR p_payload-ARRAY['request_hash','event_bytes_hex','event_projection',
                  'verification_receipt_bytes_hex','verification_receipt']::TEXT[]<>'{}'::JSONB THEN
                RAISE EXCEPTION 'V160 MARK_RECONCILE_REQUIRED payload fields rejected';
            END IF;
            v_event_bytes:=decode(p_payload->>'event_bytes_hex','hex');
            v_projection:=p_payload->'event_projection';
            v_phase:=CASE v_projection->>'response_kind'
                WHEN 'STATUS' THEN 'SIGNED_STATUS'
                WHEN 'TERMINAL' THEN 'TERMINAL_NO_INNER'
                ELSE NULL END;
        END IF;
        v_verifier_bytes:=decode(p_payload->>'verification_receipt_bytes_hex','hex');
        v_verifier:=p_payload->'verification_receipt';
        IF convert_from(v_event_bytes,'UTF8'::NAME)::JSONB IS DISTINCT FROM v_projection
           OR convert_from(v_verifier_bytes,'UTF8'::NAME)::JSONB IS DISTINCT FROM v_verifier THEN
            RAISE EXCEPTION 'V160 action byte projection mismatch';
        END IF;
    ELSE
        IF NOT p_payload?&ARRAY['request_hash','reason']::TEXT[]
           OR p_payload-ARRAY['request_hash','reason']::TEXT[]<>'{}'::JSONB
           OR p_payload->>'reason'<>'ACCEPT_WINDOW_ELAPSED' THEN
            RAISE EXCEPTION 'V160 EXPIRE_UNCLAIMED payload fields rejected';
        END IF;
        v_request_hash:=p_payload->>'request_hash';
        SELECT * INTO v_request FROM learning.alr_challenger_consumption_requests
        WHERE request_hash=v_request_hash;
        IF NOT FOUND THEN RAISE EXCEPTION 'V160 registered request not found'; END IF;
        v_durable_receipt_hash:=v_request.durable_receipt_hash;
        v_training_key_hash:=v_request.training_key_hash;
        v_generation:=v_request.request_generation;
        v_issuer_id:=v_request.issuer_id;
        v_nonce_digest:=v_request.nonce_digest;
        v_accept_by:=v_request.accept_by;
        v_complete_by:=v_request.complete_by;
    END IF;

    FOR v_lock_key IN
        SELECT DISTINCT hashtextextended(lock_material,0) AS lock_key
        FROM unnest(ARRAY[
          'v160:admission:'||v_durable_receipt_hash||':'||v_training_key_hash,
          'v160:generation:'||v_durable_receipt_hash||':'||v_training_key_hash||':'||v_generation,
          'v160:issuer_nonce:'||v_issuer_id||':'||v_nonce_digest,
          'v160:request:'||v_request_hash,
          'v159:attestation_inner:'||COALESCE(encode(public.digest(v_inner_bytes,'sha256'::TEXT),'hex'::TEXT),''),
          'v159:result:'||COALESCE(v_inner#>>'{subject,result_hash}',''),
          'v159:fit_capture:'||COALESCE(v_inner#>>'{subject,fit_capture_hash}',''),
          'v159:candidate:'||COALESCE(v_inner#>>'{subject,candidate_attestation_hash}',''),
          'v159:run:'||COALESCE(v_inner#>>'{subject,training_run_hash}',''),
          'v159:challenger:'||COALESCE(v_inner#>>'{subject,challenger_hash}',''),
          'v159:artifact:'||COALESCE(v_inner#>>'{result_observation,artifacts,q10,artifact_hash}',''),
          'v159:artifact:'||COALESCE(v_inner#>>'{result_observation,artifacts,q50,artifact_hash}',''),
          'v159:artifact:'||COALESCE(v_inner#>>'{result_observation,artifacts,q90,artifact_hash}','')
        ]::TEXT[]) lock_material
        WHERE lock_material!~':$' ORDER BY lock_key
    LOOP
        PERFORM pg_advisory_xact_lock(v_lock_key);
    END LOOP;
    v_now:=clock_timestamp();

    IF p_action<>'EXPIRE_UNCLAIMED' THEN
        v_verifier_hash:=encode(public.digest(v_verifier_bytes,'sha256'::TEXT),'hex'::TEXT);
        IF jsonb_typeof(v_verifier)<>'object'
           OR NOT v_verifier?&ARRAY[
             'schema_version','evidence_tier','declared_phase','capability_authenticity',
             'coordinator_eligible','semantic_phase_established',
             'canonical_input_bytes_established','envelope_payload_binding_established',
             'policy_overlay_adjudication_established','trusted_time_established',
             'signatures_valid','request_envelope_sha256',
             'signed_status_envelope_sha256','outer_terminal_envelope_sha256',
             'v159_inner_envelope_sha256','provider_evidence_digest_sha256',
             'host_attestation_digest_sha256']::TEXT[]
           OR v_verifier-ARRAY[
             'schema_version','evidence_tier','declared_phase','capability_authenticity',
             'coordinator_eligible','semantic_phase_established',
             'canonical_input_bytes_established','envelope_payload_binding_established',
             'policy_overlay_adjudication_established','trusted_time_established',
             'signatures_valid','request_envelope_sha256',
             'signed_status_envelope_sha256','outer_terminal_envelope_sha256',
             'v159_inner_envelope_sha256','provider_evidence_digest_sha256',
             'host_attestation_digest_sha256']::TEXT[]<>'{}'::JSONB
           OR v_verifier->>'schema_version'<>'alr_fit_verifier_host_attestation_v1'
           OR v_verifier->>'evidence_tier'<>'PLATFORM_OR_EXTERNAL_ATTESTED'
           OR v_verifier->>'capability_authenticity'<>'PLATFORM_OR_EXTERNAL_ATTESTED'
           OR v_verifier->>'declared_phase' IS DISTINCT FROM v_phase
           OR v_verifier->'coordinator_eligible'<>'true'::JSONB
           OR v_verifier->'semantic_phase_established'<>'true'::JSONB
           OR v_verifier->'canonical_input_bytes_established'<>'true'::JSONB
           OR v_verifier->'envelope_payload_binding_established'<>'true'::JSONB
           OR v_verifier->'policy_overlay_adjudication_established'<>'true'::JSONB
           OR v_verifier->'trusted_time_established'<>'true'::JSONB
           OR v_verifier->'signatures_valid'<>'true'::JSONB
           OR v_verifier->>'provider_evidence_digest_sha256'!~'^[0-9a-f]{64}$'
           OR v_verifier->>'host_attestation_digest_sha256'!~'^[0-9a-f]{64}$'
           OR v_verifier->>'request_envelope_sha256' IS DISTINCT FROM
              encode(public.digest(CASE WHEN p_action='REGISTER_REQUEST'
                  THEN v_request_bytes ELSE v_request.request_bytes END,
                  'sha256'::TEXT),'hex'::TEXT) THEN
            RAISE EXCEPTION 'V160 platform-attested verifier receipt rejected';
        END IF;
        IF p_action='RECORD_STATUS' AND
           v_verifier->>'signed_status_envelope_sha256' IS DISTINCT FROM
             encode(public.digest(v_event_bytes,'sha256'::TEXT),'hex'::TEXT) THEN
            RAISE EXCEPTION 'V160 signed-status verifier byte binding rejected';
        END IF;
        IF p_action='CONSUME_TERMINAL' AND (
           v_verifier->>'outer_terminal_envelope_sha256' IS DISTINCT FROM
             encode(public.digest(v_event_bytes,'sha256'::TEXT),'hex'::TEXT)
           OR (v_outcome='SUCCEEDED' AND
               v_verifier->>'v159_inner_envelope_sha256' IS DISTINCT FROM
                 encode(public.digest(v_inner_bytes,'sha256'::TEXT),'hex'::TEXT))
           OR (v_outcome<>'SUCCEEDED' AND
               v_verifier->'v159_inner_envelope_sha256'<>'null'::JSONB)) THEN
            RAISE EXCEPTION 'V160 terminal verifier byte binding rejected';
        END IF;
        IF (v_phase='REQUEST_ONLY' AND (
              v_verifier->'signed_status_envelope_sha256'<>'null'::JSONB
              OR v_verifier->'outer_terminal_envelope_sha256'<>'null'::JSONB
              OR v_verifier->'v159_inner_envelope_sha256'<>'null'::JSONB))
           OR (v_phase='SIGNED_STATUS' AND (
              v_verifier->>'signed_status_envelope_sha256'!~'^[0-9a-f]{64}$'
              OR v_verifier->'outer_terminal_envelope_sha256'<>'null'::JSONB
              OR v_verifier->'v159_inner_envelope_sha256'<>'null'::JSONB))
           OR (v_phase='TERMINAL_SUCCESS' AND (
              v_verifier->'signed_status_envelope_sha256'<>'null'::JSONB
              OR v_verifier->>'outer_terminal_envelope_sha256'!~'^[0-9a-f]{64}$'
              OR v_verifier->>'v159_inner_envelope_sha256'!~'^[0-9a-f]{64}$'))
           OR (v_phase='TERMINAL_NO_INNER' AND (
              v_verifier->'signed_status_envelope_sha256'<>'null'::JSONB
              OR v_verifier->>'outer_terminal_envelope_sha256'!~'^[0-9a-f]{64}$'
              OR v_verifier->'v159_inner_envelope_sha256'<>'null'::JSONB)) THEN
            RAISE EXCEPTION 'V160 verifier phase shape rejected';
        END IF;
        IF p_action='MARK_RECONCILE_REQUIRED' AND (
           (v_phase='SIGNED_STATUS' AND
              v_verifier->>'signed_status_envelope_sha256' IS DISTINCT FROM
                encode(public.digest(v_event_bytes,'sha256'::TEXT),'hex'::TEXT))
           OR (v_phase='TERMINAL_NO_INNER' AND
              v_verifier->>'outer_terminal_envelope_sha256' IS DISTINCT FROM
                encode(public.digest(v_event_bytes,'sha256'::TEXT),'hex'::TEXT))) THEN
            RAISE EXCEPTION 'V160 reconciliation verifier byte binding rejected';
        END IF;
    END IF;

    IF p_action='REGISTER_REQUEST' THEN
        SELECT * INTO v_request
        FROM learning.alr_challenger_consumption_requests r
        WHERE r.request_hash=v_request_hash
           OR (r.durable_receipt_hash=v_durable_receipt_hash
               AND r.training_key_hash=v_training_key_hash
               AND r.request_generation=v_generation)
           OR (r.issuer_id=v_issuer_id AND r.nonce_digest=v_nonce_digest)
        ORDER BY (r.request_hash=v_request_hash) DESC LIMIT 1;
        IF FOUND THEN
            IF ROW(v_request.request_hash,v_request.request_bytes,
                   v_request.request_projection,v_request.verification_receipt_bytes,
                   v_request.verification_receipt_hash,v_request.verification_receipt,
                   v_request.durable_receipt_hash,v_request.training_key_hash,
                   v_request.request_generation,v_request.issuer_id,
                   v_request.nonce_digest,v_request.accept_by,v_request.complete_by)
               IS DISTINCT FROM ROW(v_request_hash,v_request_bytes,v_projection,
                   v_verifier_bytes,v_verifier_hash,v_verifier,
                   v_durable_receipt_hash,v_training_key_hash,v_generation,
                   v_issuer_id,v_nonce_digest,v_accept_by,v_complete_by) THEN
                RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT';
            END IF;
            RETURN jsonb_build_object('status','DUPLICATE','action',p_action,
                'request_hash',v_request.request_hash,
                'registered_at',v_request.registered_at);
        END IF;
        SELECT max(r.request_generation) INTO v_previous_generation
        FROM learning.alr_challenger_consumption_requests r
        WHERE r.durable_receipt_hash=v_durable_receipt_hash
          AND r.training_key_hash=v_training_key_hash;
        IF v_previous_generation IS NOT NULL AND (
           v_generation<=v_previous_generation OR EXISTS (
             SELECT 1 FROM learning.alr_challenger_consumption_requests old
             LEFT JOIN learning.alr_challenger_consumption_terminals terminal
               ON terminal.request_hash=old.request_hash
             WHERE old.durable_receipt_hash=v_durable_receipt_hash
               AND old.training_key_hash=v_training_key_hash
               AND (terminal.request_hash IS NULL OR terminal.outcome NOT IN
                    ('REJECTED_PRE_FIT','EXPIRED_UNCLAIMED'))
           )) THEN
            RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT';
        END IF;
        IF v_projection->>'schema_version'<>'alr_trusted_fit_execution_request_v1'
           OR v_projection->>'request_hash' IS DISTINCT FROM v_projection->>'attempt_id'
           OR v_projection->>'request_hash' IS DISTINCT FROM v_projection->>'invocation_id'
           OR v_projection#>>'{signed_payload,schema_version}'<>'alr_trusted_fit_execution_request_v1'
           OR v_projection#>>'{signed_payload,signature_algorithm}'<>'ed25519'
           OR v_projection->'dispatch_allowed'<>'false'::JSONB
           OR v_projection->'training_allowed'<>'false'::JSONB
           OR v_projection->'persistence_allowed'<>'false'::JSONB
           OR (v_projection#>>'{signed_payload,not_before}')::TIMESTAMPTZ>v_now
           OR v_now>=v_accept_by
           OR v_accept_by>=v_complete_by
           OR NOT EXISTS (
             SELECT 1 FROM learning.alr_qualified_training_receipts q
             WHERE q.durable_receipt_hash=v_durable_receipt_hash
               AND q.training_key_hash=v_training_key_hash
           ) THEN
            RAISE EXCEPTION 'V160 REGISTER_REQUEST semantic binding rejected';
        END IF;
        INSERT INTO learning.alr_challenger_consumption_requests(
            request_hash,request_bytes,request_projection,
            verification_receipt_bytes,verification_receipt_hash,
            verification_receipt,durable_receipt_hash,training_key_hash,
            request_generation,issuer_id,nonce_digest,accept_by,complete_by,
            registered_at
        ) VALUES (
            v_request_hash,v_request_bytes,v_projection,v_verifier_bytes,
            v_verifier_hash,v_verifier,v_durable_receipt_hash,v_training_key_hash,
            v_generation,v_issuer_id,v_nonce_digest,v_accept_by,v_complete_by,v_now
        );
        INSERT INTO learning.alr_challenger_consumption_verifier_evidence(
            verifier_receipt_hash,request_hash,action,declared_phase,
            verification_receipt_bytes,verification_receipt,recorded_at
        ) VALUES(v_verifier_hash,v_request_hash,p_action,v_phase,
                 v_verifier_bytes,v_verifier,v_now);
        RETURN jsonb_build_object('status','PERSISTED','action',p_action,
            'request_hash',v_request_hash,'registered_at',v_now);
    END IF;

    SELECT * INTO v_request FROM learning.alr_challenger_consumption_requests
    WHERE request_hash=v_request_hash;
    IF NOT FOUND THEN RAISE EXCEPTION 'V160 registered request disappeared'; END IF;

    IF p_action='CLAIM_REQUEST' THEN
        SELECT * INTO v_claim FROM learning.alr_challenger_consumption_claims
        WHERE request_hash=v_request_hash;
        IF FOUND THEN
            IF ROW(v_claim.claim_bytes,v_claim.claim_projection,
                   v_claim.verification_receipt_bytes,v_claim.verification_receipt_hash,
                   v_claim.verification_receipt)
               IS DISTINCT FROM ROW(v_event_bytes,v_projection,v_verifier_bytes,
                                     v_verifier_hash,v_verifier) THEN
                RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT';
            END IF;
            RETURN jsonb_build_object('status','DUPLICATE','action',p_action,
                'request_hash',v_request_hash,'claimed_at',v_claim.claimed_at);
        END IF;
        IF v_now>=v_accept_by
           OR EXISTS(SELECT 1 FROM learning.alr_challenger_consumption_terminals
                     WHERE request_hash=v_request_hash)
           OR v_projection-ARRAY['schema_version','request_hash',
                                 'runner_identity_hash','claim_token_hash']::TEXT[]<>'{}'::JSONB
           OR NOT v_projection?&ARRAY['schema_version','request_hash',
                                 'runner_identity_hash','claim_token_hash']::TEXT[]
           OR v_projection->>'schema_version'<>'alr_challenger_consumption_claim_v1'
           OR v_projection->>'request_hash' IS DISTINCT FROM v_request_hash
           OR v_projection->>'runner_identity_hash'!~'^[0-9a-f]{64}$'
           OR v_projection->>'claim_token_hash'!~'^[0-9a-f]{64}$' THEN
            RAISE EXCEPTION 'V160 CLAIM_REQUEST semantic binding rejected';
        END IF;
        INSERT INTO learning.alr_challenger_consumption_claims(
            request_hash,claim_bytes,claim_projection,
            verification_receipt_bytes,verification_receipt_hash,
            verification_receipt,claimed_at
        ) VALUES(v_request_hash,v_event_bytes,v_projection,v_verifier_bytes,
                 v_verifier_hash,v_verifier,v_now);
        INSERT INTO learning.alr_challenger_consumption_verifier_evidence(
            verifier_receipt_hash,request_hash,action,declared_phase,
            verification_receipt_bytes,verification_receipt,recorded_at
        ) VALUES(v_verifier_hash,v_request_hash,p_action,v_phase,
                 v_verifier_bytes,v_verifier,v_now);
        RETURN jsonb_build_object('status','PERSISTED','action',p_action,
            'request_hash',v_request_hash,'claimed_at',v_now);
    END IF;

    IF p_action='RECORD_STATUS' THEN
        IF NOT EXISTS(SELECT 1 FROM learning.alr_challenger_consumption_claims
                      WHERE request_hash=v_request_hash)
           OR v_projection->>'schema_version'<>'alr_isolated_fit_execution_receipt_v1'
           OR v_projection->>'response_kind'<>'STATUS'
           OR v_projection->>'outcome'<>'ACCEPTED_IN_PROGRESS'
           OR v_projection#>>'{signed_payload,request_hash}' IS DISTINCT FROM v_request_hash
           OR (v_projection#>>'{signed_payload,request_generation}')::BIGINT
                IS DISTINCT FROM v_generation THEN
            RAISE EXCEPTION 'V160 RECORD_STATUS semantic binding rejected';
        END IF;
        v_event_hash:=encode(public.digest(v_event_bytes,'sha256'::TEXT),'hex'::TEXT);
        v_generation:=(v_projection#>>'{signed_payload,status_generation}')::BIGINT;
        v_verified_at:=(v_projection#>>'{signed_payload,status_issued_at}')::TIMESTAMPTZ;
        v_expires_at:=(v_projection#>>'{signed_payload,status_expires_at}')::TIMESTAMPTZ;
        SELECT * INTO v_status FROM learning.alr_challenger_consumption_statuses s
        WHERE (s.request_hash=v_request_hash AND s.status_generation=v_generation)
           OR s.response_hash=v_event_hash
        ORDER BY (s.request_hash=v_request_hash
                  AND s.status_generation=v_generation) DESC LIMIT 1;
        IF FOUND THEN
            IF ROW(v_status.request_hash,v_status.status_generation,
                   v_status.response_hash,v_status.response_bytes,
                   v_status.response_projection,v_status.verification_receipt_bytes,
                   v_status.verification_receipt_hash,v_status.verification_receipt,
                   v_status.status_issued_at,v_status.status_expires_at)
               IS DISTINCT FROM ROW(v_request_hash,v_generation,v_event_hash,
                   v_event_bytes,v_projection,v_verifier_bytes,v_verifier_hash,
                   v_verifier,v_verified_at,v_expires_at) THEN
                RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT';
            END IF;
            RETURN jsonb_build_object('status','DUPLICATE','action',p_action,
                'request_hash',v_request_hash,'status_generation',v_generation,
                'recorded_at',v_status.recorded_at);
        END IF;
        IF EXISTS(SELECT 1 FROM learning.alr_challenger_consumption_terminals
                  WHERE request_hash=v_request_hash) THEN
            RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT';
        END IF;
        SELECT max(status_generation),max(status_issued_at)
          INTO v_previous_status_generation,v_previous_status_issued
        FROM learning.alr_challenger_consumption_statuses
        WHERE request_hash=v_request_hash;
        IF (v_previous_status_generation IS NOT NULL AND
            (v_generation<=v_previous_status_generation
             OR v_verified_at<=v_previous_status_issued))
           OR v_verified_at>v_now OR v_now>=v_expires_at
           OR v_expires_at>v_complete_by
           OR EXISTS (
             SELECT 1 FROM learning.alr_challenger_consumption_statuses old,
               LATERAL jsonb_each(old.response_projection#>'{signed_payload,stage_observations}') prior
             WHERE old.request_hash=v_request_hash
               AND old.status_generation=v_previous_status_generation
               AND prior.value='true'::JSONB
               AND (v_projection#>'{signed_payload,stage_observations}')->prior.key
                    IS DISTINCT FROM 'true'::JSONB
           ) THEN
            RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT';
        END IF;
        INSERT INTO learning.alr_challenger_consumption_statuses(
            request_hash,status_generation,response_hash,response_bytes,
            response_projection,verification_receipt_bytes,
            verification_receipt_hash,verification_receipt,
            status_issued_at,status_expires_at,recorded_at
        ) VALUES(v_request_hash,v_generation,v_event_hash,v_event_bytes,
                 v_projection,v_verifier_bytes,v_verifier_hash,v_verifier,
                 v_verified_at,v_expires_at,v_now);
        INSERT INTO learning.alr_challenger_consumption_verifier_evidence(
            verifier_receipt_hash,request_hash,action,declared_phase,
            verification_receipt_bytes,verification_receipt,recorded_at
        ) VALUES(v_verifier_hash,v_request_hash,p_action,v_phase,
                 v_verifier_bytes,v_verifier,v_now);
        RETURN jsonb_build_object('status','PERSISTED','action',p_action,
            'request_hash',v_request_hash,'status_generation',v_generation,
            'recorded_at',v_now);
    END IF;

    IF p_action='MARK_RECONCILE_REQUIRED' THEN
        IF v_projection->>'schema_version'<>'alr_isolated_fit_execution_receipt_v1'
           OR v_projection#>>'{signed_payload,request_hash}' IS DISTINCT FROM v_request_hash
           OR v_phase NOT IN ('SIGNED_STATUS','TERMINAL_NO_INNER') THEN
            RAISE EXCEPTION 'V160 reconciliation event rejected';
        END IF;
        v_reconciliation_hash:=encode(public.digest(v_event_bytes,'sha256'::TEXT),'hex'::TEXT);
        IF EXISTS(SELECT 1 FROM learning.alr_challenger_consumption_reconciliation_audit a
                  WHERE a.reconciliation_hash=v_reconciliation_hash) THEN
            IF NOT EXISTS(SELECT 1 FROM learning.alr_challenger_consumption_reconciliation_audit a
                WHERE a.reconciliation_hash=v_reconciliation_hash
                  AND a.request_hash=v_request_hash AND a.reason='AMBIGUOUS_RESPONSE'
                  AND a.event_bytes=v_event_bytes AND a.event_projection=v_projection
                  AND a.verification_receipt_bytes=v_verifier_bytes
                  AND a.verification_receipt_hash=v_verifier_hash
                  AND a.verification_receipt=v_verifier) THEN
                RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT';
            END IF;
            RETURN jsonb_build_object('status','DUPLICATE','action',p_action,
                'request_hash',v_request_hash,
                'reconciliation_hash',v_reconciliation_hash);
        END IF;
        INSERT INTO learning.alr_challenger_consumption_reconciliation_audit(
            reconciliation_hash,request_hash,reason,event_bytes,event_projection,
            verification_receipt_bytes,verification_receipt_hash,
            verification_receipt,recorded_at
        ) VALUES(v_reconciliation_hash,v_request_hash,'AMBIGUOUS_RESPONSE',
                 v_event_bytes,v_projection,v_verifier_bytes,v_verifier_hash,
                 v_verifier,v_now);
        INSERT INTO learning.alr_challenger_consumption_verifier_evidence(
            verifier_receipt_hash,request_hash,action,declared_phase,
            verification_receipt_bytes,verification_receipt,recorded_at
        ) VALUES(v_verifier_hash,v_request_hash,p_action,v_phase,
                 v_verifier_bytes,v_verifier,v_now);
        RETURN jsonb_build_object('status','PERSISTED','action',p_action,
            'request_hash',v_request_hash,
            'reconciliation_hash',v_reconciliation_hash,'recorded_at',v_now);
    END IF;

    IF p_action='EXPIRE_UNCLAIMED' THEN
        SELECT * INTO v_terminal FROM learning.alr_challenger_consumption_terminals
        WHERE request_hash=v_request_hash;
        IF FOUND THEN
            IF v_terminal.outcome<>'EXPIRED_UNCLAIMED' THEN
                RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT';
            END IF;
            RETURN jsonb_build_object('status','DUPLICATE','action',p_action,
                'request_hash',v_request_hash,'outcome',v_terminal.outcome,
                'consumed_at',v_terminal.consumed_at);
        END IF;
        IF v_now<v_accept_by
           OR EXISTS(SELECT 1 FROM learning.alr_challenger_consumption_claims
                     WHERE request_hash=v_request_hash)
           OR EXISTS(SELECT 1 FROM learning.alr_challenger_consumption_statuses
                     WHERE request_hash=v_request_hash)
           OR EXISTS(SELECT 1 FROM learning.alr_challenger_consumption_reconciliation_audit
                     WHERE request_hash=v_request_hash)
           OR EXISTS(SELECT 1 FROM learning.alr_challenger_fit_attestations
                     WHERE durable_receipt_hash=v_durable_receipt_hash
                       AND training_key_hash=v_training_key_hash) THEN
            RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT';
        END IF;
        v_projection:=jsonb_build_object(
            'schema_version','alr_challenger_consumption_expiry_v1',
            'request_hash',v_request_hash,'outcome','EXPIRED_UNCLAIMED',
            'reason','ACCEPT_WINDOW_ELAPSED','expired_at',v_now);
        v_event_bytes:=convert_to(v_projection::TEXT,'UTF8'::NAME);
        v_event_hash:=encode(public.digest(v_event_bytes,'sha256'::TEXT),'hex'::TEXT);
        INSERT INTO learning.alr_challenger_consumption_terminals(
            request_hash,terminal_hash,outcome,terminal_bytes,
            terminal_projection,inner_receipt_bytes,verification_receipt_bytes,
            verification_receipt_hash,verification_receipt,consumed_at
        ) VALUES(v_request_hash,v_event_hash,'EXPIRED_UNCLAIMED',v_event_bytes,
                 v_projection,NULL,NULL,NULL,NULL,v_now);
        RETURN jsonb_build_object('status','PERSISTED','action',p_action,
            'request_hash',v_request_hash,'outcome','EXPIRED_UNCLAIMED',
            'consumed_at',v_now);
    END IF;

    -- The only remaining action is CONSUME_TERMINAL.  Exact replay is checked
    -- before any clock rejection and reuses the stored bind time and identities.
    v_event_hash:=encode(public.digest(v_event_bytes,'sha256'::TEXT),'hex'::TEXT);
    SELECT * INTO v_terminal FROM learning.alr_challenger_consumption_terminals t
    WHERE t.request_hash=v_request_hash OR t.terminal_hash=v_event_hash
    ORDER BY (t.request_hash=v_request_hash) DESC LIMIT 1;
    IF FOUND THEN
        IF ROW(v_terminal.request_hash,v_terminal.terminal_hash,v_terminal.outcome,
               v_terminal.terminal_bytes,v_terminal.terminal_projection,
               v_terminal.inner_receipt_bytes,v_terminal.verification_receipt_bytes,
               v_terminal.verification_receipt_hash,v_terminal.verification_receipt)
           IS DISTINCT FROM ROW(v_request_hash,v_event_hash,v_outcome,v_event_bytes,
               v_projection,v_inner_bytes,v_verifier_bytes,v_verifier_hash,v_verifier) THEN
            RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT';
        END IF;
        RETURN jsonb_build_object('status','DUPLICATE','action',p_action,
            'request_hash',v_request_hash,'outcome',v_terminal.outcome,
            'consumed_at',v_terminal.consumed_at,
            'training_run',(SELECT to_jsonb(r) FROM learning.alr_challenger_training_runs r
                            WHERE r.durable_attestation_hash=(
                              SELECT a.durable_attestation_hash
                              FROM learning.alr_challenger_fit_attestations a
                              WHERE a.durable_receipt_hash=v_request.durable_receipt_hash
                                AND a.training_key_hash=v_request.training_key_hash)),
            'registry',(SELECT to_jsonb(g) FROM learning.alr_challenger_registry g
                        WHERE g.durable_attestation_hash=(
                          SELECT a.durable_attestation_hash
                          FROM learning.alr_challenger_fit_attestations a
                          WHERE a.durable_receipt_hash=v_request.durable_receipt_hash
                            AND a.training_key_hash=v_request.training_key_hash)));
    END IF;
    SELECT * INTO v_claim FROM learning.alr_challenger_consumption_claims
    WHERE request_hash=v_request_hash;
    IF NOT FOUND
       OR v_projection->>'schema_version'<>'alr_isolated_fit_execution_receipt_v1'
       OR v_projection->>'response_kind'<>'TERMINAL'
       OR v_projection->>'outcome' NOT IN
          ('SUCCEEDED','REJECTED_PRE_FIT','FAILED_AFTER_START')
       OR v_projection#>>'{signed_payload,request_hash}' IS DISTINCT FROM v_request_hash
       OR (v_projection#>>'{signed_payload,request_generation}')::BIGINT
            IS DISTINCT FROM v_request.request_generation
       OR v_projection#>>'{signed_payload,nonce_digest}' IS DISTINCT FROM v_request.nonce_digest
       OR v_projection#>>'{signed_payload,issuer_id}' IS DISTINCT FROM v_request.issuer_id
       OR v_projection#>>'{signed_payload,trust_policy_id}' IS DISTINCT FROM
            v_request.request_projection#>>'{signed_payload,trust_policy_id}'
       OR v_projection#>>'{signed_payload,trust_policy_snapshot_digest}' IS DISTINCT FROM
            v_request.request_projection#>>'{signed_payload,trust_policy_snapshot_digest}'
       OR v_projection#>>'{signed_payload,runner_target_policy_hash}' IS DISTINCT FROM
            v_request.request_projection#>>'{signed_payload,runner_target_policy_hash}'
       OR v_projection#>>'{signed_payload,signature_algorithm}'<>'ed25519'
       OR (v_projection#>>'{signed_payload,issuer_verified_at}')::TIMESTAMPTZ>v_now
       OR v_now>=v_complete_by THEN
        RAISE EXCEPTION 'V160 terminal request/claim binding rejected';
    END IF;

    IF (SELECT max(s.status_issued_at)
        FROM learning.alr_challenger_consumption_statuses s
        WHERE s.request_hash=v_request_hash)>
           (v_projection#>>'{signed_payload,issuer_verified_at}')::TIMESTAMPTZ
       OR EXISTS (
          SELECT 1 FROM learning.alr_challenger_consumption_statuses latest,
            LATERAL jsonb_each(
              latest.response_projection#>'{signed_payload,stage_observations}') prior
          WHERE latest.request_hash=v_request_hash
            AND latest.status_generation=(SELECT max(s.status_generation)
                FROM learning.alr_challenger_consumption_statuses s
                WHERE s.request_hash=v_request_hash)
            AND prior.value='true'::JSONB
            AND (v_projection#>'{signed_payload,stage_observations}')->prior.key
                  IS DISTINCT FROM 'true'::JSONB
       ) THEN
        RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT';
    END IF;

    IF v_outcome IN ('REJECTED_PRE_FIT','FAILED_AFTER_START') THEN
        IF v_projection#>'{signed_payload,inner_receipt_bytes_base64url}' IS NOT NULL
           OR EXISTS(SELECT 1 FROM learning.alr_challenger_fit_attestations a
                     WHERE a.durable_receipt_hash=v_request.durable_receipt_hash
                       AND a.training_key_hash=v_request.training_key_hash) THEN
            RAISE EXCEPTION 'V160 non-success terminal forbids V159 state';
        END IF;
        INSERT INTO learning.alr_challenger_consumption_terminals(
            request_hash,terminal_hash,outcome,terminal_bytes,
            terminal_projection,inner_receipt_bytes,verification_receipt_bytes,
            verification_receipt_hash,verification_receipt,consumed_at
        ) VALUES(v_request_hash,v_event_hash,v_outcome,v_event_bytes,v_projection,
                 NULL,v_verifier_bytes,v_verifier_hash,v_verifier,v_now);
        INSERT INTO learning.alr_challenger_consumption_verifier_evidence(
            verifier_receipt_hash,request_hash,action,declared_phase,
            verification_receipt_bytes,verification_receipt,recorded_at
        ) VALUES(v_verifier_hash,v_request_hash,p_action,v_phase,
                 v_verifier_bytes,v_verifier,v_now);
        IF v_outcome='FAILED_AFTER_START' THEN
            v_projection:=jsonb_build_object(
                'schema_version','alr_challenger_reconciliation_event_v1',
                'request_hash',v_request_hash,'reason','FAILED_AFTER_START',
                'terminal_hash',v_event_hash);
            v_request_bytes:=convert_to(v_projection::TEXT,'UTF8'::NAME);
            v_reconciliation_hash:=encode(public.digest(
                convert_to(format(E'v160_failed_after_start\nrequest=%s\nterminal=%s\n',
                    v_request_hash,v_event_hash),'UTF8'::NAME),
                'sha256'::TEXT),'hex'::TEXT);
            INSERT INTO learning.alr_challenger_consumption_reconciliation_audit(
                reconciliation_hash,request_hash,reason,event_bytes,event_projection,
                verification_receipt_bytes,verification_receipt_hash,
                verification_receipt,recorded_at
            ) VALUES(v_reconciliation_hash,v_request_hash,'FAILED_AFTER_START',
                     v_request_bytes,v_projection,v_verifier_bytes,v_verifier_hash,
                     v_verifier,v_now);
        END IF;
        RETURN jsonb_build_object('status','PERSISTED','action',p_action,
            'request_hash',v_request_hash,'outcome',v_outcome,
            'consumed_at',v_now);
    END IF;

    -- SUCCEEDED: decoded inner bytes, outer fields, V158 admission, V159
    -- projection and the host-attested strict-verifier receipt are exhaustive.
    IF v_inner_bytes IS NULL OR v_inner_bytes IS DISTINCT FROM
          convert_to(v_inner::TEXT,'UTF8'::NAME)
       OR v_inner_bytes IS DISTINCT FROM decode(
            translate(v_projection#>>'{signed_payload,inner_receipt_bytes_base64url}',
                      '-_','+/')||repeat('=',(4-length(
                v_projection#>>'{signed_payload,inner_receipt_bytes_base64url}')%4)%4),
            'base64')
       OR v_inner->>'schema_version'<>'alr_fit_execution_signed_receipt_v1'
       OR v_inner->>'evidence_tier'<>'PLATFORM_OR_EXTERNAL_ATTESTED'
       OR v_inner->>'claim_kind'<>'ALR_FIT_EXECUTION_ATTESTATION_V1'
       OR v_inner->>'authentication_status'<>'SIGNATURE_VERIFIED_BY_TRUST_POLICY'
       OR v_inner#>>'{authentication,signature_algorithm}'<>'ed25519'
       OR v_projection#>>'{signed_payload,inner_receipt_digest_sha256}' IS DISTINCT FROM
            encode(public.digest(v_inner_bytes,'sha256'::TEXT),'hex'::TEXT)
       OR v_projection#>'{signed_payload,v159_subject}' IS DISTINCT FROM
            v_inner->'subject'
       OR v_projection#>'{signed_payload,v159_claims}' IS DISTINCT FROM
            v_inner->'claims'
       OR v_projection#>'{signed_payload,result_observation}' IS DISTINCT FROM
            v_inner->'result_observation'
       OR v_projection#>>'{signed_payload,actual_input_material_set_hash}' IS DISTINCT FROM
            v_inner#>>'{subject,actual_input_material_set_hash}'
       OR v_projection#>>'{signed_payload,ordered_artifact_set_hash}' IS DISTINCT FROM
            v_inner#>>'{subject,ordered_artifact_set_hash}'
       OR v_projection#>>'{signed_payload,fit_started_at}' IS DISTINCT FROM
            v_inner#>>'{result_observation,fit_started_at}'
       OR v_projection#>>'{signed_payload,fit_completed_at}' IS DISTINCT FROM
            v_inner#>>'{result_observation,fit_completed_at}'
       OR v_projection#>>'{signed_payload,issuer_id}' IS DISTINCT FROM
            v_inner#>>'{authentication,issuer_id}'
       OR v_projection#>>'{signed_payload,trust_policy_id}' IS DISTINCT FROM
            v_inner#>>'{authentication,trust_policy_id}'
       OR v_projection#>>'{signed_payload,signing_key_id}' IS DISTINCT FROM
            v_inner#>>'{authentication,signature_key_id}'
       OR v_projection#>'{signed_payload,no_authority}' IS DISTINCT FROM
            v_inner->'no_authority'
       OR v_projection#>'{signed_payload,authority_counters}' IS DISTINCT FROM
            v_inner->'authority_counters'
       OR v_inner->'no_authority' IS DISTINCT FROM v_no_authority
       OR v_inner->'authority_counters' IS DISTINCT FROM v_zero_counters
       OR v_inner#>'{claims,actual_inputs_consumed}'<>'true'::JSONB
       OR v_inner#>'{claims,actual_fit_executed}'<>'true'::JSONB
       OR v_inner#>'{claims,model_training_performed}'<>'true'::JSONB
       OR v_inner#>'{claims,artifact_readback_completed}'<>'true'::JSONB
       OR v_inner#>'{claims,onnx_semantic_validation_passed}'<>'true'::JSONB THEN
        RAISE EXCEPTION 'V160 terminal outer/inner exhaustive binding rejected';
    END IF;

    v_durable_receipt_hash:=v_inner#>>'{subject,durable_receipt_hash}';
    v_training_key_hash:=v_inner#>>'{subject,training_key_hash}';
    v_structural_result_hash:=v_inner#>>'{subject,result_hash}';
    v_structural_fit_capture_hash:=v_inner#>>'{subject,fit_capture_hash}';
    v_structural_candidate_hash:=v_inner#>>'{subject,candidate_attestation_hash}';
    v_structural_run_hash:=v_inner#>>'{subject,training_run_hash}';
    v_structural_challenger_hash:=v_inner#>>'{subject,challenger_hash}';
    v_runner_identity_hash:=v_inner#>>'{subject,runner_identity_hash}';
    v_material_set_hash:=v_inner#>>'{subject,actual_input_material_set_hash}';
    v_observation:=v_inner->'result_observation';
    v_q10_hash:=v_observation#>>'{artifacts,q10,artifact_hash}';
    v_q50_hash:=v_observation#>>'{artifacts,q50,artifact_hash}';
    v_q90_hash:=v_observation#>>'{artifacts,q90,artifact_hash}';
    v_q10_size:=(v_observation#>>'{artifacts,q10,artifact_size_bytes}')::BIGINT;
    v_q50_size:=(v_observation#>>'{artifacts,q50,artifact_size_bytes}')::BIGINT;
    v_q90_size:=(v_observation#>>'{artifacts,q90,artifact_size_bytes}')::BIGINT;
    v_verified_at:=(v_inner->>'verified_at')::TIMESTAMPTZ;
    v_expires_at:=(v_inner->>'expires_at')::TIMESTAMPTZ;
    v_bound_at:=v_now;
    IF v_durable_receipt_hash IS DISTINCT FROM v_request.durable_receipt_hash
       OR v_training_key_hash IS DISTINCT FROM v_request.training_key_hash
       OR v_inner->>'verified_at' IS DISTINCT FROM
            v_projection#>>'{signed_payload,issuer_verified_at}'
       OR v_inner->>'expires_at' IS DISTINCT FROM
            v_projection#>>'{signed_payload,receipt_expires_at}'
       OR v_verified_at>v_bound_at OR v_bound_at>=v_expires_at
       OR (v_observation->>'fit_completed_at')::TIMESTAMPTZ>v_verified_at
       OR (v_observation->>'fit_completed_at')::TIMESTAMPTZ>v_bound_at
       OR LEAST(v_q10_size,v_q50_size,v_q90_size)<=0
       OR v_q10_hash IN (v_q50_hash,v_q90_hash) OR v_q50_hash=v_q90_hash THEN
        RAISE EXCEPTION 'V160 terminal V159 time/admission/artifact binding rejected';
    END IF;
    v_set_hash:=encode(public.digest(convert_to(format(
        E'q10=%s\nq50=%s\nq90=%s\n',v_q10_hash,v_q50_hash,v_q90_hash),
        'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT);
    IF v_set_hash IS DISTINCT FROM v_inner#>>'{subject,ordered_artifact_set_hash}'
       OR NOT EXISTS(
          SELECT 1 FROM learning.alr_qualified_training_receipts q
          WHERE q.durable_receipt_hash=v_durable_receipt_hash
            AND q.training_key_hash=v_training_key_hash
            AND q.code_manifest_hash=v_observation#>>'{actual_inputs,code_manifest_hash}'
            AND q.training_config_hash=v_observation#>>'{actual_inputs,training_config_hash}'
            AND q.canonical_payload->>'dataset_hash'=v_observation#>>'{actual_inputs,dataset_hash}'
            AND q.canonical_payload->>'row_ids_hash'=v_observation#>>'{actual_inputs,row_ids_hash}'
            AND q.canonical_payload->>'split_hash'=v_observation#>>'{actual_inputs,split_hash}'
            AND q.canonical_payload->>'feature_schema_hash'=v_observation#>>'{actual_inputs,feature_schema_hash}'
            AND q.canonical_payload->>'label_schema_hash'=v_observation#>>'{actual_inputs,label_schema_hash}'
            AND (q.canonical_payload->>'training_rows')::INTEGER=
                (v_observation#>>'{actual_inputs,training_rows}')::INTEGER
       ) THEN
        RAISE EXCEPTION 'V160 exact qualified receipt lineage rejected';
    END IF;

    v_external_digest:=encode(public.digest(v_inner_bytes,'sha256'::TEXT),'hex'::TEXT);
    v_attestation_hash:=encode(public.digest(convert_to(format(
        E'alr_durable_fit_attestation_v1\nreceipt=%s\ndurable_receipt=%s\ntraining_key=%s\nresult=%s\nfit_capture=%s\ncandidate=%s\nrun=%s\nchallenger=%s\nrunner=%s\nmaterials=%s\nartifacts=%s\nissuer=%s\npolicy=%s\nkey=%s\nverified=%s\nexpires=%s\n',
        v_external_digest,v_durable_receipt_hash,v_training_key_hash,
        v_structural_result_hash,v_structural_fit_capture_hash,
        v_structural_candidate_hash,v_structural_run_hash,
        v_structural_challenger_hash,v_runner_identity_hash,v_material_set_hash,
        v_set_hash,v_inner#>>'{authentication,issuer_id}',
        v_inner#>>'{authentication,trust_policy_id}',
        v_inner#>>'{authentication,signature_key_id}',
        to_char(v_verified_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
        to_char(v_expires_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')),
        'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT);
    v_durable_run_hash:=encode(public.digest(convert_to(format(
        E'alr_durable_training_run_v1\nattestation=%s\nstructural_run=%s\nsource=%s\ndataset=%s\nrows=%s\nsplit=%s\ncode=%s\nconfig=%s\nfeature=%s\nlabel=%s\nmodel=%s\ntraining_rows=%s\nartifacts=%s\nmetrics=%s\nresources=%s\nfit_start=%s\nfit_end=%s\nbound=%s\n',
        v_attestation_hash,v_structural_run_hash,v_observation->>'source_head',
        v_observation#>>'{actual_inputs,dataset_hash}',v_observation#>>'{actual_inputs,row_ids_hash}',
        v_observation#>>'{actual_inputs,split_hash}',v_observation#>>'{actual_inputs,code_manifest_hash}',
        v_observation#>>'{actual_inputs,training_config_hash}',v_observation#>>'{actual_inputs,feature_schema_hash}',
        v_observation#>>'{actual_inputs,label_schema_hash}',v_observation#>>'{model,model_schema_version}',
        v_observation#>>'{actual_inputs,training_rows}',v_set_hash,
        v_observation#>>'{model,metrics_hash}',v_observation#>>'{model,resource_usage_hash}',
        to_char((v_observation->>'fit_started_at')::TIMESTAMPTZ AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
        to_char((v_observation->>'fit_completed_at')::TIMESTAMPTZ AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
        to_char(v_bound_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')),
        'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT);
    v_durable_challenger_hash:=encode(public.digest(convert_to(format(
        E'alr_durable_challenger_v1\nattestation=%s\ndurable_run=%s\nstructural_challenger=%s\nartifacts=%s\n',
        v_attestation_hash,v_durable_run_hash,v_structural_challenger_hash,v_set_hash),
        'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT);

    IF EXISTS(SELECT 1 FROM learning.alr_challenger_fit_attestations a
              WHERE a.durable_attestation_hash=v_attestation_hash
                 OR a.external_receipt_digest=v_external_digest
                 OR (a.durable_receipt_hash=v_durable_receipt_hash
                     AND a.training_key_hash=v_training_key_hash)
                 OR a.structural_result_hash=v_structural_result_hash
                 OR a.structural_fit_capture_hash=v_structural_fit_capture_hash
                 OR a.structural_candidate_hash=v_structural_candidate_hash
                 OR a.structural_training_run_hash=v_structural_run_hash
                 OR a.structural_challenger_hash=v_structural_challenger_hash
                 OR a.ordered_artifact_set_hash=v_set_hash)
       OR EXISTS(SELECT 1 FROM learning.alr_challenger_training_runs r
                 WHERE r.durable_attestation_hash=v_attestation_hash
                    OR r.training_run_hash=v_structural_run_hash)
       OR EXISTS(SELECT 1 FROM learning.alr_challenger_model_artifacts m
                 WHERE m.durable_attestation_hash=v_attestation_hash
                    OR m.training_run_hash=v_structural_run_hash
                    OR m.artifact_hash IN (v_q10_hash,v_q50_hash,v_q90_hash))
       OR EXISTS(SELECT 1 FROM learning.alr_challenger_registry g
                 WHERE g.durable_attestation_hash=v_attestation_hash
                    OR g.training_run_hash=v_structural_run_hash
                    OR g.challenger_hash=v_structural_challenger_hash) THEN
        RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT';
    END IF;

    v_run_payload:=jsonb_build_object(
        'schema_version','alr_challenger_training_result_v2',
        'structural_training_run_hash',v_structural_run_hash,
        'durable_training_run_hash',v_durable_run_hash,
        'durable_attestation_hash',v_attestation_hash,
        'structural_result_hash',v_structural_result_hash,
        'structural_fit_capture_hash',v_structural_fit_capture_hash,
        'structural_candidate_hash',v_structural_candidate_hash,
        'run_status','TRAINING_PERFORMED','model_training_performed',TRUE,
        'attestation_bound_at',v_bound_at,'no_authority',v_no_authority,
        'authority_counters',v_zero_counters);
    v_registry_payload:=jsonb_build_object(
        'schema_version','alr_challenger_registry_entry_v2',
        'structural_challenger_hash',v_structural_challenger_hash,
        'durable_challenger_hash',v_durable_challenger_hash,
        'durable_training_run_hash',v_durable_run_hash,
        'durable_attestation_hash',v_attestation_hash,
        'registry_status','NOT_SERVING','serving_allowed',FALSE,
        'promotion_allowed',FALSE,'latest_pointer_allowed',FALSE,
        'symlink_allowed',FALSE);

    SET CONSTRAINTS
      learning.alr_challenger_run_complete_ct_v1,
      learning.alr_challenger_artifact_complete_ct_v1,
      learning.alr_challenger_registry_complete_ct_v1,
      learning.alr_v159_run_complete_ct_v1,
      learning.alr_v159_artifact_complete_ct_v1,
      learning.alr_v159_registry_complete_ct_v1 DEFERRED;
    INSERT INTO learning.alr_challenger_fit_attestations(
        durable_attestation_hash,external_receipt_digest,signed_receipt_bytes,
        receipt_projection,evidence_tier,claim_kind,authentication_status,
        durable_receipt_hash,training_key_hash,structural_result_hash,
        structural_fit_capture_hash,structural_candidate_hash,
        structural_training_run_hash,structural_challenger_hash,
        runner_identity_hash,actual_input_material_set_hash,
        ordered_artifact_set_hash,issuer_id,trust_policy_id,signature_key_id,
        signature_algorithm,verified_at,expires_at,no_authority,authority_counters
    ) VALUES(v_attestation_hash,v_external_digest,v_inner_bytes,v_inner,
        'PLATFORM_OR_EXTERNAL_ATTESTED','ALR_FIT_EXECUTION_ATTESTATION_V1',
        'SIGNATURE_VERIFIED_BY_TRUST_POLICY',v_durable_receipt_hash,
        v_training_key_hash,v_structural_result_hash,v_structural_fit_capture_hash,
        v_structural_candidate_hash,v_structural_run_hash,v_structural_challenger_hash,
        v_runner_identity_hash,v_material_set_hash,v_set_hash,
        v_inner#>>'{authentication,issuer_id}',v_inner#>>'{authentication,trust_policy_id}',
        v_inner#>>'{authentication,signature_key_id}','ed25519',v_verified_at,
        v_expires_at,v_no_authority,v_zero_counters);
    INSERT INTO learning.alr_challenger_training_runs(
        training_run_hash,durable_receipt_hash,training_key_hash,source_head,
        actual_dataset_hash,actual_row_ids_hash,actual_split_hash,
        actual_code_manifest_hash,actual_training_config_hash,
        actual_feature_schema_hash,actual_label_schema_hash,model_schema_version,
        actual_training_rows,model_artifact_set_hash,metrics_hash,
        resource_usage_hash,run_status,model_training_performed,canonical_payload,
        no_authority,authority_counters,fit_started_at,fit_completed_at,
        durable_attestation_hash,durable_training_run_hash,attestation_bound_at,
        attestation_verified_at,attestation_expires_at
    ) VALUES(v_structural_run_hash,v_durable_receipt_hash,v_training_key_hash,
        v_observation->>'source_head',v_observation#>>'{actual_inputs,dataset_hash}',
        v_observation#>>'{actual_inputs,row_ids_hash}',v_observation#>>'{actual_inputs,split_hash}',
        v_observation#>>'{actual_inputs,code_manifest_hash}',v_observation#>>'{actual_inputs,training_config_hash}',
        v_observation#>>'{actual_inputs,feature_schema_hash}',v_observation#>>'{actual_inputs,label_schema_hash}',
        v_observation#>>'{model,model_schema_version}',(v_observation#>>'{actual_inputs,training_rows}')::INTEGER,
        v_set_hash,v_observation#>>'{model,metrics_hash}',v_observation#>>'{model,resource_usage_hash}',
        'TRAINING_PERFORMED',TRUE,v_run_payload,v_no_authority,v_zero_counters,
        (v_observation->>'fit_started_at')::TIMESTAMPTZ,
        (v_observation->>'fit_completed_at')::TIMESTAMPTZ,v_attestation_hash,
        v_durable_run_hash,v_bound_at,v_verified_at,v_expires_at);
    INSERT INTO learning.alr_challenger_model_artifacts(
        artifact_hash,training_run_hash,training_key_hash,model_artifact_set_hash,
        quantile,artifact_format,artifact_path,artifact_size_bytes,
        feature_schema_hash,model_schema_version,symlink_created,serving_visible,
        durable_attestation_hash,durable_training_run_hash
    ) VALUES
      (v_q10_hash,v_structural_run_hash,v_training_key_hash,v_set_hash,'q10','onnx',
       'runs/structural/'||v_structural_run_hash||'/q10.onnx',v_q10_size,
       v_observation#>>'{actual_inputs,feature_schema_hash}',v_observation#>>'{model,model_schema_version}',
       FALSE,FALSE,v_attestation_hash,v_durable_run_hash),
      (v_q50_hash,v_structural_run_hash,v_training_key_hash,v_set_hash,'q50','onnx',
       'runs/structural/'||v_structural_run_hash||'/q50.onnx',v_q50_size,
       v_observation#>>'{actual_inputs,feature_schema_hash}',v_observation#>>'{model,model_schema_version}',
       FALSE,FALSE,v_attestation_hash,v_durable_run_hash),
      (v_q90_hash,v_structural_run_hash,v_training_key_hash,v_set_hash,'q90','onnx',
       'runs/structural/'||v_structural_run_hash||'/q90.onnx',v_q90_size,
       v_observation#>>'{actual_inputs,feature_schema_hash}',v_observation#>>'{model,model_schema_version}',
       FALSE,FALSE,v_attestation_hash,v_durable_run_hash);
    INSERT INTO learning.alr_challenger_registry(
        challenger_hash,training_run_hash,training_key_hash,model_artifact_set_hash,
        registry_status,serving_allowed,promotion_allowed,latest_pointer_allowed,
        symlink_allowed,canonical_payload,durable_attestation_hash,
        durable_training_run_hash,durable_challenger_hash,attestation_bound_at
    ) VALUES(v_structural_challenger_hash,v_structural_run_hash,v_training_key_hash,
        v_set_hash,'NOT_SERVING',FALSE,FALSE,FALSE,FALSE,v_registry_payload,
        v_attestation_hash,v_durable_run_hash,v_durable_challenger_hash,v_bound_at);
    INSERT INTO learning.alr_challenger_consumption_terminals(
        request_hash,terminal_hash,outcome,terminal_bytes,terminal_projection,
        inner_receipt_bytes,verification_receipt_bytes,
        verification_receipt_hash,verification_receipt,consumed_at
    ) VALUES(v_request_hash,v_event_hash,'SUCCEEDED',v_event_bytes,v_projection,
             v_inner_bytes,v_verifier_bytes,v_verifier_hash,v_verifier,v_now);
    INSERT INTO learning.alr_challenger_consumption_verifier_evidence(
        verifier_receipt_hash,request_hash,action,declared_phase,
        verification_receipt_bytes,verification_receipt,recorded_at
    ) VALUES(v_verifier_hash,v_request_hash,p_action,v_phase,
             v_verifier_bytes,v_verifier,v_now);
    SET CONSTRAINTS
      learning.alr_challenger_run_complete_ct_v1,
      learning.alr_challenger_artifact_complete_ct_v1,
      learning.alr_challenger_registry_complete_ct_v1,
      learning.alr_v159_run_complete_ct_v1,
      learning.alr_v159_artifact_complete_ct_v1,
      learning.alr_v159_registry_complete_ct_v1 IMMEDIATE;
    RETURN jsonb_build_object('status','PERSISTED','action',p_action,
        'request_hash',v_request_hash,'outcome','SUCCEEDED',
        'durable_attestation_hash',v_attestation_hash,
        'structural_training_run_hash',v_structural_run_hash,
        'durable_training_run_hash',v_durable_run_hash,
        'structural_challenger_hash',v_structural_challenger_hash,
        'durable_challenger_hash',v_durable_challenger_hash,
        'attestation_bound_at',v_bound_at);
EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT' USING ERRCODE='P0001';
END
$v160_coordinator$;

CREATE OR REPLACE FUNCTION learning.read_alr_challenger_consumption_v1(
    p_request_hash TEXT
) RETURNS JSONB LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $v160_reader$
DECLARE
    v_request learning.alr_challenger_consumption_requests%ROWTYPE;
    v_claim JSONB;
    v_statuses JSONB;
    v_terminal JSONB;
    v_reconciliation JSONB;
    v_verifier_evidence JSONB;
    v_attestation JSONB;
    v_run JSONB;
    v_artifacts JSONB;
    v_registry JSONB;
BEGIN
    IF session_user<>'alr_challenger_consumption_caller'
       OR current_user<>'alr_challenger_consumption_coordinator' THEN
        RAISE EXCEPTION 'V160 reader session identity rejected';
    END IF;
    IF p_request_hash!~'^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'V160 reader request hash rejected';
    END IF;
    SELECT * INTO v_request FROM learning.alr_challenger_consumption_requests
    WHERE request_hash=p_request_hash;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('status','NOT_FOUND','request_hash',p_request_hash);
    END IF;
    SELECT to_jsonb(c) INTO v_claim
    FROM learning.alr_challenger_consumption_claims c
    WHERE c.request_hash=p_request_hash;
    SELECT COALESCE(jsonb_agg(to_jsonb(s) ORDER BY s.status_generation),'[]'::JSONB)
      INTO v_statuses FROM learning.alr_challenger_consumption_statuses s
    WHERE s.request_hash=p_request_hash;
    SELECT to_jsonb(t) INTO v_terminal
    FROM learning.alr_challenger_consumption_terminals t
    WHERE t.request_hash=p_request_hash;
    SELECT COALESCE(jsonb_agg(to_jsonb(a) ORDER BY a.recorded_at,a.reconciliation_hash),'[]'::JSONB)
      INTO v_reconciliation
    FROM learning.alr_challenger_consumption_reconciliation_audit a
    WHERE a.request_hash=p_request_hash;
    SELECT COALESCE(jsonb_agg(to_jsonb(e) ORDER BY e.recorded_at,e.action,e.verifier_receipt_hash),'[]'::JSONB)
      INTO v_verifier_evidence
    FROM learning.alr_challenger_consumption_verifier_evidence e
    WHERE e.request_hash=p_request_hash;
    SELECT to_jsonb(a) INTO v_attestation
    FROM learning.alr_challenger_fit_attestations a
    WHERE a.durable_receipt_hash=v_request.durable_receipt_hash
      AND a.training_key_hash=v_request.training_key_hash;
    SELECT to_jsonb(r) INTO v_run
    FROM learning.alr_challenger_training_runs r
    WHERE r.durable_receipt_hash=v_request.durable_receipt_hash
      AND r.training_key_hash=v_request.training_key_hash;
    SELECT COALESCE(jsonb_agg(to_jsonb(m) ORDER BY
             CASE m.quantile WHEN 'q10' THEN 1 WHEN 'q50' THEN 2 ELSE 3 END),'[]'::JSONB)
      INTO v_artifacts
    FROM learning.alr_challenger_model_artifacts m
    WHERE m.training_run_hash=v_run->>'training_run_hash';
    SELECT to_jsonb(g) INTO v_registry
    FROM learning.alr_challenger_registry g
    WHERE g.training_run_hash=v_run->>'training_run_hash';
    RETURN jsonb_build_object(
        'status','FOUND','request',to_jsonb(v_request),'claim',v_claim,
        'statuses',v_statuses,'terminal',v_terminal,
        'reconciliation_audit',v_reconciliation,
        'verifier_evidence',v_verifier_evidence,
        'v159_bundle',jsonb_build_object('attestation',v_attestation,
            'training_run',v_run,'artifacts',v_artifacts,'registry',v_registry));
END
$v160_reader$;

ALTER FUNCTION learning.coordinate_alr_challenger_consumption_v1(TEXT,JSONB)
    OWNER TO alr_challenger_consumption_coordinator;
ALTER FUNCTION learning.read_alr_challenger_consumption_v1(TEXT)
    OWNER TO alr_challenger_consumption_coordinator;
REVOKE ALL ON FUNCTION
    learning.coordinate_alr_challenger_consumption_v1(TEXT,JSONB),
    learning.read_alr_challenger_consumption_v1(TEXT)
FROM PUBLIC,alr_challenger_consumption_caller;
GRANT EXECUTE ON FUNCTION
    learning.coordinate_alr_challenger_consumption_v1(TEXT,JSONB),
    learning.read_alr_challenger_consumption_v1(TEXT)
TO alr_challenger_consumption_caller;

-- Close every old V159 application function and direct INSERT path.  The
-- exact V158 qualified-receipt writer and reader ACLs are deliberately left
-- untouched so admission can continue independently of fit consumption.
GRANT USAGE ON SCHEMA learning TO alr_challenger_consumption_coordinator;
DO $v160_relation_acl_closure$
DECLARE
    v_acl RECORD;
    v_schema_owner OID;
BEGIN
    SELECT nspowner INTO v_schema_owner FROM pg_namespace WHERE nspname='learning';
    IF session_user<>current_user
       OR current_user<>pg_get_userbyid(v_schema_owner) THEN
        RAISE EXCEPTION 'V160 ACL closure requires trusted schema owner identity';
    END IF;
    EXECUTE 'SET LOCAL ROLE alr_challenger_consumption_coordinator';
    IF current_user<>'alr_challenger_consumption_coordinator' THEN
        RAISE EXCEPTION 'V160 ACL closure failed to assume relation owner';
    END IF;
    FOR v_acl IN
        SELECT DISTINCT c.oid::regclass::TEXT AS relation_name,
                        privilege.grantee,
                        CASE WHEN privilege.grantee=0 THEN NULL
                             ELSE pg_get_userbyid(privilege.grantee) END AS grantee_name
        FROM pg_class c
        CROSS JOIN LATERAL aclexplode(
            COALESCE(c.relacl,acldefault('r',c.relowner))) privilege
        WHERE c.oid IN (
          'learning.alr_challenger_fit_attestations'::regclass,
          'learning.alr_challenger_training_runs'::regclass,
          'learning.alr_challenger_model_artifacts'::regclass,
          'learning.alr_challenger_registry'::regclass,
          'learning.alr_challenger_consumption_requests'::regclass,
          'learning.alr_challenger_consumption_claims'::regclass,
          'learning.alr_challenger_consumption_statuses'::regclass,
          'learning.alr_challenger_consumption_verifier_evidence'::regclass,
          'learning.alr_challenger_consumption_terminals'::regclass,
          'learning.alr_challenger_consumption_reconciliation_audit'::regclass)
          AND privilege.grantee<>c.relowner
        ORDER BY 1,2
    LOOP
        IF v_acl.grantee=0 THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %s FROM PUBLIC CASCADE',
                v_acl.relation_name);
        ELSE
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %s FROM %I CASCADE',
                v_acl.relation_name,v_acl.grantee_name);
        END IF;
    END LOOP;
    IF EXISTS(
        SELECT 1 FROM pg_class c
        CROSS JOIN LATERAL aclexplode(
            COALESCE(c.relacl,acldefault('r',c.relowner))) privilege
        WHERE c.oid IN (
          'learning.alr_challenger_fit_attestations'::regclass,
          'learning.alr_challenger_training_runs'::regclass,
          'learning.alr_challenger_model_artifacts'::regclass,
          'learning.alr_challenger_registry'::regclass,
          'learning.alr_challenger_consumption_requests'::regclass,
          'learning.alr_challenger_consumption_claims'::regclass,
          'learning.alr_challenger_consumption_statuses'::regclass,
          'learning.alr_challenger_consumption_verifier_evidence'::regclass,
          'learning.alr_challenger_consumption_terminals'::regclass,
          'learning.alr_challenger_consumption_reconciliation_audit'::regclass)
          AND privilege.grantee<>c.relowner) THEN
        RAISE EXCEPTION 'V160 ACL closure left a non-owner relation grant';
    END IF;
    EXECUTE 'RESET ROLE';
    IF current_user<>session_user
       OR current_user<>pg_get_userbyid(v_schema_owner) THEN
        RAISE EXCEPTION 'V160 ACL closure failed to restore trusted schema owner';
    END IF;
END
$v160_relation_acl_closure$;

REVOKE ALL ON FUNCTION
  learning.persist_alr_challenger_fit_attestation_v1(
    BYTEA,JSONB,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,
    TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ),
  learning.persist_alr_challenger_training_result_v2(
    TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,TEXT,
    TIMESTAMPTZ,TIMESTAMPTZ,TEXT,BIGINT,TEXT,BIGINT,TEXT,BIGINT),
  learning.read_alr_challenger_training_result_v2(TEXT,TEXT)
FROM PUBLIC,alr_challenger_fit_attestor_caller,
     alr_challenger_trainer_caller,alr_challenger_consumption_caller;
REVOKE ALL ON TABLE
    learning.alr_challenger_fit_attestations,
    learning.alr_challenger_training_runs,
    learning.alr_challenger_model_artifacts,
    learning.alr_challenger_registry
FROM PUBLIC,alr_challenger_writer,alr_challenger_trainer_caller,
     alr_challenger_fit_attestor,alr_challenger_fit_attestor_caller,
     alr_challenger_consumption_caller;
GRANT SELECT ON TABLE learning.alr_qualified_training_receipts
TO alr_challenger_consumption_coordinator;
GRANT SELECT,INSERT ON TABLE
    learning.alr_challenger_fit_attestations,
    learning.alr_challenger_training_runs,
    learning.alr_challenger_model_artifacts,
    learning.alr_challenger_registry,
    learning.alr_challenger_consumption_requests,
    learning.alr_challenger_consumption_claims,
    learning.alr_challenger_consumption_statuses,
    learning.alr_challenger_consumption_verifier_evidence,
    learning.alr_challenger_consumption_terminals,
    learning.alr_challenger_consumption_reconciliation_audit
TO alr_challenger_consumption_coordinator;
REVOKE ALL ON TABLE
    learning.alr_challenger_consumption_requests,
    learning.alr_challenger_consumption_claims,
    learning.alr_challenger_consumption_statuses,
    learning.alr_challenger_consumption_verifier_evidence,
    learning.alr_challenger_consumption_terminals,
    learning.alr_challenger_consumption_reconciliation_audit
FROM PUBLIC,alr_challenger_consumption_caller,
     alr_challenger_writer,alr_challenger_trainer_caller,
     alr_challenger_fit_attestor,alr_challenger_fit_attestor_caller;
GRANT USAGE ON SCHEMA learning TO
    alr_challenger_consumption_coordinator,
    alr_challenger_consumption_caller;
GRANT USAGE ON SCHEMA public TO alr_challenger_consumption_coordinator;
GRANT EXECUTE ON FUNCTION public.digest(BYTEA,TEXT)
TO alr_challenger_consumption_coordinator;
REVOKE CREATE ON SCHEMA learning,public FROM
    alr_challenger_consumption_coordinator,
    alr_challenger_consumption_caller;
REVOKE SET ON PARAMETER session_replication_role FROM
    alr_challenger_consumption_coordinator,
    alr_challenger_consumption_caller;

DO $v160_generic_closure$
DECLARE
    v_role TEXT;
BEGIN
    FOREACH v_role IN ARRAY ARRAY['trading_ai','alr_shadow'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=v_role) THEN
            EXECUTE format('REVOKE ALL ON TABLE '
              'learning.alr_challenger_fit_attestations,'
              'learning.alr_challenger_training_runs,'
              'learning.alr_challenger_model_artifacts,'
              'learning.alr_challenger_registry,'
              'learning.alr_challenger_consumption_requests,'
              'learning.alr_challenger_consumption_claims,'
              'learning.alr_challenger_consumption_statuses,'
              'learning.alr_challenger_consumption_verifier_evidence,'
              'learning.alr_challenger_consumption_terminals,'
              'learning.alr_challenger_consumption_reconciliation_audit FROM %I',v_role);
            EXECUTE format('REVOKE ALL ON FUNCTION '
              'learning.coordinate_alr_challenger_consumption_v1(TEXT,JSONB),'
              'learning.read_alr_challenger_consumption_v1(TEXT),'
              'learning.persist_alr_challenger_fit_attestation_v1('
                'BYTEA,JSONB,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,'
                'TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ),'
              'learning.persist_alr_challenger_training_result_v2('
                'TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,'
                'TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,BIGINT,TEXT,BIGINT,TEXT,BIGINT),'
              'learning.read_alr_challenger_training_result_v2(TEXT,TEXT) FROM %I',v_role);
            EXECUTE format('REVOKE CREATE ON SCHEMA learning,public FROM %I',v_role);
            EXECUTE format('REVOKE SET ON PARAMETER session_replication_role FROM %I',v_role);
        END IF;
    END LOOP;
END
$v160_generic_closure$;

DO $v160_postflight$
DECLARE
    v_coordinator OID;
    v_caller OID;
    v_writer OID;
    v_trainer_caller OID;
    v_attestor OID;
    v_attestor_caller OID;
    v_schema_owner OID;
    v_relation TEXT;
    v_function REGPROCEDURE;
    v_spec RECORD;
    v_constraint RECORD;
BEGIN
    SELECT oid INTO v_coordinator FROM pg_roles
    WHERE rolname='alr_challenger_consumption_coordinator';
    SELECT oid INTO v_caller FROM pg_roles
    WHERE rolname='alr_challenger_consumption_caller';
    SELECT oid INTO v_writer FROM pg_roles WHERE rolname='alr_challenger_writer';
    SELECT oid INTO v_trainer_caller FROM pg_roles
    WHERE rolname='alr_challenger_trainer_caller';
    SELECT oid INTO v_attestor FROM pg_roles WHERE rolname='alr_challenger_fit_attestor';
    SELECT oid INTO v_attestor_caller FROM pg_roles
    WHERE rolname='alr_challenger_fit_attestor_caller';
    SELECT nspowner INTO v_schema_owner FROM pg_namespace WHERE nspname='learning';
    IF session_user<>current_user
       OR current_user<>pg_get_userbyid(v_schema_owner)
       OR NOT EXISTS(SELECT 1 FROM pg_roles
                     WHERE oid=v_schema_owner AND rolsuper)
       OR NOT EXISTS(SELECT 1 FROM pg_roles
          WHERE oid=v_coordinator AND NOT rolcanlogin AND NOT rolinherit
            AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
            AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=-1
            AND rolvaliduntil IS NULL AND rolconfig IS NULL)
       OR NOT EXISTS(SELECT 1 FROM pg_roles
          WHERE oid=v_caller AND rolcanlogin AND NOT rolinherit
            AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
            AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=1
            AND rolvaliduntil IS NULL AND rolconfig IS NULL)
       OR NOT EXISTS(SELECT 1 FROM pg_roles
          WHERE oid=v_writer AND NOT rolcanlogin AND NOT rolinherit
            AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
            AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=-1
            AND rolvaliduntil IS NULL AND rolconfig IS NULL)
       OR NOT EXISTS(SELECT 1 FROM pg_roles
          WHERE oid=v_trainer_caller AND rolcanlogin AND NOT rolinherit
            AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
            AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=1
            AND rolvaliduntil IS NULL AND rolconfig IS NULL)
       OR NOT EXISTS(SELECT 1 FROM pg_roles
          WHERE oid=v_attestor AND NOT rolcanlogin AND NOT rolinherit
            AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
            AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=-1
            AND rolvaliduntil IS NULL AND rolconfig IS NULL)
       OR NOT EXISTS(SELECT 1 FROM pg_roles
          WHERE oid=v_attestor_caller AND rolcanlogin AND NOT rolinherit
            AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
            AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit=1
            AND rolvaliduntil IS NULL AND rolconfig IS NULL)
       OR EXISTS(SELECT 1 FROM pg_auth_members
          WHERE roleid IN(v_schema_owner,v_coordinator,v_caller,v_writer,
                          v_trainer_caller,v_attestor,v_attestor_caller)
             OR member IN(v_schema_owner,v_coordinator,v_caller,v_writer,
                          v_trainer_caller,v_attestor,v_attestor_caller)) THEN
        RAISE EXCEPTION 'V160 postflight exact owner/role posture failed';
    END IF;
    IF (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='learning' AND c.relname IN (
          'alr_challenger_consumption_requests','alr_challenger_consumption_claims',
          'alr_challenger_consumption_statuses','alr_challenger_consumption_verifier_evidence',
          'alr_challenger_consumption_terminals','alr_challenger_consumption_reconciliation_audit'
        ) AND c.relkind='r')<>6 THEN
        RAISE EXCEPTION 'V160 postflight relation inventory failed';
    END IF;
    IF (SELECT count(*) FROM pg_temp.alr_v160_expected_constraints)<>23
       OR (SELECT count(*) FROM pg_constraint c
           WHERE c.conrelid IN (
             'learning.alr_challenger_consumption_requests'::regclass,
             'learning.alr_challenger_consumption_claims'::regclass,
             'learning.alr_challenger_consumption_statuses'::regclass,
             'learning.alr_challenger_consumption_verifier_evidence'::regclass,
             'learning.alr_challenger_consumption_terminals'::regclass,
             'learning.alr_challenger_consumption_reconciliation_audit'::regclass)
             AND c.contype IN ('p','u','f','c'))<>23 THEN
        RAISE EXCEPTION 'V160 exact postflight constraint inventory drift';
    END IF;
    FOR v_spec IN SELECT * FROM pg_temp.alr_v160_expected_constraints
                  ORDER BY relation_name,name LOOP
        SELECT c.oid,c.conkey,c.contype,c.condeferrable,c.condeferred,c.convalidated,
               c.connoinherit,c.conislocal,c.coninhcount,c.conparentid,
               c.conindid,c.confupdtype,c.confdeltype,c.confmatchtype,
               (SELECT string_agg(a.attname,',' ORDER BY k.ordinality)
                FROM unnest(c.conkey) WITH ORDINALITY k(attnum,ordinality)
                JOIN pg_attribute a ON a.attrelid=c.conrelid
                                   AND a.attnum=k.attnum) AS key_columns,
               CASE WHEN c.confrelid=0 THEN NULL
                    ELSE c.confrelid::regclass::TEXT END AS foreign_relation,
               (SELECT string_agg(a.attname,',' ORDER BY k.ordinality)
                FROM unnest(c.confkey) WITH ORDINALITY k(attnum,ordinality)
                JOIN pg_attribute a ON a.attrelid=c.confrelid
                                   AND a.attnum=k.attnum) AS foreign_columns,
               CASE WHEN c.contype='c'
                    THEN pg_get_expr(c.conbin,c.conrelid,FALSE) END AS check_expr
          INTO v_constraint
          FROM pg_constraint c
         WHERE c.conrelid=v_spec.relation_name::regclass
           AND c.conname=v_spec.name;
        IF NOT FOUND
           OR (SELECT count(*) FROM pg_constraint c
               WHERE c.conrelid=v_spec.relation_name::regclass
                 AND c.conname=v_spec.name)<>1
           OR v_constraint.contype::TEXT<>v_spec.constraint_type
           OR v_constraint.condeferrable OR v_constraint.condeferred
           OR NOT v_constraint.convalidated OR NOT v_constraint.conislocal
           OR v_constraint.coninhcount<>0 OR v_constraint.conparentid<>0
           OR v_constraint.connoinherit<>(v_spec.constraint_type<>'c') THEN
            RAISE EXCEPTION 'V160 exact postflight constraint posture drift: %',
                            v_spec.name;
        END IF;
        IF v_spec.constraint_type='c' THEN
            IF v_constraint.check_expr IS DISTINCT FROM (
                SELECT pg_get_expr(c.conbin,c.conrelid,FALSE)
                FROM pg_constraint c
                WHERE c.conrelid=v_spec.expected_check_relation::regclass
                  AND c.conname=v_spec.expected_check_name) THEN
                RAISE EXCEPTION 'V160 exact postflight CHECK definition drift: %',
                                v_spec.name;
            END IF;
        ELSIF v_constraint.key_columns IS DISTINCT FROM v_spec.key_columns
           OR v_constraint.foreign_relation IS DISTINCT FROM v_spec.foreign_relation
           OR v_constraint.foreign_columns IS DISTINCT FROM v_spec.foreign_columns
           OR (v_spec.constraint_type='f' AND (
                v_constraint.confupdtype<>'a' OR v_constraint.confdeltype<>'a'
                OR v_constraint.confmatchtype<>'s')) THEN
            RAISE EXCEPTION 'V160 exact postflight key/FK definition drift: %',
                            v_spec.name;
        ELSIF v_spec.constraint_type IN ('p','u') AND NOT EXISTS (
            SELECT 1 FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid
            JOIN pg_am am ON am.oid=ic.relam
            WHERE i.indexrelid=v_constraint.conindid
              AND ic.relname=v_spec.name AND ic.relowner=v_coordinator
              AND ic.relkind='i' AND ic.relpersistence='p'
              AND ic.reloptions IS NULL AND ic.reltablespace=0
              AND am.amname='btree' AND i.indisunique
              AND i.indisprimary=(v_spec.constraint_type='p')
              AND NOT i.indisexclusion AND i.indimmediate
              AND i.indisvalid AND i.indisready AND i.indislive
              AND NOT i.indisclustered AND NOT i.indisreplident
              AND NOT i.indcheckxmin AND NOT i.indnullsnotdistinct
              AND i.indnkeyatts=i.indnatts
              AND i.indnkeyatts=cardinality(v_constraint.conkey)
              AND i.indexprs IS NULL AND i.indpred IS NULL
              AND ARRAY(SELECT k FROM unnest(i.indkey)
                        WITH ORDINALITY x(k,o) ORDER BY o)=v_constraint.conkey) THEN
            RAISE EXCEPTION 'V160 exact postflight PK/UNIQUE index drift: %',
                            v_spec.name;
        END IF;
    END LOOP;
    FOREACH v_relation IN ARRAY ARRAY[
      'learning.alr_challenger_consumption_requests',
      'learning.alr_challenger_consumption_claims',
      'learning.alr_challenger_consumption_statuses',
      'learning.alr_challenger_consumption_verifier_evidence',
      'learning.alr_challenger_consumption_terminals',
      'learning.alr_challenger_consumption_reconciliation_audit',
      'learning.alr_challenger_fit_attestations',
      'learning.alr_challenger_training_runs',
      'learning.alr_challenger_model_artifacts',
      'learning.alr_challenger_registry'
    ] LOOP
        IF NOT EXISTS(SELECT 1 FROM pg_class c
                      WHERE c.oid=v_relation::regclass
                        AND c.relowner=v_coordinator)
           OR NOT has_table_privilege('alr_challenger_consumption_coordinator',
                                   v_relation,'SELECT,INSERT')
           OR has_table_privilege('alr_challenger_consumption_caller',v_relation,
                                  'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
           OR has_table_privilege('alr_challenger_writer',v_relation,
                                  'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
           OR has_table_privilege('alr_challenger_trainer_caller',v_relation,
                                  'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
           OR has_table_privilege('alr_challenger_fit_attestor',v_relation,
                                  'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
           OR has_table_privilege('alr_challenger_fit_attestor_caller',v_relation,
                                  'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
           OR EXISTS(SELECT 1 FROM pg_class c
              CROSS JOIN LATERAL aclexplode(
                COALESCE(c.relacl,acldefault('r',c.relowner))) privilege
              WHERE c.oid=v_relation::regclass
                AND privilege.grantee<>c.relowner)
           OR (SELECT count(*) FROM pg_class c
              CROSS JOIN LATERAL aclexplode(
                COALESCE(c.relacl,acldefault('r',c.relowner))) privilege
              WHERE c.oid=v_relation::regclass
                AND privilege.grantee=c.relowner
                AND privilege.is_grantable
                AND privilege.privilege_type IN (
                  'SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'))<>7 THEN
            RAISE EXCEPTION 'V160 postflight table owner/ACL failed: %',v_relation;
        END IF;
    END LOOP;
    IF NOT EXISTS(SELECT 1 FROM pg_class c
                  WHERE c.oid='learning.alr_qualified_training_receipts'::regclass
                    AND c.relowner=v_schema_owner)
       OR EXISTS(SELECT 1 FROM pg_attribute a
                 WHERE a.attrelid IN(
                   'learning.alr_challenger_fit_attestations'::regclass,
                   'learning.alr_challenger_training_runs'::regclass,
                   'learning.alr_challenger_model_artifacts'::regclass,
                   'learning.alr_challenger_registry'::regclass,
                   'learning.alr_challenger_consumption_requests'::regclass,
                   'learning.alr_challenger_consumption_claims'::regclass,
                   'learning.alr_challenger_consumption_statuses'::regclass,
                   'learning.alr_challenger_consumption_verifier_evidence'::regclass,
                   'learning.alr_challenger_consumption_terminals'::regclass,
                   'learning.alr_challenger_consumption_reconciliation_audit'::regclass)
                   AND a.attacl IS NOT NULL) THEN
        RAISE EXCEPTION 'V160 postflight V158 preservation/column ACL failed';
    END IF;
    FOR v_spec IN SELECT * FROM (VALUES
      ('alr_challenger_run_complete_ct_v1','learning.alr_challenger_training_runs','learning.alr_v158_assert_complete_result()',29,TRUE),
      ('alr_challenger_artifact_complete_ct_v1','learning.alr_challenger_model_artifacts','learning.alr_v158_assert_complete_result()',29,TRUE),
      ('alr_challenger_registry_complete_ct_v1','learning.alr_challenger_registry','learning.alr_v158_assert_complete_result()',29,TRUE),
      ('alr_v158_immutable_alr_qualified_training_receipts_trg','learning.alr_qualified_training_receipts','learning.alr_v158_reject_mutation()',27,FALSE),
      ('alr_v158_immutable_alr_challenger_training_runs_trg','learning.alr_challenger_training_runs','learning.alr_v158_reject_mutation()',27,FALSE),
      ('alr_v158_immutable_alr_challenger_model_artifacts_trg','learning.alr_challenger_model_artifacts','learning.alr_v158_reject_mutation()',27,FALSE),
      ('alr_v158_immutable_alr_challenger_registry_trg','learning.alr_challenger_registry','learning.alr_v158_reject_mutation()',27,FALSE),
      ('alr_v159_immutable_fit_attestations_trg','learning.alr_challenger_fit_attestations','learning.alr_v159_reject_attestation_mutation()',27,FALSE),
      ('alr_v159_run_complete_ct_v1','learning.alr_challenger_training_runs','learning.alr_v159_assert_attested_bundle()',29,TRUE),
      ('alr_v159_artifact_complete_ct_v1','learning.alr_challenger_model_artifacts','learning.alr_v159_assert_attested_bundle()',29,TRUE),
      ('alr_v159_registry_complete_ct_v1','learning.alr_challenger_registry','learning.alr_v159_assert_attested_bundle()',29,TRUE),
      ('alr_v160_immutable_requests_trg','learning.alr_challenger_consumption_requests','learning.alr_v160_reject_consumption_mutation()',27,FALSE),
      ('alr_v160_immutable_claims_trg','learning.alr_challenger_consumption_claims','learning.alr_v160_reject_consumption_mutation()',27,FALSE),
      ('alr_v160_immutable_statuses_trg','learning.alr_challenger_consumption_statuses','learning.alr_v160_reject_consumption_mutation()',27,FALSE),
      ('alr_v160_immutable_verifier_evidence_trg','learning.alr_challenger_consumption_verifier_evidence','learning.alr_v160_reject_consumption_mutation()',27,FALSE),
      ('alr_v160_immutable_terminals_trg','learning.alr_challenger_consumption_terminals','learning.alr_v160_reject_consumption_mutation()',27,FALSE),
      ('alr_v160_immutable_reconciliation_trg','learning.alr_challenger_consumption_reconciliation_audit','learning.alr_v160_reject_consumption_mutation()',27,FALSE)
    ) AS x(name,relation_name,function_name,trigger_type,constrained) LOOP
        IF (SELECT count(*) FROM pg_trigger t
            WHERE t.tgname=v_spec.name AND NOT t.tgisinternal)<>1
           OR NOT EXISTS(SELECT 1 FROM pg_trigger t
              WHERE t.tgname=v_spec.name
                AND t.tgrelid=v_spec.relation_name::regclass
                AND t.tgfoid=v_spec.function_name::regprocedure
                AND t.tgtype=v_spec.trigger_type AND t.tgenabled='O'
                AND t.tgnargs=0 AND t.tgqual IS NULL AND t.tgattr::TEXT=''
                AND t.tgdeferrable=v_spec.constrained
                AND t.tginitdeferred=v_spec.constrained
                AND (t.tgconstraint<>0)=v_spec.constrained
                AND (NOT v_spec.constrained OR EXISTS(
                    SELECT 1 FROM pg_constraint c
                    WHERE c.oid=t.tgconstraint AND c.contype='t'
                      AND c.conrelid=t.tgrelid AND c.conname=t.tgname))) THEN
            RAISE EXCEPTION 'V160 exact postflight trigger tuple failed: %',
                            v_spec.name;
        END IF;
    END LOOP;
    FOREACH v_function IN ARRAY ARRAY[
      'learning.coordinate_alr_challenger_consumption_v1(text,jsonb)'::regprocedure,
      'learning.read_alr_challenger_consumption_v1(text)'::regprocedure
    ] LOOP
        IF NOT EXISTS(SELECT 1 FROM pg_proc p WHERE p.oid=v_function
            AND p.proowner=v_coordinator AND p.prosecdef
            AND p.proconfig IS NOT DISTINCT FROM CASE WHEN v_function=
                'learning.coordinate_alr_challenger_consumption_v1(text,jsonb)'::regprocedure
                THEN ARRAY['search_path=pg_catalog, pg_temp','lock_timeout=15s',
                           'statement_timeout=120s']::TEXT[]
                ELSE ARRAY['search_path=pg_catalog, pg_temp']::TEXT[] END)
           OR NOT has_function_privilege('alr_challenger_consumption_caller',
                                         v_function,'EXECUTE')
           OR EXISTS(SELECT 1 FROM pg_proc p
              CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,
                    acldefault('f',p.proowner))) privilege
              WHERE p.oid=v_function
                AND privilege.grantee NOT IN (v_coordinator,v_caller)) THEN
            RAISE EXCEPTION 'V160 postflight function ACL failed: %',v_function;
        END IF;
    END LOOP;
    IF md5((SELECT prosrc FROM pg_proc WHERE oid=
          'learning.coordinate_alr_challenger_consumption_v1(text,jsonb)'::regprocedure))
          <>'f733ebd97a6a42f3da7fa5af15f072a8'
       OR md5((SELECT prosrc FROM pg_proc WHERE oid=
          'learning.read_alr_challenger_consumption_v1(text)'::regprocedure))
          <>'27679331a7c07211a70f862d39c3d1ff'
       OR NOT EXISTS(SELECT 1 FROM pg_proc p WHERE p.oid=
          'learning.alr_v158_assert_complete_result()'::regprocedure
          AND p.proowner=v_coordinator AND p.prosecdef
          AND md5(p.prosrc)='5bc309e618dd18c926d758cb7a606204')
       OR NOT EXISTS(SELECT 1 FROM pg_proc p WHERE p.oid=
          'learning.alr_v159_assert_attested_bundle()'::regprocedure
          AND p.proowner=v_coordinator AND p.prosecdef
          AND md5(p.prosrc)='5c7e7216a1e429a08557d33bb6d9701e')
       OR NOT EXISTS(SELECT 1 FROM pg_proc p WHERE p.oid=
          'learning.persist_alr_qualified_training_receipt_v1(text,text,text,text,text,text,text,text,text,text,text,text,text,text,text,jsonb)'::regprocedure
          AND p.proowner=v_writer AND p.prosecdef
          AND md5(p.prosrc)='5edfac9aaf6b5e9e7d2ef492feb06f52')
       OR NOT EXISTS(SELECT 1 FROM pg_proc p WHERE p.oid=
          'learning.read_alr_qualified_training_receipt_v1(text,text)'::regprocedure
          AND p.proowner=v_writer AND p.prosecdef
          AND md5(p.prosrc)='0b5f006cc0cb84a970e057a01c408ea0') THEN
        RAISE EXCEPTION 'V160 postflight exact function identity failed';
    END IF;
    IF NOT has_function_privilege('alr_challenger_trainer_caller',
         'learning.persist_alr_qualified_training_receipt_v1(text,text,text,text,text,text,text,text,text,text,text,text,text,text,text,jsonb)'::regprocedure,
         'EXECUTE')
       OR NOT has_function_privilege('alr_challenger_trainer_caller',
         'learning.read_alr_qualified_training_receipt_v1(text,text)'::regprocedure,
         'EXECUTE')
       OR has_function_privilege('alr_challenger_fit_attestor_caller',
         'learning.persist_alr_challenger_fit_attestation_v1(bytea,jsonb,text,text,text,text,text,text,text,text,text,text,text,text,text,text,timestamp with time zone,timestamp with time zone)'::regprocedure,
         'EXECUTE')
       OR has_function_privilege('alr_challenger_trainer_caller',
         'learning.persist_alr_challenger_training_result_v2(text,text,text,text,text,text,text,text,text,text,integer,text,text,timestamp with time zone,timestamp with time zone,text,bigint,text,bigint,text,bigint)'::regprocedure,
         'EXECUTE')
       OR has_schema_privilege('alr_challenger_consumption_caller','learning','CREATE')
       OR has_parameter_privilege('alr_challenger_consumption_caller',
                                  'session_replication_role','SET')
       OR has_parameter_privilege('alr_challenger_writer',
                                  'session_replication_role','SET')
       OR has_parameter_privilege('alr_challenger_trainer_caller',
                                  'session_replication_role','SET')
       OR has_parameter_privilege('alr_challenger_fit_attestor',
                                  'session_replication_role','SET')
       OR has_parameter_privilege('alr_challenger_fit_attestor_caller',
                                  'session_replication_role','SET')
       OR EXISTS(SELECT 1 FROM pg_roles r
                 WHERE NOT r.rolsuper
                   AND has_schema_privilege(r.rolname,'learning','CREATE')) THEN
        RAISE EXCEPTION 'V160 postflight reachability/closure failed';
    END IF;
    IF (SELECT count(*) FROM learning.alr_challenger_fit_attestations)<>0
       OR (SELECT count(*) FROM learning.alr_challenger_training_runs)<>0
       OR (SELECT count(*) FROM learning.alr_challenger_model_artifacts)<>0
       OR (SELECT count(*) FROM learning.alr_challenger_registry)<>0 THEN
        RAISE EXCEPTION 'V160 postflight created V159 success rows';
    END IF;
END
$v160_postflight$;

COMMIT;
