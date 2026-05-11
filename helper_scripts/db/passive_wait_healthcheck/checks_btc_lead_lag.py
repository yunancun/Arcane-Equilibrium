"""W2 A4-C BTC→Alt Lead-Lag panel 健康檢查。

MODULE_NOTE:
  `[57]` 監測 W2 A4-C BTC→Alt Lead-Lag panel (`panel.btc_lead_lag_panel`,
  W-AUDIT-8a Phase B Tier 2 cross-asset namespace) 是否有真實 producer
  在寫入新鮮 snapshot，cohort 是否覆蓋 spec §2.2 的 7-symbol set，
  regime extreme ratio 是否在健康分佈，以及 W2-IMPL-1 orderbook 接線後
  `btc_book_imbalance` 是否真的寫入非 0 / 非 NULL 真實值。

  本 check 是 PA W2 dispatch plan §3.3 規範的 4 條件健康監測：
    (1) panel freshness：max(snapshot_ts_ms) age < 120s (PASS) / 120-300s (WARN) /
        ≥ 300s (FAIL)
    (2) cohort coverage：alt_symbols cohort size 必 = 7（spec §2.2
        ETHUSDT/SOLUSDT/XRPUSDT/DOGEUSDT/ADAUSDT/AVAXUSDT/DOTUSDT）
    (3) regime extreme ratio：extreme_n / total_n < 5% PASS / 5-20% WARN /
        ≥ 20% FAIL（spec §9 condition #5：|BTC 1h return| > 200 bps 標 extreme，
        持續高比率代表 BTC 異常波動，shadow log 大量被排除，evidence 失準）
    (4) book_imb_avg 非 0 非 NULL：W2-IMPL-1 orderbook 接線後 producer
        必寫真實 imbalance（spec §3.1.3），全 0 / NULL 代表 producer 還在
        placeholder 階段（W2-IMPL-1 未 land）或 orderbook subscription 斷

  Verdict matrix（PA dispatch plan §3.3）：
    PASS = 4 條件全綠
    WARN = age 120-300s OR extreme_ratio 5-20%（不破 hard FAIL 但需關注）
    FAIL = age ≥ 300s OR cohort_size < 7 OR extreme_ratio ≥ 20%
           OR (book_imb_avg=0/NULL AND OPENCLAW_W2_HEALTHCHECK_BOOK_REQUIRED=1)

  Pre-deploy 行為：
    - V088 panel.btc_lead_lag_panel table 不存在 → PASS_SKIP（pre-deploy 不阻塞）
    - panel 表存在但 0 row → PASS_SKIP（首次 deploy 後 60s 內預期）

  Opt-in env：
    - OPENCLAW_W2_HEALTHCHECK_ENABLED=1：啟用本 check（預設 = 0 PASS_SKIP）
    - OPENCLAW_W2_HEALTHCHECK_BOOK_REQUIRED=1：W2-IMPL-1 orderbook 接線
      land 後升 book_imb_avg=0/NULL 為 FAIL（預設 = 0，W2-IMPL-1 land 前 WARN）
    - OPENCLAW_W2_HEALTHCHECK_REQUIRED=1：把 WARN 升 FAIL（嚴格模式）

  Sister check：
    [66] check_panel_freshness（W1 panel.* 二表 funding/oi_delta freshness 合併版）
    本 [57] 專注 W2 panel.btc_lead_lag_panel 4 條件深度檢查，不重複 [66] 範圍。

  對應 cron：helper_scripts/cron/passive_wait_healthcheck_cron.sh
  （6h 一次，CLAUDE.md §七「被動等待 TODO 必附 healthcheck」強制配對）。
"""

from __future__ import annotations

import os


# ============================================================
# §1 常數定義
# ============================================================

# Panel freshness threshold（毫秒）— per PA dispatch plan §3.3
# (a) age < 120s → PASS（producer 健康寫入）
# (b) 120s ≤ age < 300s → WARN（producer 偶有 lag，BB WS 或 Bybit kline 延遲）
# (c) age ≥ 300s → FAIL（producer dead 或 1m grain bucket 斷 ≥ 5 個）
PANEL_FRESHNESS_PASS_THRESHOLD_MS: int = 120 * 1000
PANEL_FRESHNESS_FAIL_THRESHOLD_MS: int = 300 * 1000

