"""Pricing binding read-model for healthcheck `[45]`.
Pricing binding healthcheck `[45]` 的唯讀判定模型。

這個 Module 集中 PG proxy source 推斷與 Rust `FeeSource` compatibility table。
`checks_pricing_binding.py` 只負責查 DB / IPC 與輸出 verdict，避免把跨語言
字串契約散在 runner implementation 裡。
"""

from __future__ import annotations

from dataclasses import dataclass


RUST_FEE_SOURCE_BYBIT_API: str = "bybit_api"
RUST_FEE_SOURCE_DEMO_CONSERVATIVE_DEFAULT: str = "demo_conservative_default"
RUST_FEE_SOURCE_COLD_DEFAULT: str = "cold_default"


@dataclass(frozen=True)
class PricingBindingSnapshot:
    """單一 pricing source 對賬快照。"""

    rust_source: str
    pg_proxy_source: str

    @property
    def compatible(self) -> bool:
        return is_rust_pg_source_compatible(self.rust_source, self.pg_proxy_source)


FEE_SOURCE_COMPAT: dict[str, frozenset[str]] = {
    RUST_FEE_SOURCE_BYBIT_API: frozenset({"bybit_v5", "inactive_mainnet"}),
    RUST_FEE_SOURCE_DEMO_CONSERVATIVE_DEFAULT: frozenset(
        {"seed_default", "inactive_mainnet"}
    ),
    RUST_FEE_SOURCE_COLD_DEFAULT: frozenset({"cold_default", "inactive_mainnet"}),
}


def is_rust_pg_source_compatible(rust_enum: str, pg_proxy: str) -> bool:
    """判斷 Rust enum 字串與 PG proxy 字串是否語意相容。"""

    compat = FEE_SOURCE_COMPAT.get(rust_enum)
    if compat is None:
        return False
    return pg_proxy in compat


def infer_pricing_source(default_count: int, non_default_count: int) -> str:
    """從 24h fee_rate 分佈推斷 PG proxy source。"""

    total = default_count + non_default_count
    if total == 0:
        return "cold_default"
    if non_default_count == 0:
        return "seed_default"
    return "bybit_v5"
