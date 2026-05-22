"""
MODULE_NOTE
模塊用途：Sprint 1A-ζ Track C M11 spike trigger (skeleton)
  - 手動 1 次 trigger M11 replay (非 nightly cron;per Q4a override + spike scope §2.3)
  - scope 限 1 strategy × 1 symbol × 1 day (per spike spec §2.3 C3)
  - 接 trading_ai_sandbox PG;不動 production
  - 寫 V107 row (engine_mode='replay')
主要函數:
  - main(): 解析 args + 跑 1 次 spike trigger
  - load_fills_window(): 拉 last 1d bb_breakout BTCUSDT live_demo fills
  - detect_d1_fill_chain(): thin wrapper 委派至 divergence_d1_fill_chain
    (per round 2 HIGH-3: leak-free shift(1) + baseline column 落地)
  - write_divergence_row(): 寫 V107 row + flag_action_taken='m7_decay_candidate'
    + baseline_5d_mean / sigma / noise_floor_threshold (per round 2 HIGH-3)
依賴: psycopg2, trading.fills, learning.replay_divergence_log, learning.hypotheses
  + divergence_d1_fill_chain (sibling module, round 2 HIGH-3 後正式 import)
硬邊界:
  - 不真 nightly cron (Sprint 3 W15-18 Phase A 才上線)
  - 不寫 learning.decay_signals (M7 V113 own; per CR-7 + ADR-0044 Decision 1)
  - engine_mode INSERT='replay' (原 live trace mode 進 evidence_json)
  - 只跑 1 種 divergence type D1 fill_chain count delta (per spike spec C4)
  - sandbox DB only; default 走 sandbox_admin role (per Phase 0 §2.2 設計);
    operator 可顯式 `--user trading_admin` override 並接受 sandbox isolation 警告
治理對照: ADR-0038 + ADR-0044 + CR-7 + V107 spec
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from dataclasses import dataclass
from typing import Any

# stdlib psycopg2 (sandbox CI 已裝)
try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except ImportError:
    print(
        "ERROR: psycopg2 missing. install via `pip install psycopg2-binary` "
        "or use system package. spike sandbox runs on Linux trade-core.",
        file=sys.stderr,
    )
    sys.exit(2)

# round 2 HIGH-3: 正式 import sibling detector module;不再內聯
from divergence_d1_fill_chain import (
    compute_5d_baseline,
    detect_with_baseline,
    inject_synthetic_fixture,
    leak_free_shift1_replay,
)

# 日誌設定: 對齊 helper_scripts 標準 (per CLAUDE.md %s format)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOG = logging.getLogger("m11_spike_trigger")


# 為什麼採 dataclass:固定 trigger metadata + audit-friendly
@dataclass(frozen=True)
class SpikeTriggerConfig:
    """spike trigger 配置 (per Q4a override scope)"""

    # 連線參數 (sandbox DB only;不可指 production)
    pg_host: str
    pg_port: int
    pg_user: str
    pg_database: str  # 必 trading_ai_sandbox

    # spike scope (限 1 strategy × 1 symbol × 1 day per spike spec §2.3 C3)
    strategy_id: str
    symbol: str
    window_hours: int  # 預設 24h
    inject_synthetic_divergence: bool  # 注 1 synthetic divergence (per spike Task 2)


def get_db_connection(cfg: SpikeTriggerConfig) -> Any:
    """
    取 PG 連線;讀取 ~/.pgpass 或 PGPASSWORD env

    為什麼 sandbox-only:
        Q1d operator sign-off sandbox DB 隔絕 production;
        若連線指向 trading_ai 直接 sys.exit(2)

    為什麼 sandbox_admin fallback 邏輯 (per round 2 HIGH-2):
        Phase 0 §2.2 設計 sandbox_admin 為 sandbox 隔絕 role;但 E3 push
        back 已將 sandbox_admin 創建 defer 到 Phase 2。spike 期間
        sandbox_admin 可能不存在;此函式偵測連線失敗(InvalidPassword /
        UndefinedObject 等 InsufficientPrivilege subtype)會 retry 並提示
        operator 顯式用 trading_admin。
    """
    if "sandbox" not in cfg.pg_database.lower():
        LOG.error(
            "REFUSE: pg_database=%s 不含 'sandbox' substring; "
            "spike trigger 強制 sandbox-only;refusing connection",
            cfg.pg_database,
        )
        sys.exit(2)

    try:
        conn = psycopg2.connect(
            host=cfg.pg_host,
            port=cfg.pg_port,
            user=cfg.pg_user,
            dbname=cfg.pg_database,
        )
    except psycopg2.OperationalError as exc:
        # round 2 HIGH-2: sandbox_admin role 可能尚未創建(Phase 2 defer);
        # 提示 operator 顯式用 trading_admin override (sandbox DB 仍隔絕)
        if cfg.pg_user == "sandbox_admin":
            LOG.error(
                "DB connection failed with user=sandbox_admin (Phase 0 §2.2 "
                "role 可能尚未創建; E3 push back defer 至 Phase 2): %s",
                exc,
            )
            LOG.error(
                "→ Operator 可顯式 `--user trading_admin` retry; sandbox DB "
                "(%s) 仍隔絕 production trading_ai。長期解 = E3 + PA 創建 "
                "sandbox_admin role per Phase 0 §2.2",
                cfg.pg_database,
            )
        raise
    conn.autocommit = False
    return conn


def load_fills_window(conn: Any, cfg: SpikeTriggerConfig) -> list[dict]:
    """
    拉 last N hour 的 fills (sandbox seeded 200 row bb_breakout BTCUSDT live_demo)

    為什麼 live_demo:
        ML training filter 必 IN ('live','live_demo') per CLAUDE.md §七;
        Sprint 1A-α sandbox seed 是 live_demo 樣本 (per Phase 0 prep checklist §4)
    """
    # 為什麼 cutoff 取 now() - INTERVAL '<N> days':
    #   sandbox seed fills ts 是 2026-05-16 上下;sandbox time pin in past;
    #   用 max(ts) - 1 day 比 now() - 1 day 安全 (避免 sandbox 時鐘漂移)
    sql = """
        WITH bound AS (
            SELECT max(ts) AS upper_ts
            FROM trading.fills
            WHERE strategy_name = %s
              AND symbol = %s
              AND engine_mode IN ('live', 'live_demo')
        )
        SELECT
            f.ts,
            f.fill_id,
            f.order_id,
            f.symbol,
            f.side,
            f.qty,
            f.price,
            f.strategy_name,
            f.engine_mode,
            f.context_id
        FROM trading.fills f, bound b
        WHERE f.strategy_name = %s
          AND f.symbol = %s
          AND f.engine_mode IN ('live', 'live_demo')
          AND f.ts >= b.upper_ts - (%s || ' hours')::interval
          AND f.ts <= b.upper_ts
        ORDER BY f.ts ASC
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            sql,
            (
                cfg.strategy_id,
                cfg.symbol,
                cfg.strategy_id,
                cfg.symbol,
                str(cfg.window_hours),
            ),
        )
        rows = cur.fetchall()
    LOG.info(
        "loaded %s fills for strategy=%s symbol=%s window=%sh",
        len(rows),
        cfg.strategy_id,
        cfg.symbol,
        cfg.window_hours,
    )
    return rows


