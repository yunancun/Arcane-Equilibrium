"""Shared TOML helpers used by multiple checks.
多個 check 共用的 TOML helper。

MODULE_NOTE (EN): Centralised the two ``_read_*_from_toml`` helpers so
``check_bb_breakout_post_deadlock_fix`` (in ``checks_strategy.py``),
``check_disabled_strategy_inventory`` (in ``checks_derived.py``), and
``check_shadow_exit_ratio`` (in ``checks_ipc_edge.py``) can all import
from the same module without circular dependencies.

Both helpers return ``(value | None, diagnostic)``:
- ``None`` on any fail-soft condition (file missing / TOML parse error /
  key absent / non-bool).
- The string diagnostic carries human-readable reason for the None branch
  so the caller can annotate its PASS/FAIL message.

Uses Python 3.11+ ``tomllib`` (already used elsewhere in this codebase —
e.g. ``paper_trading_routes.py:1044``). No external dependency added.

MODULE_NOTE (中): 集中兩個 ``_read_*_from_toml`` helper，避免拆分後
``checks_strategy`` / ``checks_derived`` / ``checks_ipc_edge`` 三 module
互相 import；皆回 ``(value | None, diag)``，None 含 fail-soft 文字診斷
供 caller 在 PASS/FAIL 訊息上 annotate。用 tomllib（3.11+，codebase 既有）。
"""

from __future__ import annotations

import os
from pathlib import Path


def _read_bb_breakout_active_from_toml() -> tuple[bool | None, str]:
    """G2-06 (2026-04-26): parse `[bb_breakout].active` from
    `settings/strategy_params_demo.toml`.

    Returns ``(value, diagnostic)``. ``value`` is True/False on successful
    parse + key lookup, ``None`` on any fail-soft condition (file missing /
    parse error / key absent / non-bool). ``diagnostic`` carries the
    human-readable reason for the ``None`` branch.

    Mirrors `_read_shadow_enabled_from_toml` shape; uses Python 3.11+
    ``tomllib`` (already used elsewhere in this codebase). No external
    dependency added. Reads the **actual value** rather than mtime as a
    state proxy — operator can hand-edit TOML and mtime would skew.

    G2-06：讀 demo strategy_params TOML 的 `[bb_breakout].active` 真值，
    fail-soft 回 ``None``。與 `_read_shadow_enabled_from_toml` 同形狀。
    用 tomllib（3.11+，codebase 既有），刻意取真值而非 mtime。
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        return (None, "tomllib unavailable (Python <3.11?)")

    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    toml_path = base / "settings" / "strategy_params_demo.toml"

    if not toml_path.exists():
        return (None, f"strategy_params_demo.toml not found at {toml_path}")

    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        # Fail-soft: TOML parse error degrades to original triage logic.
        # fail-soft：TOML parse 失敗則降級走原 triage。
        return (None, f"TOML parse error: {e}")

    section = data.get("bb_breakout")
    if not isinstance(section, dict):
        return (None, "[bb_breakout] section absent in strategy_params_demo.toml")

    val = section.get("active")
    if not isinstance(val, bool):
        return (None, f"[bb_breakout].active missing or non-bool (got {val!r})")

    return (val, "ok")


def _read_shadow_enabled_from_toml() -> tuple[bool | None, str]:
    """INFRA-PREBUILD-1 L2-5 (2026-04-23): parse `[exit].shadow_enabled` from
    `settings/risk_control_rules/risk_config_demo.toml`.

    Returns a ``(value, diagnostic)`` tuple. ``value`` is True/False when the
    TOML parse and key lookup both succeed, ``None`` on any fail-soft condition
    (file missing / parse error / key absent). ``diagnostic`` carries the
    human-readable reason for the ``None`` branch so check_shadow_exit_ratio
    can annotate its PASS/FAIL message.

    Uses Python 3.11+ ``tomllib`` (already used elsewhere in this codebase —
    see paper_trading_routes.py:1044). No external dependency added.

    We deliberately parse the **actual value** rather than trusting the file
    mtime as a "flag state" proxy — operators can hand-edit the TOML and the
    mtime skew would desynchronise. This is the hot-reload contract: state
    comes from the parsed `shadow_enabled` key, nothing else.

    L2-5 TOML 解析：讀 `[exit].shadow_enabled` 真值，fail-soft 回 ``None``。
    用 tomllib（3.11+，codebase 既有使用）；刻意取真值而非 mtime，因為
    operator 可能手編 TOML 導致 mtime 與 flag 狀態不同步。
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        return (None, "tomllib unavailable (Python <3.11?)")

    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    toml_path = base / "settings" / "risk_control_rules" / "risk_config_demo.toml"

    if not toml_path.exists():
        return (None, f"risk_config_demo.toml not found at {toml_path}")

    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        # Fail-soft: TOML parse error does not flag the whole pipeline dead;
        # check_shadow_exit_ratio degrades to its pre-L2-5 ambiguous message.
        # fail-soft：TOML parse 失敗不讓整條 pipeline 紅，check 降級為原本訊息。
        return (None, f"TOML parse error: {e}")

    exit_section = data.get("exit")
    if not isinstance(exit_section, dict):
        return (None, "[exit] section absent in risk_config_demo.toml")

    val = exit_section.get("shadow_enabled")
    if not isinstance(val, bool):
        return (None, f"[exit].shadow_enabled missing or non-bool (got {val!r})")

    return (val, "ok")
