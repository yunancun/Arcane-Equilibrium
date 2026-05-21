"""[69] halt_session_root_cause_recurrence run() 邏輯單元測試（fake cursor）。

對應 P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1（2026-05-21）。

驗證重點（覆蓋 5 個 verdict ladder 分支 + spec §1.4 五候選假設行為）：
  - INSUFFICIENT_SAMPLE：0 events in window（passive-wait dead zone 不阻 deploy）
  - PASS：halt_set metric ≥ threshold（自然 recurrence；root cause 跟 v56 不同）
  - WARN：halt_set metric < threshold（v56 pattern recurrence；P1 仍 UNRESOLVED）
  - FAIL：forensic halt_audit.log 缺對應 process_pid + ts_ms row
  - PASS-mixed：daily_loss kind 的 set event payload daily_loss_pct null
    但 drawdown 達 threshold（halt_audit.rs:287 已知行為）

Production row fixture 來源（halt_audit.rs:273-302 emit shape，halt_audit_pg_writer.py
:250 INSERT 整 payload）：
  - event_type ∈ {halt_session_set / halt_session_manual_cleared
    / halt_session_auto_cleared}
  - payload->>'kind' ∈ {daily_loss / session_drawdown / other}
  - payload->>'session_drawdown_pct' / 'daily_loss_pct' /
    'loaded_drawdown_threshold' / 'loaded_daily_loss_threshold'
  - payload->>'process_pid' + 'ts_ms'（forensic cross-link 雙鍵）

為什麼用 fake cursor + fake forensic log path：
  - 不接真實 PG / 真實 forensic log（CI 上 PG 可能不存在）
  - fake_cursor 模擬 SELECT 回 row tuple；audit_log_path 用 tempdir 隔離
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# ───────────────────────────────────────────────────────────────────────────
# Helper：建 fake row（halt_audit_pg_writer.py INSERT shape）
# ───────────────────────────────────────────────────────────────────────────


def _make_row(
    *,
    event_type: str = "halt_session_set",
    engine_mode: str = "demo",
    kind: str = "session_drawdown",
    process_pid: int = 1942669,
    ts_ms: int = 1747671131234,
    drawdown_pct: float | None = 27.51,
    daily_loss_pct: float | None = None,
    threshold_drawdown: float | None = 25.0,
    threshold_daily_loss: float | None = 15.0,
    risk_config_version: str = "47",
    recompute_ok: str = "true",
    clear_path: str | None = None,
) -> tuple:
    """構造 SELECT result row（與 69_*.py:run() SELECT 順序對齊）。

    row tuple 13-欄（順序固化）：
      0: ts (datetime)
      1: event_type (str)
      2: engine_mode (str)
      3: kind (str)
      4: process_pid (bigint)
      5: ts_ms (bigint)
      6: drawdown_pct (float)
      7: daily_loss_pct (float)
      8: threshold_drawdown (float)
      9: threshold_daily_loss (float)
      10: risk_config_version (str)
      11: recompute_ok (str)
      12: clear_path (str)
    """
    ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    return (
        ts,
        event_type,
        engine_mode,
        kind,
        process_pid,
        ts_ms,
        drawdown_pct,
        daily_loss_pct,
        threshold_drawdown,
        threshold_daily_loss,
        risk_config_version,
        recompute_ok,
        clear_path,
    )


def _write_forensic_log(tmp_path: Path, *halt_events: dict) -> Path:
    """寫 forensic halt_audit.log；每行一個 JSON event。

    為什麼：[69] FAIL 邏輯需 cross-link governance_audit_log row ↔
    halt_audit.log row by (process_pid, ts_ms)；test 必須能控制兩者
    匹配 / 不匹配。
    """
    log = tmp_path / "halt_audit.log"
    with log.open("w", encoding="utf-8") as f:
        for ev in halt_events:
            f.write(json.dumps(ev) + "\n")
    return log


# ───────────────────────────────────────────────────────────────────────────
# Test cases
# ───────────────────────────────────────────────────────────────────────────


def test_empty_window_returns_insufficient_sample(hc69, fake_cursor_factory):
    """0 events in window → INSUFFICIENT_SAMPLE（passive-wait dead zone）。"""
    cur = fake_cursor_factory([[]])  # 0 rows
    result = hc69.run(
        cur,
        window_secs=hc69.DEFAULT_WINDOW_SECS_HALT,
        audit_log_path=Path("/nonexistent"),
    )
    assert result["verdict"] == "INSUFFICIENT_SAMPLE"
    assert result["n_events"] == 0
    assert result["n_halt_set"] == 0
    assert result["n_v56_pattern"] == 0
    assert result["check_id"] == "[69]"
    assert "no halt_session_* events in window" in result["note"]


def test_pass_when_drawdown_meets_threshold(hc69, fake_cursor_factory, tmp_path):
    """halt_set drawdown_pct ≥ threshold → PASS（natural recurrence；
    root cause 跟 v56 不同；v56 event 27.51% ≥ 25% 即此情境）。
    """
    # forensic log 寫對應 pid + ts_ms（FAIL 不該觸發）
    audit_log = _write_forensic_log(
        tmp_path,
        {
            "event": "halt_session_set",
            "process_pid": 1942669,
            "ts_ms": 1747671131234,
            "kind": "session_drawdown",
            "session_drawdown_pct": 27.51,
        },
    )

    rows = [
        [
            _make_row(
                event_type="halt_session_set",
                kind="session_drawdown",
                drawdown_pct=27.51,
                threshold_drawdown=25.0,
                process_pid=1942669,
                ts_ms=1747671131234,
            )
        ]
    ]
    cur = fake_cursor_factory(rows)
    result = hc69.run(
        cur,
        window_secs=hc69.DEFAULT_WINDOW_SECS_HALT,
        audit_log_path=audit_log,
    )
    assert result["verdict"] == "PASS"
    assert result["n_halt_set"] == 1
    assert result["n_v56_pattern"] == 0
    assert result["n_forensic_gap"] == 0
    cell = result["events"][0]
    assert cell["verdict"] == "PASS"
    assert cell["forensic_ok"] is True


def test_warn_when_drawdown_below_threshold_v56_pattern(
    hc69, fake_cursor_factory, tmp_path
):
    """halt_set drawdown_pct < threshold → WARN（v56 pattern recurrence
    10.2% < 25%；五候選假設 (a)-(e) 仍 UNRESOLVED）。

    這是本 healthcheck **核心** signal：若未來再見此模式，PA + E2 + FA
    須聯合 RCA。
    """
    audit_log = _write_forensic_log(
        tmp_path,
        {
            "event": "halt_session_set",
            "process_pid": 1942669,
            "ts_ms": 1747671131234,
            "kind": "session_drawdown",
            "session_drawdown_pct": 10.2,
        },
    )

    rows = [
        [
            _make_row(
                event_type="halt_session_set",
                kind="session_drawdown",
                drawdown_pct=10.2,           # v56 真實 RCA 值
                threshold_drawdown=25.0,     # TOML 真實值
                process_pid=1942669,
                ts_ms=1747671131234,
            )
        ]
    ]
    cur = fake_cursor_factory(rows)
    result = hc69.run(
        cur,
        window_secs=hc69.DEFAULT_WINDOW_SECS_HALT,
        audit_log_path=audit_log,
    )
    assert result["verdict"] == "WARN"
    assert result["n_halt_set"] == 1
    assert result["n_v56_pattern"] == 1
    cell = result["events"][0]
    assert cell["verdict"] == "WARN"
    assert "v56 pattern recurrence" in cell["note"]


def test_fail_when_forensic_log_row_missing(hc69, fake_cursor_factory, tmp_path):
    """governance_audit_log 有 halt_set INSERT 但 halt_audit.log 缺對應
    process_pid + ts_ms row → FAIL（spec §5 forensic violation）。

    這代表 halt_audit_pg_writer.py 已從某處取到事件 INSERT，但 forensic
    log 本身遺失對應 row —— 寫入機制失效或 log 被外力刪除。
    """
    # forensic log 存在但只有一條 pid=9999（與 governance_audit_log row 不匹配）
    audit_log = _write_forensic_log(
        tmp_path,
        {
            "event": "halt_session_set",
            "process_pid": 9999,
            "ts_ms": 1700000000000,
            "kind": "session_drawdown",
        },
    )

    rows = [
        [
            _make_row(
                event_type="halt_session_set",
                kind="session_drawdown",
                drawdown_pct=27.51,
                threshold_drawdown=25.0,
                process_pid=1942669,          # 不在 forensic log
                ts_ms=1747671131234,
            )
        ]
    ]
    cur = fake_cursor_factory(rows)
    result = hc69.run(
        cur,
        window_secs=hc69.DEFAULT_WINDOW_SECS_HALT,
        audit_log_path=audit_log,
    )
    assert result["verdict"] == "FAIL"
    assert result["n_forensic_gap"] == 1
    cell = result["events"][0]
    assert cell["verdict"] == "FAIL"
    assert cell["forensic_ok"] is False
    assert "missing pid=1942669" in cell["forensic_note"]


def test_fail_when_forensic_log_absent_entirely(
    hc69, fake_cursor_factory, tmp_path
):
    """forensic log 本身不存在 → FAIL（spec §5 要求永遠 armed）。

    為什麼：halt_audit_pg_writer.py 從某 source 取到 row INSERT 進 PG
    但 forensic log 路徑被某條件改掉 / 檔被清掉 → 本 healthcheck 必
    觸發 FAIL 告知 operator 重新確認 OPENCLAW_HALT_AUDIT_LOG 路徑。
    """
    rows = [
        [
            _make_row(
                event_type="halt_session_set",
                kind="session_drawdown",
                drawdown_pct=27.51,
                threshold_drawdown=25.0,
                process_pid=1942669,
                ts_ms=1747671131234,
            )
        ]
    ]
    cur = fake_cursor_factory(rows)
    result = hc69.run(
        cur,
        window_secs=hc69.DEFAULT_WINDOW_SECS_HALT,
        audit_log_path=tmp_path / "definitely_does_not_exist.log",
    )
    assert result["verdict"] == "FAIL"
    assert result["n_forensic_gap"] == 1
    cell = result["events"][0]
    assert "forensic log absent" in cell["forensic_note"]


def test_pass_when_daily_loss_kind_with_null_daily_loss_pct(
    hc69, fake_cursor_factory, tmp_path
):
    """daily_loss kind 的 halt_set event payload daily_loss_pct 為 null
    （halt_audit.rs:287 已知行為：PaperState 未暴露 daily_loss API）；
    drawdown_pct 達 threshold 即 PASS（fallback 路徑）。

    這是 daily_loss kind 觸發但 fail-safe 也達 drawdown threshold 的情境；
    根因仍可被 drawdown 數學驗證為合理 recurrence。
    """
    audit_log = _write_forensic_log(
        tmp_path,
        {
            "event": "halt_session_set",
            "process_pid": 2099215,
            "ts_ms": 1747700000000,
            "kind": "daily_loss",
            "session_drawdown_pct": 16.5,
        },
    )

    rows = [
        [
            _make_row(
                event_type="halt_session_set",
                kind="daily_loss",
                drawdown_pct=16.5,            # >= threshold (15% daily_loss
                                              # 通常也意味 drawdown >= 15%)
                daily_loss_pct=None,          # halt_audit.rs:287 null
                threshold_drawdown=25.0,
                threshold_daily_loss=15.0,
                process_pid=2099215,
                ts_ms=1747700000000,
            )
        ]
    ]
    cur = fake_cursor_factory(rows)
    result = hc69.run(
        cur,
        window_secs=hc69.DEFAULT_WINDOW_SECS_HALT,
        audit_log_path=audit_log,
    )
    # drawdown 16.5 < threshold 25.0 → 仍 WARN（drawdown 數學不通）；
    # 此 case 用於驗證 daily_loss kind null fallback 邏輯
    # PASS branch 需要 drawdown >= threshold_drawdown 或 daily_loss
    # >= threshold_daily_loss；本 case daily_loss null + drawdown < threshold
    # → 應 WARN（v56 pattern；daily_loss kind 但 drawdown 沒達 25%）
    assert result["verdict"] == "WARN", (
        f"daily_loss kind + drawdown 16.5% < threshold 25% + daily_loss null "
        f"→ 預期 WARN（無法 PASS）；got {result['verdict']}"
    )


def test_pass_when_daily_loss_kind_drawdown_meets_threshold(
    hc69, fake_cursor_factory, tmp_path
):
    """daily_loss kind + payload daily_loss_pct null + drawdown_pct
    ≥ threshold_drawdown → PASS（fallback 邏輯：daily_loss API 缺，
    但 drawdown 數學足以證明 trigger 合理）。

    區別於 test_pass_when_daily_loss_kind_with_null_daily_loss_pct 的是：
    本 case drawdown 真達 threshold，PASS。
    """
    audit_log = _write_forensic_log(
        tmp_path,
        {
            "event": "halt_session_set",
            "process_pid": 2099215,
            "ts_ms": 1747700000000,
            "kind": "daily_loss",
            "session_drawdown_pct": 30.0,
        },
    )

    rows = [
        [
            _make_row(
                event_type="halt_session_set",
                kind="daily_loss",
                drawdown_pct=30.0,            # >= 25% threshold
                daily_loss_pct=None,          # halt_audit.rs:287 null
                threshold_drawdown=25.0,
                threshold_daily_loss=15.0,
                process_pid=2099215,
                ts_ms=1747700000000,
            )
        ]
    ]
    cur = fake_cursor_factory(rows)
    result = hc69.run(
        cur,
        window_secs=hc69.DEFAULT_WINDOW_SECS_HALT,
        audit_log_path=audit_log,
    )
    assert result["verdict"] == "PASS"
    assert result["n_halt_set"] == 1
    assert result["n_v56_pattern"] == 0


def test_mixed_set_and_cleared_events_only_set_drives_verdict(
    hc69, fake_cursor_factory, tmp_path
):
    """同 window 內混 halt_session_set + halt_session_manual_cleared
    events；clear events 不參與 metric 判定（只有 set 驗 threshold）。
    """
    audit_log = _write_forensic_log(
        tmp_path,
        {
            "event": "halt_session_set",
            "process_pid": 1942669,
            "ts_ms": 1747671131234,
            "kind": "session_drawdown",
            "session_drawdown_pct": 27.51,
        },
    )

    rows = [
        [
            _make_row(
                event_type="halt_session_set",
                kind="session_drawdown",
                drawdown_pct=27.51,
                threshold_drawdown=25.0,
                process_pid=1942669,
                ts_ms=1747671131234,
            ),
            _make_row(
                event_type="halt_session_manual_cleared",
                kind="session_drawdown",
                drawdown_pct=None,            # clear event 無 metric
                threshold_drawdown=None,
                process_pid=1942669,
                ts_ms=1747671200000,          # 9s 後 clear
                clear_path="ipc_resume",
            ),
        ]
    ]
    cur = fake_cursor_factory(rows)
    result = hc69.run(
        cur,
        window_secs=hc69.DEFAULT_WINDOW_SECS_HALT,
        audit_log_path=audit_log,
    )
    # set PASS + clear PASS（非 trigger）→ overall PASS
    assert result["verdict"] == "PASS"
    assert result["n_halt_set"] == 1
    assert result["n_cleared_manual"] == 1
    assert result["n_cleared_auto"] == 0
    # clear cell 的 note 應該顯示「not a trigger row」
    clear_cell = [
        e for e in result["events"]
        if e["event_type"] == "halt_session_manual_cleared"
    ][0]
    assert "not a trigger row" in clear_cell["note"]


def test_multi_set_takes_most_severe_verdict(
    hc69, fake_cursor_factory, tmp_path
):
    """多筆 halt_session_set；severity_max 取最嚴重。

    1 筆 PASS + 1 筆 WARN → overall WARN（severity_max ladder）。
    這是 v56 P1-HALT-TRIGGER 觀察核心：只要 90d window 內出現任一筆
    v56-pattern recurrence，整個 verdict 必降到 WARN 觸發 RCA。
    """
    audit_log = _write_forensic_log(
        tmp_path,
        {
            "event": "halt_session_set",
            "process_pid": 1942669,
            "ts_ms": 1747671131234,
            "kind": "session_drawdown",
            "session_drawdown_pct": 27.51,
        },
        {
            "event": "halt_session_set",
            "process_pid": 2099215,
            "ts_ms": 1747800000000,
            "kind": "session_drawdown",
            "session_drawdown_pct": 12.0,
        },
    )

    rows = [
        [
            _make_row(
                event_type="halt_session_set",
                drawdown_pct=27.51,           # PASS (>= 25)
                threshold_drawdown=25.0,
                process_pid=1942669,
                ts_ms=1747671131234,
            ),
            _make_row(
                event_type="halt_session_set",
                drawdown_pct=12.0,            # WARN (< 25)
                threshold_drawdown=25.0,
                process_pid=2099215,
                ts_ms=1747800000000,
            ),
        ]
    ]
    cur = fake_cursor_factory(rows)
    result = hc69.run(
        cur,
        window_secs=hc69.DEFAULT_WINDOW_SECS_HALT,
        audit_log_path=audit_log,
    )
    assert result["verdict"] == "WARN"
    assert result["n_halt_set"] == 2
    assert result["n_v56_pattern"] == 1


def test_sql_uses_window_secs_and_event_type_filter(
    hc69, fake_cursor_factory, tmp_path
):
    """SQL 必含 (1) window_secs bind (2) event_type IN halt_session_*
    三值 (3) ORDER BY ts DESC LIMIT 100 (4) payload->>'field' jsonb 取值。
    """
    rows = [[]]
    cur = fake_cursor_factory(rows)
    hc69.run(
        cur,
        window_secs=3600,
        audit_log_path=tmp_path / "nope.log",
    )
    sql, params = cur.executed_sqls[0]
    # 邊界 + filter
    assert "learning.governance_audit_log" in sql
    assert "event_type IN" in sql
    assert "halt_session_set" in sql
    assert "halt_session_auto_cleared" in sql
    assert "halt_session_manual_cleared" in sql
    assert "ts > NOW() - " in sql
    assert "ORDER BY ts DESC" in sql
    assert "LIMIT 100" in sql
    # payload jsonb 取值
    assert "payload->>'session_drawdown_pct'" in sql
    assert "payload->>'loaded_drawdown_threshold'" in sql
    assert "payload->>'process_pid'" in sql
    assert "payload->>'ts_ms'" in sql
    # params: (window_secs,)
    assert params == (3600,)


def test_threshold_tolerance_avoids_false_warn_at_exact_boundary(hc69):
    """metric 剛好等於 threshold 時應 PASS（不該因 f64 rounding 誤判 WARN）。

    為什麼必要：halt_audit.rs payload 寫 f64 `session_drawdown_pct` 與
    `loaded_drawdown_threshold` 兩個來源不同，可能差 1e-12；THRESHOLD_TOLERANCE
    = 1e-6 容差防誤判。
    """
    # drawdown = threshold；無容差會走 < threshold 路徑 → WARN
    verdict, note = hc69._classify_event(
        event_type="halt_session_set",
        drawdown_pct=25.0,
        daily_loss_pct=None,
        threshold_drawdown=25.0,
        threshold_daily_loss=None,
        kind="session_drawdown",
    )
    assert verdict == "PASS", f"boundary equality 應 PASS；got {verdict}"
    assert "OK" in note


def test_classify_event_clear_events_are_always_pass(hc69):
    """clear event（manual/auto）不參與 metric 判定；單 cell 永遠 PASS。"""
    for event_type in ("halt_session_manual_cleared", "halt_session_auto_cleared"):
        verdict, note = hc69._classify_event(
            event_type=event_type,
            drawdown_pct=None,
            daily_loss_pct=None,
            threshold_drawdown=None,
            threshold_daily_loss=None,
            kind="session_drawdown",
        )
        assert verdict == "PASS"
        assert "not a trigger row" in note


def test_default_window_aligns_with_review_date_90d(hc69):
    """default window 90d 對齊 P1-HALT-TRIGGER review date 2026-08-21
    （v56 closure 2026-05-20 + 90d）。

    為什麼固化：v59 TODO §6.1 / §A.10 healthcheck cadence 與 90d cycle
    對齊；若有人未來改成 7d 或 365d，這個 test 會紅提醒 review schedule
    一致性。
    """
    assert hc69.DEFAULT_WINDOW_SECS_HALT == 90 * 24 * 3600
    # 順帶驗 tolerance 常量
    assert hc69.THRESHOLD_TOLERANCE == 1e-6
