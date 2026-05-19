"""LG-5 governance healthchecks — `[42]` + `[42b]` + `[42c]` + `[43]`.
LG-5 治理層 healthcheck — `[42]` + `[42b]` + `[42c]` + `[43]`。

MODULE_NOTE (EN): Four passive-wait sentinels for the LG-5
``review_live_candidate`` contract + label backfill cron freshness
per RFC v2 + LG5-W3-FUP-2 Fix 1 + Fix 2 (2026-05-02):

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

* ``check_42c_live_candidate_attribution_drift_3d`` — LG5-W3-FUP-2 Fix 2
  (2026-05-02 RFC §5 Plan B) gate-aligned mirror of ``[42b]``. Identical
  SQL shape / engine_mode filter / threshold bands but uses 3d window
  instead of 7d, aligning with producer
  ``mlde_demo_applier._R_META_WINDOW_DAYS = 3`` shipped by Fix 2 IMPL-1.
  ``[42b]`` keeps 7d as long-window observability sentinel; ``[42c]``
  surfaces the exact ratio R-meta gate consumer reads right now so
  operator does not have to mentally reconcile 7d/3d window dual view
  on `[42b]` PASS + R-meta defer behavior.

* ``check_43_label_backfill_freshness`` — LG5-W3-FUP-2 Fix 1 cron
  liveness sentinel. Reads ``max(label_filled_at)`` from
  ``learning.decision_features`` for engine_modes ``('demo','live_demo')``
  and verdicts on age: PASS <2h, WARN <6h, FAIL >=6h or no rows.
  Catches silent death of the new ``edge_label_backfill_cron.sh``
  (cron schedule */30 * * * *). Without this sentinel, cron stoppage
  would drag ``[42b] attribution_chain_ok`` ratio back below R-meta
  floor within ~24h with no upstream signal — MIT's FUP-2 root-cause
  diagnosis confirmed this exact failure mode (manual run ~2h before
  detection, grid 75% / ma_crossover 45% NULL labels).

All three functions follow the existing healthcheck contract:
  - signature: ``(cur) -> tuple[str, str]``
  - status string ∈ {"PASS", "WARN", "FAIL"}
  - msg string is human-readable diagnostic
  - DB unreachable / table missing → fail-closed FAIL with reason; pure
    SELECTs only (no INSERT / UPDATE) so safe inside cron loop.

MODULE_NOTE (中): RFC v2 §6 IMPL-3 + LG5-W3-FUP-2 Fix 1/Fix 2 四個被動
等待哨兵 —— ``[42]`` 驗 ``review_live_candidate`` 1 小時 SLA + audit row
寫入；``[42b]`` 監控 5 個 LG-5 strategy 7d 滾動 ``attribution_chain_ratio``，
三段判定（RFC §6 IMPL-3 line 451）：PASS ≥ 0.50 / WARN [0.30, 0.50) /
FAIL [0.10, 0.30) / FAIL pipeline-alert < 0.10（觸發 lease_revoke）。
``[42c]`` LG5-W3-FUP-2 Fix 2（2026-05-02 RFC §5 方案 B）— ``[42b]`` 的
R-meta gate 對齊鏡像，閾值結構完全一致但 window 改 3d 對齊 producer
``_R_META_WINDOW_DAYS = 3``；``[42b]`` 保 7d 作 long-window observability，
``[42c]`` surface R-meta gate 當下吃到的 ratio。
``[43]`` 監控 ``edge_label_backfill_cron.sh`` 30 分鐘 cron 是否仍跑：
讀 ``max(label_filled_at)``，PASS <2h / WARN <6h / FAIL >=6h（含無 row）；
覆蓋 cron 靜默死亡 → 24h 內 ``[42b]`` 跌回 R-meta floor 以下的 MIT
FUP-2 root-cause 失效模式。
介面對齊既有 check：``(cur) -> (status, msg)``，純 SELECT、fail-closed、
cron 安全。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# RFC v2 §3 R-meta + §4 lease_revoke_triggers thresholds.
# RFC v2 §3 R-meta + §4 lease_revoke_triggers 閾值。
# ---------------------------------------------------------------------------
# Five LG-5 strategies per RFC v2 §3 R-meta — attribution dict keyed by
# these strategy names. Missing / low-sample strategies are a sample-maturity
# watch, not a ratio failure. Keep in sync with strategy_params_demo.toml
# [<strategy>] sections + scout/strategist allow-list.
# 五個 LG-5 strategy（RFC v2 §3）— attribution dict 以這些 key 切片。
# Missing / low-sample strategy 是樣本成熟度 watch，不是 ratio failure。
# 與 strategy_params_demo.toml 同步。
LG5_STRATEGIES: tuple[str, ...] = (
    "grid_trading",
    "ma_crossover",
    "bb_breakout",
    "bb_reversion",
    "funding_arb",
)
LG5_STRATEGY_SQL_IN: str = (
    "('grid_trading','ma_crossover','bb_breakout','bb_reversion','funding_arb')"
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
ATTRIBUTION_MIN_SETTLED_SAMPLES: int = 10

# `[42]` 1h SLA per RFC v2 §6 IMPL-3 line 451-454.
# `[42]` 1h SLA（RFC v2 §6 IMPL-3 line 451-454）。
CANDIDATE_AUDIT_SLA_INTERVAL: str = "interval '1 hour'"
RECENT_CANDIDATE_WINDOW: str = "interval '24 hours'"
ATTRIBUTION_DRIFT_WINDOW: str = "interval '7 days'"

# `[42c]` window — gate-aligned mirror of `[42b]` per LG5-W3-FUP-2 Fix 2
# RFC §5 (2026-05-02 amendment). Producer
# `mlde_demo_applier._compute_attribution_chain_ratio_by_strategy` now uses
# `_R_META_WINDOW_DAYS = 3` (instead of the original 7d) so the R-meta gate
# reads "post-bug-fix" 3d slice and is not over-penalized by 4/24-28 bug-era
# residual samples. `[42b]` keeps 7d as long-window observability sentinel;
# `[42c]` mirrors it with 3d so operator can directly read the ratio R-meta
# gate sees right now (RFC §5 Plan B "dual-window" wording, line 234-263).
# `[42c]` window — `[42b]` 的 R-meta gate 對齊鏡像（LG5-W3-FUP-2 Fix 2
# RFC §5 方案 B）。Producer 已將 ratio 計算 window 從 7d 縮 3d
# (`_R_META_WINDOW_DAYS = 3`) 對齊「已修 bug 後」純後時段；`[42b]` 保 7d
# 作 long-window observability，`[42c]` 鏡 3d 讓 operator 直接看到 R-meta
# gate 當下吃到的 ratio，避免 7d/3d 雙窗解讀斷層。
ATTRIBUTION_DRIFT_WINDOW_3D: str = "interval '3 days'"

# Severity bands for `[42]` unaudited candidate count.
# `[42]` 未審計候選數的嚴重度分級。
UNAUDITED_PASS_MAX: int = 0
UNAUDITED_WARN_MAX: int = 2  # > 2 → FAIL


def _format_attribution_summary(
    ratios: dict[str, float], totals: dict[str, int]
) -> str:
    parts: list[str] = []
    for strategy in LG5_STRATEGIES:
        total = totals[strategy]
        if total < ATTRIBUTION_MIN_SETTLED_SAMPLES:
            need = ATTRIBUTION_MIN_SETTLED_SAMPLES - total
            parts.append(f"{strategy}=LOW_SAMPLE(n={total}, need={need})")
        else:
            parts.append(f"{strategy}={ratios[strategy]:.3f}(n={total})")
    return ", ".join(parts)


def _format_low_sample_watch(totals: dict[str, int], low_samples: list[str]) -> str:
    if not low_samples:
        return ""
    details = ", ".join(
        f"{strategy}(n={totals[strategy]}, need={ATTRIBUTION_MIN_SETTLED_SAMPLES - totals[strategy]})"
        for strategy in low_samples
    )
    return (
        "sample-maturity watch only; low settled sample strategies "
        f"(floor n>={ATTRIBUTION_MIN_SETTLED_SAMPLES}): {details}; "
        "R-meta will defer those strategies, but this is not attribution drift"
    )


def _attribution_ratio_sql(window: str) -> str:
    """Build the light attribution-ratio query for [42b]/[42c].

    `learning.mlde_edge_training_rows` is the canonical semantic view, but it
    also builds feature vectors and decision-context lateral joins that [42b]
    and [42c] do not read. On trade-core that made the passive healthcheck time
    out before emitting the actual attribution signal. Anchor the query on
    settled `decision_features` rows, build the valid intent -> signal context
    set once, then hash-join labels against it. This keeps the denominator
    identical for settled labels while avoiding per-row lateral lookups. The
    supporting runtime indexes are landed by V097. This query mirrors only the
    columns needed for the ratio:
      - normalized LG-5 strategy name
      - settled reward (`decision_features.label_net_edge_bps`)
      - attribution-chain proof (`intents.signal_id/context_id` has a matching
        signal row and a settled reward)
    """
    return (
        "WITH labeled AS ( "
        "  SELECT "
        "    df.label_net_edge_bps, "
        "    df.context_id, "
        "    CASE lower(COALESCE(NULLIF(df.strategy_name, ''), 'unknown')) "
        "      WHEN 'bollinger_reversion' THEN 'bb_reversion' "
        "      WHEN 'bb_reversion' THEN 'bb_reversion' "
        "      WHEN 'bb_breakout' THEN 'bb_breakout' "
        "      WHEN 'ma_crossover' THEN 'ma_crossover' "
        "      WHEN 'grid_trading' THEN 'grid_trading' "
        "      WHEN 'funding_arb' THEN 'funding_arb' "
        "      ELSE lower(COALESCE(NULLIF(df.strategy_name, ''), 'unknown')) "
        "    END AS strategy_name "
        "  FROM learning.decision_features df "
        f"  WHERE df.ts > now() - {window} "
        "    AND df.engine_mode IN ('demo', 'live_demo') "
        f"    AND df.strategy_name IN {LG5_STRATEGY_SQL_IN} "
        "    AND df.label_net_edge_bps IS NOT NULL "
        "), valid_contexts AS MATERIALIZED ( "
        "  SELECT DISTINCT i.context_id "
        "  FROM trading.intents i "
        "  JOIN trading.signals s "
        "    ON s.signal_id = i.signal_id "
        "   AND s.context_id = i.context_id "
        f"  WHERE i.ts > now() - {window} "
        "    AND i.engine_mode IN ('demo', 'live_demo') "
        "    AND i.signal_id IS NOT NULL AND i.signal_id <> '' "
        "    AND i.context_id IS NOT NULL AND i.context_id <> '' "
        "    AND COALESCE(i.details->>'source', '') <> 'command' "
        "), scored AS ( "
        "  SELECT "
        "    l.strategy_name, "
        "    l.label_net_edge_bps, "
        "    (v.context_id IS NOT NULL) AS attribution_chain_ok "
        "  FROM labeled l "
        "  LEFT JOIN valid_contexts v ON v.context_id = l.context_id "
        ") "
        "SELECT strategy_name, "
        "       count(*) FILTER (WHERE label_net_edge_bps IS NOT NULL)::int AS total, "
        "       count(*) FILTER ( "
        "         WHERE label_net_edge_bps IS NOT NULL AND attribution_chain_ok "
        "       )::int AS chain_ok, "
        "       (count(*) FILTER ( "
        "          WHERE label_net_edge_bps IS NOT NULL AND attribution_chain_ok "
        "        ))::float "
        "         / nullif(count(*) FILTER (WHERE label_net_edge_bps IS NOT NULL), 0)::float AS ratio "
        "FROM scored "
        "GROUP BY strategy_name"
    )


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

    # Per-strategy 7d settled ratio. engine_mode filter MUST match IMPL-1 producer
    # `_compute_attribution_chain_ratio_by_strategy`
    # (program_code/ml_training/mlde_demo_applier.py:907-920) exactly:
    # ``engine_mode IN ('demo', 'live_demo')`` — the drift sentinel must
    # measure the SAME source the producer feeds the consumer (LG-5-IMPL-2
    # `GovernanceHub.review_live_candidate`). Denominator is settled post-fee
    # samples only; raw open/unfilled intents are low-sample, not attribution
    # chain failure. Including 'live' here would
    # diverge from the producer's input set and yield false alarms / false
    # reassurance vs the actual ratio R-meta sees.
    # Per-strategy 7d settled 比率；engine_mode filter 必對齊 IMPL-1 producer
    # `_compute_attribution_chain_ratio_by_strategy` 的 `IN ('demo','live_demo')`
    # —— sentinel 必須測 producer 餵給 consumer 的同一資料源。分母只計 settled
    # post-fee samples；未成交/未關閉 raw intent 是 low-sample，不是 chain failure。
    sql = _attribution_ratio_sql(ATTRIBUTION_DRIFT_WINDOW)
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

    # First-deploy / quiet-window grace: if EVERY LG-5 strategy has 0 settled
    # samples within 7d, no closed post-fee evidence exists yet — emit WARN
    # (not FAIL). Single low-sample strategies are WARN too; R-meta consumer
    # will defer them via defer_attribution_chain_low_sample.
    # 全 5 strategy 7d 內 0 settled sample → WARN（未部署 / 全靜默；FAIL 過嚴）。
    if all(totals[s] == 0 for s in LG5_STRATEGIES):
        return (
            "WARN",
            "[42b] no settled MLDE training rows for any LG-5 strategy in 7d — "
            "first-deploy or production silent; cannot evaluate attribution drift",
        )

    eligible = [s for s in LG5_STRATEGIES if totals[s] >= ATTRIBUTION_MIN_SETTLED_SAMPLES]
    low_samples = [s for s in LG5_STRATEGIES if totals[s] < ATTRIBUTION_MIN_SETTLED_SAMPLES]
    if not eligible:
        summary = _format_attribution_summary(ratios, totals)
        return (
            "WARN",
            "7d per-strategy settled attribution_chain_ok ratio: "
            f"{summary} — all strategies below settled sample floor "
            f"n<{ATTRIBUTION_MIN_SETTLED_SAMPLES}; "
            "sample-maturity watch only; R-meta will defer low-sample strategies",
        )

    # Determine worst eligible strategy (lowest ratio) for the verdict + msg.
    # 找樣本足夠的最差 strategy（最低 ratio）作為 verdict + msg。
    worst_strategy = min(eligible, key=lambda s: ratios[s])
    worst_ratio = ratios[worst_strategy]

    summary = _format_attribution_summary(ratios, totals)
    base = (
        f"7d per-strategy settled attribution_chain_ok ratio: {summary}; "
        f"worst={worst_strategy}@{worst_ratio:.3f}"
    )

    # Three-band verdict per RFC v2 §6 IMPL-3 line 451
    # (PASS/WARN/FAIL = 0.50/0.30/0.10) + §3 line 377 pipeline-alert escalation.
    # 三段判定（RFC v2 §6 IMPL-3 line 451）+ §3 line 377 pipeline-alert 升級。
    if worst_ratio >= ATTRIBUTION_RATIO_PASS_FLOOR:
        if low_samples:
            return (
                "WARN",
                base
                + " — eligible strategies pass R-meta floor; "
                + _format_low_sample_watch(totals, low_samples),
            )
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


# ---------------------------------------------------------------------------
# `[43]` label_backfill_freshness — LG5-W3-FUP-2 Fix 1 cron liveness sentinel
# (2026-05-02). Reads max(label_filled_at) to verify
# `helper_scripts/cron/edge_label_backfill_cron.sh` (every 30 min) is alive.
# `[43]` LG5-W3-FUP-2 Fix 1 cron 活性哨兵：讀 max(label_filled_at)，驗
# `edge_label_backfill_cron.sh`（30 分 cron）仍在跑。
# ---------------------------------------------------------------------------

# `[43]` freshness thresholds. PASS <2h matches the 30min cron cadence with
# a 4× headroom for backfill batch latency (5000 row × 2 engine_modes can
# legitimately take >1min). WARN <6h gives operator one cycle to react
# without paging; FAIL >=6h means cron has missed ≥11 ticks consecutively
# = clear silent death (or DB unreachable, in which case [43] FAILs anyway).
# `[43]` 新鮮度閾值。PASS <2h 對應 30min cron 4× headroom（5000 行 × 2
# engine_mode 偶可超過 1 分鐘）。WARN <6h 給 operator 一個窗口反應而不
# 立即 page；FAIL >=6h 代表 cron 已連續錯過 ≥11 tick = 確定 silent death。
LABEL_BACKFILL_PASS_MAX_SECONDS: int = 7200    # 2h
LABEL_BACKFILL_WARN_MAX_SECONDS: int = 21600   # 6h


def check_44_replay_manifest_key_presence(cur) -> tuple[str, str]:
    """[44] replay_manifest_key_presence — REF-20 Sprint 1 Track B PA push back #3.

    [44] replay_manifest_key_presence — REF-20 Sprint 1 Track B PA push back #3。

    Verifies that every ``replay.run_state`` row with ``status='running'``
    has a sibling ``key.hex`` file present at ``<output_path>/key.hex``.

    為什麼存在 / Why this exists:
        REF-20 Sprint 1 Track B (this commit) closes the E3-P0-1 fail-open
        vulnerability: the Rust ``replay_runner`` binary previously returned
        ``Ok(manifest)`` with stderr-only warning when sibling ``key.hex``
        was absent — Track B switches that to hard error. After deployment,
        any replay subprocess running without a sibling ``key.hex`` will
        fail-closed at startup. PA push back #3 surfaces the operator
        runbook contract: until V042 SQL-backed key archive lands (Wave 6+),
        operator MUST place a ``key.hex`` next to every signed manifest;
        this healthcheck monitors the contract continuously without driving
        engine to FAIL (V042 land before is a known transitional state).

        Sprint 1 Track B（本 commit）封閉 E3-P0-1 fail-open 漏洞：Rust
        ``replay_runner`` 以前在 sibling ``key.hex`` 缺時 ``Ok(manifest)``
        + stderr warning；Track B 改為 hard error。Track B 部署後沒 key.hex
        的 replay subprocess 啟動即 fail-closed。PA push back #3 surface
        運維契約 — V042 SQL-backed key archive（Wave 6+）落地前 operator
        必在每個 signed manifest 旁放 ``key.hex``；本 healthcheck 連續監測
        該契約但不會 FAIL（V042 前的過渡期 known issue）。

    Verdict bands / 結果分級:
        * V045 missing or no running rows → PASS (vacuous true).
        * All running rows have sibling key.hex → PASS.
        * 1+ running rows missing key.hex → WARN (transitional gate; Track B
          deployment will cause subprocess fail-closed at next start, but
          existing running runs may pre-date the change). Operator action:
          place key.hex next to manifest, OR cancel the run, OR wait for
          V042 SQL-backed archive (Wave 6+).
        * V045 query exception (non-existence) → FAIL (signal V045 not yet
          land or DB drift).

    Pre-conditions (fail-closed):
        * ``replay.run_state`` exists (V045 deployed) — else PASS-skip with
          NOTE (V045 unreserved for some Sprint 1 deploys; not FAIL because
          downstream is gated on V045 itself).

    缺失條件處理：
        * V045 表不存在 → PASS-skip + 標明（避免 Sprint 1 部署順序差錯時
          被本 check 誤導為 FAIL）。
        * V045 表存在但無 running row → PASS（vacuously true）。
        * 1+ running row 缺 sibling key.hex → WARN（過渡 gate；Track B
          部署後新啟動 subprocess 即 fail-closed，舊已 running 的可能
          pre-date Track B）。
        * V045 query 例外 → FAIL（DB drift 訊號）。

    Returns:
        ``(status, msg)`` tuple. msg lists running run count + missing key
        count + first missing run_id for operator triage; FAIL adds explicit
        suggested operator action.
    """
    # Defensive rollback before each query (mirrors [42] / [43] pattern).
    # 每次 query 前保險 rollback（鏡 [42] / [43]）。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — defensive, rollback failure ≠ fatal
        pass

    # Existence pre-check — V045 may not be deployed yet in some Sprint 1
    # rollout orderings; treat as PASS-skip rather than FAIL so this check
    # does not block other governance signals.
    # V045 存在性檢查 — 某些 Sprint 1 部署順序下 V045 尚未 land；
    # 視為 PASS-skip 而非 FAIL，避免阻塞其他治理信號。
    try:
        cur.execute(
            "SELECT to_regclass('replay.run_state') IS NOT NULL"
        )
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[44] replay.run_state existence check failed: {exc}")
    if not exists_row or not exists_row[0]:
        return (
            "PASS",
            "[44] replay.run_state missing — V045 not applied "
            "(SKIP; upgrade to FAIL after Wave 6 V042 lands)",
        )

    # Query running rows + their output_path. status='running' is the
    # narrowest filter that catches active subprocess; status='starting' may
    # not yet have spawned the subprocess (so key.hex check is premature).
    # 查 running row 與其 output_path。status='running' 是最窄的 filter
    # 抓主動的 subprocess；status='starting' 還沒 spawn，key.hex check 過早。
    sql = (
        "SELECT run_id::text, output_path "
        "FROM replay.run_state "
        "WHERE status = 'running' AND output_path IS NOT NULL"
    )
    try:
        cur.execute(sql)
        rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[44] running row query failed: {exc}")

    total_running = len(rows)
    if total_running == 0:
        return ("PASS", "[44] no running replay subprocesses (vacuously true)")

    # Filesystem walk — for each running run check sibling key.hex presence.
    # Filesystem 步入 — 對每個 running run 檢查 sibling key.hex 是否存在。
    #
    # Why we use stdlib path-only ops (no os.access mode bits): we only need
    # presence, not readability — Track B Rust binary will handle perms /
    # invalid hex / wrong length itself at startup. False-negative on
    # presence check (e.g. NFS staleness) is acceptable WARN, not FAIL.
    #
    # 為什麼純 path 操作不檢查 readable / exec：本 healthcheck 只關心
    # presence，不關心可讀性 / 內容；NFS stale entry 偶發誤判 = 可接受 WARN。
    import os
    from pathlib import Path

    missing: list[tuple[str, str]] = []  # (run_id, expected_key_path)
    for run_id, output_path in rows:
        if not output_path:
            continue
        # Sibling key.hex layout: <output_path>/key.hex (V045 output_path is
        # the directory PA Track A `_write_manifest_fixture(...)` writes
        # manifest.json + key.hex into).
        # Sibling key.hex layout：<output_path>/key.hex（V045 output_path
        # 是 Track A `_write_manifest_fixture(...)` 寫 manifest.json +
        # key.hex 的目錄）。
        try:
            key_path = Path(output_path) / "key.hex"
            if not key_path.is_file():
                missing.append((run_id, str(key_path)))
        except (OSError, ValueError) as exc:
            # Path ops should not normally raise; defensively classify as
            # missing so operator sees the run_id.
            # Path ops 平時不會例外；防禦性歸為 missing 以便 operator 看到。
            missing.append((run_id, f"<{output_path} (path err: {exc})>"))

    if not missing:
        return (
            "PASS",
            f"[44] {total_running} running replay run(s) all have sibling key.hex",
        )

    # WARN — Track B deployed will fail-close new starts, but in-flight runs
    # without key.hex still need operator attention (V042 archive lands in
    # Wave 6+; until then sibling key.hex is the production contract).
    # WARN — Track B 部署後新啟動會 fail-closed，但 in-flight 無 key.hex
    # 的 run 仍需 operator 注意（V042 archive 於 Wave 6+ 落地；之前 sibling
    # key.hex 是 production 契約）。
    first_run_id, first_path = missing[0]
    return (
        "WARN",
        f"[44] {len(missing)}/{total_running} running replay run(s) missing "
        f"sibling key.hex; first={first_run_id} expected={first_path}; "
        "operator action: place key.hex next to manifest OR cancel run; "
        "tracker REF-20 Track B PA push back #3 / V042 Wave 6+ supersedes",
    )


def check_43_label_backfill_freshness(cur) -> tuple[str, str]:
    """[43] label_backfill_freshness — LG5-W3-FUP-2 Fix 1 cron liveness.

    Verifies that ``edge_label_backfill_cron.sh`` (suggested cron
    ``*/30 * * * *``, runs ``program_code/ml_training/edge_label_backfill.py``
    against demo + live_demo) is actually alive by reading
    ``max(label_filled_at)`` from ``learning.decision_features`` for the
    same engine_modes the cron writes (``demo`` + ``live_demo``).

    [43] label_backfill_freshness — LG5-W3-FUP-2 Fix 1 cron 活性檢查。
    驗證 ``edge_label_backfill_cron.sh``（建議 cron ``*/30 * * * *``，
    跑 ``edge_label_backfill.py`` 對 demo + live_demo）仍在活著 ——
    讀 ``learning.decision_features`` 的 ``max(label_filled_at)``，
    engine_mode IN (``demo``, ``live_demo``)（與 cron 寫入面對齊）。

    Verdict bands / 結果分級:
        * age < 2h → PASS（cron 正常 30min 節奏 + 4× headroom）
        * age < 6h → WARN（cron 漏 1-11 tick，operator 一窗反應期）
        * age >= 6h or no rows → FAIL（cron silent death，
          [42b] attribution_chain_ok 24h 內會跌回 R-meta floor 以下）

    Why this exists / 為何存在:
        MIT FUP-2 diagnosis (2026-05-02) traced [42b] FAIL ←
        attribution_chain_ok=false 86%+ ← edge_label_backfill.py 純
        on-demand 無 cron。Fix 1 加 cron wrapper + 本 healthcheck 互鎖；
        缺本 healthcheck，cron 死亡 24h 後才會經由 [42b] 二階反應 ——
        本 check 提供 30min-resolution 直接訊號。

    Pre-conditions (fail-closed):
        * ``learning.decision_features`` exists (V017 deployed) — else FAIL.

    Returns:
        ``(status, msg)`` tuple. msg includes age in hours + latest
        label_filled_at for operator triage; FAIL adds explicit "cron
        likely not running" + suggested action.
    """
    # Defensive rollback before each query (mirrors [42] / [42b] pattern).
    # 每次 query 前保險 rollback（鏡 [42] / [42b]）。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — defensive, rollback failure ≠ fatal
        pass

    # Existence pre-check — V017 hypertable required.
    # 表存在檢查 — V017 hypertable 必須存在。
    try:
        cur.execute(
            "SELECT to_regclass('learning.decision_features') IS NOT NULL"
        )
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[43] table existence check failed: {exc}")
    if not exists_row or not exists_row[0]:
        return (
            "FAIL",
            "[43] learning.decision_features missing — V017 not applied",
        )

    # Read max(label_filled_at) for the engine_modes the cron writes.
    # We compute age in seconds inside Postgres via EXTRACT(EPOCH FROM ...)
    # so the verdict is independent of Python clock vs DB clock skew (any
    # skew lives entirely on the DB side, which is also where label_filled_at
    # was stamped — symmetric).
    # 讀 cron 寫入面 engine_mode 的 max(label_filled_at)；age 在 Postgres 內
    # 算（EXTRACT(EPOCH FROM now() - max_ts)）避免 Python/DB 時鐘 skew。
    sql = (
        "SELECT max(label_filled_at) AS latest_fill, "
        "       extract(epoch from (now() - max(label_filled_at)))::float "
        "         AS age_seconds "
        "FROM learning.decision_features "
        "WHERE engine_mode IN ('demo', 'live_demo')"
    )
    try:
        cur.execute(sql)
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[43] max(label_filled_at) query failed: {exc}")

    if row is None or row[0] is None or row[1] is None:
        return (
            "FAIL",
            "[43] no decision_features rows with label_filled_at for "
            "(demo, live_demo) — backfill never ran or table empty",
        )

    latest_fill = row[0]
    age_seconds = float(row[1])
    age_hours = age_seconds / 3600.0

    base = (
        f"latest fill={latest_fill.isoformat()} "
        f"age={age_hours:.2f}h ({age_seconds:.0f}s)"
    )

    if age_seconds < LABEL_BACKFILL_PASS_MAX_SECONDS:
        return ("PASS", base + " — edge_label_backfill_cron alive (within 2h)")
    if age_seconds < LABEL_BACKFILL_WARN_MAX_SECONDS:
        return (
            "WARN",
            base
            + " — last fill 2-6h ago; cron may have skipped 1-11 ticks",
        )
    return (
        "FAIL",
        base
        + " — last fill ≥6h ago, cron likely not running; "
        "verify `crontab -l | grep edge_label_backfill_cron` and rerun manually "
        "via `bash helper_scripts/cron/edge_label_backfill_cron.sh`",
    )


# ---------------------------------------------------------------------------
# `[42c]` live_candidate_attribution_drift_3d — LG5-W3-FUP-2 Fix 2 (2026-05-02)
# gate-aligned mirror of `[42b]` per RFC §5 Plan B.
# `[42c]` LG5-W3-FUP-2 Fix 2（2026-05-02）— `[42b]` 的 R-meta gate 對齊
# 鏡像（RFC §5 方案 B）。
# ---------------------------------------------------------------------------


def check_42c_live_candidate_attribution_drift_3d(cur) -> tuple[str, str]:
    """[42c] per-strategy 3d rolling attribution_chain_ok ratio drift —
    R-meta gate aligned mirror of `[42b]` (LG5-W3-FUP-2 Fix 2 RFC §5 Plan B).

    [42c] 5 個 LG-5 strategy 的 3d 滾動 attribution_chain_ok ratio 漂移
    偵測 —— `[42b]` 的 R-meta gate 對齊鏡像（LG5-W3-FUP-2 Fix 2 RFC §5
    方案 B）。

    Identical to `check_42b_live_candidate_attribution_drift` in every
    respect (SQL shape, engine_mode filter, strategy keyset, 0.50/0.30/0.10
    band thresholds, missing-strategy fail-soft, first-deploy grace, V031
    fail-closed) except the time window: `interval '3 days'` instead of
    `interval '7 days'`. This aligns with the producer
    `mlde_demo_applier._compute_attribution_chain_ratio_by_strategy`
    R-meta window (`_R_META_WINDOW_DAYS = 3`) shipped by Fix 2 IMPL-1.

    與 `check_42b_live_candidate_attribution_drift` 在所有方面完全一致
    （SQL 結構 / engine_mode filter / strategy keyset / 0.50/0.30/0.10
    閾值 / missing-strategy fail-soft / first-deploy grace / V031
    fail-closed），唯一差別 = 時間窗口從 7d → 3d，對齊 producer
    `_R_META_WINDOW_DAYS = 3` (Fix 2 IMPL-1)。

    Verdict bands (identical to `[42b]` per RFC v2 §6 IMPL-3 line 451):
        * all 5 strategies ≥ 0.50 → PASS
        * worst in [0.30, 0.50) → WARN（R-meta gate defer expected）
        * worst in [0.10, 0.30) → FAIL standard band
        * worst < 0.10 → FAIL pipeline-alert (RFC §4 lease_revoke_trigger)

    Operator interpretation matrix (`[42b]` 7d × `[42c]` 3d):
        * `[42b]` PASS + `[42c]` PASS → R-meta gate healthy long-term
          and current — promote freely
        * `[42b]` PASS + `[42c]` WARN → 4/24-28 attribution bug 殘留
          淡出中；R-meta gate 對 worst strategy 會 defer，但 7d 視角
          仍正常 — working as intended, monitor only
        * `[42b]` FAIL + `[42c]` PASS → bug 已修，7d 視角會自然轉好；
          R-meta gate 已可放行 — wait for `[42b]` to converge
        * `[42b]` FAIL + `[42c]` FAIL → 真實 production drift；
          investigate producer side (MIT-S2-1 attribution_chain_ok writer)
          + check label backfill cron `[43]`

    Operator 對照矩陣（`[42b]` 7d × `[42c]` 3d）：
        * 雙 PASS → R-meta gate 長期 + 當下都健康，可放心 promote
        * 7d PASS + 3d WARN → 4/24-28 attribution bug 殘留淡出中；
          R-meta gate 對 worst strategy 會 defer 但 7d 視角仍正常 —
          working as intended，僅需 monitor
        * 7d FAIL + 3d PASS → bug 已修，7d 視角會自然轉好；
          R-meta gate 已可放行 — 等 `[42b]` 收斂即可
        * 雙 FAIL → 真實 production drift；查 producer
          (MIT-S2-1 attribution_chain_ok writer) + label backfill cron `[43]`

    RFC traceability:
        * LG5-W3-FUP-2 Fix 2 RFC §5 Plan B (line 234-263) — dual-window design
        * Producer pairing: `mlde_demo_applier._R_META_WINDOW_DAYS = 3`
          (Fix 2 IMPL-1)
        * `[42b]` long-window observability sentinel preserved unchanged

    Returns:
        ``(status, msg)`` tuple. msg includes worst strategy + its 3d ratio
        + per-strategy 3d summary so operator can read the exact ratio
        R-meta gate sees right now.
    """
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001
        pass

    # V031 hypertable existence — required for this check (same as [42b]).
    # V031 表不存在直接 FAIL（鏡 [42b]）。
    try:
        cur.execute(
            "SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL"
        )
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[42c] view existence check failed: {exc}")
    if not exists_row or not exists_row[0]:
        return (
            "FAIL",
            "[42c] learning.mlde_edge_training_rows missing — V031 not applied",
        )

    # Per-strategy 3d settled ratio. SQL shape identical to [42b] except window:
    # `ATTRIBUTION_DRIFT_WINDOW_3D = "interval '3 days'"` instead of 7d.
    # engine_mode filter MUST match IMPL-1 producer
    # `_compute_attribution_chain_ratio_by_strategy` (post-Fix 2:
    # `IN ('demo', 'live_demo')` + `_R_META_WINDOW_DAYS = 3`) so this
    # sentinel reads the SAME data the R-meta gate consumer reads. Denominator
    # is settled post-fee samples only; raw open/unfilled intents are low-sample.
    # Per-strategy 3d settled 比率；SQL 結構與 [42b] 一致，唯獨 window 改 3d
    # (`ATTRIBUTION_DRIFT_WINDOW_3D`)。engine_mode filter 對齊 Fix 2 後的
    # producer (`IN ('demo','live_demo')` + `_R_META_WINDOW_DAYS = 3`)。
    # 分母只計 settled post-fee samples；未成交/未關閉 raw intent 是 low-sample。
    sql = _attribution_ratio_sql(ATTRIBUTION_DRIFT_WINDOW_3D)
    try:
        cur.execute(sql)
        rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[42c] attribution-ratio query failed: {exc}")

    # Build per-strategy ratio dict; missing → 0.0 (forces alarm).
    # Mirrors [42b] logic block byte-for-byte structure except window source.
    # 建 per-strategy ratio dict；missing → 0.0（強制告警）。
    # 與 [42b] 邏輯結構完全一致，僅 window 源不同。
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

    for s in LG5_STRATEGIES:
        if s not in ratios:
            ratios[s] = 0.0
            totals[s] = 0

    # First-deploy / quiet-window grace: all 5 strategies 0 settled samples
    # in 3d → WARN. 3d window is intentionally more sensitive to low sample.
    # 全 5 strategy 3d 內 0 settled sample → WARN（首部署 / 全靜默；FAIL 過嚴）。
    if all(totals[s] == 0 for s in LG5_STRATEGIES):
        return (
            "WARN",
            "[42c] no settled MLDE training rows for any LG-5 strategy in 3d — "
            "first-deploy or production silent; cannot evaluate R-meta drift",
        )

    eligible = [s for s in LG5_STRATEGIES if totals[s] >= ATTRIBUTION_MIN_SETTLED_SAMPLES]
    low_samples = [s for s in LG5_STRATEGIES if totals[s] < ATTRIBUTION_MIN_SETTLED_SAMPLES]
    if not eligible:
        summary = _format_attribution_summary(ratios, totals)
        return (
            "WARN",
            "3d per-strategy settled attribution_chain_ok ratio "
            f"(R-meta gate aligned): {summary} — all strategies below settled sample floor "
            f"n<{ATTRIBUTION_MIN_SETTLED_SAMPLES}; "
            "sample-maturity watch only; R-meta will defer low-sample strategies",
        )

    # Determine worst eligible strategy (lowest ratio) for the verdict + msg.
    # 找樣本足夠的最差 strategy（最低 ratio）作為 verdict + msg。
    worst_strategy = min(eligible, key=lambda s: ratios[s])
    worst_ratio = ratios[worst_strategy]

    summary = _format_attribution_summary(ratios, totals)
    base = (
        f"3d per-strategy settled attribution_chain_ok ratio "
        f"(R-meta gate aligned): {summary}; "
        f"worst={worst_strategy}@{worst_ratio:.3f}"
    )

    # Three-band verdict per RFC v2 §6 IMPL-3 line 451 + §3 line 377
    # pipeline-alert escalation. Threshold constants reused from [42b]
    # (ATTRIBUTION_RATIO_PASS_FLOOR / WARN_FLOOR / FAIL_FLOOR) per RFC §5
    # Plan B "identical thresholds, only window differs" wording.
    # 三段判定（RFC v2 §6 IMPL-3 line 451）+ §3 line 377 pipeline-alert 升級。
    # 閾值常數複用 [42b]（RFC §5 方案 B「同閾值、僅 window 異」）。
    if worst_ratio >= ATTRIBUTION_RATIO_PASS_FLOOR:
        if low_samples:
            return (
                "WARN",
                base
                + " — eligible strategies pass R-meta floor; "
                + _format_low_sample_watch(totals, low_samples),
            )
        return (
            "PASS",
            base + " — all strategies ≥ 0.50 R-meta floor (3d window)",
        )
    if worst_ratio >= ATTRIBUTION_RATIO_WARN_FLOOR:
        return (
            "WARN",
            base
            + f" — {worst_strategy} below R-meta 0.50 floor (3d window); "
            "review_live_candidate will defer for this strategy "
            "(check [42b] 7d ratio for long-window context)",
        )
    if worst_ratio >= ATTRIBUTION_RATIO_FAIL_FLOOR:
        return (
            "FAIL",
            base
            + f" — {worst_strategy} below 0.30 standard FAIL floor (3d window); "
            "attribution chain systemically degraded in current 3d slice — "
            "investigate producer (MIT-S2-1 attribution_chain_ok writer) + "
            "check [43] label_backfill_freshness",
        )
    return (
        "FAIL",
        base
        + f" — {worst_strategy} below 0.10 pipeline-alert floor (3d window) "
        "(RFC v2 §4 lease_revoke_trigger fires; "
        "GovernanceHub must auto-revoke active leases)",
    )


# ---------------------------------------------------------------------------
# `[64]` unblock_candidates_drift — W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1
# (Sprint N+1 2026-05-10). 對應 spec §6.2 4 項：
#   1. Stale candidate（outcome=NULL AND candidate_at_ms < now-14d）→ WARN
#   2. Yo-yo detection（同 cell 30d 內 unfrozen + re_frozen ≥1 cycle 後仍出現
#      新 candidate）→ FAIL
#   3. Sign-off completeness（outcome='unfrozen' row 必有 pa_report_path +
#      qc_report_path + commit_sha non-NULL）→ FAIL（V090 PG CHECK 已強制；
#      此 healthcheck 是 sentinel of sentinel，偵測 constraint 被 disable）
#   4. Audit consistency（unfrozen cell 在 freeze.json unfrozen_cells_history
#      對應 entry）→ WARN（json 同步缺）
# 對應 V090: governance.unblock_candidates （schema land 2026-05-10）
# 對應 writer: helper_scripts/db/audit/blocked_symbols_30d_unblock_check.py
# ---------------------------------------------------------------------------

# spec §6.2 第 1 項閾值：candidate 14d 無 sign-off → WARN
UNBLOCK_STALE_CANDIDATE_DAYS: int = 14

# spec §5.3 yo-yo detection window
UNBLOCK_YOYO_WINDOW_DAYS: int = 30


def check_64_unblock_candidates_drift(cur) -> tuple[str, str]:
    """[64] unblock_candidates_drift — 動態解封 candidate 治理 4 項漂移哨兵。

    spec § 6.2 4 sub-check（per docs/execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md）：

      1. **Stale candidate**：`outcome=NULL` AND `candidate_at_ms < now - 14d`
         → WARN（candidate 14d 無 sign-off → operator inattention signal）。
      2. **Yo-yo detection**：同 cell 30d 內 unfrozen + re_frozen ≥1 cycle 後
         next 30d 仍出現新 candidate → FAIL（spec §5.3 selection-bias 防護）。
      3. **Sign-off completeness**：`outcome='unfrozen'` row 必有
         `pa_report_path` + `qc_report_path` + `commit_sha` non-NULL → FAIL。
         注意：V090 unfrozen_completeness_chk PG CHECK 已強制，理論上 INSERT/
         UPDATE 期 PG 直接 reject；本 healthcheck 是「constraint 還活著」的
         sentinel of sentinel — 防 partial-rollout drift（V090 sequence
         schema被 disable / DROP）。
      4. **Audit consistency**：`unfrozen` cell 在
         `docs/governance_dev/strategy_blocked_symbols_freeze.json` 對應的
         `unfrozen_cells_history` 應有 entry（writer 寫 json）→ 不對應 = WARN。
         json 為 source-of-truth governance state；同步缺即 audit chain 斷裂。

    Verdict bands / 結果分級：
        - 4 sub-check 全 PASS → PASS
        - 4 sub-check 全 PASS but stale 數 > 0 → WARN（spec §6.2 #1）
        - 4 sub-check 有 #2 or #3 trip → FAIL（不可恢復契約 break）
        - V090 表不存在 → PASS-skip（spec §6.2：「V090 absent 不阻塞，pre-deploy
          狀態」）

    Pre-conditions (fail-closed):
        - governance.unblock_candidates 表存在（V090 已 land）— 否則 PASS-skip。

    Returns:
        ``(status, msg)`` tuple. msg 列出 4 sub-check 結果概要。
    """
    # Defensive rollback before each query (mirrors `[42]` / `[42b]` pattern).
    # 每次 query 前保險 rollback（鏡 [42] / [42b]）。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — defensive, rollback failure ≠ fatal
        pass

    # Existence pre-check — V090 may not be deployed yet in some Sprint N+1
    # rollout orderings; treat as PASS-skip rather than FAIL so this check
    # does not block other governance signals.
    # V090 存在性檢查 — 某些 Sprint N+1 部署順序下 V090 尚未 land；
    # 視為 PASS-skip 而非 FAIL，避免阻塞其他治理信號。
    try:
        cur.execute(
            "SELECT to_regclass('governance.unblock_candidates') IS NOT NULL"
        )
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[64] V090 table existence check failed: {exc}")
    if not exists_row or not exists_row[0]:
        return (
            "PASS",
            "[64] governance.unblock_candidates missing — V090 not applied "
            "(SKIP; expected during Sprint N+1 rollout window)",
        )

    # ────────────────────────────────────────────────────────────────────
    # Sub-check 1: Stale candidate（outcome=NULL AND age > 14d）
    # ────────────────────────────────────────────────────────────────────
    sql_stale = (
        "SELECT count(*)::int AS stale_count "
        "FROM governance.unblock_candidates "
        "WHERE outcome IS NULL "
        f"  AND candidate_at_ms < (extract(epoch from now()) * 1000)::bigint "
        f"          - ({UNBLOCK_STALE_CANDIDATE_DAYS}::bigint * 86400000)"
    )
    try:
        cur.execute(sql_stale)
        row = cur.fetchone()
        stale_count = int(row[0] or 0) if row else 0
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[64] sub-check 1 stale-candidate query failed: {exc}")

    # ────────────────────────────────────────────────────────────────────
    # Sub-check 2: Yo-yo detection
    # 同 cell 在 30d 內既有 unfrozen 又有 re_frozen 後 next 30d 仍出現新 candidate
    # ────────────────────────────────────────────────────────────────────
    sql_yoyo = (
        "WITH yoyo_cells AS ("
        "  SELECT cell_strategy, cell_symbol "
        "  FROM governance.unblock_candidates "
        f"  WHERE candidate_at_ms > (extract(epoch from now()) * 1000)::bigint "
        f"          - ({UNBLOCK_YOYO_WINDOW_DAYS}::bigint * 86400000) "
        "    AND outcome IN ('unfrozen', 're_frozen') "
        "  GROUP BY cell_strategy, cell_symbol "
        "  HAVING count(DISTINCT outcome) >= 2"
        ") "
        "SELECT count(*)::int AS yoyo_count "
        "FROM governance.unblock_candidates u "
        "JOIN yoyo_cells y "
        "  ON u.cell_strategy = y.cell_strategy "
        " AND u.cell_symbol   = y.cell_symbol "
        f"WHERE u.candidate_at_ms > (extract(epoch from now()) * 1000)::bigint "
        f"          - ({UNBLOCK_YOYO_WINDOW_DAYS}::bigint * 86400000) "
        "  AND u.outcome IS NULL"
    )
    try:
        cur.execute(sql_yoyo)
        row = cur.fetchone()
        yoyo_count = int(row[0] or 0) if row else 0
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[64] sub-check 2 yo-yo query failed: {exc}")

    # ────────────────────────────────────────────────────────────────────
    # Sub-check 3: Sign-off completeness（V090 PG CHECK sentinel of sentinel）
    # ────────────────────────────────────────────────────────────────────
    sql_signoff = (
        "SELECT count(*)::int AS incomplete_signoff_count "
        "FROM governance.unblock_candidates "
        "WHERE outcome = 'unfrozen' "
        "  AND (pa_report_path IS NULL "
        "       OR qc_report_path IS NULL "
        "       OR commit_sha IS NULL "
        "       OR unfrozen_at_ms IS NULL)"
    )
    try:
        cur.execute(sql_signoff)
        row = cur.fetchone()
        incomplete_signoff_count = int(row[0] or 0) if row else 0
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[64] sub-check 3 sign-off query failed: {exc}")

    # ────────────────────────────────────────────────────────────────────
    # Sub-check 4: Audit consistency（unfrozen rows 對應 freeze.json
    # unfrozen_cells_history entry 是否存在）
    # 注意：純 PG SELECT 無法驗 freeze.json；此 sub-check 在 healthcheck
    # 內以「unfrozen rows count」作 surrogate signal — operator 看到 unfrozen
    # rows 後手動驗 freeze.json 同步狀態（符合 spec §6.2 #4 「json 同步缺」
    # WARN 語意）。完整 cross-check 留 force_eval API + GUI 配合執行。
    # ────────────────────────────────────────────────────────────────────
    sql_unfrozen = (
        "SELECT count(*)::int AS unfrozen_count "
        "FROM governance.unblock_candidates "
        "WHERE outcome = 'unfrozen'"
    )
    try:
        cur.execute(sql_unfrozen)
        row = cur.fetchone()
        unfrozen_count = int(row[0] or 0) if row else 0
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[64] sub-check 4 unfrozen-count query failed: {exc}")

    base = (
        f"stale_n={stale_count}, yoyo_n={yoyo_count}, "
        f"incomplete_signoff_n={incomplete_signoff_count}, "
        f"unfrozen_n={unfrozen_count}"
    )

    # ────────────────────────────────────────────────────────────────────
    # Verdict logic
    # ────────────────────────────────────────────────────────────────────
    # FAIL 優先：sub-check 2 yo-yo or sub-check 3 sign-off completeness
    if yoyo_count > 0:
        return (
            "FAIL",
            base
            + f" — yo-yo detection: {yoyo_count} candidate row(s) on cell(s) "
            f"with prior unfrozen+re_frozen cycle within {UNBLOCK_YOYO_WINDOW_DAYS}d "
            "(spec §5.3 selection-bias 防護觸發；force_eval 應拒未來相同 cell 評估)",
        )
    if incomplete_signoff_count > 0:
        return (
            "FAIL",
            base
            + f" — sign-off completeness violation: {incomplete_signoff_count} "
            "row(s) outcome='unfrozen' missing pa_report_path / qc_report_path / "
            "commit_sha / unfrozen_at_ms (V090 unfrozen_completeness_chk should "
            "have blocked; investigate constraint disable / partial rollout)",
        )

    # WARN：stale candidate（運維未及時 sign-off 信號）
    if stale_count > 0:
        return (
            "WARN",
            base
            + f" — {stale_count} candidate row(s) age > {UNBLOCK_STALE_CANDIDATE_DAYS}d "
            "with no sign-off (operator inattention signal; review pending "
            "PA + QC review in docs/CCAgentWorkSpace/{PA,QC}/workspace/reports/)",
        )

    # 全綠 PASS（含 unfrozen_count > 0 但無 sign-off violation 的健康狀態）
    return (
        "PASS",
        base
        + " — no stale candidate / no yo-yo / no sign-off violation "
        "(spec §6.2 4 sub-check all green)",
    )
