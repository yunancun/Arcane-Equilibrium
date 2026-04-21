-- ============================================================
-- Diagnostic SQL — DECISION-OUTCOMES bugs audit (2026-04-21).
-- 診斷腳本 — decision_outcomes 兩個 P1 bug 現場重現。
--
-- Covers:
--   TODO 1  DECISION-OUTCOMES-ENGINE-MODE-TAG-BUG-1
--   TODO 2  OUTCOME-BACKFILL-JOIN-NULL-1
-- NOT covered here: TODO 3 is code/log only (no SQL surface).
--
-- Usage:
--   PGPASSWORD='...' psql -h localhost -U trading_admin -d trading_ai \
--     -f helper_scripts/db/audit/2026-04-21--decision_outcomes_bugs_diagnostic.sql
-- ============================================================

\echo ''
\echo '================ TODO 1: engine_mode tagging bug ================'
\echo 'Expectation: 100% of decision_outcomes rows have engine_mode=paper,'
\echo 'but context_id prefix spans demo/live/live_demo.'
SELECT
    SPLIT_PART(context_id, '-', 2) AS mode_from_context_id,
    engine_mode                    AS stored_mode,
    COUNT(*)                       AS rows
FROM trading.decision_outcomes
GROUP BY mode_from_context_id, engine_mode
ORDER BY rows DESC
LIMIT 20;

\echo ''
\echo 'For comparison, decision_context_snapshots.engine_mode IS correct'
\echo '(distribution matches ctx prefix, rules out upstream bug):'
SELECT
    SPLIT_PART(context_id, '-', 2) AS mode_from_context_id,
    engine_mode                    AS stored_mode,
    COUNT(*)                       AS rows
FROM trading.decision_context_snapshots
GROUP BY mode_from_context_id, engine_mode
ORDER BY rows DESC
LIMIT 20;

\echo ''
\echo 'Root cause: outcome_backfiller.rs INSERT omits engine_mode →'
\echo 'schema default ''paper''::text kicks in (V015 migration L64-68'
\echo 'explicitly flagged: "No writer exists yet; column added for future"'
\echo 'correct wiring").'


\echo ''
\echo '================ TODO 2: outcome_* 100% NULL ===================='
\echo 'Buggy timeframe filter: outcome_backfiller.rs uses 1/5/60/240'
\echo '(Bybit API intervals) but market.klines.timeframe stores 1m/5m/1h/4h.'
\echo ''
\echo 'Distinct values in market.klines.timeframe:'
SELECT timeframe, COUNT(*) AS rows FROM market.klines GROUP BY timeframe ORDER BY rows DESC;

\echo ''
\echo 'Proof: fixed filter returns real prices, buggy filter returns NULL.'
\echo '(3 most recent backfilled snapshots, side-by-side.)'
SELECT
    p.context_id,
    p.symbol,
    p.ts,
    p.last_price,
    (SELECT k.close FROM market.klines k
     WHERE k.symbol = p.symbol AND k.timeframe = '1m'
       AND k.ts >= p.ts + INTERVAL '1 minute'
     ORDER BY k.ts ASC LIMIT 1) AS price_1m_fixed,
    (SELECT k.close FROM market.klines k
     WHERE k.symbol = p.symbol AND k.timeframe = '1'
       AND k.ts >= p.ts + INTERVAL '1 minute'
     ORDER BY k.ts ASC LIMIT 1) AS price_1m_buggy
FROM trading.decision_context_snapshots p
WHERE p.outcome_backfilled = TRUE
  AND p.last_price > 0
ORDER BY p.ts DESC
LIMIT 3;

\echo ''
\echo 'Scale of historical damage (rows that need re-backfill):'
SELECT
    COUNT(*)                                                 AS total_outcomes_rows,
    COUNT(*) FILTER (WHERE outcome_1m IS NULL)               AS null_1m,
    COUNT(*) FILTER (WHERE outcome_5m IS NULL)               AS null_5m,
    COUNT(*) FILTER (WHERE outcome_1h IS NULL)               AS null_1h,
    COUNT(*) FILTER (WHERE outcome_4h IS NULL)               AS null_4h,
    COUNT(*) FILTER (WHERE outcome_24h IS NULL)              AS null_24h,
    COUNT(*) FILTER (WHERE max_favorable IS NULL)            AS null_mfe,
    COUNT(*) FILTER (WHERE max_adverse IS NULL)              AS null_mae
FROM trading.decision_outcomes;

\echo ''
\echo '================ Notes ========================================='
\echo 'Fix spec (do NOT apply here — audit only):'
\echo '  1. rust/openclaw_engine/src/database/outcome_backfiller.rs'
\echo '     - L58,63,68,73,78,83,88  s/k.timeframe = ''1''/''1m''/'
\echo '                               s/k.timeframe = ''5''/''5m''/'
\echo '                               s/k.timeframe = ''60''/''1h''/'
\echo '                               s/k.timeframe = ''240''/''4h''/ (4h + 24h use 4h klines)'
\echo '     - Add p.engine_mode to pending CTE SELECT (L42-51)'
\echo '     - Add engine_mode to INSERT column list (L95) + SELECT (L97-107)'
\echo '  2. After fix: reset outcome_backfilled=FALSE on affected rows,'
\echo '     let backfiller re-run (ON CONFLICT DO NOTHING will block'
\echo '     updates → need ON CONFLICT DO UPDATE or explicit DELETE).'
\echo '     Alternative: one-shot UPDATE SQL with same LATERAL subqueries.'
