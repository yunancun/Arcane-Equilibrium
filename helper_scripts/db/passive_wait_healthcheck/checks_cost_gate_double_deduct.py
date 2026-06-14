"""Cost-gate double-cost-deduct preventive sentinel wrapper [90].

MODULE_NOTE:
  PROFIT-1 cost_gate「雙重扣成本」latent issue 預防性哨兵的 passive_wait
  註冊點。本檔僅作 runner.py wrapper + verdict 提取，不重複實作——核心
  SSOT 是 standalone
  ``helper_scripts/canary/healthchecks/check_cost_gate_double_deduct.py``
  （與 [80] pg_dump wrapper delegate 給 standalone 同模式，保單一 SSOT）。

  latent issue 摘要：runtime-derived 正 edge cell 的 `runtime_bps` 已是
  扣成本後淨值，cost_gate 又用 `threshold_bps = fee_bps /
  clamp(win_rate, floor, 1.0) × safety_multiplier` 二次扣成本門檻比較→誤拒
  （門檻 per-cell，依該 cell 的 win_rate，與 gates.rs 一致）。replay 裁 NO-FIX
  （dormant：active 路徑要求 validation_passed==true，而目前無 validated-positive
  cell）。
  風險窗：parallel session 建 explore-gate，一旦把 validation_passed=true 寫到
  正 cell，此誤拒由 dormant 轉 active。本 check 把它轉為可監測：偵測
    validation_passed==true AND runtime_bps>0 AND runtime_bps < threshold_bps
  的 cell（三環境分別算門檻），count>0 → WARN。

  WARN-by-default：本 check 是 latent issue 早期預警（gate 邏輯 replay 已裁
  NO-FIX 不改），非 promotion-blocking surface。OPENCLAW_COST_GATE_DOUBLE_DEDUCT_REQUIRED=1
  可升 WARN → FAIL 進入 fail-closed 模式（與 [80] OPENCLAW_CRON_HEARTBEAT_REQUIRED
  同慣例，但獨立 env 避免誤連動）。

  fail-soft：standalone import 失敗 / run() 拋例外 → 預設 WARN（runner 不可
  crash，其他 check 仍要跑完）；REQUIRED=1 時升 FAIL。standalone 自身對
  缺 config / 缺 cell 回 INSUFFICIENT_SAMPLE（SKIP）透傳。
"""

from __future__ import annotations

import os


_REQUIRED_ENV = "OPENCLAW_COST_GATE_DOUBLE_DEDUCT_REQUIRED"
_TRUE_VALUES = {"1", "true", "yes", "on", "required"}


def _required_mode() -> bool:
    return os.environ.get(_REQUIRED_ENV, "").strip().lower() in _TRUE_VALUES


def check_90_cost_gate_double_deduct() -> tuple[str, str]:
    """[90] PROFIT-1 cost_gate 雙重扣成本 latent issue 預防性哨兵（delegate standalone）。

    為什麼 wrapper 而非自己實作：standalone
    ``helper_scripts/canary/healthchecks/check_cost_gate_double_deduct.py`` 是
    SSOT（operator ad-hoc + dashboard 共用 + threshold 公式與 gates.rs 對齊
    只維護一處）；本檔 delegate 取 verdict + per-env 摘要 collapse 成 runner.py
    期待的 ``(verdict, msg)`` tuple。

    特殊處理：
      - import 失敗（standalone 缺檔）→ WARN（REQUIRED=1 升 FAIL）
      - standalone run() 拋例外 → WARN（REQUIRED=1 升 FAIL）；runner 不 crash
      - 整體 verdict 透傳；WARN 在 REQUIRED=1 時升 FAIL
      - INSUFFICIENT_SAMPLE（無 config / 無 validated-positive cell）透傳，
        避免 first-day / dormant 階段製造噪音
    """
    try:
        # 為什麼用 importlib：standalone module 在
        # ``srv/helper_scripts/canary/healthchecks/`` 不在本 package；走 sys.path
        # 動態 import 避免硬編 relative import 跨 package（對齊 [80] check_80 模式）。
        import importlib
        import sys
        from pathlib import Path

        srv_root = (
            os.environ.get("OPENCLAW_BASE_DIR")
            or str(Path.home() / "BybitOpenClaw" / "srv")
        )
        healthchecks_dir = Path(srv_root) / "helper_scripts" / "canary" / "healthchecks"
        if str(healthchecks_dir) not in sys.path:
            sys.path.insert(0, str(healthchecks_dir))

        mod = importlib.import_module("check_cost_gate_double_deduct")
    except ImportError as e:
        severity = "FAIL" if _required_mode() else "WARN"
        return (
            severity,
            f"[90] standalone check_cost_gate_double_deduct import failed: {e} "
            "— PROFIT-1 sentinel infra missing",
        )

    try:
        result = mod.run()
    except Exception as e:  # noqa: BLE001 — runner 不可 crash 必須包裝
        severity = "FAIL" if _required_mode() else "WARN"
        return (
            severity,
            f"[90] standalone run() raised {type(e).__name__}: {e}",
        )

    overall = result.get("verdict", "WARN")
    checks = result.get("checks", [])
    # Collapse 成單行：``[90] cost_gate_double_deduct verdict=PASS (3 env: ...)``。
    # 取 non-PASS 的 env + verdict 摘要；全 PASS 則只報 count。
    non_pass = [
        f"{c['id']}:{c['verdict']}"
        for c in checks
        if c.get("verdict") != "PASS"
    ]
    if non_pass:
        summary = (
            f"[90] cost_gate_double_deduct verdict={overall} "
            f"({len(checks)} env: {', '.join(non_pass)})"
        )
    else:
        summary = (
            f"[90] cost_gate_double_deduct verdict={overall} "
            f"({len(checks)} env all PASS — 0 double-deduct cell)"
        )

    # WARN 在 REQUIRED=1 時升 FAIL；FAIL 永不降級（雙重扣成本誤拒已 active 必須堵）。
    severity = overall
    if overall == "WARN" and _required_mode():
        severity = "FAIL"
    return (severity, summary)
