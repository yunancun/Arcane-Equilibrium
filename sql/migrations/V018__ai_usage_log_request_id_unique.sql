-- ============================================================
-- V018 — AI usage log request_id deduplication (E5-FN-2 / audit §七 7.2)
-- V018 — AI 用量日誌 request_id 去重（E5-FN-2 / audit §七 7.2）
-- ============================================================
--
-- Source / 來源:
--   docs/audits/2026-04-18--e5_full_codebase_audit.md §七 7.2 (R6 / P2)
--   CLAUDE.md §二 Principle #13 — "每次 AI 調用計費"
--
-- Problem / 問題:
--   learning.ai_usage_log 當前 PK 為 (time, scope, request_id) 且 time 欄位
--   由 INSERT 端 NOW() 生成。若 consumer_loop / record_usage 在 DB 瞬斷後
--   重試，第二次 INSERT 的 time 與第一次不同，PK 並不會拒絕；同一次 AI
--   調用會被記為兩筆 usage → cost_usd 雙計 → 月度預算可能悄悄溢出。
--
--   The current PK (time, scope, request_id) with NOW()-derived time does NOT
--   dedupe retry-after-partial-failure. Same LLM call can be billed twice if a
--   caller retries after a transient DB error — overshoots the monthly budget
--   without any warning.
--
-- Fix / 修復:
--   在 request_id 上加「部分 UNIQUE 索引」（排除 legacy default ''）。
--   Writer 端改用 INSERT ... ON CONFLICT (request_id) WHERE request_id <> ''
--   DO NOTHING，成為真正的 idempotent upsert。
--   Add a PARTIAL UNIQUE index on request_id (excluding the legacy '' default)
--   so writers can use ON CONFLICT (request_id) WHERE request_id <> ''
--   DO NOTHING for idempotent upsert semantics.
--
-- Why partial (WHERE request_id <> '') / 為什麼用部分索引:
--   V010 預設 request_id DEFAULT ''，歷史資料可能留存多筆 request_id=''。
--   整張表加 UNIQUE 會破舊資料，改用部分索引保留向後相容。
--   V010 defaults request_id to ''. Existing rows likely contain multiple ''s.
--   A partial index avoids breaking historical data while still enforcing
--   uniqueness for all new, meaningfully-tagged request_ids.
--
-- Deployment / 部署:
--   1) 生產 DB 需手動 apply 本 migration（operator）：
--        psql $DATABASE_URL -f sql/migrations/V018__ai_usage_log_request_id_unique.sql
--   2) Engine binary 需含 V018 對應的 ON CONFLICT writer（本 commit 一併提供）。
--   3) 先 apply migration 再重啟 engine（舊 binary 對 V018 schema 仍相容：
--      它照樣 INSERT，只是不會利用 ON CONFLICT；部分索引會 reject 重複
--      request_id，舊 binary 會看到 duplicate key 錯誤並 fail-closed）。
--   Operator applies this migration manually (NOT auto-run).
-- ============================================================


-- ============================================================
-- Idempotency / 冪等性: re-running V018 is a no-op.
-- ============================================================
-- Partial UNIQUE index on request_id (skips empty defaults).
-- request_id 部分 UNIQUE 索引（跳過空值預設）。
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_usage_log_request_id
    ON learning.ai_usage_log (request_id)
    WHERE request_id <> '';

COMMENT ON INDEX learning.uq_ai_usage_log_request_id IS
    'Dedup guard for request_id (E5-FN-2): prevents double-billing when a retry fires'
    ' a second record_usage with the same client-supplied request_id. Partial — skips'
    ' legacy rows with request_id='''' so V010 historical data remains valid. |'
    ' E5-FN-2：以 request_id 去重防止 record_usage 重試雙計；部分索引跳過 V010 歷史空值。';


-- ============================================================
-- Verification / 驗證:
--   1) Index exists and is partial:
--      SELECT indexdef FROM pg_indexes
--       WHERE schemaname='learning'
--         AND indexname='uq_ai_usage_log_request_id';
--      Expect: CREATE UNIQUE INDEX ... WHERE (request_id <> ''::text)
--
--   2) Dedup works (manual test on a non-prod DB):
--      INSERT INTO learning.ai_usage_log (time, scope, provider, model,
--           tokens_in, tokens_out, cost_usd, purpose, request_id)
--       VALUES (NOW(), 'agent_teacher', 'anthropic', 'claude-sonnet-4-5',
--               1000, 500, 0.0105, 'dedup_test', 'test-req-001')
--       ON CONFLICT (request_id) WHERE request_id <> '' DO NOTHING
--       RETURNING time;   -- first call: 1 row
--      -- re-run the same query:
--      -- 2nd call: 0 rows (dedupped)
--
--   3) Legacy rows still insertable (request_id=''):
--      INSERT ... (request_id='') on multiple rows does NOT violate the partial UNIQUE.
-- ============================================================
