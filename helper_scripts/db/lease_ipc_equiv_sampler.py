#!/usr/bin/env python3
"""
SM Option 2 收斂 — P-EQUIV 真實樣本驅動器（lease_ipc_equiv_sampler）。

!!! DEPRECATED — DO NOT WIRE TO PRODUCTION（operator 拍板 (b)+(b-i)，2026-06-03）!!!
    本 sampler 在 Option 2 下**語意不可達**，已從 soak gate 路徑移除。保留檔案僅為
    防止他人誤以為「P-EQUIV 缺 runtime 腿」而重寫同一個會卡死 gate 的設計。

    為何不可達（E2 HIGH-2 + PA reconciliation
    `2026-06-03--p5_sm_soak_equiv_sampler_reconciliation.md`）：
      - sampler 拿**歷史** Rust-authoritative GRANTED row 對撞 Python hub 的**當前**
        auth state。Option 2 下熱路徑 Rust-only、Python hub 不在熱路徑 → steady-state
        Python hub 結構上未授權（`is_authorized()` 為 False）→ 每筆歷史 GRANTED row 的
        Python 影子回 DENIED → record_divergence 判 divergence → comparator gate 永遠
        卡死無法轉綠。這是 **Option 2 架構下「歷史 replay 驅動 contemporaneous
        comparator」這個設計本身的語意不可達**（lease_transitions/V054 無 per-row
        auth/scope 快照，無法重建歷史 auth context），非 sampler 實作 bug。
      - 既已不接 gate，**HIGH-1（bypass-skip 未對齊 :1052）與 MEDIUM-1（dead event
        分支指錯表 + acquire 雙計）刻意不修**——修無意義。下方 classify_rust_outcome /
        replay_sample_through_comparator 保留原樣僅供歷史參照與 deprecated 測試，**勿據此
        重新接 production**。

    cutover gate 新定義 = **4a CI 綠**（`sm_contract.rs` + `test_sm_contract_parity.py`
    離線全分支 parity，authoritative SM 等價證明）**AND P-LIVE soak 健康**
    （`learning.lease_transitions` Rust 權威路徑真跑 + fresh，見
    `passive_wait_healthcheck/checks_governance_lease_ipc.py`）。comparator 降為觀測性
    信號（非 gate）。runtime 落地保真度由 P-LIVE 覆蓋，不需 sampler。

    （以下原 MODULE_NOTE 保留作歷史背景；其「O-2 keep-as-gate 前提」已被 (b)+(b-i) 推翻。）

MODULE_NOTE（歷史，已 DEPRECATED）:
    模塊用途：解 PA 設計 `2026-06-03--p5_sm_soak_observability_redesign.md` §2
    Fork ②-EQUIV / §5 R5 的核心缺陷——steady-state 下 Python GovernanceHub organic
    觸發率 ≈ 0（熱路徑 ~408k lease 從不進 Python hub），故 comparator 的 N 永遠到
    不了（原空轉偽 pass 根因）。本 sampler 從**真實** `learning.lease_transitions`
    （Rust 權威路徑已寫的表，read-only）取近期 rows，把每筆的真實 lease 語意
    （profile / engine_mode / Rust 權威 outcome）回放過既有 comparator
    （governance_divergence.record_divergence），產生**真實樣本驅動**的 divergence
    count，取代合成猜測（Fork ① 被 PA 廢棄）。

    這曾是 O-2（operator 一度拍板 comparator keep-as-gate）的前提；O-2 已於
    2026-06-03 被 (b)+(b-i) 取代（comparator 降觀測性信號）。

    主要函數：
      - ``fetch_recent_lease_transitions``：read-only SELECT 近期 lease_transitions
        rows（profile / engine_mode / event / to_state / lease_id / ts_ms）。
      - ``classify_rust_outcome``：把 Rust row 的 event/to_state 正規化成 comparator
        OUTCOME_* 標籤（這是 Rust *權威* 判定，非合成）。
      - ``replay_sample_through_comparator``：對每筆 row，rust_outcome 取自真實 row，
        python_outcome 取自**現役 Python SM 影子**（hub._shadow_local_acquire_outcome，
        同 flag-ON 路徑用的判定），呼叫 record_divergence → comparator 計入真實樣本。
      - ``run_equiv_sampler``：CLI 主入口（--limit / --since-ms / --dry-run）。

    依賴：
      - db_pool / psycopg2（read-only SELECT lease_transitions）。
      - governance_divergence（record_divergence / OUTCOME_* / OP_* — 既有 comparator）。
      - governance_routes._get_governance_hub（取現役 hub 算 Python 影子；無 hub → 影子
        回 UNKNOWN no-opinion，不偽造）。

    硬邊界（保真 + fail-soft）：
      - **read-only**：只 SELECT lease_transitions，**不 INSERT/UPDATE/DELETE** 任何
        交易 / lease / SM / 風控狀態。
      - **不偽造流量**：rust_outcome 來自真實 row、python_outcome 來自現役 SM 影子；
        無 hub / 影子無意見 → 顯式 OUTCOME_UNKNOWn（record_divergence 視為 no-opinion
        計入 total、不算 divergence），不臆造判定。
      - **fail-soft**：PG 不可用 / hub 缺失 → log + 回 0 樣本，不拋給 caller。
      - **P-EQUIV confirmatory，非熱路徑測量**：本 sampler 跑在 Python（用真實樣本驅動
        comparator），**不是**在熱路徑上比 Rust↔Python（§1 結論：熱路徑無此可測對象）。
        報告 / PR 必明標此語義，避免被誤讀為「測熱路徑」。

    用法（cron 或 operator 手動，soak 期間驅動 comparator 累積 N）：
        python -m helper_scripts.db.lease_ipc_equiv_sampler --limit 500
        python -m helper_scripts.db.lease_ipc_equiv_sampler --since-ms <epoch_ms> --dry-run

    注意：本 sampler 須在 **API process 內**（與 comparator 同 process）執行才能讓
    record_divergence 寫到同一個 in-memory _COUNTERS（flusher 再投影到 PG）。獨立
    process 跑只會更新該 process 自己的 counter（無用）。故 production 接法 = API
    process 內背景任務或 in-process 觸發；本 CLI 主供測試 / 同-process spike。
    （見 §5 報告：production 接法待 operator 定 cadence。）
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Optional

logger = logging.getLogger(__name__)

# srv root on sys.path（鏡像既有 helper test 慣例，供 -m 與直跑）。
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
if _SRV_ROOT not in sys.path:
    sys.path.insert(0, _SRV_ROOT)

# comparator OUTCOME / OP 標籤（import 失敗 → 模塊不可用，CLI fail-soft 處理）。
try:
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_divergence import (  # noqa: E501
        OP_ACQUIRE,
        OUTCOME_BYPASS,
        OUTCOME_DENIED,
        OUTCOME_GRANTED,
        OUTCOME_UNKNOWN,
        record_divergence,
    )
    _COMPARATOR_AVAILABLE = True
except Exception:  # noqa: BLE001 — import 失敗（路徑/依賴），CLI 報 fail-soft
    _COMPARATOR_AVAILABLE = False
    OP_ACQUIRE = "acquire"
    OUTCOME_GRANTED = "granted"
    OUTCOME_DENIED = "denied"
    OUTCOME_BYPASS = "bypass"
    OUTCOME_UNKNOWN = "unknown"

    def record_divergence(**_kwargs: Any) -> bool:  # type: ignore[misc]
        return True


# 代表性 scope：lease_transitions（V054）不存 scope 欄，僅存 profile/engine_mode/
# event/to_state。Python 影子的 scope 軸需要一個 scope；用 TRADE_ENTRY 作代表性 scope
# （熱路徑最常見的 acquire scope）。**這是 P-EQUIV 的已知保真度限制**：profile /
# engine_mode / Rust outcome 全來自真實 row，但 scope 軸用代表性常量（lease_transitions
# 未持久化 per-row scope）。報告明標此限制（非偽造，是資料來源的欄位約束）。
_REPRESENTATIVE_SCOPE: str = "TRADE_ENTRY"

# Rust event → comparator OUTCOME 映射（event_type 來自 V054 §57-65 canonical 7 值
# + bypass）。這是 Rust *權威* 判定的正規化（非合成）。
#   lease_acquire_success → granted（facade 回 LeaseId::Active）
#   lease_acquire_fail    → denied（facade 回 Err：auth/ttl/sm fail）
#   bypass（to_state/event 含 bypass）→ bypass（Validation/Exploration profile）
# release/get 類 event 不在 acquire-axis 取樣範圍（presence 弱通道，§2 設計只取 acquire）。


def classify_rust_outcome(event: Optional[str], to_state: Optional[str]) -> Optional[str]:
    """把 Rust lease_transitions row 的 event/to_state 正規化成 comparator OUTCOME 標籤。

    回 None 表示此 row 非 acquire-outcome 事件（release/get/中間態）→ caller 跳過
    （本 sampler 只取 acquire-axis：§2 設計主分歧通道）。

    為什麼只取 acquire-outcome：comparator 的主分歧偵測通道是 acquire scope-axis +
    auth-axis（record_divergence 對 release/get presence 弱通道視為 no-opinion）。
    取 acquire-success/fail/bypass 對撞 Python 完整 acquire 影子，保真度最高。
    """
    ev = (event or "").strip().lower()
    st = (to_state or "").strip().upper()

    # bypass：Validation/Exploration profile，Rust 回字面 bypass（to_state 或 event 標記）。
    if "bypass" in ev or st == "BRIDGED" or "bypass" in (to_state or "").lower():
        return OUTCOME_BYPASS
    if ev == "lease_acquire_success" or st == "ACTIVE" or st == "REGISTERED":
        return OUTCOME_GRANTED
    if ev == "lease_acquire_fail" or st == "REJECTED":
        return OUTCOME_DENIED
    # 非 acquire-outcome 事件（release_*/sm_transition/中間 draft 等）→ caller 跳過。
    return None


def fetch_recent_lease_transitions(
    cur: Any,
    *,
    limit: int = 500,
    since_ms: Optional[int] = None,
) -> list[dict[str, Any]]:
    """read-only SELECT 近期 lease_transitions rows（acquire-axis 取樣來源）。

    只讀 profile / engine_mode / event / to_state / lease_id / ts_ms。**不寫任何表。**
    過濾 engine_mode='shadow'（V054 §4 #2：shadow row 非真實權威路徑）。

    Args:
        cur: psycopg2-style DB cursor（read-only SELECT）。
        limit: 取樣上限（最新 N 筆）。
        since_ms: 若給定，只取 ts_ms >= since_ms 的 row（soak 視窗起點）。

    Returns:
        row dict list（最新在前）；查詢失敗回空 list（fail-soft）。
    """
    # 防禦性 rollback（鏡 checks_governance 既有 pattern，避免前一 query 污染）。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — 防禦性，rollback 失敗非致命
        pass

    where = ["engine_mode <> 'shadow'"]
    params: list[Any] = []
    if since_ms is not None:
        where.append("ts_ms >= %s")
        params.append(int(since_ms))
    where_sql = " AND ".join(where)
    sql = (
        "SELECT lease_id, event, to_state, profile, engine_mode, ts_ms "
        "FROM learning.lease_transitions "
        f"WHERE {where_sql} "
        "ORDER BY ts_ms DESC "
        "LIMIT %s"
    )
    params.append(int(limit))
    try:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 — fail-soft，回空 list
        logger.warning(
            "lease_ipc_equiv_sampler: lease_transitions query failed (fail-soft): %s / "
            "lease_transitions 查詢失敗（fail-soft）：%s",
            exc, exc,
        )
        return []

    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "lease_id": r[0],
            "event": r[1],
            "to_state": r[2],
            "profile": r[3],
            "engine_mode": r[4],
            "ts_ms": r[5],
        })
    return out


def _python_shadow_outcome(hub: Any, scope: str) -> str:
    """取現役 Python SM 對此 scope 的影子判定（同 flag-ON 路徑用的判定）。

    無 hub / 影子計算失敗 → OUTCOME_UNKNOWN（no-opinion；record_divergence 計入 total、
    不算 divergence）。**不偽造判定**——Python 無獨立意見就顯式標 UNKNOWN。
    """
    if hub is None:
        return OUTCOME_UNKNOWN
    shadow_fn = getattr(hub, "_shadow_local_acquire_outcome", None)
    if shadow_fn is None:
        return OUTCOME_UNKNOWN
    try:
        return shadow_fn(scope)
    except Exception:  # noqa: BLE001 — 影子 best-effort，無意見記 UNKNOWN
        return OUTCOME_UNKNOWN


def replay_sample_through_comparator(
    rows: list[dict[str, Any]],
    hub: Any,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """把真實 lease_transitions rows 回放過 comparator（record_divergence）。

    每筆：rust_outcome 取自真實 row（classify_rust_outcome）；python_outcome 取自現役
    Python SM 影子（_python_shadow_outcome，同 flag-ON 路徑判定）。呼叫 record_divergence
    → comparator 計入真實樣本（flusher 再投影到 PG）。

    dry_run=True：只分類 + 統計，**不**呼叫 record_divergence（測試 / 預覽用，不污染
    comparator counter）。

    Returns:
        統計 dict：{sampled, replayed, skipped_non_acquire, matches, divergences, no_opinion}。
    """
    stats = {
        "sampled": len(rows),
        "replayed": 0,
        "skipped_non_acquire": 0,
        "matches": 0,
        "divergences": 0,
        "no_opinion": 0,
    }
    for row in rows:
        rust_outcome = classify_rust_outcome(row.get("event"), row.get("to_state"))
        if rust_outcome is None:
            # 非 acquire-outcome 事件（release/get/中間態）→ 跳過（§2 只取 acquire-axis）。
            stats["skipped_non_acquire"] += 1
            continue

        python_outcome = _python_shadow_outcome(hub, _REPRESENTATIVE_SCOPE)
        is_no_opinion = (
            rust_outcome == OUTCOME_UNKNOWN or python_outcome == OUTCOME_UNKNOWN
        )

        if not dry_run:
            # record_divergence 自身 best-effort（絕不拋）；回傳是否視為 match。
            matched = record_divergence(
                op=OP_ACQUIRE,
                rust_outcome=rust_outcome,
                python_outcome=python_outcome,
                intent_id=None,
                scope=_REPRESENTATIVE_SCOPE,
                profile=row.get("profile"),
                lease_id=row.get("lease_id"),
            )
        else:
            matched = is_no_opinion or (rust_outcome == python_outcome)

        stats["replayed"] += 1
        if is_no_opinion:
            stats["no_opinion"] += 1
            stats["matches"] += 1  # no-opinion 計為 match（對齊 record_divergence 語義）
        elif matched:
            stats["matches"] += 1
        else:
            stats["divergences"] += 1
    return stats


def run_equiv_sampler(
    *,
    limit: int = 500,
    since_ms: Optional[int] = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """CLI 主入口：取真實 lease_transitions rows → 回放過 comparator。

    fail-soft：comparator 不可用 / PG 不可用 / 無 hub → log + 回 0 樣本統計，不拋。
    """
    if not _COMPARATOR_AVAILABLE:
        logger.warning(
            "lease_ipc_equiv_sampler: comparator module unavailable (import failed); "
            "0 samples / comparator 模塊不可用，0 樣本"
        )
        return {"sampled": 0, "replayed": 0, "skipped_non_acquire": 0,
                "matches": 0, "divergences": 0, "no_opinion": 0,
                "available": 0}

    # 取現役 hub（同 process 才有；獨立 process 跑 hub=None → 影子 UNKNOWN no-opinion）。
    hub: Any = None
    try:
        from program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_routes import (  # noqa: E501
            _get_governance_hub,
        )
        hub = _get_governance_hub()
    except Exception as exc:  # noqa: BLE001 — 無 hub fail-soft（影子記 UNKNOWN）
        logger.info(
            "lease_ipc_equiv_sampler: governance hub unavailable (%s); "
            "python shadow → UNKNOWN no-opinion / 無現役 hub，影子記 UNKNOWN",
            exc,
        )

    # read-only PG 連線取 rows。
    try:
        from program_code.exchange_connectors.bybit_connector.control_api_v1.app.db_pool import (  # noqa: E501
            get_pg_conn,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("lease_ipc_equiv_sampler: db_pool import failed (fail-soft): %s", exc)
        return {"sampled": 0, "replayed": 0, "skipped_non_acquire": 0,
                "matches": 0, "divergences": 0, "no_opinion": 0, "available": 1}

    with get_pg_conn() as conn:
        if conn is None:
            logger.warning(
                "lease_ipc_equiv_sampler: PG unavailable (fail-soft); 0 samples / "
                "PG 不可用，0 樣本"
            )
            return {"sampled": 0, "replayed": 0, "skipped_non_acquire": 0,
                    "matches": 0, "divergences": 0, "no_opinion": 0, "available": 1}
        with conn.cursor() as cur:
            rows = fetch_recent_lease_transitions(cur, limit=limit, since_ms=since_ms)

    stats = replay_sample_through_comparator(rows, hub, dry_run=dry_run)
    stats["available"] = 1
    logger.info(
        "lease_ipc_equiv_sampler: sampled=%d replayed=%d skipped_non_acquire=%d "
        "matches=%d divergences=%d no_opinion=%d dry_run=%s",
        stats["sampled"], stats["replayed"], stats["skipped_non_acquire"],
        stats["matches"], stats["divergences"], stats["no_opinion"], dry_run,
    )
    return stats


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "SM Option 2 P-EQUIV 真實樣本驅動器：從真實 learning.lease_transitions "
            "取近期 rows 回放過 comparator（read-only；P-EQUIV confirmatory 非熱路徑測量）。"
        )
    )
    p.add_argument("--limit", type=int, default=500, help="取樣上限（最新 N 筆 lease_transitions）")
    p.add_argument("--since-ms", type=int, default=None, help="只取 ts_ms >= 此 epoch ms 的 row")
    p.add_argument(
        "--dry-run", action="store_true",
        help="只分類統計，不呼叫 record_divergence（不污染 comparator counter）",
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _build_arg_parser().parse_args(argv)
    stats = run_equiv_sampler(limit=args.limit, since_ms=args.since_ms, dry_run=args.dry_run)
    # exit 0：成功取樣（含 0 樣本 fail-soft，非錯誤）；本 sampler 不作 gate 判定（gate
    # 由 healthcheck 讀 PG snapshot 判）。
    print(  # noqa: T201 — CLI 輸出供 operator
        "lease_ipc_equiv_sampler: " + ", ".join(f"{k}={v}" for k, v in stats.items())
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
