-- ============================================================
-- V137: research.pre_registered_hypotheses + research.alpha_wealth_ledger
--       L2 Mesh P4 online-FDR research loop —— α-wealth 事件帳本 + pre-registration
--
-- 目的：
--   P4（PA 設計 2026-06-10--l2-p4-online-fdr-design.md §2.3，經 MIT final
--   ratification N-1/N-2/N-5 修正覆寫）把「無限測試流的統計紀律」落到 PG：
--
--   research.pre_registered_hypotheses —— hypothesis 承諾（commit-reveal）。
--     immutable：修訂 = 新 row + supersedes 血緣，永不 UPDATE。
--     spec_sha256 = canonical_sha256(spec_jsonb)（與 bridge _canonical_sha256
--     byte-identical 算法），消費層 hash 重算 ≠ 註冊 hash → DEFER（防 post-hoc
--     spec mining，QC sign-off 點 1）。
--
--   research.alpha_wealth_ledger —— α-wealth append-only 事件帳本（banking-
--     ledger 式）。balance = SUM(amount)，無物化 running balance（審計純淨）。
--     debit_state 由事件導出（視圖 alpha_wealth_debit_state）= M1「debit_state
--     必須在 PG、非 in-memory fail-safe」的落點。
--
-- 建表順序是 load-bearing：表一 pre_registered_hypotheses 必須先建——
--   表二 ledger 的 pre_reg_id 帶 FK（MIT N-5：無 FK 則 orphan pre_reg_id
--   可入庫、斷 audit 鏈）。
--
-- MIT ratification 強制覆寫（蓋過 PA 設計原文 DDL）：
--   N-1：awl_debit_fields_chk 三值邏輯洞封死——PG CHECK 對 NULL 判 pass，
--        原文 `n_eff>=1` 在 n_eff IS NULL 時整式 NULL → CHECK 通過。改為
--        每欄顯式 IS NOT NULL + 值約束。
--   N-2：refund × debit_failed 終局事件互斥——原文兩個分開 partial unique
--        各管各的（同 debit_id 可同時有 refund 與 debit_failed）。改為單一
--        awl_one_terminal_per_debit（WHERE event_type IN ('refund','debit_failed')）。
--   N-5：ledger.pre_reg_id 加 REFERENCES（原文僅註解箭頭）。
--   附加（N-2 鏡像洞，承同一三值邏輯原則）：terminal 事件（refund/debit_failed）
--        必須帶 debit_id——partial unique index 對 NULL debit_id 互不相撞
--        （NULL ≠ NULL），NULL debit_id 的 refund 列可無限制累加 = wealth-inflation
--        向量（N-3 家族）。awl_terminal_needs_debit_id_chk 封死；這實作的是
--        設計原文自己宣告的「debit/refund/debit_failed 必填」欄位語義。
--   附加（N-1 同款，prh_falsification_chk）：原文 CHECK 在 falsification_test
--        key 缺席時整式 NULL → 放行；為陣列時 ? 按元素匹配也可全過。前置
--        存在性謂詞 + jsonb_typeof='object' 封死（嚴格收緊，無放寬面）。
--
-- 範圍 / 硬邊界：
--   - additive only；不改任何既有表、不碰 order / promotion / lease / live。
--   - 純 research-plane 統計紀律帳本，不授權任何 live 行為。
--   - append-only：REVOKE UPDATE, DELETE；trading_ai 只 INSERT/SELECT。
--     錯誤 refund 唯一修正 = operator_adjustment 事件（審計留痕，不 DELETE）。
--   - 部署即態 = 0 rows + 全 flag-OFF = 行為中性（P1-P3b dormant 慣例）。
--
-- 為什麼 idempotent / double-apply safe：
--   全部物件 IF NOT EXISTS / CREATE OR REPLACE / DO-block。Guard A 在表已存在
--   時反射必要欄位，缺欄即 RAISE（防 schema 漂移被靜默放過）。REVOKE 區塊用
--   DO 包住 trading_ai 分支（prod 無 trading_ai role —— P1 deploy-NOTE），
--   role 缺席時 NOTICE 不報錯（V134:230-238 範本）。Linux PG 雙 apply 冪等
--   實證見 E1-C dry-run（feedback_v_migration_pg_dry_run）。
--
-- Guard（ADR-0010）：
--   Guard A：既有表缺必要欄 → RAISE（兩表各一）。
--   Guard B：型別敏感欄位反射（numeric / jsonb / timestamptz / bigint）。
--   Guard C：unique/partial index + CHECK constraint 存在性（pg_indexes /
--            pg_constraint 反射，非空表 EXPLAIN——空表 planner 必走 seq scan，
--            EXPLAIN 驗 index 是假證據）。
--
-- Precedent（file:line）：
--   - REVOKE role-absent DO-block = V134:230-240。
--   - CREATE SCHEMA IF NOT EXISTS research = V125:154 / V127:151。
--   - hash CHECK bare-hex 風格 = V132:110-113。
--   - 事件帳本 append-only = V054 lease_transitions / V134 l2_calls。
-- ============================================================

