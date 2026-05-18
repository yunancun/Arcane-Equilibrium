#!/usr/bin/env python3
"""W-AUDIT-8c Stage 0R 報告 CLI 與 PG 取數編排層。

MODULE_NOTE
模塊用途：W-AUDIT-8c Liquidation Cluster Reaction Stage 0R replay 的唯一
operator 入口。負責：
  1. 連 PostgreSQL（read-only），執行 SQL feature query；
  2. 將 row dict 轉成 pandas.DataFrame 供 sibling worktree S0R-2 metrics
     模塊（compute_stage0r / compute_stage0r_sweep）消費；
  3. 接受 BB pre-flight gate flag（2026-05-18 BB STRUCTURAL verdict 已
     先導 demo bias confirmed，預設 True）；
  4. 產出 JSON + Markdown，落地到 docs/CCAgentWorkSpace/{role}/workspace/
     reports/YYYY-MM-DD--w_audit_8c_stage0r_<verdict>.{json,md}；
  5. Markdown 段落含 4-agent (QC / MIT / FA / BB) review-ready 結構。
主要類/函數：main / _build_packet / _render_markdown / _get_conn /
            _read_sql / _fetch_panel_df。
依賴：psycopg2、pandas（runtime）、sibling worktree 8C-S0R-2
      `liquidation_cluster_stage0r_metrics`、sibling worktree 8C-S0R-1
      `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql`。
硬邊界：read-only PG 查詢；不寫 trading.* / panel.* / market.*；不調 Rust；
       不變動 authorization / lease / mainnet enable；不接觸 paper pipeline。
       BB pre-flight gate 為硬條件：明確 False 時 exit 並列 BB 報告路徑。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    # 同包內 sibling import；正式 merge 後 8C-S0R-2 metrics.py 與本檔同層
    from .liquidation_cluster_stage0r_metrics import (  # type: ignore
        compute_stage0r,
        compute_stage0r_sweep,
    )
except ImportError:
    # 直接執行（非 -m）路徑：sys.path 已被 top-level wrapper 補入 w_audit_8c/
    from liquidation_cluster_stage0r_metrics import (  # type: ignore
        compute_stage0r,
        compute_stage0r_sweep,
    )


# ──────────────────────────────────────────────────────────────────────────
# Spec v0.3 預設常數（見 docs/execution_plan/2026-05-16--w_audit_8c_liquidation_cluster_strategy_spec.md）
# ──────────────────────────────────────────────────────────────────────────
DEFAULT_WINDOW_DAYS = 7
DEFAULT_COST_BPS = 12.0
DEFAULT_HORIZON_MIN = 5
DEFAULT_QUIET_WINDOW_SEC = 30
# Spec v0.3 初始 grid（fixed before replay）
DEFAULT_K_GRID = "2,3,5,8"
DEFAULT_N_USD_GRID = "5000,10000,25000,50000"
DEFAULT_M_GRID = "1,2,3"
DEFAULT_SIDE_DOM_GRID = "0.70,0.80,0.90"
DEFAULT_CLUSTER_NOTIONAL_FLOOR_USD = 10000.0
# BB pre-flight：2026-05-18 BB STRUCTURAL verdict 後預設 True（見 dispatch prompt）
BB_REPORT_PATH = (
    "docs/CCAgentWorkSpace/BB/workspace/reports/"
    "2026-05-18--w_audit_8c_demo_testnet_long_liq_skew_bb_review.md"
)

VERDICT_VALUES = ("PASS-BOTH", "PASS-LONG-ONLY", "PASS-SHORT-ONLY", "RED", "PARTIAL")


def _repo_root() -> Path:
    """解析 repo 根目錄，禁硬編碼路徑（feedback_cross_platform.md 跨平台原則）。"""
    base = os.environ.get("OPENCLAW_BASE_DIR") or os.environ.get("OPENCLAW_SRV_ROOT")
    if base:
        return Path(base)
    # helper_scripts/reports/w_audit_8c/<this> → parents[3] = repo root
    return Path(__file__).resolve().parents[3]


def _get_conn():
    """連 PG read-only。優先 OPENCLAW_DATABASE_URL，否則拼 POSTGRES_* env。

    為什麼這樣寫：禁止硬編碼 hostname（feedback_cross_platform.md）；同時
    與 sibling 8b funding_skew_stage0r_report.py 完全相同的連線模式，保持
    operator 操作慣性。
    """
    import psycopg2  # type: ignore

    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    conn = psycopg2.connect(dsn, application_name="openclaw_w_audit_8c_stage0r")
    with conn.cursor() as cur:
        cur.execute(
            "SET statement_timeout = %s",
            (int(os.environ.get("OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS", "180000")),),
        )
    return conn


def _read_sql() -> str:
    """讀 sibling worktree 8C-S0R-1 產出的 SQL 文件。

    為什麼讀檔而非 inline：SQL 由 S0R-1 owner 維護，consumer 不複製 SQL；
    merge 衝突最小化；任何 SQL 修訂只需動 S0R-1 worktree。
    """
    path = (
        _repo_root()
        / "sql"
        / "queries"
        / "w_audit_8c_liquidation_cluster_stage0r_features.sql"
    )
    return path.read_text(encoding="utf-8")


def _parse_float_grid(raw: str, *, name: str) -> tuple[float, ...]:
    """解析 CSV 浮點 grid（K_grid 用整數但統一以浮點承載，避免 dtype 分支）。"""
    values = tuple(float(item.strip()) for item in raw.split(",") if item.strip())
    if not values:
        raise ValueError(f"--{name} 必須含至少一個數值")
    return values


def _parse_int_grid(raw: str, *, name: str) -> tuple[int, ...]:
    values = tuple(int(item.strip()) for item in raw.split(",") if item.strip())
    if not values:
        raise ValueError(f"--{name} 必須含至少一個整數")
    return values


def _fetch_panel_df(conn, *, params: dict[str, Any]):
    """執行 SQL feature query，回傳 pandas.DataFrame。

    為什麼回傳 DataFrame：sibling 8C-S0R-2 contract 簽名 `compute_stage0r(
    panel_df, ...)` 期待 pandas.DataFrame。本檔不做數學運算，只做 schema
    對齊。SQL 取出的 column 名見 dispatch prompt §S0R-1 contract。
    """
    import pandas as pd  # type: ignore

    sql = _read_sql()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


def _clean_json(value):
    """遞迴清理 NaN/Inf，回傳 JSON-safe 結構。

    為什麼需要：pandas / numpy 浮點可能含 NaN / Inf，json.dumps 默認會吐
    出 `NaN` literal 違反 RFC 8259。8b precedent 採同樣處理。
    """
    if isinstance(value, dict):
        return {k: _clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_json(v) for v in value]
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    # numpy scalar → python native
    try:
        import numpy as np  # type: ignore

        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            f = float(value)
            if f != f or f in (float("inf"), float("-inf")):
                return None
            return f
        if isinstance(value, (np.bool_,)):
            return bool(value)
    except ImportError:
        pass
    return value


def _verdict_from_cells(cells: list[dict[str, Any]]) -> str:
    """從 sweep cells 聚合 panel-level verdict（per-cell verdict 之 OR）。

    Spec v0.3 規則：
    - 任一 cell `pass == 'PASS-BOTH'` → panel verdict = PASS-BOTH
    - 否則任一 cell `pass == 'PASS-LONG-ONLY'` → PASS-LONG-ONLY
    - 否則任一 cell `pass == 'PASS-SHORT-ONLY'` → PASS-SHORT-ONLY
    - 否則若全 RED → RED
    - 混合（部分 PASS-* 但 sweep 內非全 RED）→ PARTIAL（保守）
    """
    if not cells:
        return "RED"
    statuses = [str(c.get("pass") or "RED") for c in cells]
    if "PASS-BOTH" in statuses:
        return "PASS-BOTH"
    has_long = "PASS-LONG-ONLY" in statuses
    has_short = "PASS-SHORT-ONLY" in statuses
    if has_long and has_short:
        return "PARTIAL"
    if has_long:
        return "PASS-LONG-ONLY"
    if has_short:
        return "PASS-SHORT-ONLY"
    return "RED"


def _aggregate_sweep_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    """sweep_summary 統計。"""
    total = len(cells)
    pass_both = sum(1 for c in cells if c.get("pass") == "PASS-BOTH")
    pass_long = sum(1 for c in cells if c.get("pass") == "PASS-LONG-ONLY")
    pass_short = sum(1 for c in cells if c.get("pass") == "PASS-SHORT-ONLY")
    red = sum(1 for c in cells if c.get("pass") == "RED")
    reason_counts: dict[str, int] = {}
    for c in cells:
        for reason in c.get("red_reasons") or []:
            reason_counts[str(reason)] = reason_counts.get(str(reason), 0) + 1
    return {
        "total_cells": total,
        "pass_both_cells": pass_both,
        "pass_long_only_cells": pass_long,
        "pass_short_only_cells": pass_short,
        "red_cells": red,
        "red_reason_counts": reason_counts,
    }


def _build_packet(
    *,
    panel_df,
    cells: list[dict[str, Any]],
    primary_cell: dict[str, Any] | None,
    sweep_params: dict[str, Any],
    bb_preflight: dict[str, Any],
) -> dict[str, Any]:
    """組裝 spec v0.3 Mandatory report fields 的最終 JSON packet。"""
    verdict = _verdict_from_cells(cells)
    sweep_summary = _aggregate_sweep_summary(cells)

    # panel_meta：從 DataFrame 萃取，pandas 不可用時退到空欄位
    panel_meta: dict[str, Any] = {
        "earliest_ts": None,
        "latest_ts": None,
        "span_days": None,
        "total_rows": int(getattr(panel_df, "shape", (0, 0))[0]),
        "distinct_symbols": 0,
    }
    try:
        if hasattr(panel_df, "empty") and not panel_df.empty:
            if "bucket_5m_epoch" in panel_df.columns:
                earliest = int(panel_df["bucket_5m_epoch"].min())
                latest = int(panel_df["bucket_5m_epoch"].max())
                panel_meta["earliest_ts"] = earliest
                panel_meta["latest_ts"] = latest
                # bucket_5m_epoch 為秒級 epoch（per S0R-1 contract）；
                # span_days = (latest - earliest) / 86400
                panel_meta["span_days"] = round((latest - earliest) / 86400.0, 3)
            if "symbol" in panel_df.columns:
                panel_meta["distinct_symbols"] = int(panel_df["symbol"].nunique())
    except Exception:  # noqa: BLE001
        # 不讓 metadata 萃取失敗影響整個 packet
        pass

    # n_eff_audit：取 primary_cell 的 cluster-aware n_eff
    if primary_cell:
        raw_n = primary_cell.get("n_per_cell") or primary_cell.get("raw_n") or 0
        n_eff = primary_cell.get("pooled_n_eff") or primary_cell.get("cluster_aware_n_eff") or 0
    else:
        raw_n = 0
        n_eff = 0
    penalty_rate = None
    if raw_n and float(raw_n) > 0:
        penalty_rate = 1.0 - (float(n_eff) / float(raw_n))

    # tombstone_risk_summary：v0.3 三大 RED risk 對 BB 已先導決議
    tombstone = {
        "red_risk_1_demo_bias": (
            "RESOLVED-BB-STRUCTURAL"
            if bb_preflight.get("demo_bias_confirmed")
            else "PENDING"
        ),
        "red_risk_2_n_eff": (
            "PASS"
            if (primary_cell and "n_eff" not in (primary_cell.get("red_reasons") or []))
            else "PENDING"
        ),
        "red_risk_3_cost_gate": (
            "PASS"
            if (primary_cell and "cost_gate" not in (primary_cell.get("red_reasons") or []))
            else "PENDING"
        ),
    }

    # review_ready：當 verdict 非 RED 且 BB pre-flight 已確認 → ready；
    # RED + BB confirmed 也算 review_ready（4-agent 仍需判 RED 是否可改 spec）
    review_ready = bool(bb_preflight.get("demo_bias_confirmed"))

    return {
        "verdict": verdict,
        "panel_meta": panel_meta,
        "params": sweep_params,
        "cells": cells,
        "primary_cell": primary_cell,
        "sweep_summary": sweep_summary,
        "bb_pre_flight": bb_preflight,
        "n_eff_audit": {
            "raw_n": raw_n,
            "cluster_aware_n_eff": n_eff,
            "penalty_rate": penalty_rate,
        },
        "tombstone_risk_summary": tombstone,
        "review_ready": review_ready,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "spec_version": "v0.3",
        "strategy_id": "liquidation_cluster_reaction",
    }


def _render_markdown(packet: dict[str, Any]) -> str:
    """渲染 4-agent review-ready Markdown。

    為什麼要 4-agent 段落：dispatch prompt acceptance criteria #3 要求
    QC / MIT / FA / BB 視角都呈現；下游 PM 派 4-agent review packet 時
    可直接抓段落。
    """
    bb = packet.get("bb_pre_flight") or {}
    pm = packet.get("panel_meta") or {}
    ss = packet.get("sweep_summary") or {}
    primary = packet.get("primary_cell") or {}
    cells = packet.get("cells") or []
    tomb = packet.get("tombstone_risk_summary") or {}
    nea = packet.get("n_eff_audit") or {}
    params = packet.get("params") or {}

    # 參數列表（按 dict insertion 順序）
    params_md = "\n".join(f"- {k}: {v}" for k, v in params.items()) or "- (empty)"

    # RED reason counts 列表
    rc = ss.get("red_reason_counts") or {}
    rc_md = (
        "- red_reason_counts:\n"
        + "\n".join(
            f"  - `{r}`: {n}" for r, n in sorted(rc.items(), key=lambda kv: -kv[1])
        )
        if rc
        else ""
    )

    # BB skew data
    skew = bb.get("skew_data") or {}
    skew_md = (
        "- skew_data:\n" + "\n".join(f"  - {k}: {v}" for k, v in skew.items())
        if skew
        else ""
    )

    # Tombstone list
    tomb_md = "\n".join(f"- {k}: {v}" for k, v in tomb.items())

    # Per-cell top-10 table
    sortable = []
    for c in cells:
        nb = c.get("net_bps")
        try:
            nv = float(nb) if nb is not None else float("-inf")
        except (TypeError, ValueError):
            nv = float("-inf")
        sortable.append((nv, c))
    sortable.sort(key=lambda kv: -kv[0])
    table_rows = [
        "| {K} | {N} | {M} | {sd} | {p} | {n} | {ne} | {g} | {nb} | {dsr} | {pbo} |".format(
            K=c.get("k") or c.get("min_event_count_5m"),
            N=c.get("n_usd") or c.get("min_cluster_notional_5m_usd"),
            M=c.get("m") or c.get("min_dominant_event_count"),
            sd=c.get("side_dom") or c.get("side_dominance_floor"),
            p=c.get("pass"),
            n=c.get("n_per_cell"),
            ne=c.get("pooled_n_eff"),
            g=c.get("gross_bps"),
            nb=c.get("net_bps"),
            dsr=c.get("dsr"),
            pbo=c.get("pbo"),
        )
        for _, c in sortable[:10]
    ]
    table_md = "\n".join(table_rows) if table_rows else "| (no cells) |"

    primary_json = json.dumps(_clean_json(primary), indent=2, sort_keys=True)

    return f"""# W-AUDIT-8c Liquidation Cluster Stage 0R Report

