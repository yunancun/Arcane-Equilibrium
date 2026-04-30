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
  * [20] check_h_state_gateway_freshness     (added 2026-04-26 by
    G3-08 Phase 1C — DEFAULT-OFF env-gate sentinel; PASS-skips when
    ``OPENCLAW_H_STATE_GATEWAY != "1"`` (Phase 1 dormant by design),
    verifies IPC route + Phase 2 stub shape when env=1; Phase 2 sync
    by G3-08-PHASE-1C-FUP-CHECK20-SYNC bumped expected version 0→1 +
    h_states_keys 0→2 to reflect H1+H3 wiring (commits 9120948+f2ed286).)
  * [26] check_dust_spiral_noise_in_ef       (added 2026-04-26 by F7
    MIT DB audit + ML-TRAINING-DATA-HYGIENE-1 derived — sister check
    to [21] but on the learning corpus side; watches for B1
    ``is_partial_reduce_tag`` regression that would let new dust-spiral
    rows poison ML training input post-fix.)

These five are derivative / cross-cutting checks that don't fit the
direct fill-flow / risk-layer / strategy-flow axes. [Xa] watches the
edge-scheduler leader-lock; [Xb] cross-validates the fills/labels/intents
scale ratios; [18] surfaces TOML-disabled strategies for §三 drift
defense; [19] proves the bybit observer cron pipeline is actually
producing fresh, non-error JSON (the kind of guard CLAUDE.md §七
"被動等待 TODO 必附 healthcheck" mandates after 2026-04-22 silent-fail
postmortems); [20] proves the H-state Python→Rust hint channel + reverse
IPC route are wired correctly, with strict env-gated PASS-skip when
disabled (the canonical DEFAULT-OFF Phase 1 dormant state).

SQL strings, exit-code semantics, output formatting are byte-identical
to the pre-split version (except for the new [19]/[20] which are purely
filesystem-driven / pure-Python — no DB cursor, no live IPC roundtrip).

MODULE_NOTE (中): 衍生 / 跨層觀察性 check：[Xa] 看 edge-scheduler leader-lock，
[Xb] 三角驗證 fills/labels/intents 比例，[18] 列 TOML disabled 策略以防
CLAUDE.md §三 drift，[19] 看 bybit observer cron cycle 是否實際產出
新鮮且無錯的 JSON（OBSERVER-PIPELINE-POST-F42FACE-CLEANUP 2026-04-26 加
— cron 連續 3 天 100% fail 被 noise wrapper 吞掉的反面教材），[20] 驗證
H 狀態 Python→Rust 提示通道與 reverse IPC route 接線正確（嚴格 env=0 時
PASS-skip 對齊 G3-08 Phase 1 dormant 設計、env=1 時驗 route 註冊 +
Phase 1 stub schema）。
SQL / exit code / 輸出格式與拆分前 byte-identical（[19][20] 為新增；
[20] 純 Python import + module reflection，無 DB cursor、無 live IPC）。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from .checks_derived_observer import check_observer_pipeline_alive
from .checks_derived_h_state import check_h_state_gateway_freshness
from .checks_derived_ml_hygiene import check_dust_spiral_noise_in_ef


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





# ============================================================================
# G3-09 Phase A (2026-04-27) → Phase B (2026-04-28) cost_edge_advisor sentinel
# extracted into sibling ``checks_cost_edge.py`` by HIGH-1 fix (2026-04-28)
# to keep ``checks_derived.py`` under CLAUDE.md §九 1200-line hard cap.
# G3-09 Phase A → Phase B cost_edge_advisor 哨兵已由 HIGH-1 fix（2026-04-28）
# 抽至 sibling ``checks_cost_edge.py``，維持本檔 CLAUDE.md §九 1200 行硬上限。
# ============================================================================


# ============================================================================
# F7 (2026-04-26): MIT DB audit + ML-TRAINING-DATA-HYGIENE-1 derived sentinel.
# F7（2026-04-26）：MIT DB audit + ML-TRAINING-DATA-HYGIENE-1 衍生哨兵。
# ============================================================================
