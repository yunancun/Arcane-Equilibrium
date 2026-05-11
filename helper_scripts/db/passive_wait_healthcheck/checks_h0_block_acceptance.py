"""LG-1 H0 Blocking Production Caller acceptance healthcheck `[59]`.
LG-1 H0 阻擋生產調用驗收 healthcheck `[59]`。

MODULE_NOTE (中):
  Per PA tech plan `2026-05-11--lg_2_3_4_design_plan.md` §1.4 T2
  + §1.5 風險表 Mitigation：「H0 block 統計只有 stats clone（canary record
  帶），無法跨 process 持久化」→ 本哨兵讀 `pipeline_snapshot_{engine}.json`
  的 `h0_gate_stats`（Rust ``GateStats`` IPC 落盤，每 ~30s 一次）對 join
  `trading.fills` 推斷 H0 hard-block 失效。

  Authoritative data source:
    1. ``$OPENCLAW_DATA_DIR/pipeline_snapshot_{demo,live_demo}.json`` (filesystem).
       `h0_gate_stats` JSON shape (per Rust `openclaw_core::h0_gate::GateStats`):
         total_checks       : u64  累計檢查次數
         total_allowed      : u64  累計通過數
         blocked_freshness  : u64  鮮度阻擋
         blocked_health     : u64  系統健康阻擋
         blocked_eligibility: u64  可交易性阻擋
         blocked_envelope   : u64  風控封套阻擋
         blocked_cooldown   : u64  冷卻期阻擋
         shadow_would_block : u64  shadow 模式本應阻擋（未真阻）
         max_latency_us     : u64  單次最大延遲（微秒）
         total_latency_us   : u64  累計延遲
       `risk_manager_config.runtime.h0_shadow_mode` 為 hard-block toggle
       （`false` = hard-block；`true` = shadow only）。
    2. ``trading.fills`` PG table（cross-validation）。

  H0 block 在 step_0_5_h0_gate 早退（`ControlFlow::Break`）— 該 tick **不**
  進 IntentProcessor / Guardian，故 PG 端**沒有 risk_verdicts row**。
  哨兵改以「snapshot 顯示 hard-block 比例高 + 同期 entry fills 非零」推斷
  block 失效，並對 demo + live_demo 兩 engine 各跑一遍。

  PA §1.4 acceptance criteria (4 sub-checks):
    (1) PASS: hard-block events > 0 AND fills_during_block = 0（理論值）
    (2) WARN: stats insufficient (n < threshold)
    (3) WARN: shadow_mode=true（demo/live_demo 預設 hard-block，shadow=true 偏移）
    (4) FAIL: H0 block 期間有 entry fill 流出（block 失效）

  Env config:
    OPENCLAW_H0_BLOCK_HEALTH_REQUIRED=1 → WARN 升 FAIL
    OPENCLAW_H0_BLOCK_HEALTH_MIN_CHECKS=100 → total_checks 低樣本門檻
    OPENCLAW_H0_BLOCK_HEALTH_ENGINES="demo,live_demo" → 監測 engine 列表
    OPENCLAW_DATA_DIR → snapshot 檔目錄（與 ipc_state_reader.py 一致）

  Verdict format (operator-readable, RFC §2.4 風格):
    [59] h0_block_acceptance mode=<engine_list> verdict=<status>
        demo: shadow=<bool> blocks=<int> checks=<int> entry_fills_1h=<int> ...
        live_demo: ...

  非職責邊界:
    - 本哨兵 read-only filesystem + PG，0 IPC roundtrip
    - 不改 H0 production code（T1 + T3 領域）
    - 不寫新 PG 表（per PA §1.5 「不需新增 PG 表」）
    - hot path 影響 = 0（觀察期工件）
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 常量區 / Constants
# ---------------------------------------------------------------------------

# 預設監測的 engine_mode 列表。paper 排除，因為 paper TOML 預設 shadow_mode=true
# 且 paper pipeline 預設 disabled (OPENCLAW_ENABLE_PAPER != 1)。live 排除，因
# Mainnet 不在當前作用範圍（OPENCLAW_ALLOW_MAINNET=0 by design）。
DEFAULT_MONITORED_ENGINES: tuple[str, ...] = ("demo", "live_demo")

# Snapshot 新鮮度門檻（秒）— ipc_state_reader 用 60s STALENESS_THRESHOLD；
# 我們放寬到 300s 作為「最近 5 分鐘有寫入」哨兵邊界，避免 transient stale 誤報。
SNAPSHOT_FRESH_MAX_SECONDS: float = 300.0

# 低樣本門檻（H0 check 累計次數）。預設 100 次：tick rate ~1 tick/s 對應
# ~100 秒；過去 ~30s engine restart 後 stats 可能 < 100，避免 false WARN。
DEFAULT_MIN_TOTAL_CHECKS: int = 100

# Block leakage 偵測時窗（小時）。1h 內 entry fills 用 trading.fills 跨檢
# h0_gate_stats 是 cumulative since engine boot，所以「block ratio dominant」
# 是大概念；entry fills 是 absolute 數字（>0 即可疑）。
FILL_LEAKAGE_WINDOW_HOURS: int = 1

# Block leakage 比例門檻：blocked / total_checks > 0.5 視為「block dominant」。
# 但這只是 hint，真正 FAIL 條件是 dominant 期間還有 entry fills 流出。
BLOCK_DOMINANT_RATIO: float = 0.5


# ---------------------------------------------------------------------------
# Helpers / 輔助函數
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    """讀 OPENCLAW_DATA_DIR 環境變數，fallback 到 /tmp/openclaw（Linux 預設）。
    與 ``ipc_state_reader.py`` 一致。
    """
    return Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))


def _monitored_engines() -> tuple[str, ...]:
    """讀 OPENCLAW_H0_BLOCK_HEALTH_ENGINES 環境變數（逗號分隔），fallback 到
    ``DEFAULT_MONITORED_ENGINES``。"""
    raw = os.environ.get(
        "OPENCLAW_H0_BLOCK_HEALTH_ENGINES", ",".join(DEFAULT_MONITORED_ENGINES)
    )
    parsed = tuple(part.strip() for part in raw.split(",") if part.strip())
    return parsed or DEFAULT_MONITORED_ENGINES


def _min_total_checks() -> int:
    """讀 OPENCLAW_H0_BLOCK_HEALTH_MIN_CHECKS 環境變數，fallback 到
    ``DEFAULT_MIN_TOTAL_CHECKS``。非整數 / <=0 即用 default。"""
    raw = os.environ.get("OPENCLAW_H0_BLOCK_HEALTH_MIN_CHECKS")
    if raw is None:
        return DEFAULT_MIN_TOTAL_CHECKS
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MIN_TOTAL_CHECKS
    if val <= 0:
        return DEFAULT_MIN_TOTAL_CHECKS
    return val


def _required() -> bool:
    """是否 escalate WARN → FAIL（OPENCLAW_H0_BLOCK_HEALTH_REQUIRED=1）。"""
    return os.environ.get("OPENCLAW_H0_BLOCK_HEALTH_REQUIRED", "").strip() == "1"


def _status_or_required(base: str) -> str:
    """若 REQUIRED env 設則 WARN 升 FAIL；其他狀態（PASS / FAIL）原樣。"""
    if base == "WARN" and _required():
        return "FAIL"
    return base


def _read_snapshot(engine: str) -> tuple[dict[str, Any] | None, float | None, str]:
    """讀 `pipeline_snapshot_{engine}.json`，回 `(data, age_seconds, diag)`。

    Args:
        engine: ``demo`` / ``live_demo`` / ``paper`` / ``live``。

    Returns:
        `(data, age_seconds, diag)`：
          - `data` 為 None 即讀檔失敗（路徑詳細 diag）；其他為 dict。
          - `age_seconds` 為 None 即無 mtime 可取（FileNotFoundError）；其他
            為 `time.time() - st_mtime`，可能 < 0 若時鐘漂移（一律 fail-soft
            取 max(0, ...)）。
          - `diag` 為 human-readable 文字，提供 fail-soft 場景的 operator hint。
    """
    path = _data_dir() / f"pipeline_snapshot_{engine}.json"
    try:
        stat_result = path.stat()
    except FileNotFoundError:
        return (None, None, f"snapshot file not found: {path}")
    except OSError as exc:
        return (None, None, f"snapshot stat error ({type(exc).__name__}): {path}")
    age = max(0.0, time.time() - stat_result.st_mtime)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return (None, age, f"snapshot read/parse error ({type(exc).__name__}): {path}")
    if not isinstance(data, dict):
        return (None, age, f"snapshot root not a dict: {path}")
    return (data, age, "ok")


def _extract_h0_stats(snap: dict[str, Any]) -> tuple[dict[str, int], str]:
    """從 snapshot dict 抽出 `h0_gate_stats`，缺欄位以 0 fill。

    Returns:
        `(stats_dict, diag)`：stats_dict 永遠是 dict（缺 key 填 0）。
        diag 為 human-readable 字串說明來源狀態。
    """
    raw_stats = snap.get("h0_gate_stats")
    if not isinstance(raw_stats, dict):
        return (
            {
                "total_checks": 0,
                "total_allowed": 0,
                "blocked_freshness": 0,
                "blocked_health": 0,
                "blocked_eligibility": 0,
                "blocked_envelope": 0,
                "blocked_cooldown": 0,
                "shadow_would_block": 0,
                "max_latency_us": 0,
                "total_latency_us": 0,
            },
            "h0_gate_stats absent or non-dict",
        )
    fields = (
        "total_checks",
        "total_allowed",
        "blocked_freshness",
        "blocked_health",
        "blocked_eligibility",
        "blocked_envelope",
        "blocked_cooldown",
        "shadow_would_block",
        "max_latency_us",
        "total_latency_us",
    )
    extracted: dict[str, int] = {}
    for field in fields:
        val = raw_stats.get(field, 0)
        try:
            extracted[field] = int(val)
        except (TypeError, ValueError):
            extracted[field] = 0
    return (extracted, "ok")


def _extract_shadow_mode(snap: dict[str, Any]) -> tuple[bool | None, str]:
    """從 snapshot 抽 `risk_manager_config.runtime.h0_shadow_mode`。
    None 表示無法判讀（snapshot 不含此欄位）。"""
    rmc = snap.get("risk_manager_config")
    if not isinstance(rmc, dict):
        return (None, "risk_manager_config absent")
    runtime = rmc.get("runtime")
    if not isinstance(runtime, dict):
        return (None, "risk_manager_config.runtime absent")
    val = runtime.get("h0_shadow_mode")
    if not isinstance(val, bool):
        return (None, f"h0_shadow_mode non-bool: {val!r}")
    return (val, "ok")


def _total_blocked(stats: dict[str, int]) -> int:
    """Rust ``GateStats::total_blocked`` 同邏輯。"""
    return (
        stats.get("blocked_freshness", 0)
        + stats.get("blocked_health", 0)
        + stats.get("blocked_eligibility", 0)
        + stats.get("blocked_envelope", 0)
        + stats.get("blocked_cooldown", 0)
    )


def _query_entry_fills(cur, engine: str, window_hours: int) -> tuple[int, str]:
    """查指定 engine_mode 在過去 `window_hours` 小時內的「入場 fill」數。

    Entry fill discriminator（鏡 ``checks_execution.py`` line 1015-1017
    既有 pattern）:
        strategy_name NOT LIKE 'risk_close:%' AND
        strategy_name NOT LIKE 'strategy_close:%'

    Returns:
        `(count, diag)`：count 為 entry fill 數；diag 為「ok」/錯誤類型。
    """
    try:
        cur.execute(
            """
            SELECT COUNT(*)::int
            FROM trading.fills
            WHERE engine_mode = %s
              AND ts > now() - (%s || ' hours')::interval
              AND strategy_name IS NOT NULL
              AND strategy_name NOT LIKE 'risk_close:%%'
              AND strategy_name NOT LIKE 'strategy_close:%%'
            """,
            (engine, str(window_hours)),
        )
        row = cur.fetchone()
        if not row:
            return (0, "ok")
        return (int(row[0] or 0), "ok")
    except Exception as exc:  # noqa: BLE001 - passive sentinel must fail-soft
        return (-1, f"query error ({type(exc).__name__})")


# ---------------------------------------------------------------------------
# `[59]` h0_block_acceptance — LG-1 RFC T2 healthcheck.
# `[59]` h0_block_acceptance — LG-1 RFC T2 healthcheck。
# ---------------------------------------------------------------------------

def check_59_h0_block_acceptance(cur) -> tuple[str, str]:
    """[59] LG-1 H0 hard-block production caller acceptance sentinel.

    [59] LG-1 H0 hard-block 生產調用驗收哨兵。

    Per-engine 4 sub-check 結合 final verdict:

      Per-engine sub-check（demo / live_demo 各跑）：
        A. Snapshot 存在 + fresh (< 5min) → 否則 WARN_NO_SNAPSHOT (skip engine)
        B. shadow_mode（讀 ``risk_manager_config.runtime.h0_shadow_mode``）—
           demo/live_demo 預設 false (hard-block)。true 即 WARN_SHADOW_MODE。
        C. Stats sample size (total_checks >= MIN_TOTAL_CHECKS) → 否則
           WARN_LOW_SAMPLE。
        D. Block leakage: blocked dominant (total_blocked/total_checks >
           BLOCK_DOMINANT_RATIO) 且 entry_fills_1h > 0 → FAIL_BLOCK_LEAKAGE。

      Final verdict aggregation:
        - 全 PASS → PASS
        - 任一 FAIL → FAIL
        - 任一 WARN → WARN（OPENCLAW_H0_BLOCK_HEALTH_REQUIRED=1 升 FAIL）

    Defensive rollback at top（避免 25P02 chaining）。

    Args:
        cur: psycopg2 cursor（DB-bound）。

    Returns:
        `(status, msg)` tuple；msg 含 per-engine 摘要供 operator triage。
    """
    # 防禦性 rollback：清掉先前 abort 的交易避免 25P02 鏈式錯誤。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 - defensive only
        pass

    # Linux PG 必有 trading.fills（V003 land 多月）。若缺即 V003 未 apply，
    # fail-closed FAIL。
    try:
        cur.execute("SELECT to_regclass('trading.fills') IS NOT NULL")
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 - passive sentinel
        return ("FAIL", f"[59] trading.fills existence check failed: {exc}")
    if not exists_row or not exists_row[0]:
        return (
            "FAIL",
            "[59] trading.fills missing — V003 not applied; H0 block "
            "acceptance cannot be verified",
        )

    engines = _monitored_engines()
    min_checks = _min_total_checks()
    per_engine_msgs: list[str] = []
    worst: str = "PASS"
    fail_reasons: list[str] = []
    warn_reasons: list[str] = []

    for engine in engines:
        # Sub-check A: snapshot freshness
        # 子檢查 A：snapshot 新鮮度
        snap, age_s, snap_diag = _read_snapshot(engine)
        if snap is None or age_s is None or age_s > SNAPSHOT_FRESH_MAX_SECONDS:
            # snapshot 缺或過期：WARN（不 hard FAIL，避免 Mac dev / engine
            # cold-start false-FAIL；PA tech plan §1.5 mitigation 接受
            # snapshot-not-yet-written 情境）。
            age_repr = (
                f"{int(age_s)}s" if age_s is not None else "unavailable"
            )
            per_engine_msgs.append(
                f"{engine}: WARN_NO_SNAPSHOT (age={age_repr} diag={snap_diag})"
            )
            warn_reasons.append(f"{engine}: snapshot stale/missing ({snap_diag})")
            if worst == "PASS":
                worst = "WARN"
            continue

        # Sub-check B: shadow_mode
        # 子檢查 B：shadow_mode 旗標
        shadow_mode, shadow_diag = _extract_shadow_mode(snap)

        # Sub-check C: stats
        # 子檢查 C：H0 stats 樣本量
        stats, _stats_diag = _extract_h0_stats(snap)
        total_checks = stats["total_checks"]
        total_blocked = _total_blocked(stats)
        shadow_would_block = stats["shadow_would_block"]

        # Sub-check D: entry fills 期內
        # 子檢查 D：1h 內 entry fills 跨檢
        entry_fills, fill_diag = _query_entry_fills(
            cur, engine, FILL_LEAKAGE_WINDOW_HOURS
        )

        # 構造 per-engine 摘要
        # Build per-engine summary
        engine_summary_core = (
            f"{engine}: shadow={shadow_mode!r} "
            f"checks={total_checks} blocked={total_blocked} "
            f"shadow_would_block={shadow_would_block} "
            f"entry_fills_1h={entry_fills if entry_fills >= 0 else 'err'} "
            f"snapshot_age={int(age_s)}s"
        )

        # PG 查詢失敗 → WARN（不 FAIL，避免 PG transient 把整 sentinel 紅）
        if entry_fills < 0:
            per_engine_msgs.append(
                f"{engine_summary_core} verdict=WARN_QUERY_ERROR ({fill_diag})"
            )
            warn_reasons.append(f"{engine}: fill query failed ({fill_diag})")
            if worst == "PASS":
                worst = "WARN"
            continue

        # Verdict 級聯（嚴格 → 寬鬆）：
        # 1. shadow_mode=true → WARN_SHADOW_MODE（demo/live_demo by-design
        #    hard-block；shadow=true 表示偏離預期）
        # 2. total_checks < min → WARN_LOW_SAMPLE
        # 3. block dominant + entry_fills > 0 → FAIL_BLOCK_LEAKAGE
        # 4. 其他 → PASS
        engine_verdict = "PASS"
        if shadow_mode is True:
            engine_verdict = "WARN_SHADOW_MODE"
            warn_reasons.append(
                f"{engine}: shadow_mode=true (demo/live_demo by-design hard-block)"
            )
            if worst == "PASS":
                worst = "WARN"
        elif shadow_mode is None:
            engine_verdict = "WARN_NO_SHADOW_FLAG"
            warn_reasons.append(
                f"{engine}: shadow_mode unreadable ({shadow_diag})"
            )
            if worst == "PASS":
                worst = "WARN"
        elif total_checks < min_checks:
            engine_verdict = f"WARN_LOW_SAMPLE(n={total_checks},need={min_checks})"
            warn_reasons.append(
                f"{engine}: total_checks={total_checks} < min={min_checks}"
            )
            if worst == "PASS":
                worst = "WARN"
        else:
            # 計算 block ratio
            # Compute block ratio
            block_ratio = total_blocked / total_checks if total_checks > 0 else 0.0
            if block_ratio > BLOCK_DOMINANT_RATIO and entry_fills > 0:
                # H0 block dominant 但 entry fills 仍流出 → block 失效（FAIL）
                engine_verdict = (
                    f"FAIL_BLOCK_LEAKAGE(ratio={block_ratio:.2f},"
                    f"fills={entry_fills})"
                )
                fail_reasons.append(
                    f"{engine}: H0 block dominant ({total_blocked}/{total_checks}={block_ratio:.2%}) "
                    f"but {entry_fills} entry fill(s) in last "
                    f"{FILL_LEAKAGE_WINDOW_HOURS}h — block invariant violated"
                )
                worst = "FAIL"
            elif total_blocked == 0 and entry_fills == 0:
                # H0 從未阻擋 + 無 entry fills → 可能 pipeline 完全靜默
                # Snapshot 已 fresh 但 stats 沒動 → 引擎可能未真實 process tick
                engine_verdict = "WARN_PIPELINE_QUIET(0blocks,0fills)"
                warn_reasons.append(
                    f"{engine}: 0 blocked + 0 entry_fills despite fresh snapshot "
                    f"(checks={total_checks}) — pipeline may be quiet"
                )
                if worst == "PASS":
                    worst = "WARN"

        per_engine_msgs.append(f"{engine_summary_core} verdict={engine_verdict}")

    # Aggregate final verdict
    # 聚合最終 verdict
    base_msg = (
        f"[59] h0_block_acceptance engines={','.join(engines)} "
        f"min_checks={min_checks} window={FILL_LEAKAGE_WINDOW_HOURS}h; "
        + "; ".join(per_engine_msgs)
    )

    final_status = _status_or_required(worst)
    if final_status == "FAIL":
        # FAIL message：fail_reasons 為主，warn_reasons 為輔（context only）
        # FAIL 訊息以 fail_reasons 為主
        reasons = "; ".join(fail_reasons) if fail_reasons else "; ".join(warn_reasons)
        return ("FAIL", f"{base_msg} — {reasons}")
    if final_status == "WARN":
        reasons = "; ".join(warn_reasons) if warn_reasons else "n/a"
        return ("WARN", f"{base_msg} — {reasons}")
    return ("PASS", f"{base_msg} — H0 hard-block acceptance healthy")
