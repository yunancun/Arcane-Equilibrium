"""
Strategist promote — shared Python↔Rust IPC contract constants (single source).
策略師促升 — Python↔Rust evaluate_promotion_criteria IPC 契約常數（單一來源）。

MODULE_NOTE (中):
  模塊用途：把「`evaluate_promotion_criteria` 唯讀 IPC 的 param key 集合 + 促升
    verdict 的 canonical token 大小寫」釘成單一來源常數，供 route（生產 emit）與
    contract test（結構斷言）同時 import，杜絕「route 與 Rust handler 對 IPC 契約
    各自演化、被 mock 掩蓋」的整類 bug（承 E2/QC adversarial review 兩個 HIGH：
    route 送 strategy_name / 漏 active_symbols → handler ERR_INVALID_REQUEST →
    503；route 比對大寫 "Eligible" / handler emit 小寫 "eligible" → 永久拒）。

  Rust 對應錨點（必須與 dispatch.rs::handle_evaluate_promotion_criteria 逐字一致）：
    - 必要鍵：`strategy`（非空）、`active_symbols`（陣列）— handler 缺任一 →
      ERR_INVALID_REQUEST（fail-closed）。
    - 度量鍵：handler 以 params.get(...) 讀（缺 → 保守 fallback）。
    - verdict token：handler 回 `verdict = PromotionVerdict::tag()`，**小寫**
      `"eligible"/"pending"/"reject"`（promotion_criteria.rs:191-197）。canonical
      casing = lowercase；route 必須 `.lower()` 後比 ELIGIBLE_TOKEN。

  硬邊界：此檔只放契約常數（無邏輯、無 IO）。改任一常數即同時影響 route 與
    Rust handler 的契約——任何改動必同步檢查 dispatch.rs handler 與 contract test。

  IPC-CONTRACT OPTION（E1 2026-06-17 釘死）= **Option A**：route 算齊所有 metric
    （含 active_symbols 解析 + cost 參數讀 risk_config_live.toml SSOT + boundary
    DB 量測）傳入；engine 只自查 edge cell（freshness/runtime_field 須與 live
    cost_gate 看同一記憶體 snapshot）。理由：active_symbols 需讀兩份 TOML、boundary
    需查 demo realized drawdown（DB query），兩者在 sync IPC handler 內不可達；
    route（async + DB + tomllib）是唯一能算齊的層。
"""

from __future__ import annotations

# `evaluate_promotion_criteria` IPC method 名（route emit + handler match arm）。
CRITERIA_IPC_METHOD = "evaluate_promotion_criteria"

# ── 必要鍵（handler 缺任一 → ERR_INVALID_REQUEST，fail-closed）──
# strategy：非空字串；active_symbols：字串陣列（route 解析 allowed∩pinned）。
CRITERIA_REQUIRED_KEYS = frozenset({"strategy", "active_symbols"})

# ── handler 以 params.get(...) 讀的度量 / cost / freshness 鍵（Option A：route 全送）──
# 與 dispatch.rs::handle_evaluate_promotion_criteria 的 params.get 逐字對齊。
CRITERIA_METRIC_KEYS = frozenset(
    {
        "demo_soak_wall_clock_ms",
        "ms_since_last_param_change",
        "attributable_demo_fills",
        "demo_boundary_violation_count",
        "attribution_chain_ok_ratio",
        "fee_bps_round_trip",
        "cost_gate_safety_multiplier",
        "cost_gate_win_rate_floor",
        "edge_ttl_secs",
        "tuned_param_names",
    }
)

# route 的 OUTGOING IPC param dict 的完整 key 集合（必要鍵 ∪ 度量鍵）。
# contract test 斷言 route emit 的 key 集合 == 此集合 == handler 讀的 key 集合。
CRITERIA_OUTGOING_KEYS = CRITERIA_REQUIRED_KEYS | CRITERIA_METRIC_KEYS

# ── verdict canonical token（小寫，鏡像 Rust PromotionVerdict::tag()）──
# route 必須 `str(verdict).lower() == ELIGIBLE_TOKEN` 判定可促升。
ELIGIBLE_TOKEN = "eligible"
PENDING_TOKEN = "pending"
REJECT_TOKEN = "reject"

# handler 回應 payload 中承載 per-cell EDGE-ANCHORED 證據的鍵（route 組裝 audit
# criteria_input_json 用；handler 不回 "criteria_input" 整包，而是分欄回，故 route
# 必須讀這些鍵而非舊的 verdict_payload["criteria_input"]）。
CRITERIA_RESPONSE_PER_CELL_KEY = "per_cell"
CRITERIA_RESPONSE_ACTIVE_COUNT_KEY = "active_count"
CRITERIA_RESPONSE_FRESH_KEY = "edge_estimates_fresh"


def is_eligible(verdict_token: str | None) -> bool:
    """canonical 判定：verdict token（任意大小寫）是否 Eligible。

    為何集中於此：route 與 test 共用同一判定，避免「route 比大寫、handler emit 小寫」
    的整類 casing-mismatch bug 復發（承 QC/CC adversarial 兩個 HIGH finding）。
    """
    return str(verdict_token or "").strip().lower() == ELIGIBLE_TOKEN


__all__ = [
    "CRITERIA_IPC_METHOD",
    "CRITERIA_REQUIRED_KEYS",
    "CRITERIA_METRIC_KEYS",
    "CRITERIA_OUTGOING_KEYS",
    "ELIGIBLE_TOKEN",
    "PENDING_TOKEN",
    "REJECT_TOKEN",
    "CRITERIA_RESPONSE_PER_CELL_KEY",
    "CRITERIA_RESPONSE_ACTIVE_COUNT_KEY",
    "CRITERIA_RESPONSE_FRESH_KEY",
    "is_eligible",
]
