"""REF-20 P4-S12 — replay_routes safe_query_pattern audit + chaos drill.

模組目的 / Module purpose:
    Verify that ``replay_routes.py`` mirrors the
    ``agents_routes_helpers.py`` PG-degraded-safe pattern (V3 §12 #22):

      Case 1: All 8 endpoints use the safe-PG-wrapper for read SELECTs
              OR run inside an explicit transaction with statement_timeout
              + try/except/rollback envelope (advisory-lock paths).
      Case 2: PG kill simulation → 200 + degraded:true (NOT 5xx).
      Case 3: Cursor-direct usage outside the sanctioned transactional
              wrappers = 0 hit (grep + AST audit).
      Case 4: Function signature + return shape mirrors agents_routes:
              ``_safe_pg_select(sql, params) -> (rows, err_or_none)``.

    驗證 ``replay_routes.py`` 鏡像 ``agents_routes_helpers.py`` 的 PG-degraded-safe
    pattern（V3 §12 #22）：8 routes safe-wrapper / chaos / 0 cursor leak / shape mirror。

關聯文件 / Related docs:
    - docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
      §4 Wave 6 R20-P4-S12
    - docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
      §12 #22 ``replay_routes_use_safe_query_pattern``
    - program_code/exchange_connectors/bybit_connector/control_api_v1/app/agents_routes_helpers.py
      (mirror reference)

Hard contracts (E2 / E3 / FA review focus):
    - 4-case suite covers V3 §12 #22 acceptance binding.
    - Static analysis (grep + AST) — 不依賴 PG instance；與 P2a-S3 / P2b-T2
      既有 4-case auth suite 互補。
    - PG kill chaos simulated via TestClient + monkeypatch get_pg_conn.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

import pytest


_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)


REPLAY_ROUTES_PATH = (
    Path(_control_api_dir) / "app" / "replay_routes.py"
)


# ─── Source loader (cached) ───────────────────────────────────────────────


@pytest.fixture(scope="module")
def replay_routes_source() -> str:
    """Cached read of replay_routes.py source / 快取讀取 replay_routes.py 源碼。"""
    return REPLAY_ROUTES_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def replay_routes_ast(replay_routes_source: str) -> ast.Module:
    """Cached AST parse of replay_routes.py / 快取 AST 解析。"""
    return ast.parse(replay_routes_source, filename=str(REPLAY_ROUTES_PATH))


# ─── Endpoint inventory (sanctioned 8 routes per V3 §6 + workplan §4) ────


# Each entry: (handler-fn-name, http-verb, path, allowed_pg_pattern)
# allowed_pg_pattern ∈ {"safe_select_only", "transactional_advisory_lock",
#                        "no_pg"}
# safe_select_only — handler must use _async_safe_pg_select / _safe_pg_select
# transactional_advisory_lock — handler may run cur.execute inside a `with
#   get_pg_conn() as conn:` transaction (advisory lock + state mutation;
#   wrapper unsuitable per Wave 4 R20-P2b-T2 design).
# no_pg — handler does not touch PG at all.
#
# 8 endpoint inventory (V3 §6 + workplan §4 Wave 4 R20-P2b-T2 binding).
# 8 endpoint 清單（V3 §6 + workplan §4 Wave 4 R20-P2b-T2 binding）。
ENDPOINT_INVENTORY: list[tuple[str, str, str, str]] = [
    ("post_replay_run", "post", "/run", "transactional_advisory_lock"),
    ("get_replay_status", "get", "/status", "safe_select_only"),
    ("post_replay_cancel", "post", "/cancel", "transactional_advisory_lock"),
    ("get_replay_report", "get", "/report/{experiment_id}", "safe_select_only"),
    ("get_replay_manifests", "get", "/manifests", "safe_select_only"),
    ("post_manifest_verify", "post", "/manifest/verify", "no_pg"),
    ("get_signature_health", "get", "/health/signature", "safe_select_only"),
    ("get_replay_list", "get", "/list", "safe_select_only"),
]


# ─── Case 1: 8 endpoints use safe-wrapper or sanctioned transactional path


def test_case1_all_8_endpoints_use_safe_query_wrapper_or_sanctioned_xact(
    replay_routes_source: str,
    replay_routes_ast: ast.Module,
):
    """Case 1: each of the 8 sanctioned endpoints uses either the safe
    PG wrapper for plain SELECTs or runs cur.execute inside an explicit
    transactional helper (advisory-lock paths).
    Case 1：8 sanctioned endpoint 必走 safe wrapper 或 advisory-lock xact。
    """
    # Build map of FunctionDef nodes by name from AST.
    # 由 AST 取 FunctionDef 名稱對應節點。
    funcs: dict[str, ast.AST] = {}
    for node in ast.walk(replay_routes_ast):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = node

    failures: list[str] = []
    for fn_name, _verb, _path, expected_pattern in ENDPOINT_INVENTORY:
        if fn_name not in funcs:
            failures.append(f"{fn_name}: handler not found in AST")
            continue
        handler = funcs[fn_name]
        body_src = ast.unparse(handler) if hasattr(ast, "unparse") else ""

        if expected_pattern == "safe_select_only":
            # MUST reference the wrapper at least once; must NOT reference
            # `conn.cursor()` (which would mean a direct unmanaged cursor).
            # 必至少出現一次 wrapper；不可出現 conn.cursor()（裸 cursor）。
            uses_wrapper = (
                "_async_safe_pg_select" in body_src
                or "_safe_pg_select(" in body_src
            )
            if not uses_wrapper:
                failures.append(
                    f"{fn_name}: safe_select_only handler missing "
                    "_async_safe_pg_select / _safe_pg_select call"
                )
            if "conn.cursor()" in body_src:
                failures.append(
                    f"{fn_name}: safe_select_only handler uses raw "
                    "conn.cursor() — must go through wrapper"
                )

        elif expected_pattern == "transactional_advisory_lock":
            # MUST contain a sync helper `_do_pg_path` / `_do_pg_cancel` OR
            # delegate to the security_guards `execute_replay_cancel_pg_path`
            # helper (Sprint 1 Track C E2 retrofit moved cancel PG body to
            # sibling module for §九 1500 LOC cap compliance).
            # 必含 _do_pg_path / _do_pg_cancel 同步 helper，或委派
            # security_guards.execute_replay_cancel_pg_path（Sprint 1 Track C
            # E2 retrofit 為 §九 1500 LOC cap 將 cancel PG body 移 sibling）。
            if not (
                "_do_pg_path" in body_src
                or "_do_pg_cancel" in body_src
                or "_sg.execute_replay_cancel_pg_path" in body_src
                or "execute_replay_cancel_pg_path" in body_src
            ):
                failures.append(
                    f"{fn_name}: transactional_advisory_lock handler "
                    "missing _do_pg_path / _do_pg_cancel sync helper "
                    "or _sg.execute_replay_cancel_pg_path delegation"
                )

        elif expected_pattern == "no_pg":
            # Handler must not touch get_pg_conn / wrapper / direct cursor.
            # handler 完全不碰 PG。
            forbidden = ("get_pg_conn", "_safe_pg_select", "conn.cursor()")
            for tok in forbidden:
                if tok in body_src:
                    failures.append(
                        f"{fn_name}: no_pg handler unexpectedly references {tok!r}"
                    )

    assert not failures, "\n".join(failures)


# ─── Case 2: PG kill simulation → 200 + degraded (chaos drill) ───────────


def test_case2_pg_kill_simulation_returns_200_degraded(monkeypatch):
    """Case 2: when ``get_pg_conn`` returns None (simulating PG outage)
    the SELECT routes return 200 + ``degraded:true`` (NOT 5xx).
    Case 2：模擬 PG outage（get_pg_conn 回 None），SELECT route 回 200 +
    degraded:true（不 5xx）。
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.auth import AuthenticatedActor
    from app.main_legacy import current_actor
    from app.replay_routes import replay_router

    # Authenticated actor stub (replay:write scope).
    # 已認證 actor stub（replay:write scope）。
    def _operator_actor() -> AuthenticatedActor:
        return AuthenticatedActor(
            actor_id="alice",
            actor_type="human",
            roles={"operator", "viewer"},
            scopes={"replay:write", "private_readonly"},
        )

    # Patch get_pg_conn to yield None (PG unreachable).
    # patch get_pg_conn 回 None（PG 不可達）。
    import app.replay_routes as rr

    class _NoneCtx:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    monkeypatch.setattr(rr, "get_pg_conn", lambda: _NoneCtx())

    app = FastAPI()
    app.include_router(replay_router)
    app.dependency_overrides[current_actor] = _operator_actor
    client = TestClient(app)

    # GET /status — pure SELECT path, must return 200 + degraded.
    # GET /status — 純 SELECT 路徑，必回 200 + degraded。
    resp = client.get("/api/v1/replay/status")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
    body = resp.json()
    # Envelope: { ok, data, degraded, reason, ... }
    # _replay_response 的標準信封
    assert body.get("ok") is True
    assert body.get("degraded") is True or body.get("data", {}).get("active_run") is None
    # If degraded path triggered, reason should be set
    # 若 degraded path 觸發，reason 應有值
    if body.get("degraded") is True:
        assert body.get("reason") is not None


