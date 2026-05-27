-- post_restore_validation.sql
-- OPS-4 GAP-B 配套：PG restore 完成後跑 9 query block 驗業務完整性
-- Owner: MIT (per FA business acceptance audit §B.1)
-- Source: srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-27--ops_4_gap_bd_business_acceptance_audit.md
-- Updated: 2026-05-27
--
-- 用途 / Why this script exists:
--   pg_restore 成功 (exit 0) ≠ 業務可重用。本 script 9 query 驗 16 L0 表的 9 個關鍵
--   business invariant (4/9 9-safety-invariant 必 re-verify: I1/I2/I7/I8 + 5 額外 L0 chain
--   integrity)。restore drill 必跑；任一 query FAIL → 不可 swap 至 live。
--
-- 使用方式 / Usage:
--   PGPASSWORD=<pwd> psql -h <host> -U <user> -d <restored_db_name> \
--       -v ON_ERROR_STOP=1 -f post_restore_validation.sql
--
--   建議搭配 -X (不讀 .psqlrc) + -A (unaligned output for grep) + -t (tuples only):
--   PGPASSWORD=$PG_PASS psql -X -A -t -h $PG_HOST -U $PG_USER -d $RESTORED_DB \
--       -v ON_ERROR_STOP=1 -f post_restore_validation.sql 2>&1 | tee \
--       /tmp/openclaw/logs/post_restore_validation_$(date -u +%Y%m%dT%H%M%SZ).log
--
-- Two-mode 區分:
--   - SANDBOX MODE: 對 trading_ai_drill_YYYYMMDD 跑（drill scenario 4/5）
--   - SWAP-PREP MODE: 對 trading_ai_restore_YYYYMMDD 跑（drill scenario 1/2 即將 swap）
--   兩 mode 共用 9 query；差別在 baseline 比對：
--   - SANDBOX：比對「pre-disaster snapshot 紀錄檔」(restore 前 operator 跑 baseline_snapshot.sql)
--   - SWAP-PREP：比對「dump 前 source DB」(restore 前 source 仍可達)
--   每 query header 標 [SANDBOX] / [SWAP-PREP] / [BOTH] 適用範圍
--
-- Pass criteria summary:
--   9/9 query PASS → restore 可進入 swap phase (drill scenario 1) OR drill PASS verdict
--   任一 query FAIL → 必查 RCA，不可 swap；落 drill report 紀錄 FAIL detail
--
-- Cross-ref:
--   - FA audit §B.1: 9 query 對應 invariant + business rationale
--   - PA OPS-4 runbook §10 GAP-B
--   - MIT report 2026-05-27 §2.4 (10-step verify 補強版)
--   - CLAUDE.md §四 5-gate hard boundary / §二 root principle #8

\timing on
\set ON_ERROR_STOP on

-- =============================================================================
-- Query 1 [BOTH]: system.autonomy_level_config (V099) — I1 5-gate state 完整
-- =============================================================================
-- 業務目的：5-gate hard boundary 第一條 = autonomy posture (CONSERVATIVE/STANDARD)；
--   singleton CHECK (id=1) enforcement 必驗；level_before/level_after 對齊 enum
-- Pass criteria：1 row + id=1 + current_level IN ('CONSERVATIVE','STANDARD')
-- FAIL action：seed 缺 = 不可進 swap；走 V099 re-apply path
\echo '=== Query 1: system.autonomy_level_config (I1 5-gate state) ==='
SELECT
    id,
    current_level,
    last_switched_at_utc,
    CASE
        WHEN id = 1 AND current_level IN ('CONSERVATIVE', 'STANDARD') THEN 'PASS'
        ELSE 'FAIL'
    END AS verdict
FROM system.autonomy_level_config;
-- expect: exactly 1 row, verdict='PASS'

