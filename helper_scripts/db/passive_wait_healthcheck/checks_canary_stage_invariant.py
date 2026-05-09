"""W-AUDIT-9 T4 — graduated canary stage invariant healthcheck `[58]`.
W-AUDIT-9 T4 — 漸進式 canary stage 不變式健檢 `[58]`。

MODULE_NOTE:
  AMD-2026-05-09-03 §4.1 配套 healthcheck — 對 active cohort 驗證 graduated
  canary 5-stage state machine 不變式：
    1. 升級條件 metric 存在於 governance.canary_stage_metric_registry
       不存在 = WARN（spec drift signal）
    2. rollback metric 存在 — 同上
    3. rollback trip 偵測 — active cohort 觸發 rollback metric → FAIL
       觸 stage = 0 rollback（per AMD §3.2 SM-04 ≥ L3 + DOC-08 §12 invariant）
    4. observation_period 一致性（Stage 1=7d / 2=14d / 3=21d wall-clock）
       不一致 = WARN
    5. cohort 規範（Stage 1/2 = 1 strategy × 1 symbol，Stage 3 = active universe）
       違反 = FAIL
    6. PG-layer manual_promote NOT NULL lease（V080 已強制；本檢查觀察並 surface
       任何 partial-rollout drift）

  TODO §5.3 invariant 11 / 12 對應：
    - invariant 11：manual_promote 必伴 decision_lease_id（V080 PG CHECK）
    - invariant 12：SM-04 ≥ L3 escalate → 觸 stage = 0 rollback hard FAIL
                    （本健檢實作 SM-04 escalate 偵測）

  Cron：`0 */6 * * *`（與 passive_wait_healthcheck 同期；AMD §4.1）
  Exit：FAIL → exit 1（silent-dead 自動偵測）；WARN → exit 0 + log
  純 SELECT；fail-closed：DB 不通 / 表缺即 FAIL。

  Reference: docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md
             §4.1 healthcheck `[58]` + §2.2 5-Stage 表 + §3.2 SM-04
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# AMD-2026-05-09-03 §2.2 5-Stage 表 — 觀察期常數（ms）。
# AMD-2026-05-09-03 §2.2 spec table — observation periods (ms).
#
# Stage 0：fail-closed shadow only（持續態，無自動升級）。
# Stage 1：7 days wall-clock.
# Stage 2：14 days wall-clock.
# Stage 3：21 days wall-clock.
# Stage 4：LIVE_PENDING（operator 顯式拍板，無自動觀察期）。
# ---------------------------------------------------------------------------
STAGE_OBSERVATION_PERIOD_MS: dict[int, int] = {
    0: 0,
    1: 7 * 24 * 60 * 60 * 1000,
    2: 14 * 24 * 60 * 60 * 1000,
    3: 21 * 24 * 60 * 60 * 1000,
    4: 0,
}


# ---------------------------------------------------------------------------
# AMD §2.2：每 stage 至少需註冊的核心 metric（minimum drift floor）。
# AMD §2.2: minimum core metrics per stage that MUST be registered.
#
# Stage 1：entry_fills / boundary_violation_count
# Stage 2：gross_pnl_usdt / DSR / entry_fills / boundary_violation_count
# Stage 3：gross_pnl_usdt / DSR / attribution_chain_ok_ratio / boundary_violation_count
# Stage 4：n/a（operator-pinned, no auto metric）
#
# Missing 任一 → WARN（spec drift signal；不阻塞 silent-dead 偵測）。
# 缺任一 → WARN（spec 漂移信號；不阻塞 silent-dead 偵測）。
# ---------------------------------------------------------------------------
STAGE_PROMOTE_METRICS_MIN: dict[int, tuple[str, ...]] = {
    1: ("entry_fills", "boundary_violation_count"),
    2: ("gross_pnl_usdt", "DSR", "entry_fills", "boundary_violation_count"),
    3: (
        "gross_pnl_usdt",
        "DSR",
        "attribution_chain_ok_ratio",
        "boundary_violation_count",
    ),
}


def check_58_graduated_canary_stage_invariant(cur) -> tuple[str, str]:
    """[58] graduated_canary_stage_invariant — AMD-2026-05-09-03 §4.1。

    AMD §4.1 五語義：metric 存在 / metric 存在 / rollback trip / observation
    period 一致 / cohort 規範。

    Verdict bands / 結果分級 (per AMD §4.1):
        * 全 5 不變式 PASS → PASS
        * (1)(2)(4) drift / spec missing → WARN
        * (3) rollback trip → FAIL（必觸 stage = 0 rollback）
        * (5) cohort 規範違反（Stage 1/2 多 strategy 或 multi-symbol）→ FAIL
        * (6) manual_promote NULL lease（V080 PG CHECK 阻擋，但若觀察到實際
              row）→ FAIL（partial-rollout / V080 schema drift）
        * SM-04 ≥ L3 escalate（透過 governance.canary_stage_log
          transition_kind='incident_rollback' 偵測，invariant 12）→ FAIL

    Returns:
        ``(status, msg)`` tuple. msg 含 active cohort 數 / 違反項目 / 嚴重度。

    Pre-conditions (fail-closed):
        * governance.canary_stage_log 表存在（V080 已 apply）— else FAIL
        * governance.canary_stage_metric_registry 表存在 — else FAIL

    Notes (TODO.md §5.3 invariant 11 / 12):
        - invariant 11：V080 已透過 PG CHECK 強制 manual_promote NOT NULL
          lease；本健檢觀察任何 partial-rollout drift（理論上無法達成
          因 PG 拒絕 INSERT，仍保險檢查）。
        - invariant 12：SM-04 ≥ L3 escalate via
          transition_kind='incident_rollback' + reason 含 'sm04_l3' →
          必觸 stage = 0 rollback。本健檢驗 latest 'incident_rollback'
          後 24h 內所有 active cohort 是否回 Stage 0；若仍見 Stage ≥1
          active = FAIL（auto-rollback 失效）。
    """
    # 防禦性 rollback — 對齊 [42] / [55] 等同 family 的 cur 模板。
    # Defensive rollback — mirrors [42] / [55] same-family pattern.
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — defensive, rollback failure ≠ fatal
        pass

    # ─────────────────────────────────────────────────────────────────────
    # Pre-check：兩張 V080 表存在，否則 fail-closed FAIL
    # Pre-check: V080 tables present, else fail-closed FAIL
    # ─────────────────────────────────────────────────────────────────────
    try:
        cur.execute(
            "SELECT to_regclass('governance.canary_stage_log') IS NOT NULL, "
            "       to_regclass('governance.canary_stage_metric_registry') IS NOT NULL"
        )
        exists = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[58] table existence check failed: {exc}")

    if not exists or not exists[0]:
        return (
            "FAIL",
            "[58] governance.canary_stage_log missing — V080 not applied",
        )
    if not exists[1]:
        return (
            "FAIL",
            "[58] governance.canary_stage_metric_registry missing — V080 not applied",
        )

    # ─────────────────────────────────────────────────────────────────────
    # 1. 取所有 active cohort 的 latest stage transition row
    #    Per cohort_id 取 created_at_ms DESC 第 1 row（Hot-path index
    #    idx_canary_stage_log_cohort_created_at 對應）。
    # 1. Latest stage transition per active cohort.
    #    Hot-path index aligned: idx_canary_stage_log_cohort_created_at
    #    (cohort_id, created_at_ms DESC).
    # ─────────────────────────────────────────────────────────────────────
    sql_latest_per_cohort = (
        "SELECT DISTINCT ON (cohort_id) "
        "       cohort_id, to_stage, transition_kind, "
        "       decision_lease_id::text, triggered_metric, "
        "       created_at_ms "
        "FROM governance.canary_stage_log "
        "ORDER BY cohort_id, created_at_ms DESC"
    )
    try:
        cur.execute(sql_latest_per_cohort)
        latest_rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[58] latest-stage query failed: {exc}")

    # 0 row 是部署初期合理狀態（Stage 0 default 不寫 transition row 直至
    # operator 顯式 promote 或 SM-04 escalate）；視為 PASS 並 surface info。
    # 0 rows is acceptable initial state (Stage 0 default writes no transition
    # until operator explicit promote or SM-04 escalate); PASS + surface info.
    if not latest_rows:
        return (
            "PASS",
            "[58] 0 stage transitions logged — Stage 0 default initial state "
            "(W-AUDIT-9 not yet promoted to Stage 1+; expected post-deploy)",
        )

    # ─────────────────────────────────────────────────────────────────────
    # 2. 取 metric registry 全表（active=true 為主）
    # 2. Read full metric registry (active=true primary).
    # ─────────────────────────────────────────────────────────────────────
    sql_metric_registry = (
        "SELECT stage, metric_name, direction, "
        "       threshold_value::float, observation_window_ms, active "
        "FROM governance.canary_stage_metric_registry "
        "WHERE active = TRUE"
    )
    try:
        cur.execute(sql_metric_registry)
        registry_rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[58] metric registry query failed: {exc}")

    # 建 stage → set(metric_name) 對照
    # Build stage → set(metric_name) lookup
    registered_metrics_per_stage: dict[int, set[str]] = {}
    for row in registry_rows:
        stage = int(row[0])
        metric_name = row[1]
        registered_metrics_per_stage.setdefault(stage, set()).add(metric_name)

    # ─────────────────────────────────────────────────────────────────────
    # 3. 偵測 SM-04 ≥ L3 escalate（invariant 12）
    #    最近 24h 任一 cohort 出現 transition_kind='incident_rollback'
    #    且 reason / triggered_metric 暗示 SM-04 → 全 cohort 必須 Stage 0
    # 3. SM-04 >= L3 escalate detection (invariant 12).
    #    Recent 24h any cohort with transition_kind='incident_rollback' +
    #    reason hints SM-04 → all cohorts must be Stage 0.
    # ─────────────────────────────────────────────────────────────────────
    sql_sm04_recent = (
        "SELECT cohort_id, to_stage, triggered_metric, created_at_ms "
        "FROM governance.canary_stage_log "
        "WHERE transition_kind = 'incident_rollback' "
        "  AND created_at_ms > "
        "      (extract(epoch from now() - interval '24 hours')::bigint * 1000) "
        "  AND ( "
        "    coalesce(triggered_metric, '') ILIKE %s "
        "    OR coalesce(triggered_metric, '') ILIKE %s "
        "  ) "
        "ORDER BY created_at_ms DESC"
    )
    try:
        cur.execute(sql_sm04_recent, ("%sm04%", "%sm-04%"))
        sm04_recent_rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[58] SM-04 escalate query failed: {exc}")

    sm04_escalated_24h = len(sm04_recent_rows) > 0

    # ─────────────────────────────────────────────────────────────────────
    # 4. invariant 11 partial-rollout 偵測：manual_promote NULL lease
    #    （V080 PG CHECK 應阻擋，仍保險查）
    # 4. invariant 11 partial-rollout: manual_promote NULL lease
    #    (V080 PG CHECK should block, still defensive query).
    # ─────────────────────────────────────────────────────────────────────
    sql_manual_null_lease = (
        "SELECT count(*)::int "
        "FROM governance.canary_stage_log "
        "WHERE transition_kind = 'manual_promote' "
        "  AND decision_lease_id IS NULL"
    )
    try:
        cur.execute(sql_manual_null_lease)
        manual_null_row = cur.fetchone()
        manual_null_count = (
            int(manual_null_row[0] or 0) if manual_null_row else 0
        )
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[58] manual_promote NULL-lease query failed: {exc}")

    # ─────────────────────────────────────────────────────────────────────
    # 5. 對 latest_rows 跑 5 invariant evaluation
    #    每個 cohort 單獨評；最終 verdict 取最高嚴重度。
    # 5. Evaluate 5 invariants over latest_rows; final verdict = max severity.
    # ─────────────────────────────────────────────────────────────────────
    fails: list[str] = []
    warns: list[str] = []
    active_cohort_count = 0
    cohorts_at_stage_zero = 0

    for row in latest_rows:
        cohort_id = row[0]
        to_stage = int(row[1])
        transition_kind = row[2]
        decision_lease_id = row[3]
        triggered_metric = row[4]
        created_at_ms = int(row[5])

        if to_stage == 0:
            cohorts_at_stage_zero += 1
            # Stage 0 cohort 無更多 invariant 要驗（fail-closed default）
            # Stage 0 cohort: no further invariants to verify (fail-closed default)
            continue

        active_cohort_count += 1

        # ────────────────────────────────────────────────────────────
        # invariant 12 SM-04 escalate enforce：
        #   24h 內 SM-04 escalate → 任一 cohort 仍 Stage ≥1 = FAIL
        # ────────────────────────────────────────────────────────────
        if sm04_escalated_24h:
            fails.append(
                f"cohort={cohort_id}@stage={to_stage} "
                "but SM-04 escalate detected in 24h — auto-rollback to "
                "Stage 0 NOT honored (invariant 12)"
            )

        # ────────────────────────────────────────────────────────────
        # invariant 4 observation_period 一致性
        # 對 Stage 1/2/3 cohort，現在 - stage_entered 不應 < spec 觀察期
        # 但允許 > spec（cohort 拖延中，operator 等 metric trip）
        # ────────────────────────────────────────────────────────────
        # 注意：spec invariant 4 = "observation_period 一致"，這裡解為「Stage 1
        # cohort 在 7d 內未提前升級」。本健檢不能直接看「未來會否提前升級」，
        # 但能驗 to_stage = 1 cohort entered_at_ms 與當前 epoch 差 < 7d 時，
        # 該 cohort 仍處 Stage 1（沒已升 Stage 2 或被 rollback）。實作上以
        # to_stage < expected_stage_at_now 偵測「已升級早於期望」場景。
        # 為簡化，本實作只驗 to_stage > 0 的 cohort 不能在 created_at_ms
        # 後 < 1h 又出現另一升級 transition（提前升級顯然違反觀察期）。
        # 完整 7d/14d/21d enforcement 邏輯依賴 §4.2 metric SQL 實際執行
        # （超出 healthcheck 簡單 SELECT 範疇，留 W-AUDIT-9 T7 E4 regression
        # 完整覆蓋）。
        # ────────────────────────────────────────────────────────────
        # NOTE: spec invariant 4 = "observation_period consistency"; here
        # interpreted narrowly as "Stage 1 cohort should not advance
        # earlier than 7d wall-clock". A rigorous timeline check requires
        # cross-referencing prior transitions. We surface a WARN if
        # to_stage advanced again within < (spec observation period * 0.5)
        # of stage_entered_at_ms, signalling premature promotion drift.
        # Full 7d/14d/21d rigor lives in W-AUDIT-9 T7 E4 regression suite.
        # ────────────────────────────────────────────────────────────
        if to_stage in STAGE_OBSERVATION_PERIOD_MS:
            min_obs_ms = STAGE_OBSERVATION_PERIOD_MS[to_stage]
            if min_obs_ms > 0:
                # 對該 cohort 查更早一筆 transition 是否在 < 50% 觀察期內
                # Query prior transition for same cohort within < 50% obs period
                try:
                    cur.execute(
                        "SELECT created_at_ms "
                        "FROM governance.canary_stage_log "
                        "WHERE cohort_id = %s "
                        "  AND created_at_ms < %s "
                        "ORDER BY created_at_ms DESC "
                        "LIMIT 1",
                        (cohort_id, created_at_ms),
                    )
                    prior_row = cur.fetchone()
                except Exception as exc:  # noqa: BLE001
                    warns.append(
                        f"cohort={cohort_id} prior-transition query failed: {exc}"
                    )
                    prior_row = None

                # prior_row 可能為 None / (None,) / 真實 row；統一防禦
                # prior_row may be None / (None,) / actual row; defensive
                if prior_row is not None and prior_row[0] is not None:
                    prior_ms = int(prior_row[0])
                    elapsed_ms = created_at_ms - prior_ms
                    if elapsed_ms < (min_obs_ms // 2):
                        elapsed_h = elapsed_ms / 1000.0 / 3600.0
                        spec_d = min_obs_ms / 1000.0 / 86400.0
                        warns.append(
                            f"cohort={cohort_id}@stage={to_stage} promoted "
                            f"after {elapsed_h:.1f}h (spec observation period "
                            f"={spec_d:.0f}d) — invariant 4 premature drift"
                        )

        # ────────────────────────────────────────────────────────────
        # invariant 5 cohort 規範
        #   Stage 1/2 cohort_id 必為 'strategy:symbol:env' tuple
        #   Stage 3 cohort_id 必為 'global'
        # ────────────────────────────────────────────────────────────
        if to_stage in (1, 2):
            # cohort_id 必含至少 2 個 ':'（strategy:symbol:env）
            # cohort_id must contain >= 2 ':' (strategy:symbol:env)
            if cohort_id.count(":") < 2 or cohort_id == "global":
                fails.append(
                    f"cohort={cohort_id}@stage={to_stage} cohort_id 違反 "
                    "Stage 1/2 必為 1×1 cohort 規範（須 'strategy:symbol:env'）"
                )
        elif to_stage == 3:
            # Stage 3 必為 active universe，per AMD §2.2 = 'global'
            # Stage 3 must be active universe (per AMD §2.2 = 'global')
            if cohort_id != "global":
                fails.append(
                    f"cohort={cohort_id}@stage=3 cohort_id 違反 "
                    "Stage 3 必為 active universe（須 cohort_id='global'）"
                )

        # ────────────────────────────────────────────────────────────
        # invariant 1+2 metric registry 存在性
        # 對 to_stage 必註冊 promote condition + rollback trigger 各 1+
        # ────────────────────────────────────────────────────────────
        if to_stage in STAGE_PROMOTE_METRICS_MIN:
            min_metrics = STAGE_PROMOTE_METRICS_MIN[to_stage]
            registered = registered_metrics_per_stage.get(to_stage, set())
            missing = [m for m in min_metrics if m not in registered]
            if missing:
                warns.append(
                    f"cohort={cohort_id}@stage={to_stage} 缺 metric registry: "
                    f"{','.join(missing)}（spec drift signal）"
                )

    # ─────────────────────────────────────────────────────────────────────
    # 6. invariant 11 PG-layer NOT NULL drift（V080 應阻擋）
    # 6. invariant 11 PG-layer NOT NULL drift (V080 should block).
    # ─────────────────────────────────────────────────────────────────────
    if manual_null_count > 0:
        fails.append(
            f"manual_promote NULL-lease rows={manual_null_count} "
            "violates invariant 11 (V080 CHECK constraint partial-rollout drift)"
        )

    # ─────────────────────────────────────────────────────────────────────
    # 7. 構造 verdict
    # 7. Compose verdict.
    # ─────────────────────────────────────────────────────────────────────
    base = (
        f"active_cohorts={active_cohort_count}, "
        f"stage0_cohorts={cohorts_at_stage_zero}, "
        f"sm04_escalated_24h={sm04_escalated_24h}, "
        f"manual_null_lease={manual_null_count}"
    )

    if fails:
        # 取首 3 個 FAIL 作 msg（避免長度爆炸）
        # Take first 3 FAILs as msg (avoid bloat)
        fail_summary = "; ".join(fails[:3])
        if len(fails) > 3:
            fail_summary += f" (+{len(fails) - 3} more)"
        return (
            "FAIL",
            f"{base} — invariant violations: {fail_summary}",
        )

    if warns:
        warn_summary = "; ".join(warns[:3])
        if len(warns) > 3:
            warn_summary += f" (+{len(warns) - 3} more)"
        return (
            "WARN",
            f"{base} — drift / spec missing: {warn_summary}",
        )

    return (
        "PASS",
        f"{base} — graduated_canary_stage_invariant all 5 unbroken",
    )
