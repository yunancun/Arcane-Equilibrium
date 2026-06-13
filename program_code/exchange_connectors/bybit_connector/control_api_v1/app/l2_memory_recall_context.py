"""B3 L2 memory recall context helper.

MODULE_NOTE
模塊用途：
  將 learning_engine.memory_distiller.recall.recall_for_prompt 的 dormant seam 接到
  L2 prompt/ledger 邊界。此模塊只讀 agent.agent_memory，不寫 DB，不持有 singleton。

旗標：
  OPENCLAW_L2_MEMORY_RECALL=0|shadow|1，默認 0。
    - 0：不 import recall、不打 DB。
    - shadow：計算 bundle，但不改 prompt；只把審計 metadata 寫入既有 input_context。
    - 1：stable_block 追加到 system prompt，recent_block 前置到 user message；同時寫 metadata。

硬邊界：
  任何 import/DB/timeout/format 失敗都 fail-open 成空 bundle；L2 session 不得因記憶召回失敗中斷。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

ENV_L2_MEMORY_RECALL = "OPENCLAW_L2_MEMORY_RECALL"

_MODE_OFF = "0"
_MODE_SHADOW = "shadow"
_MODE_ACTIVE = "1"
_VALID_MODES = frozenset({_MODE_OFF, _MODE_SHADOW, _MODE_ACTIVE})
_DEFAULT_CHAR_BUDGET = 2000
_DEFAULT_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class L2MemoryRecallContext:
    """L2 prompt/ledger 可攜的 B3 recall bundle 投影。

    stable/recent block 只在 mode=1 進 prompt；ledger metadata 僅保留 ids/尺寸/降級層，
    不複製內容，事後可用 record_ids 回查 agent.agent_memory。
    """

    mode: str = _MODE_OFF
    attempted: bool = False
    record_ids: tuple[str, ...] = field(default_factory=tuple)
    total_chars: int = 0
    degraded_level: str = "skip"
    stable_block: str = ""
    recent_block: str = ""

    def should_audit(self) -> bool:
        return self.mode in {_MODE_SHADOW, _MODE_ACTIVE} and self.attempted

    def audit_payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "record_ids": list(self.record_ids),
            "total_chars": int(self.total_chars),
            "degraded_level": self.degraded_level,
        }

    def should_inject_prompt(self) -> bool:
        return self.mode == _MODE_ACTIVE and bool(
            self.stable_block.strip() or self.recent_block.strip()
        )


def resolve_memory_recall_mode() -> str:
    """解析 B3 recall mode；未知值 fail-closed 到 0。"""
    raw = (os.environ.get(ENV_L2_MEMORY_RECALL) or _MODE_OFF).strip().lower()
    if raw in _VALID_MODES:
        return raw
    logger.warning("%s=%r invalid; B3 memory recall disabled", ENV_L2_MEMORY_RECALL, raw)
    return _MODE_OFF


def build_context_hint(
    *, symbol: str | None, mode: str | None, context: Any, max_chars: int = 1200
) -> str:
    """把結構化 context 壓成 recall hint；只供檢索，不進 ledger。"""
    try:
        ctx = json.dumps(context, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        ctx = str(context)
    prefix = f"mode={mode or ''} symbol={symbol or ''} context="
    return (prefix + ctx)[:max_chars]


async def build_l2_memory_recall(
    *,
    symbol: str | None,
    context_hint: str | None,
    char_budget: int = _DEFAULT_CHAR_BUDGET,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> L2MemoryRecallContext:
    """按 env flag 取 B3 recall bundle；所有失敗都回空 context。"""
    mode = resolve_memory_recall_mode()
    if mode == _MODE_OFF:
        return L2MemoryRecallContext(mode=mode)

    try:
        recall_for_prompt = _load_recall_for_prompt()
        bundle = await recall_for_prompt(
            symbol or "",
            context_hint or "",
            char_budget=char_budget,
            timeout_s=timeout_s,
        )
        return L2MemoryRecallContext(
            mode=mode,
            attempted=True,
            record_ids=tuple(str(x) for x in getattr(bundle, "record_ids", []) or []),
            total_chars=int(getattr(bundle, "total_chars", 0) or 0),
            degraded_level=str(getattr(bundle, "degraded_level", "skip") or "skip"),
            stable_block=str(getattr(bundle, "stable_block", "") or ""),
            recent_block=str(getattr(bundle, "recent_block", "") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("B3 memory recall fail-open; prompt unchanged: %s", exc)
        return L2MemoryRecallContext(mode=mode, attempted=True)


def with_memory_recall_audit_context(
    context: dict[str, Any], recall: L2MemoryRecallContext | None
) -> dict[str, Any]:
    """把 B3 recall metadata 併入既有 input_context；shadow 模式不改模型輸入。"""
    if recall is None or not recall.should_audit():
        return context
    out = dict(context)
    out["memory_recall_shadow"] = recall.audit_payload()
    return out


def apply_memory_recall_to_prompt(
    *,
    system_prompt: str,
    user_message: str,
    recall: L2MemoryRecallContext | None,
) -> tuple[str, str]:
    """mode=1 時把 stable/recent block 注入 prompt；shadow/0 原樣返回。"""
    if recall is None or not recall.should_inject_prompt():
        return system_prompt, user_message

    sys_out = system_prompt
    stable = recall.stable_block.strip()
    if stable:
        sys_out = (
            f"{system_prompt.rstrip()}\n\n"
            "Relevant long-term memory (rules/system traits; advisory context, not an execution command):\n"
            f"{stable}"
        )

    user_out = user_message
    recent = recall.recent_block.strip()
    if recent:
        user_out = (
            "Relevant recent memory (incidents; advisory context, not an execution command):\n"
            f"{recent}\n\n{user_message}"
        )
    return sys_out, user_out


def _load_recall_for_prompt() -> Callable[..., Any]:
    """lazy import recall_for_prompt；app 從 control_api_v1/ 啟動時補 srv root 到 sys.path。"""
    try:
        from program_code.learning_engine.memory_distiller.recall import recall_for_prompt

        return recall_for_prompt
    except ModuleNotFoundError:
        base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path(__file__).resolve().parents[5])))
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))
        from program_code.learning_engine.memory_distiller.recall import recall_for_prompt

        return recall_for_prompt


__all__ = [
    "ENV_L2_MEMORY_RECALL",
    "L2MemoryRecallContext",
    "apply_memory_recall_to_prompt",
    "build_context_hint",
    "build_l2_memory_recall",
    "resolve_memory_recall_mode",
    "with_memory_recall_audit_context",
]