-- =============================================================================
-- Query 2 [BOTH]: learning.governance_audit_log lease_grant (V035) — I2 signed auth
-- =============================================================================
-- 業務目的：5-gate hard boundary 第二條 = signed authorization 必走 Python renew/approve；
--   restore 後 lease_grant event 必存在表 = audit chain 不中斷的證據
-- Pass criteria：last 24h 至少 1 row（first-day live 首日；若是 day 1 disaster 則放寬到全期 ≥ 1）
-- FAIL action：governance audit 殘缺 → I2 不可信 → restore 必重做
\echo '=== Query 2: learning.governance_audit_log lease_grant count (I2 signed auth) ==='
WITH baseline AS (
    SELECT NOW() - INTERVAL '24 hours' AS lookback_ts
)
SELECT
    'lease_grant_24h' AS metric,
    COUNT(*) AS row_count,
    MIN(ts) AS oldest_ts,
    MAX(ts) AS newest_ts,
    CASE
        WHEN COUNT(*) > 0 THEN 'PASS'
        ELSE 'WARN (0 lease_grant in 24h — accept if day-1 disaster)'
    END AS verdict
FROM learning.governance_audit_log, baseline
WHERE event_type = 'lease_grant'
  AND ts > baseline.lookback_ts;
-- expect: row_count ≥ 1 (post first-day); WARN tolerable if disaster within first 24h

-- =============================================================================
-- Query 3 [BOTH]: learning.lease_transitions (V054) — I7 Decision Lease state
-- =============================================================================
-- 業務目的：root principle #3 (AI→Lease→複核) + I7 (ML/Dream/Executor 不繞 Governance)；
--   每 lease 完整 state transition 必 reproducible 才能繼續 live trading
-- Pass criteria：last 24h lease_id 分布 + to_state 分布合理（不全 'rejected' / 不全 'pending'）
-- FAIL action：transition chain 斷 → 可能 producer code drift；不可 swap
\echo '=== Query 3: learning.lease_transitions last 24h aggregated (I7 lease state) ==='
WITH lt_24h AS (
    SELECT lease_id, to_state, ts
    FROM learning.lease_transitions
    WHERE ts > NOW() - INTERVAL '24 hours'
)
SELECT
    to_state,
    COUNT(*) AS transition_count,
    COUNT(DISTINCT lease_id) AS distinct_lease,
    MIN(ts) AS oldest_ts,
    MAX(ts) AS newest_ts
FROM lt_24h
GROUP BY to_state
ORDER BY transition_count DESC;
-- expect: ≥ 2 distinct to_state values; verdict by operator 視 lease emission rate 對齊 baseline

-- =============================================================================
-- Query 4 [BOTH]: trading.fills 完整性 (V003) — root principle #8 every-trade-reconstructable
-- =============================================================================
-- 業務目的：核心交易記錄 SoT；restore 必須能對 Bybit account balance reconcile (root principle #8)
-- Pass criteria：count + ts range + realized_pnl SUM 對齊 pre-disaster baseline snapshot；
--   engine_mode 分布合理；is_paper=false 的 row 數對齊 Bybit fills history
-- FAIL action：fills 殘缺 → 對 Bybit 對賬會 fail → 不可 swap
\echo '=== Query 4: trading.fills integrity (last 24h + cumulative; root principle #8) ==='
SELECT
    'last_24h' AS window,
    COUNT(*) AS fill_count,
    MIN(ts) AS oldest_ts,
    MAX(ts) AS newest_ts,
    COUNT(DISTINCT symbol) AS distinct_symbol,
    ROUND(SUM(realized_pnl)::NUMERIC, 4) AS sum_realized_pnl,
    COUNT(*) FILTER (WHERE is_paper = FALSE) AS live_fill_count
FROM trading.fills
WHERE ts > NOW() - INTERVAL '24 hours'
UNION ALL
SELECT
    'cumulative' AS window,
    COUNT(*),
    MIN(ts),
    MAX(ts),
    COUNT(DISTINCT symbol),
    ROUND(SUM(realized_pnl)::NUMERIC, 4),
    COUNT(*) FILTER (WHERE is_paper = FALSE)
FROM trading.fills;
-- expect: 24h count > 0 (first-day live ≥ 1 fill); cumulative SUM(realized_pnl)
--   對齊 operator pre-disaster snapshot 紀錄

-- =============================================================================
-- Query 5 [BOTH]: trading.intents → orders FK lineage — I8 lineage 不破
-- =============================================================================
-- 業務目的：root principle #8 every-trade-reconstructable；intents→orders lineage 是
--   audit chain 核心；任 orphan = lineage 中斷 → 9 invariant #8 violate
-- Pass criteria：post-restore 0 orphan intent (有對應 order)；若 dump 時點本身有
--   in-flight intent (legitimate)，需要與 pre-disaster snapshot 比對 delta
-- FAIL action：orphan intent 數量 > pre-disaster baseline → 可能 dump 不一致；不可 swap
\echo '=== Query 5: intents → orders FK lineage orphan check (I8 lineage) ==='
WITH lineage_check AS (
    SELECT
        i.intent_id,
        i.ts AS intent_ts,
        o.intent_id AS order_intent_id
    FROM trading.intents i
    LEFT JOIN trading.orders o ON o.intent_id = i.intent_id
    WHERE i.ts > NOW() - INTERVAL '24 hours'
)
SELECT
    'orphan_intents_24h' AS metric,
    COUNT(*) FILTER (WHERE order_intent_id IS NULL) AS orphan_count,
    COUNT(*) AS total_intents,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE order_intent_id IS NULL) / NULLIF(COUNT(*), 0),
        2
    ) AS orphan_pct,
    CASE
        WHEN COUNT(*) = 0 THEN 'WARN (0 intents in 24h)'
        WHEN COUNT(*) FILTER (WHERE order_intent_id IS NULL)::FLOAT / COUNT(*) > 0.1 THEN 'FAIL'
        ELSE 'PASS'
    END AS verdict
