"""Cost-edge advisor healthcheck (sibling of checks_derived).
cost_edge_advisor 健康檢查（checks_derived 的 sibling）。

MODULE_NOTE (EN): Extracted from ``checks_derived.py`` by G3-09 Phase B
Wave 1 E2-return-fix (HIGH-1, 2026-04-28). Original placement pushed
``checks_derived.py`` from 1153 to 1304 LOC, breaching CLAUDE.md §九
1200-line hard cap. Only the ``check_cost_edge_advisor_status`` function
(lines 877-1197 of the pre-fix ``checks_derived.py``) moved into this
sibling; ``check_h_state_gateway_freshness`` and the F7 ML-hygiene
``check_dust_spiral_noise_in_ef`` stay in ``checks_derived.py`` to keep
this single-purpose module focused (E1 self-decision per E2 return §
"avoid scope creep — only move cost_edge_advisor").

Pattern mirrors the existing ``checks_engine.py`` / ``checks_strategy.py``
/ ``checks_ipc_edge.py`` decomposition. Public surface is the single
function ``check_cost_edge_advisor_status`` re-exported from the package
``__init__.py`` for back-compat with any direct importers.

The function preserves Phase A + Phase B behavior **byte-identical** to
the pre-split version — same env-gate logic, same TOML parse path, same
DB query strings, same WARN/FAIL thresholds.

MODULE_NOTE (中): G3-09 Phase B Wave 1 E2 return fix（HIGH-1，2026-04-28）
從 ``checks_derived.py`` 抽出。原放置使 ``checks_derived.py`` 從 1153 行
膨脹至 1304 行，破 CLAUDE.md §九 1200 行硬上限。僅
``check_cost_edge_advisor_status`` 一個函式遷至本 sibling；
``check_h_state_gateway_freshness`` 與 F7 ``check_dust_spiral_noise_in_ef``
保留於 ``checks_derived.py``，避免 scope creep（E1 自決）。

Pattern 沿襲既有 ``checks_engine`` / ``checks_strategy`` / ``checks_ipc_edge``
拆分模式。公開介面為單一函式 ``check_cost_edge_advisor_status``，
package ``__init__.py`` 重新匯出維持向後相容。

行為與拆分前 byte-identical — env-gate / TOML 解析路徑 / DB query 字串
/ WARN/FAIL 閾值全部一致。
"""

from __future__ import annotations

import os
from pathlib import Path


# ============================================================================
# G3-09 Phase A (2026-04-27) → Phase B (2026-04-28): cost_edge_advisor sentinel.
# G3-09 Phase A → Phase B：cost_edge_advisor 哨兵。
# ============================================================================