# Cohort coverage 目標 — spec §2.2 鎖定 7 symbol
# 7-sym = ETHUSDT/SOLUSDT/XRPUSDT/DOGEUSDT/ADAUSDT/AVAXUSDT/DOTUSDT
# cohort_size < 7 → FAIL（writer hardcoded cohort 列表錯）
EXPECTED_COHORT_SIZE: int = 7

# Regime extreme ratio threshold — spec §9 condition #5
# (a) ratio < 5% → PASS（BTC 1h return 多在 normal range，shadow evidence 完整）
# (b) 5% ≤ ratio < 20% → WARN（BTC 高波動期，extreme row 較多但仍可用 normal subset）
# (c) ratio ≥ 20% → FAIL（BTC 異常波動期，evidence 失準，需 operator 評估）
REGIME_EXTREME_PASS_RATIO: float = 0.05
REGIME_EXTREME_FAIL_RATIO: float = 0.20

# Healthcheck 觀察窗 — 1h，覆蓋 producer 1m grain × 60 snapshot
# 對齊 spec §4.1 hypertable hot-path index (snapshot_ts_ms DESC) 1h window
HEALTHCHECK_WINDOW_MINUTES: int = 60


# ============================================================
# §2 env helper
# ============================================================


def _enabled(name: str, default: str = "0") -> bool:
    """讀取 env flag（"1" 才視為啟用），其他值（含未設）回 False。"""
    return os.getenv(name, default).strip() == "1"


def _status(required: bool) -> str:
    """REQUIRED env 設定時 WARN 升 FAIL；否則維持 WARN。"""
    return "FAIL" if required else "WARN"


# ============================================================
# §3 main check
# ============================================================


