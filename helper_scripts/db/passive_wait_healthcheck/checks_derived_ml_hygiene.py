"""ML-hygiene derived healthcheck [26].
ML hygiene 衍生健康檢查 [26]。

Extracted from ``checks_derived.py`` by T6-FUP-WARN-ZONE-FILES-SPLIT.
由 T6-FUP-WARN-ZONE-FILES-SPLIT 自 ``checks_derived.py`` 抽出。
"""

from __future__ import annotations

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
