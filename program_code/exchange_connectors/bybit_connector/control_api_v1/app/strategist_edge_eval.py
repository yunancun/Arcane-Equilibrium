"""
Batch 7 — StrategistAgent Edge Evaluation Sibling
==================================================
Governance refs: EX-06 §4 / CLAUDE.md §九 file-size discipline / G3-08 Phase 4

MODULE_NOTE (中文):
  本模組是 StrategistAgent 的 sibling，承載 edge 評估與 prompt 構建相關的純函數，
  從 strategist_agent.py 拆出 6 個方法以維持主檔在 §九 800 行警告線之下。
  函數一律接受 ``agent: StrategistAgent`` 作為第一個參數，透過 instance 取得
  ``self`` 等價的 lock / stats / config / 委託物件（H1 / H3 ModelRouter / TruthRegistry /
  CognitiveModulator / cost_tracker）。
  主檔保留同名 method 為 1-line delegator，向後兼容所有 callsite + test patch path。

  涵蓋方法（method-as-fn）：
  1. _evaluate_edge — 主入口，先試 Ollama 再回退啟發式
  2. _ai_evaluate — 走 judge_edge() / 含 H4 validation / TSR knowledge_update 暫存 / H5 cost
  3. _evaluate_edge_l1_5 — Claude Sonnet L1.5 路徑 + TSR 閉環（3-3）
  4. _build_prompt_context — 結構化 JSON prompt（含 cognitive / dream / TSR）
  5. _process_knowledge_update — TSR 寫回（cap 0.85/0.90）
  6. _build_route_context — 路由上下文構建（L1.5/L2 升級判斷）

MODULE_NOTE (English):
  StrategistAgent sibling carrying pure helper functions for edge evaluation and
  prompt construction. Extracted 6 methods from strategist_agent.py so the main
  file stays under the §九 800-line warning threshold. Functions take
  ``agent: StrategistAgent`` as the first parameter and access lock / stats /
  config / delegates (H1 / H3 ModelRouter / TruthRegistry / CognitiveModulator /
  cost_tracker) via the instance.
  Main file keeps same-named methods as 1-line delegators for backward
  compatibility with all callsites and test patch paths.

  Covered methods (method-as-fn):
  1. _evaluate_edge — main entry, try Ollama first then heuristic fallback
  2. _ai_evaluate — judge_edge() path with H4 validation, TSR knowledge_update
                    stash, H5 cost tracking
  3. _evaluate_edge_l1_5 — Claude Sonnet L1.5 path + TSR closed loop (3-3)
  4. _build_prompt_context — structured JSON prompt (cognitive/dream/TSR)
  5. _process_knowledge_update — TSR write-back (cap 0.85/0.90)
  6. _build_route_context — routing context for L1.5/L2 upgrade decisions

Hard boundaries (CLAUDE.md §四):
  - max_retries=0 / fail-closed unchanged. AI failure → heuristic fallback.
  - 不變動業務邏輯，只搬位置 (no business-logic change, location-only refactor).
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from .h4_validator import validate_ai_output
from .h_state_invalidator import invalidate_async as _invalidate_h_state_async
from .llm_call_wrapper import call_ollama_judge_edge, ollama_is_available
from .multi_agent_framework import IntelObject
from .strategist_models import EdgeEvaluation, _heuristic_evaluate

if TYPE_CHECKING:  # pragma: no cover — type-checker only / 僅型別檢查
    from .strategist_agent import StrategistAgent

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Route context / 路由上下文
# ─────────────────────────────────────────────────────────────────────────────

def _build_route_context(agent: "StrategistAgent", intel: Any) -> dict:
    """
    Build context dict for ModelRouter L1.5/L2 upgrade decisions.
    構建上下文字典用於 ModelRouter L1.5/L2 升級判斷。

    Extracts relevant fields from intel metadata so ModelRouter can decide
    whether to upgrade from L1 to L1.5 or L2.
    從 intel metadata 提取相關欄位，供 ModelRouter 判斷是否從 L1 升級到 L1.5 或 L2。

    Returns:
        dict with keys matching ModelRouter.route() context spec
    """
    metadata = intel.metadata if isinstance(intel.metadata, dict) else {}
    return {
        "confidence": getattr(intel, "relevance_score", 0.5),
        "amount_pct": metadata.get("position_pct", 0.0),
        "cusum_triggered": metadata.get("cusum_triggered", False),
        "daily_vol_pct": metadata.get("daily_vol_pct", 0.0),
        "is_new_symbol": metadata.get("is_new_symbol", False),
        "weekly_pnl_pct": metadata.get("weekly_pnl_pct", 0.0),
        "param_sharpe_change_pct": metadata.get("param_sharpe_change_pct", 0.0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge update / 知識更新（TSR 寫回）
# ─────────────────────────────────────────────────────────────────────────────

def _process_knowledge_update(
    agent: "StrategistAgent",
    knowledge_update: Any,
    source: str = "cloud_api",
) -> None:
    """Write knowledge_update to TSR (3-3). Principle 10: AI=INFERENCE, caps: cloud 0.90, ai 0.85.
    將 knowledge_update 寫入 TSR（3-3）。原則 10：AI=推斷。上限：cloud 0.90, ai 0.85。"""
    if not agent._truth_registry:
        return
    items = knowledge_update if isinstance(knowledge_update, list) else [knowledge_update]
    cap = 0.90 if source == "cloud_api" else 0.85
    written = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        pattern = item.get("pattern", item.get("claim", ""))[:200]  # Security: cap length / 安全：截斷長度
        if not pattern:
            continue
        try:
            conf = min(float(item.get("confidence", 0.5)), cap)
            obs_count = max(1, min(10000, int(item.get("observation_count", 1))))  # Clamp 1-10000
            agent._truth_registry.register_claim(
                pattern_text=pattern, evidence_source="ai",
                observation_count=obs_count,
                confidence=conf, applies_to_regime=item.get("regime", "all"),
                applies_to_strategy=item.get("strategy", "all"),
            )
            written += 1
            logger.info("TSR write: '%s' (conf=%.2f, src=%s)", pattern[:50], conf, source)
        except Exception as exc:
            logger.warning("TSR write failed: %s", exc)
    if written:
        agent._audit("knowledge_update", {"count": written, "source": source})


# ─────────────────────────────────────────────────────────────────────────────
# L1.5 evaluation / L1.5 評估
# ─────────────────────────────────────────────────────────────────────────────

def _evaluate_edge_l1_5(agent: "StrategistAgent", intel: Any) -> EdgeEvaluation:
    """L1.5 eval with Claude→TSR closed loop (3-3). / L1.5 Claude→TSR 閉環（3-3）。"""
    try:
        with agent._lock:
            agent._last_knowledge_update = None
        evaluation = _evaluate_edge(agent, intel)
        with agent._lock:
            ku = agent._last_knowledge_update
            agent._last_knowledge_update = None
        if ku and agent._truth_registry:
            _process_knowledge_update(agent, ku, source="cloud_api")
        if agent._budget_manager:
            try:
                agent._budget_manager.record_call("l1_5", 0.02)
            except Exception:
                pass
        return evaluation
    except Exception as e:
        logger.warning("L1.5 eval failed, fallback to L1: %s", e)
        return _evaluate_edge(agent, intel)


# ─────────────────────────────────────────────────────────────────────────────
# Prompt context / Prompt 上下文構建
# ─────────────────────────────────────────────────────────────────────────────

def _build_prompt_context(agent: "StrategistAgent", intel: IntelObject) -> str:
    """
    V2: Build structured JSON prompt context for Ollama evaluation.
    V2：構建結構化 JSON prompt 上下文供 Ollama 評估。

    Includes cognitive modulator state and dream engine insights when available,
    per Cognitive Adaptation Spec §6.2.
    包含認知調製器狀態和蒙特卡洛洞察（若可用），依據認知自適應 SPEC §6.2。

    Returns:
        JSON-formatted context string prefixed with evaluation instruction
        帶評估指令前綴的 JSON 格式上下文字串
    """
    # Base intel context / 基礎情報上下文
    context_dict: dict = {
        "symbols": intel.symbols,
        "source": intel.source,
        "sentiment": intel.sentiment.value if hasattr(intel.sentiment, "value") else str(intel.sentiment),
        "relevance": round(intel.relevance_score, 2),
        "data_quality": intel.data_quality.value if hasattr(intel.data_quality, "value") else str(intel.data_quality),
        "freshness_s": intel.freshness_seconds,
        "content": intel.content[:500],
        "regime": agent._current_regime,
    }

    # V2: CognitiveModulator state (if connected)
    # 認知調製器狀態（若已連接）
    if agent._cognitive_modulator is not None:
        try:
            # G8-01 W1 FIX-A：rename `get_current_params` → `get_all_params`
            # （前者並非 CognitiveModulator 公開 API，AttributeError 被外層 try/except
            # 靜默吞掉 → cognitive 欄位永遠缺失，違反 feedback_no_dead_params。）
            # G8-01 W1 FIX-A: rename `get_current_params` → `get_all_params`
            # (former is NOT a CognitiveModulator public API; the AttributeError
            # was silently swallowed by the outer try/except, leaving the
            # cognitive field permanently absent — violates feedback_no_dead_params.)
            cog_params = agent._cognitive_modulator.get_all_params()
            context_dict["cognitive"] = {
                "confidence_floor": round(cog_params.get("confidence_floor", 0.6), 3),
                "qty_ceiling": round(cog_params.get("qty_ceiling", 1.0), 3),
                "stoploss_multiplier": round(cog_params.get("stoploss_multiplier", 1.0), 3),
            }
        except Exception:
            pass  # No cognitive data available — skip silently / 無認知數據，靜默跳過

    # V2: DreamEngine insights (if available via cognitive modulator)
    # 蒙特卡洛洞察（若可用）
    if agent._cognitive_modulator is not None:
        try:
            dream_data = getattr(agent._cognitive_modulator, "last_dream_summary", None)
            if dream_data and isinstance(dream_data, dict):
                context_dict["dream_insights"] = {
                    "suggested_params": dream_data.get("suggested_params"),
                    "confidence": dream_data.get("confidence"),
                }
        except Exception:
            pass  # No dream data — skip silently / 無蒙特卡洛數據，靜默跳過

    # 3-3: Include high-confidence TSR claims in prompt (closed loop)
    # 3-3：在 prompt 中包含高信度 TSR 聲明（閉環）
    if agent._truth_registry:
        try:
            active = agent._truth_registry.get_active_claims(min_confidence=0.5)
            if active:
                context_dict["tsr_claims"] = [
                    {"pattern": c.pattern_text, "confidence": c.confidence,
                     "level": c.cognitive_level.value if hasattr(c.cognitive_level, "value") else str(c.cognitive_level)}
                    for c in active[:5]
                ]
        except Exception:
            pass  # TSR query failure is non-critical / TSR 查詢失敗非關鍵

    # Format as structured text for LLM / 格式化為 LLM 的結構化文本
    try:
        context_json = json.dumps(context_dict, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        # Fallback to plain text if JSON serialization fails
        # JSON 序列化失敗時回退到純文字
        return (
            f"Symbol(s): {', '.join(intel.symbols)}\n"
            f"Source: {intel.source}\n"
            f"Sentiment: {context_dict['sentiment']}\n"
            f"Relevance: {context_dict['relevance']}\n"
            f"Content: {intel.content[:500]}"
        )

    # Prefix with evaluation instruction for judge_edge()
    # 為 judge_edge() 加上評估指令前綴
    return (
        "Evaluate this trading signal. Respond in JSON: "
        '{"has_edge":bool,"confidence":0-1,"reason":"..."}. '
        "Consider cognitive state if present.\n\n"
        + context_json
    )


# ─────────────────────────────────────────────────────────────────────────────
# Edge evaluation / Edge 評估
# ─────────────────────────────────────────────────────────────────────────────

def _evaluate_edge(agent: "StrategistAgent", intel: IntelObject) -> EdgeEvaluation:
    """
    Evaluate whether intel contains a tradeable edge.
    評估情報是否包含可交易優勢。

    Strategy: 1. Try Ollama/Qwen 3.5 judge_edge() first
    2. If unavailable/error → fallback to local heuristic
    3. Never return has_edge=True without evaluation (fail-closed)
    """
    # E5-P1-4: Ollama availability check routed via llm_call_wrapper.
    # E5-P1-4：Ollama 可用性檢查統一走 llm_call_wrapper。
    if ollama_is_available(agent._ollama):
        try:
            return _ai_evaluate(agent, intel)
        except Exception as e:
            logger.warning("AI evaluation failed, falling back to heuristic: %s / AI 評估失敗: %s", e, e)
            with agent._lock:
                agent._stats["errors"] += 1

    with agent._lock:
        agent._stats["heuristic_evaluations"] += 1
    return _heuristic_evaluate(intel, agent.config)


def _ai_evaluate(agent: "StrategistAgent", intel: IntelObject) -> EdgeEvaluation:
    """
    Evaluate edge using Qwen 3.5 via judge_edge().
    使用 Qwen 3.5 的 judge_edge() 評估 edge。
    """
    start = time.time()

    # V2: Use structured JSON prompt with cognitive/dream fields
    # V2：使用含認知/蒙特卡洛欄位的結構化 JSON prompt
    context = _build_prompt_context(agent, intel)

    # E5-P1-4: routed via llm_call_wrapper.call_ollama_judge_edge
    # (thin pass-through — identical call semantics, preserves fail-closed).
    # E5-P1-4：通過 llm_call_wrapper.call_ollama_judge_edge（語義完全等同）。
    response = call_ollama_judge_edge(agent._ollama, context)
    latency_ms = (time.time() - start) * 1000

    with agent._lock:
        agent._stats["ai_evaluations"] += 1

    if not response.success:
        logger.warning("judge_edge returned unsuccessful: %s / judge_edge 返回失敗", response.error)
        with agent._lock:
            agent._stats["heuristic_evaluations"] += 1
        return _heuristic_evaluate(intel, agent.config)

    # Parse JSON response / 解析 JSON 響應
    try:
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(text)

        # H4: Validate AI output structure — delegate to h4_validator module
        # H4 輸出驗證 — 委託給 h4_validator 模組
        if not validate_ai_output(result):
            logger.warning(
                "H4 validation failed for AI output, "
                "falling back to heuristic / H4 驗證失敗，降級到啟發式"
            )
            with agent._lock:
                agent._stats["h4_validation_fail"] = agent._stats.get("h4_validation_fail", 0) + 1
                agent._stats["heuristic_evaluations"] += 1
            _invalidate_h_state_async("h4.validation_fail")  # G3-08 Phase 3 Sub-task 3-2
            return _heuristic_evaluate(intel, agent.config)

        # G3-08 Phase 3 Sub-task 3-2 — H4 PASS: count + hint (was silent gap).
        # G3-08 Phase 3 Sub-task 3-2 — H4 通過：補計數與提示（G3-08 前 silent gap）。
        with agent._lock:
            agent._stats["h4_validation_pass"] = agent._stats.get("h4_validation_pass", 0) + 1
        _invalidate_h_state_async("h4.validation_pass")

        has_edge = bool(result.get("has_edge", False))
        confidence = float(result.get("confidence", 0.0))
        reason = str(result.get("reason", "AI evaluation"))

        # 3-3: Stash knowledge_update for L1.5 TSR write-back
        # 3-3：暫存 knowledge_update 供 L1.5 寫回 TSR
        ku = result.get("knowledge_update")
        if ku:
            with agent._lock:
                agent._last_knowledge_update = ku

        # H5: Record Ollama call for cost/resource awareness (principle 13)
        # H5 成本感知：記錄 Ollama 調用（根原則 13）
        if agent.cost_tracker is not None:
            try:
                record_fn = getattr(agent.cost_tracker, "record_call", None)
                if record_fn is not None:
                    record_fn(provider="ollama", model="l1_9b", duration_ms=latency_ms, cost_usd=0.0)
                with agent._lock:
                    agent._stats["ollama_calls_tracked"] += 1
            except Exception:
                logger.warning("cost_tracker.record_call failed, non-fatal / 成本記錄失敗，非致命")

        return EdgeEvaluation(
            has_edge=has_edge,
            confidence=confidence,
            reason=reason,
            source="ai",
            latency_ms=latency_ms,
        )
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Failed to parse judge_edge response: %s / 解析 judge_edge 響應失敗: %s", e, e)
        return EdgeEvaluation(
            has_edge=False,
            confidence=0.0,
            reason=f"AI response parse error: {e}",
            source="ai_parse_error",
            latency_ms=latency_ms,
        )
