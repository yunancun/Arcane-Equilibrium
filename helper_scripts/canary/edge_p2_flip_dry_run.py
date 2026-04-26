#!/usr/bin/env python3
"""
EDGE-P2-flip Dry-Run Smoke Test (P2-flip-T1).
EDGE-P2-flip 翻轉前 dry-run 煙霧測試（P2-flip-T1）。

MODULE_NOTE (English):
  Pre-flight smoke test for the EDGE-P2-flip operation (Combine Layer
  shadow_enabled false → true). Runs five preflight checks against the
  live engine WITHOUT mutating any production state, and outputs both a
  human-readable markdown report (stdout) and a structured JSON artifact
  ($OPENCLAW_DATA_DIR/edge_p2_flip_dry_run.json) for the operator/SOP
  shell wrapper (`edge_p2_flip.sh`) to gate the actual flip on.

  The five checks (per PA RFC `2026-04-26--edge_p2_flip_sop_rfc.md` §3.1
  Pre-flight + §3.4 verify):
    (a) exit_features writer 24h cumulative > 0  (close-path producer alive)
    (b) decision_shadow_exits table exists       (V021 migration applied)
    (c) Combine Layer mock-inference path wired  (IPC get_risk_config returns
                                                  ExitConfig schema with all
                                                  expected fields)
    (d) IPC patch_risk_config deep-merge path live (build a dry payload that
        WOULD flip shadow_enabled, run a no-op `get_risk_config` round-trip
        instead — we never actually send the mutating patch; we only verify
        the channel works and the response is well-formed)
    (e) Reverse patch path constructible          (synthesize the revert
        payload `{exit: {shadow_enabled: false}}` and validate JSON shape)

  Any check FAIL → exit 1, message printed; all PASS → exit 0 with a
  "ready to flip" stamp in the markdown summary. The shell wrapper that
  calls this script reads the JSON artifact (not stdout) for machine
  decisions.

MODULE_NOTE (中文):
  EDGE-P2-flip 翻轉前 dry-run 煙霧測試（PA RFC `2026-04-26--edge_p2_flip_sop_rfc.md`
  §3.1 + §3.4）。對 live engine 跑 5 條 pre-flight 檢查，**不**修改任何 production
  狀態，輸出 markdown report (stdout) + structured JSON artifact
  ($OPENCLAW_DATA_DIR/edge_p2_flip_dry_run.json)。

  5 條檢查：
    (a) exit_features writer 24h 累積 > 0     —— close-path producer 活著
    (b) decision_shadow_exits 表存在           —— V021 已套用
    (c) Combine Layer mock-inference path 接線 —— IPC get_risk_config 回傳
                                                ExitConfig schema 含所有預期欄位
    (d) IPC patch_risk_config deep-merge 路徑通—— 構造**會**翻轉的 dry payload，
        實際只跑唯讀 get_risk_config round-trip 驗通道；**絕不**真送 mutating
        patch（這是 dry-run，不是 flip）
    (e) 反向 patch 路徑可構造                  —— 合成 `{exit: {shadow_enabled: false}}`
                                                revert payload 並驗 JSON shape

  任一 FAIL → exit 1；全 PASS → exit 0 + markdown 結尾蓋「ready to flip」章。
  shell wrapper（edge_p2_flip.sh）讀 JSON artifact（非 stdout）做機器決策。

CLI:
  python3 edge_p2_flip_dry_run.py [--engine-mode <demo|live_demo|paper>]
                                  [--verbose]
                                  [--mock-events <int>]

Env requirements (operator running outside systemd / cron context):
  - OPENCLAW_IPC_SECRET    : HMAC secret for IPC handshake (lives in
                             $OPENCLAW_SECRETS_ROOT/environment_files/ipc_secret.txt;
                             default $OPENCLAW_SECRETS_ROOT=~/BybitOpenClaw/secrets;
                             see restart_all.sh:31, 196 for the load pattern)
  - POSTGRES_USER/PASSWORD : DB credentials (basic_system_services.env)
  - OPENCLAW_BASE_DIR      : srv root (defaults to ~/BybitOpenClaw/srv)

Easiest invocation: use the wrapper helper_scripts/operator/edge_p2_flip.sh
which sources env files automatically (incl. ipc_secret.txt) before running
this dry-run. Direct invocation requires manual env setup:

  SECRETS=${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}
  set -a; source $SECRETS/environment_files/basic_system_services.env; set +a
  export OPENCLAW_IPC_SECRET="$(cat $SECRETS/environment_files/ipc_secret.txt)"
  python3 helper_scripts/canary/edge_p2_flip_dry_run.py --engine-mode demo

Exit codes:
  0 — all 5 checks PASS, ready to flip
  1 — any check FAIL, do NOT flip
  2 — IPC connect failure (engine likely down) — investigate engine health first

Outputs:
  stdout    — human-readable markdown report
  artifact  — $OPENCLAW_DATA_DIR/edge_p2_flip_dry_run.json (structured)

Reference / 參考:
  - PA RFC: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--edge_p2_flip_sop_rfc.md
  - Healthcheck [8] / [15] for parallel reads:
        srv/helper_scripts/db/passive_wait_healthcheck.py
  - sync IPC helper:
        srv/program_code/exchange_connectors/.../control_api_v1/app/ipc_client.py:735
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket as _socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# stderr logging so stdout (markdown) stays pipe-friendly.
# stderr 日誌避免污染 stdout（markdown 可直接 pipe）。
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [DRY-RUN] %(levelname)s %(message)s",
)
logger = logging.getLogger("edge_p2_flip_dry_run")


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_SOCKET_PATH = "/tmp/openclaw/engine.sock"
SOCKET_ENV_VAR = "OPENCLAW_IPC_SOCKET"
DEFAULT_DATA_DIR = "/tmp/openclaw"
DEFAULT_TIMEOUT_SECS = 5.0

# Schema fields that must be present in ExitConfig (per Rust
# `exit_features/v2.rs:120-150` + `default_*` fns). Used in check (c) to
# validate the IPC get_risk_config response shape.
# ExitConfig 預期欄位（與 Rust 端對齊）—— check (c) 用以驗 IPC 響應結構。
EXIT_CONFIG_REQUIRED_FIELDS: tuple[str, ...] = (
    "min_net_floor_bps",
    "min_hold_secs",
    "min_peak_atr_norm",
    "stale_peak_ms",
    "giveback_base",
    "giveback_slope",
    "giveback_floor",
    "missing_edge_fallback_bps",
    "shadow_enabled",
)

# Engine modes accepted by the IPC patch_risk_config / get_risk_config
# methods (per Rust `ipc_server/mod.rs:975-1003`).
# IPC 接受的 engine 模式（與 Rust IPC 路由對齊）。
VALID_ENGINE_MODES: tuple[str, ...] = ("paper", "demo", "live", "live_demo")


# ═══════════════════════════════════════════════════════════════════════════════
# Pure synchronous IPC helper / 純同步 IPC 輔助
# ═══════════════════════════════════════════════════════════════════════════════
#
# This is a stripped-down clone of `sync_ipc_call` from
# program_code/.../control_api_v1/app/ipc_client.py:735 — repeated here so
# the script is invocable WITHOUT importing the full FastAPI application
# stack (cron / operator standalone usage).
#
# 此函數是 sync_ipc_call 的精簡 clone（從 ipc_client.py:735 複製），
# 讓本腳本可獨立執行（cron / operator 手動），不必載入 FastAPI 棧。

def _sync_ipc_call(
    method: str,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECS,
    socket_path: str | None = None,
) -> dict[str, Any]:
    """
    Best-effort synchronous JSON-RPC 2.0 call against the engine Unix socket.
    對引擎 Unix socket 的同步 JSON-RPC 2.0 調用（盡力而為）。

    Returns the engine 'result' field on success.
    成功時返回 engine 響應的 'result' 欄位。

    Raises FileNotFoundError if engine socket missing (engine down).
    引擎 socket 不存在時拋 FileNotFoundError（引擎未跑）。
    Raises RuntimeError on JSON-RPC 'error' field.
    JSON-RPC 'error' 欄位非空時拋 RuntimeError。
    Raises TimeoutError on socket timeout.
    socket 超時時拋 TimeoutError。
    """
    import hashlib
    import hmac as _hmac_lib

    _path = socket_path or os.environ.get(SOCKET_ENV_VAR, DEFAULT_SOCKET_PATH)
    ipc_secret = os.environ.get("OPENCLAW_IPC_SECRET", "")

    with _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(_path)

        def _recv_line() -> str:
            buf = b""
            while True:
                ch = sock.recv(1)
                if not ch:
                    raise ConnectionResetError("engine closed connection")
                if ch == b"\n":
                    return buf.decode("utf-8")
                buf += ch

        def _send(msg: dict[str, Any]) -> None:
            data = (json.dumps(msg) + "\n").encode("utf-8")
            sock.sendall(data)

        # HMAC-SHA256 auth handshake (no-op when secret unset, dev mode).
        # `ts` MUST be unix seconds (i64) per Rust verifier
        # `ipc_server/mod.rs:624-628` — `now.as_secs() as i64` with ±30s
        # tolerance. NOTE: the legacy `sync_ipc_call` helper at
        # `app/ipc_client.py:786` uses *milliseconds* which would always
        # fail on this Rust gate; we deliberately diverge here to use the
        # value the Rust side actually validates.
        # HMAC-SHA256 認證握手（未設密鑰時跳過）。
        # `ts` 必須為 unix 秒（i64），與 Rust verifier 對齊（±30s 容差）。
        # 注意：legacy sync_ipc_call helper 用毫秒會 100% fail，我們刻意分歧
        # 用秒對齊 Rust 真正驗證的值。
        if ipc_secret:
            ts = int(time.time())
            token = _hmac_lib.new(
                ipc_secret.encode("utf-8"),
                str(ts).encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            _send({"jsonrpc": "2.0", "method": "__auth",
                   "params": {"token": token, "ts": ts}, "id": 0})
            auth_resp = json.loads(_recv_line())
            if auth_resp.get("error"):
                raise PermissionError(f"IPC auth failed: {auth_resp['error']}")

        # Send the actual request and read one response line.
        # 送出請求並讀取一行響應。
        _send({"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1})
        resp = json.loads(_recv_line())

        if resp.get("error"):
            raise RuntimeError(f"IPC error from engine: {resp['error']}")
        return resp.get("result", {})


# ═══════════════════════════════════════════════════════════════════════════════
# DB connection helper / DB 連接輔助
# ═══════════════════════════════════════════════════════════════════════════════
#
# Mirrors `passive_wait_healthcheck.py:_get_conn` env-var convention so the
# operator's existing systemd / cron environment populates POSTGRES_* and the
# dry-run runs the same way as healthchecks. OPENCLAW_DATABASE_URL takes
# priority for explicit override (CI / replay use).
#
# 對齊 `passive_wait_healthcheck.py:_get_conn` 環境變數慣例 ── operator 既有
# systemd / cron 環境已填 POSTGRES_*，dry-run 跑得和 healthcheck 一樣。
# OPENCLAW_DATABASE_URL 顯式 override 優先（CI / replay 用）。

def _open_pg_conn():
    """
    Open a Postgres connection using the same env-var convention as the
    healthcheck script. Lazy psycopg2 import so this module remains importable
    even when psycopg2 is missing (smoke tests / dry-run on Mac dev).
    依 healthcheck 同款 env 慣例開 PG 連線；psycopg2 懶載入。
    """
    import psycopg2  # type: ignore
    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    return psycopg2.connect(dsn, connect_timeout=5)


# ═══════════════════════════════════════════════════════════════════════════════
# Pre-flight checks / 飛行前檢查
# ═══════════════════════════════════════════════════════════════════════════════
#
# Each check returns (status, message, details) where:
#   - status   ∈ {"PASS", "FAIL"}
#   - message  is a single human-readable line
#   - details  is a JSON-serialisable dict for the artifact
#
# 每個 check 回傳 (status, message, details)：
#   - status   為 "PASS" 或 "FAIL"
#   - message  為單行人類可讀說明
#   - details  為可 JSON 序列化的 dict（給 artifact 用）

def check_a_exit_features_writer(engine_mode: str) -> tuple[str, str, dict[str, Any]]:
    """
    Check (a): exit_features writer 24h cumulative > 0.
    檢查 (a)：exit_features writer 24h 累積 > 0。

    Why: Phase 2 shadow flip relies on close-path emitting exit_features
    rows; if writer is dead the shadow data plane will silently dormant.
    Phase 2 翻轉依賴 close-path 寫 exit_features；writer 掛了 shadow 平面
    就會 silent-dead。

    Implementation: query learning.exit_features count in last 24h,
    filtered by engine_mode. Uses psycopg2 lazy import so script can run
    on environments without DB lib (will FAIL gracefully).
    實作：查 learning.exit_features 24h 計數（依 engine_mode 過濾）。psycopg2
    懶 import，環境無 DB 時 fail gracefully。
    """
    try:
        import psycopg2  # noqa: F401  (lazy import, raises ImportError → FAIL)
    except ImportError as e:
        return ("FAIL",
                f"check (a) skipped: psycopg2 unavailable ({e})",
                {"reason": "psycopg2_missing"})

    try:
        conn = _open_pg_conn()
    except Exception as e:
        return ("FAIL",
                f"check (a) DB connect failed: {e}",
                {"reason": "db_connect_failed"})

    try:
        with conn.cursor() as cur:
            # exit_features.engine_mode is text; filter both 'live' + 'live_demo'
            # for live_demo flip target (per CLAUDE.md §三 engine_mode upgrade).
            # exit_features.engine_mode 為 text；live_demo 同時匹配 'live'+'live_demo'
            # （per engine_mode tag 升級）。
            if engine_mode == "live_demo":
                cur.execute(
                    "SELECT COUNT(*)::bigint FROM learning.exit_features "
                    "WHERE ts > now() - interval '24 hours' "
                    "AND engine_mode IN ('live', 'live_demo')"
                )
            else:
                cur.execute(
                    "SELECT COUNT(*)::bigint FROM learning.exit_features "
                    "WHERE ts > now() - interval '24 hours' "
                    "AND engine_mode = %s",
                    (engine_mode,),
                )
            row = cur.fetchone()
            cnt = int(row[0] if row else 0)
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return ("FAIL",
                f"check (a) query failed: {e}",
                {"reason": "query_failed", "error": str(e)})
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if cnt > 0:
        return ("PASS",
                f"exit_features 24h count={cnt} (writer alive)",
                {"count_24h": cnt, "engine_mode": engine_mode})
    return ("FAIL",
            f"exit_features 24h count=0 (writer silent-dead, "
            f"engine_mode={engine_mode})",
            {"count_24h": 0, "engine_mode": engine_mode})


def check_b_decision_shadow_exits_table() -> tuple[str, str, dict[str, Any]]:
    """
    Check (b): decision_shadow_exits table exists (V021 applied).
    檢查 (b)：decision_shadow_exits 表存在（V021 已套用）。

    Why: shadow flip writes one row per close fill; without the table V021
    migration is missing and writer crashes on first emit.
    翻轉後每筆 close 寫一行；表不存在 V021 沒套用，writer 首次 emit 即崩。
    """
    try:
        import psycopg2  # noqa: F401
    except ImportError as e:
        return ("FAIL",
                f"check (b) skipped: psycopg2 unavailable ({e})",
                {"reason": "psycopg2_missing"})

    try:
        conn = _open_pg_conn()
    except Exception as e:
        return ("FAIL",
                f"check (b) DB connect failed: {e}",
                {"reason": "db_connect_failed"})

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass('learning.decision_shadow_exits') IS NOT NULL"
            )
            row = cur.fetchone()
            exists = bool(row[0]) if row else False
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return ("FAIL",
                f"check (b) query failed: {e}",
                {"reason": "query_failed"})
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if exists:
        return ("PASS",
                "learning.decision_shadow_exits exists (V021 applied)",
                {"table_exists": True})
    return ("FAIL",
            "learning.decision_shadow_exits missing — V021 migration not applied",
            {"table_exists": False})


def check_c_combine_layer_schema(engine_mode: str) -> tuple[str, str, dict[str, Any]]:
    """
    Check (c): Combine Layer mock-inference path wired (ExitConfig schema OK).
    檢查 (c)：Combine Layer mock-inference 路徑接線（ExitConfig schema 完整）。

    Why: shadow flip needs ExitConfig.shadow_enabled present in schema; if
    ExitConfig fields drifted from Rust source, deserialise will fail
    silently after deep-merge. We verify all 9 expected fields by calling
    the read-only `get_risk_config` and inspecting the JSON shape.
    翻轉需要 ExitConfig.shadow_enabled 在 schema 內；欄位漂移會讓 deep-merge
    後 deserialize silent fail。我們呼唯讀 get_risk_config 確認 9 個預期欄位。
    """
    try:
        result = _sync_ipc_call(
            "get_risk_config",
            params={"engine": engine_mode},
            timeout=DEFAULT_TIMEOUT_SECS,
        )
    except FileNotFoundError:
        return ("FAIL",
                "check (c) IPC socket not found — engine likely down",
                {"reason": "ipc_socket_missing"})
    except Exception as e:
        # IPC auth errors look like "first message must be __auth" — give the
        # operator the actionable hint (source env file before running).
        # IPC 認證錯誤指引 operator 先 source env file 再跑。
        err_str = str(e)
        if "__auth" in err_str or "auth failed" in err_str.lower():
            hint = (" [hint: OPENCLAW_IPC_SECRET not in env; "
                    "operator should `source settings/environment_files/"
                    "trading_services.env` or run from systemd context]")
        else:
            hint = ""
        return ("FAIL",
                f"check (c) IPC call failed: {e}{hint}",
                {"reason": "ipc_call_failed", "error": err_str})

    cfg = result.get("config")
    if not isinstance(cfg, dict):
        return ("FAIL",
                f"check (c) get_risk_config returned malformed config "
                f"(type={type(cfg).__name__})",
                {"reason": "config_not_object"})

    exit_section = cfg.get("exit")
    if not isinstance(exit_section, dict):
        return ("FAIL",
                f"check (c) RiskConfig.exit missing or not object "
                f"(got {type(exit_section).__name__})",
                {"reason": "exit_section_missing"})

    missing = [f for f in EXIT_CONFIG_REQUIRED_FIELDS if f not in exit_section]
    if missing:
        return ("FAIL",
                f"check (c) ExitConfig missing fields: {missing}",
                {"reason": "fields_missing",
                 "missing_fields": missing,
                 "present_fields": sorted(exit_section.keys())})

    current_shadow = exit_section.get("shadow_enabled")
    if not isinstance(current_shadow, bool):
        return ("FAIL",
                f"check (c) shadow_enabled is not bool "
                f"(got {type(current_shadow).__name__}: {current_shadow!r})",
                {"reason": "shadow_enabled_type_error",
                 "value": current_shadow})

    return ("PASS",
            f"ExitConfig schema OK; current shadow_enabled={current_shadow} "
            f"(version={result.get('version', 'n/a')})",
            {"all_fields_present": True,
             "current_shadow_enabled": current_shadow,
             "config_version": result.get("version")})


def check_d_ipc_patch_path_dry(
    engine_mode: str,
    mock_events: int,
) -> tuple[str, str, dict[str, Any]]:
    """
    Check (d): IPC patch_risk_config deep-merge path live (DRY — no mutation).
    檢查 (d)：IPC patch_risk_config deep-merge 路徑通（DRY — 不真改）。

    Why: confirm the JSON-RPC channel + auth handshake + response shape
    work end-to-end. We construct the EXACT payload that WOULD flip
    shadow_enabled and validate the JSON shape, but actually round-trip
    a read-only get_risk_config call. We do NOT send the mutating patch
    (this is a dry-run, per RFC §3.4 — flip happens only via the operator
    SOP shell wrapper edge_p2_flip.sh after this dry-run passes).
    確認 JSON-RPC 通道 + 認證 + 響應結構 e2e 通。我們構造**精確**的 mutating
    patch payload 以驗 JSON 結構，但實際只跑唯讀 get_risk_config 來
    round-trip 通道。**絕不**真送 mutating patch（per RFC §3.4，flip 只能
    透過 operator SOP shell wrapper edge_p2_flip.sh 在 dry-run pass 後執行）。

    `mock_events` is purely informational — we report how many events
    Phase 2 would observe at default emit rates; it is not a real
    pipeline test (which is unavoidable given dry-run constraint).
    `mock_events` 純資訊性 —— 我們回報 Phase 2 預期 emit 速率下能觀察到
    多少事件；非真正 pipeline test（dry-run 約束下不可避免）。
    """
    # Construct the payload that operator's flip wrapper WILL send.
    # 構造 operator flip wrapper 真要送的 payload。
    flip_patch_payload = {
        "engine": engine_mode,
        "source": "operator",
        "patch": {"exit": {"shadow_enabled": True}},
        "id": f"dry_run_validation_{int(time.time())}",
    }

    # Validate the payload's JSON shape: must serialise + the patch object
    # must be valid JSON (no NaN / cycles / unsupported types).
    # 驗 payload JSON 結構：可序列化 + patch 物件合法 JSON。
    try:
        payload_json = json.dumps(flip_patch_payload, separators=(",", ":"))
    except (TypeError, ValueError) as e:
        return ("FAIL",
                f"check (d) flip payload JSON serialise failed: {e}",
                {"reason": "payload_serialize_failed"})

    # Round-trip a read-only call to verify the IPC channel is responsive
    # and the response is well-formed. This does NOT mutate state.
    # 跑唯讀 round-trip 驗 IPC 通道活著且響應格式正確。**不**改狀態。
    try:
        result = _sync_ipc_call(
            "get_risk_config",
            params={"engine": engine_mode},
            timeout=DEFAULT_TIMEOUT_SECS,
        )
    except FileNotFoundError:
        return ("FAIL",
                "check (d) IPC socket not found — engine down",
                {"reason": "ipc_socket_missing"})
    except Exception as e:
        err_str = str(e)
        if "__auth" in err_str or "auth failed" in err_str.lower():
            hint = (" [hint: OPENCLAW_IPC_SECRET not in env; "
                    "operator should `source settings/environment_files/"
                    "trading_services.env` or run from systemd context]")
        else:
            hint = ""
        return ("FAIL",
                f"check (d) IPC round-trip failed: {e}{hint}",
                {"reason": "round_trip_failed", "error": err_str})

    if not isinstance(result, dict) or "version" not in result:
        return ("FAIL",
                "check (d) IPC response malformed (missing 'version')",
                {"reason": "response_malformed"})

    return ("PASS",
            f"IPC channel live; payload validated "
            f"({len(payload_json)} bytes, version={result.get('version')}, "
            f"mock_events_target={mock_events})",
            {"payload_bytes": len(payload_json),
             "payload_preview": flip_patch_payload,
             "mock_events_target": mock_events,
             "ipc_version_observed": result.get("version")})


def check_e_revert_path_constructible(
    engine_mode: str,
) -> tuple[str, str, dict[str, Any]]:
    """
    Check (e): Reverse patch path constructible (revert payload valid).
    檢查 (e)：反向 patch 路徑可構造（revert payload 合法）。

    Why: per RFC §4.2, manual revert SOP must complete in 90s. We verify
    the reverse payload `{exit: {shadow_enabled: false}}` is JSON-valid
    and shape-equivalent to the flip payload modulo the boolean flip;
    this guarantees the revert.sh wrapper can construct it without
    additional logic.
    per RFC §4.2，manual revert SOP 必須 90s 完成。我們驗反向 payload
    `{exit: {shadow_enabled: false}}` JSON 合法且結構與 flip payload 對稱
    （只差 bool 翻轉）；確保 revert.sh wrapper 可零附加邏輯構造它。
    """
    revert_patch_payload = {
        "engine": engine_mode,
        "source": "operator",
        "patch": {"exit": {"shadow_enabled": False}},
        "id": f"revert_validation_{int(time.time())}",
    }
    try:
        payload_json = json.dumps(revert_patch_payload, separators=(",", ":"))
    except (TypeError, ValueError) as e:
        return ("FAIL",
                f"check (e) revert payload JSON serialise failed: {e}",
                {"reason": "revert_serialize_failed"})

    # Symmetric structure check: flip and revert payloads must differ only
    # in patch.exit.shadow_enabled bool. Catches accidental schema drift.
    # 結構對稱檢查：flip 和 revert payload 應只差 patch.exit.shadow_enabled
    # bool。避免 schema 漂移。
    flip_shape = {"engine": engine_mode, "patch": {"exit": ["shadow_enabled"]}}
    revert_shape = {
        "engine": revert_patch_payload["engine"],
        "patch": {"exit": list(revert_patch_payload["patch"]["exit"].keys())},
    }
    if flip_shape != revert_shape:
        return ("FAIL",
                f"check (e) flip vs revert shape mismatch (flip={flip_shape}, "
                f"revert={revert_shape})",
                {"reason": "shape_mismatch"})

    return ("PASS",
            f"revert payload constructible ({len(payload_json)} bytes, "
            f"symmetric to flip payload)",
            {"payload_bytes": len(payload_json),
             "payload_preview": revert_patch_payload})


# ═══════════════════════════════════════════════════════════════════════════════
# Output formatters / 輸出格式化
# ═══════════════════════════════════════════════════════════════════════════════

def _emit_markdown(
    results: list[tuple[str, str, str, dict[str, Any]]],
    engine_mode: str,
    overall_pass: bool,
) -> None:
    """
    Emit the human-readable markdown report to stdout.
    輸出人類可讀 markdown report 至 stdout。

    Format mirrors check_15 / check_8 healthcheck output style for operator
    visual continuity.
    格式仿 check_15 / check_8 healthcheck 風格，operator 視覺連續性。
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"# EDGE-P2-flip Dry-Run Smoke Test")
    print()
    print(f"- timestamp: {now}")
    print(f"- engine_mode: `{engine_mode}`")
    print(f"- overall: **{'PASS — ready to flip' if overall_pass else 'FAIL — DO NOT flip'}**")
    print()
    print("## Pre-flight checks (per PA RFC §3.1)")
    print()
    print("| # | Check | Status | Message |")
    print("|---|---|---|---|")
    for label, name, status, msg in [(r[0], r[1], r[2], r[3]) for r in results]:
        # Markdown-safe: replace pipes inside msg.
        # markdown-safe：替換 msg 內 pipe。
        msg_safe = msg.replace("|", "\\|")
        print(f"| {label} | {name} | {status} | {msg_safe} |")
    print()
    if overall_pass:
        print("## Result")
        print()
        print("All 5 pre-flight checks PASS. The flip operation is safe to "
              "execute via `helper_scripts/operator/edge_p2_flip.sh`. ")
        print()
        print("**Note**: this dry-run did NOT modify any production state. ")
        print("The actual flip happens only when operator runs the SOP wrapper.")
    else:
        print("## Result")
        print()
        print("One or more pre-flight checks FAILED. **DO NOT** run the ")
        print("flip wrapper. Investigate the failed check first; the JSON ")
        print("artifact at `$OPENCLAW_DATA_DIR/edge_p2_flip_dry_run.json` ")
        print("contains structured details for downstream tooling.")
    print()