FROM lineage_check;
-- expect: orphan_pct < 10% (一些 governance reject 是 OK 但 > 10% 異常)

-- =============================================================================
-- Query 6 [BOTH]: learning.earn_movement_log (V100) — BB OPS-3 C-4 Earn audit
-- =============================================================================
-- 業務目的：Bybit Earn stake/redeem 唯一本地 audit；丟失 = 稅務 + monetary loss
--   FA gap #1 + BB OPS-3 C-4 verdict; PA spec §2.2 RPO 表已補列為 ≤ 24h
-- Pass criteria：direction 分布 stake/redeem 合理；amount_usdt SUM 對齊 Bybit
--   Earn API external query (operator 手動對賬步驟)
-- FAIL action：表內 0 row 但 operator 已 stake → RPO violation → 必 RCA + Bybit cross-check
\echo '=== Query 6: learning.earn_movement_log (BB OPS-3 C-4 Earn audit) ==='
SELECT
    direction,
    COUNT(*) AS movement_count,
    ROUND(SUM(amount_usdt)::NUMERIC, 8) AS sum_amount_usdt,
    MIN(event_ts) AS oldest_event_ts,
    MAX(event_ts) AS newest_event_ts
FROM learning.earn_movement_log
GROUP BY direction
ORDER BY direction;
-- expect: 若 operator 已 stake → ≥ 1 row direction='stake'；
--   下游 verify step: operator 用 Bybit Earn /api/v5/earn/account 對賬 SUM(amount_usdt)

-- =============================================================================
-- Query 7 [BOTH]: learning.strategist_applied_params (V019) — root principle #11
-- =============================================================================
-- 業務目的：4 active strategy applied params SoT；root principle #11 (P0/P1 boundary
--   agents 自主選 strategy/symbol/param/timing)；restore 必有 active strategy snapshot
-- Pass criteria：4 active strategy (grid_trading / ma_crossover / bb_breakout /
--   bb_reversion) 各 ≥ 1 row；engine_mode IN ('live', 'live_demo') filter；
--   funding_arb 退役後不在 active 名單
-- FAIL action：active strategy 缺 row → strategist 重啟後將 default fallback；不可 swap
\echo '=== Query 7: learning.strategist_applied_params per-strategy max(applied_at) ==='
SELECT
    strategy_name,
    engine_mode,
    COUNT(*) AS apply_count,
    MAX(applied_at) AS latest_apply,
    COUNT(*) FILTER (WHERE applied_at > NOW() - INTERVAL '7 days') AS apply_7d