generated_at_utc: {packet.get('generated_at_utc')}
strategy_id: {packet.get('strategy_id')}
spec_version: {packet.get('spec_version')}

## Verdict

**verdict: {packet.get('verdict')}**
review_ready: {bool(packet.get('review_ready'))}

## Panel Metadata

- total_rows: {pm.get('total_rows')}
- distinct_symbols: {pm.get('distinct_symbols')}
- earliest_ts: {pm.get('earliest_ts')}
- latest_ts: {pm.get('latest_ts')}
- span_days: {pm.get('span_days')}

## Parameters

{params_md}

## Sweep Summary

- total_cells: {ss.get('total_cells')}
- pass_both_cells: {ss.get('pass_both_cells')}
- pass_long_only_cells: {ss.get('pass_long_only_cells')}
- pass_short_only_cells: {ss.get('pass_short_only_cells')}
- red_cells: {ss.get('red_cells')}
{rc_md}

## BB Pre-flight Gate

- demo_bias_confirmed: {bool(bb.get('demo_bias_confirmed'))}
- bb_report_path: {bb.get('bb_report_path')}
{skew_md}

## n_eff Audit (cluster-aware)

- raw_n: {nea.get('raw_n')}
- cluster_aware_n_eff: {nea.get('cluster_aware_n_eff')}
- penalty_rate: {nea.get('penalty_rate')}

