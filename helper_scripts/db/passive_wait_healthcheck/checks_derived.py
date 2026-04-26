"""Derived / observability healthchecks.
衍生 / 觀察性 healthcheck。

MODULE_NOTE (EN): Extracted from the original ``passive_wait_healthcheck.py``:
  * [Xa] check_leader_election_health        (lines 994-1127)
  * [Xb] check_pipeline_triangulation        (lines 1130-1296)
  * [18] check_disabled_strategy_inventory   (lines 661-720)
  * [19] check_observer_pipeline_alive       (added 2026-04-26 by
    OBSERVER-PIPELINE-POST-F42FACE-CLEANUP — silent-fail guard for the
    bybit observer cron cycle that ran 100%-fail for 3 days while a
    noise wrapper swallowed every FAIL.)

These four are derivative / cross-cutting checks that don't fit the
direct fill-flow / risk-layer / strategy-flow axes. [Xa] watches the
edge-scheduler leader-lock; [Xb] cross-validates the fills/labels/intents
scale ratios; [18] surfaces TOML-disabled strategies for §三 drift
defense; [19] proves the bybit observer cron pipeline is actually
producing fresh, non-error JSON (the kind of guard CLAUDE.md §七
"被動等待 TODO 必附 healthcheck" mandates after 2026-04-22 silent-fail
postmortems).

SQL strings, exit-code semantics, output formatting are byte-identical
to the pre-split version (except for the new [19] which is purely
filesystem-driven — no DB cursor, no IPC).

MODULE_NOTE (中): 衍生 / 跨層觀察性 check：[Xa] 看 edge-scheduler leader-lock，
[Xb] 三角驗證 fills/labels/intents 比例，[18] 列 TOML disabled 策略以防
CLAUDE.md §三 drift，[19] 看 bybit observer cron cycle 是否實際產出
新鮮且無錯的 JSON（OBSERVER-PIPELINE-POST-F42FACE-CLEANUP 2026-04-26 加
— cron 連續 3 天 100% fail 被 noise wrapper 吞掉的反面教材）。
SQL / exit code / 輸出格式與拆分前 byte-identical（[19] 為新增、純檔案
系統 check，無 DB cursor / IPC）。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def check_disabled_strategy_inventory() -> tuple[str, str]:
    """[18] disabled-strategy inventory — pure observability, never FAIL.

    G2-06 (2026-04-26): CLAUDE.md §三 drift防線 (G6-04). When a strategy is
    disabled at TOML level (`active=false`), we want it to remain visible
    in healthcheck output so future audits can't "forget" disabled
    strategies. This check parses `settings/strategy_params_demo.toml`,
    walks every `[<strategy>]` section, and lists those with
    ``active=false``. Always returns PASS — purely informational.

    Phase 1a / first-run note: when no strategies are disabled, the check
    reports "no disabled strategies" + PASS (still useful as a
    structural check that the TOML parse works at all).

    [18] disabled 策略 inventory — 純觀察性，永遠不 FAIL。
    G2-06（2026-04-26）：CLAUDE.md §三 drift 防線（G6-04）。策略 TOML
    disable（active=false）時須在 healthcheck 輸出可見，避免未來 audit
    「忘了還有這策略」誤撿。讀 demo TOML，列出 active=false 策略。
    永遠 PASS（純記錄性）。
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        return ("PASS", "tomllib unavailable (Python <3.11?), inventory unavailable")

    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    toml_path = base / "settings" / "strategy_params_demo.toml"

    if not toml_path.exists():
        return ("PASS", f"strategy_params_demo.toml not found at {toml_path} (skip)")

    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        return ("PASS", f"TOML parse error (skip): {e}")

    disabled: list[str] = []
    active: list[str] = []
    for name, section in data.items():
        if not isinstance(section, dict):
            continue
        val = section.get("active")
        if isinstance(val, bool):
            if val is False:
                disabled.append(name)
            else:
                active.append(name)

    if not disabled:
        return (
            "PASS",
            f"no disabled strategies (active count={len(active)}: {', '.join(sorted(active)) or '(none)'})",
        )

    return (
        "PASS",
        f"disabled strategies: {', '.join(sorted(disabled))} "
        f"(active count={len(active)}: {', '.join(sorted(active)) or '(none)'})",
    )