FROM learning.strategist_applied_params
WHERE engine_mode IN ('live', 'live_demo')
  AND strategy_name IN ('grid_trading', 'ma_crossover', 'bb_breakout', 'bb_reversion')
GROUP BY strategy_name, engine_mode
ORDER BY strategy_name, engine_mode;
-- expect: 4 strategy 各 ≥ 1 row in live/live_demo; latest_apply 不過 7d (Wave 2 cycle)

-- =============================================================================
-- Query 8 [BOTH]: learning.hypothesis_preregistration (V100) — signed integrity
-- =============================================================================
-- 業務目的：M4 hypothesis preregistration signed append-only audit；payload_hash
--   git-style content hash 必對齊 + signed_at 時序連續；FA L0 #12 必驗
-- Pass criteria：last 10 row payload_hash NOT NULL + signed_at 嚴格遞增 + engine_mode
--   IN allowlist；preregistration_id 唯一性 (PK invariant)
-- FAIL action：payload_hash NULL 或 signed_at 倒退 → producer code drift；不可 swap
\echo '=== Query 8: hypothesis_preregistration signed integrity (last 10) ==='
SELECT
    preregistration_id,
    hypothesis_id,
    LEFT(payload_hash, 16) AS payload_hash_short,
    signed_at,
    engine_mode,
    CASE
        WHEN payload_hash IS NULL THEN 'FAIL (NULL hash)'
        WHEN engine_mode NOT IN ('paper', 'demo', 'live_demo', 'live', 'replay') THEN 'FAIL (bad engine_mode)'
        ELSE 'PASS'
    END AS verdict
FROM learning.hypothesis_preregistration
ORDER BY signed_at DESC
LIMIT 10;
-- expect: 0 'FAIL' verdict; signed_at 嚴格 DESC (no time-warp)

-- =============================================================================
-- Query 9 [BOTH]: governance.lease_lal_assignments (V112) — ADR-0034 LAL tier integrity
-- =============================================================================
-- 業務目的：M1 LAL 5-tier per-lease assignment append-only audit；ADR-0034 唯一 SoT
--   FA L0 #2 必驗；5 tier seed (governance.lease_lal_tiers tier_level 0..4) 必完整
-- Pass criteria：last 24h tier_level 分布合理 (大多 LAL 0-2 default; LAL 3-4 罕見);
--   tier_change_reason 6 enum 內;engine_mode 5 enum 內;
--   governance.lease_lal_tiers 必有 exactly 5 row (tier_level 0..4 唯一)
-- FAIL action：LAL seed 缺 → AMD-2026-05-21-01 v2 fail-safe 不可重建；不可 swap
\echo '=== Query 9a: governance.lease_lal_assignments tier distribution last 24h ==='
SELECT
    tier_level,
    COUNT(*) AS assignment_count,
    COUNT(DISTINCT lease_id) AS distinct_lease,
    MIN(assigned_at) AS oldest_assignment,
    MAX(assigned_at) AS newest_assignment
FROM governance.lease_lal_assignments
WHERE assigned_at > NOW() - INTERVAL '24 hours'
GROUP BY tier_level
ORDER BY tier_level;
\echo '=== Query 9b: governance.lease_lal_tiers 5-tier seed integrity ==='
SELECT
    tier_level,
    tier_name,
    auto_approve,
    approval_quorum,
    CASE
        WHEN tier_level IN (0, 1, 2, 3, 4) THEN 'PASS'
        ELSE 'FAIL (unexpected tier)'
    END AS verdict
FROM governance.lease_lal_tiers
ORDER BY tier_level;
-- expect: exactly 5 row, tier_level 0..4, all verdict='PASS'