BEGIN;

-- research schema 在 V125/V127 已建；此處再保險一次（IF NOT EXISTS 冪等）。
CREATE SCHEMA IF NOT EXISTS research;

-- ─────────────────────────────────────────────────────────────────────────────
-- 表一：research.pre_registered_hypotheses（先建——表二 FK 依賴）
-- ─────────────────────────────────────────────────────────────────────────────

-- Guard A（prh）：表已存在時反射必要欄位，缺欄即 RAISE。
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'research' AND table_name = 'pre_registered_hypotheses'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'pre_reg_id',
            'created_at',
            'family_id',
            'capability_id',
            'signal_axis',
            'source_l2_reply_id',
            'spec_jsonb',
            'spec_sha256',
            'supersedes_pre_reg_id',
            'actor_id'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'research' AND table_name = 'pre_registered_hypotheses'
              AND column_name = c
        );

        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V137 Guard A FAIL: research.pre_registered_hypotheses exists but missing required columns: %.',
                v_missing;
        END IF;
    END IF;
END $$;

-- immutable 承諾表：修訂 = 新 row + supersedes_pre_reg_id 血緣，永不 UPDATE。
CREATE TABLE IF NOT EXISTS research.pre_registered_hypotheses (
    pre_reg_id            BIGSERIAL   PRIMARY KEY,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    family_id             TEXT        NOT NULL,   -- = capability_id || ':' || primary_axis
    capability_id         TEXT        NOT NULL,
    signal_axis           TEXT        NOT NULL,   -- primary axis（∈ context available_signal_axes）
    source_l2_reply_id    TEXT,                   -- D3 provenance（agent.l2_calls 鏈，logical FK）
    spec_jsonb            JSONB       NOT NULL,   -- {statement, mechanism, signal_axes_used,
                                                  --  falsification_test:{null_hypothesis,
                                                  --  test_statistic, reject_condition}}
    -- canonical_sha256(spec_jsonb)：與 bridge _canonical_sha256 byte-identical
    -- （sort_keys / separators / ensure_ascii）。bare-hex（V132 風格）。
    spec_sha256           TEXT        NOT NULL
        CHECK (spec_sha256 ~ '^[0-9a-f]{64}$'),
    supersedes_pre_reg_id BIGINT
        REFERENCES research.pre_registered_hypotheses(pre_reg_id),
    actor_id              TEXT        NOT NULL,
    -- falsification_test 三欄結構化（contract v2 + guard clause F 的 DB 兜底）：
    -- 自由字串 falsification = 存而不裁 theater（QC FIX-1.3 前提）。
    -- N-1 同款三值邏輯封堵（原文 CHECK 的兩個殘洞）：
    --   (1) key 整個缺席 → spec_jsonb->'falsification_test' 為 NULL →
    --       NULL ? 'x' 為 NULL → CHECK 三值邏輯放行；前置 ? 謂詞回 false
    --       （非 NULL）即封死。
    --   (2) falsification_test 為陣列 ['null_hypothesis',...] 時 ? 按陣列
    --       元素匹配也能全過 → jsonb_typeof = 'object' 鎖死容器型別。
    CONSTRAINT prh_falsification_chk CHECK (
        spec_jsonb ? 'falsification_test'
        AND jsonb_typeof(spec_jsonb->'falsification_test') = 'object'
        AND spec_jsonb->'falsification_test' ? 'null_hypothesis'
        AND spec_jsonb->'falsification_test' ? 'test_statistic'
        AND spec_jsonb->'falsification_test' ? 'reject_condition'
    )
);

