"""
MODULE_NOTE
模塊用途：M4 Pattern Miner Stage 1 主 entry — cron 呼 / CLI dry-run。

per W1-B spec §5.2：
   1. Source ingestion（4 PG source + 1 stub）
   2. Statistical algorithm（Rust hot-path or Python fallback）
   3. 6 attribute enforcement gate
   4. Leakage scan
   5. DRAFT writeback（V100 base + V103 EXTEND 6 column）
   6. Notification

CLI usage：
   python3 -m helper_scripts.m4.pattern_miner_stage_1 --dry-run

不變量：
   - --dry-run 不寫 PG（per W1-B spec AC-S2-B-2）
   - Sprint 2 cron 預設 disabled（per W1-B spec §12 dispatch checklist）

Mac scaffold 階段：本 entry 在 Mac 上跑 --dry-run 不會連 PG；真實 production 跑
   由 Linux runtime 接 cron after W2-D MIT 接通 GovernanceHub IPC。
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

# 為什麼 module-level logger：CLAUDE.md §七 安全代碼規範 logger %s format
# (不用 f-string 進 logger.info)；caller 必經 %-style placeholder。
logger = logging.getLogger(__name__)


def run_stage_1(
    dry_run: bool = True,
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"),
    lookback_days: int = 90,
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

    # Sprint 2 scaffold：本 entry 只跑 source query build + verify Python module 可 import。
    # 真實 ingestion + statistical + writeback 由 W2-D MIT 接 cron 時 wire production。
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

    completed_at = datetime.now(tz=timezone.utc)
    summary = {
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "dry_run": dry_run,
        "symbols": list(symbols),
        "lookback_days": lookback_days,
        "n_source_queries_built": 4,
        "n_source_stubs": 1,
        "n_drafts": 0,  # scaffold 階段不真實計算 DRAFT
        "n_preregistered": 0,
        "n_exploratory": 0,
    }
    logger.info("M4 Stage 1 complete: %s", summary)
    return summary


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
        help="真實 production 模式（Linux runtime only — scaffold 不支援）",
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

    if not args.dry_run:
        # Scaffold 階段 fail-loud：禁 non-dry-run 在 Mac 上跑（per CLAUDE.md §六 Mac
        # 不跑真實 PG / engine）。Production 走 Linux runtime cron。
        logger.error(
            "scaffold 階段不支援 --no-dry-run；Production 真實 batch 由 Linux runtime "
            "cron 接 W2-D MIT wire-up 後執行"
        )
        return 2

    symbols = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
    summary = run_stage_1(
        dry_run=args.dry_run,
        symbols=symbols,
        lookback_days=args.lookback_days,
    )
    logger.info("Stage 1 batch summary: %s", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