def check_leader_election_health() -> tuple[str, str]:
    """[Xa] G6-01 (2026-04-24): edge_estimator_scheduler leader-lock health.

    The QA audit (§2.2 #5) flagged a blind spot: check [7] catches
    `edge_estimates.json` staleness but **cannot distinguish**:
      A. scheduler died entirely → eventually [7] FAILs after 90 min, AND
      B. the leader-lock holder PID died but the lock file survives → no
         worker re-elects itself → estimator silently dormant; [7] catches
         this only after 90 min with no narrative help on root cause; AND
      C. lock holder is alive but scheduler thread crashed → [7] eventually
         FAILs after 90 min but operator has no fast triage signal.

    EDGE-SCHEDULER-LEADER-1 (2026-04-23 commit `f32629c`) writes the leader
    PID into `$OPENCLAW_DATA_DIR/edge_scheduler.leader.lock` for operator
    debug (`cat <lock>` → leader PID). This check inspects:
      1. Lock file existence + mtime (stale = >24h since last leader touch).
      2. Lock holder PID liveness (`/proc/<pid>` on Linux; `ps` fallback).
      3. Cross-correlate with [7] freshness — if [7] failing AND lock dead
         → the diagnosis is "leader election broken" not "scheduler busy".

    Three-state output:
      - FAIL: lock missing entirely, or lock present but PID dead AND age > 1h
        (operator action: `rm <lock>`; restart api process to re-elect).
      - WARN: lock age >12h (stale-lock drift; restart at next maintenance).
      - PASS: lock present, PID alive, age <12h.

    Cross-platform: `/proc/<pid>` on Linux is the cheap path; macOS / fallback
    uses `os.kill(pid, 0)` which raises if PID dead. Both work without root.
    Fail-soft: any check-internal IO error → WARN (never FAIL on this check
    alone; we don't want a healthcheck plumbing bug to mask the real signal).

    [Xa] G6-01（2026-04-24）：edge_estimator_scheduler leader-lock 健康檢查。
    QA audit §2.2 #5 指 check [7] 抓不到「leader 死掉但 lock 沒清」的 silent
    death（worker 不重選舉，estimator 靜默 dormant），且 90 min 後 [7] 才
    亮紅，operator 缺快速 triage 信號。EDGE-SCHEDULER-LEADER-1（2026-04-23
    commit `f32629c`）把 leader PID 寫入 $OPENCLAW_DATA_DIR/
    edge_scheduler.leader.lock 供 operator `cat` debug。本 check：
      1. 檢查 lock 檔存在 + mtime（>24h 視為 stale）
      2. 檢查 lock 內 PID 是否存活（Linux 走 /proc，macOS fallback os.kill(0)）
      3. 與 [7] 互補：[7] FAIL + 本 check FAIL → 「leader election 壞」而非
         「scheduler 在跑」
    三態：FAIL（lock 缺 / PID 死 + age>1h）、WARN（age>12h）、PASS。
    跨平台：/proc 走 Linux 快路徑，os.kill(pid, 0) 雙平台 fallback。
    Fail-soft：本 check 內部 IO 錯一律 WARN，避免 plumbing bug 遮掩真信號。
    """
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    lock_path = data_dir / "edge_scheduler.leader.lock"

    if not lock_path.exists():
        # Distinguish "scheduler never ran" (lock never created) from
        # "scheduler ran then lock got rm'd" — both register as missing
        # and both warrant FAIL because no leader is currently holding it.
        # OPENCLAW_SCHEDULER_LEADER=0 (operator disable) is the only valid
        # path to no-lock + no-FAIL — we annotate that explicitly.
        # 區分「scheduler 從未跑」vs「跑後 lock 被刪」— 兩者都 FAIL，因為當前
        # 無 leader 持鎖。OPENCLAW_SCHEDULER_LEADER=0（operator 手動停用）是
        # 唯一合理的「無 lock 不 FAIL」路徑，我們明確標注。
        if os.environ.get("OPENCLAW_SCHEDULER_LEADER") == "0":
            return ("PASS", f"leader lock absent at {lock_path} — "
                    "OPENCLAW_SCHEDULER_LEADER=0 (operator disabled, expected)")
        return ("FAIL", f"leader lock missing at {lock_path} — "
                "edge_estimator_scheduler never elected (uvicorn dead? G1-01)")

    # Read lock metadata. mtime stays current as long as the leader process
    # holds the fd; OS releases on process exit, but the file inode persists
    # (sentinel mode). So mtime ~= last leader-acquire time, not "last write".
    # 讀 lock metadata。leader 持 fd 時 mtime 維持；OS 在 process 退出時釋放鎖，
    # 但 inode 留下（sentinel 模式）。所以 mtime ≈ 最近一次 leader 取得時間。
    try:
        mtime = datetime.fromtimestamp(lock_path.stat().st_mtime, tz=timezone.utc)
        age_h = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600.0
    except OSError as e:
        return ("WARN", f"leader lock stat failed: {e}")

    # Read PID from lock body — `_acquire_leader_lock` writes "<pid>\n" after
    # successful flock. May be empty if write failed (non-fatal in scheduler).
    # 從 lock 內容讀 PID — `_acquire_leader_lock` 在 flock 後寫入「<pid>\n」。
    # 若寫失敗（scheduler 端 non-fatal）內容會空。
    leader_pid: int | None = None
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
        if raw:
            leader_pid = int(raw.splitlines()[0])
    except (OSError, ValueError) as e:
        # PID malformed — surface as WARN with raw read for operator debug.
        # PID 格式壞 — WARN 並回顯原始內容供 operator debug。
        return ("WARN", f"leader lock at {lock_path} (age {age_h:.1f}h) — "
                f"PID read malformed: {e}")

    if leader_pid is None:
        # Lock acquired but PID write empty — partial init or scheduler crash
        # mid-acquire. Don't FAIL (lock-holder may still be alive), but WARN.
        # Lock 取得但 PID 寫入為空 — 初始化中斷或 scheduler 取鎖中崩潰。
        # 不 FAIL（持鎖者可能仍活）但 WARN。
        return ("WARN", f"leader lock at {lock_path} (age {age_h:.1f}h) — "
                "PID body empty (partial init? scheduler crash mid-acquire?)")

    # Check PID liveness. /proc/<pid> on Linux is cheapest; os.kill(pid, 0)
    # works on both Linux and macOS without sending an actual signal — raises
    # ProcessLookupError if PID doesn't exist, PermissionError if PID exists
    # but we lack rights (still proves it's alive).
    # PID 存活檢查。Linux 走 /proc 最便宜；os.kill(pid, 0) 雙平台不發訊號 —
    # 不存在則 ProcessLookupError；存在但無權限則 PermissionError（仍證活著）。
    pid_alive = False
    try:
        os.kill(leader_pid, 0)
        pid_alive = True
    except ProcessLookupError:
        pid_alive = False
    except PermissionError:
        # PID exists but other-user owned — we proved it's alive.
        # PID 存在但屬其他 user — 證明活著。
        pid_alive = True
    except OSError as e:
        # Other OS errors (rare) — fail-soft to WARN.
        # 其他 OSError（罕見）— fail-soft 為 WARN。
        return ("WARN", f"leader lock pid={leader_pid} liveness probe failed: {e}")

    if not pid_alive:
        # Dead leader + lock survives = the silent-death blind spot QA flagged.
        # Operator: rm <lock>; restart uvicorn process to re-elect.
        # 死 leader + lock 留存 = QA 指的 silent-death 盲點。
        # Operator 動作：rm <lock>; restart uvicorn 觸發重選舉。
        return ("FAIL", f"leader lock pid={leader_pid} DEAD (age {age_h:.1f}h, "
                f"lock at {lock_path}) — re-election blocked; operator: "
                f"`rm {lock_path}` + restart uvicorn")

    # PID alive — check age for staleness drift.
    # PID 活著 — 檢查 age 是否漂移過久。
    base_msg = (f"leader_pid={leader_pid} alive, lock_age={age_h:.1f}h, "
                f"path={lock_path}")
    if age_h > 24:
        return ("WARN", base_msg + " — lock >24h old (drift; restart at next maintenance)")
    return ("PASS", base_msg)