-- 同 family 同 spec 不可重複註冊（重提交必須走 supersedes 血緣鑄新 hash 或被擋）。
-- 跨 family 同 spec 合法（MIT 4b：各付各的 α，全域 bound 不破）——healthcheck
-- [85] 做 cross-family duplicate spec_sha256 觀測級計數。
CREATE UNIQUE INDEX IF NOT EXISTS prh_family_spec_uk
    ON research.pre_registered_hypotheses (family_id, spec_sha256);

-- Guard B（prh）：型別敏感欄位反射。
DO $$
DECLARE
    v_bad TEXT[];
BEGIN
    SELECT array_agg(column_name || ':' || data_type) INTO v_bad
    FROM information_schema.columns
    WHERE table_schema = 'research' AND table_name = 'pre_registered_hypotheses'
      AND (
        (column_name = 'pre_reg_id' AND data_type <> 'bigint')
        OR (column_name = 'created_at' AND data_type <> 'timestamp with time zone')
        OR (column_name = 'spec_jsonb' AND data_type <> 'jsonb')
        OR (column_name = 'spec_sha256' AND data_type <> 'text')
        OR (column_name = 'supersedes_pre_reg_id' AND data_type <> 'bigint')
      );

    IF v_bad IS NOT NULL AND array_length(v_bad, 1) > 0 THEN
        RAISE EXCEPTION 'V137 Guard B FAIL: research.pre_registered_hypotheses type drift: %.', v_bad;
    END IF;
END $$;

-- Guard C（prh）：唯一索引 + falsification CHECK 存在性。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'research' AND tablename = 'pre_registered_hypotheses'
          AND indexname = 'prh_family_spec_uk'
    ) THEN
        RAISE EXCEPTION 'V137 Guard C FAIL: prh_family_spec_uk missing.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'prh_falsification_chk'
          AND conrelid = 'research.pre_registered_hypotheses'::regclass
    ) THEN
        RAISE EXCEPTION 'V137 Guard C FAIL: prh_falsification_chk missing.';
    END IF;
END $$;

-- append-only（prh）：REVOKE UPDATE, DELETE；trading_ai 只 INSERT/SELECT。
-- DO 包住 trading_ai 分支，prod 無此 role 時 NOTICE 不報錯（V134 範本）。
REVOKE UPDATE, DELETE ON research.pre_registered_hypotheses FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON research.pre_registered_hypotheses FROM trading_ai';
        EXECUTE 'GRANT SELECT, INSERT ON research.pre_registered_hypotheses TO trading_ai';
        EXECUTE 'GRANT USAGE ON SEQUENCE research.pre_registered_hypotheses_pre_reg_id_seq TO trading_ai';
        RAISE NOTICE 'V137: research.pre_registered_hypotheses — trading_ai = INSERT/SELECT only; UPDATE/DELETE revoked';
    ELSE
        RAISE NOTICE 'V137: trading_ai role absent (dev sandbox); REVOKE on PUBLIC sufficient';
    END IF;
END $$;

COMMENT ON TABLE research.pre_registered_hypotheses IS
    'P4 online-FDR pre-registration (commit-reveal). Immutable append-only: revision = new row + supersedes_pre_reg_id lineage, never UPDATE. spec_sha256 = canonical_sha256(spec_jsonb); consumer recomputes before any statistic is rendered and DEFERs on mismatch (anti spec-mining). Not trading authority.';

-- ─────────────────────────────────────────────────────────────────────────────
-- 表二：research.alpha_wealth_ledger（append-only 事件帳本）
-- ─────────────────────────────────────────────────────────────────────────────

