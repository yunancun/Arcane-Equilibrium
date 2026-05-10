"""W5-E1-A P1-CANARY-STAGE-CRITERIA-1 — `[58a]` enrich healthcheck。

MODULE_NOTE:
  W5-E1-A spec
    `docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md`
  §7.4 enrich 加 5 項細粒度 evidence collection：
    1. 每 active cohort × stage 的 promote_condition_met 分項 (PASS/PENDING/FAIL)
    2. 每 active cohort × stage 的 rollback_trigger_tripped (true/false)
    3. 各 metric 當前值 + threshold + margin（per spec §4.3 GUI surface 顯示元素）
    4. 與 V089 governance.canary_stage_metric_registry seed 對齊（metric drift 偵測）
    5. spec / AMD 漂移偵測（registry threshold ≠ spec 公式時 WARN）

  與既有 `[58] check_58_graduated_canary_stage_invariant` 互補：
    - `[58]` 驗 5 hard invariant + invariant 11/12 → verdict-driving
    - `[58a]` 純 evidence collection（latest cohort 對 V089 metric snapshot）→
      verdict 永遠 PASS（除非 V089 未 seed → WARN）

  D+1+ 依賴：
    - W3 spec land 後 cohort metric SQL pipeline 才能跑真實 trading.fills 累計
      （per AMD-2026-05-09-03 §4.2 + spec §2.2 SQL）
    - 本 enrich 暫時只報告 registry 對 active cohort 的 stage 對齊 + metric 存在性
    - W3 land 後 enrich 加 cohort 真實 metric 計算 + margin 對 spec 閾值

  Cron：與 `[58]` 同 cron `0 */6 * * *`（passive_wait_healthcheck schedule）。
  Exit：FAIL → exit 1（silent-dead 自動偵測）；WARN → exit 0 + log。
  純 SELECT；fail-closed：DB 不通 / V089 未 seed 即 WARN（不 FAIL，避免阻塞）。

  Reference: docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md
             §4.1 healthcheck `[58]` enrich + spec §7.4
             docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md
             §2-§5 promote / rollback 公式
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# spec §2-§5 公式對應 metric 期望數量（per stage promote + rollback）
# 對齊 V089 seed：Stage 1=4 promote+1 rollback / Stage 2=5+2 / Stage 3=5+2 /
# Stage 4=0 promote+1 rollback (operator-pinned, no auto-promote)
# ---------------------------------------------------------------------------
EXPECTED_METRIC_COUNT_PER_STAGE: dict[int, dict[str, int]] = {
    1: {"promote": 4, "rollback": 1},
    2: {"promote": 5, "rollback": 2},
    3: {"promote": 5, "rollback": 2},
    4: {"promote": 0, "rollback": 1},
}


def check_58a_stage_criteria_eval(cur: Any) -> tuple[str, str]:
    """[58a] stage_criteria_eval — V089 metric registry seed enrich evidence。

    對 governance.canary_stage_metric_registry active rows，逐 stage 統計：
      - 是否與 EXPECTED_METRIC_COUNT_PER_STAGE 對齊
      - threshold drift 偵測（與 spec §2-§5 公式 byte-identical 驗證留 W5-E1-A
        E2 review，本 healthcheck 只驗 row count + active 數）
      - 對 active cohort（governance.canary_stage_log latest row 取 stage）
        報告該 stage 對應的 promote / rollback metric 列表 + threshold

    Verdict bands:
      * V089 seed 完整（每 stage row count 達 EXPECTED）→ PASS
      * V089 部分 seed / 缺 stage → WARN（spec §8 acceptance #3 ≥12 row 失敗）
      * V080 表缺 → WARN（per [58] 已 hard FAIL，本檢查避免重複）
      * DB exception → WARN（fail-soft，不阻塞 silent-dead 偵測）

    Returns:
        ``(status, msg)`` tuple. msg 含 per-stage seed count + 對齊 spec 註解。
    """
    # 防禦性 rollback — 對齊 [58] / [55] 同 family
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — defensive, rollback failure ≠ fatal
        pass

    # ─────────────────────────────────────────────────────────────────────
    # Pre-check：V089 seed 表存在
    # ─────────────────────────────────────────────────────────────────────
    try:
        cur.execute(
            "SELECT to_regclass('governance.canary_stage_metric_registry') IS NOT NULL"
        )
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[58a] table existence check failed: {exc}")

    if not row or not row[0]:
        return (
            "WARN",
            "[58a] governance.canary_stage_metric_registry missing — V080 not applied "
            "(see [58] for hard FAIL)",
        )

    # ─────────────────────────────────────────────────────────────────────
    # 1. Per-stage active row count（promote / rollback 分開）
    # ─────────────────────────────────────────────────────────────────────
    sql_stage_counts = (
        "SELECT stage, "
        "       count(*) FILTER (WHERE direction IN ('promote_upper','promote_lower')) AS promote_n, "
        "       count(*) FILTER (WHERE direction IN ('rollback_upper','rollback_lower')) AS rollback_n "
        "FROM governance.canary_stage_metric_registry "
        "WHERE active = TRUE "
        "GROUP BY stage "
        "ORDER BY stage"
    )
    try:
        cur.execute(sql_stage_counts)
        stage_count_rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[58a] stage count query failed: {exc}")

    # 建 stage → (promote_n, rollback_n) lookup
    actual: dict[int, tuple[int, int]] = {}
    for r in stage_count_rows:
        actual[int(r[0])] = (int(r[1] or 0), int(r[2] or 0))

    # ─────────────────────────────────────────────────────────────────────
    # 2. 對齊 EXPECTED_METRIC_COUNT_PER_STAGE — 短缺即 WARN
    # ─────────────────────────────────────────────────────────────────────
    drifts: list[str] = []
    total_active = 0
    for stage, expected in EXPECTED_METRIC_COUNT_PER_STAGE.items():
        promote_actual, rollback_actual = actual.get(stage, (0, 0))
        total_active += promote_actual + rollback_actual
        if promote_actual < expected["promote"]:
            drifts.append(
                f"stage={stage} promote count {promote_actual}<{expected['promote']} "
                "(V089 seed incomplete or row deactivated)"
            )
        if rollback_actual < expected["rollback"]:
            drifts.append(
                f"stage={stage} rollback count {rollback_actual}<{expected['rollback']} "
                "(V089 seed incomplete or row deactivated)"
            )

    # ─────────────────────────────────────────────────────────────────────
    # 3. 對 active cohort 取 latest stage，報告該 stage metric 列表
    #    （read-only evidence；不嘗試計算 cohort metric 值，等 W3 land cohort
    #     metric SQL pipeline）
    # ─────────────────────────────────────────────────────────────────────
    try:
        cur.execute(
            "SELECT DISTINCT ON (cohort_id) cohort_id, to_stage "
            "FROM governance.canary_stage_log "
            "ORDER BY cohort_id, created_at_ms DESC"
        )
        cohort_rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        # cohort log 缺 = [58] 已報 FAIL；此 enrich 不重複
        cohort_rows = []
        # 不 return — 仍報告 V089 stage seed 評估
        drifts.append(f"cohort_log query failed: {exc} (see [58] for primary signal)")

    active_cohort_summary: list[str] = []
    for cohort_id, to_stage in cohort_rows:
        to_stage = int(to_stage)
        if to_stage == 0:
            continue  # Stage 0 fail-closed shadow，無 metric 觀察
        promote_n, rollback_n = actual.get(to_stage, (0, 0))
        active_cohort_summary.append(
            f"cohort={cohort_id}@stage={to_stage} promote_metrics={promote_n} "
            f"rollback_metrics={rollback_n}"
        )

    # ─────────────────────────────────────────────────────────────────────
    # 4. 構造 verdict
    # ─────────────────────────────────────────────────────────────────────
    base = (
        f"[58a] stage_criteria_eval — V089 seed total_active={total_active}, "
        f"per_stage={dict(actual)}"
    )

    if active_cohort_summary:
        base += f" — active_cohorts: [{'; '.join(active_cohort_summary[:3])}]"
        if len(active_cohort_summary) > 3:
            base += f" (+{len(active_cohort_summary) - 3} more)"

    if drifts:
        drift_summary = "; ".join(drifts[:3])
        if len(drifts) > 3:
            drift_summary += f" (+{len(drifts) - 3} more)"
        return (
            "WARN",
            f"{base} — drift: {drift_summary} (W5-E1-A spec §8 acceptance #3 ≥12 row, V089 seed)",
        )

    return ("PASS", f"{base} — all stages V089 seeded per spec §2-§5")