def check_cost_edge_advisor_status(cur=None) -> tuple[str, str]:
    """[30] G3-09 Phase A (2026-04-27) → Phase B (2026-04-28): cost_edge_advisor
    env-gate + RiskConfig flag + (Phase B) trigger frequency sanity check.

    MODULE_NOTE (EN): G3-09 completion-criteria sentinel. The cost_edge_advisor
    is the Rust-side AI cost awareness module (CLAUDE.md §二 原則 #13:
    "AI 資源成本感知 — 每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉").
    Phase A landing is advisory only — daemon polls H5 snapshot every 10s,
    evaluates `paper_pnl_7d_usd / ai_spend_7d_usd <= trigger_threshold`, and
    emits transition logs/audit; no IntentProcessor wiring (Phase B/C scope).

    Phase B (G3-09 2026-04-28): the daemon now persists each evaluate cycle
    (down-sampled to 1/min for cycle rows; transition rows immediate) into
    ``learning.cost_edge_advisor_log`` (V026 hypertable). When ``cur`` is
    provided AND env=1, this check additionally runs Inv 3 (DB freshness
    in last 1h) + Inv 4 (trigger frequency sanity bounds + dead-gate
    detection at 7d window). When ``cur`` is None, behaves identically to
    Phase A pure-Python (Inv 1 + Inv 2 only) — kept for callers that have
    no DB cursor in scope (cron-driven post-cursor sentinel + DB-down
    fallback path; see runner.py LOW-2 fix 2026-04-28).

    Two-phase verdict (matches PA RFC §6.2):

      A. **DEFAULT-OFF path (``OPENCLAW_COST_EDGE_ADVISOR != "1"``)**:
         PASS-skip with explicit dormant note. Phase A advisor stays off in
         production until operator explicitly opts in (mirrors G3-08 H State
         Gateway pattern; both default off, both flipped together once H5
         snapshot accumulation provides meaningful ratio).

      B. **DEFAULT-ON path (``OPENCLAW_COST_EDGE_ADVISOR == "1"``)**:
         Verify two invariants without making a live IPC roundtrip (avoids
         cron coupling to HMAC secret + main process being up — mirrors
         [20] check_h_state_gateway_freshness philosophy):
           1. Active risk_config TOML (demo, the canonical advisor source per
              PA RFC §8.2) parses cleanly and contains a ``[cost_edge]``
              section with ``enabled`` (bool) + ``trigger_threshold``
              (numeric in [-100, 100]).
           2. The Rust ``cost_edge_advisor`` module's three sibling files exist
              on disk: ``mod.rs`` / ``types.rs`` / ``advisor.rs`` —
              regression to deleted module (rare but possible from refactor
              accident) surfaces as FAIL.
         Three-state output:
           - PASS: env=1 + TOML section present + module files exist.
           - WARN: TOML missing ``[cost_edge]`` section (advisor will run with
                   default values — non-fatal but operator should add).
           - FAIL: TOML parse error / module files missing / threshold out of
                   range.

    Pure-function check (Phase A path): pure ``Path.read_text()`` +
    ``tomllib.loads``; no live IPC, no DB cursor, no socket. Cross-platform:
    works identically on Mac dev and Linux prod.

    [30] G3-09 Phase A（2026-04-27）→ Phase B（2026-04-28）：cost_edge_advisor
    env-gate + RiskConfig flag + (Phase B) trigger 頻率合理性檢查。
    （NOTE：PA RFC §6.2 原寫 slot [22]，F7 已佔用 → 本實作改 [30]。）

    G3-09 完成標準哨兵。cost_edge_advisor 是 Rust 端 AI 成本感知模組
    （CLAUDE.md §二 原則 #13）。Phase A 純 advisory — daemon 每 10s 讀 H5、
    比對 `paper_pnl_7d / ai_spend_7d <= trigger_threshold`、轉換時 log+audit；
    不接 IntentProcessor（Phase B/C 範圍）。

    兩段判決（PA RFC §6.2）：
      A. DEFAULT-OFF（``OPENCLAW_COST_EDGE_ADVISOR != "1"``）→ PASS-skip。
      B. DEFAULT-ON（``OPENCLAW_COST_EDGE_ADVISOR == "1"``）→ 驗 2 個不變量
         （不做 live IPC 避 6h cron 與 HMAC/main 耦合，對齊 [20] 哲學）：
           1. demo TOML（advisor canonical source per RFC §8.2）可解析且含
              ``[cost_edge]`` 區塊 + ``enabled`` (bool) + ``trigger_threshold``
              (數值 ∈ [-100, 100])。
           2. Rust ``cost_edge_advisor`` 模組三 sibling 檔仍存在
              （mod.rs/types.rs/advisor.rs）— refactor 誤刪會 FAIL。
         三態：env=1+TOML+module 全綠 = PASS；TOML 缺 section = WARN（advisor
         走預設值 fail-soft）；TOML 解析錯誤 / module 缺 / threshold 超界 = FAIL。

    Phase A 路徑為純函式 check：`Path.read_text` + `tomllib.loads`，無 live IPC
    / DB / socket。Mac dev 與 Linux prod 行為一致。
    """
    # Path A: env-gate disabled → PASS-skip (env=0 dormant by design).
    # 路徑 A：env=0 → PASS-skip（dormant by design）。
    env_val = os.environ.get("OPENCLAW_COST_EDGE_ADVISOR")
    if env_val != "1":
        env_repr = f"={env_val!r}" if env_val is not None else "=unset"
        return (
            "PASS",
            f"OPENCLAW_COST_EDGE_ADVISOR{env_repr} (≠'1') — env=0 dormant "
            "by design (Phase A: 0 trade impact even when activated); skip",
        )

    # Path B: env-gate enabled → verify 2 invariants (Phase A expectations).
    # 路徑 B：env=1 → 驗 2 不變量（Phase A 預期）。

    # Invariant 1: demo TOML parses + has [cost_edge] section with valid fields.
    # 不變量 1：demo TOML 可解析且 [cost_edge] 區塊欄位合法。
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        return ("WARN", "tomllib unavailable (Python <3.11?) — cannot verify [cost_edge]")

    base = os.environ.get("OPENCLAW_BASE_DIR") or os.environ.get("OPENCLAW_SRV_ROOT")
    if not base:
        # Production Linux fallback (mirrors check_observer_pipeline_alive).
        # 生產 Linux fallback（對齊 check_observer_pipeline_alive）。
        base = str(Path.home() / "BybitOpenClaw" / "srv")
    toml_path = Path(base) / "settings" / "risk_control_rules" / "risk_config_demo.toml"

    if not toml_path.exists():
        return (
            "FAIL",
            f"risk_config_demo.toml missing at {toml_path} — "
            "advisor canonical source absent",
        )

    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
    except OSError as e:
        return ("WARN", f"TOML read failed (filesystem race?): {e}")
    except Exception as e:  # noqa: BLE001 — surface parse error
        return ("FAIL", f"TOML parse error: {e}")

    section = data.get("cost_edge")
    if section is None:
        return (
            "WARN",
            f"[cost_edge] section absent in {toml_path.name} — advisor will use "
            "RiskConfig defaults (enabled=false, threshold=-0.5); operator "
            "should add explicit section per G3-09 Phase A docs",
        )
    if not isinstance(section, dict):
        return ("FAIL", f"[cost_edge] not a table: {type(section).__name__}")

    enabled = section.get("enabled")
    threshold = section.get("trigger_threshold")
    if not isinstance(enabled, bool):
        return (
            "FAIL",
            f"[cost_edge].enabled missing or non-bool (got {enabled!r})",
        )
    if not isinstance(threshold, (int, float)):
        return (
            "FAIL",
            f"[cost_edge].trigger_threshold missing or non-numeric "
            f"(got {threshold!r})",
        )
    threshold_f = float(threshold)
    if not (-100.0 <= threshold_f <= 100.0):
        return (
            "FAIL",
            f"[cost_edge].trigger_threshold ({threshold_f}) out of range "
            "[-100.0, 100.0] — advisor would silent-disable (would never "
            "trigger / always trigger)",
        )

    # Invariant 2: Rust cost_edge_advisor module sibling files exist.
    # 不變量 2：Rust cost_edge_advisor 模組三 sibling 檔存在。
    advisor_dir = (
        Path(base) / "rust" / "openclaw_engine" / "src" / "cost_edge_advisor"
    )
    required_files = ("mod.rs", "types.rs", "advisor.rs")
    missing = [
        name for name in required_files if not (advisor_dir / name).exists()
    ]
    if missing:
        return (
            "FAIL",
            f"cost_edge_advisor module files missing: {missing} at "
            f"{advisor_dir} — refactor regression?",
        )

    # ----------------------------------------------------------------
    # Phase A invariants (Inv 1 + Inv 2) all passed. If no `cur` given,
    # caller is the Phase A no-DB code path — return PASS now. This is
    # the path also taken by the DB-down fallback sentinel in runner.py
    # (LOW-2 fix 2026-04-28) to preserve env=1 invariants when DB is
    # unreachable.
    # Phase A 不變量（Inv 1+2）通過。無 `cur` 時 caller 為 Phase A 無 DB 路徑
    # — 立即回 PASS。runner.py LOW-2 fix（2026-04-28）DB-down fallback
    # 也走此路徑，確保 DB 不通時 env=1 不變量仍生效。
    # ----------------------------------------------------------------
    if cur is None:
        return (
            "PASS",
            f"env=1 + [cost_edge].enabled={enabled} threshold={threshold_f} "
            f"+ module files present (Phase A invariants; no DB cursor for Inv 3/4)",
        )

    # ----------------------------------------------------------------
    # Phase B (G3-09 2026-04-28): Inv 3 — DB freshness in last 1h.
    # Daemon should INSERT roughly 60 cycle rows / hr (one per minute).
    # 0 rows = silent-dead pipeline (DB connection broken / daemon crashed
    # since rebuild). <30 rows = degraded (partial outage). Both surfaced.
    #
    # Phase B 不變量 3：1h INSERT 新鮮度。Daemon 每分鐘 1 cycle row → 1h
    # ~60 row。0 = 沉默死亡管線（DB 斷線 / daemon 崩潰）；<30 = 降級
    # （部分中斷）。兩者皆 surface。
    # ----------------------------------------------------------------
    try:
        cur.execute(
            "SELECT COUNT(*) FROM learning.cost_edge_advisor_log "
            "WHERE ts_ms > (extract(epoch from now()) * 1000)::BIGINT - 3600000"
        )
        row = cur.fetchone()
        inserts_1h = int(row[0]) if row and row[0] is not None else 0
    except Exception as e:  # noqa: BLE001 — surface DB-side anomaly explicitly
        # DB query failed — could be the V026 table not yet applied; treat
        # as WARN (not FAIL) so a missing migration is loud but doesn't fail
        # the entire healthcheck while V026 is rolling out.
        # DB 查詢失敗 — 可能 V026 尚未套用；視為 WARN（非 FAIL）讓缺 migration
        # 響亮但不在 V026 rollout 期間整體拉 FAIL。
        return (
            "WARN",
            f"learning.cost_edge_advisor_log query failed: {e}; V026 migration "
            f"may not yet be applied (run linux_bootstrap_db.sh --apply or set "
            f"OPENCLAW_AUTO_MIGRATE=1)",
        )

    if inserts_1h == 0:
        return (
            "FAIL",
            f"learning.cost_edge_advisor_log no INSERT in last 1h (env=1 but "
            f"daemon write path silent-dead — check engine.log for "
            f"'cost_edge_advisor_log INSERT failed' warns or daemon panic)",
        )
    if inserts_1h < 30:
        return (
            "WARN",
            f"learning.cost_edge_advisor_log only {inserts_1h} rows in last 1h "
            f"(expected ~60 at 1/min cadence; daemon may be slow or DB INSERT "
            f"degraded — check engine.log)",
        )

    # ----------------------------------------------------------------
    # Phase B Inv 4 — Trigger frequency sanity (spam upper bound + dead-gate
    # detection only when observation window is mature ≥7d).
    # Phase B 不變量 4 — Trigger 頻率合理性（spam 上界 + 觀察視窗 ≥7d 後
    # dead-gate 偵測）。
    # ----------------------------------------------------------------
    try:
        cur.execute(
            "SELECT COUNT(*) FROM learning.cost_edge_advisor_log "
            "WHERE ts_ms > (extract(epoch from now()) * 1000)::BIGINT - 3600000 "
            "  AND transition_from IS NOT NULL "
            "  AND status = 'Trigger'"
        )
        row = cur.fetchone()
        triggers_1h = int(row[0]) if row and row[0] is not None else 0
    except Exception as e:  # noqa: BLE001
        return ("WARN", f"trigger frequency query failed: {e}")

    # Spam upper bound — >20/hr suggests threshold too aggressive (noise).
    # Spam 上界 — >20/hr 表 threshold 過嚴（noise）。
    if triggers_1h > 20:
        return (
            "WARN",
            f"cost_edge_advisor triggers_per_hour={triggers_1h} > 20 (threshold "
            f"may be too aggressive; calibrate before Phase C — see RFC §4.2 "
            f"upper bound rationale)",
        )

    # Dead-gate detection — only when the table has accumulated >= 7d of
    # data. Otherwise we're still in warm-up and 0 triggers is normal.
    # Dead-gate 偵測 — 表已累積 >= 7d 資料才查；否則 warm-up 中 0 trigger
    # 屬正常。
    try:
        cur.execute(
            "SELECT MIN(ts_ms) FROM learning.cost_edge_advisor_log"
        )
        row = cur.fetchone()
        earliest_ms = int(row[0]) if row and row[0] is not None else 0
    except Exception as e:  # noqa: BLE001
        return ("WARN", f"earliest ts query failed: {e}")

    if earliest_ms > 0:
        from time import time as _time

        now_ms = int(_time() * 1000)
        observation_days = (now_ms - earliest_ms) / 86_400_000.0
        if observation_days >= 7.0:
            try:
                cur.execute(
                    "SELECT COUNT(*) FROM learning.cost_edge_advisor_log "
                    "WHERE transition_from IS NOT NULL AND status = 'Trigger'"
                )
                row = cur.fetchone()
                total_triggers = int(row[0]) if row and row[0] is not None else 0
            except Exception as e:  # noqa: BLE001
                return ("WARN", f"total trigger count query failed: {e}")
            if total_triggers == 0:
                # Check whether ratio histogram has any sample within
                # threshold ± 0.3 (i.e. close to triggering). If all
                # samples are far above threshold, the gate is genuinely
                # dead and operator should recalibrate to 5th percentile.
                # 檢查 ratio histogram 是否有 sample 在 threshold ± 0.3 區間
                # （接近 trigger）。若全離 threshold ≥ 0.3 上方，gate 真死，
                # operator 應重校到 5th percentile。
                try:
                    cur.execute(
                        "SELECT COUNT(*) FROM learning.cost_edge_advisor_log "
                        "WHERE ratio IS NOT NULL "
                        "  AND ratio < threshold + 0.3"
                    )
                    row = cur.fetchone()
                    near_threshold = int(row[0]) if row and row[0] is not None else 0
                except Exception as e:  # noqa: BLE001
                    return ("WARN", f"near-threshold count query failed: {e}")
                if near_threshold == 0:
                    return (
                        "WARN",
                        f"cost_edge_advisor 0 triggers in {observation_days:.1f}d "
                        f"+ ratio histogram entirely > threshold+0.3 (DEAD GATE: "
                        f"threshold={threshold_f} too loose; recalibrate to ratio "
                        f"5th percentile per Phase C deliverable §6)",
                    )

    # All invariants (Phase A + Phase B) passed.
    # 所有不變量（Phase A + Phase B）通過。
    return (
        "PASS",
        f"env=1 + [cost_edge].enabled={enabled} threshold={threshold_f} "
        f"+ module files present + 1h INSERT={inserts_1h} (Phase B observation; "
        f"triggers_per_hour={triggers_1h})",
    )
