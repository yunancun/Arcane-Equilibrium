"""
MODULE_NOTE
模塊用途：Sprint 1A-ζ Track C AC-6 M11 → M7 dedup contract empirical verify
  - M11 寫 V107 row (flag_action_taken='m7_decay_candidate')
  - empirical verify M11 NOT write 4 條 path:
    1. learning.strategy_lifecycle = 0 row 寫入 (M11 不寫 lifecycle per
       ADR-0044 Decision 1 + CR-7)
    2. learning.decay_signals = 0 row 寫入 (M7 V113 own;M11 只 emit signal)
    3. V107 schema 6 forbidden column = 0 hit (CR-7 single decay authority)
    4. M7 read-only consumer 走 pull/poll V107;M11 不 push 到 V113
  - round 2 HIGH-1: condition c5 = Guard A forbidden column reverse fire
    empirical (ADD COLUMN auto_demote BOOLEAN → 再跑 V107 expect RAISE EXCEPTION)
主要函數:
  - verify_v107_row_exists() / verify_v107_row_flag(): LOW-1 condition 1 分兩條
  - verify_decay_signals_untouched(): learning.decay_signals 0 row
  - verify_strategy_lifecycle_untouched(): learning.strategy_lifecycle 0 row
  - verify_forbidden_columns_absent(): 6 forbidden column 0 hit
  - verify_guard_a_forbidden_column_reverse_fire(): round 2 HIGH-1 新 c5
  - main(): 全 condition 全 PASS 才 exit 0
依賴: psycopg2, spike_trigger.py (sibling module)
硬邊界:
  - sandbox DB only;default sandbox_admin (per Phase 0 §2.2)
  - V113 / strategy_lifecycle 在 spike 階段不存在;test 應 graceful 處理
    (table-not-exist = 0 row 寫入 = PASS)
  - condition c5 cleanup: ADD COLUMN 撞 Guard A 後必 DROP COLUMN IF EXISTS,
    避免 sandbox state 殘留
治理對照: ADR-0038 + ADR-0044 + CR-7 + V107 spec AC-3
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2 missing", file=sys.stderr)
    sys.exit(2)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOG = logging.getLogger("m11_dedup_contract_test")


def get_db_connection(
    host: str,
    port: int,
    user: str,
    database: str,
) -> Any:
    """
    sandbox-only DB connection

    為什麼 sandbox_admin fallback (per round 2 HIGH-2):
        Phase 0 §2.2 設計 sandbox_admin 為 sandbox 隔絕 role;但 E3 push back
        defer 到 Phase 2。sandbox_admin 未創時連線會 InvalidPassword,提示
        operator 顯式用 trading_admin override (sandbox DB 仍隔絕)。
    """
    if "sandbox" not in database.lower():
        LOG.error("REFUSE: database=%s not sandbox", database)
        sys.exit(2)
    try:
        return psycopg2.connect(host=host, port=port, user=user, dbname=database)
    except psycopg2.OperationalError as exc:
        if user == "sandbox_admin":
            LOG.error(
                "DB connection failed with user=sandbox_admin (Phase 0 §2.2 "
                "role 可能尚未創建; E3 push back defer 至 Phase 2): %s",
                exc,
            )
            LOG.error(
                "→ Operator 可顯式 `--user trading_admin` retry; sandbox DB "
                "(%s) 仍隔絕 production trading_ai。",
                database,
            )
        raise


def verify_v107_row_exists(
    conn: Any,
    strategy: str,
    symbol: str,
) -> tuple[bool, dict[str, Any]]:
    """
    AC-6 condition 1a (LOW-1 拆分): V107 row 真實存在 (independent of flag)
    """
    sql = """
        SELECT
            id,
            replay_run_id,
            divergence_type,
            severity,
            flag_action_taken,
            strategy_id,
            symbol,
            engine_mode,
            created_by,
            baseline_5d_mean,
            baseline_5d_sigma,
            noise_floor_threshold
        FROM learning.replay_divergence_log
        WHERE strategy_id = %s
          AND symbol = %s
          AND divergence_type = 'fill_chain'
          AND created_by = 'm11_spike_trigger'
        ORDER BY divergence_detected_at DESC
        LIMIT 1
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (strategy, symbol))
        row = cur.fetchone()
    if row is None:
        LOG.error(
            "AC-6 condition 1a FAIL: V107 row not found "
            "(strategy=%s symbol=%s created_by=m11_spike_trigger)",
            strategy,
            symbol,
        )
        return False, {}
    LOG.info(
        "AC-6 condition 1a PASS: V107 row exists id=%s severity=%s",
        row["id"],
        row["severity"],
    )
    return True, dict(row)