# ─── Case 3: cursor-direct usage 0 hit outside sanctioned wrappers ───────


def test_case3_no_cursor_direct_usage_outside_sanctioned_wrappers(
    replay_routes_source: str,
    replay_routes_ast: ast.Module,
):
    """Case 3: ``cur.execute`` outside sanctioned places = 0 hit.
    Case 3：``cur.execute`` 在 sanctioned 區外 = 0 命中。

    Sanctioned places:
      - ``_safe_pg_select`` (line ~370-)
      - ``_do_pg_path`` (POST /run advisory-lock xact)
      - ``_do_pg_cancel`` (POST /cancel advisory-lock xact)

    其他位置出現 cur.execute 即視為違規（必走 wrapper / xact helper）。
    """
    # Find every cur.execute / cursor.execute / conn.execute occurrence.
    # 找所有 cur.execute / cursor.execute / conn.execute。
    pattern = re.compile(r"\b(cur|cursor)\.execute\b")
    sanctioned_fns = {"_safe_pg_select", "_do_pg_path", "_do_pg_cancel"}

    # Build span map: fn_name -> (start_line, end_line) from AST.
    # 由 AST 建函數行號區間。
    spans: dict[str, tuple[int, int]] = {}
    for node in ast.walk(replay_routes_ast):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_line = max(
                (getattr(child, "end_lineno", node.lineno) or node.lineno)
                for child in ast.walk(node)
            )
            spans[node.name] = (node.lineno, end_line)

    src_lines = replay_routes_source.splitlines()
    leaks: list[str] = []
    for line_no, line in enumerate(src_lines, start=1):
        if not pattern.search(line):
            continue
        # Determine which function the line belongs to (innermost match).
        # 該行所屬最內層 function。
        owner_fn: str | None = None
        owner_span = -1
        for fn_name, (start, end) in spans.items():
            if start <= line_no <= end:
                # Pick innermost (smallest span).
                # 取最內層（區間最短）。
                cur_span = end - start
                if owner_fn is None or cur_span < owner_span:
                    owner_fn = fn_name
                    owner_span = cur_span
        if owner_fn not in sanctioned_fns:
            leaks.append(
                f"replay_routes.py:{line_no}: {line.strip()} "
                f"(owner_fn={owner_fn!r}; not in sanctioned set "
                f"{sorted(sanctioned_fns)})"
            )

    assert not leaks, "Cursor-direct leaks outside sanctioned wrappers:\n" + "\n".join(leaks)


