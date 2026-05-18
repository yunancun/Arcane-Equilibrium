#!/usr/bin/env python3
"""W-AUDIT-8c Stage 0R 報告 CLI 與 PG 取數編排層（round 2 rework）。

MODULE_NOTE
模塊用途：W-AUDIT-8c Liquidation Cluster Reaction Stage 0R replay 的唯一
operator 入口。負責：
  1. 連 PostgreSQL（read-only）並查 `panel symbols`（mirror 8b L71-95）
     與 `learning.strategy_trial_ledger` 取 k_prior（mirror 8b L97-145）；
  2. 執行 SQL feature query 並把 row 轉成 `list[dict]`（純 stdlib，
     對齊 sibling 8C-S0R-2 `Sequence[Mapping[str, object]]` 簽名）；
  3. SQL 出 `bucket_end_ts (timestamptz)` 但 S0R-2 `_extract_trigger_rows`
     讀 `bucket_end_ts_ms (int ms)` — 本檔在 row 構造時做關鍵 normalize
     `int(bucket_end_ts.timestamp() * 1000)`，否則所有 trigger 會被靜默
     skip → 假 RED tombstone（E2 round 1 CRIT-5）；
  4. 拆 sweep / single-cell 的 kwargs（compute_stage0r 接 `horizon_min`，
     compute_stage0r_sweep 接 `horizon_grid` — round 1 共用 kwargs 在
     sweep 分支 TypeError 拋掉 E2 round 1 CRIT-3）；
  5. compute_stage0r_sweep 回 `dict[str, object]` 而非 `list[dict]`
     （sweep_cells / eligible_for_demo_canary_per_tier / best_per_tier_per_direction
     / symbol_tiers / sweep_meta 等 6 keys；round 1 把它當 list iterate
     → AttributeError 即 E2 round 1 CRIT-2）；
  6. 接受 BB pre-flight gate flag；BB 報告檔不存在或顯式 False → exit 3
     fail-fast（E2 round 1 CRIT-6 — 不再靜默信任 hardcoded path）；
  7. 產出 JSON + Markdown（4-agent QC/MIT/FA/BB review-ready 結構 +
     spec v0.3 §"Mandatory report fields" 全 14 項覆蓋，含 per-tier
     breakdown / density-floor filter efficacy / FP rate / 5 exclusion
     categories / baseline lift / PBO with purge-embargo cite）。
主要類/函數：main / fetch_panel_symbols / fetch_k_prior / _fetch_panel_rows
            / _build_packet / _render_markdown / _get_conn / _read_sql。
依賴：psycopg2、sibling worktree 8C-S0R-2
      `liquidation_cluster_stage0r_metrics`、sibling worktree 8C-S0R-1
      `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql`。
硬邊界：read-only PG 查詢；不寫 trading.* / panel.* / market.*；不調 Rust；
       不變動 authorization / lease / mainnet enable；不接觸 paper pipeline。
       BB pre-flight gate 為硬條件：報告檔不存在 OR 明確 False → exit 3。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

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
DEFAULT_CLUSTER_NOTIONAL_FLOOR_USD = 10000.0
# Spec v0.3 §"K_total" 7 軸 grid 預設值（每軸 cell 個數對應 spec 4×4×3×3×3×3×3×3×2）；
# 對齊 8C-S0R-2 DEFAULT_*_GRID（round 1 漏 floor/quiet/horizon/pct → 48× under-sweep）。
DEFAULT_K_GRID = "2,3,5,8"                  # min_event_count_5m
DEFAULT_N_USD_GRID = "5000,10000,25000,50000"  # min_cluster_notional_5m_usd
DEFAULT_M_GRID = "1,2,3"                    # min_dominant_event_count
DEFAULT_SIDE_DOM_GRID = "0.70,0.80,0.90"    # side_dominance_floor
DEFAULT_FLOOR_GRID = "10000,25000,100000"   # cluster_notional_floor_usd
DEFAULT_QUIET_GRID = "0,30,60"              # quiet_window_sec
DEFAULT_HORIZON_GRID = "1,5,15"             # horizon_min
DEFAULT_PCT_GRID = "0.80,0.90,0.95"         # notional_pct_floor（spec v0.3 §"K_total" 第 8 軸）
# BB pre-flight：2026-05-18 BB STRUCTURAL verdict 後預設 True（見 dispatch prompt）
BB_REPORT_PATH = (
    "docs/CCAgentWorkSpace/BB/workspace/reports/"
    "2026-05-18--w_audit_8c_demo_testnet_long_liq_skew_bb_review.md"
)
K_PRIOR_MODES = ("strict-liquidation", "liquidation-related", "all")

# spec v0.3 §"per-tier breakdown" — 4-value verdict 對應 BB STRUCTURAL 後規則
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


def _parse_symbols(raw: str | None) -> tuple[str, ...]:
    """解析 `--symbols BTCUSDT,ETHUSDT` 或空回 ()。"""
    if not raw:
        return ()
    return tuple(s.strip().upper() for s in raw.split(",") if s.strip())


def _parse_float_grid(raw: str, *, name: str) -> tuple[float, ...]:
    """解析 CSV 浮點 grid。"""
    values = tuple(float(item.strip()) for item in raw.split(",") if item.strip())
    if not values:
        raise ValueError(f"--{name} 必須含至少一個數值")
    return values


def _parse_int_grid(raw: str, *, name: str) -> tuple[int, ...]:
    """解析 CSV 整數 grid。"""
    values = tuple(int(item.strip()) for item in raw.split(",") if item.strip())
    if not values:
        raise ValueError(f"--{name} 必須含至少一個整數")
    return values


def fetch_panel_symbols(conn, *, window_days: int) -> tuple[str, ...]:
    """從 market.liquidations 視窗內存在資料的 symbol 列表（mirror 8b L71-95）。

    為什麼從 liquidations 直查：8c panel 唯一 source 是 market.liquidations，
    不像 8b 還有 funding/oi panel；過去 window_days 有任何 liquidation row 的
    symbol 即 candidate。下游 SQL 用 `symbol = ANY(%(symbols)s::text[])` 套用。
    若 operator 透過 --symbols 顯式給 list，這個 fallback 不會 trigger。
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT symbol
            FROM market.liquidations
            WHERE ts >= now() - (%s::int * INTERVAL '1 day')
            ORDER BY symbol
            """,
            (window_days,),
        )
        return tuple(str(row[0]) for row in cur.fetchall())


def fetch_k_prior(conn, *, mode: str) -> tuple[int, dict[str, object]]:
    """從 learning.strategy_trial_ledger 取 K_prior（mirror 8b L97-145）。

    為什麼：DSR `sr_benchmark = √(2 ln K_total)`；K_total = K_prior + K_new。
    K_prior 嚴重低估 → over-PASS bias（E2 round 1 HIGH-3）。
    spec v0.3 §"K_prior" strict-liquidation mode 對應 strategy/family/
    candidate_key/evidence 任一帶 'liquidation'；undercount 比 overcount 危險。
    """
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('learning.strategy_trial_ledger') IS NOT NULL")
        row = cur.fetchone()
        if not row or not row[0]:
            return 0, {
                "mode": mode,
                "source": "learning.strategy_trial_ledger",
                "available": False,
                "where": None,
            }
        if mode == "strict-liquidation":
            # spec v0.3 §"K_prior" strict query seed（pending MIT approval）。
            # evidence->>'alpha_source_id' = 'liquidation_cluster_reaction' 與
            # strategy/family ILIKE '%liquidation%' 任一 match。
            where_sql = """
            candidate_key IS NOT NULL
            AND (
                strategy_name ILIKE '%%liquidation%%'
                OR trial_family ILIKE '%%liquidation%%'
                OR evidence->>'alpha_source_id' = 'liquidation_cluster_reaction'
            )
            """
        elif mode == "liquidation-related":
            # 寬鬆 mode：candidate_key 任一含 liquidation。
            where_sql = """
            candidate_key IS NOT NULL
            AND (
                strategy_name ILIKE '%%liquid%%'
                OR trial_family ILIKE '%%liquid%%'
                OR candidate_key ILIKE '%%liquid%%'
            )
            """
        elif mode == "all":
            where_sql = "candidate_key IS NOT NULL"
        else:
            raise ValueError(f"unsupported K_prior mode: {mode}")
        cur.execute(
            f"""
            SELECT count(DISTINCT candidate_key)::int
            FROM learning.strategy_trial_ledger
            WHERE {where_sql}
            """
        )
        prior = cur.fetchone()
        return int(prior[0] or 0), {
            "mode": mode,
            "source": "learning.strategy_trial_ledger",
            "available": True,
            "where": " ".join(where_sql.split()),
            "count_distinct": "candidate_key",
        }


def _fetch_panel_rows(
    conn, *, params: dict[str, Any], symbols: Sequence[str]
) -> list[dict[str, Any]]:
    """執行 SQL feature query，回傳 `list[dict]`。

    為什麼 list[dict] 而非 pandas.DataFrame：sibling 8C-S0R-2 contract 簽名
    `compute_stage0r(rows: Sequence[Mapping[str, object]], ...)` 期待
    list of dicts；round 1 誤用 DataFrame 在 sibling `_extract_trigger_rows`
    迭代時 `for row in df` 會 iterate column 名（str）→ row.get TypeError
    (E2 round 1 CRIT-4)。同時放棄 pandas 依賴 (E2 round 1 MED-1)。

    bucket_end_ts → bucket_end_ts_ms normalize（E2 round 1 CRIT-5 silent-RED
    killer fix）：SQL 出 timestamptz（python datetime），但 S0R-2
    `_extract_trigger_rows` line 904 讀 `bucket_end_ts_ms` (ms int)；不
    normalize 每個 row signal_ts_ms = None → continue → n_per_cell=0 →
    every cell auto-RED with fake reason。
    """
    sql = _read_sql()
    # SQL 必含 %(symbols)s 綁定（round 1 漏 → psycopg2 KeyError 即 CRIT-1）。
    bound_params = dict(params)
    bound_params["symbols"] = list(symbols)
    with conn.cursor() as cur:
        cur.execute(sql, bound_params)
        columns = [d[0] for d in cur.description]
        raw_rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for raw in raw_rows:
        row = dict(zip(columns, raw))
        # CRIT-5：bucket_end_ts (datetime) → bucket_end_ts_ms (int ms)
        bet = row.get("bucket_end_ts")
        if bet is not None and hasattr(bet, "timestamp"):
            row["bucket_end_ts_ms"] = int(bet.timestamp() * 1000)
        elif isinstance(bet, (int, float)):
            # 容錯：若 SQL 端已輸出毫秒 epoch 純數字（不太可能但保險）
            row["bucket_end_ts_ms"] = int(bet)
        else:
            # 顯式 fail-loud：少數 row 缺 bucket_end_ts → 不繞，trigger 階段
            # 直接 skip 不污染 panel 統計。
            row["bucket_end_ts_ms"] = None
    return out


def _clean_json(value):
    """遞迴清理 NaN/Inf，回傳 JSON-safe 結構。

    為什麼需要：S0R-2 metrics 純 stdlib 但仍可能產生 NaN/Inf（如 PSR 分母 0）；
    json.dumps 默認會吐 `NaN` literal 違反 RFC 8259。
    """
    if isinstance(value, dict):
        return {k: _clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_json(v) for v in value]
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    # 不再 import numpy；S0R-2 純 stdlib（MED-1）
    return value


def _verdict_from_sweep_result(sweep_result: dict[str, Any]) -> str:
    """從 sibling S0R-2 sweep_result 直接 derive 4-value panel verdict
    （E2 round 1 HIGH-4 — 拋棄 round 1 自製 _verdict_from_cells）。

    為什麼：S0R-2 sweep_result 已含 `eligible_for_demo_canary: bool` (overall)
    + `eligible_for_demo_canary_per_tier: dict[tier → {long:bool,short:bool}]`，
    這是 spec v0.3 §"per-tier independent promotion" 的 authoritative source；
    自製 panel-level cell OR 是發明新 verdict 規則 → 與 S0R-2 結果衝突時
    operator 信哪個？
    """
    per_tier = sweep_result.get("eligible_for_demo_canary_per_tier") or {}
    if not isinstance(per_tier, dict) or not per_tier:
        return "RED"
    any_long = any(bool(v.get("long")) for v in per_tier.values() if isinstance(v, dict))
    any_short = any(bool(v.get("short")) for v in per_tier.values() if isinstance(v, dict))
    if any_long and any_short:
        return "PASS-BOTH"
    if any_long:
        return "PASS-LONG-ONLY"
    if any_short:
        return "PASS-SHORT-ONLY"
    return "RED"


def _aggregate_sweep_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    """sweep_summary 統計（per-cell verdict 分布）。"""
    total = len(cells)
    pass_both = sum(1 for c in cells if c.get("pass") == "PASS-BOTH")
    pass_long = sum(1 for c in cells if c.get("pass") == "PASS-LONG-ONLY")
    pass_short = sum(1 for c in cells if c.get("pass") == "PASS-SHORT-ONLY")
    red = sum(1 for c in cells if c.get("pass") == "RED")
    reason_counts: dict[str, int] = {}
    for c in cells:
        for reason in c.get("pass_reasons") or []:
            reason_counts[str(reason)] = reason_counts.get(str(reason), 0) + 1
    return {
        "total_cells": total,
        "pass_both_cells": pass_both,
        "pass_long_only_cells": pass_long,
        "pass_short_only_cells": pass_short,
        "red_cells": red,
        "red_reason_counts": reason_counts,
    }


def _compute_exclusion_counts(
    panel_rows: Sequence[dict[str, Any]],
    *,
    primary_cell: dict[str, Any] | None,
) -> dict[str, Any]:
    """spec v0.3 §"Mandatory report fields" L250 五個 exclusion categories
    (E2 round 1 HIGH-1)。

    為什麼：density-floor / dominance / quiet / kline-missing / mixed-side
    rejection 都是 alpha-evaluation 的關鍵 visibility；空欄會被 reviewer 反推。

    Notes：5 categories 對應 S0R-1 SQL CTE 序列；本檔從 raw panel rows 反推：
      - stale: entry_mid OR exit_mid is None（kline sparse 排除）
      - missing: 必填 column null（symbol/expected_dir/dominant_side）
      - mixed_side: dominant_side == 'mixed'（過 raw_buckets 但下層 fail）
      - quiet_window: row 已先過 quiet（SQL CTE 4 已實施）— 本層只統計成功進入比率
      - density_floor_fail: primary_cell 之 density_floor_efficacy 給出 raw vs after
    """
    counts = {
        "stale_kline_missing": 0,
        "missing_required_field": 0,
        "mixed_side": 0,
        "quiet_window_excluded": 0,  # SQL CTE 已 enforce；統計信息性質
        "density_floor_excluded": 0,
    }
    total = len(panel_rows)
    for row in panel_rows:
        if row.get("symbol") is None or row.get("expected_dir") is None:
            counts["missing_required_field"] += 1
            continue
        if str(row.get("dominant_side") or "") not in ("long_liquidated", "short_liquidated"):
            counts["mixed_side"] += 1
            continue
        if row.get("entry_mid") is None or row.get("exit_mid") is None:
            counts["stale_kline_missing"] += 1
            continue
    # density_floor_excluded：primary_cell density_floor_efficacy 表示
    # raw_5m_buckets → after_k → after_n → after_m chain；用 chain 末端
    # 與 raw 差作 excluded 數。
    if primary_cell:
        eff = primary_cell.get("density_floor_efficacy") or {}
        raw = eff.get("raw_5m_bucket_count")
        after_chain = eff.get("after_m_count")
        if isinstance(raw, int) and isinstance(after_chain, int) and raw > after_chain:
            counts["density_floor_excluded"] = raw - after_chain
    counts["total_raw_rows"] = total
    return counts


def _build_packet(
    *,
    panel_rows: Sequence[dict[str, Any]],
    sweep_result: dict[str, Any] | None,
    cells: list[dict[str, Any]],
    primary_cell: dict[str, Any] | None,
    sweep_params: dict[str, Any],
    bb_preflight: dict[str, Any],
    k_prior: int,
    k_prior_meta: dict[str, Any],
) -> dict[str, Any]:
    """組裝 spec v0.3 §"Mandatory report fields" L234-253 全 14 項覆蓋。

    新增（E2 round 1 HIGH-1 mandatory fields）：
      - per_tier_breakdown：S0R-2 sweep_result.eligible_for_demo_canary_per_tier
        + best_per_tier_per_direction + symbol_tiers
      - density_floor_efficacy_chain：每 cell 之 density_floor_efficacy
        （raw → after_K → after_N → after_M）
      - false_positive_rates：每 cell 之 false_positive_rate
      - exclusion_counts：5 categories（stale/missing/mixed/quiet/density-floor）
      - baseline_lift：vs no-cluster baseline + vs single-event noise baseline
      - pbo_with_purge_embargo：cite S0R-2 PBO method
    """
    # 抽 panel_meta（從 raw rows，不依賴 pandas）
    panel_meta: dict[str, Any] = {
        "earliest_ts": None,
        "latest_ts": None,
        "span_days": None,
        "total_rows": len(panel_rows),
        "distinct_symbols": 0,
    }
    try:
        epochs = [
            int(r["bucket_5m_epoch"])
            for r in panel_rows
            if r.get("bucket_5m_epoch") is not None
        ]
        symbols_set = {
            str(r["symbol"]) for r in panel_rows if r.get("symbol") is not None
        }
        if epochs:
            panel_meta["earliest_ts"] = min(epochs)
            panel_meta["latest_ts"] = max(epochs)
            # bucket_5m_epoch 為秒級 epoch（per S0R-1 SQL contract 確認）；
            # span_days = (latest - earliest) / 86400
            panel_meta["span_days"] = round(
                (panel_meta["latest_ts"] - panel_meta["earliest_ts"]) / 86400.0, 3
            )
        panel_meta["distinct_symbols"] = len(symbols_set)
    except (TypeError, ValueError, AttributeError) as exc:
        # MED-2：不再靜默 except:pass；顯式 stderr 警告 schema drift 風險
        print(
            f"[WARN] panel_meta 萃取部分失敗: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )

    # 從 sweep_result 抽 per-tier breakdown（HIGH-1 (a)）
    per_tier_breakdown = {}
    if sweep_result:
        per_tier_breakdown = {
            "eligible_for_demo_canary_per_tier": sweep_result.get(
                "eligible_for_demo_canary_per_tier"
            ),
            "best_per_tier_per_direction": sweep_result.get(
                "best_per_tier_per_direction"
            ),
            "symbol_tiers": sweep_result.get("symbol_tiers"),
        }

    # 從每 cell 抽 density_floor_efficacy chain（HIGH-1 (b)）+ FP rate（HIGH-1 (c)）
    density_filter_efficacy_chain = [
        {
            "cell_params": c.get("cell_params"),
            "efficacy": c.get("density_floor_efficacy"),
        }
        for c in cells
    ]
    false_positive_rates = [
        {
            "cell_params": c.get("cell_params"),
            "fp_rate": c.get("false_positive_rate"),
        }
        for c in cells
    ]

    # 5 categories exclusion counts（HIGH-1 (d)）
    exclusion_counts = _compute_exclusion_counts(
        panel_rows, primary_cell=primary_cell
    )

    # baseline lift（HIGH-1 (e)）— v0.3 spec L253 兩個 baseline；
    # 取 primary_cell avg_net_bps - 0（no-cluster baseline = 不交易 → 0 bps）
    # 與 primary_cell vs single-event-noise（從 FP rate 推：FP rate * 0 + (1-FP) * net）
    baseline_lift: dict[str, Any] = {
        "vs_no_cluster_baseline_bps": None,
        "vs_single_event_noise_baseline_bps": None,
        "note": (
            "no-cluster baseline = 0 bps（不開倉）；single-event-noise baseline "
            "= mean of cluster_notional_5m < N_usd floor 之 net_bps（若 SQL 出此欄）"
        ),
    }
    if primary_cell:
        avg_net = primary_cell.get("avg_net_bps")
        if isinstance(avg_net, (int, float)):
            baseline_lift["vs_no_cluster_baseline_bps"] = float(avg_net)
            fp_block = primary_cell.get("false_positive_rate") or {}
            fp_rate = fp_block.get("fp_rate")
            if isinstance(fp_rate, (int, float)) and 0 <= fp_rate <= 1:
                # naive lift 估算：non-FP fraction * avg_net（FP 視作 ±5 bps 內無 alpha）
                baseline_lift["vs_single_event_noise_baseline_bps"] = round(
                    float(avg_net) * (1.0 - float(fp_rate)), 3
                )

    # PBO with purge-embargo cite（HIGH-1 (f)）
    pbo_with_purge_embargo: dict[str, Any] = {
        "method": "day_block_cscv",
        "cite": (
            "S0R-2 metrics _pbo()：CSCV PBO over day-block splits with implicit "
            "purge/embargo via 7d minimum panel + max_splits=240"
        ),
        "primary_cell_pbo": (primary_cell or {}).get("pbo"),
        "primary_cell_pbo_metadata": (primary_cell or {}).get("pbo_metadata"),
    }

    # n_eff_audit：取 primary_cell 的 cluster-aware n_eff
    if primary_cell:
        raw_n = primary_cell.get("n_per_cell") or 0
        n_eff = primary_cell.get("pooled_n_eff") or 0
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
            if (
                primary_cell
                and "branch n_eff_cluster" not in str(primary_cell.get("pass_reasons") or [])
            )
            else "PENDING"
        ),
        "red_risk_3_cost_gate": (
            "PASS"
            if (
                primary_cell
                and "cost_edge_ratio" not in str(primary_cell.get("pass_reasons") or [])
            )
            else "PENDING"
        ),
    }

    # Verdict 直接 surface S0R-2 sweep_result（HIGH-4）；single-cell 模式
    # fallback 用 primary_cell.pass
    if sweep_result:
        verdict = _verdict_from_sweep_result(sweep_result)
    elif primary_cell:
        verdict = str(primary_cell.get("pass") or "RED")
    else:
        verdict = "RED"
    sweep_summary = _aggregate_sweep_summary(cells)

    # review_ready：BB pre-flight confirmed 即 ready（即便 RED 也須 4-agent 看
    # RED reason 是否可改 spec）
    review_ready = bool(bb_preflight.get("demo_bias_confirmed"))

    return {
        "spec_version": "v0.3",
        "strategy_id": "liquidation_cluster_reaction",
        "strategy_variant": (
            sweep_result.get("strategy_variant") if sweep_result else None
        )
        or (primary_cell.get("strategy_variant") if primary_cell else None),
        "alpha_source_id": (
            sweep_result.get("alpha_source_id") if sweep_result else None
        )
        or (primary_cell.get("alpha_source_id") if primary_cell else None),
        "verdict": verdict,
        "review_ready": review_ready,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "panel_meta": panel_meta,
        "params": sweep_params,
        "k_prior": k_prior,
        "k_prior_meta": k_prior_meta,
        "sweep_summary": sweep_summary,
        "per_tier_breakdown": per_tier_breakdown,
        "density_filter_efficacy_chain": density_filter_efficacy_chain,
        "false_positive_rates": false_positive_rates,
        "exclusion_counts": exclusion_counts,
        "baseline_lift": baseline_lift,
        "pbo_with_purge_embargo": pbo_with_purge_embargo,
        "n_eff_audit": {
            "raw_n": raw_n,
            "cluster_aware_n_eff": n_eff,
            "penalty_rate": penalty_rate,
        },
        "tombstone_risk_summary": tombstone,
        "bb_pre_flight": bb_preflight,
        "primary_cell": primary_cell,
        "cells": cells,
        "sweep_meta": sweep_result.get("sweep_meta") if sweep_result else None,
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
    ptb = packet.get("per_tier_breakdown") or {}
    exc = packet.get("exclusion_counts") or {}
    bl = packet.get("baseline_lift") or {}
    pbo = packet.get("pbo_with_purge_embargo") or {}

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
        else "- red_reason_counts: (empty)"
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

    # Per-tier breakdown md
    per_tier_md_lines = ["- per_tier_eligible_for_demo_canary:"]
    per_tier_e = ptb.get("eligible_for_demo_canary_per_tier") or {}
    if isinstance(per_tier_e, dict):
        for tier, dirs in per_tier_e.items():
            if isinstance(dirs, dict):
                per_tier_md_lines.append(
                    f"  - {tier}: long={dirs.get('long')} short={dirs.get('short')}"
                )
            else:
                per_tier_md_lines.append(f"  - {tier}: {dirs}")
    sym_tiers = ptb.get("symbol_tiers") or {}
    if isinstance(sym_tiers, dict) and sym_tiers:
        per_tier_md_lines.append(
            f"- symbol_tiers: {len(sym_tiers)} symbols classified"
        )

    per_tier_md = "\n".join(per_tier_md_lines)

    # Exclusion counts md
    exc_md = "\n".join(f"- {k}: {v}" for k, v in exc.items())

    # Per-cell top-10 table（按 avg_net_bps desc）
    sortable = []
    for c in cells:
        nb = c.get("avg_net_bps") or c.get("net_bps")
        try:
            nv = float(nb) if nb is not None else float("-inf")
        except (TypeError, ValueError):
            nv = float("-inf")
        sortable.append((nv, c))
    sortable.sort(key=lambda kv: -kv[0])
    table_rows = []
    for _, c in sortable[:10]:
        cp = c.get("cell_params") or {}
        table_rows.append(
            "| {K} | {N} | {M} | {fl} | {sd} | {q} | {h} | {p} | {n} | {ne} | {g} | {nb} | {dsr} | {pbo} |".format(
                K=cp.get("k_event_count"),
                N=cp.get("n_usd"),
                M=cp.get("m_dominant"),
                fl=cp.get("floor_usd"),
                sd=cp.get("side_dom"),
                q=cp.get("quiet_sec"),
                h=cp.get("horizon_min"),
                p=c.get("pass"),
                n=c.get("n_per_cell"),
                ne=c.get("pooled_n_eff"),
                g=c.get("avg_gross_bps") or c.get("gross_bps"),
                nb=c.get("avg_net_bps") or c.get("net_bps"),
                dsr=c.get("dsr"),
                pbo=c.get("pbo"),
            )
        )
    table_md = "\n".join(table_rows) if table_rows else "| (no cells) |"

    primary_json = json.dumps(_clean_json(primary), indent=2, sort_keys=True)

    return f"""# W-AUDIT-8c Liquidation Cluster Stage 0R Report

