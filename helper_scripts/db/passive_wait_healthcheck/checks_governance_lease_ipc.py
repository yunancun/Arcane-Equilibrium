"""SM Option 2 收斂 soak 可觀測性 healthcheck `[81]`（P5-SM-OPTION2 B-3）。

模塊用途：cron-side（SQL-cursor）讀 V128 `learning.lease_ipc_divergence_snapshot`
（comparator 計數器的 PG 投影）+ `learning.lease_transitions`（Rust 權威路徑落地），
以**雙信號** gate 判 SM Option 2 step-(i) soak 是否健康：

  - **P-EQUIV 信號**（comparator 真實樣本下 0 divergence）：讀 snapshot row，gate =
    ``flag_enabled AND divergences==0 AND total>=N AND snapshot_freshness<threshold``。
  - **P-LIVE 信號**（Rust 權威路徑真跑）：讀 lease_transitions row count + freshness
    證明 Rust writer 在跑、無 fail-soft drop 堆積。

per PA 設計 `2026-06-03--p5_sm_soak_observability_redesign.md` §2 recommend（Fork
②-LIVE + ②-EQUIV）+ §3 B-3 + operator O-1（cutover gate = P-LIVE AND P-EQUIV）
+ O-2（comparator keep-as-gate，故 P-EQUIV 是硬 gate）。

主要函數：``check_81_lease_ipc_soak``（``(cur) -> (status, msg)``，與既有 checks_*.py
同契約）。

依賴：``learning.lease_ipc_divergence_snapshot``（V128，flusher 寫）+
``learning.lease_transitions``（V054，Rust writer 寫，read-only）。

硬邊界（fail-closed — G-1）：
  - **stale snapshot / flag-OFF / snapshot 缺失 / V128 未 apply → 一律非 PASS（FAIL）。**
    對症原「讀不到當綠燈」空轉偽 pass：snapshot row 凍結（flusher 死）→ freshness
    gate FAIL；flag_enabled=false（legacy local SM，comparator 不 fire）→ FAIL；
    snapshot 缺失（flusher 從沒寫）→ FAIL。
  - freshness gate 是 R2 stale-snapshot 偽 pass 緩解核心：counter 單調，但 flusher 若
    死，stale row 的 divergences==0 會偽 pass → 強制 updated_at 新鮮度 < threshold。
  - 真 divergence（divergences > 0）→ FAIL（comparator gate；O-2 keep-as-gate）。
  - 純觀測 sentinel；不碰 live 決策 / 訂單 / 任一 5 live-auth gate。step-(iv) cleanup
    連同 comparator 退役後本 check 可移除。
"""
from __future__ import annotations

from typing import Any

# ── soak gate 閾值（per PA §5 R5：N 與 freshness threshold 取值，operator 可調）──

# P-EQUIV：comparator 須累積至少 N 筆真實樣本（EQUIV sampler 驅動）才算 soak 有效。
# 預設 200（O-3「N≥數百 lease ops」的保守下界）。organic-only 永遠到不了此 N，
# 故 N 來源必須是 EQUIV sampler（真實樣本回放，per PA §5 R5）。
SOAK_MIN_TOTAL: int = 200

# snapshot 新鮮度上限（秒）：flusher cadence 30s（governance_divergence_flush._FLUSH_
# INTERVAL_S）；threshold 取 300s = 10× cadence，容忍偶發 flush miss / executor 抖動，
# 但 flusher 真死（>5min 無更新）必觸發 stale FAIL。**這是 G-1 / R2 緩解的核心 gate。**
SNAPSHOT_FRESHNESS_MAX_SECONDS: int = 300

# P-LIVE：lease_transitions 新鮮度上限（秒）。Rust 權威路徑 steady-state 應持續 emit；
# 此處取較寬 3600s（1h）——soak 期間 lease emit 率受市場活躍度影響，1h 無任何 Rust
# lease transition 視為權威路徑可能 silent-dead（P-LIVE FAIL）。
LIVE_TRANSITION_FRESHNESS_MAX_SECONDS: int = 3600


