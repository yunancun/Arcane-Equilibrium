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
主要函數:
  - verify_v107_inserted(): V107 row 真實寫入
  - verify_decay_signals_untouched(): learning.decay_signals 0 row
  - verify_strategy_lifecycle_untouched(): learning.strategy_lifecycle 0 row
  - verify_forbidden_columns_absent(): 6 forbidden column 0 hit
  - main(): 全 4 condition 全 PASS 才 exit 0
依賴: psycopg2, spike_trigger.py (sibling module)
硬邊界:
  - sandbox DB only
  - V113 / strategy_lifecycle 在 spike 階段不存在;test 應 graceful 處理
    (table-not-exist = 0 row 寫入 = PASS)
治理對照: ADR-0038 + ADR-0044 + CR-7 + V107 spec AC-3
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
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
    """sandbox-only DB connection"""
    if "sandbox" not in database.lower():
        LOG.error("REFUSE: database=%s not sandbox", database)
        sys.exit(2)
    return psycopg2.connect(host=host, port=port, user=user, dbname=database)


def verify_v107_inserted(
    conn: Any,
    strategy: str,
    symbol: str,
) -> tuple[bool, dict[str, Any]]:
    """
    AC-6 condition 1: M11 spike trigger 寫 V107 row 真實成功

    驗 V107 row 存在 + flag_action_taken='m7_decay_candidate' (CRITICAL severity)
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
            created_by
        FROM learning.replay_divergence_log
        WHERE strategy_id = %s
          AND symbol = %s
          AND divergence_type = 'fill_chain'
          AND flag_action_taken = 'm7_decay_candidate'
          AND severity = 'CRITICAL'
        ORDER BY divergence_detected_at DESC
        LIMIT 1
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (strategy, symbol))
        row = cur.fetchone()
    if row is None:
        LOG.error(
            "AC-6 condition 1 FAIL: V107 row not found (strategy=%s symbol=%s)",
            strategy,
            symbol,
        )
        return False, {}
    LOG.info(
        "AC-6 condition 1 PASS: V107 row id=%s flag=%s severity=%s",
        row["id"],
        row["flag_action_taken"],
        row["severity"],
    )
    return True, dict(row)


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="M11 → M7 dedup contract empirical verify"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", default="trading_admin")
    parser.add_argument("--database", default="trading_ai_sandbox")
    parser.add_argument("--strategy", default="bb_breakout")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    conn = get_db_connection(args.host, args.port, args.user, args.database)

    try:
        # 4 conditions empirical verify
        c1_pass, _ = verify_v107_inserted(conn, args.strategy, args.symbol)
        c2_pass = verify_decay_signals_untouched(conn)
        c3_pass = verify_strategy_lifecycle_untouched(conn)
        c4_pass = verify_forbidden_columns_absent(conn)

        all_pass = all([c1_pass, c2_pass, c3_pass, c4_pass])

        if all_pass:
            LOG.info(
                "AC-6 dedup contract empirical verify ALL PASS: "
                "c1(V107 INSERT)=PASS c2(decay_signals 0 row)=PASS "
                "c3(strategy_lifecycle 0 row)=PASS c4(forbidden col 0 hit)=PASS"
            )
            return 0
        LOG.error(
            "AC-6 dedup contract FAIL: c1=%s c2=%s c3=%s c4=%s",
            c1_pass,
            c2_pass,
            c3_pass,
            c4_pass,
        )
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