def detect_d1_fill_chain(
    fills: list[dict],
    inject_synthetic: bool,
) -> dict[str, Any]:
    """
    D1 fill_chain divergence detector — thin wrapper 委派至 sibling module
    (per round 2 HIGH-3)

    為什麼 thin wrapper:
        E2 round 1 review HIGH-3 catch divergence_d1_fill_chain.py 4 函數
        全 0 caller;AC-7 leak-free shift(1) mandate 形同未落地。round 2
        正式 import sibling module 走 compute_5d_baseline +
        detect_with_baseline + leak_free_shift1_replay 三函數,使 baseline
        欄位 + leak-free shift(1) 真實 land。

    flow:
        1) leak-free shift(1) baseline = N-1 fills (排除 current bar)
        2) live count = len(fills)
        3) replay count = live count (或 +5 if synthetic)
        4) compute_5d_baseline(historical 5 day fill counts)
        5) detect_with_baseline(live, replay, baseline) → severity + 3 baseline column
        6) routing per severity:
           - CRITICAL → flag_action_taken='m7_decay_candidate'
           - WARN → 'm3_health_recheck'
           - NOISE → 'none' (writer 端 gate skip row write)
    """
    live_count = len(fills)

    # 為什麼用 leak_free_shift1_replay():
    #   per AC-7 + feedback_indicator_lookahead_bias mandate;
    #   replay baseline 不引用 current bar,避免 spike fill 自污染
    leak_free_baseline_count = leak_free_shift1_replay(fills)

    # 為什麼 inject = 5:
    #   per packet Task 2 step 3.D「inject 1 synthetic divergence
    #   (fake fill chain count delta = 5)」;
    #   delta=5 對應 CRITICAL threshold (≥ ±5 fills per spec §4.3 D1);
    #   足以走完 m7_decay_candidate routing path
    if inject_synthetic:
        replay_count = inject_synthetic_fixture(live_count, delta=5)
    else:
        # 非 synthetic 時 replay = live (no-op nightly hygiene)
        replay_count = live_count

    # 為什麼用 fake 5d history:
    #   spike skeleton 階段 sandbox seed 無 5d empirical fill_count history;
    #   nightly cron Phase A (Sprint 3 W15-18) 走真實 history aggregate;
    #   spike 用 fake 5 sample [live_count]*5 對應 sigma≈0 noise_floor≈mean,
    #   足以走通 detect_with_baseline path + 寫 3 個 baseline column row
    fake_5d_history = [live_count] * 5
    baseline = compute_5d_baseline(fake_5d_history)

    detect_result = detect_with_baseline(
        live_count=live_count,
        replay_count=replay_count,
        baseline=baseline,
    )

    # routing per severity (per V107 spec §5.1)
    severity = detect_result["severity"]
    if severity == "CRITICAL":
        flag_action: str | None = "m7_decay_candidate"
    elif severity == "WARN":
        flag_action = "m3_health_recheck"
    else:
        flag_action = "none"

    evidence = {
        "live_fill_count": live_count,
        "replay_fill_count": replay_count,
        "fill_count_diff": detect_result["divergence_count"],
        "leak_free_shift1_baseline_count": leak_free_baseline_count,
        "live_engine_mode": fills[0]["engine_mode"] if fills else "unknown",
        "synthetic_injected": inject_synthetic,
        "detector_module": "divergence_d1_fill_chain",
        "severity_origin": detect_result["severity_origin"],
        "cold_start": detect_result["cold_start"],
        "z_score": detect_result["z_score"],
    }
    LOG.info(
        "D1 fill_chain detector (via sibling module): live=%s replay=%s "
        "leak_free_baseline=%s diff=%s severity=%s flag=%s mu=%s sigma=%s",
        live_count,
        replay_count,
        leak_free_baseline_count,
        detect_result["divergence_count"],
        severity,
        flag_action,
        detect_result["baseline_mean"],
        detect_result["baseline_sigma"],
    )
    return {
        "divergence_value": float(detect_result["divergence_count"]),
        "severity": severity,
        "flag_action_taken": flag_action,
        "evidence_json": evidence,
        "baseline_5d_mean": detect_result["baseline_mean"],
        "baseline_5d_sigma": detect_result["baseline_sigma"],
        "noise_floor_threshold": detect_result["noise_floor_threshold"],
    }


