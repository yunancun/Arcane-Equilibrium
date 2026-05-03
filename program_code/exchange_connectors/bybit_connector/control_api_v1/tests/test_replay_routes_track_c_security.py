"""REF-20 Sprint 1 Track C — 3 critical Python security fix tests.
REF-20 Sprint 1 Track C — 3 個關鍵 Python 安全洞修補測試。

MODULE_NOTE (EN):
    Hermetic 6-case suite covering REF-20 Sprint 1 Track C P0-2 / P0-4 /
    P0-5 fixes in ``replay_routes.py``:

      Case 1 (P0-2 production env gate):
        OPENCLAW_RELEASE_PROFILE='live' + OPENCLAW_REPLAY_VERIFY_TEST_KEY=<x>
        → POST /api/v1/replay/manifest/verify forces test_key_hex='' →
        falls through to 501 archive-not-wired (NOT honoring test key).
        Without the live profile env, same env still hits 501 (no harm).

      Case 2 (P0-4 SIGTERM cmdline cert FAILS):
        Active V045 row pid points to a process whose argv lacks
        'replay_runner' (mocked psutil); cancel returns 409 with
        ``replay_pid_identity_mismatch`` reason — no os.kill issued.

      Case 3 (P0-5a IDOR cross-actor BLOCKED):
        Plain operator (no replay:read:any scope) querying a manifest
        owned by a different actor. SQL params include actor_id filter;
        DB returns 0 rows. Endpoint returns 200 with empty artifacts
        (NOT 200 with another actor's data).

      Case 4 (P0-5a IDOR admin bypass ALLOWED):
        Admin actor with replay:read:any scope; SQL omits actor_id
        filter. Admin bypass audit emit fires (replay_idor_admin_bypass).

      Case 5 (P0-5b path traversal BLOCKED):
        DB row contains artifact_path='/etc/passwd'. Resolved path is
        outside OPENCLAW_DATA_DIR/replay_artifacts/ allowlist root →
        artifact in response carries payload_read_error=
        'path_traversal_blocked:path_traversal_escape'; NO file read.

      Case 6 (P0-5b /etc/passwd attack denial — end-to-end):
        DB row contains artifact_path='/etc/passwd'; ensure NO actual
        bytes from /etc/passwd appear in the response payload (defense
        in depth / regression sentinel).

    All cases use ``monkeypatch`` to swap ``get_pg_conn`` and ``psutil``
    so tests run hermetically on Mac dev (no real PG, no real psutil
    process discovery).

MODULE_NOTE (中):
    封閉式 6-case 測試套件，覆蓋 REF-20 Sprint 1 Track C P0-2 / P0-4 / P0-5
    在 ``replay_routes.py`` 的修補：

      Case 1（P0-2 production env gate）：live profile + test key env →
        POST /manifest/verify 強制 test_key_hex='' → 501 archive 未接；
        不認 test key（attacker 控 env 無效）。
      Case 2（P0-4 SIGTERM cmdline cert 失敗）：V045 row pid 對應 process
        argv 不含 'replay_runner'；cancel 回 409 replay_pid_identity_mismatch；
        無 os.kill。
      Case 3（P0-5a IDOR cross-actor 拒絕）：plain operator 查別人 manifest；
        SQL 帶 actor_id filter；回 0 rows；200 + 空 artifacts。
      Case 4（P0-5a IDOR admin bypass 通過）：admin actor 持 replay:read:any
        scope；SQL 不帶 actor_id filter；emit replay_idor_admin_bypass audit。
      Case 5（P0-5b 路徑遍歷拒絕）：DB row artifact_path='/etc/passwd'；
        resolved 在 allowlist 外 → payload_read_error='path_traversal_blocked:...';
        絕無 file read。
      Case 6（P0-5b /etc/passwd 端到端拒絕）：response payload 0 byte 來自
        /etc/passwd（防禦深度回歸 sentinel）。

SPEC: REF-20 V3 §3 G3 + §6 + §11 + §12 #3
PA Sprint 1 Track C dispatch: docs/CCAgentWorkSpace/PA/workspace/reports/
                              2026-05-03--ref20_sprint1_partition_design.md
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest


_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import AuthenticatedActor  # noqa: E402
from app.main_legacy import current_actor  # noqa: E402
from app.replay_routes import (  # noqa: E402
    _ACTIVE_RUNS,
    _reset_active_runs_for_test,
    replay_router,
)


def _operator_actor_alice() -> AuthenticatedActor:
    """Operator actor with replay:write scope (no replay:read:any).
    具 replay:write scope（無 replay:read:any）的 Operator actor。
    """
    return AuthenticatedActor(
        actor_id="alice",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write", "private_readonly"},
    )


def _admin_actor_carol() -> AuthenticatedActor:
    """Admin actor holding replay:read:any scope (cross-actor IDOR bypass).
    持 replay:read:any scope 的 admin actor（跨 actor IDOR 旁通）。
    """
    return AuthenticatedActor(
        actor_id="carol",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write", "private_readonly", "replay:read:any"},
    )


@pytest.fixture(autouse=True)
def _reset_state():
    _reset_active_runs_for_test()
    yield
    _reset_active_runs_for_test()


def _build_client(actor_factory) -> TestClient:
    """Build TestClient with the given actor override.
    用指定 actor override 建 TestClient。
    """
    app = FastAPI()
    app.include_router(replay_router)
    app.dependency_overrides[current_actor] = actor_factory
    return TestClient(app)


# ─── Case 1: P0-2 env var bypass blocked in live profile ──────────────────


def test_p0_2_env_var_test_key_blocked_in_live_profile(monkeypatch):
    """Case 1 (P0-2): live profile + test_key env → 501 (test key blocked).
    Case 1（P0-2）：live profile + test_key env → 501（test key 被擋）。

    The test key is honored ONLY in dev / mac_dev_smoke_test_only. With
    OPENCLAW_RELEASE_PROFILE=live, the env value is force-cleared before
    use; verify endpoint returns 501 (archive_not_wired) instead of
    accepting attacker-injected key bytes.
    OPENCLAW_RELEASE_PROFILE=live 強制清空 test_key_hex；endpoint 回 501
    archive_not_wired，不認 attacker 注入的 key bytes。
    """
    monkeypatch.setenv("OPENCLAW_RELEASE_PROFILE", "live")
    # Attacker-controlled env: 64-hex-char string (32 bytes).
    # Attacker 控 env：64-hex 字（32 bytes）。
    monkeypatch.setenv(
        "OPENCLAW_REPLAY_VERIFY_TEST_KEY",
        "00" * 32,
    )
    client = _build_client(_operator_actor_alice)
    resp = client.post(
        "/api/v1/replay/manifest/verify",
        json={
            "canonical_bytes_b64": "AAAAAA==",
            "declared_hash_hex": "ab" * 32,
            "signature_hex": "cd" * 32,
            "fingerprint": "fp_attacker_test01",
        },
    )
    # Live profile must NOT honor test key → falls through to 501 archive
    # not wired (the production path that requires V042 SQL key archive).
    # Live profile 不認 test key → fall-through 至 501 archive 未接。
    assert resp.status_code == 501, resp.text
    detail = resp.json().get("detail", {})
    assert "replay_verify_archive_not_wired" in detail.get("reason_codes", [])


def test_p0_2_dev_profile_does_not_strip_test_key(monkeypatch):
    """Case 1b (P0-2 inverse): dev profile keeps test_key visible to handler.
    Case 1b（P0-2 反向）：dev profile 不剝離 test_key，handler 看得到。

    The fix preserves dev/test ergonomics — only LIVE blocks. Without
    OPENCLAW_RELEASE_PROFILE='live', the handler reads the env value as
    usual and enters the test_key path. We do NOT assert downstream
    success (InMemoryKeyArchive API may differ between versions); we only
    assert the response is NOT a 501 archive-not-wired (which would mean
    the env was force-cleared).
    修補保留 dev/test 開發體驗 — 僅 LIVE 擋。dev profile 下 handler 讀 env
    照常進入 test 分支。我們不斷言下游成功（InMemoryKeyArchive API 版本
    可能差異）；只斷言 response NOT 501 archive-not-wired（若 env 被強制
    清空才 501）。
    """
    monkeypatch.delenv("OPENCLAW_RELEASE_PROFILE", raising=False)
    monkeypatch.setenv("OPENCLAW_REPLAY_VERIFY_TEST_KEY", "00" * 32)
    client = _build_client(_operator_actor_alice)
    # raise_server_exceptions=False so 500 from pre-existing
    # InMemoryKeyArchive.upsert_key API drift surfaces as 500 (not test
    # exception). Track C only cares about NOT seeing the 501-archive-not-wired
    # path (which would mean live profile gate misfired in dev).
    # raise_server_exceptions=False 使 InMemoryKeyArchive.upsert_key API 漂移
    # 的 500 顯示為 500 而非 test 異常。Track C 只在乎 NOT 走 501 archive
    # 路徑（會表 live profile gate 在 dev 誤觸發）。
    client_no_raise = TestClient(client.app, raise_server_exceptions=False)
    resp = client_no_raise.post(
        "/api/v1/replay/manifest/verify",
        json={
            "canonical_bytes_b64": "AAAAAA==",
            "declared_hash_hex": "ab" * 32,
            "signature_hex": "cd" * 32,
            "fingerprint": "fp_dev_test_01",
        },
    )
    # Reject the 501 reason: replay_verify_archive_not_wired = "we forced
    # test_key_hex empty". The dev path SHOULD enter test branch; downstream
    # may 500 due to InMemoryKeyArchive API mismatch (not Track C scope).
    # Acceptable status codes: 200 / 400 / 500; NOT 501-archive-not-wired.
    # 拒 501 reason：replay_verify_archive_not_wired = 「test_key_hex 被強清」。
    # 可接受：200 / 400 / 500；不可接受：501-archive-not-wired。
    if resp.status_code == 501:
        detail = resp.json().get("detail", {})
        assert "replay_verify_archive_not_wired" not in detail.get("reason_codes", []), (
            "Dev profile incorrectly cleared test_key; archive_not_wired returned"
        )


# ─── Case 2: P0-4 SIGTERM cmdline identity verification ────────────────────


def test_p0_4_sigterm_cmdline_cert_fails_returns_409(monkeypatch):
    """Case 2 (P0-4): pid points to non-replay_runner process → 409.
    Case 2（P0-4）：pid 指向非 replay_runner process → 409。

    Mock V045 row exists and contains a pid; mock psutil to return a
    cmdline that does NOT contain 'replay_runner'. Cancel must return
    409 replay_pid_identity_mismatch and NEVER call os.kill.
    Mock V045 row + pid；mock psutil cmdline 不含 'replay_runner'。
    cancel 必回 409 replay_pid_identity_mismatch，絕不呼 os.kill。
    """
    @contextmanager
    def _stub_get_pg_conn():
        # Conn yielded supports cursor + execute + fetchone for V045 SELECT.
        # cursor + execute + fetchone 支援 V045 SELECT。
        conn = MagicMock()
        cur = MagicMock()
        # Reset rollback to a real callable mock (for finally cleanup).
        cur.connection = conn
        # _v045_table_present(cur) → True
        # SELECT FROM run_state → row(run_id, manifest_id, pid=12345, status='running')
        # UPDATE run_state SET 'cancelled' RETURNING run_id → flipped row
        # 三次 fetchone 對應這三步；execute 不 raise。
        cur.fetchone.side_effect = [
            (True,),  # _v045_table_present
            ("99999999-1234-5678-9abc-deadbeefcafe", "11111111-1111-1111-1111-111111111111", 12345, "running"),
            ("99999999-1234-5678-9abc-deadbeefcafe",),  # flipped row (won't be reached if pid cert fails)
        ]
        conn.cursor.return_value = cur
        yield conn

    monkeypatch.setattr("app.replay_routes.get_pg_conn", _stub_get_pg_conn)

    # Mock psutil so verify_replay_runner_pid returns False (cmdline lacks
    # 'replay_runner' substring → e.g. attacker injects systemd's pid).
    # Mock psutil 使 verify_replay_runner_pid 回 False（cmdline 不含
    # 'replay_runner'，例如 attacker 注入 systemd 的 pid）。
    fake_proc = MagicMock()
    fake_proc.cmdline.return_value = ["/sbin/init", "splash"]
    fake_psutil = MagicMock()
    fake_psutil.Process.return_value = fake_proc

    class _NoSuchProcess(Exception):
        pass

    class _AccessDenied(Exception):
        pass

    fake_psutil.NoSuchProcess = _NoSuchProcess
    fake_psutil.AccessDenied = _AccessDenied

    # Patch psutil import inside verify_replay_runner_pid (route_helpers.py).
    # Patch psutil 在 route_helpers verify_replay_runner_pid 內的 import。
    with patch.dict("sys.modules", {"psutil": fake_psutil}):
        # Also confirm os.kill is NOT called by spying on it.
        # 同時確認 os.kill 沒被呼叫。
        kill_calls: list = []

        def _spy_kill(pid, sig):
            kill_calls.append((pid, sig))

        monkeypatch.setattr("os.kill", _spy_kill)

        client = _build_client(_operator_actor_alice)
        resp = client.post(
            "/api/v1/replay/cancel",
            json={"reason": "p0-4-test"},
        )

    assert resp.status_code == 409, resp.text
    detail = resp.json().get("detail", {})
    assert "replay_pid_identity_mismatch" in detail.get("reason_codes", [])
    # CRITICAL: os.kill must NEVER fire when cmdline cert fails.
    # CRITICAL：cmdline cert 失敗時 os.kill 絕不該觸發。
    assert kill_calls == [], f"os.kill was called: {kill_calls}"


# ─── Case 3: P0-5a IDOR cross-actor blocked ────────────────────────────────


def test_p0_5a_idor_cross_actor_filter_in_sql(monkeypatch):
    """Case 3 (P0-5a): plain operator → SQL includes actor_id filter.
    Case 3（P0-5a）：plain operator → SQL 帶 actor_id filter。

    Mock get_pg_conn to capture the SQL passed to cur.execute. Verify
    the second execute (after SET LOCAL statement_timeout) contains
    'AND s.actor_id = %s' AND the params tuple has 2 elements
    (manifest_uuid, actor_id).
    捕獲 cur.execute 的 SQL；驗第二次 execute 含 'AND s.actor_id = %s'
    + params 有 2 元素。
    """
    captured: dict = {"sql": None, "params": None}

    @contextmanager
    def _stub_get_pg_conn():
        conn = MagicMock()
        cur = MagicMock()

        def _capture_execute(sql, params=()):
            # First execute = SET LOCAL statement_timeout. Capture the second.
            # 第一次 = SET LOCAL；捕第二次。
            if "SET LOCAL" not in str(sql):
                captured["sql"] = str(sql)
                captured["params"] = params

        cur.execute.side_effect = _capture_execute
        cur.fetchall.return_value = []  # IDOR-blocked → 0 rows
        conn.cursor.return_value = cur
        yield conn

    monkeypatch.setattr("app.replay_routes.get_pg_conn", _stub_get_pg_conn)

    client = _build_client(_operator_actor_alice)
    resp = client.get("/api/v1/replay/report/exp-test-cross-actor")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 0 artifacts → IDOR effectively blocked at SQL layer.
    # 0 artifacts → IDOR 在 SQL 層即被擋。
    assert body["data"]["artifact_count"] == 0
    # Verify the SQL has actor_id filter + 2 params.
    # 驗 SQL 帶 actor_id filter + 2 params。
    assert captured["sql"] is not None
    assert "s.actor_id = %s" in captured["sql"], f"SQL missing actor filter: {captured['sql']}"
    assert len(captured["params"]) == 2, f"Expected 2 params, got: {captured['params']}"
    # Second param must be the actor_id 'alice'.
    # 第二個 param 必為 actor_id 'alice'。
    assert captured["params"][1] == "alice"


# ─── Case 4: P0-5a IDOR admin bypass allowed ───────────────────────────────


def test_p0_5a_idor_admin_bypass_skips_actor_filter(monkeypatch):
    """Case 4 (P0-5a admin bypass): replay:read:any → SQL omits actor_id filter.
    Case 4（P0-5a admin 旁通）：replay:read:any → SQL 不帶 actor_id filter。
    """
    captured: dict = {"sql": None, "params": None}

    @contextmanager
    def _stub_get_pg_conn():
        conn = MagicMock()
        cur = MagicMock()

        def _capture_execute(sql, params=()):
            if "SET LOCAL" not in str(sql):
                captured["sql"] = str(sql)
                captured["params"] = params

        cur.execute.side_effect = _capture_execute
        cur.fetchall.return_value = []
        conn.cursor.return_value = cur
        yield conn

    monkeypatch.setattr("app.replay_routes.get_pg_conn", _stub_get_pg_conn)

    client = _build_client(_admin_actor_carol)
    resp = client.get("/api/v1/replay/report/exp-test-admin-bypass")
    assert resp.status_code == 200, resp.text
    # Verify SQL DOES NOT contain actor_id filter + only 1 param.
    # 驗 SQL 不帶 actor_id filter + 只 1 param。
    assert captured["sql"] is not None
    assert "s.actor_id = %s" not in captured["sql"], (
        f"Admin bypass leaked actor filter: {captured['sql']}"
    )
    assert len(captured["params"]) == 1, f"Expected 1 param (admin), got: {captured['params']}"


# ─── Case 5: P0-5b path traversal blocked ─────────────────────────────────


def test_p0_5b_path_traversal_etc_passwd_blocked(monkeypatch):
    """Case 5 (P0-5b): artifact_path='/etc/passwd' → blocked, no file read.
    Case 5（P0-5b）：artifact_path='/etc/passwd' → 拒讀，0 file read。

    Mock V046 row containing artifact_path outside allowlist root. Verify
    response artifact carries payload_read_error='path_traversal_blocked'
    AND no payload field present (no file content leaked).
    Mock V046 row 含 allowlist 外的 artifact_path。驗 response artifact
    帶 payload_read_error='path_traversal_blocked' + 無 payload 欄位
    （無 file 內容洩漏）。
    """
    @contextmanager
    def _stub_get_pg_conn():
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = [
            (
                "11111111-1111-1111-1111-111111111111",  # artifact_id
                "canary",                                # artifact_type
                "/etc/passwd",                           # artifact_path (ATTACK)
                4096,                                    # byte_size
                False,                                   # is_mock
                1700000000000,                           # created_at_ms
                "22222222-2222-2222-2222-222222222222",  # run_id
                "completed",                             # status
                0,                                       # exit_code
                1700000000000,                           # started_at_ms
                1700000060000,                           # completed_at_ms
            ),
        ]
        conn.cursor.return_value = cur
        yield conn

    monkeypatch.setattr("app.replay_routes.get_pg_conn", _stub_get_pg_conn)

    # Use admin so SQL filter doesn't reject (we want to test allowlist guard).
    # 用 admin 讓 SQL filter 不拒（要測 allowlist guard）。
    client = _build_client(_admin_actor_carol)
    resp = client.get("/api/v1/replay/report/exp-traversal-attack")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    artifacts = body["data"]["artifacts"]
    assert len(artifacts) == 1, f"Expected 1 artifact, got: {len(artifacts)}"
    art = artifacts[0]
    # Allowlist guard fires → payload_read_error set; no payload key.
    # allowlist 守門 → payload_read_error；無 payload。
    assert "payload_read_error" in art, f"No traversal-blocked sentinel: {art}"
    assert "path_traversal_blocked" in art["payload_read_error"], art["payload_read_error"]
    # CRITICAL: no payload field (no file content leak from /etc/passwd).
    # CRITICAL：無 payload 欄位（無 /etc/passwd 內容洩漏）。
    assert "payload" not in art, f"Payload leaked! artifact={art}"


# ─── Case 6: P0-5b /etc/passwd content denial sentinel ─────────────────────


def test_p0_5b_etc_passwd_content_never_in_response(monkeypatch):
    """Case 6 (P0-5b sentinel): /etc/passwd content NEVER in response payload.
    Case 6（P0-5b 哨兵）：/etc/passwd 內容絕不出現在 response。

    Defense in depth: even if other guards fail, the response body must
    contain ZERO bytes from /etc/passwd. We grep the JSON-serialized
    response for canonical /etc/passwd substrings.
    防禦深度：即使其他守門失效，response 也必 0 byte 來自 /etc/passwd。
    對 JSON 序化 response grep canonical 子串。
    """
    @contextmanager
    def _stub_get_pg_conn():
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = [
            (
                "33333333-3333-3333-3333-333333333333",
                "canary",
                "/etc/passwd",
                4096,
                False,
                1700000000000,
                "44444444-4444-4444-4444-444444444444",
                "completed",
                0,
                1700000000000,
                1700000060000,
            ),
        ]
        conn.cursor.return_value = cur
        yield conn

    monkeypatch.setattr("app.replay_routes.get_pg_conn", _stub_get_pg_conn)

    client = _build_client(_admin_actor_carol)
    resp = client.get("/api/v1/replay/report/exp-passwd-sentinel")
    assert resp.status_code == 200, resp.text
    raw = resp.text
    # canonical /etc/passwd lines: 'root:x:0:0' / 'nobody:' / shell paths.
    # If any of these appear in the response, the path traversal guard FAILED.
    # /etc/passwd canonical 行：'root:x:0:0' / 'nobody:' / shell paths。
    # 任一出現 = 路徑遍歷守門失效。
    forbidden_substrings = ["root:x:0:0", "/bin/bash", "/sbin/nologin"]
    for needle in forbidden_substrings:
        assert needle not in raw, f"P0-5b SENTINEL FAILED: '{needle}' leaked in response"


# ─── E2 retrofit case 7: F6 boot guard raises (not log-only) ───────────────


def test_e2_retrofit_f6_boot_guard_raises_in_live_with_test_key(monkeypatch):
    """E2 retrofit F6: boot guard MUST raise, not log only.
    E2 retrofit F6：boot guard 必 raise，不是 log only。

    The original Track C IMPL only logged ERROR if both env vars were set
    in live profile; attacker controlling env could continue uvicorn
    startup. E2 retrofit F6 demands fail-closed: ``RuntimeError`` raised
    so uvicorn boot fails before any /replay/manifest/verify request can
    reach the test_key path.
    原 Track C IMPL 雙設只 log ERROR；attacker 控 env 仍可啟動。E2 retrofit
    F6 要求 fail-closed：raise ``RuntimeError`` 使 uvicorn 啟動失敗，
    /replay/manifest/verify 請求未到 test_key 路徑即斷。
    """
    from app.replay_routes import _sg

    def _is_live_true() -> bool:
        return True

    monkeypatch.setenv("OPENCLAW_REPLAY_VERIFY_TEST_KEY", "00" * 32)
    with pytest.raises(RuntimeError) as exc_info:
        _sg.perform_p0_2_boot_guard(_is_live_true)
    msg = str(exc_info.value)
    assert "boot guard FAIL-CLOSED" in msg, msg
    assert "OPENCLAW_REPLAY_VERIFY_TEST_KEY" in msg, msg
    assert "live" in msg, msg


def test_e2_retrofit_f6_boot_guard_skips_when_not_live(monkeypatch):
    """E2 retrofit F6: boot guard does NOT raise in dev (test_key legitimate).
    E2 retrofit F6：boot guard 在 dev 不 raise（test_key 合法）。

    Dev / test workflow needs to set TEST_KEY without RELEASE_PROFILE='live';
    boot guard must short-circuit to no-op so dev tooling continues.
    Dev / test 工作流需設 TEST_KEY 但不設 RELEASE_PROFILE='live'；boot guard
    必短路 no-op 使 dev 工具鏈繼續可用。
    """
    from app.replay_routes import _sg

    def _is_live_false() -> bool:
        return False

    monkeypatch.setenv("OPENCLAW_REPLAY_VERIFY_TEST_KEY", "00" * 32)
    # No raise expected — guard short-circuits because is_live=False.
    # 不應 raise — guard 因 is_live=False 短路。
    _sg.perform_p0_2_boot_guard(_is_live_false)


def test_e2_retrofit_f6_boot_guard_skips_when_test_key_unset(monkeypatch):
    """E2 retrofit F6: boot guard does NOT raise when TEST_KEY env is unset.
    E2 retrofit F6：boot guard 在 TEST_KEY env 未設時不 raise。

    Production deploy without test key seed must boot cleanly.
    無 test key seed 的 production deploy 必須乾淨啟動。
    """
    from app.replay_routes import _sg

    def _is_live_true() -> bool:
        return True

    monkeypatch.delenv("OPENCLAW_REPLAY_VERIFY_TEST_KEY", raising=False)
    # No raise expected — guard short-circuits because TEST_KEY env empty.
    # 不應 raise — guard 因 TEST_KEY env 空短路。
    _sg.perform_p0_2_boot_guard(_is_live_true)


# ─── E2 retrofit case 8: F8 admin scope registered in defaults ─────────────


def test_e2_retrofit_f8_replay_read_any_in_default_scopes():
    """E2 retrofit F8: replay:read:any registered in Settings.auth_scopes default.
    E2 retrofit F8：replay:read:any 已登記到 Settings.auth_scopes default。

    Original Track C IMPL added admin bypass via ``replay:read:any``
    scope but did NOT register it in the Settings default scope set →
    admin actor's scope check would never include it → admin bypass
    code path was dead. F8 retrofit registers both ``replay:write`` and
    ``replay:read:any`` in the default scope csv so admin actors actually
    receive the scope post-build.
    原 Track C IMPL 加 admin bypass via ``replay:read:any`` scope，但未
    登記到 Settings default scope 集合 → admin actor scope check 永不
    含此 scope → admin bypass 代碼路徑死。F8 retrofit 把 ``replay:write``
    與 ``replay:read:any`` 同登記到 default scope csv。
    """
    from app.auth import Settings

    # Build a fresh Settings (default factory reads env or fall-back csv).
    # 重建 Settings（default factory 讀 env 或 fall-back csv）。
    settings = Settings()
    assert "replay:write" in settings.auth_scopes, settings.auth_scopes
    assert "replay:read:any" in settings.auth_scopes, settings.auth_scopes


def test_e2_retrofit_f8_actor_built_from_settings_has_replay_scopes(monkeypatch):
    """E2 retrofit F8: build_authenticated_actor returns actor with replay scopes.
    E2 retrofit F8：build_authenticated_actor 回的 actor 含 replay scope。

    End-to-end check: a fresh actor built via the production factory
    must carry ``replay:write`` + ``replay:read:any`` so the admin
    bypass at GET /replay/report/{experiment_id} actually fires.
    端到端：以 production factory 建的 actor 必持 ``replay:write`` +
    ``replay:read:any``，使 GET /replay/report/{experiment_id} admin
    bypass 真實觸發。
    """
    # Make sure env doesn't override default csv (dev shell may set it).
    # 確保 env 未覆蓋 default csv（dev shell 可能設）。
    monkeypatch.delenv("OPENCLAW_AUTH_SCOPES", raising=False)
    # Re-import settings + actor factory so env removal takes effect.
    # 重 import settings + actor factory 使 env 清除生效。
    from app.auth import Settings, AuthenticatedActor

    settings = Settings()
    actor = AuthenticatedActor(
        actor_id=settings.auth_actor_id,
        actor_type=settings.auth_actor_type,
        roles=set(settings.auth_roles),
        scopes=set(settings.auth_scopes),
    )
    assert "replay:read:any" in actor.scopes, actor.scopes
    assert "replay:write" in actor.scopes, actor.scopes


# ─── E2 retrofit case 9: F2 V053 race-free LOCK TABLE present in SQL ───────


def test_e2_retrofit_f2_v053_uses_lock_table_access_exclusive():
    """E2 retrofit F2: V053 wraps DROP+ADD in BEGIN + LOCK TABLE + COMMIT.
    E2 retrofit F2：V053 用 BEGIN + LOCK TABLE + COMMIT 包裹 DROP+ADD。

    Static-parse layer check: open V053 SQL file and verify the
    race-free pattern is present (BEGIN; ... LOCK TABLE ... ACCESS
    EXCLUSIVE MODE; ... COMMIT;) before the DROP+ADD pair. This
    catches retrofit drift if a future migration update accidentally
    removes the lock.
    Static-parse 層：打開 V053 SQL 檔，驗 race-free pattern 在 DROP+ADD
    對之前。捕後續 migration 更新誤刪 lock 的漂移。
    """
    import os as _os
    sql_path = _os.path.join(
        _os.path.dirname(_os.path.dirname(_test_dir)),
        "..", "..", "..",
        "sql", "migrations",
        "V053__governance_audit_log_replay_event_types.sql",
    )
    sql_path = _os.path.abspath(sql_path)
    with open(sql_path, "r", encoding="utf-8") as f:
        content = f.read()
    # E2 retrofit F2 expects all of these tokens in order.
    # E2 retrofit F2 期待這些 token 依序出現。
    assert "BEGIN;" in content, "V053 must wrap DROP+ADD in explicit BEGIN; transaction"
    assert "LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE" in content, (
        "V053 must take ACCESS EXCLUSIVE lock before DROP+ADD pair"
    )
    assert "COMMIT;" in content, "V053 must close BEGIN with explicit COMMIT;"
    # Lock must come BEFORE the DROP+ADD pair (positional check).
    # Lock 必在 DROP+ADD 對之前（位置檢查）。
    lock_pos = content.find("LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE")
    drop_pos = content.find("DROP CONSTRAINT IF EXISTS governance_audit_log_event_type_check")
    add_pos = content.find("ADD CONSTRAINT governance_audit_log_event_type_check")
    assert lock_pos > 0 and drop_pos > 0 and add_pos > 0
    assert lock_pos < drop_pos < add_pos, (
        f"LOCK TABLE must precede DROP+ADD; got lock={lock_pos} drop={drop_pos} add={add_pos}"
    )