-- Guard A（awl）：表已存在時反射必要欄位，缺欄即 RAISE。
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'research' AND table_name = 'alpha_wealth_ledger'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'event_id',
            'created_at',
            'family_id',
            'capability_id',
            'signal_axis',
            'event_type',
            'debit_id',
            'amount',
            'alpha_i',
            'n_eff',
            'k_for_dsr',
            'pre_reg_id',
            'demo_strategy',
            'demo_symbol',
            'demo_deployed_at',
            'evidence',
            'actor_id'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'research' AND table_name = 'alpha_wealth_ledger'
              AND column_name = c
        );

        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V137 Guard A FAIL: research.alpha_wealth_ledger exists but missing required columns: %.',
                v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS research.alpha_wealth_ledger (
    event_id      BIGSERIAL   PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    family_id     TEXT        NOT NULL,   -- = capability_id || ':' || primary_axis（§2.4）
    capability_id TEXT        NOT NULL,
    signal_axis   TEXT        NOT NULL,   -- primary axis（enum 字彙 = context available_signal_axes）
    event_type    TEXT        NOT NULL CHECK (event_type IN
                    ('family_init', 'debit', 'refund', 'debit_failed', 'operator_adjustment')),
    debit_id      TEXT,                   -- 一次 test 的群組鍵（debit/refund/debit_failed 必填）
    amount        NUMERIC(14,10) NOT NULL, -- init/refund/上調 >0；debit/下調 <0；debit_failed = 0
    alpha_i       NUMERIC(14,10),          -- debit 事件必填（名目 test level）
    n_eff         INTEGER,                 -- M2：debit 事件必填，>=1（max(1,N_eff) guard）
    k_for_dsr     INTEGER,                 -- M2：必 = n_eff（單一 N_eff 餵兩機制的審計欄）
    pre_reg_id    BIGINT
        REFERENCES research.pre_registered_hypotheses(pre_reg_id),  -- MIT N-5：FK 鎖 audit 鏈
    demo_strategy TEXT,                    -- binding（§7：debit↔demo 部署）
    demo_symbol   TEXT,
    demo_deployed_at TIMESTAMPTZ,
    evidence      JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- alpha_target/gamma/phi 當時值、對帳細節
    actor_id      TEXT        NOT NULL,
    -- 事件金額符號不變量（記帳正確性的 DB 層鐵閘之一）。
    CONSTRAINT awl_amount_sign_chk CHECK (
        (event_type = 'family_init' AND amount > 0)
        OR (event_type = 'debit' AND amount < 0)
        OR (event_type = 'refund' AND amount > 0)
        OR (event_type = 'debit_failed' AND amount = 0)
        OR (event_type = 'operator_adjustment')
    ),
    -- MIT N-1：debit 必填欄逐欄顯式 IS NOT NULL——PG CHECK 對 NULL 判 pass
    -- （三值邏輯），原文 `n_eff>=1` 在 NULL 時整式 NULL → 通過 = 「必填」未被
    -- DB enforce。本式封死該洞。
    CONSTRAINT awl_debit_fields_chk CHECK (
        event_type <> 'debit'
        OR (
            alpha_i IS NOT NULL
            AND n_eff IS NOT NULL AND n_eff >= 1
            AND k_for_dsr IS NOT NULL AND k_for_dsr = n_eff
            AND pre_reg_id IS NOT NULL
            AND debit_id IS NOT NULL
        )
    ),
    -- N-2 鏡像洞封堵：terminal 事件必帶 debit_id。partial unique 對 NULL
    -- debit_id 互不相撞（NULL ≠ NULL）→ 無此 CHECK 則 NULL debit_id 的
    -- refund(+amount) 可無限累加（wealth-inflation 向量，N-3 家族）。
    CONSTRAINT awl_terminal_needs_debit_id_chk CHECK (
        event_type NOT IN ('refund', 'debit_failed') OR debit_id IS NOT NULL
    )
);