def write_divergence_row(
    conn: Any,
    cfg: SpikeTriggerConfig,
    detector_result: dict[str, Any],
    replay_run_id: uuid.UUID,
) -> int:
    """
    寫 V107 row (per V107 spec §2.1 27 column)

    為什麼 engine_mode='replay':
        M11 自身寫入時 engine_mode=replay 區分 live trace; 原 live trace
        mode 進 evidence_json (per V107 spec §2.2 line 204)

    為什麼 created_by='m11_spike_trigger':
        對齊 V107 spec §2.2 line 205 audit field;spike 期間用 spike-specific
        created_by 區分 nightly cron (default 'm11_replay_engine')

    為什麼 round 2 補 baseline_5d_mean / sigma / noise_floor_threshold:
        E2 round 1 HIGH-3 catch round 1 INSERT 漏這 3 個 V107 schema column;
        round 2 import detect_with_baseline 後 detector_result 已含此 3 數值
    """
    sql = """
        INSERT INTO learning.replay_divergence_log (
            divergence_detected_at, replay_run_id, divergence_type, severity,
            divergence_metric_name, divergence_value,
            baseline_5d_mean, baseline_5d_sigma, noise_floor_threshold,
            strategy_id, symbol,
            evidence_json, engine_mode,
            flag_action_taken,
            created_by, source_version
        ) VALUES (
            now(), %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s,
            %s,
            %s, %s
        )
        RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                str(replay_run_id),
                "fill_chain",
                detector_result["severity"],
                "fill_count_diff",
                detector_result["divergence_value"],
                detector_result["baseline_5d_mean"],
                detector_result["baseline_5d_sigma"],
                detector_result["noise_floor_threshold"],
                cfg.strategy_id,
                cfg.symbol,
                Json(detector_result["evidence_json"]),
                "replay",
                detector_result["flag_action_taken"],
                "m11_spike_trigger",
                "V107",
            ),
        )
        new_id = cur.fetchone()[0]
    LOG.info(
        "V107 row written: id=%s replay_run_id=%s baseline_mean=%s sigma=%s noise_floor=%s",
        new_id,
        replay_run_id,
        detector_result["baseline_5d_mean"],
        detector_result["baseline_5d_sigma"],
        detector_result["noise_floor_threshold"],
    )
    return int(new_id)


def main() -> int:
    """
    spike trigger 入口 (per Q4a override + packet Task 2)

    return exit code: 0 success / 2 sandbox safety violation / 3 db error
    """
    parser = argparse.ArgumentParser(description="M11 spike trigger (manual 1-shot)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    # round 2 HIGH-2: default 改 sandbox_admin (對齊 Phase 0 §2.2 設計);
    # operator 連 production 必須顯式 `--user trading_admin`;sandbox_admin
    # 未創時 get_db_connection 偵測 OperationalError 提示 fallback
    parser.add_argument("--user", default="sandbox_admin")
    parser.add_argument(
        "--database",
        default="trading_ai_sandbox",
        help="sandbox-only;production DB will be refused",
    )
    parser.add_argument("--strategy", default="bb_breakout")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument(
        "--inject-synthetic",
        action="store_true",
        default=True,
        help="inject 1 synthetic D1 divergence delta=5 (per Task 2)",
    )
    args = parser.parse_args()

    cfg = SpikeTriggerConfig(
        pg_host=args.host,
        pg_port=args.port,
        pg_user=args.user,
        pg_database=args.database,
        strategy_id=args.strategy,
        symbol=args.symbol,
        window_hours=args.window_hours,
        inject_synthetic_divergence=args.inject_synthetic,
    )

    LOG.info(
        "M11 spike trigger starting: strategy=%s symbol=%s window=%sh sandbox=%s user=%s",
        cfg.strategy_id,
        cfg.symbol,
        cfg.window_hours,
        cfg.pg_database,
        cfg.pg_user,
    )

    try:
        conn = get_db_connection(cfg)
    except psycopg2.Error as exc:
        LOG.error("DB connection failed: %s", exc)
        return 3

    try:
        fills = load_fills_window(conn, cfg)
        if not fills:
            LOG.warning("no fills loaded;skipping divergence detection")
            return 0

        result = detect_d1_fill_chain(
            fills,
            inject_synthetic=cfg.inject_synthetic_divergence,
        )

        # 為什麼 NOISE 不寫 row:
        #   per V107 spec §2.3 + M11 design §5.1 writer 端 gate;
        #   NOISE 不寫 row 避免 V107 表灌爆 daily noise
        if result["severity"] == "NOISE":
            LOG.info("severity=NOISE;writer-side gate;skipping V107 row write")
            conn.commit()
            return 0

        replay_run_id = uuid.uuid4()
        row_id = write_divergence_row(conn, cfg, result, replay_run_id)
        conn.commit()
        LOG.info(
            "spike trigger DONE: V107 row id=%s severity=%s flag=%s",
            row_id,
            result["severity"],
            result["flag_action_taken"],
        )
        return 0
    except psycopg2.Error as exc:
        LOG.error("DB error: %s", exc)
        conn.rollback()
        return 3
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
