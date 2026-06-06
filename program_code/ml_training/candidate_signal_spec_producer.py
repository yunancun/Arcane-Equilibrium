"""
MODULE_NOTE
模塊用途：SignalSpec **producer**（補 candidate_signal_spec.py 只有 validator 的缺口）。
從候選 metadata + residual report 構造一份通過 ``validate_signal_spec`` 的 canonical
SignalSpec dict，與同候選的 demo_residual_alpha_report 一致（同 factor_panel_hash /
residualization method）。
主要函數：build_signal_spec。
依賴：candidate_signal_spec（hash + schema 常數）；僅標準庫；不讀 DB、不連交易所。
硬邊界：PIT 契約硬寫 point_in_time=True / future_data_allowed=False；hidden_oos_policy
硬寫 state_required=sealed / open_once=True（與 hidden_oos sealer 對齊）；不發明
factor_panel_hash（缺則留空，靠 factors=["btc"] 滿足 validator）。
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

try:  # 套件式 import
    from program_code.ml_training.candidate_signal_spec import (
        SIGNAL_SPEC_SCHEMA_VERSION,
        compute_signal_spec_hash,
    )
except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback
    from ml_training.candidate_signal_spec import (  # type: ignore
        SIGNAL_SPEC_SCHEMA_VERSION,
        compute_signal_spec_hash,
    )


RESIDUALIZATION_METHOD_V1 = "btc_beta_train_fit_residual_v1"
# 與 SignalPostmortem 對齊的失敗分類（validator 僅需非空序列）
DEFAULT_FAILURE_TAXONOMY: tuple[str, ...] = (
    "no_edge",
    "beta_edge",
    "cost_defeat",
    "fill_failure",
    "regime_only",
    "sample_insufficient",
    "data_leak",
    "implementation_bug",
)
DEFAULT_INPUTS: tuple[str, ...] = (
    "trading.fills.round_trip_net_bps",
    "market.klines.btc_bucket_return",
)
DEFAULT_COST_MODEL_REF = "realized_edge_stats.net_pnl_bps_fee_adjusted_winsorized"


def build_signal_spec(
    *,
    candidate_id: str,
    family_id: str,
    strategy_name: str,
    symbol: str,
    bucket_sec: float,
    residual_report: Mapping[str, Any] | None = None,
    universe_ref: str = "btc_only_v1",
    regime_ref: str | Mapping[str, Any] = "none_btc_only_v1",
    cost_model_ref: str = DEFAULT_COST_MODEL_REF,
    inputs: Sequence[str] = DEFAULT_INPUTS,
    failure_taxonomy: Sequence[str] = DEFAULT_FAILURE_TAXONOMY,
) -> dict[str, Any]:
    """構造一份通過 ``validate_signal_spec`` 的 canonical SignalSpec dict。

    residual_report：取其 ``factor_panel_hash`` 寫進 residualization（與 residual
    證據一致）；缺則留空（factors=["btc"] 已足夠 validator）。horizon 用 exit-
    attributed 非重疊 bucket 描述。spec_hash 用 canonical sha256 自算後嵌入。
    """
    factor_panel_hash = ""
    if isinstance(residual_report, Mapping):
        factor_panel_hash = str(residual_report.get("factor_panel_hash") or "").strip()

    spec: dict[str, Any] = {
        "schema_version": SIGNAL_SPEC_SCHEMA_VERSION,
        "candidate_id": str(candidate_id),
        "family_id": str(family_id),
        "hypothesis": (
            f"BTC-residual alpha: {strategy_name} on {symbol}; non-overlapping "
            f"{int(bucket_sec)}s exit-attributed buckets, train-fit BTC beta "
            "residualized, gated on residual PSR/DSR/CSCV-PBO."
        ),
        "horizon": {
            "bucket_sec": float(bucket_sec),
            "attribution": "exit",
            "label": "non_overlapping_bucket",
        },
        "inputs": list(inputs),
        "pit_contract": {"point_in_time": True, "future_data_allowed": False},
        "universe_ref": str(universe_ref),
        "regime_ref": regime_ref if isinstance(regime_ref, Mapping) else str(regime_ref),
        "feature_schema": {
            "round_trip_net_bps": "bps",
            "btc_bucket_return": "bps",
        },
        "cost_model_ref": str(cost_model_ref),
        "residualization": {
            "method": RESIDUALIZATION_METHOD_V1,
            "factors": ["btc"],
            "factor_panel_hash": factor_panel_hash,
        },
        "failure_taxonomy": list(failure_taxonomy),
        "hidden_oos_policy": {"state_required": "sealed", "open_once": True},
    }
    spec["spec_hash"] = compute_signal_spec_hash(spec)
    return spec


__all__ = [
    "RESIDUALIZATION_METHOD_V1",
    "DEFAULT_FAILURE_TAXONOMY",
    "build_signal_spec",
]