## Tombstone Risk Summary

{tomb_md}

## Primary Cell

```json
{primary_json}
```

## Per-Cell Table (top 10 by net_bps)

| K | N_usd | M | side_dom | pass | n_per_cell | pooled_n_eff | gross_bps | net_bps | dsr | pbo |
|---|---|---|---|---|---|---|---|---|---|---|
{table_md}

## 4-Agent Review Sections

### QC（Quantitative Compliance）視角

- panel n_eff vs sample floor: cluster_aware_n_eff={nea.get('cluster_aware_n_eff')} vs spec v0.3 promotion floor `n_eff ≥ 300 pooled`。
- multiple-comparison cost (K_total): sweep cells={ss.get('total_cells')}；spec v0.3 enlarged K_total=48× v0.1 (243 → 11,664 per symbol)。
- DSR / PBO 應檢視 primary_cell 與 sweep top-10；單 cell PASS 但 plateau 不形成則仍應視為 RED。

### MIT（Machine-Intelligence Trustee）視角

- density floor efficacy：raw bucket → after K → after N_usd → after M chain 應由 metrics 模塊補位（見 cells[*].density_floor_chain）；spec v0.3 要求 floor 移除 ≥ 60% 單/雙事件 bucket。
- empirical sparsity（MIT 2026-05-18 PG SoT）：HYPEUSDT 1.54% / BTCUSDT 0.89% / ETHUSDT 0.99% / LINKUSDT 0.20% 7d 5m bucket coverage；本 panel total_rows={pm.get('total_rows')} 應 cross-check 與 tier 分層一致。
- per-tier independent promotion：high / medium / low tier 需各自過 n_eff + avg_net_bps + PSR/DSR。

