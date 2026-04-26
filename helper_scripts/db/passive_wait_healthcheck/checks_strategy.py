"""Strategy-flow + scheduler healthchecks.
策略流 + scheduler healthcheck。

MODULE_NOTE (EN): Extracted from the original ``passive_wait_healthcheck.py``:
  * [10] check_intents_writer_ratio              (lines 521-610)
  * [11] check_counterfactual_clean_window_growth (lines 1299-1468)
  * [12] check_bb_breakout_post_deadlock_fix     (lines 723-814)
  * [13] check_edge_estimator_scheduler_fresh    (lines 1471-1590)
  * [14] check_exit_features_accumulation_rate   (lines 1593-1782)
  * [15] check_shadow_exit_agreement_phase2      (lines 1903-2122)
  * [16] check_strategist_cycle_fresh            (lines 1785-1900)

These all live on the strategy / scheduler axis: intent flow, EDGE-DIAG
counterfactual gate, bb_breakout deadlock-fix verification, edge
scheduler freshness, EDGE-P1b accumulation, EDGE-P2 agreement gate, and
G3-11 strategist cycle liveness.

SQL strings, exit-code semantics, output formatting are byte-identical
to the pre-split version.

MODULE_NOTE (中): 從原 passive_wait_healthcheck.py 7 個 check 抽出 — 全部
在策略流 / scheduler 軸：intent 流、EDGE-DIAG counterfactual gate、
bb_breakout deadlock-fix 驗證、edge scheduler 新鮮度、EDGE-P1b 累積、
EDGE-P2 agreement gate、G3-11 strategist cycle liveness。SQL / exit code
/ 輸出格式與拆分前 byte-identical。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .db import _scalar
from .shared import _read_bb_breakout_active_from_toml


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


def check_bb_breakout_post_deadlock_fix(cur) -> tuple[str, str]:
    """[12] bb_breakout post-FIX-26-DEADLOCK-1 fill rate — P1-11 (1) Phase 1.

    G2-06 (2026-04-26): If `[bb_breakout].active=false` in
    `settings/strategy_params_demo.toml` (per PA RFC `2026-04-26 G2-06`
    permanent disable), this check returns PASS (skip) immediately —
    silencing the FAIL noise so other dormancy checks remain visible.
    Re-enabling the strategy (active=true) restores the original 3-state
    triage logic without further code changes.

    Context: 2026-04-24 sweep + Rust commit ``bcc5401`` discovered + fixed
    `squeeze_detected_ms` permanent-deadlock bug. Pre-fix, bb_breakout had
    14d 0 fills (symbol-locked after first failed-entry expiry). Post-fix
    + ``--rebuild`` deploy + multiple validation cycles still showed 0 fills,
    confirming F1 1m bandwidth mis-scale is structural (not deadlock
    residue). PA RFC 2026-04-26 chose option C (permanent disable).

    Three-state triage (when active=true):
      - 7d entries (`strategy_name='bb_breakout'`, no risk_close prefix):
        - 0 over 7d post-deploy → FAIL (fix didn't work or thresholds still
          mis-scaled per F1; check engine binary rebuild + thresholds)
        - 1-5 over 7d → WARN (out of dormant but very low; threshold tuning
          per Phase 2 backlog needed)
        - ≥6 over 7d → PASS (operating normally)
      - Pre-deploy state: this check fails until ``--rebuild`` deploys the
        Rust fix. Operator should mark this expected until that happens.

    The check looks for the **engine PID start time** as a deploy proxy
    (`/tmp/openclaw/engine_pid` mtime); if absent, falls back to a
    7d-window strategy fill count without deploy gating.

    [12] FIX-26-DEADLOCK-1 部署後 bb_breakout 是否真的脫離 permanent-dormant。
    G2-06（2026-04-26）：若 demo TOML `[bb_breakout].active=false`（PA RFC
    永久 disable）則直接 PASS 跳過，避免持續 FAIL 噪音蓋過真 alarm；TOML
    flip 回 true 後自動恢復原三態邏輯，無需改碼。
    7d entry 數三態（active=true 時）：0=FAIL（修沒生效或閾值還錯）/
    1-5=WARN（出 dormant 但極低）/ >=6=PASS（正常運作）。
    """
    # G2-06 (2026-04-26): TOML-driven disable skip — PA RFC permanent disable.
    # Read demo strategy_params TOML; if [bb_breakout].active=false, skip.
    # Fail-soft: any TOML read error falls through to original triage logic.
    # G2-06：讀 demo TOML，active=false 則跳過；TOML 讀失敗 fail-soft 走原邏輯。
    bb_active, _diag = _read_bb_breakout_active_from_toml()
    if bb_active is False:
        return (
            "PASS",
            "[12] bb_breakout disabled by G2-06 (active=false in TOML); fill check skipped",
        )

    try:
        n_7d = _scalar(cur,
            "SELECT COUNT(*) FROM trading.fills "
            "WHERE ts > now() - interval '7 days' "
            "AND engine_mode = 'demo' "
            "AND strategy_name = 'bb_breakout'"
        )
    except Exception as e:
        return ("WARN", f"bb_breakout 7d query failed: {e}")

    # Deploy proxy: check engine PID file mtime as a "since-rebuild" timestamp.
    # 部署代理：用 engine PID 檔 mtime 作「自 rebuild 起算」時間。
    deploy_age_hint = ""
    try:
        pid_path = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")) / "engine_pid"
        if pid_path.exists():
            mtime = datetime.fromtimestamp(pid_path.stat().st_mtime, tz=timezone.utc)
            age_h = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600.0
            deploy_age_hint = f", engine_pid age {age_h:.1f}h"
            # If engine deployed within last 7d, the "7d window" includes
            # pre-fix bars. Operator should re-eval after >7d of post-fix runtime.
            # 引擎部署 <7d 時 7d 窗包含修前資料，需等 >7d 才有 clean baseline。
            if age_h < 168:  # < 7d
                deploy_age_hint += " (window includes pre-fix data, baseline pending)"
    except Exception:
        pass

    if n_7d == 0:
        return (
            "FAIL",
            f"bb_breakout 7d entries=0{deploy_age_hint} — FIX-26-DEADLOCK-1 fix "
            f"may not be deployed (--rebuild?) or thresholds still mis-scaled (P1-11 F1)",
        )
    if n_7d < 6:
        return (
            "WARN",
            f"bb_breakout 7d entries={n_7d}{deploy_age_hint} — out of permanent-dormant "
            f"but very low; Phase 2 threshold tuning recommended",
        )
    return (
        "PASS",
        f"bb_breakout 7d entries={n_7d}{deploy_age_hint} — operating normally post-deadlock-fix",
    )


def check_counterfactual_clean_window_growth() -> tuple[str, str]:
    """[11] EDGE-DIAG-1 Phase 3 gate — post-P013-clean bucket row/fire growth.

    MODULE_NOTE (EN): Phase 4 cron-side healthcheck for the "wait N days until
    post-P013-clean bucket accumulates ≥200 rows per FM bootstrap-CI threshold"
    passive-wait TODO (EDGE-DIAG-1 Phase 3 deferred 2026-04-24). Reads the
    latest `counterfactual_exit_replay_latest.json` at `$OPENCLAW_DATA_DIR/audit/`,
    extracts `by_window['post-P013-clean']` n_rows / cf_fired / per-strategy
    breakdown, snapshots today's summary to `audit/daily/YYYYMMDD.json`, and
    returns PASS (Phase 3 entry criteria met: ≥200 rows + {grid_trading,
    ma_crossover} each cf_fired ≥50 + orphan_frozen clean rows ≥20) / WARN
    (on-track with ETA) / FAIL (JSON stale >48h or n_rows regressed). Fail-soft
    on missing JSON / missing daily dir — WARN, not crash.

    MODULE_NOTE (中): Phase 4 cron 側健檢，被動等待 post-P013-clean bucket 累積
    ≥200 rows（FM bootstrap-CI 門檻）的 TODO（EDGE-DIAG-1 Phase 3 2026-04-24
    延後）。讀最新 `counterfactual_exit_replay_latest.json`，取
    `by_window['post-P013-clean']` 的 n_rows / cf_fired / 策略分佈；快照當日
    到 `audit/daily/YYYYMMDD.json`；三態返回 PASS（Phase 3 入場條件達）/
    WARN（累積中，附 ETA）/ FAIL（JSON >48h 未更新或 n_rows 倒退）。JSON
    / daily 目錄缺失 fail-soft 為 WARN，不 crash。
    """
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    audit_dir = data_dir / "audit"
    latest = audit_dir / "counterfactual_exit_replay_latest.json"
    daily_dir = audit_dir / "daily"

    if not latest.exists():
        return ("WARN", f"counterfactual_exit_replay_latest.json 不存在 at {latest} — cron 尚未首跑?")

    # Freshness guard — >48h stale means cron silent-dead.
    # Freshness：>48h 代表 cron 靜默掛掉。
    mtime = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
    age_hours = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600.0
    if age_hours > 48:
        return ("FAIL", f"counterfactual JSON age {age_hours:.1f}h > 48h — daily cron dead?")

    try:
        payload = json.load(latest.open())
    except Exception as e:
        return ("WARN", f"counterfactual JSON parse error: {e}")

    by_window = payload.get("by_window") or {}
    clean_rows = by_window.get("post-P013-clean")
    if clean_rows is None:
        return ("WARN",
                "by_window.post-P013-clean 缺失 — 檢查 cron wrapper 是否傳 --split-window")

    # Each entry in clean_rows is an aggregation group with keys:
    #   strategy_name / symbol / engine_mode / n_exits / per_model[model].cf_fired_count
    # 每 entry = aggregation group，欄位 strategy_name/symbol/n_exits/per_model[*].cf_fired_count。
    n_rows = 0
    per_strategy_fired: dict[str, int] = {}
    per_strategy_rows: dict[str, int] = {}
    for r in clean_rows:
        n = int(r.get("n_exits") or 0)
        n_rows += n
        strat = str(r.get("strategy_name") or "")
        per_strategy_rows[strat] = per_strategy_rows.get(strat, 0) + n
        pm = r.get("per_model") or {}
        # Prefer fee_only model; fall back to any single model for cf_fired.
        # 優先用 fee_only 模型；無則取任一模型的 cf_fired_count。
        fired = 0
        if isinstance(pm, dict):
            if "fee_only" in pm and isinstance(pm["fee_only"], dict):
                fired = int(pm["fee_only"].get("cf_fired_count") or 0)
            elif pm:
                first_model = next(iter(pm.values()))
                if isinstance(first_model, dict):
                    fired = int(first_model.get("cf_fired_count") or 0)
        per_strategy_fired[strat] = per_strategy_fired.get(strat, 0) + fired

    total_cf_fired = sum(per_strategy_fired.values())

    # Persist today's snapshot to daily/YYYYMMDD.json for trend / ETA computation.
    # 持久化今日 snapshot 到 daily/YYYYMMDD.json 供趨勢 / ETA 計算。
    today_key = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    try:
        daily_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = daily_dir / f"{today_key}.json"
        snapshot = {
            "utc_date": today_key,
            "recorded_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
            "source_json_mtime": mtime.isoformat(timespec="seconds"),
            "n_rows": n_rows,
            "total_cf_fired": total_cf_fired,
            "per_strategy_rows": per_strategy_rows,
            "per_strategy_fired": per_strategy_fired,
        }
        with snapshot_path.open("w") as f:
            json.dump(snapshot, f, indent=2)
    except Exception:
        # Fail-soft on daily persist failure — don't turn the whole check red.
        # 快照寫入失敗 fail-soft，不讓整個 check 紅。
        pass

    # Phase 3 entry criteria evaluation.
    # Phase 3 入場條件判定。
    grid_fired = per_strategy_fired.get("grid_trading", 0)
    ma_fired = per_strategy_fired.get("ma_crossover", 0)
    orphan_rows = per_strategy_rows.get("orphan_frozen", 0)

    criteria_ok = (
        n_rows >= 200
        and grid_fired >= 50
        and ma_fired >= 50
        and orphan_rows >= 20
    )
    base_msg = (
        f"post-P013-clean n_rows={n_rows}, cf_fired={total_cf_fired}, "
        f"grid_fired={grid_fired}, ma_fired={ma_fired}, "
        f"orphan_frozen_rows={orphan_rows}, json_age={age_hours:.1f}h"
    )

    if criteria_ok:
        return ("PASS",
                base_msg + " — Phase 3 go: strategy-scoped deploy criteria satisfied, "
                "see TODO §EDGE-DIAG-1 Phase 3")

    # Compute rate & ETA from daily snapshots (need ≥2 points).
    # 用 daily snapshots 計算速率與 ETA（需 ≥2 個點）。
    rate_per_day = 30.0  # static fallback
    rate_source = "static-30/day"
    prev_rows: int | None = None
    try:
        if daily_dir.exists():
            snapshots = sorted(daily_dir.glob("*.json"))
            # Exclude today's snapshot we just wrote; we want HISTORICAL points.
            # 排除剛寫入的今日 snapshot；僅取歷史點。
            historical = [p for p in snapshots if p.stem != today_key]
            if len(historical) >= 1:
                # Use oldest + newest-historical as two anchors.
                # 用最舊 + 最新歷史點作兩錨點。
                try:
                    oldest_data = json.load(historical[0].open())
                    newest_data = json.load(historical[-1].open())
                    prev_rows = int(newest_data.get("n_rows") or 0)
                    if historical[0].stem != historical[-1].stem:
                        d0 = datetime.strptime(historical[0].stem, "%Y%m%d")
                        d1 = datetime.strptime(historical[-1].stem, "%Y%m%d")
                        days = max(1, (d1 - d0).days)
                        delta = int(newest_data.get("n_rows") or 0) - int(oldest_data.get("n_rows") or 0)
                        if delta > 0:
                            rate_per_day = delta / days
                            rate_source = f"observed {delta}rows/{days}d"
                except Exception:
                    pass
    except Exception:
        pass

    # Regression check: if we have a previous snapshot and today's n_rows decreased → FAIL.
    # 倒退檢查：若有前次 snapshot 且今日 n_rows 下降 → FAIL（資料清除 / writer regression）。
    if prev_rows is not None and n_rows < prev_rows:
        return ("FAIL",
                base_msg + f" — n_rows regressed from {prev_rows} (prior snapshot) "
                "— data purge or writer regression suspected")

    if n_rows == 0:
        return ("WARN",
                base_msg + f" — 0 rows yet; rate={rate_source}; "
                f"ETA ~{int(200 / max(rate_per_day, 1e-6))}d to 200")

    # On-track WARN with ETA to 200-row threshold.
    # 累積中 WARN，附 ETA 到 200-row 門檻。
    remaining = max(0, 200 - n_rows)
    pct = 100.0 * n_rows / 200.0
    eta_days = int(remaining / max(rate_per_day, 1e-6)) if remaining > 0 else 0
    return ("WARN",
            base_msg + f" — {n_rows}/200 ({pct:.0f}%), rate={rate_source}, "
            f"ETA ~{eta_days}d at current rate")


def check_edge_estimator_scheduler_fresh() -> tuple[str, str]:
    """[13] G6-02 (2026-04-24): edge_estimator_scheduler freshness + cell-count.

    MODULE_NOTE (EN): G1-01 / G4-04 mandatory passive-wait healthcheck per
    CLAUDE.md §七 rule (any "wait Nh / Nd" TODO must register a check). The
    2026-04-24 10-Agent audit Verified Finding #1 was that
    `settings/edge_estimates.json` had collapsed to **1 cell** with mtime 4d
    stale — scheduler had been silently dead despite uvicorn running. Existing
    check [7] catches the freshness side at 90-min granularity (and [7a]
    enforces a 10-cell floor as the 2026-04-24 fix), but G6-02 adds a stricter
    6-hour + 50-cell sibling threshold targeted at the G1-01 recovery path:
    while we wait for scheduler to repopulate the JSON to ≥50 cells (target
    coverage matching 5 strategies × 25 symbols ≈ 125 cells with sparse
    backoff), this check FAILs the moment the JSON drifts >6h or coverage
    crosses below 10 cells. Once G1-01 stabilises and JSON is consistently
    ≥50 cells, this becomes the steady-state passive-wait sentinel.

    Distinction vs [7] / [7a]:
      - [7]: 90-min freshness floor (scheduler hourly cadence) + structure
        validation + dormant-prefix breakdown. Catches "scheduler stopped"
        within ~90 min.
      - [7a]: 10-cell minimum floor (2026-04-24 G6-01). Catches
        "JSON written but coverage collapsed".
      - [13] (this check, G6-02): tighter 6h + 50-cell **target** threshold
        for G1-01 / G4-04 recovery monitoring. Three-state distinguishes
        "scheduler healthy + full coverage" (PASS) from "partial recovery"
        (WARN at 10-49 cells) from "still broken" (FAIL at <10 OR >6h).

    Three-state output:
      - PASS: mtime <6h AND populated cells ≥50 (full G1-01 recovery target).
      - WARN: 10 ≤ populated cells < 50 (partial coverage; backfill in progress).
      - FAIL: mtime ≥6h OR populated cells <10 (scheduler dead OR coverage
        collapse — G1-01 root cause not resolved).

    Reads `_meta.n_cells` first (introduced 2026-04-20+), falls back to
    counting non-meta entries (matches [7]'s flat-map walk pattern).

    [13] G6-02（2026-04-24）：edge_estimator_scheduler 新鮮度 + cell 數雙閾值
    （CLAUDE.md §七 G1-01 / G4-04 強制要求）。2026-04-24 10-Agent audit Verified
    Finding #1 = `settings/edge_estimates.json` 縮到 1 cell + mtime 4d 停滯。
    [7]/[7a] 已覆蓋 90min freshness + 10-cell 底線；[13] 新增更嚴的 6h + 50 cell
    目標閾值，作為 G1-01 復原期主信號：scheduler 重新填滿到 ≥50 cells 期間,
    此 check 在 JSON 漂移 >6h 或覆蓋 <10 cells 時立即 FAIL。
    三態：PASS（<6h + ≥50 cells，G1-01 復原目標）/ WARN（10-49 cells partial）/
    FAIL（>=6h OR <10 cells，scheduler 仍掛或 coverage 崩潰）。
    讀法：`_meta.n_cells` 優先（2026-04-20+ 新增），fallback 數非 meta entries。
    """
    # G6-02 thresholds — tighter than [7] (90 min / 10 cells); these are the
    # G1-01 / G4-04 recovery-target sentinels. Adjust upward to 100+ cells once
    # full strategy×symbol coverage is restored (5 strategies × 25 symbols).
    # G6-02 閾值：比 [7] (90min/10 cells) 更嚴，是 G1-01 / G4-04 復原目標哨兵。
    # 全策略×幣對覆蓋恢復後（5 策略 × 25 幣對）可上調到 100+ cells。
    MAX_AGE_HOURS = 6.0
    MIN_CELLS_PASS = 50
    MIN_CELLS_WARN = 10

    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    p = base / "settings" / "edge_estimates.json"
    if not p.exists():
        return ("FAIL", f"edge_estimates.json 不存在 at {p} — scheduler never ran (G1-01)")

    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    age_h = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600.0

    # Parse cells: prefer `_meta.n_cells` (2026-04-20+ field), fall back to
    # walking the flat map (consistent with [7]'s walker for legacy JSON).
    # Cells 解析：`_meta.n_cells` 優先（2026-04-20+），fallback 走 flat map（與 [7] 一致）。
    n_cells: int | None = None
    parse_diag = ""
    try:
        data = json.load(p.open())
        meta = data.get("_meta") if isinstance(data, dict) else None
        if isinstance(meta, dict) and isinstance(meta.get("n_cells"), int):
            n_cells = int(meta["n_cells"])
            parse_diag = f"via _meta.n_cells={n_cells}"
        else:
            # Fallback: count non-meta dict entries (same logic as [7]).
            # Fallback：數非 meta dict entries（與 [7] 一致）。
            meta_keys = {"_meta", "grand_mean_bps", "generated_at", "n_total", "version"}
            cell_items = {
                k: v for k, v in data.items()
                if isinstance(v, dict) and not k.startswith("_") and k not in meta_keys
            }
            n_cells = len(cell_items)
            parse_diag = f"via flat-map walk={n_cells}"
    except Exception as e:
        # Parse failure: return FAIL because we cannot triage scheduler health
        # without cell count. Distinguish from [7] which WARNs on parse error
        # (because [7] still PASSes on freshness alone). G6-02 needs both signals.
        # Parse 失敗 FAIL：無 cell 數無法判 scheduler 狀態。與 [7] 區別：[7] 只
        # WARN（freshness 仍可單獨 PASS），G6-02 要兩個信號都齊。
        return ("FAIL",
                f"edge_estimates.json age {age_h:.1f}h, parse error: {e} — "
                "cannot triage scheduler health (G1-01)")

    msg_core = f"age={age_h:.1f}h, cells={n_cells} ({parse_diag})"

    # FAIL conditions (either dimension alone is enough).
    # FAIL 條件（任一 dimension 觸發即 FAIL）。
    if age_h >= MAX_AGE_HOURS:
        return ("FAIL",
                msg_core + f" — mtime ≥{MAX_AGE_HOURS}h (scheduler silent-dead; "
                "G1-01 root cause not resolved)")
    if n_cells < MIN_CELLS_WARN:
        return ("FAIL",
                msg_core + f" — cells <{MIN_CELLS_WARN} (coverage collapse; "
                "G1-01 / G4-04 recovery target not met)")

    # WARN: partial coverage band.
    # WARN：覆蓋恢復中。
    if n_cells < MIN_CELLS_PASS:
        return ("WARN",
                msg_core + f" — cells {n_cells}/{MIN_CELLS_PASS} (partial G1-01 "
                "recovery; backfill in progress)")

    # PASS: both dimensions meet G1-01 / G4-04 recovery target.
    # PASS：兩 dimension 皆達 G1-01 / G4-04 復原目標。
    return ("PASS",
            msg_core + f" — full G1-01 recovery target met (≥{MIN_CELLS_PASS} cells, "
            f"<{MAX_AGE_HOURS}h)")


def check_exit_features_accumulation_rate(cur) -> tuple[str, str]:
    """[14] G6-02 (2026-04-24) + EDGE-P1b T4 (2026-04-26): learning.exit_features
    weekly accumulation rate + per-strategy breakdown for calibrator readiness.

    MODULE_NOTE (EN): EDGE-P1b passive-wait healthcheck — the EDGE-P1b TODO
    waits for `learning.exit_features` to accumulate enough rows for ML
    training (per-strategy-symbol cell ≥ 200 labels). Without this check, a
    silent writer regression (e.g. paper_state hook deletion, schema_hash
    mismatch causing INSERT to be silently swapped to a no-op) could leave the
    table flat for days while the TODO still says "passive wait". This check
    compares this-week vs last-week row counts to catch acute decay AND
    surfaces per-strategy 7d row counts so operator can see which strategies
    are below the calibrator's 200-row threshold (RFC §3 EDGE-P1b T1
    `--min-samples-per-strategy 200` default).

    Compared to [3] `check_exit_features_writer` which validates the 24h
    1:1 ratio with close_fills, [14] adds a week-over-week trend signal:
      - [3] asks "is the writer firing right now per fill?"
      - [14] asks "is the writer's overall throughput consistent week to week
              AND are individual strategies meeting the calibrator threshold?"
    Both can pass independently; both are needed because [3] catches per-fill
    misses (delta > 33% over 24h) and [14] catches longer-trend collapse
    (close_fills also dropped, so per-fill ratio still looks fine) and
    per-strategy bind readiness.

    EDGE-P1b T4 (2026-04-26) addition — per-strategy slice in the message:
      * Counts last-7d rows per `strategy_name` (NO engine_mode filter,
        same scope as the global rate check).
      * Tags each strategy with its sample tier:
          [READY]   ≥200 (calibrator-min, can be bind candidate)
          [GROWING] 50-199
          [SPARSE]  1-49
        Strategies with 0 rows are silently omitted (avoid noise — the
        global headline already covers them via this_week/last_week).
      * Cohort fraction = sum of [READY] strategies' rows / total this_week
        (i.e. how much of the 7d cohort is calibrator-ready).
      * Message tail format: `; per_strategy: name1=N1[TIER], name2=N2[TIER], ...`
      * Status decision is UNCHANGED — global headline still drives PASS/WARN/FAIL;
        per-strategy slice is informational, never the cause of WARN/FAIL by
        itself (long-term goal — per RFC §2.4 fail-soft semantics).

    Three-state output (UNCHANGED from G6-02 baseline):
      - PASS: this_week > 0 AND this_week ≥ last_week × 0.5 (no severe decay).
      - WARN: this_week > 0 AND this_week < last_week × 0.3 (severe decay).
      - FAIL: this_week == 0 (writer completely silent — EDGE-P1b assumption
        violated; downstream ML training pipeline gates would silently stall).

    Edge case: last_week == 0 → if this_week > 0 the writer just started or
    came back from outage (PASS with note); if both 0 → FAIL (writer dead for
    ≥2 weeks).

    Filter: no engine_mode filter — exit_features writes for paper/demo/live_demo
    all matter for ML training corpus. Operator can grep for engine_mode
    breakdown via direct SQL if a specific engine looks anomalous.

    [14] G6-02（2026-04-24）+ EDGE-P1b T4（2026-04-26）：learning.exit_features
    週環比累積速率 + per-strategy 切片（calibrator readiness 監控）。
    EDGE-P1b TODO 被動等待 per-cell ≥200 labels；除全局週環比，T4 加 per-strategy
    7d 行數以呈現哪些策略過/未過 calibrator 200-row 門檻（RFC §3 T1 預設）。
    Per-strategy tier：[READY] ≥200 / [GROWING] 50-199 / [SPARSE] 1-49（0 行靜默忽略）；
    cohort_frac = READY 策略行數 / this_week 總行數（calibrator 就緒比例）。
    Status 決策不變：全局表頭仍主導 PASS/WARN/FAIL，per-strategy 切片為訊息資訊性
    （長期目標，RFC §2.4 fail-soft 語意）。三態：PASS（>0 且 ≥0.5×上週）/
    WARN（<0.3×上週）/ FAIL（this_week=0，writer 完全靜默 EDGE-P1b 假設破裂）。
    """
    # Defensive rollback: keep cursor clean.
    # 防禦式 rollback：保持 cursor 乾淨。
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # Table existence guard — same defensive pattern as [2]/[8]/[9].
    # 表存在性守衛 — 與 [2]/[8]/[9] 同模式。
    try:
        cur.execute("SELECT to_regclass('learning.exit_features') IS NOT NULL")
        exists = cur.fetchone()[0]
    except Exception as e:
        return ("FAIL", f"exit_features table existence check failed: {e}")
    if not exists:
        return ("FAIL", "learning.exit_features missing — V999 not applied")

    # This week (last 7d) vs last week (8d-14d ago) row counts.
    # 本週（最近 7d）vs 上週（8d-14d 前）行數。
    try:
        cur.execute(
            "SELECT COUNT(*) FROM learning.exit_features "
            "WHERE ts > now() - interval '7 days'"
        )
        this_week = int(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COUNT(*) FROM learning.exit_features "
            "WHERE ts > now() - interval '14 days' "
            "AND ts <= now() - interval '7 days'"
        )
        last_week = int(cur.fetchone()[0] or 0)
    except Exception as e:
        return ("WARN", f"exit_features rate query failed: {e}")

    # EDGE-P1b T4 addition: per-strategy 7d slice for calibrator readiness.
    # Failure of this query is non-fatal (the headline ratio still computes);
    # we just emit a "(per-strategy slice unavailable)" marker so operator
    # knows the additional context is missing rather than silently truncated.
    # EDGE-P1b T4 新增：per-strategy 7d 切片做 calibrator readiness 監控。
    # 此查詢失敗不致命（全局比仍計算）；標註 unavailable 提示 operator。
    per_strategy_tail = ""
    try:
        cur.execute(
            "SELECT strategy_name, COUNT(*) AS n "
            "FROM learning.exit_features "
            "WHERE ts > now() - interval '7 days' "
            "GROUP BY strategy_name "
            "ORDER BY n DESC, strategy_name ASC"
        )
        per_strategy_rows = cur.fetchall()
    except Exception as e:
        per_strategy_rows = None
        per_strategy_tail = f"; per_strategy=unavailable ({e})"

    if per_strategy_rows is not None:
        # Tier thresholds match RFC §3 calibrator min (200) + T2 summary tiers.
        # 分檔閾值與 RFC §3 calibrator min（200）+ T2 summary tier 對齊。
        ready_threshold = 200
        growing_threshold = 50
        ready_count = 0  # rows in READY strategies (numerator for cohort_frac)
        slice_parts: list[str] = []
        for row in per_strategy_rows:
            name = str(row[0] or "(null)")
            n = int(row[1] or 0)
            if n == 0:
                continue
            if n >= ready_threshold:
                tier = "[READY]"
                ready_count += n
            elif n >= growing_threshold:
                tier = "[GROWING]"
            else:
                tier = "[SPARSE]"
            slice_parts.append(f"{name}={n}{tier}")

        if slice_parts:
            cohort_frac = (ready_count / this_week) if this_week > 0 else 0.0
            per_strategy_tail = (
                "; per_strategy: " + ", ".join(slice_parts)
                + f" (READY_frac={cohort_frac:.0%} of this_week)"
            )
        else:
            # this_week > 0 but per-strategy GROUP BY returned no rows — impossible
            # unless `strategy_name` is all NULL. Surface as a debug note.
            # this_week > 0 但 per-strategy 無行 — 唯一可能 strategy_name 全 NULL；
            # 標註以利除錯。
            per_strategy_tail = "; per_strategy: (all rows have NULL strategy_name?)"

    base = f"this_week={this_week}, last_week={last_week}"

    # FAIL: completely silent — EDGE-P1b assumption broken.
    # FAIL：完全靜默 — EDGE-P1b 假設破裂。
    if this_week == 0:
        if last_week == 0:
            return ("FAIL", base + " — writer dead ≥2 weeks (EDGE-P1b stalled; "
                    "check exit_feature_writer.rs + paper_state hook)" + per_strategy_tail)
        return ("FAIL", base + " — writer went silent this week "
                "(check exit_feature_writer.rs + Rust panic log)" + per_strategy_tail)

    # Special case: last_week == 0 but this_week > 0 → writer just started
    # or recovered from outage. Treat as PASS with note.
    # 特例：last_week=0 但 this_week>0 → writer 剛啟動或剛恢復。PASS + 註解。
    if last_week == 0:
        return ("PASS", base + " — writer recently activated "
                "(no historical baseline; defer trend evaluation 1 more week)"
                + per_strategy_tail)

    ratio = this_week / last_week

    # WARN: severe decay (< 30% of last week).
    # WARN：嚴重衰減（<30% 上週）。
    if ratio < 0.3:
        return ("WARN", base + f" (ratio={ratio:.2f}) — severe decay <30%; "
                "EDGE-P1b accumulation stalled, investigate fill rate + writer health"
                + per_strategy_tail)

    # WARN: moderate decay (30%-50% of last week).
    # WARN：中度衰減（30%-50% 上週）。
    if ratio < 0.5:
        return ("WARN", base + f" (ratio={ratio:.2f}) — moderate decay 30-50%; "
                "monitor next-week trend" + per_strategy_tail)

    # PASS: stable or growing.
    # PASS：穩定或成長。
    return ("PASS", base + f" (ratio={ratio:.2f}) — accumulation healthy" + per_strategy_tail)


def check_strategist_cycle_fresh() -> tuple[str, str]:
    """[16] G3-11 (2026-04-25 MVP): StrategistScheduler last cycle ≤10 min ago.

    MODULE_NOTE (EN): G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 passive-wait
    sentinel. The Rust scheduler runs a 5-min cycle (R3-1; backoff to 4h on
    AI service failure). Once the cycle wedges (engine restart that didn't
    re-spawn scheduler / Demo cmd channel orphan / panic in cycle body) the
    only operator-visible symptom is "applied params haven't moved in 24h",
    which is also the legitimate steady-state. Without this check, a wedged
    scheduler can hide for days.

    Implementation choice: filesystem-only via engine.log tail parse, NOT
    IPC. The IPC method `get_strategist_cycle_metrics` exists (G3-11 Rust
    side) but requires the HMAC handshake — pulling the auth secret into
    this script would couple the healthcheck to control-api wiring. Tail
    parsing matches existing footer fallback (
    /api/v1/strategist/history/cycle_metrics in
    `strategist_history_routes.py:_parse_cycle_metrics`) and has identical
    blind-spot profile (log rotation past N min → WARN/FAIL). Operator can
    run the GUI route in parallel for the structured snapshot.

    Three-state output:
      - PASS: scheduler logged a cycle (Ok or Err) within last 10 min, OR
        scheduler not bound (engine.log shows no startup line — Demo unbound
        is by design per memory `project_strategist_scheduler_paper_orphan`).
      - WARN: last cycle 10-30 min ago (within 30-min backoff window after
        first IPC failure — still healthy but degraded).
      - FAIL: last cycle >30 min ago AND scheduler was started.

    [16] G3-11（2026-04-25 MVP）：StrategistScheduler 上次 cycle ≤10 分鐘哨兵。
    Rust 5-min cycle wedge 後唯一外部症狀「24h 沒新 apply」也可能是穩態，
    本 check 用 engine.log tail parse 區分 wedged vs 穩態。
    PASS：10 分鐘內有 cycle log，或 scheduler 未綁（log 無啟動行）。
    WARN：10-30 分鐘（首次 IPC 失敗後 30-min backoff 仍健康但降級）。
    FAIL：>30 分鐘且 scheduler 啟動過。
    """
    log_path = Path(
        os.environ.get(
            "OPENCLAW_DATA_DIR",
            "/tmp/openclaw" if os.name != "nt" else str(Path.home() / "openclaw"),
        )
    ) / "engine.log"
    if not log_path.exists():
        return ("WARN", f"engine.log missing at {log_path} — cannot evaluate cycle freshness")
    try:
        # Bounded tail (last 4 MB) mirrors the GUI footer route. The
        # scheduler logs ~1 line per 5 min so 4 MB covers many days.
        # Bounded tail（最後 4 MB）對齊 GUI footer 路由；scheduler 每 5 min
        # 一行，4 MB 覆蓋多日。
        size = log_path.stat().st_size
        with log_path.open("rb") as f:
            if size > 4 * 1024 * 1024:
                f.seek(-4 * 1024 * 1024, 2)
                f.readline()  # discard partial line
            tail = f.read().decode("utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover - filesystem race
        return ("WARN", f"engine.log read failed: {exc}")

    # Look for the most recent scheduler activity log. The Rust side emits:
    #   "StrategistScheduler started"  — once per spawn
    #   "StrategistScheduler cycle complete" — every successful cycle
    #   "StrategistScheduler cycle failed"   — every failed cycle
    #   "StrategistScheduler cancelled"      — shutdown
    # Pre-deploy of G3-11 the apply path emits "strategist params applied".
    # Match the broad family so we work pre/post G3-11 rebuild.
    # 比對所有 scheduler 活動行；廣域 match 讓 pre/post G3-11 部署都能用。
    started = "StrategistScheduler started" in tail or "策略師排程器已啟動" in tail
    activity_markers = (
        "StrategistScheduler cycle complete",
        "StrategistScheduler cycle failed",
        "strategist params applied",
        "evaluated_cycle",  # debug-level marker
        "策略師參數已應用",  # zh apply
    )

    # Find the latest matching log timestamp. Engine.log uses tracing's
    # default format with a leading RFC3339 timestamp.
    # 找最新匹配的 log 時戳；tracing 默認是 RFC3339 起頭。
    last_seen_dt: datetime | None = None
    pattern = re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)"
    )
    # Walk backwards through lines for efficiency on long tails.
    # 反向走訪行以加速長 tail 處理。
    for line in reversed(tail.splitlines()):
        if not any(marker in line for marker in activity_markers):
            continue
        m = pattern.match(line)
        if not m:
            continue
        try:
            last_seen_dt = datetime.fromisoformat(m.group("ts").replace("Z", "+00:00"))
            break
        except Exception:
            continue

    if last_seen_dt is None:
        if not started:
            return ("PASS",
                    "StrategistScheduler not started in tail — Demo unbound or fresh boot "
                    "(by design per project_strategist_scheduler_paper_orphan)")
        return ("FAIL",
                "scheduler started but no cycle activity in 4MB tail — wedged?")

    age_min = (datetime.now(tz=timezone.utc) - last_seen_dt).total_seconds() / 60.0
    if age_min < 0:
        # Clock skew — log timestamp is in the future. Pass with note.
        # 時鐘偏移 — log 時戳在未來。pass + note。
        return ("PASS", f"last cycle ts in future by {-age_min:.0f} min — clock skew")
    base = f"last cycle {age_min:.1f} min ago"
    if age_min <= 10.0:
        return ("PASS", base)
    if age_min <= 30.0:
        return ("WARN", f"{base} — within 30-min backoff window (first IPC failure?)")
    return ("FAIL", f"{base} — exceeds 30-min ceiling, scheduler likely wedged")


def check_shadow_exit_agreement_phase2(cur) -> tuple[str, str]:
    """[15] G6-02 (2026-04-24) + EDGE-P2-flip T2 (2026-04-26): Combine Layer
    shadow exit Python↔Rust agreement (overall + per-strategy slice).

    MODULE_NOTE (EN): EDGE-P2 passive-wait healthcheck — the EDGE-P2 "flip
    shadow_enabled=true and observe N days" TODO requires that the Combine
    Layer (Python decision side) and the Physical-only baseline (Rust track P
    decision side) agree on ≥95% of close events. Without this check, the
    flip period could silently produce a divergent Combine vs Physical
    distribution that operator only notices at TODO sign-off (potentially
    days late).

    Note on column semantics: V021 schema does not have separate
    `decision_python` / `decision_rust` columns; the agreement signal is
    encoded in the `disagreed BOOLEAN` column (`disagreed=FALSE` means the
    Combine output matched what Physical-only would have produced — i.e.
    Python ↔ Rust agree). This check computes 1 - disagreed_ratio over the
    last 24h window. Phase 2 target ≥95% (this G6-02 check); existing [8]
    `check_shadow_exit_ratio` uses ≥60% as the soft entry-criterion floor.

    EDGE-P2-flip T2 (2026-04-26) addition — per-strategy slice in the message:
      * Counts last-24h rows per `strategy_name` (no engine_mode filter,
        same scope as the global agreement check). Uses GROUP BY for cohort
        breakdown.
      * Per-strategy agreement ratio (1 - disagreed/total) computed for
        each active strategy.
      * Status decision policy: per RFC §2.3 (PA recommendation, PM open
        finding §11.1) — overall aggregate PASS still drives [15] status,
        but any active strategy with ≥5 rows AND <95% agreement promotes
        the result to WARN (NOT FAIL — fail-soft semantics).
        Strategies with <5 rows are skipped from the WARN trigger (sample
        too small to be reliable signal).
      * GROUP BY semantics differ from [14]: [15] uses `strategy_name`
        (exact match against `learning.decision_shadow_exits.strategy_name`
        column, written by Rust shadow_exit_writer), NOT prefix-based slice
        like [14] which uses `owner_strategy` LIKE prefix. Both 1-line
        breakdown formats are similar but the underlying COHORT MATCH is
        different: [14] groups dust_frozen / orphan_adopted / risk_close:*
        prefixes; [15] groups concrete strategy names (grid_trading,
        ma_crossover, bb_reversion, fast_track, etc.).
      * Per-strategy slice failure (GROUP BY query error) is non-fatal —
        the global agreement still computes, message gets a
        `(per-strategy slice unavailable)` marker so operator knows context
        is missing rather than silently truncated.
      * Message tail format: `; per_strategy: name=N(P%) [TIER], ...`
        where TIER = [PASS] (≥95% & n≥5) / [WARN] (<95% & n≥5) /
        [SPARSE] (n<5).

    Three-state output (UNCHANGED from G6-02 baseline status decision logic;
    T2 adds per-strategy WARN promotion as documented above):
      - PASS: 24h rows = 0 (Phase 1a dormant — shadow_enabled=false; deferred
        to [8]'s TOML-based triage), OR agreement ≥95% AND no per-strategy
        WARN trigger.
      - WARN: 80% ≤ overall agreement < 95% (Phase 2 below target but above
        intervention threshold), OR overall ≥95% but ≥1 active strategy
        (n≥5) <95% (per-strategy stratified divergence — RFC §2.3).
      - FAIL: overall agreement < 80% (Combine layer materially diverging
        from Physical baseline; flip should be reverted, EDGE-P2 paused).

    Distinction vs [8] `check_shadow_exit_ratio`:
      - [8]: Phase 2 entry guard. Asks "is shadow_enabled=true and writer
        firing?" + "is agreement ≥60% soft floor?". Checks the TOML state
        machine + writer liveness.
      - [15]: Phase 2 quality gate. Asks "given shadow is firing, is the
        Combine agreement strict ≥95% target met (overall + per-strategy)?".
        No TOML check — relies on row presence to indicate Phase 2 is actively
        underway.

    [15] G6-02（2026-04-24）+ EDGE-P2-flip T2（2026-04-26）：Combine Layer
    shadow exit Python↔Rust 一致率守衛（overall + per-strategy 切片）。
    V021 schema 用 `disagreed BOOLEAN` 編碼一致性（FALSE=Combine 同 Physical
    baseline=Python ↔ Rust agree）。本 check 算 24h 窗口 1 - disagreed_ratio。
    Phase 2 目標 ≥95%。
    T2 新增 per-strategy 切片：每策略 24h 行數 + 一致率，per RFC §2.3：
      - 任一 active 策略（n≥5）<95% → 整體升 WARN（非 FAIL，fail-soft）
      - 樣本 <5 之策略跳過 WARN trigger（樣本太小）
      - tier 標籤：[PASS] (≥95% & n≥5) / [WARN] (<95% & n≥5) / [SPARSE] (n<5)
    與 [8] 區別：[8] 是入場守衛（TOML state + ≥60% 軟底線）；[15] 是品質閘
    （strict ≥95% 目標 + per-strategy stratified）。三態：PASS（24h=0 Phase 1a
    dormant，或 ≥95% 且無 per-strategy WARN）/ WARN（80-95%，或整體 ≥95% 但
    任一活躍策略 <95%）/ FAIL（<80% 且非空，Combine 材質性分歧 EDGE-P2 應回退）。
    """
    # Defensive rollback: keep cursor clean.
    # 防禦式 rollback：保持 cursor 乾淨。
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # Table existence guard.
    # 表存在性守衛。
    try:
        cur.execute("SELECT to_regclass('learning.decision_shadow_exits') IS NOT NULL")
        exists = cur.fetchone()[0]
    except Exception as e:
        return ("FAIL", f"decision_shadow_exits table existence check failed: {e}")
    if not exists:
        return ("FAIL", "learning.decision_shadow_exits missing — V021 not applied")

    # 24h agreement query — `disagreed` BOOLEAN encodes Combine vs Physical
    # mismatch. Agreement = 1 - disagreed_ratio.
    # 24h agreement 查詢 — `disagreed` 編碼 Combine vs Physical 分歧。
    # Agreement = 1 - disagreed_ratio。
    try:
        cur.execute(
            "SELECT "
            "  COUNT(*)::int AS total, "
            "  COUNT(*) FILTER (WHERE disagreed = FALSE)::int AS agree_n "
            "FROM learning.decision_shadow_exits "
            "WHERE ts > now() - interval '24 hours'"
        )
        total, agree_n = cur.fetchone()
        total = int(total or 0)
        agree_n = int(agree_n or 0)
    except Exception as e:
        return ("WARN", f"shadow_exit agreement query failed: {e}")

    # Phase 1a dormant (shadow_enabled=false) — table empty by design.
    # Defer to [8] for the TOML-based triage; here we just pass with note.
    # Phase 1a dormant（shadow_enabled=false）— 表預期空，pass + note，
    # 細部 TOML triage 留給 [8]。
    if total == 0:
        return ("PASS",
                "decision_shadow_exits 24h=0 (Phase 1a dormant; agreement "
                "evaluation deferred until shadow_enabled=true — see [8])")

    # EDGE-P2-flip T2 addition: per-strategy 24h slice (count + agreement).
    # Failure of this query is non-fatal (the headline ratio still computes);
    # we just emit a "(per-strategy slice unavailable)" marker so operator
    # knows the additional context is missing rather than silently truncated.
    # T2 新增：per-strategy 24h 切片（行數 + 一致率）。
    # 此查詢失敗不致命（全局比仍計算）；標註 unavailable 提示 operator。
    per_strategy_tail = ""
    per_strategy_warn = False
    try:
        cur.execute(
            "SELECT strategy_name, "
            "  COUNT(*)::int AS n, "
            "  COUNT(*) FILTER (WHERE disagreed = FALSE)::int AS agree_n "
            "FROM learning.decision_shadow_exits "
            "WHERE ts > now() - interval '24 hours' "
            "GROUP BY strategy_name "
            "ORDER BY n DESC, strategy_name ASC"
        )
        per_strategy_rows = cur.fetchall()
    except Exception as e:
        per_strategy_rows = None
        per_strategy_tail = f"; per_strategy=unavailable ({e})"

    if per_strategy_rows is not None:
        # Tier thresholds match RFC §2.3:
        #   [PASS]   n ≥ 5 AND agreement ≥ 95%
        #   [WARN]   n ≥ 5 AND agreement <  95%  (triggers overall WARN promotion)
        #   [SPARSE] n < 5  (sample too small — skip WARN trigger)
        # 分檔閾值與 RFC §2.3 對齊。
        sparse_threshold = 5
        target_pct = 95.0
        slice_parts: list[str] = []
        for row in per_strategy_rows:
            name = str(row[0] or "(null)")
            n = int(row[1] or 0)
            ag = int(row[2] or 0)
            if n == 0:
                # Cannot occur (GROUP BY won't yield zero-count rows) but
                # defensive — treat as SPARSE to avoid div-by-zero.
                # 防禦：GROUP BY 不會產 0 計數行，但仍守住 div-by-zero。
                continue
            pct = 100.0 * ag / n
            if n < sparse_threshold:
                tier = "[SPARSE]"
            elif pct >= target_pct:
                tier = "[PASS]"
            else:
                tier = "[WARN]"
                per_strategy_warn = True  # overall promote → WARN per RFC §2.3
            slice_parts.append(f"{name}={n}({pct:.1f}%){tier}")

        if slice_parts:
            per_strategy_tail = "; per_strategy: " + ", ".join(slice_parts)
        else:
            # total > 0 but per-strategy GROUP BY returned no rows — only possible
            # if every row has NULL strategy_name. Surface as a debug note.
            # total > 0 但 per-strategy 無行 — 唯一可能 strategy_name 全 NULL；
            # 標註以利除錯。
            per_strategy_tail = "; per_strategy: (all rows have NULL strategy_name?)"

    agree_pct = 100.0 * agree_n / total
    base = f"24h_total={total}, agree={agree_n} ({agree_pct:.1f}%)"

    # FAIL: Combine layer materially diverging — EDGE-P2 should be paused.
    # FAIL：Combine 層材質性分歧 — EDGE-P2 應回退。
    if agree_pct < 80.0:
        return ("FAIL",
                base + " — agreement <80%; EDGE-P2 flip should be reverted "
                "(set [exit].shadow_enabled=false in risk_config_demo.toml + "
                "investigate disagreement_reason distribution)" + per_strategy_tail)

    # WARN: below 95% strict target but above intervention threshold.
    # WARN：低於 95% 嚴格目標但高於介入門檻。
    if agree_pct < 95.0:
        return ("WARN",
                base + " — Phase 2 target ≥95% not met; investigate "
                "disagreement_reason breakdown via "
                "helper_scripts/research/shadow_disagreement_breakdown.py"
                + per_strategy_tail)

    # T2 per-strategy stratified WARN: overall ≥95% but ≥1 active strategy
    # (n ≥ 5) below 95% — RFC §2.3 fail-soft semantics.
    # T2 per-strategy 升 WARN：整體達標但任一活躍策略未達標 — RFC §2.3 fail-soft。
    if per_strategy_warn:
        return ("WARN",
                base + " — overall ≥95% but ≥1 strategy <95% (per-strategy "
                "stratified divergence per RFC §2.3); investigate via "
                "helper_scripts/research/shadow_disagreement_breakdown.py"
                + per_strategy_tail)

    # PASS: ≥95% target met (overall + every active strategy).
    # PASS：≥95% 目標達成（整體 + 每個活躍策略）。
    return ("PASS", base + " — Phase 2 ≥95% target met (overall + per-strategy)"
            + per_strategy_tail)
