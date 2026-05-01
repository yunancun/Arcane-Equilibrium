"""Counterfactual clean-window healthcheck.

MODULE_NOTE (EN): Split from ``checks_strategy.py`` by
CHECKS-STRATEGY-SUBSPLIT. Owns the JSON/daily-snapshot passive-wait check for
EDGE-DIAG post-P013-clean growth.

MODULE_NOTE (中): CHECKS-STRATEGY-SUBSPLIT 從 ``checks_strategy.py`` 拆出；
負責 EDGE-DIAG post-P013-clean 累積的 JSON / daily snapshot 被動等待檢查。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


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
    (on-track with ETA, including expected rolling-window shrink) / FAIL
    (JSON stale >48h or non-rolling n_rows regressed). Fail-soft on missing
    JSON / missing daily dir — WARN, not crash.

    MODULE_NOTE (中): Phase 4 cron 側健檢，被動等待 post-P013-clean bucket 累積
    ≥200 rows（FM bootstrap-CI 門檻）的 TODO（EDGE-DIAG-1 Phase 3 2026-04-24
    延後）。讀最新 `counterfactual_exit_replay_latest.json`，取
    `by_window['post-P013-clean']` 的 n_rows / cf_fired / 策略分佈；快照當日
    到 `audit/daily/YYYYMMDD.json`；三態返回 PASS（Phase 3 入場條件達）/
    WARN（累積中，附 ETA；含 rolling window 舊資料滾出造成的合理下降）/
    FAIL（JSON >48h 未更新或非 rolling replay 的 n_rows 倒退）。JSON /
    daily 目錄缺失 fail-soft 為 WARN，不 crash。
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
        with latest.open() as f:
            payload = json.load(f)
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
            "source_days": payload.get("days"),
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
                    with historical[0].open() as f:
                        oldest_data = json.load(f)
                    with historical[-1].open() as f:
                        newest_data = json.load(f)
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

    # Regression check: a cumulative replay must not shrink, but the production
    # daily cron intentionally runs a rolling --days window. In that mode old
    # exits aging out are expected; keep the check yellow unless freshness or
    # entry criteria fail independently.
    # 倒退檢查：累積 replay 不應下降，但 production daily cron 刻意用 rolling
    # --days 視窗。此模式下舊 exits 滾出屬預期；除非 freshness 或入場條件另行
    # 失敗，僅維持黃燈。
    replay_days = payload.get("days")
    is_rolling_replay = False
    if replay_days is not None:
        try:
            is_rolling_replay = float(replay_days) > 0
        except (TypeError, ValueError):
            is_rolling_replay = False
    regression_note = ""
    if prev_rows is not None and n_rows < prev_rows:
        if is_rolling_replay:
            regression_note = (
                f"; rolling {replay_days}d window shrank from {prev_rows} "
                f"to {n_rows} as old exits aged out"
            )
        else:
            return ("FAIL",
                    base_msg + f" — n_rows regressed from {prev_rows} (prior snapshot) "
                    "— data purge or writer regression suspected")

    if n_rows == 0:
        return ("WARN",
                base_msg + regression_note + f" — 0 rows yet; rate={rate_source}; "
                f"ETA ~{int(200 / max(rate_per_day, 1e-6))}d to 200")

    # On-track WARN with ETA to 200-row threshold.
    # 累積中 WARN，附 ETA 到 200-row 門檻。
    remaining = max(0, 200 - n_rows)
    pct = 100.0 * n_rows / 200.0
    eta_days = int(remaining / max(rate_per_day, 1e-6)) if remaining > 0 else 0
    return ("WARN",
            base_msg + regression_note + f" — {n_rows}/200 ({pct:.0f}%), rate={rate_source}, "
            f"ETA ~{eta_days}d at current rate")
