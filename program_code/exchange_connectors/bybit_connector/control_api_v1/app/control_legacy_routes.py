from __future__ import annotations

"""
MODULE_NOTE (中文):
  Control / Operator legacy 路由（E5-P0-5 拆分自 legacy_routes.py）。
  包含 15 條路由，覆蓋系統重啟、canonical / closeout recheck、demo 狀態轉換、
  安全 bundle、各類 input 事件，以及產品族配置寫入。

    POST /api/v1/system/scheduled-restart         — 計劃重啟
    POST /api/v1/control/recheck/j-canonical
    POST /api/v1/control/recheck/k-canonical
    POST /api/v1/control/recheck/j-closeout
    POST /api/v1/control/recheck/k-closeout
    POST /api/v1/control/demo/validate
    POST /api/v1/control/demo/arm
    POST /api/v1/control/demo/enable
    POST /api/v1/control/demo/relock
    POST /api/v1/control/safe-recheck-bundle
    POST /api/v1/input/cost
    POST /api/v1/input/event
    POST /api/v1/input/manual-note
    POST /api/v1/input/config-change
    POST /api/v1/control/product-family/{family}/config

  ★ Monkey-patch 安全：envelope_response / get_latest_snapshot 皆在 request
    時間經 `_base.xxx(...)` 間接呼叫。

MODULE_NOTE (English):
  Control / operator write legacy routes (split out of legacy_routes.py in E5-P0-5).
  Contains 15 routes covering scheduled restart, canonical / closeout rechecks,
  demo state transitions, safe bundle, input events, and product-family config.

  ★ Monkey-patch safety: envelope_response / get_latest_snapshot resolved via
    `_base.xxx(...)` at request time.
"""

import logging
import os
import tempfile
import threading
import time
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from . import main_legacy as _base
from .control_ops import (
    apply_config_change,
    apply_input_action,
    apply_product_family_config,
    perform_demo_transition,
    perform_recheck,
    perform_safe_bundle,
    perform_validate,
)
from .state_models import (
    ConfigChangeAcceptedData,
    DemoTransitionData,
    DemoValidateData,
    InputAcceptedData,
    ProductFamilyConfigData,
    RecheckResultData,
    RequestEnvelope,
    ResponseEnvelope,
    SafeBundleData,
)


logger = logging.getLogger(__name__)


class ScheduledRestartRequest(BaseModel):
    """Request body for scheduled restart / 計劃重啟請求體."""

    delay_minutes: int = Field(
        ..., description="Restart delay in minutes (5/10/15/30/60)"
    )
    force_liquidate: bool = Field(
        False, description="Close profitable paper positions before restart"
    )

    def validate_delay(self) -> None:
        """Reject disallowed delay values / 拒絕不允許的延遲值."""
        if self.delay_minutes not in (5, 10, 15, 30, 60):
            raise ValueError("delay_minutes must be one of: 5, 10, 15, 30, 60")


def _close_profitable_paper_positions() -> dict[str, Any]:
    """
    Close paper positions where net PnL (after fees) > 0.
    關閉淨盈利（扣除手續費後）的紙盤倉位。

    DEAD-PY-1: Python PaperTradingEngine retired (ARCH-RC1 1C-3-F). Rust engine
    owns paper state, so this call always returns the retired-stub error.
    DEAD-PY-1：Python PaperTradingEngine 已退場（1C-3-F），Rust 引擎持有紙盤狀態。
    """
    return {
        "closed": [],
        "skipped": [],
        "error": "paper engine not initialized (retired, use Rust engine)",
    }


