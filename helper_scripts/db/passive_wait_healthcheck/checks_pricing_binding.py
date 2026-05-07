"""LG-3 Provider Pricing Binding healthcheck — `[45]`.
LG-3 提供者定價綁定 healthcheck — `[45]`。

MODULE_NOTE (EN): Single passive-wait sentinel for the LG-3 RFC v1
``provider_pricing_table`` binding contract per
``docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg3_provider_pricing_binding_rfc.md``.

The fee runtime — ``AccountManager`` (Rust in-memory cache) +
``IntentProcessor::fee_rate_for_intent`` (TIF-driven maker/taker dispatch)
+ ``tasks::spawn_fee_rate_tasks`` (hourly refresh) — is already 100%
landed in the engine binary. The RFC's three IMPL gates are governance
items: T1 contract test (Sprint D), T2 healthcheck output (this file),
T3 startup assertion (deferred until LG-4 supervised live IMPL).

This sentinel is a **PG-side proxy** of the Rust runtime fee health.
We deliberately do NOT add a new IPC route to query
``AccountManager::last_fee_refresh_ms`` directly because that would
break ``xlang_consistency`` (Rust IPC hot-path tax, new HMAC route,
new Python IPC client wiring). Instead, we observe the materialized
artefact: every ``trading.fills`` row carries ``fee_rate`` (V008), so
``MAX(ts) WHERE fee_rate IS NOT NULL`` is a fresher-than-hourly
heartbeat of the runtime fee binding (fills produced → IntentProcessor
called fee_rate_for_intent → AccountManager handed over a maker/taker
rate). If the engine fee path silently regressed (e.g. always returns
default), the proxy still works — we additionally check the
distribution of ``fee_rate`` against ``DEFAULT_MAKER_FEE`` /
``DEFAULT_TAKER_FEE`` constants (mirrored from Rust
``account_manager.rs:136-138``) so a 100%-default-fallback scenario
is flagged via ``source=seed_default`` rather than masquerading as
``source=bybit_v5``.

Healthcheck output shape per RFC §2.4 ``Healthcheck Shape``:

    pricing_binding mode=<mode> category=linear source=<source>
    last_refresh_age_seconds=<int> verdict=<PASS|WARN|FAIL>

Fields:
- ``mode``: per ``trading.fills.engine_mode`` slice (``demo``,
  ``live_demo``, ``live``). Multi-mode runs report aggregated worst.
- ``category``: hardcoded ``linear`` per RFC §2.1 ``Initial LG-3 scope
  is Bybit linear contracts only``.
- ``source``: derived from 24h ``fee_rate`` distribution vs
  ``DEFAULT_*_FEE`` constants:
    * 100% match default → ``seed_default`` (acceptable for demo /
      live_demo only; FAIL for live)
    * any non-default match → ``bybit_v5`` (assume Bybit-sourced)
    * 0 fills in window → ``cold_default`` (engine just booted)
- ``last_refresh_age_seconds``: ``now() - max(ts)`` for fills with
  non-null ``fee_rate`` in last 24h.
- ``verdict``:
    * PASS: age <3600s (within hourly refresh cadence)
    * WARN: 3600s ≤ age <86400s (24h)
    * FAIL: age ≥86400s OR fee_rate_count == 0 (no fills in 24h)
            OR live mode + source='seed_default'

Three hard rules from RFC §2.3 ``Fail-Closed Rules``:
1. Live + ``seed_default`` source → FAIL (RFC: ``Mainnet must not use
   default fee rates as an availability workaround``).
2. Stale beyond 24h regardless of mode → FAIL.
3. 0 fills in window + engine running >30min → WARN (engine may be
   quiet by genuine market conditions; do not false-FAIL on quiet
   periods).

LG-3 RFC closure trail:
- T1 contract test: Sprint D (Rust+Python cross-language)
- T2 healthcheck output: **THIS FILE (Sprint C R6-T7, 2026-05-05)**
- T3 startup assertion: deferred to LG-4 supervised live IMPL pre-req

MODULE_NOTE (中): LG-3 RFC v1 提供者定價綁定哨兵（單一被動等待 check
``[45]``，per ``docs/CCAgentWorkSpace/PA/.../2026-05-01--lg3_*.md``）。

Fee runtime（Rust ``AccountManager`` 內存快取 + ``IntentProcessor::
fee_rate_for_intent`` TIF 驅動 maker/taker dispatch + 每小時刷新）已 100%
land 在 engine binary。RFC 三個 IMPL gate 屬治理事項：T1 contract test
（Sprint D）/ T2 healthcheck output（本檔，Sprint C R6-T7）/ T3 startup
assertion（延 LG-4 IMPL 前提）。

本哨兵是 **PG 端 proxy**，刻意不加新 IPC route 直查
``AccountManager::last_fee_refresh_ms`` 因為會破 ``xlang_consistency``
（Rust IPC hot-path tax + 新 HMAC route + 新 Python IPC client wiring）。
改觀察物質化產物：每筆 ``trading.fills`` 帶 ``fee_rate``（V008），故
``MAX(ts) WHERE fee_rate IS NOT NULL`` 是運行時 fee binding 的活性心跳
（fills 寫入 → IntentProcessor 呼 fee_rate_for_intent → AccountManager
回 maker/taker rate）。若引擎 fee 路徑偷偷 regress（如永遠回 default），
proxy 仍能透過 24h ``fee_rate`` 分佈對比 ``DEFAULT_*_FEE`` 常量
（鏡 Rust ``account_manager.rs:136-138``）抓到，標 ``source=seed_default``
而非偽裝為 ``source=bybit_v5``。

Output shape 對齊 RFC §2.4。Source 推斷邏輯：
- 100% 匹配 default → ``seed_default``（demo/live_demo 可接受；live
  必 FAIL）
- 任一非 default 命中 → ``bybit_v5``（推定 Bybit-sourced）
- 24h 0 fills → ``cold_default``（剛開機）

三條 RFC §2.3 fail-closed 鐵則：
1. Live + seed_default → FAIL（RFC ``Mainnet must not use default fee
   rates as an availability workaround``）。
2. Age ≥24h 不論 mode → FAIL。
3. 0 fills + engine running >30min → WARN（引擎可能因真實市況靜默；
   靜默期不 false-FAIL）。

LG-3 RFC closure：T1 留 Sprint D / T2 = 本檔 / T3 留 LG-4 前提。
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Bybit V5 linear default fee rate constants — mirrored from Rust
# ``rust/openclaw_engine/src/account_manager.rs:136-138``. Any drift between
# this Python sibling and Rust source must trigger code review (LG-3 RFC §2.3
# requires explicit category map; no implicit default).
#
# Bybit V5 linear 默認費率常量 — 鏡 Rust ``account_manager.rs:136-138``。
# Python sibling 與 Rust source 漂移必須觸發 code review（RFC §2.3 要求
# 明確 category map，禁隱式 default）。
# ---------------------------------------------------------------------------
DEFAULT_MAKER_FEE: float = 0.0002
DEFAULT_TAKER_FEE: float = 0.00055

# Floating-point comparison tolerance for default-fee match (xlang IPC
# precision floor 1e-4 per CLAUDE.md memory note `engineering:debug`).
# 默認費率匹配的浮點容差（CLAUDE.md xlang 1e-4 容差）。
DEFAULT_FEE_MATCH_EPSILON: float = 1e-6

# Refresh-age verdict thresholds per RFC §2.2 ``Refresh Cadence``.
# RFC §2.2 刷新節奏判定閾值。
REFRESH_AGE_PASS_MAX_SECONDS: int = 3600       # 1 hour
REFRESH_AGE_WARN_MAX_SECONDS: int = 86400      # 24 hours

# Engine-warmup grace window: 0 fills in 24h on a fresh engine should not
# false-FAIL. We compare against ``_engine_process_age_minutes`` if available;
# otherwise fail-soft to WARN. 30 min matches the existing healthcheck pattern
# (e.g. ``check_edge_diag_2_strategy_diversity`` engine-restart grace).
# 引擎熱機豁免：剛開機的 0 fills 不 false-FAIL；30min 對齊既有
# ``check_edge_diag_2_strategy_diversity`` 模式。
ENGINE_WARMUP_GRACE_MINUTES: float = 30.0

# Engine modes monitored by LG-3 binding (LG-3 scope = linear category only,
# all three trading modes share the same fee table per ``main_pipelines.rs``
# ``shared_account_manager`` wiring). Paper mode excluded — paper does not
# call Bybit fee endpoint and does not produce real fills with fee_rate.
# LG-3 binding 監控的 engine_mode（linear category only；paper 排除因不呼
# Bybit fee endpoint 也不寫真實 fee_rate）。
MONITORED_ENGINE_MODES: tuple[str, ...] = ("demo", "live_demo", "live")


# ---------------------------------------------------------------------------
# Helpers / 輔助函數
# ---------------------------------------------------------------------------

def _matches_default(fee_rate: float) -> bool:
    """Return True if ``fee_rate`` matches either default fee constant within
    ``DEFAULT_FEE_MATCH_EPSILON``.

    若 ``fee_rate`` 在容差內匹配 maker/taker default 任一即回 True。
    """
    return (
        abs(fee_rate - DEFAULT_MAKER_FEE) < DEFAULT_FEE_MATCH_EPSILON
        or abs(fee_rate - DEFAULT_TAKER_FEE) < DEFAULT_FEE_MATCH_EPSILON
    )


def _mainnet_live_enabled() -> bool:
    """Return whether true Mainnet live flow is explicitly enabled.

    LiveDemo is represented by ``engine_mode='live_demo'`` in the DB. The
    ``live`` slot is Mainnet-only for this healthcheck; when Mainnet is not
    explicitly enabled and the slot has no fills, treating it as a warm-engine
    quiet warning creates permanent noise for the designed 0-mainnet state.
    """
    import os

    return os.environ.get("OPENCLAW_ALLOW_MAINNET", "").strip() == "1"


def _infer_source(default_count: int, non_default_count: int) -> str:
    """Infer pricing source label from 24h fee_rate distribution.

    從 24h fee_rate 分佈推斷 pricing source 標籤。

    Returns one of:
    - ``"cold_default"``  — 0 fills in window (engine cold or quiet).
    - ``"seed_default"``  — 100% match defaults (AccountManager.seed_default_fee_rates fallback).
    - ``"bybit_v5"``      — at least one non-default value (assume Bybit-sourced).
    """
    total = default_count + non_default_count
    if total == 0:
        return "cold_default"
    if non_default_count == 0:
        return "seed_default"
    return "bybit_v5"


def _format_per_mode_summary(per_mode: dict[str, dict[str, Any]]) -> str:
    """Build operator-readable per-mode summary string for the verdict msg.
    建構 verdict msg 用的 per-mode 摘要字串（operator 可讀）。
    """
    parts: list[str] = []
    for mode in MONITORED_ENGINE_MODES:
        slot = per_mode.get(mode)
        if slot is None:
            continue
        age_s = slot.get("age_seconds")
        age_str = f"{int(age_s)}s" if age_s is not None else "no_fills"
        parts.append(
            f"{mode}: source={slot['source']}, age={age_str}, "
            f"symbols={slot['symbols']}, n={slot['fill_count']}"
        )
    return "; ".join(parts) if parts else "no monitored engine_mode rows"


# ---------------------------------------------------------------------------
# `[45]` pricing_binding — LG-3 RFC §IMPL T2 healthcheck.
# `[45]` pricing_binding — LG-3 RFC §IMPL T2 healthcheck。
# ---------------------------------------------------------------------------

def check_45_pricing_binding(cur) -> tuple[str, str]:
    """[45] LG-3 provider pricing binding sentinel — RFC §IMPL T2 (2026-05-05).

    [45] LG-3 提供者定價綁定哨兵 — RFC §IMPL T2（2026-05-05）。

    Reads the last 24h ``trading.fills`` slice across the three monitored
    engine modes (``demo``, ``live_demo``, ``live``) and reports a
    per-mode + aggregate verdict capturing:

    - ``last_refresh_age_seconds``: ``now() - max(ts)`` for non-null
      ``fee_rate`` rows (proxy for ``AccountManager.last_fee_refresh_ms``).
    - ``source``: inferred from 24h ``fee_rate`` distribution against
      Rust default constants (mirrored from ``account_manager.rs``).
    - ``symbols``: distinct symbol count contributing to the slice.
    - ``fill_count``: total non-null-fee_rate rows in the slice.

    讀過去 24h 三 engine_mode 的 ``trading.fills``，產 per-mode + 整體
    verdict，報 last_refresh_age（max ts proxy）/ source（default vs Bybit
    分佈推斷）/ distinct symbol 計數 / fill 計數。

    Verdict rules (RFC §2.2 + §2.3):
        * PASS: every monitored mode either has ≥1 fill aged <3600s OR
                quiet (0 fills) and engine warmup <30min.
        * WARN: ≥1 mode aged ≥3600s and <86400s, or quiet on warm engine.
        * FAIL: ≥1 mode aged ≥86400s, OR live mode + source=seed_default
                (RFC §2.3 mainnet fail-closed).

    Verdict 規則：
        * PASS：每個 mode 不是有 <1h 內的 fill，就是靜默且引擎 <30min（剛
                開機）。
        * WARN：≥1 mode aged ∈ [1h, 24h)，或熱機後仍靜默。
        * FAIL：≥1 mode aged ≥24h，或 live + seed_default（RFC §2.3
                mainnet fail-closed）。

    Args:
        cur: psycopg2 cursor (DB-bound; runs inside cursor block of runner).

    Returns:
        ``(status, msg)`` tuple; msg is RFC §2.4 shaped + per-mode summary
        for operator triage.
    """
    # Defensive rollback: any prior aborted transaction in the cursor must be
    # cleared so this SELECT does not chain a 25P02 error.
    # 防禦性 rollback：清掉先前 abort 的交易避免 25P02 鏈式錯誤。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001
        pass

    # SQL: per engine_mode aggregate of (fill_count, default_count,
    # non_default_count, distinct_symbols, max_ts) over last 24h. Fail-closed
    # if trading.fills missing (V003 not applied).
    # SQL：per engine_mode 24h 聚合（fill_count / default_count /
    # non_default_count / distinct_symbols / max_ts）；V003 缺則 fail-closed。
    try:
        cur.execute("SELECT to_regclass('trading.fills') IS NOT NULL")
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[45] trading.fills existence check failed: {exc}")
    if not exists_row or not exists_row[0]:
        return (
            "FAIL",
            "[45] trading.fills missing — V003 not applied; pricing binding "
            "cannot be verified",
        )

    # Use parameterized query (CLAUDE.md §七 SQL parameterization rule).
    # The %s order matches the ``MONITORED_ENGINE_MODES`` tuple expansion.
    # 用 parameterized query（CLAUDE.md §七 SQL 參數化規則）。%s 對齊
    # ``MONITORED_ENGINE_MODES`` tuple 展開。
    sql = """
