#!/usr/bin/env python3
"""AEG-S2 breadth ladder runner CLI 編排。

MODULE_NOTE:
  模塊用途：breadth ladder runner 的 CLI 入口。parse args（run_id / fnd2 artifact dir /
    顯式窗）→ universe_artifact 讀 FND-2 artifact → tiers.assemble_tiers（cohort_ids
    nested）→ build_alive_mask（survivorship 繼承）→ per-tier candidate.evaluate（預設
    multiday reference adapter，OQ-B2）→ ladder.build_ladder → artifact.write_all →
    **survivorship PIT healthcheck 即時 gate（FAIL → raise）** → 印 summary。
    **無隱式 now()**（窗口為顯式參數）。
    healthcheck 接入（MIT M-2 / E2 LOW）：在 run path 產 artifact 後立即把
    ``healthcheck.check_aeg_breadth_universe_pit`` 當 gate（FAIL=非繼承 / current-survivor
    truncate → run 非 0 退出），使其 load-bearing 而非 silent-dead；cron / AEG run
    orchestration 級別的排程接入屬 (c) / AEG run orchestration（PM follow-up TODO）。
  主要函數：``main`` / ``run_ladder`` / ``assemble_tier_results``。
  CLI 範例（首跑用 FND-2 同窗，OQ-B5）：
    python3 -m aeg_breadth_ladder.harness \\
      --run-id breadth_$(date +%Y%m%dT%H%M%SZ) \\
      --fnd2-run-dir /tmp/openclaw/alpha_history_runs/<fnd2_run_id> \\
      --asof 2026-06-03T00:00:00Z --window-start 2024-06-03T00:00:00Z \\
      --window-end 2026-06-03T00:00:00Z --candidate multiday_trend_reference
  硬邊界：read-from-storage-only（FND-2 artifact 讀檔 + 候選 loader read-only PG）；
    0 DB write；artifact 寫本地檔系統（OPENCLAW_DATA_DIR）。exit 0=成功；非零=載入/IO
    失敗（fail-loud，不吞）。(b) 不算 final_label（那是 (c)）；只供 verdict_hint advisory。
  依賴：本 package 內部模塊 + 標準庫；multiday reference adapter 延遲 import 候選 harness。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import socket
import sys
from dataclasses import replace
from pathlib import Path
from typing import Optional

# 支援兩種執行方式：(a) python3 -m aeg_breadth_ladder.harness（package 相對 import）；
# (b) 直接執行檔案路徑（research/ 非 package，補 sys.path 後絕對 import）。
try:
    from . import tiers as tiers_mod
    from . import universe_artifact as ua_mod
    from . import ladder as ladder_mod
    from . import artifact as artifact_mod
    from . import healthcheck as hc_mod
    from .evaluator import MultidayTrendReferenceEvaluator, StubEvaluator
except ImportError:  # pragma: no cover - 直接執行檔案路徑時
    _here = Path(__file__).resolve()
    _research = _here.parents[1]  # .../helper_scripts/research
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_breadth_ladder import tiers as tiers_mod  # type: ignore
    from aeg_breadth_ladder import universe_artifact as ua_mod  # type: ignore
    from aeg_breadth_ladder import ladder as ladder_mod  # type: ignore
    from aeg_breadth_ladder import artifact as artifact_mod  # type: ignore
    from aeg_breadth_ladder import healthcheck as hc_mod  # type: ignore
    from aeg_breadth_ladder.evaluator import (  # type: ignore
        MultidayTrendReferenceEvaluator, StubEvaluator,
    )

# breadth ladder 消費的儲存來源（manifest source_tables；候選 adapter 決定實際讀的表）。
_SOURCE_FND2_ARTIFACT = "<fnd2 universe artifact>"


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
    """.../srv（harness 在 srv/helper_scripts/research/aeg_breadth_ladder/）。"""
    return Path(__file__).resolve().parents[3]


def assemble_tier_results(
    evaluator,
    *,
    tiers_by_name: dict,
    alive_mask: dict,
    seen_delisted_map: dict,
) -> dict:
    """對每 tier 呼候選 evaluate，回 ``{tier_name: TierResult}``。

    seen_delisted_count 由 artifact（universe_artifact）權威覆寫——候選 adapter 不獨立
    判 delisted（artifact 是 survivorship 權威，MIT b.2），這裡用 tier ∩ seen_delisted_map
    覆寫每個 TierResult.seen_delisted_count（不偽造）。
    """
    results = {}
    for tier_name, members in tiers_by_name.items():
        tr = evaluator.evaluate(
            tier=tier_name, universe=tuple(sorted(members)), alive_mask=alive_mask,
        )
        # artifact 權威 delisted count 覆寫（adapter 回 0 佔位，見 evaluator MODULE_NOTE）。
        delisted_count = ua_mod.count_tier_seen_delisted(members, seen_delisted_map)
        results[tier_name] = replace(tr, seen_delisted_count=delisted_count)
    return results


def _build_evaluator(args, *, alive_mask: dict):
    """建候選評估器（預設 multiday reference adapter，OQ-B2）。

    為什麼預設 multiday：PM 裁決——端到端真資料驗證用既有 multiday-trend 候選 panel
    （已 universe-parametrized + 已知 NO-GO），正好驗 breadth 能正確顯示 narrowness。
    listing-fade 是未來真正首消費者（待 24h 捕捉），本期不依賴。
    """
    if args.candidate == "multiday_trend_reference":
        # 用 multiday data_loader 載 panel 一次（read-only PG），per-tier 共用。
        _research = Path(__file__).resolve().parents[1]
        if str(_research) not in sys.path:
            sys.path.insert(0, str(_research))
        from multiday_trend_diagnostic import data_loader  # 延遲 import

        # universe 給 multiday loader：取 alive_mask 全 symbol（panel 只載這些 symbol）。
        universe = tuple(sorted(alive_mask.keys()))
        panel = data_loader.load_panel(universe=universe, dsn=args.dsn)
        return MultidayTrendReferenceEvaluator(panel, k=args.tsmom_k)
    raise ValueError(
        f"未知 candidate：{args.candidate!r}（目前支援 multiday_trend_reference）"
    )


def run_ladder(args: argparse.Namespace, *, evaluator=None) -> dict:
    """執行一次 ladder（load FND-2 artifact → tiers → evaluate → ladder → write）。

    evaluator：可注入（測試用 StubEvaluator）；None 時用 args.candidate 建（真跑）。
    回 result dict。
    """
    # 1) 讀 FND-2 universe artifact（survivorship 繼承來源）。
    fnd2_run_dir = Path(args.fnd2_run_dir)
    rows, meta = ua_mod.load_fnd2_universe(fnd2_run_dir)

    # 2) 組 cumulative-nested tier（從 cohort_ids，NOT recommended_tier）。
    tiers_by_name = tiers_mod.assemble_tiers(rows)
    tiers_mod.assert_nested_invariant(tiers_by_name)  # 機械驗 core25 ⊆ top_liq ⊆ full

    # 3) survivorship mask 繼承（不重算）+ delisted map（artifact 權威）。
    alive_mask = ua_mod.build_alive_mask(rows)
    seen_delisted_map = ua_mod.build_seen_delisted_map(rows)

    # 4) per-tier candidate evaluate。
    if evaluator is None:
        evaluator = _build_evaluator(args, alive_mask=alive_mask)
    tier_results = assemble_tier_results(
        evaluator,
        tiers_by_name=tiers_by_name,
        alive_mask=alive_mask,
        seen_delisted_map=seen_delisted_map,
    )

    # 5) per-tier metadata（top_liquidity 降級，OQ-B3）。
    quality, pit_mode, exclusion = ua_mod.tier_quality_and_exclusion()

    # 6) build ladder（純函數 → rows + summary + monotonicity + ladder_id）。
    asof = _parse_utc(args.asof).isoformat()
    ws = _parse_utc(args.window_start).isoformat()
    we = _parse_utc(args.window_end).isoformat()
    ladder_rows, summary = ladder_mod.build_ladder(
        tier_results,
        run_id=args.run_id,
        candidate_id=evaluator.candidate_id,
        asof_utc=asof,
        window_start_utc=ws,
        window_end_utc=we,
        fnd2_universe_id=meta["fnd2_universe_id"],
        fnd2_run_id=meta["fnd2_run_id"],
        tier_quality_by_name=quality,
        tier_rank_pit_mode_by_name=pit_mode,
        promotion_exclusion_by_name=exclusion,
    )

    # 7) 寫 artifact。
    artifact_root = Path(args.artifact_root) if args.artifact_root else None
    written = artifact_mod.write_all(
        ladder_rows, summary,
        run_id=args.run_id,
        candidate_id=evaluator.candidate_id,
        fnd2_universe_id=meta["fnd2_universe_id"],
        fnd2_run_id=meta["fnd2_run_id"],
        source_tables=["market.klines", "market.funding_rates", _SOURCE_FND2_ARTIFACT],
        repo_root=_repo_root(),
        runtime_host=socket.gethostname(),
        session_id=args.session_id,
        created_by_role=args.created_by_role,
        artifact_root=artifact_root,
    )

    # 8) survivorship PIT healthcheck 即時 gate（MIT M-2 + E2 LOW：原函數無人 call =
    # silent-dead；在此產 artifact 後立即當 gate 接入，使其 load-bearing）。
    # FAIL → raise（fail-loud，run 非 0 退出，不讓 truncate/非繼承 artifact 靜默通過）。
    # WARN/PASS → 繼續（WARN=artifact/上游 summary 缺，非 (b) 缺陷）。
    hc_status, hc_msg = hc_mod.check_aeg_breadth_universe_pit(
        Path(written["breadth_ladder_summary"]),
        fnd2_run_dir / "universe_summary.json",
    )
    if hc_status == "FAIL":
        raise RuntimeError(
            f"breadth ladder survivorship healthcheck FAIL：{hc_msg}（"
            f"artifact={written['breadth_ladder_summary']}）"
        )

    return {"summary": summary, "written": written, "row_count": len(ladder_rows),
            "tiers": {k: len(v) for k, v in tiers_by_name.items()},
            "healthcheck": {"status": hc_status, "message": hc_msg}}


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aeg_breadth_ladder.harness",
        description="AEG-S2 breadth ladder runner (read FND-2 artifact + read-only PG "
                    "→ deterministic breadth_ladder artifact)",
    )
    p.add_argument("--run-id", required=True, dest="run_id")
    p.add_argument("--fnd2-run-dir", required=True, dest="fnd2_run_dir",
                   help="FND-2 artifact run 目錄（含 universe.csv + summary + manifest）")
    # 顯式窗（無隱式 now()，對齊 FND-2 universe artifact 的窗，OQ-B5）。
    p.add_argument("--asof", required=True, help="asof_utc ISO8601 (e.g. 2026-06-03T00:00:00Z)")
    p.add_argument("--window-start", required=True, dest="window_start")
    p.add_argument("--window-end", required=True, dest="window_end")
    p.add_argument("--candidate", default="multiday_trend_reference",
                   help="候選評估器 id（目前支援 multiday_trend_reference）")
    p.add_argument("--tsmom-k", type=int, default=30, dest="tsmom_k",
                   help="multiday reference adapter 的 TSMOM holding k（天）")
    p.add_argument("--dsn", default=None, help="override PG DSN (default: lib.pg_connect)")
    p.add_argument("--artifact-root", default=None, dest="artifact_root",
                   help="override artifact root (default: $OPENCLAW_DATA_DIR/alpha_history_runs)")
    p.add_argument("--session-id", default=None, dest="session_id")
    p.add_argument("--created-by-role", default="E1", dest="created_by_role")
    return p


def main(argv: Optional[list] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = run_ladder(args)
    summary = result["summary"]
    mono = summary.get("monotonicity", {})
    out = {
        "run_id": summary["run_id"],
        "ladder_id": summary["ladder_id"],
        "candidate_id": summary["candidate_id"],
        "fnd2_universe_id": summary["fnd2_universe_id"],
        "fnd2_run_id": summary["fnd2_run_id"],
        "asof_utc": summary["asof_utc"],
        "tiers_evaluated": summary["tiers_evaluated"],
        "per_tier_breadth": summary["per_tier_breadth"],
        "per_tier_net_bps": summary["per_tier_net_bps"],
        "per_tier_n_independent": summary["per_tier_n_independent"],
        "monotonicity_trend": mono.get("net_bps_trend"),
        "narrow_only_edge": mono.get("narrow_only_edge"),
        "n_independent_invariant_to_breadth": mono.get("n_independent_invariant_to_breadth"),
        "verdict_hint": summary["verdict_hint"],
        "delisted_proof_total": summary["delisted_proof_total"],
        "survivorship_inherited_from_fnd2": summary["survivorship_inherited_from_fnd2"],
        "survivorship_healthcheck": result.get("healthcheck"),
        "artifact_dir": result["written"]["run_dir"],
        "parquet_result": result["written"]["parquet_result"],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