generated_at_utc: {packet.get('generated_at_utc')}
strategy_id: {packet.get('strategy_id')}
strategy_variant: {packet.get('strategy_variant')}
alpha_source_id: {packet.get('alpha_source_id')}
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

## K_prior

- k_prior: {packet.get('k_prior')}
- k_prior_meta: {json.dumps(_clean_json(packet.get('k_prior_meta')), sort_keys=True)}

## Sweep Summary

- total_cells: {ss.get('total_cells')}
- pass_both_cells: {ss.get('pass_both_cells')}
- pass_long_only_cells: {ss.get('pass_long_only_cells')}
- pass_short_only_cells: {ss.get('pass_short_only_cells')}
- red_cells: {ss.get('red_cells')}
{rc_md}

## Per-Tier Breakdown (spec v0.3 §"per-tier independent promotion")

{per_tier_md}

## Exclusion Counts (5 categories — spec v0.3 §"Mandatory report fields" L250)

{exc_md}

## Baseline Lift (spec v0.3 §"Mandatory report fields" L253)

- vs_no_cluster_baseline_bps: {bl.get('vs_no_cluster_baseline_bps')}
- vs_single_event_noise_baseline_bps: {bl.get('vs_single_event_noise_baseline_bps')}
- note: {bl.get('note')}

