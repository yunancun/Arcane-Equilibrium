"""
MODULE_NOTE (中文):
  H4 AI 輸出驗證器 — 驗證 AI 回傳結構的完整性與合理性。
  從 strategist_agent.py 拆分而來（§14.1 行數約定）。
  職責：
  1. confidence 存在性、數值型別、[0,1] 範圍檢查
  2. has_edge 布林型別檢查
  3. reason 非空字串檢查（根原則 8：交易可解釋）
  4. action 合法集合檢查（BUY/SELL/HOLD/SKIP）
  零循環依賴：只依賴標準庫，不 import 同目錄其他模組。

MODULE_NOTE (English):
  H4 AI output validator — validates AI response structure integrity.
  Extracted from strategist_agent.py (§14.1 line limit compliance).
  Responsibilities:
  1. confidence: presence, numeric type, [0,1] range
  2. has_edge: bool type check
  3. reason: non-empty string (principle 8: explainability)
  4. action: valid set membership (BUY/SELL/HOLD/SKIP)
  Zero circular imports: only depends on stdlib, no same-directory imports.

  Allowed imports: stdlib only (logging).
  Forbidden imports: any app.* module (to prevent circular dependency).
"""

from __future__ import annotations

import logging
from typing import FrozenSet

logger = logging.getLogger(__name__)

# Valid AI output actions — fail-closed: unknown action -> reject
# 合法的 AI 輸出動作 — fail-closed：未知動作 -> 拒絕
VALID_ACTIONS: FrozenSet[str] = frozenset({"BUY", "SELL", "HOLD", "SKIP"})


def validate_ai_output(parsed: dict) -> bool:
    """
    H4 validation: verify AI output structure before constructing EdgeEvaluation.
    H4 輸出驗證：在構造 EdgeEvaluation 前確認 AI 輸出結構完整且合理。

    Returns True if valid, False if output should be rejected (fallback to heuristic).
    返回 True 表示有效，False 表示應拒絕並降級到啟發式評估。

    Principle 6: reject -> heuristic, never allow-all.
    原則 6：拒絕時走啟發式，不可直接放行。

    Validates:
    - parsed must be a dict (not list, string, None, etc.)
    - 'confidence' key must be present (primary safety-critical field)
    - confidence must be a numeric type
    - confidence must be in [0.0, 1.0] range
    - 'has_edge' must be bool if present (type safety)
    - 'reason' must be a non-empty string if present (principle 8)
    - 'action' must be one of BUY/SELL/HOLD/SKIP if present
    驗證項目：
    - parsed 必須是 dict
    - 必須包含 'confidence' 鍵
    - confidence 必須是數值型別且在 [0.0, 1.0]
    - has_edge 若存在必須是 bool
    - reason 若存在必須是非空字串
    - action 若存在必須在 VALID_ACTIONS 中
    """
    if not isinstance(parsed, dict):
        return False
    if "confidence" not in parsed:
        return False
    confidence = parsed.get("confidence", -1)
    if not isinstance(confidence, (int, float)):
        return False
    if not (0.0 <= float(confidence) <= 1.0):
        return False

    # has_edge: must be bool if present — fail-closed on type mismatch
    # has_edge 若存在必須是 bool，型別不符則拒絕
    if "has_edge" in parsed and not isinstance(parsed["has_edge"], bool):
        logger.warning(
            "H4 validation: has_edge is not bool (%s) / has_edge 非布林型",
            type(parsed["has_edge"]).__name__,
        )
        return False

    # reason: must be non-empty str if present — principle 8 traceability
    # reason 若存在必須是非空字串（根原則 8：交易可解釋）
    if "reason" in parsed:
        reason = parsed["reason"]
        if not isinstance(reason, str) or not reason.strip():
            logger.warning("H4 validation: reason is empty or not str / reason 為空或非字串")
            return False

    # action: must be in valid set if present — prevent garbage actions
    # action 若存在必須在合法集合內
    if "action" in parsed:
        action = parsed["action"]
        if not isinstance(action, str) or action.upper() not in VALID_ACTIONS:
            logger.warning(
                "H4 validation: action '%s' not in %s / 動作不在合法集合內",
                action, VALID_ACTIONS,
            )
            return False

    return True