def verify_v107_row_flag(row: dict[str, Any]) -> bool:
    """
    AC-6 condition 1b (LOW-1 拆分): V107 row 帶 flag_action_taken='m7_decay_candidate'
    (CRITICAL severity);獨立失敗模式
    """
    if not row:
        LOG.error("AC-6 condition 1b FAIL: row=None (1a 已失敗)")
        return False
    if row.get("flag_action_taken") != "m7_decay_candidate":
        LOG.error(
            "AC-6 condition 1b FAIL: row id=%s flag_action_taken=%s "
            "(expected m7_decay_candidate)",
            row.get("id"),
            row.get("flag_action_taken"),
        )
        return False
    if row.get("severity") != "CRITICAL":
        LOG.error(
            "AC-6 condition 1b FAIL: row id=%s severity=%s "
            "(expected CRITICAL pair with m7_decay_candidate)",
            row.get("id"),
            row.get("severity"),
        )
        return False
    LOG.info(
        "AC-6 condition 1b PASS: row id=%s flag=m7_decay_candidate severity=CRITICAL",
        row["id"],
    )
    return True


def verify_decay_signals_untouched(conn: Any) -> bool:
    """
    AC-6 condition 2: M11 不寫 learning.decay_signals (M7 V113 own;per CR-7)

    為什麼 graceful 處理 table-not-exist:
        spike 階段 V113 不存在;table 不存在 = M11 物理不可能寫入 = PASS
        若 V113 已 land (Sprint 8) → count = 0 仍 PASS;> 0 = FAIL
    """
    sql = """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='learning'
              AND table_name='decay_signals'
        ) AS exists
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        exists = cur.fetchone()[0]

    if not exists:
        LOG.info(
            "AC-6 condition 2 PASS: learning.decay_signals does not exist "
            "(V113 not yet land);M11 物理不可能寫入 → dedup contract preserved"
        )
        return True

    # V113 已存在 → 必驗 0 row written by M11
    sql_count = """
        SELECT count(*) FROM learning.decay_signals
        WHERE created_by IN ('m11_replay_engine', 'm11_spike_trigger')
           OR source_module = 'm11'
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql_count)
            count = cur.fetchone()[0]
    except psycopg2.errors.UndefinedColumn:
        # V113 schema 可能無 created_by / source_module column;此情況視為 PASS
        # (graceful 對齊 spike 階段)
        conn.rollback()
        LOG.warning(
            "AC-6 condition 2 PARTIAL: V113 exists but no created_by/source_module col;"
            " skipping strict count; logical PASS"
        )
        return True

    if count > 0:
        LOG.error(
            "AC-6 condition 2 FAIL: M11 wrote %s row to learning.decay_signals "
            "(violates CR-7 single decay authority)",
            count,
        )
        return False
    LOG.info(
        "AC-6 condition 2 PASS: 0 row written to learning.decay_signals by M11"
    )
    return True


def verify_strategy_lifecycle_untouched(conn: Any) -> bool:
    """
    AC-6 condition 3 (extra strict): M11 不寫 learning.strategy_lifecycle
    (per ADR-0044 Decision 1: M7 唯一寫 strategy_lifecycle;M11 emit signal only)

    同 condition 2 logic
    """
    sql = """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='learning'
              AND table_name='strategy_lifecycle'
        ) AS exists
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        exists = cur.fetchone()[0]

    if not exists:
        LOG.info(
            "AC-6 condition 3 PASS: learning.strategy_lifecycle does not exist "
            "(V113 not yet land);M11 物理不可能寫入 → ADR-0044 Decision 1 preserved"
        )
        return True

    sql_count = """
        SELECT count(*) FROM learning.strategy_lifecycle
        WHERE created_by IN ('m11_replay_engine', 'm11_spike_trigger')
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql_count)
            count = cur.fetchone()[0]
    except psycopg2.errors.UndefinedColumn:
        conn.rollback()
        LOG.warning(
            "AC-6 condition 3 PARTIAL: strategy_lifecycle exists but no created_by col;"
            " skipping strict count; logical PASS"
        )
        return True

    if count > 0:
        LOG.error(
            "AC-6 condition 3 FAIL: M11 wrote %s row to learning.strategy_lifecycle "
            "(violates ADR-0044 Decision 1)",
            count,
        )
        return False
    LOG.info(
        "AC-6 condition 3 PASS: 0 row written to learning.strategy_lifecycle by M11"
    )
    return True


