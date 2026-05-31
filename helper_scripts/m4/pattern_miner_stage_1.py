"""
MODULE_NOTE
模塊用途：M4 Pattern Miner Stage 1 主 entry — cron 呼 / CLI。

per W1-B spec §5.2：
   1. Source ingestion（4 PG source + 1 stub）
   2. Statistical algorithm（Rust hot-path or Python fallback）
   3. 6 attribute enforcement gate
   4. Leakage scan
   5. DRAFT writeback（V100 base + V103 EXTEND 6 column）
   6. Notification

CLI usage：
   python3 -m helper_scripts.m4.pattern_miner_stage_1 --dry-run
   python3 -m helper_scripts.m4.pattern_miner_stage_1 --no-dry-run

不變量：
   - --dry-run 不連 PG / 不寫 PG（per W1-B spec AC-S2-B-2）
   - --no-dry-run 會讀 PG source；DRAFT writeback 必須額外帶 --enable-writeback
     且每 row 提供一個真實 decision_lease_draft_id UUID
   - Sprint 2 cron 預設 disabled（per W1-B spec §12 dispatch checklist）

Mac scaffold 階段：本 entry 在 Mac 上跑 --dry-run 不會連 PG；production 路徑
   fail-closed 要求 operator 提供真實 PG DSN 與 Decision Lease UUID。
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

# 為什麼 module-level logger：CLAUDE.md §七 安全代碼規範 logger %s format
# (不用 f-string 進 logger.info)；caller 必經 %-style placeholder。
logger = logging.getLogger(__name__)


def run_stage_1(
    dry_run: bool = True,
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"),
    lookback_days: int = 90,
    conn: Any | None = None,
    enable_writeback: bool = False,
    decision_lease_draft_ids: tuple[uuid.UUID | str, ...] = (),
    max_drafts: int = 3,
    engine_mode: str = "live_demo",
) -> dict:
    """Execute M4 Pattern Miner Stage 1 batch.

    Returns: dict 含 batch summary（n_drafts, n_preregistered, n_exploratory）。

    為什麼 dry-run default True：scaffold 階段必須 explicit opt-in 寫 PG；
    避免 Mac local run 誤觸 production PG（per CLAUDE.md §六）。
    """
    started_at = datetime.now(tz=timezone.utc)
    logger.info(
        "M4 Stage 1 start: dry_run=%s symbols=%s lookback=%dd",
        dry_run,
        symbols,
        lookback_days,
    )

    from helper_scripts.m4.sources.kline_loader import build_kline_query
    from helper_scripts.m4.sources.fills_loader import build_fills_query
    from helper_scripts.m4.sources.liquidations_loader import build_liquidations_query
    from helper_scripts.m4.sources.funding_loader import build_funding_query
    from helper_scripts.m4.sources.token_unlocks_stub import TokenUnlocksNotImplementedError

    kline_sql, kline_params = build_kline_query(symbols, lookback_days=lookback_days)
    fills_sql, fills_params = build_fills_query(lookback_days=lookback_days)
    liq_sql, liq_params = build_liquidations_query(lookback_days=lookback_days)
    funding_sql, funding_params = build_funding_query(lookback_days=lookback_days)

    logger.info(
        "Source query built: 4 PG queries (kline/fills/liquidations/funding) + 1 stub (token_unlocks)"
    )

    # 確認 stub fail-loud raise — 不靜默通過 5/5 source（per AC-S2-B-1 教訓）。
    try:
        from helper_scripts.m4.sources.token_unlocks_stub import load_token_unlocks
        load_token_unlocks()
        logger.warning("token_unlocks stub did NOT raise — 違反 Sprint 2 spec")
    except TokenUnlocksNotImplementedError:
        logger.info("token_unlocks stub correctly raised NotImplementedError (Sprint 3+ defer)")

    if dry_run:
        completed_at = datetime.now(tz=timezone.utc)
        summary = {
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "dry_run": dry_run,
            "symbols": list(symbols),
            "lookback_days": lookback_days,
            "n_source_queries_built": 4,
            "n_source_stubs": 1,
            "n_drafts": 0,  # dry-run 不連 PG / 不真實計算 DRAFT
            "n_preregistered": 0,
            "n_exploratory": 0,
        }
        logger.info("M4 Stage 1 complete: %s", summary)
        return summary

    opened_conn = None
    if conn is None:
        opened_conn = _connect_pg()
        conn = opened_conn

    try:
        from helper_scripts.m4.stage1_production_runner import run_production_stage1

        summary = run_production_stage1(
            conn=conn,
            symbols=symbols,
            lookback_days=lookback_days,
            max_drafts=max_drafts,
            enable_writeback=enable_writeback,
            decision_lease_draft_ids=decision_lease_draft_ids,
            engine_mode=engine_mode,
        )
        logger.info("M4 Stage 1 complete: %s", summary)
        return summary
    finally:
        if opened_conn is not None:
            opened_conn.close()


def _connect_pg() -> Any:
    """Open a psycopg2 connection from env, fail-loud if no DSN is configured."""
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError(
            "psycopg2 is required for M4 --no-dry-run production source reads"
        ) from exc

    dsn = os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if dsn:
        return psycopg2.connect(dsn, application_name="openclaw_m4_stage1")

    required = {
        "host": os.environ.get("POSTGRES_HOST"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB"),
        "user": os.environ.get("POSTGRES_USER"),
    }
    missing = [key for key, value in required.items() if not value and key != "port"]
    if missing:
        raise RuntimeError(
            "missing PG connection env for M4 --no-dry-run: " + ", ".join(missing)
        )
    password = os.environ.get("POSTGRES_PASSWORD")
    if password:
        required["password"] = password
    return psycopg2.connect(**required, application_name="openclaw_m4_stage1")


def main() -> int:
    """CLI entry — cron callable。"""
    parser = argparse.ArgumentParser(description="M4 Pattern Miner Stage 1")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="不寫 PG，只做 source query build + module import verify",
    )
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="真實 production 讀數模式；預設只讀 source + 計算，不寫 DRAFT",
    )
    parser.add_argument(
        "--enable-writeback",
        action="store_true",
        help="允許 INSERT learning.hypotheses；必須提供每 row 一個 Decision Lease UUID",
    )
    parser.add_argument(
        "--decision-lease-draft-id",
        action="append",
        default=[],
        help="預先取得的 Decision Lease UUID；writeback 每個 DRAFT row 需要一個",
    )
    parser.add_argument(
        "--max-drafts",
        type=int,
        default=3,
        help="最多選取/寫入的候選 DRAFT 數",
    )
    parser.add_argument(
        "--engine-mode",
        choices=("live", "live_demo"),
        default="live_demo",
        help="寫入 learning.hypotheses 的 engine_mode（只允許 live/live_demo）",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=90,
        help="Source ingestion 回看天數（baseline 90）",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="BTCUSDT,ETHUSDT",
        help="逗號分隔 symbol list（baseline BTCUSDT,ETHUSDT）",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    symbols = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
    try:
        decision_lease_ids = tuple(
            uuid.UUID(value) for value in args.decision_lease_draft_id
        )
        summary = run_stage_1(
            dry_run=args.dry_run,
            symbols=symbols,
            lookback_days=args.lookback_days,
            enable_writeback=args.enable_writeback,
            decision_lease_draft_ids=decision_lease_ids,
            max_drafts=args.max_drafts,
            engine_mode=args.engine_mode,
        )
    except (RuntimeError, ValueError) as exc:
        logger.error("M4 Stage 1 failed: %s", exc)
        return 2
    logger.info("Stage 1 batch summary: %s", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