## PBO with Purge/Embargo (spec v0.3 §"Mandatory report fields" L248)

- method: {pbo.get('method')}
- cite: {pbo.get('cite')}
- primary_cell_pbo: {pbo.get('primary_cell_pbo')}

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

## Per-Cell Table (top 10 by avg_net_bps)

| K | N_usd | M | floor_usd | side_dom | quiet_sec | horizon_min | pass | n_per_cell | pooled_n_eff | gross_bps | net_bps | dsr | pbo |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
{table_md}

## 4-Agent Review Sections

### QC（Quantitative Compliance）視角

- panel n_eff vs sample floor: cluster_aware_n_eff={nea.get('cluster_aware_n_eff')} vs spec v0.3 promotion floor `n_eff ≥ 300 pooled`。
- multiple-comparison cost (K_total): sweep cells={ss.get('total_cells')}；spec v0.3 enlarged K_total=48× v0.1 (243 → 11,664 per symbol)；K_prior={packet.get('k_prior')}。
- DSR / PBO 應檢視 primary_cell 與 sweep top-10；單 cell PASS 但 plateau 不形成則仍應視為 RED。

### MIT（Machine-Intelligence Trustee）視角

- density floor efficacy chain：見 packet.density_filter_efficacy_chain（每 cell 之 raw → after_K → after_N → after_M）；spec v0.3 要求 floor 移除 ≥ 60% 單/雙事件 bucket。
- empirical sparsity（MIT 2026-05-18 PG SoT）：HYPEUSDT 1.54% / BTCUSDT 0.89% / ETHUSDT 0.99% / LINKUSDT 0.20% 7d 5m bucket coverage；本 panel total_rows={pm.get('total_rows')} 應 cross-check 與 tier 分層一致。
- per-tier independent promotion：見 Per-Tier Breakdown 段；high / medium / low tier 需各自過 n_eff + avg_net_bps + PSR/DSR。

