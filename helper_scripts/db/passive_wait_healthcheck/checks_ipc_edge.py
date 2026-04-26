"""Risk-layer + edge-freshness + shadow + registry healthchecks.
風控層 + edge 新鮮度 + shadow + registry healthcheck。

MODULE_NOTE (EN): Extracted from the original ``passive_wait_healthcheck.py``:
  * [4] check_phys_lock_runtime          (lines 257-293)
  * [5] check_micro_profit_fire          (lines 296-337)
  * [6] check_trailing_stop_fire         (lines 340-350)
  * [7] check_edge_estimates_freshness   (lines 353-444)
  * [8] check_shadow_exit_ratio          (lines 870-991)
  * [9] check_model_registry_freshness   (lines 447-518)

These cover the risk-layer exit fire path ([4]/[5]/[6]) plus the edge
estimator's filesystem freshness gate ([7]) and the Phase 1a/2 dormancy
sentinels for the Combine-layer shadow + ML model registry ([8]/[9]).

SQL strings, exit-code semantics, output formatting are byte-identical
to the pre-split version.

MODULE_NOTE (中): 從原 passive_wait_healthcheck.py 6 個 check 抽出 — 涵蓋
風控層 exit fire（[4][5][6]）+ edge estimator 檔案 freshness（[7]）+
Combine-layer shadow / ML model registry 的 Phase 1a/2 dormancy 哨兵
（[8][9]）。SQL / exit code / 輸出格式與拆分前 byte-identical。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .db import _scalar
from .shared import _read_shadow_enabled_from_toml


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
    """[5] RETIRED — legacy COST EDGE gate replaced by PHYS-LOCK v2.

    Background / 背景:
      The legacy COST EDGE gate (MICRO-PROFIT-FIX-1, 2026-04-17) was permanently
      removed from `risk_checks.rs` Priority 6 by TRACK-P-V2-SWAP-1
      (commit 306993e, 2026-04-22). The replacement is `physical_micro_profit_lock_v2`
      which emits `risk_close:phys_lock_*` tags — covered by [4] phys_lock_runtime.
      `risk_checks.rs:250-264` keeps the old block as a comment for historical
      reference only ("DEPRECATED ... Do not re-enable without design review").

      Therefore `strategy_name LIKE 'risk_close:COST EDGE%'` will never increment
      again; once the 7d window slides past 2026-04-22, both counts become 0
      forever. Continuing to FAIL/WARN on it produces a permanent false alarm
      (24h=0 since the swap, eventually 7d=0 too) that masks real signals in
      the cron summary.

      傳統 COST EDGE gate（MICRO-PROFIT-FIX-1）已於 2026-04-22 commit 306993e
      被 TRACK-P-V2-SWAP-1 永久移除，由 `physical_micro_profit_lock_v2`
      取代，產出 `risk_close:phys_lock_*` 標籤——由 [4] phys_lock_runtime
      接管監控。本 check 永遠回 PASS（informational only），保留歷史殘留計數
      供 audit；要看 micro-profit-lock 是否健康請看 [4]。

    This check is intentionally kept (not deleted) so the cron output retains
    a stable check-id mapping; it just no longer fires alarms.
    本 check 故意保留（不刪），維持 cron 輸出 check-id 穩定；不再發出告警。
    """
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
    return ("PASS",
            f"RETIRED (replaced by [4] phys_lock_runtime, see TRACK-P-V2-SWAP-1 "
            f"commit 306993e); residue 24h={n_24h} 7d={n_7d}")


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
    """[7] settings/edge_estimates.json mtime < 90 min (scheduler hourly).

    G6-01 [7a] (2026-04-24): added expected-minimum cell-count guard. The
    QA audit (§2.2 #2) flagged that the existing freshness + structure check
    cannot distinguish "JSON written hourly with 1 cell" (= near-empty
    estimator output, mostly useless for downstream cost_gate) from "JSON
    written with full coverage". 2026-04-24 verified Reality: JSON had only
    **1 cell** despite CLAUDE.md narrative claiming 162 — exactly the
    coverage-collapse failure mode this guard catches. We now FAIL when
    populated cells < `MIN_EXPECTED_CELLS` (=10, conservative floor matching
    OPENCLAW's ~25 active strategy×symbol pairs). The 90-min freshness +
    structure parse + dormant-prefix breakdown checks are preserved as
    layered guards above this new floor.

    [7] settings/edge_estimates.json mtime < 90 min（scheduler 每小時）。
    G6-01 [7a]（2026-04-24）：新增最低 cell 數守衛 — QA audit §2.2 #2 指
    現有 freshness + 結構檢查無法區分「按時寫入但只 1 cell」（等於空輸出，
    cost_gate 無法用）與「全覆蓋」。2026-04-24 實測 JSON 只 1 cell（vs
    CLAUDE.md 宣稱 162），正是此守衛要 catch 的 coverage-collapse 模式。
    populated < `MIN_EXPECTED_CELLS`（=10，保守底線匹配 OPENCLAW 約 25 active
    strategy×symbol pair）即 FAIL。原 freshness + 結構 + dormant prefix 檢查
    皆保留為堆疊防線。
    """
    # G6-01 [7a]: minimum cell count below which the JSON is "freshly written
    # but useless" — cost_gate / phys_lock fall back to defaults. Conservative
    # floor; raise to 25 once scheduler stabilises post-G1-01 recovery.
    # G6-01 [7a]：低於此 cell 數視為「按時寫入但無用」— cost_gate / phys_lock
    # 改用 default。保守底線 10；待 G1-01 scheduler 恢復穩定後可拉到 25。
    MIN_EXPECTED_CELLS = 10

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
        # G6-01 [7a]: cell-count floor — JSON exists + fresh but coverage
        # collapsed. This is the 2026-04-24 "1-cell" failure mode RCA flag.
        # G6-01 [7a]：cell 數底線 — JSON 存在且新鮮但覆蓋崩潰。
        # 即 2026-04-24 「1 cell」失效模式 RCA 的指紋。
        if populated < MIN_EXPECTED_CELLS:
            return ("FAIL", msg + f" — populated {populated} < min_expected {MIN_EXPECTED_CELLS} "
                    "(coverage collapse; cost_gate fallback active; G1-01 scheduler diagnosis)")
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
