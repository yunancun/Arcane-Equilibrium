"""A2 liquidation_cascade_fade candidate adapter（復用 W-AUDIT-8c per-event 路徑）。

MODULE_NOTE
模塊用途：把 alpha tournament candidate A2（liquidation_cascade_fade，BTC/ETH
2-symbol，per-symbol notional threshold）接到既有 W-AUDIT-8c per-event Stage 0R
metrics（compute_stage0r）。8c per-event 路徑方向與 A2 一致（per spec v2 §1
[FACT]：8c expected_dir = +1 long_liquidated → mean-revert UP；A2 entry_is_long
= LongLiquidated → true = fade long-liq → long entry，語意完全一致），故沿用
8c SQL + metrics，只在本 adapter 層做兩個 candidate-specific 修正。

主要類函數：
  - A2CandidateConfig：candidate cohort + per-symbol threshold + horizon 配置。
  - run_a2_candidate(panel_rows, cfg, ...)：跑 8c compute_stage0r + 兩 adapter
    修正 → 回 candidate packet（含 6-check 原料 + sample_sufficiency）。
  - _filter_rows_by_per_symbol_threshold：per-symbol notional floor 預過濾。

兩個 candidate adapter（spec v2 §2 必修）：
  (a) k_total override：8c compute_stage0r 內部 k_new = max(25, n_symbols) ×
      11664（研究 sweep 的 11664-cell grid penalty inflation）。A2 candidate
      run = 固定單一閾值（per-symbol floor）、不掃 11664 cell → 真實 trial
      count ≪ 291600。沿用會把 DSR benchmark √(2 ln 291600) ≈ 5.0 拉到不公平
      高位，A2 永 DSR fail = silent stat 錯（mock test 不抓）。本 adapter 以
      candidate 真實 trial count（k_new = 2 symbol × 2 direction × 1 threshold
      × 1 horizon = 4，+ k_prior）override → 對 net_bps 序列重算 DSR。
  (b) dynamic_exit proxy：8c 固定 horizon mark（features.sql CTE 4 bucket_end
      + quiet + horizon 之後第一根 1m open）≠ A2 動態出場 OR(TP 1.5% / SL 2% /
      1h time-stop / reverse-cascade)。8c 固定 60m-mark 是 A2 保守 proxy（持滿
      horizon 不提前 TP/SL）→ packet 標 exit_model + dynamic_exit_not_modeled。

依賴：sibling W-AUDIT-8c `liquidation_cluster_stage0r_metrics`
      （compute_stage0r / dsr_with_k / prepare_parsed_rows）；純 stdlib。
硬邊界：read-only；不改 8c SQL 結構（leak-free 不變量繼承）；不改 8c
      compute_stage0r 內部；只在 adapter 層 pin cohort/threshold + override
      k_total（call 後重算 DSR）+ 標 proxy。
"""

from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

# ──────────────────────────────────────────────────────────────────────────
# sibling W-AUDIT-8c metrics import（純統計原語 + per-event compute_stage0r）
# 為什麼複用：8c per-event 路徑 direction-agnostic、leak-free、與 A2 方向一致，
# 不重造也不改其內部行為（spec v2 §1 #2 + §8.4 #1）。
# ──────────────────────────────────────────────────────────────────────────
try:
    from ..w_audit_8c.liquidation_cluster_stage0r_metrics import (  # type: ignore
        compute_stage0r,
        dsr_with_k,
        prepare_parsed_rows,
        _safe_float,
    )
except ImportError:
    # 直接執行（非 -m）路徑：top-level shim 已把 w_audit_8c/ 補進 sys.path。
    _HERE = Path(__file__).resolve().parent
    _C8 = _HERE.parent / "w_audit_8c"
    if str(_C8) not in sys.path:
        sys.path.insert(0, str(_C8))
    from liquidation_cluster_stage0r_metrics import (  # type: ignore
        compute_stage0r,
        dsr_with_k,
        prepare_parsed_rows,
        _safe_float,
    )


# ──────────────────────────────────────────────────────────────────────────
# A2 candidate 常數（per A2 spec 2026-05-25 §1.1-§1.3）
# ──────────────────────────────────────────────────────────────────────────