def _run_restart_in_background(delay_seconds: int) -> None:
    """
    Background thread: sleep then restart the uvicorn process.
    後台執行緒：等待後重啟 uvicorn 程序。

    Writes a temp shell script and executes it in a new session so the
    parent process can die without killing the restart script.
    寫入臨時 shell 腳本並在新 session 中執行，使父程序可退出而不殺死重啟腳本。
    """
    import subprocess
    import sys

    pid = os.getpid()
    python = sys.executable
    # Reconstruct uvicorn launch command / 重建 uvicorn 啟動命令
    work_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # P1-14: Use project logs/ dir instead of /tmp/ to prevent symlink attacks.
    # P1-14 修復：使用專案內 logs/ 目錄，防止符號連結攻擊。
    script_content = f"""#!/bin/bash
# OpenClaw scheduled restart script / 計劃重啟腳本
sleep {delay_seconds}
kill {pid} 2>/dev/null
sleep 3
cd {work_dir}
mkdir -p {work_dir}/logs
nohup {python} -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> {work_dir}/logs/restart.log 2>&1 &
echo "Restarted PID=$!" >> {work_dir}/logs/restart.log
"""
    try:
        fd, script_path = tempfile.mkstemp(suffix=".sh", prefix="openclaw_restart_")
        with os.fdopen(fd, "w") as f:
            f.write(script_content)
        os.chmod(script_path, 0o700)
        subprocess.Popen(
            ["bash", script_path],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(
            "Scheduled restart script launched: delay=%ds pid=%d",
            delay_seconds, pid,
        )
    except Exception as exc:
        logger.error("Failed to launch restart script: %s", exc)


def register_control_legacy_routes(app) -> None:
    """
    Register all control / operator-write legacy routes on the FastAPI app.
    在 FastAPI app 上註冊所有 control / operator-write legacy 路由。
    """
    settings = _base.settings

    # ── Scheduled Restart / 計劃重啟 ─────────────────────────────────────────

    @app.post(f"{settings.api_prefix}/system/scheduled-restart")
    def post_scheduled_restart(
        request: ScheduledRestartRequest,
        actor=Depends(_base.current_actor),
    ) -> dict[str, Any]:
        """
        Schedule a server restart after the specified delay.
        在指定延遲後計劃伺服器重啟。

        If force_liquidate=True, closes paper positions where net PnL > 0 immediately.
        Positions that would result in a net loss are left open.
        force_liquidate=True 時立即關閉淨盈利的紙盤倉位；會造成淨虧損的倉位保持開放。
        """
        try:
            request.validate_delay()
        except ValueError as exc:
            # Log actual error server-side for debugging; do not expose internals.
            # 伺服器端記錄實際錯誤供調試；不向客戶端洩露內部資訊。
            logger.debug("validate_delay failed: %s", exc)
            raise HTTPException(status_code=400, detail="Invalid delay parameter")

        liquidation_result: dict[str, Any] = {
            "closed": [], "skipped": [], "error": None,
        }
        if request.force_liquidate:
            liquidation_result = _close_profitable_paper_positions()

        delay_seconds = request.delay_minutes * 60
        restart_at_ts_ms = int(time.time() * 1000) + (delay_seconds * 1000)

        # Launch background restart / 啟動後台重啟
        t = threading.Thread(
            target=_run_restart_in_background,
            args=(delay_seconds,),
            daemon=True,
            name=f"scheduled-restart-{request.delay_minutes}m",
        )
        t.start()

        logger.info(
            "Scheduled restart in %d min (force_liquidate=%s) by %s",
            request.delay_minutes,
            request.force_liquidate,
            actor.get("operator_id", "unknown") if isinstance(actor, dict) else "unknown",
        )

        return {
            "action_result": "scheduled",
            "delay_minutes": request.delay_minutes,
            "restart_at_ts_ms": restart_at_ts_ms,
            "force_liquidate": request.force_liquidate,
            "positions_closed": liquidation_result["closed"],
            "positions_skipped": liquidation_result["skipped"],
            "liquidation_error": liquidation_result.get("error"),
            "message": f"Server will restart in {request.delay_minutes} minute(s).",
        }

    # ── Recheck Routes (J/K canonical/closeout) ──────────────────────────────

    @app.post(
        f"{settings.api_prefix}/control/recheck/j-canonical",
        response_model=ResponseEnvelope[RecheckResultData],
    )
    def post_j_canonical(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[RecheckResultData]:
        """J-canonical recheck / J canonical 複查."""
        result, action_result = perform_recheck(envelope, actor, "J", "canonical")
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=RecheckResultData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/control/recheck/k-canonical",
        response_model=ResponseEnvelope[RecheckResultData],
    )
    def post_k_canonical(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[RecheckResultData]:
        """K-canonical recheck / K canonical 複查."""
        result, action_result = perform_recheck(envelope, actor, "K", "canonical")
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=RecheckResultData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/control/recheck/j-closeout",
        response_model=ResponseEnvelope[RecheckResultData],
    )
    def post_j_closeout(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[RecheckResultData]:
        """J-closeout recheck / J closeout 複查."""
        result, action_result = perform_recheck(envelope, actor, "J", "closeout")
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=RecheckResultData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/control/recheck/k-closeout",
        response_model=ResponseEnvelope[RecheckResultData],
    )
    def post_k_closeout(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[RecheckResultData]:
        """K-closeout recheck / K closeout 複查."""
        result, action_result = perform_recheck(envelope, actor, "K", "closeout")
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=RecheckResultData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    # ── Demo State Transitions / Demo 狀態轉換 ────────────────────────────────

    @app.post(
        f"{settings.api_prefix}/control/demo/validate",
        response_model=ResponseEnvelope[DemoValidateData],
    )
    def post_demo_validate(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[DemoValidateData]:
        """Demo validate transition / Demo validate 狀態."""
        result, action_result = perform_validate(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=DemoValidateData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/control/demo/arm",
        response_model=ResponseEnvelope[DemoTransitionData],
    )
    def post_demo_arm(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[DemoTransitionData]:
        """Demo arm transition / Demo arm 狀態."""
        result, action_result = perform_demo_transition(envelope, actor, "arm")
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=DemoTransitionData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/control/demo/enable",
        response_model=ResponseEnvelope[DemoTransitionData],
    )
    def post_demo_enable(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[DemoTransitionData]:
        """Demo enable transition / Demo enable 狀態."""
        result, action_result = perform_demo_transition(envelope, actor, "enable")
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=DemoTransitionData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/control/demo/relock",
        response_model=ResponseEnvelope[DemoTransitionData],
    )
    def post_demo_relock(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[DemoTransitionData]:
        """Demo relock transition / Demo relock 狀態."""
        result, action_result = perform_demo_transition(envelope, actor, "relock")
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=DemoTransitionData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/control/safe-recheck-bundle",
        response_model=ResponseEnvelope[SafeBundleData],
    )
    def post_safe_bundle(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[SafeBundleData]:
        """Safe recheck bundle / 安全複查 bundle."""
        result, action_result = perform_safe_bundle(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=SafeBundleData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    # ── Input Events / 輸入事件 ───────────────────────────────────────────────

    @app.post(
        f"{settings.api_prefix}/input/cost",
        response_model=ResponseEnvelope[InputAcceptedData],
    )
    def post_input_cost(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[InputAcceptedData]:
        """Record cost input / 錄入成本事件."""
        result, action_result = apply_input_action(envelope, actor, "cost")
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=InputAcceptedData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/input/event",
        response_model=ResponseEnvelope[InputAcceptedData],
    )
    def post_input_event(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[InputAcceptedData]:
        """Record generic event input / 錄入通用事件."""
        result, action_result = apply_input_action(envelope, actor, "event")
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=InputAcceptedData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/input/manual-note",
        response_model=ResponseEnvelope[InputAcceptedData],
    )
    def post_input_note(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[InputAcceptedData]:
        """Record manual note input / 錄入手動備注."""
        result, action_result = apply_input_action(envelope, actor, "manual-note")
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=InputAcceptedData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    @app.post(
        f"{settings.api_prefix}/input/config-change",
        response_model=ResponseEnvelope[ConfigChangeAcceptedData],
    )
    def post_config_change(
        envelope: RequestEnvelope, actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[ConfigChangeAcceptedData]:
        """Apply config change / 套用配置變更."""
        result, action_result = apply_config_change(envelope, actor)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=ConfigChangeAcceptedData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )

    # ── Product Family Config Write Routes / 產品族配置寫入 ───────────────────

    @app.post(
        f"{settings.api_prefix}/control/product-family/{{family}}/config",
        response_model=ResponseEnvelope[ProductFamilyConfigData],
    )
    def post_product_family_config(
        family: str,
        envelope: RequestEnvelope,
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[ProductFamilyConfigData]:
        """
        Modify control configuration for a specific product family.
        修改指定產品族的控制配置。

        Supported payload fields / 支援的 payload 欄位：
        - enabled_switch: bool       啟用該產品族 / Enable this family
        - visibility_switch: bool    GUI 可見性 / GUI visibility
        - mode_switch: str           僅允許 disabled/observe_only/shadow_only/demo_reserved
        - action_permissions: dict   逐動作開關 / Per-action toggles

        Safety: cannot set live-related modes; requires `input:config` scope.
        安全：不能設定為 live 相關模式；需要 `input:config` scope。
        """
        result, action_result = apply_product_family_config(envelope, actor, family)
        return _base.envelope_response(
            snapshot=result["snapshot"],
            request_id=envelope.request_id,
            action_result=action_result,
            data=ProductFamilyConfigData(**result["data"]),
            audit_ref=result["audit_ref"],
            reason_codes=["replayed_request"] if action_result == "replayed" else [],
        )


__all__ = ["register_control_legacy_routes"]
