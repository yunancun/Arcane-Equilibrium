"""REF-20 Sprint A R3-T2 — POST /run/{run_id}/finalize hermetic tests.
REF-20 Sprint A R3-T2 — POST /run/{run_id}/finalize 封閉式測試。

MODULE_NOTE (EN):
    Hermetic 7-case suite for the finalize endpoint. Tests cover the
    cross-actor IDOR enum-oracle close, status guard, subprocess-still-
    running guard, missing report file, atomic xact commit, and per-fill
    writer integration.

    Cases:
      1. unknown run_id → 404 replay_run_not_found.
      2. cross-actor run_id → 404 replay_run_not_found (not 403).
      3. status='completed' (already finalized) → 409 not_finalizable.
      4. subprocess still running → 409 not_yet_completed.
      5. replay_report.json missing → 410 artifact_missing.
      6. happy path → 200 + fills_inserted + status=completed.
      7. invalid run_id shape → 400 invalid_run_id.

MODULE_NOTE (中):
    finalize endpoint 封閉式 7-case 套件。測試覆蓋跨 actor IDOR enum-oracle
    收斂、狀態守門、subprocess 仍跑守門、缺 report 檔、原子 xact commit、
    per-fill writer 整合。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md §6.R3 R3-T2
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import AuthenticatedActor  # noqa: E402
from app.main_legacy import current_actor  # noqa: E402
from app.replay_routes import replay_router  # noqa: E402


# ─── Test actors / 測試 actor ──────────────────────────────────────────


def _operator_actor_alice() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="alice",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write", "private_readonly"},
    )


def _operator_actor_bob() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="bob",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write", "private_readonly"},
    )


def _build_client(actor_factory) -> TestClient:
    app = FastAPI()
    app.include_router(replay_router)
    app.dependency_overrides[current_actor] = actor_factory
    return TestClient(app)


# ─── PG conn stubs / PG 連線 stub ─────────────────────────────────────


def _make_pg_conn_stub_unknown_run():
    """Stub: SELECT replay.run_state returns 0 row (run unknown).
    Stub：SELECT replay.run_state 0 row（run 未知）。
    """
    @contextmanager
    def _gen():
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = None  # SELECT → 0 row
        conn.cursor.return_value = cur
        yield conn
    return _gen


def _make_pg_conn_stub_cross_actor(run_id: str, expected_actor_id: str):
    """Stub: SELECT row exists but actor_id != caller (IDOR enum-oracle test)."""
    @contextmanager
    def _gen():
        conn = MagicMock()
        cur = MagicMock()
        # Row owned by 'mallory' but caller is 'alice'.
        # row 屬 'mallory' 但 caller 是 'alice'。
        cur.fetchone.return_value = (
            run_id, "mallory", "11111111-1111-1111-1111-111111111111",
            "running", None, "linux_trade_core", None,
        )
        conn.cursor.return_value = cur
        yield conn
    return _gen


def _make_pg_conn_stub_terminal_status(run_id: str, actor_id: str = "alice"):
    """Stub: SELECT row exists with status='completed' (already finalized)."""
    @contextmanager
    def _gen():
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = (
            run_id, actor_id, "11111111-1111-1111-1111-111111111111",
            "completed", None, "linux_trade_core", None,
        )
        conn.cursor.return_value = cur
        yield conn
    return _gen


def _make_pg_conn_stub_running_with_pid(
    run_id: str,
    pid: int,
    actor_id: str = "alice",
):
    """Stub: SELECT row with status='running' + pid set."""
    @contextmanager
    def _gen():
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = (
            run_id, actor_id, "11111111-1111-1111-1111-111111111111",
            "running", pid, "linux_trade_core", None,
        )
        conn.cursor.return_value = cur
        yield conn
    return _gen


def _make_pg_conn_stub_happy_path(
    run_id: str,
    actor_id: str = "alice",
    runtime_environment: str = "linux_trade_core",
):
    """Stub: SELECT row + UPDATE returning + INSERT happy path.
    Stub：SELECT row + UPDATE returning + INSERT happy path。

    fetchone sequence:
      1. SELECT run_state row
      2. SELECT strategy_name from V049
      3. UPDATE returning run_id (mark_run_finalized)
    insert calls: register_artifact_in_db (V046) + N×INSERT V050 +
                  UPDATE V045.
    """
    @contextmanager
    def _gen():
        conn = MagicMock()
        cur = MagicMock()
        # Sequence (each fetchone call):
        #   - 1st fetchone: SELECT run_state → row
        #   - 2nd fetchone: register_artifact_in_db's _table_exists probe → exists
        #   - 3rd fetchone: register_artifact_in_db RETURNING → artifact_id row
        #   - 4th fetchone: persist_replay_report SELECT strategy → ('grid_trading',)
        #   - 5th fetchone: _mark_run_finalized RETURNING → run_id row
        run_state_row = (
            run_id, actor_id, "11111111-1111-1111-1111-111111111111",
            "running", None, runtime_environment, None,
        )
        cur.fetchone.side_effect = [
            run_state_row,                         # SELECT run_state
            ("grid_trading", "BTCUSDT"),           # calibration SELECT V049
            (1,),                                  # _table_exists report_artifacts → present
            ("artifact-id-stub",),                 # register_artifact_in_db RETURNING
            ("grid_trading",),                     # SELECT strategy_name
            (run_id,),                             # _mark_run_finalized RETURNING
        ]
        cur.fetchall.return_value = []

        # rowcount per execute call sequence:
        #   - SET LOCAL statement_timeout: 0
        #   - SELECT run_state: 1
        #   - _table_exists SELECT: 1
        #   - INSERT report_artifacts: 1
        #   - SELECT strategy_name: 1
        #   - INSERT V050 fills × 2: 1, 1
        #   - UPDATE run_state: 1
        rowcount_seq = iter([0, 1, 1, 1, 1, 1, 1, 1, 1])

        def _execute(sql, params=None):
            cur.rowcount = next(rowcount_seq, 1)

        cur.execute.side_effect = _execute
        conn.cursor.return_value = cur
        yield conn
    return _gen


# ─── Replay report fixtures / replay report 固件 ──────────────────────


def _write_replay_report_fixture(
    run_id: str,
    fills: list[dict] | None = None,
) -> Path:
    """Write a valid replay_report.json in a temp output_dir.
    Returns Path to the temp output_dir (not the file).
    """
    if fills is None:
        fills = [
            {
                "ts_ms": 1717000000000,
                "symbol": "BTCUSDT",
                "side": "long",
                "qty": 1.0,
                "price": 50000.0,
                "evidence_source_tier": "synthetic_replay",
            },
            {
                "ts_ms": 1717000001000,
                "symbol": "ETHUSDT",
                "side": "long",
                "qty": 1.0,
                "price": 3000.0,
                "evidence_source_tier": "synthetic_replay",
            },
        ]

    envelope = {
        "schema_version": 1,
        "generated_at_ms": 1717000000000,
        "manifest_id": "11111111-1111-1111-1111-111111111111",
        "execution_confidence": "none",
        "result": {
            "manifest_id": "11111111-1111-1111-1111-111111111111",
            "status": "Completed",
            "execution_confidence": "none",
            "fills": fills,
            "pnl_summary": {
                "events_processed": len(fills),
                "fills_emitted": len(fills),
                "starting_balance": 10000.0,
                "ending_balance": 10100.0,
                "net_pnl": 100.0,
            },
            "diagnostics": {
                "guard_enforce_runtime_calls": 0,
                "last_action_label": "tick_pipeline_done",
                "abort_reason": None,
            },
        },
    }
    output_dir = Path(tempfile.mkdtemp(prefix=f"finalize_test_{run_id}_"))
    (output_dir / "replay_report.json").write_text(json.dumps(envelope))
    return output_dir


# ─── Case 1: unknown run_id → 404 ───────────────────────────────────


def test_finalize_unknown_run_id_404_no_oracle(monkeypatch):
    """Case 1: SELECT 0 row → 404 replay_run_not_found.
    Case 1：SELECT 0 row → 404 replay_run_not_found。
    """
    run_id = "deadbeefdeadbeefdeadbeefdeadbeef"
    monkeypatch.setattr(
        "app.replay_routes.get_pg_conn", _make_pg_conn_stub_unknown_run(),
    )

    client = _build_client(_operator_actor_alice)
    resp = client.post(f"/api/v1/replay/run/{run_id}/finalize")
    assert resp.status_code == 404, resp.text
    detail = resp.json().get("detail", {})
    assert "replay_run_not_found" in detail.get("reason_codes", [])


# ─── Case 2: cross-actor → 404 (not 403) ─────────────────────────────


def test_finalize_actor_mismatch_404_not_403(monkeypatch):
    """Case 2: cross-actor row collapses to 404 (IDOR enum-oracle close).
    Case 2：跨 actor row 收斂為 404（IDOR enum-oracle close）。
    """
    run_id = "deadbeefdeadbeefdeadbeefdeadbeef"
    monkeypatch.setattr(
        "app.replay_routes.get_pg_conn",
        _make_pg_conn_stub_cross_actor(run_id, expected_actor_id="alice"),
    )

    client = _build_client(_operator_actor_alice)
    resp = client.post(f"/api/v1/replay/run/{run_id}/finalize")
    # MUST be 404 (NOT 403). Response body unifies absent + cross-actor.
    # 必為 404（非 403）。response body 收斂 absent + 跨 actor。
    assert resp.status_code == 404, resp.text
    detail = resp.json().get("detail", {})
    assert "replay_run_not_found" in detail.get("reason_codes", [])
    # Response message MUST NOT leak the existence of the row.
    # response message 不可洩露 row 存在。
    assert "owned by another actor" not in resp.text.lower()
    assert "alice" in resp.text or "deadbeef" in resp.text  # OK: caller's own info


# ─── Case 3: already completed → 409 ─────────────────────────────────


def test_finalize_already_completed_409(monkeypatch):
    """Case 3: status='completed' → 409 replay_run_not_finalizable.
    Case 3：status='completed' → 409 replay_run_not_finalizable。
    """
    run_id = "11112222111122221111222211112222"
    monkeypatch.setattr(
        "app.replay_routes.get_pg_conn",
        _make_pg_conn_stub_terminal_status(run_id, actor_id="alice"),
    )

    client = _build_client(_operator_actor_alice)
    resp = client.post(f"/api/v1/replay/run/{run_id}/finalize")
    assert resp.status_code == 409, resp.text
    detail = resp.json().get("detail", {})
    assert "replay_run_not_finalizable" in detail.get("reason_codes", [])


# ─── Case 4: subprocess still running → 409 ──────────────────────────


def test_finalize_subprocess_still_running_409(monkeypatch):
    """Case 4: pid alive + status='running' → 409 replay_run_not_yet_completed.
    Case 4：pid 還活著 + status='running' → 409 replay_run_not_yet_completed。
    """
    run_id = "33334444333344443333444433334444"
    monkeypatch.setattr(
        "app.replay_routes.get_pg_conn",
        _make_pg_conn_stub_running_with_pid(run_id, pid=99999, actor_id="alice"),
    )
    # Mock verify_replay_runner_pid → alive=True.
    # mock verify_replay_runner_pid → alive=True。
    monkeypatch.setattr(
        "app.replay_routes._verify_replay_runner_pid",
        lambda pid: (True, None),
    )

    client = _build_client(_operator_actor_alice)
    resp = client.post(f"/api/v1/replay/run/{run_id}/finalize")
    assert resp.status_code == 409, resp.text
    detail = resp.json().get("detail", {})
    assert "replay_run_not_yet_completed" in detail.get("reason_codes", [])


# ─── Case 5: missing report file → 410 ──────────────────────────────


def test_finalize_report_artifact_missing_410(monkeypatch, tmp_path):
    """Case 5: replay_report.json absent under output_dir → 410.
    Case 5：output_dir 下無 replay_report.json → 410。
    """
    run_id = "55556666555566665555666655556666"
    monkeypatch.setattr(
        "app.replay_routes.get_pg_conn",
        _make_pg_conn_stub_running_with_pid(run_id, pid=0, actor_id="alice"),
    )
    # Empty output_dir (no replay_report.json).
    # 空 output_dir（無 replay_report.json）。
    monkeypatch.setattr(
        "app.replay_routes._resolve_artifact_output_dir",
        lambda rid: tmp_path,
    )
    # Override allowlist guard to accept temp path.
    # 覆寫 allowlist 守門接受 temp path。
    monkeypatch.setattr(
        "app.replay_routes._artifact_path_within_allowlist",
        lambda p: (True, None),
    )

    client = _build_client(_operator_actor_alice)
    resp = client.post(f"/api/v1/replay/run/{run_id}/finalize")
    assert resp.status_code == 410, resp.text
    detail = resp.json().get("detail", {})
    assert "replay_report_artifact_missing" in detail.get("reason_codes", [])


# ─── Case 6: happy path → 200 ────────────────────────────────────────


def test_finalize_happy_path_inserts_artifact_and_fills_and_marks_completed(
    monkeypatch,
):
    """Case 6: happy path completes; response carries fills_inserted + completed.
    Case 6：happy path 完成；response 帶 fills_inserted + completed。
    """
    run_id = "77778888777788887777888877778888"
    output_dir = _write_replay_report_fixture(run_id)
    try:
        monkeypatch.setattr(
            "app.replay_routes.get_pg_conn",
            _make_pg_conn_stub_happy_path(run_id, actor_id="alice"),
        )
        monkeypatch.setattr(
            "app.replay_routes._resolve_artifact_output_dir",
            lambda rid: output_dir,
        )
        monkeypatch.setattr(
            "app.replay_routes._artifact_path_within_allowlist",
            lambda p: (True, None),
        )
        # No subprocess pid set → skip verify_replay_runner_pid.
        # 無 subprocess pid → 跳過 verify_replay_runner_pid。

        client = _build_client(_operator_actor_alice)
        resp = client.post(f"/api/v1/replay/run/{run_id}/finalize")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["status"] == "completed"
        assert data["run_id"] == run_id
        assert data["fills_inserted"] == 2
        assert data["fills_skipped"] == 0
        assert data["report_artifact_registered"] is True
    finally:
        # Cleanup
        for f in output_dir.iterdir():
            try:
                f.unlink()
            except OSError:
                pass
        try:
            output_dir.rmdir()
        except OSError:
            pass


# ─── Case 7: invalid run_id shape → 400 ──────────────────────────────


def test_finalize_invalid_run_id_shape_400(monkeypatch):
    """Case 7: run_id with invalid char → 400 replay_invalid_run_id.
    Case 7：run_id 含非法字元 → 400 replay_invalid_run_id。
    """
    # No PG stub needed (validation fires before xact open).
    # 不需 PG stub（驗證在 xact open 前觸發）。
    bad_run_id = "$$$$" * 8  # 32 chars but not hex
    client = _build_client(_operator_actor_alice)
    resp = client.post(f"/api/v1/replay/run/{bad_run_id}/finalize")
    assert resp.status_code == 400, resp.text
    detail = resp.json().get("detail", {})
    assert "replay_invalid_run_id" in detail.get("reason_codes", [])


# ─── Case 9: multi-worker race no V046 dual-INSERT (R3 round 2 M-1) ──


def test_finalize_multi_worker_race_no_v046_dual_insert(monkeypatch):
    """REF-20 Sprint A R3 round 2 fix M-1: multi-worker uvicorn race must
    produce exactly 1 V046 row even when 2 finalize calls hit the same
    run_id concurrently.

    REF-20 Sprint A R3 round 2 fix M-1：multi-worker race 並發 finalize
    同 run_id 必只產生 1 個 V046 row。

    Hermetic simulation strategy:
      1. Worker A's PG conn stub is the happy path (SELECT FOR UPDATE
         returns status='running'; commit happens at end).
      2. Worker B's PG conn stub simulates the post-A-commit state:
         SELECT FOR UPDATE blocked + serialized → returns
         status='completed' → routes to 409 not_finalizable WITHOUT
         calling register_artifact_in_db / persist_replay_report /
         _mark_run_finalized.

    Single-process pytest cannot exercise true row-level locking, but it
    CAN verify that worker B's branch (status already terminal) skips
    the V046 INSERT entirely. The FOR UPDATE clause itself is verified
    by the SQL string assertion at the bottom.

    封閉式模擬策略：
      1. Worker A 的 PG conn stub 走 happy path（SELECT FOR UPDATE 回
         status='running'；最後 commit）。
      2. Worker B 的 PG conn stub 模擬 A commit 後狀態：SELECT FOR UPDATE
         被 block 序列化後回 status='completed' → 走 409
         not_finalizable，不呼 register_artifact_in_db /
         persist_replay_report / _mark_run_finalized。

    單行程 pytest 無法觸發真 row-level lock，但能驗 worker B 的分支
    （status 已終態）完全跳過 V046 INSERT。FOR UPDATE 子句由最後 SQL 文字
    比對驗證。
    """
    run_id = "abcd1234abcd1234abcd1234abcd1234"
    output_dir = _write_replay_report_fixture(run_id)
    try:
        # ── Worker A: happy path conn stub ────────────────────────────
        # Reuse the existing happy_path stub. Counts execute calls so we
        # can verify register_artifact_in_db (V046 INSERT) fired once.
        # 重用既有 happy_path stub。計 execute 呼叫次數以驗
        # register_artifact_in_db（V046 INSERT）只發一次。
        worker_a_v046_inserts: list = []
        worker_a_v050_inserts: list = []
        worker_a_v045_updates: list = []

        @contextmanager
        def _conn_a():
            conn = MagicMock()
            cur = MagicMock()
            run_state_row = (
                run_id, "alice",
                "11111111-1111-1111-1111-111111111111",
                "running", None, "linux_trade_core", None,
            )
            cur.fetchone.side_effect = [
                run_state_row,                  # SELECT FOR UPDATE
                ("grid_trading", "BTCUSDT"),    # calibration SELECT V049
                (1,),                           # _table_exists
                ("artifact-id-stub",),          # register RETURNING
                ("grid_trading",),              # SELECT strategy_name
                (run_id,),                      # _mark_run_finalized RETURNING
            ]
            cur.fetchall.return_value = []
            rowcount_seq = iter([0, 1, 1, 1, 1, 1, 1, 1, 1])

            def _execute(sql, params=None):
                sql_text = str(sql)
                if "INSERT INTO replay.report_artifacts" in sql_text:
                    worker_a_v046_inserts.append(True)
                elif "INSERT INTO replay.simulated_fills" in sql_text:
                    worker_a_v050_inserts.append(True)
                elif "UPDATE replay.run_state" in sql_text:
                    worker_a_v045_updates.append(True)
                cur.rowcount = next(rowcount_seq, 1)

            cur.execute.side_effect = _execute
            conn.cursor.return_value = cur
            yield conn

        # ── Worker B: post-A-commit terminal-status stub ──────────────
        # After worker A commits, worker B's SELECT FOR UPDATE unblocks
        # and reads status='completed'. The route routes B to 409
        # not_finalizable WITHOUT touching V046/V050/V045 again.
        # worker A commit 後，worker B 的 SELECT FOR UPDATE 解除 block
        # 讀到 status='completed'。route 走 B 至 409 not_finalizable，
        # 不再碰 V046/V050/V045。
        worker_b_v046_inserts: list = []
        worker_b_v050_inserts: list = []
        worker_b_v045_updates: list = []

        @contextmanager
        def _conn_b():
            conn = MagicMock()
            cur = MagicMock()
            cur.fetchone.return_value = (
                run_id, "alice",
                "11111111-1111-1111-1111-111111111111",
                "completed",  # already finalized by worker A
                None, "linux_trade_core", None,
            )

            def _execute(sql, params=None):
                sql_text = str(sql)
                if "INSERT INTO replay.report_artifacts" in sql_text:
                    worker_b_v046_inserts.append(True)
                elif "INSERT INTO replay.simulated_fills" in sql_text:
                    worker_b_v050_inserts.append(True)
                elif "UPDATE replay.run_state" in sql_text:
                    worker_b_v045_updates.append(True)
                cur.rowcount = 0

            cur.execute.side_effect = _execute
            conn.cursor.return_value = cur
            yield conn

        monkeypatch.setattr(
            "app.replay_routes._resolve_artifact_output_dir",
            lambda rid: output_dir,
        )
        monkeypatch.setattr(
            "app.replay_routes._artifact_path_within_allowlist",
            lambda p: (True, None),
        )

        client = _build_client(_operator_actor_alice)

        # ── Worker A request ──
        monkeypatch.setattr("app.replay_routes.get_pg_conn", _conn_a)
        resp_a = client.post(f"/api/v1/replay/run/{run_id}/finalize")
        assert resp_a.status_code == 200, resp_a.text
        body_a = resp_a.json()
        assert body_a["data"]["status"] == "completed"

        # ── Worker B request (simulated post-A-commit state) ──
        monkeypatch.setattr("app.replay_routes.get_pg_conn", _conn_b)
        resp_b = client.post(f"/api/v1/replay/run/{run_id}/finalize")
        assert resp_b.status_code == 409, resp_b.text
        detail_b = resp_b.json().get("detail", {})
        assert "replay_run_not_finalizable" in detail_b.get("reason_codes", [])

        # ── Cumulative invariants ──
        # V046 INSERT must fire exactly 1× total (worker A only).
        # V050 INSERT must fire ≥ 1× total (per-fill loop in worker A only).
        # V045 UPDATE must fire exactly 1× total (worker A only).
        # V046 INSERT 累計必恰 1×（僅 worker A）；
        # V050 INSERT 累計必 ≥ 1×（worker A 每 fill 一次迴圈）；
        # V045 UPDATE 累計必恰 1×（僅 worker A）。
        assert len(worker_a_v046_inserts) == 1, (
            f"worker A V046 INSERT count={len(worker_a_v046_inserts)}, expected 1"
        )
        assert len(worker_a_v050_inserts) >= 1, (
            f"worker A V050 INSERT count={len(worker_a_v050_inserts)}, expected >= 1"
        )
        assert len(worker_a_v045_updates) == 1, (
            f"worker A V045 UPDATE count={len(worker_a_v045_updates)}, expected 1"
        )
        assert len(worker_b_v046_inserts) == 0, (
            f"worker B V046 INSERT count={len(worker_b_v046_inserts)}, "
            "expected 0 (status terminal)"
        )
        assert len(worker_b_v050_inserts) == 0, (
            f"worker B V050 INSERT count={len(worker_b_v050_inserts)}, "
            "expected 0 (status terminal)"
        )
        assert len(worker_b_v045_updates) == 0, (
            f"worker B V045 UPDATE count={len(worker_b_v045_updates)}, "
            "expected 0 (status terminal)"
        )

        # ── FOR UPDATE clause is present in the source SQL ──
        # Source-level grep verifies the lock clause survives refactor.
        # 源碼層 grep 驗 lock 子句不被 refactor 移除。
        from replay import run_finalize_route as _fr_mod
        import inspect
        src = inspect.getsource(_fr_mod._select_run_state_for_finalize_sync)
        assert "FOR UPDATE" in src, (
            "M-1 fix regression: SELECT FOR UPDATE clause missing from "
            "_select_run_state_for_finalize_sync"
        )
    finally:
        for f in output_dir.iterdir():
            try:
                f.unlink()
            except OSError:
                pass
        try:
            output_dir.rmdir()
        except OSError:
            pass


def test_finalize_calibration_imports_are_runtime_cwd_safe():
    """Regression: API workers run from control_api_v1, where program_code is absent."""
    from replay import run_finalize_route as _fr_mod
    import inspect

    src = inspect.getsource(_fr_mod._compute_and_persist_calibration)
    assert "from replay import calibration_label" in src
    assert "from replay import experiment_registry" in src
    assert "from replay.calibration_label import FillRecord" in src
    assert "program_code.exchange_connectors" not in src


def test_finalize_registers_explicit_replay_report_artifact_type():
    """V066: finalize must register replay_report, not legacy pnl_summary."""
    from replay import run_finalize_route as _fr_mod

    assert _fr_mod.ARTIFACT_TYPE_REPLAY_REPORT == "replay_report"


# ─── Case 8: atomic xact rollback on writer failure ──────────────────


def test_finalize_atomic_xact_rollback_on_writer_failure(monkeypatch):
    """Case 8: simulated_fills writer raises → run_state stays 'running'.
    Case 8：simulated_fills writer 拋例 → run_state 保持 'running'。

    Bulk INSERT mid-failure must rollback so report_artifacts row is also
    reverted (atomic xact invariant).
    INSERT 過程拋例必 rollback 使 report_artifacts row 也回退（原子 xact 不變量）。
    """
    run_id = "99990000999900009999000099990000"
    output_dir = _write_replay_report_fixture(run_id)
    try:
        # Build a stub conn whose cursor raises on the V050 INSERT call.
        # 構造 cursor 在 V050 INSERT 時拋例的 conn stub。
        conn = MagicMock()
        cur = MagicMock()
        rollback_calls: list = []
        commit_calls: list = []
        conn.rollback.side_effect = lambda: rollback_calls.append(True)
        conn.commit.side_effect = lambda: commit_calls.append(True)

        run_state_row = (
            run_id, "alice", "11111111-1111-1111-1111-111111111111",
            "running", None, "linux_trade_core", None,
        )
        cur.fetchone.side_effect = [
            run_state_row,           # SELECT run_state
            ("grid_trading", "BTCUSDT"),  # calibration SELECT V049
            (1,),                    # _table_exists report_artifacts
            ("artifact-id-stub",),   # register_artifact_in_db RETURNING
            ("grid_trading",),       # SELECT strategy_name
            # No more fetchones expected; INSERT raises.
            # 之後 fetchone 不應被呼叫；INSERT 拋例。
        ]
        cur.fetchall.return_value = []

        call_idx = [0]

        def _execute(sql, params=None):
            call_idx[0] += 1
            sql_text = str(sql)
            if "INSERT INTO replay.simulated_fills" in sql_text:
                raise RuntimeError("simulated PG INSERT failure")
            cur.rowcount = 1

        cur.execute.side_effect = _execute
        conn.cursor.return_value = cur

        @contextmanager
        def _stub_conn():
            yield conn

        monkeypatch.setattr("app.replay_routes.get_pg_conn", _stub_conn)
        monkeypatch.setattr(
            "app.replay_routes._resolve_artifact_output_dir",
            lambda rid: output_dir,
        )
        monkeypatch.setattr(
            "app.replay_routes._artifact_path_within_allowlist",
            lambda p: (True, None),
        )

        client = _build_client(_operator_actor_alice)
        resp = client.post(f"/api/v1/replay/run/{run_id}/finalize")
        # Failure must be reported (5xx), not silently masked.
        # 失敗必須被回報（5xx），不可靜默 mask。
        assert resp.status_code == 503, resp.text
        # Rollback was called; commit was NOT.
        # 必呼 rollback；不可呼 commit。
        assert len(rollback_calls) >= 1
        assert len(commit_calls) == 0
    finally:
        for f in output_dir.iterdir():
            try:
                f.unlink()
            except OSError:
                pass
        try:
            output_dir.rmdir()
        except OSError:
            pass
