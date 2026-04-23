#!/usr/bin/env python3
"""Passive-wait pipeline healthcheck.
被動等待管線健康檢查。

MODULE_NOTE (EN): Single-command check that 7 key runtime data pipelines
are actually producing data, versus silently failing under fail-open
error handling. Triggered by 2026-04-22 P1-19 RCA which discovered that
phys_lock / MICRO-PROFIT / label backfill pipelines had all been silently
dead for 2.5–3 days despite "passive wait" TODOs treating them as healthy.

MODULE_NOTE (中): 單命令檢查 7 個關鍵 runtime 資料管線實際有資料流入，
識破 fail-open 下的 silent failure。由 2026-04-22 P1-19 RCA 觸發 — 當時
發現 phys_lock / MICRO-PROFIT / label backfill 三條管線都 silent-dead
2.5-3 天，但 TODO 卻敘述為「被動等待中（健康）」。

Usage:
  POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=... \\
    python3 helper_scripts/db/passive_wait_healthcheck.py

Exit codes:
  0 = all checks PASS (all 7 pipelines healthy)
  1 = ≥1 check FAIL (pipeline silent-dead or anomalous)
  2 = DB connection error

Checks（each prints PASS / FAIL / WARN with a one-line explanation）:
  [1] close_fills_24h                — baseline: close fills on demo in last 24h
  [2] label_backfill_ratio           — learning.decision_features writes vs close_fills ratio
  [3] exit_features_writer_ratio     — learning.exit_features writes vs close_fills (EXIT-FEATURES-TABLE-1)
  [4] phys_lock_runtime              — trading.fills 'risk_close:phys_lock_*' count (TRACK-P v2)
  [5] micro_profit_fire              — trading.fills 'risk_close:COST EDGE*' count (MICRO-PROFIT-FIX-1)
  [6] trailing_stop_fire             — trading.fills 'risk_close:TRAILING STOP%' count
  [7] edge_estimates_freshness       — settings/edge_estimates.json mtime < 90min
  [10] intents_writer_ratio          — trading.intents vs orders 24h ratio (P1-12 post-mortem 2026-04-17 outage)

Rule of thumb: close_fills_24h ≥ 10 且 labels 1:1 ratio ≥ 0.8 且 exit_features
1:1 ratio ≥ 0.8 且 ≥1 risk-layer exit mechanism (#4/5/6) fire ≥ 1 time.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---- connection ----

def _get_conn():
    import psycopg2  # type: ignore
    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    return psycopg2.connect(dsn)


# ---- single-query helpers ----

def _scalar(cur, sql: str) -> int:
    cur.execute(sql)
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


# ---- individual checks ----

def check_close_fills_24h(cur) -> tuple[str, str, int]:
    """[1] Baseline: demo close_fills in last 24h. All other ratios built on this."""
    n = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '24 hours' "
        "AND engine_mode = 'demo' AND realized_pnl != 0"
    )
    if n == 0:
        return ("FAIL", f"demo 24h close_fills = 0 — P1-10 fee drag 極度壓制 or engine dead", n)
    if n < 5:
        return ("WARN", f"demo 24h close_fills = {n} — extremely low sample, ratios unreliable", n)
    return ("PASS", f"demo 24h close_fills = {n}", n)


def check_label_backfill_ratio(cur, close_fills: int) -> tuple[str, str]:
    """[2] learning.decision_features labels vs close_fills (target ratio ≥ 0.5)."""
    n = _scalar(cur,
        "SELECT COUNT(*) FROM learning.decision_features "
        "WHERE label_filled_at > now() - interval '24 hours' "
        "AND label_net_edge_bps IS NOT NULL "
        "AND engine_mode = 'demo'"
    )
    if close_fills == 0:
        return ("WARN", f"no close_fills baseline, labels={n} unscoreable")
    ratio = n / close_fills if close_fills else 0.0
    if ratio < 0.3:
        return ("FAIL", f"labels_24h={n} vs close_fills={close_fills} (ratio {ratio:.2f}) — backfill stalled")
    if ratio < 0.7:
        return ("WARN", f"labels_24h={n} vs close_fills={close_fills} (ratio {ratio:.2f}) — partial backfill")
    return ("PASS", f"labels_24h={n} vs close_fills={close_fills} (ratio {ratio:.2f})")


def check_exit_features_writer(cur, close_fills: int) -> tuple[str, str]:
    """[3] EXIT-FEATURES-TABLE-1 Rust writer — expect 1:1 with close_fills."""
    n = _scalar(cur,
        "SELECT COUNT(*) FROM learning.exit_features "
        "WHERE ts > now() - interval '24 hours' AND engine_mode = 'demo'"
    )
    if close_fills == 0:
        return ("WARN", f"no close_fills baseline, exit_features={n} unscoreable")
    delta = abs(n - close_fills)
    if delta > max(3, close_fills // 3):
        return ("FAIL", f"exit_features_24h={n} vs close_fills={close_fills} (delta {delta}) — writer broken")
    return ("PASS", f"exit_features_24h={n} vs close_fills={close_fills} (delta {delta})")


def check_phys_lock_runtime(cur) -> tuple[str, str]:
    """[4] TRACK-P v2 phys_lock runtime fire rate — expect ≥1 per 24h if edge populated.

    Pattern note (RUST-DOUBLE-PREFIX-1 2026-04-23 post-fix): the upstream
    double-prefix bug was rooted out at the single `step_6_risk_checks.rs`
    emission site (Option B via `build_risk_close_tag`), so rows now land as
    canonical `strategy_name = "risk_close:phys_lock_gate4_giveback"` (single
    prefix). The healthcheck pattern is therefore restored to the strict
    `risk_close:phys_lock_%` form. The temporary-tolerant `risk_close:%phys_lock_%`
    pattern (commit `21e3d5e`) is intentionally **withdrawn**: keeping it would
    hide any future recurrence of the double-prefix regression — we want this
    check to go red again if the invariant breaks.

    Pattern note（RUST-DOUBLE-PREFIX-1 2026-04-23 修復後）：雙前綴 bug 已在單一
    `step_6_risk_checks.rs` emission 點（`build_risk_close_tag` Option B）根治，
    所有 PHYS-LOCK 列現以標準 `strategy_name = "risk_close:phys_lock_gate4_giveback"`
    （單前綴）寫入。Pattern 恢復為嚴格 `risk_close:phys_lock_%` 形式。
    原容錯 `risk_close:%phys_lock_%`（commit `21e3d5e`）刻意**收回**：保留會遮蔽
    未來雙前綴 regression，本檢查必須在 invariant 破壞時再次亮紅。
    """
    n_24h = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '24 hours' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:phys_lock_%'"
    )
    n_7d = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '7 days' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:phys_lock_%'"
    )
    if n_7d == 0:
        return ("FAIL", f"phys_lock_* 7d=0 — Priority 6 runtime 完全 dead (P0-13/P0-14)")
    if n_24h == 0:
        return ("WARN", f"phys_lock_* 24h=0 (7d={n_7d}) — 近期停火，查 edge_estimates / atr coverage")
    return ("PASS", f"phys_lock_* 24h={n_24h} (7d={n_7d})")


def check_micro_profit_fire(cur) -> tuple[str, str]:
    """[5] MICRO-PROFIT-FIX-1 (legacy COST EDGE gate) — expect ≥1 per 24h if alive."""
    n_24h = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '24 hours' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:COST EDGE%'"
    )
    n_7d = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '7 days' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:COST EDGE%'"
    )
    if n_7d == 0:
        return ("FAIL", f"COST EDGE 7d=0 — MICRO-PROFIT gate 已被 T3 deprecated (P0-15)，現在靠 PHYS-LOCK")
    if n_24h == 0:
        return ("WARN", f"COST EDGE 24h=0 (7d={n_7d}) — stale; 確認 runtime 是否 rebuild 後 gate 被註解")
    return ("PASS", f"COST EDGE 24h={n_24h} (7d={n_7d})")


def check_trailing_stop_fire(cur) -> tuple[str, str]:
    """[6] TRAILING STOP fire rate — expect ≥1 per 7d."""
    n_7d = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '7 days' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:TRAILING STOP%'"
    )
    if n_7d == 0:
        return ("FAIL", f"TRAILING STOP 7d=0 — 所有倉位的 peak 都 < activation_pct?")
    return ("PASS", f"TRAILING STOP 7d={n_7d}")


def check_edge_estimates_freshness() -> tuple[str, str]:
    """[7] settings/edge_estimates.json mtime < 90 min (scheduler hourly)."""
    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    p = base / "settings" / "edge_estimates.json"
    if not p.exists():
        return ("FAIL", f"edge_estimates.json 不存在 at {p}")
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    age_min = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 60.0
    if age_min > 90:
        return ("FAIL", f"edge_estimates.json age {age_min:.0f} min — scheduler 可能掛了")
    if age_min > 65:
        return ("WARN", f"edge_estimates.json age {age_min:.0f} min — 略過 hourly 節奏")
    # P0-14 RCA 2026-04-22 修正：JSON 是 flat map（key = "{strategy}::{symbol}"），不是
    # 「cells array」。原 `.get("cells", [])` 永遠回 [] 空。改成 flat map 遍歷，並同時
    # 計算 strategy prefix 分布（驗 H4 — `bybit_sync` / `orphan_*` / `dust_*` 等
    # runtime owner_strategy 是否有對應 cell）。
    # P0-14 RCA 2026-04-22 fix: JSON is a flat map (key = "{strategy}::{symbol}")
    # not a "cells array". The old `.get("cells", [])` always returned []. This
    # walks the flat map and also breaks down by strategy prefix to verify H4
    # (whether runtime owner_strategy values — bybit_sync / orphan_* / dust_* —
    # have matching cells at all).
    try:
        data = json.load(p.open())
        # Flat map path — skip meta keys (anything starting with "_" or matching
        # known aggregate names like "grand_mean_bps" / "generated_at").
        meta_keys = {"grand_mean_bps", "generated_at", "n_total", "version"}
        cell_items = {
            k: v for k, v in data.items()
            if isinstance(v, dict) and not k.startswith("_") and k not in meta_keys
        }
        total = len(cell_items)
        populated = sum(
            1 for v in cell_items.values() if v.get("shrunk_bps") is not None
        )
        # strategy prefix breakdown（用於 P0-14 H4 判斷）
        prefixes: dict[str, int] = {}
        for k in cell_items:
            prefix = k.split("::", 1)[0] if "::" in k else k
            prefixes[prefix] = prefixes.get(prefix, 0) + 1
        prefix_summary = ",".join(f"{p}:{n}" for p, n in sorted(prefixes.items()))
        cov = populated / total if total else 0.0
        msg = (f"edge_estimates.json age {age_min:.0f}m, "
               f"populated {populated}/{total} ({cov:.1%}), "
               f"prefixes[{prefix_summary or 'NONE'}]")
        if total == 0:
            return ("FAIL", msg + " — JSON 無 cells（scheduler first-run 或完全停寫）")
        # H4 指紋：若 runtime 有 bybit_sync/orphan/dust 持倉但 JSON 無對應 prefix
        known_dormant = {"bybit_sync", "orphan_adopted", "orphan_frozen", "dust_frozen"}
        missing_dormant = known_dormant - set(prefixes.keys())
        if missing_dormant:
            return ("WARN", msg + f" — P0-14 H4 indicator：JSON 缺 {sorted(missing_dormant)} prefix cells")
        if cov < 0.3:
            return ("WARN", msg + " — low coverage")
        return ("PASS", msg)
    except Exception as e:
        return ("WARN", f"edge_estimates.json age {age_min:.0f}m, parse error: {e}")


def check_model_registry_freshness(cur) -> tuple[str, str]:
    """[9] learning.model_registry latest production model age — INFRA-PREBUILD-1 Part B.

    Phase 1a/2: registry is empty (no training runs yet). PASS with explicit
    "empty" message so operator knows this is expected dormancy and not a bug.

    Phase 3+ (once production models land): latest production `train_date` per
    slot should be within 30 days — PSI/drift mitigation. Thresholds:
    - table missing → FAIL (V023 not applied)
    - no production row → PASS + "empty" (Phase 1a/2 expected)
    - latest production row train_date within 30d → PASS
    - 30d < age ≤ 60d → WARN (retraining overdue)
    - age > 60d → FAIL (model likely stale, drift risk)

    [9] learning.model_registry 最新 production model 齡期。Phase 1a/2 空表屬預期；
    Phase 3+ 要求最新 production model train_date 30 天內。
    """
    try:
        cur.execute("""
            SELECT to_regclass('learning.model_registry') IS NOT NULL
        """)
        exists = cur.fetchone()[0]
    except Exception as e:
        return ("FAIL", f"table existence check failed: {e}")
    if not exists:
        return ("FAIL", "learning.model_registry missing — V023 not applied")

    # Per-slot latest-production max age: for each (strategy, engine_mode,
    # quantile) with at least one production row, find the most recent
    # train_date. Report the MIN across slots (the oldest slot is the bottleneck).
    # 每 slot 最新 production 的最大齡：跨 slots 取最小（最舊 slot = 瓶頸）。
    try:
        cur.execute("""
            WITH latest AS (
                SELECT strategy, engine_mode, quantile,
                       MAX(train_date) AS last_train_date
                FROM learning.model_registry
                WHERE canary_status = 'production'
                GROUP BY strategy, engine_mode, quantile
            )
            SELECT
                COUNT(*)::int                         AS production_slots,
                MIN(last_train_date)                  AS oldest_train_date,
                MAX(last_train_date)                  AS newest_train_date
            FROM latest
        """)
        slots, oldest, newest = cur.fetchone()
    except Exception as e:
        return ("WARN", f"registry query failed: {e}")

    if slots == 0:
        return (
            "PASS",
            "model_registry production slots=0 (expected in Phase 1a/2; flip once "
            "training pipeline writes first row via run_training_pipeline.py)",
        )

    # Compute age in days from oldest slot's train_date.
    # 以最舊 slot 的 train_date 計算天數。
    if oldest is None:
        return ("PASS", f"model_registry production slots={slots} but no train_date set")
    now = datetime.now(timezone.utc).date()
    age_days = (now - oldest).days
    msg = (
        f"model_registry production slots={slots}, "
        f"oldest={oldest} ({age_days}d ago), newest={newest}"
    )
    if age_days > 60:
        return ("FAIL", msg + " — oldest production model >60d, retrain overdue")
    if age_days > 30:
        return ("WARN", msg + " — oldest production model >30d, retrain due")
    return ("PASS", msg)


def check_intents_writer_ratio(cur) -> tuple[str, str]:
    """[10] trading.intents vs trading.orders 24h ratio per active engine_mode
    — P1-12 post-mortem guard.

    Context: on 2026-04-17, ``trading.intents`` took zero rows for the entire
    day across demo+live_demo while ``trading.orders``/``fills``/``risk_verdicts``
    kept writing normally (e.g. demo 4/17 had 1755 orders but 0 intents;
    live_demo 4/17 had 190 orders but 0 intents, and stayed broken 4/16-4/19).
    The P1-12 "bb_reversion 100% blocked" framing was actually a symptom of
    this whole-table intents-writer silent outage. This check catches recurrence.

    Coverage: (demo, live_demo). Per-mode evaluation — each mode gets its own
    verdict, then composite status = worst across modes. Skip any mode with
    orders_24h=0 (engine quiet). ``paper`` is excluded — PAPER-DISABLE-1 makes
    paper pipeline opt-in (OPENCLAW_ENABLE_PAPER=1), so silence is expected
    default; if paper is actively spawned and the writer silently dies, the
    operator is already in an investigation path for paper separately.

    Heuristic: demo 4/20-23 healthy baseline shows intents/orders ≈ 0.70-0.87
    (orders include ``strategy_close:*`` / ``risk_close:*`` tags that originate
    downstream of the intent stage, so ratio < 1.0 is normal). Per-mode:
        - orders=0 → skip (engine quiet)
        - orders>0 + intents=0 → FAIL (4/17-style outage fingerprint)
        - ratio < 0.3 → WARN (writer under-firing)
        - ratio ≥ 0.3 → PASS

    [10] trading.intents / orders 24h 比率守衛，逐 engine_mode 判定（P1-12
    2026-04-17 全天斷裂事件 post-mortem）：當時 risk_verdicts / orders / fills
    都正常寫，唯獨 intents 整天 0 rows —— **demo 與 live_demo 同時受災**，
    live_demo 更延續 4/16-4/19 四天。原只查 demo 的版本無法捕捉 live_demo
    未來再啟用後的復發。此 check 覆蓋 (demo, live_demo)，任一 mode orders>0 +
    intents=0 即 FAIL；paper 排除（OPENCLAW_ENABLE_PAPER=1 opt-in，預設 dormant）。
    """
    # Defensive rollback: if an earlier check aborted the transaction (e.g.
    # check [9] model_registry hitting a schema mismatch under Phase 1a), the
    # cursor is poisoned until rollback. Each check should be transactionally
    # independent — so we clear any dangling aborted-tx state before running.
    # 防禦式 rollback：前 check 若打斷 transaction（例如 [9] model_registry schema
    # 不匹配），後續 query 會全被 "transaction aborted" 拒絕。每 check 獨立 — 先清。
    try:
        cur.connection.rollback()
    except Exception:
        pass

    modes = ("demo", "live_demo")
    per_mode: list[tuple[str, str, str]] = []  # (mode, status, short_msg)
    try:
        for mode in modes:
            cur.execute(
                "SELECT COUNT(*) FROM trading.orders "
                "WHERE ts > now() - interval '24 hours' AND engine_mode = %s",
                (mode,),
            )
            orders_n = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT COUNT(*) FROM trading.intents "
                "WHERE ts > now() - interval '24 hours' AND engine_mode = %s",
                (mode,),
            )
            intents_n = int(cur.fetchone()[0] or 0)

            if orders_n == 0:
                per_mode.append((mode, "SKIP", f"{mode}: quiet (orders=0)"))
                continue
            if intents_n == 0:
                per_mode.append((
                    mode, "FAIL",
                    f"{mode}: intents=0 / orders={orders_n} — writer silent-dead (4/17 fingerprint)",
                ))
                continue
            ratio = intents_n / orders_n
            seg = f"{mode}: intents={intents_n}/orders={orders_n} (ratio {ratio:.2f})"
            if ratio < 0.3:
                per_mode.append((mode, "WARN", seg + " under-firing"))
            else:
                per_mode.append((mode, "PASS", seg))
    except Exception as e:
        return ("WARN", f"intents/orders 24h query failed: {e}")

    # Composite: worst wins (FAIL > WARN > PASS > SKIP-only).
    # 彙總：最差者勝（FAIL > WARN > PASS > 只有 SKIP 代表全 engine quiet）。
    statuses = [s for _, s, _ in per_mode]
    summary = " | ".join(m for _, _, m in per_mode)
    if "FAIL" in statuses:
        return ("FAIL", summary + " — check Rust trading_writer intent INSERT + DB pool")
    if "WARN" in statuses:
        return ("WARN", summary + " — healthy baseline 0.70-0.87")
    if all(s == "SKIP" for s in statuses):
        return ("PASS", summary + " — all engines quiet, nothing to compare")
    return ("PASS", summary)


def _read_shadow_enabled_from_toml() -> tuple[bool | None, str]:
    """INFRA-PREBUILD-1 L2-5 (2026-04-23): parse `[exit].shadow_enabled` from
    `settings/risk_control_rules/risk_config_demo.toml`.

    Returns a ``(value, diagnostic)`` tuple. ``value`` is True/False when the
    TOML parse and key lookup both succeed, ``None`` on any fail-soft condition
    (file missing / parse error / key absent). ``diagnostic`` carries the
    human-readable reason for the ``None`` branch so check_shadow_exit_ratio
    can annotate its PASS/FAIL message.

    Uses Python 3.11+ ``tomllib`` (already used elsewhere in this codebase —
    see paper_trading_routes.py:1044). No external dependency added.

    We deliberately parse the **actual value** rather than trusting the file
    mtime as a "flag state" proxy — operators can hand-edit the TOML and the
    mtime skew would desynchronise. This is the hot-reload contract: state
    comes from the parsed `shadow_enabled` key, nothing else.

    L2-5 TOML 解析：讀 `[exit].shadow_enabled` 真值，fail-soft 回 ``None``。
    用 tomllib（3.11+，codebase 既有使用）；刻意取真值而非 mtime，因為
    operator 可能手編 TOML 導致 mtime 與 flag 狀態不同步。
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        return (None, "tomllib unavailable (Python <3.11?)")

    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    toml_path = base / "settings" / "risk_control_rules" / "risk_config_demo.toml"

    if not toml_path.exists():
        return (None, f"risk_config_demo.toml not found at {toml_path}")

    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        # Fail-soft: TOML parse error does not flag the whole pipeline dead;
        # check_shadow_exit_ratio degrades to its pre-L2-5 ambiguous message.
        # fail-soft：TOML parse 失敗不讓整條 pipeline 紅，check 降級為原本訊息。
        return (None, f"TOML parse error: {e}")

    exit_section = data.get("exit")
    if not isinstance(exit_section, dict):
        return (None, "[exit] section absent in risk_config_demo.toml")

    val = exit_section.get("shadow_enabled")
    if not isinstance(val, bool):
        return (None, f"[exit].shadow_enabled missing or non-bool (got {val!r})")

    return (val, "ok")