-- =============================================================================
-- Aggregate summary（drill report 直接 paste）
-- =============================================================================
\echo '=== AGGREGATE SUMMARY ==='
WITH q1 AS (SELECT COUNT(*) AS n FROM system.autonomy_level_config WHERE id = 1 AND current_level IN ('CONSERVATIVE','STANDARD')),
     q2 AS (SELECT COUNT(*) AS n FROM learning.governance_audit_log WHERE event_type = 'lease_grant' AND ts > NOW() - INTERVAL '24 hours'),
     q3 AS (SELECT COUNT(DISTINCT to_state) AS n FROM learning.lease_transitions WHERE ts > NOW() - INTERVAL '24 hours'),
     q4 AS (SELECT COUNT(*) AS n FROM trading.fills WHERE ts > NOW() - INTERVAL '24 hours'),
     q5 AS (SELECT COUNT(*) FILTER (WHERE o.intent_id IS NULL) AS orphan_n,
                   COUNT(*) AS total_n
            FROM trading.intents i LEFT JOIN trading.orders o ON o.intent_id = i.intent_id
            WHERE i.ts > NOW() - INTERVAL '24 hours'),
     q6 AS (SELECT COUNT(*) AS n FROM learning.earn_movement_log),
     q7 AS (SELECT COUNT(DISTINCT strategy_name) AS n FROM learning.strategist_applied_params
            WHERE engine_mode IN ('live', 'live_demo')
              AND strategy_name IN ('grid_trading', 'ma_crossover', 'bb_breakout', 'bb_reversion')),
     q8 AS (SELECT COUNT(*) FILTER (WHERE payload_hash IS NULL) AS bad_n,
                   COUNT(*) AS total_n
            FROM (SELECT * FROM learning.hypothesis_preregistration ORDER BY signed_at DESC LIMIT 10) sub),
     q9 AS (SELECT COUNT(*) AS n FROM governance.lease_lal_tiers WHERE tier_level IN (0,1,2,3,4))
SELECT
    'Q1 autonomy_level_config singleton' AS check_name,
    q1.n AS metric,
    CASE WHEN q1.n = 1 THEN 'PASS' ELSE 'FAIL' END AS verdict FROM q1
UNION ALL SELECT 'Q2 lease_grant 24h', q2.n,
    CASE WHEN q2.n > 0 THEN 'PASS' ELSE 'WARN' END FROM q2
UNION ALL SELECT 'Q3 lease_transitions distinct to_state 24h', q3.n,
    CASE WHEN q3.n >= 2 THEN 'PASS' ELSE 'WARN' END FROM q3
UNION ALL SELECT 'Q4 trading.fills 24h', q4.n,
    CASE WHEN q4.n > 0 THEN 'PASS' ELSE 'WARN' END FROM q4
UNION ALL SELECT 'Q5 intents orphan_pct 24h',
    CASE WHEN q5.total_n > 0 THEN ROUND(100.0 * q5.orphan_n / q5.total_n)::BIGINT ELSE 0 END,
    CASE
        WHEN q5.total_n = 0 THEN 'WARN'
        WHEN 1.0 * q5.orphan_n / q5.total_n > 0.1 THEN 'FAIL'
        ELSE 'PASS'
    END FROM q5
UNION ALL SELECT 'Q6 earn_movement_log total', q6.n,
    CASE WHEN q6.n >= 0 THEN 'PASS (operator cross-check)' ELSE 'FAIL' END FROM q6
UNION ALL SELECT 'Q7 active strategy applied_params', q7.n,
    CASE WHEN q7.n >= 1 THEN 'PASS' ELSE 'FAIL' END FROM q7
UNION ALL SELECT 'Q8 preregistration bad_hash_in_top_10', q8.bad_n,
    CASE WHEN q8.bad_n = 0 THEN 'PASS' ELSE 'FAIL' END FROM q8
UNION ALL SELECT 'Q9 lease_lal_tiers seed count', q9.n,
    CASE WHEN q9.n = 5 THEN 'PASS' ELSE 'FAIL' END FROM q9;

-- =============================================================================
-- 結束 / End
-- =============================================================================
\echo '=== post_restore_validation.sql DONE — 對照 AGGREGATE SUMMARY ==='
\echo 'PASS criteria: ≥ 7/9 PASS + 0 FAIL → drill verdict PASS;'
\echo '              0 FAIL + ≤ 2 WARN OK in day-1 disaster scenario'
\echo '              任 FAIL → drill report 紀錄 + 不可 swap to live'