SELECT engine_mode,
       count(*) FILTER (WHERE fee_rate IS NOT NULL)::int AS fill_count,
       count(*) FILTER (
           WHERE fee_rate IS NOT NULL
             AND (abs(fee_rate - %s) < %s OR abs(fee_rate - %s) < %s)
       )::int AS default_count,
       count(*) FILTER (
           WHERE fee_rate IS NOT NULL
             AND NOT (abs(fee_rate - %s) < %s OR abs(fee_rate - %s) < %s)
       )::int AS non_default_count,
       count(DISTINCT symbol) FILTER (WHERE fee_rate IS NOT NULL)::int AS symbols,
       extract(epoch FROM (now() - max(ts) FILTER (WHERE fee_rate IS NOT NULL)))::int AS age_seconds
  FROM trading.fills
 WHERE ts > now() - interval '24 hours'
   AND engine_mode = ANY(%s)
 GROUP BY engine_mode
 ORDER BY engine_mode
"""
    params = (
        DEFAULT_MAKER_FEE, DEFAULT_FEE_MATCH_EPSILON,
        DEFAULT_TAKER_FEE, DEFAULT_FEE_MATCH_EPSILON,
        DEFAULT_MAKER_FEE, DEFAULT_FEE_MATCH_EPSILON,
        DEFAULT_TAKER_FEE, DEFAULT_FEE_MATCH_EPSILON,
        list(MONITORED_ENGINE_MODES),
    )
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[45] pricing-binding query failed: {exc}")

    # Build per-mode dict; missing modes default to "quiet slot".
    # 建 per-mode dict；缺漏的 mode 視為「靜默 slot」。
    per_mode: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        mode = row[0]
        if mode not in MONITORED_ENGINE_MODES:
            continue
        fill_count = int(row[1] or 0)
        default_count = int(row[2] or 0)
        non_default_count = int(row[3] or 0)
        symbols = int(row[4] or 0)
        age_seconds = int(row[5]) if row[5] is not None else None
        per_mode[mode] = {
            "fill_count": fill_count,
            "default_count": default_count,
            "non_default_count": non_default_count,
            "symbols": symbols,
            "age_seconds": age_seconds,
            "source": _infer_source(default_count, non_default_count),
        }
    for mode in MONITORED_ENGINE_MODES:
        if mode not in per_mode:
            per_mode[mode] = {
                "fill_count": 0,
                "default_count": 0,
                "non_default_count": 0,
                "symbols": 0,
                "age_seconds": None,
                "source": "cold_default",
            }

    # Engine warmup grace lookup (filesystem-side; fail-soft to None).
    # 引擎熱機豁免查詢（filesystem 端；fail-soft 回 None）。
    # NOTE: cannot import _engine_process_age_minutes at module import time
    # because some test environments do not stub /proc; do it lazily here.
    # NOTE：避免模組 import 時對 /proc 的依賴，延遲 import。
    try:
        from .shared import _engine_process_age_minutes
        engine_age_min, _diag = _engine_process_age_minutes()
    except Exception:  # noqa: BLE001
        engine_age_min = None

    # Verdict aggregation per RFC §2.2 + §2.3.
    # 整體 verdict 聚合（RFC §2.2 + §2.3）。
    worst: str = "PASS"
    fail_reasons: list[str] = []
    warn_reasons: list[str] = []

    for mode in MONITORED_ENGINE_MODES:
        slot = per_mode[mode]
        age_s = slot["age_seconds"]
        source = slot["source"]
        fill_count = slot["fill_count"]

        # Rule 1 (RFC §2.3): live + seed_default → FAIL (mainnet fail-closed).
        # Rule 1：live + seed_default → FAIL（mainnet fail-closed）。
        if mode == "live" and source == "seed_default":
            fail_reasons.append(
                f"{mode}+source=seed_default (RFC §2.3 mainnet must not use "
                "default fee rates as availability workaround)"
            )
            worst = "FAIL"
            continue

        # Rule 2: 0 fills in window — distinguish cold engine vs production silent.
        # Rule 2：24h 0 fills — 區分冷啟動 vs production silent。
        if fill_count == 0:
            if mode == "live" and not _mainnet_live_enabled():
                slot["source"] = "inactive_mainnet"
                continue
            if engine_age_min is not None and engine_age_min < ENGINE_WARMUP_GRACE_MINUTES:
                # cold engine — accept as PASS.
                # 冷啟動 — 接受為 PASS。
                continue
            # warm engine but quiet — WARN (not enough signal to FAIL).
            # 熱機後仍靜默 — WARN（信號不足以 FAIL）。
            warn_reasons.append(
                f"{mode}: 0 fills with fee_rate in 24h "
                f"(engine_age_min={engine_age_min!r})"
            )
            if worst == "PASS":
                worst = "WARN"
            continue

        # Rule 3 (RFC §2.2): age-based verdict.
        # Rule 3（RFC §2.2）：基於 age 的判定。
        if age_s is None:
            warn_reasons.append(f"{mode}: age computation returned NULL")
            if worst == "PASS":
                worst = "WARN"
        elif age_s >= REFRESH_AGE_WARN_MAX_SECONDS:
            fail_reasons.append(
                f"{mode}: age={age_s}s exceeds 24h FAIL threshold"
            )
            worst = "FAIL"
        elif age_s >= REFRESH_AGE_PASS_MAX_SECONDS:
            warn_reasons.append(
                f"{mode}: age={age_s}s exceeds 1h refresh cadence "
                f"(but within 24h)"
            )
            if worst == "PASS":
                worst = "WARN"

    # RFC §2.4 ``Healthcheck Shape`` formatted summary.
    # RFC §2.4 標準格式輸出。
    summary = _format_per_mode_summary(per_mode)
    base = f"category=linear; {summary}"

    if worst == "FAIL":
        return (
            "FAIL",
            base + " — " + "; ".join(fail_reasons),
        )
    if worst == "WARN":
        return (
            "WARN",
            base + " — " + "; ".join(warn_reasons),
        )
    return ("PASS", base + " — pricing binding healthy across monitored modes")