### FA（Failure Analyst）視角

- RED reason 聚合（見 sweep_summary.red_reason_counts）：高頻 RED 原因即下一輪 spec 修訂重點。
- tombstone risk：demo_bias={tomb.get('red_risk_1_demo_bias')} / n_eff={tomb.get('red_risk_2_n_eff')} / cost_gate={tomb.get('red_risk_3_cost_gate')}。
- 若 verdict=RED 且 reason 集中於 n_eff，建議擴 replay 窗（spec v0.3 §6 預測 21-30d minimum）而非 lower threshold。

### BB（Bybit-side Boundary）視角

- BB pre-flight verdict (2026-05-18)：STRUCTURAL；demo_bias_confirmed={bool(bb.get('demo_bias_confirmed'))}。
- 本 packet 不變動 production WS subscription / topic builder；`allLiquidation*` 仍應在 full_subscription_list excluded 集合內，直到 PM 另行 dispatch revival 任務。
- side mapping：dominant Buy → LongLiquidated → expected_dir=+1；dominant Sell → ShortLiquidated → expected_dir=-1（per BB corrected side-semantics 2026-05-17 sign-off）。
"""


def _resolve_output_path(*, role: str, verdict: str, fmt: str, out_dir: str | None) -> Path:
    """回傳 docs/CCAgentWorkSpace/{role}/workspace/reports/<date>--w_audit_8c_stage0r_<verdict>.<ext>。"""
    base = _repo_root()
    if out_dir:
        base_dir = Path(out_dir)
    else:
        base_dir = base / "docs" / "CCAgentWorkSpace" / role / "workspace" / "reports"
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ext = "json" if fmt == "json" else "md"
    safe_verdict = str(verdict).lower().replace("-", "_")
    return base_dir / f"{date_str}--w_audit_8c_stage0r_{safe_verdict}.{ext}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="W-AUDIT-8c Liquidation Cluster Stage 0R replay report CLI"
    )
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    parser.add_argument("--horizon-min", type=int, default=DEFAULT_HORIZON_MIN)
    parser.add_argument(
        "--quiet-window-sec", type=int, default=DEFAULT_QUIET_WINDOW_SEC
    )
    parser.add_argument(
        "--cluster-notional-floor-usd",
        type=float,
        default=DEFAULT_CLUSTER_NOTIONAL_FLOOR_USD,
    )
    parser.add_argument(
        "--k-grid",
        type=str,
        default=DEFAULT_K_GRID,
        help=f"CSV of min_event_count_5m sweep cells (default: {DEFAULT_K_GRID})",
    )
    parser.add_argument(
        "--n-usd-grid",
        type=str,
        default=DEFAULT_N_USD_GRID,
        help=f"CSV of min_cluster_notional_5m_usd sweep cells (default: {DEFAULT_N_USD_GRID})",
    )
    parser.add_argument(
        "--m-grid",
        type=str,
        default=DEFAULT_M_GRID,
        help=f"CSV of min_dominant_event_count sweep cells (default: {DEFAULT_M_GRID})",
    )
    parser.add_argument(
        "--side-dom-grid",
        type=str,
        default=DEFAULT_SIDE_DOM_GRID,
        help=f"CSV of side_dominance_floor sweep cells (default: {DEFAULT_SIDE_DOM_GRID})",
    )
    parser.add_argument(
        "--bb-demo-bias-confirmed",
        type=lambda s: str(s).strip().lower() in ("1", "true", "yes", "y"),
        default=True,
        help=(
            "BB pre-flight gate：2026-05-18 BB STRUCTURAL verdict 後預設 True；"
            "若 BB review 變更顯式設 False，CLI 將 exit 並列 BB 報告路徑"
        ),
    )
    parser.add_argument(
        "--no-sweep",
        action="store_true",
        help="只跑單一 primary cell（不做 K/N_usd/M/side_dom sweep）",
    )
    parser.add_argument(
        "--role",
        type=str,
        default="PA",
        help="輸出落地的 agent 角色資料夾（docs/CCAgentWorkSpace/<role>/workspace/reports/）",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="覆寫輸出目錄（debug 用；正式 run 留空以走 role-based 路徑）",
    )
    parser.add_argument("--format", choices=("json", "markdown", "both"), default="both")
    parser.add_argument(
        "--rng-seed", type=int, default=42, help="bootstrap RNG seed（默認 42）"
    )
    parser.add_argument(
        "--bootstrap-iters",
        type=int,
        default=10000,
        help="block-bootstrap iteration 次數（默認 10000）",
    )
    args = parser.parse_args(argv)

    # ── BB pre-flight 硬 gate ──────────────────────────────────────────
    if not args.bb_demo_bias_confirmed:
        print(
            "[FATAL] BB demo bias 未確認，Stage 0R 不執行。\n"
            f"        BB 報告路徑：{BB_REPORT_PATH}\n"
            "        如需 override，請先讓 BB 重新審查或 operator 顯式授權後再"
            "傳 --bb-demo-bias-confirmed=true。",
            file=sys.stderr,
        )
        return 3

    # ── 解析 sweep grid ────────────────────────────────────────────────
    try:
        k_grid = _parse_int_grid(args.k_grid, name="k-grid")
        n_usd_grid = _parse_float_grid(args.n_usd_grid, name="n-usd-grid")
        m_grid = _parse_int_grid(args.m_grid, name="m-grid")
        side_dom_grid = _parse_float_grid(args.side_dom_grid, name="side-dom-grid")
    except ValueError as exc:
        print(f"[FATAL] grid 解析失敗：{exc}", file=sys.stderr)
        return 2

    sweep_params = {
        "window_days": args.window_days,
        "cost_bps": args.cost_bps,
        "horizon_min": args.horizon_min,
        "quiet_window_sec": args.quiet_window_sec,
        "cluster_notional_floor_usd": args.cluster_notional_floor_usd,
        "k_grid": list(k_grid),
        "n_usd_grid": list(n_usd_grid),
        "m_grid": list(m_grid),
        "side_dom_grid": list(side_dom_grid),
    }

    # ── PG 取數 ────────────────────────────────────────────────────────
    try:
        conn = _get_conn()
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] PG 連線失敗：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    try:
        # SQL 參數綁定：使用 sibling 8C-S0R-1 SQL 文件聲明的 $ 名稱 → 在
        # psycopg2 內以 %(name)s 命名參數形式對應；S0R-1 SQL 必須撰寫
        # psycopg2-friendly placeholder（與 8b precedent 相同模式）
        sql_params = {
            "window_days": args.window_days,
            "K": int(min(k_grid)),  # 取最寬鬆 K 作 SQL pre-filter
            "N_usd": float(min(n_usd_grid)),
            "M": int(min(m_grid)),
            "side_dominance_floor": float(min(side_dom_grid)),
            "cluster_notional_floor_usd": float(args.cluster_notional_floor_usd),
            "quiet_window_sec": int(args.quiet_window_sec),
            "horizon_min": int(args.horizon_min),
            "cost_bps": float(args.cost_bps),
        }
        panel_df = _fetch_panel_df(conn, params=sql_params)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[FATAL] Stage 0R query 失敗：{type(exc).__name__}: {exc}", file=sys.stderr
        )
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
        return 1
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    # ── 呼叫 sibling 8C-S0R-2 metrics ─────────────────────────────────
    try:
        common_kwargs = dict(
            cost_bps=args.cost_bps,
            horizon_min=args.horizon_min,
            rng_seed=args.rng_seed,
            bootstrap_iters=args.bootstrap_iters,
        )
        if args.no_sweep:
            primary_cell = compute_stage0r(panel_df, **common_kwargs)
            cells = [primary_cell] if primary_cell else []
        else:
            cells = compute_stage0r_sweep(
                panel_df,
                k_grid=list(k_grid),
                n_usd_grid=list(n_usd_grid),
                m_grid=list(m_grid),
                side_dom_grid=list(side_dom_grid),
                **common_kwargs,
            )
            # primary_cell：選 sweep 中 net_bps 最高且 pass != RED 的 cell；
            # 若全 RED 則取 net_bps 最高（用於診斷）
            non_red = [c for c in cells if c.get("pass") and c.get("pass") != "RED"]
            pool = non_red or cells
            primary_cell = (
                max(
                    pool,
                    key=lambda c: float(c.get("net_bps") or float("-inf")),
                )
                if pool
                else None
            )
    except ValueError as exc:
        print(f"[FATAL] Stage 0R metrics 入參非法：{exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(
            f"[FATAL] Stage 0R metrics 計算失敗：{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    # ── 組 packet ──────────────────────────────────────────────────────
    bb_preflight = {
        "demo_bias_confirmed": bool(args.bb_demo_bias_confirmed),
        "skew_data": {
            "verdict": "STRUCTURAL",
            "verdict_date_utc": "2026-05-18",
            "source": "BB Round demo testnet long liq skew review",
        },
        "bb_report_path": BB_REPORT_PATH,
    }
    packet = _build_packet(
        panel_df=panel_df,
        cells=cells,
        primary_cell=primary_cell,
        sweep_params=sweep_params,
        bb_preflight=bb_preflight,
    )

    # ── 寫檔 ───────────────────────────────────────────────────────────
    cleaned = _clean_json(packet)
    written: list[Path] = []
    if args.format in ("json", "both"):
        path_json = _resolve_output_path(
            role=args.role,
            verdict=str(packet.get("verdict") or "RED"),
            fmt="json",
            out_dir=args.out_dir,
        )
        path_json.parent.mkdir(parents=True, exist_ok=True)
        path_json.write_text(
            json.dumps(cleaned, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(path_json)
    if args.format in ("markdown", "both"):
        path_md = _resolve_output_path(
            role=args.role,
            verdict=str(packet.get("verdict") or "RED"),
            fmt="markdown",
            out_dir=args.out_dir,
        )
        path_md.parent.mkdir(parents=True, exist_ok=True)
        path_md.write_text(_render_markdown(packet), encoding="utf-8")
        written.append(path_md)

    for p in written:
        print(f"Wrote {p}", file=sys.stderr)
    print(
        json.dumps(
            {
                "verdict": packet.get("verdict"),
                "review_ready": packet.get("review_ready"),
                "outputs": [str(p) for p in written],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
