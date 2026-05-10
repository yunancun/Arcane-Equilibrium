"""ML-hygiene derived healthcheck [26]/[65].
ML hygiene 衍生健康檢查 [26]/[65]。

Extracted from ``checks_derived.py`` by T6-FUP-WARN-ZONE-FILES-SPLIT.
由 T6-FUP-WARN-ZONE-FILES-SPLIT 自 ``checks_derived.py`` 抽出。

MODULE_NOTE:
  [26] dust_spiral_noise_in_ef:learning.exit_features 的 dust-spiral 雜訊
       fingerprint 監測（EXIT-FEATURES-WRITER-BUG-1-FIX RCA-A 後 sentinel）。
  [65] chain_integrity_post_audit_4b_m3 (W-AUDIT-4b M3 post-deploy 24h
       passive observation, MIT W6-1 RFC SHOULD 7, 2026-05-10):
       監測 W-AUDIT-4b M3 producer 上線後 (`f.ts > '2026-05-09 09:22 UTC'`)
       新 fills 的 entry_context_id 對應 learning.decision_features.context_id
       chain integrity。era filter 防 pre-M3 historical artifact (3570 row
       orphan, 39%) 拖累 verdict；post-M3 era 應持續 100% (2026-05-10
       21:00 UTC PM era-split empirical 92/92 PASS)。
       任一策略 < 95% 即附 per-strategy WARN annotation；< 80% global FAIL
       表示 producer broken 需 RCA。

  兩個 check 同 file 因為都屬「ML training corpus hygiene」抽象族 —
  防止下游 ML pipeline 訓練資料被 (1) historical bug fingerprint [26]
  (2) chain integrity drift [65] 污染。

  Reference:
    - MIT W6-1 RFC verdict
      `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_1_rfc_mit_signoff_verdict.md`
      §6 chain integrity post-V086 verify + §8 SHOULD 7
    - PM Sprint N+0 closure memory `memory/project_2026_05_10_sprint_n0_closure.md`
      Chain integrity 真相 section (era-split 100% post-M3 / 39% pre-M3)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# [65] W-AUDIT-4b M3 producer 接通 timestamp（UTC）。
# 來源：MIT 2026-05-10 20:35 UTC + PM 21:00 UTC era-split empirical re-audit
# pre-M3 fills 走老 path (trading.fills + risk_verdicts only)，沒寫
# learning.decision_features，所以 chain join orphan 39%。
# post-M3 fills 全 dual-write，chain join 100%（empirical 92/92 PASS）。
# ---------------------------------------------------------------------------
W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC: str = "2026-05-09 09:22:00"

# ---------------------------------------------------------------------------
# [65] 樣本 / verdict 閾值
# spec：sample 太少 → WARN_LOW_SAMPLE；ratio < 80% → FAIL；80-95% → WARN；
# >= 95% → PASS（容忍 5% late-arriving row）。
# ---------------------------------------------------------------------------
CHAIN_INTEGRITY_MIN_SAMPLE: int = 30
CHAIN_INTEGRITY_PASS_THRESHOLD_PCT: float = 95.0
CHAIN_INTEGRITY_WARN_FAIL_BOUNDARY_PCT: float = 80.0
CHAIN_INTEGRITY_PER_STRATEGY_WARN_THRESHOLD_PCT: float = 95.0


def check_dust_spiral_noise_in_ef(cur) -> tuple[str, str]:
    """[26] learning.exit_features dust-spiral noise — ML hygiene sentinel.

    F7 MIT spec (2026-04-26), ML-TRAINING-DATA-HYGIENE-1 derived. Detects
    historical / re-emerging dust-spiral noise rows in
    ``learning.exit_features`` matching:
      * ``exit_trigger_rule = 'fast_track_reduce_half'``
      * ``realized_net_bps = -5.5``
    These rows are the unmistakable fingerprint of the pre-EXIT-FEATURES-
    WRITER-BUG-1-FIX dust spiral (commits af48ee1+83456e5 closed RCA-A by
    rejecting partial-reduce EF emission via ``is_partial_reduce_tag``).
    Even after the fix lands, this sentinel watches for:
      (a) Historical rows surfacing through the 24h slide window — should
          age out naturally (informational baseline reading)
      (b) NEW rows appearing post-fix → silent regression of B1
          (``is_partial_reduce_tag`` taxonomy missed a sub-tag)

    Three-state verdict:
      * FAIL: noise_rows_24h > 20 (regression: B1 not catching new dust spiral)
      * WARN: noise_rows_24h 6-20 (possible new sub-tag escaping B1)
      * PASS: noise_rows_24h <= 5 (B1 holding; or only historical residue
              from pre-fix window)

    Sister check: [21] ``check_paper_state_dust_inventory`` watches the
    fills table for the live-side dust-spiral fingerprint at 1h resolution.
    [26] watches the learning corpus side at 24h resolution — ensures ML
    training input doesn't get re-poisoned by post-fix regression.

    [26] learning.exit_features dust-spiral noise — ML hygiene 哨兵。
    F7 MIT spec（2026-04-26）+ ML-TRAINING-DATA-HYGIENE-1 衍生。檢測歷史 /
    復發 dust-spiral 雜訊 row（exit_trigger_rule='fast_track_reduce_half'
    AND realized_net_bps=-5.5），這是 EXIT-FEATURES-WRITER-BUG-1-FIX 修復前
    dust spiral 的唯一指紋（commits af48ee1+83456e5 RCA-A 關掉 partial-reduce
    EF 發 row）。
    即使修復部署後本哨兵仍 watch：
      (a) 24h slide 期內歷史 row 自然 age out（informational baseline）
      (b) 修復後出現新 row → B1 (is_partial_reduce_tag taxonomy) silent regression
    三態：FAIL（24h>20，B1 漏抓新 dust spiral）/ WARN（6-20，可能新 sub-tag
    逃過 B1）/ PASS（<=5，B1 工作中或僅 pre-fix 殘餘）。
    Sister check：[21] paper_state_dust_inventory 看 fills 端 1h 解析；
    [26] 看 learning corpus 端 24h 解析，確保 ML 訓練輸入修復後不被再次污染。

    NOTE：本 fn placed in checks_derived.py per F7 spec assignment（ML hygiene
    is a derived/cross-cutting observability concern, not a direct strategy
    /engine flow check）；亦為避免再撐爆 checks_strategy 1200 行硬上限。
    """
    # Defensive rollback to keep cursor clean across checks.
    # 防禦式 rollback 跨 check 保持 cursor 乾淨。
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # Table existence guard — exit_features hypertable provisioned by V016/V019.
    # 表存在性守衛 — exit_features hypertable 由 V016/V019 建。
    try:
        cur.execute("SELECT to_regclass('learning.exit_features') IS NOT NULL")
        exists = cur.fetchone()[0]
    except Exception as e:
        return ("FAIL", f"exit_features table existence check failed: {e}")
    if not exists:
        return ("FAIL", "learning.exit_features missing — V016/V019 not applied")

    sql = (
        "SELECT count(*) AS noise_rows_total, "
        "  count(*) FILTER (WHERE ts > now() - interval '24 hours') AS noise_rows_24h "
        "FROM learning.exit_features "
        "WHERE exit_trigger_rule = 'fast_track_reduce_half' "
        "  AND realized_net_bps = -5.5"
    )
    try:
        cur.execute(sql)
        row = cur.fetchone()
    except Exception as e:
        return ("WARN", f"dust_spiral noise EF query failed: {type(e).__name__}: {e}")

    if row is None:
        return ("WARN", "dust_spiral noise EF query returned no row (PG anomaly)")

    noise_total = int(row[0] or 0)
    noise_24h = int(row[1] or 0)

    base_msg = f"dust_spiral_noise_total={noise_total}, dust_spiral_noise_24h={noise_24h}"

    # Three-state verdict per MIT spec (commit dd4d64a §F7-26).
    # MIT spec（commit dd4d64a §F7-26）三態 verdict。
    if noise_24h > 20:
        return (
            "FAIL",
            base_msg + " — B1 (is_partial_reduce_tag) regression: new dust spiral "
            "EF rows >20/24h; RCA EXIT-FEATURES-WRITER-BUG-1-FIX taxonomy",
        )
    if noise_24h > 5:
        return (
            "WARN",
            base_msg + " — possible new partial-reduce sub-tag escaping B1; "
            "monitor + verify is_partial_reduce_tag taxonomy",
        )
    return ("PASS", base_msg + " — B1 holding (≤5/24h; ML training corpus clean)")


def check_chain_integrity_post_audit_4b_m3(cur) -> tuple[str, str]:
    """[65] W-AUDIT-4b M3 producer post-deploy chain integrity sentinel.

    MIT W6-1 RFC SHOULD 7 (2026-05-10) requested healthcheck — 監測
    W-AUDIT-4b M3 producer 上線後 fills.entry_context_id →
    learning.decision_features.context_id chain integrity；era filter
    `f.ts > '2026-05-09 09:22 UTC'` 防 pre-M3 historical artifact
    (3570/5854 = 39% orphan，producer 不存在，不可修復) 拖累 verdict。

    Verdict bands (per spec):
      * PASS: post-M3 chain ratio ≥ 95% (容忍 5% late-arriving row)
      * WARN: post-M3 chain ratio 80-95% (drift 偵測，monitor)
      * FAIL: post-M3 chain ratio < 80% (producer broken，需 RCA)
      * WARN_LOW_SAMPLE: post-M3 fills_w_entry < 30 (verdict 不可靠)

    Per-strategy drill-down: 任一策略 chain ratio < 95% 即附 WARN
    annotation 在 message (不直接降級 global verdict — global 仍依 ratio
    判定)。spec ref: MIT W6-1 RFC verdict §6 + Sprint N+0 closure memory。

    Empirical baseline (2026-05-10 21:00 UTC PM era-split):
      * post-M3: 92/92 = 100.00% (grid 73/73 / ma 17/17 / bb_breakout 2/2)
      * pre-M3: 5854 fills_w_entry / 2284 in_df = 39.02% (historical only)

    [65] W-AUDIT-4b M3 producer 接通後 chain integrity 哨兵。
    MIT W6-1 RFC SHOULD 7（2026-05-10）要求新 healthcheck — 監測
    fills.entry_context_id ↔ learning.decision_features.context_id 串接是否
    drift。era filter `f.ts > '2026-05-09 09:22 UTC'` 排除 pre-M3 producer
    上線前 historical artifact (3570 row orphan, 39%, 不可修)，避免拖累
    post-M3 era 真實 chain coverage。

    Verdict 三段：
      * PASS：post-M3 chain ratio ≥ 95%（容忍 5% late row）
      * WARN：80-95%（drift 偵測 / monitor）
      * FAIL：< 80%（producer broken / 急需 RCA）
      * WARN_LOW_SAMPLE：post-M3 fills_w_entry < 30（verdict 不可靠）

    Per-strategy drill-down：任一策略 chain ratio < 95% 即附 annotation
    在 message。global verdict 依整體 ratio 判定（per-strategy 為輔助
    diagnosis）。

    Sister check: [2a] check_label_backfill_ratio 看 24h 全部 close fills
    JOIN linkage（不分 era）— [65] 比 [2a] 嚴：post-M3 era only + per-strategy
    breakdown + 直接對應 W-AUDIT-4b M3 producer 部署事件作 drift 防線。

    Reference:
      - MIT W6-1 RFC verdict §6 chain integrity post-V086
        `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_1_rfc_mit_signoff_verdict.md`
      - Sprint N+0 closure memory `memory/project_2026_05_10_sprint_n0_closure.md`
        §「Chain integrity 真相」era-split table
      - W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC = '2026-05-09 09:22:00'
    """
    # Defensive rollback to keep cursor clean across checks (mirrors [26]).
    # 防禦式 rollback 跨 check 保持 cursor 乾淨（鏡 [26]）。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — defensive, rollback failure ≠ fatal
        pass

    # Table existence guard — fills + decision_features 都必須存在；
    # decision_features 由 V019 建（per [2a] guard 1 pattern）。
    # 表存在性守衛 — fills + decision_features 缺即 FAIL（V019 未套用）。
    try:
        cur.execute(
            "SELECT to_regclass('trading.fills') IS NOT NULL, "
            "       to_regclass('learning.decision_features') IS NOT NULL"
        )
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 — defensive
        return ("FAIL", f"[65] table existence check failed: {exc}")
    if not row or not row[0]:
        return ("FAIL", "[65] trading.fills missing — schema not initialized")
    if not row[1]:
        return (
            "FAIL",
            "[65] learning.decision_features missing — V019 not applied "
            "(audit_migrations.py)",
        )

    # ────────────────────────────────────────────────────────────────────
    # Sub-query 1: post-M3 era global chain ratio
    # 說明：% parametrize era timestamp 避免 SQL injection（雖然是常量，
    #   保持 parametrize 是 codebase pattern，per [2a] / [55] / [64]）。
    # ────────────────────────────────────────────────────────────────────
    sql_global = (
        "SELECT "
        "  COUNT(*)::int AS total, "
        "  SUM(CASE WHEN df.context_id IS NOT NULL THEN 1 ELSE 0 END)::int "
        "    AS in_df "
        "FROM trading.fills f "
        "LEFT JOIN learning.decision_features df "
        "  ON df.context_id = f.entry_context_id "
        "WHERE f.entry_context_id IS NOT NULL "
        "  AND f.ts > %s::timestamptz"
    )
    try:
        cur.execute(sql_global, (W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC + "+00",))
        global_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 — defensive
        return ("FAIL", f"[65] global chain query failed: {exc}")

    if not global_row:
        return ("FAIL", "[65] global chain query returned no row (PG anomaly)")

    total = int(global_row[0] or 0)
    in_df = int(global_row[1] or 0)

    # 樣本不足 → WARN_LOW_SAMPLE，verdict 不可靠
    # Sample insufficient → WARN_LOW_SAMPLE, verdict unreliable.
    if total < CHAIN_INTEGRITY_MIN_SAMPLE:
        return (
            "WARN",
            f"[65] LOW_SAMPLE post-M3 fills_w_entry={total} "
            f"(need >={CHAIN_INTEGRITY_MIN_SAMPLE} for verdict; "
            f"era_filter ts > '{W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC} UTC')",
        )

    # 計算 chain ratio（不可能除 0 因為 total >= MIN_SAMPLE > 0）
    # Compute chain ratio (no div0 since total >= MIN_SAMPLE > 0).
    chain_pct = round(100.0 * in_df / total, 2)

    # ────────────────────────────────────────────────────────────────────
    # Sub-query 2: per-strategy breakdown (best-effort)
    # 任一策略 < 95% 加 WARN annotation；查詢失敗不阻 global verdict。
    # ────────────────────────────────────────────────────────────────────
    per_strategy_warn = ""
    try:
        cur.execute(
            "SELECT "
            "  f.strategy_name, "
            "  COUNT(*)::int AS total, "
            "  SUM(CASE WHEN df.context_id IS NOT NULL THEN 1 ELSE 0 END)::int "
            "    AS in_df "
            "FROM trading.fills f "
            "LEFT JOIN learning.decision_features df "
            "  ON df.context_id = f.entry_context_id "
            "WHERE f.entry_context_id IS NOT NULL "
            "  AND f.ts > %s::timestamptz "
            "GROUP BY f.strategy_name "
            "ORDER BY total DESC",
            (W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC + "+00",),
        )
        rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001 — best-effort, don't downgrade verdict
        # Per-strategy probe failed — annotate but don't fail global verdict.
        # Per-strategy 探測失敗 — 註明但不降級 global verdict。
        per_strategy_warn = f", per_strategy_probe_failed: {type(exc).__name__}"
        rows = []

    drift_strategies: list[str] = []
    for r in rows:
        strat = str(r[0] or "<null>")
        s_total = int(r[1] or 0)
        s_in_df = int(r[2] or 0)
        # 跳過樣本太少的策略（避免 noise；單 fill 不足以判 drift）
        # Skip strategies with too few samples (avoid noise).
        if s_total < 5:
            continue
        s_pct = 100.0 * s_in_df / s_total if s_total > 0 else 0.0
        if s_pct < CHAIN_INTEGRITY_PER_STRATEGY_WARN_THRESHOLD_PCT:
            drift_strategies.append(
                f"{strat}={s_in_df}/{s_total} ({s_pct:.1f}%)"
            )

    if drift_strategies and not per_strategy_warn:
        per_strategy_warn = (
            f", per_strategy_drift: {'; '.join(drift_strategies)}"
        )

    # ────────────────────────────────────────────────────────────────────
    # Verdict logic
    # ────────────────────────────────────────────────────────────────────
    base = (
        f"[65] post-M3 chain ratio = {chain_pct}% (n={total}, in_df={in_df}, "
        f"era ts > '{W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC} UTC')"
        f"{per_strategy_warn}"
    )

    # FAIL: significant drift, producer broken
    if chain_pct < CHAIN_INTEGRITY_WARN_FAIL_BOUNDARY_PCT:
        return (
            "FAIL",
            base
            + " — significant chain drift (< 80%); investigate W-AUDIT-4b M3 "
            "producer (DecisionFeatureMsg writer) — pre-M3 historical orphan "
            "should NOT count in post-M3 era filter; FAIL = post-M3 producer "
            "broken",
        )

    # WARN: 80-95% range, drift detected, monitor
    if chain_pct < CHAIN_INTEGRITY_PASS_THRESHOLD_PCT:
        return (
            "WARN",
            base
            + " — chain drift detected (80-95% range); monitor producer "
            "dual-write path; per-strategy drift annotation if any",
        )

    # WARN: PASS threshold met but per-strategy has < 95% — surface signal
    # WARN: 全局過 PASS 閾值但 per-strategy 有 < 95% — 信號 surface
    if drift_strategies:
        return (
            "WARN",
            base
            + f" — global PASS but {len(drift_strategies)} strategy(ies) "
            "below per-strategy 95% threshold (annotation above)",
        )

    # PASS: global ≥ 95% + per-strategy 全 ≥ 95% (or sample too small to judge)
    return ("PASS", base + " — chain integrity holding (W-AUDIT-4b M3 healthy)")
