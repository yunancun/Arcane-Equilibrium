"""P1-WP03-DEPLOY-GATE-IMPL — WP-03 OU sigma residual fix post-deploy 24h monitoring gate.

MODULE_NOTE:
  ``[69]`` wp03_ou_sigma_deploy_gate 監測 WP-03 OU sigma residual fix
  (commit ``ef6ea79f`` / v35 rebuild ``2026-05-16T01:00:00Z``，engine PID
  ``69581``) 部署後 grid_trading 在 demo + live_demo 的 ``avg_net_bps``
  drift；任一窗口 trigger 即寫 ``$OPENCLAW_DATA_DIR/wp03_revert_flag``
  供 operator 顯式 decide revert（per ADR-0020 manual-only，不 auto
  trigger revert action）。

  改動範圍：``rust/openclaw_engine/src/strategies/grid_helpers.rs``
  L140 ``compute_ou_step_with_cost_floor`` sigma 估計：
    舊：``sigma = sqrt(Σdx² / n)``（含 mean-reversion drift）
    新：``sigma = sqrt(Σε² / (n-2))``（OLS 殘差 + n-2 自由度）
  預期方向：sigma 降 → grid spacing 收窄 → fill 頻次升 + signal SNR 升
  → grid_trading ``avg_net_bps`` 應升。
  反向可能：spacing 過窄 → maker fill 機率變小 / adversarial fill 升 /
  cost_bps 接近 net_bps → 任一發生 → revert flag 觸發。

  資料源 + 既有 pattern 對齊：
    - ``learning.mlde_edge_training_rows``：[40] 既有源，直接複用
      （strategy_name='grid_trading' AND engine_mode IN ('demo','live_demo')
      AND attribution_chain_ok=TRUE AND net_bps_after_fee IS NOT NULL）
    - Engine PID mtime deploy proxy：[12] 既有 pattern
      （``$OPENCLAW_DATA_DIR/engine_pid``）
    - Baseline cache JSON：filesystem persist，spec §3 lock
      window ``[2026-05-11T00:00:00Z, 2026-05-16T01:44:00Z]``
      （5 day post-V083 stable，避 V083 attribution_chain_ok transition
      contamination per spec §12 R1 mitigation）

  Verdict matrix（per PA spec §4）：
    PASS：三窗 12h / 24h / 7d 全在 baseline 容差內，且無 trigger
    WARN：任一窗接近 trigger（80% threshold approach）
    FAIL：任一 T1/T2/T3/ZERO_FILLS trigger 觸發 → 寫 revert flag

  三窗 trigger thresholds（per PA spec §4）：
    T1 (12h fast-fail) :  avg_net < -10.0 bps 且 n >= 30 → CRITICAL
    T2 (24h primary)   :  avg_net < -5.0 bps  且 n >= 50 → HIGH
    T3 (7d cumulative) :  avg_net < baseline_avg - 3.0 bps 且 n >= 200 → MEDIUM
    ZERO_FILLS         :  age_h >= 24 且 24h n == 0 → HIGH（grid dormancy）

  Pre-deploy / pre-evaluable 行為：
    - engine_pid 不存（pre-deploy / maintenance）→ PASS（gate skipped）
    - engine_pid mtime < WP-03 deploy ts → PASS（gate not active yet）
    - age_h < 1.0 → PASS（sample 累積中，三窗尚不可評估）
    - baseline compute 失敗（pre-V083 historical 樣本不足）→ WARN（無法評估 drift）
    - ``learning.mlde_edge_training_rows`` 表缺 → WARN（V031 未 apply）

  Opt-in env：
    - ``OPENCLAW_WP03_DEPLOY_GATE_REQUIRED=1``：WARN 升 FAIL（strict mode）
    - ``OPENCLAW_WP03_DEPLOY_GATE_LOOKBACK_HOURS=N``：覆寫 T2 primary 24h window

  ADR-0020 manual-only revert principle：
    Auto revert flag SET ≠ auto revert action。Flag 寫入
    ``$OPENCLAW_DATA_DIR/wp03_revert_flag`` 為 advisory + audit trail；
    operator 看到 flag 後 manual decide path A (TOML flip) 或 path B
    (git revert + --rebuild) 或 dismiss flag。

  Sister checks：
    - ``[40] realized_edge_acceptance``：DB-truth post-fee 全策略 acceptance
    - ``[12] bb_breakout_post_deadlock_fix``：engine_pid mtime deploy proxy 同 pattern
    - ``[57] btc_lead_lag_panel_health``：W2 panel default-off opt-in pattern
    - ``[68] portfolio_resting_exposure``：per-engine snapshot + cap pattern

  對應 cron：``helper_scripts/db/passive_wait_healthcheck_cron.sh``
  （CLAUDE.md §七「被動等待 TODO 必附 healthcheck」強制配對）。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================
# §1 常數定義（PA spec §4 + §6.2 對齊）
# ============================================================

# WP-03 deploy timestamp UTC：v35 rebuild engine PID 69581（PA spec §2）
WP03_DEPLOY_TIMESTAMP_UTC: str = "2026-05-16T01:00:00Z"

# WP-03 monitored commit SHA：grid_helpers.rs L140 OU sigma residual fix
WP03_COMMIT_SHA: str = "ef6ea79f"

# Baseline 14d window（PA spec §12 R1 mitigation）：避 V083
# attribution_chain_ok transition window contamination，取 5 day
# post-V083 stable window
WP03_BASELINE_START_UTC: str = "2026-05-11T00:00:00Z"
WP03_BASELINE_END_UTC: str = "2026-05-16T01:44:00Z"

# T1 fast-fail 12h（PA spec §4.1）
T1_WINDOW_HOURS: int = 12
T1_AVG_NET_FLOOR_BPS: float = -10.0
T1_MIN_SAMPLE: int = 30

# T2 primary 24h（PA spec §4.1）
T2_WINDOW_HOURS_DEFAULT: int = 24
T2_AVG_NET_FLOOR_BPS: float = -5.0
T2_MIN_SAMPLE: int = 50

# T3 cumulative 7d（PA spec §4.1）
T3_WINDOW_DAYS: int = 7
T3_DRIFT_BPS: float = 3.0  # 絕對 drift below baseline_14d
T3_MIN_SAMPLE: int = 200

# Baseline 樣本 floor：低於此 baseline compute 視為失敗（per spec §6.3）
BASELINE_MIN_SAMPLE: int = 30

# Pre-evaluable 門檻：engine_pid mtime 距今 < 此小時數 → PASS-skip（spec §6.2）
PRE_EVALUABLE_AGE_HOURS: float = 1.0

# Severity 優先級（per spec §4.3）：T1 > T2 > T3 > ZERO
TRIGGER_SEVERITY_ORDER: tuple[str, ...] = (
    "T1_CRITICAL",
    "T2_HIGH",
    "ZERO_FILLS",
    "T3_MEDIUM",
)

# WARN approach threshold：trigger threshold × 此倍率 → WARN（per spec §6.2）
# 80% threshold approach：T1 -10 × 0.8 = -8 / T2 -5 × 0.8 = -4 / T3 drift 3 × 0.8 = 2.4
WARN_APPROACH_RATIO: float = 0.8


# ============================================================
# §2 helper
# ============================================================


def _enabled(name: str, default: str = "0") -> bool:
    """讀取 env flag（"1" 才視為啟用），其他值（含未設）回 False。"""
    return os.getenv(name, default).strip() == "1"


def _status_for(required: bool, base: str) -> str:
    """REQUIRED env 設定時把 WARN 升 FAIL；否則維持原 verdict。"""
    if base == "WARN" and required:
        return "FAIL"
    return base


def _t2_window_hours() -> int:
    """讀 env override，否則取 spec §4 default 24h；無效值 fallback default。"""
    raw = os.getenv("OPENCLAW_WP03_DEPLOY_GATE_LOOKBACK_HOURS", "").strip()
    if not raw:
        return T2_WINDOW_HOURS_DEFAULT
    try:
        v = int(raw)
        return v if v > 0 else T2_WINDOW_HOURS_DEFAULT
    except ValueError:
        return T2_WINDOW_HOURS_DEFAULT


def _data_dir() -> Path:
    """取 ``OPENCLAW_DATA_DIR``，默認 ``/tmp/openclaw``（與 Rust persistence.rs 對齊）。"""
    return Path(os.getenv("OPENCLAW_DATA_DIR", "/tmp/openclaw"))


def _revert_flag_path() -> Path:
    """Revert flag 持久化路徑（spec §6.2）。"""
    return _data_dir() / "wp03_revert_flag"


def _baseline_cache_path() -> Path:
    """Baseline 14d cache 持久化路徑（spec §6.2）。"""
    return _data_dir() / "wp03_baseline_cache.json"


def _parse_iso_utc(ts: str) -> datetime:
    """Parse ISO-8601 string 帶 Z suffix；fallback 不帶 tzinfo 視為 UTC。"""
    s = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _engine_deploy_state() -> tuple[str, str, datetime | None]:
    """讀 ``engine_pid`` mtime 判斷 deploy gate 是否可評估。

    Returns (state, msg, effective_deploy_ts)：
      state="PRE_DEPLOY"：engine_pid 缺 → PASS-skip
      state="STALE_DEPLOY"：engine_pid mtime < WP-03 deploy ts → PASS-skip
      state="PRE_EVALUABLE"：age_h < PRE_EVALUABLE_AGE_HOURS → PASS-skip
      state="EVALUABLE"：可評估，effective_deploy_ts = max(pid_mtime, deploy_ts)
    """
    pid_path = _data_dir() / "engine_pid"
    if not pid_path.exists():
        return (
            "PRE_DEPLOY",
            f"engine_pid 不存在 ({pid_path})，pre-deploy or maintenance — gate skipped",
            None,
        )

    try:
        pid_mtime_utc = datetime.fromtimestamp(pid_path.stat().st_mtime, tz=timezone.utc)
    except Exception as exc:  # noqa: BLE001 - filesystem stat fail-soft
        return (
            "PRE_DEPLOY",
            f"engine_pid stat 失敗: {type(exc).__name__}: {exc}",
            None,
        )

    deploy_ts = _parse_iso_utc(WP03_DEPLOY_TIMESTAMP_UTC)
    if pid_mtime_utc < deploy_ts:
        return (
            "STALE_DEPLOY",
            f"engine restart 在 WP-03 deploy 前 (pid_mtime={pid_mtime_utc.isoformat()}, "
            f"deploy_ts={WP03_DEPLOY_TIMESTAMP_UTC}) — gate not active yet",
            None,
        )

    effective_ts = max(pid_mtime_utc, deploy_ts)
    age_h = (datetime.now(tz=timezone.utc) - effective_ts).total_seconds() / 3600.0
    if age_h < PRE_EVALUABLE_AGE_HOURS:
        return (
            "PRE_EVALUABLE",
            f"deploy_age={age_h:.2f}h < {PRE_EVALUABLE_AGE_HOURS:.1f}h — "
            f"sample 累積中，三窗尚不可評估",
            effective_ts,
        )

    return ("EVALUABLE", "ok", effective_ts)


def _query_grid_window(
    cur,
    hours: int | None = None,
    days: int | None = None,
) -> dict[str, Any]:
    """Query ``learning.mlde_edge_training_rows`` for grid_trading window stats.

    必擇一指定 hours 或 days；雙指定以 hours 為準。
    Returns {"n": int, "avg_net_bps": float, "std": float, "diag": str}。
    PG anomaly 時 diag 帶錯誤；n=0 回 0.0。
    """
    if hours is not None:
        interval = f"{int(hours)} hours"
    elif days is not None:
        interval = f"{int(days)} days"
    else:  # defensive：caller 必擇一
        return {"n": 0, "avg_net_bps": 0.0, "std": 0.0, "diag": "no window specified"}

    try:
        # 參數化 interval 用 (%s::text || ' hours/days')::interval 避 SQL injection
        # 與 [40] 同 pattern (line 1162) - hardcoded interval 字串，符合既有設計
        cur.execute(
            """
            SELECT
              COUNT(*)::int,
              AVG(net_bps_after_fee)::float8,
              STDDEV(net_bps_after_fee)::float8
            FROM learning.mlde_edge_training_rows
            WHERE ts > now() - (%s::text)::interval
              AND engine_mode IN ('demo', 'live_demo')
              AND strategy_name = 'grid_trading'
              AND attribution_chain_ok = TRUE
              AND net_bps_after_fee IS NOT NULL
            """,
            (interval,),
        )
        row = cur.fetchone()
        n_raw = row[0] if row else 0
        avg_raw = row[1] if row else None
        std_raw = row[2] if row else None
    except Exception as exc:  # noqa: BLE001 - query fail-soft 回 0 with diag
        return {
            "n": 0,
            "avg_net_bps": 0.0,
            "std": 0.0,
            "diag": f"query failed: {type(exc).__name__}: {exc}",
        }

    return {
        "n": int(n_raw or 0),
        "avg_net_bps": float(avg_raw or 0.0),
        "std": float(std_raw or 0.0),
        "diag": "ok",
    }


def _load_or_compute_baseline(cur) -> tuple[dict[str, Any] | None, str]:
    """Load baseline cache JSON if exists, else compute from PG + persist.

    Returns (baseline_dict, diagnostic)：
      baseline=None：compute 失敗（樣本不足 / PG error）
      baseline={n, avg_net_bps, computed_at, window}：成功

    Cache invalidation：本 IMPL 不主動 invalidate；spec §6.3 設計為
    第一次 compute 後 reuse；後續若 baseline window 改變需手動刪 cache。
    """
    cache_path = _baseline_cache_path()
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            # 防禦：cache 須含 n + avg_net_bps；否則重算
            if (
                isinstance(data, dict)
                and isinstance(data.get("n"), int)
                and isinstance(data.get("avg_net_bps"), (int, float))
            ):
                return (data, "cached")
            # cache 結構不對 → fall through 重算
        except Exception as exc:  # noqa: BLE001 - cache read fail-soft 重算
            # 不 raise；繼續重算
            _ = exc

    # 第一次 compute：query PG baseline window
    try:
        # spec §3 / §12 R1：baseline window = [2026-05-11, 2026-05-16T01:44:00Z]
        # 5 day post-V083 stable，避 V083 attribution_chain_ok transition window
        # 參數化避 SQL injection（ts 比較走 PG::timestamptz cast）
        cur.execute(
            """
            SELECT
              COUNT(*)::int,
              AVG(net_bps_after_fee)::float8,
              STDDEV(net_bps_after_fee)::float8
            FROM learning.mlde_edge_training_rows
            WHERE ts >= %s::timestamptz
              AND ts <  %s::timestamptz
              AND engine_mode IN ('demo', 'live_demo')
              AND strategy_name = 'grid_trading'
              AND attribution_chain_ok = TRUE
              AND net_bps_after_fee IS NOT NULL
            """,
            (WP03_BASELINE_START_UTC, WP03_BASELINE_END_UTC),
        )
        row = cur.fetchone()
        n_raw = row[0] if row else 0
        avg_raw = row[1] if row else None
        std_raw = row[2] if row else None
    except Exception as exc:  # noqa: BLE001 - baseline query fail-soft
        return (None, f"baseline query failed: {type(exc).__name__}: {exc}")

    n = int(n_raw or 0)
    if n < BASELINE_MIN_SAMPLE:
        return (None, f"baseline 樣本不足 n={n} < {BASELINE_MIN_SAMPLE}")

    baseline = {
        "n": n,
        "avg_net_bps": float(avg_raw or 0.0),
        "std": float(std_raw or 0.0),
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "window_start": WP03_BASELINE_START_UTC,
        "window_end": WP03_BASELINE_END_UTC,
        "window_label": "5 day post-V083 stable (spec §3 + §12 R1)",
    }

    # Persist cache：寫失敗也不 raise（in-memory 仍可用本次評估）
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 - cache write fail-soft
        pass

    return (baseline, "computed")


def _write_revert_flag(
    triggers: list[tuple[str, str]],
    baseline: dict[str, Any] | None,
    age_h: float,
) -> str:
    """Persist revert flag to ``$OPENCLAW_DATA_DIR/wp03_revert_flag`` (spec §6.2)。

    Returns flag persist 結果 diagnostic（"written" / failure reason）。
    flag JSON 含 trigger_at + triggers detail + severity + commit SHA + deploy_ts，
    讓 operator + audit trail 可 reconstruct 為什麼 revert。
    """
    # severity = 第一個 trigger 的 name（caller 已 sort by TRIGGER_SEVERITY_ORDER）
    severity = triggers[0][0] if triggers else "UNKNOWN"

    flag_data = {
        "trigger_at": datetime.now(timezone.utc).isoformat(),
        "wp03_commit": WP03_COMMIT_SHA,
        "deploy_ts": WP03_DEPLOY_TIMESTAMP_UTC,
        "deploy_age_hours": round(age_h, 2),
        "severity": severity,
        "triggers": [{"name": t[0], "detail": t[1]} for t in triggers],
        "baseline": baseline,
    }
    flag_path = _revert_flag_path()
    try:
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        flag_path.write_text(json.dumps(flag_data, indent=2), encoding="utf-8")
        return "written"
    except Exception as exc:  # noqa: BLE001 - flag write fail-soft 不阻 verdict
        return f"flag write failed: {type(exc).__name__}: {exc}"


def _sort_triggers_by_severity(
    triggers: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """按 TRIGGER_SEVERITY_ORDER 排序 trigger list（最高 severity 在前）。"""
    order_map = {name: idx for idx, name in enumerate(TRIGGER_SEVERITY_ORDER)}
    return sorted(triggers, key=lambda t: order_map.get(t[0], 99))


# ============================================================
# §3 main check
# ============================================================


def check_69_wp03_ou_sigma_deploy_gate(cur) -> tuple[str, str]:
    """``[69]`` WP-03 OU sigma residual fix post-deploy 24h+ monitoring + revert flag.

    監測 grid_trading 在 WP-03 殘差 sigma 修正部署後的 ``avg_net_bps``。
    三窗 trigger（spec §4）：12h fast-fail (-10 bps) / 24h primary (-5 bps) /
    7d cumulative drift (baseline - 3 bps)；任一觸發即寫 revert flag +
    operator alert（ADR-0020 manual-only：flag set ≠ auto revert action）。

    Pre-deploy / pre-evaluable 路徑（spec §6.2）：
      engine_pid 不存 / mtime < deploy_ts / age < 1h → PASS-skip。
    Baseline cache（spec §6.3）：
      第一次跑 query 14d PG window → persist；後續 reuse cache。

    Returns (status, detail_msg)：
      PASS：三窗在 baseline 容差內，無 trigger
      WARN：任一窗接近 trigger（80% threshold）
      FAIL：任一 T1/T2/T3/ZERO_FILLS trigger 觸發 → 寫 revert flag
    """
    # Defensive rollback 保 cursor 在 sibling check 間乾淨
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 - defensive cleanup must not raise
        pass

    required = _enabled("OPENCLAW_WP03_DEPLOY_GATE_REQUIRED")
    t2_window_hours = _t2_window_hours()

    # Step 0: deploy proxy gate（spec §6.2 + [12] pattern）
    state, state_msg, effective_ts = _engine_deploy_state()
    if state != "EVALUABLE" or effective_ts is None:
        return ("PASS", f"[69] {state_msg}")

    age_h = (datetime.now(tz=timezone.utc) - effective_ts).total_seconds() / 3600.0

    # Step 1: 表存在性檢查 + baseline cache load or compute
    try:
        cur.execute("SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL")
        exists = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return (
            "WARN",
            f"[69] table existence check failed: {type(exc).__name__}: {exc} "
            f"(deploy_age={age_h:.1f}h)",
        )
    if not exists or not exists[0]:
        return (
            "WARN",
            f"[69] learning.mlde_edge_training_rows missing — V031 not applied "
            f"(deploy_age={age_h:.1f}h)",
        )

    baseline, baseline_diag = _load_or_compute_baseline(cur)
    if baseline is None:
        return (
            "WARN",
            f"[69] baseline compute failed — {baseline_diag} "
            f"(deploy_age={age_h:.1f}h) — cannot evaluate T3 drift",
        )

    # Step 2: 三窗 query（T1=12h / T2=24h or env override / T3=7d）
    t1 = _query_grid_window(cur, hours=T1_WINDOW_HOURS)
    t2 = _query_grid_window(cur, hours=t2_window_hours)
    t3 = _query_grid_window(cur, days=T3_WINDOW_DAYS)

    # 任一窗 query 失敗 → WARN（不 hard FAIL，避免 PG transient noise 誤觸 revert）
    query_errors: list[str] = []
    for label, win in (("T1", t1), ("T2", t2), ("T3", t3)):
        if win["diag"] != "ok":
            query_errors.append(f"{label}_query_fail: {win['diag']}")
    if query_errors:
        return (
            "WARN",
            f"[69] window query failures: {'; '.join(query_errors)} "
            f"(deploy_age={age_h:.1f}h, baseline={baseline['avg_net_bps']:.2f}bps "
            f"n={baseline['n']})",
        )

    # Step 3: trigger evaluation（spec §4.1）
    triggers: list[tuple[str, str]] = []

    # T1 fast-fail 12h
    if t1["n"] >= T1_MIN_SAMPLE and t1["avg_net_bps"] < T1_AVG_NET_FLOOR_BPS:
        triggers.append((
            "T1_CRITICAL",
            f"12h n={t1['n']} avg={t1['avg_net_bps']:.2f}bps < {T1_AVG_NET_FLOOR_BPS:.1f}",
        ))

    # T2 primary 24h（或 env override window）
    if t2["n"] >= T2_MIN_SAMPLE and t2["avg_net_bps"] < T2_AVG_NET_FLOOR_BPS:
        triggers.append((
            "T2_HIGH",
            f"{t2_window_hours}h n={t2['n']} avg={t2['avg_net_bps']:.2f}bps "
            f"< {T2_AVG_NET_FLOOR_BPS:.1f}",
        ))

    # T3 cumulative drift 7d
    t3_floor = baseline["avg_net_bps"] - T3_DRIFT_BPS
    if t3["n"] >= T3_MIN_SAMPLE and t3["avg_net_bps"] < t3_floor:
        triggers.append((
            "T3_MEDIUM",
            f"7d n={t3['n']} avg={t3['avg_net_bps']:.2f}bps drift > {T3_DRIFT_BPS:.1f}bps "
            f"below baseline {baseline['avg_net_bps']:.2f}bps",
        ))

    # ZERO_FILLS：age_h >= 24h 且 T1 12h + T2 (24h 或 env override) 都 n == 0（spec §4.2）
    # 嚴重副作用 — grid 全 dormancy 可能是 WP-03 root cause（sigma 過收）
    # 雙窗 secondary guard（E2 Round 1 MEDIUM-1 fix）：避免當 LOOKBACK_HOURS env override
    # 使 t2 window > engine age 時 t2["n"]=0 純粹是 query window 超過 engine age 而非
    # 真 dormancy 的 false-positive；T1 12h（hardcoded floor）+ T2 都 0 fills 才算真 dormancy
    if age_h >= T2_WINDOW_HOURS_DEFAULT and t1["n"] == 0 and t2["n"] == 0:
        triggers.append((
            "ZERO_FILLS",
            f"12h n=0 + {t2_window_hours}h n=0 grid_trading — possible strategy dormancy from WP-03",
        ))

    # Base evidence message（永遠包含）
    base_msg = (
        f"deploy_age={age_h:.1f}h, baseline_14d={baseline['avg_net_bps']:.2f}bps "
        f"(n={baseline['n']}, {baseline_diag}), "
        f"12h n={t1['n']} avg={t1['avg_net_bps']:.2f}bps, "
        f"{t2_window_hours}h n={t2['n']} avg={t2['avg_net_bps']:.2f}bps, "
        f"7d n={t3['n']} avg={t3['avg_net_bps']:.2f}bps "
        f"(t3_floor={t3_floor:.2f}bps)"
    )

    # Step 4: FAIL 路徑 — trigger 觸發 → 寫 revert flag
    if triggers:
        sorted_triggers = _sort_triggers_by_severity(triggers)
        flag_diag = _write_revert_flag(sorted_triggers, baseline, age_h)
        trigger_summary = "; ".join(f"{t[0]}({t[1]})" for t in sorted_triggers)
        return (
            "FAIL",
            f"[69] WP-03 deploy-gate FAIL revert_recommended=true — "
            f"triggers: {trigger_summary} — flag {flag_diag} ({_revert_flag_path()}) "
            f"— {base_msg}",
        )

    # Step 5: WARN 路徑 — 80% threshold approach（spec §6.2）
    warnings: list[str] = []
    # 注意：approach 是 threshold 「更接近 0」一側 — T1 -10 × 0.8 = -8 bps（i.e. avg < -8 是 approaching）
    # 對負閾值，approach floor 比 trigger floor 更接近 0
    if t1["n"] >= T1_MIN_SAMPLE and t1["avg_net_bps"] < T1_AVG_NET_FLOOR_BPS * WARN_APPROACH_RATIO:
        # 已過 approach 但未過 trigger
        warnings.append(
            f"12h avg {t1['avg_net_bps']:.2f}bps approaching T1 "
            f"(floor {T1_AVG_NET_FLOOR_BPS * WARN_APPROACH_RATIO:.1f}bps)"
        )
    if t2["n"] >= T2_MIN_SAMPLE and t2["avg_net_bps"] < T2_AVG_NET_FLOOR_BPS * WARN_APPROACH_RATIO:
        warnings.append(
            f"{t2_window_hours}h avg {t2['avg_net_bps']:.2f}bps approaching T2 "
            f"(floor {T2_AVG_NET_FLOOR_BPS * WARN_APPROACH_RATIO:.1f}bps)"
        )
    # T3 approach：baseline - drift × 0.8（drift 是正數，baseline - 2.4 比 baseline - 3 寬一點）
    t3_warn_floor = baseline["avg_net_bps"] - T3_DRIFT_BPS * WARN_APPROACH_RATIO
    if t3["n"] >= T3_MIN_SAMPLE and t3["avg_net_bps"] < t3_warn_floor:
        warnings.append(
            f"7d cumulative drift approaching T3 "
            f"(avg {t3['avg_net_bps']:.2f}bps < {t3_warn_floor:.2f}bps, "
            f"baseline {baseline['avg_net_bps']:.2f}bps)"
        )

    if warnings:
        verdict = _status_for(required, "WARN")
        if verdict == "FAIL":
            # REQUIRED env 升 FAIL：仍視為觸發 revert（保守 strict mode）
            # 但本路徑 warnings approach 而非 hard trigger，不寫 revert flag
            # （flag 是 hard trigger 的 advisory，approach 升 FAIL 純 escalation）
            # E2 Round 1 LOW-1 fix：msg 明寫 revert_recommended=false hint，讓 operator
            # / GUI 看到 FAIL 但 wp03_revert_flag 不存在時不會困惑（與 Step 4 hard FAIL
            # 的 revert_recommended=true 對稱）
            return (
                "FAIL",
                f"[69] WP-03 deploy-gate FAIL (REQUIRED escalation) "
                f"revert_recommended=false (approach_escalation, no flag written) — "
                f"approaching triggers: {'; '.join(warnings)} — {base_msg}",
            )
        return (
            "WARN",
            f"[69] WP-03 deploy-gate approaching trigger — "
            f"{'; '.join(warnings)} — {base_msg}",
        )

    # PASS 路徑
    return (
        "PASS",
        f"[69] WP-03 deploy-gate within tolerance — {base_msg}",
    )