def check_81_lease_ipc_soak(cur: Any) -> tuple[str, str]:
    """[81] lease_ipc_soak — SM Option 2 step-(i) soak 雙信號 gate（P-EQUIV + P-LIVE）。

    Verdict（G-1 fail-closed，全部非 PASS 即 FAIL，無 WARN 軟化）：
      * V128 snapshot 表不存在 → FAIL（flusher 投影層未部署，不可當綠燈）。
      * snapshot row 缺失（flusher 從沒成功寫）→ FAIL。
      * flag_enabled=false → FAIL（legacy local SM，comparator 不 fire，counter 無意義）。
      * snapshot stale（updated_at 老於 SNAPSHOT_FRESHNESS_MAX_SECONDS）→ FAIL（flusher
        死，stale divergences==0 偽 pass 防護；R2 緩解）。
      * divergences > 0 → FAIL（comparator 偵測到真分歧；O-2 keep-as-gate）。
      * total < SOAK_MIN_TOTAL → FAIL（樣本不足，soak 未達 N；organic-only 不可達，
        須 EQUIV sampler 驅動）。
      * P-LIVE：lease_transitions 表缺 / 0 row / 最新 row stale → FAIL（Rust 權威路徑
        未跑 / silent-dead）。
      * 全部滿足 → PASS（P-EQUIV 0 divergence over N fresh + P-LIVE Rust 真跑）。

    Returns:
        ``(status, msg)``。msg 含 total/divergences/snapshot age + lease_transitions
        count/age，供 operator triage；FAIL 標明哪個 gate 未過。
    """
    # 防禦性 rollback（鏡 checks_governance 既有 pattern）。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — 防禦性，rollback 失敗非致命
        pass

    # ── P-EQUIV 信號：讀 V128 snapshot row + freshness ──
    # V128 存在性檢查（未 apply → FAIL，投影層缺不可當綠燈）。
    try:
        cur.execute(
            "SELECT to_regclass('learning.lease_ipc_divergence_snapshot') IS NOT NULL"
        )
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[81] lease_ipc_divergence_snapshot existence check failed: {exc}")
    if not exists_row or not exists_row[0]:
        return (
            "FAIL",
            "[81] learning.lease_ipc_divergence_snapshot missing — V128 not applied "
            "(soak observability projection absent; fail-closed, NOT a green light)",
        )

    # 讀 snapshot row + DB-side freshness（用 EXTRACT(EPOCH FROM now()-updated_at) 算
    # age，避免 cron host 與 DB clock skew 影響 freshness 判定 — freshness 權威是
    # DB now() vs DB updated_at）。
    try:
        cur.execute(
            "SELECT total, matches, divergences, flag_enabled, "
            "       EXTRACT(EPOCH FROM (now() - updated_at))::BIGINT AS age_s "
            "FROM learning.lease_ipc_divergence_snapshot "
            "WHERE snapshot_key = 'singleton'"
        )
        snap = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[81] snapshot row query failed: {exc}")

    if snap is None:
        return (
            "FAIL",
            "[81] no snapshot row (flusher never wrote 'singleton') — "
            "fail-closed (cannot treat absent counter as 0 divergence)",
        )

    total = int(snap[0] or 0)
    divergences = int(snap[2] or 0)
    flag_enabled = bool(snap[3])
    snap_age_s = int(snap[4] or 0)

    # flag-OFF → FAIL（comparator 不 fire，counter 無意義；不可當綠燈，G-1）。
    if not flag_enabled:
        return (
            "FAIL",
            "[81] flag_enabled=false (OPENCLAW_LEASE_PYTHON_IPC_ENABLED != '1') — "
            "legacy local SM, comparator not firing; soak NOT in progress (fail-closed)",
        )

    # snapshot stale → FAIL（flusher 死，stale divergences==0 偽 pass 防護；R2 緩解，G-1）。
    if snap_age_s >= SNAPSHOT_FRESHNESS_MAX_SECONDS:
        return (
            "FAIL",
            f"[81] snapshot stale: updated_at age={snap_age_s}s "
            f">= {SNAPSHOT_FRESHNESS_MAX_SECONDS}s — flusher likely dead; "
            f"stale divergences==0 must NOT pass (fail-closed, R2 mitigation)",
        )

    # 真 divergence → FAIL（comparator gate；O-2 keep-as-gate）。
    if divergences > 0:
        return (
            "FAIL",
            f"[81] P-EQUIV FAIL: divergences={divergences} > 0 over total={total} "
            f"(Rust-IPC vs Python-shadow disagreement; inspect get_mismatch_snapshot)",
        )

    # 樣本不足 → FAIL（soak 未達 N；organic-only 不可達，須 EQUIV sampler 驅動）。
    if total < SOAK_MIN_TOTAL:
        return (
            "FAIL",
            f"[81] P-EQUIV insufficient sample: total={total} < N={SOAK_MIN_TOTAL} "
            f"(soak not yet matured; drive comparator via EQUIV sampler — "
            f"organic Python-hub rate is ~0)",
        )

    # ── P-LIVE 信號：lease_transitions Rust 權威路徑真跑（read-only）──
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
    # → FAIL（Rust 權威路徑未跑 / silent-dead；P-LIVE 是 soak gate 必要信號）。
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

    # ── 全 gate 通過：P-EQUIV（0 div over N fresh）AND P-LIVE（Rust 真跑）──
    return (
        "PASS",
        f"[81] soak healthy: P-EQUIV total={total} divergences=0 "
        f"snapshot_age={snap_age_s}s flag=ON; "
        f"P-LIVE lease_transitions count={lt_count} newest_age={lt_age_s}s",
    )


__all__ = [
    "check_81_lease_ipc_soak",
    "SOAK_MIN_TOTAL",
    "SNAPSHOT_FRESHNESS_MAX_SECONDS",
    "LIVE_TRANSITION_FRESHNESS_MAX_SECONDS",
]
