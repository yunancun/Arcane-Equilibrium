"""LG-5 governance healthchecks — `[42]` + `[42b]`.
LG-5 治理層 healthcheck — `[42]` + `[42b]`。

MODULE_NOTE (EN): Two passive-wait sentinels for the LG-5
``review_live_candidate`` contract per RFC v2 (2026-05-02):

* ``check_42_live_candidate_eval_contract`` — verifies that every newly
  inserted ``learning.mlde_param_applications`` row with
  ``application_type='live_promotion_candidate'`` has a matching
  ``learning.governance_audit_log`` row whose ``event_type =
  'review_live_candidate'`` ties it to a Decision Lease verdict within
  one hour of the candidate's ``ts``. Catches GovernanceHub silent
  failures where the consumer (LG-5-IMPL-2) drops candidates without
  emitting a verdict — without this sentinel, candidates would queue
  forever in ``status='candidate'`` and live promotion would deadlock
  invisibly. Implements RFC v2 §6 IMPL-3 line 451-454 + §4 lease-revoke
  trigger (line 404).

* ``check_42b_live_candidate_attribution_drift`` — per-strategy 7d
  rolling attribution_chain_ratio (production data quality signal sliced
  per strategy). Three-band verdict per RFC v2 §6 IMPL-3 line 451:
  PASS = every LG-5 strategy ≥ 0.50 (R-meta floor, RFC §3 line 366-367);
  WARN = worst in [0.30, 0.50) (defer expected); FAIL = worst in
  [0.10, 0.30) (standard FAIL band, attribution producer degraded);
  FAIL pipeline-alert = worst < 0.10 (RFC §3 line 377 + §4
  lease_revoke_trigger line 405; GovernanceHub must auto-revoke active
  leases — this check just surfaces the alarm).

Both functions follow the existing healthcheck contract:
  - signature: ``(cur) -> tuple[str, str]``
  - status string ∈ {"PASS", "WARN", "FAIL"}
  - msg string is human-readable diagnostic
  - DB unreachable / table missing → fail-closed FAIL with reason; pure
    SELECTs only (no INSERT / UPDATE) so safe inside cron loop.

MODULE_NOTE (中): RFC v2 §6 IMPL-3 規定的 LG-5 兩個被動等待哨兵 ——
``[42]`` 驗 ``review_live_candidate`` 1 小時 SLA + audit row 寫入；
``[42b]`` 監控 5 個 LG-5 strategy 7d 滾動 ``attribution_chain_ratio``，
三段判定（RFC §6 IMPL-3 line 451）：PASS ≥ 0.50 / WARN [0.30, 0.50) /
FAIL [0.10, 0.30) / FAIL pipeline-alert < 0.10（觸發 lease_revoke）。
介面對齊既有 check：``(cur) -> (status, msg)``，純 SELECT、fail-closed、
cron 安全。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# RFC v2 §3 R-meta + §4 lease_revoke_triggers thresholds.
# RFC v2 §3 R-meta + §4 lease_revoke_triggers 閾值。
# ---------------------------------------------------------------------------
# Five LG-5 strategies per RFC v2 §3 R-meta — attribution dict keyed by
# these strategy names. Missing strategy → defer (producer bug, treated as
# 0.0 ratio for this healthcheck so it surfaces). Keep in sync with
# strategy_params_demo.toml [<strategy>] sections + scout/strategist allow-list.
# 五個 LG-5 strategy（RFC v2 §3）— attribution dict 以這些 key 切片。
# Missing strategy 視為 0.0（暴露 producer bug）。與 strategy_params_demo.toml
# 同步。
LG5_STRATEGIES: tuple[str, ...] = (
    "grid_trading",
    "ma_crossover",
    "bb_breakout",
    "bb_reversion",
    "funding_arb",
)

# RFC v2 §6 IMPL-3 line 451 mandates three bands for `[42b]` per-strategy 7d
# rolling attribution_chain_ratio drift: PASS/WARN/FAIL = 0.50/0.30/0.10.
# Round 1 collapsed [0.30, 0.50) WARN with [0.10, 0.30) FAIL into a single
# WARN band (alarm severity under-call); round 2 restores the third boundary.
# Pipeline-alert escalation still triggers below FAIL_FLOOR (0.10) per RFC §3
# line 377 + §4 lease_revoke_trigger line 405.
# RFC v2 §6 IMPL-3 line 451 明定 `[42b]` 三段閾值：PASS/WARN/FAIL =
# 0.50/0.30/0.10。Round 1 把 [0.30, 0.50) WARN 與 [0.10, 0.30) FAIL 合併成
# 單一 WARN（嚴重度 under-call），round 2 還原三 boundary。低於 0.10 仍升
# pipeline-alert（RFC §3 line 377 + §4 lease_revoke_trigger line 405）。
ATTRIBUTION_RATIO_PASS_FLOOR: float = 0.50
ATTRIBUTION_RATIO_WARN_FLOOR: float = 0.30
ATTRIBUTION_RATIO_FAIL_FLOOR: float = 0.10

# `[42]` 1h SLA per RFC v2 §6 IMPL-3 line 451-454.
# `[42]` 1h SLA（RFC v2 §6 IMPL-3 line 451-454）。
CANDIDATE_AUDIT_SLA_INTERVAL: str = "interval '1 hour'"
RECENT_CANDIDATE_WINDOW: str = "interval '24 hours'"
ATTRIBUTION_DRIFT_WINDOW: str = "interval '7 days'"

# Severity bands for `[42]` unaudited candidate count.
# `[42]` 未審計候選數的嚴重度分級。
UNAUDITED_PASS_MAX: int = 0
UNAUDITED_WARN_MAX: int = 2  # > 2 → FAIL


def check_42_live_candidate_eval_contract(cur) -> tuple[str, str]:
    """[42] live_candidate_eval_contract — every >1h-old live candidate must
    have a ``review_live_candidate`` audit row. SLA = 1h per RFC v2 §6.

    [42] live_candidate_eval_contract — 每個建立 >1h 的 live candidate 都
    必須有對應 ``review_live_candidate`` audit row。SLA = 1h（RFC v2 §6）。

    Catches:
        * GovernanceHub silent failure — candidate inserted by
          ``mlde_demo_applier._insert_live_candidate`` (LG-5-IMPL-1) but
          ``GovernanceHub.review_live_candidate`` (LG-5-IMPL-2) never
          fires → candidate queues forever, live promotion deadlocks.
        * Consumer crash / lock contention — ``review_live_candidate``
          starts but throws before INSERT into ``governance_audit_log``.
        * V035 not deployed — ``governance_audit_log`` missing → FAIL
          fast (must apply migration first).

    捕捉：
        * GovernanceHub 靜默失敗 — IMPL-1 寫入 candidate 但 IMPL-2 從未
          觸發 → candidate 永遠卡 ``status='candidate'``。
        * Consumer crash / 鎖競爭 — ``review_live_candidate`` 跑到一半
          就拋例外、沒寫 audit row。
        * V035 沒部署 — ``governance_audit_log`` 不存在 → 直接 FAIL。

    Verdict bands / 結果分級:
        * unaudited == 0 → PASS
        * 1 <= unaudited <= 2 → WARN（小規模延遲，可能 GovernanceHub 排隊中）
        * unaudited >= 3 → FAIL（contract 系統性破裂；RFC §4 line 404
          lease_revoke_trigger 觸發；engine 應自動撤銷 lease）

    Returns:
        ``(status, msg)`` tuple.
    """
    # Defensive rollback before each query to detach from any prior aborted txn
    # in the cursor's connection (mirrors checks_execution.py pattern).
    # 在每次 query 前保險 rollback，避免上一個 query 例外殘留 aborted txn。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — defensive, rollback failure ≠ fatal
        pass

    # Existence pre-check — both tables required. Fail-closed if either missing.
    # 表存在檢查 — 任一缺即 fail-closed FAIL。
    try:
        cur.execute(
            "SELECT to_regclass('learning.mlde_param_applications') IS NOT NULL, "
            "       to_regclass('learning.governance_audit_log') IS NOT NULL"
        )
        exists = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[42] table existence check failed: {exc}")

    if not exists or not exists[0]:
        return (
            "FAIL",
            "[42] learning.mlde_param_applications missing — V032 not applied",
        )
    if not exists or not exists[1]:
        return (
            "FAIL",
            "[42] learning.governance_audit_log missing — V035 not applied",
        )

    # Count unaudited candidates older than 1h. NOT EXISTS subquery against
    # governance_audit_log scoped to event_type='review_live_candidate' —
    # other event types (lease_grant / lease_auto_revoke / bulk_re_evaluation /
    # audit_write_failed) do not satisfy the contract on their own.
    #
    # 統計 >1h 老但無 review_live_candidate audit row 的 candidate 數。
    # NOT EXISTS subquery 限於 event_type='review_live_candidate' —
    # 其他 event_type（lease_grant / lease_auto_revoke / bulk_re_evaluation /
    # audit_write_failed）不算滿足 contract。
    sql_unaudited = (
        "SELECT count(*)::int AS unaudited_candidates "
        "FROM learning.mlde_param_applications c "
        "WHERE c.engine_mode = 'live' "
        "  AND c.application_type = 'live_promotion_candidate' "
        "  AND c.status = 'candidate' "
        f"  AND c.ts < now() - {CANDIDATE_AUDIT_SLA_INTERVAL} "
        "  AND NOT EXISTS ( "
        "    SELECT 1 FROM learning.governance_audit_log a "
        "    WHERE a.candidate_id = c.id "
        "      AND a.event_type = 'review_live_candidate' "
        "  )"
    )
    try:
        cur.execute(sql_unaudited)
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[42] unaudited-candidates query failed: {exc}")

    unaudited = int(row[0] or 0) if row else 0

    # Context: total recent candidates (24h) for dashboard situational awareness.
    # 上下文：24h 累積候選總數，dashboard 提供 situational awareness。
    sql_recent_total = (
        "SELECT count(*)::int "
        "FROM learning.mlde_param_applications "
        "WHERE engine_mode = 'live' "
        "  AND application_type = 'live_promotion_candidate' "
        f"  AND ts > now() - {RECENT_CANDIDATE_WINDOW}"
    )
    try:
        cur.execute(sql_recent_total)
        recent_row = cur.fetchone()
        recent_total = int(recent_row[0] or 0) if recent_row else 0
    except Exception:  # noqa: BLE001 — context only, do not flip verdict on this
        recent_total = -1  # sentinel: query failed but main verdict still valid

    base = (
        f"recent_24h_total={recent_total}, "
        f"unaudited_over_1h={unaudited}"
    )

    if unaudited <= UNAUDITED_PASS_MAX:
        return (
            "PASS",
            base + " — review_live_candidate contract intact (1h SLA)",
        )
    if unaudited <= UNAUDITED_WARN_MAX:
        return (
            "WARN",
            base + " — small backlog; possible GovernanceHub queuing or recent restart",
        )
    return (
        "FAIL",
        base
        + " — review_live_candidate contract broken; check GovernanceHub.review_live_candidate "
        "consumer health (RFC v2 §4 lease_revoke_trigger fires)",
    )


def check_42b_live_candidate_attribution_drift(cur) -> tuple[str, str]:
    """[42b] live_candidate_attribution_drift — per-strategy 7d rolling
    ``attribution_chain_ok`` ratio drift detector for the 5 LG-5
    strategies (per RFC v2 §3 R-meta + MIT MF-M5).

    [42b] live_candidate_attribution_drift — 5 個 LG-5 strategy 的 7d
    滾動 ``attribution_chain_ok`` ratio 漂移偵測（RFC v2 §3 R-meta + MIT MF-M5）。

    Verdict bands / 結果分級（RFC v2 §6 IMPL-3 line 451 三段）:
        * all 5 strategies ≥ 0.50 → PASS（RFC §3 R-meta floor）
        * worst in [0.30, 0.50) → WARN（below R-meta 0.50 floor;
          review_live_candidate defer 觸發，但仍在標準 WARN 區間）
        * worst in [0.10, 0.30) → FAIL（standard FAIL band, attribution
          chain 系統性衰退，operator must investigate producer side）
        * worst < 0.10 → FAIL pipeline-alert（RFC §3 line 377 + §4
          lease_revoke_trigger line 405；任何使用此 strategy 的 active
          lease 應被 GovernanceHub 自動撤銷）

    Missing strategy in `mlde_edge_training_rows` is treated as ratio = 0.0
    so the alert fires (producer-side bug exposed instead of hidden).
    缺 strategy = ratio 0.0 強制觸發告警（暴露 producer bug，而非隱藏）。

    Returns:
        ``(status, msg)`` tuple. msg includes worst strategy + its ratio
        + per-strategy summary so operator can identify which strategy's
        attribution chain regressed.
    """
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001
        pass

    # V031 hypertable existence — required for this check.
    # V031 表不存在直接 FAIL。
    try:
        cur.execute(
            "SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL"
        )
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[42b] view existence check failed: {exc}")
    if not exists_row or not exists_row[0]:
        return (
            "FAIL",
            "[42b] learning.mlde_edge_training_rows missing — V031 not applied",
        )

    # Per-strategy 7d ratio. engine_mode filter MUST match IMPL-1 producer
    # `_compute_attribution_chain_ratio_by_strategy`
    # (program_code/ml_training/mlde_demo_applier.py:907-920) exactly:
    # ``engine_mode IN ('demo', 'live_demo')`` — the drift sentinel must
    # measure the SAME source the producer feeds the consumer (LG-5-IMPL-2
    # `GovernanceHub.review_live_candidate`). Including 'live' here would
    # diverge from the producer's input set and yield false alarms / false
    # reassurance vs the actual ratio R-meta sees.
    # Per-strategy 7d 比率；engine_mode filter 必對齊 IMPL-1 producer
    # `_compute_attribution_chain_ratio_by_strategy` 的 `IN ('demo','live_demo')`
    # —— sentinel 必須測 producer 餵給 consumer 的同一資料源，否則 drift
    # 訊號失真（會 false alarm / false reassurance）。
    sql = (
        "SELECT strategy_name, "
        "       count(*)::int AS total, "
        "       count(*) FILTER (WHERE attribution_chain_ok)::int AS chain_ok, "
        "       (count(*) FILTER (WHERE attribution_chain_ok))::float "
        "         / nullif(count(*), 0)::float AS ratio "
        "FROM learning.mlde_edge_training_rows "
        f"WHERE ts > now() - {ATTRIBUTION_DRIFT_WINDOW} "
        "  AND engine_mode IN ('demo', 'live_demo') "
        "  AND strategy_name IS NOT NULL "
        "GROUP BY strategy_name"
    )
    try:
        cur.execute(sql)
        rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[42b] attribution-ratio query failed: {exc}")

    # Build per-strategy ratio dict; missing → 0.0 (forces alarm).
    # 建 per-strategy ratio dict；missing → 0.0（強制告警）。
    ratios: dict[str, float] = {}
    totals: dict[str, int] = {}
    for r in rows or []:
        name = r[0]
        if name not in LG5_STRATEGIES:
            continue
        total = int(r[1] or 0)
        ratio = float(r[3]) if r[3] is not None else 0.0
        ratios[name] = ratio
        totals[name] = total

    # Force-fill missing strategies with ratio=0.0 / total=0 so they alarm.
    # 缺 strategy 強制 ratio=0.0 / total=0 觸發告警。
    for s in LG5_STRATEGIES:
        if s not in ratios:
            ratios[s] = 0.0
            totals[s] = 0

    # First-deploy / quiet-window grace: if EVERY LG-5 strategy has total=0
    # within 7d, no production traffic exists yet — emit WARN (not FAIL),
    # because forcing FAIL would alarm on greenfield deploy. Single missing
    # strategy still falls through to standard band logic (= 0.0 ratio).
    # 全 5 strategy 7d 內 0 row → WARN（未部署 / 全靜默；FAIL 過嚴）。
    if all(totals[s] == 0 for s in LG5_STRATEGIES):
        return (
            "WARN",
            "[42b] no MLDE training rows for any LG-5 strategy in 7d — "
            "first-deploy or production silent; cannot evaluate attribution drift",
        )

    # Determine worst strategy (lowest ratio) for the verdict + msg.
    # 找最差 strategy（最低 ratio）作為 verdict + msg。
    worst_strategy = min(LG5_STRATEGIES, key=lambda s: ratios[s])
    worst_ratio = ratios[worst_strategy]

    summary = ", ".join(
        f"{s}={ratios[s]:.3f}(n={totals[s]})" for s in LG5_STRATEGIES
    )
    base = (
        f"7d per-strategy attribution_chain_ok ratio: {summary}; "
        f"worst={worst_strategy}@{worst_ratio:.3f}"
    )

    # Three-band verdict per RFC v2 §6 IMPL-3 line 451
    # (PASS/WARN/FAIL = 0.50/0.30/0.10) + §3 line 377 pipeline-alert escalation.
    # 三段判定（RFC v2 §6 IMPL-3 line 451）+ §3 line 377 pipeline-alert 升級。
    if worst_ratio >= ATTRIBUTION_RATIO_PASS_FLOOR:
        return ("PASS", base + " — all strategies ≥ 0.50 R-meta floor")
    if worst_ratio >= ATTRIBUTION_RATIO_WARN_FLOOR:
        return (
            "WARN",
            base
            + f" — {worst_strategy} below R-meta 0.50 floor; "
            "review_live_candidate will defer for this strategy",
        )
    if worst_ratio >= ATTRIBUTION_RATIO_FAIL_FLOOR:
        return (
            "FAIL",
            base
            + f" — {worst_strategy} below 0.30 standard FAIL floor; "
            "attribution chain systemically degraded — investigate producer "
            "(MIT-S2-1 attribution_chain_ok writer)",
        )
    return (
        "FAIL",
        base
        + f" — {worst_strategy} below 0.10 pipeline-alert floor "
        "(RFC v2 §4 lease_revoke_trigger fires; "
        "GovernanceHub must auto-revoke active leases)",
    )
