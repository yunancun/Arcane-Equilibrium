"""
E5-P1-4 — Unified LLM call wrapper for the 5-Agent system
==========================================================
Governance refs: DOC-01 §5.13 (cost awareness), §5.14 (zero-external-cost),
                 EX-06 §4 (Strategist), §5 (Guardian), §7 (Analyst)

MODULE_NOTE (中文):
  本模組提供 5-Agent 體系中 LLM 調用的統一封裝層。只封裝重複骨架，
  不改變任何層級的路由決策、prompt 內容、或回退行為。

  設計邊界（重要）：
  - L0（確定性回退 / heuristic）：不走此 wrapper — 每個 Agent 在自己的
    _heuristic_evaluate/_statistical_* 等函式中直接產出結果。
  - L1（Ollama 本地調用）：提供 call_ollama_generate()/call_ollama_judge_edge()/
    call_ollama_classify()；wrapper 負責可用性檢查、計時、成本記錄、異常映射。
  - L1.5 / L2（Claude API）：層級 routing 保留在 ModelRouter；本 wrapper 只提供
    call_ollama_*，Claude 通過原生 ModelRouter 路徑進行。

  保留語義（嚴格零行為改動）：
  - StrategistAgent._ai_evaluate / _evaluate_edge 中的 Ollama 路徑
  - GuardianAgent._handle_event_alert 中的 classify() 調用
  - AnalystAgent._ai_pattern_analysis 中的 generate() 調用
  Wrapper 返回的是與 Ollama client 原生 response 相同的對象
  （rely on .success / .text / .error 欄位），不做二次封裝。

  成本記錄契約：
  - provider 固定為 "ollama"
  - model 由調用方傳入（如 "l1_9b" / "l1_27b"）
  - cost_usd=0.0（本地 Ollama 無現金成本，保留 duration_ms 供 principle 13 審計）

MODULE_NOTE (English):
  Unified wrapper layer for LLM calls in the 5-Agent system. Only wraps duplicated
  boilerplate; does NOT change any tier routing decisions, prompt content, or
  fallback behavior.

  Design boundaries (important):
  - L0 (deterministic heuristic fallback): does NOT go through this wrapper —
    each Agent produces results directly in its own _heuristic_evaluate /
    _statistical_* functions.
  - L1 (local Ollama): provides call_ollama_generate()/judge_edge()/classify();
    wrapper handles availability check, timing, cost recording, error mapping.
  - L1.5 / L2 (Claude API): tier routing stays in ModelRouter; this wrapper only
    exposes call_ollama_*, Claude continues through the existing ModelRouter path.

  Preserved semantics (strict zero-behavior-change):
  - StrategistAgent._ai_evaluate / _evaluate_edge Ollama path
  - GuardianAgent._handle_event_alert classify() call
  - AnalystAgent._ai_pattern_analysis generate() call
  Wrapper returns the same object the Ollama client natively returns (relying
  on .success / .text / .error fields); no secondary wrapping.

  Cost recording contract:
  - provider fixed to "ollama"
  - model supplied by caller (e.g. "l1_9b" / "l1_27b")
  - cost_usd=0.0 (local Ollama has no cash cost; duration_ms retained for
    principle-13 auditability)
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Ollama availability check / Ollama 可用性檢查
# ═══════════════════════════════════════════════════════════════════════════════

def ollama_is_available(client: Optional[Any]) -> bool:
    """
    Safely check whether the Ollama client is non-None and reports available.
    安全地檢查 Ollama client 是否非 None 且報告可用。

    Matches the exact pattern `self._ollama and self._ollama.is_available()`
    used throughout the 5 agents. Any exception from is_available() → False.
    匹配 5 個 agent 中到處出現的 `self._ollama and self._ollama.is_available()` 模式。
    is_available() 拋異常 → 視為 False。
    """
    if client is None:
        return False
    try:
        is_avail = getattr(client, "is_available", None)
        if is_avail is None:
            return False
        return bool(is_avail())
    except Exception as e:  # noqa: BLE001 — fail-closed on unknown client errors
        logger.debug("Ollama is_available() raised: %s", e)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# L1 Ollama call helpers / L1 Ollama 調用輔助
# ═══════════════════════════════════════════════════════════════════════════════

def call_ollama_judge_edge(
    client: Any,
    context: str,
) -> Any:
    """
    Call Ollama client's judge_edge(context) and return the raw response object.
    調用 Ollama client 的 judge_edge(context)，返回原始 response 對象。

    Caller is responsible for parsing response.text and checking response.success.
    This wrapper does NOT swallow exceptions — it re-raises so the caller can
    apply its own fail-closed heuristic fallback (matching original behavior).
    調用方負責解析 response.text 並檢查 response.success。此 wrapper 不吞異常 —
    原樣拋出，讓調用方執行自己的 fail-closed 啟發式回退（與原行為完全一致）。
    """
    return client.judge_edge(context)


def call_ollama_classify(
    client: Any,
    text: str,
    labels: List[str],
) -> Any:
    """
    Call Ollama client's classify(text, labels) and return the raw response.
    調用 Ollama client 的 classify(text, labels)，返回原始 response 對象。

    Used by GuardianAgent for event severity classification.
    Exceptions re-raise so the caller applies its own try/except fallback.
    供 GuardianAgent 用於事件嚴重性分類。異常原樣拋出，調用方處理回退。
    """
    return client.classify(text, labels)


def call_ollama_generate(
    client: Any,
    prompt: str,
    *,
    system: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    think: bool = True,
) -> Any:
    """
    Call Ollama client's generate(prompt, ...) and return the raw response.
    調用 Ollama client 的 generate(prompt, ...)，返回原始 response 對象。

    Used by AnalystAgent for L2 pattern analysis. Keeps the original kwarg set
    (temperature=0.3, max_tokens=1024, think=True) as the default to preserve
    byte-for-byte identical call semantics.
    供 AnalystAgent L2 模式分析使用。保留原始 kwarg 默認值以字節級別等同原調用。
    """
    return client.generate(
        prompt,
        system=system,
        temperature=temperature,
        max_tokens=max_tokens,
        think=think,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Timed call helper / 帶計時的調用輔助
# ═══════════════════════════════════════════════════════════════════════════════

def call_ollama_timed(
    fn: Any,
    *args: Any,
    **kwargs: Any,
) -> tuple[Any, float]:
    """
    Invoke `fn(*args, **kwargs)` and return (response, latency_ms).
    調用 fn(*args, **kwargs)，返回 (response, latency_ms)。

    Convenience for agents that need duration_ms for cost_tracker.record_call().
    Exceptions propagate — caller owns fallback behavior.
    供需要 duration_ms 傳給 cost_tracker.record_call() 的 agent 使用。
    異常原樣拋出，調用方擁有回退邏輯。
    """
    start = time.time()
    resp = fn(*args, **kwargs)
    latency_ms = (time.time() - start) * 1000.0
    return resp, latency_ms