def check_57_btc_lead_lag_panel_health(cur) -> tuple[str, str]:
    """[57] W2 A4-C BTC→Alt Lead-Lag panel 4 條件健康檢查。

    Pure SELECT inside cursor block；defensive rollback at top to keep
    cursor clean across sibling checks（與 [55]/[58]/[66] 同 pattern）。

    Returns (status, detail_msg)：
      - "PASS"：4 條件全綠 OR 預設 disabled OR pre-deploy
      - "WARN"：1-2 條件偏移（age 120-300s OR extreme 5-20%）
      - "FAIL"：≥3 條件破 OR age ≥ 300s OR cohort < 7 OR extreme ≥ 20%
    """
    # default-off opt-in：未設 env 視為 PASS-skip（pre-deploy 不阻塞）
    if not _enabled("OPENCLAW_W2_HEALTHCHECK_ENABLED"):
        return (
            "PASS",
            "[57] W2 btc_lead_lag panel healthcheck disabled by env "
            "(set OPENCLAW_W2_HEALTHCHECK_ENABLED=1 to enable, default-off pre-IMPL-1)",
        )

    required = _enabled("OPENCLAW_W2_HEALTHCHECK_REQUIRED")
    book_required = _enabled("OPENCLAW_W2_HEALTHCHECK_BOOK_REQUIRED")

    # Defensive rollback：保 cursor 在 sibling check 間乾淨（per [55]/[58]/[66] 同 pattern）
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 - defensive cleanup must not raise
        pass

    # ============================================================
    # 條件 1：V088 panel.btc_lead_lag_panel 存在性檢查
    # ============================================================
    try:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL", ("panel.btc_lead_lag_panel",))
        row = cur.fetchone()
        exists = bool(row and row[0])
    except Exception as exc:  # noqa: BLE001 - passive sentinel 必須 surface
        return (
            _status(required),
            f"[57] panel.btc_lead_lag_panel existence query failed: "
            f"{type(exc).__name__}: {exc}",
        )

    if not exists:
        # V088 未 deploy → pre-deploy 不阻塞（PASS_SKIP）
        return (
            "PASS",
            "[57] panel.btc_lead_lag_panel ABSENT — V088 not yet deployed "
            "(pre-deploy gate; W2 IMPL-2 producer not running)",
        )

    # ============================================================
    # 條件 2：聚合 1h window 內 4 指標（age / cohort / extreme / book_imb）
    # ============================================================
    #
    # SQL 一次取 4 條件 evidence（避免多次 cursor roundtrip）：
    #   - age_seconds：NOW() - max(to_timestamp(snapshot_ts_ms/1000)) 秒數
    #   - cohort_size：max(array_length(alt_symbols, 1))（writer hardcoded 7
    #     symbol cohort；最大值代表 producer 真實寫入的 cohort 完整度）
    #   - total_n：1h window 內 row 總數（producer 1m × 60 = 60 row 預期）
    #   - extreme_n：regime_tag = 'extreme' row 數
    #   - book_imb_avg：abs(btc_book_imbalance) 平均（0 = placeholder
    #     或全 NULL = orderbook subscription 斷；非 0 = W2-IMPL-1 接線生效）
    #   - book_imb_nonnull_n：btc_book_imbalance IS NOT NULL row 數
    #
    # 走 hot-path index idx_btc_lead_lag_panel_ts_window (snapshot_ts_ms DESC)
    # WHERE snapshot_ts_ms > NOW() - 1h epoch ms — index scan，1h 約 60 row 極輕
    try:
        cur.execute(
            """
            SELECT
                EXTRACT(EPOCH FROM NOW() - to_timestamp(MAX(snapshot_ts_ms)::BIGINT / 1000.0))
                    AS age_seconds,
                MAX(array_length(alt_symbols, 1))::INT
                    AS cohort_size_max,
                COUNT(*)::INT
                    AS total_n,
                COUNT(*) FILTER (WHERE regime_tag = 'extreme')::INT
                    AS extreme_n,
                AVG(ABS(btc_book_imbalance)) FILTER (WHERE btc_book_imbalance IS NOT NULL)
                    AS book_imb_abs_avg,
                COUNT(*) FILTER (WHERE btc_book_imbalance IS NOT NULL)::INT
                    AS book_imb_nonnull_n
            FROM panel.btc_lead_lag_panel
            WHERE snapshot_ts_ms > (EXTRACT(EPOCH FROM NOW() - (%s::text || ' minutes')::interval) * 1000)::BIGINT
            """,
            (HEALTHCHECK_WINDOW_MINUTES,),
        )
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 - passive sentinel 必須 surface
        return (
            _status(required),
            f"[57] panel.btc_lead_lag_panel aggregate query failed: "
            f"{type(exc).__name__}: {exc}",
        )

    if not row:
        return (
            _status(required),
            "[57] panel.btc_lead_lag_panel aggregate returned NULL row — "
            "unexpected (V088 hot-path index broken?)",
        )

    age_seconds_raw, cohort_size_max, total_n, extreme_n, book_imb_abs_avg, book_imb_nonnull_n = row

    # total_n = 0 → 1h 內無新 row（V088 deploy 後 60s 內 OR producer dead）
    if total_n is None or int(total_n) <= 0:
        return (
            "PASS",
            f"[57] panel.btc_lead_lag_panel exists but 0 rows in last {HEALTHCHECK_WINDOW_MINUTES}m "
            "— W2 IMPL-2 producer not yet writing (post-deploy <60s window OR producer dead "
            "— if engine running >5min, investigate panel_aggregator/btc_lead_lag.rs)",
        )

    total_n = int(total_n)
    extreme_n = int(extreme_n or 0)
    book_imb_nonnull_n = int(book_imb_nonnull_n or 0)

    # ============================================================
    # 條件 3：分項 verdict 計算
    # ============================================================

    # ── (1) age verdict
    # age_seconds_raw 可能為 None（無 row）/ Decimal / float；統一轉 float
    age_seconds = float(age_seconds_raw) if age_seconds_raw is not None else float("inf")
    age_ms = age_seconds * 1000.0
    if age_ms < PANEL_FRESHNESS_PASS_THRESHOLD_MS:
        age_verdict = "PASS"
    elif age_ms < PANEL_FRESHNESS_FAIL_THRESHOLD_MS:
        age_verdict = "WARN"
    else:
        age_verdict = "FAIL"

    # ── (2) cohort_size verdict
    cohort_size = int(cohort_size_max) if cohort_size_max is not None else 0
    if cohort_size == EXPECTED_COHORT_SIZE:
        cohort_verdict = "PASS"
    elif cohort_size < EXPECTED_COHORT_SIZE:
        cohort_verdict = "FAIL"
    else:
        # cohort_size > 7（writer 多寫）— WARN，spec §2.2 上限 7 但 producer 可預留
        cohort_verdict = "WARN"

    # ── (3) regime extreme ratio verdict
    extreme_ratio = float(extreme_n) / float(total_n)
    if extreme_ratio < REGIME_EXTREME_PASS_RATIO:
        extreme_verdict = "PASS"
    elif extreme_ratio < REGIME_EXTREME_FAIL_RATIO:
        extreme_verdict = "WARN"
    else:
        extreme_verdict = "FAIL"

    # ── (4) book_imbalance verdict
    # W2-IMPL-1 接線前：btc_book_imbalance = 0.0 placeholder（producer 寫死）
    # W2-IMPL-1 接線後：abs(btc_book_imbalance) > 0 真實值（top-10 bid/ask imbalance）
    # avg 為 None = 全 NULL；avg = 0.0 = 全 placeholder
    if book_imb_abs_avg is None:
        # 全 NULL — orderbook subscription 斷 OR producer 不寫此欄
        book_verdict = "FAIL" if book_required else "WARN"
        book_state = "all_null"
    elif float(book_imb_abs_avg) <= 1e-9:
        # 全 0（placeholder）— W2-IMPL-1 未 land
        book_verdict = "FAIL" if book_required else "WARN"
        book_state = "placeholder_zero"
    else:
        # 真實非 0 值 — W2-IMPL-1 接線生效
        book_verdict = "PASS"
        book_state = f"real(avg_abs={float(book_imb_abs_avg):.4f}, nonnull_n={book_imb_nonnull_n}/{total_n})"

    # ============================================================
    # 條件 4：整體 verdict 整合（PA dispatch plan §3.3 規則）
    # ============================================================

    verdicts = [age_verdict, cohort_verdict, extreme_verdict, book_verdict]
    fail_count = sum(1 for v in verdicts if v == "FAIL")
    warn_count = sum(1 for v in verdicts if v == "WARN")

    # PA dispatch plan §3.3：
    #   FAIL = age ≥ 300s OR cohort_size < 7 OR extreme_ratio ≥ 20%
    #          OR (book_required=1 AND book FAIL)
    #          OR ≥3 條件破
    #   WARN = 1-2 條件偏移
    #   PASS = 4 條件全綠
    if (
        age_verdict == "FAIL"
        or cohort_verdict == "FAIL"
        or extreme_verdict == "FAIL"
        or fail_count >= 3
        or (book_required and book_verdict == "FAIL")
    ):
        overall = "FAIL"
    elif warn_count > 0 or fail_count > 0:
        overall = _status(required)
    else:
        overall = "PASS"

    # ============================================================
    # 條件 5：detail msg（4 sub-verdict + raw value，供 reviewer 解讀）
    # ============================================================

    detail = (
        f"window={HEALTHCHECK_WINDOW_MINUTES}m total_n={total_n} "
        f"age={age_seconds:.1f}s/{age_verdict} "
        f"cohort={cohort_size}/{EXPECTED_COHORT_SIZE}/{cohort_verdict} "
        f"extreme={extreme_n}({extreme_ratio:.1%})/{extreme_verdict} "
        f"book={book_state}/{book_verdict}"
    )

    if overall == "PASS":
        return (
            "PASS",
            f"[57] W2 btc_lead_lag panel healthy ({detail})",
        )
    if overall == "WARN":
        return (
            "WARN",
            f"[57] W2 btc_lead_lag panel degraded "
            f"({fail_count} FAIL / {warn_count} WARN sub-checks) — {detail}",
        )
    return (
        "FAIL",
        f"[57] W2 btc_lead_lag panel silent-dead or evidence corrupt "
        f"({fail_count} FAIL / {warn_count} WARN sub-checks) — {detail}",
    )