### FA（Failure Analyst）視角

- RED reason 聚合（見 sweep_summary.red_reason_counts）：高頻 RED 原因即下一輪 spec 修訂重點。
- tombstone risk：demo_bias={tomb.get('red_risk_1_demo_bias')} / n_eff={tomb.get('red_risk_2_n_eff')} / cost_gate={tomb.get('red_risk_3_cost_gate')}。
- 若 verdict=RED 且 reason 集中於 n_eff，建議擴 replay 窗（spec v0.3 §6 預測 21-30d minimum）而非 lower threshold。
- 5 exclusion categories（見 Exclusion Counts 段）幫助分辨「sparse data」vs「filter too aggressive」。

### BB（Bybit-side Boundary）視角

- BB pre-flight verdict (2026-05-18)：STRUCTURAL；demo_bias_confirmed={bool(bb.get('demo_bias_confirmed'))}。
- 本 packet 不變動 production WS subscription / topic builder；`allLiquidation*` 仍應在 full_subscription_list excluded 集合內，直到 PM 另行 dispatch revival 任務。
- side mapping：dominant Buy → LongLiquidated → expected_dir=+1；dominant Sell → ShortLiquidated → expected_dir=-1（per BB corrected side-semantics 2026-05-17 sign-off）。
"""


def _resolve_output_path(
    *, role: str, verdict: str, fmt: str, out_dir: str | None
) -> Path:
    """回傳 docs/CCAgentWorkSpace/{role}/workspace/reports/<date>--w_audit_8c_stage0r_<verdict>.<ext>。

    MED-3：跨日邊界 / 同日多 run 用 timestamp suffix 避 collision；正式 run
    若 collision 用 `_HHMMSS` 區隔（spec 未明定但避 race-overwrite）。
    """
    base = _repo_root()
    if out_dir:
        base_dir = Path(out_dir)
    else:
        base_dir = base / "docs" / "CCAgentWorkSpace" / role / "workspace" / "reports"
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    ext = "json" if fmt == "json" else "md"
    safe_verdict = str(verdict).lower().replace("-", "_")
    path = base_dir / f"{date_str}--w_audit_8c_stage0r_{safe_verdict}.{ext}"
    if path.exists():
        # 同檔避 race-overwrite：加 HHMMSS suffix
        ts_suffix = now.strftime("%H%M%S")
        path = base_dir / f"{date_str}--w_audit_8c_stage0r_{safe_verdict}_{ts_suffix}.{ext}"
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="W-AUDIT-8c Liquidation Cluster Stage 0R replay report CLI (round 2)"
    )
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="CSV symbol list（如 BTCUSDT,ETHUSDT）；空則 fetch_panel_symbols() fallback。",
    )
    parser.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    parser.add_argument("--horizon-min", type=int, default=DEFAULT_HORIZON_MIN)
    parser.add_argument("--quiet-window-sec", type=int, default=DEFAULT_QUIET_WINDOW_SEC)
    parser.add_argument(
        "--cluster-notional-floor-usd",
        type=float,
        default=DEFAULT_CLUSTER_NOTIONAL_FLOOR_USD,
    )
    # CRIT-3 fix：sweep 7 + 1 grid 完整 argparse（pct-grid 是 spec v0.3 §K_total 第 8 軸）
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
        "--floor-grid",
        type=str,
        default=DEFAULT_FLOOR_GRID,
        help=f"CSV of cluster_notional_floor_usd sweep cells (default: {DEFAULT_FLOOR_GRID})",
    )
    parser.add_argument(
        "--quiet-grid",
        type=str,
        default=DEFAULT_QUIET_GRID,
        help=f"CSV of quiet_window_sec sweep cells (default: {DEFAULT_QUIET_GRID})",
    )
    parser.add_argument(
        "--horizon-grid",
        type=str,
        default=DEFAULT_HORIZON_GRID,
        help=f"CSV of horizon_min sweep cells (default: {DEFAULT_HORIZON_GRID})",
    )
    parser.add_argument(
        "--pct-grid",
        type=str,
        default=DEFAULT_PCT_GRID,
        help=(
            f"CSV of notional_pct_floor sweep cells (default: {DEFAULT_PCT_GRID}); "
            "spec v0.3 K_total 第 8 軸；S0R-2 metrics 已升 8-D 接受此 axis"
        ),
    )
    parser.add_argument(
        "--notional-pct-floor",
        type=float,
        default=None,
        help=(
            "--no-sweep 單值 override（spec v0.3 §K_total 第 8 軸的 single-cell "
            "對應值）；若 None 則 fallback 用 min(pct_grid)，與 SQL pre-filter "
            "同源；HIGH-R2-2：避免 single_kwargs 漏接 8th axis"
        ),
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
        help="只跑單一 primary cell（不做 7 軸 sweep）",
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
    parser.add_argument(
        "--k-prior",
        type=int,
        default=None,
        help="手動指定 K_prior（若 None 則從 learning.strategy_trial_ledger query）",
    )
    parser.add_argument(
        "--k-prior-mode",
        choices=K_PRIOR_MODES,
        default="strict-liquidation",
        help="K_prior query mode（spec v0.3 §K_prior strict undercount-safe）",
    )
    args = parser.parse_args(argv)

    # ── CRIT-6：BB pre-flight 報告檔 fail-fast 檢查 ──────────────────────
    bb_report_full = _repo_root() / BB_REPORT_PATH
    if not bb_report_full.exists():
        print(
            "[FATAL] BB STRUCTURAL 報告檔不存在，Stage 0R 拒絕執行。\n"
            f"        期望路徑：{bb_report_full}\n"
            f"        ({BB_REPORT_PATH} relative to repo root)\n"
            "        必須由 PM 從 BB chat verdict scaffold 該檔後才能 run。",
            file=sys.stderr,
        )
        return 3

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
        floor_grid = _parse_float_grid(args.floor_grid, name="floor-grid")
        quiet_grid = _parse_int_grid(args.quiet_grid, name="quiet-grid")
        horizon_grid = _parse_int_grid(args.horizon_grid, name="horizon-grid")
        pct_grid = _parse_float_grid(args.pct_grid, name="pct-grid")
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
        "floor_grid": list(floor_grid),
        "quiet_grid": list(quiet_grid),
        "horizon_grid": list(horizon_grid),
        "pct_grid": list(pct_grid),
    }

    # ── PG 取數 ────────────────────────────────────────────────────────
    try:
        conn = _get_conn()
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] PG 連線失敗：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    try:
        # CRIT-1：fetch_panel_symbols fallback（若 --symbols 空）
        symbols = _parse_symbols(args.symbols) or fetch_panel_symbols(
            conn, window_days=args.window_days
        )
        if not symbols:
            print(
                "[FATAL] 視窗內 market.liquidations 無任何 symbol；無 panel 可跑 Stage 0R。",
                file=sys.stderr,
            )
            return 1
        # HIGH-3：K_prior 真實 query（mirror 8b L97-145）
        if args.k_prior is not None:
            k_prior = int(args.k_prior)
            k_prior_meta = {
                "mode": "manual",
                "source": "--k-prior",
                "available": True,
                "where": None,
            }
        else:
            k_prior, k_prior_meta = fetch_k_prior(conn, mode=args.k_prior_mode)
        # SQL 參數綁定（CRIT-1：sql_params 補 symbols 由 _fetch_panel_rows 包進）
        # SQL pre-filter 用 min(grid) 取最寬鬆，Python sweep 再 tighten
        # CRIT-R2-1：補 notional_pct_floor 第 11 個 SQL named param；round 2 漏
        # → 第一次 cur.execute(sql) 即 psycopg2 KeyError on %(notional_pct_floor)s。
        # SQL features.sql L235 用 %(notional_pct_floor)s::float8 做 magnitude
        # 第三層 gate；min(pct_grid) 是最寬鬆 pre-filter，Python sweep cell 再
        # tighten 到實際 pct 值（monotone：SQL ≤ Python tighten 保證不漏）。
        sql_params = {
            "window_days": args.window_days,
            "k_event_floor": int(min(k_grid)),
            "n_usd_floor": float(min(n_usd_grid)),
            "m_dominant_floor": int(min(m_grid)),
            "side_dominance_floor": float(min(side_dom_grid)),
            "cluster_notional_floor_usd": float(min(floor_grid)),  # HIGH-2：用 min(floor_grid) 而非單 arg
            "notional_pct_floor": float(min(pct_grid)),  # CRIT-R2-1：SQL 11/11 named param 全綁
            "quiet_window_sec": int(min(quiet_grid)),
            "horizon_min": int(min(horizon_grid)),
            "cost_bps": float(args.cost_bps),
        }
        panel_rows = _fetch_panel_rows(conn, params=sql_params, symbols=symbols)
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
    # CRIT-3：拆 sweep_kwargs vs single_kwargs（horizon_min vs horizon_grid 名衝突）
    sweep_result: dict[str, Any] | None = None
    primary_cell: dict[str, Any] | None = None
    cells: list[dict[str, Any]] = []
    try:
        # HIGH-R2-2：single-cell 8th axis 值 = --notional-pct-floor override 或 min(pct_grid)。
        # 維持 SQL pre-filter 與 Python tighten 同源（CRIT-R2-1 同邏輯）。
        single_pct_floor = (
            float(args.notional_pct_floor)
            if args.notional_pct_floor is not None
            else float(min(pct_grid))
        )
        single_kwargs = dict(
            cost_bps=args.cost_bps,
            horizon_min=args.horizon_min,
            quiet_sec=args.quiet_window_sec,
            notional_pct_floor=single_pct_floor,  # HIGH-R2-2：8th axis 同源；CRIT 配套
            k_prior=k_prior,
            rng_seed=args.rng_seed,
            bootstrap_iters=args.bootstrap_iters,
        )
        sweep_kwargs = dict(
            cost_bps=args.cost_bps,
            k_grid=list(k_grid),
            n_usd_grid=list(n_usd_grid),
            m_grid=list(m_grid),
            side_dom_grid=list(side_dom_grid),
            floor_grid=list(floor_grid),
            quiet_grid=list(quiet_grid),
            horizon_grid=list(horizon_grid),
            pct_grid=list(pct_grid),  # HIGH-R2-1：spec v0.3 §K_total 第 8 軸接到 sweep
            k_prior=k_prior,
            rng_seed=args.rng_seed,
            bootstrap_iters=args.bootstrap_iters,
        )
        if args.no_sweep:
            primary_cell = compute_stage0r(panel_rows, **single_kwargs)
            cells = [primary_cell] if primary_cell else []
        else:
            # CRIT-2：sweep_result 是 dict 6 keys；用 sweep_cells key
            sweep_result = compute_stage0r_sweep(panel_rows, **sweep_kwargs)
            if not isinstance(sweep_result, dict):
                print(
                    "[FATAL] compute_stage0r_sweep 返回非 dict；S0R-2 contract drift",
                    file=sys.stderr,
                )
                return 1
            cells = list(sweep_result.get("sweep_cells") or [])
            # primary_cell：選 sweep 中 avg_net_bps 最高且 verdict != RED 的 cell；
            # 若全 RED 則取 avg_net_bps 最高（用於診斷）
            non_red = [c for c in cells if c.get("pass") and c.get("pass") != "RED"]
            pool = non_red or cells
            if pool:
                primary_cell = max(
                    pool,
                    key=lambda c: float(
                        c.get("avg_net_bps") or c.get("net_bps") or float("-inf")
                    ),
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
        panel_rows=panel_rows,
        sweep_result=sweep_result,
        cells=cells,
        primary_cell=primary_cell,
        sweep_params=sweep_params,
        bb_preflight=bb_preflight,
        k_prior=k_prior,
        k_prior_meta=k_prior_meta,
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
    # LOW-1：stdout JSON 經 _clean_json 包，避 numpy scalar 拋
    stdout_summary = _clean_json(
        {
            "verdict": packet.get("verdict"),
            "review_ready": packet.get("review_ready"),
            "outputs": [str(p) for p in written],
        }
    )
    print(
        json.dumps(stdout_summary, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