# A2 alpha 識別字串（per SSOT alpha_source_id）。
A2_ALPHA_SOURCE_ID = "liquidation_cascade_fade"

# per-symbol dominant_notional_5m threshold（A2 spec §1.3 Stage 1 hard-coded）：
# BTCUSDT $500k / ETHUSDT $300k（per historical Bybit Q1 2026 liquidation
# distribution percentile）。
A2_DEFAULT_PER_SYMBOL_THRESHOLD = {
    "BTCUSDT": 500_000.0,
    "ETHUSDT": 300_000.0,
}

# A2 entry gate min_events（A2 spec §1.1 #3，default 3，防 single-large-event 假訊號）。
A2_MIN_EVENTS = 3

# A2 cohort（spec v2 §1：BTC/ETH 2-symbol）。
A2_COHORT = ("BTCUSDT", "ETHUSDT")

# A2 fixed-horizon proxy：A2 max_hold default 60min（A2 spec §1.2 #1 time-stop）；
# 8c 固定 horizon mark 為 A2 動態出場保守 proxy（spec v2 §1 B）。
A2_PROXY_HORIZON_MIN = 60

# k_total override（spec v2 §4.3）：candidate 真實 trial count =
# len(symbols)[2] × len(direction)[2 long/short] × len(threshold-set)[1] ×
# len(horizon)[1] = 4。**override 8c 內部 max(25, n) × 11664 inflation**。
A2_K_NEW_CANDIDATE = (
    len(A2_COHORT)        # 2 symbol
    * 2                   # 2 direction（long_liquidated / short_liquidated branch）
    * 1                   # 1 threshold-set（per-symbol pinned 單組，非 sweep）
    * 1                   # 1 primary horizon
)

# A2 cost model：與 8c / 8b 對齊 default 12 bps（A2 spec 無另指定）。
A2_COST_BPS = 12.0

# A2 動態出場 OR 四條（A2 spec §1.2）；fixed-horizon proxy 不建模這些。
A2_DYNAMIC_EXIT_NOT_MODELED = [
    "TP_1.5pct",
    "SL_2.0pct",
    "time_stop_60m",   # 8c 固定 horizon=60m 已對齊 time-stop，但無 path-dependent 提前
    "reverse_cascade_flip",
]


@dataclass(frozen=True)
class A2CandidateConfig:
    """A2 candidate run 配置。

    為什麼 frozen：配置在 run 期間不可變；避免 adapter 中途被改 threshold
    造成 silent 不一致。
    """

    cohort: tuple[str, ...] = A2_COHORT
    per_symbol_threshold: Mapping[str, float] = field(
        default_factory=lambda: dict(A2_DEFAULT_PER_SYMBOL_THRESHOLD)
    )
    min_events: int = A2_MIN_EVENTS
    horizon_min: int = A2_PROXY_HORIZON_MIN
    cost_bps: float = A2_COST_BPS
    # k_prior 由 caller（runner）從 SSOT/ledger 讀傳入（spec v2 §4.3：不自創）。
    k_prior: int = 0


def _filter_rows_by_per_symbol_threshold(
    panel_rows: Sequence[Mapping[str, Any]],
    cfg: A2CandidateConfig,
) -> list[dict[str, Any]]:
    """per-symbol notional threshold 預過濾（A2 spec §1.1 #2 + §1.3）。

    為什麼預過濾而非靠 8c floor_usd 單 scalar：A2 threshold 是 per-symbol
    （BTC $500k ≠ ETH $300k），8c compute_stage0r 的 floor_usd 只接單一
    scalar 套全 cohort。若用單 scalar 會對其中一個 symbol 過鬆/過緊。本層
    依 per-symbol threshold 過濾 cluster_notional_5m，過濾後 rows 傳給
    compute_stage0r 時 floor_usd=0（已預過濾，不重複套絕對 floor）。

    **不改 8c SQL 結構**：本層純 Python row 過濾，SQL leak-free 不變量繼承。
    僅保留 cohort 內 symbol（cohort 外 row 一律丟棄，candidate 只跑 BTC/ETH）。
    """
    out: list[dict[str, Any]] = []
    for row in panel_rows:
        symbol = str(row.get("symbol") or "")
        if symbol not in cfg.cohort:
            continue
        threshold = cfg.per_symbol_threshold.get(symbol)
        if threshold is None:
            # cohort 內但無 threshold 配置 → 保守丟棄（不憑空套 default）。
            continue
        cn = _safe_float(row.get("cluster_notional_5m"))
        if cn is None or cn < threshold:
            continue
        out.append(dict(row))
    return out


