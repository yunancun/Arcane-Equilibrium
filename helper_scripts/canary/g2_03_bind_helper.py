#!/usr/bin/env python3
"""
G2-03 ma_crossover SL/TP binding helper (PA RFC §6.T4 / §4.2 binding SOP).
G2-03 ma_crossover SL/TP 綁定輔助腳本（PA RFC §6.T4 / §4.2 binding SOP）。

MODULE_NOTE (English):
  Pure CLI helper invoked by `helper_scripts/operator/g2_03_bind_ma_sltp.sh`.
  Three subcommands:

    diff        — show before/after JSON of a candidate patch (read-only).
    apply       — send IPC `patch_risk_config` mutating the per_strategy
                   ma_crossover override fields (ONLY called after operator
                   confirm + QC report path passed in).
    verify      — read get_risk_config() and confirm the 4 override fields
                   landed at the expected values.

  Why split out from the shell wrapper:
    * Per memory `feedback_shell_paste_safety` — complex IPC + JSON math
      should not live inside heredocs; helper Python keeps the shell wrapper
      paste-safe (single-line case-statements, no multi-line for-loops).
    * Reuses `edge_p2_flip_dry_run._sync_ipc_call` for the HMAC handshake
      (which is calibrated against the Rust verifier — see RFC §IPC HMAC ts
      unit footnote in PA RFC `2026-04-26--edge_p2_flip_sop_rfc.md`).
    * Single source of truth for the patch payload shape — shell wrapper
      passes 4 floats; helper builds the {per_strategy: {ma_crossover: {...}}}
      JSON exactly once.

MODULE_NOTE (中文):
  純 CLI 輔助腳本，由 `helper_scripts/operator/g2_03_bind_ma_sltp.sh` 呼叫。
  3 子命令：diff（讀僅 before/after）/ apply（真送 IPC patch）/ verify
  （讀 get_risk_config 確認 4 欄位落地）。

  抽出原因：
    * memory `feedback_shell_paste_safety` —— 複雜 IPC + JSON 邏輯不該寫在
      heredoc，helper Python 讓 shell wrapper 維持 paste-safe（單行 case，
      無多行 for）。
    * 重用 `edge_p2_flip_dry_run._sync_ipc_call` 的 HMAC 握手（已對齊 Rust
      verifier，避開 legacy sync_ipc_call 毫秒 bug）。
    * patch payload shape 單一來源；shell 傳 4 floats，helper 構造唯一 JSON。

CLI:
  python3 g2_03_bind_helper.py diff   --engine-mode <env> \\
                                      --sl-pct <f> --tp-pct <f> \\
                                      --trail-act-pct <f> --trail-dist-pct <f>
  python3 g2_03_bind_helper.py apply  --engine-mode <env> \\
                                      --sl-pct <f> ... [same 4 args]
  python3 g2_03_bind_helper.py verify --engine-mode <env> \\
                                      --sl-pct <f> ... [same 4 args]

Exit codes:
  0 — operation succeeded (diff produced / apply OK / verify match)
  1 — operation failed (validate error / engine reject / verify mismatch)
  2 — IPC connect failure (engine down or socket missing)
  3 — argument error (missing flag / invalid float)

Outputs:
  stdout — JSON envelope {action, engine, before, after, status, ...}
  stderr — INFO log

Reference / 參考:
  PA RFC: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g2_03_option_b_rfc.md
  Reuses _sync_ipc_call from edge_p2_flip_dry_run.py (same HMAC seconds path).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# stderr logging keeps stdout (JSON envelope) machine-parseable.
# stderr 日誌讓 stdout（JSON envelope）可機器解析。
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [g2_03_bind] %(levelname)s %(message)s",
)
logger = logging.getLogger("g2_03_bind_helper")


# ═══════════════════════════════════════════════════════════════════════════════
# Env / paths / 環境與路徑
# ═══════════════════════════════════════════════════════════════════════════════

# Resolve srv root: helper lives at srv/helper_scripts/canary/g2_03_bind_helper.py.
# 解析 srv root：本檔位於 srv/helper_scripts/canary/g2_03_bind_helper.py。
THIS_FILE = Path(__file__).resolve()
SRV_ROOT = THIS_FILE.parent.parent.parent  # canary -> helper_scripts -> srv
sys.path.insert(0, str(SRV_ROOT / "helper_scripts" / "canary"))

# Reuse _sync_ipc_call from the EDGE-P2-flip dry-run script — single source of
# truth for IPC handshake (HMAC ts in seconds, calibrated against Rust verifier).
# 重用 edge_p2_flip_dry_run._sync_ipc_call —— IPC 握手單一來源（HMAC ts 用秒）。
try:
    from edge_p2_flip_dry_run import _sync_ipc_call  # type: ignore[import]
except ImportError as e:
    logger.error("Failed to import _sync_ipc_call from edge_p2_flip_dry_run: %s", e)
    sys.exit(3)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════════

VALID_ENGINE_MODES = {"paper", "demo", "live", "live_demo"}

# 4 override fields ordered for stable JSON output.
# 4 個 override 欄位排序確保 JSON 輸出穩定。
OVERRIDE_FIELDS = (
    "stop_loss_max_pct_override",
    "take_profit_max_pct_override",
    "trailing_activation_pct_override",
    "trailing_distance_pct_override",
)


# ═══════════════════════════════════════════════════════════════════════════════
# Argument validation / 參數驗證
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_floats(args: argparse.Namespace) -> dict[str, float]:
    """
    Validate the 4 override floats: must be finite + > 0. Defense-in-depth on
    top of Rust validate() — catches typos before round-tripping to engine.
    驗證 4 個 override 為 finite > 0；提前抓拼寫錯，不靠 Rust validate。
    """
    out: dict[str, float] = {}
    for arg_name, field_name in (
        ("sl_pct", "stop_loss_max_pct_override"),
        ("tp_pct", "take_profit_max_pct_override"),
        ("trail_act_pct", "trailing_activation_pct_override"),
        ("trail_dist_pct", "trailing_distance_pct_override"),
    ):
        v = getattr(args, arg_name)
        if v is None:
            logger.error("missing required arg --%s", arg_name.replace("_", "-"))
            sys.exit(3)
        try:
            f = float(v)
        except (TypeError, ValueError):
            logger.error("--%s must be a float, got %r", arg_name.replace("_", "-"), v)
            sys.exit(3)
        # Reject NaN, +/-Inf, <= 0 — would be rejected by Rust validate too,
        # but failing fast in Python lets operators see the error before
        # the IPC trip.
        # 拒 NaN/Inf/<=0 —— Rust validate 也會拒，提前在 Python 失敗。
        if f != f or f == float("inf") or f == float("-inf") or f <= 0.0:
            logger.error(
                "--%s must be finite > 0, got %s",
                arg_name.replace("_", "-"),
                f,
            )
            sys.exit(3)
        out[field_name] = f
    return out


def _build_patch_payload(engine_mode: str, overrides: dict[str, float]) -> dict[str, Any]:
    """
    Construct the IPC patch_risk_config payload. Per PA RFC § 6.T1 the per_strategy
    keys are merged via deep-merge inside Rust ConfigStore, so we send only the
    ma_crossover overrides — other strategies / fields untouched.
    構造 IPC patch payload；per_strategy 經 Rust deep-merge，只送 ma_crossover 子欄位。
    """
    patch_obj = {
        "per_strategy": {
            "ma_crossover": {
                # enabled stays true (default); we don't touch it.
                # enabled 保持 true（預設），本次不動。
                **overrides,
            }
        }
    }
    return {
        "engine": engine_mode,
        "source": "operator",
        "patch": patch_obj,
    }


def _read_current_overrides(engine_mode: str) -> dict[str, Any]:
    """
    Read the current per_strategy.ma_crossover override values from the engine.
    Returns a dict with 4 keys (None for unset fields).
    從 engine 讀現行 ma_crossover override；4 個欄位 dict（未設為 None）。
    """
    result = _sync_ipc_call("get_risk_config", params={"engine": engine_mode})
    if not isinstance(result, dict):
        raise RuntimeError(f"get_risk_config returned non-dict: {result!r}")
    cfg = result.get("config")
    if not isinstance(cfg, dict):
        raise RuntimeError("get_risk_config result missing 'config' field")
    per_strategy = cfg.get("per_strategy") or {}
    ma = per_strategy.get("ma_crossover") or {}
    return {
        f: ma.get(f) for f in OVERRIDE_FIELDS
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Subcommand handlers / 子命令處理
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_diff(args: argparse.Namespace) -> int:
    """
    diff subcommand: read current overrides, build candidate, print before/after.
    No mutation. Operator pipes this output into a review queue.
    diff 子命令：讀當前值，構造候選，輸出 before/after，無變更。
    """
    overrides = _validate_floats(args)
    try:
        before = _read_current_overrides(args.engine_mode)
    except FileNotFoundError as e:
        logger.error("engine socket missing: %s", e)
        sys.exit(2)
    except (PermissionError, RuntimeError, ConnectionResetError) as e:
        logger.error("IPC error: %s", e)
        sys.exit(2)

    after = dict(before)
    for k, v in overrides.items():
        after[k] = v

    payload = _build_patch_payload(args.engine_mode, overrides)

    envelope = {
        "action": "diff",
        "engine": args.engine_mode,
        "before": before,
        "after": after,
        "patch_payload_preview": payload,
        "qc_report_path": args.qc_report_path,
        "status": "ok",
    }
    print(json.dumps(envelope, indent=2, sort_keys=True))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    """
    apply subcommand: send the mutating IPC patch_risk_config call.
    Returns engine response. Caller (shell wrapper) is responsible for
    confirming with operator + checking qc_report_path BEFORE calling apply.
    apply 子命令：真送 IPC patch；caller 負責 operator 確認 + QC report 檢查。
    """
    overrides = _validate_floats(args)
    if not args.qc_report_path:
        logger.error("--qc-report-path REQUIRED for apply (PA RFC §4.2 binding SOP)")
        sys.exit(3)
    qc_path = Path(args.qc_report_path)
    if not qc_path.exists():
        logger.error("QC report not found at %s — cannot apply binding", qc_path)
        sys.exit(3)

    payload = _build_patch_payload(args.engine_mode, overrides)
    logger.info("sending IPC patch_risk_config to %s engine", args.engine_mode)
    try:
        result = _sync_ipc_call("patch_risk_config", params=payload)
    except FileNotFoundError as e:
        logger.error("engine socket missing: %s", e)
        sys.exit(2)
    except (PermissionError, RuntimeError, ConnectionResetError) as e:
        logger.error("IPC error: %s", e)
        envelope = {
            "action": "apply",
            "engine": args.engine_mode,
            "status": "fail",
            "error": str(e),
        }
        print(json.dumps(envelope, indent=2, sort_keys=True))
        sys.exit(1)

    envelope = {
        "action": "apply",
        "engine": args.engine_mode,
        "patch_sent": payload,
        "engine_response": result,
        "qc_report_path": str(qc_path),
        "status": "ok" if (isinstance(result, dict) and result.get("ok") is True) else "fail",
    }
    print(json.dumps(envelope, indent=2, sort_keys=True))
    return 0 if envelope["status"] == "ok" else 1


def cmd_verify(args: argparse.Namespace) -> int:
    """
    verify subcommand: read get_risk_config and confirm 4 override fields match
    the expected values. Used by shell wrapper after apply (5s sleep + verify).
    verify 子命令：讀 get_risk_config 確認 4 欄位匹配；shell wrapper apply 後跑。
    """
    overrides = _validate_floats(args)
    try:
        actual = _read_current_overrides(args.engine_mode)
    except FileNotFoundError as e:
        logger.error("engine socket missing: %s", e)
        sys.exit(2)
    except (PermissionError, RuntimeError, ConnectionResetError) as e:
        logger.error("IPC error: %s", e)
        sys.exit(2)

    mismatches: list[str] = []
    for field, expected in overrides.items():
        got = actual.get(field)
        # Tolerance 1e-9 for f64 round-trip; engine should not transform values
        # but TOML serialize/deserialize can have minor precision drift.
        # 1e-9 容差防 TOML round-trip 微差；engine 不該改值但 round-trip 可能有 ULP 飄。
        if got is None or abs(float(got) - expected) > 1e-9:
            mismatches.append(f"{field}: expected={expected}, got={got}")

    envelope = {
        "action": "verify",
        "engine": args.engine_mode,
        "expected": overrides,
        "actual": actual,
        "mismatches": mismatches,
        "status": "ok" if not mismatches else "fail",
    }
    print(json.dumps(envelope, indent=2, sort_keys=True))
    return 0 if not mismatches else 1


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point / 主入口
# ═══════════════════════════════════════════════════════════════════════════════

def _build_parser() -> argparse.ArgumentParser:
    """
    Build the argparse parser. Three subcommands share the 4 override floats.
    建構 argparse parser；3 子命令共享 4 個 override 浮點。
    """
    p = argparse.ArgumentParser(
        prog="g2_03_bind_helper",
        description="G2-03 ma_crossover SL/TP binding helper (PA RFC §6.T4)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def _add_common(sp: argparse.ArgumentParser) -> None:
        # Common 4 override args + engine mode.
        # 共通 4 個 override 參數 + engine mode。
        sp.add_argument(
            "--engine-mode",
            required=True,
            choices=sorted(VALID_ENGINE_MODES),
            help="target engine (paper / demo / live / live_demo)",
        )
        sp.add_argument(
            "--sl-pct",
            type=str,
            required=True,
            help="stop_loss_max_pct_override (must be finite > 0 and <= P1 limit)",
        )
        sp.add_argument(
            "--tp-pct",
            type=str,
            required=True,
            help="take_profit_max_pct_override (must be finite > 0 and <= P1 limit)",
        )
        sp.add_argument(
            "--trail-act-pct",
            type=str,
            required=True,
            help="trailing_activation_pct_override (must be finite > 0)",
        )
        sp.add_argument(
            "--trail-dist-pct",
            type=str,
            required=True,
            help="trailing_distance_pct_override (must be finite > 0)",
        )
        sp.add_argument(
            "--qc-report-path",
            type=str,
            default=None,
            help="path to QC report PDF/markdown (REQUIRED for apply subcommand)",
        )

    sp_diff = sub.add_parser("diff", help="show before/after override values")
    _add_common(sp_diff)
    sp_apply = sub.add_parser("apply", help="send mutating IPC patch_risk_config")
    _add_common(sp_apply)
    sp_verify = sub.add_parser("verify", help="read get_risk_config + confirm match")
    _add_common(sp_verify)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "diff":
        return cmd_diff(args)
    if args.cmd == "apply":
        return cmd_apply(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    parser.error(f"unknown subcommand: {args.cmd}")
    return 3


if __name__ == "__main__":
    sys.exit(main())
