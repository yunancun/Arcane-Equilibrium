#!/usr/bin/env python3
"""FND-2 PIT universe builder CLI 編排。

MODULE_NOTE:
  模塊用途：FND-2 builder 的 CLI 入口。parse args（run_id/asof/window/cutoff）→
    data_loader 唯讀載入 lifecycle → builder.build_universe → artifact.write_all →
    seed regression 比對 → 印 summary。**無隱式 now()**（窗口為顯式參數，contract §1）。
  主要函數：``main`` / ``run_build`` / ``compute_seed_regression``。
  CLI 範例（OQ-5 PM 裁決窗）：
    python3 -m fnd2_pit_universe.harness \\
      --run-id fnd2_18mo_$(date +%Y%m%dT%H%M%SZ) \\
      --asof 2026-06-03T00:00:00Z --window-start 2024-06-03T00:00:00Z \\
      --window-end 2026-06-03T00:00:00Z --cutoff 2026-06-02T00:00:00Z
  硬邊界：read-only PG；0 DB write；artifact 寫本地檔系統（OPENCLAW_DATA_DIR）。
    exit 0 = 成功；非零 = builder/載入/IO 失敗（fail-loud，不吞）。seed drift **非
    fail**（須解釋，contract §7）；survivor_rejection_status=FAIL 才是真失敗信號。
  依賴：本 package 內部模塊 + 標準庫。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import socket
import sys
from pathlib import Path
from typing import Optional

# 支援兩種執行方式：(a) python3 -m fnd2_pit_universe.harness（package 相對 import）；
# (b) 直接執行檔案路徑（research/ 非 package，補 sys.path 後絕對 import）。
try:
    from .builder import WindowSpec, build_universe
    from .data_loader import load_lifecycles
    from . import artifact as artifact_mod
    from .cohorts import CORE25_PINNED
except ImportError:  # pragma: no cover - 直接執行檔案路徑時
    _here = Path(__file__).resolve()
    _research = _here.parents[1]  # .../helper_scripts/research
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from fnd2_pit_universe.builder import WindowSpec, build_universe  # type: ignore
    from fnd2_pit_universe.data_loader import load_lifecycles  # type: ignore
    from fnd2_pit_universe import artifact as artifact_mod  # type: ignore
    from fnd2_pit_universe.cohorts import CORE25_PINNED  # type: ignore


# 預設 seed CSV（contract §1 regression check）。
_DEFAULT_SEED_REL = (
    "docs/CCAgentWorkSpace/MIT/workspace/reports/"
    "2026-05-31--s1_w1_s1_survivorship_universe_18mo_usdt_perp.csv"
)
_SEED_SHA256 = "fbf14a3f1fb52fd0e963ab3560323e0cc11cbb7e4f730439c722cec7e2364c23"

# universe_sources（manifest PIT gate）。symbol_universe_snapshots 必含；scanner /
# market_tickers 為 overlap / tier 排序源（缺表時不入）。
_PRIMARY_SOURCE = "market.symbol_universe_snapshots"


def _parse_utc(s: str) -> dt.datetime:
    """解析 ISO8601 UTC 時間（接受 ...Z 或 +00:00）。"""
    s2 = s.strip()
    if s2.endswith("Z"):
        s2 = s2[:-1] + "+00:00"
    d = dt.datetime.fromisoformat(s2)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def _repo_root() -> Path:
    """.../srv（harness 在 srv/helper_scripts/research/fnd2_pit_universe/）。"""
    return Path(__file__).resolve().parents[3]


def compute_seed_regression(
    rows: list,
    summary: dict,
    *,
    seed_path: Optional[Path],
) -> dict:
    """seed regression（contract §7）：載入 seed CSV 比對 count / tier，解釋 drift。

    drift **非 fail**——須解釋（new listings + new delistings since seed + tier 命名
    分類法差異）。drift 量級異常（built << seed，疑似 survivor truncation）才是警訊，
    但裁決留給 E2/MIT；本函數只產證據。
    """
    out: dict = {
        "seed_path": (str(seed_path) if seed_path else None),
        "seed_present": False,
        "seed_csv_digest": None,
        "seed_sha256_expected": _SEED_SHA256,
        "seed_sha256_match": None,
        "seed_row_count": None,
        "built_row_count": summary["included_count"],
        "drift_explanation": None,
    }
    if not seed_path or not seed_path.exists():
        out["drift_explanation"] = "seed_csv_absent: skipped count comparison"
        return out

    digest = hashlib.sha256(seed_path.read_bytes()).hexdigest()
    out["seed_present"] = True
    out["seed_csv_digest"] = digest
    out["seed_sha256_match"] = (digest == _SEED_SHA256)

    seed_symbols = set()
    seed_tier_counts: dict = {}
    seed_seen_delisted = 0
    with open(seed_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            sym = (r.get("symbol") or "").strip()
            if not sym:
                continue
            seed_symbols.add(sym)
            tier = (r.get("recommended_tier") or "").strip()
            seed_tier_counts[tier] = seed_tier_counts.get(tier, 0) + 1
            if (r.get("seen_delisted") or "").strip().lower() in ("t", "true", "1"):
                seed_seen_delisted += 1
    out["seed_row_count"] = len(seed_symbols)
    out["seed_tier_counts"] = seed_tier_counts
    out["seed_seen_delisted_count"] = seed_seen_delisted

    built_included_symbols = {r["symbol"] for r in rows if r["included"]}
    new_listings = sorted(built_included_symbols - seed_symbols)
    dropped_vs_seed = sorted(seed_symbols - built_included_symbols)
    out["new_symbols_vs_seed"] = new_listings
    out["new_symbols_vs_seed_count"] = len(new_listings)
    out["dropped_vs_seed"] = dropped_vs_seed
    out["dropped_vs_seed_count"] = len(dropped_vs_seed)
    out["built_tier_counts"] = summary["counts_by_recommended_tier"]
    out["built_seen_delisted_count"] = summary["delisted_proof_count"]

    # 解釋 drift（contract §7：須解釋，非靜默）。
    out["drift_explanation"] = (
        f"count drift = built({len(built_included_symbols)}) - "
        f"seed({len(seed_symbols)}) = {len(built_included_symbols) - len(seed_symbols)}; "
        f"new symbols since seed (listings + symmetric-window inclusion): {len(new_listings)}; "
        f"dropped vs seed: {len(dropped_vs_seed)}; "
        "tier-name drift expected: seed predates contract tier taxonomy "
        "(seed uses current_bybit_usdt_perp/historical_delisted_18mo/scanner_24h_dynamic; "
        "builder uses PA-spec full_survivorship/top_liquidity_40_50/scanner_active_asof); "
        "drift is NOT a failure (contract §7) unless built_count << seed_count "
        "(survivor-truncation regression suspect)."
    )
    return out


def run_build(args: argparse.Namespace) -> dict:
    """執行一次 build（load → build → write → seed regression）。回 result dict。"""
    window = WindowSpec(
        window_start_utc=_parse_utc(args.window_start),
        window_end_utc=_parse_utc(args.window_end),
        asof_utc=_parse_utc(args.asof),
        closed_bar_cutoff_utc=_parse_utc(args.cutoff),
    )

    lifecycles = load_lifecycles(
        window,
        quote_coin=args.quote_coin,
        contract_type=args.contract_type,
        dsn=args.dsn,
    )
    rows, summary = build_universe(lifecycles, window, run_id=args.run_id)

    # universe_sources：primary 必含；scanner / market_tickers 若有 symbol 命中才標
    # （tier 排序源存在性由 data_loader to_regclass guard 決定，這裡據實況標）。
    universe_sources = [_PRIMARY_SOURCE]
    if any(r["in_scanner_window"] for r in rows):
        universe_sources.append("trading.scanner_snapshots")
    if any(r["recommended_tier"] == "top_liquidity_40_50" for r in rows):
        universe_sources.append("market.market_tickers")

    seed_path = Path(args.seed_csv) if args.seed_csv else (_repo_root() / _DEFAULT_SEED_REL)
    seed_reg = compute_seed_regression(rows, summary, seed_path=seed_path)
    summary["seed_regression"] = seed_reg

    artifact_root = Path(args.artifact_root) if args.artifact_root else None
    written = artifact_mod.write_all(
        rows, summary,
        run_id=args.run_id,
        window=window,
        universe_sources=universe_sources,
        repo_root=_repo_root(),
        runtime_host=socket.gethostname(),
        session_id=args.session_id,
        created_by_role=args.created_by_role,
        artifact_root=artifact_root,
    )
    return {"summary": summary, "written": written, "row_count": len(rows)}


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fnd2_pit_universe.harness",
        description="FND-2 PIT universe builder (read-only PG → deterministic artifact)",
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    # 顯式窗（無隱式 now()，contract §1 / OQ-5）。
    p.add_argument("--asof", required=True, help="asof_utc ISO8601 (e.g. 2026-06-03T00:00:00Z)")
    p.add_argument("--window-start", required=True, dest="window_start")
    p.add_argument("--window-end", required=True, dest="window_end")
    p.add_argument("--cutoff", required=True, help="closed_bar_cutoff_utc ISO8601")
    p.add_argument("--quote-coin", default="USDT", dest="quote_coin")
    p.add_argument("--contract-type", default="LinearPerpetual", dest="contract_type")
    p.add_argument("--dsn", default=None, help="override PG DSN (default: lib.pg_connect)")
    p.add_argument("--seed-csv", default=None, dest="seed_csv", help="override seed CSV path")
    p.add_argument("--artifact-root", default=None, dest="artifact_root",
                   help="override artifact root (default: $OPENCLAW_DATA_DIR/alpha_history_runs)")
    p.add_argument("--session-id", default=None, dest="session_id")
    p.add_argument("--created-by-role", default="E1", dest="created_by_role")
    return p


def main(argv: Optional[list] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = run_build(args)
    summary = result["summary"]
    seed = summary.get("seed_regression", {})
    out = {
        "run_id": summary["run_id"],
        "universe_id": summary["universe_id"],
        "window_start_utc": summary["window_start_utc"],
        "window_end_utc": summary["window_end_utc"],
        "asof_utc": summary["asof_utc"],
        "total_rows": result["row_count"],
        "included_count": summary["included_count"],
        "excluded_count": summary["excluded_count"],
        "delisted_proof_count": summary["delisted_proof_count"],
        "unknown_lifetime_count": summary["unknown_lifetime_count"],
        "survivor_rejection_status": summary["survivor_rejection_status"],
        "counts_by_recommended_tier": summary["counts_by_recommended_tier"],
        "core25_member_count": len(CORE25_PINNED),
        "seed_row_count": seed.get("seed_row_count"),
        "seed_sha256_match": seed.get("seed_sha256_match"),
        "drift_explanation": seed.get("drift_explanation"),
        "artifact_dir": result["written"]["run_dir"],
        "parquet_result": result["written"]["parquet_result"],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