def check_shadow_exit_ratio(cur) -> tuple[str, str]:
    """[8] learning.decision_shadow_exits activity — INFRA-PREBUILD-1 Part A.

    Shadow mode is OFF by default (ExitConfig.shadow_enabled=false). L2-5
    audit (2026-04-23) upgraded this check from the ambiguous "24h=0 → PASS
    (if flag ON this is silent-dead)" message to a deterministic three-state
    triage by actively parsing `settings/risk_control_rules/risk_config_demo.toml`
    for the `[exit].shadow_enabled` value:

    - `shadow_enabled=false` + 24h rows=0 → PASS (dormant as designed)
    - `shadow_enabled=true`  + 24h rows=0 → FAIL silent-dead (explicit alarm,
        exit 1 via the `any_fail` branch in main)
    - `shadow_enabled=true`  + 24h rows>0 → PASS with disagreement breakdown
        (Phase 2 agreement target ≥60%)
    - table missing → FAIL (V021 migration not applied)
    - TOML parse fails → degrade to pre-L2-5 ambiguous PASS message so a
        healthcheck-side IO hiccup does not flag the whole pipeline dead

    The TOML value is read **at check time** (no caching); operator hot-
    reloads via TOML edit or IPC patch_risk_config flip the state machine
    immediately on the next healthcheck pass.

    [8] decision_shadow_exits 三態診斷（L2-5，2026-04-23）：
    - flag=false + 24h=0 → PASS（dormant 預期）
    - flag=true  + 24h=0 → FAIL（silent-dead，Phase 2 啟動後 writer 掛掉指紋）
    - flag=true  + 24h>0 → PASS + 分歧比率
    - TOML parse 失敗 → 降級回原始 ambiguous 訊息（不讓 healthcheck 自身 IO
      問題讓整條 pipeline 亮紅）
    """
    # Table existence check — V021 applied?
    # 檢查表是否存在（V021 是否已套用？）。
    try:
        cur.execute("""
            SELECT to_regclass('learning.decision_shadow_exits') IS NOT NULL
        """)
        exists = cur.fetchone()[0]
    except Exception as e:
        return ("FAIL", f"table existence check failed: {e}")
    if not exists:
        return ("FAIL", "learning.decision_shadow_exits missing — V021 not applied")

    # Row count + disagreement breakdown over 24h window.
    # 24h 窗口：行數 + 分歧比率。
    try:
        cur.execute("""
            SELECT
                COUNT(*)::int                                        AS total,
                COUNT(*) FILTER (WHERE disagreed)::int               AS disagreed_n,
                COUNT(DISTINCT engine_mode)::int                     AS engines,
                MAX(ts) AT TIME ZONE 'UTC'                            AS last_ts
            FROM learning.decision_shadow_exits
            WHERE ts > now() - interval '24 hours'
        """)
        total, disagreed_n, engines, last_ts = cur.fetchone()
    except Exception as e:
        return ("WARN", f"shadow_exits 24h query failed: {e}")

    # INFRA-PREBUILD-1 P3-4 (2026-04-23): 加查 last_1h 作為 channel-stall 指紋。
    # 若 24h 有大量 rows 但 last_1h=0 → writer/channel 近期停擺（overflow 或 lag），
    # 24h 累積掩蓋了近期狀態。operator 看到 `24h=100, last_1h=0` 即可直覺判斷。
    # 純 observability context，不加決策邏輯（無新 WARN/FAIL 觸發條件）。
    #
    # INFRA-PREBUILD-1 P3-4（2026-04-23）：加查 last_1h 作 channel-stall 指紋。
    # 若 24h 有量但 last_1h=0 → 近期 writer/channel 停擺，24h 累積遮蔽近期；
    # operator 肉眼見 `24h=100, last_1h=0` 即秒懂。純觀察 context，不加決策邏輯。
    try:
        cur.execute("""
            SELECT COUNT(*)::int
            FROM learning.decision_shadow_exits
            WHERE ts > now() - interval '1 hour'
        """)
        last_1h = cur.fetchone()[0]
    except Exception:
        # Sub-query best-effort — don't fail the whole check on this.
        # 次要查詢 best-effort — 失敗不拖垮整體檢查。
        last_1h = -1  # sentinel for "query failed"

    # L2-5 (2026-04-23): active triage via TOML parse.
    # L2-5（2026-04-23）：主動 TOML 三態診斷。
    shadow_enabled, toml_diag = _read_shadow_enabled_from_toml()

    if total == 0:
        if shadow_enabled is None:
            # Fail-soft: TOML parse failed → fall back to ambiguous message
            # (pre-L2-5 behaviour). PASS so healthcheck self-IO glitch does
            # not flag the pipeline dead.
            # fail-soft：TOML parse 失敗 → 降級回原 ambiguous 訊息。
            return (
                "PASS",
                f"decision_shadow_exits 24h=0 "
                f"(shadow_enabled state unknown: {toml_diag}; "
                f"if flag ON this would be silent-dead)",
            )
        if shadow_enabled is True:
            # Flag ON + 0 rows → silent-dead (writer broken or channel full).
            # FAIL causes main()'s any_fail → exit 1.
            # flag=true + 24h=0 → silent-dead；main() any_fail → exit 1。
            return (
                "FAIL",
                "decision_shadow_exits 24h=0 BUT [exit].shadow_enabled=true "
                "— silent-dead writer (Phase 2 active but zero rows). "
                "Check Rust shadow_exit_writer log + channel capacity + "
                "ExitConfig hot-reload propagation.",
            )
        # shadow_enabled is False → dormant as designed.
        # shadow_enabled=false → 預期 dormant。
        return (
            "PASS",
            "decision_shadow_exits 24h=0 (shadow_enabled=false, dormant as designed)",
        )

    agreement_pct = 100.0 * (1.0 - disagreed_n / total)
    last_1h_str = f"last_1h={last_1h}" if last_1h >= 0 else "last_1h=?"
    msg = (
        f"decision_shadow_exits 24h={total}, {last_1h_str}, disagreed={disagreed_n} "
        f"({100 - agreement_pct:.1f}%), engines={engines}, last_ts={last_ts}"
    )
    # Phase 2 agreement target ≥60% (Track P vs Combine+mock-ML).
    # Phase 2 一致性目標 ≥60%（Track P vs Combine+mock-ML）。
    if agreement_pct < 60.0:
        return ("WARN", msg + " — agreement <60% Phase 2 target")
    return ("PASS", msg)