def check_pipeline_triangulation(cur, close_fills_24h: int) -> tuple[str, str]:
    """[Xb] G6-01 (2026-04-24): cross-pipeline triangulation between fills / labels / intents.

    QA audit §2.2 #4 flagged a blind spot: the 12 existing checks are each
    locally consistent (ratio ≥ N%, row count ≥ M, fire count ≥ K) but they
    **do not cross-reference each other**. A subtle pipeline-level failure can
    leave every individual check green while the aggregate telemetry is
    incoherent. Examples this check catches that individual [1]/[2]/[10]
    miss:

      A. **Duplicate-intent writer bug**: intents_24h = 3× orders_24h because
         an IPC retry loop double-emits the same intent. [10] rates 0.3-1.0 as
         under-firing / normal; it does **not** alarm on 3.0. Fills + labels
         look clean, but intent ledger is inflated — contaminates downstream
         auditing + strategy attribution.

      B. **Label-backfill lagging fill rate but above floor**: close_fills=50,
         labels=40 (ratio 0.80 PASS by [2]), intents=15 (ratio 0.30 PASS by
         [10]). Each looks OK; triangulation notices fills >> intents (3.3×)
         which points at engine emitting fills from a path that skips intent
         ledger (orphan adopter? phantom close?). This is the P0-4 / P0-5
         phantom-close fingerprint that [10] alone cannot surface because
         [10] compares intents to orders, not to fills.

      C. **Silent scale drift**: all three counts non-zero but one drifts 2+
         orders of magnitude vs the others over 24h. Without cross-check, a
         "fills=5 / labels=500" scenario (label backfiller looping on stale
         rows) passes [2] (ratio=100) without flagging the absurd mismatch.

    Three-state triage:
      - **FAIL**: any pairwise ratio outside the "plausible" band
        `[0.1, 10.0]` when all three anchors > 0 (severe divergence; silent
        corruption indicator).
      - **WARN**: any pairwise ratio outside `[0.3, 3.0]` (drift indicator,
        investigate).
      - **PASS**: all three pairwise ratios inside `[0.3, 3.0]`, or close_fills
        too low (< 5) to triangulate reliably (defer to [1]'s own FAIL/WARN).

    Fail-soft: if any of the 3 counts cannot be queried (schema drift, aborted
    transaction), downgrade to WARN with diag — do NOT let a healthcheck-side
    IO glitch shadow the triangulation signal.

    [Xb] G6-01（2026-04-24）：fills / labels / intents 跨管線三角驗證。
    QA audit §2.2 #4 指 12 個 check 彼此獨立（各驗自己門檻），不做交叉比對。
    許多管線級 bug（重複寫 intent、phantom fill、label backfill 失控循環）個別
    check 全綠但彙總不合理；本 check 做 pairwise ratio 檢查，覆蓋 [1]/[2]/[10]
    個別盲點。三態：全部 ratio ∈ [0.3, 3.0] = PASS；任一在 [0.1, 0.3) 或
    (3.0, 10.0] = WARN（drift）；任一超出 [0.1, 10.0] = FAIL（severe divergence）。
    Close_fills < 5 時樣本太小無法三角化，降級回 [1] 自身判決。
    Fail-soft：任一查詢失敗 WARN + diag，不讓 IO glitch 遮蔽信號。
    """
    # Defensive rollback: keep cursor clean in case an earlier check aborted
    # the transaction. Same pattern as check_intents_writer_ratio.
    # 防禦式 rollback：避免前 check 異常打斷 transaction 讓後續 query 全失敗。
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # Small-sample short-circuit: close_fills < 5 makes every ratio noisy.
    # Defer to [1]'s own WARN/FAIL verdict; emit PASS with an explicit note so
    # operator sees the triangulation was intentionally skipped, not silenced.
    # 樣本過小（close_fills < 5）比率完全不可信 — 降級 PASS + 明示被跳過，
    # 不要變成「沉默 PASS」讓 operator 以為真的三角化過。
    if close_fills_24h < 5:
        return (
            "PASS",
            f"triangulation skipped: close_fills_24h={close_fills_24h} < 5 "
            "(defer to [1] verdict; ratios unreliable at this sample size)",
        )

    # Query labels_24h (same filter as [2]) and intents_24h (same filter as [10]
    # but demo-only, since close_fills baseline is demo-scoped).
    # 查 labels_24h（同 [2]）與 intents_24h（同 [10]，demo-only 匹配 baseline）。
    try:
        cur.execute(
            "SELECT COUNT(*) FROM learning.decision_features "
            "WHERE label_filled_at > now() - interval '24 hours' "
            "AND label_net_edge_bps IS NOT NULL "
            "AND engine_mode = 'demo'"
        )
        labels_24h = int(cur.fetchone()[0] or 0)
    except Exception as e:
        return ("WARN", f"triangulation labels query failed: {e}")

    try:
        cur.execute(
            "SELECT COUNT(*) FROM trading.intents "
            "WHERE ts > now() - interval '24 hours' AND engine_mode = 'demo'"
        )
        intents_24h = int(cur.fetchone()[0] or 0)
    except Exception as e:
        return ("WARN", f"triangulation intents query failed: {e}")

    # Pairwise ratio analysis. Reference anchor = close_fills_24h.
    # fills:labels and fills:intents are most informative; labels:intents is
    # a secondary cross-check.
    # Pairwise 比率分析。參考錨 = close_fills_24h。
    def _ratio(a: int, b: int) -> float:
        """Safe ratio a/b; returns float('inf') on b=0, 0.0 on a=b=0.
        安全比率：b=0 時 inf，a=b=0 時 0.0，讓上層判 "one-sided" 分歧。"""
        if b == 0:
            return float("inf") if a > 0 else 0.0
        return a / b

    r_fl = _ratio(close_fills_24h, labels_24h)     # fills / labels
    r_fi = _ratio(close_fills_24h, intents_24h)    # fills / intents
    r_li = _ratio(labels_24h, intents_24h)         # labels / intents

    # Plausible / WARN / FAIL bands (symmetric around 1.0).
    # 合理 / WARN / FAIL 區間（對稱於 1.0）。
    WARN_LO, WARN_HI = 0.3, 3.0       # outside this → WARN
    FAIL_LO, FAIL_HI = 0.1, 10.0      # outside this → FAIL

    def _classify(r: float) -> str:
        """Return '', 'WARN', or 'FAIL' for a single ratio.
        單一比率分類：空字串（正常）/ WARN / FAIL。"""
        if r == 0.0 or r == float("inf"):
            # One-sided zero — e.g. fills>0 + labels=0. FAIL-grade because
            # either anchor totally missing despite baseline alive.
            # 單邊零 — 其中一方完全空，FAIL（基線活但某端完全斷）。
            return "FAIL"
        if r < FAIL_LO or r > FAIL_HI:
            return "FAIL"
        if r < WARN_LO or r > WARN_HI:
            return "WARN"
        return ""

    classes = {
        "fills/labels": (r_fl, _classify(r_fl)),
        "fills/intents": (r_fi, _classify(r_fi)),
        "labels/intents": (r_li, _classify(r_li)),
    }

    # Summarise pairwise ratios for operator readability. Use "inf" / "0.00"
    # sentinels for one-sided divergence; float('inf') formats as 'inf' so
    # explicit branch for clarity.
    # 總結 pairwise 比率供 operator 可讀。單邊分歧用 inf / 0.00 顯示。
    def _fmt(r: float) -> str:
        if r == float("inf"):
            return "inf"
        return f"{r:.2f}"

    pairs_str = ", ".join(
        f"{name}={_fmt(r)}{'[' + cls + ']' if cls else ''}"
        for name, (r, cls) in classes.items()
    )
    base = (
        f"close_fills={close_fills_24h}, labels={labels_24h}, intents={intents_24h} | "
        f"{pairs_str}"
    )

    # Composite verdict: FAIL wins > WARN wins > PASS.
    # 彙總：FAIL > WARN > PASS。
    statuses = [cls for _, (_, cls) in classes.items() if cls]
    if "FAIL" in statuses:
        return (
            "FAIL",
            base + " — severe pairwise divergence (duplicate writer / phantom "
            "close / label-backfill runaway; see RCA log)",
        )
    if "WARN" in statuses:
        return (
            "WARN",
            base + " — drift; inspect intent writer + label backfill lag",
        )
    return ("PASS", base)


