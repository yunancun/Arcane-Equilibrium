"""bb_breakout strategy healthchecks.

MODULE_NOTE (EN): Split from ``checks_strategy.py`` by
CHECKS-STRATEGY-SUBSPLIT to keep the strategy healthcheck module below the
1200-line governance threshold while preserving the public import path through
``checks_strategy``.

MODULE_NOTE (中): CHECKS-STRATEGY-SUBSPLIT 從 ``checks_strategy.py`` 拆出，
讓策略 healthcheck 主模組維持 1200 行以下；外部仍可經 ``checks_strategy``
原路徑 import。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from .db import _scalar
from .shared import (
    _read_bb_breakout_active_from_toml,
    _read_bb_breakout_config_from_toml,
)


def _bb_breakout_rescue_config_summary() -> tuple[bool, str]:
    """Return whether demo bb_breakout has the post-F1 rescue gate profile.
    判斷 demo bb_breakout 是否已套用 F1 後的 rescue 閘值配置。
    """
    section, diag = _read_bb_breakout_config_from_toml()
    if section is None:
        return (False, diag)

    try:
        squeeze = float(section.get("squeeze_bw"))
        expansion = float(section.get("expansion_bw"))
        volume = float(section.get("volume_threshold"))
    except (TypeError, ValueError):
        return (False, "bb_breakout rescue params missing/non-numeric")

    donchian = str(section.get("donchian_mode", "hard")).lower()
    try:
        persistence_ms = int(section.get("min_persistence_ms", 60_000))
    except (TypeError, ValueError):
        persistence_ms = 60_000

    # The 2026-04-24 sweep showed the legacy 1m gate family
    # (squeeze≈0.02/0.03, expansion≈0.04) was structurally unreachable.
    # Treat this as "rescued" only when the deployed demo config is in the
    # observed 1m band and Donchian/persistence no longer recreate the
    # old hard 5-AND chain.
    # 2026-04-24 sweep 證實舊 1m gate family 結構不可達；只有落在觀測 1m
    # 區間且 Donchian/persistence 不再形成硬 5-AND 鏈時才視為 rescue。
    rescued = (
        0.0 < squeeze < expansion <= 0.011
        and squeeze <= 0.0035
        and volume <= 1.2
        and (donchian in {"score", "off"} or persistence_ms <= 30_000)
    )
    summary = (
        f"squeeze={squeeze:g}, expansion={expansion:g}, volume={volume:g}, "
        f"donchian={donchian}, persistence_ms={persistence_ms}"
    )
    return (rescued, summary)


def check_bb_breakout_post_deadlock_fix(cur) -> tuple[str, str]:
    """[12] bb_breakout post-FIX-26-DEADLOCK-1 fill rate — P1-11 (1) Phase 1.

    G2-06 (2026-04-26): If `[bb_breakout].active=false` in
    `settings/strategy_params_demo.toml` (per PA RFC `2026-04-26 G2-06`
    permanent disable), this check returns PASS (skip) immediately —
    silencing the FAIL noise so other dormancy checks remain visible.
    Re-enabling the strategy (active=true) restores the original 3-state
    triage logic without further code changes.

    Context: 2026-04-24 sweep + Rust commit ``bcc5401`` discovered + fixed
    `squeeze_detected_ms` permanent-deadlock bug. Pre-fix, bb_breakout had
    14d 0 fills (symbol-locked after first failed-entry expiry). Post-fix
    + ``--rebuild`` deploy + multiple validation cycles still showed 0 fills,
    confirming F1 1m bandwidth mis-scale is structural (not deadlock
    residue). PA RFC 2026-04-26 chose option C (permanent disable).

    Three-state triage (when active=true):
      - 7d entries (`strategy_name='bb_breakout'`, no risk_close prefix):
        - 0 over 7d post-deploy → FAIL (fix didn't work or thresholds still
          mis-scaled per F1; check engine binary rebuild + thresholds)
        - 1-5 over 7d → WARN (out of dormant but very low; threshold tuning
          per Phase 2 backlog needed)
        - ≥6 over 7d → PASS (operating normally)
      - Pre-deploy state: this check fails until ``--rebuild`` deploys the
        Rust fix. Operator should mark this expected until that happens.

    The check looks for the **engine PID start time** as a deploy proxy
    (`/tmp/openclaw/engine_pid` mtime); if absent, falls back to a
    7d-window strategy fill count without deploy gating.

    [12] FIX-26-DEADLOCK-1 部署後 bb_breakout 是否真的脫離 permanent-dormant。
    G2-06（2026-04-26）：若 demo TOML `[bb_breakout].active=false`（PA RFC
    永久 disable）則直接 PASS 跳過，避免持續 FAIL 噪音蓋過真 alarm；TOML
    flip 回 true 後自動恢復原三態邏輯，無需改碼。
    7d entry 數三態（active=true 時）：0=FAIL（修沒生效或閾值還錯）/
    1-5=WARN（出 dormant 但極低）/ >=6=PASS（正常運作）。
    """
    # G2-06 (2026-04-26): TOML-driven disable skip — PA RFC permanent disable.
    # Read demo strategy_params TOML; if [bb_breakout].active=false, skip.
    # Fail-soft: any TOML read error falls through to original triage logic.
    # G2-06：讀 demo TOML，active=false 則跳過；TOML 讀失敗 fail-soft 走原邏輯。
    bb_active, _diag = _read_bb_breakout_active_from_toml()
    if bb_active is False:
        return (
            "PASS",
            "[12] bb_breakout disabled by G2-06 (active=false in TOML); fill check skipped",
        )

    try:
        n_7d = _scalar(cur,
            "SELECT COUNT(*) FROM trading.fills "
            "WHERE ts > now() - interval '7 days' "
            "AND engine_mode = 'demo' "
            "AND strategy_name = 'bb_breakout'"
        )
    except Exception as e:
        return ("WARN", f"bb_breakout 7d query failed: {e}")

    # Deploy proxy: check engine PID file mtime as a "since-rebuild" timestamp.
    # 部署代理：用 engine PID 檔 mtime 作「自 rebuild 起算」時間。
    deploy_age_hint = ""
    try:
        pid_path = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")) / "engine_pid"
        if pid_path.exists():
            mtime = datetime.fromtimestamp(pid_path.stat().st_mtime, tz=timezone.utc)
            age_h = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600.0
            deploy_age_hint = f", engine_pid age {age_h:.1f}h"
            # If engine deployed within last 7d, the "7d window" includes
            # pre-fix bars. Operator should re-eval after >7d of post-fix runtime.
            # 引擎部署 <7d 時 7d 窗包含修前資料，需等 >7d 才有 clean baseline。
            if age_h < 168:  # < 7d
                deploy_age_hint += " (window includes pre-fix data, baseline pending)"
    except Exception:
        pass

    if n_7d == 0:
        rescue_ok, rescue_msg = _bb_breakout_rescue_config_summary()
        if rescue_ok:
            return (
                "PASS",
                f"bb_breakout 7d entries=0{deploy_age_hint} — demo rescue config deployed "
                f"({rescue_msg}); fill baseline pending, no legacy deadlock/mis-scale FAIL",
            )
        return (
            "FAIL",
            f"bb_breakout 7d entries=0{deploy_age_hint} — FIX-26-DEADLOCK-1 fix "
            f"may not be deployed (--rebuild?) or thresholds still mis-scaled (P1-11 F1)",
        )
    if n_7d < 6:
        return (
            "WARN",
            f"bb_breakout 7d entries={n_7d}{deploy_age_hint} — out of permanent-dormant "
            f"but very low; Phase 2 threshold tuning recommended",
        )
    return (
        "PASS",
        f"bb_breakout 7d entries={n_7d}{deploy_age_hint} — operating normally post-deadlock-fix",
    )
