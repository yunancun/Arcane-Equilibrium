"""
Governance Divergence Comparator — Rust-IPC vs Python-local-SM 影子比對器
（SM Option 2 收斂 — step (i) soak 儀器）。

MODULE_NOTE:
    本模組是 SM Option 2 收斂遷移 step (i) 的「soak 儀器」。當
    ``OPENCLAW_LEASE_PYTHON_IPC_ENABLED=1`` 時，GovernanceHub 的 lease 操作
    （acquire / release / get）以 Rust IPC 結果為「權威」回傳值；同時 *影子*
    計算本地 Python SM 的判定（無任何副作用），並把兩者送進本比對器：

      1. 把 Rust 權威結果與 Python 影子結果正規化成「outcome」標籤後比對。
      2. 對每筆操作記一筆結構化 divergence 條目（match=True 也記，供 N 計數），
         寫入可查詢的 in-memory ring buffer（sink），並維護計數器。
      3. 真 mismatch（match=False）時額外發一條 WARN 結構化 log（soak 可 grep）。

    比對軸（E2 HIGH #5 修正後）：
      - **auth-axis（主通道）**：``op="is_authorized"``，由 acquire 開頭在 Step-2
        *之前* 跑，比對 Rust ``is_authorized`` IPC vs Python ``is_authorized()``。
        這是 step-(i) 真正能 fire 的主分歧偵測通道（解掉「Step-2 預先過濾掉
        Rust-grant/Python-deny 分歧」的近盲問題）。
      - **acquire scope-axis**：``op="acquire"``，比對 Rust acquire outcome vs
        Python 完整 acquire 影子（auth-effective + scope-permit）。
      - **release/get presence-axis（弱通道）**：``op="release"/"get"``，本地通常
        不持有 Rust lease → 影子回 ``OUTCOME_UNKNOWN``（no-opinion），由
        ``record_divergence`` 視為「計入 total、不算 divergence、不發 WARN」。

    No-opinion 語義（A3）：任一側為 ``OUTCOME_UNKNOWN`` 即該側「無獨立意見」，
    *不*算分歧（修掉弱通道每次 release 假報 ``rust=granted python=unknown`` 的
    over-fire）。

    這是 *觀測*，不影響也不阻塞權威回傳值（hub 先拿到 Rust 結果就回，影子+比對
    是事後 best-effort）。step (i) 的 gate 讀「soak 視窗內 0 divergence」=
    ``get_divergence_counters()["divergences"] == 0`` 且 ``["total"] >= N``。

    設計對齊 governance_lease_bridge._DUAL_WRITE_MIRROR：模組層級、package-private、
    threading.Lock 保護、無 TTL/LRU/DB 持久化、提供 snapshot + reset（測試隔離）。
    本模組的 ``_DIVERGENCE_RING`` / ``_COUNTERS`` / ``_DIVERGENCE_LOCK`` 已登記於
    docs/architecture/singleton-registry.md §2.5。step (iv) cleanup 會連同
    dual-write mirror 一起移除本比對器。

安全保證:
  - 純觀測：記錄絕不向 caller 拋例外（best-effort）；不改、不阻塞權威回傳值。
  - 有界記憶體（ring buffer cap）；thread-safe；除 package-private buffer +
    counters（僅透過下方 helper 變更）外無 singleton。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Divergence sink（in-memory ring buffer + 計數器）/ divergence 槽
# ═══════════════════════════════════════════════════════════════════════════════

# 環形緩衝上限。soak 視窗（24-48h / N≥數百筆）在低 lease emit rate 下遠低於此；
# 上限僅防長跑無界增長。舊條目 FIFO 丟棄；但計數器不因 capping 重置（故「N 筆
# 0 divergence」即使個別條目滾出仍精確）。
_RING_CAP: int = 2048

_DIVERGENCE_RING: list[dict[str, Any]] = []
_DIVERGENCE_LOCK = threading.Lock()

# 單調計數器（不隨環形緩衝 FIFO 淘汰而失真）。
_COUNTERS: dict[str, int] = {
    "total": 0,        # 已比對的操作總數（match + no-opinion + mismatch）
    "matches": 0,      # 視為 match 的筆數（rust == python，或任一側 UNKNOWN no-opinion）
    "divergences": 0,  # 真分歧筆數（兩側皆有意見且不一致；step-(i) gate 要求 == 0）
}

# 正規化 outcome 標籤（讓 Rust↔Python 在穩定詞彙上比對，不受原始 payload 形狀影響）。
OUTCOME_GRANTED: str = "granted"      # acquire: 取得 lease / release/get: 成功/存在
OUTCOME_DENIED: str = "denied"        # acquire/release: 拒絕/失敗 / get: 不存在
OUTCOME_BYPASS: str = "bypass"        # acquire: Rust Bypass outcome（Validation/Exploration profile）
OUTCOME_UNKNOWN: str = "unknown"      # 影子無獨立意見（no-opinion；precondition 不足或 lease 在 Rust）

# 已知操作標籤。
OP_ACQUIRE: str = "acquire"
OP_RELEASE: str = "release"
OP_GET: str = "get"
# auth-axis 比對（acquire 開頭做，Step-2 之前）：Rust is_authorized vs Python
# is_authorized。這是 step-(i) 真正能 fire 的主分歧偵測通道（acquire/release/get
# 的 presence 通道是弱通道）。
OP_IS_AUTHORIZED: str = "is_authorized"


def record_divergence(
    *,
    op: str,
    rust_outcome: str,
    python_outcome: str,
    intent_id: Optional[str] = None,
    scope: Optional[str] = None,
    profile: Optional[str] = None,
    lease_id: Optional[str] = None,
    differing_fields: Optional[list[str]] = None,
) -> bool:
    """記一筆 Rust-IPC vs Python-shadow 比對結果，回傳是否視為 match。

    Best-effort：本函式絕不向 caller 拋例外（影子比對不可破壞權威路徑）。每筆都
    記入 ring（供 soak 計 N），但只有真 mismatch 發 WARN log。

    No-opinion（A3）：任一側為 ``OUTCOME_UNKNOWN`` 視為「該側無獨立意見」，計入
    total 但*不*算 divergence、*不*發 WARN（見下方實作註）。

    Args / 參數:
        op: 操作標籤（acquire / release / get / is_authorized）。
        rust_outcome: Rust 權威結果正規化標籤（OUTCOME_*）。
        python_outcome: Python 影子判定正規化標籤（OUTCOME_*）。
        intent_id / scope / profile / lease_id: 追溯欄位（可選）。
        differing_fields: 若 caller 已知差異欄位則傳入；否則由本函式於 mismatch
            時填 ["outcome"]。

    Returns / 回傳:
        True 若視為 match（rust == python，或任一側 UNKNOWN no-opinion）；
        False 僅當兩側皆有意見且不一致（真 divergence）。
    """
    try:
        # No-opinion 排除（A3）：當任一側為 OUTCOME_UNKNOWN，代表該側「無獨立意見」
        # （flag-ON acquire 在 Rust 註冊 lease，本地 Python SM 不持有 → release/get
        # 的 presence 影子回 UNKNOWN 是*合法的* no-opinion，不是分歧）。把它計入 total
        # 但*不*算 divergence、*不*發 WARN。這修掉「python=unknown → 記分歧」的
        # over-fire（弱通道每次 release 都假報 rust=granted python=unknown）。
        # release/get 是弱通道（presence echo）；主分歧偵測靠 acquire 開頭的 auth-axis
        # 比對（OP_IS_AUTHORIZED）+ acquire 的 scope-axis 影子。
        no_opinion = (
            rust_outcome == OUTCOME_UNKNOWN or python_outcome == OUTCOME_UNKNOWN
        )
        match = no_opinion or (rust_outcome == python_outcome)
        if not match and differing_fields is None:
            differing_fields = ["outcome"]
        entry: dict[str, Any] = {
            "ts": time.time(),
            "op": op,
            "intent_id": intent_id,
            "scope": scope,
            "profile": profile,
            "lease_id": lease_id,
            "rust_outcome": rust_outcome,
            "python_outcome": python_outcome,
            "match": match,
            # no_opinion=True 表示此筆是「一側 UNKNOWN」的合法 no-op（計入 total、
            # 不算 divergence），供 soak 區分「真 match」與「無意見」。
            "no_opinion": no_opinion,
            "differing_fields": list(differing_fields) if differing_fields else [],
        }
        with _DIVERGENCE_LOCK:
            _COUNTERS["total"] += 1
            if match:
                _COUNTERS["matches"] += 1
            else:
                _COUNTERS["divergences"] += 1
            _DIVERGENCE_RING.append(entry)
            # 超過 cap 即 FIFO 淘汰；計數器已先累加，不受影響。
            if len(_DIVERGENCE_RING) > _RING_CAP:
                del _DIVERGENCE_RING[: len(_DIVERGENCE_RING) - _RING_CAP]

        if not match:
            # 一條結構化 WARN，soak 可 grep "SM_DIVERGENCE"。
            logger.warning(
                "SM_DIVERGENCE op=%s intent_id=%s scope=%s profile=%s lease_id=%s "
                "rust=%s python=%s differing=%s / Rust-IPC 與 Python-shadow 判定分歧",
                op, intent_id, scope, profile, lease_id,
                rust_outcome, python_outcome,
                entry["differing_fields"],
            )
        return match
    except Exception:  # noqa: BLE001 — 影子比對 best-effort，絕不影響權威回傳
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "record_divergence 內部錯誤已吞噬（不影響權威路徑）",
                exc_info=True,
            )
        return True  # 不把比對器自身的故障當成 divergence


def get_divergence_counters() -> dict[str, int]:
    """回傳 divergence 計數快照（soak gate 讀此判 0 divergence over N ops）。

    Return a snapshot of the divergence counters. The step-(i) gate reads
    ``divergences == 0`` with ``total >= N`` over the soak window.
    """
    with _DIVERGENCE_LOCK:
        return dict(_COUNTERS)


def get_divergence_snapshot(limit: Optional[int] = None) -> list[dict[str, Any]]:
    """回傳 ring buffer 內 divergence 條目的防禦性副本（測試 + 可觀測性）。

    若 ``limit`` 給定，只回最近 ``limit`` 筆。
    """
    with _DIVERGENCE_LOCK:
        rows = _DIVERGENCE_RING[-limit:] if limit is not None else list(_DIVERGENCE_RING)
        return [dict(r) for r in rows]


def get_mismatch_snapshot(limit: Optional[int] = None) -> list[dict[str, Any]]:
    """只回 match=False 的真分歧條目副本（soak 失敗時的取證入口）。

    no-opinion（任一側 UNKNOWN）筆 match=True，不會出現在此（不算分歧）。
    """
    with _DIVERGENCE_LOCK:
        rows = [dict(r) for r in _DIVERGENCE_RING if not r["match"]]
    return rows[-limit:] if limit is not None else rows


def reset_divergence_state() -> None:
    """清空 ring + 計數器（僅供測試隔離；勿於 production 呼叫）。"""
    with _DIVERGENCE_LOCK:
        _DIVERGENCE_RING.clear()
        for k in _COUNTERS:
            _COUNTERS[k] = 0


__all__ = [
    "OUTCOME_GRANTED",
    "OUTCOME_DENIED",
    "OUTCOME_BYPASS",
    "OUTCOME_UNKNOWN",
    "OP_ACQUIRE",
    "OP_RELEASE",
    "OP_GET",
    "OP_IS_AUTHORIZED",
    "record_divergence",
    "get_divergence_counters",
    "get_divergence_snapshot",
    "get_mismatch_snapshot",
    "reset_divergence_state",
]