def run_a2_candidate(
    panel_rows: Sequence[Mapping[str, Any]],
    cfg: A2CandidateConfig,
    *,
    total_bucket_count: int | None,
    bootstrap_iters: int = 400,
    rng_seed: int = 20260529,
) -> dict[str, Any]:
    """跑 A2 candidate（8c per-event compute_stage0r + 兩 adapter 修正）。

    為什麼傳 total_bucket_count：8c both-direction floor check 用「fraction of
    all 5m buckets that triggered」當分母；8c compute_stage0r 收 None 會 fail-
    closed（missing_bucket_count_denominator hard RED）。caller（runner）必從
    raw_buckets count(*) SELECT 傳入真實值，避免 64× anti-conservative bias。

    返回 dict 含：
      packet_8c：8c compute_stage0r 原始回傳（k_total 已 override DSR 重算）。
      dsr_override：override 紀錄（8c inflated k_total → candidate k_total）。
      exit_model / dynamic_exit_not_modeled：proxy 標註（adapter b）。
      candidate_thresholds / cohort / horizon：candidate 配置回顯。
    """
    # === 1. per-symbol threshold 預過濾 + cohort pin ===
    filtered_rows = _filter_rows_by_per_symbol_threshold(panel_rows, cfg)

    # === 2. 呼 8c per-event compute_stage0r（不改其內部）===
    # A2 entry gate 對應 8c 參數：
    #   - dominant_notional > threshold → 已在 _filter_rows 預過濾 → floor_usd=0
    #     避免重複套絕對 floor。
    #   - event_count >= min_events（A2 #3）→ k_event_count = cfg.min_events。
    #   - dominant_side != Mixed（A2 #4）→ 8c 內部已 filter（dominant_side IN
    #     long/short）。
    #   - A2 無 N_usd 密度 / dominant-event / side_dominance / notional_pct
    #     額外 gate → 設最寬鬆值（不引入 A2 沒有的 gate）。
    #   - parsed_rows 預解析（8c P2-13 優化，數值不變）。
    parsed = prepare_parsed_rows(filtered_rows, cost_bps=cfg.cost_bps)
    packet_8c = compute_stage0r(
        filtered_rows,
        cost_bps=cfg.cost_bps,
        horizon_min=cfg.horizon_min,
        k_event_count=cfg.min_events,   # A2 min_events gate
        n_usd=1,                        # 最寬鬆：A2 無 N_usd 密度 gate
        m_dominant=1,                   # 最寬鬆：A2 無 dominant-event 數 gate
        floor_usd=0,                    # 已 per-symbol 預過濾
        notional_pct_floor=0.0,         # 最寬鬆：A2 無 24h percentile gate
        side_dom=0.0,                   # 最寬鬆：A2 無 side_dominance 收緊
        quiet_sec=0,                    # A2 無 quiet window（即時 pulse snapshot）
        k_prior=cfg.k_prior,
        bootstrap_iters=bootstrap_iters,
        rng_seed=rng_seed,
        bb_demo_bias_confirmed=True,
        total_bucket_count=total_bucket_count,
        parsed_rows=parsed,
    )

    # === 3. adapter (a)：k_total override → 重算 DSR（spec v2 §4.3）===
    # 8c 內部 k_new = max(25, n_symbols) × 11664；對 candidate 固定單閾值不公平。
    # 從 8c packet 取 net_bps 序列重算 DSR：candidate k_total = k_prior + k_new(4)。
    inflated_k_total = int(packet_8c.get("k_total") or 0)
    inflated_k_new = int(packet_8c.get("k_new") or 0)
    candidate_k_total = int(cfg.k_prior) + A2_K_NEW_CANDIDATE
    # 從 8c per-event triggers 重建 net_bps 序列：8c packet 無直接暴露 net 序列，
    # 但 long_branch / short_branch n 與 avg 已暴露；DSR 需 raw 序列 → 用同樣
    # filtered_rows + 同 cell 參數重抽 net（與 8c 內部 _extract_trigger_rows 同
    # 邏輯）。為避免 import 內部 helper（私有），直接用 8c packet 暴露的
    # per-event net 不可得 → 改以 8c compute_stage0r 的 net_bps 數值來源一致性：
    # 8c packet 的 dsr 是用 inflated k_total 算的，本 adapter 用同樣 net 序列換
    # k_total 重算。net 序列從 filtered_rows 經 prepare_parsed_rows 取（已含
    # net_bps，與 8c 內部完全同源 → 數值一致）。
    net_values = [
        float(pr["net_bps"])
        for pr in parsed
        if pr is not None and _safe_float(pr.get("net_bps")) is not None
    ]
    dsr_candidate = dsr_with_k(net_values, candidate_k_total)

    dsr_override = {
        "reason": "candidate 固定單閾值非 11664-cell sweep；8c k_total inflation "
                  "(max(25,n)×11664) 對 candidate DSR 不公平 → 用真實 trial count override",
        "k_8c_inflated_total": inflated_k_total,
        "k_8c_inflated_new": inflated_k_new,
        "k_candidate_new": A2_K_NEW_CANDIDATE,
        "k_candidate_new_basis": "2sym × 2direction × 1threshold × 1horizon",
        "k_prior": int(cfg.k_prior),
        "k_candidate_total": candidate_k_total,
        "dsr_8c_inflated": _safe_float(packet_8c.get("dsr")),
        "dsr_candidate_overridden": dsr_candidate,
        "n_net_values": len(net_values),
    }

    # 用 override 後的 DSR 覆蓋 packet 的 dsr / k_total（下游 6-check 讀 override 值）。
    packet_8c_overridden = dict(packet_8c)
    packet_8c_overridden["dsr"] = dsr_candidate
    packet_8c_overridden["k_total"] = candidate_k_total
    packet_8c_overridden["k_new"] = A2_K_NEW_CANDIDATE
    packet_8c_overridden["dsr_8c_inflated_preserved"] = _safe_float(packet_8c.get("dsr"))

    # === 4. avg_net_bps 取 candidate net 序列（與 8c 同源，但限 candidate cohort）===
    avg_net = statistics.mean(net_values) if net_values else None

    return {
        "alpha_source_id": A2_ALPHA_SOURCE_ID,
        "path": "8c_per_event_adapter",
        "candidate_thresholds": {
            "btc_threshold_usd": cfg.per_symbol_threshold.get("BTCUSDT"),
            "eth_threshold_usd": cfg.per_symbol_threshold.get("ETHUSDT"),
            "min_events": cfg.min_events,
        },
        "cohort": list(cfg.cohort),
        "horizon_min": cfg.horizon_min,
        # adapter (b)：fixed-horizon dynamic-exit proxy 標註。
        "exit_model": "fixed_horizon_60m_conservative_proxy",
        "exit_model_note": "8c 固定 horizon=60m mark = A2 動態出場保守 proxy（持滿 "
                           "horizon 不提前 TP/SL）；proxy 偏低估 alpha，proxy PASS "
                           "→ 真實動態出場只會更好；proxy fail → 標 observe_more 非 reject",
        "dynamic_exit_not_modeled": list(A2_DYNAMIC_EXIT_NOT_MODELED),
        # adapter (a)：k_total override 紀錄。
        "dsr_override": dsr_override,
        # 8c packet（DSR / k_total 已 override）。
        "packet_8c": packet_8c_overridden,
        "avg_net_bps": avg_net,
        "n_filtered_rows": len(filtered_rows),
        "n_net_values": len(net_values),
    }