def check_observer_pipeline_alive() -> tuple[str, str]:
    """[19] OBSERVER-PIPELINE-POST-F42FACE-CLEANUP (2026-04-26): observer cron freshness + ok ratio.

    The G9-04 (commit ``c7d7179``) follow-up audit uncovered that
    ``bybit_full_readonly_observer_cycle.py`` had 9 hard-coded ``scripts/``
    paths surviving the ``f42face`` 98-shim wipe (2026-04-23). Cron ran
    ``cron_observer_cycle.sh`` every 5 minutes and 100% of stages fail-loop
    with ``[Errno 2] No such file or directory`` for **3 full days** — yet
    the cron wrapper's ``if ... ; then ... else echo "non-fatal" ; fi``
    pattern translated every failure into an info log line and exit 0.
    Cron daemon never noticed; healthcheck never noticed; no other guard
    was watching this pipeline. That is the textbook silent-fail mode
    CLAUDE.md §七 "被動等待 TODO 必附 healthcheck" was written to prevent.

    Two-axis verdict using purely filesystem state:
      1. **Freshness** — ``runtime/bybit/bybit_observer_cycle_latest.json``
         must have been written within the last 24h. Cron runs every 5min
         under nominal load; missing the 24h window = pipeline definitely
         dead even if cron is dispatching (locked file? venv missing?
         systemd cron disabled?).
      2. **ok ratio** — read the JSON, sum ``steps[].ok`` over the most
         recent cycle. ≥75% PASS is healthy; 50-75% WARN (degraded but
         partial); <50% FAIL (silent-fail mode). 0% with mtime fresh =
         the post-f42face fingerprint we saw — that's why <50% must FAIL.

    Three-state output:
      - **FAIL**: latest JSON missing OR mtime > 24h OR ok ratio < 50%
        OR JSON parse error (corruption is itself a silent-fail signal).
      - **WARN**: ok ratio in [50%, 75%) OR mtime in (1h, 24h] (cron may
        have skipped a beat — drift indicator).
      - **PASS**: mtime ≤ 1h AND ok ratio ≥ 75%.

    Phase 1a / first-run note: when the pipeline has never run, the JSON
    does not exist — that registers as FAIL because ``cron_observer_cycle``
    is wired up by default in production crontabs and "never ran" is a
    real silent-fail (operator forgot to enable cron / VENV moved /
    OPENCLAW_SRV_ROOT unset). Operators bringing up a fresh node that
    does not yet have observer cron should comment out [19] in runner
    or set ``OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1`` (latter PASS-skip).

    Cross-platform: pure ``Path.stat()`` + ``json.loads()`` — no
    Linux-only API. Mac dev-only environments without observer cron
    can set ``OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1``.

    [19] OBSERVER-PIPELINE-POST-F42FACE-CLEANUP（2026-04-26）：observer
    cron 新鮮度 + ok 比率守衛。G9-04 follow-up audit 揭發
    ``bybit_full_readonly_observer_cycle.py`` 有 9 條 hard-coded
    ``scripts/`` 路徑（2026-04-23 commit ``f42face`` 清 98 個 shim 後失效），
    cron 每 5 分鐘觸發、100% 階段 ``[Errno 2] No such file`` 連續 3 天，
    但 cron wrapper 的 ``if ... ; then ... else echo "non-fatal"`` pattern
    把所有失敗譯成 log 行 + exit 0。cron daemon、healthcheck、所有 guard
    都沒看見。這正是 CLAUDE.md §七「被動等待 TODO 必附 healthcheck」要防的
    教科書級 silent-fail 模式。

    兩軸 verdict（純檔案系統）：
      1. **新鮮度** — ``runtime/bybit/bybit_observer_cycle_latest.json``
         mtime 必須在 24h 內。標準負載下 cron 5min 一次，逾 24h = pipeline
         必死（即便 cron 還在 dispatch）。
      2. **ok 比率** — 讀 JSON 統計 ``steps[].ok``。≥75% 健康；
         50-75% WARN（部分降級）；<50% FAIL（silent-fail 模式）。
         post-f42face 連 3 天 0% + mtime 新 = 本 ticket 觸發點，因此 <50%
         必 FAIL。

    三態輸出：FAIL（檔缺 / mtime>24h / ok<50% / JSON 壞）/ WARN（ok 50-75%
    或 mtime 1-24h）/ PASS（mtime≤1h + ok≥75%）。

    跨平台：純 ``Path.stat()`` + ``json.loads()``，無 Linux-only API。
    Mac dev-only 環境若無 observer cron 可設
    ``OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1``。
    """
    # Optional opt-out for environments that legitimately don't run the
    # observer cron (Mac dev-only, fresh nodes pre-cron-bootstrap).
    # 允許環境級 opt-out（Mac dev / 尚未啟用 cron 的新節點）。
    if os.environ.get("OPENCLAW_OBSERVER_PIPELINE_OPTIONAL") == "1":
        return (
            "PASS",
            "observer pipeline optional (OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1, skip)",
        )

    # Locate the cycle JSON. OPENCLAW_SRV_ROOT is the canonical anchor;
    # fall back to OPENCLAW_BASE_DIR for forward-compat per CLAUDE.md §六.
    # 解析 cycle JSON 路徑。OPENCLAW_SRV_ROOT 為主錨，OPENCLAW_BASE_DIR
    # 為 forward-compat fallback（CLAUDE.md §六）。
    base = os.environ.get("OPENCLAW_SRV_ROOT") or os.environ.get(
        "OPENCLAW_BASE_DIR"
    )
    if not base:
        # Last-resort default: production Linux layout.
        # 最終 fallback：生產 Linux 預設路徑。
        base = str(Path.home() / "BybitOpenClaw" / "srv")
    cycle_path = (
        Path(base)
        / "docker_projects"
        / "trading_services"
        / "runtime"
        / "bybit"
        / "bybit_observer_cycle_latest.json"
    )

    if not cycle_path.exists():
        # Missing entirely — pipeline either never ran or output was wiped.
        # Either way that is a real silent-fail in production.
        # 檔完全不存在 — 從未跑或 output 被清掉，生產環境兩種都算真實 silent-fail。
        return (
            "FAIL",
            f"observer cycle JSON missing at {cycle_path} — cron not running? "
            "(set OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1 if intentional)",
        )

    # Freshness — the cron beat is 5 min, so 1h leaves > 10 missed cycles
    # before WARN; 24h leaves > 280 missed cycles before FAIL. That's the
    # ratio CLAUDE.md §七 expects for "silent-dead 自動偵測".
    # 新鮮度：cron 5min 一次，1h ≈ 12 拍 buffer → WARN 門檻；24h ≈ 288 拍
    # buffer → FAIL 門檻，符合 CLAUDE.md §七 silent-dead 自動偵測比例。
    try:
        mtime = datetime.fromtimestamp(
            cycle_path.stat().st_mtime, tz=timezone.utc
        )
        age_h = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600.0
    except OSError as e:
        return ("FAIL", f"observer cycle JSON stat failed: {e}")

    if age_h > 24.0:
        return (
            "FAIL",
            f"observer cycle JSON stale (age={age_h:.1f}h > 24h, "
            f"path={cycle_path}) — cron daemon / wrapper / venv likely broken",
        )

    # Parse JSON for the ok ratio. Corruption itself is a silent-fail signal
    # (wrapper aborted mid-write? disk full?). Treat as FAIL.
    # 解析 JSON 算 ok 比率。檔損壞本身就是 silent-fail（wrapper 寫一半中斷？
    # 磁碟滿？）— 直接 FAIL。
    try:
        cycle = json.loads(cycle_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return (
            "FAIL",
            f"observer cycle JSON parse error (age={age_h:.1f}h, "
            f"path={cycle_path}): {e}",
        )

    steps = cycle.get("steps")
    if not isinstance(steps, list) or not steps:
        # Schema drift — old cycle shape or partial write. Don't pretend
        # we know the ok ratio; surface the anomaly with WARN so operator
        # checks vs FAIL'ing on a healthcheck-side schema bug.
        # Schema 漂移 — 舊版 cycle 結構或部分寫入。不假設知道 ok 比率，
        # 用 WARN 提報讓 operator 確認，避免 healthcheck-side schema bug
        # 直接 FAIL。
        return (
            "WARN",
            f"observer cycle JSON has no steps array "
            f"(age={age_h:.1f}h, path={cycle_path}) — schema drift?",
        )

    total = len(steps)
    ok_count = sum(1 for s in steps if isinstance(s, dict) and s.get("ok") is True)
    ratio = ok_count / total if total else 0.0
    overall_ok = bool(cycle.get("overall_ok"))

    base_msg = (
        f"age={age_h:.1f}h, ok={ok_count}/{total} ({ratio:.0%}), "
        f"overall_ok={overall_ok}, path={cycle_path}"
    )

    # Severity ladder: <50% ok ratio FAIL (post-f42face fingerprint),
    # 50-75% WARN (degraded), ≥75% with mtime ≤ 1h PASS.
    # 嚴重度階梯：ok<50% FAIL（post-f42face 指紋）、50-75% WARN（部分降級）、
    # ≥75% 且 mtime ≤ 1h PASS。
    if ratio < 0.5:
        return (
            "FAIL",
            base_msg + " — silent-fail mode (post-f42face fingerprint? "
            "check observer_cycle path config + cron wrapper + venv)",
        )
    if ratio < 0.75:
        return ("WARN", base_msg + " — degraded; investigate failing steps")
    if age_h > 1.0:
        # ≥75% ok but mtime drift — cron may have skipped a beat or
        # cron daemon is paused. Surface as WARN for operator triage.
        # ok≥75% 但 mtime 漂移 — cron 可能漏拍或 daemon 暫停，WARN 提示
        # operator triage。
        return ("WARN", base_msg + " — mtime drift (>1h since last cycle)")
    return ("PASS", base_msg)