# ---- main ----

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true", help="Only print non-PASS lines")
    args = ap.parse_args()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"Passive-wait healthcheck @ {now} UTC")
    print("=" * 70)

    try:
        conn = _get_conn()
    except Exception as e:
        print(f"[FATAL] DB connect failed: {e}")
        return 2

    results: list[tuple[str, str, str]] = []  # (check_name, status, msg)
    try:
        with conn.cursor() as cur:
            # [1] baseline
            s, m, close_fills = check_close_fills_24h(cur)
            results.append(("[1] close_fills_24h", s, m))

            # [2] labels
            s, m = check_label_backfill_ratio(cur, close_fills)
            results.append(("[2] label_backfill", s, m))

            # [3] exit_features writer
            s, m = check_exit_features_writer(cur, close_fills)
            results.append(("[3] exit_features_writer", s, m))

            # [4] phys_lock
            s, m = check_phys_lock_runtime(cur)
            results.append(("[4] phys_lock_runtime", s, m))

            # [5] micro_profit
            s, m = check_micro_profit_fire(cur)
            results.append(("[5] micro_profit_fire", s, m))

            # [6] trailing stop
            s, m = check_trailing_stop_fire(cur)
            results.append(("[6] trailing_stop_fire", s, m))

            # [8] shadow_exits — INFRA-PREBUILD-1 Part A
            # Runs before conn.close(); [7] (filesystem-only) runs after.
            # [8] shadow_exits — INFRA-PREBUILD-1 A 部；在 conn.close 前跑。
            s, m = check_shadow_exit_ratio(cur)
            results.append(("[8] shadow_exits_24h", s, m))

            # [9] model_registry — INFRA-PREBUILD-1 Part B
            # Phase 1a/2 expected empty; [9] turns signal once Phase 3+ lands.
            # [9] model_registry — INFRA-PREBUILD-1 B 部；Phase 1a/2 預期空。
            s, m = check_model_registry_freshness(cur)
            results.append(("[9] model_registry_freshness", s, m))

            # [10] intents_writer_ratio — P1-12 post-mortem guard
            # Catches 4/17-style whole-table intents-writer silent outage.
            # [10] intents writer 比率守衛 — P1-12 post-mortem，防 4/17 事件復發。
            s, m = check_intents_writer_ratio(cur)
            results.append(("[10] intents_writer_ratio", s, m))
    finally:
        conn.close()

    # [7] filesystem check
    s, m = check_edge_estimates_freshness()
    results.append(("[7] edge_estimates_freshness", s, m))

    # output
    any_fail = False
    any_warn = False
    for name, status, msg in results:
        if args.quiet and status == "PASS":
            continue
        print(f"{status:4s} {name:<36s} {msg}")
        if status == "FAIL":
            any_fail = True
        elif status == "WARN":
            any_warn = True

    print("=" * 70)
    if any_fail:
        print("SUMMARY: FAIL — ≥1 pipeline silent-dead，查 docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md")
        return 1
    if any_warn:
        print("SUMMARY: WARN — 非致命但需關注")
        return 0
    print("SUMMARY: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
