"""SM Option 2 收斂 soak 可觀測性 healthcheck `[81]`（P5-SM-OPTION2 B-3，rework (b)+(b-i)）。

模塊用途：cron-side（SQL-cursor）判 SM Option 2 step-(i) soak 是否健康。

**rework 背景（operator 拍板 (b)+(b-i)，2026-06-03）**：E2 HIGH-2 + PA reconciliation
（`2026-06-03--p5_sm_soak_equiv_sampler_reconciliation.md`）證實——Option 2 下「歷史
replay 驅動 contemporaneous comparator」語意不可達：sampler 拿歷史 Rust-GRANTED row
對撞 Python hub「當前」auth state，steady-state Python hub 結構上未授權 → 每筆歷史
GRANTED → Python 影子 DENIED → comparator divergence 永遠卡死。故 comparator 從「硬
gate」**降為觀測性信號（非 gate）**。

**cutover gate 新定義 = 4a CI 綠 AND P-LIVE soak 健康**（不含 comparator counter）：
  - **4a 離線全分支 parity**（`sm_contract.rs` + `test_sm_contract_parity.py`，190-vector
    兩獨立實作）是 P-EQUIV 的 authoritative proof，**CI 物（非本 soak healthcheck）**。
  - **P-LIVE 信號**（本 healthcheck 唯一 gate）：讀 `learning.lease_transitions` row
    count + freshness，證 Rust 權威路徑（真實 engine + serde + IPC + PG writer +
    profile/engine_mode 解析）熱路徑在跑且健康。**這徹底解原 fake-pass**：gate 改讀
    真實熱路徑 `lease_transitions`（Rust 真寫），非空轉的 comparator counter（Option 2
    steady-state organic≈0、sampler 語意不可達）。

主要函數：``check_81_lease_ipc_soak``（``(cur) -> (status, msg)``，與既有 checks_*.py
同契約）。

依賴：
  - ``learning.lease_transitions``（V054，Rust writer 寫，read-only）—— **gate 唯一資料源**。
  - ``learning.lease_ipc_divergence_snapshot``（V128，flusher 寫）—— **僅觀測**：comparator
    counter（total / matches / divergences / snapshot freshness / flag_enabled）在 message
    報數值供 operator triage，**不再是 FAIL 條件**。讀取失敗 / 缺表 / stale 一律降級為
    觀測欄缺值（不致 FAIL）。

硬邊界（fail-closed — G-1，僅對 P-LIVE 適用）：
  - **P-LIVE 任一不滿足 → FAIL（exit 1）非 WARN**：lease_transitions 表缺（V054 未 apply）
    / 窗內 0 row / 最新 row stale（age >= threshold）。Rust 權威路徑死 → soak 不健康，
    必 fail-closed（不可當綠燈）。
  - freshness threshold 容忍低交易期短暫安靜（預設 3600s，O-3 ops param，operator 可調），
    但「表缺 / 0 row / 長期 stale」= 引擎或 Rust 權威路徑死 → FAIL。
  - comparator 觀測欄**不 fail-closed**：它已非 gate（Option 2 下語意不可達），讀不到只是
    觀測缺值；把它當 gate 正是原 fake-pass 根因，rework 已移除。
  - 純觀測 sentinel；不碰 live 決策 / 訂單 / 任一 5 live-auth gate。step-(iv) cleanup
    連同 comparator 退役後本 check 可移除。
"""
from __future__ import annotations

from typing import Any

# ── soak gate 閾值（per PA §5 R5 + operator O-3：freshness threshold operator 可調）──

# P-LIVE：lease_transitions 新鮮度上限（秒）。Rust 權威路徑 steady-state 應持續 emit；
# 此處取 3600s（1h）——soak 期間 lease emit 率受市場活躍度影響，低交易期可能 row 少，
# 1h 容忍短暫安靜；但 1h 內無任何 Rust lease transition 視為權威路徑可能 silent-dead
# （P-LIVE FAIL）。**operator 可依市場活躍度調整此預設（O-3 ops param）。**
LIVE_TRANSITION_FRESHNESS_MAX_SECONDS: int = 3600