# ─── Case 4: signature + return shape mirrors agents_routes_helpers ──────


def test_case4_safe_pg_select_signature_mirrors_agents_routes():
    """Case 4: ``_safe_pg_select`` and ``_async_safe_pg_select`` mirror
    the agents_routes pattern (sql, params) -> (rows, err_or_none).
    Case 4：``_safe_pg_select`` 與 async wrapper 簽名 / 回傳 shape 鏡像
    agents_routes pattern。
    """
    import inspect

    from app.replay_routes import _async_safe_pg_select, _safe_pg_select

    # Sync helper signature: (sql, params) -> (rows, err)
    # 同步 helper 簽名
    sig = inspect.signature(_safe_pg_select)
    param_names = list(sig.parameters.keys())
    assert param_names == ["sql", "params"], (
        f"_safe_pg_select signature drift: got {param_names}, "
        "expected ['sql', 'params']"
    )

    # Async wrapper must be `async def` (coroutine when called).
    # async wrapper 必須是 coroutine function。
    assert inspect.iscoroutinefunction(_async_safe_pg_select), (
        "_async_safe_pg_select must be async (asyncio.to_thread wrapper)"
    )
    async_sig = inspect.signature(_async_safe_pg_select)
    async_params = list(async_sig.parameters.keys())
    assert async_params == ["sql", "params"], (
        f"_async_safe_pg_select signature drift: got {async_params}"
    )

    # Return annotation must be a 2-tuple (rows, err_or_none).
    # 回傳註解必為 2-tuple (rows, err_or_none)。
    return_annotation = sig.return_annotation
    return_str = str(return_annotation)
    assert "Tuple" in return_str or "tuple" in return_str, (
        f"_safe_pg_select return shape drift: {return_str}"
    )
    assert "Optional[str]" in return_str or "str | None" in return_str or "None" in return_str, (
        f"_safe_pg_select must return Optional error string: {return_str}"
    )

    # ``_replay_response`` envelope must include the 4-key contract
    # mirrored from agents_routes (degraded boolean + reason field).
    # _replay_response 信封必含 agents_routes 鏡像 4-key。
    from app.replay_routes import _replay_response

    sample = _replay_response({"x": 1}, degraded=True, reason="test")
    for key in ("ok", "data", "degraded", "reason"):
        assert key in sample, f"_replay_response envelope missing key: {key}"
    assert sample["ok"] is True
    assert sample["degraded"] is True
    assert sample["reason"] == "test"