def _emit_json_artifact(
    results_obj: dict[str, Any],
    out_path: Path,
) -> None:
    """
    Emit the structured JSON artifact for shell wrapper consumption.
    為 shell wrapper 消費輸出 structured JSON artifact。

    Path is $OPENCLAW_DATA_DIR/edge_p2_flip_dry_run.json (per RFC §7).
    路徑為 $OPENCLAW_DATA_DIR/edge_p2_flip_dry_run.json（per RFC §7）。
    """
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(results_obj, f, indent=2, ensure_ascii=False)
        logger.info("artifact written: %s", out_path)
    except Exception as e:
        # Don't fail the whole dry-run on artifact write error — stdout
        # markdown is the primary output, artifact is convenience for shell.
        # artifact 寫失敗不讓 dry-run 整體 fail —— stdout markdown 是主要
        # 輸出，artifact 是給 shell 的便利。
        logger.warning("artifact write failed: %s (markdown still on stdout)", e)


# ═══════════════════════════════════════════════════════════════════════════════
# Main / 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    """
    Run all 5 pre-flight checks, emit markdown + JSON, return exit code.
    跑 5 條 pre-flight 檢查，輸出 markdown + JSON，回傳 exit code。

    Exit codes:
      0 — all PASS
      1 — any FAIL
      2 — IPC connect failure (engine likely down) — distinguished from
          generic FAIL because operator workflow differs (investigate
          engine first, not data plane).
    """
    parser = argparse.ArgumentParser(
        description="EDGE-P2-flip dry-run smoke test (no mutation)",
    )
    parser.add_argument(
        "--engine-mode",
        default="demo",
        choices=list(VALID_ENGINE_MODES),
        help="Engine to run dry-run against (default: demo)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose stderr logging (default: INFO level)",
    )
    parser.add_argument(
        "--mock-events",
        type=int,
        default=100,
        help="Synthetic event count target for pipeline volume hint "
             "(default: 100; informational only)",
    )
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.info("starting dry-run for engine_mode=%s mock_events=%d",
                args.engine_mode, args.mock_events)

    # Engine socket sanity check before running any check — distinguishes
    # exit code 2 (engine down) from exit code 1 (data plane FAIL).
    # 跑檢查前先驗 engine socket —— 區分 exit 2（引擎掛）vs exit 1（data plane）。
    socket_path = os.environ.get(SOCKET_ENV_VAR, DEFAULT_SOCKET_PATH)
    if not Path(socket_path).exists():
        logger.error("engine socket missing: %s — cannot run IPC checks "
                     "(engine likely down; investigate before retrying dry-run)",
                     socket_path)
        # Still emit a minimal markdown / JSON so caller has something
        # structured to read.
        # 仍輸出最小 markdown / JSON 給 caller。
        print(f"# EDGE-P2-flip Dry-Run — IPC UNAVAILABLE")
        print()
        print(f"- timestamp: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
        print(f"- engine_mode: `{args.engine_mode}`")
        print(f"- overall: **FAIL — engine socket missing at `{socket_path}`**")
        print()
        print("Investigate engine health (`engine_watchdog.py --status`) ")
        print("before retrying. This dry-run did NOT execute any check.")
        print()
        return 2

    # Run all 5 checks in order. Each tuple = (label, check_name, status, msg, details).
    # 順序跑 5 檢查；每 tuple = (label, check_name, status, msg, details)。
    results: list[tuple[str, str, str, str, dict[str, Any]]] = []

    s, m, d = check_a_exit_features_writer(args.engine_mode)
    results.append(("a", "exit_features_writer_24h", s, m, d))

    s, m, d = check_b_decision_shadow_exits_table()
    results.append(("b", "decision_shadow_exits_table", s, m, d))

    s, m, d = check_c_combine_layer_schema(args.engine_mode)
    results.append(("c", "combine_layer_schema", s, m, d))

    s, m, d = check_d_ipc_patch_path_dry(args.engine_mode, args.mock_events)
    results.append(("d", "ipc_patch_dry_round_trip", s, m, d))

    s, m, d = check_e_revert_path_constructible(args.engine_mode)
    results.append(("e", "revert_path_constructible", s, m, d))

    overall_pass = all(r[2] == "PASS" for r in results)

    # Markdown to stdout (operator-friendly, pipe-safe).
    # markdown 至 stdout（operator 友善 + 可 pipe）。
    _emit_markdown(
        [(r[0], r[1], r[2], r[3]) for r in results],
        args.engine_mode,
        overall_pass,
    )

    # JSON artifact to $OPENCLAW_DATA_DIR (shell wrapper consumes this).
    # JSON artifact 至 $OPENCLAW_DATA_DIR（shell wrapper 讀此）。
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", DEFAULT_DATA_DIR))
    artifact_path = data_dir / "edge_p2_flip_dry_run.json"
    _emit_json_artifact(
        {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "engine_mode": args.engine_mode,
            "mock_events_target": args.mock_events,
            "overall_pass": overall_pass,
            "checks": [
                {
                    "label": r[0],
                    "name": r[1],
                    "status": r[2],
                    "message": r[3],
                    "details": r[4],
                }
                for r in results
            ],
            "next_step": (
                "run helper_scripts/operator/edge_p2_flip.sh"
                if overall_pass
                else "investigate failed checks; do NOT flip"
            ),
            "rfc_reference": (
                "srv/docs/CCAgentWorkSpace/PA/workspace/reports/"
                "2026-04-26--edge_p2_flip_sop_rfc.md"
            ),
        },
        artifact_path,
    )

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