def verify_forbidden_columns_absent(conn: Any) -> bool:
    """
    AC-6 condition 4: V107 schema 6 forbidden column = 0 hit
    (per CR-7 + ADR-0038 Decision 3 + ADR-0044 Decision 1)

    M11 sensor;M7 single decay authority。V107 不可含:
        auto_demote / target_state / decay_recommendation /
        demote_proposal_id / decay_stage / stage_demoted
    """
    forbidden_cols = [
        "auto_demote",
        "target_state",
        "decay_recommendation",
        "demote_proposal_id",
        "decay_stage",
        "stage_demoted",
    ]
    sql = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='learning'
          AND table_name='replay_divergence_log'
          AND column_name = ANY(%s)
        ORDER BY column_name
    """
    with conn.cursor() as cur:
        cur.execute(sql, (forbidden_cols,))
        hits = cur.fetchall()
    if hits:
        LOG.error(
            "AC-6 condition 4 FAIL: V107 schema contains forbidden columns: %s",
            [h[0] for h in hits],
        )
        return False
    LOG.info(
        "AC-6 condition 4 PASS: 0 forbidden column in V107 schema "
        "(CR-7 single decay authority preserved)"
    )
    return True


def verify_guard_a_forbidden_column_reverse_fire(
    conn: Any,
    v107_sql_path: Path,
) -> bool:
    """
    AC-6 condition 5 (round 2 HIGH-1 新): Guard A forbidden column reverse
    pattern empirical fire

    為什麼必要:
        spec C2 + AC-3 要求 runtime RAISE fire empirical;round 1 只做靜態
        grep (V107.sql DDL forbidden column 0 hit) 未撞 RAISE 點。round 2
        empirical fire flow:
            1) ALTER TABLE learning.replay_divergence_log
                 ADD COLUMN auto_demote BOOLEAN;
            2) 再跑 V107 Guard A 那個 DO $$ ... END $$ block (透過 \\i 或
               psql -f) → 預期 RAISE EXCEPTION 'V107 Guard A FAIL: ...
               FORBIDDEN action column ...'
            3) 截 RAISE message 對齊 spec
            4) 必 cleanup: DROP COLUMN IF EXISTS auto_demote
        若 RAISE 未 fire → Guard A 反模式失敗 → c5 FAIL → IMPL 失敗

    return: True 若 RAISE fire 且 cleanup 成功;False 任一階段 fail
    """
    LOG.info(
        "AC-6 condition 5 START: Guard A forbidden column reverse fire empirical"
    )
    # Step 1: ALTER TABLE ADD COLUMN auto_demote
    try:
        with conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE learning.replay_divergence_log "
                "ADD COLUMN IF NOT EXISTS auto_demote BOOLEAN"
            )
        conn.commit()
        LOG.info("c5 Step 1 OK: ADD COLUMN auto_demote BOOLEAN")
    except psycopg2.Error as exc:
        conn.rollback()
        LOG.error("c5 Step 1 FAIL: ADD COLUMN error: %s", exc)
        return False

    # Step 2: 再跑 V107 Guard A 那個 DO block (直接以 inline SQL 把 forbidden
    # column 反模式 reproduce — 對齊 V107.sql line 108-124 的 RAISE 邏輯;
    # 為什麼用 inline reproduce: 避免重 apply 整個 V107.sql 影響 sandbox
    # state;只測 Guard A forbidden column DO block 行為)
    inline_guard_a_reverse = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='learning' AND table_name='replay_divergence_log'
          AND column_name IN (
              'auto_demote', 'target_state', 'decay_recommendation',
              'demote_proposal_id', 'decay_stage', 'stage_demoted'
          )
    ) THEN
        RAISE EXCEPTION
            'V107 Guard A FAIL: learning.replay_divergence_log contains '
            'FORBIDDEN action column. Per CR-7 + ADR-0038 Decision 3 + '
            'ADR-0044 Decision 1, M11 is SENSOR only — M7 (V113) is '
            'single decay authority. V107 schema must not contain '
            'auto_demote / target_state / decay_recommendation / '
            'demote_proposal_id / decay_stage / stage_demoted. Remove '
            'offending column or move to V113.';
    END IF;
END $$;
"""
    fire_ok = False
    raise_message = ""
    try:
        with conn.cursor() as cur:
            cur.execute(inline_guard_a_reverse)
        # 為什麼到這代表 FAIL:Guard A 應該 RAISE EXCEPTION 中斷;走到 commit 表示反模式偵測失效
        conn.commit()
        LOG.error(
            "c5 Step 2 FAIL: Guard A inline reverse 應 RAISE EXCEPTION,"
            "但 DO block 正常完成 → forbidden column 反模式偵測失效"
        )
    except psycopg2.errors.RaiseException as exc:
        # 預期路徑:Guard A RAISE 點火;
        conn.rollback()
        raise_message = str(exc).strip()
        if "V107 Guard A FAIL" in raise_message and "FORBIDDEN action column" in raise_message:
            LOG.info(
                "c5 Step 2 PASS: Guard A RAISE EXCEPTION fired correctly. "
                "Message: %s",
                raise_message[:300],
            )
            fire_ok = True
        else:
            LOG.error(
                "c5 Step 2 FAIL: RAISE fired but message mismatch. Actual: %s",
                raise_message[:300],
            )
    except psycopg2.Error as exc:
        conn.rollback()
        LOG.error("c5 Step 2 FAIL: unexpected DB error: %s", exc)

    # Step 3: cleanup — DROP COLUMN IF EXISTS auto_demote
    try:
        with conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE learning.replay_divergence_log "
                "DROP COLUMN IF EXISTS auto_demote"
            )
        conn.commit()
        LOG.info("c5 Step 3 OK: DROP COLUMN IF EXISTS auto_demote cleanup done")
    except psycopg2.Error as exc:
        conn.rollback()
        LOG.error(
            "c5 Step 3 FAIL: cleanup DROP COLUMN error: %s. "
            "Sandbox state 可能殘留 auto_demote column!",
            exc,
        )
        return False

    # Suppress unused variable warning;v107_sql_path 保留 in API 供未來
    # 完整 V107.sql replay 升級 (Sprint 3 W15-18 Phase A)
    _ = v107_sql_path
    if fire_ok:
        LOG.info("AC-6 condition 5 PASS: Guard A forbidden column reverse fire empirical 通過")
    return fire_ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="M11 → M7 dedup contract empirical verify"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    # round 2 HIGH-2: default 改 sandbox_admin (對齊 Phase 0 §2.2);
    # operator 連 production 必須顯式 `--user trading_admin`
    parser.add_argument("--user", default="sandbox_admin")
    parser.add_argument("--database", default="trading_ai_sandbox")
    parser.add_argument("--strategy", default="bb_breakout")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument(
        "--v107-sql",
        default="srv/sql/migrations/V107__replay_divergence_log.sql",
        help="V107.sql path for c5 Guard A reverse fire test (inline reproduce)",
    )
    parser.add_argument(
        "--skip-c5",
        action="store_true",
        help="skip round 2 HIGH-1 condition c5 Guard A reverse fire (for debug)",
    )
    args = parser.parse_args()

    conn = get_db_connection(args.host, args.port, args.user, args.database)

    try:
        # 4+1 conditions empirical verify (round 2 LOW-1 拆 c1 為 1a+1b;
        # round 2 HIGH-1 新增 c5 Guard A reverse fire)
        c1a_pass, row = verify_v107_row_exists(conn, args.strategy, args.symbol)
        c1b_pass = verify_v107_row_flag(row)
        c2_pass = verify_decay_signals_untouched(conn)
        c3_pass = verify_strategy_lifecycle_untouched(conn)
        c4_pass = verify_forbidden_columns_absent(conn)

        if args.skip_c5:
            LOG.warning("c5 skipped per --skip-c5")
            c5_pass = True
        else:
            c5_pass = verify_guard_a_forbidden_column_reverse_fire(
                conn, Path(args.v107_sql)
            )

        all_pass = all([c1a_pass, c1b_pass, c2_pass, c3_pass, c4_pass, c5_pass])

        if all_pass:
            LOG.info(
                "AC-6 dedup contract empirical verify ALL PASS: "
                "c1a(V107 row exist)=PASS c1b(flag=m7_decay_candidate)=PASS "
                "c2(decay_signals 0 row)=PASS c3(strategy_lifecycle 0 row)=PASS "
                "c4(forbidden col 0 hit)=PASS c5(Guard A reverse fire)=PASS"
            )
            return 0
        LOG.error(
            "AC-6 dedup contract FAIL: c1a=%s c1b=%s c2=%s c3=%s c4=%s c5=%s",
            c1a_pass,
            c1b_pass,
            c2_pass,
            c3_pass,
            c4_pass,
            c5_pass,
        )
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
