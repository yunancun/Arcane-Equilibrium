#!/usr/bin/env python3
"""
OpenClaw DB Fresh-Start Reset Script
開發噪音數據清理 / 重置系統經驗為乾淨起點

MODULE_NOTE (EN):
    Clears all development-phase "experience data" (fills, orders, intents,
    signals, agent messages, learning state) while preserving objective market
    data (klines, funding rates, orderbook snapshots, regime snapshots, news).

    Three modes:
      --report-only  Print row counts only (default; safe to run any time)
      --dry-run      Print what WOULD be truncated, no DB writes
      --execute      Actually perform the reset (requires --confirm)

    LinUCB bandit state is archived to learning.linucb_state_archive before
    any wipe, so warm-start data is recoverable if needed.

MODULE_NOTE (中):
    清除所有開發階段「經驗數據」（fills / orders / intents / signals /
    agent messages / 學習狀態），保留客觀市場數據（klines / funding rates /
    ob snapshots / regime snapshots / news）。

    三種模式：
      --report-only  僅顯示 row 數（默認；隨時可安全執行）
      --dry-run      顯示「將被清除的表」，不寫 DB
      --execute      真實執行（需搭配 --confirm）

    執行前會把 LinUCB bandit 狀態存入 learning.linucb_state_archive，
    如需恢復仍可找回 warm-start 數據。

Usage / 用法:
    # 需要先激活 psycopg2 所在的 venv / Must activate the venv with psycopg2:
    source program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/activate

    # 1. 查看各表行數（無任何副作用）
    # Uses POSTGRES_* vars from settings/environment_files/basic_system_services.env
    source settings/environment_files/basic_system_services.env
    python3 helper_scripts/db/fresh_start_reset.py

    # 2. 預覽將被清除的內容
    python3 helper_scripts/db/fresh_start_reset.py --dry-run

    # 3. 真實執行（填入今天日期作為確認碼）
    python3 helper_scripts/db/fresh_start_reset.py \\
        --execute --confirm "<print expected code from previous mismatch message>"

    # Or provide DSN directly:
    DSN=postgresql://user:pass@127.0.0.1/trading_ai python3 helper_scripts/db/fresh_start_reset.py
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fresh_start_reset")

# ─────────────────────────────────────────────────────────────────────────────
# Table classification
# 表分類
# ─────────────────────────────────────────────────────────────────────────────

# Tables to PRESERVE — objective market data, schema metadata, audit trails
# 保留表 — 客觀市場數據、schema 元數據、審計記錄
PRESERVE_TABLES: list[str] = [
    # market.* — objective exchange data; safe to keep forever
    "market.market_tickers",
    "market.ob_snapshots",
    "market.trade_agg_1m",
    "market.klines",
    "market.funding_rates",
    "market.open_interest",
    "market.long_short_ratio",
    "market.liquidations",
    "market.regime_snapshots",
    "market.regime_transitions",
    "market.news_signals",
    # features.versions — feature schema definitions (not experience data)
    "features.versions",
    # learning — model artifacts + audit trails
    "learning.model_registry",
    "learning.promotion_pipeline",
    "learning.linucb_state_archive",   # rollback archive; always kept
    "learning.linucb_migrations",      # migration audit log; always kept
    "learning.ai_budget_config",       # re-seeded after wipe
]

# Tables to WIPE — system/agent experience data accumulated during development
# 清除表 — 開發過程積累的系統/Agent 經驗數據
WIPE_TABLES: list[tuple[str, str]] = [
    # ── trading schema ──────────────────────────────────────────────────────
    ("trading.signals",                   "signal log (strategy output)"),
    ("trading.intents",                   "trade intents (pre-order)"),
    ("trading.risk_verdicts",             "risk guardian verdicts"),
    ("trading.decision_context_snapshots","decision context snapshots"),
    ("trading.decision_outcomes",         "post-hoc return attribution"),
    ("trading.orders",                    "order log"),
    ("trading.order_state_changes",       "order state transitions"),
    ("trading.fills",                     "execution fills"),
    ("trading.position_snapshots",        "position state snapshots"),
    # ── agent schema ────────────────────────────────────────────────────────
    ("agent.messages",                    "inter-agent message log"),
    ("agent.ai_invocations",              "AI call log + cost tracking"),
    ("agent.state_changes",               "agent state transitions"),
    # ── learning schema (experience data only; model artifacts preserved) ──
    ("learning.rl_transitions",           "RL episode transitions"),
    ("learning.ml_parameter_suggestions", "parameter suggestion log"),
    ("learning.bayesian_posteriors",      "Thompson Sampling posteriors"),
    ("learning.cpcv_results",             "cross-validation results"),
    ("learning.james_stein_estimates",    "JS shrinkage estimates"),
    ("learning.symbol_clusters",          "k-means cluster assignments"),
    ("learning.teacher_directives",       "Claude teacher directives"),
    ("learning.directive_executions",     "directive execution tracking"),
    ("learning.experiment_ledger",        "hypothesis experiment log"),
    ("learning.foundation_model_features","DL-3 foundation model outputs"),
    ("learning.weekly_review_log",        "operator weekly review log"),
    ("learning.ai_usage_log",             "AI cost usage log"),
    # ── features schema ─────────────────────────────────────────────────────
    ("features.online_latest",            "online feature cache (auto-repopulated)"),
    # ── observability schema ─────────────────────────────────────────────────
    ("observability.scorer_predictions",  "model score log"),
    ("observability.model_performance",   "rolling model performance"),
    ("observability.drift_events",        "feature drift events"),
    ("observability.feature_baselines",   "feature distribution baselines"),
    ("observability.data_quality_events", "data quality events"),
    ("observability.engine_events",       "engine lifecycle audit log"),
    # ── risk schema ──────────────────────────────────────────────────────────
    ("risk.black_swan_events",            "black swan detection events"),
    ("risk.black_swan_votes",             "black swan vote log"),
    ("risk.correlation_pairs",            "correlation matrix snapshots"),
]

# linucb_state is archived then wiped (special handling)
# linucb_state 先歸檔再清除
LINUCB_TABLE = "learning.linucb_state"

# Default AI budget config rows re-inserted after wipe
# 清除後重新插入默認 AI 預算配置
AI_BUDGET_DEFAULTS = [
    ("local_total",       100.0),
    ("platform_hard_cap", 150.0),
    ("agent_teacher",      60.0),
    ("agent_analyst",      30.0),
    ("agent_reserve",      10.0),
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _try_import_psycopg2():
    """Import psycopg2 or return None with warning.
    嘗試 import psycopg2，失敗時回傳 None 並記錄警告。"""
    try:
        import psycopg2
        return psycopg2
    except ImportError:
        logger.error(
            "psycopg2 not installed. Install with: pip install psycopg2-binary"
        )
        return None


def _load_env_file(path: str) -> dict[str, str]:
    """Parse a KEY=VALUE env file (handles unquoted values with special chars).
    解析 KEY=VALUE 格式的 env 文件（正確處理含括號等特殊字符的未引號值）。"""
    result: dict[str, str] = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                # Strip optional surrounding quotes (single or double)
                # 去除可選的引號包裹
                if (val.startswith('"') and val.endswith('"')) or \
                   (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                result[key] = val
    except OSError:
        pass
    return result


def _resolve_dsn(env_file: Optional[str] = None) -> Optional[str]:
    """Resolve database DSN from env vars or env file, in priority order.

    優先級（高→低）：
      1. DSN env var (direct connection string)
      2. OPENCLAW_DATABASE_URL env var
      3. --env-file 指定的文件中的 POSTGRES_* 變量
      4. 自動查找 settings/environment_files/basic_system_services.env
      5. os.environ 中的 POSTGRES_* 變量

    Priority (high → low):
      1. DSN env var
      2. OPENCLAW_DATABASE_URL env var
      3. POSTGRES_* vars from --env-file
      4. Auto-detect basic_system_services.env relative to script location
      5. POSTGRES_* vars from os.environ
    """
    if val := os.environ.get("DSN") or os.environ.get("OPENCLAW_DATABASE_URL"):
        return val

    # Build overlay from env file (handles special chars in password)
    # 從 env 文件構建覆蓋（正確處理密碼中的特殊字符）
    overlay: dict[str, str] = {}
    if env_file:
        overlay = _load_env_file(env_file)
    else:
        # Auto-detect relative to this script / 相對腳本自動探測
        script_dir = os.path.dirname(os.path.abspath(__file__))
        srv_root = os.path.dirname(os.path.dirname(script_dir))
        candidates = [
            os.path.join(srv_root, "settings", "environment_files", "basic_system_services.env"),
            os.path.join(script_dir, "..", "..", "settings", "environment_files", "basic_system_services.env"),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                overlay = _load_env_file(candidate)
                logger.debug("Loaded env from: %s", candidate)
                break

    env = {**os.environ, **overlay}
    user = env.get("POSTGRES_USER")
    password = env.get("POSTGRES_PASSWORD")
    db = env.get("POSTGRES_DB")
    port = env.get("POSTGRES_PORT", "5432")
    host = env.get("POSTGRES_HOST", "127.0.0.1")

    if user and password and db:
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    return None


def _build_confirmation_code(dsn: str) -> str:
    """Build execute confirmation code with DB/environment fingerprint.
    生成帶 DB/環境指紋的執行確認碼。
    """
    today_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    parsed = urlparse(dsn)
    host = parsed.hostname or "unknown_host"
    port = str(parsed.port or 5432)
    db = (parsed.path or "/unknown_db").lstrip("/") or "unknown_db"
    user = parsed.username or "unknown_user"
    env = os.environ.get("OPENCLAW_ENV", "unspecified")
    raw_fp = f"{host}_{port}_{db}_{user}_{env}"
    fp = re.sub(r"[^A-Za-z0-9_]+", "_", raw_fp).strip("_")
    return f"FRESH_START_{today_str}_{fp}"


def _connect(dsn: Optional[str]):
    """Connect to PostgreSQL. Exit on failure.
    連接 PostgreSQL；失敗時終止程序。"""
    psycopg2 = _try_import_psycopg2()
    if psycopg2 is None:
        sys.exit(1)
    if not dsn:
        logger.error(
            "No DSN provided. Set DSN or OPENCLAW_DATABASE_URL env variable.\n"
            "Example: DSN=postgresql://trading_admin:PASS@127.0.0.1/trading_ai"
        )
        sys.exit(1)
    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = False
        return conn
    except Exception as exc:
        logger.error("Connection failed: %s", exc)
        sys.exit(1)


def _row_count(cur, table: str) -> int:
    """Return approximate row count for a table (uses reltuples for speed).
    返回近似 row 數（使用 reltuples 加速；精確數在 VACUUM 後更新）。"""
    schema, tname = table.split(".", 1)
    try:
        cur.execute(
            """
            SELECT COALESCE(reltuples::bigint, 0)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND c.relname = %s
            """,
            (schema, tname),
        )
        row = cur.fetchone()
        return int(row[0]) if row else -1
    except Exception:
        return -1


def _exact_count(cur, table: str) -> int:
    """Return exact row count (slower; used for report display).
    返回精確 row 數（較慢；僅用於報告顯示）。"""
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")  # nosec — table names are static
        row = cur.fetchone()
        return int(row[0]) if row else -1
    except Exception:
        return -1


# ─────────────────────────────────────────────────────────────────────────────
# Core operations
# 核心操作
# ─────────────────────────────────────────────────────────────────────────────

def report_row_counts(conn) -> None:
    """Print current row counts for all managed tables.
    顯示所有受管理表的當前 row 數。"""
    with conn.cursor() as cur:
        print("\n" + "═" * 72)
        print("  OpenClaw DB Row Count Report")
        print(f"  Generated: {datetime.now(timezone.utc).isoformat()}")
        print("═" * 72)

        print("\n📊 PRESERVE (market + metadata) — NOT touched:")
        for tbl in PRESERVE_TABLES:
            n = _exact_count(cur, tbl)
            label = f"{n:>10,}" if n >= 0 else "      N/A "
            print(f"  {label}  {tbl}")

        print(f"\n  {'':>10}  {LINUCB_TABLE}  [archive-before-wipe]")
        n = _exact_count(cur, LINUCB_TABLE)
        print(f"  {n:>10,}  {LINUCB_TABLE}")

        print("\n🗑️  WIPE — system/agent experience data:")
        total_wipe = 0
        for tbl, desc in WIPE_TABLES:
            n = _exact_count(cur, tbl)
            if n >= 0:
                total_wipe += n
            label = f"{n:>10,}" if n >= 0 else "      N/A "
            print(f"  {label}  {tbl:<50}  # {desc}")

        print(f"\n  {'TOTAL':>10}  rows to wipe: {total_wipe:,}")
        print("═" * 72 + "\n")


def archive_linucb_state(cur, dry_run: bool) -> int:
    """Copy learning.linucb_state rows to linucb_state_archive before wipe.
    清除前將 learning.linucb_state 備份至 linucb_state_archive。"""
    cur.execute(f"SELECT COUNT(*) FROM {LINUCB_TABLE}")
    count = cur.fetchone()[0]
    if count == 0:
        logger.info("linucb_state is empty — nothing to archive.")
        return 0

    ts_now = datetime.now(timezone.utc)
    reason = "fresh_start_reset"
    if dry_run:
        logger.info(
            "[DRY-RUN] Would archive %d linucb_state rows (reason=%s)", count, reason
        )
        return count

    cur.execute(
        """
        INSERT INTO learning.linucb_state_archive
            (arm_id, parent_arm_id, strategy_name, symbol, timeframe,
             feature_schema_hash, inheritance_gamma, n_pulls, alpha,
             A_matrix_flat, b_vector, last_updated_at, archived_ts, archive_reason)
        SELECT
            arm_id, parent_arm_id, strategy_name, symbol, timeframe,
            feature_schema_hash, inheritance_gamma, n_pulls, alpha,
            A_matrix_flat, b_vector, last_updated_at,
            %s AS archived_ts, %s AS archive_reason
        FROM learning.linucb_state
        ON CONFLICT DO NOTHING
        """,
        (ts_now, reason),
    )
    archived = cur.rowcount
    logger.info("Archived %d linucb_state rows → linucb_state_archive.", archived)
    return archived


def truncate_tables(cur, dry_run: bool) -> dict[str, int]:
    """Truncate all WIPE_TABLES + linucb_state. Returns counts before truncate.
    清除所有 WIPE_TABLES + linucb_state。返回截斷前的 row 數。"""
    counts: dict[str, int] = {}

    all_tables = [(LINUCB_TABLE, "linucb bandit state (archived above)")] + list(WIPE_TABLES)

    for tbl, desc in all_tables:
        n = _exact_count(cur, tbl)
        counts[tbl] = n
        if n < 0:
            logger.info("SKIPPED missing table %s  # %s", tbl, desc)
            continue
        if dry_run:
            logger.info("[DRY-RUN] Would TRUNCATE %s (%s rows)  # %s", tbl, n, desc)
        else:
            try:
                cur.execute(f"TRUNCATE {tbl} RESTART IDENTITY CASCADE")  # nosec — static names
                logger.info("TRUNCATED %s (%s rows removed)  # %s", tbl, n, desc)
            except Exception as exc:
                logger.error("Failed to truncate %s: %s", tbl, exc)
                raise

    return counts


def reseed_ai_budget_config(cur, dry_run: bool) -> None:
    """Re-insert default rows into learning.ai_budget_config after truncate.
    截斷後重新插入 learning.ai_budget_config 默認行。"""
    if dry_run:
        logger.info("[DRY-RUN] Would re-seed learning.ai_budget_config with defaults.")
        return

    cur.execute("SELECT COUNT(*) FROM learning.ai_budget_config")
    if cur.fetchone()[0] == 0:
        for scope, monthly_usd in AI_BUDGET_DEFAULTS:
            cur.execute(
                """
                INSERT INTO learning.ai_budget_config (scope, monthly_usd, updated_by)
                VALUES (%s, %s, 'fresh_start_reset')
                ON CONFLICT (scope) DO NOTHING
                """,
                (scope, monthly_usd),
            )
        logger.info(
            "Re-seeded %d default rows into learning.ai_budget_config.",
            len(AI_BUDGET_DEFAULTS),
        )
    else:
        logger.info(
            "learning.ai_budget_config already has rows — skipping re-seed."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OpenClaw DB Fresh-Start Reset — wipe dev-noise experience data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples / 示例:
  # Show row counts only (safe)
  DSN=postgresql://... python3 helper_scripts/db/fresh_start_reset.py

  # Preview what would be wiped
  DSN=postgresql://... python3 helper_scripts/db/fresh_start_reset.py --dry-run

  # Execute reset (fill in today's date as confirmation code)
  DSN=postgresql://... python3 helper_scripts/db/fresh_start_reset.py \\
      --execute --confirm "<expected_fingerprint_code>"
        """,
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        default=False,
        help="Print row counts only (default behavior)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be truncated without writing",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually perform the reset (requires --confirm)",
    )
    parser.add_argument(
        "--confirm",
        type=str,
        default="",
        help=(
            "Confirmation code required with --execute. "
            "Format is DSN/environment fingerprinted and printed on mismatch."
        ),
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Path to KEY=VALUE env file for POSTGRES_* vars (auto-detected if not set)",
    )
    args = parser.parse_args()

    # Determine mode / 確定模式
    if args.execute:
        mode = "execute"
    elif args.dry_run:
        mode = "dry_run"
    else:
        mode = "report_only"

    dsn = _resolve_dsn(env_file=args.env_file)
    # Validate confirmation for execute mode / 驗證 execute 模式的確認碼
    if mode == "execute":
        if not dsn:
            logger.error("No DSN available for execute mode fingerprint check.")
            sys.exit(1)
        expected = _build_confirmation_code(dsn)
        if args.confirm != expected:
            logger.error(
                "Confirmation code mismatch.\n"
                "  Provided:  %r\n"
                "  Expected:  %r\n"
                "This guard binds destructive reset to the target DB/environment.\n"
                "Re-run with --confirm %r",
                args.confirm,
                expected,
                expected,
            )
            sys.exit(1)
        logger.warning(
            "⚠️  EXECUTE MODE: This will permanently delete all experience data.\n"
            "   Market data (klines, funding rates, etc.) will be preserved.\n"
            "   LinUCB state will be archived before deletion.\n"
            "   Proceeding in 3 seconds..."
        )
        import time
        time.sleep(3)

    conn = _connect(dsn)

    try:
        with conn.cursor() as cur:
            # Always print row counts first / 始終先顯示 row 數
            report_row_counts(conn)

            if mode == "report_only":
                logger.info("Report-only mode. Use --dry-run or --execute to proceed.")
                return

            is_dry = mode == "dry_run"

            print("\n" + ("─" * 72))
            print(f"  Mode: {'DRY RUN (no changes)' if is_dry else '🔴 EXECUTE — writing to DB'}")
            print("─" * 72 + "\n")

            # Step 1: Archive LinUCB state / 步驟1：歸檔 LinUCB 狀態
            logger.info("Step 1/3: Archive LinUCB bandit state...")
            archive_linucb_state(cur, dry_run=is_dry)

            # Step 2: Truncate all experience tables / 步驟2：清除所有經驗表
            logger.info("Step 2/3: Truncating experience tables...")
            counts = truncate_tables(cur, dry_run=is_dry)

            # Step 3: Re-seed ai_budget_config / 步驟3：重置 AI 預算配置
            logger.info("Step 3/3: Re-seeding ai_budget_config defaults...")
            reseed_ai_budget_config(cur, dry_run=is_dry)

            if not is_dry:
                conn.commit()
                total_removed = sum(v for v in counts.values() if v >= 0)
                logger.info(
                    "✅ Fresh-start reset complete. %d rows removed across %d tables.",
                    total_removed,
                    len(counts),
                )
                logger.info(
                    "Market data preserved. System will accumulate clean experience "
                    "data from this point forward."
                )
            else:
                conn.rollback()
                logger.info(
                    "✅ Dry-run complete. No changes made. Re-run with --execute to proceed."
                )

    except Exception as exc:
        conn.rollback()
        logger.error("Reset failed, rolled back: %s", exc)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