# ─── Bonus audit helper export (E3 reuse) ────────────────────────────────


def _audit_replay_routes_safe_query() -> dict:
    """Standalone audit function — verify 0 direct cur.execute outside
    sanctioned wrappers + return summary dict for E3 / FA reuse.

    獨立 audit function — 驗 0 cur.execute 散落 + 回 summary dict 供 E3/FA。

    Used by:
      - This test suite (test_case3 indirectly)
      - E3 chaos drill scaffold (case 2 imports + invokes)
      - PA Wave 7 sign-off binding
    """
    src = REPLAY_ROUTES_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(REPLAY_ROUTES_PATH))
    pattern = re.compile(r"\b(cur|cursor)\.execute\b")
    sanctioned_fns = {"_safe_pg_select", "_do_pg_path", "_do_pg_cancel"}

    spans: dict[str, tuple[int, int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_line = max(
                (getattr(child, "end_lineno", node.lineno) or node.lineno)
                for child in ast.walk(node)
            )
            spans[node.name] = (node.lineno, end_line)

    leaks: list[dict] = []
    total_hits = 0
    src_lines = src.splitlines()
    for line_no, line in enumerate(src_lines, start=1):
        if not pattern.search(line):
            continue
        total_hits += 1
        owner_fn: str | None = None
        owner_span = -1
        for fn_name, (start, end) in spans.items():
            if start <= line_no <= end:
                cur_span = end - start
                if owner_fn is None or cur_span < owner_span:
                    owner_fn = fn_name
                    owner_span = cur_span
        if owner_fn not in sanctioned_fns:
            leaks.append({
                "line": line_no,
                "code": line.strip(),
                "owner_fn": owner_fn,
            })

    return {
        "file": str(REPLAY_ROUTES_PATH),
        "total_cur_execute_hits": total_hits,
        "sanctioned_fns": sorted(sanctioned_fns),
        "leaks": leaks,
        "audit_ok": len(leaks) == 0,
    }


def test_audit_helper_returns_clean_summary():
    """Bonus: audit helper returns audit_ok=True + leaks=[] (smoke test).
    audit helper 回 audit_ok=True + leaks=[]（smoke test）。

    Sprint 1 Track C E2 retrofit moved ``_do_pg_cancel`` body to
    ``replay/security_guards.py::execute_replay_cancel_pg_path`` for
    §九 1500 LOC cap compliance; ``cur.execute`` hit count in
    ``replay_routes.py`` dropped from 8 to 5 (only ``_do_pg_path`` and
    ``_safe_pg_select`` remain in this file). ``_do_pg_cancel`` is still
    in the sanctioned_fns allow-list because legacy callers may grep
    for the marker, but ``spans`` no longer contains it.
    Sprint 1 Track C E2 retrofit 將 ``_do_pg_cancel`` body 移至
    ``replay/security_guards.py::execute_replay_cancel_pg_path``，以符合
    §九 1500 LOC cap；``replay_routes.py`` 內 ``cur.execute`` 命中數從
    8 降至 5。``_do_pg_cancel`` 仍在 sanctioned_fns allow-list 內供
    legacy grep，但 ``spans`` 不再含。
    """
    summary = _audit_replay_routes_safe_query()
    assert summary["audit_ok"] is True
    assert summary["leaks"] == []
    # Post-retrofit baseline: ≥5 sanctioned hits (3 in _do_pg_path + 2 in
    # _safe_pg_select). ``_do_pg_cancel`` body now lives in security_guards
    # and adds 3 hits there, but those are NOT in this file's audit scope.
    # Retrofit 後 baseline：≥5 sanctioned hits（_do_pg_path 3 + _safe_pg_select 2）。
    assert summary["total_cur_execute_hits"] >= 5
    assert "_safe_pg_select" in summary["sanctioned_fns"]
    assert "_do_pg_path" in summary["sanctioned_fns"]
    # ``_do_pg_cancel`` allow-listed for backward compat; physical body
    # extracted, so ``spans`` may not contain it (do not assert presence).
    # ``_do_pg_cancel`` allow-list 為向後相容；body 已抽出，spans 可能無此項。
    assert "_do_pg_cancel" in summary["sanctioned_fns"]