-- 冪等 / 反重複（記帳正確性的 DB 層鐵閘；double-debit / double-refund 必須
-- 在 DB 層就不可能，不靠應用層自律——設計 §14-1）：
CREATE UNIQUE INDEX IF NOT EXISTS awl_one_init_per_family
    ON research.alpha_wealth_ledger (family_id) WHERE event_type = 'family_init';
CREATE UNIQUE INDEX IF NOT EXISTS awl_one_debit_per_id
    ON research.alpha_wealth_ledger (debit_id) WHERE event_type = 'debit';
-- MIT N-2：refund 與 debit_failed 是同一 debit 的互斥終局事件——單一 partial
-- unique 同時封死 double-refund、double-fail、refund+fail 並存三種壞態。
CREATE UNIQUE INDEX IF NOT EXISTS awl_one_terminal_per_debit
    ON research.alpha_wealth_ledger (debit_id)
    WHERE event_type IN ('refund', 'debit_failed');
-- balance 查詢熱路徑：SELECT COALESCE(SUM(amount),0) WHERE family_id = ...
CREATE INDEX IF NOT EXISTS awl_family_created
    ON research.alpha_wealth_ledger (family_id, created_at DESC);

-- Guard B（awl）：型別敏感欄位反射。amount/alpha_i 必須是 numeric（float8 會
-- 破 NUMERIC(14,10) 的十進位精確記帳語義）。
DO $$
DECLARE
    v_bad TEXT[];
BEGIN
    SELECT array_agg(column_name || ':' || data_type) INTO v_bad
    FROM information_schema.columns
    WHERE table_schema = 'research' AND table_name = 'alpha_wealth_ledger'
      AND (
        (column_name = 'amount' AND data_type <> 'numeric')
        OR (column_name = 'alpha_i' AND data_type <> 'numeric')
        OR (column_name = 'n_eff' AND data_type <> 'integer')
        OR (column_name = 'k_for_dsr' AND data_type <> 'integer')
        OR (column_name = 'pre_reg_id' AND data_type <> 'bigint')
        OR (column_name = 'created_at' AND data_type <> 'timestamp with time zone')
        OR (column_name = 'demo_deployed_at' AND data_type <> 'timestamp with time zone')
        OR (column_name = 'evidence' AND data_type <> 'jsonb')
      );

    IF v_bad IS NOT NULL AND array_length(v_bad, 1) > 0 THEN
        RAISE EXCEPTION 'V137 Guard B FAIL: research.alpha_wealth_ledger type drift: %.', v_bad;
    END IF;
END $$;

-- Guard C（awl）：反重複鐵閘 + N-1/N-2 約束存在性（pg_indexes / pg_constraint
-- 反射；不可用空表 EXPLAIN——空表 planner 必走 seq scan，假證據）。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'research' AND tablename = 'alpha_wealth_ledger'
          AND indexname = 'awl_one_init_per_family'
    ) THEN
        RAISE EXCEPTION 'V137 Guard C FAIL: awl_one_init_per_family missing.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'research' AND tablename = 'alpha_wealth_ledger'
          AND indexname = 'awl_one_debit_per_id'
    ) THEN
        RAISE EXCEPTION 'V137 Guard C FAIL: awl_one_debit_per_id missing.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'research' AND tablename = 'alpha_wealth_ledger'
          AND indexname = 'awl_one_terminal_per_debit'
    ) THEN
        RAISE EXCEPTION 'V137 Guard C FAIL: awl_one_terminal_per_debit missing (MIT N-2).';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'research' AND tablename = 'alpha_wealth_ledger'
          AND indexname = 'awl_family_created'
    ) THEN
        RAISE EXCEPTION 'V137 Guard C FAIL: awl_family_created missing.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'awl_debit_fields_chk'
          AND conrelid = 'research.alpha_wealth_ledger'::regclass
    ) THEN
        RAISE EXCEPTION 'V137 Guard C FAIL: awl_debit_fields_chk missing (MIT N-1).';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'awl_amount_sign_chk'
          AND conrelid = 'research.alpha_wealth_ledger'::regclass
    ) THEN
        RAISE EXCEPTION 'V137 Guard C FAIL: awl_amount_sign_chk missing.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'awl_terminal_needs_debit_id_chk'
          AND conrelid = 'research.alpha_wealth_ledger'::regclass
    ) THEN
        RAISE EXCEPTION 'V137 Guard C FAIL: awl_terminal_needs_debit_id_chk missing.';
    END IF;