def check_81_lease_ipc_soak(cur: Any) -> tuple[str, str]:
    """[81] lease_ipc_soak — SM Option 2 step-(i) soak gate（P-LIVE only；comparator 觀測）。

    **rework (b)+(b-i)**：gate 唯一條件 = P-LIVE（lease_transitions Rust 權威路徑健康）。
    comparator counter 降為觀測欄（在 msg 報數值，不再 FAIL）。

    Verdict（G-1 fail-closed，僅對 P-LIVE；任一不滿足即 FAIL，無 WARN 軟化）：
      * P-LIVE：lease_transitions 表缺（V054 未 apply）→ FAIL（Rust 權威路徑不可確認）。
      * P-LIVE：窗內 0 row → FAIL（Rust 權威路徑未 emit 任何 lease transition）。
      * P-LIVE：最新 row stale（age >= LIVE_TRANSITION_FRESHNESS_MAX_SECONDS）→ FAIL
        （Rust 權威路徑可能 silent-dead）。
      * P-LIVE 全滿足 → PASS（Rust 真跑且 fresh）。msg 附 comparator 觀測欄供 triage。

    comparator 觀測欄（**非 gate**，best-effort 讀 V128 snapshot；讀不到報缺值不致 FAIL）：
      total / matches / divergences / snapshot_age / flag_enabled —— 供 operator 觀測
      comparator 在 organic 控制面流量下是否偵測到分歧；Option 2 steady-state 多半為
      organic≈0（counter 不累積），這是預期，非 soak 失敗。

    Returns:
        ``(status, msg)``。msg 含 P-LIVE lease_transitions count/age（gate）+ comparator
        觀測欄（observed:...）；FAIL 標明 P-LIVE 哪個條件未過。
    """
    # 防禦性 rollback（鏡 checks_governance 既有 pattern）。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — 防禦性，rollback 失敗非致命
        pass

    # ── P-LIVE 信號（gate 唯一條件）：lease_transitions Rust 權威路徑真跑（read-only）──
    try:
        cur.execute("SELECT to_regclass('learning.lease_transitions') IS NOT NULL")
        lt_exists = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[81] lease_transitions existence check failed: {exc}")
    if not lt_exists or not lt_exists[0]:
        return (
            "FAIL",
            "[81] P-LIVE FAIL: learning.lease_transitions missing (V054 not applied) — "
            "cannot confirm Rust authoritative path is running",
        )

    # 最新 lease_transition 的 freshness（ts_ms 是 facade emit epoch ms）。空表 / stale
    # → FAIL（Rust 權威路徑未跑 / silent-dead；P-LIVE 是 soak gate 唯一信號）。
    try:
        cur.execute(
            "SELECT COUNT(*), "
            "       (EXTRACT(EPOCH FROM now()) * 1000)::BIGINT - COALESCE(MAX(ts_ms), 0) "
            "FROM learning.lease_transitions"
        )
        lt_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[81] lease_transitions freshness query failed: {exc}")

    lt_count = int(lt_row[0] or 0) if lt_row else 0
    lt_age_ms = int(lt_row[1] or 0) if lt_row else 0
    if lt_count == 0:
        return (
            "FAIL",
            "[81] P-LIVE FAIL: 0 lease_transitions rows — Rust authoritative path "
            "has emitted no lease transition (path not running)",
        )
    lt_age_s = lt_age_ms // 1000
    if lt_age_s >= LIVE_TRANSITION_FRESHNESS_MAX_SECONDS:
        return (
            "FAIL",
            f"[81] P-LIVE FAIL: newest lease_transition age={lt_age_s}s "
            f">= {LIVE_TRANSITION_FRESHNESS_MAX_SECONDS}s — Rust authoritative path "
            f"may be silent-dead",
        )

    # ── comparator 觀測欄（非 gate）：best-effort 讀 V128 snapshot 報數值供 triage ──
    # rework (b)+(b-i)：comparator 已降為觀測性信號（Option 2 下語意不可達，不作 gate）。
    # 讀取失敗 / 缺表 / 缺 row / stale 一律降級為觀測欄缺值（report-only），**不致 FAIL**。
    observed = _read_comparator_observed(cur)

    # ── P-LIVE 通過 → PASS（gate 滿足）；msg 附 comparator 觀測欄 ──
    return (
        "PASS",
        f"[81] soak healthy (P-LIVE gate): lease_transitions count={lt_count} "
        f"newest_age={lt_age_s}s; observed[comparator non-gate]: {observed}",
    )


def _read_comparator_observed(cur: Any) -> str:
    """best-effort 讀 V128 snapshot comparator counter，回 observability 字串（**非 gate**）。

    為什麼 best-effort 而非 fail-closed：rework (b)+(b-i) 後 comparator 是觀測性信號，
    非 cutover gate 條件。Option 2 steady-state comparator organic≈0（sampler 語意不可達，
    見 module docstring），counter 不累積是預期，不該致 soak FAIL。任何讀取失敗（V128
    缺 / row 缺 / stale / 查詢例外）→ 回缺值描述字串，caller 照常 PASS（gate 由 P-LIVE 定）。

    回字串範例：
      ``total=12 matches=12 divergences=0 snapshot_age=8s flag=ON``
      ``unavailable: V128 snapshot table absent``
      ``unavailable: no snapshot row (flusher not yet written)``
    """
    # 防禦性 rollback（前一 P-LIVE query 後重置 tx 狀態，避免污染本觀測查詢）。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — 防禦性
        pass

    try:
        cur.execute(
            "SELECT to_regclass('learning.lease_ipc_divergence_snapshot') IS NOT NULL"
        )
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 — 觀測讀取失敗不致 FAIL
        return f"unavailable: snapshot existence check error ({exc})"
    if not exists_row or not exists_row[0]:
        return "unavailable: V128 snapshot table absent"

    try:
        cur.execute(
            "SELECT total, matches, divergences, flag_enabled, "
            "       EXTRACT(EPOCH FROM (now() - updated_at))::BIGINT AS age_s "
            "FROM learning.lease_ipc_divergence_snapshot "
            "WHERE snapshot_key = 'singleton'"
        )
        snap = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 — 觀測讀取失敗不致 FAIL
        return f"unavailable: snapshot row query error ({exc})"

    if snap is None:
        return "unavailable: no snapshot row (flusher not yet written)"

    total = int(snap[0] or 0)
    matches = int(snap[1] or 0)
    divergences = int(snap[2] or 0)
    flag_enabled = bool(snap[3])
    snap_age_s = int(snap[4] or 0)
    flag_str = "ON" if flag_enabled else "OFF"
    return (
        f"total={total} matches={matches} divergences={divergences} "
        f"snapshot_age={snap_age_s}s flag={flag_str}"
    )


__all__ = [
    "check_81_lease_ipc_soak",
    "LIVE_TRANSITION_FRESHNESS_MAX_SECONDS",
]