END $$;

-- append-only（awl）：REVOKE UPDATE, DELETE；trading_ai 只 INSERT/SELECT
-- + USAGE on BIGSERIAL sequence。錯誤帳務唯一修正 = operator_adjustment 事件。
REVOKE UPDATE, DELETE ON research.alpha_wealth_ledger FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON research.alpha_wealth_ledger FROM trading_ai';
        EXECUTE 'GRANT SELECT, INSERT ON research.alpha_wealth_ledger TO trading_ai';
        EXECUTE 'GRANT USAGE ON SEQUENCE research.alpha_wealth_ledger_event_id_seq TO trading_ai';
        RAISE NOTICE 'V137: research.alpha_wealth_ledger — trading_ai = INSERT/SELECT only; UPDATE/DELETE revoked';
    ELSE
        RAISE NOTICE 'V137: trading_ai role absent (dev sandbox); REVOKE on PUBLIC sufficient';
    END IF;
END $$;

COMMENT ON TABLE research.alpha_wealth_ledger IS
    'P4 online-FDR alpha-wealth append-only event ledger (M1). balance = SUM(amount) per family_id; no materialized running balance. debit-on-test, phi=1.0 refund only on demo-confirmed. Double-debit / double-refund / refund+fail coexistence are impossible at DB level (partial unique indexes awl_one_debit_per_id + awl_one_terminal_per_debit). Research-plane accounting only, not trading authority.';
COMMENT ON COLUMN research.alpha_wealth_ledger.k_for_dsr IS
    'M2 audit column: MUST equal n_eff (DB CHECK). The single N_eff feeds both compute_dsr(n_trials=...) and this debit row — same value, same source.';
COMMENT ON COLUMN research.alpha_wealth_ledger.debit_id IS
    'Groups one conducted test: exactly one debit row (awl_one_debit_per_id) and at most one terminal row — refund XOR debit_failed (awl_one_terminal_per_debit, MIT N-2).';

-- ─────────────────────────────────────────────────────────────────────────────
-- debit_state 導出視圖（M1「debit_state 在 PG」驗收字面落點）
--   N-2 互斥索引保證 r/f 至多一邊存在 → CASE 判定無歧義。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW research.alpha_wealth_debit_state AS
SELECT d.debit_id,
       d.family_id,
       d.pre_reg_id,
       d.alpha_i,
       d.n_eff,
       d.created_at AS debited_at,
       CASE WHEN r.debit_id IS NOT NULL THEN 'confirmed'
            WHEN f.debit_id IS NOT NULL THEN 'failed'
            ELSE 'pending' END AS debit_state
FROM research.alpha_wealth_ledger d
LEFT JOIN research.alpha_wealth_ledger r
       ON r.debit_id = d.debit_id AND r.event_type = 'refund'
LEFT JOIN research.alpha_wealth_ledger f
       ON f.debit_id = d.debit_id AND f.event_type = 'debit_failed'
WHERE d.event_type = 'debit';

REVOKE UPDATE, DELETE ON research.alpha_wealth_debit_state FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'GRANT SELECT ON research.alpha_wealth_debit_state TO trading_ai';
        RAISE NOTICE 'V137: research.alpha_wealth_debit_state — trading_ai SELECT granted';
    ELSE
        RAISE NOTICE 'V137: trading_ai role absent (dev sandbox); view grants skipped';
    END IF;
END $$;

COMMENT ON VIEW research.alpha_wealth_debit_state IS
    'Event-derived debit state machine: pending (no terminal row) / confirmed (refund row) / failed (debit_failed row). Consumed by alpha_wealth_refund_reconciler (pending rows only).';

COMMIT;
